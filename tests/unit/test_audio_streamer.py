import pytest
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add the voice-gateway directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'voice-gateway'))
from audio_streamer import AudioStreamer
from session_manager import VoiceSession

@pytest.mark.asyncio
async def test_stream_tts_audio_success():
    websocket = AsyncMock()
    session = VoiceSession("test123", websocket)
    streamer = AudioStreamer("http://localhost:8880")
    
    # Mock the entire httpx client workflow
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    async def mock_aiter_bytes(chunk_size):
        for chunk in [b"chunk1", b"chunk2", b"chunk3"]:
            yield chunk
    
    mock_response.aiter_bytes = mock_aiter_bytes
    
    async def mock_post_context_manager(*args, **kwargs):
        return mock_response
    
    mock_client = MagicMock()
    mock_client.post.return_value.__aenter__ = mock_post_context_manager
    mock_client.post.return_value.__aexit__ = AsyncMock(return_value=None)
    
    async def mock_client_context_manager(*args, **kwargs):
        return mock_client
    
    with patch('audio_streamer.httpx.AsyncClient') as mock_async_client:
        mock_async_client.return_value.__aenter__ = mock_client_context_manager
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
        
        await streamer.stream_tts_audio("test text", session)
    
    # Verify WebSocket calls
    assert websocket.send_json.call_count == 2  # start + end markers
    assert websocket.send_bytes.call_count == 3  # 3 audio chunks
    
    # Verify start marker
    websocket.send_json.assert_any_call({
        "type": "audio_start",
        "session_id": "test123",
        "format": "wav"
    })
    
    # Verify end marker  
    websocket.send_json.assert_any_call({
        "type": "audio_end", 
        "session_id": "test123"
    })

@pytest.mark.asyncio 
async def test_stream_tts_audio_cancellation():
    websocket = AsyncMock()
    session = VoiceSession("test123", websocket)
    session.cancel()  # Cancel before streaming
    
    streamer = AudioStreamer("http://localhost:8880")
    
    await streamer.stream_tts_audio("test text", session)
    
    # Should send cancellation message, no audio
    websocket.send_json.assert_called_once_with({
        "type": "audio_cancelled",
        "session_id": "test123"
    })
    websocket.send_bytes.assert_not_called()

@pytest.mark.asyncio
async def test_stream_tts_audio_http_error():
    websocket = AsyncMock()
    session = VoiceSession("test123", websocket)
    streamer = AudioStreamer("http://localhost:8880")
    
    # Mock HTTP error response
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    async def mock_post_context_manager(*args, **kwargs):
        return mock_response
    
    mock_client = MagicMock()
    mock_client.post.return_value.__aenter__ = mock_post_context_manager
    mock_client.post.return_value.__aexit__ = AsyncMock(return_value=None)
    
    async def mock_client_context_manager(*args, **kwargs):
        return mock_client
    
    with patch('audio_streamer.httpx.AsyncClient') as mock_async_client:
        mock_async_client.return_value.__aenter__ = mock_client_context_manager
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
        
        await streamer.stream_tts_audio("test text", session)
    
    # Should send error message (after sending start marker)
    assert websocket.send_json.call_count == 2
    websocket.send_json.assert_any_call({
        "type": "audio_start",
        "session_id": "test123", 
        "format": "wav"
    })
    websocket.send_json.assert_any_call({
        "type": "error",
        "message": "TTS failed with status 500"
    })