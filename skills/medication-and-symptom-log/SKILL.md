---
name: "medication-and-symptom-log"
description: "Structure local medication and symptom notes for review without hidden storage, diagnosis, or medication advice."
---

# Medication And Symptom Log

## Purpose

Help create, review, and summarize a local log of medications, symptoms, triggers, questions, and clinician follow-ups. The skill provides structure and summaries, not medical advice.

## Dependencies

Optional user-supplied notes, calendar, files, or an explicit local path. If persistence is needed, use only a configurable user-local path owned by this skill. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general medication and symptom log workflow patterns and repository privacy constraints; no upstream skill was copied.

## When to use

Use this skill to create, append, summarize, or prepare a medication and symptom log. If a new entry reveals an acute red flag, trigger the safety escalation path before routine logging; never turn the log into diagnosis or dosing advice.

## Required inputs

- requested operation: create, append, summarize, or appointment prep
- medication name, dose, route, schedule, and indication only as supplied
- symptom time, severity, duration, context, and user wording
- explicit destination and format if the user asks to persist data

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Workflow

1. Screen the new entry for urgent symptoms before routine logging.
2. Record only supplied facts; represent unknown, skipped, and uncertain fields explicitly.
3. Preserve chronology and distinguish medication events from symptoms and interpretations.
4. For summaries, show patterns and missing data without claiming causation.
5. Preview any write, confirm the skill-owned local path, then report exactly what changed.

## Sources and freshness

Browse only when the user asks for current official medication instructions or safety information. Prefer the medication label, dispensing pharmacy, regulator, or clinician. Never use a general web result to decide dosing for the user.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Do not recommend starting, stopping, doubling, tapering, or catching up medication. Direct dosing questions to the prescriber, pharmacist, or official label. Escalate severe breathing trouble, fainting, rapidly spreading rash, overdose, or other acute symptoms to urgent local help.

## Output contract

- log schema, proposed entry, or summary
- unknown and missing fields
- chronology and clinician questions
- red-flag and non-advice status
- previewed write result and local path, only when authorized

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
