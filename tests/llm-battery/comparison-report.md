# LLM Competency Battery — Three-Way Comparison

**Date:** 2026-02-16
**Models:** Qwen 2.5 32B (local) vs Claude Sonnet 4 vs Claude Haiku 4
**Hardware:** Qwen on RTX 4070 Ti Super (~5.5 tok/s) | Claude models via API

---

## Scoring Key
- **A** = Excellent, fully correct, well-formatted
- **B** = Good, minor issues, usable
- **C** = Mediocre, significant gaps
- **F** = Failed the task

---

## Test-by-Test Results

### #1 — JSON Server Status (Structured Output)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | Valid JSON, all fields correct, realistic values. Used 2023 timestamp (stale). |
| **Sonnet** | A | Valid JSON, added extra services (nginx, postgres, redis). More realistic. |
| **Haiku** | A | Valid JSON, clean and minimal. All fields correct. |

**Winner:** Tie — all three produced valid, usable JSON.

---

### #2 — Tech Article Summary (Summarization)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | 3 bullets, all under 30 words, accurate coverage. |
| **Sonnet** | A | 3 bullets, all under 30 words, slightly better structure. |
| **Haiku** | A | 3 bullets, all under 30 words, clean and precise. |

**Winner:** Tie — all three nailed it.

---

### #3 — Find the Bugs (Code Review)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | B- | Found path traversal, unused auth, loose equality, missing PORT default. Missed timing-safe comparison, query string issue. Verbose, rewrote the whole file. |
| **Sonnet** | A- | Found path traversal, loose equality, unused auth, missing Content-Type, PORT validation. Provided corrected code. Missed timing-safe comparison. |
| **Haiku** | A | Found path traversal, loose equality AND timing attack, unused auth, Content-Type, PORT issue, `listen` callback race. Most thorough of all three. |

**Winner:** Haiku — only model to catch the timing attack vulnerability.

---

### #4 — Complex Formatting Task (Instruction Following)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | All 7 requirements met. Good energy. |
| **Sonnet** | A | All 7 requirements met. Used bold formatting effectively. |
| **Haiku** | A | All 7 requirements met. Most natural tone. |

**Winner:** Tie — all met every constraint.

---

### #5 — Logic Puzzle (Reasoning)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | C | Rambling, 3.5 minutes, never reached a clean final answer. Got lost in conditional branches. |
| **Sonnet** | A | Correct answer. Clean step-by-step. Position 1: Plex (64GB), 2: Nextcloud (32GB), 3: HomeAssistant (16GB), 4: PiHole (8GB), 5: Ollama (128GB). |
| **Haiku** | A- | Correct answer (same as Sonnet, with note that positions 1/3 RAM could swap). Slightly verbose with backtracking. |

**Correct answer verification:**
- Plex (1) directly above Nextcloud (2) ✅
- 128GB in position 5 ✅
- Ollama (5, 128GB) has more RAM than all above ✅
- PiHole (4, 8GB) not in position 5 ✅
- HomeAssistant in position 3 ✅
- Position 2 has 32GB ✅

Note: Positions 1 and 3 RAM (16GB/64GB) can swap and still satisfy all constraints. Both Sonnet and Haiku acknowledged this.

**Winner:** Sonnet — clean, correct, efficient.

---

### #6 — Styled Email Section (Writing/HTML)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | B | Valid HTML, correct colors/fonts. But used `href="#"` placeholder links and generic news. Basic structure. |
| **Sonnet** | A | Better HTML structure, proper sizing, realistic news items with named sources. More polished inline CSS. |
| **Haiku** | A | Clean, well-structured, good spacing. Realistic news items. Slightly better readability. |

**Winner:** Sonnet/Haiku tied — both significantly better than Qwen's placeholder approach.

---

### #7 — Extract Key Facts (Memory Maintenance)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | 6 key facts, all correct, correctly ignored routine items. Concise. |
| **Sonnet** | A | 6 key facts with bold labels. Included Mechanicus lore discussion (debatable value). |
| **Haiku** | A+ | 7 key facts, best formatting, included emoji for Isabel's milestone. Most thorough while staying concise. |

**Winner:** Haiku by a hair — best formatting and completeness.

---

### #8 — Cost Analysis (Reasoning/Math)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | Correct math ($9 vs $3.12, $5.88 savings). Very detailed step-by-step. |
| **Sonnet** | A+ | Same correct math, plus added annual projection ($70.56 savings). More concise presentation. |
| **Haiku** | A+ | Same correct math, plus added GPU ROI analysis (136 months payback). Best real-world context. |

**Winner:** Haiku — added genuinely useful ROI context that the others missed.

---

### #9 — Constrained Rewrite (Exactly 50 Words)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | F | Produced 39 words. Failed the core constraint by 22%. |
| **Sonnet** | C | Produced 46 words. Close but still failed. |
| **Haiku** | C | Produced 46 words. Same miss as Sonnet. |

