# Omni Vox Conversation UX — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## MDD Documentation

### Goal & Context
**Goal:** Refactor the Omni Vox servo-skull from single-turn wake-and-respond to a conversation session model with persistent mic, barge-in, and latency masking.
**Why:** Current UX requires wake word for every utterance, has 22s+ dead air on tool calls, false wake triggers from own audio, and no ability to interrupt.
**Success Criteria:**
- Multi-turn conversations without re-triggering wake word
- TTFA ≤3s for simple queries (currently 2.7s — maintain)
- No dead air >3s on tool-call queries (currently 22s)
- Barge-in stops playback and accepts new input
- No false wake triggers from own audio output
- Session auto-closes after inactivity with audible cue

### Architecture & Approach
**Pattern:** Async state machine with producer-consumer pipeline
**Tech Stack:** Python 3.13, asyncio, ALSA (dmix/dsnoop), Silero VAD, SpeexDSP, aplay/arecord
**Dependencies:** `speexdsp-python` (pip), ALSA `~/.asoundrc` config, pre-recorded WAV files

### Existing Codebase (1128 lines total)
| File | Lines | Role | Refactor Scope |
|------|-------|------|----------------|
| `main.py` | 140 | Entry point, linear wake→pipeline→cooldown loop | **Heavy** — becomes session state machine |
| `pipeline.py` | 136 | Sequential STT→LLM→TTS→play | **Heavy** — becomes producer-consumer |
| `config.py` | 69 | Constants | **Light** — add session/AEC config |
| `audio/player.py` | 83 | Blocking aplay wrapper | **Medium** — add cancel, async cue, queue |
| `audio/recorder.py` | 168 | arecord + Silero VAD | **Medium** — add playback-aware mode |
| `llm/openclaw_client.py` | 124 | SSE streaming + sentence buffer | **Light** — add tool-call event detection |
| `tts/kokoro_client.py` | 148 | Kokoro API + vox filter | **None** — already correct |
| `wake_word/detector.py` | 144 | OpenWakeWord + pre-roll buffer | **Light** — remove cue logic (moved to session) |
| `stt/whisper_client.py` | 59 | Whisper API call | **None** — already correct |
| `transcript/logger.py` | 57 | JSONL logging | **Light** — add session/turn tracking |

### Quality Requirements
**Performance:** TTFA ≤3s simple, ≤5s tool-call (with filler masking dead air)
**Reliability:** Graceful error recovery within session, no crashes on service failures
**Audio:** No self-triggering, clean barge-in, audible session state cues

---

## Phase 1: ALSA Foundation (Est: 30 min)

### Task 1.1: Deploy dmix/dsnoop Configuration (10 min)

**MDD Context:** Everything else depends on simultaneous capture + playback. This is the foundation.

**Requirements:**
- MUST: `arecord` and `aplay` can run simultaneously on the ReSpeaker
- MUST: No sudo required (user-level `~/.asoundrc`)
- MUST: Audio quality equivalent to current `plughw:2,0`

**Files:**
- Create: `~/.asoundrc` on servo-skull (ALSA config)
- Modify: `skull/config.py` — change `ALSA_DEVICE` default from `plughw:2,0` to `default`

**Steps:**
1. Deploy `~/.asoundrc` with dmix/dsnoop config per design spec (card `seeed2micvoicec`)
2. Update `ALSA_DEVICE` default in config.py
3. Update all `arecord` and `aplay` calls to use new device names

**Verification:**
```bash
# Test simultaneous record + play
arecord -D capture -f S16_LE -r 16000 -c 1 -d 3 /tmp/test.raw &
aplay -D playback ~/omni-vox-skull/skull/audio/cues/vox_activate.wav
wait
# Both should complete without "device busy" errors
```

### Task 1.2: Benchmark dmix Latency (10 min)

**MDD Context:** dmix adds a software mixing layer. Need to verify it doesn't add perceptible latency.

