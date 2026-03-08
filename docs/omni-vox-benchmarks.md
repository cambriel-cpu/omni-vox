# Omni Vox Performance Benchmarks

## Baseline — Pre-Conversation-UX (2026-03-08 12:47 EDT)

Measured from servo-skull logs. "End-of-speech" = silence timeout fired.

### Simple Query: "Hey Jarvis, hello"
| Metric | Value | Notes |
|--------|-------|-------|
| Wake → record start | 0.0s | VAD pre-loaded, cue non-blocking |
| Recording duration | 1.8s | Speech + 1.5s silence timeout |
| STT | 443ms | Whisper warm |
| LLM first token | 1935ms | No tool calls |
| TTS + vox (first sentence) | 296ms | "Hey!" |
| **TTFA (from end of speech)** | **2.7s** | Target: 2-3s ✅ |
| Total pipeline | 10.1s | 3 sentences |

### Tool-Call Query: "Tell me the weather in Marietta, Georgia"
| Metric | Value | Notes |
|--------|-------|-------|
| Recording duration | 5.4s | Longer utterance |
| STT | 642ms | Whisper warm |
| LLM first token | 21,489ms | Weather tool call |
| TTS + vox (first sentence) | 570ms | Long sentence |
| **TTFA (from end of speech)** | **22.7s** | Target: ≤5s with filler ❌ |
| Total pipeline | 46.6s | 2 sentences |

### Pipeline Component Benchmarks
| Component | Cold | Warm | Notes |
|-----------|------|------|-------|
| Silero VAD load | ~2000ms | 0ms | Pre-loaded at startup |
| Whisper STT | 1845ms | 355-642ms | Warmed at startup |
| LLM first token (no tools) | — | 1800-2400ms | Claude Opus via OpenClaw |
| LLM first token (tool call) | — | 21,000-22,000ms | Weather API |
| Kokoro TTS (short sentence) | — | 93-175ms | "Hey!" / "One moment." |
| Kokoro TTS (long sentence) | — | 284-495ms | Full weather report |
| Vox filter (ffmpeg) | — | 102-155ms | On Pi 5 |
| aplay playback | — | 1257-16190ms | Proportional to audio length |

### Audio Format
- **Format:** MP3 from Kokoro (switched from WAV, which was switched from Opus)
- **Opus bug:** Truncates audio at round durations (2s, 5s)
- **MP3 advantage:** 55KB avg (vs 162KB WAV), 124ms avg TTS time, no truncation

### Configuration at Baseline
- Silence timeout: 1.5s
- Wake word threshold: 0.50
- ALSA device: plughw:2,0 (exclusive, no simultaneous capture+play)
- Pipeline: fully sequential (record → STT → LLM → TTS → vox → play → next)
- No filler/acknowledgment audio
- No session persistence (wake word required for every interaction)
- 2s post-response cooldown (causes false re-triggers)
