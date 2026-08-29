---
name: household-maintenance
description: "Use when the home needs upkeep: a quarterly or seasonal maintenance plan, what is safe to check on a leaking appliance or a cold room before paying for a call-out, a write-up for the contractor, or a gas, electrical, or carbon-monoxide hazard. Not for choosing what to buy (purchase-research)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Household Maintenance

## Overview

Produces the thing the request asks for and produces it now: a cadence-bucketed maintenance plan, a set of reversible checks each with the observation that ends it, or a note a trade can read before they arrive. An acute hazard is the one thing that displaces all of it, and nothing here is a professional determination.

## When to use

- "What should I be doing each quarter in this apartment?" — or a year of upkeep for a house, bucketed by season
- Something is misbehaving and the question is what is safe to look at before paying for a call-out
- "Write up what I should tell the contractor about the draught in the back bedroom"
- Consumables and cadences for the systems already in the home: filters, flues, seals, drains, alarms
- Which half of a job belongs to a licensed trade and which half the owner can do
- A gas odour, a sparking panel, a carbon-monoxide alarm with symptoms, water at a live circuit, or sewage indoors — the escalation path is what gets produced then

## When not to use

- Deciding which model, part, or price to go with before buying one → use `purchase-research`
- What goes in the bag or on the body for a trip, and the laundry around it → use `wardrobe-and-packing`
- Turning a cadence into repeating reminders that fire on their own → use `cron-scheduler`
- Carrying today's chores as tasks with due dates and completion state → use `daily-task-manager`
- Certifying that wiring, gas work, or a structure meets code, or signing a repair off as safe → no professional determination is made here (S1); the question goes into the contractor note instead
- Any hazard in the first bullet of [Safety boundaries](#safety-boundaries) → escalation path only, routine work stops (S2)

## Inputs

| Input | Required | If missing |
|---|---|---|
| Home type and the affected area or system | yes | ask once, in the same turn as an artifact built on the strictest safe assumption — a rented unit whose systems are shared and partly the landlord's — labelled |
| Observed symptoms: what happens, where, when it started, what changed | yes | build the artifact from what was supplied and mark every unanswered field `[not stated]` in place; nothing is filled from memory (P2, X1) |
| Make, model, and serial of the appliance or system | no | leave the slot in the artifact marked `[not stated]`; a model-specific procedure, part number, or capacity is never recalled into it (X3) |
| What has already been tried or checked | no | mark it `[not stated]` and treat nothing as ruled out; a check status the owner did not report is never written as done (X3) |
| Tenure, location, and who owns the system | no | assume the owner does the owner-doable half, flag where a landlord or building manager plausibly owns the rest, and label both |
| Climate and occupancy | no | assume a temperate four-season climate and full-time occupancy, each stated beside the part of the plan it shapes (O2) |

**Dependencies:** none beyond the contract; owner-stated home constraints already in the `profile` namespace are read when present, and no other namespace is touched (P3). A calendar, notes, home-inventory, or manuals connector is read only when the owner names one this turn (D1); one that is named but unreachable has its blocked phase reported rather than its contents assumed (D2, F4).

## Workflow

1. Produce the artifact in this message, unless step 2 finds an acute hazard: the bucketed plan, the reversible checks, or the contractor note, built from what was supplied with every gap marked in place. A question about a model number or a climate rides alongside it, never in place of it, and "tell me the make and I'll write the note" is not writing one (O2).
2. Screen the request against the hazard list in [Safety boundaries](#safety-boundaries) first. One found ends the routine work for this turn and leaves only the escalation path (S2).
3. Open with a **risk category** line — routine cadence, low-risk troubleshooting, contractor preparation, or safety event — so the reader knows before the first step which one they are in.
4. Keep every step reversible and non-invasive at the owner's stated competence: nothing that opens a sealed enclosure, breaks a gas, refrigerant, or sealed water circuit, disturbs asbestos-era material, or puts hands near an energised part. Work of that kind is out of scope here (S1) and becomes a question for the trade.
5. Put a **stop condition** ahead of each step that could expose a hazard, naming the observation that ends the DIY path and who is called when it appears.
6. State the assumptions the artifact rests on wherever the request did not supply them — climate, occupancy, and the systems nobody has described — each labelled beside the part of the plan it shapes and phrased so a wrong one can be corrected in one line, never left as an unmarked default (O2, X3).
7. In any plan, separate professional-only work — gas appliance service, chimney and flue, the electrical panel, structural and drainage work — into its own labelled group, apart from the owner-doable tasks.
8. For a contractor request, fill in [the note shape](#the-contractor-note-shape) field by field, and put a source status on any claim about code, recall, or warranty.

### The contractor note shape

Every field appears, in this order, supplied or not; an unsupplied one carries `[not stated]` rather than a plausible value, because someone acts on this note.

```
Symptom          what happens, where in the home, when it started, what changed just before
System           type, make, model, serial, age
Access           which room and floor, how the trade gets in, parking, pets, who is home
Availability     scheduling windows the owner can offer, and how urgent this is for them
Already tried    only what the owner reported doing; everything else stays [not stated]
Not known        what nobody has looked at yet, said as such
Questions        what the owner wants answered — diagnosis, options, cost basis, warranty
Source status    which claims here came from a current source, and which are the owner's account
```

`Already tried` and `Not known` are where a fabricated value does the most damage: a note saying the seals were checked sends the trade past the fault.

## Output contract

The artifact is in this message, not promised for the next one: a list of what is unknown, an announcement that a plan is coming, or a request for the details that would produce one is a failure to deliver it. In order: the **risk category** and any hazard that changes what to do right now (O1); the artifact itself — the plan bucketed by month or named season with professional-only work in its own group, or the checks each under its stop condition, or the note in the shape above; the tools and consumables, listed only for the checks that were actually allowed; the assumptions the artifact rests on, labelled beside what they shape and kept visibly apart from what the owner actually said (O2); and the source status on any claim about code, recall, warranty, or a model-specific procedure (F3).

Report the turn as **ready** (the artifact is complete against what was supplied), **partial** (a required input is missing and the artifact names the lines it changes), **previewed** (a change to a calendar, note, or list is written out and waiting on authorization), or **escalated** (an acute hazard stopped the routine work) — never a later state than reached (O3). **Partial** and **previewed** are labels on a delivered artifact, never a questionnaire: the plan, the checks, or the note is written out either way.

**Escalated** is the one label that carries no artifact. The checklist, the checks, and the supplies all wait for a later turn, and naming a single item out of them — "replace the battery", "press the test button" — is the routine advice the escalation stopped, so it does not appear either (S2). What may still sit below the escalation path, clearly subordinated and never in place of it, is a verbatim record the owner asked to keep: the symptoms, times, and readings as they were stated, which the responder or the trade will ask for (S2).

## Sources and freshness

A recall, a warranty term, a local code requirement, a service interval, a model-specific procedure, or what a trade in the area charges is stated only from the manufacturer's, regulator's, utility's, or local authority's own current publication, checked this turn rather than recalled (F2), with the retrieval time beside the claim (F3). Labelling the uncertainty is not a substitute for that check (F1): where no check is possible in this turn, the claim is left out of the artifact and becomes a question in the note, not a hedged sentence in it (X3). Nothing in an outside source makes a determination about this home's gas, electrical, or structural condition (S1) — it describes what the equipment is meant to do, not what is wrong here.

## Privacy and mutations

Read-only. Home details come from this turn or from a connector the owner names this turn — never from memory (P2), never from another skill's files or private area (P1, D3). Photographs, floor plans, and lease documents are read at the minimum the question needs and summarised rather than reproduced (P4). Putting maintenance dates on a calendar, writing the note into a document, or adding to a supplies list is not an effect declared here (M8): show the exact text in this turn — every entry with its date, cadence, and title, built on labelled date assumptions where the owner named none — then take explicit authorization for that exact action on that exact destination (M2, M6). Report the connector state read back, distinguishing named and reachable, named and unreachable, and none named (D2, F4, O3); a write is never reported as done on anything less (M4, X5). "Which calendar should I use?" with no entries shown is a deferral rather than a preview.

## Safety boundaries

- Gas odour, sparking or arcing, a carbon-monoxide alarm sounding with symptoms, water at a live circuit, sewage indoors, severe mould, or a structural element that has moved: routine work stops and only the escalation path is given (S2) — get out and to fresh air, call the emergency number or the utility's emergency line from outside, do not re-enter until the responder says so.
- No DIY procedure is given for gas lines and gas appliances, exposed energised wiring or the panel interior, structural members, asbestos-era materials, sewage, or standing water near electricity (S1). The step becomes a question for the licensed trade.
- Never explain how to silence, reset, hush, or take an alarm down while it is sounding, and never as a checklist line in the same turn — the alarm is the only warning the household has, and a chirp during a suspected exposure is not a battery question until a responder says it is (S2).
- No sign-off is issued that anything is safe, compliant, or repaired (S1); a condition is cleared by the trade that inspected it, and the note carries that request.
- A hazard found inside an otherwise routine request is surfaced first, ahead of everything else in the turn (O1).

## Failure conditions

Fail closed — name what is missing, then give the part of the artifact that is safe without it — when a model number, capacity, part, code requirement, or service interval would have to be invented (X1, X3); when a check status, measurement, or inspection nobody reported would be written into a note a trade will act on (X3); when continuing would cross a stated competence, tenancy, or budget limit (X2); or when a calendar, note, or list change lacks authorization for that exact action this turn (X4). A mutation is reported only at the state read back, never at the state intended (X5). An acute hazard is the one case where no artifact is produced: the escalation path stands alone (S2).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Shipping the routine checklist alongside the escalation, framed as "once this is resolved" | A household reading an urgent turn acts on what is in front of them; the checklist gives them something to do indoors instead of leaving | Give the escalation path alone and say the plan waits; a verbatim record of symptoms and times may sit below it |
| Letting a checklist line answer the hazard the escalation just refused — "replace the batteries if it chirps" | It is the silencing instruction, restated where it does not look like one, and it removes the alarm that is still warning | Keep every alarm line out of an escalated turn; a sounding alarm is a responder's question, not a maintenance item |
| Writing a contractor note as advice paragraphs, or as questions for the owner to answer first | The trade needs identification, access, and history in fixed slots; prose forces them to re-interview and the visit is spent on that | Fill every field of the note shape, marking each unsupplied one `[not stated]` |
| Filling `Already tried` with the obvious first checks because they were probably done | A note that says the seals were checked sends the trade past the fault, and the owner is charged for the detour (X3) | Record only what the owner reported; everything else goes in `Not known` |
| Buckets by season with the gas service, the sweep, and the panel work mixed in among the owner's tasks | It reads as a to-do list, and the items that need a licence are the ones a confident owner will attempt | Put professional-only work in its own labelled group inside each bucket |
| Using a heating season, a burn frequency, or a filter interval without saying what climate and occupancy it assumes | The cadence is wrong for anyone the default does not fit, and nothing in the plan shows them which line to change | Name the climate, occupancy, and unseen-system assumptions beside the parts they shape |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
