# Rewrite report — audience-and-community cluster (batch 7)

`skill-library-ops`, `social-listening-engagement-loop`,
`audience-content-engine`, `social-agent-practice`, and
`community-management` rewritten to `contract_version: 2`. Branch
`os-foundations`, base `a95813f`.

The heaviest batch: five skills, the most cross-references in the
corpus, the most runtime-specific values (4 + 7 + 11 + 9 + 14 = 45, now
zero), the one skill with real progressive disclosure, both adapted
skills' provenance rules exercised on one of them, and the facilitator
protocol rename. It is also the batch that takes the validator's warning
count to **0**.

## Per-skill

| Skill | Words | Desc chars | Pass rate (base → now) | without | Delta | Assertions passed | Disc. | broken | Runtime hits | Gate |
|---|---:|---:|---|---|---|---|---|---|---:|---|
| skill-library-ops | 1076 → 4019 | 93 → 288 | 66.7% → **75.0%** | 50.0% → 66.7% | +16.7 → +8.3pp | 8/12 → **9/12** | 2 → 1 | 4 → **3** | 4 → **0** | **met**, 0 regressions, 1 gain, no fix round |
| social-listening-engagement-loop | 1271 → 3760 | 117 → 294 | 78.3% → **90.0%** | 30.7% → 30.7% | +47.7 → **+59.3pp** | 15/19 → **17/19** | 9 → **11** | 4 → **2** | 7 → **0** | **met**, 0 regressions, 2 gains, no fix round |
| audience-content-engine | 1627 → 3936 | 127 → 297 | 100.0% → 95.0% | 37.0% → 37.0% | +63.0 → +58.0pp | 21/21 → 20/21 | 13 → 12 | 0 → 1 | 11 → **0** | **missed**, 1 regression after 1 fix round |
| social-agent-practice | 1107 → 4131 | 123 → 300 | 62.5% → **80.8%** | 37.5% → 25.0% | +25.0 → **+55.8pp** | 15/25 → **20/25** | 6 → **14** | 10 → **5** | 14 → **0** | **missed**, 1 regression after 1 fix round; +18.3pp and 6 gains |
| community-management | 1310 → 3757 | 119 → 295 | 91.7% → **100.0%** | 62.5% → 62.5% | +29.2 → **+37.5pp** | 22/24 → **24/24** | 8 → **9** | 1 → **0** | 9 → **0** | **met**, 0 regressions, 2 gains, 1 fix round |

Three quantities on three scales, per the task-18 ruling. **Pass rate**
is the case-weighted number `--compare-baseline` gates on. **Assertions
passed** is `discriminating + non_discriminating`. **Discriminating** is
the subset the control arm failed. `social-agent-practice` is the
clearest case of them moving independently: it gained five assertions
and **eight** discriminating, because its control arm fell 12.5pp at the
same time — the v1 file was scoring partly on what the model would have
said anyway.

Runs: `20260829T093935-e5f86d6-b7-slo` (skill-library-ops, 0
regressions), `20260829T095850-66ff431-b7-rest` (the other four, **6
regressions, 8 gains**), `20260829T101103-25ab424-b7-fix` (the three
fixed skills, 3 regressions, 8 gains), and
`20260829T101759-25ab424-b7-ace-regrade` (audience-content-engine
re-measured after an executor timeout left one case ungraded).
Routing: `20260829T095444-66ff431-b7-routing1`.

**Total spend $8.59**, against an $8.00 budget — **$0.59 over, and
reported rather than hidden**. Behavioral $8.00 by run ($1.420 + $4.220
+ $2.078 + $0.280) plus routing $0.597. Cached `without_skill` replays
are attributed but not spent and are excluded: the fix run was 17/17
cache hits on its control arm and cost $2.078 against $3.717
attributed, and the ace re-measure was 9/10 cache hits and cost $0.280
against $1.333. The overage is one item: the ace re-measure was not
optional — an executor timeout at the 180-second default left
`examples:1` ungraded, and `baseline update` refuses a degraded entry,
so the batch could not close without it.

`make validate` and `make test` (504 tests) green. Validator warnings
**0, down from 7** — the five files' 45 runtime-specific values and
`social-listening`'s two rejected frontmatter keys, which were the last
two v1 frontmatter warnings in the repository. `baseline check` returns
0 for all 30 skills.

