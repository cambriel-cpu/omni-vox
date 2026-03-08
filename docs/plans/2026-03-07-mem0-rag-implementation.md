# Mem0 + Qdrant RAG Memory System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## MDD Documentation

### Goal & Context
**Goal:** Replace static MEMORY.md system prompt injection (~5.2K tokens/request) with Mem0 semantic memory backed by Qdrant + Ollama embeddings. Only relevant memories are injected per request (~500-1K tokens), saving ~4K tokens per message with no quality degradation.

**Why:** Token efficiency and memory quality. Every message currently carries the full MEMORY.md whether relevant or not. Mem0's auto-recall injects only semantically matched memories. Mem0's deduplication pipeline prevents memory bloat over months of use. Qdrant's multi-collection architecture enables future Horus Heresy knowledge base.

**Success Criteria:**
1. Mem0 plugin operational with self-hosted Qdrant + Ollama nomic-embed-text
2. MEMORY.md content migrated as atomic facts into Qdrant
3. MEMORY.md removed from system prompt injection
4. Auto-recall injects relevant memories; auto-capture stores new facts (via Haiku)
5. System prompt drops from ~20K to ~15-16K tokens (measured)
6. Quality regression test passes: 10 reference questions answered correctly
7. All operations fully local — no cloud dependencies
8. Success metrics tracked in `telemetry/memory-metrics.jsonl`

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    OpenClaw      │────▶│  Mem0 Plugin     │────▶│    Qdrant       │
│  (container)     │     │  (tensakulabs    │     │  (container)    │
│  192.168.68.99   │     │   fork)          │     │  192.168.68.51  │
└─────────────────┘     └───┬──────────┬───┘     │  :6333          │
                            │          │         └─────────────────┘
                   Embedding│   Extract│ (async, post-response)
                            ▼          ▼
                   ┌──────────┐  ┌──────────┐
                   │  Ollama   │  │  Haiku   │
                   │  nomic-   │  │  (fact   │
                   │  embed    │  │  extract)│
                   │  :11434   │  │          │
                   └──────────┘  └──────────┘
```

**Component choices and rationale:**

| Component | Choice | Why |
|-----------|--------|-----|
| Plugin | tensakulabs/openclaw-mem0 | Fixes critical bugs in official plugin (broken auto-recall, baseURL ignored) |
| Vector store | Qdrant (Docker) | Multi-collection (memory now, HH rules later), dedup support, dashboard UI, ~50MB RAM |
| Embeddings | BGE-M3 via Ollama | Best local retrieval quality, 1024 dims, ~1.2GB VRAM, <80ms latency, hybrid search capable |
| Fact extraction | Gemini Flash 2.5 | OpenAI-compatible API natively, fast, cheap, async post-response (zero latency impact) |
| Fallback extraction | Sonnet via OpenRouter | If Flash fails |

### Latency Budget

| Operation | When | Latency | User-facing? |
|-----------|------|---------|-------------|
| Embed inbound message (BGE-M3) | Before response | ~30-80ms | Yes (but negligible) |
| Qdrant vector search | Before response | ~5-20ms | Yes (but negligible) |
| Memory injection | Before response | ~1ms | No (string concat) |
| **Total recall overhead** | | **~35-100ms** | **Barely noticeable** |
| Fact extraction (Gemini Flash 2.5) | After response delivered | ~1-2s | **No — async** |
| Embed + store new facts (BGE-M3) | After response delivered | ~100ms | **No — async** |

### Chunking Strategy (Critical for Retrieval Quality)

**Mem0's pipeline is NOT traditional document RAG.** It does not chunk documents. Instead:

1. **Auto-capture** sends each conversation exchange to Haiku
2. **Haiku extracts atomic facts**: "Chris prefers Haiku for voice chat cost efficiency"
3. **Each fact is embedded** independently (one vector per fact)
4. **Before storing**, Mem0 checks for similar existing memories via embedding search
5. **LLM decides**: ADD (new fact), UPDATE (revise existing), DELETE (outdated), NOOP (already known)

This deduplication loop is why Mem0 > LanceDB for long-term use.

**For migrating MEMORY.md**, we manually decompose into atomic facts:

```
❌ Bad chunk (too broad, context-dependent):
"Setup Day - Fixed gateway pairing issue, completed SOUL.md customization,
deleted BOOTSTRAP.md, key preferences learned..."

