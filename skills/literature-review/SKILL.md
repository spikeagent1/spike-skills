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
