import httpx
import asyncio
import logging
import time
import os
from typing import Optional
from session_manager import VoiceSession

logger = logging.getLogger(__name__)

class AudioStreamer:
    """Handles TTS streaming over WebSocket using binary frames"""
    
    def __init__(self, kokoro_base_url: str, timeout_seconds: int = 30):
        self.kokoro_base_url = kokoro_base_url
        self.timeout = httpx.Timeout(timeout_seconds, read=5.0)
        
        # ElevenLabs configuration
        self.elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        self.elevenlabs_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "qD2z2CBGpZkjKjCxsv76")
    
    async def stream_tts_audio(self, text: str, session: VoiceSession, provider: str = "kokoro") -> None:
        """Stream TTS audio chunks over WebSocket"""
        from metrics import metrics
        
        if session.is_cancelled:
            await session.websocket.send_json({
                "type": "audio_cancelled",
                "session_id": session.session_id
            })
            metrics.message_sent("audio_cancelled")
            return
        
        tts_start_time = metrics.tts_request_started()
        logger.info(f"TTS request using provider: {provider}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Send start marker
                await session.websocket.send_json({
                    "type": "audio_start",
                    "session_id": session.session_id,
                    "format": "opus"
                })
                metrics.message_sent("audio_start")
                metrics.audio_stream_started(session.session_id)
                
                # Configure TTS request based on provider
                if provider == "elevenlabs":
                    if not self.elevenlabs_api_key:
                        raise Exception("ElevenLabs API key not configured")
                    
                    tts_request = client.stream(
                        "POST", 
                        f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}",
                        headers={
                            "xi-api-key": self.elevenlabs_api_key,
                            "Content-Type": "application/json"
                        },
                        json={
                            "text": text,
                            "model_id": "eleven_multilingual_v2"
                        }
                    )
                else:
                    # Default to Kokoro
                    tts_request = client.stream(
                        "POST",
                        f"{self.kokoro_base_url}/v1/audio/speech", 
                        json={
                            "model": "kokoro",
                            "voice": "bm_george",
                            "input": text,
                            "response_format": "opus",
                            "stream": True
                        },
                        headers={"Content-Type": "application/json"}
                    )
                
                # Stream TTS response
                async with tts_request as response:
                    
                    if response.status_code != 200:
                        metrics.tts_request_failed(f"http_{response.status_code}")
                        await session.websocket.send_json({
                            "type": "error",
                            "message": f"TTS failed with status {response.status_code}"
                        })
                        metrics.message_sent("error")
                        return
                    
                    metrics.tts_request_completed(tts_start_time)
                    
                    # Stream audio chunks as they're generated
                    chunk_count = 0
                    total_bytes = 0
                    
                    async for chunk_data in response.aiter_bytes(chunk_size=4096):
                        # Check for cancellation before sending each chunk
                        if session.is_cancelled:
                            await session.websocket.send_json({
                                "type": "audio_cancelled", 
                                "session_id": session.session_id
                            })
                            metrics.message_sent("audio_cancelled")
                            metrics.audio_stream_cancelled(session.session_id)
                            return
                        
                        # Send audio chunk as WebSocket binary frame
                        if chunk_data:
                            chunk_start = time.time()
                            await session.websocket.send_bytes(chunk_data)
                            chunk_latency = time.time() - chunk_start
                            metrics.audio_chunk_sent(chunk_latency)
                            chunk_count += 1
                            total_bytes += len(chunk_data)
                            logger.debug(f"Sent chunk {chunk_count} ({len(chunk_data)} bytes) for session {session.session_id}")
                    
                    if chunk_count > 0:
                        logger.info(f"Streamed {chunk_count} audio chunks ({total_bytes} bytes total) for session {session.session_id}")
                    else:
                        logger.warning(f"No audio chunks received for session {session.session_id}")
                    
                    # Send completion marker
                    await session.websocket.send_json({
                        "type": "audio_end",
                        "session_id": session.session_id
                    })
                    metrics.message_sent("audio_end")
                    metrics.audio_stream_completed(session.session_id)
                    
                    logger.info(f"Streamed {chunk_count} audio chunks for session {session.session_id}")
                    
        except httpx.TimeoutException:
            logger.error(f"TTS timeout for session {session.session_id}")
            metrics.tts_request_failed("timeout")
            await session.websocket.send_json({
                "type": "error",
                "message": "TTS request timed out"
            })
            metrics.message_sent("error")
        except Exception as e:
            logger.error(f"TTS streaming error for session {session.session_id}: {e}")
            metrics.tts_request_failed("exception")
            await session.websocket.send_json({
                "type": "error",
                "message": f"Streaming error: {str(e)}"
            })
            metrics.message_sent("error")