import pytest
import json
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

# Import will be available after we modify server.py
# from server import app

@pytest.fixture
def client():
    from server import app
    return TestClient(app)

def test_websocket_connection(client):
    """Test basic WebSocket connection"""
    with client.websocket_connect("/ws") as websocket:
        # Send ping
        websocket.send_text(json.dumps({"type": "ping"}))
        
        # Receive pong
        data = websocket.receive_text()
        message = json.loads(data)
        
        assert message["type"] == "pong"

def test_websocket_rate_limiting(client):
    """Test rate limiting prevents abuse"""
    with client.websocket_connect("/ws") as websocket:
        # Send many requests rapidly
        for i in range(12):  # Over the limit of 10
            websocket.send_text(json.dumps({"type": "ping"}))
            if i < 10:
                data = websocket.receive_text()
                message = json.loads(data)
                assert message["type"] == "pong"
            else:
                # Should receive error for rate limiting
                data = websocket.receive_text()
                message = json.loads(data)
                assert message["type"] == "error"
                assert "rate limit" in message["message"].lower()

@pytest.mark.asyncio
async def test_websocket_voice_processing_mock(client):
    """Test voice processing with mocked TTS"""
    with patch('audio_streamer.AudioStreamer.stream_tts_audio') as mock_stream:
        mock_stream.return_value = None  # Mock successful streaming
        
        with client.websocket_connect("/ws") as websocket:
            # Send voice request
            websocket.send_text(json.dumps({
                "type": "voice_request",
                "audio_data": "dGVzdCBhdWRpbyBkYXRh"  # base64 "test audio data"
            }))
            
            # Should receive some response (exact response depends on implementation)
            data = websocket.receive_text()
            message = json.loads(data)
            
            # Should not be an error
            assert message.get("type") != "error"

def test_websocket_large_message_rejected(client):
    """Test that oversized messages are rejected"""
    with client.websocket_connect("/ws") as websocket:
        # Send oversized message
        large_text = "x" * 20000  # Over limit
        websocket.send_text(json.dumps({"text": large_text}))
        
        data = websocket.receive_text()
        message = json.loads(data)
        
        assert message["type"] == "error"
        assert "too large" in message["message"].lower()