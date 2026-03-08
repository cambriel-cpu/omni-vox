"""Wake word detector — OpenWakeWord with ALSA mic capture."""

import collections
import logging
import subprocess
import time

import numpy as np

from skull.config import (
    ALSA_CAPTURE_DEVICE,
    CHANNELS,
    SAMPLE_RATE,
    WAKE_WORD_MODEL,
    WAKE_WORD_THRESHOLD,
)

log = logging.getLogger(__name__)

# Keep ~2 seconds of audio before the wake word for context
_PRE_ROLL_SECONDS = 2.0

# Target peak amplitude for normalization (70% of int16 max)
_TARGET_PEAK = 23000

# Minimum raw peak to consider for wake word detection.
# Rejects quiet speaker bleed that normalization would amplify.
_MIN_RAW_PEAK = 800


def _normalize_chunk(audio: np.ndarray) -> np.ndarray:
    """Normalize audio chunk to a consistent level."""
    peak = np.abs(audio).max()
    if peak < 100:
        return audio  # Silence — don't amplify noise floor
    scale = _TARGET_PEAK / peak
    return np.clip(audio * scale, -32768, 32767).astype(np.int16)


class WakeWordDetector:
    """Continuously listens for a wake word on the ReSpeaker mic."""

    def __init__(self):
        from openwakeword.model import Model

        self.model = Model()
        self._target = WAKE_WORD_MODEL
        log.info(
            "Wake word detector ready: target=%s (threshold=%.2f), available=%s",
            self._target,
            WAKE_WORD_THRESHOLD,
            list(self.model.models.keys()),
        )

    async def wait_for_wake_word(self) -> tuple[float, bytes]:
        """Block until the wake word is detected.

        Returns:
            Tuple of (confidence, pre_roll_audio_bytes).
            pre_roll_audio is raw PCM int16 mono 16kHz.
        """
        import asyncio

        # OpenWakeWord expects 1280 samples (80ms at 16kHz)
        chunk_samples = 1280
        chunk_bytes = chunk_samples * 2  # 16-bit

        # Rolling buffer: ~2s of raw audio chunks
        max_chunks = int(_PRE_ROLL_SECONDS * SAMPLE_RATE / chunk_samples)
        ring = collections.deque(maxlen=max_chunks)

        proc = subprocess.Popen(
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

        confidence = 0.0

        try:
            while True:
                raw = proc.stdout.read(chunk_bytes)
                if not raw or len(raw) < chunk_bytes:
                    await asyncio.sleep(0.01)
                    continue

                ring.append(raw)

                audio = np.frombuffer(raw, dtype=np.int16)
                normalized = _normalize_chunk(audio)
                prediction = self.model.predict(normalized)

                score = prediction.get(self._target, 0)
                raw_peak = int(np.abs(audio).max())
                if score > WAKE_WORD_THRESHOLD and raw_peak >= _MIN_RAW_PEAK:
                    confidence = score
                    log.info(
                        "Wake word '%s' detected (confidence=%.3f, raw_peak=%d)",
                        self._target,
                        score,
                        raw_peak,
                    )
                    break

                await asyncio.sleep(0)

        finally:
            proc.kill()
            proc.wait()

        # Reset model state for next detection
        self.model.reset()

        # Collect pre-roll audio (raw, unnormalized)
        pre_roll = b"".join(ring)

        # NOTE: Activation cue is now played by the session state machine,
        # not here. This allows the cue to play via the dmix playback device
        # while the session's continuous mic capture runs on dsnoop.

        return confidence, pre_roll
