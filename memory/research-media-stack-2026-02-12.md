# Media Stack Integration Research for OpenClaw

**Date:** 2026-02-12  
**Services:** Plex, Tautulli, Sonarr, Radarr, Overseerr  
**Platform:** Unraid + OpenClaw

---

## 1. Existing OpenClaw Skills

**ClawHub** (clawhub.ai) is OpenClaw's public skill registry with ~5,700 skills. The curated "awesome-openclaw-skills" list has ~3,000 vetted skills across many categories.

There is a **"Media & Streaming" category with 80 skills** and a **"Self-Hosted & Automation" category with 25 skills**. However, I could not find specific, dedicated skills for Plex, Sonarr, Radarr, Overseerr, or Tautulli in my search. The media skills appear to focus more on Spotify, YouTube, podcast, and general streaming integrations.

**Bottom line:** No ready-made *arr stack or Plex skills found. We'll likely need to build custom skills.

Install skills via: `npx clawhub@latest install <skill-slug>` or copy to `~/.openclaw/skills/`

---

## 2. Overseerr API

**Docs:** https://api-docs.overseerr.dev/ (Swagger UI)  
**Base URL:** `http://<host>:5055/api/v1`  
**Auth:** API key via `X-Api-Key` header

### Key Endpoints for an AI Assistant

| What you'd want to do | Endpoint | Method |
|---|---|---|
| **Search for a movie or show** | `/search?query=<title>` | GET |
| **Get movie details** | `/movie/{tmdbId}` | GET |
| **Get TV show details** | `/tv/{tmdbId}` | GET |
| **Request a movie** | `/request` | POST (body: `{ mediaType: "movie", mediaId: tmdbId }`) |
| **Request a TV show** | `/request` | POST (body: `{ mediaType: "tv", mediaId: tmdbId, seasons: [1,2] }`) |
| **List all requests** | `/request?take=20&skip=0` | GET |
| **Get request status** | `/request/{requestId}` | GET |
| **Approve a request** | `/request/{requestId}/approve` | POST |
| **Deny a request** | `/request/{requestId}/decline` | POST |
| **Trending movies** | `/discover/movies` | GET |
| **Trending TV** | `/discover/tv` | GET |
| **Get user list** | `/user` | GET |

**Why it matters:** Overseerr is the "front door" for media requests. An AI assistant could let family members say "I want to watch Dune" and handle the entire request flow conversationally.

---

## 3. Sonarr & Radarr APIs

Both use nearly identical API structures (they share the same codebase lineage).

**Sonarr docs:** https://sonarr.tv/docs/api/  
**Radarr docs:** https://radarr.video/docs/api/  
**Auth:** API key via `X-Api-Key` header  
**Sonarr base:** `http://<host>:8989/api/v3`  
**Radarr base:** `http://<host>:7878/api/v3`

### Key Sonarr Endpoints (TV Shows)

| What you'd want to do | Endpoint | Method |
|---|---|---|
| **List all series** | `/series` | GET |
| **Get a specific series** | `/series/{id}` | GET |
| **Add a new series** | `/series` | POST |
| **Search for a series (lookup)** | `/series/lookup?term=<query>` | GET |
| **View download queue** | `/queue` | GET |
| **View upcoming episodes** | `/calendar?start=&end=` | GET |
| **Check wanted/missing episodes** | `/wanted/missing` | GET |
| **Trigger search for episodes** | `/command` | POST (body: `{ name: "EpisodeSearch" }`) |
| **System status** | `/system/status` | GET |

### Key Radarr Endpoints (Movies)

| What you'd want to do | Endpoint | Method |
|---|---|---|
| **List all movies** | `/movie` | GET |
| **Get a specific movie** | `/movie/{id}` | GET |
| **Add a new movie** | `/movie` | POST |
| **Search for a movie (lookup)** | `/movie/lookup?term=<query>` | GET |
| **View download queue** | `/queue` | GET |
| **View upcoming releases** | `/calendar?start=&end=` | GET |
| **Check wanted/missing** | `/wanted/missing` | GET |
| **System status** | `/system/status` | GET |

**Why it matters:** These tell you what's downloading, what's missing, and let you add new content. Great for "what's downloading right now?" or "is Breaking Bad complete?"

---

## 4. Tautulli API

**Docs:** https://github.com/Tautulli/Tautulli/wiki/Tautulli-API-Reference  
**Base URL:** `http://<host>:8181/api/v2?apikey=<key>&cmd=<command>`

### Key Commands for an AI Assistant

| What you'd want to do | Command | Notes |
|---|---|---|
| **What's playing right now?** | `get_activity` | Shows all active streams with user, title, progress, quality, transcode info |
| **Recently added content** | `get_recently_added` | Params: `count`, `section_id` |
| **User watch history** | `get_history` | Filter by `user_id`, `section_id`, date range |
| **Library stats** | `get_library_media_info` | Stats per library section |
| **User stats** | `get_user_player_stats` | Per-user playback stats |
| **Most watched** | `get_home_stats` | Top movies, shows, users, platforms |
| **Server info** | `get_server_info` | Plex server details |
| **Get metadata** | `get_metadata` | Details about a specific item by `rating_key` |
| **Notify recently added** | `notify_recently_added` | Trigger a notification |

