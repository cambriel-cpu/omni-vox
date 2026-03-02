"""
WebSocket Context Injection for voice conversation memory system.
Integrates memory system with WebSocket voice requests.
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .layered_memory import LayeredMemorySystem
from .context_builder import ContextBuilder, ContextRequest
from .session_manager import ConversationTurn


@dataclass
class VoiceRequest:
    """Voice request from WebSocket with session context"""
    type: str
    transcript: str
    session_id: Optional[str] = None


@dataclass
class VoiceResponse:
    """Voice response with context injection and debug information"""
    type: str = "voice_response"
    llm_context: str = ""
    session_id: str = ""
    context_injected: bool = False
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    debug_info: Optional[Dict[str, Any]] = None


class WebSocketContextHandler:
    """Handles WebSocket context injection for voice requests"""
    
    def __init__(self, memory_system: LayeredMemorySystem, context_builder: ContextBuilder,
                 debug_mode: bool = False):
        """Initialize WebSocket context handler"""
        self.memory_system = memory_system
        self.context_builder = context_builder
        self.debug_mode = debug_mode
        self._websocket_sessions: Dict[Any, str] = {}
        self._session_websockets: Dict[str, Any] = {}
    
    async def handle_websocket_message(self, websocket, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle WebSocket message with context injection for voice requests"""
        if not isinstance(message_data, dict):
            return {"error": "Invalid message format"}
        
        message_type = message_data.get("type")
        
        if message_type == "voice_request":
            voice_request = VoiceRequest(
                type=message_type,
                transcript=message_data.get("transcript", ""),
                session_id=message_data.get("session_id")
            )
            
            voice_response = await self.handle_voice_request(websocket, voice_request)
            
            return {
                "type": voice_response.type,
                "llm_context": voice_response.llm_context,
                "session_id": voice_response.session_id,
                "context_injected": voice_response.context_injected,
                "performance_metrics": voice_response.performance_metrics,
                "debug_info": voice_response.debug_info if self.debug_mode else None
            }
        else:
            return message_data
    
    async def handle_voice_request(self, websocket, request: VoiceRequest) -> VoiceResponse:
        """Handle voice request with context injection from memory system"""
        start_time = time.time()
        
        # Get or create session ID
        session_id = self._get_or_create_session_id(websocket, request.session_id)
        
        # Build conversation context
        context_start = time.time()
        context_request = ContextRequest(
            session_id=session_id,
            current_input=request.transcript,
            include_personality=True,
            include_memory_search=False
        )
        
        context_response = self.context_builder.build_context(context_request)
        context_end = time.time()
        
        # Performance metrics
        performance_metrics = {
            "context_injection_ms": (context_end - start_time) * 1000,
            "context_building_ms": context_response.performance_ms,
            "total_context_overhead_ms": (context_end - start_time) * 1000
        }
        
        # Debug information
        debug_info = None
        if self.debug_mode:
            conversation_turns = self.memory_system.get_immediate_context(session_id)
            debug_info = {
                "session_id": session_id,
                "context_length": len(context_response.formatted_context),
                "context_tokens": context_response.tokens_used,
                "memory_turns": len(conversation_turns),
                "context_building_time_ms": context_response.performance_ms,
                "context_summary": context_response.context_summary
            }
        
        return VoiceResponse(
            type="voice_response",
            llm_context=context_response.formatted_context,
            session_id=session_id,
            context_injected=True,
            performance_metrics=performance_metrics,
            debug_info=debug_info
        )
    
    async def record_conversation_turn(self, session_id: str, user_input: str, 
                                       assistant_response: str) -> None:
        """Record completed conversation turn to memory system"""
        turn = ConversationTurn(
            user_input=user_input,
            assistant_response=assistant_response,
            timestamp=time.time(),
            session_id=session_id
        )
        
        await asyncio.get_event_loop().run_in_executor(
            None, self.memory_system.store_session_turn, session_id, turn
        )
    
    def cleanup_websocket_session(self, websocket) -> None:
        """Clean up session mapping when WebSocket disconnects"""
        if websocket in self._websocket_sessions:
            session_id = self._websocket_sessions[websocket]
            del self._websocket_sessions[websocket]
            if session_id in self._session_websockets:
                del self._session_websockets[session_id]
    
    def _get_or_create_session_id(self, websocket, provided_session_id: Optional[str]) -> str:
        """Get or create session ID for WebSocket connection"""
        if provided_session_id and len(provided_session_id) > 8:
            self._websocket_sessions[websocket] = provided_session_id
            self._session_websockets[provided_session_id] = websocket
            return provided_session_id
        
        if websocket in self._websocket_sessions:
            return self._websocket_sessions[websocket]
        
        new_session_id = f"ws_{str(uuid.uuid4())}"
        self._websocket_sessions[websocket] = new_session_id
        self._session_websockets[new_session_id] = websocket
        
        return new_session_id
    
    def get_active_sessions(self) -> Dict[str, Any]:
        """Get information about currently active WebSocket sessions"""
        return {
            "total_websockets": len(self._websocket_sessions),
            "total_sessions": len(self._session_websockets),
            "session_ids": list(self._session_websockets.keys())
        }
