# Mem0 RAG Memory System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## MDD Documentation

### Goal & Context
**Goal:** Replace the static MEMORY.md system prompt injection (~5.2K tokens/request) with Mem0 semantic memory that injects only relevant context (~500-1K tokens/request), saving ~4K tokens per message.

**Why:** Token efficiency. Every voice and chat message carries the full MEMORY.md whether relevant or not. Mem0's auto-recall injects only semantically relevant memories. Secondary goal: lay the foundation for a Horus Heresy knowledge base RAG collection.

**Success Criteria:**
1. Mem0 plugin installed and operational with self-hosted Qdrant + Ollama embeddings
2. MEMORY.md content migrated into Mem0 vector store as structured memories
3. MEMORY.md removed from system prompt injection (workspace context)
4. Auto-recall injects relevant memories before each response
5. Auto-capture stores new facts from conversations automatically
6. System prompt drops from ~20K to ~15-16K tokens
7. Response quality maintained or improved (relevant context > full dump)
8. All embedding and LLM operations run locally (no cloud dependencies)

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    OpenClaw      │────▶│  Mem0 Plugin     │────▶│    Qdrant       │
│  (container)     │     │  (auto-recall/   │     │  (container)    │
│  192.168.68.99   │     │   auto-capture)  │     │  :6333          │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │    Ollama         │
                        │  nomic-embed-text │
                        │  192.168.68.51   │
                        │  :11434           │
                        └──────────────────┘
```

**Plugin choice: `memory-lancedb` (stock) vs `@mem0/openclaw-mem0` (npm) vs `tensakulabs/openclaw-mem0` (fork)**

After reviewing all three:

- **`memory-lancedb`** — Stock plugin, already bundled. Uses OpenAI-compatible embeddings with LanceDB (local file-based vector store). No extra containers needed. Supports `baseUrl` override for Ollama. Categories: preference, fact, decision, entity, other. Auto-recall and auto-capture built in. **Simpler, zero new infrastructure.**
- **`@mem0/openclaw-mem0`** — Official Mem0 plugin. More features (session + long-term scopes, 5 tools). But has known bugs in self-hosted mode (broken auto-recall, embeddings ignore baseURL). Requires Qdrant container.
- **`tensakulabs/openclaw-mem0`** — Community fork fixing the official plugin's bugs. Works with OpenAI-compatible providers. Requires Qdrant container.

**Recommendation: Start with `memory-lancedb` (stock plugin).**

Rationale:
- Already bundled — no `npm install` or external dependencies
- LanceDB is file-based — no Qdrant container needed (one fewer thing to manage)
- Supports Ollama via `baseUrl: "http://192.168.68.51:11434/v1"`
- Auto-recall/capture built in with category classification
- If we outgrow it, we can migrate to Mem0+Qdrant later (same embedding vectors, different store)

### Embedding Model Choice

**nomic-embed-text** via Ollama:
- 768 dimensions, 8192 token context window
- ~274MB VRAM (negligible alongside Qwen 32B)
- Best quality/speed ratio for self-hosted (86.2% top-5 hit rate)
- Ollama pulls it in seconds: `ollama pull nomic-embed-text`
- OpenAI-compatible API at `/v1/embeddings`

### Chunking Strategy (Critical for Quality)

**How Mem0/LanceDB memory capture works:**

Unlike traditional RAG that chunks documents, Mem0-style memory systems extract **atomic facts** from conversations. The pipeline is:

1. **After each conversation turn**, the auto-capture hook sends the exchange to an LLM
2. **The LLM extracts discrete facts**: "Chris prefers Haiku for voice chat", "Servo-skull uses Pi 5 at 100.69.9.99", etc.
3. **Each fact is embedded** as a single vector (not chunked from a larger doc)
4. **On recall**, the inbound message is embedded and similar facts are retrieved

This means chunking quality depends on:
- **The extraction LLM prompt** — what it's told to extract (the plugin handles this)
- **The capture window** — `captureMaxChars` controls max message length for auto-capture (default 500, we should raise to 2000+ for our longer exchanges)
- **Fact granularity** — one fact per vector entry, not paragraphs

**For migrating MEMORY.md:** We need to manually chunk it into atomic facts before seeding. Each section becomes multiple individual memories:
```
# Bad: One giant chunk
"Chris is a Director of UX Research at Meta working on AI wearables. Household: Chris, wife Ashley, daughter Isabel..."

