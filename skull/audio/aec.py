"""Acoustic Echo Cancellation using SpeexDSP.

Removes the system's own audio output from the microphone input,
enabling barge-in detection without false triggers from playback.
"""

import logging
import numpy as np

log = logging.getLogger(__name__)

# Frame size in samples (must match across all components)
FRAME_SIZE = 256  # 16ms at 16kHz


class EchoCanceller:
    """SpeexDSP-based acoustic echo canceller.
    
    Usage:
        aec = EchoCanceller()
        
        # During playback, feed the speaker output:
        aec.feed_playback(speaker_frame)
        
        # Process mic input to remove echo:
        clean = aec.process(mic_frame)
    """

    def __init__(self, frame_size: int = FRAME_SIZE, sample_rate: int = 16000):
        from speexdsp import EchoCanceller as SpxEC

        self._ec = SpxEC.create(frame_size, frame_size, sample_rate, 1)
        self._frame_size = frame_size
        self._playback_buffer = np.zeros(frame_size, dtype=np.int16)
        self._is_warmed_up = False
        self._frames_processed = 0
        log.info("AEC initialized (frame_size=%d, rate=%d)", frame_size, sample_rate)

    def feed_playback(self, audio: bytes) -> None:
        """Feed speaker output audio as the reference signal.
        
        Call this with the audio being sent to the speaker so the AEC
        can subtract it from the mic input.
        
        Args:
            audio: Raw PCM int16 mono audio bytes.
        """
        samples = np.frombuffer(audio, dtype=np.int16)
        
        # Process in frame-sized chunks
        offset = 0
        while offset + self._frame_size <= len(samples):
            self._playback_buffer = samples[offset:offset + self._frame_size].copy()
            offset += self._frame_size

    def process(self, mic_frame: bytes) -> bytes:
        """Remove echo from a mic frame using the playback reference.
        
        Args:
            mic_frame: Raw PCM int16 mono audio (frame_size samples).
            
        Returns:
            Echo-cancelled audio bytes (same size as input).
        """
        mic_samples = np.frombuffer(mic_frame, dtype=np.int16)
        
        if len(mic_samples) != self._frame_size:
            # If frame size doesn't match, pass through
            return mic_frame
        
        try:
            # SpeexDSP expects bytes
            out = self._ec.process(
                mic_frame,
                self._playback_buffer.tobytes(),
            )
            self._frames_processed += 1
            
            # AEC typically needs ~100 frames to converge
            if not self._is_warmed_up and self._frames_processed >= 100:
                self._is_warmed_up = True
                log.info("AEC converged after %d frames", self._frames_processed)
            
            return out
        except Exception:
            log.exception("AEC processing failed — passing through raw audio")
            return mic_frame

    @property
    def is_warmed_up(self) -> bool:
        """Whether the AEC has processed enough frames to be effective."""
        return self._is_warmed_up

    def reset(self) -> None:
        """Reset the AEC state (e.g., after a long silence)."""
        self._playback_buffer = np.zeros(self._frame_size, dtype=np.int16)
        self._is_warmed_up = False
        self._frames_processed = 0
        log.info("AEC reset")
