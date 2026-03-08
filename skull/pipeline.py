"""Pipeline orchestrator — STT → LLM → TTS → playback with barge-in."""

import asyncio
import io
import logging
import time

import numpy as np

from skull.audio import cue_manager, player
from skull.audio.aec import EchoCanceller
from skull.audio.recorder import detect_barge_in
from skull.config import VAD_BARGE_IN_THRESHOLD
from skull.llm import openclaw_client
from skull.session import Session, SessionState
from skull.stt import whisper_client
from skull.transcript import logger as tx_log
from skull.tts import kokoro_client

log = logging.getLogger(__name__)

# Signals that a query likely needs external/real-time data (tool call)
_TOOL_CALL_SIGNALS = [
    "weather", "temperature", "forecast",
    "news", "score", "price", "stock",
    "look up", "search", "find out", "check on",
    "right now", "latest", "current",
    "happening", "send email", "send a message",
    "calendar", "schedule", "appointment",
    "play music", "play song",
]

# Filler delays (seconds)
_FILLER_DELAY_TOOL = 0.5      # Immediate — we know it'll be slow
_FILLER_DELAY_GENERATION = 2.5  # Wait — LLM might respond before this


def _classify_query(text: str) -> str:
    """Classify a query as 'tool' or 'generation' based on content signals."""
    lower = text.lower()
    for signal in _TOOL_CALL_SIGNALS:
        if signal in lower:
            return "tool"
    return "generation"