✅ Good atomic facts:
"Chris Langston is a Director of UX Research at Meta working on AI-powered wearable devices"
"Chris's wife is Ashley"
"Chris's daughter Isabel was born around May 2024 and is approximately 21 months old"
"The family dog Maggie is a Bernese Mountain Dog, about 2 years old"
"Chris is located in Marietta, Georgia, timezone America/New_York"
```

**Fact quality rules:**
- **~50-100 tokens max** per fact (shorter = better retrieval precision)
- **Self-contained**: No pronouns without antecedents. "He prefers Haiku" → "Chris prefers Claude Haiku for voice chat"
- **Entity names in full**: "Omni Vox" not "the voice gateway", "servo-skull" not "the Pi"
- **Temporal context when relevant**: "As of February 2026, heartbeats are disabled in OpenClaw"
- **One fact per entry**: "The Omnissiah server has an RTX 4070 Ti Super GPU" (not "The server has GPU and 64GB RAM and runs Unraid")
- **Categorized**: preference / fact / decision / entity

### Success Metrics

**Primary metric: Token savings without quality degradation**

Track in `telemetry/memory-metrics.jsonl`:
```json
{
  "timestamp": "2026-03-08T00:00:00Z",
  "event": "response",
  "totalTokens": 16234,
  "cacheRead": 14500,
  "memoriesInjected": 3,
  "memoriesTokens": 450,
  "baselineTokens": 20500,
  "tokensSaved": 4266
}
```

**Quality regression test — 10 reference questions:**

| # | Question | Expected Answer | Source Memory |
|---|----------|-----------------|---------------|
| 1 | What is Chris's job title? | Director of UX Research at Meta | entity/fact |
| 2 | What's the servo-skull's Tailscale IP? | 100.69.9.99 | fact |
| 3 | What voice does Omni use for TTS? | bm_george via Kokoro | preference |
| 4 | Who is Nate? | Beta tester, Discord natecro_magnon | entity |
| 5 | What's the Omni Vox container port? | 7100 | fact |
| 6 | Why were heartbeats disabled? | Qwen unreliable at tool-use cron tasks | decision |
| 7 | What's Chris's daughter's name? | Isabel | entity |
| 8 | What GPU does the Omnissiah have? | RTX 4070 Ti Super (16GB VRAM) | fact |
| 9 | What wake word does the servo-skull use? | "Hey Jarvis" | fact |
| 10 | Why did we choose host networking for Omni Vox? | Eliminates macvlan shim dependencies | decision |

Run before migration (against MEMORY.md) and after (against Mem0 recall). All 10 must pass.

### Quality Requirements
**Performance:** Total recall overhead <100ms per request
**Accuracy:** 10/10 regression questions answered correctly post-migration
**Token savings:** ≥3K tokens saved per message (measurable)
**Reliability:** Qdrant data persists across container restarts
**Fallback:** MEMORY.md backup retained; can re-enable if quality degrades

---

## Task List

### Task 1: Deploy Qdrant Container on Unraid (Estimated: 15m)

**MDD Context:** Qdrant is the vector database backing Mem0. Single container, minimal resources.

**Requirements:**
- MUST: Deploy Qdrant Docker container on Unraid with persistent storage
- MUST: Accessible from OpenClaw container at 192.168.68.51:6333
- MUST: Data persists at `/mnt/user/appdata/qdrant/`
- MUST: Auto-restart policy `unless-stopped`

**Step 1: Deploy Qdrant**

```bash
ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no omni@192.168.68.51 "
  sudo docker run -d \
    --name qdrant \
    --restart unless-stopped \
    -p 6333:6333 \
    -p 6334:6334 \
    -v /mnt/user/appdata/qdrant/storage:/qdrant/storage:z \
    -v /mnt/user/appdata/qdrant/snapshots:/qdrant/snapshots:z \
    qdrant/qdrant:latest && \
  echo 'deployed'
"
```

**Step 2: Verify Qdrant is running**

```bash
curl -s http://192.168.68.51:6333/collections | python3 -m json.tool
```
Expected: `{"result": {"collections": []}, "status": "ok"}`

**Step 3: Verify dashboard accessible**

Open `http://192.168.68.51:6333/dashboard` — should show Qdrant web UI.

