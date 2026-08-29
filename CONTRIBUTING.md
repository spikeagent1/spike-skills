# Contributing

Keep each change attributable, testable, and safe to share.

- Do not commit credentials, private messages, visitor identity, memories, production checkpoints, or raw session transcripts.
- Use synthetic fixtures that preserve the structure of a real failure.
- Record upstream URL, commit, license, and local modifications for imported work.
- Do not edit vendored imports in place.
- Put reusable skill changes through Skill Workshop. Pending proposals are not releases.
- Include representative success cases, an edge case, near-miss triggers, and authorization cases for mutating skills.
- Reject improvements that only polish prose without improving held-out behavior or eliminating a documented defect.

## Candidate package checklist

A candidate skill must:

1. Keep its purpose and trigger narrow enough that an agent can route reliably.
2. Separate required user inputs from assumptions and ask only when safety or
   feasibility depends on the answer.
3. Declare source freshness rules for claims that can change.
4. Preview connector or file mutations and require explicit authorization.
5. State domain-specific stop and escalation conditions.
6. Define a concrete output contract and explicit failure conditions.
7. Include unique positive eval IDs, at least two non-empty assertions per case,
   and meaningful `expected_output` text when that optional field is used.
8. Cover a representative success, edge case, factual-uncertainty case, and
   authorization case for every available mutation path.

Run `make validate` before opening or updating a pull request. If `make` is
unavailable, run the three commands documented in the root `README.md`.

Run `make eval-skill SKILL=<name>` before opening a PR that edits a skill; a
per-skill pass-rate drop vs `evals/baseline.json` blocks the PR.

`make eval-skill` exits 3 when any grading in the run is ungraded
(`grader_error`, `no_response`) — a transient grader error is never cached, so
it costs nothing to retry. Re-grade with
`python3 tools/run_evals.py grade --run <run-id>` (only the ungraded cases are
re-graded) and re-invoke `make eval-skill`.
