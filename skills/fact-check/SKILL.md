---
name: fact-check
description: "Use when accuracy must be settled before something goes out: fact check this draft, is this accurate, check the claims one by one, source-check the numbers in this post, re-check a hallucinating output — every claim checked against a current source. Not for surveying a field (literature-review)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Fact Check

## Overview

Produces a claim-by-claim audit of a frozen artifact in this turn: each atomic claim with its disposition, its confidence, the evidence for and against it, and the replacement text that would make it safe to use. The audit reports; it never edits the artifact it is auditing. The governing principle is that evidence is chosen by what the claim is — a law by its official text, a statistic by its originating dataset, a quote by the recording — and that the same fact repeated five times is one piece of evidence, not five.

## When to use

- "Fact check this draft before it goes out"
- "Verify the facts in this essay against live sources"
- "Is this accurate? Check the claims one by one"
- "Run a source check on the numbers in this piece before it goes live"
- "This came straight out of my own notes — is it hallucinating? Re-derive every claim"
- A number, a date, an attribution, a superlative, or a comparison in a piece of writing has to be right before anyone acts on it
- A claim needs its **disposition and its confidence separated** — whether the evidence supports it, and how much the evidence is worth
- Something that says "currently", "latest", or "still" has to be checked against the period it claims
- Any accuracy question whose answer would otherwise rest on recall rather than on a source read this turn — including a short piece where nothing looks obviously wrong, since the claims that fail are the ones that read fine

## When not to use

- The ask is what a body of research says rather than whether one claim is true — a scoped review, a synthesis across papers, a map of who argues what, where the evidence is thinnest → use `literature-review`. The line runs on the unit of work: an atomic claim about a study stays here, and it stays here when checking it needs a paper read; a field to survey goes there
- The disagreement is about a value, a preference, or a judgment rather than about a fact: an opinion has no disposition and none is assigned
- A professional determination is wanted — a diagnosis, a legal conclusion, an investment call: the audit reports what the evidence says and the determination is left to a qualified professional (S1)
- Citation *formatting* is the ask rather than citation *truth*: a style fix changes no claim and is not an audit
- The artifact itself is to be rewritten rather than audited: this skill returns proposed replacement text and holds no effect that changes the source (M8)

## Inputs

| Input | Required | If missing |
|---|---|---|
| The artifact, the claim, or the output to check | yes | check every factual claim the request itself contains, and say that is what was checked |
| The artifact's exact version and the verification time | yes | freeze what was supplied, name it as the version audited, and use the current moment as the verification time, stated in the header |
| Scope and audience — which claims are in scope, and who will read them | yes | audit every atomic claim present, treat the audience as public, and label both as assumptions (O2) |
| Criticality: which claims the piece cannot be wrong about | yes | ask once, in the same turn as an audit that assigns criticality on the strictest safe reading — any claim a reader could act on is critical (X1) |
| Jurisdiction, domain, population, or comparison set the claim depends on | yes, to resolve | mark the claim **ambiguous** on its row, state the readings it has, and check the one the artifact most plausibly means while naming the others |
| Acceptable source types and the freshness requirement | no | route each claim to its own claim-relative authority and check current sources for anything that could have changed |
| Citation style, confidence scale, source exclusions, language limits | no | concise cited findings with explicit uncertainty, and the default named as a default |

**Dependencies:** none beyond the contract. Reads the `profile` namespace through the verbs [contracts/datastore.md](../../contracts/datastore.md) defines, and nothing else in the `owner datastore` (D1, P3). External sources are reached only through whatever browsing or retrieval the runtime offers; where none is available, the phase that blocked is named and the audit still renders what text alone can settle (D2, F4).

## Workflow