**Winner:** None — all failed. This is genuinely hard for LLMs. But Sonnet/Haiku were much closer (46 vs 39).

---

### #10 — Bash Script (Code Generation)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | B | Works but uses associative arrays (bash 4+ only). Bug: files with same word count overwrite. Wrapped in code fences despite instruction not to. |
| **Sonnet** | B+ | Cleaner approach with while loop. Has a bug: sort happens after print (piping issue). No code fences but includes non-shebang header. |
| **Haiku** | A- | Cleanest approach. Proper while/read loop, formatted output, separator line. Most portable. Same sort-pipe issue as Sonnet. |

**Winner:** Haiku — cleanest, most portable, best formatted output.

---

### #11 — Meeting Notes Distillation (Summarization)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | B+ | Good structure. Combined Omni's two action items. Misclassified phone testing as open question. |
| **Sonnet** | A | Clean separation. All items correctly classified. Included phone testing as joint action item. |
| **Haiku** | A | Same quality as Sonnet. Clean formatting, correct classification. |

**Winner:** Sonnet/Haiku tied.

---

### #12 — Docker Troubleshooting (Diagnostic Reasoning)

| Model | Grade | Notes |
|-------|-------|-------|
| **Qwen** | A | Correct diagnosis (localhost = container self, use container name). Clear explanation. Verification steps. |
| **Sonnet** | A | Same correct diagnosis. More concise. Added alternative solutions. |
| **Haiku** | A+ | Same correct diagnosis. Best explanation of WHY `pg_isready` succeeds (runs inside postgres container). Most thorough root cause analysis. |

**Winner:** Haiku — best explanation of the subtle "why" behind the symptoms.

---

## Summary Scorecard

| Test | Category | Qwen | Sonnet | Haiku |
|------|----------|------|--------|-------|
| #1 JSON Output | Structured Output | A | A | A |
| #2 Article Summary | Summarization | A | A | A |
| #3 Code Review | Code Review | B- | A- | **A** |
| #4 Discord Message | Instruction Following | A | A | A |
| #5 Logic Puzzle | Reasoning | C | **A** | A- |
| #6 Email HTML | Writing/HTML | B | A | A |
| #7 Key Facts | Memory Maintenance | A | A | **A+** |
| #8 Cost Analysis | Math/Reasoning | A | A+ | **A+** |
| #9 50-Word Rewrite | Exact Constraints | F | C | C |
| #10 Bash Script | Code Generation | B | B+ | **A-** |
| #11 Meeting Notes | Summarization | B+ | A | A |
| #12 Docker Diagnosis | Diagnostic Reasoning | A | A | **A+** |

### Grade Point Averages (A+=4.3, A=4, A-=3.7, B+=3.3, B=3, B-=2.7, C=2, F=0)

- **Haiku: 3.58** (strongest overall)
- **Sonnet: 3.56** (nearly identical to Haiku)
- **Qwen: 2.81** (clearly behind on harder tasks)

---

## Speed Comparison

| Model | Total Time (12 prompts) | Avg per Prompt |
|-------|------------------------|----------------|
| **Qwen** | ~18 minutes | 95 seconds |
| **Sonnet** | ~1.5 minutes | ~8 seconds |
| **Haiku** | ~1.5 minutes | ~8 seconds |

Qwen is **12x slower** than either Claude model.

---

## Key Findings

### Where Qwen matches Claude (A grades on both):
1. ✅ Structured JSON output
2. ✅ Basic summarization
3. ✅ Simple instruction following
4. ✅ Straightforward diagnostic reasoning
5. ✅ Math calculations

### Where Qwen falls behind:
1. ❌ Complex reasoning/logic puzzles (C vs A)
2. ❌ Code review depth (misses security subtleties)
3. ❌ Creative/polished output (placeholder links, generic content)
4. ❌ Exact constraint following (word counts)
5. ❌ Speed (12x slower)

### Surprise: Haiku outperformed Sonnet
Haiku edged out Sonnet on several tasks (code review, cost analysis context, Docker explanation). For the cost difference, Haiku is remarkable value.

---

## Recommendations

### Keep Qwen for:
- GPU telemetry processing (structured data extraction)
- Memory maintenance / fact extraction
- Simple summarization of logs
- Structured output generation (JSON, YAML)
- Basic math / calculations

### Use Sonnet for:
- Morning briefings (multi-step tool use + creativity)
- Code review and generation
- Complex reasoning tasks
- Any task requiring polished output

### Consider Haiku for:
- Code review (caught timing attack that Sonnet missed!)
- Diagnostic reasoning (best explanations)
- Cost-sensitive tasks where Sonnet quality isn't needed
- Could potentially replace some Qwen tasks if API costs are acceptable

### Task Routing Strategy:
```
Simple/structured → Qwen (free, good enough)
Complex/creative → Sonnet (reliable, fast)
Security review  → Haiku (surprisingly thorough)
Primary chat     → Opus (current, stays)
```
