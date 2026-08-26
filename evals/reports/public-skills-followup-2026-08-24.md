# Public Skills Follow-up Hardening - 2026-08-24

## Scope

This report covers the 20 approved non-health/home packages requested for autonomous public-skill hardening:

- audience/community: `skill-library-ops`, `audience-content-engine`, `community-management`, `social-agent-practice`, `social-listening-engagement-loop`
- safety/state mutation: `publish`, `cron-scheduler`, `conversation-archive`
- owner operations: `daily-task-manager`, `briefing`, `owner-dream-cycle`
- research/writing: `literature-review`, `fact-check`, `draft-in-voice`
- portfolio governance: `team-skill-sharing-norm`, `public-post-workshop`
- onboarding: `owner-context-onboarding`, `mcp-connector-onboarding`, `runtime-handoff-onboarding`, `social-agent-onboarding`

The ten pending health/home candidates were not rewritten. Repository-wide validation changes remain compatible with them.

## Initial Gap Inventory

The initial audit found that all 20 in-scope approved skills had useful domain-specific procedure text but lacked a consistent public operator contract. Common missing pieces were explicit `When not to use`, `Optional inputs`, mutation authorization boundaries, output contracts, and failure conditions. `skill-library-ops` also had only two eval cases. The validator allowed those gaps because the stricter section contract only applied to `pending-review` packages.

## Scorecard

| Skill | Public contract | Synthetic eval cases | Main hardening focus |
| --- | --- | ---: | --- |
| `audience-content-engine` | pass | 5 | source-gated content, publication authority, engagement-safety boundary |
| `briefing` | pass | 4 | read-only coverage ledger, current-source citations, mutation refusal |
| `community-management` | pass | 14 | member-to-member diagnosis, consent, moderation, non-growth boundary |
| `conversation-archive` | pass | 4 | mode split, privacy scan, idempotent archive writes |
| `cron-scheduler` | pass | 4 | timezone resolution, idempotency, scheduler readback |
| `daily-task-manager` | pass | 4 | provider truth, task identity, mutation preview/readback |
| `draft-in-voice` | pass | 4 | voice authority, privacy clearance, draft-only boundary |
| `fact-check` | pass | 6 | atomic claims, current primary sources, confidence/disposition split |
| `literature-review` | pass | 4 | bounded protocol, dedupe, evidence synthesis limits |
| `mcp-connector-onboarding` | pass | 4 | install/auth/probe split, least privilege, secret handling |
| `owner-context-onboarding` | pass | 4 | one-question interview, durable memory preview/readback |
| `owner-dream-cycle` | pass | 4 | authorized corpus, duplicate prevention, non-clinical reflection boundary |
| `public-post-workshop` | pass | 4 | governance truth, draft-only publication package, PR boundary |
| `publish` | pass | 4 | exact target preview, verification URL/ID, rollback/correction path |
| `runtime-handoff-onboarding` | pass | 4 | identity recovery, capability matrix, stale handoff reconciliation |
| `skill-library-ops` | pass | 4 | repository lifecycle, governance preservation, validation/PR evidence |
| `social-agent-onboarding` | pass | 4 | identity/account state matrix, human-only steps, disclosure boundaries |
| `social-agent-practice` | pass | 6 | task routing, Spike identity/privacy, verified social/email mutations |
| `social-listening-engagement-loop` | pass | 5 | qualified opportunities, pagination, idempotent verified actions, no quotas |
| `team-skill-sharing-norm` | pass | 4 | immutable artifact identity, least-privilege adoption, sender-authority non-transfer |

## Validator and Eval Improvements

