"""
Conversation memory for Omni Vox multi-turn voice interactions.
Stores recent turns per session key, formats them for LLM context injection.
"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Turn:
    """A single conversation turn (user + assistant)"""
    user: str
    assistant: str
    timestamp: float = field(default_factory=time.time)


class ConversationBuffer:
    """Per-session conversation history buffer.
    
    Maintains a rolling window of recent turns per session key.
    Thread-safe for async usage (GIL protects list operations).
    """
    
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._buffers: dict[str, list[Turn]] = {}
    
    def add_turn(self, session_key: str, user_text: str, assistant_text: str) -> None:
        """Record a completed turn"""
        if session_key not in self._buffers:
            self._buffers[session_key] = []
        buf = self._buffers[session_key]
        buf.append(Turn(user=user_text, assistant=assistant_text))
        # Trim to max
        if len(buf) > self.max_turns:
            self._buffers[session_key] = buf[-self.max_turns:]
    
    def get_history(self, session_key: str) -> list[Turn]:
        """Get all turns for a session"""
        return list(self._buffers.get(session_key, []))
    
    def format_context(self, session_key: str) -> Optional[str]:
        """Format conversation history as a context block for the LLM.
        
        Returns None if no history exists.
        """
        turns = self._buffers.get(session_key, [])
        if not turns:
            return None
        
        lines = ["[Previous conversation:]"]
        for turn in turns:
            lines.append(f"Chris: {turn.user}")
            lines.append(f"Omni: {turn.assistant}")
        
        return "\n".join(lines)
    
    def clear(self, session_key: Optional[str] = None) -> None:
        """Clear history for a session, or all sessions if key is None"""
        if session_key:
            self._buffers.pop(session_key, None)
        else:
            self._buffers.clear()
    
    def turn_count(self, session_key: str) -> int:
        """Get number of stored turns for a session"""
        return len(self._buffers.get(session_key, []))