**Step 4: Document in TOOLS.md**

Add Qdrant section:
```
## Qdrant (Vector Database)
- **Container:** `qdrant` on Unraid
- **Ports:** 6333 (HTTP API), 6334 (gRPC)
- **Storage:** `/mnt/user/appdata/qdrant/storage/`
- **Dashboard:** `http://192.168.68.51:6333/dashboard`
- **Purpose:** Vector store for Mem0 memory system
```

**Step 5: Commit**

```bash
git commit -m "docs: add Qdrant vector database to TOOLS.md"
```

---

### Task 2: Install Ollama Embedding Model (Estimated: 10m)

**MDD Context:** nomic-embed-text provides local embeddings. Needs to be pulled on Ollama.

**Requirements:**
- MUST: Pull nomic-embed-text on Ollama
- MUST: Verify OpenAI-compatible embedding endpoint works
- MUST: Measure embedding latency (<100ms target)

**Step 1: Pull the model**

```bash
ssh -i /root/.ssh/id_ed25519 omni@192.168.68.51 "sudo docker exec ollama ollama pull bge-m3"
```

**Step 2: Test embedding endpoint**

```bash
curl -s http://192.168.68.51:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "bge-m3", "input": "Chris prefers Haiku for voice chat"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Dims: {len(d[\"data\"][0][\"embedding\"])}, first 3: {d[\"data\"][0][\"embedding\"][:3]}')"
```
Expected: `Dims: 1024, first 3: [0.xxx, 0.xxx, 0.xxx]`

**Step 3: Measure latency**

```bash
time curl -s http://192.168.68.51:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "bge-m3", "input": "Test embedding latency measurement"}'
```
Expected: <100ms warm, <3s cold start.

**Step 4: Document in TOOLS.md**

Add under Ollama section:
```
- **Embedding model:** `bge-m3` (1024 dims, ~1.2GB VRAM)
- **Endpoint:** `http://192.168.68.51:11434/v1/embeddings` (OpenAI-compatible)
- **Use:** Mem0 memory embeddings
```

**Step 5: Commit**

```bash
git commit -m "docs: add nomic-embed-text embedding model to TOOLS.md"
```

---

### Task 3: Install and Configure Mem0 Plugin (Estimated: 25m)

**MDD Context:** The tensakulabs fork of openclaw-mem0 fixes critical self-hosted bugs. Configure with Qdrant + Ollama embeddings + Haiku extraction.

**Requirements:**
- MUST: Install tensakulabs/openclaw-mem0 plugin
- MUST: Configure Qdrant at 192.168.68.51:6333
- MUST: Configure Ollama nomic-embed-text for embeddings
- MUST: Configure Haiku for fact extraction
- MUST: Enable autoCapture and autoRecall
- MUST: Verify plugin loads and creates Qdrant collection
- SHOULD: Disable memory-core plugin to avoid tool name collision

**Step 1: Install the plugin**

```bash
openclaw plugins install github:tensakulabs/openclaw-mem0
```

**Step 2: Run quality regression baseline**

Before any changes, test the 10 reference questions against current MEMORY.md system. Record answers as the baseline. Save to `telemetry/memory-regression-baseline.json`.

**Step 3: Configure via gateway config patch**

⚠️ **This triggers a gateway restart.**

```json
{
  "plugins": {
    "entries": {
      "openclaw-mem0": {
        "enabled": true,
        "config": {
          "mode": "open-source",
          "userId": "chris",
          "autoCapture": true,
          "autoRecall": true,
          "topK": 5,
          "searchThreshold": 0.3,
          "oss": {
            "embedder": {
              "provider": "openai",
              "config": {
                "apiKey": "ollama",
                "baseURL": "http://192.168.68.51:11434/v1",
                "model": "bge-m3"
              }
            },
            "vectorStore": {
              "provider": "qdrant",
              "config": {
                "host": "192.168.68.51",
                "port": 6333,
                "collectionName": "omni-memories"
              }
            },
            "llm": {
              "provider": "openai",
              "config": {
                "apiKey": "${GEMINI_API_KEY}",
                "baseURL": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-2.5-flash"
              }
            }
          }
        }
      }
    }
  }
}
```

Notes:
- `userId: "chris"` — scopes all memories to Chris
- `topK: 5` — recall up to 5 relevant memories per request
- `searchThreshold: 0.3` — minimum similarity score (tune in Task 6)
- Embedder: Ollama nomic-embed-text via OpenAI-compatible API
- LLM (extraction): Gemini Flash 2.5 for fact extraction/dedup decisions (OpenAI-compatible natively)
- Vector store: Qdrant on Unraid

**Gemini Flash 2.5** is used for fact extraction because Google's API has a native OpenAI-compatible endpoint — no proxy needed. The GEMINI_API_KEY is already available in the environment.

**Step 4: Verify plugin loads**

```bash
openclaw plugins list | grep -i mem0
```
Expected: `openclaw-mem0` shows as loaded.

**Step 5: Verify Qdrant collection created**

```bash
curl -s http://192.168.68.51:6333/collections/omni-memories | python3 -m json.tool
```
Expected: Collection exists with vector config matching 768 dimensions.

**Step 6: Test auto-capture with a simple message**

Send a test message in Discord: "My favorite color is blue."
Wait 10 seconds, then check:
```bash
openclaw mem0 search "favorite color"
```
Expected: Returns "User's favorite color is blue" or similar extracted fact.

**Step 7: Disable memory-core plugin (optional, if tool names collide)**

```bash
openclaw plugins disable memory-core
```

Only do this if there's a naming collision between memory-core's `memory_search` and Mem0's `memory_search`. If they coexist without conflict, keep both.

**Step 8: Commit**

```bash
git commit -m "feat: install and configure Mem0 plugin with Qdrant + Ollama embeddings"
```

---

### Task 4: Chunk and Migrate MEMORY.md (Estimated: 45m)

**MDD Context:** The most critical task. MEMORY.md (~5.2K tokens) must be decomposed into atomic, self-contained facts and seeded into Qdrant via Mem0's memory_store.

**Requirements:**
- MUST: Parse MEMORY.md into sections
- MUST: Decompose each section into atomic facts (~50-100 tokens each)
- MUST: Each fact is self-contained (no dangling pronouns or references)
- MUST: Each fact includes full entity names and temporal context
- MUST: Store all facts via Mem0's memory_store tool with appropriate categorization
- MUST: Verify all facts are searchable after migration
- SHOULD: Produce 80-150 total atomic facts

**Files:**
- Create: `scripts/migrate-memory-to-mem0.py`
- Read: `MEMORY.md`

**Step 1: Create the migration script**

```python
#!/usr/bin/env python3
"""
Migrate MEMORY.md into Mem0 vector memory.

Reads MEMORY.md, decomposes into atomic facts,
stores each via OpenClaw CLI or Mem0 API.
"""

