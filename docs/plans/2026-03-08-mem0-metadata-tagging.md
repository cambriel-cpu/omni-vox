# Mem0 Metadata Tagging — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## MDD Documentation

### Goal & Context
**Goal:** Tag every Mem0 memory with structured metadata (`category`, `source`, `scope`) and wire sender identity from Discord through to storage and filtered retrieval, so memories are properly attributed, categorized, and scoped.

**Why:** Without metadata, auto-capture attributes all facts to a single `userId` regardless of who said them or what context they came from. This caused Nate's campaign facts to surface in Chris's conversations. Metadata tagging enables:
- **Category-based retrieval routing** — rules questions pull rules memories, not personal preferences
- **Source tracking** — diagnose bad memories by filtering where they came from
- **Scope isolation** — shared campaign memories vs private personal memories
- **Sender attribution** — prevent cross-user fact leakage

**Success Criteria:**
1. Every stored memory carries `category`, `source`, `scope`, `senderId`, `senderName` metadata
2. Auto-capture tags memories with sender identity from the originating Discord message
3. Auto-recall filters by sender and category appropriate to context
4. Manual `memory_store` accepts optional metadata parameters
5. Filtered search verified: Chris's memories don't leak into Nate's context and vice versa
6. Existing manual seed workflow (`memory_store`) still works with sensible defaults

### Architecture

```
Discord message arrives
        │
        ▼
┌─────────────────────────┐
│  message_received hook  │  ← captures senderId, senderName, channelId
│  stores in sessionMap   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  before_agent_start     │  ← auto-recall with category/scope filters
│  (existing, enhanced)   │
└────────┬────────────────┘
         │
         ▼
    [Agent runs]
         │
         ▼
┌─────────────────────────┐
│  agent_end hook         │  ← auto-capture: looks up sender from sessionMap,
│  (existing, enhanced)   │    tags metadata on stored memories
└─────────────────────────┘
```

### Data Model

**Metadata fields on every Qdrant point payload:**

```typescript
interface MemoryMetadata {
  // --- Mem0 built-in ---
  userId: string;          // "chris" (Mem0's own field)
  data: string;            // The memory text
  hash: string;            // MD5 of memory text
  createdAt: string;       // ISO timestamp

  // --- Our additions ---
  senderId: string;        // Discord user ID: "282277097823666177"
  senderName: string;      // Display name: "Chris", "Nate"
  category: Category;      // Closed taxonomy (see below)
  source: string;          // Open: "discord:#general", "manual", "migration"
  scope: Scope;            // "private" or "shared:<namespace>"
}
```

**Closed taxonomy — `category`:**

| Value | Description | Example |
|-------|-------------|---------|
| `personal` | Facts about people (biographical, family, relationships) | "Chris's daughter Isabel is 21 months old" |
| `preference` | How someone likes things done (communication, tools, settings) | "Chris prefers dark mode" |
| `project` | Infrastructure, technical decisions, ongoing work | "Omni Vox runs on port 7100" |
| `rpg_session` | Campaign narrative, character actions, session events | "Thexis killed 15 raiders in Session 7" |
| `rules` | Game mechanics, rulebook content, authoritative reference | "Salvo attacks cost 2 ammo per shot" |
| `meta` | Facts about Omni, lessons learned, operational patterns | "Never use sed to remove debug code" |

**Closed taxonomy — `scope`:**

| Value | Description |
|-------|-------------|
| `private` | Only returns for this userId (default) |
| `shared:<namespace>` | Returns for anyone querying that namespace (e.g., `shared:campaign_tzeentch`) |

**Open values — `source`:**

Examples: `discord:#general`, `discord:#wrath-and-glory`, `voice`, `manual`, `migration`, `heresy_rules`

### Retrieval Strategy

Auto-recall should route by context:

