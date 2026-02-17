# AI Voice Assistant on a Smart Speaker — Research Report

**Date:** February 13, 2026  
**Goal:** "Hey Omni" wake word → back-and-forth voice conversation with Claude/OpenClaw AI  
**Server:** AMD Ryzen 9 9950X, 64GB RAM, RTX 4070 Ti Super, Unraid

---

## Executive Summary

This is very doable today. The most practical path is **Home Assistant + Wyoming voice satellites + custom LLM conversation agent**. The ecosystem is mature, actively developed, and directly supports swapping in Claude/Anthropic as the conversation backend. Hardware-wise, an **ESP32-S3-BOX-3** (~$45) or **Raspberry Pi + ReSpeaker mic HAT** (~$70-90) serves as the satellite, while your beefy Unraid server runs Whisper STT and Piper/Kokoro TTS on the GPU.

---

## 1. Existing Solutions & Projects

### Home Assistant Voice Pipeline (⭐ RECOMMENDED)
- **What:** HA has a full voice assistant stack built around the **Wyoming protocol** — an open standard connecting wake word → STT → conversation agent → TTS → audio output
- **LLM Support:** Native Anthropic Claude integration exists (`home-assistant.io/integrations/anthropic`). Also supports OpenAI, local LLMs via OpenAI-compatible APIs, and custom conversation agents
- **Key projects:**
  - [wyoming-satellite](https://github.com/rhasspy/wyoming-satellite) — Official remote voice satellite for Raspberry Pi
  - [wyoming-enhancements](https://github.com/FutureProofHomes/wyoming-enhancements) — Adds ChatGPT/LLM capabilities to Wyoming satellites
  - [Wyoming Bridge](https://www.reddit.com/r/homeassistant/comments/1ljhg0x/) — Proxy to inject custom processing into the voice pipeline
  - [ha-realtime-assist](https://github.com/nicholastripp/ha-realtime-assist) — Standalone RPi voice assistant using OpenAI Realtime API + HA
- **Source:** <https://www.home-assistant.io/integrations/wyoming/>

### Xiaozhi ESP32 Framework
- **What:** Open-source (MIT) AI chatbot framework designed for ESP32 devices. Supports wake word, voice conversation, MCP integration, and smart home control
- **Pros:** Very cheap hardware (~$15-30), active development, supports custom LLM backends
- **Cons:** More DIY, less integrated with HA ecosystem, primarily Chinese community
- **Source:** <https://github.com/78/xiaozhi-esp32>, <https://xiaozhi.dev>

### Willow
- **What:** ESP-IDF based voice assistant targeting ESP32-S3-BOX hardware. Claims Amazon Echo-competitive performance
- **Pros:** <$50 hardware, 100% self-hosted, <1% failure rate, HA integration
- **Cons:** Still in development (active issues on GitHub as of late 2025), smaller community
- **Source:** <https://heywillow.io/>, <https://github.com/HeyWillow/willow>

### Mycroft / OVOS (Open Voice OS)
- **What:** Mycroft is defunct but OVOS is the community fork. Full voice assistant stack
- **Pros:** Mature, plugin architecture
- **Cons:** Heavier weight, designed for RPi not ESP32, community-maintained
- **Source:** <https://openvoiceos.org/>

---

## 2. Hardware Options

### Option A: ESP32-S3-BOX-3 (~$45) ⭐ BEST VALUE
- Built-in mic array, speaker, 2.4" touch display
- Officially supported by Home Assistant as voice satellite
- Runs microWakeWord on-device, streams audio to server for STT/TTS
- **Setup guide:** <https://www.home-assistant.io/voice_control/s3_box_voice_assistant/>
- **Pros:** Cheapest, lowest power, tiny, official HA support, display for visual feedback
- **Cons:** Small speaker (adequate for voice, not music), limited audio quality

### Option B: Raspberry Pi Zero 2W / Pi 4 + ReSpeaker 2-Mic HAT (~$50-90)
- Better audio quality potential, more flexible
- Runs full wyoming-satellite with OpenWakeWord
- Can drive better speakers via 3.5mm or USB DAC
- **Pros:** Better audio, more hackable, can run local wake word
- **Cons:** More setup, needs case/enclosure, higher power draw

### Option C: FutureProofHomes Satellite1 (~$99 preorder)
- Purpose-built Wyoming satellite hardware
- Better mic array than ESP32-S3-BOX
- From the team behind wyoming-enhancements
- **Source:** <https://futureproofhomes.net>
- **Pros:** Designed for this exact use case, good mic performance
- **Cons:** New product, availability uncertain

### Option D: Old Tablet/Phone as Always-On Station
- Install a browser-based WebRTC voice chat interface
- Or use HA companion app with Assist
- **Pros:** Great mic/speaker, display, already own one
- **Cons:** Power hungry, ugly as dedicated device, overkill

### Option E: Repurposed Echo/Google Home
- **Don't bother.** These are locked down. No realistic custom firmware path for voice assistant replacement. The effort-to-reward ratio is terrible.

---

## 3. Software Stack (End-to-End)

### Wake Word Detection
| Option | Runs On | Custom Words | Notes |
|--------|---------|-------------|-------|
| **microWakeWord** | ESP32-S3 | Train custom ("Hey Omni" possible) | HA native, tiny models |
| **OpenWakeWord** | Server/RPi | Yes, train custom | HA add-on available, runs on CPU |
| **Porcupine (Picovoice)** | Anywhere | Yes (web tool) | Free tier available, very accurate |
| **Mycroft Precise** | RPi/Server | Yes | Older, less maintained |

**For "Hey Omni":** Use OpenWakeWord with a custom trained model, or Porcupine's console to create a custom wake word. OpenWakeWord is free and integrates directly with HA.

### Speech-to-Text (STT)
| Option | Location | Latency | Quality | Notes |
|--------|----------|---------|---------|-------|
| **faster-whisper (large-v3-turbo)** | Your GPU ⭐ | ~0.3-1s for typical utterance | Excellent | Best local option. RTX 4070 Ti Super will crush this |
| **Whisper.cpp** | GPU/CPU | Similar | Excellent | C++ implementation, also fast |
| **Wyoming Whisper** | HA add-on | ~1-3s | Good | Easy setup, CPU-based by default |
| **Whisper TensorRT** | Your GPU | ~0.1-0.5s | Excellent | Fastest, needs TensorRT setup |

**Recommendation:** Run **faster-whisper with large-v3-turbo** on your RTX 4070 Ti Super via a Wyoming-compatible server. Your GPU will transcribe a 5-second utterance in well under a second. See [this guide](https://jonahmay.net/accelerating-speech-to-text-stt-for-home-assistant-with-tensorrt/) for TensorRT acceleration with Wyoming.

### LLM / Conversation Agent
| Option | Notes |
|--------|-------|
| **Anthropic Claude via HA** ⭐ | Native integration: `Settings → Integrations → Anthropic`. Supports tool use for controlling HA devices |
| **Extended OpenAI Conversation** | HACS custom component, supports any OpenAI-compatible API. Could proxy to Claude via LiteLLM |
| **OpenClaw/Claude API direct** | Build a custom Wyoming conversation agent that calls Claude API |
| **Local LLM (Ollama/vLLM)** | Run on your GPU when not doing STT. Latency trade-off vs cloud |

**Recommendation:** Use the **native Anthropic integration** in HA. It works today, supports Assist features, and Claude is the conversation agent. For OpenClaw integration specifically, you could build a custom conversation agent component or use the HA MCP Server integration to expose HA to your OpenClaw agent.

### Text-to-Speech (TTS)
| Option | Location | Latency | Quality | Notes |
|--------|----------|---------|---------|-------|
| **Piper** | Local (CPU!) ⭐ | ~50-200ms | Good (comparable to Google/Amazon) | HA native, many voices, runs on CPU easily |
| **Kokoro (82M)** | Local GPU | ~100ms | Very good (near ElevenLabs) | Only 82M params, blazing fast, open-weight |
| **ElevenLabs** | Cloud | ~350-500ms | Best | Paid, adds network latency |
| **Coqui XTTS** | Local GPU | ~500ms-1s | Very good, voice cloning | Heavier, project discontinued but forks exist |

**Recommendation:** Start with **Piper** (dead simple, HA native, fast). Upgrade to **Kokoro** if you want better quality — it's tiny and would run effortlessly on your GPU alongside Whisper.

### Audio Routing
- **Wyoming protocol** handles all of this. The satellite streams audio to HA, which routes to STT → conversation agent → TTS, then streams audio back
- No manual audio routing needed if using the HA ecosystem

---

## 4. Home Assistant Angle (Deep Dive)

**Yes, this is THE path.** Here's the full architecture:

```
[ESP32-S3-BOX / RPi Satellite]
    ↓ (Wyoming protocol, TCP)
[Home Assistant]
    ├── Wake Word: OpenWakeWord (add-on) or on-device microWakeWord
    ├── STT: faster-whisper on GPU (Wyoming service)
    ├── Conversation: Anthropic Claude (native integration)
    └── TTS: Piper (add-on) or Kokoro (Wyoming service)
    ↓ (Wyoming protocol, TCP)
[ESP32-S3-BOX / RPi Satellite] → Speaker output
```

### Key HA Voice Features (as of 2025-2026):
- **Voice satellites** auto-discovered via Zeroconf
- **Announcements** — push TTS to any satellite (2025.3+)
- **Ask Question** action — announce + wait for voice response in automations
- **Custom conversation agents** — plug in any LLM
- **MCP Server integration** — expose HA entities to external AI agents
- **Multiple wake words** supported simultaneously

### Custom LLM with HA Voice Pipeline:
1. Install **Anthropic integration** → `Settings → Devices & Services → Add → Anthropic`
2. Create a **Voice Assistant** → `Settings → Voice Assistants → Add`
3. Set conversation agent to **Claude**
4. Set STT to your Whisper instance
5. Set TTS to Piper
6. Set wake word to OpenWakeWord
7. Add your satellite — it auto-discovers

Claude can then control your smart home devices AND have free-form conversations, all through voice.

---

## 5. Creative / Novel Approaches

### WebRTC Voice Chat on a Display
- Build a web app with WebRTC that connects to your server
- Run on a cheap Android tablet or old iPad mounted on the wall
- Full duplex audio, low latency
- Could connect directly to OpenClaw without HA

### Phone as Satellite
- HA Companion app supports Assist with voice
- Works but battery drain, not always-listening (need manual trigger)

### Bluetooth Speaker + RPi
- RPi runs wyoming-satellite, connects to Bluetooth speaker for output
- USB mic for input
- Works but Bluetooth adds ~100-200ms latency

### Wyoming Bridge (Custom Pipeline Injection)
- [Wyoming Bridge project](https://www.reddit.com/r/homeassistant/comments/1ljhg0x/) acts as proxy between HA and Wyoming services
- Inject custom processing at any pipeline stage
- Could intercept STT output, send to OpenClaw, return response to TTS

---

## 6. Latency Analysis

**Target: <3 seconds end-to-end for conversational feel**

| Stage | Estimated Time | Notes |
|-------|---------------|-------|
| Wake word detection | ~0ms (on-device) | microWakeWord runs on ESP32 |
| Audio streaming to server | ~50-100ms | LAN, Wyoming protocol |
| STT (faster-whisper large-v3-turbo, RTX 4070 Ti Super) | **~300-800ms** | For 3-5 second utterance |
| LLM response (Claude API) | **~500-1500ms** | Network + inference, streaming helps |
| TTS (Piper, local CPU) | **~100-200ms** | Very fast, can stream |
| Audio streaming back | ~50-100ms | LAN |
| **Total** | **~1.0-2.7 seconds** | ✅ Conversational! |

**With optimizations:**
- Use Whisper TensorRT: save ~200ms on STT
- Stream Claude response to TTS (process chunks as they arrive): save ~500ms
- Use Kokoro on GPU: comparable latency to Piper but better quality

**Your hardware is overkill for this** (in a good way). The RTX 4070 Ti Super with 16GB VRAM can easily run Whisper + Kokoro TTS simultaneously. The Ryzen 9 9950X can handle Piper TTS on CPU alone.

---

## 7. Recommended Path Forward

### Phase 1: Quick Win (1-2 hours)
1. **Buy an ESP32-S3-BOX-3** (~$45 on Amazon/AliExpress)
2. Flash ESPHome voice assistant firmware (HA provides this)
3. Install HA add-ons: **OpenWakeWord**, **Whisper**, **Piper**
4. Add **Anthropic integration** with Claude as conversation agent
5. Create voice assistant, pair satellite → **working voice assistant with Claude**

### Phase 2: Performance (1-2 days)
1. Set up **faster-whisper on GPU** as a Wyoming service (Docker container on Unraid)
2. Train **custom "Hey Omni" wake word** with OpenWakeWord
3. Optionally set up **Kokoro TTS on GPU** for better voice quality

### Phase 3: Advanced (ongoing)
1. Build custom **OpenClaw conversation agent** for HA that routes through your agent
2. Add more satellites in different rooms
3. Explore **Wyoming Bridge** for custom pipeline logic
4. Add voice-activated automations with Ask Question

### Shopping List
| Item | Price | Purpose |
|------|-------|---------|
| ESP32-S3-BOX-3 | ~$45 | Voice satellite (has mic, speaker, display) |
| (Optional) Raspberry Pi 5 + ReSpeaker | ~$90 | Better audio satellite |
| (Optional) FutureProofHomes Satellite1 | ~$99 | Premium satellite option |

**Total minimum: ~$45** (you already have the server)

---

## Key Source Links

- HA Wyoming Protocol: <https://www.home-assistant.io/integrations/wyoming/>
- HA Anthropic Integration: <https://www.home-assistant.io/integrations/anthropic>
- Wyoming Satellite: <https://github.com/rhasspy/wyoming-satellite>
- Wyoming Enhancements (LLM): <https://github.com/FutureProofHomes/wyoming-enhancements>
- ESP32-S3-BOX Setup: <https://www.home-assistant.io/voice_control/s3_box_voice_assistant/>
- OpenWakeWord: <https://github.com/dscripka/openWakeWord>
- faster-whisper: <https://github.com/SYSTRAN/faster-whisper>
- Piper TTS: <https://github.com/rhasspy/piper>
- Kokoro TTS: <https://huggingface.co/hexgrad/Kokoro-82M>
- Willow: <https://heywillow.io/>
- Xiaozhi ESP32: <https://github.com/78/xiaozhi-esp32>
- FutureProofHomes: <https://futureproofhomes.net>
- HA Voice Blog (Speech-to-Phrase): <https://www.home-assistant.io/blog/2025/02/13/voice-chapter-9-speech-to-phrase/>
- Local LLM HA Guide: <https://blog.natsuki-cloud.dev/posts/voicellm/>
- Whisper TensorRT for HA: <https://jonahmay.net/accelerating-speech-to-text-stt-for-home-assistant-with-tensorrt/>
- Extended OpenAI Conversation: <https://github.com/jekalmin/extended_openai_conversation>