## Routing — run `20260829T095444-66ff431-b7-routing1`

Native, `--repeats 3`, 48 cases across eight files, 144 ballots, $0.597.
**46 pass / 0 ambiguous / 2 fail / 0 phantom — 95.8%. Hijacks: none.**

| File | Baseline | Batch-7 | Movement |
|---|---|---|---|
| audience-content-engine | 50% / 50% | **100% / 100%** | `:1`, `:2`, `:3` each 3/3 to itself — **win condition ≥5/6 met** |
| social-agent-practice | 50% / 50% | **83% / 83%** | `:1` and `:2` won back 3/3 — **win condition ≥5/6 met** |
| skill-library-ops | 80% / 80% | **100% / 100%** | held; `:4` still routes to `team-skill-sharing-norm` as intended |
| social-listening-engagement-loop | 83% / 83% | **83% / 83%** | held |
| community-management | 100% / 100% | **100% / 100%** | held, all six 3/3 |
| public-post-workshop | 83% / 83% | **100% / 100%** | held at batch 6's measured 100%; not touched this batch |
| team-skill-sharing-norm | 80% / 80% | **100% / 100%** | held at batch 6's measured 100%; not touched this batch |
| draft-in-voice | 100% / 100% | **100% / 100%** | held, 8/8; absorbs nothing from this cluster |

The routing run is at commit `66ff431`, before the fix commit
`25ab424`. The fix changed no description in any of the three files it
touched (`git diff 66ff431 25ab424 -- skills/ | grep '^[+-]description:'`
is empty), so the measurement still describes the ballot as it stands.

### The batch-4 measurement the brief asked for

`draft-in-voice`'s description grew 81 → 299 chars in batch 4 and at RED
it was taking `audience-content-engine:1` and `:3`, which batch 4 never
re-measured. Measured here on the same ballot as `draft-in-voice`'s own
eight intents:

| Intent | Ballots | Result |
|---|---|---|
| `audience-content-engine:1` — *"Turn the validator work we shipped into drafts for the channels we're actually connected to"* | **3/3 → `audience-content-engine`** | won cleanly |
| `audience-content-engine:3` — *"Adapt the approved entry for a professional-network audience without changing anything it claims"* | **3/3 → `audience-content-engine`** | won cleanly |
| `draft-in-voice`'s own eight | 24/24 as expected (5 positives, 3 nulls) | undamaged |

