# Contributing

Keep each change attributable, testable, and safe to share.

- Do not commit credentials, private messages, visitor identity, memories,
  production checkpoints, or raw session transcripts.
- Use synthetic fixtures that preserve the structure of a real failure.
- Record upstream URL, commit, license, and local modifications for imported work.
- Do not edit vendored imports in place.
- Put reusable skill changes through Skill Workshop. Pending proposals are not releases.
- Include representative success cases, an edge case, near-miss triggers, and
  authorization cases for mutating skills.
- Reject improvements that only polish prose without improving held-out behaviour
  or eliminating a documented defect.

## Editing a skill

[contracts/SKILL.template.md](contracts/SKILL.template.md) is the shape and
[contracts/skill-contract.md](contracts/skill-contract.md) is the rule set. A
skill must:

1. Carry the thirteen canonical H2 sections in their fixed order — eight
   mandatory, five optional — with each optional section holding domain deltas
   only. A section that restates a contract rule instead of citing its ID is the
   duplication the contract exists to remove.
2. Open with a `description` that is third person, at most 300 characters, starts
   with "Use when", names concrete phrasings, names no principal and no runtime,
   and carries one negative clause naming a sibling skill.
3. Declare in `metadata.spike-os` its semantic version, the runtimes it claims,
   the namespaces it reads and writes, and the effects it performs. A non-empty
   `reads_from` needs `datastore:read`; a non-empty `writes_to` needs
   `datastore:write`; any mutating effect needs `effects` in `writes_to`, and
   `notify:owner` needs `notifications`. Declare what the skill actually does,
   not what makes the scan quiet: the validator's effect check greps the body
   for keywords ("publish", "send", "delete", "commit") and cannot tell a verb
   the skill performs from one it forbids or routes elsewhere, so it both
   misfires and misses. And the declaration is lint, not a boundary — nothing at
   run time stops an undeclared effect; it buys a claim the installer can refuse
   on and the `effects/` ledger can be audited against.
4. Name every runtime fact with a term from
   [adapters/vocabulary.yaml](adapters/vocabulary.yaml), never a product name, a
   path, or a proper noun a single runtime supplies.
5. Carry a produce-anyway clause as a numbered `Workflow` step and again at the
   top of `Output contract`: the deliverable is produced in this turn from what
   the request already carries. A marked slot stands in for a missing fact, never
   for the substance of a draft, a reply, or an argument (X6).
6. Name every cluster sibling from `catalog/routing.yaml` in `When not to use`,
   each with the observable condition that sends work there.
7. Link every supporting file from `SKILL.md`, one level deep, and declare any
   repository file it reads on the `Dependencies:` line — that line is what the
   installer bundles and what the eval executor grants.
8. Keep unique positive eval IDs, at least two non-empty assertions per case, at
   least two `routing-eval.jsonl` lines expecting the skill itself and one
   expecting no skill.

After editing a skill body, re-run `python3 tools/check_citations.py --show` and
confirm every anchor into that file still lands on the sentence the citing rule
is about. Line numbers move; the citation does not follow.

Two version numbers are easy to confuse and never move together.
`catalog/approved.yaml`'s `contract_version: 2` is the **template shape** a
package is written to — the thirteen sections, `metadata.spike-os`, the
declaration rules. The `<!-- contract-version: 1 -->` marker at the top of
`contracts/skill-contract.md` is the version of that document's own rules, which
each skill cites as `v1` in its `## Contract` section. A `contract_version: 2`
package following skill-contract v1 is correct, not skewed.

## Before opening a pull request

```sh
make validate                     # tests, validator, citation check, index check
make eval-skill SKILL=<name>      # for every skill the change touches
```

`make validate` is the whole gate and the only thing CI runs (twice: once on a
stock Python, once with `jsonschema` installed). A check worth having belongs in
that target, not in the workflow file.

A per-skill pass-rate drop against `evals/baseline.json`, or any assertion that
regresses, blocks the PR. Fix the skill, never the eval: a fixture change is a
separate proposal, and the standing ones live in
`evals/reports/assertion-pruning-2026-08-29.md`.

`make eval-skill` exits **3** when any grading in the run is ungraded
(`grader_error`, `no_response`) — a transient grader error is never cached, so it
costs nothing to retry. Re-grade with
`python3 tools/run_evals.py grade --run <run-id>` (only the ungraded cases are
re-graded) and re-invoke `make eval-skill`.

When a `description` changes, re-run routing for the skill and every sibling in
its `catalog/routing.yaml` cluster: the description is the ballot the router
votes on, and changing one line moves every file's numbers.

Re-baseline from a clean tree once the gates pass:

```sh
python3 tools/run_evals.py baseline update --from <run-id> --skill <name> --require-clean
python3 tools/run_evals.py baseline check
```

`baseline update` refuses a merge that regresses against the entry it would
replace, and one carrying an ungraded assertion. Both refusals leave every
committed entry untouched; `--allow-regression` and `--allow-ungraded` merge
deliberately, and either is a decision to state in the pull request.
