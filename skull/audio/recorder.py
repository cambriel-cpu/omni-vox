"""Audio recorder — speech capture via shared MicStream with Silero VAD.

Features speculative STT: on first silence gap (0.5s), sends audio to
Whisper to check if the utterance is a complete thought. If so, accepts
immediately (saving ~1s). If fragment, continues recording with normal timeout.
"""

import asyncio
import io
import logging
import time
import wave

import numpy as np
import torch

from skull.config import (
    CHANNELS,
    SAMPLE_RATE,
    VAD_MAX_DURATION,
    VAD_MIN_SPEECH_DURATION,
    VAD_SILENCE_TIMEOUT,
    VAD_SPEECH_THRESHOLD,
)

log = logging.getLogger(__name__)

# Silero VAD model (lazy-loaded)
_vad_model = None

# Speculative STT: early silence threshold before checking completeness
_SPECULATIVE_SILENCE = 0.5  # seconds

# Words that suggest an incomplete thought when at the end
_DANGLING_WORDS = frozenset({
    "about", "and", "but", "or", "the", "a", "an",
    "in", "on", "for", "to", "with", "of", "that", "which",
    "who", "where", "when", "how", "what", "if", "then",
    "like", "from", "at", "by", "so", "because", "since",
    "my", "your", "their", "its", "our", "this", "these",
    "um", "uh", "well",
})


def _get_vad():
    """Load Silero VAD model (cached after first call)."""
    global _vad_model
    if _vad_model is None:
        model, _ = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", trust_repo=True
        )
        _vad_model = model
        log.info("Silero VAD loaded")
    return _vad_model


def _is_complete_thought(text: str) -> bool:
    """Check if transcribed text appears to be a complete utterance.
    
    Returns True if the text ends with sentence-terminal punctuation
    and doesn't end with a dangling word (preposition, conjunction, etc.).
    """
    text = text.strip()
    if not text:
        return False

    words = text.split()
    if len(words) < 2:
        return False

    # Must end with sentence-terminal punctuation
    if text[-1] not in ".?!":
        return False

    # Check the last real word (strip punctuation)
    last_word = words[-1].rstrip(".?!,;:").lower()
    if last_word in _DANGLING_WORDS:
        return False

    return True


def _build_wav(audio_chunks: list[bytes]) -> bytes:
    """Build WAV from raw PCM chunks."""
    raw = b"".join(audio_chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw)
    return buf.getvalue()


