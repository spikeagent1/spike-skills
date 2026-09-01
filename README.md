# spike-skills

A personal operating system, as a library of installable skills. Thirty-two
packages — a day's briefing, a week's meals, a clinical visit to prepare, a post
to publish — each written once, portable across runtimes, and installed into the
agent you actually use. [ARCHITECTURE.md](ARCHITECTURE.md) is the design.

Runtime-installed skills, private state, credentials, memories, and raw
conversation transcripts do not belong here.

## Start here

You need **Python 3.11 or newer** (the version CI pins; older interpreters are
told so and stop), `git`, and — for the last step only — the
[Claude Code](https://claude.com/claude-code) CLI.

```sh
git clone https://github.com/spikeagent1/spike-skills.git
cd spike-skills
make start                      # or: python3 tools/bootstrap.py
```

`make start` is the whole setup, and it asks before it writes:

1. **Probes this host now** — the interpreter, the `claude` CLI, and every
   provider the adapter names, read against the connectors this machine
   actually registers. What it finds absent, it names, with the fix for that
   one thing; the run carries on.
2. **Asks for your ten local values** — your name, your timezone, where your
   vault lives, when your quiet hours are. Each question carries a one-line
   gloss and an example. They are written to
   `~/.config/spike-os/claude-code.local.yaml`, outside this repository, and
   never committed. Leave one empty and the run says which and exits nonzero:
   an unfilled value stays a literal `${OWNER_TZ}` in the file your agent reads.
3. **Installs `home` and a starter set** — `home`, `owner-context-onboarding`,
   `briefing`, `daily-task-manager` — into `~/.claude/skills`.
4. **Verifies with one real invocation**: `claude -p "/home"`. It costs pennies
   and needs a logged-in session; without the CLI, or with `--no-smoke`, it
   prints the command for you to run rather than skipping it in silence.
5. **Tells you what to type.**

Then, in Claude Code:

```
/home
```

`home` is the dispatcher. It reads [catalog/index.md](catalog/index.md), names
exactly one skill, and hands your request over — it never does the work itself.
Invoked bare, with no request at all, it prints the index: eight domains and the
skills under them. That is the fastest way to see what you have.

### Your first real skill

```
/owner-context-onboarding
```

This is the one to run first: it establishes who you are to the agent — how to
address you, what it may keep, what it may never write down — and puts that in
your vault, where every other skill reads it. Then try `/briefing` ("what's
happening today") and `/daily-task-manager` ("remind me to renew the insurance
next Tuesday").

### When a run says `degraded:`

The installer prints its notes first, before anything else, and two of them
matter on a fresh machine:

- **`degraded: <term>`** — a runtime binding this host is *known* to lack or
  half-have. `task provider` is DEGRADED on a machine with no Todoist
  connector: `daily-task-manager` still installs, tasks are kept in your vault
  instead, and the skill says so every time it runs. Nothing is broken.
- **`unfilled placeholders`** — a value you have not given yet. The note names
  the file and every key in one line, and the run exits **nonzero**: an
  ADAPTER.md still carrying `${OWNER_TZ}` where your agent reads it is not a
  configured host. Fill them there, or re-run `make start` and answer the
  questions. `make start` reports this once, itself, and passes
  `--allow-unconfigured` to the installer so the same fact is not reported
  twice; use that flag yourself for a deliberately half-configured install.

A third case, **UNCONFIRMED**, is usually a refusal rather than a note: nobody
can attest the binding on this host, so a skill that depends on it is not
installed at all. Where the unattested term is only a *fallback* — the second
notification channel, say — it prints as a note instead and nothing is refused;
that is what `notification fallback \`agent inbox\` is UNCONFIRMED` on a fresh
machine is. [ONBOARDING.md](ONBOARDING.md) walks the whole first hour, including
what to read when one of these appears.

## Installing more skills

```sh
python3 tools/install_skill.py --runtime claude-code meal-planner   # one, by name
python3 tools/install_skill.py --runtime claude-code --all          # every eligible skill
python3 tools/install_skill.py --runtime claude-code --list         # what is installed
python3 tools/install_skill.py --runtime claude-code --check        # installed vs. this tree
python3 tools/install_skill.py --runtime claude-code --update       # bring them up to this tree
python3 tools/install_skill.py --help                               # the full usage doc
```

The installer renders the portable `SKILL.md` for one runtime: it emits that
adapter's frontmatter keys, appends the `## Runtime binding` trailer, copies the
supporting directories and the repository files the skill declares as inputs,
and writes a `.spike-os.json` stamp — which is what makes a directory ours to
overwrite and `--check` possible at all. It refuses a skill whose declared
runtimes exclude the target, a destination holding somebody else's skill, and a
skill depending on a term the adapter marks UNCONFIRMED. `--dry-run` prints what
a run would write and writes nothing. `--uninstall` removes stamped installs and
nothing else.

`--check` reports **drift** — a body edited in place, a supporting file that no
longer matches its digest, a file no install wrote, a stamp older than the
adapter, a declaration that no longer matches this tree. It is not a health
check: it says nothing about whether a skill works, only whether what is
installed is still what this repository says it should be.

`--update` is how drift is resolved without losing anything. Re-installing
replaces the whole directory; `--update` reads three states of every installed
file — the digest the stamp recorded, what is on disk now, and what this tree
renders — and rewrites only the files you have not touched and the repository
has changed. A file you edited, deleted, or added yourself is named instead,
with the diff of what would have replaced it and the `--overwrite` line that
would take it; that refusal exits nonzero and the run carries on to the next
skill. Each re-rendered skill prints what changed, from `git log` between the
stamp's commit and HEAD. Nothing is ever deleted. A stamp written before
per-file digests is refused rather than guessed at, and says which re-install
upgrades it.

What `--update` cannot clear is the drift it refuses to touch. A file you edited
stays drift until you take the repository's version (`--overwrite`) or re-install;
a file you added yourself is drift for as long as it is there, and no `--update`
will ever remove it — that is the point. `--check` will keep reporting both, which
is the honest reading of an install that is partly yours.

Two refusals `--overwrite` cannot take either, because they are checked after it
has had its say: a file whose name your filesystem treats as one the install
already holds (a re-install applies that rename; copy your copy out first), and
any path reached through a symlink you placed (remove the link, then re-run). The
run prints that on the file itself rather than offering a command that cannot
work.

`make stage-openclaw` stages every eligible skill into `dist/` for
[OpenClaw](docs/openclaw-handoff.md), the second runtime — a hosted agent on a
Railway volume rather than a CLI on your Mac. Its handoff note is also the
record of which bindings were checked against a live deployment, and when.

## Words this repository uses

| Term | What it means here |
| --- | --- |
| **runtime** | An agent the library installs into. Two exist: `claude-code` (the CLI on your machine) and `openclaw` (a hosted agent — see [docs/openclaw-handoff.md](docs/openclaw-handoff.md)). |
| **adapter** | One directory per runtime holding what that runtime can honestly do: `adapters/<runtime>/adapter.yaml` and the `ADAPTER.md` rendered from it into your home directory. Skills name runtime facts only through it. |
| **vocabulary term** | A backticked neutral name — `owner datastore`, `task provider`, `notification channel` — that a skill uses instead of a product name, and that the adapter binds to something real. The rule is [§R of the contract](contracts/skill-contract.md#r-runtime-vocabulary); the list is [adapters/vocabulary.yaml](adapters/vocabulary.yaml). |
| **UNCONFIRMED / DEGRADED** | An adapter's two ways of not being sure. UNCONFIRMED is ignorance — nobody has attested this binding, so a skill needing it is refused. DEGRADED is knowledge — it is absent or partial, the skill's own contract already says what it does without it, so it installs and discloses. |
| **rule ID** | A citation like `D1`, `M3`, `X2`. Every rule lives once, in [contracts/skill-contract.md](contracts/skill-contract.md), under a lettered section — **D**ependencies, **M**utation boundary, **P**rivacy, **S**afety, **F**reshness, **O**utput, e**X**ceptions, pro**V**enance, **R**untime vocabulary. A skill cites the ID rather than restating the rule. |
| **capability** | Something a skill does that reaches past reading, declared in its frontmatter (`capabilities: [datastore:write, notify:owner]`), from the closed enum of 21 in [contracts/capabilities.yaml](contracts/capabilities.yaml). Declaration is lint and adapter policy, never a sandbox. |
| **`activity/`** | The ledger namespace. Every mutating capability appends a record of what it did, with the readback, so a run can be audited after the fact against what was declared. |
| **namespace** | A place in your vault a skill may read or write — `profile`, `people`, `projects`, `activity`, `autonomy`. Declared per skill, defined in [contracts/datastore.md](contracts/datastore.md). |
| **gbrain** | The MCP server that indexes the vault on the author's host. It is one of three ordered ways in; Markdown is canonical, so the file itself is always the last, safe fallback. |
| **stamp** | The `.spike-os.json` written into every installed skill directory: name, version, commit, adapter version, and a sha256 per installed file. Without it a directory is not ours and the installer will not touch it; without the per-file digests `--update` cannot tell your edit from a stale render, and says so. |

Standing permission — "stop asking me every time" — is its own skill,
`skills/autonomy`, and its own contract under `autonomy/`; the newcomer path
does not need it.

## Where things are

```text
skills/              32 skill packages, each centred on SKILL.md
contracts/           The rules every skill follows, and the stores they name
adapters/            One directory per runtime: the vocabulary bindings and the rendered ADAPTER.md
catalog/             The inventory, the domains, the cohorts, the routing clusters, the generated index
evals/baseline.json  The committed behavioural + routing baseline
evals/reports/       Shareable benchmark summaries and the fixture-debt registers
evals/workspaces/    Local generated runs; gitignored
docs/                The related-work survey, the runtime inventory, the OpenClaw handoff
imports/             Pinned upstream material, unchanged
schemas/             Validation schemas
tools/               The bootstrap, the installer, the validator, the eval runner, the index builder
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
namespaces it reads and writes, and the capabilities it performs. The closed
capability enum is [contracts/capabilities.yaml](contracts/capabilities.yaml);
the namespaces are [contracts/datastore.md](contracts/datastore.md); the neutral
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

## Contributing

### The gate

```sh
make validate     # the unit tests, the repository validator, the citation check
```

Run it before opening or updating a pull request. It runs `make test` (a compile
pass over every tool and test, then `python3 -m unittest discover -s tests`),
then `tools/validate_repo.py`, `tools/check_citations.py`, and
`tools/build_index.py --check`. Without `make`, run those four commands
directly. `.github/workflows/validate.yml` calls the target itself, twice —
once on a stock Python and once with `jsonschema` installed, since the validator
takes a different path on each — so a gate added here is a gate CI runs.

`tools/validate_repo.py` composes the rule modules under `tools/validators/`:
frontmatter, structure, catalog, contracts, and evals. It checks the canonical
sections, the description rules and the launcher listing budget, catalog and
source parity, provenance artifacts, the declared namespaces and capabilities
against the contracts, the runtime binding for every adapter a skill claims, the
eval fixtures against `schemas/skill-evals.schema.json`, and the committed
baseline against the tree.

What the validator checks about capabilities is a **keyword scan, not an
understanding of intent**. `CAPABILITY_HINTS` maps body words — "publish",
"send", "delete", "schedule", "commit" — to the capabilities that would cover
them, and reports a skill that uses one without declaring it. Some rows also
require a context word in the same clause, because the verb alone is ambiguous:
"create" is `provider:write` only beside a `provider`, "notify" is `notify:owner`
only beside the `owner`. It reads a negation as governing the clause it sits in
rather than the whole sentence, so "never publishes — it hands the draft on"
scans the second clause; it still cannot tell a verb the skill performs from one
it quotes or routes elsewhere, and it misses any phrasing outside the list. So
the declaration is **lint, not a boundary**: nothing at run time stops a skill
taking a capability it never declared. What the declaration does buy is a
machine-readable claim — the installer refuses on it, `--check` re-derives the
hints from it, and the `activity/` ledger is auditable against it after the
fact. Emitting a `PreToolUse` hook from the declaration is the enforcement path,
and it is on the roadmap rather than in the repository.

`tools/check_citations.py` verifies that every `skills/<name>/SKILL.md:<line>`
anchor in `contracts/`, `adapters/`, and `docs/` still resolves to a body
statement; `--show` prints each anchor beside the line it lands on, which is the
audit to do after editing a skill.

### Evaluation

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

### Reviewing a candidate

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

The related-work survey grounding the design is in
[docs/related-work.md](docs/related-work.md); what each runtime can and cannot
attest is in [docs/runtime-adapter-inventory.md](docs/runtime-adapter-inventory.md).

The public remote is `spikeagent1/spike-skills`. Public releases exclude
credentials, private memory, raw conversations, and internal operational
weakness reports.
