#!/usr/bin/env python3
"""
Omni Vox — Voice gateway for the Machine Spirit
Integrates Whisper (transcription), Claude (LLM), Kokoro (TTS), and Sonos (playback)
"""
import os
import json
import time
import asyncio
import base64
import glob
import tempfile
import uuid
import logging
from pathlib import Path
from typing import Optional

import httpx
import soco
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, WebSocket, WebSocketDisconnect
from validation import MessageValidator, ValidationError
from session_manager import SessionManager, VoiceSession
from audio_streamer import AudioStreamer
from conversation import ConversationBuffer
from metrics import metrics, start_metrics_server


def _short_model_name(model: str) -> str:
    """Extract short name from model ID, e.g. 'anthropic/claude-haiku-4-5' -> 'haiku'"""
    parts = model.split("/")[-1].split("-")
    return parts[1] if len(parts) > 1 else parts[0]
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
WHISPER_URL = os.environ.get("WHISPER_URL", "http://192.168.68.100:8000/v1/audio/transcriptions")
WHISPER_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
KOKORO_URL = os.environ.get("KOKORO_URL", "http://192.168.68.51:8880/v1/audio/speech")
KOKORO_BASE_URL = os.environ.get("KOKORO_BASE_URL", "http://192.168.68.51:8880")
KOKORO_MODEL = "kokoro"
KOKORO_VOICE = "bm_george"
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "qD2z2CBGpZkjKjCxsv76")
OPENCLAW_GATEWAY = os.environ.get("OPENCLAW_GATEWAY", "http://127.0.0.1:18789")
HOOKS_SESSION_KEY = "hook:voice"
MAGNUS_BRIDGE = os.environ.get("MAGNUS_BRIDGE_URL", "http://100.72.144.77:5111")

# Global state
app = FastAPI(title="Omni Vox", version="1.1.0")

# Start metrics server on startup
startup_time = time.time()

@app.on_event("startup")
async def startup_event():
    global startup_time
    startup_time = time.time()
    metrics_port = int(os.getenv("METRICS_PORT", "9090"))
    start_metrics_server(metrics_port)
    logger.info("OmniVox WebSocket server started")
system_prompt = ""
local_speakers = []
hooks_token = None
conversation = ConversationBuffer(max_turns=20)

# WebSocket components
message_validator = MessageValidator()
session_manager = SessionManager()
audio_streamer = AudioStreamer(
    kokoro_base_url=KOKORO_BASE_URL
)

# CORS - allow all origins for now
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class TTSRequest(BaseModel):
    text: str
    tts_provider: str = "kokoro"

class VoiceResponse(BaseModel):
    transcript: str
    response: str
    audio: str  # base64 encoded
    timing: dict = {}

