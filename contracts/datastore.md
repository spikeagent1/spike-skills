# Owner datastore contract v1

<!-- contract-version: 1 -->

The one store every skill shares. A skill declares the namespaces it touches in
`metadata.spike-os.reads_from` / `writes_to`; anything undeclared is out of
bounds (P3). `contracts/datastore.yaml` is the machine-readable form.

## Substrate

Records are gbrain pages: a compiled_truth block above the line and an
append-only timeline below it. A namespace is the page `type`; the record
envelope is the page frontmatter; each provenance event is a timeline entry.
When compiled_truth is older than the newest timeline entry the page is **stale**
— that is the supersession signal, and a stale page is read as context, never as
current truth (F2). Deletes are soft; nothing is destroyed in place.

## Namespaces

Six axes per namespace: authority (who may write), scope, mutability,
provenance, recoverability, actionability.

| Namespace | Status | System of record | Kinds | Authority | Scope | Mutability | Provenance | Recoverability | Actionability |
|---|---|---|---|---|---|---|---|---|---|
| `profile/` | active | datastore | owner-fact, preference, boundary, authority-rule, correction | consolidation and owner-context-onboarding | owner-private | supersede-only | owner turns | history plus superseded records | authority-rule gates every permission check |
| `people/` | active | datastore; contact-card from provider | person, relationship-context, voice-profile, contact-card | consolidation; draft-in-voice for voice-profile | one slug per human or org | supersede-only | owner-stated or agent-inference | history | consent required before quoting (P5) |
| `agents/` | active | datastore | agent-identity, account-state, roster-entry, connector-state | the onboarding skills | the agent and its accounts | explicit state transitions | verified probes | re-probe the provider | gates connector and account use |
| `projects/` | active | datastore | brief, status, handoff | any skill holding `datastore:write` | one page per project slug | append status, supersede brief | session handoffs | history | read before resuming work |
| `decisions/` | active | datastore | decision, commitment | consolidation only | dated owner choices | supersede-only | corpus span and local date | history | cited in briefings |
| `journal/` | active | datastore | dream-report, candidate-ledger, reflection-cycle, run-report | any session kind | dated run artifacts | append-only per run key | run identity | rerun is idempotent | candidates only, never authority |
| `conversations/` | active | datastore, separate root | transcript, manifest | conversation-archive only | imported external transcripts | create-only; quarantine on hash change | untrusted origin, always | manifest replay | evidence only (S3) |
| `tasks/` | active | provider | task, id-map | daily-task-manager | owner tasks mirrored from the task provider | provider-led, mirror follows | provider readback | reconcile from provider | the mirror is never provider truth |
| `calendar/` | reserved | provider | event, id-map | none yet | owner events | read-only until a conduit exists | provider readback | resync | read through `provider:read` |
| `inbox/` | reserved | provider | thread, message-ref, id-map | none yet | refs and triage state, never bodies | read-only until a conduit exists | provider readback | resync | never store message bodies |
| `jobs/` | active | scheduler | job-spec, occurrence | cron-scheduler | scheduled work the owner can see | update by stable job key | scheduler readback | prior-definition snapshot | occurrence key deduplicates runs |
| `effects/` | active | datastore | effect | every mutating skill appends | side-effect ledger | append-only | operation key and readback | rollback handle | consulted before any retry |
| `checkpoints/` | active | datastore | cursor | holders of `checkpoint:advance` | one cursor per skill and channel | advance only after terminal verification | last verified item | replay from prior cursor | never advanced by a read |
| `notifications/` | active | datastore | delivery, held | holders of `notify:owner` | one record per delivery key | state transitions only | channel readback | held digest replay | retry on the same key is a no-op |

A reserved namespace may be named and read about; it may not appear in any
skill's `writes_to`.

Record keys: `journal/` dream-report is `<local-date>--<corpus-hash-8>`
(`skills/owner-dream-cycle/SKILL.md:49`); `jobs/` job-spec is the stable job key
and occurrence is `<job-key>@<scheduled-instant>`
(`skills/cron-scheduler/SKILL.md:43`); `checkpoints/` cursor is
`<skill>/<channel-or-source>` (`skills/social-listening-engagement-loop/SKILL.md:54`);
`effects/` effect carries `operation_key`, `target`, `effect_state`, `readback`,
and `rollback_handle` (`skills/publish/SKILL.md:12`).

