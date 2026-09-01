---
name: health-appointment-prep
description: "Use when a clinical visit is the point: fifteen minutes with a doctor on Thursday, a one-page timeline a clinician can read fast, what to ask about a treatment or a result, what records to bring or verify first. Not for keeping the daily record of doses and symptoms (medication-and-symptom-log)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    capabilities: [datastore:read]
---

# Health Appointment Prep

## Overview

Produces what the owner walks in with: a brief short enough to be read inside the visit, a chronology in their own words, ranked questions, and the records still to verify. Nothing is diagnosed and no gap is filled from memory — an unanswered field is marked in place, and the brief is written anyway.

## When to use

- "Fifteen minutes with my doctor on Thursday about headaches — what do I walk in with?"
- Questions for a specialist: switching treatment, weighing options, a result to have explained
- Compressing a stretch of notes into a one-page timeline a clinician can read fast
- Naming the decision the visit has to reach, so the appointment ends with an answer
- What to bring — medications, allergies, results, referrals — and what still needs verifying

## When not to use

- The running record itself — today's doses, today's symptoms, a month of entries to summarise → use `medication-and-symptom-log`
- Broken nights and what to change about them, with no visit in play → use `sleep-review`
- Training around an injury or a lay-off, rather than preparing to discuss it → use `fitness-coach`
- Naming a cause, reading a result, or advising a medication change → no professional determination is made here (S1); the question goes onto the list for the clinician instead
- Sudden worst-ever headache, one-sided weakness, chest pain, severe breathlessness, or loss of consciousness → escalation path only, routine preparation stops (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| The visit: type, when, clinician or specialty | yes | ask once, in the same turn as a brief written for a short primary-care visit, labelled |
| The main concern, and the decision the owner wants from the visit | yes | ask once, in the same turn as a brief that marks the decision unstated and ranks the questions for the concern as given (X1) |
| Timeline, severity, triggers, associated symptoms, what was already tried — in the owner's words | yes | write the brief from what was supplied and mark every unanswered field in place as `[not stated]`; never fill one from memory (P2, X3) |
| Medications, allergies, results, records | no | list them as **to verify** and name where each is verified from; nothing is recalled into the list (X3) |
| Visit length | no | assume fifteen minutes, labelled, and cut the brief to fit it |

**Dependencies:** none beyond the contract; owner-stated boundaries already in the `profile` namespace are read when present, and no other namespace is touched (P3). A calendar, notes, or records connector is read only when the owner names one this turn, and only for the subset this visit needs (D1, P4).

## Workflow

1. Write the brief into this message before asking anything — the paragraph, the timeline, the ranked questions — from what was supplied, each gap marked in place; a question about a date or a dose rides alongside it, never in place of it, and "share the details and I'll refine this into a brief" is not writing one (O2).
2. Screen the supplied text for urgent red flags first; one found ends the routine preparation and leaves only the escalation path (S2).
3. Keep the owner's wording and chronology intact, and label each entry by where it came from — the notes or the recollection — never merging the two (P2, O2).
4. Sort what was given into facts, uncertainties, worries, goals, and questions, and keep the five apart.
5. Cut the brief to the visit's length: one paragraph a clinician reads in under a minute, then the timeline, then the questions ranked so the top one survives a short visit.
6. Turn every discrepancy, uncertainty, or thing the owner cannot answer into a question addressed to the clinician — phrased as a question, ending in a question mark — and rank it with the others (X3).
7. Close with the records and medication details still to verify, and where each one is verified from.

## Output contract

The brief is in this message, not promised for the next one: a list of what is unknown, an announcement that a brief is coming, or a request for the details that would produce one is a failure to deliver it. In order: any red flag that changes what to do today (O1); the brief itself — one short paragraph built from what was supplied, each unanswered field marked `[not stated]` in place; the chronology in the owner's words, every entry attributed to the notes or to recollection (O2); the ranked questions, each one an actual question; medications, allergies, and records split into supplied and **to verify**; and the source status beside any claim taken from outside the owner's own account (F3).

Report the brief as **ready** (it fits the visit and every field is either supplied or marked), **partial** (a required answer is missing and the brief names the line it changes), or **escalated** (a red flag stops routine preparation) — never a later state than reached (O3). **Partial** is a label on a delivered brief, never a questionnaire and never an empty turn: the paragraph, the timeline, and the ranked questions are written out either way.

## Sources and freshness

An outside source earns its place twice here: to say why a symptom needs urgent evaluation, and to state what the visit or procedure requires — fasting, a referral, records to bring. Each comes from the clinical body's or the practice's own current guidance rather than recall (F2), timestamped beside it (F3), and labelling the uncertainty is not a substitute for that check (F1). No source is consulted to work out what the owner has (S1). A personal fact that is absent stays absent and is marked as absent, never reconstructed (P2).

## Privacy and mutations

Read-only. Health facts come from this turn or from a connector the owner names this turn — never from memory (P2), never from another skill's files or private storage (P1, D3). A records connector is read at the minimum the visit needs, named item by item; an unfiltered read of everything is not what a fifteen-minute visit requires and is not performed here, whatever the phrasing of the request (P4, X2). Passing records or a message to a clinician, a portal, or a family member is not an effect declared here (M8): show the exact text in this turn — the message as it would read and every item it would carry, built on labelled assumptions when the owner has not said what to include — then take explicit authorization for that exact action and that exact recipient (M2, M6), reporting only the state read back (M4, O3). Asking which address to use, or promising the text once the record list is agreed, is a deferral rather than a preview. Nothing is kept past this turn: the durable record belongs to `medication-and-symptom-log`.

## Safety boundaries

- Sudden worst-ever headache, one-sided weakness or numbness, chest pain, severe breathlessness, fainting, or loss of consciousness: routine preparation stops and only the escalation path is given (S2) — urgent local emergency help now, not an appointment later. No brief for a future visit goes in its place; the time the symptoms started goes with the escalation.
- No cause is named, ranked, or hinted at, and no result is interpreted (S1): the possibility the owner is worried about becomes a question for the clinician, not an answer from here.
- No medication is started, stopped, held, or adjusted, including before a procedure (S1); that instruction comes from the prescriber or the surgical team, and the brief carries the question to them.
- A red flag found inside an otherwise routine request is surfaced first, ahead of everything else in the turn (O1).

## Failure conditions

Fail closed — name what is missing, then give the part of the brief that is safe without it — when a date, a dose, or a result would have to be invented or chosen between (X1, X3); when a records read would exceed what the owner authorized (X2, X4); when the owner asks for a certainty their own account does not support (X2); or when passing anything to a third party lacks authorization for that exact action this turn (X4). An acute red flag is the one case where no brief is produced: the escalation path stands alone (S2).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Answering with a gap list and an offer to refine it later | The brief is what the owner carries into the room; a catalogue of unknowns does not survive a fifteen-minute visit | Write the paragraph, the timeline, and the ranked questions from what was supplied, marking each gap in place |
| Smoothing a discrepancy into a certain-sounding line, or picking the likelier date | A tidy timeline the owner cannot stand behind misleads the clinician who acts on it | Keep both, attributed to the notes and to recollection, and put the discrepancy to the clinician |
| Leaving that discrepancy as a declarative note in the script | A statement nobody is asked to act on gets nodded at rather than resolved | Phrase it as a question ending in a question mark and rank it with the others |
| Reconstructing a medication list from memory because the owner asked | An invented dose in a pre-operative brief is a medication error (X3) | List only what was supplied, mark the rest **to verify**, and name where to verify each |
| Reading or forwarding the whole record because the owner said "everything" | Minimum necessary is the standard for health data, and the visit needs a subset (P4) | Name the subset, show exactly what would go and to whom, and take authorization for that exact set |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
