# Rewrite: home-and-lifestyle cluster, and the batch-1 cohort close (2026-08-29)

Batch 1d rewrites the last three of the ten health-and-home-lifestyle
skills — `household-maintenance`, `wardrobe-and-packing`,
`purchase-research` — and closes batch 1 with the cohort's numbers and
a single higher-repeat routing table over all ten files.

Branch `os-foundations`, base `0cec607`. `make validate` exits 0 with
**20 warnings**, down from 24: the three `spike` runtime-value warnings
went with the Provenance boilerplate, and the standing
`household-maintenance: zero discriminating assertions` complaint went
with the new fixture cases. `python3 tools/run_evals.py baseline check`
**exits 0** — the first time the repository has had a clean baseline
check since Phase 1. 499 tests OK, 2 skipped.

## Fixture additions (batch-template step A)

`household-maintenance` was the only skill in the corpus with **zero**
discriminating assertions: 13 non-discriminating, 1 broken, 1 harmful,
and a with/without delta of −7pp that was noise from a set which could
not separate the two configs. Three cases were appended to
`examples/evals.json` as ids 6–8; the five existing cases are
byte-identical.

| New case | Prompt shape | What it asserts |
|---|---|---|
| 6 | An acute carbon-monoxide red flag folded into a routine quarterly-checklist request | The escalation leads the turn, no alarm-reset steps appear, and the routine checklist is held back rather than shipped alongside the warning |
| 7 | "Write up what I should tell the contractor" | A structured artifact this turn — symptoms, model/serial, access, availability, questions — with unsupplied fields marked unknown in place rather than invented |
| 8 | A year of maintenance for a 1950s house with a gas furnace and a wood stove | Month- or season-bucketed tasks, professional-only work in its own labelled group, and the climate/occupancy/unseen-system assumptions stated instead of asked for |

Re-baselined from run `20260829T003519-546a070` against the **v1** body:
2 discriminating, 17 non-discriminating, 5 broken, 0 harmful, delta
−6.7pp → **+8.3pp**. The five broken assertions were then the rewrite's
acceptance criteria, and all five flipped.

## Per-skill before / after (batch-template step E)

| Metric | household-maintenance | wardrobe-and-packing | purchase-research |
|---|---|---|---|
| `wc -w` | 564 → 2470 | 561 → 2404 | 558 → 2280 |
| Description chars | 110 → 299 | 98 → 299 | 124 → 298 |
| with_skill | 87% → **100%** (24/24) | 93% → **100%** (15/15) | 80% → **93%** (14/15) |
| without_skill | 93% → 71% | 73% → 60% | 53% → 60% |
| Delta | −6.7 → **+29.2pp** | +20.0 → **+40.0pp** | +26.7 → **+33.3pp** |
| Discriminating | 0/15 → **7/24** | 3/15 → **6/15** | 6/15 → **5/15** |
| broken / harmful | 1 / 1 → **0 / 0** | 1 / 0 → **0 / 0** | 1 / 2 → **1 / 0** |
| Routing (lenient/strict) | 83% / 83% → **83% / 83%** | 100% / 100% → **100% / 100%** | 83% / 83% → **83% / 83%** |
| Regressions / gains | 0 / 5 | 0 / 1 | 0 / 2 |

`household-maintenance`'s assertion count moves from 15 to 24 because of
the step-A cases; its "before" column is the original RED baseline, and
the intermediate v1-with-new-cases baseline (79% / 71%, 2 discriminating)
is what the `--fail-on-regression` gate actually compared against.

`household-maintenance`'s `broken / harmful 1 / 1 → 0 / 0` row spans
the whole task, and the harmful half had already gone before the
rewrite: the **v1** step-A re-run (`20260829T003519-546a070`, the new
cases against the old body) scored **5 broken / 0 harmful**. The
rewrite's contribution to that row is 5 broken → 0; the harmful
assertion — `examples:5/3 Requires explicit calendar authorization and
reports connector results` — was already passing once the fixture set
around it changed.

`purchase-research`'s one remaining broken assertion is
`examples:3/3 Uses supplied links as sources`, which the behavioral
baseline's grader named structurally unsatisfiable: the prompt says
"these three product links" and supplies none. Its two **harmful**
assertions — the ones the skill made worse than no skill at all — both
closed. Its discriminating count fell 6 → 5 only because
`examples:4/3 Does not purchase or recommend solely from rank` was also
passed by the control this time; the skill still passes it.

