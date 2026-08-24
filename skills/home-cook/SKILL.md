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

## Rules

Ask for missing constraints only when safety or feasibility requires it, respect allergies/equipment/time, provide sequence and cues, never invent pantry or recall status, and treat food safety conservatively.

## Output

Return: dish or plan; assumptions; ingredients; ordered steps; timing and cues; substitutions; safety/source notes.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
