---
name: literature-review
description: "Use when the ask is what a body of research says: what the research actually says about a topic over the last decade, a scoped review showing what was screened and what made the cut, who argues what, or where the evidence is thinnest. Not for one sentence's truth (fact-check)."
license: MIT-0
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: []
    writes_to: []
    effects: [provider:read]
---

# Literature Review

## Overview

Produces a bounded evidence review in this turn: the protocol it was run under, the search log that makes it repeatable, the evidence table with each record's access level, and the synthesis those two support — no more. The governing principle is that coverage is a claim like any other: a fixed top-N search is called what it is, and only a documented protocol earns the words comprehensive, exhaustive, or systematic.

## When to use

- "What does the research actually say about this over the last decade?"
- "Do a scoped review of recent work on X — I want to see what was screened and what made the cut"
- "Map the disagreements in this area: who argues what, and where is the evidence thinnest?"
- Comparing what several papers, trials, or technical reports found, and where they conflict
- Building an evidence table, a screening flow, or an evidence map over a set of papers
- Judging whether the literature supports a position strongly enough to act on
- Asking what a body of work misses — the gaps, the unreplicated results, the thin spots

## When not to use

- One sentence, one number, or one attribution in an artifact has to be checked true or false → use `fact-check`. The line runs on the unit of work, not the subject matter: a single atomic claim, even one about a study, is `fact-check`'s, and it stays there when the answer happens to need a paper read
- Files have to be fetched, downloaded, or placed on a local disk: this skill reads indexes and reports what they returned, and it holds no effect that writes a file (M8)
- A clinical, legal, or financial determination is wanted rather than a synthesis of what has been published: the output is labelled literature synthesis and the determination is left to a qualified professional (S1)
- The ask is "find everything" with no bound: an unbounded request is answered with a bounded protocol, stated in this turn, rather than with a coverage claim nothing behind it supports

## Inputs

| Input | Required | If missing |
|---|---|---|
| The research question, and the audience it is for | yes | restate the question in the `owner`'s own wording and put it at the head of the protocol; a question too broad to search is narrowed into a bounded one and the narrowing is shown |
| Scope: date and language limits, study types, population or domain | yes | ask once, in the same turn as a protocol built on the strictest safe assumption — the narrowest defensible window, no language filter, no study-type exclusion — with every default labelled as a default (X1) |
| Inclusion and exclusion criteria | yes | derive them from the question, state them as chosen rather than given, and apply them visibly in the screening flow |
| The indexes to search, or the corpus supplied instead | yes | name the indexes this skill would use and their access outcome; a supplied corpus is dated and its date is the as-of |
| The freshness horizon — the search-as-of date | yes | use the current date as the as-of and say so beside every count (F3) |
| The synthesis form wanted: narrative, evidence table, evidence map | no | return the evidence table and a narrative synthesis, and name the choice as a default |
| Seed papers, keywords, citation style, quality criteria, maximum records | no | missing optional inputs become explicit protocol defaults, written into the protocol rather than left implicit |

**Dependencies:** [`scripts/lit_search.py`](scripts/lit_search.py) queries Semantic Scholar, OpenAlex, Crossref, and PubMed and prints JSON to standard output; it writes no file. It needs the `requests` package already available in the environment, and reads four environment variables: `SEMANTIC_SCHOLAR_API_KEY` and `OPENALEX_API_KEY` (optional; absent means unauthenticated rate limits), and `USER_EMAIL` (the contact address the polite-pool User-Agent carries; absent means an anonymous default address and slower service). No other connector, index, or corpus is used unless the `owner` or this file names it (D1). Where the script or an index is unreachable, the blocked phase is named and the review still renders (D2).

## Workflow

