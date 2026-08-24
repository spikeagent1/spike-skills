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

## Released cohorts

The evaluated audience/community, safety/state-mutation, owner-operations, research/writing, portfolio-governance, and onboarding packages are released. A 2026-08-24 follow-up hardening pass added the reusable public operator contract to all 20 approved non-health/home packages, strengthened validator coverage for public contracts, catalog/source parity, and adapted provenance metadata, and recorded the scorecard in `evals/reports/public-skills-followup-2026-08-24.md`. Routing-overlap and long-tail cleanup follows; unresolved candidates remain unpublished until they pass their own gates.

## Cohort 2: health and home/lifestyle - pending review

This candidate cohort prepares the first everyday-life slice after audience/community with
portable, advisory packages rather than a hosted personal-data platform. The packages remain pending Skill Workshop review and are not released.

Pending health candidates:

- fitness-coach
- meal-planner
- sleep-review
- health-appointment-prep
- medication-and-symptom-log

Pending home/lifestyle candidates:

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
- real pending proposal IDs recorded in `catalog/approved.yaml`, with candidates kept in domain `next` lists until explicit approval.
