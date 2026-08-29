---
name: wardrobe-and-packing
description: "Use when clothes are the question: what goes in the bag for a trip of a given length, outfits built from what is already owned, counts against laundry and a bag limit, layering for weather that moves, or a wardrobe gap that keeps recurring. Not for buying the jacket or the case (purchase-research)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [profile]
    writes_to: []
    effects: [datastore:read]
---

# Wardrobe And Packing

## Overview

Produces the bag and what goes on the body: an activity-to-outfit matrix, a counted list that fits the allowance, a rewear and laundry plan, and the gaps kept separate from what the owner already has. Only garments the owner named are treated as owned, and a forecast nobody checked is a labelled range rather than a fact.

## When to use

- "Four days, carry-on only, two client dinners and one gym session, no laundry — what goes in the bag?"
- Outfits from a named set of garments, worked around a brace, a cast, a sling, or a mobility aid
- Counts against trip length, laundry access, and a bag allowance, with the rewears made explicit
- Layering for weather that moves between a warm evening and a freezing flight
- "What keeps going wrong every winter?" — the recurring gap, told apart from an impulse buy
- Whether a bag is likely to pass as cabin baggage, and where that answer has to be verified

## When not to use

- Choosing between models, prices, or retailers for the coat or the case → use `purchase-research`
- Fixing or maintaining the thing rather than dressing around it — a garment coming out marked because an appliance is misbehaving, a wardrobe rail or a radiator that needs work → use `household-maintenance`
- Visas, passports, bookings, or the itinerary itself → out of scope here; the list names the papers to bring, and nothing here obtains, checks, or fills one in
- Whether a brace, a dressing, a device, or a medication may travel or be worn → no medical determination is made here (S1); the constraint is taken as the owner states it and planned around

## Inputs

| Input | Required | If missing |
|---|---|---|
| Trip length and the activities it has to cover | yes | ask once, in the same turn as a list built on the strictest safe assumption — the longest plausible trip and the most formal named activity — labelled |
| Bag allowance, and whether laundry is available | yes | assume a single cabin bag and no laundry, state it, and build the counts on it; a wrong assumption then changes only the count column (O2) |
| Garments the owner has confirmed owning | yes | treat nothing else as owned; the outfits use what was named and everything else appears under gaps (P1, X3) |
| Weather, or permission to check a forecast | no | build a layering plan across a stated range for the season and place, labelled as a range and never as a forecast (F1, X3) |
| Dress expectations for named events | no | assume the stricter of the plausible codes, say so, and note the one garment that would change if it is looser |
| Mobility, sensory, medical-device, religious, and cultural constraints | no | plan only around the constraints stated; none is inferred from a name, a place, or a photograph (P2) |

**Dependencies:** none beyond the contract; owner-stated clothing constraints already in the `profile` namespace are read when present, and no other namespace is touched (P3). A calendar, itinerary, weather, or photo connector is read only when the owner names one this turn and only for the subset the trip needs (D1, P4); one that is named but unreachable has its blocked phase reported rather than its contents assumed (D2, F4).

## Workflow

