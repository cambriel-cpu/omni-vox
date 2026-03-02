"""Test suite for WebSocket Context Injection"""
import sys
import asyncio
import tempfile
from unittest.mock import Mock
sys.path.append('.')

from src.websocket_context import WebSocketContextHandler, VoiceRequest, VoiceResponse
from src.layered_memory import LayeredMemorySystem
from src.context_builder import ContextBuilder
from src.session_manager import ConversationTurn


def test_voice_request_gets_context_injection():
    """Test that voice requests receive conversation context"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder)
        
        session_id = "voice_session_test"
        
        # Add conversation history
        memory_system.store_session_turn(session_id, ConversationTurn(
            user_input="What's the weather?",
            assistant_response="I can help with weather information.",
            timestamp=1234567890,
            session_id=session_id
        ))
        
        mock_websocket = Mock()
        voice_request = VoiceRequest(
            type="voice_request",
            transcript="Will it rain today?",
            session_id=session_id
        )
        
        response = asyncio.run(handler.handle_voice_request(mock_websocket, voice_request))
        
        assert isinstance(response, VoiceResponse)
        assert response.context_injected is True
        assert "What's the weather?" in response.llm_context
        assert "Will it rain today?" in response.llm_context
        assert "System:" in response.llm_context


def test_backward_compatibility_with_web_interface():
    """Test that non-voice requests work without context injection"""  
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder)
        
        mock_websocket = Mock()
        web_request = {
            "type": "web_request", 
            "message": "Hello from web interface"
        }
        
        response = asyncio.run(handler.handle_websocket_message(mock_websocket, web_request))
        
        assert response.get("type") == "web_request"
        assert "context_injected" not in response


def test_graceful_handling_of_empty_session():
    """Test that requests with no conversation history work gracefully"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder)
        
        mock_websocket = Mock()
        voice_request = VoiceRequest(
            type="voice_request",
            transcript="Hello, this is my first message",
            session_id="new_empty_session"
        )
        
        response = asyncio.run(handler.handle_voice_request(mock_websocket, voice_request))
        
        assert isinstance(response, VoiceResponse)
        assert response.context_injected is True
        assert "Hello, this is my first message" in response.llm_context
        assert "System:" in response.llm_context


def test_context_injection_performance():
    """Test that context injection doesn't add significant latency"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder)
        
        session_id = "performance_test"
        
        for i in range(5):
            memory_system.store_session_turn(session_id, ConversationTurn(
                user_input=f"Question {i}",
                assistant_response=f"Response {i}",
                timestamp=1234567890 + i,
                session_id=session_id
            ))
        
        mock_websocket = Mock()
        voice_request = VoiceRequest(
            type="voice_request", 
            transcript="Performance test question",
            session_id=session_id
        )
        
        import time
        start = time.time()
        response = asyncio.run(handler.handle_voice_request(mock_websocket, voice_request))
        end = time.time()
        
        context_injection_ms = (end - start) * 1000
        
        assert isinstance(response, VoiceResponse)
        assert context_injection_ms < 10.0
        assert response.performance_metrics["context_injection_ms"] > 0


def test_session_id_persistence():
    """Test that WebSocket sessions maintain consistent session IDs"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder)
        
        mock_websocket = Mock()
        
        request1 = VoiceRequest(
            type="voice_request",
            transcript="First message", 
            session_id=None
        )
        
        response1 = asyncio.run(handler.handle_voice_request(mock_websocket, request1))
        session_id_1 = response1.session_id
        
        assert session_id_1 is not None
        assert len(session_id_1) > 8
        
        request2 = VoiceRequest(
            type="voice_request", 
            transcript="Second message",
            session_id=session_id_1
        )
        
        # Simulate recording the first conversation turn (what would happen after LLM responds)
        asyncio.run(handler.record_conversation_turn(
            session_id_1, 
            "First message", 
            "I received your first message"
        ))
        
        response2 = asyncio.run(handler.handle_voice_request(mock_websocket, request2))
        
        assert response2.session_id == session_id_1
        assert "First message" in response2.llm_context


def test_debug_information_included():
    """Test that debug information is included when enabled"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        handler = WebSocketContextHandler(memory_system, context_builder, debug_mode=True)
        
        mock_websocket = Mock()
        voice_request = VoiceRequest(
            type="voice_request",
            transcript="Debug test message", 
            session_id="debug_session"
        )
        
        response = asyncio.run(handler.handle_voice_request(mock_websocket, voice_request))
        
        assert response.debug_info is not None
        assert "context_length" in response.debug_info
        assert "memory_turns" in response.debug_info
        assert "context_building_time_ms" in response.debug_info


if __name__ == "__main__":
    tests = [
        test_voice_request_gets_context_injection,
        test_backward_compatibility_with_web_interface,
        test_graceful_handling_of_empty_session,
        test_context_injection_performance,
        test_session_id_persistence,
        test_debug_information_included
    ]
    
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__} PASSED")
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
