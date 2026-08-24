---
name: "draft-in-voice"
description: "Make voice drafting identity-safe, scope-bound, source-grounded, and non-copying."
mutating: true
writes_pages: true
writes_to:
  - people/
---

# Draft In Voice

Draft options in a specific person's evidenced voice. Access to a person's writing or private context is not permission to imitate, disclose, quote, or publish it.

## Resolve identity and use
Resolve the exact subject and visible author/byline; disambiguate name collisions. Resolve requester authority, destination, audience, purpose, format/length, register, intended action, and whether direct quotation is permitted.

Do not default consequential ambiguities. Drafting never authorizes posting or sending.

## Per-use authorization
Require a current validated profile whose recorded authorization covers the requester, subject, channel, format, audience, purpose, and use. Re-check the scope on every drafting request. Missing, expired, ambiguous, or narrower consent stops the draft and asks for the missing authority.

## Source classes
Classify each profile/context source as:

- public and reusable for the intended audience;
- private but explicitly cleared for this use;
- prohibited for disclosure or imitation.

Access is not disclosure permission. Public drafts use only public or audience-cleared facts. Direct quotation and close phrase reuse require separate permission and attribution where appropriate. Never leak a distinctive line by near-paraphrase.

## Voice evidence
Infer voice features only from repeated first-party evidence across representative samples and registers. Record confidence and counterexamples. Absence is unknown, not proof that the subject never uses a feature. Prefer abstract guidance about cadence, sentence shape, diction, and register over copying signature phrases or caricaturing quirks.

A thin, stale, or unvalidated profile does not unlock drafting.

## Ground substance
Map every factual claim to an identified source and disclosure authorization. Do not invent positions, experiences, metrics, relationships, customers, or voice traits. If a requested number or claim conflicts with the cleared source, correct it, omit it, or ask; never preserve it for style.

## Draft
Produce multiple options within the same requested register unless the user asks for register variants. Vary angle, not identity. Keep each option within the requested channel and format constraints.

## Pre-display checks
Before showing drafts, verify:

- exact subject and byline;
- current authorization scope;
- audience and destination fit;
- claim-to-source grounding;
- privacy and disclosure clearance;
- quote and phrase-reuse permission;
- non-copying and non-caricature;
- register, length, and format;
- no posting or sending.

## Profile building and validation
Build profiles only from authorized first-party samples with source-level sensitivity and reuse metadata. Record subject identity, consent scope, profile version, corpus coverage, evidence confidence, counterexamples, and allowed channels/audiences.

Validation uses held-out first-party samples plus authorized human review. Test factuality, privacy, disclosure, non-copying, register, and audience fit. Do not optimize only for being indistinguishable from the person.

## Output
Return labeled draft options and a concise check result. Do not expose private source text, internal profile details, or sensitive clearance metadata. Never send or post.

## Failure conditions
Fail review if identity is inferred from a name alone; profile consent is treated as universal; private text enters public copy; a direct or near quote lacks permission; absence becomes a rigid ban; an unsupported fact survives because it sounds in-voice; validation optimizes deception alone; or a draft is sent.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.

## When to use
Use this skill when the user wants a draft in Spike's or another specified voice for a known channel, audience, and purpose, especially when privacy, authority, or style fidelity matters.

## When not to use
Do not use it to impersonate a real person without authorization, fabricate experience, send or publish directly, or launder private text into public copy without clearance.

## Required inputs
Required inputs are target voice, audience, channel, purpose, source material, and send/publish authority state. If voice owner, audience, or private-source clearance is unclear, ask before drafting or mark the draft blocked.

## Optional inputs
Optional inputs include length, format, examples, taboo phrases, required points, links, and desired level of polish. Missing optional inputs become reversible draft assumptions.

## Workflow
1. Identify voice owner, channel, audience, purpose, and authority.
2. Separate factual source material from style examples and private context.
3. Ask only for missing facts that affect truth, consent, identity, or delivery.
4. Draft without sending, scheduling, posting, or saving unless separately authorized.
5. Check for fabricated traits, overclaiming, private disclosure, and channel mismatch.
6. Return variants or a revision target when useful.
7. Route publication to `publish` or channel-specific workflow after approval.

## Sources and freshness
Use provided source material as the factual base. Time-sensitive facts, product details, public claims, or platform limits need current verification or an uncertainty label.

## Privacy and mutations
Drafting in chat is non-mutating. Saving a file, updating a doc, sending email, posting, or scheduling is mutating and requires explicit target and approval. Do not retain private exemplars beyond the current task unless authorized.

## Safety boundaries
Refuse deception, undisclosed impersonation, fake testimonials, fabricated credentials, harassment, phishing, or privacy leaks. For high-stakes legal, medical, financial, or employment messages, draft only as user-authored preparation and recommend qualified review where needed.

## Output contract
Return channel-ready draft text, assumptions, excluded private details, unresolved facts, and publication status. If blocked, return the missing authority or evidence needed.

## Failure conditions
Fail when source truth is insufficient for the central claim, voice authority is missing, the request requires impersonation or deception, or the user asks to send/publish without a verified target and approval.

## Worked example
For "write a LinkedIn note about the validator PR in Spike voice," return a concise draft grounded in the PR, name that it is draft-only, list unverified claims, and avoid saying it was posted.
