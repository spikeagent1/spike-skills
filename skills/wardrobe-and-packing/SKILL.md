---
name: "wardrobe-and-packing"
description: "Plan outfits, packing lists, and wardrobe gaps from context, weather, activities, and constraints."
---

# Wardrobe And Packing

## Purpose

Create outfit plans, capsule options, packing lists, and wardrobe-gap decisions from trip/activity needs, weather, laundry access, preferences, and constraints.

## Dependencies

Optional calendar, itinerary, weather lookup, wardrobe notes, or user-supplied photos/lists when authorized. Current weather, baggage policy, event dress code, and product claims require current source lookup or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general wardrobe and packing workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill for outfit planning, packing lists, wardrobe gaps, and baggage preparation. Keep photo access, current weather or policy lookup, and any persistent list change behind explicit scope and authorization.

## Required inputs

- destination, dates, activities, and dress expectations
- baggage limits, laundry access, mobility, comfort, and accessibility needs
- user-confirmed owned items and outfit preferences
- current forecast or explicit permission to retrieve it

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Workflow

1. Build an activity matrix before selecting items.
2. Separate confirmed owned items from suggested gaps or optional purchases.
3. Choose a small color and layering system that produces complete outfits.
4. Check quantities against trip length, laundry, baggage, weather uncertainty, and contingencies.
5. Run a final essentials, documents, medication, charger, and return-trip check when relevant.

## Sources and freshness

Current weather, baggage policy, venue rules, and event dress code require a current source and timestamp. Use forecast ranges and contingency layers rather than false precision. Do not infer wardrobe inventory from photos or memory without permission.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Ask before analyzing user photos and minimize retention of image-derived details. Do not recommend items that conflict with stated mobility, sensory, religious, cultural, medical-device, or safety constraints. Never purchase or modify a packing list without explicit authorization.

## Output contract

- assumptions and source coverage
- activity-to-outfit matrix
- packing list with quantities
- rewear, laundry, and contingency plan
- owned items, optional gaps, and policy/weather caveats

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
