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

- **Container:** Ollama on Unraid (Docker, GPU passthrough, macvlan br0)
- **Macvlan IP:** `192.168.68.101`
- **API:** `http://192.168.68.101:11434` (OpenAI-compatible at `/v1`)
- **Model:** `qwen2.5:32b` (Q4_K_M, ~19GB, ~13.3GB VRAM)
- **OpenClaw ref:** `ollama/qwen2.5:32b`
- **Performance:** ~5.5 tok/s generation, cold start ~9s
- **Embedding model:** `bge-m3` (1024 dims, ~1.2GB, ~75ms warm latency, ~20s cold start)
- **Embedding endpoint:** `http://192.168.68.101:11434/v1/embeddings` (OpenAI-compatible)
- **Use for:** Subagent tasks, briefings, heartbeats, cron, bulk processing, Mem0 embeddings
- **⚠️ Macvlan shim route needed on Unraid host:** `sudo ip route add 192.168.68.101 dev macvlan-shim` (non-persistent, re-add after reboot)

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

- **Unraid host:** `ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51`
- **User:** `omni` (full sudo access, use `sudo docker` for container operations)

### Servo-Skull SSH
- **Direct Tailscale access:** `ssh -i /root/.ssh/id_ed25519 omni@100.69.9.99`  
- **Specs:** Pi 5, 8GB RAM, 128GB storage, Debian Linux aarch64
- **Status:** Online, SSH functional, ready for voice assistant configuration
- **Uptime:** 1+ days, fully operational

## Network

- **Unraid host:** 192.168.68.51 / omnissiah.local
- **OpenClaw container:** 192.168.68.99 (macvlan)
- **Ollama container:** 192.168.68.101 (macvlan)
- **Macvlan shim:** 192.168.68.200

### Tailscale Network
- **OpenClaw (me):** `100.110.15.105` - omni
- **Omnissiah:** `100.109.78.64` - omnissiah (Unraid host)
- **Servo-skull:** `100.69.9.99` - servo-skull (Pi 5)
- **Magnus:** `100.72.144.77` - magnus (Chris's Windows laptop, office)
- **Malcador:** `100.67.23.81` - malcador (Windows device)
- **Pixel 9 Pro:** `100.108.160.83` - pixel-9-pro (Chris's phone)

**Direct mesh connectivity:** All devices reachable via Tailscale IPs

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

- **Repository:** `https://github.com/cambriel-cpu/omni-vox` (clean project structure)
- **Container:** `omni-vox` on Unraid (host networking)  
- **Image:** `omni-vox:v1.0.1`
- **Port:** 7100
- **URL (home):** `http://192.168.68.51:7100`
- **URL (Tailscale):** `http://omnissiah.tail806b98.ts.net:7100`
- **Config:** `/mnt/user/appdata/omni-vox/.env` on Unraid (chmod 600)
- **Mounts:**
  - `/mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro`
  - `/mnt/user/appdata/openclaw/config/workspace/SOUL.md:/app/SOUL.md:ro`
- **Restart policy:** `unless-stopped`
- **Auto-starts:** Yes (Docker restart policy)
- **Logs:** `ssh omni@192.168.68.51 "sudo docker logs omni-vox"`
- **Deploy from GitHub:**
  ```bash
  # Use clean deployment script
  /root/.openclaw/workspace/scripts/deploy-omni-vox.sh
  ```
- **⚠️ `.env` changes need full recreate** — `docker restart` does NOT re-read `--env-file`. Must `stop + rm + run`.
- **Development:** Clone repository for VS Code debugging: `git clone https://github.com/cambriel-cpu/omni-vox.git`

## Qdrant (Vector Database)

- **Container:** `qdrant` on Unraid
- **Image:** `qdrant/qdrant:latest`
- **Ports:** 6333 (HTTP API), 6334 (gRPC)
- **Storage:** `/mnt/user/appdata/qdrant/storage/`
- **Snapshots:** `/mnt/user/appdata/qdrant/snapshots/`
- **Dashboard:** `http://192.168.68.51:6333/dashboard`
- **API:** `http://192.168.68.51:6333`
- **Restart policy:** `unless-stopped`
- **Purpose:** Vector store for Mem0 memory system (future: Horus Heresy knowledge base)

## Whisper (STT)

- **Container:** `faster-whisper` on Unraid (host networking)
- **Image:** `fedirz/faster-whisper-server:latest-cuda`
- **Port:** 8000
- **URL:** `http://192.168.68.51:8000`
- **Model:** `deepdml/faster-whisper-large-v3-turbo-ct2` (CUDA int8)
- **GPU:** Full GPU passthrough
- **Cache:** `/mnt/user/appdata/faster-whisper/cache:/root/.cache/:rw`
- **Restart policy:** `unless-stopped`
- **Previously:** macvlan at `192.168.68.100` — moved to host networking 2026-02-17

## Macvlan Shim Routes (Non-Persistent)

After any Unraid reboot, macvlan-shim routes must be re-added:
```bash
ssh omni@192.168.68.51 "
  sudo ip route add 192.168.68.99 dev macvlan-shim   # OpenClaw
  sudo ip route add 192.168.68.101 dev macvlan-shim  # Ollama
"
```
**Whisper no longer needs a shim route** (moved to host networking 2026-02-17).
Consider adding to Unraid User Scripts startup task for persistence.

## Unraid Host Path Mapping (Reference)

OpenClaw container mounts (easy to get wrong):
| Inside OpenClaw | On Unraid Host |
|----------------|----------------|
| `/root/.openclaw/` | `/mnt/user/appdata/openclaw/config/` |
| `/home/node/clawd` | `/mnt/user/appdata/openclaw/workspace/` |
| `/projects` | `/mnt/user/appdata/openclaw/projects/` |

**Common mistake:** `/mnt/user/appdata/openclaw/agents/` does NOT exist. Sessions are at `/mnt/user/appdata/openclaw/config/agents/main/sessions/`.

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
