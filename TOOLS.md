# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## TTS

- **Provider:** Kokoro (local, GPU-accelerated)
- **API:** `http://192.168.68.51:8880/v1` (OpenAI-compatible)
- **Voice:** `bm_george` (British male)
- **Model:** `kokoro`
- **Config:** `OPENAI_TTS_BASE_URL` env var + `messages.tts.provider=openai`
- **Fallback:** ElevenLabs config still in place (switch provider back to `elevenlabs`)

## Local LLM (Ollama)

- **Container:** Ollama on Unraid (Docker, GPU passthrough)
- **API:** `http://192.168.68.51:11434` (OpenAI-compatible at `/v1`)
- **Model:** `qwen2.5:32b` (Q4_K_M, ~19GB, ~13.3GB VRAM)
- **OpenClaw ref:** `ollama/qwen2.5:32b`
- **Performance:** ~5.5 tok/s generation, cold start ~9s
- **Use for:** Subagent tasks, briefings, heartbeats, cron, bulk processing

## Google Account
- **Email:** omni.omnissiah@gmail.com
- **Password:** stored at `/root/.openclaw/google-password` (chmod 600)
- **Purpose:** Google Calendar sharing, other Google services with Chris

## GitHub

- **Account:** Omni-Omnissiah
- **Email:** omni@omnissiah.cloud
- **Password:** stored at `/root/.openclaw/github-password` (chmod 600)
- **Previous account (Chris's):** `cambriel-cpu` — PAT available as `GITHUB_TOKEN` env var

## SSH

- **Unraid host:** `ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51`
- **User:** `omni` (docker group, no root)

## Network

- **Unraid host:** 192.168.68.51 / omnissiah.local
- **OpenClaw container:** 192.168.68.99 (macvlan)
- **Macvlan shim:** 192.168.68.200

### Tailscale
- **Omnissiah:** On the tailnet (home server)
- **Magnus:** Chris's Windows laptop (office), `magnus.tail806b98.ts.net`

### Sonos Speakers
- **Office network (via Magnus bridge):** Office, Game Room, Workshop
- **Home network (direct from OpenClaw):** _TBD — get room names from Chris_

## Obsidian Second Brain

- **Container:** `obsidian` (ghcr.io/linuxserver/obsidian)
- **Browser UI:** `http://192.168.68.51:3000` (HTTPS: port 3001)
- **Login:** user `chris`, password `omnissiah-vault-2026`
- **Vault path (on Unraid):** `/mnt/user/appdata/obsidian/config/vault/`
- **Access from Omni:** SSH to Unraid, read/write vault files directly
- **Structure:** PARA (Projects / Areas / Resources / Archive) + Templates, Inbox, Daily

### Obsidian LiveSync (CouchDB)

- **Container:** `obsidian-couchdb`
- **Endpoint:** `http://192.168.68.51:5984`
- **Database:** `obsidian-livesync`
- **Login:** user `omni`, password `omnissiah-sync-2026`
- **Purpose:** Syncs vault between browser instance and native Obsidian apps
- **Setup on native apps:** Install "Self-hosted LiveSync" community plugin, configure with above endpoint + credentials

### Local REST API
- **Endpoint:** `https://192.168.68.51:27124`
- **API key:** stored at `/root/.openclaw/obsidian-rest-api-key`
- **Auth header:** `Authorization: Bearer <key>`
- **TLS:** Self-signed cert (use `-k` with curl, cert issued for `localhost`)
- **Bind:** `0.0.0.0` (LAN-accessible)

### Writing to the Vault
- **Preferred:** Use the Local REST API (above) — proper Obsidian integration, triggers LiveSync
- **Alternative:** SSH to filesystem: `/mnt/user/appdata/obsidian/config/vault/`
- **NEVER** write directly to CouchDB — LiveSync's chunk format is internal and undocumented
- For phone to pick up changes: LiveSync Settings → Rebuild → "Fetch from remote"

## Omni Vox (Voice Gateway)

- **Container:** `omni-vox` on Unraid (host networking)
- **Image:** `omni-vox:v1.0.0`
- **Port:** 7100
- **URL (home):** `http://192.168.68.51:7100`
- **URL (Tailscale):** `http://omnissiah.tail806b98.ts.net:7100`
- **Source:** `scripts/voice-gateway/` in workspace repo
- **Config:** `/mnt/user/appdata/omni-vox/.env` on Unraid (chmod 600)
- **Mounts:**
  - `/mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro`
  - `/mnt/user/appdata/openclaw/config/workspace/SOUL.md:/app/SOUL.md:ro`
- **Restart policy:** `unless-stopped`
- **Auto-starts:** Yes (Docker restart policy)
- **Logs:** `ssh omni@192.168.68.51 "docker logs omni-vox"`
- **Rebuild & redeploy:**
  ```bash
  cd /root/.openclaw/workspace/scripts/voice-gateway
  tar czf /tmp/omni-vox-build.tar.gz --exclude=venv --exclude=__pycache__ --exclude='*.pyc' Dockerfile .dockerignore requirements.txt server.py static/
  scp -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes /tmp/omni-vox-build.tar.gz omni@192.168.68.51:/tmp/
  ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "cd /tmp/omni-vox-build && tar xzf /tmp/omni-vox-build.tar.gz && docker build -t omni-vox:v1.0.0 . && docker stop omni-vox && docker rm omni-vox && docker run -d --name omni-vox --network host --restart unless-stopped --env-file /mnt/user/appdata/omni-vox/.env -v /mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro -v /mnt/user/appdata/openclaw/config/workspace/SOUL.md:/app/SOUL.md:ro omni-vox:v1.0.0"
  ```
- **Networking note:** Whisper container (192.168.68.100) requires macvlan-shim route on Unraid. Added on 2026-02-17 via privileged Docker container. Route may need re-adding after Unraid reboot:
  ```bash
  ssh omni@192.168.68.51 "docker run --rm --privileged --network host alpine ip route add 192.168.68.100 dev macvlan-shim"
  ```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
