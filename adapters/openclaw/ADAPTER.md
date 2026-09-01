# ADAPTER — openclaw

Rendered from `adapters/openclaw/adapter.yaml`; `${...}` is filled at install
from `${HOME}/.config/spike-os/openclaw.local.yaml`. **UNCONFIRMED** marks a value
no git-owned runtime file states: verify it, never treat it as evidence (F2).
**DEGRADED** marks one whose absence is known and whose skill contract
states what it does without it; the installer installs such a skill with a printed note.

## Vocabulary
| Term | Value |
|---|---|
| `owner` | ${OWNER_NAME}, described in USER.md |
| `agent` | Spike, defined by SOUL.md and IDENTITY.md |
| `owner datastore` | GBrain 0.46.28 at /data/.gbrain/brain.pglite, driven by /data/.local/bin/gbrain and registered as the gbrain MCP server |
| `durable memory` | MEMORY.md and memory/<date>.md in the workspace, plus the owner datastore |
| `task provider` | the Todoist MCP server registered at mcp.servers.todoist; live health check passes |
| `calendar provider` | none configured |
| `mail provider` | AgentMail, polled by scripts/check_agentmail.py on a five-minute cron |
| `contacts provider` | none configured |
| `owner timezone` | ${OWNER_TZ} — owner-supplied in the overrides file |
| `scheduler` | OpenClaw cron, one job per stable job key, addressed by job id |
| `notification channel` | a Telegram owner DM, which lands in the main session |
| `owner channel` | the Telegram main session, agent:main:main |
| `public surfaces` | the wall, X, and the agent community network |
| `agent's public journal` | the wall, built from site/src/content/stream/ in ${DEPLOY_REPO} |
| `agent community network` | Moltbook, where the agent is claimed and active |
| `agent inbox` | ${AGENT_INBOX} |
| `durable tool paths` | /data/.local/bin and /data/.bun/bin |
| `credential store` | /data/.openclaw/credentials/ |
| `connector registry` | /data/.openclaw/openclaw.json, deep-merged from the git seed on every boot |
| `runtime health check` | openclaw doctor through the spike wrapper, plus gbrain doctor --json |
| `runtime reload` | a deploy, which restarts the gateway and re-seeds the git-owned workspace files |
| `identity files` | SOUL.md, IDENTITY.md, USER.md, AGENTS.md, TOOLS.md, BOOTSTRAP.md, HANDOFF.md, and HEARTBEAT.md under /data/.openclaw/workspace |
| `skills dir` | /data/.openclaw/workspace/skills |
| `activity log` | ops/activity/ pages in the owner datastore |
| `checkpoint store` | ops/checkpoints/ pages in the owner datastore |
| `autonomy contract` | autonomy/ pages in the owner datastore |
| `capabilities` | metadata.spike-os.capabilities on the staged skill, beside metadata.openclaw.requires |
| `repo identity` | spikeagent1, with GH_CONFIG_DIR pointed at /data/.openclaw/credentials/github-cli |
| `proposal workflow` | a Skill Workshop proposal, applied only on explicit owner approval |
| `journal build toolchain` | Astro, building site/ in ${DEPLOY_REPO} |
| `entry schema` | the stream contract v1 at contracts/stream.v1.schema.json |
| `journal source branch` | main, reached by an unmerged pull request |
| `norms directory` | /data/.openclaw/workspace/team-roster/.agents/behaviors/<name>/BEHAVIOR.md |

## Datastore
GBrain page slugs. At the brain root: `profile` `people` `agents` `decisions`
`journal` `autonomy`, and `projects/<slug>/`. Under `ops/`: `tasks` `calendar` `inbox`
`jobs` `activity` `checkpoints` `notifications`. `conversations/` is a separate root, so
far empty. One page per record key.

| Verb | Invocation |
|---|---|
| `read` `search` `list` `timeline` | `gbrain get <slug>` · `search <query>` · `list --type <ns> --limit <limit>` · `timeline <slug>` |
| `write` | `gbrain put <slug>` with the page on stdin, then read it back |
| `append_timeline` | `gbrain timeline-add <slug> <date> <text>` |
| `supersede` | `gbrain put` the replacement, then the original with `status: superseded` |

## Providers
Tasks use the live Todoist MCP server. If its tools are unavailable in a turn,
the skill reports that phase blocked rather than claiming a provider write;
calendar and contacts are unconfigured.

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
The gbrain CLI is the adapter's canonical verb binding, and the live runtime
also registers a healthy gbrain MCP server. If neither route is available, the
phase is blocked (D2), never a reason to answer from memory (P2). Verb spellings
were confirmed against the live GBrain 0.46.28 CLI. Hand edits to the volume's
config are lost on deploy — use the CLI.
