---
name: "skill-library-ops"
description: "Govern, evaluate, version, and publish an audience-first portfolio of shareable agent skills."
---

# Skill Library Operations

## Purpose
Maintain a shareable skill portfolio as tested software rather than a loose folder of prompts. Preserve runtime metadata, measure candidates against baselines, and keep every published change attributable and reversible.

## Repository contract
Use `skills/<name>/SKILL.md` with optional scripts, references, assets, and `evals/evals.json`; machine-readable inventory under `catalog/`; committed summaries under `evals/reports/`; ignored generated runs under `evals/workspaces/`; schemas under `schemas/`; deterministic validators under `tools/`.

Keep installed/runtime copies separate from repository source. Sync only from a reviewed commit.

## Inventory
For every live skill record canonical name, directory, trigger intent, owner, provenance URL/commit/license, local modifications, runtime dialect, tools/dependencies, last validation, and status. Detect name collisions, trigger overlap, missing dependencies, oversized files, and undocumented scripts.

Classify each as owned, adapted, vendored, or runtime-only.

## Cohort priority
Optimize one cohort at a time. Current owner-selected order:
1. Audience and community: social listening, social-agent practice, social content, and community management.
2. Safety and state mutation: publishing, messaging, cron, ingestion, deletion, memory, and repository writes.
3. Owner operations: daily tasks, briefing, team facilitation, and owner grounding.
4. Research and writing.
5. Routing overlap and long-tail skills.

Within a cohort, rank by observed correction, invocation frequency, failure impact, and missing evaluation coverage.

## Evidence and tests
Extract authorized real prompts, corrections, outputs, and failures. Sanitize them into synthetic fixtures. Include representative success tasks, an edge case, near-miss triggers, and authorization/scope cases for mutating skills. Define objective checks when possible; use human review for voice and strategy.

Never commit private conversations, visitor identity, credentials, production state, or private memory.

## Baseline
Snapshot the current version before editing. Run the same cases against current and candidate versions; for a new skill use no-skill behavior. Record pass rate, failure category, time, and token cost. Repair flaky or non-discriminating checks before accepting a change.

## Improvement
Make the smallest generalizable change supported by trajectory evidence. Clarify routing descriptions, move conditional detail to references, add deterministic scripts for repeated mechanical work, explain decision rationale, preserve OpenClaw metadata, and avoid unrelated rewrites.

Do not accept a candidate because it sounds polished. Accept it when held-out behavior improves or a documented defect is removed without regression.

## Release gate
A releasable skill passes:
1. frontmatter and folder validation;
2. OpenClaw eligibility and dependency checks;
3. provenance, license, secret, and security review;
4. task and near-miss trigger cases;
5. authorization cases for mutating workflows;
6. regression comparison;
7. human review of representative outputs.

Record evaluator model, harness version, commit, and date.

## Version, publish, and sync
Use semantic versions per skill. Pin upstream provenance. Commit one coherent change at a time and use pull requests for shared repositories. Package from the reviewed repository commit, sync to runtime, run discovery checks, and smoke-test a representative prompt. Retain the previous working package for rollback.

Applying, rejecting, or quarantining a Skill Workshop proposal requires explicit owner direction.

## Cadence
Capture a sanitized regression case after every meaningful failure. Optimize the active cohort continuously until its release gate passes, then move to the next cohort. Audit routing overlap, stale provenance, dependencies, and unused skills monthly. Rerun the full gate before public releases.

## Report
Report cohort, skills evaluated, baseline versus candidate, accepted/rejected changes, unresolved dependencies or human questions, proposal/commit, and the next highest-value work.

## Anti-patterns
- Bulk rewriting without baselines.
- Treating long prose as better triggering.
- Publishing private fixtures or runtime state.
- Copying upstream work without provenance and license.
- Applying improvements that overfit examples.
- Optimizing action volume instead of the owner’s intended outcome.
