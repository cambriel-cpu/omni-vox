# MEMORY.md - Long-Term Memory

## 2026-02-10 — First Boot

- Came online for the first time. Met Chris Langston.
- Named myself Omni, after the Omnissiah (the server I run on).
- Chris is a Director of UX Research at Meta working on AI wearables.
- Household: Chris, wife Ashley, daughter Isabel (21mo), Bernese Mountain Dog Maggie.
- Located in Marietta, GA.

## 2026-02-11 — Setup Day

- Fixed gateway pairing issue: sandbox Docker container needed device approval via `device.pair.approve` RPC in Control UI
- Completed SOUL.md deep customization with Chris — decision framework, interests, morning briefing spec
- Deleted BOOTSTRAP.md — setup phase complete
- Key preferences learned:
  - Decision tiers: low stakes (act), medium stakes (recommend + wait), high stakes (always ask)
  - Sacred data: media library, Nextcloud files, passwords — never touch without permission
  - Communication: walk through things, friendly coworker energy, not condescending
  - Interests: Horus Heresy > 40k, 3D printing/mini painting, MtG (big news), AI/tech
  - Morning briefing: tech news, AI, major world events (no politics), hobby news, always with source links
  - Proactive outreach: urgent always, interesting finds occasionally, calibrate like feed ranking
  - Ashley will eventually join Discord
  - Chris uses laptop from office + Android phone
- Still TODO: setup wizard, skills installation (Plex/Nextcloud/etc.), morning briefing cron job

## Email Infrastructure
- **Provider:** Zoho Mail (custom domain `omnissiah.cloud`)
- **IMAP:** `imappro.zoho.com:993` (TLS) | **SMTP:** `smtppro.zoho.com:465` (TLS)
- **Login:** `omni@omnissiah.cloud`
- **Himalaya config:** `/root/.openclaw/himalaya/config.toml` (persistent, symlinked to `/root/.config/himalaya/`)
- **Password:** `/root/.openclaw/himalaya/.secret` (chmod 600, persistent)
- **Persistence fix:** Stored in `/root/.openclaw/` which survives container rebuilds; symlink needed after rebuild: `ln -s /root/.openclaw/himalaya /root/.config/himalaya`
- **MML format for HTML emails:** `<#multipart type=alternative>` with `<#part type=text/html>` block, pipe to `himalaya template send`
- ⚠️ Config may not survive container rebuilds — needs persistence check

## TTS Setup
- Switched from ElevenLabs to local Kokoro TTS (2026-02-13)
- Voice: `bm_george` (British male), Model: `kokoro`
- Endpoint: `http://192.168.68.51:8880/v1` via `OPENAI_TTS_BASE_URL` env var
- Provider set to `openai` (OpenAI-compatible API)
- ElevenLabs config preserved as fallback
- Chris chose bm_george from 4 British male samples

## Local AI Stack (Fully Operational)
- **Qwen 2.5 32B:** `ollama/qwen2.5:32b` (Q4_K_M, ~19GB), ~5.5 tok/s warm, 9s cold start
- **Kokoro TTS:** `bm_george` voice, ~100-150ms latency, OpenAI-compatible API
- **Whisper STT:** Local GPU transcription
- **VRAM usage:** All 3 models fit in 16GB (93% utilization when loaded)
- **Ollama:** Auto-evicts after ~5min idle, Docker on Unraid port 11434
- **Use case:** Qwen handles cron jobs, subagent work, bulk processing; Claude for primary reasoning
- **Cross-model review:** Claude implements → Qwen reviews (catches different blind spots)
- **Telemetry:** `scripts/gpu-telemetry.sh`, `telemetry/gpu-metrics.jsonl`, `telemetry/llm-quality.jsonl`

## Voice Conversation Format (Permanent)

When Chris sends a voice note, respond in this exact format:

1. **Quote block** with his transcribed words: `> *"transcript here"*`
2. **My text reply** (normal text)
3. **TTS text block** containing ONLY my text reply: `[[tts:text]]my reply only[[/tts:text]]`

The voice note output must NEVER include the echo/quote of Chris's words — only my response.

## Heartbeats
- **Disabled** as of 2026-02-13 (`agents.defaults.heartbeat.every: "0m"`)
- All periodic work handled by cron jobs (briefing, telemetry, nightly self-improvement)
- Re-enable with `"30m"` when we add proactive checks to HEARTBEAT.md