async def run_once(
    wav_bytes: bytes,
    rec_duration: float,
    wake_confidence: float,
    instructions: str = "",
    session: Session | None = None,
    mic_stream=None,
) -> None:
    """Execute one pipeline cycle: transcribe → respond → speak.

    Args:
        wav_bytes: WAV audio data from the recorder.
        rec_duration: Recording duration in seconds.
        wake_confidence: Wake word detection confidence (for logging).
        instructions: System instructions (SOUL.md content).
        session: Active conversation session (for state tracking).
        mic_stream: Active MicStream for barge-in monitoring during playback.
    """
    pipeline_t0 = time.monotonic()
    first_audio_t: float | None = None
    tts_chunks: list[dict] = []
    llm_first_token_ms = 0.0
    llm_total_ms = 0.0
    full_response = ""
    recording_ms = rec_duration * 1000

    # ── STT ───────────────────────────────────────────────────
    stt_t0 = time.monotonic()
    try:
        transcript = await whisper_client.transcribe(wav_bytes)
    except Exception:
        log.exception("STT failed")
        cue_manager.play_error("stt")
        return

    stt_ms = (time.monotonic() - stt_t0) * 1000

    if not transcript.strip():
        log.info("Empty transcript — returning")
        return

    log.info("User said: %r", transcript)

    # ── Build context for interrupted responses ────────────────
    context_prefix = ""
    if session and session.interrupted_after:
        context_prefix = (
            f"[Your previous response was interrupted after: "
            f"'{session.interrupted_after}'. The user may be correcting or redirecting.]\n\n"
        )
        session.interrupted_after = ""

    # ── LLM → TTS → Playback (producer-consumer with barge-in) ─
    llm_t0 = time.monotonic()
    cancel_event = asyncio.Event()
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
    play_queue: asyncio.Queue[tuple[bytes, str] | None] = asyncio.Queue()
    filler_played = False
    barge_in_detected = False

    # Initialize AEC for barge-in detection
    aec = None
    if mic_stream:
        try:
            aec = EchoCanceller(frame_size=256, sample_rate=16000)
        except Exception:
            log.warning("AEC init failed — barge-in will use raw audio")

    async def _llm_producer():
        """Read LLM SSE stream, buffer sentences, put to tts_queue."""
        nonlocal llm_first_token_ms, full_response, filler_played

        filler_timer_task = None

        # Classify query to choose filler strategy
        query_type = _classify_query(transcript)
        if query_type == "tool":
            filler_delay = _FILLER_DELAY_TOOL
            filler_category = "ack_tool"
        else:
            filler_delay = _FILLER_DELAY_GENERATION
            filler_category = "ack_short"

        log.info("Query classified as '%s' — filler at %.1fs (%s)",
                 query_type, filler_delay, filler_category)

        async def _filler_timer():
            """Play single ack after appropriate delay."""
            nonlocal filler_played
            await asyncio.sleep(filler_delay)
            if not cancel_event.is_set() and not filler_played:
                filler_played = True
                log.info("Playing %s filler (%.1fs elapsed)", filler_category, filler_delay)
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, cue_manager.play_random, filler_category, True
                )

        try:
            filler_timer_task = asyncio.create_task(_filler_timer())

            async for sentence in openclaw_client.stream_sentences(
                context_prefix + transcript, instructions=instructions
            ):
                if cancel_event.is_set():
                    break

                if filler_timer_task and not filler_timer_task.done():
                    filler_timer_task.cancel()

                if not full_response:
                    llm_first_token_ms = (time.monotonic() - llm_t0) * 1000

                full_response += sentence + " "
                log.info("LLM sentence: %r", sentence)
                await tts_queue.put(sentence)

        except Exception:
            log.exception("LLM streaming failed")
            if not filler_played:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, cue_manager.play_error, "connection")
        finally:
            if filler_timer_task and not filler_timer_task.done():
                filler_timer_task.cancel()
            await tts_queue.put(None)

    async def _tts_worker():
        """Synthesize + vox filter sentences from tts_queue."""
        while True:
            sentence = await tts_queue.get()
            if sentence is None or cancel_event.is_set():
                await play_queue.put(None)
                break

            tts_t0 = time.monotonic()
            try:
                wav_audio = await kokoro_client.synthesize_with_vox(sentence)
            except Exception:
                log.exception("TTS failed for: %r", sentence[:40])
                continue

            tts_ms = (time.monotonic() - tts_t0) * 1000

            if wav_audio is None:
                log.warning("Skipping unspeakable: %r", sentence[:40])
                continue

            tts_chunks.append({
                "text": sentence,
                "tts_ms": round(tts_ms, 1),
            })

            await play_queue.put((wav_audio, sentence))

    async def _player_worker():
        """Play audio chunks with barge-in monitoring."""
        nonlocal first_audio_t, barge_in_detected

        while True:
            item = await play_queue.get()
            if item is None or cancel_event.is_set():
                break

            wav_audio, sentence = item

            if first_audio_t is None:
                first_audio_t = time.monotonic()

            if session:
                session.transition(SessionState.SPEAKING)
                session.last_spoken_sentence = sentence

            play_t0 = time.monotonic()

            if mic_stream and mic_stream.is_active:
                # Feed playback audio to AEC as reference signal
                if aec:
                    try:
                        import wave as _wave
                        _wf = _wave.open(io.BytesIO(wav_audio), "rb")
                        _raw = _wf.readframes(_wf.getnframes())
                        _rate = _wf.getframerate()
                        _wf.close()
                        # Downsample to 16kHz if needed
                        if _rate != 16000:
                            _samples = np.frombuffer(_raw, dtype=np.int16)
                            _factor = _rate // 16000
                            _downsampled = _samples[::_factor]
                            aec.feed_playback(_downsampled.tobytes())
                        else:
                            aec.feed_playback(_raw)
                    except Exception:
                        log.warning("Failed to feed playback to AEC")

                # Play with barge-in monitoring
                play_task = asyncio.create_task(player.play(wav_audio))
                barge_task = asyncio.create_task(
                    detect_barge_in(mic_stream, vad_threshold=VAD_BARGE_IN_THRESHOLD, aec=aec)
                )

                done, pending = await asyncio.wait(
                    {play_task, barge_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if barge_task in done and barge_task.result():
                    # Barge-in! Cancel playback and pipeline
                    log.info("Barge-in during: %r", sentence[:40])
                    barge_in_detected = True
                    player.cancel()
                    cancel_event.set()
                    play_task.cancel()
                    if session:
                        session.interrupted_after = sentence
                    break
                else:
                    # Playback completed normally, cancel barge-in monitor
                    barge_task.cancel()
            else:
                # No mic stream — just play
                await player.play(wav_audio)

            play_ms = (time.monotonic() - play_t0) * 1000

            for chunk in tts_chunks:
                if chunk["text"] == sentence and "play_ms" not in chunk:
                    chunk["play_ms"] = round(play_ms, 1)
                    break

    try:
        await asyncio.gather(
            _llm_producer(),
            _tts_worker(),
            _player_worker(),
        )
    except Exception:
        log.exception("Pipeline gather failed")
        cancel_event.set()

    llm_total_ms = (time.monotonic() - llm_t0) * 1000
    total_ms = (time.monotonic() - pipeline_t0) * 1000
    ttfa_ms = ((first_audio_t - pipeline_t0) * 1000) if first_audio_t else 0.0

    log.info(
        "Pipeline complete: total=%.0fms, TTFA=%.0fms, STT=%.0fms, LLM=%.0fms%s",
        total_ms, ttfa_ms, stt_ms, llm_total_ms,
        " [BARGE-IN]" if barge_in_detected else "",
    )

    # ── Log transcript ────────────────────────────────────────
    try:
        tx_log.log_run(
            wake_confidence=wake_confidence,
            recording_duration_ms=recording_ms,
            stt_text=transcript,
            stt_ms=stt_ms,
            llm_first_token_ms=llm_first_token_ms,
            llm_total_ms=llm_total_ms,
            llm_response=full_response.strip(),
            tts_chunks=tts_chunks,
            total_pipeline_ms=total_ms,
            time_to_first_audio_ms=ttfa_ms,
        )
    except Exception:
        log.exception("Failed to log transcript")
