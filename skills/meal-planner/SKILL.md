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

## When to use

Use this skill for meal schedules, prep plans, leftovers, and grocery needs. Treat allergy, food-safety, and medical-nutrition risk as constraints or escalation paths; do not diagnose, treat, or prescribe a therapeutic diet.

## Required inputs

- people and meals covered
- dietary pattern, allergies, intolerances, and disliked foods
- budget, time, equipment, cooking confidence, and leftover preferences
- user-confirmed pantry items and nutrition goals

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Workflow

1. Treat allergies and medically required restrictions as hard constraints.
2. Separate confirmed pantry contents and preferences from assumptions.
3. Choose repeatable components and plan leftovers before adding variety.
4. Check time, storage, and food-safety feasibility; add substitutions for constrained ingredients.
5. Produce the meal schedule, prep sequence, and deduplicated grocery list.

## Sources and freshness

Browse authoritative sources for current food recalls, medical nutrition claims, or changing food-safety guidance. Use sourced labels or user-provided data for calories and macros; otherwise give approximate, non-clinical guidance and say it is approximate.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Do not prescribe a therapeutic diet, promise disease reversal, or recommend changing medication. For allergies, preserve label and cross-contact checks. Redirect medical nutrition questions to a qualified clinician or registered dietitian.

## Output contract

- constraints and assumptions
- meal-by-meal schedule with leftover use
- prep blocks and storage notes
- grouped grocery list with quantities
- substitutions, safety notes, and source status

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