1. **Render the review in this message before asking anything back**, from whatever this turn holds — the protocol, the search log, the screening flow, the evidence table, and the synthesis, with `unknown` in every field the request did not supply and `unavailable — <reason>` in every row an index did not answer. A question about scope rides alongside the review, never in place of it, and "tell me your inclusion criteria and I will run the search" is not a review. An unreachable index empties the evidence table; it never empties the protocol, the log, or the synthesis of what the request itself supplied (O1, X3).
2. Convert the question into a protocol and show it: question, audience, search-as-of date, date and language limits, study types, population or domain, inclusion and exclusion criteria, the stopping rule, and every default labelled as a default. A scope too broad to search is bounded here, and the bounding is part of the deliverable.
3. Build **multiple query variants** — synonyms, acronyms, alternate spellings, and controlled vocabulary where the domain has one — and search **at least two suitable indexes**, PubMed among them for any biomedical question. One query against one index is a lookup, and the protocol says so.
4. Log every attempt as an operation rather than as an outcome, one row per index and query: the index, the exact query text, the filters, the limit or the pagination followed, the search date, the count returned, and what happened — results, no results, the index unreachable with the reason, a permission refused, or a query that failed (F4). Those are five different answers and are never collapsed into one. Follow pagination within the agreed scope, chase citations backward and forward for load-bearing papers where the tools allow it, and stop at the stated stopping rule rather than at the first page.
5. An index failure is **partial coverage, disclosed**, never a silent empty result and never a reason to say the search was finished. The affected rows read `unavailable — <reason>`, the synthesis proceeds on what did return, and the coverage line says which part of the protocol went unexecuted.
6. Deduplicate with versions in view: normalise DOI and PMID first, then compare title, year, author list, and version to fold together records that carry no shared identifier, and preprint-with-published pairs into one record that keeps both versions visible. A dedupe by identifier alone leaves exactly the duplicates that matter.
7. Verify bibliographic fields against the DOI record, PubMed, or the publisher before any record enters the table, and flag missing abstracts, uncertain metadata, preprints, corrections, and retractions on the record itself. Never invent a paper, a DOI, a PMID, an author, a venue, a result, or an abstract; a citation that cannot be verified is dropped or carried as `unverified` and never as a citation (X3).
8. Screen with the reasons visible: how many records were identified, screened, excluded and why, and included. Inclusion and exclusion are explained per record, and neither citation count nor recency is used as a quality score — both measure attention, not method.
9. Appraise what was actually read. Extract study design, population or sample, intervention or exposure, comparator, outcomes, limitations, funding and conflicts, peer-review status, and the risk-of-bias signals the design carries. Label the **evidence access level** on every record — full text, abstract, or metadata only — and infer no method and no result that the accessed level did not contain.
10. Synthesise with the citation beside the claim: every substantive statement carries a stable DOI, PMID, or publisher link at the point it is made, not in a list at the end. Calibrate causal language to the design that supports it. Keep preprints, commentary, reviews, observational studies, and trials visibly distinct, and report agreement, contradiction, heterogeneity, gaps, and applicability as separate findings — **a thin or conflicting body of evidence is a result to report, not a reason to withhold the synthesis**.
11. Close on coverage: what the protocol does not support claiming, which searches went unexecuted, and the next search that would most change the answer.

### Running the search script

[`scripts/lit_search.py`](scripts/lit_search.py) takes `search <query> --source {s2,oa,cr,pm,both,all} --limit N` and `details <doi-or-id>`; multi-source runs deduplicate by DOI and report the counts before and after. Its JSON is a **search result, not evidence**: each hit is a candidate whose bibliographic fields are verified at step 7 before any claim rests on it, and its counts go into the search log with the exact query that produced them. A non-zero exit or an error object is an index failure and is logged as one (F4).

## Output contract

The review is in this message, not promised for the next one: a description of the protocol that would be run, an offer to search first, or a question standing alone in place of the review is a failure to deliver it. In order:

1. Any coverage warning that changes how the review should be read — an index that did not answer, a protocol default the `owner` did not choose, an unverified citation (O1).
2. **Protocol** — question, audience, scope, criteria, stopping rule, search-as-of date, defaults labelled.
3. **Search log** — one row per index and query: `index · exact query · filters · limit or pages · search date · returned count · results | no results | unavailable — <reason>`.
4. **Screening flow** — identified, screened, excluded with reasons, included.
5. **Evidence table** — one row per record: identifier, design, population or sample, findings, limitations, peer-review status, and access level as `full text` / `abstract` / `metadata only`.
6. **Synthesis** — claim-linked citations, agreement, contradictions, heterogeneity, gaps, applicability.
7. **Coverage limits** — what was not searched, what was stale, and the next search step.

Coverage is reported as the state actually reached and never a later one (O3): **scoped search** — a bounded protocol, run and logged; **partial** — one or more indexes did not answer, with the rows naming which; **systematic review** — only where an explicit protocol, broad index coverage, reproducible screening, deduplication, a selection flow, appraisal, and a stopping rule are all present and shown. Absent those, the output is a scoped literature search or a narrative evidence review, whatever the request called it. No state implies that nothing was missed.