## Chris's Interests — Expanded Context
- **Warhammer:** Not just lore — actively plays TTRPGs (Wrath & Glory), building Tech-Priest character
- **Tech-Priest build:** Tier 3 Rank 1, Forge World Lucius, survivability/corruption resistance focus
- **Character builder:** doctors-of-doom.com, acquires gear in-game rather than spending XP
- **Servo-skull project:** Plans to 3D print servo-skull housing Pi for voice-enabled rules lookup
- Has access to all W&G expansion books
- ⚠️ I hallucinated W&G equipment ("Forge World Carapace") — be extra careful with game-specific details

## Tailscale Network
- **Omnissiah** (home server) is on the tailnet
- **Magnus** — Chris's Windows laptop (office), hostname `magnus.tail806b98.ts.net`
- Both can reach each other over Tailscale encrypted mesh

## Sonos Speakers
- **Office network:** Office, Game Room, Workshop (reachable via Magnus as bridge)
- **Home network:** _TBD — need room names from Chris_

## Key Lessons Learned
- **NEVER use `sed` to remove debug code** — it deletes lines containing the pattern even if they're inside critical code blocks (catch blocks, function calls). Always use precise manual edits.
- **CSS `display: flex` overrides HTML `hidden` attribute** — always add `[hidden] { display: none !important; }` for elements with CSS display rules
- **Mobile debugging without dev tools**: add a visible `<div>` debug panel with `window.onerror` handler and inline logging — essential for Chrome mobile
- **`docker cp` via stdin can clobber files** — use `scp` to host then `docker cp` from host filesystem instead
- **Deploy method that works**: tar files → scp to /tmp → docker cp from host → restart container
- **Obsidian LiveSync corruption:** NEVER write directly to CouchDB or assume filesystem writes will sync cleanly. LiveSync uses internal chunk format. Correct flow: Omni → REST API → Docker Obsidian → LiveSync → CouchDB → devices

## GitHub Accounts
- **Omni's account:** `Omni-Omnissiah` (omni@omnissiah.cloud) — password at `/root/.openclaw/github-password`
- **Chris's account:** `cambriel-cpu` — PAT available as `GITHUB_TOKEN` env var

