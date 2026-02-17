# Voice Client PWA — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Progressive Web App that enables real-time voice conversation with Omni from any device (Android phone, Windows laptop, etc.), with optional Sonos speaker output.

**Architecture:** A Python backend (FastAPI) hosted on the Omnissiah serves the PWA frontend and handles three responsibilities: (1) audio transcription via local Whisper, (2) message relay to/from Omni via OpenClaw webhooks, and (3) TTS generation via local Kokoro. The PWA frontend captures mic audio, sends it to the backend, and plays back the TTS response — or routes it to Sonos via the existing bridge.

**Tech Stack:** FastAPI (Python), vanilla HTML/JS PWA frontend, OpenClaw webhook API (`/hooks/agent`), Whisper (local), Kokoro TTS (local), Sonos bridge (existing)

---

## Architecture Diagram

```
┌────────────────────────┐
│  PWA (Browser)         │
│  - Mic capture         │
│  - Audio playback      │
│  - Push-to-talk UI     │
├────────────────────────┤
│         ▼ audio blob   │
│         ▲ TTS audio    │
├────────────────────────┤
│  Voice Gateway         │
│  (FastAPI on Omnissiah)│
│  Port 7100             │
│                        │
│  POST /api/voice       │
│  1. Receive audio      │
│  2. Whisper → text     │
│  3. OpenClaw webhook   │
│     → wait for response│
│  4. Kokoro → TTS audio │
│  5. Return audio       │
│                        │
│  POST /api/sonos       │
│  → Forward to bridge   │
├────────────────────────┤
│         ▼              │
│  OpenClaw Gateway      │  ← /hooks/agent (async, poll for result)
│  :18789                │
│         ▼              │
│  Omni (main session)   │  ← Full context, tools, memory
│         ▼              │
│  Kokoro TTS :8880      │  ← Local GPU, ~100ms
│  Whisper STT :8000     │  ← Local GPU, ~1-2s
└────────────────────────┘
```

## Key Design Decisions

1. **Webhook + polling for OpenClaw integration:** The `/hooks/agent` endpoint returns 202 async. We'll use `deliver: false` and poll the session for the response. Alternative: use `/hooks/wake` to inject into main session, but that doesn't return a response at all. Best approach TBD — may need to test both.

2. **Synchronous API for the PWA:** The frontend POSTs audio and gets back TTS audio in one round-trip. The backend handles all the async complexity internally. Simple for the client.

3. **Kokoro for TTS (not ElevenLabs):** Keeps everything local, no cloud dependency, 96ms generation time proven. Talk Mode uses ElevenLabs — we're building something better for our use case.

4. **Push-to-talk first:** Simpler than always-listening. Press-and-hold to record, release to send. Can add voice activity detection later.

5. **Sonos routing is optional:** Default plays audio in the browser. Toggle to route to a specific Sonos speaker instead.

---

## Task 0: Enable OpenClaw Webhooks

**Files:**
- Modify: OpenClaw config via `gateway config.patch`

**Step 1: Generate a webhook token**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the output — this is our hooks token.

**Step 2: Enable hooks in OpenClaw config**

```bash
gateway config.patch with:
{
  "hooks": {
    "enabled": true,
    "token": "<generated-token>",
    "path": "/hooks",
    "allowedAgentIds": ["main"],
    "defaultSessionKey": "hook:voice",
    "allowRequestSessionKey": true,
    "allowedSessionKeyPrefixes": ["hook:"]
  }
}
```

**Step 3: Verify webhook is accessible**

```bash
curl -s -X POST http://localhost:18789/hooks/wake \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Webhook test","mode":"now"}'
```

Expected: 200 OK

**Step 4: Test agent endpoint**

```bash
curl -s -X POST http://localhost:18789/hooks/agent \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message":"Say hello from the voice client test","deliver":false,"timeoutSeconds":30}'
```

Expected: 202 with session info

**Step 5: Save token to file**

```bash
echo "<token>" > /root/.openclaw/voice-client-token
chmod 600 /root/.openclaw/voice-client-token
```

