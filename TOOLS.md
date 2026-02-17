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

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