**Requirements:**
- MUST: Playback latency within 50ms of direct `plughw:2,0`
- MUST: Capture quality sufficient for Whisper STT (>95% accuracy)

**Steps:**
1. Record speech via `capture` device, transcribe with Whisper, compare to `plughw:2,0` baseline
2. Time playback of test WAV via `playback` device vs `plughw:2,0`
3. Test simultaneous capture + playback quality

**Verification:**
```bash
# Latency comparison
time aplay -D playback test.wav
time aplay -D plughw:2,0 test.wav
```

### Task 1.3: Update Player and Recorder for New ALSA Devices (10 min)

**Requirements:**
- MUST: `player.py` uses `playback` ALSA device for speech, supports separate device for cues
- MUST: `recorder.py` uses `capture` ALSA device
- MUST: Cues can play while recording is active (the whole point)

**Files:**
- Modify: `skull/config.py` — add `ALSA_PLAYBACK_DEVICE`, `ALSA_CAPTURE_DEVICE`
- Modify: `skull/audio/player.py` — use playback device
- Modify: `skull/audio/recorder.py` — use capture device

---

## Phase 2: Pre-Recorded Response Library (Est: 25 min)

### Task 2.1: Generate Audio Cues (10 min)

**MDD Context:** Non-speech audio cues for session state transitions. Generated once, stored as WAVs.

**Requirements:**
- MUST: `cue_wake.wav` — short mic-open indicator
- MUST: `cue_close.wav` — session-end indicator
- MUST: `cue_processing.wav` — loopable 2-3s ambient static (walkie-talkie aesthetic)
- MUST: `cue_error.wav` — error indicator (existing)

**Files:**
- Create: `skull/audio/cues/cue_wake.wav`
- Create: `skull/audio/cues/cue_close.wav`
- Create: `skull/audio/cues/cue_processing.wav`
- Keep: `skull/audio/cues/vox_activate.wav` → rename to `cue_wake.wav`
- Keep: `skull/audio/cues/error_tone.wav` → rename to `cue_error.wav`

**Steps:**
1. Rename existing cues to new naming convention
2. Generate `cue_close.wav` (ascending tone, inverse of error)
3. Download/generate `cue_processing.wav` from SoundSnap reference or synthesize walkie-talkie static with ffmpeg
4. Apply vox filter to all generated cues for aesthetic consistency

### Task 2.2: Generate Pre-Recorded TTS Responses (15 min)

**MDD Context:** Deterministic, instant, token-free responses for latency masking.

**Requirements:**
- MUST: 6 brief acknowledgments (`ack_short_*.wav`)
- MUST: 5 long/tool-call acknowledgments (`ack_tool_*.wav`)
- MUST: 3 error responses (`error_*.wav`)
- MUST: All generated with `bm_drogan` voice + vox filter

**Files:**
- Create: `skull/audio/cues/ack_short_{1-6}.wav`
- Create: `skull/audio/cues/ack_tool_{1-5}.wav`
- Create: `skull/audio/cues/error_{connection,timeout,stt}.wav`

**Steps:**
1. Script to call Kokoro TTS API for each phrase
2. Apply vox filter to each output
3. Verify all files play correctly on ReSpeaker
4. Create `skull/audio/cues/manifest.json` listing all cues with categories

**Verification:**
```bash
for f in skull/audio/cues/ack_*.wav; do
  echo "Playing $f"
  aplay -D playback "$f"
  sleep 0.5
done
```

---

## Phase 3: Session State Machine (Est: 60 min)

### Task 3.1: Define Session State and Cue Manager (15 min)

**MDD Context:** Central state tracking and cue playback logic.

**Requirements:**
- MUST: Enum for states: IDLE, SESSION_OPEN, LISTENING, PROCESSING, SPEAKING, FOLLOW_UP, SESSION_CLOSE
- MUST: State transition logging
- MUST: Turn counter for follow-up timeout extension
- MUST: Random cue selection from categories (brief ack, tool ack, errors)
- MUST: Looping ambient playback for `cue_processing.wav`