@app.on_event("startup")
async def startup_event():
    """Load SOUL.md and discover Sonos speakers at startup"""
    global system_prompt, local_speakers
    
    # Load SOUL.md
    soul_path = Path(os.environ.get("SOUL_PATH", "/root/.openclaw/workspace/SOUL.md"))
    if soul_path.exists():
        system_prompt = soul_path.read_text()
        print(f"✓ Loaded system prompt from SOUL.md ({len(system_prompt)} chars)")
    else:
        print("⚠ SOUL.md not found - using empty system prompt")
        system_prompt = "You are Omni, a helpful AI assistant."
    
    # Initialize OpenClaw hooks connection
    global hooks_token
    hooks_token = os.environ.get("HOOKS_TOKEN")
    if hooks_token:
        print("✓ OpenClaw hooks token loaded from env")
    else:
        print("⚠ HOOKS_TOKEN env var not set — voice interactions will fail")
    
    # Discover local Sonos speakers
    try:
        local_speakers = list(soco.discover(timeout=2) or [])
        if local_speakers:
            print(f"✓ Found {len(local_speakers)} local Sonos speakers:")
            for speaker in local_speakers:
                print(f"  - {speaker.player_name} ({speaker.ip_address})")
        else:
            print("⚠ No local Sonos speakers found")
    except Exception as e:
        print(f"⚠ Error discovering Sonos speakers: {e}")
        local_speakers = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Production WebSocket endpoint with security and session management"""
    await websocket.accept()
    metrics.websocket_connected()
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    try:
        async with session_manager.get_session(session_id, websocket) as session:
            logger.info(f"WebSocket connected: {session_id}")
            
            while True:
                try:
                    # Receive message with timeout
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    
                    # Validate message
                    try:
                        message = message_validator.validate_raw_message(data, session_id)
                        metrics.message_received(message.get("type", "unknown"))
                    except ValidationError as e:
                        metrics.validation_failed(str(e)[:20])  # Truncate error type
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e)
                        })
                        metrics.message_sent("error")
                        continue
                    
                    # Handle different message types
                    await handle_message(message, session)
                    
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    await websocket.send_json({"type": "ping"})
                    metrics.message_sent("ping")
                    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally: {session_id}")
        metrics.websocket_disconnected("normal")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        metrics.websocket_disconnected("error")

async def handle_message(message: dict, session: VoiceSession):
    """Handle validated WebSocket messages"""
    message_type = message.get("type")
    
    if message_type == "ping":
        await session.websocket.send_json({"type": "pong"})
        metrics.message_sent("pong")
        
    elif message_type == "voice_request":
        # Process voice input
        audio_data = message.get("audio_data", "")
        if audio_data:
            # For now, echo back - TODO: integrate with OpenClaw hooks
            await session.websocket.send_json({
                "type": "transcript", 
                "session_id": session.session_id,
                "text": "Mock transcript from voice data"  # TODO: Replace with real STT
            })
            metrics.message_sent("transcript")
            
            # Mock response - TODO: integrate with OpenClaw
            response_text = "Mock response to voice input"
            
            await session.websocket.send_json({
                "type": "response_text",
                "session_id": session.session_id, 
                "text": response_text
            })
            metrics.message_sent("response_text")
            
            # Stream TTS audio (metrics handled in audio_streamer)
            await audio_streamer.stream_tts_audio(response_text, session)
        else:
            await session.websocket.send_json({
                "type": "error",
                "message": "No audio data provided"
            })
            metrics.message_sent("error")
            
    elif message_type == "stream_tts":
        # Direct TTS streaming
        text = message.get("text", "")
        if text:
            await audio_streamer.stream_tts_audio(text, session)
        else:
            await session.websocket.send_json({
                "type": "error",
                "message": "No text provided"
            })
            metrics.message_sent("error")
            
    elif message_type == "cancel":
        # Cancel current operations
        session.cancel()
        await session.websocket.send_json({
            "type": "cancelled",
            "session_id": session.session_id
        })
        metrics.message_sent("cancelled")
        
    else:
        await session.websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {message_type}"
        })
        metrics.message_sent("error")

@app.get("/health")
async def health_check():
    """Comprehensive health check with dependency validation"""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "2.0.0-websocket-streaming",
        "active_sessions": session_manager.get_session_count(),
        "dependencies": {},
        "metrics": {
            "websocket_connections": len(session_manager.active_sessions),
            "total_connections": session_manager.get_session_count(),
            "audio_streams_active": len(metrics.audio_stream_start_times),
        }
    }
    
    overall_healthy = True
    
    # Check Kokoro TTS
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            kokoro_health = await client.get(f"{KOKORO_BASE_URL}/health")
            health_status["dependencies"]["kokoro"] = {
                "status": "healthy" if kokoro_health.status_code == 200 else "unhealthy",
                "url": KOKORO_BASE_URL,
                "response_time_ms": kokoro_health.elapsed.total_seconds() * 1000
            }
    except Exception as e:
        health_status["dependencies"]["kokoro"] = {
            "status": "unhealthy", 
            "url": KOKORO_BASE_URL,
            "error": str(e)
        }
        overall_healthy = False
    
    # Check Whisper STT  
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            whisper_health = await client.get(f"{WHISPER_URL.replace('/v1/audio/transcriptions', '/health')}")
            health_status["dependencies"]["whisper"] = {
                "status": "healthy" if whisper_health.status_code == 200 else "unhealthy",
                "url": WHISPER_URL,
                "response_time_ms": whisper_health.elapsed.total_seconds() * 1000
            }
    except Exception as e:
        health_status["dependencies"]["whisper"] = {
            "status": "unhealthy",
            "url": WHISPER_URL, 
            "error": str(e)
        }
        overall_healthy = False
    
    # Check OpenClaw Gateway
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            gateway_health = await client.get(f"{OPENCLAW_GATEWAY}/health")
            health_status["dependencies"]["openclaw_gateway"] = {
                "status": "healthy" if gateway_health.status_code == 200 else "unhealthy",
                "url": OPENCLAW_GATEWAY,
                "response_time_ms": gateway_health.elapsed.total_seconds() * 1000
            }
    except Exception as e:
        health_status["dependencies"]["openclaw_gateway"] = {
            "status": "degraded",  # Not critical for WebSocket streaming
            "url": OPENCLAW_GATEWAY,
            "error": str(e)
        }
    
    # Check local Sonos speakers
    health_status["dependencies"]["sonos_local"] = {
        "status": "healthy",
        "count": len(local_speakers),
        "speakers": [{"name": s.player_name, "ip": s.ip_address} for s in local_speakers]
    }
    
    # Overall status
    if not overall_healthy:
        health_status["status"] = "degraded"
    
    # Return appropriate HTTP status
    status_code = 200 if overall_healthy else 503
    return JSONResponse(content=health_status, status_code=status_code)

@app.get("/health/ready")
async def readiness_check():
    """Kubernetes-style readiness probe - checks if service can accept traffic"""
    ready = True
    checks = {}
    
    # WebSocket server must be able to accept connections
    checks["websocket_server"] = {"ready": True}
    
    # Audio streaming dependencies must be available
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            kokoro_check = await client.get(f"{KOKORO_BASE_URL}/health")
            checks["kokoro_tts"] = {
                "ready": kokoro_check.status_code == 200,
                "status_code": kokoro_check.status_code
            }
            if kokoro_check.status_code != 200:
                ready = False
    except Exception as e:
        checks["kokoro_tts"] = {"ready": False, "error": str(e)}
        ready = False
    
    result = {
        "ready": ready,
        "checks": checks,
        "timestamp": time.time()
    }
    
    return JSONResponse(content=result, status_code=200 if ready else 503)

@app.get("/health/live")
async def liveness_check():
    """Kubernetes-style liveness probe - checks if service is alive"""
    return {
        "alive": True,
        "timestamp": time.time(),
        "uptime_seconds": time.time() - startup_time if 'startup_time' in globals() else 0
    }

@app.get("/metrics/websocket")
async def websocket_metrics():
    """WebSocket-specific metrics for monitoring"""
    return {
        "active_sessions": session_manager.get_session_count(),
        "audio_streams_active": len(metrics.audio_stream_start_times),
        "timestamp": time.time()
    }

async def call_openclaw(message: str, timeout: float = 45.0, model: str = None) -> str:
    """Send message to OpenClaw via hooks and poll transcript for response"""
    
    sessions_dir = os.environ.get("SESSIONS_DIR", "/root/.openclaw/agents/main/sessions")
    send_time = time.time()
    
    # Record line counts of all existing session files before sending
    pre_counts = {}
    for f in glob.glob(f"{sessions_dir}/*.jsonl"):
        try:
            with open(f) as fh:
                pre_counts[f] = sum(1 for _ in fh)
        except IOError:
            pass
    
    # Use model-specific session keys so model override takes effect
    session_key = HOOKS_SESSION_KEY
    if model:
        # e.g. "hook:voice:haiku" from "anthropic/claude-haiku-4-5-20251001"
        short_name = _short_model_name(model)
        session_key = f"{HOOKS_SESSION_KEY}:{short_name}"

    # Build voice message with conversation context
    voice_prefix = "[Voice conversation from Chris via Omni Vox. Respond naturally and concisely - this will be spoken aloud via TTS. Do NOT use any tools (exec, sonos-play, tts, etc.) — just return text. Audio playback is handled by Omni Vox, not by you. Do NOT echo or quote back what Chris said — the transcript is already displayed in the UI. Just respond directly.]"
    
    # Inject conversation history if available
    history_context = conversation.format_context(session_key)
    if history_context:
        voice_message = f"{voice_prefix}\n\n{history_context}\n\nChris: {message}"
    else:
        voice_message = f"{voice_prefix}\n\n{message}"
    
    hook_payload = {
        "message": voice_message,
        "sessionKey": session_key,
        "deliver": False,
    }
    if model:
        hook_payload["model"] = model
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{OPENCLAW_GATEWAY}/hooks/agent",
            headers={"Authorization": f"Bearer {hooks_token}", "Content-Type": "application/json"},
            json=hook_payload,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise Exception(f"Hooks returned error: {result}")
        run_id = result.get("runId")
        print(f"  → OpenClaw run: {run_id}")
    
    # Poll session transcript files for the assistant response
    poll_start = time.time()
    while time.time() - poll_start < timeout:
        await asyncio.sleep(0.1)
        
        # Check all session files for new lines
        for f in sorted(glob.glob(f"{sessions_dir}/*.jsonl"), key=os.path.getmtime, reverse=True)[:5]:
            try:
                with open(f) as fh:
                    lines = fh.readlines()
                
                # Only look at new lines (after what we recorded before sending)
                start_line = pre_counts.get(f, 0)
                new_lines = lines[start_line:]
                
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    # Look for message entries with assistant role
                    if entry.get("type") != "message":
                        continue
                    msg = entry.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    
                    # Extract text content
                    content = msg.get("content", [])
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        texts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                texts.append(block.get("text", ""))
                        text = " ".join(texts).strip()
                    else:
                        continue
                    
                    # Skip empty and NO_REPLY
                    if text and text != "NO_REPLY":
                        print(f"  → Got response ({len(text)} chars) from {os.path.basename(f)}")
                        usage = msg.get("usage", {})
                        return text, usage
                        
            except IOError:
                continue
    
    raise Exception("Timeout waiting for OpenClaw response")


async def log_to_obsidian(transcript: str, response: str, timing: dict):
    """Append voice exchange to daily Obsidian vault transcript"""
    from datetime import datetime, timezone, timedelta
    
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%-I:%M %p")
    
    note_path = f"Daily/Voice/Voice-{date_str}.md"
    total = sum(v for k, v in timing.items() if isinstance(v, (int, float)))
    
    entry = (
        f"\n### {time_str}\n"
        f"> **Chris:** \"{transcript}\"\n\n"
        f"**Omni:** {response}\n\n"
        f"*stt: {timing.get('transcribe', 0)}s · llm: {timing.get('llm', 0)}s · tts: {timing.get('tts', 0)}s · total: {total:.1f}s*\n\n---\n"
    )
    
    # Read API key and URL from env
    api_key = os.environ.get("OBSIDIAN_API_KEY", "")
    base = os.environ.get("OBSIDIAN_URL", "https://192.168.68.51:27124")
    if not api_key:
        print("  ⚠ OBSIDIAN_API_KEY not set — skipping vault log")
        return
    headers = {"Authorization": f"Bearer {api_key}"}
    
    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        # Check if today's file exists
        check = await client.get(f"{base}/vault/{note_path}", headers=headers)
        
        if check.status_code == 200:
            # Append to existing file
            resp = await client.post(
                f"{base}/vault/{note_path}",
                headers={**headers, "Content-Type": "text/markdown"},
                content=entry,
            )
        else:
            # Create new file with header
            header = f"# Voice Log — {now.strftime('%B %d, %Y')}\n\n---\n"
            resp = await client.put(
                f"{base}/vault/{note_path}",
                headers={**headers, "Content-Type": "text/markdown"},
                content=header + entry,
            )
        
        if resp.status_code < 300:
            print(f"  ✓ Logged to Obsidian: {note_path}")
        else:
            print(f"  ⚠ Obsidian write failed: {resp.status_code} {resp.text}")


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe audio using Whisper"""
    try:
        # Read audio file
        audio_bytes = await audio.read()
        
        # Send to Whisper
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (audio.filename or "audio.wav", audio_bytes, audio.content_type)}
            data = {"model": WHISPER_MODEL}
            response = await client.post(WHISPER_URL, files=files, data=data)
            response.raise_for_status()
            result = response.json()
        
        return {"transcript": result.get("text", "")}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

