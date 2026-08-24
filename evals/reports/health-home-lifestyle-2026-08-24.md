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

- Every candidate has `SKILL.md` frontmatter, explicit dependencies, provenance, and synthetic evals.
- Health skills include non-diagnostic and urgent-escalation boundaries.
- Home/lifestyle skills require current sources or uncertainty for prices, inventory, weather, recalls, specs, and safety claims.
- `tools/validate_repo.py` checks manifests, evals, catalog consistency, dependency/provenance declarations, `.gitignore` local-state rules, and obvious secrets/private paths.

## Acceptance

Ready for proposal review when `make validate` passes on the full repository. Release still requires explicit Skill Workshop approval and application. No private records, credentials, caches, transcripts, or generated local state are included.
