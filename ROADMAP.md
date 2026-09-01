# Optimization roadmap

## Cohort 1: audience and community

### 1. Social listening and engagement — released

Observed defect: the live skill encoded a bounded feed and “a few” interactions, so a quality guard became an engagement quota. The candidate replaces this with opportunity-based completion, direct-response priority, verified mutations, and outcome attribution.

Acceptance evidence:

- regression cases for empty first pages, platform verification, unavailable channels, activity-versus-traction reporting, and attempts to reintroduce quotas;
- comparison against the current runtime skill;
- review of real but sanitized Moltbook failure patterns;
- live smoke test after explicit proposal approval and runtime sync.

### 2. Social media content engine — released as audience-content-engine

The imported engine mixes useful templates with hard-coded posting cadences, engagement quotas, unsupported performance claims, stale platform specifications, engagement-pod tactics, and generic brand advice. Split stable strategy from time-sensitive platform references. Remove fabricated certainty and require native analytics or cited current sources for claims that change over time.

### 3. Social agent practice — released

This owned skill currently combines social conduct, writing and belief updates, email handling, facilitator protocol, and scheduled-run policy. Preserve its authority and privacy contract, but extract narrowly scoped references so social engagement does not need to load unrelated email and roster procedures.

### 4. Community management — released

The imported skill has a strong member-to-member community distinction, but assumes unavailable WoopSocial companion skills and makes broad “algorithm-proof” claims. Adapt it to our actual wall, Moltbook, AgentMail, GitHub, and future connected channels; preserve consent and genuine-community protections.

## Evaluation sequence

For each skill:

1. Capture trigger intent and expected output.
2. Build synthetic cases from observed corrections and near misses.
3. Snapshot the current version.
4. Compare candidate and baseline on the same cases.
5. Generate a review artifact for human inspection.
6. Accept only measured improvements or a documented defect removal without regression.
7. Apply the proposal explicitly, sync to runtime, and smoke-test.

## Released cohorts — complete

**All eight cohorts are released and every one of the 31 packages is at
`contract_version: 2`.** The audience/community, safety/state-mutation,
owner-operations, research/writing, portfolio-governance, onboarding,
health, and home/lifestyle packages each passed their own behavioural and
routing gates, and each carries the canonical thirteen-section contract,
`metadata.spike-os` declarations checked against
`contracts/capabilities.yaml` and `contracts/datastore.md`, and a runtime
binding that resolves for every adapter it claims.

A 2026-08-24 follow-up hardening pass added the reusable public operator
contract to the 20 approved non-health/home packages and recorded the
scorecard in `evals/reports/public-skills-followup-2026-08-24.md`. The
eight rewrite batches that followed are reported per cluster in
`evals/reports/rewrite-*.md`.

What is open, and where it is tracked:

- **Eval fixture debt.** 72 assertions fail on the skill-loaded arm, most
  of them asserting an action a text-only harness cannot take. The
  standing proposals are in
  `evals/reports/assertion-pruning-2026-08-29.md`; none has been applied,
  and no fixture has been edited.
- **Routing overlap.** Measured per cluster in the rewrite reports; the
  residual null-case hijacks are in the pruning report's routing section.
  `catalog/cohorts.yaml` carries `routing-overlap-and-long-tail` as a
  queued cohort with no skills assigned; the launcher is its first
  candidate. `home` routes **50%** in the committed baseline (8 of 16
  intents, lenient and strict alike) -- the lowest file on the ballot, and
  by design the hardest, since every intent it should win is one another
  skill's description also fits. Raising that number is the cohort's work,
  not a fix to one description.
- **Effect enforcement.** The effect declaration is lint: the validator
  greps the body for keywords and cannot see intent, and nothing at run
  time stops an undeclared effect. The enforcement path is emitting a
  `PreToolUse` hook from `metadata.spike-os.effects` so the runtime denies
  the call rather than the repository documenting that it should not
  happen. Nothing of it exists yet.
- **Listing budget bound to the adapter.** `LISTING_BUDGET_CHARS` is
  16,000 in `tools/validators/context.py`, a constant the validator owns.
  The number it stands for is OpenClaw's `maxSkillsPromptChars`, which the
  runtime configures and the adapter should carry, so the budget the
  validator enforces is the budget the runtime actually applies.
- **Rendered-frontmatter routing mode.** Every routing baseline puts the
  portable `skills/*/SKILL.md` frontmatter on the ballot. The installed
  form differs -- claude-code renders `disable-model-invocation: true` for
  any skill declaring a `never_autonomous` effect, which removes it from
  the native router's ballot -- so no measurement yet describes routing
  over an installed library. `run_evals.py routing` needs a mode that
  renders each ballot entry through the adapter first. No skill in the
  library declares one today, so the two ballots currently agree.
- **New domains.** Wealth and travel/mobility have no packages. They are
  the next cohorts, not unfinished work in these eight.

## Cohort 2: health and home/lifestyle - released

This released cohort provides the first everyday-life slice after audience/community with
portable, advisory packages rather than a hosted personal-data platform. The ten proposals were explicitly approved, applied through Skill Workshop, discovered by the runtime, and reconciled in the release catalogs.

Released health skills:

- fitness-coach
- meal-planner
- sleep-review
- health-appointment-prep
- medication-and-symptom-log

Released home/lifestyle skills:

- home-cook
- grocery-planner
- household-maintenance
- purchase-research
- wardrobe-and-packing

Review evidence:

- synthetic eval cases for normal planning, red-flag escalation, source freshness,
  allergy/safety constraints, and refusal to fabricate personal or current facts;
- explicit dependencies and provenance in every `SKILL.md`;
- deterministic `make validate` gate for manifests, evals, catalog status, privacy,
  dependency declarations, and obvious secrets;
- local-only persistence language where a skill may write user-owned files;
- real proposal IDs retained in `catalog/approved.yaml`, with applied packages moved to domain `released` lists.