# Good: Atomic facts
"Chris's role is Director of UX Research at Meta"
"Chris works on AI-powered wearable devices at Meta"
"Chris's wife is Ashley"
"Chris's daughter Isabel is approximately 21 months old, born around May 2024"
"The family dog is Maggie, a Bernese Mountain Dog, about 2 years old"
```

**For future Horus Heresy knowledge base:** Different approach needed:
- Rulebooks are large documents, not conversational facts
- Would use traditional document RAG: chunk into ~500-token segments with overlap
- Separate LanceDB table or separate Qdrant collection
- Phase 2 work, not part of this plan

### Quality Requirements
**Performance:** Embedding generation <100ms, vector search <20ms, total RAG overhead <200ms
**Accuracy:** Retrieved memories should be relevant >80% of the time
**Token savings:** System prompt reduction from ~20K to ~15-16K tokens
**Reliability:** Memory persistence across container restarts (LanceDB stores to disk)

---

## Task List

### Task 1: Install and Configure Ollama Embedding Model (Estimated: 15m)

**MDD Context:** nomic-embed-text needs to be available on Ollama before we can use it for embeddings. We also need to verify the OpenAI-compatible embedding endpoint works.

**Requirements:**
- MUST: Pull nomic-embed-text model on Ollama
- MUST: Verify embedding endpoint returns vectors
- MUST: Confirm VRAM coexistence with existing models

**Files:**
- No file changes — infrastructure only

**Step 1: Pull the embedding model**

```bash
ssh -i /root/.ssh/id_ed25519 omni@192.168.68.51 "sudo docker exec ollama ollama pull nomic-embed-text"
```

**Step 2: Test the embedding endpoint**

```bash
curl -s http://192.168.68.51:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "input": "Chris prefers Haiku for voice chat"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Dims: {len(d[\"data\"][0][\"embedding\"])}')"
```
Expected: `Dims: 768`

**Step 3: Verify VRAM usage**

```bash
ssh -i /root/.ssh/id_ed25519 omni@192.168.68.51 "nvidia-smi --query-gpu=memory.used,memory.total --format=csv"
```
Expected: nomic-embed-text adds ~274MB, well within 16GB budget.

**Step 4: Test latency**

```bash
time curl -s http://192.168.68.51:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "input": "Test embedding latency"}'
```
Expected: <100ms after model is loaded.

**Step 5: Commit (docs only)**

```bash
# Update TOOLS.md with embedding model info
# Add under "Local LLM (Ollama)" section
git commit -m "docs: add nomic-embed-text embedding model to TOOLS.md"
```

---

### Task 2: Enable and Configure memory-lancedb Plugin (Estimated: 20m)

**MDD Context:** The stock memory-lancedb plugin is already bundled in OpenClaw. We need to enable it with Ollama as the embedding provider.

**Requirements:**
- MUST: Enable memory-lancedb plugin in openclaw.json
- MUST: Configure to use Ollama's nomic-embed-text via OpenAI-compatible API
- MUST: Set appropriate dimensions (768 for nomic-embed-text)
- MUST: Enable autoCapture and autoRecall
- MUST: Set captureMaxChars high enough for our conversations (2000)
- SHOULD: Verify plugin loads successfully after restart

**Files:**
- Modify: `/root/.openclaw/openclaw.json` (via gateway config.patch)

**Step 1: Check current memory-core plugin status**

The existing `memory-core` plugin provides `memory_search` and `memory_get` tools that search MEMORY.md. We need to understand if enabling memory-lancedb conflicts with or replaces memory-core.

```bash
openclaw plugins info memory-core
openclaw plugins info memory-lancedb
```

**Step 2: Enable memory-lancedb via gateway config patch**

⚠️ **This triggers a gateway restart.** Warn Chris before executing.

```json
{
  "plugins": {
    "entries": {
      "memory-lancedb": {
        "enabled": true,
        "config": {
          "embedding": {
            "apiKey": "ollama",
            "baseUrl": "http://192.168.68.51:11434/v1",
            "model": "nomic-embed-text",
            "dimensions": 768
          },
          "autoCapture": true,
          "autoRecall": true,
          "captureMaxChars": 2000
        }
      }
    }
  }
}
```

Notes:
- `apiKey: "ollama"` — Ollama doesn't require a real key but the field is required
- `baseUrl` points to Ollama's OpenAI-compatible endpoint
- `dimensions: 768` — nomic-embed-text output size (required since it's not in the hardcoded dimension map for OpenAI models)
- `captureMaxChars: 2000` — our voice/chat exchanges can be longer than the 500 default
- `autoRecall: true` — inject relevant memories before each response
- `autoCapture: true` — extract facts after each exchange

**Step 3: Verify plugin loads after restart**

```bash
openclaw plugins list | grep -i memory
```
Expected: Both `memory-core` (loaded) and `memory-lancedb` (loaded)

**Step 4: Verify LanceDB database created**

```bash
ls -la /root/.openclaw/memory/lancedb/
```
Expected: LanceDB data files present

**Step 5: Test with a simple conversation**

Send a test message and check if auto-capture stores a memory:
```bash
openclaw mem0 stats  # or check LanceDB files
```

**Step 6: Commit**

No code changes — config only. Document the configuration in memory file.

---

### Task 3: Chunk and Migrate MEMORY.md into Vector Store (Estimated: 45m)

**MDD Context:** This is the most important task for embedding quality. MEMORY.md contains ~5.2K tokens of structured information that needs to be broken into atomic facts for effective semantic retrieval.

**Requirements:**
- MUST: Parse MEMORY.md into semantic sections
- MUST: Break each section into atomic, self-contained facts
- MUST: Each fact should be independently meaningful (no "it" or "this" references)
- MUST: Preserve key metadata (dates, categories)
- MUST: Inject all facts into LanceDB via the plugin's memory_store tool
- SHOULD: Verify retrieval quality with test queries
- MUST: Keep MEMORY.md as a backup until we verify the migration

**Files:**
- Create: `scripts/migrate-memory-to-lancedb.py` — migration script
- Read: `MEMORY.md` — source data

**Step 1: Create the migration script**

The script should:
1. Read MEMORY.md
2. Parse it into sections (split by `## ` headers)
3. For each section, extract atomic facts (one per line, self-contained)
4. Categorize each fact (preference, fact, decision, entity)
5. Store each fact via the memory-lancedb plugin's tools

