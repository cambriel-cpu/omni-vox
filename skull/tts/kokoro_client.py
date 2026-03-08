"""TTS client — Kokoro with Opus output and vox-caster filter."""

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from skull.config import (
    KOKORO_FORMAT,
    KOKORO_MODEL,
    KOKORO_TIMEOUT,
    KOKORO_URL,
    KOKORO_VOICE,
    VOX_FILTER,
)

log = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=KOKORO_TIMEOUT)
    return _client


async def synthesize(text: str) -> bytes:
    """Generate speech audio from text via Kokoro TTS.

    Returns raw audio bytes (Opus or WAV depending on config).
    """
    client = await _get_client()

    t0 = time.monotonic()
    response = await client.post(
        KOKORO_URL,
        json={
            "model": KOKORO_MODEL,
            "voice": KOKORO_VOICE,
            "input": text,
            "response_format": KOKORO_FORMAT,
        },
    )
    response.raise_for_status()
    audio = response.content
    elapsed_ms = (time.monotonic() - t0) * 1000

    log.info("TTS: %.0fms, %d bytes, %r", elapsed_ms, len(audio), text[:60])
    return audio


def apply_vox_filter(audio_bytes: bytes) -> bytes:
    """Apply the vox-caster filter via ffmpeg.

    Takes Opus/WAV input, applies the heavy vox-caster filter chain,
    returns WAV PCM suitable for ALSA playback.

    Uses a temp file for input because ffmpeg cannot detect Opus
    format from a pipe (needs seekable container headers).
    """
    t0 = time.monotonic()

    # Write input to temp file — ffmpeg can't detect Opus from pipe
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        in_path = tmp_in.name

    # Output to temp file too — ffmpeg can't write valid WAV headers
    # to a pipe (can't seek back to update data size in header)
    out_path = in_path + ".wav"

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", in_path,
                "-af", VOX_FILTER,
                "-ar", "48000",
                "-ac", "1",
                out_path,
            ],
            capture_output=True,
            timeout=10,
        )

        if proc.returncode != 0:
            log.error("ffmpeg vox filter failed: %s", proc.stderr.decode()[-200:])
            raise RuntimeError("Vox filter failed")

        with open(out_path, "rb") as f:
            wav_data = f.read()
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    elapsed_ms = (time.monotonic() - t0) * 1000
    log.info("Vox filter: %.0fms, %d → %d bytes", elapsed_ms, len(audio_bytes), len(wav_data))
    return wav_data


def _clean_for_speech(text: str) -> str:
    """Strip markdown, tags, and non-speakable characters for TTS."""
    import re
    # Remove [[tag]] and [[/tag]] style tags (e.g. [[tts]], [[reply_to_current]])
    text = re.sub(r'\[\[/?[^\]]*\]\]', '', text)
    # Remove markdown bold/italic
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    # Remove markdown links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove backticks
    text = text.replace('`', '')
    # Remove emoji (basic pattern)
    text = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]', '', text)
    return text.strip()


async def synthesize_with_vox(text: str) -> bytes | None:
    """Generate speech and apply vox-caster filter. Returns WAV PCM.

    Returns None if the text produces no speakable audio (e.g. emoji-only).
    """
    text = _clean_for_speech(text)
    if not text:
        log.info("Text empty after cleanup — skipping TTS")
        return None
    opus_audio = await synthesize(text)
    if len(opus_audio) < 200:
        log.warning("TTS output too small (%d bytes) — likely unspeakable text, skipping", len(opus_audio))
        return None
    return apply_vox_filter(opus_audio)


async def close():
    """Shut down the connection pool."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
