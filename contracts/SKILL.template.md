---
name: <kebab-name>
description: "Use when <trigger phrasings and situations>. Not for <sibling scope> (see `<sibling-skill>`)."
license: <SPDX id — only for an adapted skill, matching catalog/sources.yaml>
compatibility: <optional; runtime requirements in prose, omit when none>
allowed-tools: <optional; omit unless the skill genuinely needs a tool allowlist>
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: []
    writes_to: []
    effects: []
---

# <Title>

<!-- These six top-level keys are the only ones agentskills.io allows; drop
     license, compatibility, and allowed-tools when they do not apply.
     Under metadata.spike-os: version is semver and matches catalog/approved.yaml;
     runtime lists adapters under adapters/; reads_from and writes_to name
     namespaces from contracts/datastore.md; effects names entries from
     contracts/capabilities.yaml. Description: third person, <=300 chars, opens
     with "Use when", names no principal or runtime, and carries one negative
     clause naming the sibling skill. -->

## Overview

<!-- Mandatory. One to three sentences: what the skill produces and the single
     governing principle. No history, no restatement of the shared contract. -->

## When to use

<!-- Mandatory. Bullets of triggers — phrasings, symptoms, situations — using the
     same vocabulary as the description, expanded. -->

## When not to use

<!-- Mandatory. One routing line per bullet, of the form "<observable
     condition> -> use <sibling-skill>". Every cluster sibling in
     catalog/routing.yaml appears; out-of-scope refusals cite a rule ID
     such as (S1). -->

## Inputs

<!-- Mandatory. A table `| Input | Required | If missing |`, then one bold
     Dependencies: line naming connectors, scripts, and env vars, or stating
     "none beyond the contract" (D1). -->

| Input | Required | If missing |
|---|---|---|
| <input> | yes/no | <fail-closed or ask> |

**Dependencies:** none beyond the contract.

## Workflow

<!-- Mandatory. One numbered list. Sub-procedures become H3s or a linked
     references/<file>.md, one level deep and linked from here. One numbered
     step is the produce-anyway clause: the skill produces its deliverable in
     this turn from what the request already carries, marking the facts it had
     to assume, and previews any mutation by showing its exact text here. A
     marked slot stands in for a missing fact — a metric, a name, a date, a link
     — never for the substance of a draft, a reply, or an argument, which is
     written from the request's own framing and revised when the fact arrives; a
     response whose substantive fields are all slots is a deferral (X6). -->

## Output contract

<!-- Mandatory. What the response contains, in order, with the exact state
     vocabulary the skill reports (O3). Opens by restating the produce-anyway
     clause: what this turn delivers, and which fields may carry a marked slot
     (X6). -->

## Worked example

<!-- Optional. One request condensed to the shape of the response. No dates, no
     session references, no personal values. -->

## Sources and freshness

<!-- Optional. Only freshness rules specific to this skill; F1-F4 are generic. -->

## Privacy and mutations

<!-- Optional. Read-versus-mutate classification for this skill, and any standing
     authority it claims, named here and nowhere else (M5). P1-P6 are generic. -->

## Safety boundaries

<!-- Optional. Domain-specific hard limits and the escalation path. S1-S4 are
     generic. -->

## Failure conditions

<!-- Mandatory. Runtime stop conditions specific to this skill, fail-closed.
     X1-X6 are generic. -->

## Common mistakes

<!-- Optional. A table `| Mistake | Why wrong | Do instead |` drawn from baseline
     eval failures and any retired reviewer rubric. -->

## Contract

<!-- Mandatory. The link and one Provenance line, nothing else. For an adapted
     skill replace the line below with:
     - Provenance: adapted from <publisher>/<slug> <version> (see catalog/sources.yaml) -->

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
