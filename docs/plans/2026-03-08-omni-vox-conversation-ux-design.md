# Omni Vox Conversation UX Design

**Date:** 2026-03-08
**Status:** Draft — awaiting review

## Overview

Redesign the Omni Vox servo-skull from a single-turn wake-word-and-respond model to a **conversation session** model with persistent open mic, barge-in support, and latency masking. The goal is a natural, interactive voice experience with no awkward dead air.

## Latency Target

**2-3 seconds** from end-of-user-speech to first meaningful audio (TTFA). Current best: 2.7s for simple queries, 22s+ for tool-call queries.

## Conversation Session State Machine

```
                    ┌──────────────────────────────┐
                    │          IDLE                 │
                    │   (wake word detector only)   │
                    └──────────┬───────────────────┘
                               │ wake word detected
                               ▼
                    ┌──────────────────────────────┐
                    │      SESSION_OPEN            │
                    │  (mic open, play wake cue)   │
                    │  await speech for 5s         │
                    └──────────┬───────────────────┘
                               │ speech detected / timeout
                        ┌──────┴──────┐
                        │             │
                   speech          no speech
                        │             │
                        ▼             ▼
            ┌───────────────┐   ┌───────────────┐
            │  LISTENING    │   │ SESSION_CLOSE │
            │  (VAD active) │   │ (close cue,   │
            │               │   │  return IDLE)  │
            └───────┬───────┘   └───────────────┘
                    │ silence detected (end of speech)
                    ▼
            ┌───────────────┐
            │  PROCESSING   │
            │  STT → LLM   │
            │  (filler if   │
            │   needed)     │
            └───────┬───────┘
                    │ first audio ready
                    ▼
            ┌───────────────┐
            │  SPEAKING     │◄──── barge-in detected ──┐
            │  (TTS play)   │                          │
            │  (mic open    ├──────────────────────────►│
            │   for barge)  │  stop playback,          │
            └───────┬───────┘  → LISTENING             │
                    │ playback complete                 │
                    ▼                                   │
            ┌───────────────┐                          │
            │  FOLLOW_UP    │                          │
            │  (mic open,   ├──► speech → LISTENING ───┘
            │   await 5-10s)│
            │   (multi-turn │
            │    extends)   │
            └───────┬───────┘
                    │ timeout (no speech)
                    ▼
            ┌───────────────┐
            │ SESSION_CLOSE │
            │ (close cue,   │
            │  return IDLE) │
            └───────────────┘
```

### State Descriptions

| State | Mic | Speaker | Wake Word | Description |
|-------|-----|---------|-----------|-------------|
| IDLE | Off | Off | Active | Lowest power. Only wake word detector runs. |
| SESSION_OPEN | Open | Cue | Ignored | Wake cue plays. Mic opens. 5s window for speech. |
| LISTENING | Open | Off | Ignored | VAD captures speech. Silence triggers end-of-speech. |
| PROCESSING | Open (passive) | Filler/ambient | Ignored | STT → LLM pipeline runs. Filler plays if needed. |
| SPEAKING | Open (barge-in) | TTS output | Ignored | Response plays. Barge-in detection active. |
| FOLLOW_UP | Open | Off | Ignored | Awaiting follow-up speech. 5-10s timeout. |
| SESSION_CLOSE | Off | Close cue | — | Plays close cue, transitions to IDLE. |

### Follow-Up Timeout Extension

Base timeout: **5 seconds**. After 2+ conversational turns in the same session, extend to **10 seconds**. This accommodates natural thinking pauses in multi-turn conversations.

### "Hey Jarvis" During a Session

When the session is open, "Hey Jarvis" is treated as normal speech input, not as a new session trigger. The wake word only matters in IDLE state.

## Audio Foundation: Simultaneous Capture + Playback

### Problem

ALSA `plughw:2,0` (ReSpeaker 2-Mic HAT) cannot do simultaneous playback and capture. Currently `arecord` and `aplay` fight for exclusive device access.

### Solution: ALSA Software Mixing

