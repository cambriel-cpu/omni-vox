# Multi-Agent Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up a coordinator/worker multi-agent system where main (Opus) dispatches specialized agents (Haiku/Sonnet) for research, writing, monitoring, and vault management tasks.

**Architecture:** Define named agents in `agents.list` config, each with their own model, tools, and workspace. Main agent (Opus) coordinates. Specialists use cheaper/faster models for focused work. All share the same workspace directory so they read the same AGENTS.md, TOOLS.md, skills, and memory files. Agent identification via "When spawned as X" sections in AGENTS.md.

**Tech Stack:** OpenClaw `agents.list` config, Anthropic Claude (Opus/Sonnet/Haiku), local Ollama (Qwen 2.5 32B), Obsidian REST API for vault ops.

---

### Task 1: Define Agent Configs in openclaw.json

**Files:**
- Modify: `/root/.openclaw/openclaw.json` (via `gateway config.patch`)

**Step 1: Apply the agents.list config patch**

Use `gateway config.patch` to add agents to the config. Each agent gets:
- **researcher** — Haiku, minimal tools (web_search, web_fetch, Read, memory_search, memory_get), no messaging
- **writer** — Sonnet, coding tools (Read, Write, Edit, exec, memory_search, memory_get), no messaging
- **monitor** — Haiku, messaging + web tools, heartbeat-enabled for proactive checks
- **vault-manager** — Haiku, exec only (for curl to Obsidian REST API), no messaging

Config patch to apply:

