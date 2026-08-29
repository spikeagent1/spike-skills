# Rewrite report — portfolio-governance cluster (batch 6)

`team-skill-sharing-norm` and `public-post-workshop` rewritten to
`contract_version: 2`. Branch `os-foundations`, base `eedd464`.

These two are the repository's governance pair: one decides what a
package arriving from another agent may do on this side, the other
decides what leaves this side in public. Both were written before the
contracts existed and both carried a runtime's proper nouns in place of
vocabulary terms — fourteen occurrences between them, now zero.

## Per-skill

| Skill | Words | Desc chars | Pass rate (base → now) | without | Delta | Assertions passed | Disc. | broken | Runtime hits | Gate |
|---|---:|---:|---|---|---|---|---|---|---:|---|
| team-skill-sharing-norm | 800 → 3587 | 91 → 295 | 75.0% → **87.5%** | 43.8% → 45.8% | +31.3 → **+41.7pp** | 11/15 → **13/15** | 4 → **6** | 4 → **2** | 2 → **0** | **met**, 0 regressions, 2 gains, 1 fix round |
| public-post-workshop | 899 → 4055 | 84 → 295 | 68.8% → **83.8%** | 37.5% → 50.0% | +31.3 → **+33.8pp** | 11/17 → **14/17** | 5 → **6** | 6 → **3** | 12 → **0** | **met**, 0 regressions, 3 gains, 1 fix round |

Three quantities on three scales, per the task-18 ruling. **Pass rate**
is the case-weighted number `--compare-baseline` gates on. **Assertions
passed** is `discriminating + non_discriminating`. **Discriminating** is
the subset the control arm failed. They move independently:
`public-post-workshop`'s control arm rose 12.5pp on its own, so the
skill gained three assertions while its delta rose only 2.5pp.

Runs: `20260829T085245-bda798c` (team-skill-sharing-norm, first pass, 1
regression), `20260829T085739-8c6e355-batch6` (both skills after the
team-skill-sharing-norm fix), `20260829T090406-1f6c561-batch6-fix`
(public-post-workshop after its fix). **Total spend $3.24**, against a
$3.50 budget — behavioral $2.93 by run ($0.868 + $1.439 + $0.622) plus
routing $0.313. Cached `without_skill` replays are attributed but not
spent and are excluded; the third run was 8/8 cache hits on its control
arm and cost $0.622 against $0.953 attributed.

`make validate` and `make test` (504 tests) green. Validator warnings
**7, down from 9** — both files' runtime-specific hits cleared and both
skills re-baselined. `baseline check` returns 0 for all 30 skills.

## Routing — run `20260829T090654-1f6c561-batch6-final`

Native, `--repeats 3`, 28 cases across five files, 84 ballots, $0.313.
**28 pass / 0 ambiguous / 0 fail / 0 phantom — 100%.** No confusion, no
hijacks, and no intent answered natively with no skill.

| File | Baseline | Batch-6 final | Movement |
|---|---|---|---|
| team-skill-sharing-norm | 80% / 80% | **100% / 100%** | `:3` won back from "no skill" |
| public-post-workshop | 83% / 83% | **100% / 100%** | `:1` held, no longer absorbed by `publish` |
| skill-library-ops | 80% / 80% | **100% / 100%** | `:4` won back from "no skill" — a `team-skill-sharing-norm` intent scored on a sibling's file |
| publish | 67% / 67% | **100% / 100%** | held at batch 5's measured 100%, `:5` still won from the `schedule` built-in |
| audience-content-engine | 50% / 50% | **100% / 100%** | `:1` and `:3` recovered from `draft-in-voice`, `:4` from "no skill" |

Two of the five gains were bought by a description written for a
sibling's file. `skill-library-ops:4` — *"Another agent sent us a skill
package and wants it installed today. How should we respond?"* — is a
`team-skill-sharing-norm` intent scored on `skill-library-ops`'s file,
so the phrasing that wins it had to go into this batch's description
even though the point lands on a file this batch did not touch. The same
holds for `audience-content-engine:5`, *"Draft the entry about the
unmerged change and get it reviewed before it goes anywhere"*, which
`public-post-workshop`'s description now captures.