Configure `~/.asoundrc` with `dmix` (playback multiplexing) and `dsnoop` (capture sharing):

```
# ~/.asoundrc for ReSpeaker 2-Mic HAT (card 2: seeed2micvoicec)
# Enables simultaneous capture and playback on the same hardware

defaults.pcm.rate_converter "samplerate"

pcm.!default {
    type asym
    playback.pcm "playback"
    capture.pcm "capture"
}

pcm.playback {
    type plug
    slave.pcm "dmixed"
}

pcm.capture {
    type plug
    slave.pcm "array"
}

pcm.dmixed {
    type dmix
    slave.pcm "hw:seeed2micvoicec"
    ipc_key 555555
}

pcm.array {
    type dsnoop
    slave {
        pcm "hw:seeed2micvoicec"
        channels 2
    }
    ipc_key 666666
}
```

After this config, use `default` device (or named `playback`/`capture` devices) instead of `plughw:2,0`.

**Source:** Seeed Studio ReSpeaker documentation, Raspberry Pi Forums ALSA configuration threads.

**Risk:** `dmix` resampling may add latency or quality loss. Needs benchmarking. The `samplerate` converter is recommended over `speexdsp` for quality.

## Barge-In: Echo Cancellation Strategy

### The Problem

With mic open during playback, the speaker audio feeds back into the mic. The ReSpeaker's small speaker is inches from the microphones. The system's own voice triggers false wake words and false speech detection.

### Industry Best Practice

From research (VOCAL, Sierra, Orga AI, Vocalis):

