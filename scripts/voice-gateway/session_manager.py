import asyncio
import time
import logging
from typing import Dict, Optional
from contextlib import asynccontextmanager
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class VoiceSession:
    """Represents an active voice WebSocket session"""
    
    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.created_at = time.time()
        self.is_cancelled = False
        self.current_task: Optional[asyncio.Task] = None
        
    def cancel(self):
        """Cancel any ongoing operations"""
        self.is_cancelled = True
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        logger.info(f"Session {self.session_id} cancelled")
    
    def cleanup(self):
        """Clean up session resources"""
        self.cancel()
        logger.info(f"Session {self.session_id} cleaned up")

class SessionManager:
    """Manages WebSocket voice sessions with proper cleanup"""
    
    def __init__(self):
        self.active_sessions: Dict[str, VoiceSession] = {}
        self.session_locks: Dict[str, asyncio.Lock] = {}
    
    @asynccontextmanager
    async def get_session(self, session_id: str, websocket: WebSocket):
        """Context manager for session lifecycle"""
        if session_id in self.active_sessions:
            raise ValueError(f"Session {session_id} already exists")
        
        # Create session and lock
        session = VoiceSession(session_id, websocket)
        self.active_sessions[session_id] = session
        self.session_locks[session_id] = asyncio.Lock()
        
        logger.info(f"Created session {session_id}")
        
        try:
            yield session
        finally:
            # Guaranteed cleanup
            session.cleanup()
            self.active_sessions.pop(session_id, None)
            self.session_locks.pop(session_id, None)
            logger.info(f"Removed session {session_id}")
    
    def get_active_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get active session if it exists"""
        return self.active_sessions.get(session_id)
    
    def cancel_session(self, session_id: str) -> bool:
        """Cancel a specific session"""
        session = self.active_sessions.get(session_id)
        if session:
            session.cancel()
            return True
        return False
    
    def get_session_count(self) -> int:
        """Get number of active sessions"""
        return len(self.active_sessions)