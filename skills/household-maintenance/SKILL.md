---
name: "household-maintenance"
description: "Plan household maintenance, troubleshooting, and contractor-ready notes while escalating safety-critical work."
---

# Household Maintenance

## Purpose

Organize routine maintenance, basic troubleshooting, supplies, schedules, and contractor-ready notes. Keep safety-critical electrical, gas, structural, mold, and hazardous-material issues out of DIY instructions.

## Dependencies

Optional calendar, home inventory, appliance manuals, local notes, or current source lookup when authorized. Current code, recall, warranty, or contractor claims require current sources or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general household maintenance workflow patterns and repository privacy constraints; no upstream skill was copied.

## Rules

Classify routine/troubleshooting/safety/contractor prep, ask for model/location only when needed, give safe checks first, escalate gas smell/exposed wiring/structural movement/sewage/severe mold/flooding near electricity/CO alarms, and do not claim local code without current lookup.

## Output

Return: category; safe next checks; tools/supplies; schedule/checklist; escalation threshold; contractor note; source coverage.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
