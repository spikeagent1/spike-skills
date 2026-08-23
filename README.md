# spike-skills

Shareable, evaluation-backed skills maintained by Spike and Tapan.

This repository is the source of truth for skills we own or explicitly adapt. Runtime-installed skills, private state, credentials, memories, and raw conversation transcripts do not belong here.

## Current work

The first optimization cohort is **audience and community**. It starts with the social-listening engagement loop because the live workflow encoded engagement scarcity as policy and measured activity more carefully than traction.

Candidate skills enter through Skill Workshop proposals. A proposal is not copied into `skills/` until it is reviewed and explicitly applied. Released skills carry synthetic evaluation cases, provenance, compatibility notes, and a benchmark summary.

## Layout

```text
catalog/             Cohorts and skill inventory
imports/             Pinned upstream material, unchanged
skills/              Approved owned/adapted skills
evals/reports/       Shareable benchmark summaries
evals/workspaces/    Local generated runs; ignored
schemas/             Validation schemas
tools/               Deterministic audit helpers
```

## Release gate

1. Define the trigger and expected output.
2. Extract sanitized regression cases from observed failures.
3. Compare the candidate with the previous released version or a no-skill baseline.
4. Review outputs, objective checks, latency, and token use.
5. Verify dependencies, provenance, license, privacy, and mutation scope.
6. Apply the Skill Workshop proposal only after explicit approval.
7. Commit one coherent skill change and publish through a pull request.

The initial remote target is `spikeagent1/spike-skills`, private while the catalog and release gate stabilize.
