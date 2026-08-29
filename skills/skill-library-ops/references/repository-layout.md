# Repository layout

What each tracked directory holds, and what may never enter one.

## Source

- `skills/<name>/SKILL.md` — the skill itself, one directory per skill, plus
  optional `references/`, `scripts/`, `templates/`, and `assets/`.
- `skills/<name>/examples/evals.json` — the behavioral cases, synthetic only.
- `skills/<name>/routing-eval.jsonl` — the routing intents: at least two whose
  `expected_skill` is this skill, at least one `null`, and at least one
  `ambiguous_with` naming a cluster sibling.

## Contracts

- `contracts/skill-contract.md` — the D/M/P/S/F/O/X/V/R rules every skill cites
  by ID instead of restating.
- `contracts/SKILL.template.md` — the canonical section skeleton.
- `contracts/capabilities.yaml` — the closed effect enum and each effect's
  approval floor.
- `contracts/datastore.{md,yaml}` — the namespaces, the record envelope, the
  verbs, and the closed `effect_state` enum.
- `contracts/notifications.md`, `contracts/sync.md` — the owner-notification
  and provider-sync contracts.

## Adapters

- `adapters/vocabulary.yaml` — the neutral runtime terms a skill is allowed to
  name.
- `adapters/<runtime>/adapter.yaml` — what each term resolves to in that
  runtime, validated against `adapters/adapter.schema.json`.

## Catalog

- `catalog/approved.yaml` — the inventory: classification, paths, status,
  cohort, `contract_version`, `version`.
- `catalog/sources.yaml` — provenance: upstream, publisher, license,
  `license_source`, `local_modifications`, and `upstream_version` where a
  rewrite has moved `version` off the upstream number.
- `catalog/cohorts.yaml` — the cohorts and their acceptance criteria; this file
  is the owner-selected order, and no skill restates it.
- `catalog/routing.yaml`, `catalog/domains.yaml` — the routing clusters and the
  released/next split.
- `catalog/provenance/<skill>/` — the upstream install artifacts (`_meta.json`,
  `origin.json`) for an adapted package, never in the skill directory (V3).

## Evaluation

- `evals/baseline.json` — the committed RED numbers: pass rates, assertion
  classes, routing counts, and the run each came from.
- `evals/reports/` — shareable dated summaries, committed.
- `evals/workspaces/` — generated run artifacts, git-ignored, never committed.
- `schemas/` — the catalog and eval JSON schemas.
- `tools/` — the deterministic validators and the eval runner.

## Never tracked here

Owner conversations, visitor identity, credentials or secret values, production
runtime state, durable memory, generated workspaces, and caches. A fixture is
synthetic or it does not land (V1, P6).
