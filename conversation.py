"""
Conversation memory for Omni Vox multi-turn voice interactions.
Stores recent turns per session key, formats them for LLM context injection.

Enhanced with persistent storage to survive container restarts.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
import time
import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """A single conversation turn (user + assistant)"""
    user: str
    assistant: str
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Turn':
        return cls(**data)


class ConversationBuffer:
    """Per-session conversation history buffer with persistent storage.
    
    Maintains a rolling window of recent turns per session key.
    Automatically saves to disk and loads on startup.
    Thread-safe for async usage (GIL protects operations).
    """
    
    def __init__(self, max_turns: int = 20, storage_dir: str = "/tmp/omni-vox-conversations"):
        self.max_turns = max_turns
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._buffers: dict[str, list[Turn]] = {}
        self._load_all_sessions()
    
    def _session_file_path(self, session_key: str) -> Path:
        """Get the file path for a session's conversation history"""
        # Sanitize session key for filename
        safe_key = "".join(c for c in session_key if c.isalnum() or c in ('-', '_'))
        return self.storage_dir / f"conversation_{safe_key}.json"
    
    def _load_session(self, session_key: str) -> list[Turn]:
        """Load conversation history for a session from disk"""
        file_path = self._session_file_path(session_key)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            turns = []
            for turn_data in data.get('turns', []):
                turns.append(Turn.from_dict(turn_data))
            
            # Ensure we don't exceed max_turns when loading
            if len(turns) > self.max_turns:
                turns = turns[-self.max_turns:]
            
            logger.info(f"Loaded {len(turns)} conversation turns for session '{session_key}'")
            return turns
            
        except Exception as e:
            logger.error(f"Failed to load conversation for session '{session_key}': {e}")
            return []
    
    def _save_session(self, session_key: str) -> None:
        """Save conversation history for a session to disk"""
        turns = self._buffers.get(session_key, [])
        if not turns:
            # Remove file if no turns
            file_path = self._session_file_path(session_key)
            if file_path.exists():
                file_path.unlink()
            return
        
        try:
            file_path = self._session_file_path(session_key)
            data = {
                'session_key': session_key,
                'last_updated': time.time(),
                'turn_count': len(turns),
                'turns': [turn.to_dict() for turn in turns]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved {len(turns)} turns for session '{session_key}'")
            
        except Exception as e:
            logger.error(f"Failed to save conversation for session '{session_key}': {e}")
    
    def _load_all_sessions(self) -> None:
        """Load all existing conversation sessions from disk"""
        if not self.storage_dir.exists():
            return
        
        for file_path in self.storage_dir.glob("conversation_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session_key = data.get('session_key')
                if session_key:
                    self._buffers[session_key] = self._load_session(session_key)
            except Exception as e:
                logger.error(f"Failed to load session from {file_path}: {e}")
    
    def add_turn(self, session_key: str, user_text: str, assistant_text: str) -> None:
        """Record a completed turn and save to disk"""
        if session_key not in self._buffers:
            self._buffers[session_key] = self._load_session(session_key)
        
        buf = self._buffers[session_key]
        buf.append(Turn(user=user_text, assistant=assistant_text))
        
        # Trim to max turns
        if len(buf) > self.max_turns:
            self._buffers[session_key] = buf[-self.max_turns:]
        
        # Persist to disk
        self._save_session(session_key)
        
        logger.info(f"Added turn to session '{session_key}' (total: {len(self._buffers[session_key])} turns)")
    
    def get_history(self, session_key: str) -> list[Turn]:
        """Get all turns for a session"""
        if session_key not in self._buffers:
            self._buffers[session_key] = self._load_session(session_key)
        return list(self._buffers.get(session_key, []))
    
    def format_context(self, session_key: str) -> Optional[str]:
        """Format conversation history as a context block for the LLM.
        
        Returns None if no history exists.
        """
        if session_key not in self._buffers:
            self._buffers[session_key] = self._load_session(session_key)
        
        turns = self._buffers.get(session_key, [])
        if not turns:
            return None
        
        lines = ["[Recent conversation context:]"]
        for turn in turns:
            lines.append(f"Chris: {turn.user}")
            lines.append(f"Omni: {turn.assistant}")
        lines.append("[End of conversation context]")
        
        return "\n".join(lines)
    
    def clear(self, session_key: Optional[str] = None) -> None:
        """Clear history for a session, or all sessions if key is None"""
        if session_key:
            self._buffers.pop(session_key, None)
            self._save_session(session_key)  # This will remove the file
        else:
            # Clear all sessions
            for key in list(self._buffers.keys()):
                self._buffers[key] = []
                self._save_session(key)  # This will remove all files
            self._buffers.clear()
    
    def turn_count(self, session_key: str) -> int:
        """Get number of stored turns for a session"""
        if session_key not in self._buffers:
            self._buffers[session_key] = self._load_session(session_key)
        return len(self._buffers.get(session_key, []))
    
    def get_session_stats(self) -> dict:
        """Get statistics about all conversation sessions"""
        stats = {
            'total_sessions': len(self._buffers),
            'total_turns': sum(len(turns) for turns in self._buffers.values()),
            'sessions': {}
        }
        
        for session_key, turns in self._buffers.items():
            if turns:
                stats['sessions'][session_key] = {
                    'turn_count': len(turns),
                    'last_interaction': max(turn.timestamp for turn in turns),
                    'first_interaction': min(turn.timestamp for turn in turns)
                }
        
        return stats
    
    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """Remove conversation files older than max_age_days. Returns number of cleaned up sessions."""
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        cleaned_count = 0
        
        for session_key in list(self._buffers.keys()):
            turns = self._buffers[session_key]
            if not turns:
                continue
                
            # Check if the most recent turn is older than cutoff
            most_recent = max(turn.timestamp for turn in turns)
            if most_recent < cutoff_time:
                self.clear(session_key)
                cleaned_count += 1
                logger.info(f"Cleaned up old session '{session_key}' (last activity: {time.ctime(most_recent)})")
        
        return cleaned_count