async def generate_tts(text: str, provider: str = "kokoro") -> bytes:
    """Generate speech audio bytes using the specified TTS provider"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider == "elevenlabs":
            if not ELEVENLABS_API_KEY:
                raise Exception("ELEVENLABS_API_KEY not configured")
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
        else:
            response = await client.post(
                KOKORO_URL,
                json={"model": KOKORO_MODEL, "input": text, "voice": KOKORO_VOICE},
            )
        response.raise_for_status()
        return response.content


@app.get("/api/tts/providers")
async def tts_providers():
    """List available TTS providers"""
    providers = [{"id": "kokoro", "name": "Kokoro (Local)"}]
    if ELEVENLABS_API_KEY:
        providers.append({"id": "elevenlabs", "name": "ElevenLabs"})
    return {"providers": providers}


LLM_MODELS = [
    {"id": "anthropic/claude-opus-4-6", "name": "Claude Opus"},
    {"id": "anthropic/claude-sonnet-4-6", "name": "Claude Sonnet"},
    {"id": "anthropic/claude-haiku-4-5-20251001", "name": "Claude Haiku"},
]

@app.get("/api/llm/models")
async def llm_models():
    """List available LLM models"""
    return {"models": LLM_MODELS}


@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    """Generate speech using selected TTS provider"""
    try:
        audio_bytes = await generate_tts(request.text, request.tts_provider)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")

@app.post("/api/voice")
async def voice_interaction(
    audio: UploadFile = File(...),
    sonos_speaker: Optional[str] = Form(None),
    sonos_location: Optional[str] = Form("local"),
    sonos_volume: Optional[int] = Form(None),
    tts_provider: Optional[str] = Form("kokoro"),
    llm_model: Optional[str] = Form(None),
):
    """Main voice endpoint - transcribe, chat with Claude, generate TTS, optionally play on Sonos"""
    timing = {}
    print(f"  Voice request: tts={tts_provider}, llm={llm_model}, speaker={sonos_speaker}, location={sonos_location}, volume={sonos_volume}")
    
    try:
        # Step 1: Transcribe
        start = time.time()
        audio_bytes = await audio.read()
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (audio.filename or "audio.wav", audio_bytes, audio.content_type)}
            data = {"model": WHISPER_MODEL}
            response = await client.post(WHISPER_URL, files=files, data=data)
            response.raise_for_status()
            transcript = response.json().get("text", "")
        timing["transcribe"] = round(time.time() - start, 2)
        
        if not transcript:
            raise HTTPException(status_code=400, detail="No transcript generated")
        
        # Step 2: OpenClaw LLM (via hooks + transcript polling)
        start = time.time()
        if not hooks_token:
            raise HTTPException(status_code=500, detail="OpenClaw hooks token not configured")
        
        llm_response, llm_usage = await call_openclaw(transcript, model=llm_model)
        timing["llm"] = round(time.time() - start, 2)
        
        # Clean up response for TTS (strip OpenClaw markup)
        import re
        tts_text = llm_response
        # Extract [[tts:text]]...[[/tts:text]] if present, otherwise use full response
        tts_match = re.search(r'\[\[tts:text\]\](.*?)\[\[/tts:text\]\]', tts_text, re.DOTALL)
        if tts_match:
            tts_text = tts_match.group(1).strip()
        # Strip any remaining [[ ]] tags
        tts_text = re.sub(r'\[\[.*?\]\]', '', tts_text).strip()
        
        # Step 3: TTS
        start = time.time()
        audio_bytes = await generate_tts(tts_text, tts_provider or "kokoro")
        timing["tts"] = round(time.time() - start, 2)
        
        # Step 4: Sonos playback (optional)
        if sonos_speaker:
            start = time.time()
            try:
                await play_on_sonos(sonos_speaker, audio_bytes, sonos_volume, sonos_location)
                timing["sonos"] = round(time.time() - start, 2)
            except Exception as e:
                timing["sonos_error"] = str(e)
        
        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        clean_response = re.sub(r'\[\[.*?\]\]', '', re.sub(r'\[\[tts:text\]\].*?\[\[/tts:text\]\]', '', llm_response, flags=re.DOTALL)).strip()
        
        # Log exchange to Obsidian vault (daily voice transcript)
        try:
            await log_to_obsidian(transcript, clean_response, timing)
        except Exception as e:
            print(f"  ⚠ Obsidian log failed: {e}")
        
        # Store turn in conversation buffer for multi-turn context
        # Use the same session key logic as call_openclaw
        conv_session_key = HOOKS_SESSION_KEY
        if llm_model:
            short_name = _short_model_name(llm_model)
            conv_session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
        conversation.add_turn(conv_session_key, transcript, clean_response)
        
        return {
            "transcript": transcript,
            "response": clean_response,
            "audio": audio_b64,
            "timing": timing,
            "turnCount": conversation.turn_count(conv_session_key),
            "usage": {
                "input": llm_usage.get("input", 0),
                "output": llm_usage.get("output", 0),
                "cacheRead": llm_usage.get("cacheRead", 0),
                "total": llm_usage.get("totalTokens", 0),
                "cost": llm_usage.get("cost", {}).get("total", 0),
                "ttsChars": len(clean_response),
                "ttsProvider": tts_provider,
            } if llm_usage else None,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Voice interaction failed: {str(e)}")

async def play_on_sonos(speaker_name: str, audio_bytes: bytes, volume: Optional[int] = None, location: Optional[str] = "local"):
    """Play audio on Sonos speaker (local via soco, office via Magnus bridge)"""
    import socket
    import threading
    import urllib.parse
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    # Route by location — skip local matching for office speakers
    speaker = None
    if location != "office":
        for s in local_speakers:
            if speaker_name.lower() in s.player_name.lower():
                speaker = s
                break

    if not speaker:
        # Try office bridge (Magnus)
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{MAGNUS_BRIDGE}/play/{speaker_name}"
            if volume is not None:
                url += f"?volume={volume}"
            resp = await client.post(
                url,
                files={"audio": ("speech.mp3", audio_bytes, "audio/mpeg")},
            )
            if resp.status_code == 200:
                print(f"  → Played on office speaker '{speaker_name}' via Magnus bridge")
                return
            else:
                raise Exception(f"Magnus bridge error: {resp.status_code} {resp.text}")

    # Local Sonos playback
    original_volume = speaker.volume
    was_playing = speaker.get_current_transport_info()["current_transport_state"] == "PLAYING"

    if was_playing:
        speaker.pause()

    if volume is not None:
        speaker.volume = volume

    # Save audio to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        file_dir = os.path.dirname(temp_path)
        file_name = os.path.basename(temp_path)

        # Find free port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', 0))
        serve_port = sock.getsockname()[1]
        sock.close()

        # Get local IP reachable from Sonos
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((speaker.ip_address, 1400))
        local_ip = s.getsockname()[0]
        s.close()

        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=file_dir, **kwargs)
            def log_message(self, format, *args):
                pass

        httpd = HTTPServer(('0.0.0.0', serve_port), QuietHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        uri = f"http://{local_ip}:{serve_port}/{urllib.parse.quote(file_name)}"
        speaker.play_uri(uri)

        # Non-blocking: start a cleanup thread
        def cleanup():
            time.sleep(1)
            max_wait = 120
            waited = 0
            while waited < max_wait:
                try:
                    info = speaker.get_current_transport_info()
                    if info["current_transport_state"] != "PLAYING":
                        break
                except:
                    break
                time.sleep(0.5)
                waited += 0.5
            httpd.shutdown()
            if volume is not None:
                speaker.volume = original_volume
            if was_playing:
                try:
                    speaker.play()
                except:
                    pass
            Path(temp_path).unlink(missing_ok=True)

        threading.Thread(target=cleanup, daemon=True).start()

    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        if volume is not None:
            speaker.volume = original_volume
        raise

@app.post("/api/sonos/discover")
async def discover_sonos():
    """Discover Sonos speakers (local + Magnus bridge)"""
    speakers = []
    
    # Local speakers
    for s in local_speakers:
        speakers.append({
            "name": s.player_name,
            "ip": s.ip_address,
            "location": "local"
        })
    
    # Office speakers via Magnus bridge
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MAGNUS_BRIDGE}/speakers")
            if resp.status_code == 200:
                bridge_speakers = resp.json()
                for name, info in bridge_speakers.items():
                    speakers.append({
                        "name": info.get("name", name),
                        "ip": info.get("ip", ""),
                        "location": "office"
                    })
    except Exception as e:
        print(f"  ⚠ Magnus bridge unreachable: {e}")
    
    return {"speakers": speakers, "count": len(speakers)}

@app.post("/api/sonos/stop")
async def stop_sonos():
    """Stop all Sonos playback"""
    stopped = []
    
    # Stop local speakers
    for speaker in local_speakers:
        try:
            speaker.stop()
            stopped.append(speaker.player_name)
        except Exception as e:
            print(f"Error stopping {speaker.player_name}: {e}")
    
    return {"stopped": stopped, "count": len(stopped)}

@app.post("/api/voice/clear")
async def clear_conversation(llm_model: Optional[str] = Form(None)):
    """Clear conversation history for a model session"""
    if llm_model:
        short_name = _short_model_name(llm_model)
        session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
        conversation.clear(session_key)
        return {"cleared": session_key, "status": "ok"}
    else:
        conversation.clear()
        return {"cleared": "all", "status": "ok"}


@app.get("/api/voice/history")
async def get_conversation_history(llm_model: Optional[str] = None):
    """Get conversation history for a model session"""
    if llm_model:
        short_name = _short_model_name(llm_model)
        session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
    else:
        session_key = HOOKS_SESSION_KEY
    
    turns = conversation.get_history(session_key)
    return {
        "session_key": session_key,
        "turns": [{"user": t.user, "assistant": t.assistant, "timestamp": t.timestamp} for t in turns],
        "count": len(turns),
    }


# Mount static files last
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7100)
