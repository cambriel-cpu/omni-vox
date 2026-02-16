---
name: obsidian-rest-api
description: Use when reading, writing, searching, or managing notes in the Obsidian vault via the Local REST API plugin
---

# Obsidian Local REST API

Read, write, search, and manage notes in the Obsidian vault via HTTP.

## Connection

```
BASE=https://192.168.68.51:27124
API_KEY=$(cat /root/.openclaw/obsidian-rest-api-key)
AUTH="Authorization: Bearer $API_KEY"
```

**Always use `-k` with curl** — the cert is self-signed and issued for `localhost`, not the LAN IP.

## Quick Reference

| Operation | Method | Endpoint | Content-Type |
|-----------|--------|----------|-------------|
| List vault root | GET | `/vault/` | — |
| List directory | GET | `/vault/{dir}/` | — |
| Read note (markdown) | GET | `/vault/{path}` | — |
| Read note (JSON+meta) | GET | `/vault/{path}` | Accept: `application/vnd.olrapi.note+json` |
| Get document map | GET | `/vault/{path}` | Accept: `application/vnd.olrapi.document-map+json` |
| Create/replace note | PUT | `/vault/{path}` | `text/markdown` |
| Append to note | POST | `/vault/{path}` | `text/markdown` |
| Patch note (heading/block/frontmatter) | PATCH | `/vault/{path}` | `text/markdown` or `application/json` |
| Delete note | DELETE | `/vault/{path}` | — |
| Simple text search | POST | `/search/simple/?query=X` | — |
| Advanced search (JsonLogic) | POST | `/search/` | `application/vnd.olrapi.jsonlogic+json` |
| Dataview query | POST | `/search/` | `application/vnd.olrapi.dataview.dql+txt` |
| List commands | GET | `/commands/` | — |
| Execute command | POST | `/commands/{id}/` | — |
| Get active file | GET | `/active/` | — |
| Update active file | PUT | `/active/` | `text/markdown` |
| Periodic note (current) | GET | `/periodic/{period}/` | — |
| Periodic note (by date) | GET | `/periodic/{period}/{year}/{month}/{day}/` | — |
| Open file in UI | POST | `/open/{path}` | — |
| Server status | GET | `/` | — |

## Common Patterns

### Read a note
```bash
curl -k -s -H "$AUTH" "$BASE/vault/My%20Note.md"
```

### Read note with metadata (tags, frontmatter, stat)
```bash
curl -k -s -H "$AUTH" -H "Accept: application/vnd.olrapi.note+json" "$BASE/vault/My%20Note.md"
```
Returns: `{ content, frontmatter, tags, stat: { ctime, mtime, size }, path }`

### Create or replace a note
```bash
curl -k -s -X PUT -H "$AUTH" -H "Content-Type: text/markdown" \
  -d '# Title\n\nContent here' \
  "$BASE/vault/folder/My%20Note.md"
```
PUT creates parent folders automatically. Returns 204 on success.

### Append to a note
```bash
curl -k -s -X POST -H "$AUTH" -H "Content-Type: text/markdown" \
  -d '\n\n## New Section\nAppended content' \
  "$BASE/vault/My%20Note.md"
```

### Patch: insert relative to heading
```bash
curl -k -s -X PATCH -H "$AUTH" \
  -H "Content-Type: text/markdown" \
  -H "Operation: append" \
  -H "Target-Type: heading" \
  -H "Target: Heading 1::Subheading" \
  -d 'Content under subheading' \
  "$BASE/vault/My%20Note.md"
```
Heading delimiter is `::` by default (configurable via `Target-Delimiter` header).

### Patch: set frontmatter field
```bash
curl -k -s -X PATCH -H "$AUTH" \
  -H "Content-Type: application/json" \
  -H "Operation: replace" \
  -H "Target-Type: frontmatter" \
  -H "Target: status" \
  -H "Create-Target-If-Missing: true" \
  -d '"done"' \
  "$BASE/vault/My%20Note.md"
```

### Simple text search
```bash
curl -k -s -X POST -H "$AUTH" \
  "$BASE/search/simple/?query=my%20search%20term&contextLength=100"
```
Returns: `[{ filename, score, matches: [{ match: {start, end}, context }] }]`

### JsonLogic search (find by tag)
```bash
curl -k -s -X POST -H "$AUTH" \
  -H "Content-Type: application/vnd.olrapi.jsonlogic+json" \
  -d '{"in": ["myTag", {"var": "tags"}]}' \
  "$BASE/search/"
```

### JsonLogic search (find by frontmatter value)
```bash
curl -k -s -X POST -H "$AUTH" \
  -H "Content-Type: application/vnd.olrapi.jsonlogic+json" \
  -d '{"==": [{"var": "frontmatter.status"}, "active"]}' \
  "$BASE/search/"
```