**Step 6: Commit config changes**

---

## Task 1: Voice Gateway Backend (FastAPI)

**Files:**
- Create: `scripts/voice-gateway/server.py`
- Create: `scripts/voice-gateway/requirements.txt`

**Step 1: Create requirements.txt**

```
fastapi>=0.110
uvicorn>=0.27
python-multipart>=0.0.6
httpx>=0.27
aiofiles>=23.0
```

**Step 2: Build the gateway server**

The server exposes:
- `GET /` — serves the PWA frontend
- `POST /api/voice` — full voice loop (audio in → text → Omni → TTS → audio out)
- `POST /api/transcribe` — Whisper only (for debugging)
- `POST /api/tts` — Kokoro only (for debugging)
- `POST /api/sonos/<speaker>` — proxy to Sonos bridge
- `GET /api/health` — health check

Core `/api/voice` flow:
```python
async def voice_endpoint(audio: UploadFile):
    # 1. Save uploaded audio to temp file
    # 2. Send to Whisper for transcription
    transcript = await transcribe(audio_path)
    # 3. Send transcript to OpenClaw via webhook
    response_text = await ask_omni(transcript)
    # 4. Generate TTS via Kokoro
    tts_audio = await generate_tts(response_text)
    # 5. Return JSON with transcript, response text, and base64 audio
    return {
        "transcript": transcript,
        "response": response_text,
        "audio": base64_encode(tts_audio),
        "audio_url": "/api/tts/last"  # alternative: stream URL
    }
```

**OpenClaw integration challenge:** The `/hooks/agent` endpoint is async (returns 202). Options to get the response:
- **Option A:** Use `deliver: true, channel: "discord"` and scrape the response from Discord — too hacky.
- **Option B:** Use sessions_list/sessions_history to poll for the response on the hook session key — requires gateway auth token.
- **Option C:** Use `/hooks/wake` to inject into main session as a system event, then poll session history — main session gets cluttered.
- **Option D:** Call the Claude API directly with SOUL.md context, bypassing OpenClaw — loses tools/memory but fastest.

**Recommended: Start with Option D (direct Claude API), with a plan to upgrade to Option B.**

For Option D, the gateway server calls the Anthropic API directly with:
- System prompt: contents of SOUL.md + recent memory context
- User message: the transcribed text
- This gives us a synchronous response in ~2-3 seconds

Later we can upgrade to full OpenClaw integration via webhook polling.

```python
async def ask_omni(transcript: str) -> str:
    # Phase 1: Direct Claude API
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",  # Sonnet for speed
        max_tokens=500,  # Keep responses short for voice
        system=SOUL_PROMPT,
        messages=[{"role": "user", "content": transcript}]
    )
    return response.content[0].text
```

**Step 3: Install and test**

```bash
cd scripts/voice-gateway
pip install -r requirements.txt
python server.py
```

**Step 4: Test each endpoint**

```bash
# Health
curl http://localhost:7100/api/health

# Transcribe
curl -X POST http://localhost:7100/api/transcribe -F "audio=@test.wav"

# TTS
curl -X POST http://localhost:7100/api/tts -H "Content-Type: application/json" -d '{"text":"Hello world"}'

# Full loop
curl -X POST http://localhost:7100/api/voice -F "audio=@test.wav"
```

**Step 5: Commit**

---

## Task 2: PWA Frontend

**Files:**
- Create: `scripts/voice-gateway/static/index.html`
- Create: `scripts/voice-gateway/static/app.js`
- Create: `scripts/voice-gateway/static/style.css`
- Create: `scripts/voice-gateway/static/manifest.json`

**Step 1: Build the HTML shell**

Mobile-first, single page:
- Large push-to-talk button (center of screen)
- Status indicator (Listening / Thinking / Speaking)
- Response text display
- Settings toggle (Sonos speaker select, volume)
- Install prompt for PWA

**Step 2: Build the JavaScript**

