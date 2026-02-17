# Omni Vox Containerization — Design Doc

**Date:** 2026-02-17  
**Status:** Approved  
**Phase:** 1 of 2  

## Summary
Move Omni Vox from a nohup process inside OpenClaw to its own Docker container on Unraid. Host networking, env-var config, read-only volume mounts. Zero regressions.

## Decisions
- Host networking (Sonos multicast, Tailscale access)
- No auth (Tailscale boundary, Authentik later)
- Read-only session transcript mount (better than current full-container access)
- Env vars for all secrets (HOOKS_TOKEN, OBSIDIAN_API_KEY)
- SOUL.md mounted read-only (picks up changes without rebuild)
- Same workspace repo (scripts/voice-gateway/)

## Container: python:3.11-slim, host network, port 7100, unless-stopped

## Full plan: See Obsidian Projects/OmniVox/Containerization Plan
