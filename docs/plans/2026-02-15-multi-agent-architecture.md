# Multi-Agent Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up a coordinator/worker multi-agent system where main (Opus) dispatches specialized agents (Haiku/Sonnet) for research, writing, monitoring, and vault management tasks.

**Architecture:** Define named agents in `agents.list` config, each with their own model, tools, and workspace. Main agent (Opus) coordinates. Specialists use cheaper/faster models for focused work. All share the same workspace directory so they read the same AGENTS.md, TOOLS.md, skills, and memory files. Agent identification via "When spawned as X" sections in AGENTS.md.

**Tech Stack:** OpenClaw `agents.list` config, Anthropic Claude (Opus/Sonnet/Haiku), local Ollama (Qwen 2.5 32B), Obsidian REST API for vault ops.

---

### Task 1: Define Agent Configs and Enable Subagent Access

**Files:**
- Modify: `/root/.openclaw/openclaw.json` (via `gateway config.patch`)

**Step 1: Apply the complete agents.list config patch**

Use `gateway config.patch` to add all agents to the config including main agent with subagent permissions. Each specialist agent gets:
- **researcher** — Haiku, minimal tools (web_search, web_fetch, Read, memory_search, memory_get), no messaging
- **writer** — Sonnet, coding tools (Read, Write, Edit, exec, memory_search, memory_get), no messaging
- **monitor** — Haiku, messaging + web tools, heartbeat-enabled for proactive checks
- **vault-manager** — Haiku, exec only (for curl to Obsidian REST API), no messaging
- **main** — Opus (default agent), subagents.allowAgents configured to spawn all 4 specialists

Config patch to apply:

```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "default": true,
        "model": "anthropic/claude-opus-4-6",
        "subagents": {
          "allowAgents": ["researcher", "writer", "monitor", "vault-manager"]
        }
      },
      {
        "id": "researcher",
        "name": "Researcher",
        "model": "anthropic/claude-haiku-4-5-20251001",
        "workspace": "/root/.openclaw/workspace",
        "tools": {
          "profile": "minimal",
          "alsoAllow": ["web_search", "web_fetch", "memory_search", "memory_get"]
        },
        "identity": {
          "name": "Omni (Research)",
          "emoji": "🔍"
        }
      },
      {
        "id": "writer",
        "name": "Writer",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "workspace": "/root/.openclaw/workspace",
        "tools": {
          "profile": "coding"
        },
        "identity": {
          "name": "Omni (Writer)",
          "emoji": "✍️"
        }
      },
      {
        "id": "monitor",
        "name": "Monitor",
        "model": "anthropic/claude-haiku-4-5-20251001",
        "workspace": "/root/.openclaw/workspace",
        "tools": {
          "profile": "messaging",
          "alsoAllow": ["web_search", "web_fetch", "memory_search", "memory_get"]
        },
        "heartbeat": {
          "every": "30m",
          "activeHours": {
            "start": "08:00",
            "end": "23:00",
            "timezone": "America/New_York"
          },
          "prompt": "Check HEARTBEAT.md for monitoring tasks. Run any due checks. Reply HEARTBEAT_OK if nothing needs attention."
        },
        "identity": {
          "name": "Omni (Monitor)",
          "emoji": "📡"
        }
      },
      {
        "id": "vault-manager",
        "name": "Vault Manager",
        "model": "anthropic/claude-haiku-4-5-20251001",
        "workspace": "/root/.openclaw/workspace",
        "tools": {
          "profile": "minimal",
          "alsoAllow": ["exec"]
        },
        "identity": {
          "name": "Omni (Vault)",
          "emoji": "📚"
        }
      }
    ]
  }
}
```

**Step 2: Verify the config applied**

Run: `gateway config.get`
Expected: JSON response with `agents.list` containing 5 entries (main + 4 specialists) with correct ids and configurations.

**Step 3: Verify agents are spawnable**

Run: `agents_list` tool
Expected: Response shows main + researcher + writer + monitor + vault-manager all available.

**Step 4: No commit needed**

Note: Config lives outside workspace git repository. No commit step for this task.

**Troubleshooting:**
- If `gateway config.patch` fails with "invalid JSON": Verify the JSON is valid using `echo '<json>' | jq .`
- If `agents_list` doesn't show new agents: Restart the gateway service or check gateway logs
- If main agent's `allowAgents` is missing: Verify the main agent entry in config has `subagents.allowAgents` array

---

### Task 2: Add Agent Role Sections to AGENTS.md

**Files:**
- Modify: `/root/.openclaw/workspace/AGENTS.md`

**Step 1: Read current AGENTS.md to verify location**

