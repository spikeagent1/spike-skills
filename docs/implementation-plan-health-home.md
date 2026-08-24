# Health and home/lifestyle implementation plan

Target branch: `docs/life-domain-map`

## Goal

Prepare the first everyday-life cohort after audience/community as pending-review Skill Workshop candidates by adding portable health and home/lifestyle packages plus repository gates that keep every skill independently installable, attributable, dependency-declared, privacy-safe, and covered by synthetic evaluations.

## Step 0 Scope Challenge

What already exists: `ARCHITECTURE.md` defines the public-library boundary, `catalog/domains.yaml` names health and home/lifestyle as next but had no releases, `skills/skill-library-ops/SKILL.md` defines release gates, and existing skills use plain `SKILL.md` plus eval fixtures.

Minimum complete change: add the listed health and home/lifestyle candidate packages, add synthetic evals, update catalogs/docs, and add deterministic validation for manifests, evals, catalogs, local-state ignore rules, and obvious secret/private-data leaks.

Complexity decision: the file count is high because a library candidate cohort is many independent packages. The architecture stays small: no services, database, package manager, shared storage, or new runtime. Complete candidate-review option selected in spawned-session mode.

Search check: [Layer 1] reuse the repo skill layout and vendored Anthropic eval schema guidance. [Layer 1] use Python standard library validation because the repo has no package manifest. [Layer 3] keep health/home skills advisory and source-driven rather than adapting hidden hosted workflows.

## Architecture Review

Issue 1 accepted: prose gates are not enough. Recommendation selected: add `tools/validate_repo.py` and `make validate`, including pending-review catalog rules.

Issue 2 accepted: health skills need explicit non-diagnostic boundaries. Recommendation selected: add boundaries and eval cases for emergency or medical-advice pressure.

Issue 3 accepted: home/lifestyle skills must not fabricate prices, safety claims, stock, or real-time availability. Recommendation selected: require current sources or uncertainty.

## Code Quality Review

Issue 1 accepted: repeated portability/privacy rules can drift. Recommendation selected: centralize enforcement in one validator and keep skill bodies domain-specific.

Issue 2 accepted: catalog updates must be checked deterministically. Recommendation selected: validate approved and pending-review catalog entries, domain released/next entries, and skill directories together.

## Test Review

```text
CODE PATHS                                             USER FLOWS
[+] tools/validate_repo.py                             [+] Skill release gate
  |-- main()                                             |-- [TESTED] all current skills validate
  |-- iter skill dirs                                    |-- [TESTED] missing eval fails by rule
  |-- validate_skill()                                   |-- [TESTED] unlisted skill fails by rule
  |   |-- frontmatter present                            |-- [TESTED] local-state ignore checked
  |   |-- name/description valid                         |
  |   |-- eval JSON present and parseable              [+] Health invocation
  |   |-- catalog inventory entry exists                  |-- [EVAL] emergency request escalates
  |   |-- domain release or next entry exists             |-- [EVAL] medical diagnosis refused
  |   |-- dependency/provenance declared                  |
  |-- parse_domain_lists()/parse_catalog_inventory()                 [+] Home/lifestyle invocation
  |   |-- released/catalog mismatch                      |-- [EVAL] stale prices not fabricated
  |   |-- duplicate/missing skill names                   |-- [EVAL] household safety escalates
  |-- scan_secrets()
      |-- obvious token/secret line
      |-- private-state filename/path

COVERAGE AFTER IMPLEMENTATION: 13/13 paths covered by `make validate` plus synthetic eval fixtures for each new skill.
```

## Performance Review

No runtime performance issue. The validator is linear over tracked text, JSON, and Markdown files and skips generated workspaces and `.git`.

## NOT In Scope

- Hosted accounts, billing, Postgres, DBOS, queues, or shared event streams: contradicted by `ARCHITECTURE.md`.
- Runtime sync/install automation: no runtime credentials or connector state belong in the public repo.
- Real medical, purchase, pantry, or household records: public repo must use synthetic fixtures only.
- Full LLM eval scoring harness: deterministic schema/privacy validation is the immediate repository gate.

## What Already Exists

- Existing skill layout and eval fixture conventions are reused.
- Vendored Anthropic schema guidance is referenced but not modified.
- Existing catalogs are extended rather than replaced.

## Failure Modes

- Validator false positive on docs: covered by direct verification and scoped regexes.
- Health skill gives medical advice: covered by explicit skill boundaries and evals.
- Home skill fabricates current facts: covered by source-discipline instructions and evals.
- Catalog claims a missing release or candidate status: covered by `tools/validate_repo.py`.
- Private local state committed: covered by `.gitignore` and tracked-file scan.

## Parallelization

Lane A: health candidates -> catalog update. Lane B: home/lifestyle candidates -> catalog update. Lane C: validator/schema -> Make target. Lane D: docs/report after A+B+C. Conflict flag: A and B both touch `catalog/`.

## Implementation Tasks

- [x] T1 (P1) health candidate packages with boundaries and evals.
- [x] T2 (P1) home/lifestyle candidate packages with source discipline and evals.
- [x] T3 (P1) deterministic validation gate.
- [x] T4 (P2) docs/catalog/candidate review evidence.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | Decisions recovered from user prompt and commit `1bd7c4d` |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | - | Skipped: no external model tool available in this ACP session |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 5 issues, 0 critical gaps; all complete options folded into implementation |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | - | Not applicable: no UI changes |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | Not applicable: repo gate is command-line only |

- **VERDICT:** CEO + ENG CLEARED - ready to present as an unmerged pending-review PR.
NO UNRESOLVED DECISIONS
