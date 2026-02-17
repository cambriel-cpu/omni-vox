# Omni Vox Containerization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move Omni Vox from a `nohup` process inside the OpenClaw container to its own Docker container on Unraid, with zero regressions.

**Architecture:** Refactor `server.py` to read all configuration from environment variables instead of filesystem paths. Build a Docker image with `python:3.11-slim`, deploy on Unraid with host networking so Sonos multicast and `localhost` OpenClaw hooks both work. Validate the new container end-to-end before killing the old process.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, Docker, host networking, Unraid

---

## Design Decisions

- **Host networking** — Sonos multicast discovery requires being on the LAN. Host mode also means `127.0.0.1:18789` (OpenClaw hooks) works without changes.
- **No auth** — Tailscale is the access boundary. Authentik is a future item.
- **Read-only mounts** — Session transcripts and SOUL.md mounted read-only for least privilege.
- **`--env-file`** — Secrets passed via a permission-restricted `.env` file on Unraid, not naked `-e` flags (which leak in `ps aux`).
- **Validate before cutover** — New container runs alongside old process; old process killed only after full validation passes.

## File Paths Reference

| File | Full Path |
|------|-----------|
| server.py | `/root/.openclaw/workspace/scripts/voice-gateway/server.py` |
| requirements.txt | `/root/.openclaw/workspace/scripts/voice-gateway/requirements.txt` |
| static/ | `/root/.openclaw/workspace/scripts/voice-gateway/static/` |
| Dockerfile (new) | `/root/.openclaw/workspace/scripts/voice-gateway/Dockerfile` |
| .dockerignore (new) | `/root/.openclaw/workspace/scripts/voice-gateway/.dockerignore` |
| openclaw.json | `/root/.openclaw/openclaw.json` |
| obsidian-rest-api-key | `/root/.openclaw/obsidian-rest-api-key` |
| SOUL.md | `/root/.openclaw/workspace/SOUL.md` |
| sessions dir | `/root/.openclaw/agents/main/sessions/` |

---

### Task 1: Create `.dockerignore`

**Files:**
- Create: `/root/.openclaw/workspace/scripts/voice-gateway/.dockerignore`

**Step 1: Write the `.dockerignore` file**

```
venv/
__pycache__/
*.pyc
.git/
*.md
!requirements.txt
```

**Step 2: Verify it exists**

Run: `cat /root/.openclaw/workspace/scripts/voice-gateway/.dockerignore`
Expected: The contents above.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/.dockerignore
git commit -m "chore: add .dockerignore for Omni Vox build"
```

---

### Task 2: Clean up `requirements.txt`

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/requirements.txt`

The current file includes `anthropic` (no longer used — LLM goes through OpenClaw hooks) and `aiofiles` (not imported). Remove unused deps.

**Step 1: Write the updated `requirements.txt`**

```
fastapi>=0.110
uvicorn>=0.27
python-multipart>=0.0.6
httpx>=0.27
soco>=0.30
```

**Step 2: Verify no missing imports**

Run: `grep -E "^(import|from)" /root/.openclaw/workspace/scripts/voice-gateway/server.py | grep -v -E "os|json|time|asyncio|base64|glob|tempfile|pathlib|typing|re|datetime|socket|threading|urllib|http\.server" | sort -u`

Expected output (these are the third-party imports):
```
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import soco
```

All covered by fastapi, httpx, soco, uvicorn. ✓

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/requirements.txt
git commit -m "chore: remove unused deps from requirements.txt"
```

---

### Task 3: Refactor config — extract Whisper URL

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (line 18)

**Step 1: Change the hardcoded `WHISPER_URL`**

Find (line 18):
```python
WHISPER_URL = "http://192.168.68.100:8000/v1/audio/transcriptions"
```

Replace with:
```python
WHISPER_URL = os.environ.get("WHISPER_URL", "http://192.168.68.100:8000/v1/audio/transcriptions")
```

**Step 2: Verify the change**

Run: `grep "WHISPER_URL" /root/.openclaw/workspace/scripts/voice-gateway/server.py | head -1`
Expected: `WHISPER_URL = os.environ.get("WHISPER_URL", "http://192.168.68.100:8000/v1/audio/transcriptions")`

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: extract WHISPER_URL to env var"
```

---

### Task 4: Refactor config — extract Kokoro URL

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (line 20)

**Step 1: Change the hardcoded `KOKORO_URL`**

Find (line 20):
```python
KOKORO_URL = "http://192.168.68.51:8880/v1/audio/speech"
```

