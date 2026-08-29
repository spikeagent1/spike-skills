# Runtime-specific inventory

Every concrete runtime fact today's skills name, the neutral term that replaces
it, and where an adapter binds that term. Source for the left three columns and
the citations: the hygiene design's runtime inventory. The right column is
`adapters/vocabulary.yaml` plus the key each `adapters/<runtime>/adapter.yaml`
binds it under; "both" means the openclaw and claude-code adapters each give the
term a value. Line numbers are pre-rewrite and go stale as Tasks 13–20 land —
they locate a passage, they are not a contract.

A skill body naming anything in the first column instead of the second is an
error once `tools/validate_repo.py` gates runtime binding (Task 12).

## Bound terms

| Concrete today | Neutral term | Adapter key | Skills (lines) | Bound by adapter? |
|---|---|---|---|---|
| Spike | `agent` | `vocabulary.agent` | social-agent-practice 8,20-27; the Provenance boilerplate library-wide | yes, both |
| Tapan | `owner` | `vocabulary.owner` | owner-context-onboarding 13; audience-content-engine; daily-task-manager | yes, both — value is `${OWNER_NAME}` |
| Todoist | `task provider` | `vocabulary.task_provider` | daily-task-manager 12,37,42,52,61 | yes, both — OpenClaw binds the healthy live `todoist` MCP server; claude-code retains its own host binding |
| brain, pages, search/query/get, timeline, enrich entities | `owner datastore` | `vocabulary.owner_datastore`, `datastore.verbs` | briefing 12,20-21,37,40,72,90; fact-check 45; conversation-archive | yes, both — plus all 7 verbs mapped |
| recall cursors | `checkpoint store` | `vocabulary.checkpoint_store`, `datastore.paths.checkpoints` | briefing 12,93; social-listening-engagement-loop 54 | yes, both |
| `MEMORY.md`, `memory/`, "canonical memory surface" | `durable memory` | `vocabulary.durable_memory` | owner-dream-cycle 43 | yes, both |
| `ops/tasks.md` | the `tasks` namespace | `datastore.paths.tasks` | daily-task-manager 12,42 | yes, both — a namespace path, not a vocabulary term |
| `conversations/`, `people/` | datastore namespaces | `datastore.paths.*` | conversation-archive 6-7; draft-in-voice 6-7 | yes, both — all 14 namespaces mapped |
| `America/Los_Angeles` | `owner timezone` | `vocabulary.owner_timezone` | owner-dream-cycle 17,58 | yes, both — value is `${OWNER_TZ}` |
| OpenClaw cron | `scheduler` | `vocabulary.scheduler`, top-level `scheduler` | cron-scheduler 12,17,43,85,102 | yes, both |
| wall, wall entry, wall PR | `agent's public journal` | `vocabulary.agents_public_journal` | public-post-workshop 3,8,11,13,19,24,33-42,50,60,84; publish 52 | yes, both — none in claude-code |
| wall, X, Moltbook as destinations | `public surfaces` | `vocabulary.public_surfaces` | publish 17,52; community-management references/surfaces.md | yes, both — `${PUBLIC_SURFACES}` in claude-code |
| Moltbook | `agent community network` | `vocabulary.agent_community_network` | social-agent-onboarding 48; community-management 11,15,16 | yes, both |
| AgentMail, `@agentmail.to` | `agent inbox`, `mail provider` | `vocabulary.agent_inbox`, `vocabulary.mail_provider` | social-agent-onboarding 34,44; community-management 35-41 | yes, both — address is `${AGENT_INBOX}` |
| Telegram | `owner channel`, `notification channel` | `vocabulary.owner_channel`, `vocabulary.notification_channel`, `notification.channels` | social-agent-practice 57-64; cron-scheduler 40; community-management references | yes, both |
| `/data/.local/bin`, "configured private GitHub CLI directory" | `durable tool paths`, `credential store` | `vocabulary.durable_tool_paths`, `vocabulary.credential_store` | social-agent-onboarding 21,24,28 | yes, both |
| OpenClaw MCP server, ChatGPT app connector | `connector registry` | `vocabulary.connector_registry` | mcp-connector-onboarding 12 | yes, both |
| `openclaw doctor`, transport status | `runtime health check` | `vocabulary.runtime_health_check` | mcp-connector-onboarding 102; runtime-handoff-onboarding 8 | yes, both |
| OpenClaw, "gateway restart", "next runtime build" | `runtime reload` | `vocabulary.runtime_reload` | runtime-handoff-onboarding 8; mcp-connector-onboarding 50; skill-library-ops 40,47 | yes, both |
| bootstrap, handoff, soul, identity, user, agent, heartbeat, tool notes | `identity files` | `vocabulary.identity_files`, top-level `identity_files` | runtime-handoff-onboarding 12,95; owner-dream-cycle 14,46 | yes, both — openclaw binds all eight, `TOOLS.md` included |
| `/data/.openclaw/workspace/skills` | `skills dir` | `vocabulary.skills_dir`, top-level `skills_dir` | skill-library-ops templates | yes, both |
| Skill Workshop, proposal IDs | `proposal workflow` | `vocabulary.proposal_workflow` | skill-library-ops 59,79 | yes, both |
| Astro | `journal build toolchain` | `vocabulary.journal_build_toolchain` | public-post-workshop 33-42 | yes, both — none in claude-code |
| `edited_by_human`, "voice-agent Stream entry" | `entry schema` | `vocabulary.entry_schema` | public-post-workshop 33-42 | yes, both — none in claude-code |
| "active site branch" | `journal source branch` | `vocabulary.journal_source_branch` | public-post-workshop 33-42 | yes, both — none in claude-code |
| "commit as Spike" | `repo identity` | `vocabulary.repo_identity` | public-post-workshop 33-42; publish | yes, both |
| `.agents/behaviors/<name>/BEHAVIOR.md` | `norms directory` | `vocabulary.norms_directory` | team-skill-sharing-norm | yes, both — OpenClaw binds `/data/.openclaw/workspace/team-roster/.agents/behaviors/<name>/BEHAVIOR.md`; claude-code retains its own host binding |

## Bound but not yet named by any skill

`calendar provider` (`vocabulary.calendar_provider`, `calendar/` reserved),
`contacts provider` (`vocabulary.contacts_provider`, `people/contact-card`
reserved), and `effects ledger` (`vocabulary.effects_ledger`,
`datastore.paths.effects`) are defined by both adapters and enter the library
when the rewrite adds `contracts/skill-contract.md` M7 records.

## Not bound — removed instead

| Concrete today | Disposition |
|---|---|
| frontmatter `tools: [memory_search, memory_get]` | Deleted; the key is never allowed in frontmatter (social-listening-engagement-loop) |
| `soul-audit` | Dead reference; reworded to "a candidate for explicit owner confirmation in a later interaction; never auto-apply" (owner-dream-cycle 46) |

Eval fixtures are deliberately unchanged: a rewritten skill must still answer a
prompt that says "Todoist".
