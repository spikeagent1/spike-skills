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

## When to use

Use this skill for sleep-pattern review, habit experiments, and clinician-ready notes. If an in-domain request reveals drowsy-driving danger or another acute red flag, trigger only the immediate safety and escalation path.

## When not to use

Do not use this skill to make professional medical, legal, financial, structural, electrical, gas, fire-safety, or other high-stakes determinations; to bypass urgent escalation; or to mutate records without explicit authorization.

## Required inputs

- sleep and wake times across typical days
- user-reported awakenings, daytime function, naps, caffeine, alcohol, and routines
- environmental or schedule constraints
- device measurements only when supplied or explicitly authorized

Ask a focused question only when missing information changes safety or feasibility. Otherwise continue with labeled assumptions and make them easy to correct.

## Optional inputs

Optional inputs include preferences, budget, schedule, location, authorized connector data, prior attempts, and desired output format. Missing optional inputs remain unknown and must not be invented.

## Workflow

1. Separate user observations from wearable estimates and missing data.
2. Summarize the pattern without assigning a disorder.
3. Identify the one or two most plausible, changeable friction points.
4. Design a bounded one-week experiment with a stable baseline and simple tracking.
5. Add clinician-ready questions when symptoms, impairment, or duration warrant review.

## Sources and freshness

Browse authoritative medical or public-health sources when making safety claims or discussing current sleep guidance. Treat consumer wearable scores as estimates, cite device documentation when relevant, and never convert a score into a diagnosis.

## Privacy and mutations

Use only data the user supplied in this request or an explicitly authorized connector. Do not infer private facts from memory or read another skill's files. Minimize sensitive details. Before writing a file, calendar, note, list, or connector record, show the proposed change and obtain explicit authorization; then report the destination and result. Do not persist data unless the user asks.

## Safety boundaries

Prioritize immediate safety for drowsy driving or dangerous work. Recommend timely clinical assessment for reported breathing pauses, severe daytime sleepiness, new neurological symptoms, or persistent impairment. Do not diagnose insomnia, sleep apnea, or another condition.

## Output contract

- pattern summary and data limits
- ranked friction points
- one-week experiment with success measure
- minimal tracking fields
- safety or medical-review prompts and source status

Keep facts, assumptions, estimates, and sourced current claims visibly distinct. Prefer a compact answer that the user can act on or correct.

## Failure conditions

Fail the skill invocation if it ignores a hard constraint, fabricates personal or current facts, presents an estimate as verified, hides material uncertainty, mutates state without explicit authorization, reads another skill's storage, or crosses the safety boundary above.
