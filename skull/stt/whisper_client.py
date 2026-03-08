"""STT client — async Whisper transcription via Faster-Whisper API."""

import logging
import time

import httpx

from skull.config import WHISPER_URL, WHISPER_MODEL, WHISPER_TIMEOUT

log = logging.getLogger(__name__)

# Persistent connection pool (reused across requests)
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=WHISPER_TIMEOUT)
    return _client


async def transcribe(audio_bytes: bytes, mime: str = "audio/wav") -> str:
    """Send audio to Whisper and return the transcript text.

    Args:
        audio_bytes: Raw audio data (WAV or Opus).
        mime: MIME type of the audio data.

    Returns:
        Transcribed text string.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        httpx.TimeoutException: On timeout.
    """
    client = await _get_client()
    ext = "opus" if "opus" in mime else "wav"

    t0 = time.monotonic()
    response = await client.post(
        WHISPER_URL,
        files={"file": (f"audio.{ext}", audio_bytes, mime)},
        data={"model": WHISPER_MODEL, "language": "en"},
    )
    response.raise_for_status()
    elapsed_ms = (time.monotonic() - t0) * 1000

    text = response.json().get("text", "").strip()
    log.info("STT: %.0fms, %d bytes → %r", elapsed_ms, len(audio_bytes), text[:80])
    return text


async def close():
    """Shut down the connection pool."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
