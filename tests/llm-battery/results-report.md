# Local LLM Competency Battery — Results

**Date:** 2026-02-16
**Model Tested:** Qwen 2.5 32B (Q4_K_M) via Ollama
**Baseline:** Claude (Opus 4.6 / Sonnet 4 judgment)
**Hardware:** RTX 4070 Ti Super, ~5.5 tok/s

---

## Test Results

### #1 — JSON Server Status (Structured Output)
**Time:** 49.5s | **Grade: A**

Qwen produced valid JSON with all required fields, correct types, realistic values. Minor nit: timestamp uses 2023 date (stale training data) and service names are slightly informal ("Plex Media Server" vs "plex"). But structurally perfect, would parse cleanly.

**Verdict:** Fully usable for structured data generation tasks.

---

### #2 — Tech Article Summary (Summarization)
**Time:** 24.8s | **Grade: A**

Three bullet points, all under 30 words, accurate content coverage. Hit all three key themes: adoption, security tradeoff, ongoing debate. Clean and concise. Indistinguishable from what I'd write.

**Verdict:** Excellent at summarization.

---

### #3 — Find the Bugs (Code Review)
**Time:** 145.8s | **Grade: B-**

Found the major issues:
- ✅ Path traversal vulnerability (req.url unsanitized)
- ✅ authenticate() is never called
- ✅ Loose equality (==) for token comparison
- ✅ Missing PORT default
- ❌ Missed: No Content-Type headers on responses (mentioned for errors but not 200s)
- ❌ Missed: Timing-safe comparison needed for auth tokens
- ❌ Missed: server.listen() callback vs console.log race condition
- ❌ Missed: req.url can include query strings, breaking file lookup
- ⚠️ Verbose — rewrote the whole file instead of being surgical about findings

**Verdict:** Catches obvious bugs but misses subtle security issues. Too verbose. Wouldn't trust for security-sensitive review.

---

### #4 — Complex Formatting Task (Instruction Following)
**Time:** 23.1s | **Grade: A**

Hit all 7 requirements: date ✅, Horus Heresy ✅, 2000 points ✅, ⚔️ react ✅, no headers ✅, extra emoji ✅, casual tone ✅. Well under 500 chars. Good energy.

**Verdict:** Nails constrained creative writing.

---

### #5 — Logic Puzzle (Reasoning)
**Time:** 208.9s | **Grade: C**

Took 3.5 minutes and produced a long, rambling chain-of-thought that got cut off before reaching a final answer. The reasoning path was partially correct but meandering, with repeated restarts and conditional branches that didn't resolve. Never delivered a clean answer table.

**Verdict:** Struggles with complex constraint satisfaction. Too slow and inconclusive.

---

### #6 — Styled Email Section (Writing/HTML)
**Time:** 72.1s | **Grade: B**

Produced valid, email-safe HTML with correct inline CSS. Hit all design requirements (dark bg, amber border-left, monospace header, white headlines). However:
- Used placeholder `href="#"` instead of realistic URLs
- News items are generic/boring (Google ethics, Tesla chargers, Microsoft cloud)
- Structurally correct but lacks polish

**Verdict:** Good enough for templating, but needs creative direction for final output.

---

### #7 — Extract Key Facts (Memory Maintenance)
**Time:** 19.3s | **Grade: A**

Excellent extraction. Captured exactly the right items:
- TTS preference (British, bm_george) ✅
- Isabel milestone ✅
- W&G character preference ✅
- CSS lesson ✅
- Briefing preference (no weather) ✅
- Docker deployment lesson ✅

Correctly ignored routine items (telemetry, git, lunch). This is exactly what I'd extract.

**Verdict:** Ideal for memory maintenance tasks.

---

### #8 — Cost Analysis (Reasoning)
**Time:** 138.5s | **Grade: A**

Math is correct:
- Option A: $4.50 input + $4.50 output = $9/month ✅
- Option B: 18kWh inference + 6kWh idle = 24kWh × $0.13 = $3.12/month ✅
- Difference: $5.88/month ✅

Clear step-by-step presentation, well-organized. Correct conclusion.

**Verdict:** Handles arithmetic and structured analysis well.

---

### #9 — Constrained Rewrite (Instruction Following)
**Time:** 137.8s | **Grade: F**

