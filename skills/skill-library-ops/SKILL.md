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

## When to use
Use this skill to maintain this public skill library: audit packages, update catalogs, add evals, validate governance, prepare reviewable branches, and open unmerged PRs.

## When not to use
Do not use it to install or apply live Skill Workshop proposals, merge PRs, edit private runtime skills outside the repository, publish secrets, or create hidden hosted dependencies.

## Required inputs
Required inputs are repository path, target package set, governance scope, desired change, and verification requirements. If proposal state or package scope is unclear, inspect catalogs and report the blocker before editing.

## Optional inputs
Optional inputs include cohort label, reviewer focus, issue/PR links, release notes, and benchmark report destination. Missing optional inputs should not block validation or a focused PR.

## Workflow
1. Read repository contracts, catalogs, schemas, validators, and current git state.
2. Produce a gap inventory before changing package content.
3. Make reviewable commits that preserve public portable boundaries and proposal truth.
4. Add or update synthetic evals and validator regression tests for systemic gaps.
5. Run compile, unit tests, validator, JSON/JSONL parsing, schema, catalog, provenance, dependency, privacy, secret, workflow, and whitespace gates.
6. Self-review the diff, then run an independent review when available.
7. Push a branch and open an unmerged PR with truthful evidence and limitations.
8. Do not merge or apply live proposals without explicit separate authorization.

## Sources and freshness
Use current git state, local validation output, catalog files, PR/CI state, and repository docs as sources of truth. Re-check branch status and CI immediately before final reporting.

## Privacy and mutations
Reading and auditing are non-mutating. Editing files, creating commits, pushing branches, opening PRs, or writing reports are mutating. Never modify owner workspace live skills outside this repository or commit private state, credentials, raw transcripts, or generated local workspaces.

## Safety boundaries
Preserve governance truth: pending proposals remain pending, proposal IDs are not invented, and public packages cannot depend on hidden hosted control planes or shared private databases.

## Output contract
Return gap inventory, changed packages, eval counts, validator/test evidence, review findings/fixes, branch, commits, PR URL, CI state, governance state, and honest limitations.

## Failure conditions
Fail when validation does not pass, catalogs and packages disagree, private data is tracked, proposal state would be falsified, CI cannot be verified for a required claim, or the PR cannot be opened unmerged.

## Worked example
For "harden a cohort," audit all named skills, patch contracts and evals, add validator tests for discovered gaps, run `make validate`, push a branch, open a PR, and report exact evidence.

## Dependencies
Requires a local git checkout, Python 3 for validators/tests, optional `jsonschema` for schema parity, and GitHub/`gh` only when opening or checking PRs. No hidden service, shared database, or private runtime dependency is required.

## Provenance
Repo-owned operations workflow maintained as public portable skill text with synthetic fixtures only.