## Not in the datastore

Identity and authority files — the runtime's `identity files` term — are outside
it and are reached only through `identity:propose` and `identity:write`
(`skills/owner-dream-cycle/SKILL.md:14`). Adapter-local vault trees that hold no
namespace (an adapter's own global, interests, or timeline folders) are not
datastore records. Credentials live in the `credential store`, never here
(`skills/mcp-connector-onboarding/SKILL.md:28`).

## Record envelope

The page frontmatter. `provenance` and `sync` are flat sub-mappings.

```yaml
id: <stable slug>
namespace: profile
kind: owner-fact
title: <one line>
created: <local date>
updated: <local date>
provenance:
  source_ids: []
  source_span: ""
  local_date: <local date>
  recorded_by: <skill>@<version>
  runtime: openclaw | claude-code
  origin: owner | agent | untrusted | system
  session_kind: interactive | cron | heartbeat | sub-agent
claim_class: owner-stated | agent-inference | unresolved | public-fact | private-context | proposed-change
visibility: public | personal | confidential | restricted
confidence: high | medium | low
status: active | superseded | historical | hypothesis | contested
supersedes: []
derived_from: []
valid_at: null
invalid_at: null
expires: null
expiry_rationale: ""
sync: {}   # provider-backed kinds only; fields in contracts/sync.md
```

`origin` and `session_kind` are set by the runtime, not by the record's author,
and a skill never edits them (`docs/related-work.md` §(c)). Where an adapter's
store already names a field differently — the claude-code vault's `sensitivity`
and `status: confirmed` — the adapter maps it; records are never renamed here.

## Write invariants

1. One claim per record (`skills/owner-dream-cycle/SKILL.md:36`).
2. A correction supersedes; it never overwrites (`skills/owner-context-onboarding/SKILL.md:50`).
3. A skill never relabels `agent-inference` as `owner-stated` (`skills/owner-dream-cycle/SKILL.md:33`).
4. Only consolidation — `owner-dream-cycle` — writes curated `profile/` and `decisions/` records (`skills/owner-dream-cycle/SKILL.md:43`, `docs/related-work.md` §(a)7).
5. A session whose `session_kind` is `cron`, `heartbeat`, or `sub-agent` may write only `journal/`, `effects/`, `checkpoints/`, `notifications/`, and `jobs/`, and may never promote a candidate (`skills/owner-dream-cycle/SKILL.md:12`, `docs/related-work.md` §(a)7).
6. Provenance is structured frontmatter, never prose (`skills/owner-dream-cycle/SKILL.md:38`).
7. No credentials, OTPs, email addresses, or raw sensitive excerpts, in any namespace (`skills/owner-dream-cycle/SKILL.md:38`).
8. Every write is followed by a readback that compares envelope and body (M4).

## Verbs

| Verb | Mutating | Semantics |
|---|---|---|
| `read(ns, id)` | no | The only way to obtain a record's content. |
| `search(q, ns?, limit?)` | no | Keyword only; every hit must be `read` before it is used (`skills/briefing/SKILL.md:21`). |
| `list(ns, filter?)` | no | Enumeration; follow pagination and never infer absence from one page (`skills/daily-task-manager/SKILL.md:24`). |
| `timeline(ns, id, range)` | no | Explicit range always; never "since last run" (`skills/briefing/SKILL.md:21`). |
| `write(ns, record)` | yes | Put, then read back and compare envelope and body hash before claiming success. |
| `append_timeline(ns, id, entry)` | yes | Append one provenance event; never rewrites an earlier entry. |
| `supersede(ns, old, new)` | yes | Write both records; the old one keeps its content and gains `status: superseded`. |

No verb advances a cursor. Cursor movement is a `write` to `checkpoints/` under
`checkpoint:advance` (`skills/briefing/SKILL.md:12`).

## The conversations partition

`conversations/` is a separate root, not a tagged sub-tree of anything. Its
records carry `origin: untrusted` without exception, no search over another
namespace returns them, and no record elsewhere may cite one as authority — only
as evidence (S3). Promotion out of it follows the promotion gate in
`contracts/capabilities.yaml`: source text and summary promote to nothing; a
belief needs `belief:update`; an operating instruction needs `identity:propose`
then `identity:write`; a permission is owner-only
(`skills/social-agent-practice/SKILL.md:47`).
