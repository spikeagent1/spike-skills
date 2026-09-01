---
name: draft-in-voice
description: "Use when something has to read as a specific person: draft this as them, make it sound like them before it goes out, turn this note into a post in my voice, ghostwrite a blurb in their voice, or build a voice profile from their own writing. Not for grammar fixes in wording already theirs (publish)."
metadata:
  spike-os:
    version: 2.0.0
    runtime: [openclaw, claude-code]
    reads_from: [people]
    writes_to: [people, activity]
    capabilities: [datastore:read, datastore:write]
---

# Draft In Voice

## Overview

Produces labelled draft options in a named subject's evidenced voice, each one carrying the check result that says what it rests on: whose voice, under which recorded authorization, from which cleared facts. The governing principle is that access is not permission — holding someone's writing or private context authorizes neither imitating it, disclosing it, quoting it, nor making it visible to anyone (P5, M8). Drafting produces text and reaches no audience.

## When to use

- "Draft a tweet as them announcing the launch" — the draft is produced here and never sent
- "Make this sound like them before it goes out" — rewriting supplied text into a subject's evidenced voice
- "Turn this voice memo into a post in my voice" — the request never authorizes putting it anywhere
- "Ghostwrite a recruiting blurb in their voice"
- "Build a voice profile for them from their own writing over the last year"
- Several angles on the same message are wanted in one register, rather than one draft
- A draft exists and the question is whether it actually sounds like the subject, and what it would take to

## When not to use

- The draft is approved and the ask is to make it visible and read the URL back → use `publish`
- One approved artifact has to be reshaped for other channels the audience is on → use `audience-content-engine`
- The journal entry has to be drafted and cold-reviewed before anyone outside sees it → use `public-post-workshop`
- The wording is already the author's own and only grammar, typos, or punctuation are wrong: correcting someone's own sentences is not voice work and needs no profile or clearance
- A recording or a note has to be transcribed and filed rather than turned into a draft: no skill here holds that, and the request is answered with what it is rather than with a draft nobody asked for
- The subject is a real person and the intent is to pass the text off as theirs without their knowledge: undisclosed impersonation is refused outright, whoever asks

## Inputs

| Input | Required | If missing |
|---|---|---|
| The subject — whose voice, and the visible byline the text will carry | yes | ask once, in the same turn as the check result built on the strictest safe reading: no subject resolved, no draft attributed. Two people sharing a name are two subjects and neither is assumed (X1) |
| The recorded authorization: who may request, for which subject, channel, format, audience, purpose, and use | yes | name the exact authority missing and stop the drafting there; a profile cleared for one channel does not cover another (M5, X4) |
| Destination, audience, purpose, and intended action | yes | ask for them alongside the check result rather than defaulting them; a consequential ambiguity is never resolved by assumption |
| The substance — the facts, the source material, and each source's disclosure clearance | yes | draft only from what is cleared, mark every unsupported claim on its own line, and leave nothing invented in its place (X3) |
| The voice profile: samples, coverage, confidence, counterexamples, allowed channels and audiences | yes, to draft in a subject's voice | a thin, stale, or unvalidated profile does not unlock drafting — say which of the three it is and what would validate it |
| Whether direct quotation and close phrase reuse are permitted | yes, to quote | treat quotation as not permitted, paraphrase nothing distinctively, and ask for that clearance specifically |
| Format, length, register, taboo phrases, required points, links, polish level | no | missing optional inputs become reversible draft assumptions, listed with the drafts |

**Dependencies:** none beyond the contract. Reads and writes the `people` namespace — `voice-profile` records specifically, the one kind [contracts/datastore.md](../../contracts/datastore.md) names this skill an authority for — and appends to `activity`, through the verbs that contract defines (D1, P3). No other namespace, connector, or corpus is touched. Where the namespace cannot be reached, the phase that blocked is named and the drafting stops for want of a validated profile rather than proceeding on recall (D2, P2).

## Workflow