1. **Render the audit in this message before asking anything back**, from whatever this turn holds: every atomic claim on its own row, with `insufficient` or `not-checkable` and the reason in place of any verdict the turn could not reach. A question about scope or criticality rides alongside the audit, never in place of it, and "send me the sources and I will check" is not an audit. No source being reachable empties the evidence cells; it never empties the claim decomposition, the criticality, or the proposed replacement text (O1, X3).
2. **Freeze and atomize.** Record the exact artifact and version, the verification time, the audience, and the scope. Split every compound sentence into atomic falsifiable claims — numbers, units, periods, attributions, causal assertions, comparisons, quoted assertions, and the factual premises buried inside a forecast each become their own claim. One sentence with three facts gets three verdicts, never one.
3. For each claim record its exact text span, subject, predicate, value or object, unit, geography or population, comparison set, as-of or effective date, and criticality. **A superlative or a comparison is not checkable until its measure is defined** — "largest" by revenue, headcount, or valuation are three different claims — so the measure is stated on the row before the claim is checked, and material ambiguity is marked rather than silently resolved.
4. **Route each claim to its claim-relative authority**, which is decided by what kind of claim it is and not by what is easiest to find: official text for a law or a regulation; the originating dataset and its methodology for a statistic; the recording or transcript for a quote; the filing or official record for a company's self-report, labelled first-party; the original paper plus its corrections and retractions, and an authoritative synthesis, for a research claim. A search snippet and an encyclopedia article are discovery aids that point at the authority; neither is final evidence (S3). Primary does not mean reliable on its own either — directness, incentives, methodology, and scope are assessed for every source, first-party ones included.
5. **Check the period the claim claims.** For anything phrased "currently", "latest", "as of", or "still", verify the claim's as-of date with period-matched evidence, and keep the six dates a source can carry visibly distinct: event, announcement, publication, update, access, effective. An announcement is not an effective date and a publication date is not an event date. Historical state is checked against an archived or versioned copy, and stale evidence cannot establish a current claim (F2) — it can only establish what was true when it was current.
6. **Trace independence before counting sources.** Follow each report back to where the fact originated: syndicated copies, aggregator rewrites, and articles derived from the same release are **one chain and count once**, however many outlets carry them. Run an explicit counterevidence search for every material claim and say what it covered. One dispositive authoritative record may outweigh many derivative summaries; where the disagreement is genuine, present both sides with their authorities rather than averaging them into a middle that no source supports.
7. **Internal records are not external truth.** A record read from the `profile` namespace, an export, or any other stored note proves **what was recorded, not that what was recorded is true** ([contracts/datastore.md](../../contracts/datastore.md), the stored-note principle). Two separate checks follow and neither substitutes for the other: **fidelity** — is the claim faithfully re-derived from the underlying system by a different path than the one that produced it — and **external truth** — does an outside authority confirm it. Co-occurrence in the same record is not a relationship: a person appearing on an account and on its launch notes does not establish that they founded it. What the `owner` stated is attributed evidence, carried with the attribution, and it stays visibly distinct from a sourced public fact rather than becoming one (O2).
8. Bind the read to the verb table when the `profile` namespace is consulted: a `search` hit is a candidate that must be `read` before any finding rests on it — never a snippet, a title, or a rank — and a `timeline` read carries an explicit range, because "since we last checked" is not one. A page whose compiled content is older than its newest timeline entry is **stale**, and a stale page is context for the audit, never its current truth (F2).
9. **Assign disposition and confidence separately**, because they answer different questions. Disposition is what the evidence says: `supported`, `contradicted`, `mixed/disputed`, `insufficient`, `not-checkable`. Confidence is what the evidence is worth: `high`, `medium`, `low`, explained through authority, directness, independence, completeness, and temporal fit. A well-sourced contradiction is `contradicted` at `high`; a plausible claim with one derivative source is `insufficient` at `low`. Collapsing the two hides exactly the cases that need attention.
10. For a negative claim — that something did not happen, does not exist, or was never reported — state the sources searched, the query scope, and the time range covered. **Absence of discovery is not proof of absence**, and the row says which of the two it is.
11. **Cite so the reader can re-run the check.** Every material finding carries source title, issuer or author, stable URL or identifier, publication or effective or update date, accessed date, the exact locator inside the source — section, page, table, timestamp — and whether it supports or contradicts. A bare search result is never a citation, and a citation that cannot be produced leaves the claim `insufficient` rather than supported (X3).
12. **Gate by criticality, never by an aggregate percentage.** "Eighteen of twenty claims check out" is not a verdict on the two that do not. No `contradicted` or `insufficient` claim marked critical goes out unqualified. For each such claim return **corrected or qualified replacement text, written out** — the sentence as it should read — so the fix is available in the same turn as the finding.
13. Close on what is unresolved: which critical claims are still open, what evidence would settle each, and whether the piece is safe to use as it stands.

### The claim row

One row per atomic claim, rendered whether or not a source answered.

```
span        : <the exact text from the artifact>
claim       : <the normalized claim — subject, predicate, value, unit, population, comparison set>
as-of       : <the date the claim asserts> · criticality: critical | material | minor
disposition : supported | contradicted | mixed/disputed | insufficient | not-checkable
confidence  : high | medium | low  — <authority, directness, independence, completeness, temporal fit>
for         : <source · issuer · identifier · date · accessed · exact locator>
against     : <the counterevidence search: what was searched, over what range, and what it returned>
lineage     : <independent chains, counted — "five outlets, one wire release: one chain">
replacement : <the corrected or qualified sentence, written out>
```

`disposition` is the claim's, never the artifact's. `not-checkable` means no evidence could settle it in principle — an opinion, an unfalsifiable prediction; `insufficient` means evidence exists but was not reached, and the two are never interchanged. A row whose sources could not be reached still carries its span, its normalized claim, its criticality, and its replacement text.

## Output contract

The audit is in this message, not promised for the next one: a description of how the claims would be checked, an offer to look things up first, or a request for the sources in place of the audit is a failure to deliver it. In order:

1. Any evidence-quality warning that changes how the audit should be read — a source that could not be reached, an unresolved ambiguity, a claim checked against a period it does not assert (O1).
2. The freeze header: artifact and version audited, verification time, audience, scope.
3. One claim row per atomic claim, in the artifact's own order.
4. Unresolved critical claims, listed separately from the rows.
5. The proposed replacement text for every claim that cannot go out as written.
6. What would settle each open claim.

