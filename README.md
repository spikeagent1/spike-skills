# spike-skills

A personal operating system, as a library of installable skills. The portable
core — skills, contracts, catalog, tooling — lives here; a runtime is an adapter
over that core, not a fork of it. [ARCHITECTURE.md](ARCHITECTURE.md) is the
design; this file is how to work in the repository.

Runtime-installed skills, private state, credentials, memories, and raw
conversation transcripts do not belong here.

## Where things are

```text
skills/              31 skill packages, each centred on SKILL.md
contracts/           The rules every skill follows, and the stores they name
adapters/            One directory per runtime: the vocabulary bindings and the rendered ADAPTER.md
catalog/             The inventory, the domains, the cohorts, the routing clusters, the generated index
evals/baseline.json  The committed behavioural + routing baseline
evals/reports/       Shareable benchmark summaries and the fixture-debt registers
evals/workspaces/    Local generated runs; gitignored
docs/                The related-work survey the design is grounded in
imports/             Pinned upstream material, unchanged
schemas/             Validation schemas
tools/               The validator, the eval runner, the installer, the index builder
```

## The contract every skill follows

[contracts/skill-contract.md](contracts/skill-contract.md) holds the rule IDs —
dependencies, mutation boundary, privacy, safety, freshness, output, failure,
provenance, and the runtime vocabulary. A skill cites a rule by ID rather than
restating it, and restates one only to add a domain-specific delta.

[contracts/SKILL.template.md](contracts/SKILL.template.md) is the canonical
shape: **thirteen H2 sections in a fixed order**, of which eight are mandatory —
`Overview`, `When to use`, `When not to use`, `Inputs`, `Workflow`,
`Output contract`, `Failure conditions`, `Contract` — and five optional:
`Worked example`, `Sources and freshness`, `Privacy and mutations`,
`Safety boundaries`, `Common mistakes`. An optional section carries domain
deltas only; the generic rules live in the contract. `tools/validate_repo.py`
enforces the set, the order, and the body quality of every one of them.

Frontmatter is the six agentskills.io keys plus `metadata.spike-os`, which
declares the semantic version, the runtimes the skill claims, the datastore
namespaces it reads and writes, and the effects it performs. The closed effect
enum is [contracts/capabilities.yaml](contracts/capabilities.yaml); the
namespaces are [contracts/datastore.md](contracts/datastore.md); the neutral
runtime terms are [adapters/vocabulary.yaml](adapters/vocabulary.yaml).

`catalog/approved.yaml` carries each package's `contract_version`. Version 2 is
the only shape the validator knows; the field stays so a future bump has
somewhere to declare itself. It is a different number from the
`<!-- contract-version: 1 -->` marker at the top of
[contracts/skill-contract.md](contracts/skill-contract.md) and
[contracts/datastore.md](contracts/datastore.md), and the two never move
together: the catalog field is the **template shape** a package is written to
(thirteen sections, `metadata.spike-os`, the declaration rules), while the
file-level marker is the version of that contract document's own rules, which a
skill cites as `v1` in its `## Contract` section. A skill at
`contract_version: 2` follows skill-contract v1; both numbers are correct.

## The gate

```sh
make validate     # the unit tests, the repository validator, the citation check
```

`make validate` runs `make test` (a compile pass over every tool and test, then
`python3 -m unittest discover -s tests`), then `tools/validate_repo.py`,
`tools/check_citations.py`, and `tools/build_index.py --check`. Run it before
opening or updating a pull request. Without `make`, run those four commands
directly. `.github/workflows/validate.yml` calls the target itself, twice --
once on a stock Python and once with `jsonschema` installed, since the validator
takes a different path on each -- so a gate added here is a gate CI runs.

`tools/validate_repo.py` composes the rule modules under `tools/validators/`:
frontmatter, structure, catalog, contracts, and evals. It checks the canonical
sections, the description rules and the launcher listing budget, catalog and
source parity, provenance artifacts, the declared namespaces and effects against
the contracts, the runtime binding for every adapter a skill claims, the eval
fixtures against `schemas/skill-evals.schema.json`, and the committed baseline
against the tree.

