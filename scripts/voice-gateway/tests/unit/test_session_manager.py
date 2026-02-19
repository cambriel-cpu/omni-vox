import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from session_manager import SessionManager, VoiceSession

@pytest.mark.asyncio
async def test_create_session():
    manager = SessionManager()
    websocket = AsyncMock()
    
    async with manager.get_session("test123", websocket) as session:
        assert session.session_id == "test123"
        assert session.websocket == websocket
        assert not session.is_cancelled
        assert "test123" in manager.active_sessions

@pytest.mark.asyncio
async def test_session_cleanup_on_exit():
    manager = SessionManager()
    websocket = AsyncMock()
    
    async with manager.get_session("test123", websocket) as session:
        pass  # Session should cleanup automatically
    
    # Session should be removed after context exit
    assert "test123" not in manager.active_sessions

@pytest.mark.asyncio
async def test_session_cancellation():
    manager = SessionManager()
    websocket = AsyncMock()
    
    async with manager.get_session("test123", websocket) as session:
        assert not session.is_cancelled
        session.cancel()
        assert session.is_cancelled

@pytest.mark.asyncio
async def test_concurrent_sessions():
    manager = SessionManager()
    ws1, ws2 = AsyncMock(), AsyncMock()
    
    async with manager.get_session("session1", ws1) as s1:
        async with manager.get_session("session2", ws2) as s2:
            assert len(manager.active_sessions) == 2
            assert s1.session_id != s2.session_id
    
    # Both should cleanup
    assert len(manager.active_sessions) == 0