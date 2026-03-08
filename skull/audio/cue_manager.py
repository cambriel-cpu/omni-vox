"""Cue manager — categorized pre-recorded audio playback."""

import glob
import logging
import random
from pathlib import Path

from skull.audio.player import play_cue, play_cue_async
from skull.config import CUES_DIR

log = logging.getLogger(__name__)


def _list_cues(prefix: str) -> list[str]:
    """List available cue names matching a prefix (without .wav extension)."""
    pattern = str(Path(CUES_DIR) / f"{prefix}*.wav")
    paths = glob.glob(pattern)
    return [Path(p).stem for p in sorted(paths)]


# Pre-built cue lists (populated at first use)
_cue_cache: dict[str, list[str]] = {}


def _get_cues(category: str) -> list[str]:
    """Get list of cue names for a category, cached."""
    if category not in _cue_cache:
        _cue_cache[category] = _list_cues(category)
        if _cue_cache[category]:
            log.info("Loaded %d cues for category '%s'", len(_cue_cache[category]), category)
        else:
            log.warning("No cues found for category '%s'", category)
    return _cue_cache[category]


def play_random(category: str, blocking: bool = True) -> str | None:
    """Play a random cue from a category.
    
    Categories: ack_short, ack_tool, error, cue
    
    Returns the cue name played, or None if no cues available.
    """
    cues = _get_cues(category)
    if not cues:
        log.warning("No cues for category '%s'", category)
        return None

    name = random.choice(cues)
    log.info("Playing cue: %s (category=%s)", name, category)
    if blocking:
        play_cue(name)
    else:
        play_cue_async(name)
    return name


def play_wake_cue() -> None:
    """Play the session-open / wake cue."""
    play_cue_async("cue_wake")


def play_close_cue() -> None:
    """Play the session-close cue."""
    play_cue("cue_close")


def play_error(error_type: str = "connection") -> None:
    """Play an error response.
    
    error_type: connection, timeout, stt
    """
    name = f"error_{error_type}"
    path = Path(CUES_DIR) / f"{name}.wav"
    if path.exists():
        play_cue(name)
    else:
        # Fall back to generic error cue
        play_cue("cue_error")


def play_processing_loop() -> None:
    """Play the processing ambient loop (walkie-talkie static).
    
    This is blocking and plays the loop once. The caller should
    call this in a loop/thread and check for cancellation.
    """
    play_cue("cue_processing")
