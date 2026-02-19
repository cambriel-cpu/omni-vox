import httpx
import asyncio
import logging
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
        if session.is_cancelled:
            await session.websocket.send_json({
                "type": "audio_cancelled",
                "session_id": session.session_id
            })
            return
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Send start marker
                await session.websocket.send_json({
                    "type": "audio_start",
                    "session_id": session.session_id,
                    "format": "wav"
                })
                
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
                        await session.websocket.send_json({
                            "type": "error",
                            "message": f"TTS failed with status {response.status_code}"
                        })
                        return
                    
                    # Stream audio chunks as binary WebSocket frames
                    chunk_count = 0
                    async for chunk in response.aiter_bytes(8192):
                        # Check for cancellation
                        if session.is_cancelled:
                            await session.websocket.send_json({
                                "type": "audio_cancelled",
                                "session_id": session.session_id
                            })
                            return
                        
                        if chunk:  # Non-empty chunk
                            await session.websocket.send_bytes(chunk)
                            chunk_count += 1
                    
                    # Send completion marker
                    await session.websocket.send_json({
                        "type": "audio_end",
                        "session_id": session.session_id
                    })
                    
                    logger.info(f"Streamed {chunk_count} audio chunks for session {session.session_id}")
                    
        except httpx.TimeoutException:
            logger.error(f"TTS timeout for session {session.session_id}")
            await session.websocket.send_json({
                "type": "error",
                "message": "TTS request timed out"
            })
        except Exception as e:
            logger.error(f"TTS streaming error for session {session.session_id}: {e}")
            await session.websocket.send_json({
                "type": "error",
                "message": f"Streaming error: {str(e)}"
            })