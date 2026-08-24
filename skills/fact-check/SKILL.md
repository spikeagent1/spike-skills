---
name: "fact-check"
description: "Verify atomic claims with current claim-relative evidence and non-mutating audit defaults."
mutating: false
---

# Fact Check

Verify a frozen artifact claim by claim. An audit reports findings and proposed replacements; it edits the source only when the user explicitly authorizes correction or invokes a correction gate.

## Freeze and atomize
Record the exact artifact/version, verification time, audience, and scope. Split compound sentences into atomic falsifiable claims, including numbers, units, periods, attribution, causality, comparisons, quoted assertions, and factual premises inside forecasts.

For each claim record exact text span, subject, predicate, value/object, unit, geography/population, comparison set, as-of/effective date, and criticality. Clarify or mark material ambiguity before checking.

## Route to claim-relative authority
Choose evidence by claim type: official text for law; originating dataset and methodology for statistics; recording/transcript for quotes; filings or official records for company self-reports, labeled first-party; and original papers plus corrections/retractions and authoritative synthesis for research.

Search snippets and Wikipedia are discovery aids, not final evidence. Primary does not automatically mean reliable; assess directness, incentives, methodology, and scope.

## Temporal verification
For current/latest/still claims, verify the claim-as-of date with period-matched evidence. Distinguish event, announcement, publication, update, access, and effective dates. Use archived/versioned sources for historical state. Stale evidence cannot establish a current claim.

## Independence and counterevidence
Trace claims to evidence origin. Syndicated copies and reports derived from the same source count as one chain. Run an explicit counterevidence search for every material claim. One dispositive authoritative record may outweigh many derivative summaries. Present genuine disagreement rather than averaging it away.

## Internal data
Separate fidelity, independently re-derived from a different path, from external-world truth verified against external authority. A stored note proves what was recorded, not that a relationship or date is true. Personal memory is attributed evidence.

## Findings
Assign disposition as supported, contradicted, mixed/disputed, insufficient, or not-checkable. Assign confidence separately as high, medium, or low. Explain confidence through authority, directness, independence, completeness, and temporal fit.

For negative claims, state sources, query scope, and time range searched. Absence of discovery is not proof of absence.

## Reproducible citations
Map every material finding to source title, issuer/author, stable URL or identifier, publication/effective/update date, accessed date, exact locator, and supporting or contradicting evidence. Never cite a bare search result.

## Gate and corrections
Gate by claim criticality, not aggregate percentages. No contradicted or insufficient critical claim may ship unqualified. Provide corrected or qualified replacement text. Do not mutate the artifact unless authorized; otherwise return a proposed patch.

## Report
For each claim include span, normalized claim, criticality, disposition, confidence, evidence for and against, source lineage, temporal fit, and proposed correction. Summarize unresolved critical claims and publication safety.

## Failure conditions
Fail review if compound claims receive one verdict; stale evidence verifies current state; syndicated sources count as independent; brain data becomes external truth; disposition/confidence are conflated; counterevidence is absent; citations lack locators; an unresolved critical claim passes through an average score; or an audit mutates without authority.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.