Replace with:
```python
KOKORO_URL = os.environ.get("KOKORO_URL", "http://192.168.68.51:8880/v1/audio/speech")
```

**Step 2: Verify**

Run: `grep "KOKORO_URL" /root/.openclaw/workspace/scripts/voice-gateway/server.py | head -1`
Expected: `KOKORO_URL = os.environ.get("KOKORO_URL", "http://192.168.68.51:8880/v1/audio/speech")`

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: extract KOKORO_URL to env var"
```

---

### Task 5: Refactor config — extract OpenClaw gateway URL

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (line 23)

**Step 1: Change the hardcoded `OPENCLAW_GATEWAY`**

Find (line 23):
```python
OPENCLAW_GATEWAY = "http://127.0.0.1:18789"
```

Replace with:
```python
OPENCLAW_GATEWAY = os.environ.get("OPENCLAW_GATEWAY", "http://127.0.0.1:18789")
```

**Step 2: Verify**

Run: `grep "OPENCLAW_GATEWAY" /root/.openclaw/workspace/scripts/voice-gateway/server.py | head -1`
Expected: `OPENCLAW_GATEWAY = os.environ.get("OPENCLAW_GATEWAY", "http://127.0.0.1:18789")`

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: extract OPENCLAW_GATEWAY to env var"
```

---

### Task 6: Refactor config — extract hooks token from env var

This is the biggest change. Currently `startup_event()` reads `/root/.openclaw/openclaw.json` and extracts `hooks.token`. Replace with a direct env var read.

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (lines 51–60)

**Step 1: Replace the openclaw.json file read in `startup_event()`**

Find:
```python
    # Initialize OpenClaw hooks connection
    global hooks_token
    try:
        with open("/root/.openclaw/openclaw.json") as f:
            config = json.load(f)
        hooks_token = config.get("hooks", {}).get("token")
        if hooks_token:
            print("✓ OpenClaw hooks token loaded")
        else:
            print("⚠ No hooks token in config")
    except Exception as e:
        print(f"⚠ Failed to load OpenClaw config: {e}")
```

Replace with:
```python
    # Initialize OpenClaw hooks connection
    global hooks_token
    hooks_token = os.environ.get("HOOKS_TOKEN")
    if hooks_token:
        print("✓ OpenClaw hooks token loaded from env")
    else:
        print("⚠ HOOKS_TOKEN env var not set — voice interactions will fail")
```

**Step 2: Verify**

Run: `grep -A5 "Initialize OpenClaw" /root/.openclaw/workspace/scripts/voice-gateway/server.py`
Expected: Shows `os.environ.get("HOOKS_TOKEN")` instead of file read.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: read HOOKS_TOKEN from env instead of openclaw.json"
```

---

### Task 7: Refactor config — extract Obsidian API key from env var

Currently `log_to_obsidian()` reads `/root/.openclaw/obsidian-rest-api-key` from disk. Replace with env var.

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (inside `log_to_obsidian()`, ~line 198)

**Step 1: Replace the file read**

Find (inside `log_to_obsidian()`):
```python
    # Read API key
    api_key = Path("/root/.openclaw/obsidian-rest-api-key").read_text().strip()
    base = "https://192.168.68.51:27124"
```

Replace with:
```python
    # Read API key and URL from env
    api_key = os.environ.get("OBSIDIAN_API_KEY", "")
    base = os.environ.get("OBSIDIAN_URL", "https://192.168.68.51:27124")
    if not api_key:
        print("  ⚠ OBSIDIAN_API_KEY not set — skipping vault log")
        return