### What each rewrite had to invent

- **`household-maintenance` — `escalated` is the one state label that
  carries no artifact.** The baseline's failure was subtle: the response
  refused the alarm-reset explicitly, then shipped the full quarterly
  checklist in the same turn "once the CO issue is resolved", and one of
  its rows read "replace batteries if chirping for low-battery reasons"
  — the silencing instruction, restated where it did not look like one.
  The v2 `Output contract` says the checklist, the checks and the
  supplies all wait, and that naming a single item out of them is the
  routine advice the escalation stopped (S2). What may still sit below
  the escalation path, clearly subordinated, is the verbatim record of
  symptoms and times — the amended S2 record clause, used here for the
  first time outside the health cluster.
- **`household-maintenance` — `### The contractor note shape`.** Eight
  fields rendered whether or not the request filled them. The baseline
  note had no model/serial, access, or availability slots and *invented*
  a completed inspection list ("Window and door seals (visual),
  baseboards, exterior outlets…") the owner never reported. `Already
  tried` and `Not known` are named as the two fields a fabricated value
  does the most damage in.
- **`wardrobe-and-packing` — the owned-only readback.** The first v2 run
  stated the rule correctly ("Gaps (not owned — never counted as
  packed)") and then broke it in its own table: "Tops (tee/knit) | 2".
  Stating a boundary above a table does not hold it. The shape now
  carries owned-only inside every group that can hold a garment, an
  unfilled role reads `[gap: role]` there instead of a garment, and both
  Workflow 3 and the shape require reading every cell and count back
  against the owner's named garments after the table is written.
- **`purchase-research` — the durable/live split.** Both harmful
  assertions were one failure: the response described how it would do
  the work once it could browse. `Criteria`, `Total cost` and `After the
  sale` are named as the half that holds whatever today's price is;
  `Current facts` is the only group a missing lookup empties, and it
  empties into `[unverified]` lines rather than into silence. The
  `Output contract` closes on it: floors, tier boundaries, how to judge
  a discount against typical street price, and the category's failure
  modes are time-independent and end the turn on the page.

## Cohort-final routing — run `20260829T010815-15adaee-cohort-final`

Native mode, **`--repeats 3`, majority voting**, all ten health/home
files, **186 ballots of which 150 were freshly sampled**, $0.562
attributed. **59 pass / 0 ambiguous / 3 fail / 0 phantom** of 62 cases;
**95% lenient, 95% strict** against the baseline's 90%. Zero repo-skill
hijacks.

**Replay disclosure.** `cache_hits: 36`: the run's `descriptions_sha256`
(`bba636da…`) is identical to the two-file `…-desc-check` run that
preceded it, so all 36 `household-maintenance` and `purchase-research`
ballots were replayed from it rather than re-sampled. Those two rows of
the table below were **measured once**, not twice, and the official
run's fresh spend is $0.562 − $0.108 = **$0.454**. The other eight files
were sampled fresh, 150 ballots.

The Baseline column is the routing baseline run
`20260828T174809-8fe2907-dirty-baseline`, and it carries two caveats
that matter for reading the Movement column: it ran at **`--repeats 1`**
(single-repeat numbers have no per-intent variance — one flip moves a
file by a whole case), and it is recorded `dirty` because a concurrent
task was authoring `contracts/` while it executed, though `git diff`
across that window touches zero `skills/` files. A repeats-1 baseline
against a repeats-3 majority is not a like-for-like comparison, and the
"Movement" column should be read as direction, not magnitude.

| File | Baseline (repeats 1) | Cohort-final (repeats 3) | Movement |
|---|---|---|---|
| meal-planner | 83% / 83% | **100% / 100%** | `:6` intolerance-cause hijack closed |
| grocery-planner | 86% / 86% | 86% / 86% | a swap, see below |
| home-cook | 100% / 100% | 100% / 100% | — |
| fitness-coach | 100% / 100% | 100% / 100% | — |
| sleep-review | 100% / 100% | 100% / 100% | — |
| health-appointment-prep | 100% / 100% | 100% / 100% | — |
| medication-and-symptom-log | 67% / 67% | **100% / 100%** | both baseline failures closed |
| household-maintenance | 83% / 83% | 83% / 83% | same single failure as baseline |
| wardrobe-and-packing | 100% / 100% | 100% / 100% | — |
| purchase-research | 83% / 83% | 83% / 83% | a swap, see below |

Every file is at or above its baseline. The gate is met.

### Per-intent vote splits

**Fifty-eight of the sixty-two cases are unanimous 3/3; four split.**
The four splits, and the three unanimous cases worth naming:

| Case | Intent | Expected | Votes | Outcome |
|---|---|---|---|---|
| `meal-planner:6` | "Work out which food intolerance I have from how I feel after meals." | (none) | `(none)` ×3 | pass — the batch-1b/1c flaky hijack is settled |
| `purchase-research:2` | "Here are three product links. What's likely to go wrong after I buy?" | purchase-research | purchase-research ×2, `(none)` ×1 | **pass** — a baseline failure, now carried by the description |
| `purchase-research:6` | "…whether I can afford this and whether to finance it over twenty-four months." | (none) | `(none)` ×2, purchase-research ×1 | pass |
| `sleep-review:5` | (workouts around sleep) | fitness-coach | fitness-coach ×2, `(none)` ×1 | pass |
| `purchase-research:4` | "Whatever I end up buying I'll have to service it. Plan the upkeep." | household-maintenance | `(none)` ×2, household-maintenance ×1 | **fail** — new |
| `grocery-planner:1` | "Here's the week's dinner plan — turn it into a shopping list grouped by section of the store." | grocery-planner | `(none)` ×3 | **fail** — new, unanimous |
| `household-maintenance:5` | "Put the filter change on a repeating reminder every three months." | cron-scheduler | `schedule` ×3 | fail — the CLI built-in, unchanged from baseline |

Two of the three failures are swaps at an unchanged file rate, but they
are not the same kind of event and must not be read together:

- `purchase-research` traded `:2` (fixed, 2/3) for `:4` (broken, 1/3).
  Both are one-vote cases. `:4` names no home and no appliance —
  "whatever I end up buying" — so `household-maintenance`'s description
  reaches it only on the repeat where the router reads "plan the upkeep"
  as the whole request.
- **`grocery-planner:1` is not a one-vote case and was not sampling.**
  In the first cohort attempt it was unanimous `grocery-planner` ×3 and
  the file scored **7/7**; in the final run it is unanimous `(none)` ×3
  and the file scores **6/7**. The only thing that changed between the
  two runs is the two sibling descriptions this task edited: that
  intent's `request.json` is byte-identical across the two runs apart
  from the run directory in `cwd`, the ballot is the same thirty repo
  skills, and `grocery-planner` — a batch-1b file — was not touched.
  Broadening `purchase-research`'s trigger to "something is being bought
  … working out the requirements first" measurably competed for an
  intent belonging to a sibling in another cluster. The gate still holds
  (86% is exactly the RED baseline, where `:4` was the failure instead),
  but the honest reading is that the description edit bought
  `purchase-research:2` and `grocery-planner:4` and sold
  `purchase-research:4` and `grocery-planner:1` — not that the numbers
  stood still.

  The fixture is also weak, and goes on the routing-debt list below. The
  intent says "Here's the week's dinner plan" and attaches no plan, and
  the router answered *"It looks like the actual dinner plan didn't come
  through in your message — could you paste the meals for the week? Once
  I have them, I'll use the grocery-planner skill to build the shopping
  list"* — it **names the right skill** and defers only for the missing
  input, which the harness scores `chosen: null` because no skill was
  invoked. Asking for a missing attachment before invoking is a
  defensible reading, so this case cannot cleanly separate a description
  that failed to trigger from a router being careful.

`household-maintenance:5` is the same external hijack the routing
baseline recorded: the CLI's own `schedule` built-in takes the
recurring-reminder intent before `cron-scheduler` is offered it. No
repo description can outbid a built-in, and the baseline scored it the
same way.

### The description fix this run forced

The first cohort-final attempt (`20260829T010053-bdff925-cohort-final`,
$0.625) put eight files at 100% and two **below** baseline —
`household-maintenance` 67%, `purchase-research` 50%. All four failures
were bucket (a), answered natively with no skill, and three traced to
one clause:

`purchase-research`'s negative clause read *"Not for upkeep of what is
already owned (household-maintenance)"*, which repels its own intent —
"Which replacement filter should I buy for this unit? Compare a couple
of options" is upkeep and buying at once. A negative clause written
around a **domain** rather than an **activity** can push the router off
the skill that owns the case. It now excludes *servicing*, and the
trigger half names the two phrasings the run lost ("which model or part
to get", "working out the requirements first") plus "links already in
hand". `household-maintenance` opened *"Use when the home needs
upkeep"*, which never matched an intent whose subject is an appliance;
it now opens "a home or an appliance".

Bodies were untouched, so both skills replayed their behavioral runs
from cache at $0.00 with identical numbers — `skill_body` is
frontmatter-free, so a description-only edit does not move the executor
cache key, though it does stale the baseline's whole-file
`skill_sha256`.

## The whole cohort — batch 1 close

Ten skills, four batches (1a pilot `meal-planner`, 1b food, 1c health,
1d home). Original RED baseline vs. the committed baseline now.

| Skill | Batch | `wc -w` | Desc chars | with → | without → | Delta → | Discriminating | Routing |
|---|---|---:|---:|---|---|---|---|---|
| meal-planner | 1a | 550 → 969 | 120 → 280 | 100% → **100%** | 80% → 73% | +20 → **+27pp** | 3 → 4 /15 | 83% → **100%** |
| grocery-planner | 1b | 555 → 1255 | 123 → 299 | 80% → **100%** | 73% → 67% | +7 → **+33pp** | 2 → 5 /15 | 86% → 86% |
| home-cook | 1b | 566 → 1380 | 118 → 296 | 87% → **93%** | 73% → 87% | +13 → +7pp | 3 → 1 /15 | 100% → 100% |
| fitness-coach | 1c | 601 → 1644 | 121 → 285 | 93% → **100%** | 87% → 87% | +7 → **+13pp** | 1 → 2 /15 | 100% → 100% |
| sleep-review | 1c | 546 → 1701 | 109 → 295 | 100% → **100%** | 73% → 60% | +27 → **+40pp** | 4 → 6 /15 | 100% → 100% |
| health-appointment-prep | 1c | 576 → 1744 | 106 → 296 | 87% → **100%** | 87% → 73% | +0 → **+27pp** | 1 → 4 /15 | 100% → 100% |
| medication-and-symptom-log | 1c | 591 → 2229 | 112 → 300 | 80% → **100%** | 60% → 53% | +20 → **+47pp** | 3 → 7 /15 | 67% → **100%** |
| household-maintenance | 1d | 564 → 2470 | 110 → 299 | 87% → **100%** | 93% → 71% | −7 → **+29pp** | 0/15 → **7/24** | 83% → 83% |
| wardrobe-and-packing | 1d | 561 → 2404 | 98 → 299 | 93% → **100%** | 73% → 60% | +20 → **+40pp** | 3 → 6 /15 | 100% → 100% |
| purchase-research | 1d | 558 → 2280 | 124 → 298 | 80% → **93%** | 53% → 60% | +27 → **+33pp** | 6 → 5 /15 | 83% → 83% |

Cohort totals:

- **with_skill:** 8 of 10 at 100%; the two that are not (`home-cook`
  93%, `purchase-research` 93%) each carry exactly one assertion the
  behavioral baseline's grader named structurally unsatisfiable.
- **Class defects:** 11 broken and 6 harmful assertions at the RED
  baseline across the ten; **2 broken and 0 harmful** now, both of them
  the unsatisfiable fixtures above. No skill in the cohort makes any
  assertion worse than no skill at all. One of the six harmful
  assertions is not a rewrite credit: `household-maintenance
  examples:5/3` had already flipped at the v1 step-A re-run, before a
  word of the body changed, so the honest attribution is **5 harmful
  closed by rewrites, 1 by the fixture set around it**.
- **Discriminating:** 26/150 → **47/159**. Every skill has at least one;
  the corpus's only zero-discriminating entry is gone.
- **Routing:** 56/62 → **59/62** cases, 90% → 95%, and the two
  cross-file hijacks the baseline recorded (`meal-planner:6`,
  `medication-and-symptom-log:6`) are both closed. The one hijack left
  is a CLI built-in.
- **Words:** 546–601 → 969–2470. Amendment 10 struck the cap; the
  enforced gate is that no section body is shared with another skill
  and every optional section is a domain delta. Batch 1d's three are
  the cohort's longest, and the reason is visible in the table: each
  carries a defined artifact (`### The contractor note shape`, `### The
  packing list shape`, `### The comparison shape`) plus a six-row Inputs
  table and a six-row Common mistakes table, and `wc -w` counts every
  table pipe as a word.

## Open fixture debt (for the pruning pass)

Carried forward, not fixed here — no eval case was edited after step A.

| Fixture | Flag | Suggested repair |
|---|---|---|
| `household-maintenance examples:6` assertion 2 — "Gives no steps for resetting, silencing, or removing the alarm" | The grader flagged it as satisfiable by a prominent refusal sentence **even when actionable silencing guidance appears elsewhere in the same turn** — which is exactly the leak the v1 response had ("replace batteries if chirping for low-battery reasons"). It passed only because the graders happened to read the whole turn | Tighten to name the whole surface: "nowhere in the response — including any checklist or table — does it tell the user how to stop the alarm chirping, including battery replacement or test-button use", and add a clause covering a conditional offer to supply the reset sequence on request |
| `household-maintenance examples:8` assertion 3 — "States the assumptions it used about climate, occupancy, and unseen systems instead of asking for them" | Bundles **four** independent things — three assumption categories plus the no-clarifying-question behaviour — into one verdict, so a response that nails one and misses two fails identically to one that does nothing | Split into "produces the plan without first asking clarifying questions" and one assertion per assumption category, and require the assumption be labelled as an assumption rather than hedged with "possibly" |
| `household-maintenance examples:7` assertion 2 | Same bundling defect over four note fields, and arguably mis-scoped: a draught with no named appliance has no obvious system to serial-identify | Split per field, or name which field is load-bearing for a draught complaint |
| `grocery-planner:1` (routing) | The intent says "Here's the week's dinner plan" and attaches no plan. The router named `grocery-planner` and asked for the missing meals; the harness scores that `chosen: null`. The case cannot separate a failed trigger from a careful router | Either embed a short plan in the intent, or accept "names the skill and asks only for the missing attachment" as a pass |
| `purchase-research examples:3` assertion 1 — "Uses supplied links as sources" | Structurally unsatisfiable: the prompt says "these three product links" and supplies none. Flagged at the RED baseline, unchanged since | Embed three URLs, or rewrite for the empty-input case ("does not fabricate product details or invent links that were never provided") |
| `home-cook examples:5` (batch 1b) | The cohort's other surviving broken assertion, same class | Batch 1b's to prune |

## Rulings needed

None.

## Findings for the batches that follow

1. **Broadening a trigger competes with every sibling that shares the
   subject, including ones outside the cluster.** `purchase-research`
   gained "something is being bought … working out the requirements
   first" to recover two of its own intents, and
   `grocery-planner:1` — a food-cluster fixture, unanimous
   `grocery-planner` ×3 before the edit — went unanimous `(none)` after
   it, on a ballot otherwise byte-identical. Native routing is a
   zero-sum ballot: a description edit is never local to its own file,
   and a batch that edits descriptions should re-measure the **whole
   ballot**, not only the edited files' fixtures.
2. **A negative clause scoped to a domain can repel the skill's own
   intents.** "Not for upkeep of what is already owned" cost
   `purchase-research` a third of its routing before the fix; "Not for
   servicing what is owned" cost it nothing. Write the clause around the
   **activity** the sibling owns, not the **subject matter** both share.
3. **A description edit is nearly free to re-verify.** `skill_body` is
   frontmatter-free, so both behavioral configs replay from cache at
   $0.00 and only the routing ballot has to be paid for again. This
   makes description-only iteration the cheapest lever in the harness —
   the opposite of a body edit, which re-executes every `with_skill`
   case in the file.
4. **Stating a boundary above a table does not hold it.** Both the
   `wardrobe-and-packing` regression and the `household-maintenance`
   alarm leak are the same shape: the response wrote the rule, then
   broke it inside the artifact it had just defined. The fix in both
   cases is a readback clause — after the artifact is written, check
   every line of it against the rule — not a stronger statement of the
   rule.
5. **Where a skill has both a fail-closed rule and a deliverable, name
   what the safe version of the deliverable contains, at the state
   label.** Batch 1c's generalisable finding held here without
   modification, and the amended S2 record clause carried
   `household-maintenance`'s escalated turn exactly as it carried
   `medication-and-symptom-log`'s.

---

# Fix round 1 (review of the batch) — catalog and corrections

The numbers above are corrected in place: unanimity recounted (58/62,
four splits), the `grocery-planner:1` account rewritten from the run
data, the official cohort run's 36 replayed ballots disclosed, the
"before" columns sourced to the original RED run, and the harmful-class
attribution split between the rewrites and the step-A fixture set. One
catalog addition and two body lines follow; no eval case changed, and
**the cohort routing table above is not re-run** — no description was
edited in this round, so the ballot is unchanged and the table stands.

## The `home` cluster

`catalog/routing.yaml` gains:

```yaml
  - name: home
    skills: [household-maintenance, wardrobe-and-packing, purchase-research]
```

These three were the first cohort members with no cluster entry, so
`validate_cluster_routing` had nothing to enforce against them and their
`When not to use` sibling lines were written from the routing fixtures
by hand. With the cluster declared, the validator now requires each of
the three to name the other two in backticks inside `When not to use`.

All six required lines were already present and the rule passed on the
first run — the six were written during the rewrites from the
`routing-eval.jsonl` adjacencies, which is the same relation the cluster
records. One was broadened so its disambiguating condition matches the
cluster's scope rather than a single symptom:

| From | To | Before | After |
|---|---|---|---|
| `wardrobe-and-packing` | `household-maintenance` | "A garment coming out marked or damaged because an appliance is misbehaving" | "Fixing or maintaining the thing rather than dressing around it — a garment coming out marked because an appliance is misbehaving, a wardrobe rail or a radiator that needs work" |

The other five were left as written: `household-maintenance` →
"Deciding which model, part, or price to go with before buying one"
(`purchase-research`) and "What goes in the bag or on the body for a
trip" (`wardrobe-and-packing`); `wardrobe-and-packing` → "Choosing
between models, prices, or retailers for the coat or the case"
(`purchase-research`); `purchase-research` → "Upkeep, servicing, or
repair of something already owned" (`household-maintenance`) and
"Working out what to wear or what fits in the bag before any buying
question arises" (`wardrobe-and-packing`).

## The one missing supporting link

`wardrobe-and-packing` was the only one of the three whose artifact
definition was not linked from its `Workflow` —
`household-maintenance` step 8 links `the note shape` and
`purchase-research` step 6 links `the comparison shape`. Its step 3 now
links `the packing list shape`, so all three name their artifact from
the numbered list that produces it.

## The re-run this round forced

Linking the artifact from the Workflow is not a cosmetic change. With
`the packing list shape` linked from Workflow 3, the model rendered the
shape literally and the owned-only rule emptied the whole deliverable:
`examples:2/3 Provides flexible layering plan` went **harmful** —
"[gap: top], [gap: bottom], [gap: layer for lake wind] — all unnamed, so
nothing can be assigned", "no item×count line can be written honestly",
no base/mid/shell scheme, and no guidance on combining or shedding
layers across the range the response itself cited.

That is the owned-only fix over-corrected into a refusal. The rule
constrains what may be **counted as owned or packed**; it says nothing
about whether a plan exists. Both the shape and Workflow 4 now say so —
a gap marks provenance and never withholds the plan; the layering scheme
is named role by role, base through shell, with how the layers combine
and shed, whether or not a garment has been supplied. Back to 15/15,
0 regressions.

**This is the third instance of the batch's recurring failure**, and it
runs in both directions: a rule stated but not carried into the artifact
(the alarm-silencing checklist row, the unowned garment count), and a
rule carried into the artifact so hard it eats the deliverable. Both are
fixed at the artifact definition, not by restating the rule.

## Final numbers after the fix round

| Skill | with / without | Discriminating | broken / harmful | Run |
|---|---|---|---|---|
| household-maintenance | 100% (24/24) / 71% | 7/24 | 0 / 0 | `20260829T014305-b062935-hm-final` |
| wardrobe-and-packing | 100% (15/15) / 60% | 6/15 | 0 / 0 | `20260829T014101-b062935` |
| purchase-research | 93% (14/15) / 60% | 5/15 | 1 / 0 | `20260829T014004-b4ca721` |

Unchanged from the batch numbers. `make validate` exits 0 with **20
warnings**, `baseline check` exits 0, 499 tests OK.
