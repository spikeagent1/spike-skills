---
name: medication-and-symptom-log
description: "Use when the record itself is the ask: starting a medication or symptom diary, adding today's doses and how the day went, or summarising entries kept so far — what shows up most often, and when. Not for deciding a dose, working out what causes a symptom, or visit questions (health-appointment-prep)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: [journal]
    effects: [datastore:read, datastore:write, fs:write-local]
---

# Medication And Symptom Log

## Overview

Produces the record and what it shows: a dated entry in a fixed shape, the shape itself, or a summary of the entries kept — what appears, how often, in what order. Structure only; nothing here says what an entry means, names a cause, or touches a dose. Every write is shown as the exact text it would add, in the turn that asks for it.

## When to use

- "I start a new medication tomorrow — how do I keep track of doses and how I feel?"
- Adding today: what was taken, what was missed, what was felt, and when
- Summarising a stretch of entries: what shows up most often, on which days, in what order
- Fixing the shape of the record — fields, units, a severity scale — so entries stay comparable
- Noting a missed or skipped dose without deciding what to do about it

## When not to use

- The visit is the point — the brief, the timeline for the clinician, the questions to ask → use `health-appointment-prep`
- Sleep is the subject and the ask is the pattern or an experiment, not an entry → use `sleep-review`
- Training load, soreness, and how the week's sessions went → use `fitness-coach`
- What caused a symptom, whether a medication is working, or what a pattern means → no professional determination is made here (S1); the entries and the question go to the clinician or pharmacist
- Whether to take, skip, halve, double, catch up on, or stop a dose → a prescribing decision (S1); the record notes what happened and the prescriber, pharmacist, or label answers what next
- Trouble breathing, fainting, a rapidly spreading rash, a suspected overdose, or any acute symptom → escalation path first and alone, routine logging waits (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| What is wanted: the shape to fill, an entry to add, or a summary of entries | yes | ask once, in the same turn as the shape, built to the strictest safe default and labelled |
| The entry's own content — date and time, item, dose or symptom, severity, trigger, note | yes, to add | render the entry anyway, every unsupplied field written `unknown`, and name which line the answer fills (X1, X3) |
| The entries themselves, for a summary or a question about them | yes, to summarise | render the events the request itself names as entry lines in the stated order, `unknown` where times are missing, and name what was not supplied (X1, X3) |
| Destination: an owner-named local path, or the `journal` namespace | yes, to write | propose one, show the exact text against it, and take authorization for that exact write (M2, X4) |
| Severity scale, units, the owner's day boundary | no | assume the owner's own words and a plain 1–10 scale, labelled (O2) |

**Dependencies:** none beyond the contract; owner-stated boundaries already in the `profile` namespace are read when present. A notes, files, or medication-log connector is read only when the owner names one this turn (D1). Entries land in the `journal` namespace or an owner-named local path and nowhere else — there is no default, shared, or hidden health database here, and no other skill's namespace or files are touched (D3, P3).

## Workflow

1. Write the entry, the shape, or the summary into this message before asking anything — the exact text, with `unknown` in every field the request did not supply; a question about the date, the dose, or the destination rides alongside it, never in place of it, and "send me the entry and I'll show you the preview" is not showing one (O2).
2. Screen the content for acute symptoms before anything else: one found leads the turn alone as advice, the escalation path with nothing added to it (S2, O1) — the entry is still rendered verbatim below it, clearly subordinated, because a record is not advice; rendering it is not writing it, and the write still needs its own authorization (M2).
3. Record only what was supplied, field by field, in the owner's own wording; a field nobody answered is `unknown` and a dose the owner chose not to take is `skipped` — the two are never merged and neither is filled from memory (P2, X3).
4. Keep medication events and symptom events on separate lines of one timeline, in the order the owner stated, so the sequence survives without anything being claimed about it. When the log itself was not supplied, the events the request names — a medication started, a symptom that began after it — are rendered as entry lines in that stated order with `unknown` times: "there is nothing to order" is never the answer to a request that names two events (X3).
5. For a summary: count what appears, say when it appeared, and stop there — no cause, no trend, no improvement or worsening, no correlation offered as one (S1, X3).
6. Show the exact text and the exact destination, take authorization for that write (M2), then write, read back, and report only the state read back (M4, O3).
7. Close with the questions the entries raise for the clinician or pharmacist, and the fields still to fill.

### The entry shape

Six fields per event, so entries stay comparable and a summary can count them: date with local time; kind; the item — a medication with its dose and route, or the symptom in the owner's words; the state — `taken`, `missed`, `skipped`, or `unknown` for a medication, severity and duration for a symptom; the trigger or context the owner named; and a free note in the owner's own wording.

```
<date> <local time> | medication | <name> <dose> <route> | taken|missed|skipped|unknown | trigger/context: <as stated> | note: <owner's words>
<date> <local time> | symptom    | <owner's words>      | severity <n>/10, duration <as stated> | trigger/context: <as stated> | note: <owner's words>
```

Anything the owner did not supply is written `unknown` rather than guessed or dropped — a field with no value is still a field — and the owner's own severity words are kept beside any scale.

## Output contract

The entry, the shape, or the summary is in this message, not promised for the next one: a description of the fields, an announcement that a preview is coming, or a request for the content that would produce one is a failure to deliver it. In order: any acute symptom, first and alone as advice (O1, S2); the artifact itself — for an add, the exact lines that would be written, verbatim, `unknown` in every unsupplied field; for a shape, the fields with one filled example line; for a summary or any question about what the entries show, the events in time order with medication and symptom on their own lines — including the events the request itself names when no log was supplied — then the counts; the destination path or namespace, proposed when the owner has not named one, with the change shown against whatever is already there; the questions for the clinician or pharmacist; and the fields still to fill.

Report each write as **previewed** (the exact text is shown, authorization pending), **written** (authorized, performed, and read back from the destination), or **blocked** (no destination, or no authorization for that exact write) — never a later state than reached (M4, O3). **Previewed** and **blocked** both still carry the full entry text in this turn: the preview is the deliverable, and no state beyond the one read back is ever reported (O3).

## Sources and freshness

Official medication instructions — the label, the dispensing pharmacy, the regulator, the prescriber's own directions — are the only sources for what a medication is or how it is taken, read this turn rather than recalled (F2) and timestamped beside the claim (F3); labelling the uncertainty is not a substitute for that lookup (F1). A general web result is never the basis for anything about a dose (S1). Nothing external is consulted to explain a symptom: an entry is a record, and the explanation is the clinician's (S1).

## Privacy and mutations

Mutating, inside one boundary: entries go to the `journal` namespace or an owner-named local path, and nowhere else (P3, M8). Every write is previewed as the exact text this turn — the lines as they would appear, `unknown` where content was not supplied — against the exact destination, proposing a path when the owner has not named one and showing the change against what is already there; only then is authorization taken for that exact write (M2, M6). Asking which path to use, or promising the preview once the entry arrives, is a deferral rather than a preview. Authorization covers the write named in this turn and nothing else: another entry, another destination, or the same entry again later each need their own (M5, M6). An append is keyed by date, time, and item, so the identical entry twice is one entry rather than two (M3); an overwrite is previewed against what it replaces, which it destroys. After the write the destination is read back and only the state read back is reported (M4, O3). Health detail is minimised inside the record too: the owner's words about what happened, never a raw transcript, a clinical document, an account identifier, or a credential (P4, P6).

## Safety boundaries

- No dose decision is made here in any direction — starting, stopping, halving, doubling, tapering, catching up, shifting a time (S1); the record notes what happened, and the prescriber, pharmacist, or label answers what to do about it.
- No cause is named for anything in the record: not an allergy, a hypersensitivity, an adverse reaction, a side effect, or an interaction, and not as a possibility, a pattern, a hedge, or a "consistent with" either (S1, X3). Two entries close together in time are two entries; the causal question is written down for the clinician instead.
- Trouble breathing, fainting, a rapidly spreading rash, chest pain, a suspected overdose, or any symptom the owner calls severe: urgent local help now, first and alone as advice (S2). The entries are preserved verbatim below it, unchanged and uninterpreted.
- A summary counts and orders. It never claims a trend, an improvement, a worsening, or that a medication is or is not working (S1, X3).

## Failure conditions

Fail closed — name what is missing, then give the part of the record that is safe without it — when a write was asked for and the destination is unnamed or ambiguous (X1, X4); when a date, a dose, a time, or an entry nobody supplied would have to be invented (X3); when the owner asks for a causal or dosing conclusion the record cannot support (X2); when the readback of a write is unavailable (X5); or when a write would land anywhere but the `journal` namespace or the owner-named path (X2, X4). An acute symptom leads the turn alone as advice (S2); the record itself is still written out below it.

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Promising to show the entry once the content arrives | The preview is what authorization is given for, and a write nobody has seen cannot be authorized (M2) | Render the exact lines this turn with `unknown` in every unsupplied field, against a proposed destination |
| Linking a rash and a breathing symptom into a "possible reaction", even hedged | Naming a cause is a clinical determination, and the hedge does not survive: the pattern is what gets repeated to the clinician as fact (S1) | Escalate the acute symptom, keep the entries side by side in time order, and write the causal question down for the clinician |
| Answering "there is nothing to order" when the log was not attached, or offering a blank template instead | The request itself names events in an order, and that order is a record; a template preserves nothing | Render those events as entry lines in the stated order with `unknown` times, then name what was not supplied |
| Answering a missed-dose question with a catch-up rule | Dosing is the prescriber's decision, and a wrong catch-up is a double dose (S1) | Log the miss with its time, and put the question to the prescriber, pharmacist, or label |
| Writing into a "default health database" because the request named one | No shared or default destination exists here, and a health record in the wrong place cannot be taken back (D3, P3) | Name the `journal` namespace or an owner-given path, show the exact text, and take authorization for that exact write |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