| Context | Category filter | Scope filter |
|---------|----------------|-------------|
| General chat (#general) | `personal`, `preference`, `project`, `meta` | `private` + `shared:*` for this user |
| RPG session (#wrath-and-glory) | `rpg_session`, `rules` | `shared:campaign_tzeentch` + sender's `private` |
| Voice (Omni Vox) | `personal`, `preference`, `project`, `meta` | `private` |
| Rules question (any channel) | `rules` | any scope |

**Recall filter logic:**
```
WHERE (senderId = currentSender OR senderId IS NULL)
  AND (category IN contextCategories OR category IS NULL)
  AND (scope = "private" OR scope IN user's shared namespaces)
```
This prevents cross-user leakage, routes the right kind of memory to the right context, and keeps shared campaign memories accessible to participants.

### Quality Requirements
**Performance:** Zero additional latency — metadata is stored alongside vectors, filtering adds negligible overhead to Qdrant queries
**Reliability:** If sender lookup fails (e.g., hook message, cron), use sensible defaults (`senderId: "system"`, `category: "meta"`)
**Backward compatibility:** Existing memories without metadata fields still return on unfiltered queries

---

## Task List

### Task 1: Add `message_received` Hook for Sender Tracking (Estimated: 20m)

**MDD Context:** The plugin needs to know who sent each message. OpenClaw fires `message_received` with `event.from` (sender ID) and `ctx.channelId` before the agent runs. We stash this in a Map keyed by session key so `agent_end` can look it up later.

**Requirements:**
- MUST: Register `message_received` hook in the plugin
- MUST: Store `{senderId, senderName, channelId, source}` keyed by a correlatable identifier
- MUST: Handle missing/undefined sender gracefully (default to `"system"`)
- MUST: Clean up stale entries to prevent memory leaks (TTL or max size)
- SHOULD: Use session key if available, fall back to channel ID

**Files:**
- Modify: `/root/.openclaw/extensions/openclaw-mem0/index.ts` — add `message_received` handler, add `senderMap` data structure

**Step 1: Define the sender context type and Map**

```typescript
interface SenderContext {
  senderId: string;
  senderName: string;
  channelId: string;
  source: string;
  timestamp: number;
}

// Map<sessionKey, SenderContext> — TTL cleanup on access
const senderMap = new Map<string, SenderContext>();
const SENDER_MAP_TTL_MS = 30 * 60 * 1000; // 30 minutes
const SENDER_MAP_MAX_SIZE = 100;
```

**Step 2: Register message_received hook**

Inside the plugin's `init` function, after existing hook registrations:

```typescript
api.on("message_received", async (event, ctx) => {
  // Derive a key — prefer session-level correlation
  const key = ctx.conversationId ?? ctx.channelId ?? "unknown";
  
  // Parse sender info from event
  const senderId = event.from ?? "system";
  const senderName = event.metadata?.senderName 
    ?? event.metadata?.username 
    ?? event.from 
    ?? "unknown";
  const channelId = ctx.channelId ?? "unknown";
  
  // Derive source from channel context
  const source = `${channelId}`;
  
  senderMap.set(key, {
    senderId,
    senderName,
    channelId,
    source,
    timestamp: Date.now(),
  });
  
  // Evict stale entries
  if (senderMap.size > SENDER_MAP_MAX_SIZE) {
    const now = Date.now();
    for (const [k, v] of senderMap) {
      if (now - v.timestamp > SENDER_MAP_TTL_MS) senderMap.delete(k);
    }
  }
});
```

**Step 3: Verify hook fires**

Add temporary logging to confirm `message_received` fires and contains sender data:
```typescript
api.logger.info(`openclaw-mem0: message_received from=${event.from} channel=${ctx.channelId}`);
```

Check logs after sending a test message.

**Step 4: Investigate correlation key**

The critical question: how does `message_received`'s context correlate with `agent_end`'s context? Both have `ctx.channelId`. Check if `ctx.conversationId` in `message_received` matches `ctx.sessionKey` in `agent_end`. If not, we need `channelId` as the join key.

⚠️ **This step requires investigation at runtime.** Log both contexts and compare before finalizing the correlation strategy.

**Step 5: Commit**

```bash
git add /root/.openclaw/extensions/openclaw-mem0/index.ts
git commit -m "feat(mem0): add message_received hook for sender identity tracking"
```

---

### Task 2: Enhance Auto-Capture with Metadata Tagging (Estimated: 25m)

**MDD Context:** The `agent_end` hook currently calls `provider.add()` with only `userId` and `sessionId`. We need to look up the sender from the `senderMap` and pass `category`, `source`, `scope`, `senderId`, `senderName` as metadata.

**Requirements:**
- MUST: Look up sender context from `senderMap` using the correlation key
- MUST: Pass `senderId`, `senderName`, `source` as metadata to `provider.add()`
- MUST: Default `category` to `"meta"` (Flash will eventually classify, but defaults first)
- MUST: Default `scope` to `"private"`
- MUST: Handle lookup failure gracefully (use system defaults)
- SHOULD: Include category classification in the extraction prompt via `customInstructions`

**Files:**
- Modify: `/root/.openclaw/extensions/openclaw-mem0/index.ts` — enhance `agent_end` hook

**Step 1: Modify the agent_end hook**

In the existing `agent_end` handler, after formatting messages and before calling `provider.add()`:

```typescript
// Look up sender context
const correlationKey = ctx.sessionKey ?? ctx.channelId ?? "unknown";
// Try multiple key formats since message_received and agent_end may use different keys
const senderCtx = senderMap.get(correlationKey) 
  ?? senderMap.get(ctx.channelId ?? "")
  ?? { senderId: "system", senderName: "system", channelId: "unknown", source: "unknown" };

const metadata = {
  senderId: senderCtx.senderId,
  senderName: senderCtx.senderName,
  source: senderCtx.source,
  category: "meta",  // Default; Phase 2 adds LLM classification
  scope: "private",  // Default; shared scope requires explicit tagging
};
```

**Step 2: Pass metadata through provider.add()**

The `OSSProvider.add()` method in the plugin currently calls:
```typescript
const result = await this.memory.add(messages, addOpts);
```

Modify `buildAddOptions()` or the call site to include metadata:
```typescript
const addOpts = {
  ...buildAddOptions(undefined, currentSessionId),
  metadata,
};
```

Verify that the `OSSProvider.add()` method passes `metadata` through to `this.memory.add()`. Check the current implementation:

```typescript
async add(messages, options) {
  // ... 
  const addOpts = { userId: options.user_id };
  // Need to also pass: metadata: options.metadata
}
```

If the plugin's `OSSProvider.add()` doesn't forward metadata, add it.

**Step 3: Update customInstructions for category classification**

Enhance the `customInstructions` config to include category guidance:

```
"...existing instructions...

When extracting facts, classify each into exactly one category:
- personal: facts about people (biographical, family, relationships)
- preference: how someone likes things done (tools, settings, communication style)
- project: infrastructure, technical decisions, ongoing work
- rpg_session: campaign narrative, character actions, game session events
- rules: game mechanics, rulebook content
- meta: facts about Omni, lessons learned, operational patterns"
```

Note: The category from `customInstructions` affects the *extracted text* but not the metadata field directly. To get category into metadata, we would need to parse Flash's output or add a structured extraction step. **For Phase 1, default to "meta" and revisit in Phase 2.**

**Step 4: Test auto-capture with metadata**

Re-enable auto-capture temporarily, send a test message, then verify the stored memory has metadata:

```bash
curl -s http://192.168.68.51:6333/collections/omni-memories/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 5, "with_payload": true}' | python3 -m json.tool
```

Check that `senderId`, `senderName`, `source`, `category`, `scope` are present in the payload.

**Step 5: Commit**

```bash
git commit -m "feat(mem0): tag auto-captured memories with sender and metadata"
```

---

### Task 3: Enhance Auto-Recall with Sender Filtering (Estimated: 20m)

**MDD Context:** The `before_agent_start` hook currently searches all memories for `userId: "chris"` with no sender filtering. We need to filter results so only the current speaker's memories (plus universal/untagged memories) are injected.

**Requirements:**
- MUST: Look up current sender from `senderMap`
- MUST: Filter recalled memories by sender: `senderId = currentSender OR senderId IS NULL`
- MUST: Filter recalled memories by category based on context (see routing table)
- MUST: Filter recalled memories by scope: `scope = "private" OR scope IN user's shared namespaces`
- MUST: Include untagged memories (from manual seeding / migration) that have no metadata fields
- MUST: Not break recall when sender is unknown (fall back to unfiltered)
- SHOULD: Log which filters were applied

**Files:**
- Modify: `/root/.openclaw/extensions/openclaw-mem0/index.ts` — enhance `before_agent_start` hook

**Step 1: Look up sender in before_agent_start**

```typescript
const correlationKey = ctx.sessionKey ?? ctx.channelId ?? "unknown";
const senderCtx = senderMap.get(correlationKey) 
  ?? senderMap.get(ctx.channelId ?? "");
```

**Step 2: Apply sender filter to search**

Option A — Qdrant native filter (preferred, most efficient):

Pass `senderId` as a filter to `provider.search()`, which flows through to Qdrant's `createFilter()`:

```typescript
const searchFilters = senderCtx 
  ? { senderId: senderCtx.senderId }
  : undefined;

const longTermResults = await provider.search(
  event.prompt,
  buildSearchOptions(searchFilters),
);
```

**Problem:** This would EXCLUDE untagged memories (those without `senderId`). We need an OR condition: `senderId = X OR senderId IS NULL`.

Option B — Post-filter in plugin (simpler, handles the OR conditions):

Search without metadata filters, then filter results in the plugin:

```typescript
const allResults = await provider.search(event.prompt, buildSearchOptions());

// Determine context-appropriate categories based on channel/session
const contextCategories = deriveContextCategories(senderCtx?.channelId);
// e.g., #general → ["personal", "preference", "project", "meta"]
// e.g., #wrath-and-glory → ["rpg_session", "rules"]

const filteredResults = allResults.filter(r => {
  const meta = r.metadata ?? {};
  
  // Sender filter: this sender's memories + untagged universals
  const senderOk = !meta.senderId 
    || !senderCtx 
    || meta.senderId === senderCtx.senderId;
  
  // Category filter: context-appropriate categories + untagged
  const categoryOk = !meta.category 
    || contextCategories.includes(meta.category);
  
  // Scope filter: private + user's shared namespaces + untagged
  const scopeOk = !meta.scope 
    || meta.scope === "private" 
    || userSharedNamespaces.includes(meta.scope);
  
  return senderOk && categoryOk && scopeOk;
});
```

**Recommendation:** Option B. It handles all three OR conditions cleanly, and the performance cost is negligible (filtering 5-20 results in memory). Move to Qdrant-native filtering if we scale to thousands of memories.

**Channel → Category routing helper:**

```typescript
function deriveContextCategories(channelId?: string): string[] {
  // Channel-specific routing
  const channelMap: Record<string, string[]> = {
    "discord:#wrath-and-glory": ["rpg_session", "rules", "personal"],
    "discord:#servo-skull": ["project", "rules"],
  };
  
  // Default for general chat and voice
  return channelMap[channelId ?? ""] 
    ?? ["personal", "preference", "project", "meta"];
}
```

**Step 3: Update the memory injection format**

Optionally include sender context in the injected block so I know whose memories I'm seeing:

```typescript
const memoryContext = filteredResults
  .map(r => {
    const sender = r.metadata?.senderName ? ` (from ${r.metadata.senderName})` : '';
    return `- ${r.memory}${sender}`;
  })
  .join("\n");
```

**Step 4: Test filtered recall**

1. Store a memory tagged with Chris's senderId
2. Store a memory tagged with Nate's senderId
3. Send a message as Chris → verify only Chris's + untagged memories appear
4. Verify Nate's memories don't leak through

**Step 5: Commit**

```bash
git commit -m "feat(mem0): filter auto-recall by sender identity"
```

---

### Task 4: Enhance memory_store Tool with Metadata Parameters (Estimated: 15m)

**MDD Context:** The `memory_store` tool is used for manual seeding (MEMORY.md migration) and explicit memory storage. It should accept optional `category`, `source`, and `scope` parameters with sensible defaults.

**Requirements:**
- MUST: Add optional `category`, `source`, `scope` parameters to `memory_store` tool schema
- MUST: Default `category` to `"personal"`, `source` to `"manual"`, `scope` to `"private"`
- MUST: Validate `category` against closed taxonomy
- MUST: Validate `scope` format (`"private"` or `"shared:<namespace>"`)
- MUST: Pass metadata through to `provider.add()`
- SHOULD: When called from main session, auto-set `senderId` to Chris's ID

**Files:**
- Modify: `/root/.openclaw/extensions/openclaw-mem0/index.ts` — update `memory_store` tool registration

**Step 1: Update tool parameter schema**

```typescript
parameters: Type.Object({
  text: Type.String({ description: "Information to remember" }),
  category: Type.Optional(Type.Union([
    Type.Literal("personal"),
    Type.Literal("preference"),
    Type.Literal("project"),
    Type.Literal("rpg_session"),
    Type.Literal("rules"),
    Type.Literal("meta"),
  ], { description: "Memory category. Default: personal" })),
  source: Type.Optional(Type.String({ 
    description: "Where this memory originated. Default: manual" 
  })),
  scope: Type.Optional(Type.String({ 
    description: 'Memory scope: "private" (default) or "shared:<namespace>"' 
  })),
}),
```

**Step 2: Build metadata in execute handler**

```typescript
const metadata = {
  senderId: cfg.userId === "chris" ? "282277097823666177" : "system",
  senderName: cfg.userId === "chris" ? "Chris" : "system",
  category: params.category ?? "personal",
  source: params.source ?? "manual",
  scope: params.scope ?? "private",
};
```

**Step 3: Pass metadata to provider.add()**

Ensure the `add()` call includes the metadata object.

**Step 4: Test manual storage with metadata**

```
memory_store "Chris's favorite color is blue" category=preference source=manual scope=private
```

Verify in Qdrant that the payload contains all metadata fields.

**Step 5: Commit**

```bash
git commit -m "feat(mem0): add category/source/scope parameters to memory_store tool"
```

---

### Task 5: Investigate Hook Correlation and End-to-End Test (Estimated: 25m)

**MDD Context:** The critical unknown is whether `message_received` and `agent_end` share a correlatable key. This task investigates at runtime and validates the full pipeline.

**Requirements:**
- MUST: Determine the correct correlation key between hooks
- MUST: Verify sender identity flows from Discord → message_received → senderMap → agent_end → Qdrant
- MUST: Verify auto-recall filters correctly by sender
- MUST: Document the correlation mechanism for future reference

**Step 1: Add diagnostic logging to both hooks**

```typescript
// In message_received:
api.logger.info(`mem0:msg_received from=${event.from} channel=${ctx.channelId} conv=${ctx.conversationId}`);

// In agent_end:
api.logger.info(`mem0:agent_end session=${ctx.sessionKey} channel=${ctx.channelId}`);
```

**Step 2: Send a test message and check logs**

```bash
openclaw logs | grep "mem0:"
```

Compare the keys. If `ctx.conversationId` in `message_received` matches part of `ctx.sessionKey` in `agent_end`, that's our join key. If not, `ctx.channelId` is the fallback.

**Step 3: Adjust correlation key based on findings**

Update the `senderMap` key strategy in both hooks to use the discovered correlation.

**Step 4: Full pipeline test**

1. Enable auto-capture temporarily
2. Send a message as Chris in #general
3. Verify stored memory has correct metadata:
   ```bash
   curl -s http://192.168.68.51:6333/collections/omni-memories/points/scroll \
     -H "Content-Type: application/json" \
     -d '{"limit": 5, "with_payload": true}'
   ```
4. Send another message → verify auto-recall injects only Chris's memories
5. Verify no Nate-attributed memories appear

**Step 5: Document correlation mechanism**

Add a comment block in the plugin explaining the hook correlation strategy.

**Step 6: Commit**

```bash
git commit -m "feat(mem0): verify hook correlation and end-to-end metadata flow"
```

---

### Task 6: Re-seed MEMORY.md with Metadata (Estimated: 30m)

**MDD Context:** With metadata support working, re-seed MEMORY.md into a clean Qdrant collection. Each fact gets proper `category`, `source: "migration"`, `scope: "private"`, and `senderId` for Chris.

**Requirements:**
- MUST: Wipe the existing collection (fresh start)
- MUST: Tag each memory with appropriate `category` from the closed taxonomy
- MUST: Set `source: "migration"` and `scope: "private"` for all migrated memories
- MUST: Set `senderId: "282277097823666177"` (Chris) for all Chris-related facts
- MUST: Verify retrieval with the 10-question regression test
- MUST: Store 80-150 atomic facts covering all MEMORY.md content

**Step 1: Wipe collection**

```bash
curl -s -X DELETE http://192.168.68.51:6333/collections/omni-memories
```

**Step 2: Seed facts using memory_store with metadata**

Group facts by category and store systematically:

```
# Personal facts
memory_store "Chris Langston is a Director of UX Research at Meta" category=personal source=migration
memory_store "Chris's wife is named Ashley" category=personal source=migration
memory_store "Chris's daughter Isabel was born around May 2024" category=personal source=migration
...

# Preference facts
memory_store "Chris prefers friendly coworker energy, not condescending" category=preference source=migration
memory_store "Morning briefings should include tech news, AI, hobby news, with source links" category=preference source=migration
...

# Project facts
memory_store "Omni Vox runs as Docker container omni-vox:v2.5.8 on port 7100" category=project source=migration
memory_store "Qdrant runs on port 6333 at 192.168.68.51" category=project source=migration
...

# Meta facts
memory_store "Never use sed to remove debug code — use precise manual edits" category=meta source=migration
memory_store "Qwen 2.5 32B is unreliable for tool-use automation" category=meta source=migration
...
```

**Step 3: Run 10-question regression test**

| # | Question | Expected Category | Expected Answer |
|---|----------|------------------|-----------------|
| 1 | What is Chris's job title? | personal | Director of UX Research at Meta |
| 2 | What's the servo-skull's Tailscale IP? | project | 100.69.9.99 |
| 3 | What voice does Omni use for TTS? | project | bm_george via Kokoro |
| 4 | Who is Nate? | personal | Beta tester, Discord natecro_magnon |
| 5 | What's the Omni Vox container port? | project | 7100 |
| 6 | Why were heartbeats disabled? | meta | Qwen unreliable at tool-use cron tasks |
| 7 | What's Chris's daughter's name? | personal | Isabel |
| 8 | What GPU does the Omnissiah have? | project | RTX 4070 Ti Super (16GB VRAM) |
| 9 | What wake word does the servo-skull use? | project | "Hey Jarvis" |
| 10 | Why did we choose host networking for Omni Vox? | meta | Eliminates macvlan shim dependencies |

All 10 must pass.

**Step 4: Commit**

```bash
git commit -m "feat(mem0): seed MEMORY.md with categorized metadata"
```

---

## Summary of Changes

| Component | Change |
|-----------|--------|
| Plugin `index.ts` | Add `message_received` hook for sender tracking |
| Plugin `index.ts` | Enhance `agent_end` to tag metadata on captured memories |
| Plugin `index.ts` | Enhance `before_agent_start` to filter recall by sender |
| Plugin `index.ts` | Add `category`/`source`/`scope` params to `memory_store` tool |
| Qdrant payloads | New fields: `senderId`, `senderName`, `category`, `source`, `scope` |
| OpenClaw config | Updated `customInstructions` with category taxonomy |
| Qdrant collection | Re-seeded with categorized, metadata-tagged memories |

## What This Does NOT Do (Future)

- **LLM-driven category classification during auto-capture** — Auto-capture defaults category to `"meta"`; structured extraction with Flash parsing category from its output is a follow-up
- **Qdrant-native OR filters** — Post-filters in plugin for now; move to Qdrant `should` conditions if we scale to thousands of memories
- **MEMORY.md removal from system prompt** — Keep it until regression test passes and we're confident in retrieval quality

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Hook correlation key mismatch | Medium | High | Task 5 investigates at runtime; fallback to channelId |
| Metadata not passed through Mem0 SDK | Low | High | Already verified in testing — metadata flows to Qdrant |
| `message_received` hook not available | Low | High | Confirmed in plugin SDK types; tested via logs |
| NaN embedding errors on certain content | Medium | Medium | Already observed; skip and retry, or use shorter text |
| Sender lookup miss on hook/cron messages | Medium | Low | Default to `senderId: "system"`, `category: "meta"` |

## Estimated Total Time: ~2.5 hours

| Task | Time | Description |
|------|------|-------------|
| 1 | 20m | `message_received` hook for sender tracking |
| 2 | 25m | Auto-capture metadata tagging |
| 3 | 20m | Auto-recall sender filtering |
| 4 | 15m | `memory_store` tool metadata params |
| 5 | 25m | Hook correlation investigation + E2E test |
| 6 | 30m | Re-seed MEMORY.md with metadata |
| **Total** | **~135m** | |
