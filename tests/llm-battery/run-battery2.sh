#!/bin/bash
cd /root/.openclaw/workspace/tests/llm-battery

python3 << 'PYEOF'
import json, subprocess, time, tempfile, os

with open('prompts.json') as f:
    prompts = json.load(f)

results = []
for p in prompts:
    print(f"Running prompt {p['id']}/{len(prompts)}: {p['name']}...", flush=True)
    payload = json.dumps({"model": "qwen2.5:32b", "prompt": p["prompt"], "stream": False})
    
    # Write payload to temp file to avoid shell escaping issues
    tmp = f"/tmp/ollama_prompt_{p['id']}.json"
    with open(tmp, 'w') as f:
        f.write(payload)
    
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "120", "http://192.168.68.51:11434/api/generate", "-d", f"@{tmp}", "-H", "Content-Type: application/json"],
            capture_output=True, text=True, timeout=130
        )
        os.unlink(tmp)
        if r.returncode != 0:
            raise Exception(f"curl exit {r.returncode}: {r.stderr}")
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
    
    # Save incrementally
    with open('qwen-results.json', 'w') as f:
        json.dump(results, f, indent=2)

print("All done!", flush=True)
PYEOF
