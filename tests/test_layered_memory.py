"""Test suite for LayeredMemorySystem - TDD approach with explicit assertions"""
import sys
import os
import time
import tempfile
sys.path.append('.')

from src.session_manager import ConversationTurn
from src.layered_memory import LayeredMemorySystem  # Will fail until implemented


def test_immediate_context_buffer_performance():
    """Test that immediate context access is <1ms"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        session_id = "test_session"
        
        # Add some turns to the session
        for i in range(10):
            turn = ConversationTurn(
                user_input=f"Question {i}",
                assistant_response=f"Response {i}",
                timestamp=time.time(),
                session_id=session_id
            )
            memory_system.store_session_turn(session_id, turn)
        
        # Test immediate context performance
        start = time.time()
        context = memory_system.get_immediate_context(session_id, turns=5)
        end = time.time()
        
        duration_ms = (end - start) * 1000
        
        # Explicit assertions
        assert len(context) == 5  # Should return requested number of turns
        assert all(turn.session_id == session_id for turn in context)
        assert duration_ms < 1.0  # Performance requirement: <1ms
        assert context[0].user_input == "Question 9"  # Most recent first


def test_session_memory_persistence():
    """Test that session memory persists and loads <5ms"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create memory system and store data
        memory_system1 = LayeredMemorySystem(storage_dir=temp_dir)
        session_id = "persistent_session"
        
        original_turn = ConversationTurn(
            user_input="Remember this",
            assistant_response="I'll remember",
            timestamp=time.time(),
            session_id=session_id
        )
        memory_system1.store_session_turn(session_id, original_turn)
        
        # Create new memory system (simulate restart)
        memory_system2 = LayeredMemorySystem(storage_dir=temp_dir)
        
        # Test session loading performance
        start = time.time()
        loaded_turns = memory_system2.load_session_memory(session_id)
        end = time.time()
        
        duration_ms = (end - start) * 1000
        
        # Explicit assertions
        assert len(loaded_turns) == 1
        assert loaded_turns[0].user_input == "Remember this"
        assert loaded_turns[0].assistant_response == "I'll remember"
        assert loaded_turns[0].session_id == session_id
        assert duration_ms < 5.0  # Performance requirement: <5ms


def test_memory_bridge_sync_non_blocking():
    """Test that memory bridge sync is async and non-blocking"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        session_id = "sync_test"
        
        # Add a turn
        turn = ConversationTurn(
            user_input="Sync this",
            assistant_response="Syncing",
            timestamp=time.time(),
            session_id=session_id
        )
        memory_system.store_session_turn(session_id, turn)
        
        # Test sync performance (should be immediate, not block)
        start = time.time()
        memory_system.sync_to_memory_bridge(session_id)
        end = time.time()
        
        duration_ms = (end - start) * 1000
        
        # Should not block - either immediate return or very fast
        assert duration_ms < 10.0  # Should not block operations


def test_context_caching_for_active_sessions():
    """Test that active sessions cache context for performance"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        session_id = "cached_session"
        
        # Add turns
        for i in range(20):
            turn = ConversationTurn(
                user_input=f"Cached question {i}",
                assistant_response=f"Cached response {i}",
                timestamp=time.time(),
                session_id=session_id
            )
            memory_system.store_session_turn(session_id, turn)
        
        # First call - may be slower (loads from storage)
        context1 = memory_system.get_immediate_context(session_id, turns=5)
        
        # Second call - should be cached and faster
        start = time.time()
        context2 = memory_system.get_immediate_context(session_id, turns=5)
        end = time.time()
        
        duration_ms = (end - start) * 1000
        
        # Explicit assertions
        assert len(context2) == 5
        assert context1 == context2  # Same data
        assert duration_ms < 0.5  # Should be very fast from cache


def test_session_cleanup():
    """Test that sessions can be cleared completely"""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_system = LayeredMemorySystem(storage_dir=temp_dir)
        session_id = "cleanup_test"
        
        # Add some data
        turn = ConversationTurn(
            user_input="Delete me",
            assistant_response="Will be deleted",
            timestamp=time.time(),
            session_id=session_id
        )
        memory_system.store_session_turn(session_id, turn)
        
        # Verify data exists
        context_before = memory_system.get_immediate_context(session_id)
        assert len(context_before) == 1
        
        # Clear session
        memory_system.clear_session(session_id)
        
        # Verify data is gone
        context_after = memory_system.get_immediate_context(session_id)
        assert len(context_after) == 0


# Simple test runner
if __name__ == "__main__":
    tests = [
        test_immediate_context_buffer_performance,
        test_session_memory_persistence, 
        test_memory_bridge_sync_non_blocking,
        test_context_caching_for_active_sessions,
        test_session_cleanup
    ]
    
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__} PASSED")
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
