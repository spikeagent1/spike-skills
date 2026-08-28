# ADAPTER — openclaw

Rendered from `adapters/openclaw/adapter.yaml`; `${...}` is filled at install
from `${HOME}/.config/spike-os/openclaw.local.yaml`. **UNCONFIRMED** marks a value
no git-owned runtime file states: verify it, never treat it as evidence (F2).

## Vocabulary
| Term | Value |
|---|---|
| `owner` | ${OWNER_NAME}, described in USER.md |
| `agent` | Spike, defined by SOUL.md and IDENTITY.md |
| `owner datastore` | GBrain 0.46.1 at /data/.gbrain/brain.pglite, driven by /data/.local/bin/gbrain |
| `durable memory` | MEMORY.md and memory/<date>.md in the workspace, plus the owner datastore |
| `task provider` | the Todoist connector — **UNCONFIRMED** |
| `calendar provider` | none configured |
| `mail provider` | AgentMail, polled by scripts/check_agentmail.py on a five-minute cron |
| `contacts provider` | none configured |
| `owner timezone` | ${OWNER_TZ} — **UNCONFIRMED** |
| `scheduler` | OpenClaw cron, one job per stable job key, addressed by job id |
| `notification channel` | a Telegram owner DM, which lands in the main session |
| `owner channel` | the Telegram main session, agent:main:main |
| `public surfaces` | the wall, X, and the agent community network |
| `agent's public journal` | the wall, built from site/src/content/stream/ in chughtapan/vibe-blogging |
| `agent community network` | Moltbook, where the agent is claimed and active |
| `agent inbox` | ${AGENT_INBOX} |
| `durable tool paths` | /data/.local/bin and /data/.bun/bin |
| `credential store` | /data/.openclaw/credentials/ |
| `connector registry` | /data/.openclaw/openclaw.json, deep-merged from the git seed on every boot |
| `runtime health check` | openclaw doctor through the spike wrapper, plus gbrain doctor --json |
| `runtime reload` | a deploy, which restarts the gateway and re-seeds the git-owned workspace files |
| `identity files` | SOUL.md, IDENTITY.md, USER.md, AGENTS.md, TOOLS.md, BOOTSTRAP.md, HANDOFF.md, and HEARTBEAT.md under /data/.openclaw/workspace |
| `skills dir` | /data/.openclaw/workspace/skills |
| `effects ledger` | ops/effects/ pages in the owner datastore |
| `checkpoint store` | ops/checkpoints/ pages in the owner datastore |
| `repo identity` | spikeagent1, with GH_CONFIG_DIR pointed at /data/.openclaw/credentials/github-cli |
| `proposal workflow` | a Skill Workshop proposal, applied only on explicit owner approval |
| `journal build toolchain` | Astro, building site/ in chughtapan/vibe-blogging |
| `entry schema` | the stream contract v1 at contracts/stream.v1.schema.json |
| `journal source branch` | main, reached by an unmerged pull request |
| `norms directory` | .agents/behaviors/<name>/BEHAVIOR.md, relative to the repo in hand — **UNCONFIRMED** |

## Datastore
GBrain page slugs. At the brain root: `profile` `people` `agents` `decisions`
`journal`, and `projects/<slug>/`. Under `ops/`: `tasks` `calendar` `inbox` `jobs`
`effects` `checkpoints` `notifications`. `conversations/` is a separate root, so
far empty. One page per record key.

| Verb | Invocation |
|---|---|
| `read` `search` `list` `timeline` | `gbrain get <slug>` · `search <query>` · `list --type <ns> -n <limit>` · `timeline <slug>` |
| `write` | `gbrain put <slug>` with the page on stdin, then read it back |
| `append_timeline` | `gbrain timeline-add <slug> <date> <text>` |
| `supersede` | `gbrain put` the replacement, then the original with `status: superseded` |

## Providers
Tasks are **mirror-only** until a task provider is registered, and the skill says
so (`contracts/sync.md`); calendar and contacts are unconfigured.

## Channels and quiet hours
`notification channel` first (outbound `sendMessage` is not currently enabled — see the
`adapter.yaml` note), then a reply in the main session. Quiet hours are
`${QUIET_START}`–`${QUIET_END}` in the `owner timezone` and govern delivery, not
execution, with the two overrides in `contracts/notifications.md`.

## Identity files
`SOUL.md` `IDENTITY.md` `USER.md` `AGENTS.md` `TOOLS.md` `BOOTSTRAP.md` `HANDOFF.md`
`HEARTBEAT.md` under `/data/.openclaw/workspace`: re-seeded from git on every
boot, outside the datastore, changed only through `identity:propose` then
`identity:write`. `TOOLS.md` is the deployment's tool notes, not policy.

## Skills dir
`/data/.openclaw/workspace/skills`. The installer stages into
`dist/openclaw/workspace/skills/` and prints the copy step.

## Notes on fallbacks
The gbrain CLI is the only way into the datastore here — there is no MCP
fallback, so a failed `gbrain doctor --json` is a blocked phase to report (D2),
never a reason to answer from memory (P2). Verb spellings come from GBrain 0.18.2
on the owner's host; the volume runs 0.46.1, so re-check after the next runtime
build. Hand edits to the volume's config are lost on deploy — use the CLI.
