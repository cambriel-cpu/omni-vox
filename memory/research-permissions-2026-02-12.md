# Permissions Research: OpenClaw → Unraid Container Management

**Date:** 2026-02-12
**Context:** OpenClaw runs as a Docker container on Unraid 7.0.0 (The Omnissiah), br0 network, IP 192.168.68.99. Currently has gateway exec access but no Docker or host management capabilities.

**Goal:** What would Omni need to deploy/manage Docker containers remotely, and what are the security trade-offs?

---

## TL;DR — The Recommendation

**Use the Unraid GraphQL API with a scoped API key.** It's the safest option that gives you real container management without handing over the keys to the kingdom. Unraid 7.0+ has this built in (via the Connect plugin; native in 7.2+). You create an API key with *only* the permissions Omni needs — like Docker read/write but NOT array management or flash access.

If you need more power later, SSH with a restricted command set is a reasonable step up. Avoid Docker socket mounting unless you fully understand you're giving the AI root-equivalent access.

---

## Option 1: Docker Socket Mount (`/var/run/docker.sock`)

### What It Is
You'd add `/var/run/docker.sock:/var/run/docker.sock` to OpenClaw's container config. This gives the container direct access to Docker's control interface — the same one Unraid itself uses.

### What It Enables
- **Everything.** Create, start, stop, delete any container on the system
- Pull any Docker image
- Inspect all container configs (including environment variables with passwords/API keys)
- Create privileged containers (which can access the host filesystem)
- Manage Docker networks and volumes
- View logs from every container

### Security Risk Level: 🔴 CRITICAL

### Why It's So Dangerous
This is effectively **root access to the Omnissiah**. Here's the worst case: a compromised AI (or a prompt injection attack) could:

1. Spin up a new privileged container that mounts the entire host filesystem (`/`)
2. Through that container, read/write/delete **anything** — your media library, Nextcloud data, Unraid flash drive config, user passwords
3. Install a backdoor that persists across reboots
4. Access credentials stored in other containers' environment variables (database passwords, API keys, etc.)

This isn't theoretical — "container escape via Docker socket" is a well-known attack vector.

### Blast Radius If Compromised
**Total.** Everything on the Omnissiah — all data, all containers, the OS config itself. Equivalent to someone sitting at the server with root access.

### Reversible?
Technically yes (remove the mount), but damage done while it was active may not be recoverable. If someone exfiltrates data or corrupts files, removing the socket doesn't undo that.

### Recommendation: ⛔ NOT RECOMMENDED
The risk-to-benefit ratio is terrible. Every other option on this list gives you container management with less exposure. The only reason to do this is if you need *maximum speed* for container operations and trust the AI completely. Given that the Omnissiah hosts irreplaceable data, this is a hard no.

---

## Option 2: Unraid GraphQL API (with Scoped API Key) ⭐ RECOMMENDED

### What It Is
Unraid 7.0+ (via the Connect plugin) and 7.2+ (built-in) provides a **GraphQL API** — a modern, structured interface for managing your server. You create an API key with specific permissions, and Omni uses that key to make requests to the API over HTTP.

### What It Enables
With appropriate permissions, Omni could:
- **List containers** — see what's running, what's stopped, resource usage
- **Start/stop/restart containers** — manage your services
- **Monitor system health** — CPU, memory, disk temps, array status
- **Manage Docker networks**
- Query server info, check parity status, etc.

The key feature: **permissions are granular**. You can create a key that allows:
- `DOCKER:READ_ANY` — view containers (read-only monitoring)
- `DOCKER:READ_ANY,DOCKER:UPDATE_ANY` — view + start/stop/restart
- `DOCKER:CREATE_ANY,DOCKER:DELETE_ANY` — full container lifecycle

Available permission scopes include: `DOCKER`, `ARRAY`, `VMS`, `NETWORK`, `SHARE`, `DISK`, `INFO`, `NOTIFICATIONS`, `CONFIG`, and more. Each can be set to read-only or read-write independently.

### How To Set It Up
1. In Unraid WebGUI: **Settings → Management Access → API** (or install the Connect plugin if on 7.0)
2. Create an API key with specific permissions (e.g., Docker read/write only)
3. Give Omni that API key
4. Omni makes HTTP requests to `http://192.168.68.1/graphql` (or whatever your Unraid IP is) with the key in the `x-api-key` header

Example query Omni would run:
```graphql
query { dockerContainers { id names state status autoStart } }
```

### Security Risk Level: 🟢 LOW to 🟡 MEDIUM (depending on permissions granted)