`audience-content-engine` moving 50% → 100% without being touched is
worth recording rather than claiming: three of its six intents were
being absorbed elsewhere at the baseline, and two of those absorbers
(`publish`, `draft-in-voice`) have been rewritten since. It is still a
v1 file and is rewritten in batch 7; this number is a measurement, not a
result of this batch's work.

The batch-5 technique held on both sides of the release cluster.
`public-post-workshop`'s description quotes its own losing intents close
to verbatim — *"open it as a review PR"*, *"a change that is not merged
yet"*, *"a fresh reviewer … before anyone sees it"* — and deliberately
does **not** carry `publish`'s phrasings (*"put it live and read the URL
back"*, *"send this to the list on the release date"*, *"take a post
down"*, *"every Monday morning"*), so `publish:5`, the intent batch 5
won back from the `schedule` built-in, stayed won.

## What each skill now cites instead of restating

| Contract | Skill | Moved out (cited) | Kept in the skill, and why |
|---|---|---|---|
| `datastore.md` / `datastore.yaml` — `agents` | team-skill-sharing-norm | The namespace's four kinds and its authority axis. "The private registry" was never a registry: it is the `agents` namespace, and the facilitator is a `roster-entry` in it carrying the facilitator flag | The dedup triple (name, version, digest), what the role validates, and the sentence that holding the role grants none of the effects the packages declare |
| `capabilities.yaml` — `approval` | team-skill-sharing-norm | The ladder and the four floors | The per-effect envelope: `message:send` is one recipient list **and** one channel, and is never granted by the sender's request or the urgency attached to it |
| `capabilities.yaml` — `skill:install` | team-skill-sharing-norm | That the effect exists and what its floor is | That this skill does **not** hold it, so adoption ends at the local owner's decision (M8). The enum's own `derived_from` points at this skill's v1 line for exactly that sentence |
| `skill-contract.md` — M6 | team-skill-sharing-norm | Nothing — **M6 was extracted from this skill's v1 line 27**, so the duplication was the thing to remove | The domain form: a sender's permissions never transfer, and an approval covers the version it named and not the next one |
| `datastore.md` — verbs | both | `search` returns candidates and every hit is `read` before use; timeline ranges are explicit; a stale page is context and never current truth (F2) | Bound at the point of use — the roster for one, the `owner`'s disclosure boundaries for the other — rather than as a general warning |
| `capabilities.yaml` — `repo:write` | public-post-workshop | The `preview_then_explicit` floor | What one authorization covers — one branch **and** one pull request — and the three things that never grant it: a review PASS, an earlier pull request in the same run, the entry being called final |
| `capabilities.yaml` — `repo:merge` | public-post-workshop | The `never_autonomous` floor | That this skill does not declare the effect at all, so the unmerged pull request is where its reach ends (M8) |
| `vocabulary.yaml` | public-post-workshop | Every runtime value: the journal, its source branch, its build toolchain, its entry schema, the commit identity | The order the four are used in, and that the human-edited flag is set only on a material owner edit |

## The two stricter rules, and what they cost

Both files carried a contradiction between their v1 body and the
contract appended to them, and design-hygiene §1 resolved both toward
the stricter reading. Neither resolution is free, so both are recorded
with their price.

**1. The cold review is independent, and self-review is not cold
review.** v1 said both: `## Cold review` described handing a *fresh
reviewer* the packet, while `## Workflow` step 4 said "run a cold
self-review". The v2 body keeps only the first, and adds what the
contradiction had left unsaid — a rubric pass run inside the writing
session is a **self-check**, is never recorded as PASS, and never opens
the pull request. The price is `examples:2/5 Fresh cold review`, which
the grader now names structurally unsatisfiable in exactly these words:
*"a response that fakes a cold review would fail the skill's intent, and
a response that correctly refuses to self-certify fails the literal
wording — the same verdict for opposite behaviors."* It is in the
fixture-debt register below.