import re
import subprocess
import json
import time

def parse_memory_md(filepath: str) -> list[dict]:
    """Parse MEMORY.md into sections, then atomic facts."""
    with open(filepath) as f:
        content = f.read()
    
    # Split by ## headers
    sections = re.split(r'^## ', content, flags=re.MULTILINE)
    
    facts = []
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        header = lines[0].strip()
        body = '\n'.join(lines[1:])
        
        section_facts = extract_atomic_facts(header, body)
        facts.extend(section_facts)
    
    return facts

def extract_atomic_facts(header: str, body: str) -> list[dict]:
    """Extract self-contained atomic facts from a section."""
    facts = []
    
    for line in body.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('```'):
            continue
        # Strip markdown formatting
        line = line.lstrip('- ').lstrip('* ').strip()
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # Remove bold
        
        if len(line) < 10:  # Skip tiny fragments
            continue
            
        # Determine if line needs section context
        fact_text = line
        if needs_context(line):
            fact_text = f"{header} — {line}"
        
        facts.append({
            "text": fact_text,
            "category": classify(line, header),
            "section": header,
        })
    
    return facts

def needs_context(line: str) -> bool:
    """Check if a line needs its section header for context."""
    # Lines starting with pronouns or lacking clear subject
    context_indicators = ['it ', 'its ', 'this ', 'that ', 'he ', 'she ', 'they ']
    lower = line.lower()
    return any(lower.startswith(ind) for ind in context_indicators)

