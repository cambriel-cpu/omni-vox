"""Omni Vox Skull — Headless voice assistant entry point.

"Phone call" model: wake word picks up the call, mic stays open for
the entire conversation, hang up on silence timeout.

Session state machine:
  IDLE → SESSION_OPEN → LISTENING → PROCESSING → SPEAKING → FOLLOW_UP
                                                      ↓ (barge-in)
                                                   LISTENING
  FOLLOW_UP → LISTENING (speech) | SESSION_CLOSE (timeout) → IDLE
"""

import asyncio
import logging
from pathlib import Path

from skull import pipeline
from skull.audio import cue_manager
from skull.audio.mic_stream import MicStream
from skull.audio.recorder import record_speech_from_stream
from skull.config import SOUL_PATH
from skull.session import Session, SessionState
from skull.wake_word.detector import WakeWordDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("omni-vox-skull")

# Seconds to wait after session close before re-enabling wake word.
_POST_SESSION_COOLDOWN = 3.0


def _load_soul() -> str:
    """Load SOUL.md for system instructions."""
    path = Path(SOUL_PATH)
    if path.exists():
        return path.read_text()
    log.warning("SOUL.md not found at %s", SOUL_PATH)
    return ""


async def _health_check() -> bool:
    """Verify all upstream services are reachable."""
    import httpx

    checks = {
        "Whisper STT": "http://100.109.78.64:8000/health",
        "Kokoro TTS": "http://100.109.78.64:8880/health",
    }

    ok = True
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in checks.items():
            try:
                r = await client.get(url)
                if r.status_code < 400:
                    log.info("✓ %s — reachable", name)
                else:
                    log.warning("✗ %s — status %d", name, r.status_code)
                    ok = False
            except Exception as e:
                log.warning("✗ %s — %s", name, e)
                ok = False

    return ok


async def _warmup() -> None:
    """Pre-load models and warm up services."""
    from skull.audio.recorder import _get_vad
    _get_vad()
    log.info("Silero VAD pre-loaded")

    from skull.stt import whisper_client
    import io, time as _time, wave
    _warm_t0 = _time.monotonic()
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * 16000)
        await whisper_client.transcribe(buf.getvalue())
        _warm_ms = (_time.monotonic() - _warm_t0) * 1000
        log.info("Whisper STT warmed up (%.0fms)", _warm_ms)
    except Exception as e:
        log.warning("Whisper warmup failed: %s", e)


async def main():
    log.info("═══ Omni Vox Skull starting ═══")

    healthy = await _health_check()
    if not healthy:
        log.warning("Some services unreachable — continuing anyway")

    soul = _load_soul()
    if soul:
        log.info("SOUL.md loaded (%d chars)", len(soul))

    await _warmup()

    detector = WakeWordDetector()
    session = Session()
    confidence = 0.0
    log.info("═══ Ready — listening for wake word ═══")

    while True:
        try:
            # ── IDLE: Wait for wake word ─────────────────────────
            confidence, pre_roll = await detector.wait_for_wake_word()
            session.start()

            # Play wake cue (non-blocking via dmix)
            cue_manager.play_wake_cue()

            # ── Open the "phone call" — start persistent mic ─────
            mic = MicStream()
            await mic.start()

            try:
                await _run_session(mic, session, soul, confidence)
            finally:
                # ── Hang up — close mic ──────────────────────────
                await mic.stop()
                session.end()

            # Post-session cooldown to prevent false re-triggers
            log.info("Cooldown %.1fs before re-listening", _POST_SESSION_COOLDOWN)
            await asyncio.sleep(_POST_SESSION_COOLDOWN)

        except KeyboardInterrupt:
            log.info("Shutting down (KeyboardInterrupt)")
            break
        except Exception:
            log.exception("Main loop error — resetting to IDLE")
            session.end()
            await asyncio.sleep(1)

    # Cleanup
    from skull.llm import openclaw_client
    from skull.stt import whisper_client
    from skull.tts import kokoro_client
    await whisper_client.close()
    await openclaw_client.close()
    await kokoro_client.close()
    log.info("═══ Omni Vox Skull stopped ═══")


async def _run_session(mic: MicStream, session: Session, soul: str, confidence: float):
    """Run a conversation session with a persistent mic stream.
    
    This is the "phone call" — mic is open for the entire session.
    """
    while True:
        if session.state == SessionState.SESSION_OPEN:
            # ── Wait for initial speech ──────────────────────
            session.transition(SessionState.LISTENING)
            wav_bytes, rec_duration = await record_speech_from_stream(
                mic, no_speech_timeout=session.open_timeout,
            )

            if not wav_bytes or rec_duration < 0.3:
                log.info("No speech after wake word — closing session")
                session.transition(SessionState.SESSION_CLOSE)
                cue_manager.play_close_cue()
                return

        elif session.state == SessionState.FOLLOW_UP:
            # ── Wait for follow-up speech ────────────────────
            log.info("Listening for follow-up (%.1fs timeout)",
                     session.follow_up_timeout)
            wav_bytes, rec_duration = await record_speech_from_stream(
                mic, no_speech_timeout=session.follow_up_timeout,
            )

            if not wav_bytes or rec_duration < 0.3:
                log.info("No follow-up speech — closing session")
                session.transition(SessionState.SESSION_CLOSE)
                cue_manager.play_close_cue()
                return

            session.transition(SessionState.LISTENING)

        else:
            log.warning("Unexpected state %s in session — closing",
                        session.state.value)
            return

        # ── Process speech ───────────────────────────────────
        session.transition(SessionState.PROCESSING)
        session.increment_turn()

        try:
            await pipeline.run_once(
                wav_bytes=wav_bytes,
                rec_duration=rec_duration,
                wake_confidence=confidence if session.turn_count == 1 else 0.0,
                instructions=soul,
                session=session,
                mic_stream=mic,
            )
        except Exception:
            log.exception("Pipeline error")
            cue_manager.play_error("connection")

        # ── After response, go to follow-up ──────────────────
        session.transition(SessionState.FOLLOW_UP)

        # Check session expiry
        if session.is_expired:
            log.info("Session expired (max duration) — closing")
            cue_manager.play_close_cue()
            return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
