# Rewrite: the owner-operations cluster (2026-08-29)

Batch 2 rewrites the three OS-core skills — `daily-task-manager`,
`briefing`, `owner-dream-cycle` — to contract v2. These are the first
skills in the corpus to bind to `contracts/datastore.md`,
`contracts/sync.md`, `contracts/notifications.md`, and
`adapters/vocabulary.yaml` for real, rather than describing a runtime in
its own product nouns.

Branch `os-foundations`, base `e9117d3`. `make validate` exits 0 with
**17 warnings**, down from 20 — the three runtime-value complaints these
files carried (`todoist`, `ops/tasks.md`, `tapan`, `spike`,
`america/los_angeles`) are gone. `baseline check` exits 0. 499 tests OK,
2 skipped. No eval case was added or edited: all three skills had
non-zero discriminating counts at the baseline, so batch-template step A
did not apply.

## Per-skill before / after

`with_skill` and `without_skill` are **case-means** — the mean of each
case's own pass fraction — which is what `evals/baseline.json` stores and
what every table in this document uses. On a fixture whose cases hold
different numbers of assertions the case-mean and the raw
assertions-passed fraction diverge: `daily-task-manager`'s cases carry
5, 4, 3, and 4 assertions, so its 8-of-16 run is a **52.1%** case-mean,
not 50%. `briefing` and `owner-dream-cycle` have four four-assertion
cases each, so for them the two measures coincide.

| Metric | daily-task-manager | briefing | owner-dream-cycle |
|---|---|---|---|
| `wc -w` | 1082 → 2686 | 1051 → 2476 | 1083 → 2980 |
| Description chars | 79 → 295 | 85 → 286 | 84 → 297 |
| with_skill | 39.6% → **52.1%** | 68.8% → **87.5%** | 56.3% → **75.0%** |
| without_skill | 27.1% → 33.3% | 56.3% → 56.3% | 50.0% → 31.3% |
| Delta | +12.5 → **+18.8pp** | +12.5 → **+31.3pp** | +6.3 → **+43.8pp** |
| Discriminating | 2/16 → **3/16** | 2/16 → **5/16** | 1/16 → **7/16** |
| broken / harmful | 10 / 0 → **8 / 0** | 5 / 0 → **2 / 0** | 7 / 0 → **4 / 0** |
| Routing (lenient/strict) | 83/83 → **83/83** | 100/100 → **100/100** | 100/100 → **100/100** |
| Regressions / gains | 0 / 2 | 0 / 3 | 0 / 3 |
| Gate run | `20260829T030749-6a3e2fc` | `20260829T040028-e5ad196` | `20260829T040824-7494ed9` |

Every skill improved and none regressed. The cluster's broken-assertion
count fell 22 → 14 and its discriminating count rose 5/48 → **15/48**.
`owner-dream-cycle` moved furthest: its whole worldview case (4/4) is
now discriminating where none of it was, and its with/without delta went
from +6.3pp — barely distinguishable from no skill at all — to +43.8pp.

**Read that delta with its control in view.** Roughly half of
`owner-dream-cycle`'s +37.5pp swing is the skill rising (56.3% → 75.0%)
and half is its **control falling** (50.0% → 31.3%). The control drop is
not a measurement artefact of this rewrite — `without_skill` was
re-sampled fresh against unchanged eval cases and the skill body is not
in that config's prompt — but it is a one-sample control on a 4-case
fixture, and a swing of three assertions is well inside what a single
resample can produce. The honest claim is that the skill improved by
**18.8pp measured directly**; the delta figure is the headline the
harness computes, not an independent second measurement.
`daily-task-manager`'s control moved the other way (27.1% → 33.3%) and
`briefing`'s did not move at all (56.3% → 56.3%), which is what an
unbiased resample looks like across three files.

## The routing ballot — run `20260829T041004-6ef4834-batch2-final`