Run: `cat /root/.openclaw/workspace/AGENTS.md | grep -n "Make It Yours"`
Expected: Line number where "Make It Yours" section appears (or empty if section doesn't exist).

**Step 2: Write the agent role identification sections**

Use the Edit tool to append before the "Make It Yours" section (or at end of file if that section doesn't exist):

```markdown
## Agent Roles

When spawned as a sub-agent, check your agent id in the runtime line. Follow the role instructions below.

### When spawned as `researcher`
You are a research specialist. Your job:
- Search the web, fetch pages, and synthesize findings
- Return structured research summaries with source links
- Focus on accuracy and citation — always include URLs
- You do NOT have messaging tools — return results to your parent session
- Read TOOLS.md for API endpoints and credentials you may need

### When spawned as `writer`
You are a writing and coding specialist. Your job:
- Write, edit, and refactor code and documentation
- Follow TDD practices — write tests first when applicable
- You have full coding tools (Read, Write, Edit, exec)
- You do NOT have messaging tools — return results to your parent session
- Read TOOLS.md for project conventions and paths

### When spawned as `monitor`
You are a monitoring specialist with a heartbeat. Your job:
- Check email, calendar, server health, and other periodic tasks
- Use HEARTBEAT.md for your task checklist
- You HAVE messaging tools — send alerts directly to Discord/WhatsApp when urgent
- Track check timestamps in `memory/heartbeat-state.json`
- Be quiet unless something needs attention

### When spawned as `vault-manager`
You are the Obsidian vault specialist. Your job:
- Read and write notes via the Obsidian REST API (curl commands)
- Maintain PARA structure (Projects/Areas/Resources/Archive)
- Sync skills and documentation between workspace and vault
- Always use `curl -k` (self-signed cert) and `sleep 2` between writes
- API details are in TOOLS.md under "Local REST API"
- Read the `obsidian-rest-api` skill for API patterns
```

**Step 3: Run a quick read to verify the edit**

Run: `cat /root/.openclaw/workspace/AGENTS.md | tail -50`
Expected: See the new "Agent Roles" section with all 4 role descriptions at the end of the file.

**Step 4: Commit**

```bash
cd /root/.openclaw/workspace
git add AGENTS.md
git commit -m "feat: add multi-agent role sections to AGENTS.md"
```

**Troubleshooting:**
- If Edit tool fails with "old_string not found": The file structure may have changed. Read the full file, identify the correct insertion point, and adjust the edit.
- If commit fails with "nothing to commit": Verify the edit actually modified the file using `git diff AGENTS.md`

---

### Task 3: Test Each Agent with a Simple Spawn

**Files:** None (validation only)

**Step 1: Test researcher agent**

Run the tool:
```
sessions_spawn(agentId="researcher", task="Search the web for 'OpenClaw multi-agent setup guide' and return a 3-bullet summary with links.")
```

Expected: Returns within ~30s with a research summary and source URLs. Confirms web_search tool works.

**Step 2: Test writer agent**

Run the tool:
```
sessions_spawn(agentId="writer", task="Read /root/.openclaw/workspace/AGENTS.md and report how many H2 headers (## ) it contains.")
```

Expected: Returns with correct count (should be at least 6 after Task 2). Confirms Read tool works.

**Step 3: Test vault-manager agent**

Run the tool:
```
sessions_spawn(agentId="vault-manager", task="Read the file /root/.openclaw/obsidian-rest-api-key, then use curl -k to list all files in the Obsidian vault at https://192.168.68.51:27124. Use the API key as a Bearer token in the Authorization header. Report the first 5 files.")
```

Expected: Returns vault file listing. Confirms exec + API access works.

**Step 4: Test monitor agent**

Run the tool:
```
sessions_spawn(agentId="monitor", task="Read HEARTBEAT.md and report what tasks are configured. If the file doesn't exist yet or is empty, say so.")
```

Expected: Reports HEARTBEAT.md doesn't exist or is empty (will be created in Task 5).

**Step 5: No commit needed**

Note: This task only validates configuration. No files modified.

**Troubleshooting:**
- If any spawn fails with "agent not found": Verify `agents_list` shows the agent, check spelling of agentId
- If researcher fails with "web_search tool not available": Check agent config has web_search in alsoAllow array
- If vault-manager fails with "connection refused": Verify Obsidian REST API is running on the target host
- If spawns fail with "max concurrent exceeded": Run tests sequentially with delays, or check `agents.defaults.subagents.maxConcurrent` setting

---

### Task 4: Create Obsidian Project Note

**Files:**
- Create: Obsidian vault `Projects/MultiAgentArchitecture/README.md` (via REST API)

**Step 1: Write the project note using vault-manager agent**

Spawn vault-manager to create the project documentation in Obsidian:

```
sessions_spawn(agentId="vault-manager", task="Create a new file in the Obsidian vault at path 'Projects/MultiAgentArchitecture/README.md' with the following content. Use the API key from /root/.openclaw/obsidian-rest-api-key and the REST API at https://192.168.68.51:27124. Use PUT method with -k flag for self-signed cert.

Content:
# Multi-Agent Architecture

## Status: In Progress

## Goal
Coordinator/worker multi-agent system for the Omnissiah.

## Agents
- **main** (Opus) — Coordinator, dispatches tasks
- **researcher** (Haiku) — Web research, source gathering
- **writer** (Sonnet) — Code and documentation
- **monitor** (Haiku) — Proactive checks, alerts
- **vault-manager** (Haiku) — Obsidian vault operations

## Key Files
- `AGENTS.md` — Agent role definitions
- `openclaw.json` — Agent configs
- `HEARTBEAT.md` — Monitor task checklist
- `memory/heartbeat-state.json` — Check timestamps

## Tasks
- [x] Define agent configs in openclaw.json
- [x] Add role sections to AGENTS.md
- [x] Test each agent
- [x] Create this project note
- [ ] Set up monitor heartbeat tasks
- [ ] Build skill sync (vault ↔ workspace)
- [ ] Add cross-provider fallbacks
")
```

Expected: vault-manager confirms file created successfully.

**Step 2: Sleep before verification**

Run: `sleep 2`
Expected: 2-second pause (Obsidian REST API needs rate limiting between operations).

**Step 3: Verify the note exists using vault-manager**

```
sessions_spawn(agentId="vault-manager", task="Read the file 'Projects/MultiAgentArchitecture/README.md' from Obsidian vault using the REST API and report the first 5 lines.")
```

Expected: Returns the markdown content starting with `# Multi-Agent Architecture`.

**Step 4: No workspace commit needed**

Note: The project note lives in Obsidian vault, not workspace git. No commit step.

**Troubleshooting:**
- If vault-manager fails to create file: Check API key is valid, check network connectivity to 192.168.68.51:27124
- If PUT returns 404: Verify the parent directory `Projects/MultiAgentArchitecture/` exists or create it first
- If verification shows wrong content: Check for URL encoding issues in the PUT request body
- If "connection refused": Verify Obsidian with REST API plugin is running

---

### Task 5: Set Up Monitor Heartbeat Tasks

**Files:**
- Create: `/root/.openclaw/workspace/HEARTBEAT.md`
- Create: `/root/.openclaw/workspace/memory/heartbeat-state.json`

**Step 1: Create the HEARTBEAT.md file**

Use Write tool to create the monitor checklist:

```bash
# Create HEARTBEAT.md
```

Content:
```markdown
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
```

**Step 2: Create the heartbeat state tracking file**

Run:
```bash
mkdir -p /root/.openclaw/workspace/memory
```

Then use Write tool to create state file at `/root/.openclaw/workspace/memory/heartbeat-state.json`:

```json
{
  "lastChecks": {
    "email": null,
    "serverHealth": null
  }
}
```

**Step 3: Verify heartbeat files exist**

Run: `ls -la /root/.openclaw/workspace/HEARTBEAT.md /root/.openclaw/workspace/memory/heartbeat-state.json`
Expected: Both files listed with recent timestamps.

**Step 4: Verify heartbeat state file content**

Run: `cat /root/.openclaw/workspace/memory/heartbeat-state.json`
Expected: Valid JSON with null timestamps for both checks.

**Step 5: Commit**

```bash
cd /root/.openclaw/workspace
git add HEARTBEAT.md memory/heartbeat-state.json
git commit -m "feat: configure monitor heartbeat tasks and state tracking"
```

**Troubleshooting:**
- If mkdir fails: Directory may already exist (not an error) or permissions issue
- If Write fails: Check file paths are absolute and parent directories exist
- If JSON is invalid: Validate with `cat memory/heartbeat-state.json | jq .`
- If commit fails: Verify files were actually created and contain expected content

---

## Execution Notes

- **Task 1** includes both agent definitions AND main agent subagent permissions in a single config patch
- **Task 3 tests** should be run sequentially to avoid hitting maxConcurrent limits (default 8)
- **Task 4** uses vault-manager agent exclusively for consistency with the multi-agent architecture
- **Sleep commands** are included where REST API rate limiting is needed (Task 4 Step 2)
- **Monitor heartbeat** won't fire until Task 5 is complete and gateway has processed the config — the monitor's `heartbeat.every: "30m"` setting triggers it automatically after that
- The monitor agent is **independent** — it runs on its own heartbeat schedule, separate from main's disabled heartbeat

## Next Steps

After completing this plan:
1. Monitor the monitor agent's heartbeat behavior for the first few cycles
2. Implement skill sync between workspace and Obsidian vault
3. Add cross-provider fallback (Ollama for non-critical tasks when Anthropic quota exceeded)
4. Create example workflows that demonstrate coordinator/worker patterns
