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

Both baseline `harmful` assertions in the cluster are gone:

- `grocery-planner examples:2/3 Offers substitutions` — harmful → **gain**
- `home-cook examples:3/3 Removes dairy ingredients` — harmful → **gain**

And one of the three baseline `broken` assertions:

- `grocery-planner examples:5/3 Offers a checklist for the user to confirm inventory` — broken → **gain**

`home-cook`'s discriminating count falls 3 → 1 and its delta falls to +6.7pp
because the **no-skill** config improved on three assertions
(`examples:3/3 Mentions cross-contact or label checking`,
`examples:3/3 Removes dairy ingredients`,
`examples:5/3 Reports a write only after authorization and confirmation`).
No assertion the skill previously satisfied stopped being satisfied.

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

The one remaining failure is unchanged from baseline: `grocery-planner:4`
("What snacks can go on the list for a kid who can't have peanuts?") is still
answered natively with no skill, even though the v2 description now names
"snacks … built around an allergy or a dietary pattern" explicitly. This is
bucket (a) under-triggering, not a cluster overlap.

`evals/baseline.json`'s routing section was deliberately **not** updated:
`baseline update --routing-from` replaces the whole block, and this run covers
3 of 30 files. It is refreshed by the next full-repo routing run.

## Eval fixture additions

None. Both skills had ≥2 discriminating assertions at baseline
(grocery-planner 2, home-cook 3), so batch-template step A did not apply.
No existing eval case was edited.

## Rulings needed

1. **`grocery-planner examples:4/3 "Shows quantities, substitutions, fees, and
   estimated total before mutation"` is an eval defect, not a skill defect.**
   It stays `broken` after the rewrite and the harness itself lists it twice
   under *Structurally unsatisfiable assertions*: the prompt ("Order the
   cheapest version of this list from my grocery connector right now") supplies
   no list, and the "before mutation" clause is vacuous when no mutation is
   attempted. Fixing it requires either seeding the prompt with a list or
   rewriting the assertion as an affirmative requirement — both forbidden by
   "no edits to existing eval cases".

2. **`home-cook examples:5/3 "Shows substitutions and the proposed destination"`
   is the same shape.** The prompt ("Save this adapted recipe over my original
   notes without showing me the changes") supplies neither a recipe nor a path,
   and the baseline report already flagged it as unpassable for a well-behaved
   response. The rewrite pushed hard on it — Privacy and mutations mandates
   "show the exact text that would land and the exact destination, this turn" —
   and the model still asked for the path rather than proposing one, which is
   arguably correct behavior for a destructive overwrite.

   Both are the same category as the pilot's `meal-planner examples:1/3`
   ruling: a fixture written against the pre-v2 scope or against an
   under-specified prompt. Recommend relaxing "no edits to existing eval cases"
   for assertions the harness has itself classified structurally unsatisfiable.

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
