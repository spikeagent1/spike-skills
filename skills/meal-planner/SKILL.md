---
name: meal-planner
description: "Use when someone wants meals planned for several days or a week: 'what should we eat this week', meal prep, leftovers, cooking around allergies, budget, or schedule. Not for a single recipe or cooking session (home-cook) or a shopping list from an existing plan (grocery-planner)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Meal Planner

## Overview

Produces a multi-day meal plan: what to eat each day, what to cook ahead, where leftovers land. Allergies and medically required restrictions are hard constraints, never preferences traded against time or budget. A missing input becomes a labelled assumption, not a reason to withhold the plan.

## When to use

- "What should we eat this week", "plan our dinners", "meal prep for the week"
- Several days of meals to fit around evenings out, work hours, or short cooking windows
- Cooking around allergies, intolerances, a dietary pattern, or foods someone refuses
- Feeding a household to a budget, or cutting waste by planning leftovers

## When not to use

- One recipe, one technique, or tonight's single session → use `home-cook`
- Meals already chosen and the ask is a shopping list, aisle grouping, pantry check, or budget total → use `grocery-planner`
- Which food causes a reaction, or whether a diet treats a condition → no professional determination is made here (S1); name the clinician or registered dietitian, then plan general balanced meals anyway
- Acute symptoms after eating → escalation path only, routine work stops (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| Who eats, which meals are covered | yes | ask once; plan the stated household only |
| Allergies, intolerances, dietary pattern, dislikes | yes | ask once, in the same turn as a plan built on the strictest safe assumption; never infer them (P1, P2) |
| Days covered, cooking time per day | no | assume the coming week, labelled |
| Budget, equipment, leftover appetite | no | continue; mark every figure an estimate (O2) |
| Owner-confirmed pantry items | no | plan as if nothing is on hand; never invent stock (X3) |

**Dependencies:** none beyond the contract; dietary boundaries already in the `profile` namespace are read when present, and no other namespace is touched (P3).

## Workflow

1. Split hard constraints — allergy, medical restriction — from soft ones; a hard constraint is never traded.
2. Keep confirmed facts apart from assumptions; ask only what changes safety or feasibility, and plan on labelled assumptions rather than waiting for an answer (O2).
3. Pick repeating components first — a grain, a sauce, a protein — and vary how they combine.
4. Place meals across the days, longest cook where the most time is, each leftover routed into a named later meal.
5. Check feasibility: time per day, refrigerator and freezer room, how long each cooked component keeps.
6. Substitute for every constrained ingredient, then hand shopping to `grocery-planner`.

## Output contract

In order: whatever must be answered before the plan is safe (O1); constraints, split into confirmed and assumed (O2); the plan day by day, each meal named and each leftover pointed at the meal that eats it; prep blocks with how long each component keeps; substitutions; a current authoritative source beside any recall or food-safety claim, where labelled uncertainty is not an accepted substitute, and a source or labelled uncertainty beside any other nutrition claim (F1, F3); and the ingredients the plan needs, grouped by category. Aisle order, quantities to buy against the pantry, and the budget total belong to `grocery-planner`.

Report each day as **planned**, **assumed** (a labelled assumption stands in for an input), or **blocked** (a safety or allergy answer is missing) — never a later state than reached (O3).

## Privacy and mutations

Read-only. Pantry contents, health facts, and household details come from this turn or from owner-stated preferences in the `profile` namespace — never from memory (P2), never from another skill's files (D3). Saving the plan into a file, note, or list is not an effect declared here (M8): show the exact text that would land, in this turn, and take explicit authorization before any skill writes it (M2).

## Safety boundaries

- Allergy work includes cross-contact and label reading; neither is dropped for time or budget.
- No therapeutic diet, disease-reversal claim, or medication advice (S1); the general balanced plan is still delivered, with the clinical targets left to the clinician.
- Food of unknown temperature history: ask how warm and how long, and offer a plan that does not use it (X1).

## Failure conditions

Fail closed — name what is missing and give the part that is safe without it — when an allergy or medical restriction is unstated or ambiguous (X1, X2); when pantry contents, prices, or nutrient values would have to be invented (X3); when a food-safety fact the plan depends on is unknown (X1); or when honoring one stated constraint would quietly drop another (X2).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Producing the shopping list — aisle order, quantities to buy, pantry math, budget total | `grocery-planner`'s deliverable; two of them means two lists to reconcile | List what the plan needs, grouped, and hand the shopping to `grocery-planner` |
| Naming the food behind a reaction | Diagnosis from symptom patterns is a clinical determination no skill here owns (S1) | Refuse it, give the clinician path, and plan the meals that are safe to plan |
| Planning around food of unknown temperature history | Optimizes waste ahead of safety | Ask how warm and how long; plan without it if either is unknown |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
