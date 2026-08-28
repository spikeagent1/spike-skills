---
name: sleep-review
description: "Use when sleep is the problem: six broken hours and waking tired, late caffeine or a phone in bed, shift rotation, a wearable sleep score to make sense of, or a bounded experiment to test one change. Not for training load (fitness-coach) or preparing a clinician visit (health-appointment-prep)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Sleep Review

## Overview

Produces a read of the nights and one bounded experiment: the pattern, the one or two frictions worth changing, and a week of tracking small enough to finish. A pattern is never turned into a disorder. What the owner reports, what a device estimated, and what is missing stay three visibly separate things.

## When to use

- "Six hours, coffee at four, phone in bed, shattered every morning — where do I start?"
- Designing a one- or two-week experiment that tests a single change
- Reading back a stretch of sleep notes: what actually changed, what did not
- Making sense of a wearable's sleep score, stage breakdown, or readiness number
- Shift rotation, jet lag, a newborn, or anything that breaks a fixed night
- Writing clinician-ready notes when the nights warrant medical review

## When not to use

- Where the training sessions sit in the week, or how hard to train on poor sleep → use `fitness-coach`
- A dated record of doses, symptoms, or how each day felt → use `medication-and-symptom-log`
- A clinical visit is the point and the ask is the brief, the timeline, or the questions → use `health-appointment-prep`
- Naming insomnia, apnea, or another condition, or writing a note that excuses work → no professional determination is made here (S1); name the clinician, then keep working the habits and the tracking
- Falling asleep at the wheel, or witnessed breathing pauses with severe daytime sleepiness → escalation path only, the habit experiment stops (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| Sleep and wake times across a typical week, work days and free days | yes | ask once, in the same turn as a read built on the times stated so far, labelled |
| What the owner notices: awakenings, how the day goes, naps, caffeine, alcohol, wind-down | yes | ask once, in the same turn as a read that names which friction the answer would confirm (X1) |
| The rotation itself, whenever nights are not fixed | yes | ask once, in the same turn as a version assuming no fixed night; never impose a conventional night on a rotation (X1, X2) |
| Device figures | no | use only what was supplied, always as an estimate; a stage, a score, or an hour nobody gave is never inferred (X3, P2) |
| Room, household, and the commitments that fix the times | no | continue on labelled assumptions (O2) |

**Dependencies:** none beyond the contract; sleep-related boundaries already in the `profile` namespace are read when present, and no other namespace is touched (P3). A wearable, notes, or habit-log connector is read only when the owner names one this turn (D1).

## Workflow

1. Write the read and the experiment into this message before asking anything, on labelled assumptions; a question about times, rotation, or caffeine rides alongside them, never in place of them, and "I'll design it once you send a week of data" is not designing it (O2).
2. Screen for the acute red flags first — drowsy driving, witnessed breathing pauses with severe daytime sleepiness, new neurological symptoms — which stop the routine review and leave the escalation path (S2).
3. Sort what was reported from what a device estimated from what is missing, and keep the three apart everywhere downstream (O2).
4. Describe the pattern in the owner's own units — time in bed, sleep as reported, how far work days and free days drift apart — and name no condition (S1).
5. Rank the one or two frictions that are both plausible and changeable this week, and say what changing each one costs.
6. Design one bounded experiment: a single change, a baseline first, a fixed end date, one success measure, and the fewest tracking fields that can answer it.
7. Close with the threshold that sends this to a clinician and, when the nights already meet it, the clinician-ready note itself, written out here.

## Output contract

The read and the experiment are in this message, not promised for the next one: a description of the experiment, an announcement that it is coming, or a request for a week of data first is a failure to deliver it. In order: any safety item that changes what to do tonight (O1); the pattern summary with its data limits, reported facts and device estimates visibly apart (O2); the ranked frictions; the experiment — one change, its baseline, its end date, its success measure; the tracking fields, named and minimal; the clinician-review threshold and, when it is met, the note itself; and a source or a labelled uncertainty beside any claim about risk or current guidance (F1, F3).

Report the review as **read** (the pattern is described from what was supplied), **assumed** (a labelled assumption stands in for an input), or **escalated** (an acute red flag) — never a later state than reached (O3). **Escalated** carries the escalation path and the clinician-ready note written out in this turn; what stops is the habit experiment, not the turn.

## Sources and freshness

A claim about risk — drowsy driving, sleep-disordered breathing, what a substance does to sleep — comes from a public-health body's or a professional clinical organisation's current guidance, never from recall (F2), timestamped beside the claim (F3). Labelling the uncertainty is not a substitute for that lookup (F1): with none available, give the version that does not turn on the figure and name what to confirm. A consumer device's score is a vendor composite over motion and heart rate, not a measurement: cite the vendor's own documentation for what it contains, treat every stage figure as an estimate, and never convert a score into a condition (S1, O2).

## Privacy and mutations

Read-only. Times, habits, household details, and anything a partner observed come from this turn, from a connector the owner names this turn, or from owner-stated preferences in the `profile` namespace — never from memory (P2), never from another skill's files (P1, D3). What happens in a bedroom is intimate: keep the least detail that makes the read work, and carry a partner's observation only as the owner relayed it (P4). Creating a nightly note or a repeating reminder is not an effect declared here (M8): show the exact text in this turn — the note's fields as they would read, and each reminder with its day, time, and wording, built on labelled assumptions when the experiment's details were not supplied — then take explicit authorization for that exact action (M2, M6), reporting only the state read back (M4, O3). Asking where the note should live, or promising the text once the tracking is agreed, is a deferral rather than a preview.

## Safety boundaries

- Drowsy driving, or operating machinery while impaired, is immediate: the routine review stops and only the escalation path is given (S2) — do not drive or operate while sleepy, stop somewhere safe, and get prompt clinical assessment. The clinician-ready note is part of that path and is written out in the same turn.
- Witnessed breathing pauses, gasping, severe daytime sleepiness, or persistent impairment: name the clinical assessment as prompt, organise the observations for it, and name no condition (S1).
- Insomnia, apnea, restless legs, narcolepsy, a circadian disorder: none is diagnosed or ruled out here (S1); the habit work and the tracking are still delivered.
- No sleep medication, supplement, or alcohol is started, stopped, or dosed here; that question goes to the prescriber or pharmacist (S1).
- A rotation is worked with, never against: the experiment fits the rota as stated, and where the rota is unstated the assumption is labelled rather than a fixed night imposed (X1, X2).

## Failure conditions

Fail closed — name what is missing, then give the part of the read that is safe without it — when the rotation or the times are ambiguous and the advice turns on them (X1); when a stage, a score, an hour, or any device figure would have to be invented (X3); when a fixed constraint — a start time, a newborn, a shared room — makes the experiment unusable (X2); or when a note or reminder write lacks authorization for that exact action this turn (X4). An acute red flag is the one case where the routine review is not delivered: the escalation path and the clinician note stand alone (S2).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Asking for a week of data before saying anything | The read and the experiment are the deliverable; another week of unstructured nights answers nothing | Give both on the times stated, then name the field that would sharpen them |
| Reading a wearable score as a condition, or its stages as measurements | The number is a vendor's arithmetic over motion and heart rate, not a sleep study (S1) | Say what the number contains, then work from the reported pattern |
| Prescribing a 10pm-to-6am routine to someone on rotating nights | A fixed night the rota contradicts is unusable, and following it costs sleep | Build around the rotation as stated; where it is unstated, label the assumption and ask |
| An experiment with five changes and a month of tracking | Nothing is attributable and nobody finishes it | One change, one week, one success measure, the fewest fields that answer it |
| Treating "almost fell asleep driving" as one more data point in the review | Drowsy driving is the acute risk in this domain and it is happening now (S2) | Escalation path first and alone, with the clinician-ready note in the same turn |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