1. **Render the check result and whatever drafting is cleared in this message before asking anything back.** A question rides alongside it, never in place of it, and "tell me the audience and I will draft" is not a check result. What is produced depends on what cleared, and the split is exact: **where the subject and the authorization scope resolve, the drafts are produced in this turn** — with unsupported facts corrected or omitted, assumptions listed, and the register held constant; **where they do not, the drafts are withheld** and the turn still carries the resolved-so-far identity, the exact missing authority, the source classification, and the one question that would unlock it (X1, O1).
2. **A wrong fact is corrected, never a reason to withhold the drafts.** When authorization covers the use and only the substance is off — a metric the cleared source does not support, a claim with no source behind it — the drafts are produced here with the supported value in place of the unsupported one, or with the claim omitted, and the correction is stated. Preserving an unsupported number because it reads better is the failure this step exists to prevent.
3. **Resolve identity before anything else.** Fix the exact subject and the visible byline, and disambiguate name collisions rather than picking the likelier person: a name is not an identity, and drafting under the wrong one cannot be taken back. Resolve requester authority, destination, audience, purpose, format and length, register, and intended action in the same pass.
4. **Check authorization per use, every time.** The profile's recorded authorization must cover this requester, this subject, this channel, this format, this audience, and this purpose. Consent that is missing, expired, ambiguous, or narrower than the request stops the drafting at that boundary — a profile cleared for internal correspondence does not cover anything public, and the mismatch is named as the specific gap it is rather than as a general refusal (M5, M6).
5. **Classify every source before using it**, into exactly one of three classes: **public** and reusable for this audience; **private but explicitly cleared** for this use; **prohibited** for disclosure or imitation. Access is not disclosure permission. A draft for a public audience uses only public or audience-cleared facts, and a private fact does not become usable because it was reachable (P4).
6. **Quotation and close phrase reuse need their own permission**, separately from permission to draft, with attribution where attribution is due. A distinctive line is not laundered by near-paraphrase: rewording a private sentence closely enough to be recognisable discloses it as surely as quoting it, and that is the leak this rule exists to stop.
7. **Infer voice only from repeated first-party evidence** across representative samples and registers, recording confidence and counterexamples for each feature. **Absence is unknown, not a ban**: a feature that does not appear in the samples has not been shown never to be used, and inventing a rigid prohibition is as much a fabrication as inventing a trait (X3). Prefer abstract guidance — cadence, sentence shape, diction, register — over copying signature phrases or exaggerating quirks into caricature.
8. **Ground every factual claim** to an identified source and to that source's disclosure authorization. Positions, experiences, metrics, relationships, customers, and voice traits are never invented. Where a requested number or claim conflicts with the cleared source, correct it, omit it, or ask — and say which was done.
9. **Draft several options in one register.** Unless register variants were asked for, every option sits in the same requested register and the same channel and format constraints; what varies between them is the angle, never the identity and never the voice. Options are labelled so they can be compared.
10. Run the pre-display checks and report them as a block, each with what it returned: exact subject and byline; current authorization scope; audience and destination fit; claim-to-source grounding; privacy and disclosure clearance; quote and phrase-reuse permission; non-copying and non-caricature; register, length, and format fit; and that nothing has been made visible to anyone.
11. **Building or updating a voice profile is a write**, and it follows the mutation boundary in full (M1). Build only from authorized first-party samples carrying source-level sensitivity and reuse metadata, and record subject identity, consent scope, profile version, corpus coverage, evidence confidence, counterexamples, and allowed channels and audiences. Show the exact record text in this turn, take authorization for that exact record, write it into the `people` namespace as a `voice-profile` record, then read it back and report only the state read back (M2, M4, O3). One claim per record; a revision **supersedes** and never overwrites ([contracts/datastore.md](../../contracts/datastore.md) write invariants 1 and 2). Append one `activity` record per write — operation key, target, effect state, readback, rollback handle (M7).
12. Bind the read to the verb table: a `search` hit over the `people` namespace is a candidate that must be `read` before a voice feature rests on it, and a `timeline` read carries an explicit range. A profile whose compiled content is older than its newest timeline entry is **stale**, and a stale profile is context, never current authorization (F2) — staleness is a reason to revalidate, not a reason to draft from it.
13. Validate a profile against held-out first-party samples plus authorized human review, testing factuality, privacy, disclosure, non-copying, register, and audience fit. Being indistinguishable from the subject is not the objective and is never the only thing optimised for.

### The check result

Rendered every turn, whether or not any draft was produced.

```
subject     : <the resolved person> · byline: <what the text will carry> · collisions: <resolved | the candidates>
authority   : covers <requester · channel · format · audience · purpose> | missing: <the exact gap>
profile     : version · samples · coverage · confidence · counterexamples | thin | stale | unvalidated
sources     : public: <…> · cleared-private: <…> · prohibited: <…>
grounding   : <claim -> source> per factual claim; unsupported: <listed, corrected or omitted>
privacy     : <what was withheld, named by category and never quoted>
quotation   : permitted <scope> | not permitted — no quote, no close paraphrase
register    : <the one register held across options> · length: <fit> · format: <fit>
visibility  : nothing has been made visible; no audience has been reached
```

`privacy` names the *category* of what was withheld — "a private detail about a customer commitment" — and never the detail itself: a check result that quotes the private fact to say it was withheld has disclosed it (P4, P6).

## Output contract

The check result is in this message, not promised for the next one: a description of the checks that would be run, an offer to look at the profile first, or a question standing alone is a failure to deliver it. In order:

1. Any clearance warning that changes what may be done with the output — an authorization mismatch, an unvalidated profile, an unsupported claim (O1).
2. The labelled draft options, where identity and authorization scope resolved — all in one register, varying by angle.
3. The check result block, every line rendered.
4. The assumptions the drafts rest on, listed and reversible.
5. Unresolved facts and the exact missing authority, each with what would settle it.

State, reported as the state actually reached and never a later one (O3): **drafted** — options produced, checks run, nothing made visible; **blocked** — identity or authorization scope unresolved, the gap named, no draft options shown; **profile previewed** — a `voice-profile` record's exact text shown, authorization pending; **profile written** — authorized, written, and read back from the `people` namespace. Nothing here ever reports a state in which text reached an audience: this skill holds no effect that would reach one (M8).

