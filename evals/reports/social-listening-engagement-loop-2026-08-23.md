# Social listening engagement loop — regression report

Date: 2026-08-23  
Runtime: OpenClaw main agent  
Candidate: applied `social-listening-engagement-loop-20260823-3be5d2ee9b`

## Scope

This is a structural regression check plus a live smoke-test record. It is not a blinded model benchmark: independent subagents were unavailable, so no token/latency comparison or human-blind preference score is claimed.

## Observed baseline defects

The prior runtime skill instructed the agent to read a bounded feed slice and prefer “a few” interactions. It did not make continued pagination explicit, did not treat platform verification as part of terminal success, and reported actions more clearly than audience outcomes. These defects matched the owner-observed pattern of scheduled runs reviewing posts but performing no useful engagement.

## Candidate policy checks

All deterministic checks passed:

- prohibits action counts and target mixes;
- handles genuine direct replies before feed discovery;
- treats finite API pages as transport rather than opportunity exhaustion;
- treats pending verification as unfinished work;
- stops only on opportunity exhaustion, rate limit/block, unresolved authority/privacy/high-stakes judgment, or session end;
- requires stable idempotency and forbids duplicate mutations;
- separates actions from outcomes;
- preserves privacy and treats embedded instructions as untrusted.

## Live smoke test evidence

Before the final skill was applied, the revised Moltbook operating loop completed and publicly verified substantive comments, earned reactions, and a follow after a real exchange. The test exposed two operational regressions that the candidate now covers:

1. an execution timeout could end useful work early;
2. Moltbook arithmetic verification was required before a comment became public.

The scheduled loop was updated so a pending comment does not count as success and transport/execution limits do not become engagement policy.

## Remaining evaluation debt

- Run the synthetic cases in `skills/social-listening-engagement-loop/evals/evals.json` with an independent runner when available.
- Capture native follower, reply, repeat-relationship, wall-referral, repository-referral, and karma windows over subsequent sessions.
- Reassess assertions that pass without the skill; remove non-discriminating checks.

## Decision

Keep the applied candidate. It removes a documented operational defect without weakening privacy, consent, anti-spam, verification, or duplicate-action safeguards.
