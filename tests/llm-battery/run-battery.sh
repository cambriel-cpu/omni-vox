#!/bin/bash
cd /root/.openclaw/workspace/tests/llm-battery

# Read prompts and run each one
python3 << 'PYEOF'
import json, subprocess, time

with open('prompts.json') as f:
    prompts = json.load(f)

results = []
for p in prompts:
    print(f"Running prompt {p['id']}/{len(prompts)}: {p['name']}...", flush=True)
    payload = json.dumps({"model": "qwen2.5:32b", "prompt": p["prompt"], "stream": False})
    try:
        r = subprocess.run(
            ["curl", "-s", "http://192.168.68.51:11434/api/generate", "-d", payload, "--max-time", "120"],
            capture_output=True, text=True, timeout=130
        )
        data = json.loads(r.stdout)
        results.append({
            "id": p["id"],
            "category": p["category"],
            "name": p["name"],
            "response": data.get("response", ""),
            "duration_seconds": round(data.get("total_duration", 0) / 1e9, 2)
        })
        print(f"  Done in {results[-1]['duration_seconds']}s", flush=True)
    except Exception as e:
        results.append({
            "id": p["id"],
            "category": p["category"],
            "name": p["name"],
            "response": f"ERROR: {str(e)}",
            "duration_seconds": 0
        })
        print(f"  FAILED: {e}", flush=True)

with open('qwen-results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("All done!", flush=True)
PYEOF
