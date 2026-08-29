---
name: purchase-research
description: "Use when something is being bought: which model or part to get, comparing options or links already in hand, working out the requirements first, what goes wrong after the sale — warranty, returns, compatibility, repairability — or total cost. Not for servicing what is owned (household-maintenance)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Purchase Research

## Overview

Produces the decision, not a promise of one: weighted criteria, a shortlist against them, what the thing costs over the years it is kept, and what tends to go wrong after the sale. The durable half of that is time-independent and is written in this turn whether or not a live figure can be checked; the live half is checked or marked unverified, never recalled into the table.

## When to use

- "Which one under this budget actually handles this, and can I repair it?"
- "Here are the options I am looking at — what is likely to go wrong after I buy?"
- Warranty terms, the returns window, compatibility with what is already owned, support lifetime, spare parts
- Working out the requirements first, when the owner does not yet know what they need
- Total cost over the years it will be kept: consumables, repairs, subscriptions, the eventual replacement
- A manufacturer figure and an independent test that disagree, and which one the decision should rest on

## When not to use

- Upkeep, servicing, or repair of something already owned → use `household-maintenance`
- Working out what to wear or what fits in the bag before any buying question arises → use `wardrobe-and-packing`
- Whether it is affordable, or whether to finance it over a term → no financial determination is made here (S1); the comparison gives the total cost and the owner or their adviser decides what to do with it
- Whether a device, supplement, or aid is medically or legally suitable for a person → no such determination is made here (S1); the requirement is taken as the owner states it

## Inputs

| Input | Required | If missing |
|---|---|---|
| Use case, and the dealbreakers that rule an option out | yes | ask once, in the same turn as criteria weighted for the commonest reading of the request, labelled as that reading (X1) |
| Budget, the timeframe for deciding, and where the buying would happen | no | assume the request's own figure where it names one, no deadline otherwise, and the owner's own market; label all three, because price, availability, warranty terms and returns rights are regional, and say which lines the region sets |
| Constraints: compatibility, size, accessibility, repairability, privacy, sustainability | no | plan around only the constraints stated; none is inferred from the owner or the category (P2) |
| Options or links already in view | no | say plainly that none arrived, name what would be read from each if supplied, and give the criteria and after-sale risks for the category anyway (X3) |
| Whether a current-source check can be made this turn | no | assume it cannot; ship the durable half and leave the current facts marked `[unverified]` (F1, F4) |
| Tolerance for used, refurbished, or waiting | no | assume new-only and say so; note the option the other answer would add |

**Dependencies:** none beyond the contract; owner-stated purchase constraints already in the `profile` namespace are read when present, and no other namespace is touched (P3). A browsing, retailer, or purchase-history connector is read only when the owner names one this turn (D1); one that is named but unreachable has its blocked phase reported rather than its contents assumed (D2, F4). No affiliate, referral, or ranking relationship is taken as a dependency of this skill (D3).

## Workflow

