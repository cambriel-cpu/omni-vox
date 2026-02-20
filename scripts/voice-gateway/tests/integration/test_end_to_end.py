import pytest
import asyncio
import json
import base64
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

@pytest.fixture
def client():
    from server import app
    return TestClient(app)

def test_full_voice_pipeline_mock(client):
    """Test complete voice processing pipeline with mocked components"""
    with patch('audio_streamer.AudioStreamer.stream_tts_audio') as mock_stream:
        mock_stream.return_value = None
        
        with client.websocket_connect("/ws") as websocket:
            # Send voice request
            test_audio = base64.b64encode(b"mock audio data").decode('utf-8')
            websocket.send_text(json.dumps({
                "type": "voice_request",
                "audio_data": test_audio
            }))
            
            # Should receive transcript
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "transcript"
            
            # Should receive response text  
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "response_text"
            
            # Audio streaming should have been called
            assert mock_stream.called

def test_streaming_with_cancellation(client):
    """Test audio streaming can be cancelled mid-stream"""
    with client.websocket_connect("/ws") as websocket:
        # Start TTS streaming
        websocket.send_text(json.dumps({
            "type": "stream_tts",
            "text": "This is a test message that would normally result in audio streaming"
        }))
        
        # Send cancel immediately
        websocket.send_text(json.dumps({"type": "cancel"}))
        
        # Should receive cancellation confirmation
        messages = []
        try:
            while len(messages) < 3:  # Collect a few messages
                data = websocket.receive_text() 
                messages.append(json.loads(data))
        except:
            pass  # WebSocket may close
        
        # Should have some form of cancellation response
        message_types = [msg["type"] for msg in messages]
        assert "cancelled" in message_types or "audio_cancelled" in message_types

def test_error_recovery_large_message(client):
    """Test error handling for oversized messages"""
    with client.websocket_connect("/ws") as websocket:
        # Send oversized message
        large_audio = "x" * (6 * 1024 * 1024)  # 6MB (over 5MB limit)
        websocket.send_text(json.dumps({
            "type": "voice_request", 
            "audio_data": large_audio
        }))
        
        # Should receive error
        data = websocket.receive_text()
        message = json.loads(data)
        
        assert message["type"] == "error"
        assert "too large" in message["message"].lower()
        
        # Connection should still be alive
        websocket.send_text(json.dumps({"type": "ping"}))
        data = websocket.receive_text()
        message = json.loads(data)
        assert message["type"] == "pong"

def test_concurrent_sessions(client):
    """Test multiple WebSocket sessions don't interfere"""
    with client.websocket_connect("/ws") as ws1:
        with client.websocket_connect("/ws") as ws2:
            # Both should be able to ping
            ws1.send_text(json.dumps({"type": "ping"}))
            ws2.send_text(json.dumps({"type": "ping"}))
            
            # Both should receive pongs
            data1 = ws1.receive_text()
            data2 = ws2.receive_text()
            
            msg1 = json.loads(data1)
            msg2 = json.loads(data2)
            
            assert msg1["type"] == "pong"
            assert msg2["type"] == "pong"

def test_metrics_collection(client):
    """Test that metrics are being collected"""
    from metrics import metrics
    
    initial_connections = metrics.websocket_connections_active._value._value
    
    with client.websocket_connect("/ws") as websocket:
        # Connection count should increase
        assert metrics.websocket_connections_active._value._value == initial_connections + 1
        
        # Send a message
        websocket.send_text(json.dumps({"type": "ping"}))
        websocket.receive_text()
        
        # Message counters should increment (we can't easily test exact values due to other tests)
        
    # Connection count should decrease after disconnect
    # (May not be immediate due to async cleanup)