Chunking rules for quality:
- **Maximum chunk size:** ~100 tokens (~400 chars). Shorter is better for retrieval precision.
- **Self-contained:** Each chunk must make sense without context. Bad: "He uses Pi 5". Good: "The servo-skull project uses a Raspberry Pi 5 at Tailscale IP 100.69.9.99"
- **Deduplicate:** Remove redundant information across sections
- **Temporal markers:** Include dates where relevant: "As of February 2026, heartbeats are disabled"
- **Entity linking:** Always include the full name: "Chris Langston" not "Chris" for the first reference, "Omni Vox" not "the voice gateway"

Categories mapping:
- **preference:** Communication style, interests, how Chris likes things done
- **fact:** Infrastructure details, network IPs, container configs, family info
- **decision:** Architectural choices, tool selections, why we chose X over Y
- **entity:** People (Chris, Ashley, Nate), devices (Omnissiah, Magnus, servo-skull), services

**Step 2: Write a chunking function**

```python
def chunk_memory_section(header: str, body: str) -> list[dict]:
    """Break a memory section into atomic facts with categories."""
    facts = []
    # Split by bullet points or newlines
    for line in body.strip().split('\n'):
        line = line.strip().lstrip('- ').strip()
        if not line or line.startswith('#'):
            continue
        # Each non-empty line becomes a fact
        # Prefix with section context if needed for self-containment
        fact = {
            'text': f"{header}: {line}" if needs_context(line) else line,
            'category': classify_fact(line),
            'section': header,
        }
        facts.append(fact)
    return facts
```

**Step 3: Run the migration**

Execute the script to inject all facts. Use the OpenClaw CLI or direct LanceDB access.

**Step 4: Verify retrieval quality**

Test queries that should retrieve specific memories:
```bash
# Should find servo-skull info
openclaw mem0 search "servo-skull SSH access"

# Should find Chris's interests
openclaw mem0 search "what are Chris's hobbies"

# Should find voice gateway config
openclaw mem0 search "Omni Vox container configuration"

# Should find family info
openclaw mem0 search "Chris's family members"

# Should NOT return irrelevant results
openclaw mem0 search "what's the weather like"
```

**Step 5: Count total memories and verify coverage**

```bash
openclaw mem0 stats
```
Expected: 80-150 atomic facts covering all MEMORY.md content.

**Step 6: Commit**

```bash
git add scripts/migrate-memory-to-lancedb.py
git commit -m "feat: add MEMORY.md migration script for LanceDB vector memory"
```

---

### Task 4: Remove MEMORY.md from System Prompt (Estimated: 15m)

**MDD Context:** Once memories are in LanceDB and auto-recall is working, we can remove MEMORY.md from the workspace context files that get injected into every system prompt.

**Requirements:**
- MUST: Verify auto-recall is working correctly before removing
- MUST: Remove MEMORY.md from workspace file injection (not delete the file)
- MUST: Keep MEMORY.md as a reference backup
- MUST: Verify token reduction in system prompt
- SHOULD: Test a conversation to confirm quality is maintained

**Step 1: Verify auto-recall works**

Send a message referencing something only in MEMORY.md (e.g., "What's Nate's Discord username?") and confirm the answer comes back correctly via auto-recall.

**Step 2: Move MEMORY.md out of workspace context injection**