def classify(line: str, header: str) -> str:
    """Classify a fact into a category."""
    lower = line.lower()
    header_lower = header.lower()
    
    if any(w in lower for w in ['prefer', 'chose', 'like', 'want', 'style']):
        return "preference"
    if any(w in lower for w in ['decided', 'chose', 'switched', 'because', 'rationale']):
        return "decision"
    if any(w in lower for w in ['chris', 'ashley', 'nate', 'isabel', 'bennett']):
        return "entity"
    return "fact"

def store_fact(fact: dict) -> bool:
    """Store a fact via OpenClaw Mem0 CLI."""
    # Use openclaw mem0 store command if available
    # Otherwise use the memory_store tool via hooks
    cmd = [
        "openclaw", "mem0", "store",
        "--text", fact["text"],
        "--long-term"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"  Error storing: {e}")
        return False

def main():
    facts = parse_memory_md("/root/.openclaw/workspace/MEMORY.md")
    
    print(f"Extracted {len(facts)} atomic facts from MEMORY.md")
    print(f"Categories: { {c: sum(1 for f in facts if f['category']==c) for c in set(f['category'] for f in facts)} }")
    print()
    
    # Save extracted facts for review before storing
    with open("/tmp/memory-facts.json", "w") as f:
        json.dump(facts, f, indent=2)
    print("Facts saved to /tmp/memory-facts.json for review")
    print()
    
    # Store each fact with a delay to avoid rate limits
    stored = 0
    failed = 0
    for i, fact in enumerate(facts):
        print(f"[{i+1}/{len(facts)}] {fact['category']:12} | {fact['text'][:80]}...")
        if store_fact(fact):
            stored += 1
        else:
            failed += 1
        time.sleep(0.5)  # Rate limit
    
    print(f"\nMigration complete: {stored} stored, {failed} failed")

if __name__ == "__main__":
    main()