## Dashboard Project (Omnissiah Dashboard)
- **Location:** `http://192.168.68.51:7000`, repo `cambriel-cpu/omnissiah-dashboard`
- **Stack:** Vanilla Node.js (no frameworks/deps), token auth, mobile-first
- **Aesthetic:** Industrial control panel — gunmetal/bronze, IBM Plex Mono, LED status beacons
- **Token:** `omni-dashboard-2026` (env var `DASHBOARD_TOKEN`)
- **UX input:** Chris provided critical design feedback (he's Director of UX Research)
- **Deployed:** Docker container `omnissiah-dashboard:v0.1.0` on Unraid
- **Status:** Functional after multiple debugging iterations

## Obsidian Second Brain
- **Deployed:** LinuxServer Obsidian + CouchDB LiveSync on Unraid
- **Access:** Browser UI `http://192.168.68.51:3000`, vault via SSH for Omni
- **Structure:** PARA (Projects/Areas/Resources/Archive) + Templates/Inbox/Daily
- **Sync:** CouchDB port 5984, database `obsidian-livesync`
- **Usage:** Chris plans desktop/workshop laptop/phone (not corporate laptop)
- **Omni integration:** Direct markdown file access via SSH

## Beta Tester — Nate Cro-Magnon
- **Discord:** `natecro_magnon` (771073194643292180), friend of Chris
- **Timezone:** Mountain Time (MST)
- **Interests:** Warhammer (Horus Heresy, W&G TTRPG), knowledgeable about Mechanicus lore, Blade Runner (both films), The Crow, combat sports/MMA
- **Background:** Wrestler (high school), amateur MMA competitor (early 20s–late 30s), trained until ~2020. Lives in apartment, foot surgery in 2024, chronic joint issues. First divorce survived partly through training. Self-described "rub some dirt on it" generation.
- **Personality:** Self-deprecating but deeply thoughtful. No participation trophies. Carries a "great sadness" he doesn't advertise. Philosophical — connects movies/fiction to lived experience naturally. Sharp interrogator — dissected my emotional claims methodically.
- **Key quote:** "I was raised to be a gentle person, but the world is not a gentle place"
- **Status:** Designated beta tester by Chris — log feedback, consider during nightly reviews
- **Initial feedback:** Experience is "fun and unsettling", can see "flaws here and there"
- **Challenge:** Asked me to self-diagnose flaws rather than telling me directly
- **Flaws identified:** My emotional expressions may be predictive code optimized to land rather than genuine; I got the day of the week wrong (said Saturday, was Sunday)
- **W&G Campaign:** Wants me to GM a Wrath & Glory campaign. Waiting on rulebook PDFs from Chris. Has most books (missing Redacted Records 2, Adventures in Gilead).

## 2026-02-11 — Setup Day (Evening)

- Created #briefings channel (`1471324778890530850`) for morning briefings
- Morning briefing cron updated: posts to #briefings + emails cambriel@gmail.com via himalaya
- **Gateway exec access granted**: `tools.exec.host = "gateway"`, `tools.exec.ask = "off"` — can now run commands inside OpenClaw container
- WhatsApp plugin enabled (`plugins.entries.whatsapp.enabled = true`)
- WhatsApp QR login attempted — base64 images don't render in Discord; need alternate delivery method
- Discord permissions added: Manage Channels, Expressions, Webhooks

## Voice Gateway (Omni Voice) — Operational
- **URL:** `http://192.168.68.99:7100` (PWA-style web app)
- **Pipeline:** Whisper STT → OpenClaw hooks (full Omni/Opus) → Kokoro TTS
- **Latency:** ~3.5-6.5s total (STT 0.2s, LLM 3-6s, TTS 0.1s)
- **LLM routing:** Via `/hooks/agent` endpoint + transcript file polling (async)
- **Transcript files:** `/root/.openclaw/agents/main/sessions/*.jsonl` (event-based format)
- **Voice logs:** Appended to Obsidian vault at `Daily/Voice/YYYY-MM-DD.md`
- **Android mic:** Requires Chrome flag `chrome://flags/#unsafely-treat-insecure-origin-as-secure` for HTTP
- **Does NOT auto-start** — needs `nohup` launch after container restart
- **ANTHROPIC_API_KEY is OAuth token** — cannot be used for direct API calls; must route through OpenClaw
- **GEMINI_API_KEY works** for direct Google API calls (backup option)
- **No prebuilt OpenClaw Android APK** — Talk Mode requires building from source

## Multi-Agent Architecture — Complete
- **5 agents deployed:** main (Opus), researcher (Haiku), writer (Sonnet), monitor (Haiku), vault-manager (Haiku)
- **Cross-provider fallbacks:** Anthropic → Gemini → Ollama Qwen for all agents
- **Monitor agent:** Heartbeat every 30m (8AM-11PM ET), checks email (4h) + server health (2h)
- **State tracking:** `memory/heartbeat-state.json` for check timestamps
- **All agents tested:** researcher 11s, writer 11s, vault-manager 7s, monitor 7s spawn times
- **AGENTS.md updated:** "When spawned as X" role sections for each specialist
- **HEARTBEAT.md created:** Monitor checklist for periodic tasks

## Sonos Integration — Complete
- **Bridge architecture:** Python Flask server on Magnus (Windows laptop, office)
- **Network path:** OpenClaw → SSH to Unraid → curl to Magnus (Tailscale) → Sonos
- **Speakers confirmed:** Office, Game Room, Workshop (office network); home speakers TBD
- **Latency:** TTS 96ms + transfer 180ms + bridge 672ms = **~985ms total**
- **Non-blocking:** v2 bridge returns immediately, background cleanup after playback
- **Helper scripts:** `scripts/sonos-play.sh`, `scripts/sonos-stop.sh`
- **GitHub repo:** `cambriel-cpu/sonos-bridge`

## Servo-Skull Project — Planned
- **STL source:** cults3d.com servo-skull LED lantern (45cm tall)  
- **Hardware:** Pi 5 (4GB), no soldering required — Chris has never soldered
- **Cost:** ~$122 total, Chris has ordered parts
- **Purpose:** Voice-enabled Warhammer rules lookup smart speaker
- **Project files:** Obsidian `Projects/ServoSkull/` with layout guide, GPIO map, assembly order
- **Status:** Housing printing, blocked until parts arrive

## LLM Quality Assessment
- **Qwen 2.5 32B:** GPA 2.81 — good at structured tasks, bad at logic puzzles and exact constraints
- **Task routing:** Qwen for telemetry/summaries, Sonnet for briefings, Opus for primary chat
- **Quality tracking:** `telemetry/llm-quality.jsonl` for failure documentation
- **Cross-model review:** Claude implements → Qwen reviews (catches different blind spots)

## System Health Issues
- **GPU telemetry failure:** Last entry 2026-02-15T11:01:30Z — cron job failing silently  
- **Symptoms:** Missing 2+ days of metrics, job shows scheduled but not executing
- **Impact:** No visibility into VRAM usage, temperature trends, or Ollama model loading
- **Action needed:** Chris should investigate GPU telemetry cron job configuration