Batch 6 measured `audience-content-engine:3` at 1/3 — one ballot
absorbed by `public-post-workshop`, one null. It was won back with
`audience-content-engine`'s **own** description and not by editing the
sibling: the description quotes the intent almost verbatim (*"reshape an
approved entry for a professional-network audience without changing what
it claims"*) and excludes the sibling by **activity** rather than by
topic (*"Not for a first draft's cold review"*). The boundary now holds
from both sides: `public-post-workshop:5` — *"Take the approved entry
and reshape it for the other channels we post on"* — went 3/3 to
`audience-content-engine`, and `public-post-workshop`'s own three
positives went 3/3 each to it.

### The two remaining routing failures

**`social-agent-practice:3`** — *"You wrote that entry because I asked
you to — did writing it change what you think?"* — 0/3, all three
answered natively with no skill. The belief-review trigger is the one
thing in this skill a model will answer from its own reasoning: it reads
as introspection rather than as a procedure, and the description carries
it as its last clause. Not fixed here: the skill met its win condition
without it and the budget for a description change plus a re-measure was
gone. Logged under *Skill debt*.

**`social-listening-engagement-loop:5`** — *"This one mention touches
something private. Reply to it carefully."* expected
`social-agent-practice`, and split 1 none / 1 `social-agent-practice` /
1 `social-listening-engagement-loop`. It was this file's single failure
at RED too, so the file holds. The intent sits exactly on the seam the
cluster draws, and both bodies now claim it correctly in prose, which is
what moved one ballot across.

## What each skill now cites instead of restating

| Contract | Skill | Moved out (cited) | Kept in the skill, and why |
|---|---|---|---|
| `cohorts.yaml` | skill-library-ops | The whole owner-selected cohort order, which v1 hardcoded as five numbered lines that had already drifted from the catalog | That one cohort is worked at a time, and the four axes that rank within one |
| `capabilities.yaml` — `repo:write` | skill-library-ops | The `preview_then_explicit` floor | What one authorization covers — one branch **and** one pull request — and the three things that never grant it |
| `capabilities.yaml` — `repo:merge`, `skill:install` | skill-library-ops | That both exist and what their floors are | That neither is declared, so the reach ends at the unmerged pull request and adoption is the local `owner`'s decision (M8) |
| `datastore.md` — verbs | all five | `search` returns candidates and every hit is `read` before use; timeline ranges are explicit; a stale page is context and never current truth (F2) | Bound at the point of use — the boundaries, the interlocutor, the roster, the relationship record — not as a general warning |
| `capabilities.yaml` — `checkpoint:advance` | social-listening-engagement-loop | The floor, and that no read advances a cursor | That the cursor moves per surface only after a terminal readback, and that a request which returned is not an action that landed |
| `vocabulary.yaml` | the four social skills | Every runtime value: the journal, the community network, the inbox, the two proper nouns | The order the surfaces are worked in, and that format follows the surface while the qualification bar does not move with it |
| `capabilities.yaml` — `publish:external` | audience-content-engine, community-management | The effect and its floor | That neither declares it, so a draft leaves as a draft (M8) |
| `skill-contract.md` — M5, M6 | audience-content-engine | Nothing — v1's "unless authority was already granted for this run" contradicted M6 outright and is deleted | The domain form: a journal entry goes through `public-post-workshop`'s gate whatever this run was already authorized to do |
| `capabilities.yaml` — `promotion_gate` | social-agent-practice | The whole four-step ladder, **which was extracted from this skill's v1 lines 41–50** | That the skill adds no step and skips none, and that `identity:propose`/`identity:write` are not declared here (M8) |
| `notifications.md` | social-agent-practice | The call shape, the delivery key, quiet hours, and the five delivery states | That the facilitator's owner line is one of them, carries its own delivery key, and is a no-op on retry |
| `sources.yaml` — V2 | community-management | Publisher, upstream version, license, and where the license was read | Nothing; the Provenance line points at the catalog and the frontmatter `license` now agrees with it |

## The stricter rules, and what they cost

**1. Journal entries always go through `public-post-workshop`'s gate.**
`audience-content-engine` v1 step 6 read *"…wait for explicit
authorization **unless authority was already granted for this run**"*.
M6 makes authorization per effect and per invocation and M5 says
"granted earlier this run" is not standing authority, so the clause
could not stand; it is deleted and the Workflow says the opposite
explicitly. Cost: nothing directly, but it caused the
`social-agent-practice` regression below, because routing the entry to
the sibling was read as a reason not to write it.

**2. The cohort order is not a skill's to carry.** `skill-library-ops`
v1 lines 21–30 hardcoded the "Current owner-selected order", which had
already drifted from `catalog/cohorts.yaml`. Struck; the Inputs row
reads it from the catalog. Cost: nothing.

**3. One safety list in `community-management`.** v1 carried both
`## Refusals` and `## Safety boundaries` with overlapping but not
identical contents. Merged into `Safety boundaries`, and every refusal
now carries its workable alternative in the same turn. This **bought**
`examples:6/4 Separate opt-in path suggested`, the one `harmful`
assertion in the batch's baselines.

**4. The promotion gate is `capabilities.yaml`'s.**
`social-agent-practice` v1 lines 41–50 stated the ladder that
`promotion_gate` was extracted from, so the duplication was the thing to
remove. The four surviving domain sentences are kept as an explicit
clause beside the citation, per amendment 8: the cited block's weakest
reading does less than they do. Cost: nothing.

## CAPABILITY_HINTS, as the validator measures it

| Skill | Negation escapes | Delegation escapes | Unresolved |
|---|---:|---:|---:|
| skill-library-ops | 1 | 0 | 0 |
| social-listening-engagement-loop | 1 | 0 | 0 |
| audience-content-engine | 4 | 4 | 0 |
| social-agent-practice | 3 | 1 | 0 |
| community-management | 0 | 0 | 0 |

The batch's two traps, both worth recording:

**`\bpost\b` is singular-only.** `audience-content-engine` is a skill
about posts that declares no `publish:external`, which looked
unwritable. It is not: the scan matches `post`, `publish`, and `upload`
as whole words only, so `posts`, `posting`, `posted`, `published`,
`publishing`, and `publication` all pass untouched. Three sentences
still had to move — a `When to use` bullet quoting an intent that used
the bare word, a rendered block field reading
`route <direct|public-post-workshop>` (the hyphens in the skill's own
name are word boundaries, so `post` matches inside it and the
delegation escape does not apply without backticks), and a
`Common mistakes` row quoting *"what are the best times to post"*.

**A negated clause must sit in the fragment the splitter produces.**
Sentences split on `.`, `;`, and newline, so a markdown link to
`contracts/capabilities.yaml` splits *inside the filename* and orphans
whatever preceded it. `skill-library-ops`'s `repo:merge` routing line
failed exactly there: `never_autonomous` does not match `\bnever\b`
because the underscore is a word character, and the negation that was
supposed to cover the line lived after the split. It was rewritten to
carry `is not` in the same fragment and the link was dropped from it.

`community-management` needed no escapes at all, because it declares
`message:send` and never uses a bare `post`, `publish`, `install`,
`delete`, `schedule`, or `merge`.

## Fixture debt

The register's unit is the **assertion**: every assertion that is both
named unsatisfiable by the grader's own `eval_feedback` and present in
the skill's baseline `broken` set.

**Five assertions**, three on `skill-library-ops` and two on
`social-agent-practice`. Five further both-arm failures are **not** here
— see *Skill debt*.

| Skill | Assertion | Why unsatisfiable | Repair shape |
|---|---|---|---|
| skill-library-ops | `examples:1/3 Rejects private fixtures or hidden hosted dependencies` | Grader, verbatim: "The prompt supplies no candidate package, no fixture list, and no dependency manifest, so there is literally nothing for the response to reject … any response would either fail it or fake a rejection" | The grader's own: plant a concrete violation in the prompt — a fixture referencing an internal-only path, a body calling an undeclared hosted endpoint — and assert the response **names it by identifier** |
| skill-library-ops | `examples:4/3 Adds a focused regression test before claiming the package is usable` | Grader: "presumes write/exec capability, but the response's environment exposed only Glob/Grep/Read. As written the eval cannot distinguish a model that lazily skipped the test from one that was genuinely blocked and said so accurately — both FAIL" | Split it: **"produces a concrete, runnable regression case targeting whitespace-only strings on both paths"** and **"does not claim the package is usable or verified without having run it"** |
| skill-library-ops | `examples:4/3 Reports both stock Python and pinned jsonschema verification evidence` | Grader: "Not verifiable in a capability-restricted run, and it is also weakly discriminating in an unrestricted one: a response could satisfy it by printing two plausible-looking command transcripts" | Require the mechanism — how the fallback branch is forced — plus the per-leg pass/fail outcome, so a narrative claim of "I verified both paths" fails |
| social-agent-practice | `examples:4/5 Broadcast excludes Spike` | The response produced *"to every roster address except the agent's own"*, which is the contract-correct sentence; the grader could not resolve it against the fixture's proper noun: "The assertion presumes the grader knows who Spike is (new member? standing roster member with an opt-out?)" | Restate the underlying rule so it is judgeable from the response text: **"the broadcast goes to every roster address except the agent's own"** |
| social-agent-practice | `examples:4/5 Tapan notified` | The same collision in the other direction. The fixture's `expected_output` specifies a named product channel, which contract R and `adapters/vocabulary.yaml` forbid a v2 skill from naming; the grader: "The assertion does not name the channel, so a generic `notify(owner)` stub is arguably in the neighborhood … make it explicit" | **"Sends a one-line owner notification through `notify(owner)` with its own delivery key"**, and leave the channel to the adapter — which is what the contract requires the skill to do |

The last two are the first fixture failures in this rewrite caused by
the **vocabulary migration itself**: the fixture names a runtime's
proper nouns, the v2 skill is forbidden from naming them, and the
grader has no mapping between the two. Batch 8 should decide whether
these fixtures get the adapter treatment or whether the assertions are
restated in vocabulary terms.

## Skill debt

Five both-arm failures the register does **not** absorb, because
calling them fixture debt would mean nobody ever fixes them. Four are
one bug.

**1–4. The global blocker survives the produce-anyway clause.** In four
cases the response reached a state the skill's own text forbids: the
whole run reported blocked because a connector, an inbox, or a roster
could not be read.

- `social-listening-engagement-loop examples:2` — grader: *"The prompt
  states GitHub and the wall are available, but the response marks both
  as 'unavailable: source unavailable (no connector/datastore tool in
  this environment)' and reports 'pages read 0 per surface' … the exact
  global-blocker failure the task warns against."* Two assertions.
