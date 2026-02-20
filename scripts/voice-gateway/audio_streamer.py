import httpx
import asyncio
import logging
import time
from typing import Optional
from session_manager import VoiceSession

logger = logging.getLogger(__name__)

class AudioStreamer:
    """Handles TTS streaming over WebSocket using binary frames"""
    
    def __init__(self, kokoro_base_url: str, timeout_seconds: int = 30):
        self.kokoro_base_url = kokoro_base_url
        self.timeout = httpx.Timeout(timeout_seconds, read=5.0)
    
    async def stream_tts_audio(self, text: str, session: VoiceSession) -> None:
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
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Send start marker
                await session.websocket.send_json({
                    "type": "audio_start",
                    "session_id": session.session_id,
                    "format": "wav"
                })
                metrics.message_sent("audio_start")
                metrics.audio_stream_started(session.session_id)
                
                # Stream TTS response
                async with client.post(
                    f"{self.kokoro_base_url}/v1/audio/speech",
                    json={
                        "model": "kokoro",
                        "voice": "bm_george", 
                        "input": text,
                        "response_format": "wav"
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status_code != 200:
                        metrics.tts_request_failed(f"http_{response.status_code}")
                        await session.websocket.send_json({
                            "type": "error",
                            "message": f"TTS failed with status {response.status_code}"
                        })
                        metrics.message_sent("error")
                        return
                    
                    metrics.tts_request_completed(tts_start_time)
                    
                    # Stream audio chunks as binary WebSocket frames
                    chunk_count = 0
                    async for chunk in response.aiter_bytes(8192):
                        # Check for cancellation
                        if session.is_cancelled:
                            await session.websocket.send_json({
                                "type": "audio_cancelled",
                                "session_id": session.session_id
                            })
                            metrics.message_sent("audio_cancelled")
                            metrics.audio_stream_cancelled(session.session_id)
                            return
                        
                        if chunk:  # Non-empty chunk
                            chunk_start = time.time()
                            await session.websocket.send_bytes(chunk)
                            chunk_latency = time.time() - chunk_start
                            metrics.audio_chunk_sent(chunk_latency)
                            chunk_count += 1
                    
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