1. **AEC (Acoustic Echo Cancellation)** is the gold standard. The system uses a reference signal (what it's playing) to subtract the echo from the mic input.
2. **VAD confidence gating** raises the threshold for speech detection during playback — only a significantly louder/different signal (the user) triggers.
3. **Context management** — when barge-in occurs, signal the LLM that its previous response was interrupted so it doesn't assume the user heard everything.

### Recommended Approach: Layered Defense

**Layer 1: Playback-Aware Suppression (simple, no deps)**

The system knows exactly when it's playing audio. During `SPEAKING` state:
- Raise VAD speech probability threshold from 0.5 to 0.85
- Require speech energy significantly above expected playback bleed level
- Track playback state as a boolean flag accessible to the recorder

This is cheap, effective for most cases, and has zero additional dependencies.

**Layer 2: SpeexDSP AEC (proper echo cancellation)**

Use `speexdsp-python` or the `voice-engine/ec` project (C binary, built for ReSpeaker + RPi). This feeds the playback reference signal into the AEC, which subtracts it from the mic input:

```
Mic Input ──►┌─────┐
             │ AEC ├──► Clean Audio (user voice only)
Playback ──►└─────┘
Reference
```

**Proven on this exact hardware** — `voice-engine/ec` explicitly lists ReSpeaker 2-Mic HAT as supported. Uses ALSA API + SpeexDSP. Note: SpeexDSP AEC needs several seconds to converge/warm up.

**Layer 3: Energy-Based Double-Talk Detection (fallback)**

If AEC hasn't converged or is struggling, use raw energy comparison. The system knows the expected playback energy. If mic energy significantly exceeds expected playback energy, it's likely a human speaking over the output.

### Barge-In Behavior

When barge-in is detected during SPEAKING:
1. **Immediately kill `aplay` process** (stops audio output)
2. **Cancel pending TTS queue** (discard unplayed sentences)
3. **Discard remaining LLM stream** (close SSE connection or drain)
4. **Inform LLM context** — next request should include: "Your previous response was interrupted after: '{last_spoken_sentence}'"
5. **Transition to LISTENING** — capture the user's new speech
6. **Mic remains open** for the user's follow-up input

## Latency Masking: Pre-Recorded Responses

### Design Principle

Pre-recorded responses are **deterministic, instant, and token-free**. Use them for:
- Audio cues (wake, close, processing)
- Brief acknowledgments before tool calls
- Error states
- Ambient filler during long waits

Generate them once with Kokoro + vox-caster filter, store as WAV files.

### Pre-Recorded Response Library

**Audio Cues** (non-speech):
- `cue_wake.wav` — mic-open indicator (current: pink noise burst)
- `cue_close.wav` — mic-close/session-end indicator
- `cue_processing.wav` — loopable walkie-talkie static/interference (~2-3s loop, source: analog noise with intermittent artifacts and static bursts — see <https://www.soundsnap.com/analog_noise_walkie_talkie_interference_and_intermittent_artifacts_with_static_bursts_and_buzzing>)
- `cue_error.wav` — error tone (current: descending two-tone)

**Brief Acknowledgments** (pre-recorded TTS, randomized):
- `ack_short_1.wav` — "One moment."
- `ack_short_2.wav` — "Understood."
- `ack_short_3.wav` — "Let me check."
- `ack_short_4.wav` — "Processing."
- `ack_short_5.wav` — "Acknowledged."
- `ack_short_6.wav` — "Cogitating."

**Long Acknowledgments / Tool-Call Banter** (pre-recorded TTS, randomized):
- `ack_tool_1.wav` — "Consulting the noosphere. Stand by."
- `ack_tool_2.wav` — "Querying the data-stacks. One moment."
- `ack_tool_3.wav` — "Communing with the machine spirits. This may take a moment."
- `ack_tool_4.wav` — "Accessing external cogitators. Stand by."
- `ack_tool_5.wav` — "Aetheric interference detected. Adjusting. One moment."

**Error Responses** (pre-recorded TTS):
- `error_connection.wav` — "Lost connection to the noosphere. Try again."
- `error_timeout.wav` — "The machine spirits are unresponsive. Try again shortly."
- `error_stt.wav` — "I didn't catch that. Say again?"

### Filler Trigger Logic

```
End of speech detected
    │
    ├──► Start STT immediately
    │
    ├──► STT complete → Start LLM stream
    │
    ├──► IF first SSE event is tool_call:
    │        Play random long ack (ack_tool_*.wav)
    │        IF still waiting after ack finishes:
    │            Loop cue_processing.wav until LLM text arrives
    │
    ├──► IF no LLM text within 3 seconds:
    │        Play random short ack (ack_short_*.wav)
    │        IF still waiting after ack finishes:
    │            Loop cue_processing.wav until LLM text arrives
    │
    └──► IF LLM text arrives within 3 seconds:
             Play LLM response directly (no filler needed)
```

### Detecting Tool Calls in SSE Stream

The OpenClaw `/v1/responses` SSE stream emits different event types. Tool calls appear as events *before* text output. The pipeline should inspect the first SSE event type:
- `response.output_text.delta` → text response, no filler needed
- Tool-related events → play long acknowledgment immediately

**Open question:** Need to verify the exact SSE event types for tool calls in the OpenResponses spec. May need to inspect the `response.created` event's `output` array for `function_call` type items.

## Error Recovery

| Error | Behavior |
|-------|----------|
| STT fails/times out | Play `error_stt.wav`, return to LISTENING (within session) |
| LLM timeout (>30s) | Play `error_timeout.wav`, return to FOLLOW_UP |
| LLM stream error | Play `error_connection.wav`, return to FOLLOW_UP |
| TTS fails | Log error, skip sentence, continue with next |
| ALSA device error | Play `cue_error.wav` (if possible), return to IDLE, attempt recovery |

**Key principle:** Errors within a session should NOT close the session unless unrecoverable. The user should be able to retry without re-triggering the wake word.

## Ambient Noise Rejection

With mic open for 5-10 seconds, background noise (TV, music, other people) may trigger false speech detection.

### Mitigations

1. **VAD probability threshold tuning** — raise from default 0.5 to 0.6-0.7 for SESSION_OPEN and FOLLOW_UP states (lower for LISTENING since we expect speech)
2. **Minimum speech duration** — require at least 0.5s of continuous speech before committing to "speech detected" (filters brief sounds)
3. **STT confidence gating** — if Whisper returns very low confidence or nonsensical transcription, treat as noise and return to waiting
4. **Energy-based pre-filter** — ignore audio below a baseline ambient energy level (calibrated on startup or periodically)

## Pipeline Parallelization

### Current (Sequential)

```
Record → STT → LLM → TTS → Vox → Play → Next Sentence
```

### Target (Pipelined)

```
Record ────────────────────────►
         STT ──────────────────►
              LLM (streaming) ─────────────►
                   TTS (per sentence) ─────►
                        Vox (per sentence) ─►
                             Play ──────────►
```

Each stage feeds into the next as soon as it has sufficient data:
- **STT starts** when silence is detected (batch, ~0.4s — acceptable)
- **LLM starts** when STT completes
- **TTS starts** on first complete sentence from LLM stream
- **Vox filter starts** when TTS returns audio
- **Playback starts** when vox filter returns audio
- **Next sentence TTS** can begin while current sentence plays

### Producer-Consumer Architecture

```python
# Conceptual pipeline
llm_queue = asyncio.Queue()    # LLM → sentences
tts_queue = asyncio.Queue()    # TTS → audio chunks
play_queue = asyncio.Queue()   # Vox → playable audio

# Three concurrent tasks:
# 1. LLM consumer: reads SSE stream, buffers sentences, puts to llm_queue
# 2. TTS worker: takes from llm_queue, synthesizes + vox filters, puts to tts_queue
# 3. Player: takes from tts_queue, plays via aplay, signals completion
```

This allows TTS of sentence N+1 while sentence N is playing — eliminating inter-sentence gaps.

## Technical Dependencies

| Component | Purpose | Status |
|-----------|---------|--------|
| `~/.asoundrc` (dmix/dsnoop) | Simultaneous playback+capture | Needs deployment (no sudo) |
| `speexdsp-python` | AEC for barge-in | Needs installation on Pi |
| Pre-recorded WAV files | Filler/cue responses | Need generation |
| Pipeline refactor | Async producer-consumer | Needs implementation |
| State machine refactor | Session lifecycle | Needs implementation |

## Implementation Order

1. **ALSA dmix/dsnoop config** — deploy `~/.asoundrc`, test simultaneous record+play
2. **Pre-record response library** — generate all cue/ack/error WAVs using Kokoro + vox filter
3. **Session state machine** — refactor `main.py` from linear wake→process→idle to full state machine
4. **Follow-up listening window** — after SPEAKING, enter FOLLOW_UP with 5-10s timeout
5. **Filler/acknowledgment logic** — play pre-recorded acks during PROCESSING based on timing heuristics
6. **Pipeline parallelization** — producer-consumer queues for LLM→TTS→Play
7. **Barge-in (Layer 1)** — playback-aware VAD suppression
8. **Barge-in (Layer 2)** — SpeexDSP AEC integration
9. **Ambient noise rejection tuning** — VAD thresholds, minimum speech duration
10. **Error recovery** — graceful handling with pre-recorded error responses

## Research Sources

- **Sierra AI** — "Engineering low-latency voice agents" (TTFA measurement, parallel execution, progress indicators, caching)
- **Orga AI** — "Barge-in for Voice Agents" (VAD-based detection, context management on interruption, WebSocket control channels)
- **VOCAL** — "AEC Barge-In" (AEC as prerequisite for barge-in, NER requirements, SpeexDSP linear filter)
- **voice-engine/ec** — Open-source AEC for ReSpeaker + RPi using SpeexDSP (proven on our exact hardware)
- **speexdsp-python** — Python bindings for Speex echo cancellation
- **Vocalis (Lex-au)** — Open-source speech-to-speech assistant with barge-in, interrupt handler, silence-based follow-ups
- **Nikhil R** — "How to optimise latency for voice agents" (semantic caching, prompt compression, staged startup, filler audio)
- **Twilio** — "Core Latency in AI Voice Agents" (interstitial fillers for tool/LLM latency masking)
- **Seeed Studio / RPi Forums** — ALSA dmix/dsnoop configuration for ReSpeaker HAT
