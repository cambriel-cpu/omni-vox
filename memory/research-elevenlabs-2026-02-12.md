# ElevenLabs TTS + OpenClaw Research
**Date:** 2026-02-12

## 1. ElevenLabs Pricing — What Plan Makes Sense?

| Plan | Price/mo | Characters | Overage | Voice Cloning |
|------|----------|-----------|---------|---------------|
| **Free** | $0 | 10k (Multilingual) / 20k (Flash) | N/A | ❌ |
| **Starter** | $5 | 30k / 60k | N/A | Instant Clone |
| **Creator** | $11 | 100k / 200k | $0.30/1k chars | 1 Pro Clone |
| **Pro** | $99 | 500k / 1M | $0.24/1k chars | 1 Pro Clone |

**Recommendation: Starter ($5/mo) or Creator ($11/mo)**

For occasional voice messages (not constant streaming), the **Starter plan at $5/mo** is the sweet spot. 30,000 characters ≈ roughly 30-50 voice messages of moderate length. If you find yourself bumping into limits or want voice cloning (custom voice), step up to **Creator at $11/mo** which gives 100k chars + overage support + 1 Professional Voice Clone.

> **Rough math:** A typical Discord voice message response is ~200-500 characters. At 30k chars/month on Starter, that's 60-150 voice messages per month — plenty for personal assistant use.

---

## 2. OpenClaw TTS Configuration

OpenClaw has **built-in ElevenLabs TTS support** — no plugins needed! It's configured in `openclaw.json` under `messages.tts`.

### Config to add to `~/.openclaw/openclaw.json`:

```json5
{
  messages: {
    tts: {
      // Enable auto-TTS: "off" | "always" | "inbound" | "tagged"
      // "inbound" = only reply with voice when user sends voice
      // "tagged" = only when agent includes [[tts]] tags
      // "always" = every response gets voice
      auto: "tagged",  // recommended starting point

      // Which provider to use
      provider: "elevenlabs",  // options: "elevenlabs" | "openai" | "edge" (free/local)

      // ElevenLabs settings
      elevenlabs: {
        voiceId: "pMsXgVXv3BLzUgSXRplE",  // default voice (see Voice Selection below)
        modelId: "eleven_multilingual_v2",   // best quality model
        voiceSettings: {
          stability: 0.5,        // 0-1, higher = more consistent
          similarityBoost: 0.75, // 0-1, higher = closer to original voice
          style: 0.0,            // 0-1, higher = more expressive
          useSpeakerBoost: true,
          speed: 1.0,            // 0.5-2.0
        },
      },
    },
  },
}
```

### TTS Modes Explained:
- **`"off"`** — No automatic TTS
- **`"always"`** — Every reply becomes voice audio
- **`"inbound"`** — Only reply with voice when user sends a voice message (good for "reply in kind")
- **`"tagged"`** — Agent decides when to use voice via `[[tts]]` tags in its response (most control, recommended)

### Provider Fallback:
OpenClaw automatically falls back through providers: if ElevenLabs fails, it tries OpenAI TTS, then Edge TTS (free, built-in). So you always get voice even if an API is down.

---

## 3. Voice Selection

### Default ElevenLabs Voice
The default voice ID `pMsXgVXv3BLzUgSXRplE` is **"Eli"** — a standard ElevenLabs voice.

### How to Pick a Voice:
1. Go to **https://elevenlabs.io/voice-library** — browse hundreds of community and premade voices
2. Find one you like, click it, and grab the **Voice ID** from the URL or voice settings
3. Put that ID in `elevenlabs.voiceId` in your config

