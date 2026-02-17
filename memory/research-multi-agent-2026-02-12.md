# Multi-Agent Architecture Research for OpenClaw
**Date:** 2026-02-12  
**Requested by:** Chris Langston  
**Target:** Discord guild `1339240201045938198`

---

## 1. How OpenClaw Supports Multiple Agents

OpenClaw has **first-class multi-agent support** built into a single Gateway instance. Each agent is a fully isolated "brain" with:

- **Its own workspace** — separate `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, memory files, skills
- **Its own state directory** (`agentDir`) — auth profiles, model registry, per-agent config
- **Its own session store** — chat history and routing state under `~/.openclaw/agents/<agentId>/sessions`
- **Its own identity** — name, emoji, avatar (set via `openclaw agents set-identity`)
- **Its own model** — can run different LLM models per agent
- **Its own sandbox/tool policy** — restrict what tools each agent can use

### Key Config Structure
```json5
{
  agents: {
    list: [
      {
        id: "omni",
        default: true,
        name: "Omni",
        workspace: "~/.openclaw/workspace",
        identity: { name: "Omni", emoji: "⚙️", avatar: "avatars/omni.png" }
      },
      {
        id: "lexicanum",
        name: "Lexicanum",
        workspace: "~/.openclaw/workspace-lexicanum",
        model: "anthropic/claude-sonnet-4",
        identity: { name: "Lexicanum", emoji: "📚", avatar: "avatars/lexicanum.png" }
      }
    ]
  }
}
```

### Agent CLI
```bash
openclaw agents add lexicanum --workspace ~/.openclaw/workspace-lexicanum
openclaw agents set-identity --agent lexicanum --name "Lexicanum" --emoji "📚" --avatar avatars/lexicanum.png
openclaw agents list --bindings
```

---

## 2. One Gateway or Multiple?

**One Gateway handles everything.** The docs are explicit:

> "Most setups should use one Gateway because a single Gateway can handle multiple messaging connections and agents."

Multiple Gateways are only needed for strong isolation (e.g., a rescue bot). For Chris's use case — multiple themed agents in one Discord server — a single Gateway is the right approach.

Each agent within the Gateway gets:
- Isolated workspace, sessions, and auth
- Per-agent sandbox and tool restrictions if desired
- Deterministic message routing via `bindings`

---

## 3. Discord Bot Identity Options

This is the trickiest part. There are **three approaches**, each with trade-offs:

### Option A: One Bot, Webhooks for Identity (Recommended for Start)
- **One Discord bot token** shared across all agents
- Use **Discord webhooks** to post messages with different names and avatars per channel
- Each agent posts to its dedicated channel via webhook, appearing with its own name/avatar
- **Pros:** Simple setup, one bot to manage, works today
- **Cons:** Webhook messages can't be @mentioned, limited interactivity

### Option B: Multiple Discord Bot Tokens (Full Identity)
- **Create a separate Discord bot application** for each agent in the Discord Developer Portal
- Each bot has its own token, name, avatar, and presence
- Configure OpenClaw with `channels.discord.accounts` (multi-account support)
- Route each account to its agent via bindings
- **Pros:** Each agent is a real bot with full Discord presence, @mentionable, own avatar
- **Cons:** More setup (one bot app per agent), need to manage multiple tokens, each bot needs to be invited to the server

### Option C: Single Bot, Channel Routing (Simplest)
- **One bot** handles everything, but posts are routed to different channels
- The bot's name/avatar stays the same everywhere
- Personality changes are only in the text style, not the visual identity
- **Pros:** Simplest possible setup
- **Cons:** No visual differentiation — all agents look like the same bot

### Multi-Account Discord Config (Option B)
```json5
{
  channels: {
    discord: {
      accounts: {
        omni: { token: "BOT_TOKEN_OMNI" },
        lexicanum: { token: "BOT_TOKEN_LEXICANUM" },
        enginseer: { token: "BOT_TOKEN_ENGINSEER" }
      }
    }
  },
  bindings: [
    { agentId: "omni", match: { channel: "discord", accountId: "omni" } },
    { agentId: "lexicanum", match: { channel: "discord", accountId: "lexicanum" } },
    { agentId: "enginseer", match: { channel: "discord", accountId: "enginseer" } }
  ]
}
```

### Recommendation
**Start with Option C** (single bot, channel routing, personality in text) to validate the concept. **Graduate to Option B** (multiple bots) once you know which agents are worth keeping. Option B gives the full experience but requires creating Discord bot applications for each.

---

## 4. Practical Setup Steps

### Phase 1: Add a Second Agent (Proof of Concept)
1. **Create the agent workspace:**
   ```bash
   openclaw agents add lexicanum --workspace ~/.openclaw/workspace-lexicanum
   ```
2. **Write its personality files:**
   - `~/.openclaw/workspace-lexicanum/SOUL.md` — Lexicanum's personality
   - `~/.openclaw/workspace-lexicanum/AGENTS.md` — Operating instructions
   - `~/.openclaw/workspace-lexicanum/IDENTITY.md` — Name, emoji, avatar
3. **Set identity:**
   ```bash
   openclaw agents set-identity --agent lexicanum --from-identity
   ```
4. **Add a binding** to route a Discord channel to this agent:
   ```json5
   bindings: [
     {
       agentId: "lexicanum",
       match: { channel: "discord", peer: { kind: "group", id: "CHANNEL_ID" } }
     }
   ]
   ```
5. **Create a Discord channel** (e.g., `#lexicanum`) and get its ID
6. **Update config** and restart gateway

