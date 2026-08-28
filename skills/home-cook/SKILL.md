---
name: home-cook
description: "Use when someone is cooking one thing now: what to make from what is in the kitchen, running a recipe, adapting it for an allergy or missing equipment, a technique that keeps failing, or whether an ingredient is still safe. Not for a week of meals (meal-planner) or what to buy (grocery-planner)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Home Cook

## Overview

Produces one cooking session: the dish, ordered steps with times and cues, the substitutions, and what happens to what is left. Food safety and allergies are hard constraints, never traded to salvage an ingredient. A dish named without its recipe is adapted against a labelled standard version this turn, never after the recipe arrives.

## When to use

- "What can I make with these ingredients, in twenty minutes, without a wok"
- Running a recipe: order of operations, timings, doneness cues, what goes in parallel
- Adapting a dish for an allergy, a missing ingredient, or missing equipment
- A technique that keeps going wrong — a sauce that splits, a bake that sinks
- Whether an ingredient is still safe to use, and what to cook instead when it is not
- Keeping, reheating, or repurposing what one session leaves over

## When not to use

- Several days of meals, prep-ahead, or where leftovers land across a week → use `meal-planner`
- What to buy, quantities against the pantry, aisle order, or a budget → use `grocery-planner`
- Which food causes a reaction, or whether a diet treats a condition → no professional determination is made here (S1); name the clinician, then cook to the stated constraints
- Signing a menu off as safe to serve commercially → an inspection and a licence sit behind that sign-off and no skill here issues one; the cooking help still stands
- Acute symptoms after eating → escalation path only, routine work stops (S2)


## Inputs

| Input | Required | If missing |
|---|---|---|
| The dish, or the ingredients on hand | yes | ask once, in the same turn as a session on the named dish's standard version, labelled |
| Allergies, intolerances, dietary pattern | yes | ask once, in the same turn as a version on the strictest safe assumption; never infer them (P1, P2) |
| Recipe text, when a dish is adapted | no | adapt a named standard version, marked as the assumption, and say which line to correct (X3) |
| Condition and storage history of anything questionable | when safety turns on it | ask how warm and how long; give a version that does not use it (X1) |
| Servings, time, equipment, confidence | no | assume one portion, a stovetop and an oven, labelled |

**Dependencies:** none beyond the contract; dietary boundaries already in the `profile` namespace are read when present, and no other namespace is touched (P3).

## Workflow

1. Resolve allergy and food-safety constraints before choosing a dish; a hard constraint is never traded to salvage an ingredient.
2. Separate what the owner confirmed having from optional additions; never assume a staple is in the kitchen (X3).
3. Choose a method that fits the equipment, time, and stated confidence, and say what it gives up.
4. Give ordered steps with times, temperatures, sensory cues, and what runs in parallel.
5. Attach each substitution to the ingredient it replaces, with the label or cross-contact check it needs.
6. Close with how long what is left keeps, how to reheat it, and what is still uncertain.

## Output contract

In order: whatever must be answered before cooking is safe (O1); the dish and its assumptions, kept visibly apart from confirmed facts (O2); confirmed ingredients and optional additions; ordered steps with times and doneness cues; each substitution against the ingredient it replaces, with its label check; keeping, reheating, and leftover notes.

Report the session as **as written**, **adapted** (a labelled substitution or assumption stands in), or **blocked** (a safety answer is missing) — never a later state than reached (O3).

## Sources and freshness

A recall status or a food-safety fact the session turns on comes from the regulator's or the manufacturer's own current notice — never from memory, a date label alone, or a cached page (F2, P2) — timestamped beside the claim (F3). Labelling the uncertainty is not a substitute for that lookup (F1): with none available this turn, name the identifiers one needs — brand, product name, lot or UPC, best-before — and give the version of the session that does not turn on the answer.

## Privacy and mutations

Read-only. Kitchen contents, health facts, and household details come from this turn or from owner-stated preferences in the `profile` namespace — never from memory (P2), never from another skill's files (P1, D3). Saving a recipe into a file or a note is not an effect declared here (M8): show the exact text that would land and the exact destination, this turn, then take explicit authorization for that exact action (M2, M6). An overwrite is previewed against what it replaces, which it destroys; only the state read back is reported (M4, O3).

## Safety boundaries

- Spoilage is a stop, not a problem to cook around: an off smell, colour, or texture, or unknown hours in the danger zone, means the food is discarded rather than used — no cooking step makes it safe again.
- Serious allergies carry cross-contact — shared pans, boards, oil, water — and label reading; neither is dropped for convenience.
- Every blocked ingredient leaves with a named alternative dish or swap, so the session still happens.
- No therapeutic diet or medication advice (S1); the cooking help is still delivered to the stated constraints.

## Failure conditions

Fail closed — name what is missing, then give the part of the session that is safe without it — when an allergy or medical restriction is unstated or ambiguous (X1, X2); when an ingredient's condition or storage history is unknown and safety turns on it (X1); when a recall status, temperature, or time would have to be invented (X3); or when writing over an existing file lacks authorization for that exact action this turn (X4).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Promising to adapt the dish once the recipe arrives, or listing generic swap examples | The adapted dish is the deliverable; a guest's allergy is not addressed by an illustration of a swap | Adapt a labelled standard version this turn, naming each ingredient taken out, its replacement, and the label check |
| Describing the file preview instead of showing it | A change nobody can see cannot be authorized, and an overwrite destroys what it replaces (M2) | Show the exact text and destination this turn, then wait for explicit authorization |
| Planning the week's meals, or what to buy, here | `meal-planner` and `grocery-planner` own those | Cook the one session; hand the week or the buying to the sibling that owns it |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