Core flow:
```javascript
// Push-to-talk: hold to record, release to send
button.addEventListener('pointerdown', startRecording);
button.addEventListener('pointerup', stopAndSend);

async function stopAndSend() {
    const audioBlob = recorder.stop();
    setStatus('thinking');
    
    const formData = new FormData();
    formData.append('audio', audioBlob, 'voice.webm');
    
    // Optional: add Sonos routing
    if (sonosEnabled) {
        formData.append('sonos_speaker', selectedSpeaker);
        formData.append('sonos_volume', volume);
    }
    
    const response = await fetch('/api/voice', {
        method: 'POST',
        body: formData
    });
    
    const data = await response.json();
    displayResponse(data.transcript, data.response);
    
    if (data.audio) {
        setStatus('speaking');
        await playAudio(data.audio);
        setStatus('idle');
    }
}
```

**Step 3: Style it**

Industrial / Mechanicum aesthetic to match the dashboard:
- Dark background (gunmetal)
- Amber/bronze accent for the talk button
- Pulsing animation while listening
- IBM Plex Mono font

**Step 4: PWA manifest**

```json
{
    "name": "Omni Voice",
    "short_name": "Omni",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#1a1a2e",
    "theme_color": "#c9a84c",
    "icons": [...]
}
```

**Step 5: Test on desktop browser**

Open `http://192.168.68.51:7100` in Chrome, test push-to-talk.

**Step 6: Test on Android**

Open the same URL on phone (must be on same network or Tailscale).
Test mic capture, response playback.
Add to home screen (PWA install).

**Step 7: Commit**

---

## Task 3: Sonos Integration

**Files:**
- Modify: `scripts/voice-gateway/server.py` (add Sonos proxy endpoint)

**Step 1: Add Sonos proxy**

```python
@app.post("/api/sonos/{speaker}")
async def play_on_sonos(speaker: str, volume: int = 65):
    """Proxy TTS audio to Sonos bridge on Magnus."""
    # Use the last generated TTS audio
    # Forward to Magnus bridge via SSH tunnel or direct if accessible
```

**Step 2: Add Sonos toggle to PWA**

Dropdown to select: "Phone Speaker" or specific Sonos room.
When Sonos is selected, after getting the voice response, also POST to `/api/sonos/<speaker>`.

**Step 3: Test end-to-end with Sonos**

**Step 4: Commit**

---

## Task 4: Docker Deployment

**Files:**
- Create: `scripts/voice-gateway/Dockerfile`
- Create: `scripts/voice-gateway/docker-compose.yml`

**Step 1: Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7100
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7100"]
```

**Step 2: docker-compose.yml** (for Unraid deployment)

**Step 3: Deploy and test**

**Step 4: Commit**

---

## Task 5: OpenClaw Webhook Integration (Phase 2)

**Files:**
- Modify: `scripts/voice-gateway/server.py`

Replace the direct Claude API call with proper OpenClaw webhook integration:

**Step 1: Implement webhook + session polling**

```python
async def ask_omni_via_openclaw(transcript: str) -> str:
    # 1. POST to /hooks/agent with deliver=false
    # 2. Get session key from 202 response
    # 3. Poll session history for the assistant response
    # 4. Return response text
```

**Step 2: Test full loop through OpenClaw**

This gives us the real Omni — tools, memory, personality, everything.

**Step 3: Commit**

---

## Summary

| Task | Description | Complexity | Dependencies |
|------|-------------|------------|-------------|
| 0 | Enable OpenClaw webhooks | Low | Config change |
| 1 | Voice Gateway backend | Medium | Whisper, Kokoro, Anthropic API |
| 2 | PWA frontend | Medium | Task 1 |
| 3 | Sonos integration | Low | Task 1, existing bridge |
| 4 | Docker deployment | Low | Tasks 1-3 |
| 5 | OpenClaw webhook upgrade | Medium | Task 0, Task 1 |

**Estimated total effort:** 4-6 hours across tasks

**Phase 1 MVP (Tasks 0-2):** Voice conversation with Omni from any browser. Uses direct Claude API for speed. ~2-3 hours.

**Phase 2 (Tasks 3-5):** Sonos routing + proper OpenClaw integration + Docker deployment. ~2-3 hours.