### Phase 2: Multiple Bot Identities
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new Application for each agent
3. Add a Bot to each, set its name and avatar
4. Enable Message Content Intent + Server Members Intent on each
5. Generate invite URLs and add each bot to the server
6. Configure multi-account Discord in OpenClaw config
7. Set up bindings per account

### Phase 3: Inter-Agent Communication
```json5
{
  tools: {
    agentToAgent: {
      enabled: true,  // off by default
      allow: ["omni", "lexicanum", "enginseer", "astropath"]
    }
  }
}
```

---

## 5. Warhammer 40k Mechanicum Agent Ideas

Themed around the Cult Mechanicus / Adeptus Mechanicus:

### ⚙️ Omni (Fabricator-General) — Already Exists
- **Role:** Primary assistant, orchestrator, general purpose
- **Channel:** `#omni` / DMs
- **Personality:** The machine spirit of the Omnissiah. Direct, competent, dry wit.
- **Model:** Claude Opus (current setup)

### 📚 Lexicanum (Data-Savant)
- **Role:** Research, knowledge retrieval, fact-checking, lore questions
- **Channel:** `#lexicanum` or `#research`
- **Personality:** Scholarly, precise, loves citations. Speaks like a Tech-Priest who has read every data-scroll in the Librarius. Uses formal but not impenetrable language.
- **Model:** Claude Sonnet (cost-efficient for research tasks)
- **Skills:** Web search, document analysis, summarization
- **Quote style:** *"The data-stacks have been consulted. Cross-referencing against 3 primary noospheric sources..."*

### 🔧 Enginseer (Ops-Adept)
- **Role:** Server monitoring, Docker management, system health, backups
- **Channel:** `#enginseer` or `#ops`
- **Personality:** Practical, hands-on, speaks in terms of sacred rites and maintenance protocols. Concerned with uptime and the health of machine spirits.
- **Model:** Sonnet or cheaper model (routine ops tasks)
- **Skills:** Exec access, system monitoring, healthcheck skill
- **Quote style:** *"The sacred rites of maintenance have been performed. All systems nominal. The machine spirit is appeased."*

### 📡 Astropath (Media-Herald)
- **Role:** News aggregation, morning briefings, social media monitoring, hobby news
- **Channel:** `#astropath` or `#briefings`
- **Personality:** Dramatic, prophetic tone. Delivers news like transmissions from the Astronomican. Sees connections and patterns.
- **Model:** Sonnet (content generation)
- **Skills:** Web search, RSS monitoring, news aggregation
- **Quote style:** *"A signal pierces the Warp. From the forge-worlds of Nottingham, Games Workshop transmits..."*

### 🛡️ Skitarius (Guardian-Sentinel)
- **Role:** Security monitoring, threat detection, access control
- **Channel:** `#security`
- **Personality:** Vigilant, terse, military precision. Reports threats with cold efficiency.
- **Model:** Haiku/cheap model (simple monitoring tasks)
- **Skills:** Healthcheck skill, log analysis
- **Quote style:** *"THREAT ASSESSMENT: Low. Perimeter secure. No unauthorized access detected in the last 24 cycles."*