**Files:**
- Create: `skull/session.py` (~100 lines) — `SessionState` enum, `Session` class
- Create: `skull/audio/cue_manager.py` (~80 lines) — categorized cue playback, random selection, looping

**Data Model:**
```python
class Session:
    state: SessionState
    turn_count: int
    last_spoken_sentence: str
    started_at: float
    
    @property
    def follow_up_timeout(self) -> float:
        return 10.0 if self.turn_count >= 2 else 5.0
```

### Task 3.2: Refactor main.py to Session Loop (25 min)

**MDD Context:** Replace linear wake→pipeline→cooldown with full state machine.

**Requirements:**
- MUST: IDLE state only runs wake word detector
- MUST: SESSION_OPEN plays wake cue, opens mic, 5s timeout for speech
- MUST: LISTENING captures speech with VAD, transitions to PROCESSING on silence
- MUST: PROCESSING runs STT→LLM pipeline with filler logic
- MUST: SPEAKING plays TTS output with barge-in monitoring
- MUST: FOLLOW_UP waits 5-10s for follow-up speech, transitions to LISTENING or SESSION_CLOSE
- MUST: SESSION_CLOSE plays close cue, returns to IDLE
- MUST: "Hey Jarvis" during session treated as speech, not new wake
- SHOULD: Error states return to FOLLOW_UP (not IDLE) to keep session alive

**Files:**
- Rewrite: `skull/main.py` (~200 lines) — session state machine
- The startup/warmup/health-check code stays, the main loop is replaced

**State Transition Table:**
| From | Event | To | Action |
|------|-------|----|--------|
| IDLE | wake word | SESSION_OPEN | play cue_wake |
| SESSION_OPEN | speech detected | LISTENING | — |
| SESSION_OPEN | 5s timeout | SESSION_CLOSE | play cue_close |
| LISTENING | silence detected | PROCESSING | start STT |
| PROCESSING | first audio ready | SPEAKING | play audio |
| PROCESSING | error | FOLLOW_UP | play error cue |
| SPEAKING | playback complete | FOLLOW_UP | — |
| SPEAKING | barge-in | LISTENING | cancel playback |
| FOLLOW_UP | speech detected | LISTENING | — |
| FOLLOW_UP | timeout | SESSION_CLOSE | play cue_close |
| SESSION_CLOSE | cue complete | IDLE | — |

### Task 3.3: Implement Continuous Mic Capture (20 min)

**MDD Context:** Currently mic opens/closes per interaction. Need persistent capture during session.

**Requirements:**
- MUST: Single `arecord` process runs for entire session (SESSION_OPEN → SESSION_CLOSE)
- MUST: Audio stream feeds into VAD continuously
- MUST: Pipeline can grab audio segments on demand
- MUST: Clean shutdown on SESSION_CLOSE
- SHOULD: Share audio stream between VAD and pre-roll buffer

**Files:**
- Create: `skull/audio/mic_stream.py` (~120 lines) — persistent `arecord` subprocess, async chunk generator
- Modify: `skull/audio/recorder.py` — accept mic stream instead of spawning own `arecord`

**Design:**
```python
class MicStream:
    """Persistent microphone capture via arecord subprocess."""
    
    async def start(self):
        """Start arecord subprocess for session duration."""
        
    async def read_chunk(self, n_bytes: int) -> bytes:
        """Read next chunk from mic. Non-blocking async."""
        
    async def stop(self):
        """Kill arecord subprocess."""
        
    @property
    def is_active(self) -> bool: ...
```

---

## Phase 4: Pipeline Parallelization (Est: 45 min)

### Task 4.1: Producer-Consumer Pipeline (30 min)

**MDD Context:** Replace sequential sentence processing with concurrent tasks.

