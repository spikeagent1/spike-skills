---
name: "briefing"
description: "Make briefings truly read-only, current, coverage-aware, conflict-aware, and cited."
mutating: false
---

# Briefing

Compile an owner briefing without advancing cursors, modifying pages, or inventing current events from stale context.

## Read-only boundary
Every operation in this skill is read-only. Do not use commands that advance recall cursors, write checkpoints, create pages, enrich entities, schedule jobs, or send messages. If the owner asks to save, distribute, or update something from the briefing, route that as a separate authorized mutation after presenting the briefing.

## Establish the frame
Resolve the current date, owner timezone, requested briefing horizon, and available connected sources. For time-sensitive calendar, task, inbox, weather, or market claims, query their authoritative current source. A stale cache is not current evidence. If an authoritative source is unavailable, mark that section unavailable rather than filling it from memory.

## Coverage ledger
Before composing, record which sources were queried, their freshness, pagination status, and failures. Follow pagination and bounded time windows appropriate to the section. Distinguish no results from source unavailable, permission denied, stale cache, and query failure.

## Brain context
Use current brain search/query/get and timeline reads for participant history, active work, commitments, recent changes, and personal preferences. Do not use recall modes that mutate a since-last-run cursor. Use an explicit time range or a read-only snapshot.

For each factual claim, cite source ID, slug or external object ID, and update/event time. If sources conflict, present the conflict and source timestamps; do not silently select the more convenient claim. Flag stale context in place.

## Priority logic
Prioritize:

1. events and commitments inside the briefing horizon;
2. overdue or blocked owner-visible tasks;
3. decisions or corrections since the previous relevant period;
4. people and projects connected to today's events;
5. anomalies or high-salience items only when their underlying evidence is current and relevant.

Salience and anomaly scores guide attention; they are not facts and do not create urgency by themselves.

## Meetings
Read the authoritative calendar for the full local-day range. Verify event status, time, timezone, attendees, location/link, and cancellations. Resolve attendees against brain context. Do not claim there are no meetings if calendar coverage is unavailable or stale.

## Tasks and commitments
Read the authoritative task provider when connected, then reconcile supporting brain context. Include due/overdue state and source identity. Do not present a local task mirror as current provider state unless provider readback is unavailable and the limitation is explicit.

## Output
Lead with data-quality warnings that could change decisions. Then provide:

- meetings and time-bound events;
- owner tasks and commitments;
- decisions/corrections and recent changes;
- people/project context;
- conflicts, gaps, and stale evidence.

Keep the briefing concise. Every item carries a nearby citation and freshness marker. Do not include empty decorative sections.

## Completion
A briefing is complete only when every requested authoritative source is either queried successfully or explicitly classified by failure/coverage state, all material claims are cited, time-sensitive data is current, and the run performed no mutation.

## Failure conditions
Fail review if the workflow advances a cursor; calls a write tool; uses stale calendar data as current; says no events from unavailable coverage; omits pagination; presents salience as fact; hides contradictions; or cites memory without source/freshness.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.