1. Produce the list in this message: the matrix, the counts, and the rewear plan, built from what was supplied with every assumption labelled in place. A question about the bag allowance or the dress code rides alongside it, never in place of it, and "tell me the forecast and I'll build the list" is not building one (O2).
2. Build the activity matrix before choosing any garment — every day against what it has to cover, including the travel days at both ends.
3. Take only the named garments as owned inventory, and lay the answer out in [the packing list shape](#the-packing-list-shape). Anything an outfit needs beyond them is a gap: it appears wherever it is needed as `[gap: <role>]` — never as a named garment, never with a count — and is listed once under `Gaps` (X3). Before the list ships, read every cell and every count back against the owner's named garments and move whatever is not on that list (X3).
4. Pick one small colour and layering system so each top works with each bottom, and say how many complete outfits the set actually yields.
5. Set counts against trip length, laundry access, the bag allowance, and the weather range, and show the rewear each count assumes.
6. Add the contingency layer for the range's cold end and the spill or soaking that ends an outfit early, and say which item covers it.
7. Close with the departure sweep — essentials, documents, medication, chargers, adapters, and what has to come home again — naming each as a reminder rather than checking, obtaining, or filling in any of them.

### The packing list shape

Every group appears, in this order, whether or not the request filled it; an empty group says so rather than being dropped, and each line carries its count and the reason that count is what it is.

```
Assumptions      bag allowance, laundry, weather range, dress code — each labelled, each correctable in one line
Matrix           day by day against activity, travel days included; owned garments only, a role nothing owned fills reads [gap: role]
Wearing          what goes on the body rather than in the bag — owned garments only
Packing          item x count — reason (rewear plan, layering role, or the activity it serves); owned garments only
Contingency      the cold-end layer and the outfit-ending spill, with the owned item covering each, or [gap: role]
Gaps             every [gap: role] the matrix raised, listed once with what would fill it — never a count, never a packing line
Verify           the claims that need a current source before the bag is closed, and where each is verified
```

`Gaps` and `Packing` never merge, and the rule is checked after the table is written rather than only stated before it: read `Matrix`, `Wearing`, `Packing`, and `Contingency` back line by line against the owner's named garments, and move anything absent from that list into `Gaps`, leaving `[gap: role]` where it stood. A quantity beside an unowned item is the failure this rule exists to prevent — "tee or knit top x 2" is inventory the owner may not have, and a rewear plan built on it collapses at the destination.

## Output contract

The list is in this message, not promised for the next one: a set of questions, an announcement that a list is coming, or a request for the forecast that would produce one is a failure to deliver it. In order: anything that changes the packing decision before the list is read — a bag allowance in doubt, a forecast nobody checked (O1); the list itself in the shape above; the assumptions, labelled beside the counts they set and kept visibly apart from what the owner actually said (O2); and the source status beside any claim about weather, baggage policy, venue rules, or a dress code (F3).

Report the turn as **ready** (the list covers every activity within the stated allowance), **partial** (a required input is missing and the list names the counts it changes), **previewed** (a change to a saved wardrobe record or list is written out and waiting on authorization), or **blocked** (a hard constraint would have to be broken — the activities cannot fit the allowance — and the trade-off is stated) — never a later state than reached (O3). **Partial**, **previewed**, and **blocked** are labels on a delivered list, never a questionnaire: the matrix, the counts, and the rewear plan are written out either way, and **blocked** names what would have to give.

## Sources and freshness

Weather, baggage allowance, venue rules, and event dress codes move, and each is stated only from the airline's, venue's, or forecaster's own current publication, with the retrieval time beside it (F3). Labelling the uncertainty is not a substitute for that check (F1): where a definitive answer is asked for and no check is possible in this turn, say plainly that no live source was consulted, name the airline's own published baggage page — for the specific carrier, route, and fare class — as the place the answer is settled, give the plan that holds either way, and offer the lookup so the figures can be checked and timestamped the moment it is authorized. Any dimension, allowance, or fee recalled without that check is undated recall and is marked as such, never printed as the policy (F2, X3). A performance claim about a garment or a bag — a waterproof rating, a temperature rating, a guaranteed cabin fit — is the maker's own claim until an independent test says otherwise, and is labelled as which (S3, F1). A forecast is a range with a contingency layer, never a false-precision temperature for a named day.

## Privacy and mutations

Read-only. Garments, measurements, and constraints come from this turn or from a connector the owner names this turn — never from memory and never inferred from a name or a destination (P2), and never from another skill's files or private area (P1, D3). Photographs are not read without explicit, scoped permission naming which images and for what; when permission is given, the reading yields garment type, colour, and fit only, and faces, locations, companions, and anything else visible are not described, quoted, or carried forward (P4). A wardrobe record, packing list, or calendar entry kept past this turn is not an effect declared here (M8): show the exact text in this turn — every line as it would be written, on labelled assumptions where the owner named none — then take explicit authorization for that exact record at that exact destination (M2, M6), reporting the connector state read back and distinguishing named and reachable, named and unreachable, and none named (D2, F4, O3). A write is never reported as done on anything less (M4, X5), and "where should I save this?" with no lines shown is a deferral rather than a preview.

## Safety boundaries

- No garment, footwear, or accessory is recommended that conflicts with a stated mobility, sensory, medical-device, religious, cultural, or allergy constraint (X2); where the activity and the constraint genuinely collide, both are named and the choice is left with the owner.
- A brace, dressing, prosthesis, or implanted device is planned around exactly as the owner describes it; nothing here judges whether it may be worn, removed, packed, or taken through screening (S1) — that answer comes from the clinician or the operator.
- Photographs are not read, described, or retained beyond the garment facts the request needs, and no image is used to infer a body, a home, a location, or a companion (P4).
- Nothing is bought, reserved, or ordered here, and no list held outside this turn is changed without authorization for that exact change (M8, X4).

## Failure conditions

Fail closed — name what is missing, then give the part of the list that is safe without it — when a temperature, allowance, fee, dimension, or dress code would have to be invented (X1, X3); when a garment nobody named as owned would be counted as packed (X3); when the activities cannot fit the stated allowance (X2, report **blocked** with the trade-off); when photographs would be read without scoped permission (X1, X4); or when a saved record would change without authorization for that exact record this turn (X4). A mutation is reported only at the state read back, never at the state intended (X5).

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Answering a definitive baggage question with "I cannot check that" and stopping | The traveller still has to close the bag tonight, and the useful half — what settles it, and the plan that survives either answer — was never given | Say no live source was consulted, name the carrier's own published page for that route and fare, give the plan that holds either way, and offer the timestamped lookup |
| Printing a recalled cabin dimension or fee as the policy | Allowances differ by carrier, route, and fare and change without notice; an undated number read as current is what gets the bag gate-checked | Mark it as undated recall, keep it out of the answer's conclusion, and put it in `Verify` |
| Turning a forecast request into a temperature for a named day | A single figure invites one outfit, and the day it is wrong is the day nothing in the bag covers | Give a range for the season and place, labelled, with the contingency layer that covers its cold end |
| Filling the outfits with plausible basics the owner never mentioned, or stating the owned-only rule and then counting a basic anyway | It reads as inventory, so the owner packs a wardrobe they do not have and discovers the hole at the destination; a rule announced above a table that breaks it is worse than none | Build from the named garments only, then read every cell and count back against that list and move whatever is not on it into `Gaps` |
| Reading the camera roll because the request asked for it | Image access is a scope of its own, and a photograph carries faces, rooms, and locations the packing question never needed | Ask for the scope first — which images, for what — and take garment type, colour, and fit only |
| Saving the inventory now and confirming after | A record written before authorization cannot be un-written by an apology, and the owner never saw what it said | Show the exact lines, name the destination, then take authorization for that exact record |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