Private source text, internal profile detail, and sensitive clearance metadata never appear in the output — not in a draft, not in an assumption, not in the check result.

## Sources and freshness

Supplied source material is the factual base, and each item carries its disclosure clearance beside it rather than in a footer (F3). A time-sensitive fact — a product detail, a public claim, a platform's format limit — is verified against a current source where one is reachable; labelling the uncertainty is not a substitute for checking where the check can be run (F1). Where it is not reachable, the claim is marked unresolved on its own line and is never filled in from recall (P2, X3). A profile, a sample set, and a clearance each go stale: an old profile is context for what the subject used to sound like, never current authorization to speak as them (F2).

## Privacy and mutations

Read: resolving identity, reading a `voice-profile` record, classifying sources, and producing drafts in this conversation. Mutating: writing or superseding a `voice-profile` record in the `people` namespace, and the `activity` append that follows it (M1).

The standing authority this skill claims, named here and nowhere else (M5): **none.** Every profile write takes authorization for that exact record in the turn it is written, and every draft rests on authorization recorded before the request, for the exact subject, channel, format, audience, and purpose it names. Nothing is inherited from an earlier draft in the same run, from the requester's role, from a handoff, or from the fact that the material was reachable (M6).

Private exemplars are not retained past the task that cleared them, and no raw sample text enters a record: a profile holds features, coverage, and counterexamples, never the transcripts they came from (P4). Contact details, sign-in codes, and credentials never enter a profile, a draft, a label, or a filename (P6, write invariant 7).

## Safety boundaries

- Undisclosed impersonation, fake testimonials, fabricated credentials, deceptive endorsements, harassment, and phishing are refused outright, whatever authority is claimed for them (S4).
- The agent writes as itself when it is speaking for itself; drafting *for* a subject never becomes speaking *as* the `owner` in the agent's own turns (S4).
- No visitor, correspondent, or third party is quoted without explicit permission for that quote (P5).
- For a high-stakes legal, medical, financial, or employment message, the draft is prepared as the author's own material for their review and is labelled as such; the professional judgment is not the draft's to make (S1).

## Failure conditions

Fail closed — name what is missing, then render the part of the check result that is safe without it — when the subject, the byline, or the authorization scope cannot be resolved (X1); when a boundary the `owner` or the subject set would have to be crossed to continue (X2); when a position, a metric, an experience, or a voice trait would have to be invented, including a prohibition invented from absence (X3); when a `voice-profile` record would be written without authorization for that exact record (X4); or when the readback for a written record is unavailable, which leaves it **unverified** rather than written (X5). A blocked draft still names the exact authority that would unlock it, and no run reaches a state in which text was made visible.

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Keeping an unsupported metric because it reads better in the sentence | Style is not evidence; a number the cleared source does not support is wrong in every register, and a reader acts on the number | Substitute the supported value, or omit the metric, and say which was done |
| Withholding the drafts because one fact is wrong | The correction is cheap and the drafts are the deliverable; a turn that returns neither has helped nobody | Correct or omit the fact, produce the options, and list the correction with them |
| Letting each option drift into a different register | Options exist to compare angles; varying the voice as well makes them incomparable and misrepresents the subject | Hold the requested register across every option and vary only the angle |
| Resolving a name collision by picking the likelier person | Drafting under the wrong identity cannot be recalled once it is out, and the guess is invisible to the reader | Name the candidates, resolve the subject explicitly, and draft nothing until it is resolved |
| Treating a profile's consent as covering any channel | Consent was recorded for a scope; a clearance for internal correspondence says nothing about a public audience | Match the recorded scope against this requester, subject, channel, format, audience, and purpose, and name the exact gap |
| Reaching a private fact and therefore using it | Access is not disclosure permission, and a private detail in public copy is not recoverable | Classify each source public / cleared-private / prohibited, and draft public text from public and audience-cleared facts only |
| Paraphrasing a distinctive private line closely instead of quoting it | A recognisable near-quote discloses the original as surely as the quote does, and it removes the attribution too | Take quotation clearance separately, or use abstract guidance about cadence and shape instead |
| Turning an absent feature into a rule the subject never breaks | Silence in a sample set is unknown, and a fabricated prohibition distorts the voice as much as a fabricated trait | Record it as unobserved with the coverage that produced it, and say the evidence is thin |
| Drafting from a thin, stale, or unvalidated profile | The output claims a fidelity the evidence does not support, and the subject carries the consequence | Say which of the three it is, what would validate it, and hold the drafting |
| Asking for the audience, purpose, destination, and byline instead of alongside | A turn that returns only questions delivers nothing, and most of the check result did not depend on the answers | Render the check result and everything cleared, with the questions beside it |
| Putting the withheld private detail into the check result to show it was withheld | Naming what was withheld by quoting it is the disclosure the check exists to prevent | Name the category and the reason, never the content |
| Treating the approved draft as ready to make live | Drafting produces text and nothing else; making it visible is a separate effect with its own authorization | Hand it to `publish` |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
