import json
import time
from typing import Dict, Any, List
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Raised when message validation fails"""
    pass

class MessageValidator:
    def __init__(self, max_message_size=1024*1024, max_audio_size=5*1024*1024, 
                 max_requests=10, rate_window=60):
        self.max_message_size = max_message_size
        self.max_audio_size = max_audio_size
        self.max_requests = max_requests
        self.rate_window = rate_window
        
        # Rate limiting storage
        self.request_history: Dict[str, List[float]] = defaultdict(list)
    
    def validate_raw_message(self, raw_data: str, session_id: str) -> Dict[str, Any]:
        """Validate raw WebSocket message"""
        # Size check
        if len(raw_data) > self.max_message_size:
            raise ValidationError("Message too large")
        
        # JSON parsing
        try:
            message = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise ValidationError("Invalid message format")
        
        return self.validate_message(message, session_id)
    
    def validate_message(self, message: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Validate parsed message content"""
        # Rate limiting
        self._check_rate_limit(session_id)
        
        # Message type validation
        if not isinstance(message, dict):
            raise ValidationError("Message must be an object")
        
        # Audio data size check (for voice requests)
        if message.get("type") == "voice_request":
            audio_data = message.get("audio_data", "")
            if len(audio_data) > self.max_audio_size:
                raise ValidationError("Audio data too large")
        
        # Text length validation
        if "text" in message and len(message["text"]) > 10000:
            raise ValidationError("Text too long")
        
        return message
    
    def _check_rate_limit(self, session_id: str):
        """Check if session exceeds rate limit"""
        now = time.time()
        
        # Clean old requests
        self.request_history[session_id] = [
            req_time for req_time in self.request_history[session_id]
            if now - req_time < self.rate_window
        ]
        
        # Check limit
        if len(self.request_history[session_id]) >= self.max_requests:
            raise ValidationError("Rate limit exceeded")
        
        # Record this request
        self.request_history[session_id].append(now)
        
        logger.debug(f"Rate check for {session_id}: {len(self.request_history[session_id])}/{self.max_requests}")