OpenClaw injects workspace files listed in the project context. Check how MEMORY.md gets included:

Option A: Rename to `MEMORY.md.bak` (stops injection, preserves file)
Option B: Move to `memory/MEMORY-archive.md` (if workspace only injects root-level files)
Option C: Configure OpenClaw to exclude it (check if there's an excludeFiles config)

Choose the least disruptive option. The file must remain accessible for manual reference but not auto-injected into every prompt.

**Step 3: Verify token reduction**

After restart, check a response's token usage:
- Previous: ~20K total tokens (with ~5.2K from MEMORY.md)
- Expected: ~15-16K total tokens
- Auto-recalled memories should add ~200-500 tokens of relevant context

**Step 4: Quality check**

Have a short conversation testing:
1. General chat (should work normally)
2. Infrastructure question (should recall relevant facts from LanceDB)
3. Personal context question (should recall family info, preferences)

**Step 5: Commit**

```bash
git commit -m "perf: remove MEMORY.md from system prompt, now served via LanceDB auto-recall"
```

---

### Task 5: Verify End-to-End and Tune (Estimated: 20m)

**MDD Context:** Final verification that the full pipeline works — embeddings, storage, retrieval, injection — and tuning parameters for quality.

**Requirements:**
- MUST: Verify auto-recall injects memories in Discord chat
- MUST: Verify auto-recall works through Omni Vox voice hooks
- MUST: Verify auto-capture stores new facts from conversations
- MUST: Verify token savings are realized
- SHOULD: Tune topK and searchThreshold if recall quality is poor

**Step 1: Test Discord conversation**

Have a normal conversation in Discord. Check that:
- Relevant memories appear in context (visible in session transcripts)
- Irrelevant memories are NOT injected
- Response quality is maintained

**Step 2: Test Omni Vox voice**

Send a voice message referencing prior context. Verify the response reflects recalled memories.

**Step 3: Test auto-capture**

Share a new fact in conversation ("My favorite Horus Heresy legion is the Iron Warriors").
Then in a new session, ask about it. If auto-capture worked, the fact should be retrievable.

**Step 4: Check token metrics**

Compare before/after token usage from the session transcripts:
```python
# Check recent assistant messages for token counts
import json
with open("<session_file>") as f:
    for line in f:
        e = json.loads(line)
        if e.get("type") == "message" and e["message"].get("role") == "assistant":
            usage = e["message"].get("usage", {})
            print(f"total: {usage.get('totalTokens')}, cache: {usage.get('cacheRead')}")
```

**Step 5: Tune parameters if needed**

- If too many irrelevant memories: raise `searchThreshold` from 0.3 to 0.5
- If missing relevant memories: lower `searchThreshold` to 0.2, raise `topK` from 5 to 8
- If capture missing facts: raise `captureMaxChars` to 3000

**Step 6: Document final configuration**

Update TOOLS.md and daily memory file with final Mem0/LanceDB configuration details.

**Step 7: Commit**

```bash
git add -A
git commit -m "docs: finalize Mem0 RAG configuration and tuning parameters"
```

---

## Summary of Changes

| Component | Change |
|-----------|--------|
| Ollama | Pull nomic-embed-text embedding model |
| OpenClaw config | Enable memory-lancedb plugin with Ollama embeddings |
| MEMORY.md | Content migrated to LanceDB, file removed from system prompt |
| scripts/ | Migration script for chunking and seeding memories |
| TOOLS.md | Updated with embedding model and LanceDB config |

## What This Does NOT Do (Phase 2)

- **Horus Heresy knowledge base** — Separate RAG collection for rulebooks/lore
- **Cross-channel memory sync** — Discord ↔ Voice memory sharing
- **Memory maintenance UI** — CLI-only for now
- **Automatic memory pruning** — Manual review for now
- **Document RAG** — Different chunking strategy needed for rulebooks (500-token overlapping windows)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Embedding model not on Ollama | Fall back to OpenAI text-embedding-3-small (cloud, but works) |
| LanceDB plugin won't load | memory-core (existing) continues working as fallback |
| Poor recall quality | MEMORY.md backup remains; re-enable if needed |
| Ollama latency spike | nomic-embed-text is tiny (~274MB); cold start <2s |
| LanceDB data loss | Persist to /root/.openclaw/memory/lancedb/ (survives container restarts) |

## Estimated Total Time: ~2 hours

| Task | Time | Description |
|------|------|-------------|
| 1 | 15m | Ollama embedding model setup |
| 2 | 20m | Plugin configuration |
| 3 | 45m | MEMORY.md chunking and migration |
| 4 | 15m | Remove from system prompt |
| 5 | 20m | E2E verification and tuning |
| **Total** | **~115m** | |