### Why It's Safer
- **Principle of least privilege** — Omni gets *only* what it needs
- **No filesystem access** — can't read/write host files
- **No container escape** — the API is a controlled interface, not raw Docker access
- **Auditable** — API requests can be logged
- **Revocable** — delete the API key instantly to cut off access
- A read-only key is basically zero risk (monitoring only)
- Even a full Docker permission key can't access the array, flash drive, or other containers' secrets

### Blast Radius If Compromised
- **Read-only key:** Near zero. Attacker sees container names and status. That's it.
- **Docker read/write key:** Could stop/start containers (annoying but recoverable), potentially create new containers. But can't access host filesystem, can't read other containers' passwords, can't modify Unraid config.
- **Admin key:** Similar to Docker socket — avoid this.

### Reversible?
**Yes, instantly.** Delete the API key from the Unraid GUI and access is cut off. No traces left.

### Recommendation: ✅ STRONGLY RECOMMENDED
This is the right answer for your situation. Start with a read-only key for monitoring, then expand to Docker read/write when you're comfortable. The Unraid API was literally designed for this use case.

**Suggested starting permissions:** `DOCKER:READ_ANY,DOCKER:UPDATE_ANY,INFO:READ_ANY,NOTIFICATIONS:READ_ANY`
This lets Omni: view containers, start/stop them, check system info, and read notifications. Nothing destructive.

---

## Option 3: SSH Access to Unraid Host

### What It Is
Set up SSH key authentication so OpenClaw can SSH into the Unraid host and run commands directly.

