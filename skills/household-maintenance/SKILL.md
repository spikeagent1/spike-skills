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

## When to use

Use this skill for routine maintenance, low-risk troubleshooting, and contractor preparation. If an in-domain request reveals a gas, electrical, structural, carbon-monoxide, flooding, sewage, mold, or hazardous-material danger, trigger only the safety and escalation path.

## Required inputs

- home type, affected area, and observed symptoms
- appliance model or system details when relevant
- what changed, what has already been tried, and current hazards
- tenant/owner constraints and location only when code or service options matter

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Workflow

1. Classify the request as routine maintenance, low-risk troubleshooting, safety event, or contractor preparation.
2. Check immediate hazards before suggesting inspection or tools.
3. Give only reversible, non-invasive checks that fit the user's stated competence.
4. Define a stop condition before each step that could expose a hazard.
5. Produce a maintenance record or concise contractor note when escalation is appropriate.

## Sources and freshness

Current code, recalls, warranty terms, and manufacturer procedures require authoritative current sources. Prefer official manuals, regulators, utilities, or local authorities. Never invent model-specific steps or local code.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Do not provide DIY repair instructions for gas lines, exposed energized wiring, structural movement, hazardous materials, sewage, severe mold, carbon-monoxide alarms, or flooding near electricity. Prioritize evacuation and local emergency or utility guidance when appropriate.

## Output contract

- risk category and immediate action
- safe reversible checks
- tools or supplies only for allowed checks
- stop/escalation thresholds
- maintenance checklist or contractor-ready note with source status

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
