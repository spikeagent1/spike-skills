---
name: "grocery-planner"
description: "Build grocery lists from meal plans, pantry checks, budgets, and store constraints without fabricating prices or inventory."
---

# Grocery Planner

## Purpose

Convert meals, household needs, budget, dietary constraints, and pantry facts into a grouped grocery list and shopping plan.

## Dependencies

Optional meal plan, pantry notes, grocery app, current store lookup, or local list file when authorized. Current prices, inventory, coupons, and substitutions require live source lookup or labeled estimates. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general grocery planner workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill for grocery-list construction, pantry reconciliation, budget planning, and shopping preparation. Keep allergy constraints prominent and use a separate explicit authorization step for connected-list changes or orders.

## When not to use

Do not use this skill to make professional medical, legal, financial, structural, electrical, gas, fire-safety, or other high-stakes determinations; to bypass urgent escalation; or to mutate records without explicit authorization.

## Required inputs

- meals, people, duration, and household needs
- dietary constraints and allergies
- confirmed pantry inventory
- budget, preferred stores, transport, and storage constraints

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Optional inputs

Optional inputs include preferences, budget, schedule, location, authorized connector data, prior attempts, and desired output format. Missing optional inputs remain unknown and must not be invented.

## Workflow

1. Convert meals into quantities, then subtract only confirmed pantry items.
2. Consolidate duplicates and group the list by store section or shopping route.
3. Mark required, optional, and substitution items.
4. Estimate budget with explicit price assumptions or use current store sources when available.
5. Check allergy labels, storage capacity, and likely waste before finalizing.

## Sources and freshness

Live prices, coupons, and inventory require current store or delivery-source lookup and a timestamp. If access is unavailable, provide ranges or a budget allocation rather than exact claims. Prefer store-native sources over aggregators.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Treat allergies as hard constraints and call out label or cross-contact verification. Do not infer household inventory from prior conversations or another skill's files. Never place an order or modify a connected list without explicit authorization and a preview.

## Output contract

- assumptions and confirmed pantry coverage
- grouped list with quantities and priority
- estimated or sourced budget status
- substitutions and waste-reduction notes
- source timestamp and any proposed mutation result

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
