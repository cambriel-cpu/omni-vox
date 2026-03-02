"""Test suite for SessionManager - TDD approach"""
import sys
import os
sys.path.append('.')

from src.session_manager import SessionManager, SessionState

def test_session_starts_on_wake_word():
    """Test that SessionManager starts a new active session"""
    manager = SessionManager()
    session = manager.start_session("voice")
    
    assert session.state == SessionState.ACTIVE
    assert session.session_id is not None
    assert session.start_time > 0
    assert len(session.turns) == 0

def test_timing_uses_defaults():
    """Test default timing values"""
    manager = SessionManager()
    assert manager.mic_open_duration == 15
    assert manager.wake_word_timeout == 5

# Simple test runner
if __name__ == "__main__":
    try:
        test_session_starts_on_wake_word()
        print("✅ test_session_starts_on_wake_word PASSED")
    except Exception as e:
        print(f"❌ test_session_starts_on_wake_word FAILED: {e}")
    
    try:
        test_timing_uses_defaults()
        print("✅ test_timing_uses_defaults PASSED")
    except Exception as e:
        print(f"❌ test_timing_uses_defaults FAILED: {e}")