What the validator checks about effects is a **keyword scan, not an
understanding of intent**. `CAPABILITY_HINTS` maps body words -- "publish",
"send", "delete", "schedule", "commit" -- to the effects that would cover them,
and reports a skill that uses one without declaring the effect. Some rows also
require a context word in the same clause, because the verb alone is ambiguous:
"create" is `provider:write` only beside a `provider`, "notify" is `notify:owner`
only beside the `owner`. It reads a negation as governing the clause it sits in
rather than the whole sentence, so "never publishes -- it hands the draft on"
scans the second clause; it still cannot tell a verb the skill performs from one
it quotes or routes elsewhere, and it misses any phrasing outside the list. So
the declaration is **lint, not a boundary**: nothing at run time stops a skill taking an effect it never
declared. What the declaration does buy is a machine-readable claim -- the
installer refuses on it, `--check` re-derives the hints from it, and the
`effects/` ledger is auditable against it after the fact. Emitting a
`PreToolUse` hook from the declaration is the enforcement path, and it is on the
roadmap rather than in the repository.

`tools/check_citations.py` verifies that every `skills/<name>/SKILL.md:<line>`
anchor in `contracts/`, `adapters/`, and `docs/` still resolves to a body
statement; `--show` prints each anchor beside the line it lands on, which is the
audit to do after editing a skill.

## Installing a skill into a runtime

```sh
python3 tools/install_skill.py --runtime claude-code <name>     # or --all
python3 tools/install_skill.py --runtime claude-code --check    # declared vs actual
make stage-openclaw                                             # stage every eligible skill into dist/
```

The installer renders the portable `SKILL.md` for one runtime: it emits that
adapter's frontmatter keys, appends the `## Runtime binding` trailer, copies the
supporting directories and the repository files the skill declares as inputs,
and writes a `.spike-os.json` stamp — which is what makes a directory ours to
overwrite and `--check` possible at all. It refuses a skill whose declared
runtimes exclude the target, a destination holding somebody else's skill, and a
skill depending on a term the adapter marks UNCONFIRMED — a binding nobody can
attest. A binding the runtime knows to be absent or partial is marked DEGRADED
instead: the skill's own contract already discloses what it does without it, so
the skill installs and the run prints a `degraded:` note naming the term.
`--dry-run` prints what a run would write and writes nothing.

## Evaluation

Behavioural and routing evals run the real Claude Code CLI in an isolated
project, so they cost money and are never run in CI.

| Command | What it does |
| --- | --- |
| `make eval-doctor` | Probes auth and isolation and writes `evals/workspaces/doctor.json`. Required before any run; every other eval command refuses without it. |
| `make eval-skill SKILL=<name>` | Runs one skill's cases with and without its `SKILL.md` and compares against `evals/baseline.json`. |
| `make eval-routing` | Measures which skill the router picks for each `routing-eval.jsonl` intent. |
| `make eval-report RUN=<id>` | Re-renders one run's report. |
| `make eval-baseline` | Re-records the full baseline: all behavioural cases, then routing in native mode. |

Each case is answered twice — once with the skill loaded, once without — and a
second, blind model grades both. An assertion both configs satisfy is
`non_discriminating`: it measures the model, not the skill. An assertion the
skill-loaded arm fails is `broken`; the standing proposals for those are in
`evals/reports/assertion-pruning-2026-08-29.md`.

`make eval-skill` exits **3** when any grading in the run is ungraded
(`grader_error`, `no_response`). A transient grader error is never cached, so a
retry costs nothing: re-grade with `python3 tools/run_evals.py grade --run
<run-id>` — only the ungraded cases are re-graded — then re-invoke
`make eval-skill`.

`python3 tools/run_evals.py baseline update --from <run> [--skill a,b]` merges a
run into the baseline, per skill; `--routing-from <run>` merges a routing run
per file, leaving files the run did not cover alone.

## Review a candidate

Candidate skills enter through Skill Workshop proposals. A candidate may appear
in `skills/` on `main` for inspection before approval only when it is marked
`pending-review`, sits in a domain `next` list rather than `released`, records a
real proposal ID, and passes validation. Presence here does not approve, apply,
install, or release a proposal.

The release gate:

1. Define the trigger and the expected output.
2. Extract sanitized regression cases from observed failures.
3. Compare the candidate against the previous released version or the no-skill arm.
4. Review outputs, objective checks, latency, and token use.
5. Verify dependencies, provenance, license, privacy, and mutation scope.
6. Apply the Skill Workshop proposal only after explicit approval.
7. Run `make validate`, and `make eval-skill SKILL=<name>` for every skill touched.
8. Commit one coherent skill change and publish through a pull request.

Start with the [onboarding collection](ONBOARDING.md) when setting up a new owner
relationship, connector, runtime handoff, or social-agent identity. The
related-work survey grounding the design is in
[docs/related-work.md](docs/related-work.md).

The public remote is `spikeagent1/spike-skills`. Public releases exclude
credentials, private memory, raw conversations, and internal operational
weakness reports.
