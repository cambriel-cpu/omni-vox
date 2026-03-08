"""Persistent microphone capture via ALSA arecord subprocess.

One arecord process runs for the entire conversation session.
Different consumers (wake word, VAD, barge-in) read from the same stream.
"""

import asyncio
import collections
import logging
import subprocess

from skull.config import ALSA_CAPTURE_DEVICE, CHANNELS, SAMPLE_RATE

log = logging.getLogger(__name__)

# Chunk size for Silero VAD (512 samples = 32ms at 16kHz)
CHUNK_SAMPLES = 512
CHUNK_BYTES = CHUNK_SAMPLES * 2  # 16-bit mono


class MicStream:
    """Persistent microphone capture for a conversation session.
    
    Usage:
        mic = MicStream()
        await mic.start()
        
        # Read chunks (blocks until audio available)
        chunk = await mic.read_chunk()
        
        # When session ends
        await mic.stop()
    """

    def __init__(self, chunk_bytes: int = CHUNK_BYTES):
        self._proc: subprocess.Popen | None = None
        self._chunk_bytes = chunk_bytes
        self._active = False
        self._loop: asyncio.AbstractEventLoop | None = None
        # Ring buffer for pre-roll (last ~2s of audio)
        max_chunks = int(2.0 * SAMPLE_RATE * 2 / chunk_bytes)
        self._ring: collections.deque[bytes] = collections.deque(maxlen=max_chunks)

    async def start(self) -> None:
        """Start arecord subprocess."""
        if self._active:
            return

        self._loop = asyncio.get_running_loop()
        self._proc = subprocess.Popen(
            [
                "arecord",
                "-D", ALSA_CAPTURE_DEVICE,
                "-f", "S16_LE",
                "-r", str(SAMPLE_RATE),
                "-c", str(CHANNELS),
                "-t", "raw",
                "-q",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._active = True
        self._ring.clear()
        log.info("Mic stream started (device=%s, chunk=%d bytes)",
                 ALSA_CAPTURE_DEVICE, self._chunk_bytes)

    async def read_chunk(self) -> bytes | None:
        """Read one chunk from the mic. Returns None if stream is closed."""
        if not self._active or not self._proc:
            return None

        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(
                None, self._proc.stdout.read, self._chunk_bytes
            )
        except Exception:
            return None

        if not raw or len(raw) < self._chunk_bytes:
            return None

        # Add to ring buffer for pre-roll access
        self._ring.append(raw)
        return raw

    def get_pre_roll(self) -> bytes:
        """Get the last ~2 seconds of audio from the ring buffer."""
        return b"".join(self._ring)

    async def stop(self) -> None:
        """Kill arecord subprocess and clean up."""
        self._active = False
        if self._proc:
            try:
                self._proc.kill()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None
        self._ring.clear()
        log.info("Mic stream stopped")

    @property
    def is_active(self) -> bool:
        return self._active and self._proc is not None and self._proc.poll() is None