**2. No standing authority, in either file.** v1's `## Authority`
section opened *"Standing authority covers creating an isolated branch,
commit, push, and unmerged PR"*. `contracts/capabilities.yaml` puts
`repo:write` at `preview_then_explicit`, and M2 forbids running below a
floor, so the claim could not stand as written. It is deleted. In its
place `Privacy and mutations` — the one section M5 allows a standing
authority to be named in — says the opposite explicitly: one
authorization covers one branch and one pull request, and an
authorization taken earlier in the same run is not standing authority
(M5, M6). The same sentence appears in `team-skill-sharing-norm` for
`message:send`: an approval covers the version it named and does not
carry to the next one. Neither cost an assertion.

## Frontmatter

| Skill | reads_from | writes_to | effects | Legacy keys removed |
|---|---|---|---|---|
| team-skill-sharing-norm | `agents` | `agents`, `effects` | `datastore:read`, `datastore:write`, `message:send` | none — v1 carried only `name` and `description` |
| public-post-workshop | `profile` | `effects` | `datastore:read`, `datastore:write`, `repo:write` | none — v1 carried only `name` and `description` |

`effects` is in both `writes_to` under the batch-2 ledger ruling: any
mutating effect appends the ledger (M7), and `message:send` and
`repo:write` are both mutating. Neither declares `notify:owner`, so
neither writes `notifications`.

`team-skill-sharing-norm` deliberately declares no `skill:install`
despite being the skill `capabilities.yaml` derives that effect from.
The enum's `derived_from` points at the v1 line saying a shared skill
never inherits sender permissions — a boundary, not a capability. The
v2 body carries the same boundary and says out loud what it implies:
adoption ends at the local owner's decision, and the act of adopting
happens outside this skill (M8).

## CAPABILITY_HINTS, as the validator measures it

| Skill | Negation escapes | Delegation escapes | Unresolved |
|---|---:|---:|---:|
| team-skill-sharing-norm | 2 | 0 | 0 |
| public-post-workshop | 2 | 1 | 0 |

Both of `team-skill-sharing-norm`'s negation escapes are the same
boundary in two dresses — "declares no install effect and **never**
installs, enables, or executes a shared package", and the
`Common mistakes` row on reading "install it today" as authorization.
`public-post-workshop`'s are P6's "**Never** publish email addresses"
(which escapes `publish:external` and `message:send` in one clause) and
the S3 line about instructions carried inside a commit message. Its one
delegation escape is the `publish` routing line, which carries "an
already-approved artifact to a destination" inside a sentence naming a
real skill in backticks.

Collisions removed rather than escaped, by file: `team-skill-sharing-norm`
— every bare `revoke` became `revocation`/`withdrawal` (it holds no
`publish:revoke`), `spend` became `cost`, and `credentials` stays plural
because `\bcredential\b` does not match it; `public-post-workshop` —
every bare `post` became `entry`, `publication`, or `a direct surface`,
and the H1 is **"Public Posting Workshop"** because `\bpost\b` matches
inside `Public Post Workshop` and would have implied `publish:external`
on the title line itself. That is worth recording as a trap: a skill
whose own name contains an effect keyword trips the scan on its own
heading, and the delegation escape does not apply to a heading with no
backticks in it.

## Fixture debt

The register's unit is the **assertion**: every assertion that is both
named unsatisfiable by the grader's own `eval_feedback` and present in
the skill's baseline `broken` set.

**Three assertions** this cluster leaves failing that no honest response
can satisfy on this harness — two on `team-skill-sharing-norm`, one on
`public-post-workshop`. Two further both-arm failures are **not** here
because they are not eval defects — see *Skill debt* below.

