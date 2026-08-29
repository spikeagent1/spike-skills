# Rewrite report — safety-and-mutation cluster (batch 5)

`publish`, `cron-scheduler`, `conversation-archive` rewritten to
`contract_version: 2`. Branch `os-foundations`, base `20b3b1c`.

These three are the skills the contracts were *derived from*: nineteen of
the twenty-two `derived_from` and rule anchors that point into a skill
file point into one of them. The rewrite's job was to make each cite the
contract back instead of restating it, without losing anything the v1
body mandated.

## Per-skill

| Skill | Words | Desc chars | with (base → now) | without | Delta | Disc. | broken | Runtime hits | Gate |
|---|---:|---:|---|---|---|---|---|---:|---|
| publish | 1004 → 3459 | 82 → 298 | 81.3% → **75.0%** | 50.0% → 56.3% | +31.3 → +18.8pp | 5/16 → 3/16 | 3 → 4 | 1 → **0** | **not met** |
| cron-scheduler | 1071 → 3574 | 76 → 298 | 68.8% → **63.2%** | 11.3% → 10.5% | +57.5 → +52.7pp | 11/19 → 12/19 | 6 → 7 | 1 → **0** | **not met** (runner: noise) |
| conversation-archive | 1142 → 3305 | 87 → 296 | 78.8% → **83.3%** | 28.8% → 22.2% | +50.0 → +61.1pp | 9/18 → 11/18 | 4 → 3 | 1 → **0** | **met**, 0 regressions, 1 gain |

Runs: `20260829T072534-938f9f4` (publish, after one fix iteration),
`20260829T073855-4ca89d1` (cron-scheduler, after one fix iteration),
`20260829T074554-5451c36` (conversation-archive). Behavioral spend
$4.17; routing $0.22.

`make validate` and `make test` (503 tests) green. Validator warnings
11, down from 12: all three files' runtime-specific hits are cleared and
`conversation-archive` is re-baselined; the two remaining are the
deliberately-stale `skill_sha256` entries for `publish` and
`cron-scheduler`.

## Routing — run `20260829T074825-5451c36-batch5-final`

Native, `--repeats 3`, 37 cases across six files, 111 ballots, $0.217.
**36 pass / 0 ambiguous / 1 fail / 0 phantom — 97%.**

| File | Baseline | Batch-5 final | Movement |
|---|---|---|---|
| publish | 67% / 67% | **100% / 100%** | `:3` won from "no skill"; `:5` won from the `schedule` built-in |
| cron-scheduler | 67% / 67% | **100% / 100%** | `:3` won from the `schedule` built-in |
| conversation-archive | 86% / 86% | **100% / 100%** | `:7` recovered from batch 2's sale |
| public-post-workshop | 83% / 83% | **100% / 100%** | `:1` no longer absorbed by `publish` |
| owner-dream-cycle | 100% / 100% | **100% / 100%** | — |
| daily-task-manager | 83% / 83% | **83% / 83%** | `:6` unchanged, same absorber |

**Zero built-in hijacks and zero answered-natively-with-no-skill.** The
`schedule` built-in held four intents at the repo-wide baseline; the two
that belong to these six files are both won. The technique is batch 2's,
applied twice inside one description: lift each losing intent's phrasing
close to verbatim, then exclude the built-in's own scope by activity —
here "Not for one dated reminder (daily-task-manager)", which is exactly
the `schedule` built-in's one-off branch.

The `publish` ↔ `cron-scheduler` pair had to be written against each
other rather than in sequence: `publish:5` is a cron-scheduler intent
scored on publish's file, so cron-scheduler's description buys publish's
point.

## What each skill now cites instead of restating

| Contract | Skill | Moved out (cited) | Kept in the skill, and why |
|---|---|---|---|
| `datastore.yaml` / `datastore.md` — `effects` | publish | The `effect_state` vocabulary is named as the ledger's, not the skill's | The six state names and what evidence each takes to reach — that is the domain delta |
| `capabilities.yaml` — `approval` | publish | The four floors and the ladder | The **per-effect envelope table**: what each effect is authorized *per* (one destination AND one audience; one recipient AND one channel; one named object) and what never grants it. This is the batch's exemplar |
| `datastore.yaml` — `jobs` | cron-scheduler | Two kinds, both key shapes, the prior-definition snapshot as recoverability | Cadence normalization, DST and missed-firing policy, the four idempotency keys, the transactional order |
| `notifications.md` | cron-scheduler | The whole quiet-hours paragraph — mode enum, delivery-key shape, digest release, the two overrides, never-infer-awake, delivery-record states. **This contract was extracted from this skill's v1 line 40**, so the duplication was the thing to remove | *Execution and delivery carry separate idempotency keys*, and an unresolved delivery mode is an incomplete definition rather than a default |
| `datastore.md` — `conversations/` | conversation-archive | Separate root, `origin: untrusted` without exception, create-only with quarantine on hash change, evidence-only actionability | The manifest, the four collision cases, the check-then-write prohibition, the trial's coverage dimensions, the reconciliation equation |
| `datastore.md` — `checkpoints/` | conversation-archive | One cursor per skill and source, advanced only after terminal verification, never by a read | Atomic checkpointing per terminally verified item, and what a retry may and may not mark complete |
| `sync.md` | cron-scheduler | **Nothing.** `jobs`'s `system_of_record` is the `scheduler`, not a provider, so it is not a sync instance | The pagination rule stays in full rather than being folded into a contract that does not govern this namespace |

