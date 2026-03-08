"""Audio player — queued WAV playback via ALSA with cancellation."""

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from skull.config import ALSA_PLAYBACK_DEVICE, CUES_DIR

log = logging.getLogger(__name__)

# Active playback process (for cancellation / barge-in)
_current_proc: subprocess.Popen | None = None
_is_playing: bool = False


def is_playing() -> bool:
    """Return True if audio is currently being played."""
    return _is_playing


def play_sync(wav_bytes: bytes) -> None:
    """Play WAV audio through ALSA. Blocking call.
    
    Waits for previous playback to fully complete before starting.
    """
    global _current_proc, _is_playing

    # Wait for any previous playback to finish
    if _current_proc is not None and _current_proc.poll() is None:
        log.warning("Previous aplay still running — waiting...")
        _current_proc.wait(timeout=30)

    t0 = time.monotonic()
    proc = subprocess.Popen(
        ["aplay", "-D", ALSA_PLAYBACK_DEVICE],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _current_proc = proc
    _is_playing = True

    try:
        _, stderr = proc.communicate(input=wav_bytes, timeout=30)
        elapsed_ms = (time.monotonic() - t0) * 1000
        if proc.returncode != 0:
            log.error("aplay failed (rc=%d): %s", proc.returncode, stderr.decode()[-200:])
        else:
            log.info("Playback complete: %.0fms, %d bytes", elapsed_ms, len(wav_bytes))
    except subprocess.TimeoutExpired:
        proc.kill()
        log.warning("Playback timed out after 30s")
    finally:
        _current_proc = None
        _is_playing = False


async def play(wav_bytes: bytes) -> None:
    """Play WAV audio through ALSA. Non-blocking async wrapper."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, play_sync, wav_bytes)


def play_cue(name: str) -> None:
    """Play a pre-rendered audio cue by name. Blocking."""
    path = Path(CUES_DIR) / f"{name}.wav"
    if not path.exists():
        log.warning("Audio cue not found: %s", path)
        return

    global _is_playing
    _is_playing = True
    try:
        subprocess.run(
            ["aplay", "-D", ALSA_PLAYBACK_DEVICE, str(path)],
            timeout=5,
            check=False,
            capture_output=True,
        )
    finally:
        _is_playing = False


def play_cue_async(name: str) -> None:
    """Play a pre-rendered audio cue non-blocking (fire and forget)."""
    import threading
    path = Path(CUES_DIR) / f"{name}.wav"
    if not path.exists():
        log.warning("Audio cue not found: %s", path)
        return

    def _play():
        global _is_playing
        _is_playing = True
        try:
            subprocess.run(
                ["aplay", "-D", ALSA_PLAYBACK_DEVICE, str(path)],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        finally:
            _is_playing = False

    threading.Thread(target=_play, daemon=True).start()


def cancel() -> None:
    """Stop any active playback (for barge-in)."""
    global _current_proc, _is_playing
    if _current_proc and _current_proc.poll() is None:
        _current_proc.kill()
        _current_proc = None
        _is_playing = False
        log.info("Playback cancelled (barge-in)")
