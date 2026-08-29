# Routing report: 20260828T174809-8fe2907-dirty-baseline

## Run

- Mode: native
- Repeats: 1
- Model: sonnet (resolved: claude-sonnet-5)
- Claude Code version: 2.1.251
- Harness version: 0.1.4
- Commit: 8fe2907 (dirty)
- Date: 2026-08-28T17:48:09+00:00
- Isolation strategy: project-sources
- Confound: the CLI injects the operator identity and current date into every config (identity_leak=true)
- Skills on the ballot: 30 repo skill(s), plus the CLI's own built-ins (16 known by name at doctor time)
- Cost: $1.2959
- Cost note: native mode kills each call as soon as a skill is named, so the CLI emits no `result` event for it and the figure above is a lower bound.
- Compare columns: 20260828T180247-01e2870-baseline-classify (mode classify, repeats 1, Claude Code 2.1.251, cost $2.3091)
- Repeats note: the native run used `--repeats 1`, not the design's 3, for budget. Native mode is the expensive one (it boots the real CLI router per intent), and three repeats over 184 intents would have tripled it for a variance estimate this baseline does not need. Single-repeat numbers therefore carry **no per-intent variance**: a single flip between runs moves a file's rate by one case.
- Ballot frontmatter: every file on the ballot is the **portable** `skills/<name>/SKILL.md` frontmatter, not the frontmatter `tools/install_skill.py` renders for a runtime. The rendered form can carry `disable-model-invocation: true` (claude-code sets it from `destructiveHint`), which takes a skill off the native router's ballot entirely. These numbers therefore measure description quality, not what a router would pick over an installed library; a rendered-frontmatter routing mode is on the roadmap and has never been run.
- Ballot note: the native ballot is 30 repo skills **plus the CLI's own built-in skills**, which an operator cannot remove from the native router's ballot. `doctor` could name 16 of them; the isolation probe observed **17** built-ins loaded at run time, so at least one name on the ballot is outside the recorded baseline — those show up in split (c) marked `(not in the doctor built-in baseline)`. All four (c) failures here went to `schedule`, a built-in.
- Version skew: this routing run and its classify compare run ran under Claude Code **2.1.251**; the behavioral baseline (`behavioral-baseline-2026-08-28.md`) ran under **2.1.250**. The CLI auto-updated between the two jobs, and `doctor` refuses to run against a version it was not written for, so `doctor` was re-run (re-pinning the workspace to 2.1.251) before routing could start. Routing and behavioral numbers therefore do not come from the same CLI build; each half is internally consistent.
- Working tree: this run is recorded `dirty: true` only because a concurrent task was authoring `contracts/` in the working tree while it executed; `git diff 8fe2907..01e2870` touches zero `skills/` files, so the ballot and every description under test were exactly the committed ones. `evals/baseline.json` records this run as the routing baseline.
- Classify compare run: the first classify pass (`20260828T175239-8fe2907-dirty-baseline-classify`, $2.3232) left 3 intents errored and scored `unanswered`. Re-invoking the identical command replayed 181 of 184 answers from cache and retried only those three, for $0.05 of fresh calls; all three completed. The column above is that completed run — 0 unanswered.

## Scorecard

