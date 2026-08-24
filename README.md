# spike-skills

Shareable, evaluation-backed skills maintained by Spike and Tapan.

This repository is the source of truth for skills we own or explicitly adapt. Runtime-installed skills, private state, credentials, memories, and raw conversation transcripts do not belong here.

## Current work

Audience/community, safety/state-mutation, owner-operations, research/writing, portfolio-governance, and onboarding cohorts have evaluated releases. Health and home/lifestyle candidate packages are present in `skills/` on this review branch only while their Skill Workshop proposals remain pending review. Wealth, travel/mobility, routing-overlap, and long-tail cleanup are next.

Candidate skills enter through Skill Workshop proposals. On review branches, candidate packages may appear in `skills/` for inspection before approval; they must be marked `pending-review`, remain in domain `next` lists, and carry the real proposal ID. Released skills carry synthetic evaluation cases, provenance, compatibility notes, and a benchmark summary.

Start with the [onboarding collection](ONBOARDING.md) when setting up a new owner relationship, connector, runtime handoff, or social-agent identity.

## Layout

```text
catalog/             Cohorts and skill inventory
imports/             Pinned upstream material, unchanged
skills/              Approved owned/adapted skills plus review-branch candidates
evals/reports/       Shareable benchmark summaries
evals/workspaces/    Local generated runs; ignored
schemas/             Validation schemas
tools/               Deterministic audit helpers
```

## Review a candidate

Each candidate package uses `SKILL.md` as its package-level user and reviewer
documentation. It must define when to use the skill, required inputs, workflow,
source freshness, privacy and mutation boundaries, safety boundaries, output
contract, dependencies, provenance, and failure conditions. The adjacent
`examples/evals.json` must exercise normal behavior, edge cases, factual
uncertainty, and authorization before mutations.

Run the local gate from the repository root:

```sh
python3 -m py_compile tools/validate_repo.py tests/test_validate_repo.py
python3 -m unittest discover -s tests
python3 tools/validate_repo.py
```

`make validate` runs the same commands when `make` is installed. Candidate
review does not apply, install, or release a Skill Workshop proposal.

## Release gate

1. Define the trigger and expected output.
2. Extract sanitized regression cases from observed failures.
3. Compare the candidate with the previous released version or a no-skill baseline.
4. Review outputs, objective checks, latency, and token use.
5. Verify dependencies, provenance, license, privacy, and mutation scope.
6. Apply the Skill Workshop proposal only after explicit approval.
7. Run `make validate` to compile validation code, run validator tests, and check manifests, eval schema structure, catalogs, dependencies, provenance, ignored local state, and obvious secrets. When `make` is unavailable, run the three commands in the Makefile directly.
8. Commit one coherent skill change and publish through a pull request.

The public remote is `spikeagent1/spike-skills`. Public releases exclude credentials, private memory, raw conversations, and internal operational weakness reports.
