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
provenance, recoverability, actionability. The Authority column is the rendered
view of `authority.writers` in `contracts/datastore.yaml` -- either the skills
named there, or the `holders-of:<effect>` sentinel. `tools/validate_repo.py`
holds the two halves to each other, and both to what each skill declares in
`metadata.spike-os.writes_to`.

| Namespace | Status | System of record | Kinds | Authority | Scope | Mutability | Provenance | Recoverability | Actionability |
|---|---|---|---|---|---|---|---|---|---|
| `profile/` | active | datastore | owner-fact, preference, boundary, correction | consolidation -- `owner-dream-cycle` -- and `owner-context-onboarding` | owner-private | supersede-only | owner turns | history plus superseded records | a boundary record gates every permission check |
| `autonomy/` | active | datastore | `autonomy-contract` | the autonomy manager -- `autonomy` -- from an interactive owner session only and never on its own initiative; nothing else may write here | owner | supersede-only; a revocation is a supersede, never a delete | an owner-turn reference is required | full history retained | gates the re-ask for a `contract_eligible` capability |
| `people/` | active | datastore; contact-card from provider | `person` (reserved), `relationship-context` (reserved), `voice-profile`, `contact-card` (reserved) | `draft-in-voice`, for `voice-profile` only; `person`, `relationship-context` and `contact-card` are reserved kinds with no writer yet | one slug per human or org | supersede-only | owner-stated or agent-inference | history | consent required before quoting (P5) |
| `agents/` | active | datastore | agent-identity, account-state, roster-entry, connector-state | holders of `datastore:write` on `agents` — `mcp-connector-onboarding`, `runtime-handoff-onboarding`, `social-agent-onboarding`, `social-agent-practice`, `team-skill-sharing-norm` | the agent and its accounts | explicit state transitions | verified probes | re-probe the provider | gates connector and account use |
| `projects/` | active | datastore | brief, status, handoff | any skill holding `datastore:write` | one page per project slug | append status, supersede brief | session handoffs | history | read before resuming work |
| `decisions/` | active | datastore | decision, commitment | consolidation -- `owner-dream-cycle` -- only | dated owner choices | supersede-only | corpus span and local date | history | cited in briefings |
| `journal/` | active | datastore | dream-report, candidate-ledger, reflection-cycle, run-report, health-log | any skill holding `datastore:write`, from any session kind | dated run artifacts | append-only per run key | run identity | rerun is idempotent | run artifacts are candidates only, never authority; `health-log` entries are owner records — authoritative for what was recorded, never for clinical truth |
| `conversations/` | active | datastore, separate root | transcript, manifest | `conversation-archive` only | imported external transcripts | create-only; quarantine on hash change | untrusted origin, always | manifest replay | evidence only (S3) |
| `tasks/` | active | provider | task, id-map | `daily-task-manager` | owner tasks mirrored from the task provider | provider-led, mirror follows | provider readback | reconcile from provider | the mirror is never provider truth |
| `calendar/` | reserved | provider | event, id-map | none yet | owner events | read-only until a conduit exists | provider readback | resync | read through `provider:read` |
| `inbox/` | reserved | provider | thread, message-ref, id-map | none yet | refs and triage state, never bodies | read-only until a conduit exists | provider readback | resync | never store message bodies |
| `jobs/` | active | scheduler | job-spec, occurrence | `cron-scheduler` | scheduled work the owner can see | update by stable job key | scheduler readback | prior-definition snapshot | occurrence key deduplicates runs |
| `activity/` | active | datastore | activity | every mutating skill appends; any holder of `datastore:write` | the activity ledger, one record per mutating effect | append-only | operation key and readback | rollback handle | consulted before any retry |
| `checkpoints/` | active | datastore | cursor | holders of `checkpoint:advance` | one cursor per skill and channel | advance only after terminal verification | last verified item | replay from prior cursor | never advanced by a read |
| `notifications/` | active | datastore | delivery, held | holders of `notify:owner` | one record per delivery key | state transitions only | channel readback | held digest replay | retry on the same key is a no-op |