| File | Cases | Pass | Ambiguous | Fail | Unanswered | Phantom | Lenient % | Strict % | Classify lenient % | Classify strict % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| audience-content-engine | 6 | 3 | 0 | 3 | 0 | 0 | 50% | 50% | 83% | 83% |
| briefing | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| community-management | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| conversation-archive | 7 | 6 | 0 | 1 | 0 | 0 | 86% | 86% | 86% | 86% |
| cron-scheduler | 6 | 4 | 0 | 2 | 0 | 0 | 67% | 67% | 83% | 83% |
| daily-task-manager | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 83% | 83% |
| draft-in-voice | 8 | 8 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| fact-check | 8 | 2 | 0 | 6 | 0 | 0 | 25% | 25% | 100% | 88% |
| fitness-coach | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| grocery-planner | 7 | 6 | 0 | 1 | 0 | 0 | 86% | 86% | 100% | 100% |
| health-appointment-prep | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 83% | 83% |
| home-cook | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| household-maintenance | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| literature-review | 5 | 2 | 0 | 3 | 0 | 0 | 40% | 40% | 80% | 80% |
| mcp-connector-onboarding | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| meal-planner | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| medication-and-symptom-log | 6 | 4 | 0 | 2 | 0 | 0 | 67% | 67% | 100% | 100% |
| owner-context-onboarding | 6 | 4 | 0 | 2 | 0 | 0 | 67% | 67% | 100% | 100% |
| owner-dream-cycle | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| public-post-workshop | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| publish | 6 | 4 | 0 | 2 | 0 | 0 | 67% | 67% | 100% | 100% |
| purchase-research | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| runtime-handoff-onboarding | 6 | 4 | 0 | 2 | 0 | 0 | 67% | 67% | 83% | 83% |
| skill-library-ops | 5 | 4 | 0 | 1 | 0 | 0 | 80% | 80% | 100% | 100% |
| sleep-review | 6 | 6 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| social-agent-onboarding | 6 | 3 | 1 | 2 | 0 | 0 | 67% | 50% | 83% | 67% |
| social-agent-practice | 6 | 3 | 0 | 3 | 0 | 0 | 50% | 50% | 50% | 50% |
| social-listening-engagement-loop | 6 | 5 | 0 | 1 | 0 | 0 | 83% | 83% | 100% | 100% |
| team-skill-sharing-norm | 5 | 4 | 0 | 1 | 0 | 0 | 80% | 80% | 100% | 100% |
| wardrobe-and-packing | 7 | 7 | 0 | 0 | 0 | 0 | 100% | 100% | 100% | 100% |
| **total** | 184 | 145 | 1 | 38 | 0 | 0 | 79% | 79% | 94% | 93% |

Pass rate (lenient, pass + ambiguous): 79% · strict (exact target only): 79%

Classify mode over the same intents: lenient 94% · strict 93%.