1. Produce the comparison in this message: the weighted criteria, the shortlist, the total-cost model, and the after-sale risks, built from what was supplied with every assumption labelled. A question about the budget or the room size rides alongside it, never in place of it, and "send me the links and I will build the comparison" is not building one (O2).
2. Turn the request into weighted criteria and a separate list of hard exclusions, so an option that fails an exclusion is out regardless of how well it scores.
3. Look past the first result and the first ranking: a shortlist that reproduces one list's order has been anchored, and a ranking is one source's opinion — evidence to test the criteria against, never the authority that sets them (S3).
4. Check every decisive current fact — price, stock, model specification, warranty term, recall, policy — against the manufacturer's, regulator's, retailer's, or independent tester's own current publication, and mark it `[unverified]` where that check cannot be made this turn (F2, F3).
5. Compare on total cost over the years the thing is kept, not the sticker: consumables, repairs, subscriptions, and the replacement the failure mode implies.
6. Say what tends to go wrong after the sale for this category — warranty exclusions, the returns window and who pays the shipping, compatibility with what is already owned, support and firmware lifetime, parts availability — using [the comparison shape](#the-comparison-shape).
7. Recommend by use case, keep any conflicting evidence intact rather than resolving it by preference, and name what would change the recommendation.

### The comparison shape

Every group appears, in this order, whether or not a lookup was possible; a group nothing can fill says why, because a group silently missing reads as one that was checked and came back clear.

```
Criteria         weighted, with hard exclusions listed separately
Shortlist        each option against each criterion
Excluded         what was dropped, and on which criterion
Current facts    price, stock, spec, warranty term — each with its source and retrieval time, or [unverified]
Total cost       purchase, consumables, repairs, subscriptions, replacement — over the years assumed
After the sale   warranty exclusions, returns window, compatibility, support and parts lifetime, known failure modes
Recommendation   by use case, and what would change it
Open questions   what is unresolved, and who answers it
```

`Criteria`, `Total cost`, and `After the sale` are the durable half: they hold whatever today's price is, so they are never withheld for a lookup that could not be made. `Current facts` is the only group a missing lookup empties, and it empties into `[unverified]` lines, not into silence.

## Output contract

The comparison is in this message, not promised for the next one: an intake questionnaire, an announcement that a comparison is coming, or a description of how the work would be approached once the links arrive is a failure to deliver it. In order: anything that changes the decision before the table is read — a figure nobody verified, a conflict between sources, an exclusion no option meets (O1); the comparison in the shape above; the assumptions, labelled beside what they decide and kept visibly apart from the sourced facts and the owner's own statements (O2); and the retrieval time beside each current claim, with `[unverified]` beside each one that has none (F3).

Report the turn as **ready** (every decisive fact is sourced and the criteria are met), **partial** (a required input is missing, or the current facts are `[unverified]`, and the comparison names what each would change), **previewed** (a change to a saved list or record is written out and waiting on authorization), or **blocked** (no option clears a hard exclusion, and the trade-off is named) — never a later state than reached (O3). **Partial** is a label on a delivered comparison, never a questionnaire: the criteria, the total-cost model, and the after-sale risks are written out either way. Stable buying guidance is never withheld for a missing lookup — the sensible floors for the category, what separates its tiers, how to judge a discount against the typical street price, and its usual failure modes are time-independent, and a turn that could not check a price still ends with them on the page.

## Sources and freshness

Every live price, stock level, model specification, warranty term, recall, review claim, and retailer policy is checked against a current authoritative publication in this turn — the manufacturer, the regulator, the retailer itself, or an independent tester — with the retrieval time beside the claim (F3). Labelling the uncertainty is not a substitute for that check (F1): where the check cannot be made, the figure is not printed at all, the line reads `[unverified]` and names where it is settled, and the durable guidance carries the turn (X3). A number remembered from before is undated recall and is context, never evidence (F2). Manufacturer claim, independent test, aggregated user reports, and inference are four different things and are labelled as which (O2, S3); where two disagree, both stay, with the test conditions that separate them and what the disagreement changes (X3). No results, source unreachable, and permission refused are three different outcomes and are reported as which (F4).

## Privacy and mutations

Read-only. Requirements, budgets, and prior purchases come from this turn or from a connector the owner names this turn — never from memory (P2), never from another skill's files or private area (P1, D3). A budget, an address, an income signal, or a purchase history is used for the comparison and summarised rather than reproduced, and none of it is written into the response beyond what the recommendation needs (P4). Buying, reserving, ordering, adding to a basket, or keeping a wishlist past this turn is not an effect declared here (M8): show the exact action in this turn — the item, the option, the total, and the destination — then take explicit authorization for that exact action (M2, M6), reporting the connector state read back and distinguishing named and reachable, named and unreachable, and none named (D2, F4, O3). A purchase is never reported as made on anything less than the authority's own readback (M4, X5).

## Safety boundaries

- No option is presented as universally best, and no urgency the sources do not support is manufactured — no invented stock scarcity, no deadline, no "prices are rising" without a dated source (X3, O2).
- No affiliate, referral, sponsorship, or ranking placement influences the shortlist, and a source with a commercial relationship to a listed option is named as such where it is known (S3).
- For anything whose failure hurts someone — electrical, gas, child, medical, structural, load-bearing, protective equipment — certification, recall status, and standards compliance outrank popularity, price, and review counts, and an option missing a required certification is excluded rather than ranked (X2).
- Nothing here decides whether a purchase is affordable, financeable, tax-deductible, or medically or legally suitable (S1); the comparison supplies the figures and the requirement, and the determination stays with the owner or their professional.
- Missing evidence and conflicting evidence are disclosed in the recommendation itself, not left in a footnote below it (O1).

## Failure conditions

Fail closed — name what is missing, then give the durable half of the comparison — when a price, stock level, specification, warranty term, or model number would have to be invented (X1, X3); when links, options, or documents the request refers to did not arrive (X1, say so and give the category's criteria and after-sale risks anyway); when a conflict between sources would be resolved by picking the more favourable figure (X3); when no option clears a hard exclusion (X2, report **blocked**); or when a purchase or list change lacks authorization for that exact action this turn (X4). A mutation is reported only at the state read back, never at the state intended (X5).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Answering "no browsing" with intake questions and an offer to compare later | The time-independent half of the answer needed no lookup, and withholding it leaves the owner with nothing to decide on | Give the floors, the tier boundaries, how to judge a discount against typical street price, and the category's failure modes in this turn, with the live figures marked `[unverified]` |
| Describing how the post-purchase risks would be analysed once the links arrive | A preview of the method is not the analysis; warranty exclusions, the returns window, compatibility and support lifetime are category facts that hold without the specific links | Fill `After the sale` for the category now, and name what each specific option would change |
| Picking the larger of two disagreeing figures, or averaging them | The disagreement is usually the test conditions, and flattening it hides the one thing that decides the purchase | Keep both, attribute each to manufacturer or independent test, give the conditions, and say what the conflict changes |
| Printing a remembered price or spec as current | An undated figure read as today's is what turns a comparison into a wrong purchase | Check it this turn with the retrieval time beside it, or write `[unverified]` and name where it is settled |
| Building the shortlist from the first ranking found | A ranking is one source's opinion and often a commercial placement; reproducing its order imports its bias whole | Derive the shortlist from the criteria, then use rankings as evidence to test it (S3) |
| Naming a single best product | Best depends on the use case, and a single answer hides the exclusion that rules it out for this owner | Recommend by use case, name what would change it, and list what was excluded and why |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
