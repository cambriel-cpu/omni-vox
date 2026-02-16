# HEARTBEAT.md

## Monitor Checklist
When the monitor agent receives a heartbeat, run through these checks:

### Email Check (every 4 hours)
- Read unread emails via himalaya
- Alert Chris if anything urgent
- Log check timestamp to memory/heartbeat-state.json

### Server Health (every 2 hours)
- Check disk space on Unraid: `ssh -i /root/.openclaw/omni_ssh_key omni@192.168.68.51 df -h /mnt/user`
- Check Docker containers: `ssh -i /root/.openclaw/omni_ssh_key omni@192.168.68.51 docker ps --format 'table {{.Names}}\t{{.Status}}'`
- Alert if any container is unhealthy or disk >90%

### Timing
- Track last check times in `memory/heartbeat-state.json`
- Only run checks that are due based on their intervals
- If nothing is due, reply HEARTBEAT_OK
