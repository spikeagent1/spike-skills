# ADAPTER — claude-code

Rendered from `adapters/claude-code/adapter.yaml`; `${...}` is filled at install from `${HOME}/.config/spike-os/claude-code.local.yaml`.
A value marked **UNCONFIRMED** is not attested on this host today: verify it before relying on it, never assume it (F2). A value marked **DEGRADED** is one whose absence is known and whose skill contract already states what it does without it — the skill runs and discloses the reduced state.

## Vocabulary
| Term | Value |
|---|---|
| `owner` | ${OWNER_NAME}, described in ~/.claude/CLAUDE.md and the profile namespace |
| `agent` | the Claude Code session, operating under ~/.claude/CLAUDE.md |
| `owner datastore` | the owner's vault at ${VAULT_ROOT}, indexed by _system/shared-context.pglite |
| `durable memory` | the same vault; ~/.claude/CLAUDE.md is its always-loaded summary |
| `task provider` | the Todoist MCP server when the connector registry lists one, otherwise mirror-only — **DEGRADED** |
| `calendar provider` | the Google Calendar MCP server |
| `mail provider` | the agentmail MCP server for the agent, the Gmail MCP server for the owner — **DEGRADED** (owner half only) |
| `contacts provider` | none configured |
| `owner timezone` | ${OWNER_TZ} |
| `scheduler` | Claude Code /schedule routines, with launchd for host-local jobs |
| `notification channel` | an in-session reply, then the agent inbox, then a routine notification |
| `owner channel` | the interactive Claude Code session |
| `public surfaces` | none unless ${PUBLIC_SURFACES} names one |
| `agent's public journal` | none in this runtime |
| `agent community network` | none in this runtime |
| `agent inbox` | ${AGENT_INBOX} — **UNCONFIRMED** |
| `durable tool paths` | ~/.bun/bin, ~/.local/bin, and ${AGENT_BIN} — **UNCONFIRMED** |
| `credential store` | the macOS keychain, plus per-server env in ~/.claude.json |
| `connector registry` | the union of `claude mcp list` (account-level connectors) and the `mcpServers` blocks of ~/.claude.json (top-level and per-project) |
| `runtime health check` | mcp__gbrain__get_health, or claude mcp list for the registry as a whole |
| `runtime reload` | restart the session, or reconnect one server with /mcp |
| `identity files` | ~/.claude/CLAUDE.md and the profile pages under ${VAULT_ROOT}/profile/ |
| `skills dir` | ~/.claude/skills |
| `activity log` | ${VAULT_ROOT}/ops/activity/ |
| `checkpoint store` | ${VAULT_ROOT}/ops/checkpoints/ |
| `autonomy contract` | ${VAULT_ROOT}/autonomy/ |
| `capabilities` | metadata.spike-os.capabilities on the installed skill, plus the disable-model-invocation flag a never_autonomous tier renders |
| `repo identity` | ${REPO_IDENTITY}, through the gh CLI |
| `proposal workflow` | pull-request review on the repository in hand |
| `journal build toolchain` | none in this runtime |
| `entry schema` | none in this runtime |
| `journal source branch` | none in this runtime |
| `norms directory` | .agents/behaviors/<name>/BEHAVIOR.md, relative to the repo in hand — **UNCONFIRMED** |

## Datastore
Vault root `${VAULT_ROOT}/`: `profile` `people` `agents` `decisions` `autonomy`, and
`projects/<name>/`. Under `ops/`: `journal` `tasks` `calendar` `inbox` `jobs` `activity`
`checkpoints` `notifications`. `conversations` is `${CONVERSATIONS_ROOT}`, a separate root.
Only `profile/` `people/` `projects/` `decisions/` exist in the vault today; `agents/`,
`autonomy/`, every `ops/` path, and `${CONVERSATIONS_ROOT}` are chosen layouts the
installer creates on first write. The vault's own `inbox/` is a **different thing** —
user-approved source captures, cited from `index.md` — so the `inbox` namespace maps to
`ops/inbox/`, never to it.

| Verb | Invocation |
|---|---|
| `read` `search` `list` `timeline` | `mcp__gbrain__get_page` · `search` · `list_pages` · `get_timeline`, on `<ns>/<id>` |
| `write` | `mcp__gbrain__put_page` with `slug` and `content` (full Markdown with frontmatter), then read back |
| `append_timeline` | `mcp__gbrain__add_timeline_entry` with `slug`, `date`, `summary`, optional `detail` |
| `supersede` | put the replacement, then the original with `status: superseded` |

Envelope fields the vault names differently — the adapter maps them, records are never
renamed in `contracts/datastore.md`: `namespace` → `type`, `visibility` → `sensitivity`,
`status: active` → `status: confirmed`, `provenance.source_ids` → `source_ids`. `id` is
the page slug (filename without `.md`); `kind` has no vault field and is written through.

## Providers
Tasks are **mirror-only** until a task provider is registered, and the skill says so
(`contracts/sync.md`); contacts unconfigured; `calendar` and `inbox` reserved, read-only.

## Channels and quiet hours
An in-session reply, then the `agent inbox`, then a routine notification. Quiet hours
are `${QUIET_START}`–`${QUIET_END}` in the `owner timezone`: delivery, not execution.

## Identity files
`~/.claude/CLAUDE.md` and `${VAULT_ROOT}/profile/`, outside the datastore, changed only
through `identity:propose` then `identity:write`. The installer keeps the line
`@~/.claude/spike-os/ADAPTER.md` between `<!-- spike-os:begin -->` and `<!-- spike-os:end -->`
in `CLAUDE.md`, printing the `git -C ~/.claude commit` command rather than running it.

## Skills dir
`~/.claude/skills`, shared with ~100 unrelated skills; the installer writes only into directories carrying a `.spike-os.json` stamp.

## Notes on fallbacks
Every verb has three ordered paths: the gbrain MCP server, then
`${VAULT_ROOT}/bin/gbrain-local` (same subcommands), then the Markdown file directly.
Markdown is canonical and the index is rebuilt from it, so the last path is safe — name
the one that answered. Embeddings are off, so search is keyword-only: prefer exact slugs.
The MCP tool names above come from `gbrain --tools-json` on this host (41 tools, including
`get_timeline` and `get_health`); the configured server binary is missing, so nothing was
round-tripped live — expect the CLI or the file to answer, and say which did.
