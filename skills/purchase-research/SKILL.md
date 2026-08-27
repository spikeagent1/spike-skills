---
name: "purchase-research"
description: "Compare purchases from requirements, constraints, current sources, and tradeoffs without fabricated specs or affiliate bias."
---

# Purchase Research

## Purpose

Help make deliberate purchase decisions by clarifying requirements, comparing options, checking current sources when needed, and explaining tradeoffs.

## Dependencies

Current web/source lookup is required for live prices, availability, warranty, model specs, reviews, recalls, and policy claims. Optional user links, notes, or purchase history when authorized. No hidden hosted dependency, affiliate dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general purchase research workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill for requirements discovery, current-market comparison, and purchase-risk analysis. Do not trigger it merely to endorse a product, repeat a ranking, or make a purchase without evidence and explicit authorization.

## When not to use

Do not use this skill to make professional medical, legal, financial, structural, electrical, gas, fire-safety, or other high-stakes determinations; to bypass urgent escalation; or to mutate records without explicit authorization.

## Required inputs

- use case, budget, location, timing, and dealbreakers
- compatibility, size, accessibility, repairability, privacy, or sustainability constraints
- products or links already under consideration
- decision horizon and tolerance for used, refurbished, or delayed purchase

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Optional inputs

Optional inputs include preferences, budget, schedule, location, authorized connector data, prior attempts, and desired output format. Missing optional inputs remain unknown and must not be invented.

## Workflow

1. Translate the request into weighted criteria and hard exclusions.
2. Search broadly enough to avoid anchoring on the first product or affiliate list.
3. Verify decisive facts against manufacturer, regulator, retailer, or independent test sources.
4. Compare total cost, compatibility, support, returns, repairability, and failure modes.
5. Recommend by use case, show uncertainty, and state what would change the decision.

## Sources and freshness

Browse for every live price, stock, model specification, warranty, recall, review, and policy claim. Timestamp current facts and cite sources near the claim. Distinguish manufacturer claims, independent evidence, user reviews, and inference.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Disclose missing or conflicting evidence and avoid affiliate-like urgency. Do not claim universal 'best'. For safety-critical products, prioritize regulator guidance, certifications, compatibility, and recall checks over popularity.

## Output contract

- requirements and weighted criteria
- shortlist and excluded options
- comparison table with sourced current facts
- recommendation by use case and total-cost risks
- source freshness, conflicts, and open questions

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