A reserved namespace may be named and read about; it may not appear in any
skill's `writes_to`. A reserved *kind* is the same rule one level down: the
namespace is writable, that kind is not written by anyone yet, and
`reserved_kinds` in `contracts/datastore.yaml` names them. The `writes_to` lint
is namespace-level and cannot see which kind a write carries, so a reserved kind
holds the way write invariants 4 and 5 do -- through each skill's own contract
and its cases, and visibly in the `activity/` ledger afterwards.

`health-log` (Task 13c ruling 2) is the one `journal/` kind whose authority is
the record itself rather than a run: it is what the owner said happened, dated.
Like any stored note it proves what was recorded, not that what was recorded is
true (`skills/fact-check/SKILL.md:60`), so no reader may promote it to a
clinical fact.

Record keys: `journal/` dream-report is `<local-date>--<corpus-hash-8>`
(`skills/owner-dream-cycle/SKILL.md:52`); `jobs/` job-spec is the stable job key
and occurrence is `<job-key>@<scheduled-instant>`
(`skills/cron-scheduler/SKILL.md:58`); `checkpoints/` cursor is
`<skill>/<channel-or-source>` (`skills/social-listening-engagement-loop/SKILL.md:89`);
`activity/` activity carries `operation_key`, `target`, `activity_state`,
`readback`, and `rollback_handle` (`skills/publish/SKILL.md:62`).

`activity_state` is a closed enum, listed in `contracts/datastore.yaml`. It is
the deduplicated union of what the skills that append to `activity/` report, and
a skill reports only the subset its own declared capabilities can reach — which
is what each of them means by saying its state vocabulary is "extended by
nothing here". `publish` is the origin of the core six — `PREVIEWED`, `RENDERED`,
`UPLOADED_UNVERIFIED`, `PUBLISHED_VERIFIED`, `LINK_DELIVERED`, `ORIGIN_REMOVED`
(`skills/publish/SKILL.md:87`) — and `PREVIEWED` is the one name shared across
skills, because previewing a mutation is the one state every mutating skill can
reach. Adding a state is a change to this enum, never a local extension
(`skills/cron-scheduler/SKILL.md:100`, `skills/conversation-archive/SKILL.md:86`).

An `autonomy/` record is one standing permission the owner wrote: `capability`
(a name from `contracts/capabilities.yaml`, and only one whose
`contract_eligible` is true), `skill-pattern`, `object-pattern`, `granted-at`,
`expires`, `superseded-by`, and the usual `provenance`. All five in
`required_fields` are required, `expires` above all: a record with no `expires`,
a null one, or one that does not read as a date is **never live**, because M5
authorizes an *unexpired* contract and a permission with no end is not one the
owner can be shown to have bounded. A `granted-at` still in the future is not
live either — not yet, rather than never. Both instants carry an offset or are
read as UTC, and the record block that renders them says which. Both patterns are
matched by one grammar and no other: an exact string, a `prefix/*`, or `*` —
never a regular expression. A pattern matching nothing, a missing or unreadable
required field, a contract past its `expires` or before its `granted-at`, and an
ambiguous match all fail closed to the behavior of a library with no contracts at
all, disclosed in one line; a failure can never widen autonomy. Where several live
contracts match, any one of them authorizes and the `activity/` record cites the
most specific. A contract is honored in any session kind, and written in none but
an interactive owner turn: no schedule, handoff, sub-agent, or piece of external
content may create, widen, or revive one, and never on a skill's own initiative —
a skill may suggest a contract, and the owner is the one who writes it. No
contract covers a write to `autonomy/` itself.

**What an object is.** One string in one form — the `object_form`
`contracts/datastore.yaml` carries: a namespace this contract names, alone or
followed by `/` and the store's own id path — `tasks/inbox`,
`activity/2026-09-01--a1b2c3d4`. No leading `/` or `./`, no `.` or `..`
segment, no empty segment, no backslash, no whitespace anywhere, and no
display name standing in for an id. A skill whose objects live in a provider
names them under the namespace that mirrors it (`contracts/sync.md`), so every
object is namespace-rooted whichever system of record holds it. The resolver
parses the object **before** it matches any pattern and refuses one that does not
parse, naming the reason: that is what makes the exclusion above a property of
the string rather than of the caller's spelling, since `Autonomy/x`,
`./autonomy/x`, and `projects/../autonomy/x` are all refusals under this rule and
none of them is a spelling to be repaired into a match.