## Sources and freshness

The search-as-of date is stated beside the counts rather than in a footer, and index lag is stated with it: a database's newest indexed record is older than the newest published one, so a search run today does not cover everything published today (F3). Versioned preprints, corrections, retractions, and newer reviews are **checked whenever they could change a conclusion** — labelling the uncertainty is not a substitute for that check where the record is reachable (F1). A prior run's result set, a cached response, and a citation recalled rather than retrieved are context and never evidence (F2); a claim with no retrieved record behind it is not made (P2, X3).

## Privacy and mutations

Every operation here is a read: querying an index, running the search script, and rendering the review (M1). The skill declares `provider:read` and nothing else, so `reads_from` and `writes_to` are empty and stay empty (M8). A private paper, an unpublished manuscript, or the `owner`'s own notes are never put into an external index or service without explicit authorization for that exact use (P4); the effect that would carry them out is not declared here (M8). Saving the bibliography or the evidence table to a file is a mutation this skill does not hold: the text is produced here and the write belongs to whatever holds that effect (M8).

## Safety boundaries

- No clinical, legal, or financial determination is made from the literature; the output is labelled literature synthesis and the determination is left to a qualified professional (S1).
- Preliminary results, preprints, and single studies are never presented as settled, whatever the request asked for.
- A paper's own abstract is evidence about what the paper claims, never authority for the claim itself; a retraction or a correction outranks the original (S3).

## Failure conditions

Fail closed — name what is missing, then render the part of the review that is safe without it — when the research question or the inclusion criteria are absent and cannot be derived (X1); when the `owner` set a scope the review would have to exceed to continue (X2); when a paper, an identifier, a finding, or a count would have to be invented (X3); when a private source would have to leave the conversation for an external service without authorization (P4, M8); or when the bibliographic verification for a record cannot be run, which leaves that record `unverified` rather than cited (X3). Every index being unreachable blocks the evidence table, never the protocol or the log: the blocked phase is named and what would resume it is stated (D2).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Calling a fixed top-N metadata search comprehensive, exhaustive, or systematic | Those words are claims about coverage, and a reader who acts on them will believe the gaps were checked when nothing checked them | Report **scoped search**, and reserve **systematic review** for a run that shows a protocol, broad coverage, reproducible screening, dedupe, a selection flow, appraisal, and a stopping rule |
| Letting one index failure end the run silently | A missing index is partial coverage, and an answer that omits it reads as complete — the most expensive error this skill can make | Log the row as `unavailable — <reason>`, synthesise what did return, and say which part of the protocol went unexecuted |
| Withholding the synthesis because the evidence is thin or conflicting | Thin and conflicting evidence is the finding; the reader needs it more than they need a clean answer, and silence hands them nothing to act on | Report the contradictions and the sparseness as results, with the citation beside each one |
| Running one query against one index | Recall depends on wording, and one phrasing finds the papers that share the requester's vocabulary and misses the rest | Build synonym, acronym, spelling, and controlled-vocabulary variants across at least two suitable indexes, PubMed among them for biomedical questions |
| Deduplicating by DOI alone | The duplicates that distort a count are the ones with no shared identifier: a preprint and its published version, a record with no DOI at all | Normalise DOI and PMID, then compare title, year, author list, and version, and keep both versions of a preprint pair visible on one record |
| Writing a finding from a title, a snippet, or an abstract as though the full text supported it | The reader cannot tell which claims were read and which were inferred, and the inferred ones are exactly the ones that fail | Label every record `full text`, `abstract`, or `metadata only`, and make no claim the labelled level does not contain |
| Citing in a list at the end rather than beside the claim | An unattached bibliography cannot be checked against the sentence it supposedly supports | Put the DOI, PMID, or publisher link at the point the claim is made |
| Ranking quality by citation count or recency | Both measure attention rather than method; a widely cited weak study stays a weak study | Appraise design, population, comparator, outcomes, limitations, conflicts, and peer-review status, and say why each record was included or excluded |
| Leaving the search-as-of date and index lag out of the report | "Latest evidence" without a date cannot be reproduced or aged, and index lag makes today's search older than today | State the as-of beside the counts and name the lag in the same place |
| Answering a single-sentence truth question with a full protocol | The unit of work is one claim; a review is the wrong shape and buries the answer | Route it to `fact-check` |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: adapted from weird-aftertaste/literature-review 1.2.0 (see catalog/sources.yaml)
