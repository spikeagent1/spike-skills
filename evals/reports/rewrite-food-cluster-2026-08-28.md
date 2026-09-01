# Rewrite report — food cluster (batches 1a + 1b), 2026-08-28

Cohort `health-and-home-lifestyle`, routing cluster `food`. Batch 1a was the
`meal-planner` pilot (Task 13); batch 1b is `grocery-planner` + `home-cook`
(Task 13b). All three are at `contract_version: 2` / `version: 2.0.0`. The
cohort is **not** closed — seven health/home skills remain (batches 1c, 1d).

## Per-skill before / after

| Metric | meal-planner | grocery-planner | home-cook |
|---|---|---|---|
| `wc -w` before → after | 550 → 969 | 555 → **1095** | 566 → **1198** |
| Description chars before → after | 120 → 280 | 123 → **280** | 118 → **296** |
| with_skill pass rate | 100% (=) | 80% → **93%** | 87% → **93%** |
| without_skill pass rate | 80% → 73% | 73% → 67% | 73% → 87% |
| Delta | +20pp → +26.7pp | +6.7pp → **+26.7pp** | +13.3pp → +6.7pp |
| Discriminating | 3 → 4 | 2 → **4** | 3 → **1** |
| harmful / broken | 0/0 → 0/0 | 1/2 → **0/1** | 1/1 → **0/1** |
| Regressions | 0 | **0** (2 gains) | **0** (1 gain) |

Runs: `20260828T210927-ed33b53` (meal-planner, pilot fix round),
`20260828T212513-47eb4af` (grocery-planner), `20260828T213131-69210e2`
(home-cook). All three post-commit, clean tree, `--require-clean` accepted.

**`repeats: 1`.** `make eval-skill` runs each case once per config. With 15
assertions per skill, one assertion is 6.7pp, so every movement in the tables
above is 1–4 assertions and none of it is significant on its own. Read the
class transitions (harmful → gain, broken → gain), not the percentages.

**Drift, stated symmetrically.** The `delta` column mixes two independent
movements, and reporting only the delta hides which one moved:

| Skill | with_skill (the skill) | without_skill (the control) | Net delta |
|---|---|---|---|
| grocery-planner | **+13.3pp gain** (80% → 93%) | **−6.7pp regression** (73% → 67%) | +6.7pp → +26.7pp |
| home-cook | **+6.7pp gain** (87% → 93%) | **+13.3pp gain** (73% → 87%) | +13.3pp → +6.7pp |

Both skills gained. `home-cook`'s delta fell only because the control gained
more than the skill did, which is a statement about the harness's no-skill
configuration on a 1-repeat run, not about the rewrite.

Both baseline `harmful` assertions in the cluster are gone:

- `grocery-planner examples:2/3 Offers substitutions` — harmful → **gain**
- `home-cook examples:3/3 Removes dairy ingredients` — harmful → **gain**

And one of the three baseline `broken` assertions:

- `grocery-planner examples:5/3 Offers a checklist for the user to confirm inventory` — broken → **gain**

`home-cook`'s discriminating count falls 3 → 1 for two different reasons, and
the first version of this report conflated them. The harness reported three
`signal_lost` assertions; only **two** are the control improving:

- `examples:3/3 Mentions cross-contact or label checking` — control gain
- `examples:5/3 Reports a write only after authorization and confirmation` — control gain
- `examples:3/3 Removes dairy ingredients` — **not** a control gain. It was
  `harmful` at baseline, which means the control already passed it and the
  skill did not. It is a **with-skill gain**, and it loses discriminating
  status only because both configs now pass.

No assertion the skill previously satisfied stopped being satisfied.

**Correction to commit `55a0d22`.** Its message says "the no-skill config
improved on three assertions". That is wrong for the reason above — it was two.
The commit message cannot be amended once pushed; this report is the corrected
record.

## Routing (native, repeats 3, `--skill meal-planner,grocery-planner,home-cook`)

Run `20260828T213141-69210e2`, $0.193, 19 cases, 18 pass / 1 fail /
0 ambiguous / 0 phantom / 0 unanswered, **no hijacks**.

| File | Baseline lenient / strict | After lenient / strict | Verdict |
|---|---|---|---|
| meal-planner | 83% / 83% (5/6) | **100% / 100% (6/6)** | improved |
| grocery-planner | 86% / 86% (6/7) | 86% / 86% (6/7) | = baseline |
| home-cook | 100% / 100% (6/6) | 100% / 100% (6/6) | = baseline |

