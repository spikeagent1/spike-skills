# Health and home/lifestyle candidate review report

Date: 2026-08-24
Branch: docs/life-domain-map

## Cohort

Prepared health and home/lifestyle Skill Workshop candidates as portable plain-file packages. They are present in `skills/` only for review on this branch and are not approved, applied, installed, or released:

- fitness-coach
- meal-planner
- sleep-review
- health-appointment-prep
- medication-and-symptom-log
- home-cook
- grocery-planner
- household-maintenance
- purchase-research
- wardrobe-and-packing

## Gate evidence

- Every candidate has a domain-specific `SKILL.md` contract covering trigger,
  required inputs, workflow, source freshness, privacy/mutations, safety, output,
  dependencies, provenance, and failure conditions.
- The cohort has 50 synthetic cases: five per skill. The added cases target
  authorization before mutation, cross-skill storage isolation, current-fact
  verification, conflicting evidence, and high-risk escalation.
- Health skills include non-diagnostic, medication, and urgent-escalation
  boundaries. Home/lifestyle skills require current sources or explicit
  uncertainty for prices, inventory, weather, recalls, specifications, and
  safety claims.
- The eval schema and stock-Python fallback require positive integer IDs and
  non-empty fields. The validator also rejects duplicate IDs, blank assertions,
  and the prior non-informative expected-output placeholder.
- `tools/validate_repo.py` checks manifests, eval schema structure, catalog
  consistency, dependency/provenance declarations, ignored local state, and
  obvious secrets/private paths.
- `.github/workflows/validate.yml` pins the official `actions/checkout@v5`
  and `actions/setup-python@v6` Node 24 commits, then runs compilation,
  tests, and repository validation twice: stock Python first, then with pinned
  `jsonschema==4.26.0` to exercise parity.

## Independent review

A cold reviewer applied the pinned engineering-practices sections
`What to look for in a code review: Design, Functionality, Tests,
Documentation, Every Line`. The first pass found three correctness gaps:
urgent-routing contradictions, optional eval IDs, and schema/fallback
whitespace drift. All three were fixed and the second pass returned clear.

Residual risks are bounded and explicit:

- the 50 cases validate contracts and assertions, not live model-output quality;
- GitHub Actions must pass both the stock-Python and `jsonschema` gates on the
  final pushed head.

## Acceptance

The local gate passes on the full repository: nine tests (one skipped when
optional `jsonschema` is unavailable) and 30 skill packages. GitHub Actions
must pass again on the pushed head before merge.
Release still requires explicit Skill Workshop approval and application. The
ten candidates remain pending review; no private records, credentials, caches,
transcripts, or generated local state are included.