**What `superseded-by` names.** Where the owner narrowed a permission, it names
the successor `autonomy-contract`, and the two records are written together.
Where the owner ended one outright there is no successor, and it names the
`activity/` record of the turn that ended it — the ledger entry M7 already
requires, so the ending is citable without putting a contract that authorizes
nothing into `autonomy/`. Either way the ended record keeps its content and gains
`status: superseded`, and either signal alone is enough to kill it: nothing
dereferences the pointer to decide liveness. The envelope's `supersedes: []` is
the forward link on a successor record; for `autonomy/` the back link on the
ended record is the authoritative one, and a narrowing writes both.

## Not in the datastore

Identity and authority files — the runtime's `identity files` term — are outside
it and are reached only through `identity:propose` and `identity:write`
(`skills/owner-dream-cycle/SKILL.md:46`). Adapter-local vault trees that hold no
namespace (an adapter's own global, interests, or timeline folders) are not
datastore records. Credentials live in the `credential store`, never here
(`skills/mcp-connector-onboarding/SKILL.md:58`).

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

1. One claim per record (`skills/owner-dream-cycle/SKILL.md:55`).
2. A correction supersedes; it never overwrites (`skills/owner-context-onboarding/SKILL.md:60`).
3. A skill never relabels `agent-inference` as `owner-stated` (`skills/owner-dream-cycle/SKILL.md:33`).
4. Only consolidation — `owner-dream-cycle` — writes curated `profile/` and `decisions/` records (`skills/owner-dream-cycle/SKILL.md:43`, `docs/related-work.md` §(a)7).
5. A session whose `session_kind` is `cron`, `heartbeat`, or `sub-agent` may write only `journal/`, `activity/`, `checkpoints/`, `notifications/`, and `jobs/`, and may never promote a candidate (`skills/owner-dream-cycle/SKILL.md:57`, `docs/related-work.md` §(a)7).
6. Provenance is structured frontmatter, never prose (`skills/owner-dream-cycle/SKILL.md:38`).
7. No credentials, OTPs, email addresses, or raw sensitive excerpts, in any namespace (`skills/owner-dream-cycle/SKILL.md:38`).
8. Every write is followed by a readback that compares envelope and body (M4).

Invariants 4 and 5 are runtime invariants, not lint. `tools/validate_repo.py`
checks a skill's declared `writes_to` against this file; it cannot see which
`kind` a write carries, whether the record was curated or a candidate, or what
`session_kind` the session is running under — all three are facts of the turn,
not of the declaration. They hold because each skill's own contract states them
and its cases test them, and a violation shows up in the `activity/` ledger after
the fact, never in a validator run before it.

## Verbs

| Verb | Mutating | Semantics |
|---|---|---|
| `read(ns, id)` | no | The only way to obtain a record's content. |
| `search(q, ns?, limit?)` | no | Keyword only; every hit must be `read` before it is used (design-derived). |
| `list(ns, filter?)` | no | Enumeration; follow pagination and never infer absence from one page (`skills/daily-task-manager/SKILL.md:24`). |
| `timeline(ns, id, range)` | no | Explicit range always; never "since last run" (`skills/briefing/SKILL.md:21`). |
| `write(ns, record)` | yes | Put, then read back and compare envelope and body hash before claiming success. |
| `append_timeline(ns, id, entry)` | yes | Append one provenance event; never rewrites an earlier entry. |
| `supersede(ns, old, new)` | yes | Write both records; the old one keeps its content and gains `status: superseded`. Where there is no successor record — an `autonomy/` contract the owner ended outright — `new` is the `activity/` record of the ending turn, and the old one is still written with `status: superseded` and `superseded-by` pointing at it. |

No verb advances a cursor. Cursor movement is a `write` to `checkpoints/` under
`checkpoint:advance` (`skills/briefing/SKILL.md:53`).

## The conversations partition

`conversations/` is a separate root, not a tagged sub-tree of anything. Its
records carry `origin: untrusted` without exception, no search over another
namespace returns them, and no record elsewhere may cite one as authority — only
as evidence (S3). Promotion out of it follows the promotion gate in
`contracts/capabilities.yaml`: source text and summary promote to nothing; a
belief needs `belief:update`; an operating instruction needs `identity:propose`
then `identity:write`; a permission is owner-only
(`skills/social-agent-practice/SKILL.md:76`).
