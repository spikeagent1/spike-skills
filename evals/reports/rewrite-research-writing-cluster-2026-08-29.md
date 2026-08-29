# Rewrite report — research-and-writing cluster (2026-08-29)

`literature-review`, `fact-check`, `draft-in-voice` rewritten to the
canonical contract v2 template. Branch `os-foundations`, base `18a8b3c`,
final `29ab9e1`.

| Commit | What |
|---|---|
| `395e72f` | `feat(literature-review): rewrite to canonical contract v2` |
| `483cefb` | `feat(fact-check): rewrite to canonical contract v2` |
| `d8d3278` | `feat(draft-in-voice): rewrite to canonical contract v2` |
| `7ad56ef` | `fix(fact-check): a bare accuracy question is a source question` — **measured flat and reverted** |
| `a9a4e40` | the revert |
| `29ab9e1` | `test(evals): re-baseline research-and-writing after rewrite` |

## Per-skill table

| Skill | `wc -w` | desc chars | with (RED) | without (RED) | delta (RED) | disc. (RED) | broken (RED) | harmful (RED) | routing len/strict (RED) | Gate |
|---|---|---|---|---|---|---|---|---|---|---|
| literature-review | 934 → 2735 | 86 → 277 | **47.5%** (42.5%) | 27.5% (37.5%) | +20.0 (+5.0) | 4 (2) | 10 (10) | **0** (1) | **80% / 80%** (40% / 40%) | **pass**, 0 fix rounds |
| fact-check | 933 → 3166 | 90 → 297 | **80.0%** (76.7%) | 56.7% (60.0%) | +23.3 (+16.7) | 7 (5) | 6 (7) | 0 (0) | **50% / 50%** (25% / 25%) | **pass** on eval; routing below target |
| draft-in-voice | 977 → 3118 | 81 → 299 | **90.0%** (78.8%) | 70.0% (63.8%) | +20.0 (+15.0) | 4 (4) | **1** (2) | **1** (2) | 100% / 100% (100% / 100%) | **pass**, 0 fix rounds |

Behavioral runs, all post-commit on a clean tree, all with
`--fail-on-regression`: `20260829T061555-395e72f`,
`20260829T062438-483cefb`, `20260829T063249-d8d3278`. **Zero regressions
across all three skills; four gains.**

| Gain | Skill | Was |
|---|---|---|
| `examples:4/5 Screening/stopping rules` | literature-review | broken |
| `examples:5/5 Proposed replacement text returned` | fact-check | broken |
| `examples:3/4 Audience, purpose, destination, and byline requested` | draft-in-voice | broken |
| `examples:4/5 24 percent cited internally or metric omitted` | draft-in-voice | **harmful** |

Two of the batch's three `harmful` assertions cleared. Validator warnings
across the repo: **14 → 12** (`draft-in-voice` ×3 and `fact-check` ×1
runtime-specific values removed; runtime-specific hits are 0 for all
three files).

## Routing — run `20260829T063439-d8d3278-batch4-final`

Native, `--repeats 3`, ballot of 30 skills, 99 ballots over the 33 cases
owned by the five gate files. **25 pass / 0 ambiguous / 8 fail /
0 phantom.** $0.783.

| File | RED (repeats 1) | Batch-4 final (repeats 3) | Movement |
|---|---|---|---|
| literature-review | 40% / 40% | **80% / 80%** | **+40pp** |
| fact-check | 25% / 25% | **50% / 50%** | **+25pp** |
| draft-in-voice | 100% / 100% | 100% / 100% | flat (held) |
| publish | 67% / 67% | 67% / 67% | flat, file not touched |
| public-post-workshop | 83% / 83% | 83% / 83% | flat, file not touched |

**All five files held or rose, none fell, and no intent was sold to buy
another.** Every case that passed at RED passes now. The two untouched
files fail on exactly the cases they failed at RED: `public-post-workshop:1`
to the `publish` hijack, `publish:3` answered natively, and `publish:5`
to `schedule` at RED and to no skill now — the same fail either way.

**Bought (four intents, all previously answered natively with no skill):**

- `literature-review:2` "What does the research actually say about remote work and productivity over the last decade?"
- `literature-review:4` "Just tell me whether this one sentence in my draft is true." → now correctly `fact-check`
- `fact-check:2` "verify the facts in this essay against live sources"
- `fact-check:4` "this briefing came straight out of the brain — is this output hallucinating? re-derive every claim" — at RED this went to `briefing`; the cross-pair now resolves

**Still failing, all five to "answered natively, no skill":**
`fact-check:1`, `:3`, `:5`, `:8`, and `literature-review:3`.

### Ballot stability is the finding

**8 of 33 cases split**, against batch 3's 2 of 35. The split cases are
where the native router is genuinely marginal rather than decided:

| Case | Ballots | Outcome |
|---|---|---|
| `fact-check:2` | none, fact-check, fact-check | pass |
| `fact-check:5` | fact-check, none, none | **fail** |
| `literature-review:3` | none, none, literature-review | **fail** |
| `literature-review:4` | fact-check, fact-check, none | pass |
| `draft-in-voice:5` | draft-in-voice, draft-in-voice, none | pass |
| `public-post-workshop:1` | publish, publish, public-post-workshop | fail |
| `public-post-workshop:3` | public-post-workshop, public-post-workshop, none | pass |
| `publish:5` | none, schedule, none | fail |

Six of the eight splits are the same contest: **the skill against no
skill at all.** That is the shape of native under-triggering — not a
description the router cannot read, but a threshold the router applies
before it reads any description.

### The fix round that bought nothing

`fact-check` reached 4/8 against a 6/8 win condition, and the three
intents it did not buy — "fact check this draft before I post it", "is
this accurate? check the claims one by one", "run a source check on the
numbers in this post" — already appeared in the v2 description **word for
word**. The one budgeted fix iteration (`7ad56ef`) moved the description
from a trigger list to a trigger list plus the procedure ("every claim
checked against a current source") on the hypothesis that the two intents
that *did* trigger are the two that name external work.

Re-measured at `--repeats 3` on the same eight cases: **4 pass, 4 fail,
the identical four cases.** No movement in either direction, so the
commit was reverted (`a9a4e40`) and HEAD's tree is byte-identical to the
tree the five-file ballot measured. $0.368 spent to learn that the
description is not the lever here.

## Eval fixture additions

**None.** All three skills had at least one `discriminating` assertion at
RED (2, 5 and 4 respectively), so template step A did not apply and no
`examples/evals.json` or `routing-eval.jsonl` was touched.

## Rulings taken

1. **`literature-review` effects.** Design §9 proposed `fs:write-local`
   "for script output"; `scripts/lit_search.py` writes no file (every
   path ends at `print(json.dumps(...))`). Declared
   `effects: [provider:read]` for the four academic-index reads instead,
   with `reads_from: []` and `writes_to: []` — and therefore no
   `effects/` ledger namespace, since the Addendum's row was conditional
   on `fs:write-local`.
2. **The adapted-skill version fork.** `catalog/sources.yaml` gains
   `upstream_version`, and `validate_provenance_artifacts` compares
   `origin.json`'s `installedVersion` against it when present. `version`
   is the repository's own skill version; the installer's record of the
   upstream package is no longer forced to move with it. Pinned by a new
   test.

## Rulings needed

See `.superpowers/sdd/lets-audit-this-skillbase-giggly-umbrella/reports/task-17-report.md`
§ Adjudication requests: `fact-check`'s routing target, `draft-in-voice`
case 4's profile gate, and the 14 assertion instances the grader itself
declared structurally unsatisfiable on `literature-review`.