### What It Enables
- Run any command on the host as root (Unraid's SSH is root-only by default)
- `docker` commands (same as socket mount, effectively)
- Edit config files
- Access the filesystem
- Run Unraid CLI tools
- Basically anything you can do in the Unraid terminal

### Security Risk Level: 🔴 HIGH to CRITICAL

### Why It's Risky
SSH to Unraid = root shell on the host. It's slightly better than Docker socket because:
- You could restrict it with a `ForceCommand` in SSH config (limit what commands can be run)
- SSH access is logged
- You could use a non-standard port

But by default, it's unrestricted root access.

### Blast Radius If Compromised
**Total** (same as Docker socket) unless you set up command restrictions, in which case it's limited to whatever commands you allow.

### Reversible?
Yes — remove the SSH key from `/root/.ssh/authorized_keys` on the Unraid host.

### Recommendation: 🟡 ACCEPTABLE (only with restrictions)
If the Unraid API doesn't cover a specific need, SSH with a `ForceCommand` restriction (limiting it to specific Docker commands) is a reasonable fallback. But don't do unrestricted SSH — it's root access with extra steps.

---

## Option 4: Tailscale / Remote Access

### What It Is
Tailscale creates an encrypted network overlay (like a private VPN) between your devices. If both the Unraid host and OpenClaw container are on Tailscale, they can communicate securely even from different networks.

### What It Enables
Tailscale itself doesn't enable container management — it's a **transport layer**. It secures the connection *between* OpenClaw and whatever management interface you choose (API, SSH, etc.). It's relevant if:
- You want Omni to manage the server when you're away from home
- You want to avoid exposing any management ports on the LAN
- You want encrypted, authenticated connections between the container and host

### Security Risk Level: 🟢 LOW (Tailscale itself)
Tailscale is well-regarded for security. It uses WireGuard encryption, requires device authentication, and doesn't open ports on your network.

### Why Use It
- **No open ports** — management interfaces aren't exposed to the whole LAN
- **Works remotely** — Omni could manage containers even when not on local network
- **ACLs** — Tailscale lets you define which devices can talk to which (you could restrict OpenClaw to only reach the API port)
- **Audit logging** — Tailscale logs connections

### Blast Radius If Compromised
Depends entirely on what's behind Tailscale. If it's just providing access to the scoped API, blast radius is the same as the API option (low). If it's providing access to SSH, blast radius is the same as SSH (high).

### Reversible?
Yes — remove the device from your Tailnet.

### Recommendation: ✅ RECOMMENDED (as a transport layer)
Tailscale + Unraid API is an excellent combination. But Tailscale alone doesn't solve the permissions question — it just secures how you get there. Think of it as a locked tunnel; you still need to decide what's on the other end.

**Note:** You already have br0 networking giving OpenClaw LAN access. Tailscale becomes more valuable if you want to restrict which ports/services OpenClaw can reach, or enable remote management.

---

## Option 5: Docker TCP API

### What It Is
Instead of mounting the Docker socket file, you expose Docker's API over a TCP port (e.g., `tcp://192.168.68.1:2375`). OpenClaw would then make HTTP requests to that port to manage Docker.

### What It Enables
Same as Docker socket — full Docker control (create, delete, start, stop containers, etc.)

### Security Risk Level: 🔴 CRITICAL

### Why It's Worse Than the Socket
- **Network-exposed** — anyone on your LAN (or who compromises any device on your network) can control Docker
- Docker's TCP API has **no authentication by default**
- Even with TLS certificates, it's the same power as the socket — full Docker control
- You'd be opening a port that gives root-equivalent access to anyone who can reach it

### Blast Radius If Compromised
**Total.** Same as Docker socket, but now *any device on the network* can exploit it, not just OpenClaw.

### Reversible?
Yes — close the port. But damage while open could be severe.

### Recommendation: ⛔ NOT RECOMMENDED
Strictly worse than Docker socket mount in every way. The Unraid API exists — use that instead.

---

## Option 6: Portainer (or similar container management UI)

### What It Is
Portainer is a popular web-based Docker management tool that runs as a container. It has its own API that OpenClaw could use programmatically.

### What It Enables
- Create, manage, delete containers via REST API
- Manage stacks (docker-compose-style deployments)
- Monitor resource usage
- Manage networks and volumes
- User/role system with permission controls

### Security Risk Level: 🟡 MEDIUM

### Why It's a Mixed Bag
**Pros:**
- Has its own user/role system (can create a limited account for Omni)
- REST API is well-documented and easy to use
- Provides a nice middle ground between raw Docker and the Unraid API
- You get a web UI too for when you want to manage things manually

**Cons:**
- Portainer itself needs the Docker socket mounted (so it has full Docker access)
- You're adding another attack surface (Portainer has had security vulnerabilities in the past)
- It's another container to maintain and update
- The Unraid API already does most of what Portainer offers

### Blast Radius If Compromised
Depends on the Portainer user's role. An admin Portainer account = full Docker access. A limited account could be scoped to specific containers/operations.

### Reversible?
Yes — delete the Portainer user or stop the Portainer container.

### Recommendation: 🟡 ACCEPTABLE (but probably unnecessary)
Portainer is a fine tool, but since Unraid 7.0+ has a native API with granular permissions, adding Portainer just for API access adds complexity and attack surface without clear benefit. If you already run Portainer for other reasons, using its API is reasonable. Don't install it just for this.

---

## Summary Table

| Option | Risk Level | Blast Radius | Granular Perms? | Recommendation |
|--------|-----------|--------------|-----------------|----------------|
| Docker Socket Mount | 🔴 Critical | Total system | No | ⛔ Not recommended |
| **Unraid GraphQL API** | 🟢 Low-Med | Scoped | **Yes** | ✅ **Strongly recommended** |
| SSH Access | 🔴 High | Total (unless restricted) | Possible | 🟡 Acceptable with restrictions |
| Tailscale | 🟢 Low | N/A (transport) | N/A | ✅ Recommended as transport |
| Docker TCP API | 🔴 Critical | Total + network | No | ⛔ Not recommended |
| Portainer API | 🟡 Medium | Depends on role | Partial | 🟡 Acceptable but unnecessary |

---

## Recommended Setup (What I'd Actually Do)

### Phase 1: Monitoring (Low Risk)
1. Enable the Unraid API (install Connect plugin if not on 7.2+)
2. Create a **read-only** API key: `DOCKER:READ_ANY,INFO:READ_ANY,NOTIFICATIONS:READ_ANY`
3. Give Omni the key and the Unraid host IP
4. Omni can now monitor containers, check system health, report issues

### Phase 2: Container Management (Medium Risk)
1. Expand the API key to include: `DOCKER:UPDATE_ANY` (start/stop/restart)
2. Omni can now restart crashed containers, stop misbehaving ones, etc.
3. Still can't create new containers or delete existing ones

### Phase 3: Full Docker Management (Higher Risk, if desired)
1. Add `DOCKER:CREATE_ANY,DOCKER:DELETE_ANY`
2. Omni can now deploy new containers and remove old ones
3. Still scoped — can't touch the array, filesystem, or other Unraid subsystems

### Optional: Add Tailscale
If you want remote management or tighter network controls, add Tailscale to both the Unraid host and OpenClaw container. Use Tailscale ACLs to restrict which ports OpenClaw can access.

---

## Important Security Notes

1. **The API key is a secret.** Store it securely. Don't put it in plaintext in a file that gets committed to git.

2. **Start small.** Read-only first. You can always expand permissions later. You can't undo a data breach.

3. **The Omnissiah hosts irreplaceable data.** Every permission you grant is a potential attack vector. Prompt injection attacks against AI assistants are real and getting more sophisticated. A scoped API key limits what damage a compromised AI session could do.

4. **Unraid's API is the right tool.** It was literally designed for this — programmatic access with granular permissions. Using Docker socket or SSH is like using a chainsaw when you need a scalpel.

5. **Review regularly.** Check what permissions Omni has every few months. Rotate the API key periodically.

---

*Research conducted 2026-02-12. Unraid API docs: https://docs.unraid.net/API/*
