"""Test suite for ContextBuilder - TDD approach with explicit assertions"""
import sys
import time
import tempfile
sys.path.append('.')

from src.context_builder import ContextBuilder, ContextRequest, ContextResponse
from src.layered_memory import LayeredMemorySystem
from src.session_manager import ConversationTurn


def test_context_assembly_performance():
    """Test that context assembly is <5ms (performance critical)"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        
        # Setup test session
        session_id = "perf_test"
        for i in range(10):
            turn = ConversationTurn(
                user_input=f"Question {i}",
                assistant_response=f"Response {i}", 
                timestamp=time.time(),
                session_id=session_id
            )
            memory_system.store_session_turn(session_id, turn)
        
        # Test performance
        request = ContextRequest(session_id=session_id, current_input="New question")
        
        start = time.time()
        response = context_builder.build_context(request)
        end = time.time()
        
        duration_ms = (end - start) * 1000
        
        assert isinstance(response, ContextResponse)
        assert response.formatted_context is not None
        assert len(response.formatted_context) > 0
        assert abs(response.performance_ms - duration_ms) < 1.0  # Should be reasonably close
        assert duration_ms < 5.0  # Critical performance requirement


def test_includes_conversation_context():
    """Test that context includes conversation history"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        
        session_id = "context_test"
        
        # Add conversation
        memory_system.store_session_turn(session_id, ConversationTurn(
            user_input="Hello there",
            assistant_response="Hello! How can I help?",
            timestamp=time.time(),
            session_id=session_id
        ))
        
        request = ContextRequest(session_id=session_id, current_input="My name is Chris")
        response = context_builder.build_context(request)
        
        # Should include previous conversation
        assert "Hello there" in response.formatted_context
        assert "My name is Chris" in response.formatted_context


def test_includes_personality_prompt():
    """Test that context includes personality prompt"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        custom_personality = "You are Omni, a helpful AI assistant."
        context_builder = ContextBuilder(memory_system, personality_prompt=custom_personality)
        
        request = ContextRequest(
            session_id="personality_test",
            current_input="Who are you?",
            include_personality=True
        )
        
        response = context_builder.build_context(request)
        
        # Should include personality
        assert custom_personality in response.formatted_context
        assert "Who are you?" in response.formatted_context


def test_context_truncation():
    """Test that context is truncated when exceeding token limits"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        
        session_id = "truncation_test"
        
        # Add many long turns to force truncation
        for i in range(20):
            long_text = f"Very long question {i} " * 50
            turn = ConversationTurn(
                user_input=long_text,
                assistant_response=f"Long response {i} " * 50,
                timestamp=time.time(),
                session_id=session_id
            )
            memory_system.store_session_turn(session_id, turn)
        
        request = ContextRequest(
            session_id=session_id,
            current_input="Final question",
            max_context_length=1000  # Small limit
        )
        
        response = context_builder.build_context(request)
        
        # Should respect limits
        assert response.tokens_used <= 1000
        assert len(response.formatted_context) < 10000
        assert "Final question" in response.formatted_context


def test_performance_tracking():
    """Test that ContextBuilder tracks performance"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        context_builder = ContextBuilder(memory_system)
        
        request = ContextRequest(session_id="perf_tracking", current_input="Test")
        response = context_builder.build_context(request)
        
        # Should track metrics
        assert response.performance_ms >= 0
        assert response.tokens_used >= 0
        assert response.context_summary is not None


def test_optional_memory_search():
    """Test that memory search is optional"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir) 
        context_builder = ContextBuilder(memory_system)
        
        # Both should work
        request1 = ContextRequest(session_id="memory_test", 
                                current_input="Without memory", 
                                include_memory_search=False)
        response1 = context_builder.build_context(request1)
        
        request2 = ContextRequest(session_id="memory_test", 
                                current_input="With memory", 
                                include_memory_search=True)
        response2 = context_builder.build_context(request2)
        
        assert response1.formatted_context is not None
        assert response2.formatted_context is not None


# Test runner
if __name__ == "__main__":
    tests = [
        test_context_assembly_performance,
        test_includes_conversation_context,
        test_includes_personality_prompt,
        test_context_truncation,
        test_performance_tracking,
        test_optional_memory_search
    ]
    
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__} PASSED")
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
