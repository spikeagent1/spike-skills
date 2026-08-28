# spike-skills

Shareable, evaluation-backed skills maintained by Spike and Tapan.

This repository is the source of truth for skills we own or explicitly adapt. Runtime-installed skills, private state, credentials, memories, and raw conversation transcripts do not belong here.

## Current work

Audience/community, safety/state-mutation, owner-operations, research/writing, portfolio-governance, and onboarding cohorts have evaluated releases and now carry a consistent public operator contract for routing, inputs, workflow, freshness, privacy/mutation boundaries, outputs, and failures. See `evals/reports/public-skills-followup-2026-08-24.md` for the follow-up scorecard and verification evidence. Health and home/lifestyle packages are approved, applied through Skill Workshop, and released with the same operator-contract and evaluation gates. Wealth, travel/mobility, routing-overlap, and long-tail cleanup are next. A related-work survey grounding the personal-OS direction is in [docs/related-work.md](docs/related-work.md).

Candidate skills enter through Skill Workshop proposals. Candidate packages may appear in `skills/` on `main` for inspection before approval only when the repository contract marks them `pending-review`, keeps them in domain `next` lists instead of `released` lists, records the real proposal ID, and passes validation. Presence in this repository does not approve, apply, install, or release a Skill Workshop proposal. Released skills carry synthetic evaluation cases, provenance, compatibility notes, and a benchmark summary.

Start with the [onboarding collection](ONBOARDING.md) when setting up a new owner relationship, connector, runtime handoff, or social-agent identity.

## Layout

```text
catalog/             Cohorts and skill inventory
imports/             Pinned upstream material, unchanged
skills/              Approved owned/adapted skill packages
evals/baseline.json  Committed behavioral + routing baseline; regenerate with `make eval-baseline`
evals/reports/       Shareable benchmark summaries
evals/workspaces/    Local generated runs; ignored
schemas/             Validation schemas
tools/               Deterministic audit helpers
```

## Review a candidate

Each package uses `SKILL.md` as its package-level user and reviewer documentation. Approved public packages must define when to use the skill, when not to use it, required and optional inputs, workflow, source freshness, privacy and mutation boundaries, safety boundaries, output contract, dependencies, provenance, and failure conditions. Pending candidates use the same core contract while preserving their `pending-review` governance state. The adjacent `examples/evals.json` must exercise normal behavior, edge cases, factual uncertainty, privacy, and authorization before mutations.

Run the local gate from the repository root:

```sh
python3 -m py_compile tools/validate_repo.py tests/test_validate_repo.py
python3 -m unittest discover -s tests
python3 tools/validate_repo.py
```

`make validate` runs the same commands when `make` is installed. Candidate
review does not apply, install, or release a Skill Workshop proposal.

### Evaluation

Behavioral and routing evals run the real Claude Code CLI in an isolated
project, so they cost money and are never run in CI.

| Command | What it does |
| --- | --- |
| `make eval-doctor` | Probes auth and isolation and writes `evals/workspaces/doctor.json`. Required before any run; every other eval command refuses without it. |
| `make eval-skill SKILL=<name>` | Runs one skill's cases with and without its `SKILL.md` and compares the result against `evals/baseline.json`. |
| `make eval-baseline` | Re-records the full baseline: all behavioral cases, then routing in native mode. |

Each case is answered twice — once with the skill loaded, once without — and a
second, blind model grades both. An assertion both configs satisfy is
`non_discriminating`: it measures the model, not the skill.

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
