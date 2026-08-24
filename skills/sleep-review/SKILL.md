---
name: "sleep-review"
description: "Review sleep patterns, routines, and constraints to support better habits without diagnosing sleep disorders."
---

# Sleep Review

## Purpose

Help understand sleep patterns, friction, routines, and environmental constraints. Turn observations into practical experiments and clinician-ready notes when symptoms suggest medical review.

## Dependencies

Optional wearable, calendar, notes, or habit logs when authorized. Current medical or safety claims require authoritative sources or uncertainty. No hidden hosted dependency, shared user database, or cross-skill private storage.

## Provenance

Owned by Spike. Based on general sleep review workflow patterns and repository privacy constraints; no upstream skill was copied.

## Rules

Distinguish user reports from device measurements, check schedule/caffeine/light/stress/naps/exercise/environment, prefer one or two experiments, flag breathing pauses, drowsy driving, or neurological symptoms, and never infer diagnoses from scores.

## Output

Return: pattern summary; friction points; one-week experiment; what to track; medical-review prompts; source/data coverage status.

## Failure conditions

Fail if the response ignores user constraints, fabricates personal or current facts, hides uncertainty, uses another skill's storage, or crosses the safety boundary described above.
