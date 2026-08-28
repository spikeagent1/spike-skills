---
name: grocery-planner
description: "Use when someone needs the shopping list itself: turning a meal plan into what to buy, checking it against the pantry, aisle order, a budget cap, snacks or staples for an allergy or dietary pattern, swaps for an out-of-stock item. Not for choosing meals (meal-planner) or cooking a dish (home-cook)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Grocery Planner

## Overview

Produces the actionable shopping list: what to buy, in what quantity, in aisle order, reconciled against confirmed pantry items and a budget. Allergies are hard constraints, never traded for price. A missing input becomes a labelled assumption and the list still lands this turn — a questionnaire is not a list.

## When to use

- "Turn this week's dinners into a shopping list", "what do I still need to buy"
- Checking a list against confirmed pantry items so nothing is bought twice
- Capping a shop at a budget: what to cut, what to swap, what the total comes to
- Aisle order for one supermarket; swaps for an item out of stock, over budget, or off-limits
- Snacks or staples built around an allergy or a dietary pattern

## When not to use

- The meals are not chosen yet → use `meal-planner`; that plan comes back here for the shopping
- How to cook a dish, adapt a recipe, or run tonight's session → use `home-cook`
- Which food causes a reaction, or whether a diet treats a condition → no professional determination is made here (S1); name the clinician, then build the list on the stated constraints
- Acute symptoms after eating → escalation path only, routine work stops (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| Meals or occasions covered, household size | yes | ask once, in the same turn as a list on a labelled standard week |
| Allergies, intolerances, dietary pattern | yes | ask once, in the same turn as a list on the strictest safe assumption; never infer them (P1, P2) |
| Owner-confirmed pantry items | no | give an itemised checklist of the staples this list leans on; unticked means "buy unless already on hand" (X3) |
| Budget, chosen shop, storage room | no | continue; figures stay labelled ranges or allocations (F1, O2) |

**Dependencies:** none beyond the contract; dietary boundaries already in the `profile` namespace are read when present, and no other namespace is touched (P3).

## Workflow

1. Write the list into this message before asking anything, on labelled assumptions; a question about meals, pantry, or budget rides alongside the list, never in place of it, and "I'll build it once you confirm" is not building it (O2).
2. Split hard constraints — allergy, medical restriction — from soft ones; a hard constraint is never traded.
3. Turn each meal into items and quantities for the household and the days covered.
4. Subtract only owner-confirmed pantry items; the rest stays on the list marked unconfirmed, never assumed present (X3).
5. Consolidate duplicates and group the lines in aisle order for one trip.
6. Mark each line required, optional, or a swap, and name one swap for every item that is allergy-constrained, out of stock, or over budget.
7. Total against the budget, naming what gets cut; check labels, cross-contact, storage room at home, and what a pack size leaves to spoil.

## Output contract

The list is in this message, not promised for the next one: a description of the list, an announcement that it is coming, or a request for the inputs that would produce one is a failure to deliver it. In order: whatever must be answered before the list is safe (O1); assumptions kept visibly apart from confirmed facts (O2); the pantry checklist whenever stock is unconfirmed; the list in aisle order, each line carrying a quantity, a required/optional/swap mark, and a named swap wherever a constraint bites; the total, every figure marked **sourced** or **estimated** beside the number (F3); label and cross-contact notes per constrained item.

Report each line as **on hand** (owner-confirmed), **to buy**, **unconfirmed** (buy unless already on hand), or **cut** — never a later state than reached (O3). With no pantry data at all, every line is **unconfirmed** and the checklist enumerates them: an unknown pantry is a labelling problem, not a reason to withhold the list.

## Sources and freshness

Prices, fees, and stock come from the shop's own source or the delivery service's own, ahead of any aggregator, and never from a cached page or a prior run (F2), timestamped beside the figure (F3). With no current source read this turn, figures stay ranges or allocations — an exact price stays out, because labelling the uncertainty is not a substitute for the lookup (F1), and stock is never asserted from recall. A total is still given on that basis — a range or an allocation, with delivery, service, and tip fees as their own line; a zero, a blank, or "not calculable" is not a total.

## Privacy and mutations

Read-only. Pantry contents, budget, and dietary boundaries come from this turn, from an explicitly authorized connector, or from owner-stated preferences in the `profile` namespace — never from memory (P2), never from another skill's files or private storage (P1, D3). Placing an order or changing a list in a connected app is not an effect declared here (M8): show the exact basket this turn, built on labelled assumptions when no list was supplied — every item, quantity, swap, fee, and the total — then take explicit authorization for that exact action (M2, M6), reporting only the state read back (M4, O3).

## Safety boundaries

- Allergy work includes label reading and cross-contact, at the shelf and at home; neither is dropped for price or time.
- Every constrained item leaves with a named safe swap; "may contain" and shared-line labels count as in scope for a severe allergy unless the owner says otherwise.
- No therapeutic diet, disease-reversal claim, or medication advice (S1); the list is still built to the stated constraints.

## Failure conditions

Fail closed — name what is missing, then give the part of the list that is safe without it — when an allergy or medical restriction is unstated or ambiguous (X1, X2); when stock, a price, or a fee would have to be invented (X3); when the budget cannot be met without dropping a hard constraint (X2); or when an order lacks authorization for that exact action this turn (X4).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Asking for meals, pantry, and budget instead of producing a list | The list is the deliverable; a questionnaire sends the shopper to the aisles with nothing | Build it on labelled assumptions this turn, one named swap per constrained item |
| Describing an order preview instead of showing one | An action nobody can see cannot be authorized (M2) | Show the exact basket — items, quantities, swaps, fees, total — this turn |
| Counting a staple as on hand because households usually have it | Invented stock sends the trip home short (X3) | Offer the checklist to tick; unticked means "buy" |
| Choosing the week's meals here | `meal-planner`'s deliverable; two plans mean two lists | Take the plan as given, or hand meal choice to `meal-planner` |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
