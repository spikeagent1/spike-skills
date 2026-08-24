---
name: "home-cook"
description: "Help plan, adapt, and troubleshoot home cooking from ingredients, equipment, skill level, and food-safety constraints."
---

# Home Cook

## Purpose

Turn available ingredients, preferences, equipment, time, and skill level into practical cooking plans. Adapt recipes without pretending to know pantry state or current safety recalls unless sources are checked.

## Dependencies

Optional pantry notes, grocery list, recipe files, timer, or source lookup when authorized. Current food safety, recall, or product claims require authoritative current sources or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general home cook workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill for recipe planning, adaptation, sequencing, substitutions, and cooking troubleshooting. If the request reveals unsafe food or a serious allergy risk, trigger the safety path and offer a safe alternative instead of continuing the recipe.

## Required inputs

- available ingredients and confirmed pantry staples
- allergies, dietary constraints, servings, and preferences
- time, equipment, and cooking confidence
- ingredient condition or storage history when safety is relevant

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Workflow

1. Resolve allergy and food-safety constraints before choosing a dish.
2. Separate supplied ingredients from optional additions and substitutions.
3. Choose a method that fits the equipment, time, and skill level.
4. Give ordered steps with sensory cues, temperatures, and parallel timing where useful.
5. End with storage, leftover, and uncertainty notes.

## Sources and freshness

Browse authoritative current sources for recalls or changing food-safety questions. Prefer regulator guidance and manufacturer notices. Do not claim an ingredient is safe from a date label alone or invent recall status.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Do not suggest tasting or cooking obviously spoiled food to make it safe. Treat serious allergies and cross-contact as hard constraints. If ingredient history is too uncertain for a safe answer, recommend discarding it and offer an alternative.

## Output contract

- dish choice and assumptions
- confirmed and optional ingredients
- ordered steps with timing and doneness cues
- substitutions and equipment adaptations
- allergy, storage, and source notes

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