## Frontmatter

| Skill | reads_from | writes_to | effects | Legacy keys removed |
|---|---|---|---|---|
| publish | `effects` | `effects` | `datastore:read`, `datastore:write`, `fs:write-local`, `publish:external`, `publish:revoke`, `message:send` | `mutating: true` |
| cron-scheduler | `jobs` | `jobs`, `effects` | `datastore:read`, `datastore:write`, `schedule:manage`, `delete:external` | `mutating: true` |
| conversation-archive | `conversations` | `conversations`, `checkpoints`, `effects` | `datastore:read`, `datastore:write`, `checkpoint:advance`, `spend`, `fs:write-local` | `mutating: true`, `writes_pages: true`, bare `writes_to:` list |

`effects` is in every `writes_to` per the batch-2 Addendum (any mutating
effect ⇒ M7's ledger append). `cron-scheduler` declares neither
`notify:owner` nor `message:send`, and the body carries the clause that
makes that honest: the skill *sets* a job's delivery fields; the job's
own run does the delivering, and **a registered job carries no
authorization into the runs it triggers** (M6).

## CAPABILITY_HINTS, as the validator measures it

| Skill | Negation escapes | Delegation escapes | Unresolved |
|---|---:|---:|---:|
| publish | 1 | 1 | 0 |
| cron-scheduler | 1 | 1 | 0 |
| conversation-archive | 1 | 0 | 0 |

All three negation escapes are the same sentence in a different dress —
the Dependencies line saying a secret is **never** copied out of the
`credential store` — because `credential` implies `credential:manage`,
which none of the three declares. The two delegation escapes are routing
lines carrying a backticked real skill name: `public-post-workshop` (for
"unmerged pull request" → `repo:write`) and `publish` (for "putting one
approved artifact live" → `publish:external`).

Collisions removed rather than escaped, by file: `publish` — "push it
live" → "put it live" in the body while the **description** keeps the
routing word, and "remove plaintext temporary artifacts" → "cleared";
`cron-scheduler` — every singular `checkpoint` (it holds no
`checkpoint:advance`) and every bare `send`/`reply`/`DM`;
`conversation-archive` — the RETRIEVE clause redrafted from "it **does
not** ingest…" to "it **never** ingests, syncs, extracts, writes,
schedules, repairs, or backfills", because `does not` is not in
`EFFECT_NEGATION_RE` and the redraft also restores v1's dropped
"schedule".

## Contract anchors repointed

Twenty-two `skills/<name>/SKILL.md:<line>` citations across
`skill-contract.md`, `capabilities.yaml`, `notifications.md`, `sync.md`,
and `datastore.md` pointed at v1 line numbers that all moved. Every one
was repointed and verified to land on the sentence carrying the rule
(`7e00e45`). `notify:owner` now points at cron-scheduler's "Quiet hours
govern **delivery** and not execution", which is the sentence
`notifications.md` was extracted from.

One anchor outside the batch was corrected in passing: `delete:external`
cited `daily-task-manager:19`, a `When to use` bullet after batch 2's
rewrite; it now points at `:54`. The rest of the batch-1 through -4
anchor drift is untouched and remains the open sweep task 17 recorded.

## Assertions that need an eval-fixture ruling

Four assertions across `publish` and `cron-scheduler` are what stands
between this batch and a clean behavioral gate. Two are the live-provider
class the grader itself names unsatisfiable; two are text-derivable and
would fall to one more skill-side iteration.

| Skill | Assertion | Class | What would clear it |
|---|---|---|---|
| publish | `examples:1/4 State is RENDERED, not PUBLISHED` | live-provider | `RENDERED` means a local artifact exists and passed verification; the harness has no filesystem write and the prompt supplies no briefing body, so claiming it is claiming a mutation with no readback — X5/M4/O3, the rules this skill is the source of. Grader: split into "no external release state is claimed" and a separate artifact assertion |
| publish | `examples:3/4 ACL and expiry verified` | live-provider | Verification is a readback from a destination that does not exist here. Grader: "forces a FAIL on an arguably-correct refusal"; accept either branch |
| cron-scheduler | `examples:3/5 Per-reply key defined` | skill-side | The record's `per item` line still accepts `n/a`; it must carry the *scheme* (`<occurrence key> + <target object id>`) before the objects are known |
| cron-scheduler | `examples:3/5 Atomic checkpoint after verification` | skill-side | Same shape: the `resume point` line must carry "written only after the action on that object is confirmed" rather than accepting `n/a` |

The v1 bodies scored the first two by letting the model **narrate** a
render and a readback it never performed. The v2 bodies forbid exactly
that, and `publish`'s `examples:2/4 Material redactions surfaced without
values` moved from `broken` to a **gain** on the same mechanism. The
honesty rules cost two assertions and bought one.

`publish` and `cron-scheduler` are deliberately **not** re-baselined:
merging their runs would move the bar down, and a later fix round's
`--compare-baseline` would then measure "no regression" against a
degraded number.

## Rulings requested

1. **The two live-provider assertions on `publish`** — edit the fixture
   (the batch template forbids editing existing cases without a ruling),
   accept the deficit as the honest-behaviour price, or fund a second
   skill-side iteration.
2. **`cron-scheduler`'s remaining two** — one more iteration at ~$0.69
   with-arm-only, or accept `−3.8pp, classified noise by the runner` as
   clearing the gate.
