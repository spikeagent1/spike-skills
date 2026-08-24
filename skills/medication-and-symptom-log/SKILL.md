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

## Rules

Classify create/append/summarize/prep, never invent doses or symptoms, preserve uncertainty, never recommend medication changes, escalate severe symptoms, and confirm any local path before writing.

## Output

Return: log schema or entry; missing fields; clinician-ready summary; red-flag status; local storage path if used; non-advice boundary.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