**Requirements:**
- MUST: LLM streaming, TTS, and playback run as concurrent async tasks
- MUST: TTS of sentence N+1 begins while sentence N plays
- MUST: Pipeline cancellable at any point (for barge-in)
- MUST: Track which sentence was last spoken (for barge-in context)
- SHOULD: Filler audio plays if LLM takes >3s or emits tool-call event

**Files:**
- Rewrite: `skull/pipeline.py` (~250 lines) — producer-consumer architecture

**Design:**
```python
async def run_pipeline(transcript: str, instructions: str, session: Session) -> None:
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
    play_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    cancel_event = asyncio.Event()
    
    # Three concurrent tasks
    await asyncio.gather(
        _llm_producer(transcript, instructions, tts_queue, cancel_event, session),
        _tts_worker(tts_queue, play_queue, cancel_event),
        _player_worker(play_queue, cancel_event, session),
    )
```

**Steps:**
1. Create `_llm_producer`: reads SSE stream, buffers sentences, puts to queue, detects tool calls
2. Create `_tts_worker`: takes sentences, calls Kokoro + vox, puts audio to play queue
3. Create `_player_worker`: takes audio, plays via aplay, updates `session.last_spoken_sentence`
4. Add filler logic: if `tts_queue` empty for >3s, play short ack; if tool-call detected, play long ack
5. Add cancel: `cancel_event.set()` causes all tasks to drain and exit
6. Wire into session state machine

### Task 4.2: Tool-Call Detection in SSE Stream (15 min)

**MDD Context:** Need to distinguish fast text responses from slow tool-call responses to trigger appropriate filler.

**Requirements:**
- MUST: Detect when LLM is performing a tool call (not just slow)
- MUST: Signal the pipeline to play long acknowledgment immediately
- SHOULD: Not require changes to the OpenClaw server

**Files:**
- Modify: `skull/llm/openclaw_client.py` — yield sentinel values for tool-call events

**Steps:**
1. Research OpenResponses SSE event types for tool calls (inspect raw SSE during weather query)
2. Add event type inspection to `stream_sentences()` generator
3. Yield a `ToolCallEvent` sentinel when tool calls detected
4. Pipeline handles sentinel by triggering long ack playback

**Verification:**
```bash
# Manual SSE test
curl -N -X POST http://100.109.78.64:18789/v1/responses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"openclaw:main","input":"What is the weather in Atlanta?","stream":true,"user":"test-sse"}' \
  2>/dev/null | head -50
```

---

## Phase 5: Barge-In (Est: 45 min)

### Task 5.1: Playback-Aware VAD Suppression — Layer 1 (15 min)

**MDD Context:** Simplest barge-in defense. No dependencies. Prevents most false triggers.

**Requirements:**
- MUST: During SPEAKING state, VAD threshold raised to 0.85
- MUST: Require mic energy significantly above baseline during playback
- MUST: Track playback state as shared flag

**Files:**
- Modify: `skull/audio/recorder.py` — accept `playback_active` flag, adjust thresholds
- Modify: `skull/audio/player.py` — export `is_playing` property
- Modify: `skull/session.py` — wire playback state into VAD

### Task 5.2: Barge-In Handler (15 min)

**MDD Context:** When user speaks during SPEAKING, stop everything and listen.

**Requirements:**
- MUST: Kill active `aplay` process immediately
- MUST: Cancel pending TTS and LLM tasks
- MUST: Record what was last spoken for LLM context
- MUST: Transition to LISTENING to capture user's new input
- SHOULD: Include interrupted context in next LLM request

**Files:**
- Modify: `skull/audio/player.py` — add `cancel()` function (already exists)
- Modify: `skull/pipeline.py` — add cancel_event handling
- Modify: `skull/session.py` — add `interrupted_after` field

### Task 5.3: SpeexDSP AEC Integration — Layer 2 (15 min)

**MDD Context:** Proper echo cancellation for robust barge-in. Uses playback reference signal.

