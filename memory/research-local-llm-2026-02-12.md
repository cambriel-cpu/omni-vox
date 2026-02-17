# Local LLM Research — Unraid Server Setup

**Date:** 2026-02-12  
**Hardware:** AMD Ryzen 9 9950X · 64GB RAM · NVIDIA RTX 4070 Ti Super (16GB VRAM)  
**Existing workload:** faster-whisper container using ~2–3GB VRAM

---

## 1. VRAM Budget

| Component | VRAM Usage |
|-----------|-----------|
| faster-whisper | ~2–3 GB |
| CUDA overhead / OS | ~0.5–1 GB |
| **Available for LLM** | **~12–13 GB** |

**Key insight:** With ~12–13GB free VRAM, you can comfortably run a 14B model at Q4_K_M quantization (~9 GB model weights), leaving headroom for KV cache (context window). At Q5_K_M (~10.5 GB) it's tighter but still workable with shorter contexts.

**Can they coexist?** Yes — Ollama loads models on demand and can unload them when idle (configurable via `OLLAMA_KEEP_ALIVE`). Whisper is bursty (only uses VRAM during transcription), so in practice they share well. Set `OLLAMA_KEEP_ALIVE=5m` so the LLM unloads after 5 minutes of inactivity, freeing VRAM for Whisper bursts.

---

## 2. Ollama Setup on Unraid

### Installation

Ollama is available in the Unraid Community Applications store. Search "Ollama" and install from there, or deploy manually:

```yaml
# Docker run equivalent
docker run -d \
  --name ollama \
  --gpus all \
  --restart always \
  -p 11434:11434 \
  -v /mnt/user/appdata/ollama:/root/.ollama \
  -e OLLAMA_KEEP_ALIVE=5m \
  ollama/ollama
```

### GPU Passthrough

- Install the **NVIDIA Driver** plugin from Community Applications (if not already installed for Whisper)
- In the Ollama container settings, set **Extra Parameters:** `--gpus all`
- Alternatively, pass a specific GPU UUID if you want more control: `--gpus "device=GPU-xxxxx"`
- The NVIDIA Container Toolkit must be working (it should be if Whisper already uses GPU)

### Persistent Model Storage

- Map `/root/.ollama` to a persistent Unraid path like `/mnt/user/appdata/ollama`
- Models are large (9–15 GB each) — make sure the target share has enough space
- Models survive container rebuilds/updates this way

### Pull Your First Model

```bash
docker exec -it ollama ollama pull qwen2.5:14b-instruct-q4_K_M
```

### Verify GPU is Working

```bash
docker exec -it ollama ollama run qwen2.5:14b-instruct-q4_K_M "Hello"
# Check nvidia-smi to confirm VRAM usage
nvidia-smi
```

**Common Unraid gotcha:** If GPU isn't detected, ensure the container has `--runtime=nvidia` or `--gpus all` in Extra Parameters. Some Unraid templates miss this.

---

## 3. Qwen2.5-14B — Quantization & Performance

### Quantization Recommendations

Based on community benchmarks (MMLU-Pro Computer Science):

| Quantization | Model Size | MMLU-Pro CS Score | Fits in ~13GB VRAM? |
|-------------|-----------|-------------------|---------------------|
| **Q4_K_M** ⭐ | **~9 GB** | **64.15** | **✅ Best choice — room for context** |
| Q5_K_M | ~10.5 GB | 66.83 | ⚠️ Tight, shorter context only |
| Q5_K_S | ~10.3 GB | 65.12 | ⚠️ Similar to Q5_K_M |
| Q3_K_L | ~7.9 GB | 64.15 | ✅ Max context, slight quality drop |

**Recommendation: Q4_K_M** — best balance of quality and VRAM. Only ~2 points below Q8 (full precision is 66.83), and leaves ~4GB for KV cache (enough for ~8K–16K context comfortably).

### Expected Performance on RTX 4070 Ti Super

- **Generation speed:** ~20–30 tokens/sec at Q4_K_M (very usable, feels responsive)
- **Prompt processing:** ~200+ tokens/sec
- **Context window:** Model supports 128K natively, but with 13GB VRAM budget you'll realistically get 8K–16K context before hitting memory limits. For most tasks that's plenty.

### Qwen2.5 vs Qwen3-14B?

Qwen3-14B exists and has improved reasoning. Same VRAM profile. **If available in Ollama, prefer Qwen3-14B** — it's a strict upgrade with hybrid thinking/non-thinking modes. Check:

```bash
ollama pull qwen3:14b
```

---

## 4. OpenClaw Integration

OpenClaw has **built-in Ollama support** with auto-discovery. Here's how to set it up:

### Option A: Auto-Discovery (Simplest)

