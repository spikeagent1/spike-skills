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

## Rules

Identify destination/dates/activities/dress expectations/laundry/baggage/climate/mobility, prefer rewearable combinations, separate owned items from gaps, never invent inventory/weather/policy/dress code, and ask before using photos.

## Output

Return: assumptions/source coverage; packing or outfit list; combinations; laundry/rewear plan; missing items; weather/policy caveats.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
