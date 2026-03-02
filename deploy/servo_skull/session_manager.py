"""
SessionManager for voice conversation memory system.

Minimal implementation to pass TDD tests.
"""
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional


class SessionState(Enum):
    """Voice conversation session states"""
    LISTENING = "listening"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass
class ConversationTurn:
    """A single conversation turn"""
    user_input: str
    assistant_response: str
    timestamp: float
    session_id: str


@dataclass
class ConversationSession:
    """Voice conversation session with state and timing"""
    session_id: str
    state: SessionState
    start_time: float
    turns: List[ConversationTurn]
    estimated_end_time: float
    session_key: str = "voice"


class SessionManager:
    """Manages voice conversation session lifecycle and timing"""
    
    def __init__(self, mic_open_duration: Optional[int] = None, 
                 wake_word_timeout: Optional[int] = None):
        """Initialize SessionManager with configurable timing"""
        self.mic_open_duration = (
            mic_open_duration if mic_open_duration is not None
            else int(os.getenv("MIC_OPEN_DURATION", "15"))
        )
        self.wake_word_timeout = (
            wake_word_timeout if wake_word_timeout is not None  
            else int(os.getenv("WAKE_WORD_TIMEOUT", "5"))
        )
        self._sessions: Dict[str, ConversationSession] = {}
    
    def start_session(self, session_key: str) -> ConversationSession:
        """Start a new conversation session"""
        session_id = self._generate_session_id()
        start_time = time.time()
        
        session = ConversationSession(
            session_id=session_id,
            state=SessionState.ACTIVE,
            start_time=start_time,
            turns=[],
            estimated_end_time=start_time + self.mic_open_duration,
            session_key=session_key
        )
        
        self._sessions[session_id] = session
        return session
    
    def extend_session(self, session_id: str) -> ConversationSession:
        """Extend session timeout"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self._sessions[session_id]
        session.estimated_end_time = time.time() + self.mic_open_duration
        return session
    
    def check_session_timeout(self, session_id: str) -> ConversationSession:
        """Check if session has timed out"""
        session = self._sessions[session_id]
        if time.time() >= session.estimated_end_time:
            session.state = SessionState.ENDED
        return session
    
    def recover_session(self, session_id: str) -> Optional[ConversationSession]:
        """Recover session state (placeholder)"""
        return None
    
    def _generate_session_id(self) -> str:
        """Generate secure session ID"""
        return str(uuid.uuid4())