### Popular Voice Options:
- Browse the ElevenLabs Voice Library for categories like: Narration, Conversational, Characters
- You can filter by language, accent, age, gender, use case
- On Starter plan: use any premade or community voice
- On Creator+ plan: create a **Professional Voice Clone** (clone anyone's voice from audio samples)

### Runtime Voice Switching:
The agent can switch voices per-message using inline directives:
```
[[tts:voiceId=ABC123DEF456]]
```
This means Omni could theoretically use different voices for different contexts.

---

## 4. Integration Details — Step by Step

### Step 1: Get an ElevenLabs API Key
1. Sign up at **https://elevenlabs.io**
2. Pick your plan (Starter $5/mo recommended to start)
3. Go to **Profile → API Keys** (or https://elevenlabs.io/app/settings/api-keys)
4. Copy your API key

### Step 2: Set the Environment Variable
Add to `~/.openclaw/.env`:
```
ELEVENLABS_API_KEY=your_key_here
```
(Alternative env var name: `XI_API_KEY` also works)

Or set it in config directly (less recommended — keeps secrets in config):
```json5
{
  messages: {
    tts: {
      elevenlabs: {
        apiKey: "your_key_here",
      },
    },
  },
}
```

### Step 3: Update OpenClaw Config
Add the TTS section from step 2 above to `~/.openclaw/openclaw.json`, then restart:
```bash
openclaw gateway restart
```

### Step 4: Test It
Send Omni a message asking it to speak, or use the `tts` tool directly. The agent has a built-in `tts` tool that converts text to speech and returns audio.

---

## 5. Discord Voice Channel Feasibility

### Current State: Text Channel Voice Messages ✅
OpenClaw's TTS already works for sending **voice message attachments** in text channels. The `tts` tool generates audio files that get sent as Discord attachments. This works today with no extra setup beyond the TTS config above.

### Discord Voice Channels (Join/Listen/Speak): ⚠️ Significant Effort

**This is NOT currently built into OpenClaw.** Here's what it would take:

1. **Discord Voice Gateway** — Discord voice channels use a separate WebSocket + UDP protocol (not the same as text). The bot needs to:
   - Connect to Discord's Voice Gateway (WebSocket)
   - Establish a UDP connection for audio streaming
   - Handle Opus audio encoding/decoding

2. **Libraries needed:**
   - `@discordjs/voice` — Discord.js voice connection library
   - `sodium-native` or `tweetnacl` — encryption for voice
   - `prism-media` — audio transcoding (Opus ↔ PCM)

3. **Listen (STT):** Receive audio streams from voice channel → decode Opus → send to Whisper for transcription
4. **Speak (TTS):** Generate audio via ElevenLabs → encode to Opus → stream to voice channel

5. **OpenClaw Plugin:** There is a **voice-call plugin** (`openclaw voicecall`) but it's for **phone calls** (Twilio/telephony), not Discord voice channels. Discord voice would need either:
   - A new OpenClaw plugin/extension (custom code)
   - Or a standalone bot that bridges Discord voice ↔ OpenClaw's agent

**Bottom line:** Discord voice channels are a substantial custom development project. Start with text-channel voice messages (easy, works today), then consider voice channels as a future project.

### Recommended Approach for Voice Channels (Future):
1. Build a separate Discord bot service that handles voice connections
2. Have it use OpenClaw's API/gateway for the AI brain
3. Pipe audio: Discord Voice → Whisper STT → OpenClaw Agent → ElevenLabs TTS → Discord Voice
4. This is similar to how projects like "Discord AI Voice Bot" work on GitHub

---

## Summary & Recommended Next Steps

1. **Sign up for ElevenLabs Starter plan** ($5/mo) — https://elevenlabs.io
2. **Get API key** and add `ELEVENLABS_API_KEY` to `~/.openclaw/.env`
3. **Add TTS config** to `openclaw.json` (use the config block from section 2)
4. **Restart gateway** — `openclaw gateway restart`
5. **Pick a voice** — browse https://elevenlabs.io/voice-library, update `voiceId`
6. **Test** — ask Omni to say something with voice
7. **Discord voice channels** — park for later; text-channel voice messages work great as a starting point