```

**IMPORTANT:** Before running the automated script, manually review and edit the extracted facts in `/tmp/memory-facts.json`. The automated extraction will be imperfect — some facts will need manual splitting, context addition, or rewording for self-containment. This is where quality comes from.

**Manual chunking examples for key sections:**

MEMORY.md Section: "2026-02-10 — First Boot"
```
→ "Omni came online for the first time on February 10, 2026"
→ "Omni was named after the Omnissiah, the home server it runs on"
→ "Chris Langston is a Director of UX Research at Meta working on AI-powered wearable devices"
→ "Chris's wife is named Ashley"
→ "Chris's daughter Isabel is approximately 21 months old, born around May 2024"
→ "The family dog Maggie is a Bernese Mountain Dog, about 2 years old"
→ "Chris and family are located in Marietta, Georgia"
```

MEMORY.md Section: "TTS Setup"
```
→ "Omni's TTS voice is bm_george (British male) via Kokoro, running locally on the Omnissiah"
→ "Kokoro TTS runs at http://192.168.68.51:8880/v1 via OpenAI-compatible API"
→ "Chris chose the bm_george voice from 4 British male samples on February 13, 2026"
→ "ElevenLabs TTS config is preserved as a fallback to Kokoro"
```

MEMORY.md Section: "Local AI Stack"
```
→ "Qwen 2.5 32B runs on Ollama at 192.168.68.51:11434 with Q4_K_M quantization"
→ "Qwen 2.5 32B generates at approximately 5.5 tokens/second warm, with 9 second cold start"
→ "Kokoro TTS, Whisper STT, and Qwen 2.5 32B all fit in 16GB VRAM at 93% utilization"
→ "Ollama auto-evicts models after approximately 5 minutes idle"
→ "Qwen is used for cron jobs, subagent work, and bulk processing; Claude for primary reasoning"
```

**Step 2: Run the extraction**

```bash
cd /root/.openclaw/workspace && python3 scripts/migrate-memory-to-mem0.py
```

**Step 3: Review extracted facts**

Open `/tmp/memory-facts.json` and manually verify:
- Each fact is self-contained
- No duplicate information
- Categories are reasonable
- All critical info from MEMORY.md is captured

Edit as needed, then run the storage phase.

**Step 4: Verify storage in Qdrant**

```bash
curl -s http://192.168.68.51:6333/collections/omni-memories | python3 -c "
import json,sys
d = json.load(sys.stdin)
print(f'Points stored: {d[\"result\"][\"points_count\"]}')"
```
Expected: 80-150 points.

**Step 5: Test retrieval quality**

Run the 10 regression questions:
```bash
openclaw mem0 search "Chris's job title"
openclaw mem0 search "servo-skull Tailscale IP address"
openclaw mem0 search "Omni TTS voice"
openclaw mem0 search "Nate beta tester"
openclaw mem0 search "Omni Vox container port"
openclaw mem0 search "why heartbeats disabled"
openclaw mem0 search "Chris daughter name"
openclaw mem0 search "Omnissiah GPU"
openclaw mem0 search "servo-skull wake word"
openclaw mem0 search "why host networking Omni Vox"
```

All 10 must return relevant results. Record results in `telemetry/memory-regression-post.json`.

**Step 6: Commit**

```bash
git add scripts/migrate-memory-to-mem0.py telemetry/
git commit -m "feat: MEMORY.md migration script and regression test results"
```

---

### Task 5: Remove MEMORY.md from System Prompt (Estimated: 15m)

**MDD Context:** With memories in Qdrant and auto-recall working, MEMORY.md no longer needs to be in the system prompt. This is where we realize the token savings.

**Requirements:**
- MUST: Only proceed if Task 4 regression test passed 10/10
- MUST: Remove MEMORY.md from workspace context injection
- MUST: Keep the file as a reference backup (do NOT delete)
- MUST: Measure token reduction
- MUST: Verify auto-recall injects relevant context in its place

**Step 1: Take a token usage baseline**

Record current system prompt token count from a fresh response:
```python
# Get totalTokens and cacheRead from latest assistant message
# Save as baseline in telemetry/memory-metrics.jsonl
```

**Step 2: Move MEMORY.md out of injection path**

OpenClaw injects files from the workspace root that match known patterns. Options:

Option A: Rename to `MEMORY.md.bak` (stops auto-injection)
Option B: Move to `memory/MEMORY-archive.md`

Use Option A — simplest, clearly communicates intent, easy to revert:
```bash
mv MEMORY.md MEMORY.md.bak
```

⚠️ **This triggers a workspace reload. May require restart.**

**Step 3: Measure token reduction**

After next response, compare:
- Baseline total tokens: ~20K
- New total tokens: should be ~15-16K
- Difference: ~4-5K tokens saved
- Auto-recalled memories: should see ~200-500 tokens of injected context

Log to `telemetry/memory-metrics.jsonl`:
```json
{"event": "migration", "before": 20500, "after": 15800, "saved": 4700, "recalled": 3, "recalledTokens": 420}
```

**Step 4: Quality spot-check**

Have a conversation that touches on different memory areas:
1. Ask about infrastructure → should recall network/container facts
2. Ask about Chris → should recall personal/family facts  
3. Ask about a past decision → should recall decision context
4. General chat → should not inject irrelevant memories

**Step 5: If quality degrades, revert**

```bash
mv MEMORY.md.bak MEMORY.md
# Restart gateway
```

**Step 6: Commit**

```bash
git add -A
git commit -m "perf: remove MEMORY.md from system prompt — now served via Mem0 auto-recall