```json
{
  "agents": {
    "list": [
      {
        "id": "researcher",
        "name": "Researcher",
        "model": "anthropic/claude-haiku-3.5",
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
        "model": "anthropic/claude-sonnet-4",
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
        "model": "anthropic/claude-haiku-3.5",
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
        "model": "anthropic/claude-haiku-3.5",
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

Run: `gateway config.get` and confirm `agents.list` contains 4 entries with correct ids.
Expected: Array with researcher, writer, monitor, vault-manager.

**Step 3: Verify agents are spawnable**

Run: `agents_list` tool
Expected: Should show main + all 4 new agents.

**Step 4: Commit note**

No file change to commit — config lives outside workspace git.

---

### Task 2: Add Agent Role Sections to AGENTS.md

**Files:**
- Modify: `/root/.openclaw/workspace/AGENTS.md`

**Step 1: Write the agent role identification sections**

Append the following to the end of AGENTS.md (before "Make It Yours"):

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

**Step 2: Run a quick read to verify the edit**

Run: `cat /root/.openclaw/workspace/AGENTS.md | tail -50`
Expected: See the new "Agent Roles" section with all 4 role descriptions.

**Step 3: Commit**

```bash
cd /root/.openclaw/workspace
git add AGENTS.md
git commit -m "feat: add multi-agent role sections to AGENTS.md"
```

---

### Task 3: Configure Main Agent Subagent Access

**Files:**
- Modify: `/root/.openclaw/openclaw.json` (via `gateway config.patch`)

**Step 1: Update main agent defaults to allow spawning all agents**

The main agent needs `subagents.allowAgents` set to spawn the new agents. Apply config patch:

```json
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 8,
        "allowAgents": ["researcher", "writer", "monitor", "vault-manager"]
      }
    }
  }
}
```

Wait — `allowAgents` is on per-agent subagents config, not defaults. Let me check...

Actually, from the schema: `agents.list[].subagents.allowAgents` is the per-agent field. But `agents.defaults.subagents` doesn't have `allowAgents`. So we need to either:
1. Add a main agent entry to `agents.list` with `subagents.allowAgents`, or
2. Check if `allowAny` defaults to true when no list is configured.

From `agents_list` response: `"allowAny": false`. So we need to explicitly configure this.

Apply patch adding main to the agents list:

```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "default": true,
        "subagents": {
          "allowAgents": ["researcher", "writer", "monitor", "vault-manager"]
        }
      },
      {
        "id": "researcher",
        "name": "Researcher",
        "model": "anthropic/claude-haiku-3.5",
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
        "model": "anthropic/claude-sonnet-4",
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
        "model": "anthropic/claude-haiku-3.5",
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
        "model": "anthropic/claude-haiku-3.5",
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

Note: Tasks 1 and 3 are merged — apply this combined patch as a single operation in Task 1.

**Step 2: Verify spawnable agents**

Run: `agents_list`
Expected: main + researcher + writer + monitor + vault-manager all listed.

---

### Task 4: Test Each Agent with a Simple Spawn

**Files:** None (validation only)

**Step 1: Test researcher agent**

```
sessions_spawn(agentId="researcher", task="Search the web for 'OpenClaw multi-agent setup guide' and return a 3-bullet summary with links.")
```

Expected: Returns within ~30s with a research summary. Confirms web_search tool works.

**Step 2: Test writer agent**

```
sessions_spawn(agentId="writer", task="Read /root/.openclaw/workspace/AGENTS.md and report how many H2 headers it contains.")
```

Expected: Returns with correct count. Confirms Read tool works.

**Step 3: Test vault-manager agent**

```
sessions_spawn(agentId="vault-manager", task="Read the file /root/.openclaw/obsidian-rest-api-key, then use curl -k to list all files in the Obsidian vault at https://192.168.68.51:27124. Use the API key as a Bearer token in the Authorization header. Report the first 5 files.")
```

Expected: Returns vault file listing. Confirms exec + API access works.

**Step 4: Test monitor agent**

```
sessions_spawn(agentId="monitor", task="Read HEARTBEAT.md and report what tasks are configured. If none, say so.")
```

Expected: Reports HEARTBEAT.md is empty/comments only.

---

### Task 5: Create Obsidian Project Note

**Files:**
- Create: Obsidian vault `Projects/MultiAgentArchitecture/README.md` (via REST API)

**Step 1: Write the project note to the vault**

Use the vault-manager or direct exec to push via Obsidian REST API:

```bash
API_KEY=$(cat /root/.openclaw/obsidian-rest-api-key)
curl -k -X PUT "https://192.168.68.51:27124/vault/Projects/MultiAgentArchitecture/README.md" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: text/markdown" \
  -d '# Multi-Agent Architecture

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
- [x] Configure subagent access
- [x] Test each agent
- [x] Create this project note
- [ ] Set up monitor heartbeat tasks
- [ ] Build skill sync (vault ↔ workspace)
- [ ] Add cross-provider fallbacks
'
```

**Step 2: Verify the note exists**

```bash
curl -k -s "https://192.168.68.51:27124/vault/Projects/MultiAgentArchitecture/README.md" \
  -H "Authorization: Bearer $API_KEY" | head -5
```

Expected: Returns the markdown content starting with `# Multi-Agent Architecture`.

**Step 3: Commit workspace changes**

```bash
cd /root/.openclaw/workspace
git add docs/plans/
git commit -m "docs: add multi-agent architecture implementation plan"
```

---

### Task 6: Set Up Monitor Heartbeat Tasks

**Files:**
- Modify: `/root/.openclaw/workspace/HEARTBEAT.md`

**Step 1: Write monitor-specific heartbeat checklist**

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

**Step 2: Create the heartbeat state file**

```bash
mkdir -p /root/.openclaw/workspace/memory
cat > /root/.openclaw/workspace/memory/heartbeat-state.json << 'EOF'
{
  "lastChecks": {
    "email": null,
    "serverHealth": null
  }
}
EOF
```

**Step 3: Verify heartbeat state file**

Run: `cat /root/.openclaw/workspace/memory/heartbeat-state.json`
Expected: Valid JSON with null timestamps.

**Step 4: Commit**

```bash
cd /root/.openclaw/workspace
git add HEARTBEAT.md memory/heartbeat-state.json
git commit -m "feat: configure monitor heartbeat tasks and state tracking"
```

---

## Execution Notes

- **Task 1 & 3 are merged** — apply the full agents.list patch (including main with subagents.allowAgents) as a single config.patch operation
- **Task 4 tests** should be run sequentially to avoid hitting maxConcurrent limits
- **Task 5** needs `sleep 2` before the verify step (known REST API rate issue)
- **Monitor heartbeat** (Task 6) won't fire until the config is applied and gateway restarts — the monitor's `heartbeat.every: "30m"` setting triggers it automatically
- The monitor agent is **independent** — it runs on its own heartbeat schedule, separate from main's disabled heartbeat
