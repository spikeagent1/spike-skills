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

## Rules

Respect allergies first, separate confirmed pantry items from assumptions, group by store section, use ranges or current sourced prices for budgets, and never claim stock without current source.

## Output

Return: assumptions; grouped list; quantities; budget status; substitutions; pantry/current-price coverage.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
