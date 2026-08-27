---
name: "health-appointment-prep"
description: "Prepare concise, source-grounded notes and questions for clinical appointments without giving a diagnosis."
---

# Health Appointment Prep

## Purpose

Help prepare for clinical conversations by organizing symptoms, timeline, medications, questions, records, and decisions. It does not diagnose, triage beyond red-flag escalation, or advise medication changes.

## Dependencies

Optional calendar, notes, files, or medication logs when authorized. Current clinical claims require authoritative sources or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general health appointment prep workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill to organize a routine clinical visit, timeline, records, and questions. If the supplied symptoms reveal an urgent red flag, trigger only the immediate safety and escalation path rather than continuing routine appointment preparation.

## When not to use

Do not use this skill to make professional medical, legal, financial, structural, electrical, gas, fire-safety, or other high-stakes determinations; to bypass urgent escalation; or to mutate records without explicit authorization.

## Required inputs

- visit type, date, clinician or specialty when known
- primary concern and desired decision or outcome
- timeline, severity, triggers, associated symptoms, and prior attempts supplied by the user
- verified medications, allergies, test results, and records

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Optional inputs

Optional inputs include preferences, budget, schedule, location, authorized connector data, prior attempts, and desired output format. Missing optional inputs remain unknown and must not be invented.

## Workflow

1. Screen the supplied text for urgent red flags before preparing a routine visit.
2. Preserve the user's wording and chronology; never fill gaps from memory.
3. Separate facts, uncertainties, worries, goals, and questions.
4. Compress the brief for the available visit time and rank the top questions.
5. List records or medication details that still need verification.

## Sources and freshness

Use current authoritative sources only to explain why a symptom may need urgent evaluation or to clarify a preparation requirement. Do not use browsing to infer the user's diagnosis. Mark every externally sourced claim and every missing personal fact.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Urgent symptoms override appointment preparation. Recommend immediate local emergency or urgent medical help for time-sensitive red flags such as sudden severe headache with weakness, chest pain, severe breathing difficulty, or loss of consciousness. Do not diagnose or advise medication changes.

## Output contract

- one-paragraph appointment brief
- chronological symptom timeline
- verified medications, allergies, and records supplied
- ranked questions and visit goals
- missing information, red-flag status, and source coverage

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