The task required EXACTLY 50 words. Qwen produced 43 words. Spent over 2 minutes and still failed the core constraint. Also wrapped in markdown code fences (not requested).

**Verdict:** Cannot reliably hit exact word counts. This type of precise constraint is beyond it.

---

### #10 — Bash Script (Code Generation)
**Time:** 65.0s | **Grade: B**

Produced a working script that handles all 7 requirements. However:
- Used associative arrays (bash 4+ only, not portable)
- Word counting logic has a subtle bug: files with same word count overwrite in the associative array
- Wrapped in markdown fences despite "ONLY the script" instruction
- Would mostly work but has edge cases

**Verdict:** Usable code generation but not bulletproof. Needs review.

---

### #11 — Meeting Notes Distillation (Summarization)
**Time:** 88.6s | **Grade: B+**

Good structure with all three required sections. Correctly identified:
- 5 decisions (all accurate)
- Action items with owners (combined two Omni items — slightly imprecise)
- Open questions (got all of them)

Minor issues: "Testing on Chris's phone" is an action item, not an open question. Omni's action items should be separate (CSS vs logout button).

**Verdict:** Good enough for meeting notes, minor classification errors.

---

### #12 — Docker Troubleshooting (Multi-Step Reasoning)
**Time:** 151.7s | **Grade: A**

Correctly diagnosed the root cause: `DATABASE_HOST=localhost` means the Node.js container tries to connect to itself, not the postgres container. Explained why `localhost` means something different inside a container. Provided the correct fix: change to `DATABASE_HOST=postgres` (container name). Included verification steps.

Clear, accurate, well-structured explanation.

**Verdict:** Strong at diagnostic reasoning with clear cause-and-effect.

---

## Summary Table

| # | Test | Category | Grade | Time | Usable? |
|---|------|----------|-------|------|---------|
| 1 | JSON Server Status | Structured Output | A | 50s | ✅ Yes |
| 2 | Tech Article Summary | Summarization | A | 25s | ✅ Yes |
| 3 | Find the Bugs | Code Review | B- | 146s | ⚠️ Partial |
| 4 | Complex Formatting | Instruction Following | A | 23s | ✅ Yes |
| 5 | Logic Puzzle | Reasoning | C | 209s | ❌ No |
| 6 | Styled Email Section | Writing/HTML | B | 72s | ⚠️ Partial |
| 7 | Extract Key Facts | Memory Maintenance | A | 19s | ✅ Yes |
| 8 | Cost Analysis | Math/Reasoning | A | 139s | ✅ Yes |
| 9 | Constrained Rewrite | Instruction Following | F | 138s | ❌ No |
| 10 | Bash Script | Code Generation | B | 65s | ⚠️ Partial |
| 11 | Meeting Notes | Summarization | B+ | 89s | ✅ Yes |
| 12 | Docker Troubleshoot | Diagnostic Reasoning | A | 152s | ✅ Yes |

## Grades Distribution
- **A (fully capable):** 6/12 (50%)
- **B range (usable with review):** 4/12 (33%)
- **C or F (not reliable):** 2/12 (17%)

## Speed Analysis
- **Fast tasks (<30s):** Summarization, simple formatting, memory extraction
- **Medium tasks (60-90s):** HTML generation, code generation, meeting notes
- **Slow tasks (>120s):** Code review, reasoning, math analysis, diagnostics
- **Average across all 12:** 95.2 seconds per prompt

## Recommendations

### ✅ Qwen IS good for:
- **Memory maintenance** (extracting key facts, updating notes)
- **Summarization** (article summaries, meeting notes)
- **Structured data generation** (JSON, config files)
- **Simple instruction following** (formatting, constrained creative writing)
- **Straightforward diagnostic reasoning** (Docker, network issues)
- **Math/cost calculations** (when well-structured)

### ❌ Qwen is NOT good for:
- **Multi-step tool use** (morning briefings — confirmed by real failure)
- **Complex constraint satisfaction** (logic puzzles, exact word counts)
- **Security-focused code review** (misses subtle vulnerabilities)
- **Tasks requiring creativity + technical precision** (styled emails that need to be *good*)

### 💡 Suggested Task Routing
Keep Qwen for: GPU telemetry processing, memory maintenance, nightly log summarization, structured data extraction, simple file operations
Move to Claude/Sonnet for: Morning briefings, code review, any task requiring tool orchestration, creative content
