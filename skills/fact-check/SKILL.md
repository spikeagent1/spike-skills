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

## Operational failure conditions
Fail review if compound claims receive one verdict; stale evidence verifies current state; syndicated sources count as independent; brain data becomes external truth; disposition/confidence are conflated; counterevidence is absent; citations lack locators; an unresolved critical claim passes through an average score; or an audit mutates without authority.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.

## When to use
Use this skill to verify factual claims, separate claims into checkable units, compare evidence, and produce cited dispositions with uncertainty.

## When not to use
Do not use it for broad literature synthesis, opinion adjudication, legal/medical/financial advice, or claims whose answer depends on private inaccessible evidence unless the limitation can be stated.

## Required inputs
Required inputs are the claim or document, target jurisdiction/domain if relevant, acceptable source types, freshness requirement, and desired output depth. If the claim is ambiguous, decompose and ask only for context needed to determine what is being checked.

## Optional inputs
Optional inputs include preferred citation style, confidence scale, source exclusions, language constraints, and deadline. Missing optional inputs default to concise cited findings with explicit uncertainty.

## Workflow
1. Break the request into atomic claims and identify the largest consequential measure.
2. Determine freshness needs and authoritative source hierarchy.
3. Search or inspect primary/current sources first; use secondary sources only as leads or context.
4. Seek counterevidence for each material claim.
5. Record source dates, access dates, jurisdiction, and ambiguity.
6. Assign disposition and confidence separately.
7. Return corrections and what evidence would change the result.

## Sources and freshness
Use primary sources, official records, original papers, standards, filings, or direct artifact evidence whenever possible. Browse or query current sources for claims that could have changed, and include absolute dates for time-sensitive claims.

## Privacy and mutations
Fact-checking is read-only unless the user separately asks to edit a document or publish a correction. Do not expose private source material in the public answer; cite private evidence only as authorized and with minimal detail.

## Safety boundaries
Do not fabricate sources, overstate certainty, or collapse announcement/submission/effective dates. Escalate high-stakes professional advice to qualified experts and frame findings as evidence review, not final professional judgment.

## Output contract
Return atomic claims, verdicts, confidence, citations with dates, reasoning summary, counterevidence, corrections, unresolved questions, and freshness limits.

## Failure conditions
Fail or mark inconclusive when authoritative evidence is unavailable, the claim is too ambiguous to check, sources conflict without resolution, current-source access fails for time-sensitive facts, or privacy constraints prevent necessary evidence use.

## Worked example
For "check whether rule X took effect yesterday," identify jurisdiction, verify official rule text and effective date, distinguish proposal/publication/effective dates, and answer using absolute dates.