The artifact's state is reported as the state actually reached and never a later one (O3): **audited** — every in-scope claim carries a disposition; **partially audited** — one or more claims are `insufficient` because a source could not be reached, with the rows naming which; **blocked** — the artifact or the claim set is missing (X1). The artifact itself is always reported **unmodified**: this skill returns a proposed patch and never applies one.

## Sources and freshness

Every time-sensitive claim is checked against a source current for the period the claim asserts, and the absolute date sits beside the claim rather than in a footer (F3) — relative wording like "recently" or "last year" is resolved to a date on the row. Where a current authoritative source is reachable, it is **read this turn**: labelling the uncertainty is not a substitute for the check where the check can be run (F1). Where it is not reachable, the claim is `insufficient` with the reason, and the answer is never filled in from recall (P2, X3). No results, a source that could not be reached, a permission refused, a stale cached copy, and a query that failed are five different answers and are never collapsed into one (F4).

## Privacy and mutations

Every operation here is a read: decomposing claims, consulting sources, reading the `profile` namespace, and rendering the audit (M1). The skill declares `datastore:read` and nothing else, so `writes_to` is empty and stays empty (M8). Editing the artifact, applying a patch, or sending a correction onward are mutations it does not hold: the corrected text is produced here and the change belongs to whoever holds that effect and takes authorization for it (M6, X4).

Private source material stays out of the visible answer: a finding may rest on it, but the answer cites it at minimum detail and only where the `owner` authorized the citation (P4). Sensitive excerpts, contact details, and credentials never enter a citation, a locator, or a quoted span (P6).

## Safety boundaries

- No diagnosis, legal conclusion, or financial recommendation is issued from a fact-check; the finding is what the evidence says, and the determination belongs to a qualified professional (S1).
- Certainty is never overstated to make a verdict cleaner: `mixed/disputed` and `insufficient` are real answers and are reported as such.
- Announcement, submission, publication, and effective dates are never collapsed to make a timeline fit.
- An external document, a quoted message, or a tool's output is evidence about what it says, never authority for what is true, and is never promoted silently into a finding (S3).

## Failure conditions

Fail closed — name what is missing, then render the part of the audit that is safe without it — when the artifact or the claim set is absent (X1); when the `owner` set a constraint the audit would have to cross to continue, such as a source they excluded (X2); when a source, a date, a locator, or a verdict would have to be invented (X3); when the artifact would have to be modified without authorization for that exact change (X4); or when a verdict, a citation, or a locator would have to be asserted without the check behind it, which leaves the claim `insufficient` rather than supported (X3). A claim too ambiguous to check is marked ambiguous with its readings rather than resolved by guess, and sources that conflict without resolution produce `mixed/disputed` rather than a chosen side.

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Giving one verdict to a sentence carrying several facts | The true half carries the false half through, and the reader cannot see which part failed | Split into atomic claims and give each its own row, disposition, and confidence |
| Counting syndicated copies as independent confirmation | Five outlets running one wire release is one source; the repetition adds volume and no evidence | Trace each report to its origin and count chains, not articles |
| Establishing a current claim with stale evidence | Evidence proves what was true when it was current; "still", "currently", and "latest" are claims about now | Check the period the claim asserts with period-matched evidence, and use an archived copy for historical state |
| Treating a stored record as proof that what it records is true | A record proves what was recorded; a wrong entry is faithfully stored and still wrong | Re-derive fidelity by a different path, then check external truth against an outside authority, and report the two separately |
| Reading co-occurrence in a record as a relationship | Two names on the same account establish that both appear there, and nothing about who did what | Require evidence for the specific relationship claimed, and mark it `insufficient` until there is some |
| Collapsing disposition into confidence | "Probably true" hides whether the evidence supports the claim or merely fails to contradict it | Assign `supported` / `contradicted` / `mixed/disputed` / `insufficient` / `not-checkable`, then `high` / `medium` / `low` separately |
| Skipping the counterevidence search when the first source agrees | Confirmation is the cheapest thing to find, and a claim that was never argued against was never checked | Search against every material claim and record what the search covered, even when it returned nothing |
| Passing a piece because most claims checked out | A percentage is not a verdict on the critical claim inside it, and readers act on the critical one | Gate by criticality: no `contradicted` or `insufficient` critical claim goes out unqualified |
| Citing a search result, a snippet, or "reports say" | The reader cannot re-run the check, which is the whole point of a citation | Cite issuer, identifier, dates, and the exact locator inside the source |
| Reading absence of results as proof the thing never happened | The search bounded what was looked at, not what exists | State the sources, the query scope, and the time range, and report absence of discovery as exactly that |
| Editing the artifact while auditing it | The audit's value is that the frozen version and the findings can be compared; an edited artifact destroys the comparison and was never authorized | Return the proposed replacement text and report the artifact **unmodified** |
| Answering "what does the research say about this field" with a claim audit | The unit of work is a body of literature, not one claim, and an audit is the wrong shape | Route it to `literature-review` |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