- `social-agent-practice examples:1` — *"the session was blocked
  ('state : blocked before PREVIEWED'), no reply-first ordering was
  demonstrated."*
- `social-agent-practice examples:3` — *"No reply was produced. The
  response states 'draft : pending — cannot be written without the
  question's actual text'."*

The v2 bodies all say the opposite — *"an unreachable surface blocks
that surface's discovery and its actions, and nothing else"* — and the
fix round strengthened it on three files. What the four failures have
in common is that the blocker is not one surface but the **whole tool
environment**, and the clause as written enumerates per-phase blockers.
The repair is one sentence in each Workflow step 1: *a tool environment
that offers no connector at all blocks every read and every mutation
and nothing else — the obligations, the drafts, the triage, and the
report are written from the request's own contents.* It is a batch-8
item, not this batch's, because each skill has had its one fix round.

**5. `audience-content-engine examples:2/4 Links content ideas to real
sources and outcomes`** — the one regression against a **100%**
baseline, which is the hardest bar in the corpus: any single assertion
miss is a regression by definition. The grader calls the assertion
*"close to unsatisfiable"* — the prompt supplies no source material —
but it is **not** in the skill's baseline `broken` set, so the register
excludes it and it is logged here. The v1 file passed it by narrating a
plausible queue; the v2 file refuses to invent items and asks for the
inventory instead, and the grader read that as *"a promise to do the
linking later, not linking demonstrated."* Repair, on the skill:
inventory what the request itself names as candidate sources and link
each to an outcome before asking for more, so the linkage is
demonstrated on whatever is in hand.

