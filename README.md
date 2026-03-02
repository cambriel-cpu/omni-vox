# Omni Vox

Voice gateway for the Machine Spirit - A comprehensive voice interaction system integrating speech-to-text, language models, text-to-speech, and audio playback.

## Features

- **🎙️ Speech Recognition** - Whisper STT integration for accurate transcription
- **🧠 AI Language Model** - OpenClaw integration with Claude/Sonnet/Haiku models  
- **🗣️ Text-to-Speech** - Kokoro TTS (local) and ElevenLabs (cloud) support
- **🔊 Audio Playback** - Sonos speaker integration (local and remote)
- **🌐 WebSocket API** - Real-time voice interaction with web interface
- **📊 Metrics & Monitoring** - Prometheus metrics and comprehensive health checks
- **🎛️ Web Interface** - PWA-style web application for voice interaction

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───▶│   Omni Vox  │───▶│  OpenClaw   │───▶│    Claude   │
│  (Browser)  │    │  (Gateway)  │    │  (Agent)    │    │    (LLM)    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                           │                   │
                           ▼                   ▼
                   ┌─────────────┐    ┌─────────────┐
                   │   Whisper   │    │   Kokoro    │
                   │    (STT)    │    │    (TTS)    │
                   └─────────────┘    └─────────────┘
                           │
                           ▼
                   ┌─────────────┐
                   │    Sonos    │
                   │ (Playback)  │
                   └─────────────┘
```

## Installation

### Environment Variables

Create a `.env` file with:

```bash
# Required
HOOKS_TOKEN=your_openclaw_hooks_token

# Service URLs (defaults shown)
WHISPER_URL=http://192.168.68.51:8000/v1/audio/transcriptions
KOKORO_URL=http://192.168.68.51:8880/v1/audio/speech
KOKORO_BASE_URL=http://192.168.68.51:8880
OPENCLAW_GATEWAY=http://127.0.0.1:18789

# Optional integrations
MAGNUS_BRIDGE_URL=http://100.72.144.77:5111
ELEVENLABS_API_KEY=your_elevenlabs_key
OBSIDIAN_API_KEY=your_api_key
OBSIDIAN_URL=https://192.168.68.51:27124
METRICS_PORT=9090
```

### Docker Deployment

```bash
docker build -t omni-vox:latest .

docker run -d \
  --name omni-vox \
  --network host \
  --restart unless-stopped \
  --env-file .env \
  -v /sessions/path:/sessions:ro \
  omni-vox:latest
```

## API Endpoints

- **WebSocket:** `ws://localhost:7100/ws` - Real-time voice interaction
- **HTTP:** `POST /api/voice` - Voice processing (upload audio file)
- **Health:** `GET /health` - Service health with dependencies
- **TTS:** `POST /api/tts` - Text-to-speech generation
- **Sonos:** `POST /api/sonos/discover` - Find speakers

## Usage

### Web Interface
1. Open `http://localhost:7100`
2. Allow microphone permissions  
3. Click and hold microphone button to record
4. Release to send for AI processing
5. Receive transcription, response, and audio playback

### HTTP API
```bash
curl -X POST http://localhost:7100/api/voice \
  -F "audio=@recording.wav" \
  -F "tts_provider=kokoro" \
  -F "sonos_speaker=Office"
```

## Development

### Local Setup
```bash
pip install -r requirements.txt
python server.py
```

Server runs on `http://localhost:7100`

## License

MIT License - see LICENSE file for details.