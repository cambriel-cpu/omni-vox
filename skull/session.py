"""Session state management for conversation lifecycle."""

import enum
import logging
import time

from skull.config import (
    SESSION_FOLLOWUP_EXTEND_AFTER,
    SESSION_FOLLOWUP_EXTENDED,
    SESSION_FOLLOWUP_TIMEOUT,
    SESSION_MAX_DURATION,
    SESSION_OPEN_TIMEOUT,
)

log = logging.getLogger(__name__)


class SessionState(enum.Enum):
    IDLE = "IDLE"
    SESSION_OPEN = "SESSION_OPEN"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    FOLLOW_UP = "FOLLOW_UP"
    SESSION_CLOSE = "SESSION_CLOSE"


class Session:
    """Tracks state for a single conversation session."""

    def __init__(self):
        self.state = SessionState.IDLE
        self.turn_count = 0
        self.last_spoken_sentence = ""
        self.interrupted_after = ""
        self.started_at = 0.0
        self._state_entered_at = 0.0

    def transition(self, new_state: SessionState) -> None:
        """Transition to a new state with logging."""
        old = self.state
        self.state = new_state
        self._state_entered_at = time.monotonic()
        log.info("Session: %s → %s (turn %d)", old.value, new_state.value, self.turn_count)

    def start(self) -> None:
        """Begin a new conversation session."""
        self.turn_count = 0
        self.last_spoken_sentence = ""
        self.interrupted_after = ""
        self.started_at = time.monotonic()
        self.transition(SessionState.SESSION_OPEN)

    def end(self) -> None:
        """End the conversation session."""
        duration = time.monotonic() - self.started_at if self.started_at else 0
        log.info("Session ended: %d turns, %.1fs duration", self.turn_count, duration)
        self.transition(SessionState.IDLE)

    def increment_turn(self) -> None:
        """Increment the turn counter."""
        self.turn_count += 1

    @property
    def follow_up_timeout(self) -> float:
        """Timeout for follow-up listening, extended after multiple turns."""
        if self.turn_count >= SESSION_FOLLOWUP_EXTEND_AFTER:
            return SESSION_FOLLOWUP_EXTENDED
        return SESSION_FOLLOWUP_TIMEOUT

    @property
    def open_timeout(self) -> float:
        """Timeout for initial speech after wake word."""
        return SESSION_OPEN_TIMEOUT

    @property
    def is_expired(self) -> bool:
        """Check if session has exceeded max duration."""
        if not self.started_at:
            return False
        return (time.monotonic() - self.started_at) > SESSION_MAX_DURATION

    @property
    def time_in_state(self) -> float:
        """Seconds spent in current state."""
        return time.monotonic() - self._state_entered_at
