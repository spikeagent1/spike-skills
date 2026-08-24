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

## Rules

Capture visit type, clinician/date, concern, timeline, severity, triggers, prior attempts, medications, allergies, and records. Preserve exact words, separate facts/questions/worries/goals, and flag urgent red symptoms.

## Output

Return: appointment brief; symptom timeline; supplied medications/allergies; top questions; records to bring; red-flag note; source/data coverage.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