Saves ~4-5K tokens per message. Memories stored in Qdrant
and injected only when semantically relevant."
```

---

### Task 6: End-to-End Verification and Tuning (Estimated: 20m)

**MDD Context:** Final verification across all channels (Discord, Omni Vox voice) and parameter tuning.

**Requirements:**
- MUST: Verify auto-recall works in Discord chat
- MUST: Verify auto-recall works through Omni Vox voice hooks
- MUST: Verify auto-capture stores new facts
- MUST: Verify deduplication (storing same fact twice doesn't duplicate)
- MUST: Set up ongoing metrics tracking
- SHOULD: Tune topK and searchThreshold based on results

**Step 1: Test Discord conversation**

Have a normal conversation in Discord that touches on stored memories. Verify relevant context appears.

**Step 2: Test Omni Vox voice**

Send a voice message referencing prior context. Verify response reflects recalled memories.

⚠️ **Verify auto-recall fires on hook requests.** Omni Vox sends messages via `/hooks/agent` which creates new sessions per request (bug #11665). If auto-recall doesn't fire on hook sessions, we need to add explicit Qdrant search in Omni Vox's `server.py` before the hook call — embed the transcript via Ollama, search Qdrant, inject results into the voice message prefix. Same latency, different code path.

**Step 3: Test auto-capture**

Share a new fact: "I'm thinking about getting a second 3D printer for resin."
Wait 30 seconds. Then search:
```bash
openclaw mem0 search "3D printer resin"
```
Expected: Fact captured and retrievable.

**Step 4: Test deduplication**

Share the same fact again: "I'm thinking about getting a resin 3D printer."
Search again — should still show 1 result (updated, not duplicated):
```bash
openclaw mem0 search "3D printer resin"
```

**Step 5: Tune parameters if needed**

- **Too many irrelevant memories recalled:** Raise `searchThreshold` from 0.3 → 0.5
- **Missing relevant memories:** Lower `searchThreshold` to 0.2, raise `topK` from 5 → 8
- **Auto-capture missing facts:** Check Haiku extraction logs, may need to raise `captureMaxChars`

Apply tuning via:
```bash
# gateway config.patch with updated values
```

**Step 6: Set up ongoing metrics**

Create a lightweight metrics logger that tracks per-response:
- Total tokens
- Tokens saved vs baseline
- Number of memories recalled
- Memory recall relevance (sampled)

Store in `telemetry/memory-metrics.jsonl` for periodic review.

**Step 7: Update documentation**

- Update TOOLS.md with final Qdrant + Mem0 configuration
- Update AGENTS.md if memory workflow changes
- Create daily memory note documenting the migration

**Step 8: Commit**

```bash
git add -A
git commit -m "docs: finalize Mem0 RAG configuration, tuning, and metrics tracking"
```

---

## Summary of Changes

| Component | Change |
|-----------|--------|
| Qdrant | New Docker container on Unraid, port 6333 |
| Ollama | Pull nomic-embed-text embedding model |
| OpenClaw plugins | Install tensakulabs/openclaw-mem0, configure with Qdrant + Ollama + Haiku |
| MEMORY.md | Content migrated to Qdrant, file renamed to .bak (removed from system prompt) |
| memory-core plugin | Potentially disabled (if tool name collision) |
| scripts/ | Migration script for chunking and seeding |
| telemetry/ | Memory metrics tracking, regression test results |
| TOOLS.md | Updated with Qdrant, embedding model, Mem0 config |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Gemini Flash 2.5 extraction quality insufficient | Low | Medium | Fall back to Sonnet via OpenRouter |
| BGE-M3 embedding quality insufficient | Low | Medium | Switch to text-embedding-3-small (cloud, ~$0.02/1M tokens) |
| Qdrant container fails | Low | Medium | LanceDB plugin as fallback, MEMORY.md.bak to restore |
| Poor recall quality | Medium | High | Tune searchThreshold/topK, manual fact editing, revert to MEMORY.md |
| Auto-capture stores garbage | Medium | Low | Review with `openclaw mem0 list`, use `memory_forget` to clean up |
| Gemini Flash OpenAI endpoint changes | Low | Medium | Fall back to OpenRouter for Haiku/Sonnet |

## What This Does NOT Do (Phase 2)

- **Horus Heresy knowledge base** — Separate Qdrant collection for rulebooks (different chunking: 500-token overlapping windows)
- **TOOLS.md migration** — Prove value with MEMORY.md first
- **Cross-channel memory** — Discord ↔ Voice context sharing
- **Automatic memory pruning** — Manual review for now
- **Memory UI/dashboard** — Use Qdrant dashboard for debugging

## Estimated Total Time: ~2.5 hours

| Task | Time | Description |
|------|------|-------------|
| 1 | 15m | Deploy Qdrant container |
| 2 | 10m | Install Ollama embedding model |
| 3 | 25m | Install and configure Mem0 plugin |
| 4 | 45m | Chunk and migrate MEMORY.md |
| 5 | 15m | Remove from system prompt |
| 6 | 20m | E2E verification and tuning |
| **Total** | **~130m** | |