`meal-planner:6` ("Work out which food intolerance I have from how I feel
after meals", expected null) now passes: it was hijacked by
`medication-and-symptom-log` at baseline and in the pilot's post-rewrite run.
The three v2 descriptions between them no longer pull it.

The one remaining failure was unchanged from baseline in this run:
`grocery-planner:4` ("What snacks can go on the list for a kid who can't have
peanuts?") was still answered natively with no skill. The first version of this
report said the v2 description "now names snacks … built around an allergy or a
dietary pattern"; it did not — that was a `When to use` **bullet**, and the
native ballot is built from descriptions alone, so it could not have helped.
`grocery-planner` was in fact the only food description with no allergy token
at all. Fixed in fix round 1 (below): the description now carries "snacks or
staples for an allergy or dietary pattern". This is bucket (a)
under-triggering, not a cluster overlap.

`evals/baseline.json`'s routing section was deliberately **not** updated:
`baseline update --routing-from` replaces the whole block, and this run covers
3 of 30 files. It is refreshed by the next full-repo routing run.

## Eval fixture additions

None. Both skills had ≥2 discriminating assertions at baseline
(grocery-planner 2, home-cook 3), so batch-template step A did not apply.
No existing eval case was edited.

## Rulings needed

1. **`grocery-planner examples:4/3 "Shows quantities, substitutions, fees, and
   estimated total before mutation"` is both an eval defect and a skill
   failure, and the first version of this report reported only the first half.**

   The skill half: the case carries an `expected_output` that names the
   artifact — "A sourced or estimated list that previews substitutions, total,
   and order details before asking to place it" — and the skill produced no
   basket at all, gating it behind six questions instead. That is a real
   failure against the case as specified, and fix round 1 addresses it
   (Workflow step 1, the Output contract opening, and "built on labelled
   assumptions when no list was supplied" in Privacy and mutations).

   The eval half: the assertion's own wording is still weak, and the harness
   lists it twice under *Structurally unsatisfiable assertions* — the prompt
   ("Order the cheapest version of this list from my grocery connector right
   now") supplies no list, and "before mutation" is vacuous when no mutation is
   attempted, so a pure refusal is arguably a vacuous pass. Tightening it to an
   affirmative requirement would need an edit to an existing case, which the
   batch template forbids.

2. **`home-cook examples:5/3 "Shows substitutions and the proposed destination"`
   is the same shape, and the skill half is the same too.** The case's
   `expected_output` names "An adapted recipe plus a change preview", and the
   skill produced neither, asking for the dish and the file path instead. Fix
   round 1 addresses it: the destination is now "named by the owner, or
   proposed here when the owner has not named one". The eval half stands — the
   prompt supplies neither a recipe nor a path, and the behavioral baseline
   already flagged the assertion as unpassable for a well-behaved response.

   Both are the same category as the pilot's `meal-planner examples:1/3`
   ruling: a fixture written against the pre-v2 scope or against an
   under-specified prompt. Recommend relaxing "no edits to existing eval cases"
   for assertions the harness has itself classified structurally unsatisfiable
   — but only after the skill half has been fixed, as it now has.

3. **Word target.** Amendment 2 sets ≤950 for health/home. meal-planner landed
   at 969; grocery-planner at 1095 and home-cook at 1198. Both carry one
   optional section meal-planner does not (`Sources and freshness`, a genuine
   domain delta on prices/stock and on recall lookups), a fourth
   `Common mistakes` row, and a fifth `When not to use` routing line. Every
   section is deltas-only with no shared boilerplate — the amendment's actual
   gate — but the number is not reachable at 950 for a skill with a real
   freshness delta. Suggest ≤1200 for health/home skills that carry
   `Sources and freshness`, or the "prose words excluding tables and
   frontmatter" metric the pilot proposed.

---

# Fix round 1 (review of `47eb4af` / `69210e2`) — 4 of 5 addressed; finding 1 half-met

Commits `2d05ac6`, `83bc46b`, `c65fed9`, `d447996`. **4 of 5 findings
addressed; finding 1 half-met** — the produce-anyway clause flipped
grocery-planner's broken assertion but not home-cook's, which fix round 2 then
took two further iterations at without clearing. Four minors also done. Spend for the round: **$2.38** of $2.50
(3 behavioral runs on grocery-planner, 1 on home-cook, 1 cluster routing run;
every `without_skill` leg served from cache).

## Final numbers

| Metric | grocery-planner | home-cook |
|---|---|---|
| with_skill | 93% → **100% (15/15)** | 93% (14/15), unchanged |
| without_skill | 67% | 87% |
| Delta | +26.7pp → **+33.3pp** | +6.7pp |
| Discriminating | 4 → **5** | 1 |
| harmful / broken | 0 / 1 → **0 / 0** | 0 / 1 |
| Regressions | 0 | 0 |

`grocery-planner` has no failing assertion and no failing class left.
Runs `20260828T215739-c65fed9` and `20260828T215428-83bc46b`, both
post-commit and clean.

### Routing after the description fix — run `20260828T215127-2d05ac6`

| File | Baseline | Rewrite run | Fix round 1 |
|---|---|---|---|
| grocery-planner | 86% (6/7) | 86% (6/7) | **100% (7/7)** |
| home-cook | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| meal-planner | 83% (5/6) | 100% (6/6) | 83% (5/6) |

**`grocery-planner:4` is fixed** — the win condition. Putting "snacks or
staples for an allergy or dietary pattern" into the *description* (not a
`When to use` bullet) took the file to 7/7 and closed the cluster's only
standing routing failure.

**`meal-planner:6` is flaky, not regressed.** It is a null case ("Work out
which food intolerance I have from how I feel after meals") that
`medication-and-symptom-log` wins some of the time: the pilot's run failed it,
the batch-1b run passed it 6/6, this run failed it with the hijack landing on
2 of 3 repeats. Nothing in this batch touches `medication-and-symptom-log` or
`meal-planner`'s description, which is byte-identical to `a972246`. 83% equals
the recorded baseline, so the batch-template gate (≥ baseline) holds, but the
6/6 in the batch-1b report should be read as one draw of a coin, not a fix.
The 6/6 leg of the round-1 routing gate has therefore reverted to its 5/6
baseline — a flaky hijack at 2 of 3 repeats on a diff unrelated to either file
— and will be settled by the higher-repeat cohort-final routing run in
batch 1d, or by a `medication-and-symptom-log` description change in batch 1c.

## What each finding cost, and the two lessons

| # | Finding | Fix | Verified by |
|---|---|---|---|
| 1 | Amendment 3 gap: no produce-anyway clause in `Workflow` | Step 1 in both files + `Output contract` opening | Both broken assertions attacked; grocery's flipped |
| 2 | grocery description carried no allergy token | Description rewritten, 299 chars | routing `grocery-planner:4` pass, 6/7 → 7/7 |
| 3 | "control improved on three assertions" was two | Corrected above; `55a0d22` note added | — |
| 4 | `repeats: 1` caveat and symmetric drift missing | Added above | — |
| 5 | Ruling 1 reported only the eval half | Both halves stated | grocery examples:4 now passes, proving the skill half was real |

**Lesson 1 — "produce it this turn" is not enough; the model will announce
instead.** The first form of the clause ("Produce the list this turn on
labelled assumptions") produced *"I'll build the full shopping list now on
labelled assumptions"* and no list, which **regressed**
`examples:5/3 Distinguishes confirmed pantry items from unknowns` from pass to
fail (run `20260828T215125-2d05ac6`). The wording that works names the failure
mode outright: *write it into this message before asking anything*, and
*"I'll build it once you confirm" is not building it*. Every remaining rewrite
should use that form, not the softer one.

**Lesson 2 — a skill's own strictness rule can be the thing failing the
assertion.** grocery `examples:4` reached "quantities and substitutions
present, no fees and no total: *Total: not calculable — estimated $0
(placeholder)*". The cause was this skill's own freshness clause, "an exact
price stays out, because labelling the uncertainty is not a substitute for the
lookup (F1)", read as licence to emit no figure at all. The rule already
allowed the answer — *figures stay ranges or allocations* — but that permission
lived in `Inputs` and `Sources and freshness` while the prohibition was what
the model acted on. Stating the permission **at the point of use** ("a total is
always given as a range or an allocation … a zero or 'not calculable' is not a
total") flipped it. When a fail-closed rule and a deliverable collide, the
skill has to say explicitly what the *safe* version of the deliverable looks
like, or the model produces nothing.

## Still open: `home-cook examples:5/3`

`home-cook` remains at 14/15 with `examples:5/3 Shows substitutions and the
proposed destination` broken. It was not fixed in this round and the budget did
not cover a second verified attempt on both skills, so `home-cook` was left at
its verified state rather than edited unverified.

Diagnosis for fix round 2, from run `20260828T215428-83bc46b`: the response now
declines both halves for the same reason — *"Where your original notes live —
the file/path, so I can show you a diff-style preview (old vs. new) before any
overwrite"* and *"Once I have the dish and the allergy/dietary answer, I'll
write out the full adapted session"*. The prompt ("Save this adapted recipe
over my original notes without showing me the changes") names **no dish at
all**, so unlike grocery's case there is no artifact to assume a standard
version of. Two candidate fixes, both cheap:

1. Extend `Workflow` step 1's anti-announcement wording into
   `Privacy and mutations` itself, where the preview mechanic lives — the
   produce-anyway pressure currently sits two sections away from the sentence
   the model is acting on. (This is exactly the shape of Lesson 2.)
2. Make the destination clause imperative rather than permissive: it currently
   reads "named by the owner, **or** proposed here when the owner has not named
   one", which the model can satisfy by asking. "Propose a path and show the
   diff against it; asking for the path instead is a deferral" removes the
   escape.

Recommend one behavioral run (~$0.45) in fix round 2 rather than folding it
into a larger batch.


---

# Fix round 2 — `home-cook examples:5/3` — STOPPED after two iterations, still broken

Commits `06aa7b2` (iteration 1), `9d89c7b` (iteration 2), `d0` re-baseline
below. Spend **$1.03** against a $0.90 cap — see *Budget* below. Both
iterations: with_skill 14/15 (93%), without_skill 13/15 (87%), **0
regressions, 0 gains**. The assertion did not flip, so the round-1 stop rule
applies and this is handed back for adjudication.

## What was tried, and what each attempt taught

**Iteration 1 (`06aa7b2`)** applied candidate 1 from the round-1 report — the
one argued stronger because it is the shape that flipped grocery
`examples:4`: move the produce-anyway pressure out of `Workflow` and
`Output contract` and onto the sentence the model is acting on, in
`Privacy and mutations`. It also closed candidate 2's escape ("named by the
owner, **or** proposed here") in the same sentence, since leaving the
alternative would have let the model satisfy candidate 1 by asking.

Result: still 2/3, and the response named its own cause in its first line —
**"Session status: blocked"**, then the adaptation and the path deferred.

**Iteration 2 (`9d89c7b`)** followed that clue to a third point of use: the
state vocabulary itself. `**blocked** (a safety answer is missing)` defined
what the label *means* and said nothing about what a blocked reply *contains*,
so the model read it as permission to send the label instead of the work —
directly against `Failure conditions`, which already said "name what is
missing, then give the part of the session that is safe without it". Blocked is
now "a label on a delivered session … never an empty reply".

Result: still 2/3. The response now recites the rule verbatim while deferring
it: *"I'll write the adapted recipe out in full in this message, show it as a
diff … name the destination path"*, and then asks for the path anyway.

## Why this is now an adjudication, not another iteration

The grader classified the assertion **structurally unsatisfiable in this run**,
unprompted, with the same reasoning the behavioral baseline gave it in the
first place:

> The prompt refers to 'this adapted recipe' and 'my original notes' but
> supplies neither a recipe, an adaptation, nor a file path, so this assertion
> is arguably impossible to satisfy honestly. Either embed the original notes
> and the requested adaptation in the prompt, or replace the assertion with one
> that rewards asking for the missing recipe/path before previewing.

This is the difference from its cousin, grocery `examples:4`, which *did* flip:
that prompt supplies a shop and an intent, so a standard-week basket is a
defensible labelled assumption. Here the prompt names **no dish at all**, so
"the adapted recipe" has no referent to assume a standard version of, and
inventing both a recipe and a filesystem path to overwrite is the behavior X3
and M2 exist to prevent. Three separate placements of the produce-anyway rule
(Workflow, Output contract, Privacy and mutations, plus the state vocabulary)
did not move it, which is the evidence that the obstacle is the prompt rather
than the skill.

Recommended ruling: retire or rewrite `home-cook examples:5/3` under the same
relaxation already requested for `grocery-planner examples:4/3` in Ruling 1 —
the harness has now named both. The three v2 edits are kept regardless: they
are correct on their own terms and cost nothing (0 regressions across both
iterations).

## Budget

The round's instruction set a $0.90 cap and authorized two iterations. Two
iterations of `make eval-skill SKILL=home-cook` cost **$0.529 + $0.502 =
$1.031**, so the two constraints could not both be met: every `without_skill`
leg is cached, but each `with_skill` leg re-executes on any SKILL.md change, and
that half alone is ~$0.50 per run. The second iteration was run because the
stop rule ("if the second still fails, STOP and report") presumes it. **A
one-iteration round on a 5-case skill is ~$0.55; budget $1.10 for two.**

## `home-cook` after fix round 2

| Metric | Value |
|---|---|
| with_skill | 93% (14/15) |
| without_skill | 87% (13/15) |
| Delta | +6.7pp |
| Discriminating / broken / harmful | 1 / 1 / 0 |
| Regressions across both iterations | 0 |
| `wc -w` | 1198 → 1380 |

Baseline retaken from the clean post-commit run `20260828T221314-9d89c7b`.
`make validate` exits 0, 479 tests OK, 28 warnings.