**Why it matters:** Tautulli is the "eyes" on your Plex server. "Who's watching right now?", "What did we add this week?", "What are the most watched shows?" — all answered here.

---

## 5. Plex API

**Base URL:** `http://<host>:32400`  
**Auth:** `X-Plex-Token` header or `?X-Plex-Token=<token>` query param

### Key Endpoints

| What you'd want to do | Endpoint |
|---|---|
| **List libraries** | `/library/sections` |
| **Browse a library** | `/library/sections/{id}/all` |
| **Search library** | `/search?query=<term>` |
| **Recently added** | `/library/recentlyAdded` |
| **On Deck (continue watching)** | `/library/onDeck` |
| **Current sessions** | `/status/sessions` |
| **Get item metadata** | `/library/metadata/{ratingKey}` |
| **Server identity** | `/identity` |

**Note:** For most monitoring tasks, **Tautulli wraps the Plex API** with much richer data and easier access. Direct Plex API is useful mainly for library search and "On Deck" info that Tautulli doesn't cover as well.

---

## 6. Integration Approach

### Recommendation: Build a Custom "Media Assistant" Skill

Since no existing OpenClaw skills cover this stack, we should build a custom skill. Here's what it would look like:

**Architecture: One unified skill called `media-assistant`**

```
skills/media-assistant/
  SKILL.md          ← Instructions for the AI on how/when to use each API
  config.env        ← API keys and URLs (Overseerr, Sonarr, Radarr, Tautulli, Plex)
```

The skill would be a **SKILL.md file** (OpenClaw skills are text-based instructions) that teaches the AI how to call each service's REST API using `curl` or `fetch`. No code needed — OpenClaw can make HTTP requests directly.

**The SKILL.md would cover these conversational scenarios:**

1. **"Request a movie/show"** → Search Overseerr → confirm with user → submit request
2. **"What's downloading?"** → Check Sonarr + Radarr queues
3. **"Who's watching?"** → Tautulli `get_activity`
4. **"What was added recently?"** → Tautulli `get_recently_added`
5. **"Is [show] complete?"** → Sonarr series detail + missing episodes
6. **"What should I watch?"** → Plex On Deck + Overseerr trending
7. **"Show me stats"** → Tautulli `get_home_stats`
8. **"Approve/deny requests"** → Overseerr approve/decline endpoints

### Why One Skill vs. Five?

- **One skill** = the AI understands the whole picture and can chain actions ("request Dune, then tell me when it finishes downloading")
- Easier to maintain, single config file for all API keys
- The services are tightly related — separating them would feel unnatural

---

## 7. Priority Recommendation

### Tier 1 — Build First (Highest Value)

**🥇 Overseerr** — This is the #1 integration. It lets anyone in the family say "I want to watch X" and the AI handles everything. Search, request, auto-approve (or notify you). This single integration replaces the need for family members to learn Overseerr's web UI.

**🥈 Tautulli** — "What's playing?", "What was added this week?", and watch stats are the most frequently asked questions on a home media server. Read-only and low-risk.

### Tier 2 — Add Next

**🥉 Sonarr + Radarr** — Useful for "what's downloading?" and "is this show complete?" queries. Slightly more technical but very handy for the server admin.

### Tier 3 — Nice to Have

**Plex direct API** — Most of what you'd want is already covered by Tautulli. Direct Plex API adds library search and On Deck, but it's lower priority since Tautulli + Overseerr cover the main use cases.

### Suggested Rollout Plan

1. **Week 1:** Create the `media-assistant` SKILL.md with Overseerr integration (search + request)
2. **Week 2:** Add Tautulli (activity + recently added + stats)
3. **Week 3:** Add Sonarr/Radarr (queue monitoring + missing episodes)
4. **Week 4:** Add Plex direct (search + on deck) and polish the unified experience

### What This Enables

> **Family member in Discord:** "Hey, can we get the new season of Severance?"  
> **OpenClaw:** *searches Overseerr* "Season 3 of Severance is available! Want me to request it?"  
> **Family member:** "Yes please!"  
> **OpenClaw:** *submits request* "Done! I'll let you know when it's ready to watch. 🎬"

> **You:** "What's everyone watching right now?"  
> **OpenClaw:** "2 active streams — Mom is watching The Bear S3E4 (direct play), and Dad is watching Oppenheimer (transcoding to 720p)."

---

## Resources

- ClawHub skill registry: https://clawhub.ai
- Awesome OpenClaw Skills: https://github.com/VoltAgent/awesome-openclaw-skills
- Overseerr API docs: https://api-docs.overseerr.dev/
- Tautulli API reference: https://github.com/Tautulli/Tautulli/wiki/Tautulli-API-Reference
- Sonarr API docs: https://sonarr.tv/docs/api/
- Radarr API docs: https://radarr.video/docs/api/
- Plex API (unofficial): https://github.com/Arcanemagus/plex-api/wiki