- Approved packages now must expose the reusable public operator sections: when to use, when not to use, required inputs, optional inputs, workflow, source freshness, privacy/mutations, safety, output contract, and failure conditions. The gate now also rejects blank, TODO-style, very short, and exactly duplicated public section bodies; this is deterministic structural coverage, not semantic completeness.
- Pending-review packages keep the existing candidate contract, preserving health/home proposal content while still validating all 30 packages.
- `catalog/sources.yaml` is now parsed as full source entries. Validation requires every tracked skill to have a source entry and checks classification, runtime path, repository path, status, and cohort parity with `catalog/approved.yaml`; adapted and vendored sources require upstream, publisher, version, license, local-modification summary, and an immutable commit or digest.
- Eval validation continues to reject generic placeholder assertions such as "Uses the skill" and requires at least four synthetic eval cases per package across supported eval files.
- Regression tests cover approved-package contract enforcement, weak section-body rejection, placeholder assertion rejection, package-level eval count enforcement, source entry presence/parity, and incomplete adapted metadata.
- `skill-library-ops` remains in the audience/community cohort, matching `catalog/approved.yaml`, `catalog/sources.yaml`, and the original release cohort. The previous report grouping under portfolio governance was drift and has been corrected.

## Governance State

No live Skill Workshop proposal was approved, applied, installed, released, or directly edited. No proposal IDs were invented. Pending health/home packages remain `pending-review` and in domain `next` lists. The public portable-library boundary remains intact: no hosted platform, hidden service, shared personal database, private runtime coupling, or tracked private state was introduced.

## Local Verification

Passed locally in stock Python:

```sh
python3 -m py_compile tools/validate_repo.py tests/test_validate_repo.py
python3 -m unittest discover -s tests
python3 tools/validate_repo.py
```

Observed output:

- unit tests: `Ran 21 tests ... OK (skipped=1)`; the skipped test is the optional installed-`jsonschema` parity test because `jsonschema` is not present in this base image.
- validator: `Validation passed: 30 skills checked.`

Pinned `jsonschema==4.23.0` could not be provisioned locally: `python3 -m venv` failed because `ensurepip` is unavailable, `python3 -m pip` failed because `pip` is absent, `sudo` is unavailable, and direct `apt-get` lacks permission to update package lists. This is an environment limitation, not a repository failure; CI should install `jsonschema` if it wants that optional path.

## Author Review

Reviewed the changed skill contracts for public usability rather than section presence only. The main fixes were adding explicit missing-input behavior, exact mutation/authorization boundaries, failure states, and worked examples while preserving the existing domain-specific bodies. This correction pass also rechecked appended public sections against existing domain sections for direct contradictions and kept eval assertions domain-specific rather than relying on generic contract language. A validator false positive was fixed by removing the phrase that matched hidden private dependency language in `mcp-connector-onboarding`.

## Provenance Corrections

- `literature-review`: catalog and `SKILL.md` now attribute the adapted source to ClawHub package `weird-aftertaste/literature-review` version 1.2.0, publisher `weird-aftertaste`, MIT-0 license from the public ClawHub page, archive SHA-256 `4fc44a5f45ae6820c08adc0a7aa4276aaa640e4eee3bd667059bceead772021e`, imported `SKILL.md` SHA-256 `c2f51919e7a65e36fb47a18dc09c451f59e046121c51e6bbcc002abfa9167b04`, and a local modification summary.
- `community-management`: catalog and `SKILL.md` now attribute the adapted source to ClawHub origin metadata for package `social-media-skills/community-management` version 1.0.1, archive SHA-256 `b9fdf15a26afa4b2e71c99a7c013947d897409fb592ac41cab9762c416a6c405`, imported `SKILL.md` SHA-256 `0b1be214f6b67bc184935fd54e46256835148fcb92c0c0c9e6f1239fddc603d1`, MIT license recorded in the imported `SKILL.md` frontmatter at repo commit `9df9234`, and a local modification summary. The exact public upstream page was not retrievable during this correction, so the license is not claimed as independently rechecked from a public page.

## Remaining Limitations

- The validator can verify catalog parity, adapted/vendored metadata presence, public-contract structure, deterministic weak bodies, and basic eval quality, but it cannot prove every section or assertion is semantically complete; human review remains required for domain quality.
- The exact public ClawHub page for `social-media-skills/community-management` was not retrievable during this correction; only local origin metadata, imported file digests, git history, and the imported `SKILL.md` license field were used for that package.
- Installed-`jsonschema` parity was not runnable in this local container for the provisioning reasons above.
- No live Skill Workshop proposal or runtime skill was changed; applying these repository package improvements remains a separate governed action.
