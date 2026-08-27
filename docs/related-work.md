# Related work: a personal OS run by agents

This survey grounds the personal-OS direction for spike-skills: a PalmOS-shaped design where core apps (calendar, contacts, memos, todos, home) share one datastore, a launcher/home screen routes between them, and a HotSync-style sync layer reconciles state with external providers — running on two runtimes, OpenClaw and Claude Code. It was compiled 2026-08-27 across seven areas: skill packaging standards, agent-OS/personal-OS projects, shared memory and datastore contracts, routing and dispatch, sync, permission and capability models, and evaluating skill libraries.

Every row below ends in one of three verdicts:

- **BORROW** — take the mechanism, not the implementation.
- **AVOID** — the approach doesn't fit this design.
- **SOLVED** — reuse the existing artifact or spec; don't rebuild it.

The findings feed directly into the design revisions recorded in the last section of this document.

## A.1 Skill packaging standards

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [Agent Skills spec](https://agentskills.io/specification) | Six keys: `name` (≤64, = dir), `description` (≤1024), `license`, `compatibility` (≤500), `metadata` (str→str), `allowed-tools` (experimental); tiers ~100 tok metadata / <5k body / on-demand files; refs one level deep; `skills-ref validate`. | SOLVED | Portable core; OS keys go under `metadata.<ns>`. |
| [Claude Code skills](https://code.claude.com/docs/en/skills) | `when_to_use` (combined with description, 1,536-char cap in the listing), `argument-hint`, `disable-model-invocation`, `user-invocable`, `allowed-tools` (per-turn, not trust-gated — "a repo skill can grant itself broad tool access"), `disallowed-tools`, `model`, `effort`, `context: fork`, `hooks`, `paths`, `metadata` (ignored by Claude Code). | BORROW | Adapter-emitted keys; not a security boundary. |
| [OpenClaw skills](https://docs.openclaw.ai/tools/skills) / [ClawHub skill format](https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md) | `metadata.openclaw.requires.{env,bins,anyBins,config}`, `envVars`, `always`, `os`, `install[]`, top-level `version`; per-agent allowlist is the final set; XML injection with `skills.limits.maxSkillsPromptChars` (silent truncation); ClawHub checks declared-vs-actual. | BORROW | `requires.*`, budget check, declared-vs-actual lint. |
| [Hermes skills](https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills) | `metadata.hermes.{related_skills, requires_tools, fallback_for_tools, …}`, three-level loading (`skills_list` ~3k tok → `skill_view`), trust levels, `/learn`. | BORROW | `related_skills`, conditional visibility. |
| [OpenAI Codex](https://developers.openai.com/api/docs/guides/tools-skills) / [openai/skills openai_yaml.md](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/references/openai_yaml.md) | agentskills.io frontmatter plus sidecar `agents/openai.yaml` (`interface.*`, `policy.allow_implicit_invocation`). | BORROW | Sidecar pattern. |
| [Cursor rules](https://cursor.com/docs/context/rules) | `globs`, `alwaysApply` ("be miserly"). | BORROW | — |
| [superpowers](https://github.com/obra/superpowers) / [gstack SKILL.md](https://github.com/garrytan/gstack/blob/main/SKILL.md) | gstack router skill (rule table then fallthrough); `SKILL.md.tmpl` generation. | BORROW | Dispatcher + generated SKILL.md. |
| [Claude Code plugin.json](https://code.claude.com/docs/en/plugins) / [issue #48864](https://github.com/anthropics/claude-code/issues/48864) | No dependency declarations anywhere; skill→skill refs are inferred by the model, not declared ([Anthropic blog](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills)). | AVOID (as dependency model) | Dispatcher owns them. |

**Note:** no standard declares reads/writes/effects per skill. Nearest analogues: `allowed-tools`, OpenClaw's `requires.*`, MCP annotations, A2A `securityRequirements`.

## A.2 Agent-OS / personal-OS projects

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [AIOS](https://arxiv.org/abs/2403.16971) | Kernel with scheduler, context/memory/storage/tool/access managers. | AVOID (architecture) | Keep the memory-vs-storage split and access-manager vocabulary. |
| [Karpathy LLM OS](https://campedersen.com/llm-os) / [LLM Wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | Paging framing; `raw/` immutable + `wiki/` compiled + `log.md` + `lint`. | BORROW | Lint op, raw-vs-compiled split. |
| [OpenClaw memory architecture](https://docs.openclaw.ai/concepts/memory-architecture) / [cron jobs](https://docs.openclaw.ai/automation/cron-jobs) / [heartbeat](https://docs.openclaw.ai/gateway/heartbeat) | Five memory tiers; provenance in unforgeable SQLite columns (origin `owner\|agent\|untrusted\|system`, session kind `interactive\|cron\|heartbeat\|sub-agent`, supersession keys); only dreaming writes curated core; automation sessions produce no durable candidates; trigger injection ≥0.72; intents `pending→armed→fired→done/cancelled/expired`. | SOLVED on OpenClaw | BORROW the invariants for both runtimes. |
| [Letta/MemGPT memory blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks) | Blocks `label, description, value, limit(2000), read_only`; LWW, no provenance. | BORROW shape for home block; AVOID as store | — |
| [Mem0/OpenMemory](https://docs.mem0.ai/api-reference/memory/get-memory) | `replaced_by, lifecycle_state, expiration_date, synthesized`. | BORROW | Fields. |
| [Zep/Graphiti](https://arxiv.org/html/2501.13956v1) | Bitemporal `valid_at/invalid_at`; LLM contradiction check. | BORROW fields; AVOID LLM-on-write | — |
| [Hindsight](https://hindsight.vectorize.io/blog/2026/07/16/bank-strategy-agent-memory) / [paper](https://arxiv.org/pdf/2512.12818) | Hard isolation for untrusted; unstable bank IDs fragment memory. | BORROW | Partition rule. |
| [Honcho](https://github.com/plastic-labs/honcho) | Peers/sessions/dialectic. | AVOID (for now) | — |
| [Cognee](https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory) | ECL, `memify`, `ontology_valid`. | AVOID | — |
| [gbrain](https://github.com/garrytan/gbrain/blob/master/docs/GBRAIN_V0.md) | Pages `slug,type,title,frontmatter`; compiled_truth + append-only timeline; typed links; page_versions; soft deletes; stale alert; git canonical → PGLite; CLI/MCP parity tests; OAuth scopes. | SOLVED | Datastore substrate. |
| [Basic Memory](https://docs.basicmemory.com/reference/mcp-tools-reference) | Inline `- [category] content #tag`, `- relation [[Entity]]`, `memory://`, `permalink`. | BORROW | Syntax. |
| [Khoj](https://github.com/khoj-ai/khoj) | AGPL app. | AVOID | — |
| [Anthropic Managed Agents memory](https://sdtimes.com/anthropic/anthropic-adds-memory-to-claude-managed-agents/) | Files-as-memory + Dreaming. | BORROW | Confirms markdown-as-DB. |
| ["Agent OS" market term](https://cortexprism.io/blog/open-source-ai-agent-os-2026-landscape) | Branding. | AVOID | — |

## A.3 Shared memory / datastore contracts

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [MCP memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | Entities/relations JSONL, no provenance. | AVOID | — |
| [MCP roots](https://modelcontextprotocol.io/specification/2025-06-18/client/roots) | Root URIs; servers respect boundaries. | BORROW | Namespaces as roots. |
| [MCP resource annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) | `audience, priority, lastModified`. | BORROW (minor) | — |
| [OpenAI Agents SDK Sessions](https://openai.github.io/openai-agents-python/sessions/) | — | AVOID | — |
| [MemClaw "Governed Shared Memory"](https://arxiv.org/html/2606.24535v1) | `visibility_scope ∈ {agent-local, team-shared, tenant-global, restricted}`, `supersedes_id`, `derived_from`, `source_system`; four failure modes (leakage, stale propagation, contradiction persistence, provenance collapse); ArgusFleet `leak_rate, miss_rate, stale-read, chain completeness`. | BORROW | Envelope + datastore eval categories. |
| [StateFuse](https://arxiv.org/html/2607.05844v1) | Claim keyed `(namespace, subject, predicate)`, union merge, ConflictSet at projection, retractions. | BORROW | — |
| [ProjectMem](https://arxiv.org/html/2606.12329v1) / [ESAA](https://arxiv.org/pdf/2606.23752) | Append-only event log, projections. | BORROW | — |
| [Eywa](https://arxiv.org/abs/2605.30771) | Evidence stored before derivation; zero-LLM retrieval. | BORROW | Split. |
| [Always-On Agents survey](https://arxiv.org/abs/2606.30306) | Six axes (authority, scope, mutability, provenance, recoverability, actionability); AOEP-v0. | BORROW | Checklist. |

## A.4 Routing / dispatch

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [Claude Code listing](https://code.claude.com/docs/en/skills) / [Anthropic lessons](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) | Listing at session start; 1,536-char cap; `paths`; PreToolUse hook usage telemetry finds under-triggering; "a skill that restates what Claude would do by default adds context without adding value". | SOLVED (level-0); BORROW telemetry | — |
| [Anthropic best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) | Third-person, what+when, "pushy" descriptions (measured under-triggering); risk is confusion between near descriptions. | BORROW | Near-miss evals. |
| [OpenClaw injection](https://docs.openclaw.ai/tools/skills) | Budget-aware XML listing. | SOLVED | — |
| [Hermes three-level](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) | Category→skill. | BORROW | — |
| [gstack router](https://github.com/garrytan/gstack/blob/main/SKILL.md) | Precedence rules first. | BORROW | — |
| [semantic-router](https://github.com/aurelio-labs/semantic-router) | Route = name + utterances. | BORROW | Pre-filter past ~100 skills. |
| [RouteLLM](https://github.com/lm-sys/routellm) | Model-tier routing. | AVOID | — |
| [ToolRet](https://arxiv.org/abs/2503.01763) | Retrieval bottleneck past ~100 tools. | BORROW | Insight. |
| [AnyTool/ToolLLM](https://arxiv.org/html/2307.16789v2) / [Tool-RAG](https://next.redhat.com/2025/11/26/tool-rag-the-next-breakthrough-in-scalable-ai-agents/) / [Tool-RAG paper](https://arxiv.org/html/2604.00835v1) | Hierarchical retrieval + reflection. | BORROW | — |
| [Routing-eval formats](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) (skill-creator trigger set, 20 queries, 60/40, 3 runs, ≤5 iters) / [promptfoo `skill-used`](https://www.promptfoo.dev/docs/guides/test-agent-skills/) / [control-plane evals](https://dikrana.dev/blog/claude-code-agent-evals/) | Trigger-set and cross-runtime eval formats. | BORROW | `{query, should_trigger}` export. |

## A.5 Sync (HotSync conduit pattern)

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [Palm HotSync](https://github.com/jichu4n/palm-sync/blob/master/docs/how-palm-os-hotsync-works.md) / [conflict resolution](https://ipsit.bu.edu/nislab/theses/ska/node11.html) | Conduit per DB; dirty/deleted flags; fast sync only with same PC; conflict → duplicate on both sides. | BORROW; AVOID two-party assumption | — |
| [RFC 6578](https://datatracker.ietf.org/doc/html/rfc6578) (CalDAV/CardDAV) | `sync-token`, `sync-collection`, etag tuples. | SOLVED | — |
| [vdirsyncer](https://vdirsyncer.pimutils.org/en/stable/config.html) | (href, etag) status; UID identity; never auto-merge; `conflict_resolution`; `partial_sync: revert`. | SOLVED/BORROW | — |
| [Todoist Sync API](https://developer.todoist.com/sync/v8/) / [v1](https://developer.todoist.com/api/v1/) | `sync_token`, command `uuid` idempotency, `temp_id_mapping`. | BORROW | — |
| [Replicache](https://doc.replicache.dev/concepts/how-it-works) | mutationID, cookie deltas, rebase/replay. | BORROW | Loop. |
| [Zero](https://zero.rocicorp.dev/docs/custom-mutators) | Server-side mutators own conflict policy. | BORROW | Pattern. |
| [Automerge](https://automerge.org/docs/reference/documents/conflicts/) / ElectricSQL | CRDTs. | AVOID (for provider sync) | — |

## A.6 Permission / capability models

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [Claude Code permissions](https://code.claude.com/docs/en/skills) / [permission modes guide](https://thepromptshelf.dev/blog/claude-code-permission-modes-complete-guide-2026/) | `Tool(pattern)` rules, deny→ask→allow, modes. | BORROW syntax; AVOID as boundary | — |
| [MCP tool annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) / [announcement](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) | `readOnlyHint destructiveHint idempotentHint openWorldHint`, pessimistic defaults, untrusted unless trusted server. | BORROW | The hint vocabulary. |
| [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/) | Tool guardrails/tripwire. | BORROW | Pattern. |
| [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/agents/tools/tool-approval) | `always_require/never_require` on the tool. | BORROW | — |
| [A2A Agent Card](https://a2a-protocol.org/latest/specification/) | `AgentSkill{tags, examples, securityRequirements}`. | BORROW | Fields. |
| [Tracked Capabilities](https://arxiv.org/html/2603.00991v2) | Resource classes fs/exec/network/classified, attenuation. | BORROW | — |
| [Lingering Authority](https://arxiv.org/pdf/2606.22504) / [OCAP agents](https://apartresearch.com/project/ocap-agents) | Revocable, time-bound grants. | BORROW | — |
| [Computer-use safety](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) | Confirm before consequential effects. | BORROW | — |
| [Permission manifests](https://arxiv.org/abs/2601.02371) / [agent-manifest](https://github.com/agent-manifest/agent-manifest) | Resource×action declaration layer. | BORROW | Shape. |
| [Supply chain](https://arxiv.org/abs/2604.02837) ([Snyk ToxicSkills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/), [Unit42](https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/)) | 13.4% critical of 3,984 ClawHub skills; single-approval persistent trust is the flaw. | AVOID | — |

## A.7 Evaluating skill libraries

| Project | What it defines | Verdict | Take |
|---|---|---|---|
| [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) | `evals.json`, `grading.json`, `benchmark.json`, with/without, trigger loop, non-discriminating warning. | SOLVED/BORROW | Formats. |
| [promptfoo](https://www.promptfoo.dev/docs/guides/test-agent-skills/) | Cross-runtime `skill-used`. | BORROW | For OpenClaw parity. |
| [Anthropic telemetry](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) | PreToolUse usage logging. | BORROW | — |
| [Control-plane evals](https://dikrana.dev/blog/claude-code-agent-evals/) / [cc-plugin-eval](https://github.com/sjnims/cc-plugin-eval) | No-model layer. | BORROW | — |
| [danielsogl/skills](https://github.com/danielsogl/skills) | Worked +16pp example. | BORROW | Template. |
| ArgusFleet / AOEP (see A.3 above) | Datastore-level metrics. | BORROW | — |
| inspect-ai / braintrust | Eval frameworks considered; no URL given in source material. | AVOID | Unnecessary. |

## Implications for the design

### (a) Recommendations (confirm / change)

1. **Confirm: shared datastore with declared namespaces — implement it on gbrain's page model.** Typed pages (`type: calendar-event | contact | memo | todo`) with compiled_truth + append-only timeline give provenance and a stale-flag for free (<https://github.com/garrytan/gbrain/blob/master/docs/GBRAIN_V0.md>). Do not write a second store.
2. **Change: namespace declarations must answer the six Always-On axes** (authority, scope, mutability, provenance, recoverability, actionability) (<https://arxiv.org/abs/2606.30306>). A namespace that is "untrusted import" must be a hard partition, not a tag (<https://hindsight.vectorize.io/blog/2026/07/16/bank-strategy-agent-memory>).
3. **Confirm: dispatcher skill — model it on gstack's router** (rule table first, model judgment second) and keep every core-app skill's `description + when_to_use` ≤1,536 chars so Claude Code doesn't truncate (<https://code.claude.com/docs/en/skills>), and the OpenClaw XML block stays under `maxSkillsPromptChars` (<https://docs.openclaw.ai/tools/skills>). Reuse the trigger-eval "should" queries as semantic-router utterances for a local pre-filter if the library grows past ~100 (<https://arxiv.org/abs/2503.01763>).
4. **Change: capability model = MCP's four annotation hints + resource list, under `metadata`.** The industry has converged on `readOnlyHint/destructiveHint/idempotentHint/openWorldHint` (<https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/>). Enforcement happens in the datastore adapter, not in frontmatter (annotations are "untrusted" by spec).
5. **Change: mark side-effecting skills `disable-model-invocation: true`** (Claude Code) and mirror with `policy.allow_implicit_invocation: false` / OpenClaw's equivalent; "you don't want Claude deciding to deploy because your code looks ready" (<https://code.claude.com/docs/en/skills>). Sync conduits and "send" actions are exactly these.
6. **Confirm: per-runtime adapters — but generate them from one manifest.** OpenClaw wants `metadata.openclaw.requires.*`/`os`/`always`; Codex wants `agents/openai.yaml`; Claude Code wants `paths`/`when_to_use`. gstack's `SKILL.md.tmpl` shows generation is the sane way to keep 30 skills consistent (<https://github.com/garrytan/gstack/blob/main/SKILL.md.tmpl>).
7. **Adopt OpenClaw's two memory-write invariants across both runtimes:** only a consolidation pass writes curated state, and cron/heartbeat/sub-agent sessions cannot promote durable records (<https://docs.openclaw.ai/concepts/memory-architecture>). The Claude Code adapter has no such rule natively — implement it in the datastore.
8. **Sync: build conduits as vdirsyncer-style status files + RFC 6578 for DAV, sync_token + idempotent command UUIDs for Todoist-class APIs.** Never auto-merge; duplicate or surface a ConflictSet (<https://vdirsyncer.pimutils.org/en/stable/config.html>, <https://arxiv.org/html/2607.05844v1>). Skip CRDTs for provider sync.
9. **Eval runner: adopt skill-creator's `evals.json`/`grading.json`/`benchmark.json` formats and promptfoo's `skill-used` assertion**, so trigger evals run unchanged on both runtimes (<https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md>, <https://www.promptfoo.dev/docs/guides/test-agent-skills/>). Add a control-plane layer (no model call) and a datastore layer (leak_rate/miss_rate/stale-read).
10. **Home screen = a Letta-style fixed-size block** (label/value/limit) rendered at session start with agenda + counts, rebuilt by a projection, never edited in place by skills (<https://docs.letta.com/guides/core-concepts/memory/memory-blocks>).
11. **Add a `lint` operation** over the vault (dangling links, stale compiled_truth, records missing envelope fields), per Karpathy's LLM-wiki pattern (<https://github.com/Astro-Han/karpathy-llm-wiki>).
12. **Treat skill install as untrusted every load**: re-run a declared-vs-actual check (ClawHub's approach) against the capability manifest; single-approval persistent trust is the named structural flaw (<https://arxiv.org/abs/2604.02837>).

### (b) Frontmatter keys to adopt (not invent)

- Portable core (agentskills.io): `name, description, license, compatibility, metadata, allowed-tools`.
- Under `metadata.<your-ns>` (reusing existing names): `version` (OpenClaw/Hermes), `tags`, `related_skills`, `requires_tools`, `fallback_for_tools` (Hermes), `requires.env/bins/config`, `os`, `always`, `install` (OpenClaw), `globs`/`paths` + `alwaysApply` (Cursor/Claude Code), `examples` (A2A AgentSkill), plus the effect hints `readOnlyHint, destructiveHint, idempotentHint, openWorldHint` (MCP).
- Claude-Code-only, emitted by the adapter: `when_to_use, disable-model-invocation, user-invocable, paths, context: fork, hooks, model, effort`.
- Codex-only sidecar: `agents/openai.yaml` → `interface.display_name, interface.short_description, policy.allow_implicit_invocation`.

### (c) Record-envelope fields common across memory systems

`id` (+ `permalink`/`claim_ref` semantic handle) · `namespace`/`bank`/`visibility_scope` (MemClaw enum `agent-local | team-shared | tenant-global | restricted`) · `created_at` / `updated_at` · `observed_at` vs `valid_at`/`invalid_at` (bitemporal; Zep) · `origin` ∈ `owner | agent | untrusted | system` (OpenClaw) + `source`/`source_system` ref · `session_kind` · `confidence` (StateFuse; Hindsight opinion vs world) · `synthesized`/`derived_from` (mem0/MemClaw/Eywa) · `supersedes_id` / `replaced_by` (MemClaw/mem0) · `lifecycle_state`/`status` (mem0/MemClaw; OpenClaw intents `pending→armed→fired→done/cancelled/expired`) · `expiration_date` · `importance` (OpenClaw). Sync-specific additions: `dirty`, `deleted`, per-provider `{external_id, etag|version, last_synced_with}`.

### (d) Sync ID / conflict consensus

Stable internal UID (vdirsyncer/iCalendar UID) + per-provider external id and version token (etag / sync_token / mutationID) stored in a status table; per-record dirty/deleted flags; fast path uses flags only when "last synced with" matches, otherwise full compare (HotSync); writes carry idempotent command UUIDs and temp-id mapping (Todoist); provider is authoritative and local pending ops replay after readback (Replicache/Zero); conflicts are never auto-merged — either duplicate (HotSync), pick a side by policy (vdirsyncer `a wins`), or surface a ConflictSet (StateFuse). LWW only for fields with no user-authored content.

### (e) Effect-type enum to adopt

MCP ToolAnnotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` with the spec's pessimistic defaults (<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>). Pair each with a resource list drawn from the ocap literature — `fs` (scoped to declared namespace roots, cf. MCP roots), `exec` (whitelist), `network` (hostnames), `classified` (owner-private data) (<https://arxiv.org/html/2603.00991v2>) — and an approval mode on the capability (`always_require | never_require`, Microsoft AF). That gives a closed vocabulary without a new taxonomy.

### (f) Risks / anti-patterns others hit

- Descriptions too similar between sibling skills fire the wrong one; under-triggering is the measured default (skill-creator, <https://www.kdnuggets.com/anthropics-complete-guide-to-claude-skills-building>). Run near-miss evals between calendar/todo/memo.
- Silent truncation of listings when over budget (OpenClaw `maxSkillsPromptChars`; Claude Code 1,536-char cap).
- `allowed-tools` applied even in untrusted folders; repo skills can self-grant (<https://code.claude.com/docs/en/skills>).
- Provenance parsed from prose is forgeable; keep it in structured columns (OpenClaw).
- Lazily created namespaces with unstable IDs fragment memory (Hindsight).
- LWW shared blocks with no history (Letta) lose edits between two runtimes.
- LLM contradiction detection on every write (Graphiti) is costly and non-deterministic; keyed records don't need it.
- Marketplace supply chain: 13.4% critical-issue rate, persistent single-approval trust, no data/instruction boundary (Snyk, <https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/>; <https://arxiv.org/abs/2604.02837>).
- Skill-to-skill dependencies are inferred by the model, not declared (Anthropic blog) — the dispatcher must own them.
- "Agent OS" products are mostly branding with no shared schema; AIOS-style kernels solve server scheduling, not personal data.

## Revisions adopted into the plan

**Survey done (2026-08-27; full report → `docs/related-work.md` is the first Phase 0 commit).** Design revisions adopted from it — these override the earlier track designs where they conflict:

| Finding | Source | Revision |
|---|---|---|
| agentskills.io allows exactly six frontmatter keys (`name, description, license, compatibility, metadata, allowed-tools`); claude.ai's validator rejects others; OpenClaw/Hermes/Codex all put runtime keys under `metadata.<ns>` or a sidecar | [agentskills.io/specification](https://agentskills.io/specification); [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills); [docs.openclaw.ai/tools/skills](https://docs.openclaw.ai/tools/skills) | **All OS keys move under `metadata.spike-os`** (`version, runtime, reads_from, writes_to, effects`). Top-level stays spec-pure. `OS_NAME = spike-os` is a single constant (also `~/.claude/spike-os/`, `~/.config/spike-os/`, `.spike-os.json`) — renamable any time. |
| Claude Code adds `when_to_use` (combined with description, 1,536-char cap), `disable-model-invocation`, `user-invocable`, `paths`, `hooks`; Codex uses sidecar `agents/openai.yaml`; gstack generates SKILL.md from a template | [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills); [github.com/garrytan/gstack/SKILL.md.tmpl](https://github.com/garrytan/gstack/blob/main/SKILL.md.tmpl) | **Installer renders, not copies:** claude-code adapter emits `when_to_use` (from the trigger clause), `disable-model-invocation: true` for any skill with a destructive/open-world effect (publish, cron-scheduler, daily-task-manager, social-listening loop…), `user-invocable: false` for background-knowledge skills; openclaw adapter emits `metadata.openclaw.requires.*`. Portable source stays runtime-free. |
| MCP tool annotations `readOnlyHint / destructiveHint / idempotentHint / openWorldHint` are the converged risk vocabulary; approval belongs on the capability (`always_require / never_require`, Microsoft AF); resource classes `fs / exec / network / classified` (tracked-capabilities lit.) | [modelcontextprotocol.io/specification/2025-06-18/server/tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools); [arxiv 2603.00991](https://arxiv.org/html/2603.00991v2) | **Keep the `resource:action` effect list** (it is what the skills already distinguish and what per-effect authorization needs) **but each entry in `capabilities.yaml` carries the four MCP hints + `approval` + `resource_class`;** validator derives skill-level hints from declared effects and adapters emit them. Standard vocabulary, no lost expressiveness. Declaration ≠ enforcement: frontmatter/`allowed-tools` is not a security boundary; real enforcement = datastore adapter + (follow-up) Claude Code `PreToolUse` hooks emitted by the adapter from `effects`. |
| gbrain page model: compiled_truth above the line, append-only timeline below, typed pages, soft deletes, **stale flag when compiled_truth is older than latest timeline entry**, git canonical → PGLite derived | [github.com/garrytan/gbrain/docs/GBRAIN_V0.md](https://github.com/garrytan/gbrain/blob/master/docs/GBRAIN_V0.md) | **Datastore = gbrain pages.** Namespace → page `type`; record envelope → frontmatter; provenance → timeline entries; supersession signal → stale flag. No second store. Both adapters already have gbrain (OpenClaw: `/data/.gbrain`; Mac: `~/Tapan-Brain`). |
| OpenClaw memory architecture: provenance in unforgeable structured columns (origin `owner\|agent\|untrusted\|system`, session kind `interactive\|cron\|heartbeat\|sub-agent`); only consolidation writes curated core; automation sessions produce no durable candidates | [docs.openclaw.ai/concepts/memory-architecture](https://docs.openclaw.ai/concepts/memory-architecture) | Envelope gains `origin` + `session_kind`; **two write invariants become datastore rules on both runtimes:** only `owner-dream-cycle` (consolidation) writes `profile/decisions/` curated records; `session_kind ∈ {cron, heartbeat, sub-agent}` may write only `journal/effects/checkpoints/notifications/jobs/` candidates, never promote. |
| Common envelope fields across mem0 / MemClaw / Zep / StateFuse / Hindsight: `visibility_scope`, `supersedes_id`/`replaced_by`, `derived_from`, `synthesized`, `valid_at/invalid_at`, `lifecycle_state`, `expiration`; hard partition (not a tag) for untrusted sources; namespaces should answer six axes (authority, scope, mutability, provenance, recoverability, actionability) | [arxiv 2606.24535](https://arxiv.org/html/2606.24535v1), [2607.05844](https://arxiv.org/html/2607.05844v1), [2501.13956](https://arxiv.org/html/2501.13956v1), [2606.30306](https://arxiv.org/abs/2606.30306); [hindsight.vectorize.io](https://hindsight.vectorize.io/blog/2026/07/16/bank-strategy-agent-memory) | Envelope adds `derived_from`, optional `valid_at/invalid_at`; `datastore.yaml` namespace entries must state the six axes; `conversations/` (external imports) is a **separate root**, not a tagged sub-tree. |
| Sync consensus: stable internal UID + per-provider `{external_id, version_token, last_synced_with}`; dirty/deleted flags; HotSync fast/slow switch; idempotent command UUID + temp-id mapping (Todoist); provider authoritative, pending local ops replay after readback (Replicache); **never auto-merge** — duplicate, side-wins policy, or surface a ConflictSet; vdirsyncer + RFC 6578 already solve CalDAV/CardDAV | [palm-sync docs](https://github.com/jichu4n/palm-sync/blob/master/docs/how-palm-os-hotsync-works.md); [developer.todoist.com/sync](https://developer.todoist.com/sync/v8/); [doc.replicache.dev](https://doc.replicache.dev/concepts/how-it-works); [vdirsyncer.pimutils.org](https://vdirsyncer.pimutils.org/en/stable/config.html); [RFC 6578](https://datatracker.ietf.org/doc/html/rfc6578) | `contracts/sync.md` gains the status-table fields, fast/slow rule, command UUIDs, and `CONFLICT` = surfaced ConflictSet (never silent pick). `calendar/` conduit = vdirsyncer semantics when built. |
| gstack router = rule table first, model judgment second; Anthropic: under-triggering is the measured default, near-miss confusion between siblings is the real risk; OpenClaw silently truncates listings over `maxSkillsPromptChars` | [gstack SKILL.md](https://github.com/garrytan/gstack/blob/main/SKILL.md); [claude.com/blog/lessons-from-building-claude-code-how-we-use-skills](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) | `home` gets an explicit precedence-rule table before judgment; validator computes total listing size (description + when_to_use ≤1,536/skill; whole-library budget) and fails on overflow; near-miss routing cases are mandatory per cluster (already in §2.3e). |
| skill-creator formats (`evals.json`, `grading.json`, `benchmark.json`, trigger set `{query, should_trigger}` + `run_loop.py` description optimizer); promptfoo `skill-used` assertion runs the same suite on multiple runtimes; control-plane evals need no model call | [github.com/anthropics/skills skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md); [promptfoo.dev/docs/guides/test-agent-skills](https://www.promptfoo.dev/docs/guides/test-agent-skills/) | Runner keeps skill-creator-compatible artifacts (already) **and exports each skill's routing cases as a skill-creator trigger set**, so the vendored `run_loop.py` can optimize descriptions during Phase 3. Validator = the control-plane layer. promptfoo noted as the cross-runtime option for OpenClaw parity later. |
| Supply-chain: single-approval persistent trust is the named structural flaw; ClawHub checks declared-vs-actual | [arxiv 2604.02837](https://arxiv.org/abs/2604.02837); [Snyk ToxicSkills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) | `install_skill.py --check` re-runs declared-vs-actual (effects hints, namespaces, vocabulary) on every install/upgrade; no persistent trust. |
| Karpathy LLM-wiki `lint`; Letta fixed-size home block | [github.com/Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki); [docs.letta.com](https://docs.letta.com/guides/core-concepts/memory/memory-blocks) | Deferred follow-ups: `tools/lint_datastore.py` (dangling links, stale compiled_truth, missing envelope fields); a rendered "today" block for `home`. |
