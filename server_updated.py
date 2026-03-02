#!/usr/bin/env python3
"""
Omni Vox — Voice gateway for the Machine Spirit
Integrates Whisper (transcription), Claude (LLM), Kokoro (TTS), and Sonos (playback)

Enhanced with persistent conversation memory and cross-channel memory bridge.
"""
import os
import json
import time
import asyncio
import ssl
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
from memory_bridge import MemoryBridge  # NEW: Memory bridge integration
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
WHISPER_URL = os.environ.get("WHISPER_URL", "http://192.168.68.51:8000/v1/audio/transcriptions")
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
app = FastAPI(title="Omni Vox", version="2.0.0-persistent-memory")

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

# ENHANCED: Persistent conversation buffer with configurable storage
conversation_storage_dir = os.environ.get("CONVERSATION_STORAGE", "/tmp/omni-vox-conversations")
conversation = ConversationBuffer(max_turns=20, storage_dir=conversation_storage_dir)

# NEW: Memory bridge for cross-channel memory integration
sessions_dir = os.environ.get("SESSIONS_DIR", "/sessions") 
memory_bridge = MemoryBridge(sessions_dir=sessions_dir, memory_sync_interval=5)

# WebSocket components
message_validator = MessageValidator()
session_manager = SessionManager()
audio_streamer = AudioStreamer(
    kokoro_base_url=KOKORO_BASE_URL
)