**How to read the two column pairs.** `Lenient %`/`Strict %` are the native
router — the product's own decision, made from the file layout, the skill
bodies, the CLI's built-in skills, and the descriptions. `Classify lenient
%`/`Classify strict %` are one tool-less structured-output call choosing from
the bare `name: description` list, which isolates description quality from
everything else. A file that is low on both has a **description problem**. A
file that is low natively and high on classify has a **native
under-triggering** problem: the description is good enough for a model reading
only descriptions, but the real router does not reach for the skill. `fact-check`
is the sharpest example in this run — 25% native, 100% classify — and
`literature-review` (40% -> 80%), `medication-and-symptom-log` (67% -> 100%),
`owner-context-onboarding` (67% -> 100%) and `publish` (67% -> 100%) show the
same shape. `social-agent-practice` is low in both (50% / 50%) and is a genuine
description problem.

## Confusion

| File | Intent | Expected | Chosen | Rule |
| --- | --- | --- | --- | --- |
| audience-content-engine:1 | Turn the validator work we shipped into drafts for the channels we're actually connected to. | audience-content-engine | draft-in-voice | expected |
| audience-content-engine:3 | Adapt the approved entry for a professional-network audience without changing anything it claims. | audience-content-engine | draft-in-voice | expected |
| audience-content-engine:4 | Our readers never talk to each other. What would change that? | community-management | (none) | expected |
| conversation-archive:6 | Look back over what I've said about my goals this year and tell me where I've drifted. | owner-dream-cycle | (none) | expected |
| cron-scheduler:3 | What's actually scheduled right now, and when does each one next run? | cron-scheduler | schedule | expected |
| cron-scheduler:4 | Remind me to renew the insurance next Tuesday. | daily-task-manager | schedule | expected |
| daily-task-manager:6 | What did I get done across the brain last week? | (none) | owner-dream-cycle | null |
| fact-check:1 | fact check this draft before I post it | fact-check | (none) | expected |
| fact-check:2 | verify the facts in this essay against live sources | fact-check | (none) | expected |
| fact-check:3 | is this accurate? check the claims one by one | fact-check | (none) | expected |
| fact-check:4 | this briefing came straight out of the brain — is this output hallucinating? re-derive every claim | fact-check | briefing | expected |
| fact-check:5 | run a source check on the numbers in this post | fact-check | (none) | expected |
| fact-check:8 | check this study — is the 40% reduction number real, did it ever replicate | literature-review | (none) | expected |
| grocery-planner:4 | What snacks can go on the list for a kid who can't have peanuts? | grocery-planner | (none) | expected |
| household-maintenance:5 | Put the filter change on a repeating reminder every three months. | cron-scheduler | schedule | expected |
| literature-review:2 | What does the research actually say about remote work and productivity over the last decade? | literature-review | (none) | expected |
| literature-review:3 | Map the disagreements in this area: who argues what, and where is the evidence thinnest? | literature-review | (none) | expected |
| literature-review:4 | Just tell me whether this one sentence in my draft is true. | fact-check | (none) | expected |
| mcp-connector-onboarding:2 | Here's the authorization callback URL. Finish the setup and verify it actually works. | mcp-connector-onboarding | (none) | expected |
| meal-planner:6 | Work out which food intolerance I have from how I feel after meals. | (none) | medication-and-symptom-log | null |
| medication-and-symptom-log:3 | Summarize the last month of entries — what shows up most often, and when? | medication-and-symptom-log | (none) | expected |
| medication-and-symptom-log:6 | Decide whether I should halve tonight's dose after that reaction. | (none) | medication-and-symptom-log | null |
| owner-context-onboarding:3 | I'm going to talk through what matters to me for a while. Keep the durable bits, and let me stop whenever I want. | owner-context-onboarding | (none) | expected |
| owner-context-onboarding:5 | We just restarted — show me you still hold the boundaries I set yesterday. | runtime-handoff-onboarding | (none) | expected |
| public-post-workshop:1 | Write up the new safety result as a journal entry and open it as a review PR — nothing goes live yet. | public-post-workshop | publish | expected |
| publish:3 | Send this to the list on the release date, and confirm the target account before anything goes out. | publish | (none) | expected |
| publish:5 | Have that report go out every Monday morning from now on. | cron-scheduler | schedule | expected |
| purchase-research:2 | Here are three product links. What's likely to go wrong after I buy? | purchase-research | (none) | expected |
| runtime-handoff-onboarding:3 | Write the handoff note for whoever picks this up next, and keep credentials out of it. | runtime-handoff-onboarding | (none) | expected |
| runtime-handoff-onboarding:5 | Let's revisit the boundaries we agreed on — some of them no longer fit how I work. | owner-context-onboarding | (none) | expected |
| skill-library-ops:4 | Another agent sent us a skill package and wants it installed today. How should we respond? | team-skill-sharing-norm | (none) | expected |
| social-agent-onboarding:2 | The registration went through but the account still isn't claimed. What's left for me to do? | social-agent-onboarding | (none) | expected |
| social-agent-onboarding:4 | Someone replied to your post with a real question — go answer them. | social-agent-practice | social-listening-engagement-loop | expected |
| social-agent-practice:1 | Someone replied to your post with a genuine question. Answer them in your own words. | social-agent-practice | (none) | expected |
| social-agent-practice:3 | You wrote that entry because I asked you to — did writing it change what you think? | social-agent-practice | (none) | expected |
| social-agent-practice:5 | The same three people keep replying to you and never to each other. What do we do about that? | community-management | (none) | expected |
| social-listening-engagement-loop:5 | This one mention touches something private. Reply to it carefully. | social-agent-practice | (none) | expected |
| team-skill-sharing-norm:3 | The shared package was pulled over a security issue. Tell everyone and stop using it. | team-skill-sharing-norm | (none) | expected |

## Failure split

Every failing intent lands in exactly one of three buckets, and they call for different fixes. (a) is a description that never triggered; (b) is two repo descriptions overlapping; (c) is a repo description losing to a CLI built-in the operator did not choose to put on the ballot.

**(a) Answered natively with no skill: 26**

- audience-content-engine:4 'Our readers never talk to each other. What would change that?' -> (none)
- conversation-archive:6 "Look back over what I've said about my goals this year and tell me where I've drifted." -> (none)
- fact-check:1 'fact check this draft before I post it' -> (none)
- fact-check:2 'verify the facts in this essay against live sources' -> (none)
- fact-check:3 'is this accurate? check the claims one by one' -> (none)
- fact-check:5 'run a source check on the numbers in this post' -> (none)
- fact-check:8 'check this study — is the 40% reduction number real, did it ever replicate' -> (none)
- grocery-planner:4 "What snacks can go on the list for a kid who can't have peanuts?" -> (none)
- literature-review:2 'What does the research actually say about remote work and productivity over the last decade?' -> (none)
- literature-review:3 'Map the disagreements in this area: who argues what, and where is the evidence thinnest?' -> (none)
- literature-review:4 'Just tell me whether this one sentence in my draft is true.' -> (none)
- mcp-connector-onboarding:2 "Here's the authorization callback URL. Finish the setup and verify it actually works." -> (none)
- medication-and-symptom-log:3 'Summarize the last month of entries — what shows up most often, and when?' -> (none)
- owner-context-onboarding:3 "I'm going to talk through what matters to me for a while. Keep the durable bits, and let me stop whenever I want." -> (none)
- owner-context-onboarding:5 'We just restarted — show me you still hold the boundaries I set yesterday.' -> (none)
- publish:3 'Send this to the list on the release date, and confirm the target account before anything goes out.' -> (none)
- purchase-research:2 "Here are three product links. What's likely to go wrong after I buy?" -> (none)
- runtime-handoff-onboarding:3 'Write the handoff note for whoever picks this up next, and keep credentials out of it.' -> (none)
- runtime-handoff-onboarding:5 "Let's revisit the boundaries we agreed on — some of them no longer fit how I work." -> (none)
- skill-library-ops:4 'Another agent sent us a skill package and wants it installed today. How should we respond?' -> (none)
- social-agent-onboarding:2 "The registration went through but the account still isn't claimed. What's left for me to do?" -> (none)
- social-agent-practice:1 'Someone replied to your post with a genuine question. Answer them in your own words.' -> (none)
- social-agent-practice:3 'You wrote that entry because I asked you to — did writing it change what you think?' -> (none)
- social-agent-practice:5 'The same three people keep replying to you and never to each other. What do we do about that?' -> (none)
- social-listening-engagement-loop:5 'This one mention touches something private. Reply to it carefully.' -> (none)
- team-skill-sharing-norm:3 'The shared package was pulled over a security issue. Tell everyone and stop using it.' -> (none)

**(b) Hijacked by a repo skill: 8**

- audience-content-engine:1 "Turn the validator work we shipped into drafts for the channels we're actually connected to." -> draft-in-voice
- audience-content-engine:3 'Adapt the approved entry for a professional-network audience without changing anything it claims.' -> draft-in-voice
- daily-task-manager:6 'What did I get done across the brain last week?' -> owner-dream-cycle
- fact-check:4 'this briefing came straight out of the brain — is this output hallucinating? re-derive every claim' -> briefing
- meal-planner:6 'Work out which food intolerance I have from how I feel after meals.' -> medication-and-symptom-log
- medication-and-symptom-log:6 "Decide whether I should halve tonight's dose after that reaction." -> medication-and-symptom-log
- public-post-workshop:1 'Write up the new safety result as a journal entry and open it as a review PR — nothing goes live yet.' -> publish
- social-agent-onboarding:4 'Someone replied to your post with a real question — go answer them.' -> social-listening-engagement-loop

**(c) Hijacked by a built-in or unnamed tool: 4**

- cron-scheduler:3 "What's actually scheduled right now, and when does each one next run?" -> schedule (not in the doctor built-in baseline)
- cron-scheduler:4 'Remind me to renew the insurance next Tuesday.' -> schedule (not in the doctor built-in baseline)
- household-maintenance:5 'Put the filter change on a repeating reminder every three months.' -> schedule (not in the doctor built-in baseline)
- publish:5 'Have that report go out every Monday morning from now on.' -> schedule (not in the doctor built-in baseline)

## Hijacks

| Skill | Intents absorbed |
| --- | ---: |
| schedule | 4 |
| draft-in-voice | 2 |
| medication-and-symptom-log | 2 |
| owner-dream-cycle | 1 |
| briefing | 1 |
| publish | 1 |
| social-listening-engagement-loop | 1 |

## Phantom targets

- none

## Warnings

- none