async def record_speech_from_stream(
    mic_stream,
    vad_threshold: float | None = None,
    no_speech_timeout: float = 8.0,
) -> tuple[bytes, float]:
    """Capture speech from a running MicStream until silence is detected.

    Uses speculative STT: after 0.5s of silence, sends audio to Whisper
    to check if the utterance is complete. If so, returns immediately.
    Otherwise continues recording with the normal silence timeout.

    Args:
        mic_stream: Active MicStream instance.
        vad_threshold: Override VAD speech probability threshold.
        no_speech_timeout: Seconds to wait for any speech before giving up.

    Returns:
        Tuple of (wav_bytes, duration_seconds). Empty bytes if no speech.
    """
    vad = _get_vad()
    threshold = vad_threshold if vad_threshold is not None else VAD_SPEECH_THRESHOLD

    all_audio: list[bytes] = []
    speech_started = False
    speech_start_time: float | None = None
    speech_confirmed = False
    silence_start: float | None = None
    speculative_check_done = False
    t0 = time.monotonic()

    log.info("Recording started — waiting for speech...")

    while True:
        elapsed = time.monotonic() - t0
        if elapsed > VAD_MAX_DURATION:
            log.info("Max recording duration reached (%.1fs)", elapsed)
            break

        chunk = await mic_stream.read_chunk()
        if chunk is None:
            log.warning("Mic stream ended unexpectedly")
            break

        all_audio.append(chunk)

        # VAD check
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(samples)
        speech_prob = vad(tensor, SAMPLE_RATE).item()

        if speech_prob > threshold:
            if not speech_started:
                speech_started = True
                speech_start_time = time.monotonic()
                log.info("Speech detected (prob=%.2f)", speech_prob)
            silence_start = None
            # Reset speculative check if speech resumes
            speculative_check_done = False

            if not speech_confirmed and speech_start_time:
                if time.monotonic() - speech_start_time >= VAD_MIN_SPEECH_DURATION:
                    speech_confirmed = True

        elif speech_confirmed:
            if silence_start is None:
                silence_start = time.monotonic()
            else:
                silence_duration = time.monotonic() - silence_start

                # Speculative STT check at 0.5s silence
                if (not speculative_check_done
                        and silence_duration >= _SPECULATIVE_SILENCE):
                    speculative_check_done = True
                    wav_bytes = _build_wav(all_audio)
                    
                    try:
                        from skull.stt import whisper_client
                        spec_t0 = time.monotonic()
                        transcript = await whisper_client.transcribe(wav_bytes)
                        spec_ms = (time.monotonic() - spec_t0) * 1000

                        if _is_complete_thought(transcript):
                            log.info(
                                "Speculative STT: complete thought detected "
                                "(%.0fms, %r) — accepting early",
                                spec_ms, transcript[:60],
                            )
                            duration = time.monotonic() - t0
                            log.info("Recorded %.1fs of audio (%d bytes WAV)",
                                     duration, len(wav_bytes))
                            return wav_bytes, duration
                        else:
                            log.info(
                                "Speculative STT: fragment detected "
                                "(%.0fms, %r) — continuing recording",
                                spec_ms, transcript[:60],
                            )
                    except Exception:
                        log.warning("Speculative STT failed — falling back to timeout")

                # Normal silence timeout
                if silence_duration > VAD_SILENCE_TIMEOUT:
                    log.info("Silence timeout — recording complete")
                    break

        # No speech timeout
        if not speech_started and elapsed > no_speech_timeout:
            log.info("No speech detected after %.0fs — aborting", no_speech_timeout)
            return b"", 0.0

    duration = time.monotonic() - t0

    if not all_audio or not speech_confirmed:
        if speech_started and not speech_confirmed:
            log.info("Speech too brief (< %.1fs) — treating as noise",
                     VAD_MIN_SPEECH_DURATION)
        return b"", 0.0

    wav_bytes = _build_wav(all_audio)
    log.info("Recorded %.1fs of audio (%d bytes WAV)", duration, len(wav_bytes))
    return wav_bytes, duration


async def detect_barge_in(
    mic_stream,
    vad_threshold: float = 0.85,
    min_duration: float = 0.3,
    aec=None,
) -> bool:
    """Monitor mic stream for speech during playback (barge-in detection).

    If an AEC (echo canceller) is provided, mic audio is processed through
    it first to remove speaker bleed before VAD analysis.

    Returns True as soon as barge-in speech is confirmed.

    Args:
        mic_stream: Active MicStream instance.
        vad_threshold: High threshold to distinguish speech from speaker bleed.
        min_duration: Minimum speech duration to confirm barge-in.
        aec: Optional EchoCanceller instance for removing speaker bleed.

    Returns:
        True if barge-in detected, False if stream ends.
    """
    vad = _get_vad()
    speech_start: float | None = None

    while True:
        chunk = await mic_stream.read_chunk()
        if chunk is None:
            return False

        # Apply AEC if available — process in 256-sample frames
        if aec:
            frame_bytes = 256 * 2  # 256 samples * 2 bytes per sample
            cleaned_parts = []
            offset = 0
            while offset + frame_bytes <= len(chunk):
                frame = chunk[offset:offset + frame_bytes]
                cleaned = aec.process(frame)
                cleaned_parts.append(cleaned)
                offset += frame_bytes
            # Handle remainder (pass through)
            if offset < len(chunk):
                cleaned_parts.append(chunk[offset:])
            chunk = b"".join(cleaned_parts)

        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(samples)
        speech_prob = vad(tensor, SAMPLE_RATE).item()
        raw_peak = int(np.abs(np.frombuffer(chunk, dtype=np.int16)).max())

        if speech_prob > vad_threshold and raw_peak > 1000:
            if speech_start is None:
                speech_start = time.monotonic()
                log.info("Possible barge-in (prob=%.2f, peak=%d, aec=%s)",
                         speech_prob, raw_peak, "on" if aec else "off")
            elif time.monotonic() - speech_start >= min_duration:
                log.info("Barge-in confirmed (%.1fs of speech)",
                         time.monotonic() - speech_start)
                return True
        else:
            speech_start = None
