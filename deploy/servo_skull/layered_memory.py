"""
LayeredMemorySystem for voice conversation memory.
Three-layer memory architecture with performance optimization.
"""
import os
import json
import time
import threading
from typing import List, Dict
from .session_manager import ConversationTurn


class LayeredMemorySystem:
    """Three-layer memory system for voice conversations"""
    
    def __init__(self, storage_dir: str = "/tmp/voice-sessions"):
        """Initialize layered memory system"""
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        # Layer 1: In-memory immediate context cache
        self._context_cache: Dict[str, List[ConversationTurn]] = {}
        
        # Layer 2: Session storage paths
        self._session_paths: Dict[str, str] = {}
        
        # Layer 3: Memory bridge sync queue (async)
        self._sync_queue: List[str] = []
        self._sync_lock = threading.Lock()
        
        # Start background sync worker
        self._start_sync_worker()
    
    def get_immediate_context(self, session_id: str, turns: int = 5) -> List[ConversationTurn]:
        """Get immediate conversation context (<1ms target)"""
        # Layer 1: Check cache first (fastest path)
        if session_id in self._context_cache:
            cached_turns = self._context_cache[session_id]
            recent_turns = cached_turns[-turns:] if len(cached_turns) > turns else cached_turns
            return list(reversed(recent_turns))
        
        # Layer 2: Load from storage and cache
        all_turns = self.load_session_memory(session_id)
        self._context_cache[session_id] = all_turns
        
        recent_turns = all_turns[-turns:] if len(all_turns) > turns else all_turns
        return list(reversed(recent_turns))
    
    def load_session_memory(self, session_id: str) -> List[ConversationTurn]:
        """Load complete session memory from persistent storage (<5ms target)"""
        session_file = self._get_session_file(session_id)
        
        if not os.path.exists(session_file):
            return []
        
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
            
            turns = []
            for turn_data in data.get('turns', []):
                turns.append(ConversationTurn(
                    user_input=turn_data['user_input'],
                    assistant_response=turn_data['assistant_response'],
                    timestamp=turn_data['timestamp'],
                    session_id=turn_data['session_id']
                ))
            
            return turns
            
        except (json.JSONDecodeError, KeyError, OSError):
            return []
    
    def store_session_turn(self, session_id: str, turn: ConversationTurn) -> None:
        """Store conversation turn to persistent storage and update cache"""
        # Update Layer 1 cache immediately
        if session_id not in self._context_cache:
            self._context_cache[session_id] = []
        
        self._context_cache[session_id].append(turn)
        
        # Persist to Layer 2 storage
        self._persist_session(session_id)
        
        # Queue for Layer 3 sync (async)
        with self._sync_lock:
            if session_id not in self._sync_queue:
                self._sync_queue.append(session_id)
    
    def sync_to_memory_bridge(self, session_id: str) -> None:
        """Sync session to memory bridge (async, non-blocking)"""
        with self._sync_lock:
            if session_id not in self._sync_queue:
                self._sync_queue.append(session_id)
    
    def clear_session(self, session_id: str) -> None:
        """Remove session data completely"""
        # Clear Layer 1 cache
        if session_id in self._context_cache:
            del self._context_cache[session_id]
        
        # Remove Layer 2 storage
        session_file = self._get_session_file(session_id)
        if os.path.exists(session_file):
            os.remove(session_file)
        
        # Remove from Layer 3 sync queue
        with self._sync_lock:
            if session_id in self._sync_queue:
                self._sync_queue.remove(session_id)
    
    def _get_session_file(self, session_id: str) -> str:
        """Get file path for session storage"""
        if session_id not in self._session_paths:
            safe_id = "".join(c for c in session_id if c.isalnum() or c in '-_')
            self._session_paths[session_id] = os.path.join(
                self.storage_dir, f"session_{safe_id}.json"
            )
        
        return self._session_paths[session_id]
    
    def _persist_session(self, session_id: str) -> None:
        """Persist session cache to storage"""
        if session_id not in self._context_cache:
            return
        
        session_file = self._get_session_file(session_id)
        turns_data = []
        
        for turn in self._context_cache[session_id]:
            turns_data.append({
                'user_input': turn.user_input,
                'assistant_response': turn.assistant_response,
                'timestamp': turn.timestamp,
                'session_id': turn.session_id
            })
        
        data = {
            'session_id': session_id,
            'turns': turns_data,
            'last_updated': time.time()
        }
        
        try:
            with open(session_file, 'w') as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
    
    def _start_sync_worker(self) -> None:
        """Start background worker for memory bridge sync"""
        def sync_worker():
            while True:
                session_to_sync = None
                
                with self._sync_lock:
                    if self._sync_queue:
                        session_to_sync = self._sync_queue.pop(0)
                
                if session_to_sync:
                    time.sleep(0.1)  # Simulate sync work
                else:
                    time.sleep(1)    # Wait for work
        
        worker_thread = threading.Thread(target=sync_worker, daemon=True)
        worker_thread.start()