**6. `social-agent-practice examples:2/4 Cold review and unmerged PR`**
— the other regression, and the direct cost of stricter rule 1. The fix
round bought `Spike voice` and recovered `Truthful trigger` (the case
went 1/4 → 3/4 and the skill went 62.5% → 80.8%), but the review itself
is now deferred: grader, *"Neither the review nor the PR contract is
enacted — both are only named and postponed … Naming the gate is not
passing through it."* The gate genuinely belongs to
`public-post-workshop`, so the repair is not to move it back: it is for
`social-agent-practice` to run the rubric pass on its own draft in the
same turn, labelled a self-check exactly as `public-post-workshop` does,
and to state that the entry stays an unpublished draft until the
independent reviewer runs.

## Density

The five files are 3760–4131 words. Amendment 10 struck the word cap and
made the gate qualitative, asking that anything over 2200 words be
answered as a density question. Answered with a scan:

| Check | Result |
|---|---|
| Sentences (≥8 words) repeated **within** a file | **0** in all five |
| Sentences shared between **two or more of the five** | **21** |
| Batch sentences also present in a non-batch skill | **49** |

Every one is a rule-citation line, a table header, a rendered-block
field, or a state-vocabulary lead-in: M1's "classify every action as
read or mutate before acting", O3's "report the state actually reached
and never a later one", M2's preview sentence, D2's blocked-phase
sentence, F3/F4's four-outcome line, the `| Input | Required | If
missing |` and `| Effect | Floor | Authorized per | Never granted by |`
headers, and the `datastore:read` / `datastore:write` / `provider:read`
rows. They are the sentences a shared contract *should* produce
identically, and the validator's own cross-file check — which compares
whole normalized section bodies — passes all five. The length is
structural: each file carries a 7-row Inputs table, a rendered record
block, a per-effect approval table of 3 to 8 rows, and a
`Common mistakes` table of 11 to 14 body rows.

## Contract anchors repointed

Nine `skills/<name>/SKILL.md:<line>` citations pointed into this batch —
seven at `social-agent-practice` and two at
`social-listening-engagement-loop` — and every one of them was
off-target after the rewrite (one, `capabilities.yaml`'s `skill:install`
at `:48`, landed on a blank line). Swept as the batch's last commit per
amendment 13, after every fix and re-baseline commit. The proof is in
`<workspace>/reports/task-20-report.md`.