Since Ollama will be on the same Unraid server (not localhost from OpenClaw's perspective), use explicit config:

### Option B: Explicit Config (Recommended for Network Ollama)

Add to your `openclaw.json` (or via `openclaw config`):

```json5
{
  // Set the Ollama env var
  env: {
    OLLAMA_API_KEY: "ollama-local"
  },
  
  agents: {
    defaults: {
      // Keep Claude as primary, Ollama as fallback — or vice versa
      model: { 
        primary: "anthropic/claude-opus-4-6",  // Smart tasks
      },
    },
  },
  
  // If Ollama is on a different host/IP than the OpenClaw container:
  models: {
    providers: {
      ollama: {
        baseUrl: "http://<UNRAID-IP>:11434/v1",
        apiKey: "ollama-local",
        api: "openai-completions",
        models: [
          {
            id: "qwen2.5:14b-instruct-q4_K_M",
            name: "Qwen 2.5 14B (Local)",
            reasoning: false,
            input: ["text"],
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            contextWindow: 16384,
            maxTokens: 8192
          }
        ]
      }
    }
  }
}
```

### Switching Models in Chat

Once configured, switch on the fly:

```
/model ollama/qwen2.5:14b-instruct-q4_K_M    # Use local
/model anthropic/claude-opus-4-6               # Use cloud
```

### If OpenClaw runs on the SAME Unraid box

If the OpenClaw container and Ollama container are on the same Unraid host, use the Docker network IP or host networking:
- With `--network=host` on both: use `http://127.0.0.1:11434/v1`
- Otherwise: use `http://<ollama-container-ip>:11434/v1` or create a custom Docker network

---

## 5. Local vs Cloud — When to Use Each

### Route to LOCAL LLM (Ollama/Qwen) — "Fast & Free"

- ✅ Quick Q&A, definitions, simple lookups
- ✅ Summarizing short text
- ✅ Writing drafts, brainstorming
- ✅ Code snippets and simple refactors
- ✅ Formatting, translation, text transformation
- ✅ Heartbeat/cron tasks that don't need deep reasoning
- ✅ High-volume, low-stakes tasks
- ✅ Privacy-sensitive content you don't want leaving your network

### Route to CLOUD (Claude) — "Smart & Expensive"

- 🧠 Complex multi-step reasoning
- 🧠 Long-context analysis (>16K tokens)
- 🧠 Nuanced writing that needs to be really good
- 🧠 Complex coding tasks, architecture decisions
- 🧠 Tasks requiring tool use chains (browsing, multi-tool workflows)
- 🧠 Anything where quality really matters

### Practical Setup

You could configure Ollama as the default for subagents/cron and keep Claude for main conversations:

```json5
{
  agents: {
    defaults: {
      model: { primary: "anthropic/claude-opus-4-6" }
    },
    // In cron jobs, specify the local model
  }
}
```

Or use `/model` to switch manually when you want to save money on a simple task.

---

## 6. Alternative Models Comparison

With ~12–13GB available VRAM:

| Model | Size (Q4_K_M) | Strengths | Weaknesses | Verdict |
|-------|--------------|-----------|------------|---------|
| **Qwen3-14B** ⭐ | ~9 GB | Best overall 14B, reasoning, coding, multilingual | Newer, less battle-tested | **Top pick if available** |
| **Qwen2.5-14B** | ~9 GB | Excellent coding, well-tested, great benchmarks | Slightly weaker reasoning than Qwen3 | **Safe pick** |
| Gemma 3 12B | ~7.5 GB | Google quality, good at instruction following | Smaller param count | Good alternative |
| Phi-4 14B | ~9 GB | Microsoft, strong reasoning for size | Less community tooling | Worth trying |
| DeepSeek-R1-Distill-Qwen-14B | ~9 GB | Reasoning/chain-of-thought specialist | Slower (generates thinking tokens), narrower | Good for math/logic |
| Mistral Small 24B | ~14 GB | Larger = smarter, multilingual | Barely fits, no context headroom | ⚠️ Too tight |
| Llama 3.3 8B | ~5 GB | Tiny, fast, Meta quality | Noticeably weaker than 14B class | Only if speed > quality |
| GLM-4 9B | ~6 GB | Good tool calling, coding | Smaller than 14B class | Decent for tool use |

### Recommendation

1. **Primary pick: Qwen3-14B at Q4_K_M** — best quality-per-VRAM in the 14B class
2. **Fallback: Qwen2.5-14B at Q4_K_M** — proven, well-supported in Ollama
3. **Also install: a small fast model** like `qwen2.5:7b` for ultra-quick tasks

---

## 7. Summary & Action Plan

1. **Install Ollama** from Unraid Community Apps with `--gpus all` and persistent storage
2. **Pull Qwen3-14B** (or Qwen2.5-14B) at Q4_K_M quantization
3. **Set `OLLAMA_KEEP_ALIVE=5m`** so it plays nice with Whisper's VRAM needs
4. **Configure OpenClaw** with explicit Ollama provider pointing to the Unraid host
5. **Use Claude for complex tasks**, local LLM for quick/cheap/private tasks
6. **Monitor VRAM** with `nvidia-smi` to verify coexistence works smoothly

**Estimated cost savings:** Every task routed to local = $0 instead of API costs. For high-volume tasks (cron, heartbeats, simple queries), this adds up fast.