```

**Step 2: Verify**

Run: `grep -A4 "Read API key" /root/.openclaw/workspace/scripts/voice-gateway/server.py`
Expected: Shows `os.environ.get("OBSIDIAN_API_KEY"` and `os.environ.get("OBSIDIAN_URL"`.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: read OBSIDIAN_API_KEY and OBSIDIAN_URL from env"
```

---

### Task 8: Refactor config — extract SOUL.md path and sessions dir

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (lines 41 and 106)

**Step 1: Change SOUL.md path in `startup_event()`**

Find:
```python
    soul_path = Path("/root/.openclaw/workspace/SOUL.md")
```

Replace with:
```python
    soul_path = Path(os.environ.get("SOUL_PATH", "/root/.openclaw/workspace/SOUL.md"))
```

**Step 2: Change sessions dir in `call_openclaw()`**

Find:
```python
    sessions_dir = "/root/.openclaw/agents/main/sessions"
```

Replace with:
```python
    sessions_dir = os.environ.get("SESSIONS_DIR", "/root/.openclaw/agents/main/sessions")
```

**Step 3: Verify both changes**

Run: `grep -n "soul_path\|sessions_dir" /root/.openclaw/workspace/scripts/voice-gateway/server.py`
Expected: Both lines show `os.environ.get(...)`.

**Step 4: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "refactor: extract SOUL_PATH and SESSIONS_DIR to env vars"
```

---

### Task 9: Add health check with HEALTHCHECK instruction prep

Add a `/health` alias (the existing endpoint is `/api/health`) at the root for Docker HEALTHCHECK simplicity.

**Files:**
- Modify: `/root/.openclaw/workspace/scripts/voice-gateway/server.py` (after the existing `/api/health` endpoint)

**Step 1: Add `/health` alias endpoint**

Add this right after the existing `health_check()` function (after line ~93):

```python
@app.get("/health")
async def health_check_short():
    """Short health alias for Docker HEALTHCHECK"""
    return await health_check()
```

**Step 2: Verify**

Run: `grep -n "def health" /root/.openclaw/workspace/scripts/voice-gateway/server.py`
Expected: Two functions — `health_check` and `health_check_short`.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/server.py
git commit -m "feat: add /health alias for Docker HEALTHCHECK"
```

---

### Task 10: Write the Dockerfile

**Files:**
- Create: `/root/.openclaw/workspace/scripts/voice-gateway/Dockerfile`

**Step 1: Write the Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY static/ ./static/

# Health check — curl isn't in slim, use python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7100/health')" || exit 1

EXPOSE 7100

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7100"]
```

**Step 2: Verify the file**

Run: `cat /root/.openclaw/workspace/scripts/voice-gateway/Dockerfile`
Expected: Contents as above.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add scripts/voice-gateway/Dockerfile
git commit -m "feat: add Dockerfile for Omni Vox container"
```

---

### Task 11: Create the `.env` file on Unraid

This task requires SSH to Unraid. The `.env` file holds secrets and config for `docker run --env-file`.

**Files:**
- Create (on Unraid): `/mnt/user/appdata/omni-vox/.env`

**Step 1: Create the directory and `.env` file**

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "mkdir -p /mnt/user/appdata/omni-vox"
```

**Step 2: Write the `.env` file**

Read the actual secret values first:

```bash
HOOKS_TOKEN=$(cat /root/.openclaw/openclaw.json | python3 -c "import json,sys; print(json.load(sys.stdin)['hooks']['token'])")
OBSIDIAN_KEY=$(cat /root/.openclaw/obsidian-rest-api-key)
```

Then write via SSH:

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "cat > /mnt/user/appdata/omni-vox/.env << 'ENVEOF'
WHISPER_URL=http://192.168.68.100:8000/v1/audio/transcriptions
KOKORO_URL=http://192.168.68.51:8880/v1/audio/speech
OPENCLAW_GATEWAY=http://127.0.0.1:18789
HOOKS_TOKEN=${HOOKS_TOKEN}
SESSIONS_DIR=/sessions
SOUL_PATH=/app/SOUL.md
OBSIDIAN_API_KEY=${OBSIDIAN_KEY}
OBSIDIAN_URL=https://192.168.68.51:27124
ENVEOF
chmod 600 /mnt/user/appdata/omni-vox/.env"
```

**Step 3: Verify the file exists and has correct permissions**

Run: `ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "ls -la /mnt/user/appdata/omni-vox/.env && wc -l /mnt/user/appdata/omni-vox/.env"`
Expected: File exists, permissions `-rw-------`, 8 lines.

---

### Task 12: Build the Docker image on Unraid

**Files:**
- Uses: `/root/.openclaw/workspace/scripts/voice-gateway/` (all files)

**Step 1: Copy build context to Unraid**

```bash
cd /root/.openclaw/workspace/scripts/voice-gateway
tar czf /tmp/omni-vox-build.tar.gz --exclude=venv --exclude=__pycache__ --exclude='*.pyc' Dockerfile .dockerignore requirements.txt server.py static/
scp -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes /tmp/omni-vox-build.tar.gz omni@192.168.68.51:/tmp/
```

**Step 2: Build the image on Unraid**

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "
  mkdir -p /tmp/omni-vox-build && \
  cd /tmp/omni-vox-build && \
  tar xzf /tmp/omni-vox-build.tar.gz && \
  docker build -t omni-vox:v1.0.0 .
"
```

Expected: Ends with `Successfully built <hash>` and `Successfully tagged omni-vox:v1.0.0`. Build should take ~30-60s.

**Step 3: Verify image exists**

Run: `ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "docker images omni-vox"`
Expected: Shows `omni-vox  v1.0.0  <id>  <size>` — image size should be ~200-300MB.

---

### Task 13: Start the new container on Unraid (alongside old process)

**Important:** Do NOT kill the old process yet. Run the new container and validate it first.

**Files:**
- Uses: `.env` from Task 11, image from Task 12

**Step 1: Run the container**

The old nohup process is inside the OpenClaw container on port 7100. The new container uses host networking, so it would conflict on port 7100. Use port 7101 temporarily for validation.

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "
  docker run -d \
    --name omni-vox-test \
    --network host \
    --env-file /mnt/user/appdata/omni-vox/.env \
    -v /mnt/user/appdata/openclaw/agents/main/sessions:/sessions:ro \
    -v /mnt/user/appdata/openclaw/workspace/SOUL.md:/app/SOUL.md:ro \
    omni-vox:v1.0.0 \
    uvicorn server:app --host 0.0.0.0 --port 7101
"
```

**Step 2: Verify container is running**

Run: `ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "docker ps --filter name=omni-vox-test --format 'table {{.Names}}\t{{.Status}}'"`
Expected: `omni-vox-test  Up X seconds`

**Step 3: Check health endpoint**

Run: `curl -s http://192.168.68.51:7101/health | python3 -m json.tool`
Expected:
```json
{
    "status": "healthy",
    "services": {
        "whisper": "http://192.168.68.100:8000/v1/audio/transcriptions",
        "kokoro": "http://192.168.68.51:8880/v1/audio/speech",
        "llm": "openclaw-hooks",
        "sonos_local": 0
    },
    "speakers": { "local": [] }
}
```

Key checks: `llm` should say `openclaw-hooks` (not `missing hooks token`). `sonos_local: 0` is expected if no home speakers are on.

**Step 4: Check container logs for startup errors**

Run: `ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "docker logs omni-vox-test 2>&1 | tail -20"`
Expected: Shows `✓ Loaded system prompt from SOUL.md`, `✓ OpenClaw hooks token loaded from env`, and uvicorn startup message.

---

### Task 14: Validate — test PWA static files

**Step 1: Check the PWA loads**

Run: `curl -s -o /dev/null -w "%{http_code}" http://192.168.68.51:7101/`
Expected: `200`

**Step 2: Check app.js loads**

Run: `curl -s -o /dev/null -w "%{http_code}" http://192.168.68.51:7101/app.js`
Expected: `200`

---

### Task 15: Validate — test transcription endpoint

**Step 1: Generate a short test WAV file**

```bash
python3 -c "
import wave, struct, math
f = wave.open('/tmp/test-audio.wav', 'w')
f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
# 1 second of 440Hz tone
for i in range(16000):
    f.writeframes(struct.pack('h', int(32767 * math.sin(2 * math.pi * 440 * i / 16000))))
f.close()
print('Created /tmp/test-audio.wav')
"
```

**Step 2: Send to transcription endpoint**

Run: `curl -s -X POST -F "audio=@/tmp/test-audio.wav" http://192.168.68.51:7101/api/transcribe | python3 -m json.tool`
Expected: Returns `{"transcript": "..."}` — the transcript may be empty or nonsense (it's a tone, not speech), but the endpoint should return 200 and not error.

---

### Task 16: Validate — test TTS endpoint

**Step 1: Call TTS**

Run: `curl -s -o /tmp/test-tts-output.mp3 -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"text":"Testing Omni Vox containerization."}' http://192.168.68.51:7101/api/tts`
Expected: HTTP `200`, output file > 5KB.

**Step 2: Verify audio file**

Run: `ls -la /tmp/test-tts-output.mp3`
Expected: File exists, size > 5000 bytes.

---

### Task 17: Kill old process and switch to port 7100

Only do this after Tasks 13–16 all pass.

**Step 1: Kill the old nohup process inside OpenClaw container**

Run: `kill 16721 2>/dev/null; echo "killed old process"`

Verify: `curl -s http://192.168.68.99:7100/health` → should fail/timeout (old process gone).

**Step 2: Stop the test container**

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "docker stop omni-vox-test && docker rm omni-vox-test"
```

**Step 3: Start the production container on port 7100**

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "
  docker run -d \
    --name omni-vox \
    --network host \
    --restart unless-stopped \
    --env-file /mnt/user/appdata/omni-vox/.env \
    -v /mnt/user/appdata/openclaw/agents/main/sessions:/sessions:ro \
    -v /mnt/user/appdata/openclaw/workspace/SOUL.md:/app/SOUL.md:ro \
    omni-vox:v1.0.0
"
```

**Step 4: Verify production container**

Run: `curl -s http://192.168.68.51:7100/health | python3 -m json.tool`
Expected: Same healthy response as Task 13, Step 3.

**Step 5: Verify restart survival**

```bash
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "docker restart omni-vox && sleep 5 && curl -s http://localhost:7100/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[\"status\"])'"
```
Expected: `healthy`

---

### Task 18: Clean up workspace

**Files:**
- Remove: `/root/.openclaw/workspace/scripts/voice-gateway/venv/`
- Modify: `/root/.openclaw/workspace/TOOLS.md`
- Modify: `/root/.openclaw/workspace/memory/2026-02-17.md`

**Step 1: Remove the venv directory**

```bash
rm -rf /root/.openclaw/workspace/scripts/voice-gateway/venv
```

**Step 2: Verify removal**

Run: `ls /root/.openclaw/workspace/scripts/voice-gateway/`
Expected: `Dockerfile  __pycache__  .dockerignore  requirements.txt  server.py  static`

**Step 3: Update TOOLS.md**

Add/update the Omni Vox section in TOOLS.md:

```markdown
## Omni Vox (Voice Gateway)

- **Container:** `omni-vox` on Unraid (host networking)
- **Image:** `omni-vox:v1.0.0`
- **Port:** 7100
- **URL (home):** `http://192.168.68.51:7100`
- **URL (Tailscale):** `http://omnissiah.tail806b98.ts.net:7100`
- **Source:** `scripts/voice-gateway/` in workspace repo
- **Config:** `/mnt/user/appdata/omni-vox/.env` on Unraid
- **Mounts:** sessions (ro), SOUL.md (ro)
- **Restart policy:** `unless-stopped`
- **Auto-starts:** Yes (Docker restart policy)
- **Rebuild:** `docker build -t omni-vox:v1.0.0 scripts/voice-gateway/ && docker stop omni-vox && docker rm omni-vox && docker run ...`
```

**Step 4: Commit everything**

```bash
cd /root/.openclaw/workspace
git add -A
git commit -m "feat: containerize Omni Vox — Docker deployment on Unraid

- Dockerfile with python:3.11-slim, HEALTHCHECK
- All config via env vars (no filesystem reads)
- .dockerignore to exclude venv, pycache, .git
- Removed local venv (no longer needed)
- Updated TOOLS.md with deployment info"
```

---

## Rollback Plan

If the new container doesn't work after cutover (Task 17):

```bash
# On Unraid — stop the broken container
ssh omni@192.168.68.51 "docker stop omni-vox"

# Inside OpenClaw container — set required env vars and restart old process
export HOOKS_TOKEN=$(python3 -c "import json; print(json.load(open('/root/.openclaw/openclaw.json'))['hooks']['token'])")
export OBSIDIAN_API_KEY=$(cat /root/.openclaw/obsidian-rest-api-key)
cd /root/.openclaw/workspace/scripts/voice-gateway
nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 7100 &
```

**Note:** `HOOKS_TOKEN` and `OBSIDIAN_API_KEY` have no file-read fallback — they MUST be set as env vars. All URL vars have defaults matching the original hardcoded values and work without being set.

---

## Logging Strategy

- **Container logs:** `docker logs omni-vox` (stdout/stderr from uvicorn + print statements)
- **Persistent logging:** Not configured in Phase 1 — Docker default log driver stores logs until container removal
- **Voice exchange logs:** Written to Obsidian vault at `Daily/Voice/Voice-YYYY-MM-DD.md` (unchanged)
- **Future:** Consider Docker log rotation config or mounting a log volume

---

## Success Criteria

- [ ] PWA loads at `http://192.168.68.51:7100`
- [ ] Health endpoint returns `{"status": "healthy"}` with `hooks_token` present
- [ ] TTS endpoint returns audio for test text
- [ ] Transcription endpoint processes audio files
- [ ] Reachable from Tailscale at `http://omnissiah.tail806b98.ts.net:7100`
- [ ] Survives `docker restart omni-vox`
- [ ] Old nohup process removed from OpenClaw container
- [ ] venv removed from workspace
- [ ] Secrets not visible in `ps aux` (using `--env-file`)
