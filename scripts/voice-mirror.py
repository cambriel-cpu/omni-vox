#!/usr/bin/env python3
"""Watch /tmp/voice-exchanges.jsonl and write new entries to a pickup file for OpenClaw"""
import json, time, os

WATCH = "/tmp/voice-exchanges.jsonl"
PICKUP = "/tmp/voice-mirror-pickup.jsonl"
SEEN = "/tmp/voice-mirror-seen"

def get_seen_count():
    try:
        with open(SEEN) as f:
            return int(f.read().strip())
    except:
        return 0

def set_seen_count(n):
    with open(SEEN, "w") as f:
        f.write(str(n))

if not os.path.exists(WATCH):
    exit(0)

with open(WATCH) as f:
    lines = f.readlines()

seen = get_seen_count()
new_lines = lines[seen:]

if not new_lines:
    exit(0)

for line in new_lines:
    entry = json.loads(line.strip())
    with open(PICKUP, "a") as f:
        f.write(line)

set_seen_count(len(lines))
# Print for cron output
for line in new_lines:
    e = json.loads(line.strip())
    print(f"🎤 Chris: \"{e['transcript']}\"")
    print(f"⚙️ Omni: {e['response']}")