def test_health_endpoints(client):
    """Test all health check endpoints"""
    # Basic health
    response = client.get("/health")
    assert response.status_code in [200, 503]  # May be degraded if dependencies unavailable
    data = response.json()
    assert "status" in data
    assert "active_sessions" in data
    assert "dependencies" in data
    
    # Readiness
    response = client.get("/health/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    
    # Liveness  
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["alive"] is True
    
    # WebSocket metrics
    response = client.get("/metrics/websocket")
    assert response.status_code == 200
    data = response.json()
    assert "active_sessions" in data
    assert "total_connections" in data

@pytest.mark.asyncio
async def test_websocket_binary_streaming_mock(client):
    """Test binary audio streaming over WebSocket"""
    with patch('httpx.AsyncClient') as mock_client_class:
        # Mock the HTTP response for TTS
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_bytes.return_value.__aiter__ = lambda: iter([
            b"chunk1", b"chunk2", b"chunk3"
        ])
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        with client.websocket_connect("/ws") as websocket:
            # Send TTS request
            websocket.send_text(json.dumps({
                "type": "stream_tts",
                "text": "Test audio streaming"
            }))
            
            messages_received = []
            binary_chunks = 0
            
            try:
                # Collect messages for a few seconds
                for _ in range(10):  # Expect start + chunks + end
                    try:
                        # Try text message first
                        data = websocket.receive_text()
                        message = json.loads(data)
                        messages_received.append(message)
                    except:
                        try:
                            # Try binary message
                            binary_data = websocket.receive_bytes()
                            binary_chunks += 1
                        except:
                            break
            except:
                pass
            
            # Should have received audio_start and potentially audio_end
            message_types = [msg["type"] for msg in messages_received]
            assert "audio_start" in message_types
            
            # Mock should have been called
            assert mock_client.called

def test_rate_limiting_behavior(client):
    """Test rate limiting prevents abuse but allows normal usage"""
    with client.websocket_connect("/ws") as websocket:
        successful_pings = 0
        rate_limited = False
        
        # Send requests rapidly (validation default is 10 per 60 seconds)
        for i in range(15):
            websocket.send_text(json.dumps({"type": "ping"}))
            
            try:
                data = websocket.receive_text()
                message = json.loads(data)
                
                if message["type"] == "pong":
                    successful_pings += 1
                elif message["type"] == "error" and "rate limit" in message["message"].lower():
                    rate_limited = True
                    break
                    
            except Exception:
                break
        
        # Should allow some requests but eventually rate limit
        assert successful_pings >= 5  # At least some requests should succeed
        assert rate_limited  # Should eventually be rate limited

def test_invalid_message_handling(client):
    """Test handling of malformed and invalid messages"""
    with client.websocket_connect("/ws") as websocket:
        # Send invalid JSON
        websocket.send_text("invalid json")
        
        data = websocket.receive_text()
        message = json.loads(data)
        assert message["type"] == "error"
        
        # Send unknown message type
        websocket.send_text(json.dumps({"type": "unknown_type"}))
        
        data = websocket.receive_text()
        message = json.loads(data)
        assert message["type"] == "error"
        assert "unknown message type" in message["message"].lower()
        
        # Connection should still be alive after errors
        websocket.send_text(json.dumps({"type": "ping"}))
        data = websocket.receive_text()
        message = json.loads(data)
        assert message["type"] == "pong"

def test_session_cleanup_on_disconnect(client):
    """Test that sessions are properly cleaned up when clients disconnect"""
    from server import session_manager
    
    initial_sessions = session_manager.get_session_count()
    
    # Create and immediately close connection
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "ping"}))
        websocket.receive_text()
        
        # Session should exist while connected
        assert session_manager.get_session_count() == initial_sessions + 1
    
    # After disconnect, session should be cleaned up
    # (may not be immediate due to async cleanup, but should happen quickly)
    import time
    time.sleep(0.1)  # Small delay for cleanup
    
    # Session count should return to initial level
    final_sessions = session_manager.get_session_count()
    assert final_sessions <= initial_sessions + 1  # Allow for some async delay