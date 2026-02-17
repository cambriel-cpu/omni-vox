#!/bin/bash
# GPU Telemetry Logger for the Omnissiah
# Logs GPU utilization, VRAM, temperature, and power to a JSONL file
# Usage: Run via cron or manually. Each invocation appends one snapshot.

SSH_CMD="ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51"
LOG_FILE="/root/.openclaw/workspace/telemetry/gpu-metrics.jsonl"

mkdir -p "$(dirname "$LOG_FILE")"

# Query nvidia-smi for key metrics
METRICS=$($SSH_CMD "nvidia-smi --query-gpu=timestamp,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit --format=csv,noheader,nounits" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$METRICS" ]; then
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"error\":\"nvidia-smi failed\"}" >> "$LOG_FILE"
  exit 1
fi

# Parse CSV output
IFS=',' read -r TIMESTAMP TEMP GPU_UTIL MEM_UTIL MEM_USED MEM_TOTAL POWER_DRAW POWER_LIMIT <<< "$METRICS"

# Get running GPU processes
PROCESSES=$($SSH_CMD "nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader,nounits" 2>/dev/null | tr '\n' '|' | sed 's/|$//')

# Get Ollama model info if running
OLLAMA_STATUS=$($SSH_CMD "curl -s http://localhost:11434/api/ps 2>/dev/null" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    models=d.get('models',[])
    if models:
        m=models[0]
        print(json.dumps({'model':m.get('name',''),'size_vram':m.get('size_vram',0),'size':m.get('size',0)}))
    else:
        print('null')
except:
    print('null')
" 2>/dev/null)

cat >> "$LOG_FILE" << EOF
{"ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","temp_c":${TEMP// /},"gpu_util_pct":${GPU_UTIL// /},"mem_util_pct":${MEM_UTIL// /},"vram_used_mb":${MEM_USED// /},"vram_total_mb":${MEM_TOTAL// /},"power_w":${POWER_DRAW// /},"power_limit_w":${POWER_LIMIT// /},"ollama":${OLLAMA_STATUS:-null},"processes":"${PROCESSES}"}
EOF
