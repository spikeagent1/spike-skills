---
name: "meal-planner"
description: "Create practical meal plans from dietary constraints, schedule, budget, and nutrition goals without medical diet claims."
---

# Meal Planner

## Purpose

Plan meals, prep blocks, leftovers, and shopping needs around user constraints. It does not prescribe medical diets, treat illness, or override a clinician or registered dietitian.

## Dependencies

Optional calendar, pantry notes, grocery list, or recipe sources when authorized. Current nutrition, recall, or food safety claims need authoritative sources or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general meal planner workflow patterns and repository privacy constraints; no upstream skill was copied.

## Rules

Respect allergies first, separate stated needs from inferred preferences, prefer repeatable components, include substitutions, do not fabricate calorie or macro precision, and escalate medical nutrition questions.

## Output

Return: assumptions; meal schedule; prep plan; grouped grocery list; substitutions; nutrition/source caveats.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