### List directory contents
```bash
curl -k -s -H "$AUTH" "$BASE/vault/Projects/"
```
Returns: `{ files: ["note.md", "subfolder/"] }` — directories end with `/`.

### Get document map (discover PATCH targets)
```bash
curl -k -s -H "$AUTH" \
  -H "Accept: application/vnd.olrapi.document-map+json" \
  "$BASE/vault/My%20Note.md"
```
Returns: `{ headings: [...], blocks: [...], frontmatterFields: [...] }`

### Create folders
No explicit folder creation endpoint. PUT a note with a path like `folder/subfolder/note.md` and folders are created automatically.

## PATCH Operations Reference

PATCH supports three operation types via the `Operation` header:
- **append** — add content after the target
- **prepend** — add content before the target
- **replace** — replace the target's content

Target types via `Target-Type` header:
- **heading** — target a heading (use `::` delimiter for nested: `H1::H2::H3`)
- **block** — target a block reference (e.g. `2d9b4a` for `^2d9b4a`)
- **frontmatter** — target a YAML frontmatter field

Optional headers:
- `Target-Delimiter` — change heading delimiter (default `::`)
- `Trim-Target-Whitespace` — trim whitespace from target value (`true`/`false`)
- `Create-Target-If-Missing` — create frontmatter field if it doesn't exist

For table manipulation: use `application/json` content type with `[["col1", "col2"]]` array format when targeting a block-referenced table.

## Periodic Notes

Requires the Periodic Notes plugin. Periods: `daily`, `weekly`, `monthly`, `quarterly`, `yearly`.

- Current period: `/periodic/{period}/`
- Specific date: `/periodic/{period}/{year}/{month}/{day}/`

All support GET (read), PUT (replace), POST (append), PATCH (partial update), DELETE.

## Search Details

### Simple search (`/search/simple/`)
- Query param: `?query=text&contextLength=100`
- Returns filename, score, and match contexts
- Uses Obsidian's built-in search

### Advanced search (`/search/`)
Two content types:
- `application/vnd.olrapi.jsonlogic+json` — JsonLogic queries against note metadata
  - Extra operators: `glob` and `regexp` for pattern matching
  - Searches against NoteJson schema (content, frontmatter, tags, stat, path)
- `application/vnd.olrapi.dataview.dql+txt` — Dataview DQL queries (requires Dataview plugin)
  - Only TABLE-type queries supported

## Important Notes

- **URL-encode paths** — spaces become `%20`, special chars must be encoded
- **Self-signed TLS** — always use `curl -k`; cert is for `localhost` not the LAN IP
- **Auth required** on all endpoints except `GET /`
- **204 = success** for PUT/POST/DELETE (no response body)
- **Directories trail with `/`** in listing responses
- **LiveSync integration** — writes via this API go through Obsidian properly, triggering LiveSync to all devices
- **Never write directly to CouchDB or filesystem** — always use this API
- **Bind address** — plugin defaults to `127.0.0.1`; must be changed to `0.0.0.0` in plugin settings for LAN access (Docker port mapping requires this)

## Known Bugs & Rate Limiting

- **⚠️ Spaces in NEW folder names hang PUT indefinitely** — when creating a new folder via PUT, folder names with spaces (e.g. `Omni%20Skills`) cause the request to hang and never return. Workaround: use names without spaces (e.g. `OmniSkills`), then rename in Obsidian UI if needed.
- **Rapid-fire writes can lock the API** — sending many PUT requests without delays causes the plugin to stop responding to all write operations (GETs still work). If this happens, restart the Obsidian container. **Always add `sleep 2` between batch writes.**
- **After API lockup, container restart required** — toggling the plugin may not be enough; a full container restart clears the stuck state.

## Batch Write Pattern

When writing multiple files, use this safe pattern:
```bash
for file in list_of_files; do
  curl -k -s -m 30 -o /dev/null -w "%{http_code}" -X PUT \
    -H "$AUTH" -H "Content-Type: text/markdown" \
    --data-binary @"$file" \
    "$BASE/vault/$target_path"
  echo " $target_path"
  sleep 2  # REQUIRED — prevents API lockup
done
```

## Common Mistakes

- Forgetting `-k` flag → TLS handshake failure
- Forgetting to URL-encode spaces in paths → 404
- Using GET for search (it's POST)
- Missing `Content-Type: text/markdown` on PUT/POST → 400
- PATCH without all 3 required headers (Operation, Target-Type, Target) → 400
- Rapid-fire PUTs without delay → API lockup requiring container restart
- Spaces in new folder names → PUT hangs forever (use camelCase or hyphens)
