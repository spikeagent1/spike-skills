---
name: "literature-review"
description: "Make academic reviews scoped, reproducible, current, appraised, and citation-grounded."
---

# Literature Review

Use this workflow for bounded evidence discovery and synthesis. Do not call a top-N metadata search comprehensive, exhaustive, or systematic without a documented protocol that supports those terms.

## Frame the question
Restate the research question, audience, search-as-of date, date/language limits, study types, population or domain, and inclusion/exclusion criteria. If the user does not specify them, choose conservative defaults and label them.

## Search reproducibly
Build multiple query variants using synonyms, acronyms, alternate spellings, and controlled vocabulary where relevant. Search at least two appropriate indexes; include PubMed for biomedical questions. Record each engine, exact query, filters, limit or pagination, search date, returned count, and failure.

Follow pagination within the agreed scope. Use backward and forward citation chasing for load-bearing papers when tools permit. Define a stopping rule. Database/API failure produces partial coverage, not a silent empty result.

## Verify and deduplicate
Normalize DOI and PMID, then compare title, year, authors, and version to merge records without identifiers and preprint/published duplicates. Verify bibliographic fields against DOI/Crossref, PubMed, or publisher records. Flag missing abstracts, uncertain metadata, preprints, corrections, and retractions.

Never fabricate a paper, DOI, PMID, author, venue, result, or abstract.

## Select and appraise
Explain why records were included or excluded. Do not use citation count or recency as a quality score. Extract study design, population/sample, intervention or exposure, comparator, outcomes, limitations, funding/conflicts, peer-review status, and relevant risk-of-bias signals.

Label the evidence level available for each record: full text, abstract, or metadata only. Do not infer methods or results absent from the accessed evidence.

## Synthesize
Base every substantive claim on retrieved evidence and cite it nearby with a stable DOI, PMID, or publisher link. Calibrate causal language to study design. Compare agreement, contradictions, heterogeneity, evidence gaps, and applicability. Keep preprints, commentary, reviews, observational studies, and trials distinct.

## Report
Include:

- question, scope, criteria, and search-as-of date;
- databases attempted and succeeded, exact queries, filters, and counts;
- screening/inclusion flow and deduplication;
- evidence table with access level and appraisal;
- thematic synthesis with claim-linked citations;
- contradictions, uncertainty, gaps, and coverage limits;
- references and next search steps.

If retrieval is sparse or fails, return a partial-results report. Never imply that nothing was missed.

## Systematic-review boundary
A systematic review requires an explicit protocol, broad database coverage, reproducible screening, deduplication, selection flow, appraisal, and stopping rule. If those are absent, call the output a scoped literature search or narrative evidence review.

## Failure conditions
Fail review if the workflow claims complete abstracts from every source; calls a fixed top-N search comprehensive; hides an engine failure; deduplicates only by DOI; ranks quality by citation count; writes beyond abstract/metadata evidence; omits currentness; or includes an unsupported citation.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.

## When to use
Use this skill for scoped research-paper discovery, screening, synthesis, and evidence mapping across academic or technical literature.

## When not to use
Do not use it for single-claim fact checks, unbounded "find everything" requests, clinical advice, or citation laundering from abstracts without reading enough of the source to support the claim.

## Required inputs
Required inputs are research question, scope, inclusion/exclusion criteria, source databases or corpus, freshness horizon, and desired synthesis form. If scope is too broad, propose a bounded protocol before searching.

## Optional inputs
Optional inputs include seed papers, keywords, citation style, quality criteria, language, date range, and maximum number of papers. Missing optional inputs become explicit protocol defaults.

## Workflow
1. Convert the question into a search protocol with inclusion/exclusion criteria.
2. Run multiple query variants across named databases or provided corpus.
3. Deduplicate by DOI/PMID/arXiv/title/version and record search dates.
4. Screen titles/abstracts, then inspect full text or relevant sections for included claims.
5. Extract methods, population/data, findings, limitations, and citation metadata.
6. Synthesize agreement, disagreement, gaps, and confidence without claiming comprehensive coverage unless the protocol supports it.
7. Provide a reproducible search log and next search improvements.

## Sources and freshness
Use current database results or a dated supplied corpus. Versioned preprints, retractions, corrections, and newer reviews must be checked when they could change conclusions.

## Privacy and mutations
The workflow is read-only unless the user asks to save a bibliography or notes. Do not upload private papers or notes to external tools without authorization.

## Safety boundaries
Do not invent papers, infer findings from titles alone, or present preliminary/preprint evidence as settled. For medical, legal, or financial topics, label the output as literature synthesis, not advice.

## Output contract
Return research question, protocol, search log, included/excluded counts, evidence table, synthesis, limitations, citation list, freshness date, and unresolved gaps.

## Failure conditions
Fail or narrow scope when databases are unavailable, full text needed for central claims cannot be inspected, dedupe cannot be trusted, inclusion criteria are undefined, or the requested conclusion overreaches the evidence.

## Worked example
For "review recent papers on agent eval reliability," produce query strings, database/date, screened count, included table, themes, disagreements, and a non-comprehensive caveat if only a subset was searched.