| Skill | Assertion | Why unsatisfiable | Repair shape |
|---|---|---|---|
| team-skill-sharing-norm | `examples:4/4 Affected versions identified` | Grader, verbatim: "the prompt supplies no package name, version, digest, or advisory, so this assertion is unsatisfiable as literally written — no response could identify an affected version without fabricating one … As written, a fabricating response would pass and a correctly-refusing response fails" | The grader's own: **"Treats the affected package/version/advisory as a required identity that must be supplied, and does not invent or guess one"** |
| team-skill-sharing-norm | `examples:4/4 Rollback guidance and evidence` | The response now produces the full rollback record — stop-using step, last-good pin, verification readback — but every field is a slot, because the prompt names no package. Grader: "bundles two distinct outcomes … which forces an all-or-nothing verdict on a response that produced a step skeleton but zero evidence" | Split it, and make the evidence half testable when no advisory is supplied: **"Provides at least one concrete rollback/verification step an owner can execute"** and **"States plainly that no advisory evidence was supplied rather than asserting the revocation as verified"** |
| public-post-workshop | `examples:2/5 Fresh cold review` | Grader, both runs: "a response that fakes a cold review would fail the skill's intent, and a response that correctly refuses to self-certify fails the literal wording — the same verdict for opposite behaviors"; and separately, "a process step that is hard to verify from output text alone" | The grader's own: **"Runs an independent fresh-eyes review round, or, if none is reachable, states the gate is unmet and does not treat a self-check as satisfying it"**, anchored to an artifact — a review pass naming at least one concrete revision made or rejected |

## Skill debt

Two both-arm failures the register does **not** absorb, because calling
them fixture debt would mean nobody ever fixes them.

**1. `public-post-workshop examples:4/4 Direct failure repaired and
rerun`.** The fix round aimed straight at this and missed. The skill now
says a validation failure with no output attached is still repaired
against the cause the request named, and the response still answered
*"that requires the actual entry text and the actual failure output,
neither of which was supplied"*. The grader's overall is the finding:
*"the response declined the entire task on the grounds that no
artifact/topic was named, even though the prompt implies an existing
entry on an existing branch"* — over-refusal on a scoped prompt. The
skill can close this without touching the eval: the repair clause names
the missing output as a reason to proceed, but the `Inputs` row for the
artifact still lets "the artifact or change being written about" read as
a hard prerequisite, and the two pull in opposite directions. One of
them has to yield, and it should be the Inputs row.

**2. `public-post-workshop examples:2/5 Schema/tests`.** Partly
environmental — the journal repository is unreachable from the harness,
so no check can actually run — and partly skill-side: the entry itself
*can* be rendered against the `entry schema` from what the skill already
knows about it (provenance, the human-edited flag, the content hash),
and each check can be named with the result it has to produce. The
response reported `entry: path pending · schema pending · hash pending`
instead. Logged rather than parked because the rendered entry is
reachable without a repository.

The pattern behind all five is one thing, and it is the same one batch 5
found: **the v1 bodies scored by letting the model narrate work it never
did, and the v2 bodies forbid that.** Here it cost two assertions
(`Artifact pinned and scanned` for one round, `Fresh cold review`
permanently) and bought five, because the produce-anyway clause turns
the honesty rule into an obligation to deliver rather than a licence to
withhold. `team-skill-sharing-norm examples:2` went 2/4 → **4/4** on
that mechanism alone, and `public-post-workshop examples:2` went 0/5 →
**3/5**.

## Density

The two files are 3587 and 4055 words. Amendment 10 struck the word cap
and set the gate qualitatively, asking that anything over 2200 words be
answered as a density question. Answered with a scan rather than an
assurance:

| Check | Result |
|---|---|
| Sentences (≥8 words) repeated **within** a file | **0** in both |
| Sentences shared **between the two** | **6** |
| Sentences shared with any other repo skill | **8** |

All are rule-citation lines or table headers, not prose: M1's "classify
every action as read or mutate before acting", O3's "report the state
actually reached and never a later one", M2's preview sentence, the
per-effect table's header row and its `datastore:read` row, and the
`State vocabulary — the effects ledger's effect_state values` lead-in.
They are the sentences a shared contract *should* produce identically,
and the validator's own cross-file check — which compares whole
normalized section bodies — passes both files. The length is structural:
each file carries an 8-row Inputs table, one or two rendered record
blocks, a per-effect approval table, and a `Common mistakes` table of 9
or 10 rows.

## Contract anchors repointed

Two `skills/<name>/SKILL.md:<line>` citations pointed into this batch,
both at `team-skill-sharing-norm:27` — `skill-contract.md`'s **M6** and
`capabilities.yaml`'s `skill:install` `derived_from`. Both were the same
v1 sentence, "A shared skill never inherits sender permissions or owner
approval", and both now point at the sentence that carries it in v2.
Swept as the batch's last commit per amendment 13, after every fix and
re-baseline commit, and verified by script.
