# Public Skills Follow-up Hardening - 2026-08-24

## Scope

This report covers the 20 approved non-health/home packages requested for autonomous public-skill hardening:

- audience/community: `audience-content-engine`, `community-management`, `social-agent-practice`, `social-listening-engagement-loop`
- safety/state mutation: `publish`, `cron-scheduler`, `conversation-archive`
- owner operations: `daily-task-manager`, `briefing`, `owner-dream-cycle`
- research/writing: `literature-review`, `fact-check`, `draft-in-voice`
- portfolio governance: `skill-library-ops`, `team-skill-sharing-norm`, `public-post-workshop`
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

- Approved packages now must expose the reusable public operator sections: when to use, when not to use, required inputs, optional inputs, workflow, source freshness, privacy/mutations, safety, output contract, and failure conditions.
- Pending-review packages keep the existing candidate contract, preserving health/home proposal content while still validating all 30 packages.
- Eval validation now rejects generic placeholder assertions such as "Uses the skill" and requires at least four synthetic eval cases per package across supported eval files.
- Regression tests cover approved-package contract enforcement, placeholder assertion rejection, and package-level eval count enforcement.
- `skill-library-ops` now includes governance and jsonschema-parity failure cases in addition to release-gate cases.

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

- unit tests: `Ran 12 tests ... OK (skipped=1)`; the skipped test is the optional installed-`jsonschema` parity test because `jsonschema` is not present in this base image.
- validator: `Validation passed: 30 skills checked.`

Pinned `jsonschema==4.23.0` could not be provisioned locally: `python3 -m venv` failed because `ensurepip` is unavailable, `python3 -m pip` failed because `pip` is absent, `sudo` is unavailable, and direct `apt-get` lacks permission to update package lists. This is an environment limitation, not a repository failure; CI should install `jsonschema` if it wants that optional path.

## Author Review

Reviewed the changed skill contracts for public usability rather than section presence only. The main fixes were adding explicit missing-input behavior, exact mutation/authorization boundaries, failure states, and worked examples while preserving the existing domain-specific bodies. A validator false positive was fixed by removing the phrase that matched hidden private dependency language in `mcp-connector-onboarding`.

## Remaining Limitations

- The validator can verify public-contract structure and basic eval quality, but it cannot prove every assertion is semantically complete; human review remains required for domain quality.
- Installed-`jsonschema` parity was not runnable in this local container for the provisioning reasons above.
- No live Skill Workshop proposal or runtime skill was changed; applying these repository package improvements remains a separate governed action.
