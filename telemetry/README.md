# Telemetry

## GPU Metrics (`gpu-metrics.jsonl`)
Snapshots of GPU health: temp, utilization, VRAM, power draw, active processes.
Collected via `scripts/gpu-telemetry.sh` — run during heartbeats or on-demand.

## LLM Quality Log (`llm-quality.jsonl`)
Quality gate for local model (Qwen) outputs during bake-in period.

Schema:
```json
{
  "ts": "ISO timestamp",
  "task": "briefing|research|summary|heartbeat|other",
  "model": "qwen2.5:32b",
  "duration_s": 12.3,
  "tokens_est": 500,
  "pass": true,
  "issues": [],
  "notes": "optional reviewer notes"
}
```

Issue categories:
- `hallucination` — fabricated facts/sources
- `incomplete` — truncated or missing content
- `incoherent` — garbled or nonsensical text
- `slow` — unreasonable generation time (>60s for simple tasks)
- `format` — wrong structure/format for the task
- `quality` — generally low quality, vague, or unhelpful

## Review Cadence
- First 3 days: review every Qwen output
- Days 4-7: spot-check ~50%
- After week 1: review on failure signals only (unless patterns emerge)