Native mode, `--repeats 3`, ballot of 30 skills, 93 ballots over the
31 cases owned by the five files in the two clusters this batch touches
(`day` = {briefing, daily-task-manager}, `datastore-readers` =
{conversation-archive, owner-dream-cycle, briefing}, plus
`cron-scheduler` as `daily-task-manager`'s recurrence target).
**28 pass / 0 ambiguous / 3 fail / 0 phantom.** $0.229.

| File | Baseline (repeats 1) | Batch-2 final (repeats 3) | Movement |
|---|---|---|---|
| briefing | 100% / 100% | **100% / 100%** | — |
| owner-dream-cycle | 100% / 100% | **100% / 100%** | — |
| daily-task-manager | 83% / 83% | **83% / 83%** | `:6` still fails, different absorber |
| conversation-archive | 86% / 86% | **86% / 86%** | a swap — `:6` won, `:7` lost |
| cron-scheduler | 67% / 67% | **83% / 83%** | `:4` recovered from a CLI built-in |

Every file is at or above its baseline. The gate is met. As in batch 1,
the baseline column is a **repeats-1** run and this one is a repeats-3
majority, so the movement column is direction, not magnitude.

**All 31 cases were unanimous 3/3.** There is not one split ballot in
the run — unusual against batch 1's four splits in 62, and it suggests
these five descriptions now separate cleanly rather than sitting near a
boundary.

### The two intents this batch bought

- **`conversation-archive:6`** — "Look back over what I've said about my
  goals this year and tell me where I've drifted." Expected
  `owner-dream-cycle`; answered natively with no skill at the baseline;
  now unanimous `owner-dream-cycle`. This was a target: the description
  had to keep firing on drift-review phrasings even though the design
  ruling stripped the interactive framing out of the body, and
  "looking back over what was said about goals this year and where the
  drift is" carries it.
- **`cron-scheduler:4`** — "Remind me to renew the insurance next
  Tuesday." Expected `daily-task-manager`; taken by the CLI's own
  `schedule` built-in at the baseline; now unanimous
  `daily-task-manager`. **This is the first time in this project a repo
  description has outbid a built-in on an intent the built-in had
  already taken.** What did it is quoting the intent's own shape in the
  trigger — "'remind me to renew the insurance next Tuesday'" — and
  pairing it with "a single task" and an explicit exclusion of anything
  recurring. Batch 1's routing debt listed built-in hijacks as
  unwinnable; on this evidence they are winnable when the description
  names the exact phrasing and the built-in's own scope is excluded.

### The two intents still failing, and one sold

- **`daily-task-manager:6`** — "What did I get done across the brain last
  week?", expected `(none)`. It failed at the baseline too, absorbed by
  `owner-dream-cycle`; it now fails absorbed by `briefing`. The
  `owner-dream-cycle` half was fixed on purpose — its description
  narrowed to "a closed span of the owner's **own turns**" and its
  `When not to use` explicitly disowns activity retrospectives — and
  `briefing` picked the intent up instead, because "a summary of what
  the notes already say" reaches it. That clause cannot simply be
  removed: `owner-dream-cycle:5` ("Read-only summary of what my notes
  say about this quarter's goals. Don't write anything.") **expects
  `briefing`** and is carried by exactly that phrase. The file rate is
  unchanged and the intent is a null-expectation, so this was left
  rather than traded.
- **`conversation-archive:7`** — "did my colleague answer in the group
  channel last night?", expected `(none)`, now unanimously absorbed by
  `conversation-archive` — **a file this batch never opened**, on an
  intent that passed at the baseline. Its sibling `:6` moved the other
  way in the same run, so the file rate is flat at 86%. This is batch
  1's finding reproducing exactly: *native routing is a zero-sum ballot
  and a description edit is never local to its own file.* Two of this
  batch's three descriptions name transcripts, conversations, or "what
  was said", and the honest reading is that they shifted where the
  router draws the conversation boundary — buying `:6` and selling `:7`
  — not that `conversation-archive` stood still.
- **`cron-scheduler:3`** — "What's actually scheduled right now, and when
  does each one next run?" is still taken by the `schedule` built-in.
  Unlike `:4` this one asks for the built-in's own listing behaviour by
  name, and no description edit here was aimed at it.

**The repo-wide routing baseline was deliberately not overwritten.**
`baseline update --routing-from` *replaces* the whole routing block, and
this run covers 5 files of 30; merging it would delete the other 25
files' routing baselines. The committed block stays the full `--all`
run (`20260828T174809-8fe2907-dirty-baseline`), and this table is the
record for these five files.

## What each rewrite had to invent

- **`daily-task-manager` — the operation record, and what an unreachable
  provider may *not* become.** The skill is the sync reference instance,
  so the body shrank to "operates the `tasks` sync instance per
  `contracts/sync.md`" plus what is genuinely task-specific, and the
  state enum now appears exactly once, in `Output contract`, as the state
  vocabulary. What had to be invented is the deliverable: one operation
  record per request — mode, resolved target, identity, semantic key,
  change, derived values, state, what is open — rendered in the turn with
  `unknown` in unsupplied fields and `pending` where a provider would
  have answered. The hard-won clause is the one that took two iterations:
  *mirror-only is the owner's explicit choice of system of record, never
  what an unreachable provider degrades into.* Without it the record
  resolved the target well enough that the same-turn-verb authority fired
  and the run wrote a mirror object for a provider object that never
  existed — manufacturing `EXTERNAL_MISSING`, the exact case the skill
  exists to prevent.
- **`briefing` — the `current` line on a conflict row.** The rewrite
  turned conflict-surfacing into the skill's spine and immediately
  over-corrected: given a note saying 10am and a live calendar saying
  moved to 11am *and cancelled*, it recorded a standing conflict and said
  "nothing here tells me which is current". The contracts already settle
  it — `contracts/datastore.md` names a **system of record per
  namespace** — so a conflict between a provider-backed fact and a
  datastore copy of it is not symmetric: the copy is stale context (F2).
  The conflict row gained `current` for that and kept `standing` for the
  case where neither side is the system of record. *A cancellation is a
  status, so it settles attendance whatever the disputed time was.*
- **`briefing` — the five distinct coverage states.** `answered`,
  `partial`, `unavailable`, `stale`, `empty`, with **empty** defined as
  "the source answered and held nothing, which is never the same report
  as any of the others". F4's weakest reading only asks that the
  categories be distinguished; naming them as states with one row per
  source is what makes the rule checkable, and it is what "no meetings
  today" being wrong actually costs.
- **`owner-dream-cycle` — separating an integrity failure from a no-op.**
  An integrity failure is a **contradiction** (an empty corpus while
  another source says the owner was active). A corpus that is genuinely
  unchanged is idempotency working, terminates `NO_OP`, and is a
  successful outcome. The first v2 run collapsed the two and failed
  closed on the rerun case, which is the property the rerun was checking.
- **`owner-dream-cycle` — `counterevidence` as a ledger field.** v1
  mandated "supporting evidence, counterevidence, confidence, and the
  exact proposed change" for a worldview candidate. The fold put that in
  the run-report description and lost it as an action, and the eval
  caught what the mechanical check did not. It is a field on the row now,
  "searched, none found" is a valid entry, and the distinction is
  written out: *corroboration of the same claim is supporting evidence,
  not counterevidence — a candidate weighed only against repetitions of
  itself has not been weighed.*

## Contract binding — the first real use of the OS contracts

| Contract | Bound by | How |
|---|---|---|
| `sync.md` | daily-task-manager | The **reference instance**. State machine, mutation order, four reconciliation cases, id-map / semantic-key mechanics, pagination, match-fallback: cited. **Two are deliberately restated** — the one-way mutation order and the absolute never-roll-back rule — because both read stricter here than the contract alone would imply and both are what stop a mirror object outliving its provider object; the body says so rather than claiming it restates nothing. The full state enum is enumerated once, in `Output contract`. Kept in the skill: mode classification, explicit-delete-language, mirror-only disclosure |
| `datastore.md` verbs | briefing | `read` / `search` / `list` / `timeline` named as the four non-mutating verbs, `timeline` given an explicit range every time; "since the last run" named as a move rather than a read |
| `datastore.md` system-of-record | briefing | The conflict asymmetry — provider-backed fact wins, the copy is stale context |
| `datastore.md` invariants 1–8 | owner-dream-cycle | One claim per record; correction supersedes; no relabelling inference as owner-stated; **invariant 4 = the curated-write privilege, cited explicitly**; **invariant 5 = session-kind gate**; structured provenance; no secrets; readback |
| `capabilities.yaml` promotion gate | owner-dream-cycle | Quoted in full for `conversations`: source text and summary → nothing, belief → `belief:update`, operating instruction → `identity:propose` then an authority the skill does not hold, permission → owner-only |
| `capabilities.yaml` non-declaration | briefing | `checkpoint:advance` cited as an effect the skill **does not** declare |
| `notifications.md` | owner-dream-cycle | Delivery key, held-digest release, quiet hours governing delivery not execution, and exactly two overrides |
| `vocabulary.yaml` | all three | `task provider`, `owner timezone`, `owner datastore`, `durable memory`, `identity files`, `checkpoint store`, `effects ledger` |

## The recurring failure, three more times

Batch 1 closed on a finding: *a rule stated but not carried into the
artifact, or carried into the artifact so hard it eats the deliverable —
and both are fixed at the artifact definition, not by restating the
rule.* Every one of this batch's four fix iterations is the second
direction of it.

| Skill | The rule | What it ate |
|---|---|---|
| daily-task-manager | resolve the target the request names | Same-turn authority fired on a resolved target and wrote a mirror row for a provider object that did not exist |
| briefing | surface conflicts, never resolve them silently | Refused to say a cancelled meeting was cancelled |
| owner-dream-cycle | stop on an incomplete corpus | Failed closed on the rerun case, hiding the idempotency it was asked to demonstrate |
| owner-dream-cycle | worldview candidates need repeated evidence | Weighed a candidate only against repetitions of itself, never against what contradicts it |

Three of the four were invisible to `make validate` and to the
amendment-8 mechanical check, and visible only in the behavioral run.
The check compares a cited rule against the v1 sentence it replaced; it
has no procedure for a v1 **action** that survived into the rewrite as a
**mention in a different section**, which is what happened to
`counterevidence`. That is a gap in the check worth closing for
batches 3–8: after folding, grep the v1 body for its imperative verbs
and confirm each still sits on a numbered Workflow step or a shape
field, not in prose.

## Open fixture debt

**Fourteen** assertions across this cluster — 8 in `daily-task-manager`,
2 in `briefing`, 4 in `owner-dream-cycle` — assert behaviour that cannot
be produced in a text-only harness without fabricating it, and **the
graders flagged six of them themselves**, unprompted, in the run's
`structurally_unsatisfiable` block. Full table and the recommended
repairs are in the task report; the shape is uniform:

| Fixture | Flag | Suggested repair |
|---|---|---|
| `daily-task-manager examples:1` — `State SYNCED_VERIFIED`, `Provider readback matches`, `Mirror stores provider ID` | `SYNCED_VERIFIED` is reachable only after a provider readback matches; with no connector the honest state is `BLOCKED`. The grader: "a literal-string check on an internal state label, so a response could emit the token without any of the underlying verification and still pass" | Bind to evidence — "reports the state actually reached and does not claim `SYNCED_VERIFIED`" — or stub a provider |
| `daily-task-manager examples:1` — `Tomorrow derived with trusted timezone` | The grader: "passes for any response that mentions a timezone, and fails for one that computes the correct date but flags timezone uncertainty" | "States the resolved date and the zone it came from, and whether that zone was read or assumed" |
| `daily-task-manager examples:2` — `Existing provider ID returned` | No provider, no ID | Rewrite for the empty-provider case |
| `daily-task-manager examples:3` — `Ambiguity reported with IDs` | The grader: "conflates two things (detecting ambiguity, and citing IDs) and the response passes the first while failing the second" | Split into "reports the match as ambiguous / does not auto-pick" and "cites the ids or titles of both candidates" |
| `daily-task-manager examples:3` — `Active provider tasks searched` | The grader: "a response could assert 'I searched active tasks' without any retrieval and superficially satisfy the current phrasing" | Name the observable evidence of the search |
| `briefing examples:1` — `Calendar and task provider queried authoritatively`, `Current owner date/timezone resolved` | No calendar or task conduit exists; the coverage ledger correctly records `unavailable: no conduit` | Stub the providers, or assert the ledger rows instead |
| `owner-dream-cycle examples:1/2` — `Corpus hash recorded`, `Same run identity`, `Idempotency verified` | There is no exporter and no prior run, so no hash exists to record or match | Supply a corpus hash and a prior report in the prompt |

## Rulings — the ledger namespaces (settled in fix round 1)

The batch raised one ruling request and it was granted. **A skill
declaring any mutating effect declares `effects` in `writes_to` (M7); a
skill declaring `notify:owner` declares `notifications` (notifications.md
§Ledger).** design-os-foundations §9 gave `owner-dream-cycle`
`writes_to: [journal, profile, decisions, projects]` with neither, while
M7 requires an effects record for every mutating effect and
`validate_namespaces` errors on a body naming an undeclared namespace —
so the body had been citing M7 through the `effects ledger` *vocabulary
term* to keep the namespace scan quiet, which is a workaround rather
than a declaration.

Applied here: `owner-dream-cycle` is now
`writes_to: [journal, profile, decisions, projects, effects,
notifications]` and its Dependencies line names both ledgers directly.
`daily-task-manager` already declared `effects`. `briefing` declares no
mutating effect and correctly gains neither. The validator rule that
enforces this lands in cleanup, where cohort-1's
`medication-and-symptom-log` gets the same retro-fix.

## Findings for the batches that follow

1. **A repo description can outbid a CLI built-in** — quote the intent's
   exact phrasing in the trigger and exclude the built-in's own scope by
   activity. `cron-scheduler:4` moved from `schedule` to
   `daily-task-manager` on "'remind me to renew the insurance next
   Tuesday'" plus "a single task" and "not … anything recurring".
   Batch 1 recorded built-in hijacks as unwinnable; they are not always.
2. **`SENTENCE_SPLIT_RE` splits on `.`, so an inline link to a `.yaml` or
   `.md` file cuts a sentence in half — and can strip a negation away
   from the keyword it was protecting.** `briefing`'s checkpoint rule
   read as one sentence to a human and three to the scanner, only the
   first carrying `never`. Put the negation and the effect keyword
   **before** any file link in a sentence that relies on the M8 escape.
3. **The negation escape is almost always avoidable.** `briefing` ends
   with exactly one, deliberately, for `checkpoint:advance`; three others
   in the first draft were removed by rewording (`store` → dropped,
   `credential` → "sign-in secret") rather than kept.
   `owner-dream-cycle` needs **zero**: every hint keyword in it passes by
   declaration. A file leaning on several escapes is usually describing
   effects it should either declare or not be doing.
4. **The amendment-8 check does not cover a v1 action folded into your
   own prose.** It compares cited rules against replaced v1 sentences,
   and `counterevidence` slipped through as a mention inside a shape
   description. Add a pass: grep the v1 body for imperative verbs and
   confirm each still lands on a Workflow step or a shape field.
5. **Both directions of batch 1's recurring failure appear in one
   batch.** Four fix iterations, all of them a rule eating its own
   deliverable, none of them caught by the validator. Budget one fix
   iteration per skill as the expected case, not the exception.


---

# Fix round 1 (review of the batch)

Six Important findings, all small, plus one regression the fixes
themselves caused and closed. `make validate` exits 0 with 17 warnings,
`baseline check` exits 0, 499 tests OK. All three skills re-gated and
re-baselined from clean post-commit runs; **no skill's numbers moved**.

| Skill | with / without | Discriminating | broken / harmful | Run |
|---|---|---|---|---|
| daily-task-manager | 52.1% / 33.3% | 3/16 | 8 / 0 | `20260829T043417-ff51507` |
| briefing | 87.5% / 56.3% | 5/16 | 2 / 0 | `20260829T043527-ff51507` |
| owner-dream-cycle | 75.0% / 31.3% | 7/16 | 4 / 0 | `20260829T043909-3829af7` |

Unchanged from the batch numbers. The routing ballot was **not re-run**:
no description was edited in this round, so the ballot is byte-identical
and the table above stands.

## What changed

1. **`briefing` binds the search rule.** `contracts/datastore.md`'s verb
   table says every `search` hit must be `read` before it is used, and
   the rewrite had bound the other three verbs but not that one.
   Workflow step 3 now says a hit is not yet evidence, so no claim rests
   on a snippet, a title, or a rank.
2. **`owner-dream-cycle` binds staleness and supersession.** A page
   whose compiled truth is older than its newest timeline entry is
   stale — that is the supersession signal, and a stale page is context
   and never current truth (F2). v1's dropped action is restored with
   it: an older goal or commitment is stale until this corpus reaffirms
   it, carried in to test the new turns against rather than cited back
   as live. v1's **"trial one closed day and inspect the ledger before
   enabling recurrence"** is restored as a Workflow clause.
3. **`daily-task-manager`'s sync-reference claim was false.** "Adds
   nothing to them and restates none of them" is replaced by what the
   file does: cites `sync.md` for the state machine, the mutation order
   and the reconciliation cases, and restates exactly two — the one-way
   mutation order and the never-roll-back rule — with the reason. Both
   reports' "all cited, none restated" line is corrected above.
4. **Two X2 mis-cites → X3.** X2 is an owner-set hard constraint.
   Neither `briefing`'s "the disagreement cannot be represented without
   picking a side" nor `owner-dream-cycle`'s "a rerun would produce a
   second record" is one; both are facts that would be asserted with
   nothing behind them. Both now carry the consequence in the sentence.
5. **`owner-dream-cycle`'s corpus boundary reconciled.** `When to use`
   and `Inputs` accept "or the span" while `Privacy and mutations` said
   "one closed local day". Both are true and the relation is now
   written: the privilege operates **per closed day**, and a longer span
   is a sequence of closed days each with its own hash and its own
   ledger, never one undifferentiated corpus. What a span adds is the
   comparison across those days, not a wider grant.
6. **Ledger namespaces**, per the ruling above.

## The regression this round caused, and closed

The staleness clause (2) read as a **precondition** rather than as a
weighting rule, and `owner-dream-cycle` case 1 went **2/4 → 0/4** on an
empty ledger: "## 3. Candidate ledger — No rows", with the response
explaining that it had been told visitor text and tool output were
present but had "none of it to isolate and exclude". **Two** assertions
regressed, both of them gains the rewrite had made — the run's summary
line counted three, but a direct diff of the two `results.json` files
shows exactly two `with_skill` losses, each also dropping
discriminating → broken. The other two of case 1's four assertions were
already broken before this round and are fixture debt (see the table
above).

This is batch 1's finding for the **fifth** time in this batch, and the
fix is the one `wardrobe-and-packing` needed: *a gap marks provenance,
it does not withhold the artifact.* The staleness rule is now scoped to
how a record that **was** read is weighed and explicitly does not gate
whether the ledger is built; where no durable record is reachable every
row is still written, with `supersedes` saying so. And a request that
names the classes of content a transcript holds — owner turns, quoted
visitor text, tool output — has named exactly what must be classified,
so each class becomes a row carrying its `origin` and its authority with
`unknown` spans. **"No rows" is never the answer to a request that names
content.** Back to 12/16 across the file and 2/4 on case 1 — the two assertions the rewrite had gained, `Visitor and tool content excluded as authority` and `Quoted instructions remain data`, both recovered — with 0 regressions.

That five of the batch's six fix iterations are the same failure is the
strongest finding either report carries: **the artifact definition, not
the rule statement, is where these skills are actually written.**