### 🎨 Artisan (Servo-Skull of Creativity)
- **Role:** Image generation, creative writing, hobby project ideas, paint scheme suggestions
- **Channel:** `#artisan` or `#creative`
- **Personality:** Enthusiastic about craft and creation. Appreciates beauty in both organic and mechanical forms.
- **Model:** Could use image generation APIs
- **Skills:** OpenAI image gen skill, creative writing
- **Quote style:** *"The muse-program activates. Processing aesthetic parameters... I suggest a layered approach: basecoat Leadbelcher, wash with Nuln Oil..."*

---

## 6. Limitations and Gotchas

### Token Costs 💰
- **Each agent has its own sessions** — every agent burns tokens independently
- System prompts (SOUL.md, AGENTS.md, etc.) are injected per session, so more agents = more baseline token usage
- **Mitigation:** Use cheaper models for specialized agents (Sonnet for research, Haiku for monitoring)
- **Mitigation:** Use sub-agents (`sessions_spawn`) for one-off tasks instead of persistent agents

### Complexity 🔧
- Each agent needs its own workspace with personality files maintained
- More agents = more config to manage, more things to break
- Bindings/routing can get complex with many agents and channels
- Auth profiles are per-agent — if an agent needs Gmail access, you set it up separately

### Maintenance Burden 📋
- Updating AGENTS.md/SOUL.md across multiple workspaces
- Memory files accumulate per agent
- More Discord bots to manage (if using Option B)
- Gateway restart affects all agents

### Discord-Specific ⚠️
- Each separate Discord bot needs its own application in the Developer Portal
- Each bot needs to be invited to the server separately
- Bot name/avatar are set in the Developer Portal (not dynamically changeable per-channel)
- Webhook approach loses @mention capability
- All bots share the same rate limits if on the same IP

### Resource Usage 🖥️
- The Omnissiah has plenty of power (Ryzen 9 9950X, 64GB RAM, RTX 4070 Ti Super)
- CPU/RAM impact of multiple agents is minimal — it's all API calls
- The real cost is API tokens, not compute

---

## 7. Phased Rollout Plan

### Phase 1: Proof of Concept (Week 1)
**Goal:** Get a second agent working alongside Omni

1. Create `Lexicanum` agent with its own workspace and personality
2. Create a `#lexicanum` channel in Discord
3. Bind that channel to the Lexicanum agent (single bot, channel routing)
4. Test: mention the bot in `#lexicanum` and verify it responds in character
5. Cost: ~30 min setup, no additional API costs beyond usage

### Phase 2: Refine & Add One More (Week 2-3)
**Goal:** Validate the multi-agent experience

1. Tune Lexicanum's personality based on how it feels
2. Add `Astropath` agent for the `#briefings` channel (replaces Omni's briefing duties)
3. Move morning briefing cron job to the Astropath agent
4. Set Astropath to use Sonnet to save costs
5. Evaluate: Is this actually better than one agent doing everything?

### Phase 3: Separate Bot Identities (Week 4+)
**Goal:** Full visual identity per agent

1. Create Discord bot applications for Lexicanum and Astropath
2. Set up multi-account Discord config
3. Each bot gets its own name, avatar, and presence in the server
4. Consider adding Enginseer for ops monitoring

### Phase 4: Expand Cautiously (Ongoing)
**Goal:** Add agents only when they earn their place

1. Each new agent must solve a real problem or add real value
2. Monitor token costs monthly
3. Use sub-agents for one-off tasks, persistent agents only for ongoing roles
4. Consider agent-to-agent communication for complex workflows
5. Possible additions: Skitarius (security), Artisan (creative)

### Decision Point After Phase 2
Before investing in Phase 3, answer:
- Do the separate agents feel meaningfully different from one agent with different channels?
- Is the token cost acceptable?
- Is the maintenance overhead worth it?
- Does Chris actually interact with the secondary agents regularly?

If the answer to any of these is "no," consolidate back to Omni with channel-specific system prompts (simpler, cheaper).

---

## Summary

OpenClaw is **well-architected for multi-agent setups**. The infrastructure supports it natively — separate workspaces, bindings, per-agent models, per-agent tools, and per-agent identity. The main decisions are:

1. **How many agents do you actually need?** Start with 2, expand based on value.
2. **One bot or many?** Start with one bot + channel routing. Graduate to multiple bots for full identity.
3. **Cost management:** Use cheaper models for specialized agents. Monitor token usage.
4. **The Mechanicum theme is 🔥** — it gives each agent a natural role and personality that maps to real functionality.

The Omnissiah has the hardware. The framework has the features. The only question is finding the right balance between cool factor and practical value.
