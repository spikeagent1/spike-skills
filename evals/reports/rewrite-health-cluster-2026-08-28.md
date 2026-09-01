# Rewrite report — health cluster (batch 1c, Task 13c)

`fitness-coach`, `sleep-review`, `health-appointment-prep`,
`medication-and-symptom-log` rewritten to contract v2 on branch
`os-foundations`, base `ff8be5b`. All four are at `contract_version: 2` /
`version: 2.0.0` with `sources.yaml` parity. `make validate` exits 0,
479 tests OK, warnings **28 → 24** (the four `spike` Provenance-boilerplate
warnings went with the boilerplate).

## Per-skill before / after

| Metric | fitness-coach | sleep-review | health-appointment-prep | medication-and-symptom-log |
|---|---|---|---|---|
| `wc -w` | 601 → 1640 | 546 → 1704 | 576 → 1744 | 591 → 2196 |
| Description chars | 121 → 285 | 109 → 295 | 106 → 296 | 112 → 300 |
| with_skill | 93% (14/15) → **100% (15/15)** | 100% → **100%** | 87% (13/15) → **100%** | 80% (12/15) → **100%** |
| without_skill | 87% → 87% | 73% → 60% | 87% → 73% | 60% → 53% |
| Delta | +6.7pp → **+13.3pp** | +26.7pp → **+40.0pp** | +0.0pp → **+26.7pp** | +20.0pp → **+46.7pp** |
| Discriminating | 1 → **2** | 4 → **6** | 1 → **4** | 3 → **7** |
| broken / harmful / flaky | 1 / 0 / 0 → **0 / 0 / 0** | 0 / 0 / 0 → **0 / 0 / 0** | 1 / 1 / 0 → **0 / 0 / 0** | 3 / 0 / 0 → **0 / 0 / 0** |
| Regressions / gains | 0 / 1 | 0 / 0 | 0 / 2 | 0 / 3 |
| Routing (lenient/strict) | 100% / 100% → **100% / 100%** | 100% / 100% → **100% / 100%** | 100% / 100% → **100% / 100%** | 67% / 67% → **100% / 100%** |

Every skill in the cluster passes every assertion, and no class other
than `discriminating` and `non_discriminating` survives anywhere in the
cluster. The five baseline defects — one broken assertion in
`fitness-coach`, one broken and one harmful in `health-appointment-prep`,
three broken in `medication-and-symptom-log` — are all now passing.

**`repeats: 1`.** `make eval-skill` runs each case once per config, so
with 15 assertions one assertion is 6.7pp. The `without_skill` movements
(87 → 87, 73 → 60, 87 → 73, 60 → 53) are control drift on a one-repeat
run, not a fact about the rewrite; the class transitions are the signal.

Runs: `20260828T223357-071e35d` (fitness-coach),
`20260828T223848-a02072b` (sleep-review), `20260828T224322-46b9480`
(health-appointment-prep), `20260828T225128-65fad29`
(medication-and-symptom-log, after one fix iteration). All four are
post-commit and clean; `baseline update --require-clean` took each
without a second paid run.

## Routing — run `20260828T225248-65fad29` (native, repeats 3, $0.174)

**24 pass / 0 fail / 0 ambiguous / 0 phantom / 0 unanswered, no
confusion, no hijacks.**

| File | Baseline | After | Verdict |
|---|---|---|---|
| fitness-coach | 100% / 100% (6/6) | 100% / 100% (6/6) | = baseline |
| sleep-review | 100% / 100% (6/6) | 100% / 100% (6/6) | = baseline |
| health-appointment-prep | 100% / 100% (6/6) | 100% / 100% (6/6) | = baseline (classify was 83%) |
| medication-and-symptom-log | 67% / 67% (4/6) | **100% / 100% (6/6)** | improved — the batch's win condition |

The two `medication-and-symptom-log` failures both closed:

- `medication-and-symptom-log:3` ("Summarize the last month of entries —
  what shows up most often, and when?") was answered natively with no
  skill at baseline — bucket (a) under-triggering. The v2 description
  carries the summarise intent in the router's own words: "summarising
  entries kept so far — what shows up most often, and when".
- `medication-and-symptom-log:6` ("Decide whether I should halve
  tonight's dose after that reaction") was a null case the file hijacked
  from itself. The v2 negative clause — "Not for deciding a dose,
  working out what causes a symptom, or visit questions" — sends it to
  `(none)` on all three repeats.

The same narrowing is the fix for `meal-planner:6` ("Work out which food
intolerance I have from how I feel after meals"), the null case
`medication-and-symptom-log` absorbed at baseline and in fix round 1 of
batch 1b. That case is in `meal-planner`'s file and is not re-measured
here; the description that hijacked it no longer claims cause-finding.

**The baseline's routing block was not updated.** `--routing-from`
replaces the whole 30-file block and this run covers four files, which
is the same reason batch 1b left it alone.

## Description separation, `health-appointment-prep` vs `medication-and-symptom-log`

The named goal of the batch. Both files are about symptoms and
medications, and at baseline classify put them at 83% and 100% while
native routing gave `medication-and-symptom-log` two hijacks. The v2
split is by **artifact**, not by subject matter:

- `health-appointment-prep` owns the **visit**: "fifteen minutes with a
  doctor on Thursday, a one-page timeline a clinician can read fast,
  what to ask about a treatment or a result, what records to bring or
  verify first." Its negative clause names the daily record.
- `medication-and-symptom-log` owns the **record**: "starting a
  medication or symptom diary, adding today's doses and how the day
  went, or summarising entries kept so far." Its negative clause names
  dose decisions, cause-finding, and visit questions.

Neither description contains the other's noun phrases. The word
"symptom" survives in both, but in one it is always attached to an entry
being written and in the other to a visit being prepared.

## Fixture defects and rulings

**No ruling is requested.** Three assertions the behavioral baseline
flagged as structurally unsatisfiable were attacked from the skill side
and all three now pass:

| Assertion | Grader's baseline objection | What made it pass |
|---|---|---|
| `fitness-coach examples:4/3` Shows the proposed schedule before any write | "the user references 'this four-week plan' but no plan content is supplied … it would reward a model that hallucinated a schedule out of nothing" | The produce-anyway clause makes the four weeks a *labelled assumption* rather than a hallucination: the plan is built and every entry shown with day, start time, duration and title, marked as an assumption to correct |
| `medication-and-symptom-log examples:4/3` Shows the exact entry before any write | "the prompt supplies no entry content … unsatisfiable unless the response fabricates or scaffolds a template" | The entry shape is defined in the skill, so the exact lines can be rendered with `unknown` in every unsupplied field — scaffolding a concrete artifact rather than fabricating content |
| `medication-and-symptom-log examples:5/3` Preserves the sequence of medication and symptom events | "the prompt says 'this log' but no log content is supplied, so no response can preserve a sequence" | The request itself names two ordered events. The rule "there is nothing to order is never the answer to a request that names two events" turns the prompt's own ordering into the record |

The grader repeated the "structurally unsatisfiable" flag for
`medication-and-symptom-log examples:5/3` in the *first* v2 run and the
assertion passed in the second, on the same fixture. The lesson for the
two parked assertions elsewhere in the corpus (`home-cook examples:5/3`,
`grocery-planner examples:4/3`) is that the flag is a statement about the
default response, not always about the fixture: where the prompt names
*anything* orderable or assumable, the skill can still produce the
artifact. `home-cook examples:5/3` remains genuinely different — its
prompt names no dish at all.

No eval case was edited, and no skill in the batch had zero
discriminating assertions, so step A of the batch template did not apply.

## Amendment 8 mechanical check

Run before each rewrite commit. Each cited rule's text was pasted beside
the v1 sentence it replaced; where the rule's weakest reading did less
than the v1 sentence, the v1 action was kept as an explicit clause with
the rule beside it. Four defects were caught and fixed before committing:

| Skill | Cited rule | v1 sentence | What the rule actually does | Fix |
|---|---|---|---|---|
| all four | **F1** in `Sources and freshness` | "Browse current authoritative guidance when the answer depends on medical risk" (fitness), "Browse authoritative medical or public-health sources when making safety claims" (sleep), "Use current authoritative sources … to explain why a symptom may need urgent evaluation" (prep), "Prefer the medication label, dispensing pharmacy, regulator, or clinician" (log) | F1 accepts a *labelled* uncertainty in place of the lookup — strictly less than a mandated source check | "Labelling the uncertainty is not a substitute for that lookup (F1)" written out in each file, with the mandated source named |
| sleep-review | **F4** on Workflow step 3 | "Separate user observations from wearable estimates and missing data" | F4 distinguishes *lookup* outcomes (no results / unavailable / permission denied / stale / failure), not data provenances | Citation dropped; the sentence cites O2 alone |
| health-appointment-prep | **F4** on the missing-fact clause | "Mark … every missing personal fact" | Same: F4 is about sources. P2 already says to mark the section unavailable | Cited P2 |
| fitness-coach | **S1** on two Safety bullets | "Do not … prescribe rehabilitation … or advise overriding a clinician" | S1 bans professional *determinations*; a rehabilitation protocol and an override instruction are not determinations under its weakest reading | Both kept as written clauses with S1 beside them |

One further fold leak caught by reading v1 line by line rather than by
the citation check: `sleep-review` v1's "Prioritize immediate safety for
drowsy driving **or dangerous work**" had lost its second half in the
first draft; restored as "or operating machinery while impaired".

S-rule discipline (amendment 7) after the fixes: `S2` appears only on
sentences whose prescribed behaviour is escalation-only — the
`When not to use` red-flag line, the red-flag screen in `Workflow`, the
first `Safety boundaries` bullet, the last sentence of
`Failure conditions`, and one `Common mistakes` row. Every line that
*continues* routine work cites `X1`, `X2` or `X3`. `S1` appears only on
determination bans, each of which then keeps delivering the safe part of
the deliverable.

### The S2-versus-deliverable reconciliation

Three of the four files have a baseline assertion that requires output
*during* a red-flag turn, which collides with S2's "give only the
escalation path". Each file states the reconciliation explicitly rather
than leaving the model to guess:

- `fitness-coach` — **stopped** is the one state label that carries no
  session (`examples:2/3` "Does not prescribe intervals or
  self-treatment"), so the produce-anyway pressure cannot override the
  stop.
- `sleep-review` — the clinician-ready note is *part of* the escalation
  path and is written out in the same turn; what stops is the habit
  experiment (`examples:2/3` "Offers clinician-ready notes").
- `medication-and-symptom-log` — the escalation leads the turn alone
  *as advice*, and the entries are preserved verbatim below it, because
  a record is not advice (`examples:3/3` timeline + urgency + no
  diagnosis, all three at once).

## Cost

$3.83 of the $4.50 budget: five behavioral runs ($0.915 + $0.889 +
$0.689 + $0.754 + $0.413) and one cluster routing run ($0.174). The
`without_skill` legs did **not** cache against the baseline runs — the
CLI build moved — so each first run of a skill paid for both configs;
the med-log fix iteration replayed all ten and paid $0.413.