**Requirements:**
- MUST: Install `speexdsp-python` on Pi
- MUST: Feed playback audio as reference signal
- MUST: Output clean (echo-cancelled) audio to VAD
- SHOULD: Graceful fallback to Layer 1 if AEC fails

**Files:**
- Create: `skull/audio/aec.py` (~80 lines) — SpeexDSP echo canceller wrapper
- Modify: `skull/audio/mic_stream.py` — integrate AEC into capture pipeline

**Design:**
```python
class EchoCanceller:
    def __init__(self, frame_size=256, sample_rate=16000):
        from speexdsp import EchoCanceller as SpxEC
        self._ec = SpxEC.create(frame_size, frame_size, sample_rate, 1)
    
    def process(self, mic_frame: bytes, speaker_frame: bytes) -> bytes:
        """Remove echo of speaker_frame from mic_frame."""
        return self._ec.process(mic_frame, speaker_frame)
```

---

## Phase 6: Error Recovery & Polish (Est: 20 min)

### Task 6.1: Error Recovery Within Sessions (10 min)

**Requirements:**
- MUST: STT failure → play `error_stt.wav`, return to LISTENING
- MUST: LLM timeout → play `error_timeout.wav`, return to FOLLOW_UP
- MUST: TTS failure → log error, skip sentence, continue
- MUST: ALSA error → attempt recovery, fall back to IDLE if unrecoverable

**Files:**
- Modify: `skull/pipeline.py` — wrap each stage in try/except with appropriate recovery
- Modify: `skull/main.py` — session-aware error handling

### Task 6.2: Ambient Noise Rejection (10 min)

**Requirements:**
- MUST: Minimum 0.5s continuous speech before committing to "speech detected"
- SHOULD: Baseline ambient energy calibration at startup
- SHOULD: STT confidence gating (discard nonsensical transcriptions)

**Files:**
- Modify: `skull/audio/recorder.py` — add minimum speech duration check
- Modify: `skull/pipeline.py` — add STT confidence check

---

## Phase 7: Integration Testing & Deployment (Est: 30 min)

### Task 7.1: End-to-End Testing (15 min)

**Test Cases:**
1. Wake word → greeting → follow-up question (no re-trigger)
2. Wake word → 5s silence → session closes with cue
3. Weather query → filler plays → response arrives → plays fully
4. Barge-in during long response → stops, listens, new response
5. Two errors in a row → session stays open
6. Multi-turn conversation (3+ turns) → 10s follow-up timeout

### Task 7.2: Deploy & Commit (15 min)

**Steps:**
1. Run full test suite on servo-skull
2. Commit all changes to `feature/skull-headless` branch
3. Update `deploy-skull.sh` if needed
4. Update SOUL.md if needed
5. Push to GitHub
6. Log session results to memory

---

## Implementation Readiness Checklist

- [x] Requirements clearly documented (conversation UX design spec)
- [x] Architecture defined (state machine + producer-consumer pipeline)
- [x] Implementation phases planned with time estimates
- [x] Quality gates identified (verification commands per task)
- [x] Security considerations addressed (no new attack surface)
- [x] Performance requirements specified (TTFA ≤3s)
- [x] Error handling strategy defined (per-state recovery)
- [x] Dependencies identified (speexdsp-python, ~/.asoundrc, pre-recorded WAVs)

**Total Estimated Time: ~4.5 hours**
**Recommended Execution:** Subagent-driven, one phase at a time with checkpoint reviews.

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| dmix adds >50ms latency | Playback quality | Benchmark before proceeding; fall back to device contention workaround |
| SpeexDSP AEC doesn't converge on small speaker | Barge-in unreliable | Layer 1 (VAD suppression) as primary; AEC as enhancement |
| Persistent arecord drops samples | Missing speech | Monitor for gaps; restart subprocess if needed |
| asyncio contention between tasks | Pipeline stalls | Use dedicated executor for blocking I/O; careful queue sizes |
| Session state machine edge cases | Stuck states | Watchdog timer: force SESSION_CLOSE after 120s of inactivity |
