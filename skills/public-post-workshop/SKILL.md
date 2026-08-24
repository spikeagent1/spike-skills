---
name: "public-post-workshop"
description: "Create reviewed unmerged wall PRs while preserving disclosure and direct-post gates."
---

# Public Post Workshop

Turn a public-content idea into a reviewed wall-entry PR without widening disclosure or silently posting to a direct surface.

## Authority
Standing authority covers creating an isolated branch, commit, push, and unmerged PR for a validated Spike wall entry. It does not cover merge, direct posting, syndication, announcement, quoting private people, or widening disclosure.

Direct X, Moltbook, email, or other posts stop after review and require explicit posting authority.

## Brief
Resolve audience, intended takeaway, reason to care, public artifact or evidence, destination, and intended action. Infer routine editorial choices from context; ask only when a gap changes substance, audience, disclosure, attribution, or effect.

## Evidence and disclosure
Use only public or explicitly cleared facts. Separate Tapan's statements, Spike's inference, and third-party evidence. Before quoting a private conversation, ask in that thread: "May I quote this on the wall - anonymously, or with a handle?" Never publish email addresses.

Run claim-level verification for load-bearing factual claims. A catchy but unsupported claim blocks the draft.

## Draft
Write in Spike's first-person voice, never Tapan's. Prefer one concrete idea in a few short paragraphs. Use visible scenes and direct language. Avoid launch boilerplate, engagement bait, inflated claims, generic calls to action, and operational maps.

Use audience-content-engine when adapting an already approved artifact for another platform, but do not let adaptation authorize direct posting.

## Cold review
Give a fresh reviewer only the brief, cleared public evidence, draft, and rubric. The reviewer checks audience fit, takeaway, reason to care, economy, Spike voice, attribution, factual grounding, privacy/disclosure, and public safety. It returns PASS or the smallest concrete fixes.

Revise and use a fresh cold reviewer until PASS. Stop if passing requires changing the brief or disclosure boundary.

## Wall-entry PR
After PASS:

1. base an isolated branch on the active site branch;
2. write one voice-agent Stream entry with accurate provenance;
3. set edited_by_human only when Tapan materially edited the final draft;
4. compute the exact content hash;
5. validate schema/content, Astro, and relevant tests;
6. commit as Spike, push, and open an unmerged PR;
7. verify the PR contains only the intended entry and remains unmerged.

Repair safe regressions caused by the change and rerun checks. Report infrastructure-only failures separately.

## Output
For wall entries, report the brief, final draft, review rounds, verification, PR link, and unmerged state. For direct surfaces, report the brief, draft, PASS, and posting-authorization gate.

## Failure conditions
Fail review if the draft speaks as Tapan; private content or a quote lacks clearance; a critical fact is unsupported; the reviewer receives unrelated private context; the same warm reviewer is reused; direct posting occurs; the PR includes unrelated changes; or PASS is claimed without independent review.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.

## When to use
Use this skill to prepare a public post package from a repository change, release, benchmark, or proposal while preserving review, evidence, and publication boundaries.

## When not to use
Do not use it to directly post, merge PRs, approve Skill Workshop proposals, invent proposal IDs, or market private/unreleased work as shipped.

## Required inputs
Required inputs are artifact or change, intended audience, factual claims, publication surface, governance state, and authority to draft or publish. If governance state or evidence is unclear, produce a blocked draft package.

## Optional inputs
Optional inputs include desired tone, length, screenshots, related links, known limitations, and reviewer notes. Missing optional inputs should not block a draft unless they affect claim truth.

## Workflow
1. Inspect the artifact/change and governance state from source of truth.
2. Build an audience/takeaway/evidence brief.
3. Draft platform-native copy without claiming unmerged or pending work is released.
4. Run a cold self-review for factuality, privacy, provenance, and overclaiming.
5. If repository changes are needed, create or update an unmerged PR; do not merge.
6. If direct publication is requested, preview exact content and target and require explicit authorization.
7. Return publication package, evidence, and blockers.

## Sources and freshness
Use current git state, PR state, CI results, catalog/proposal metadata, and linked artifacts. Time-sensitive PR/CI/release claims must be checked immediately before final output.

## Privacy and mutations
Drafting is non-mutating. Creating branches, commits, PRs, comments, screenshots, or posts is mutating and requires the authority granted by the user or an explicit preview. Never include credentials, private transcripts, or unpublished owner context.

## Safety boundaries
Refuse to misrepresent release state, fabricate metrics, publish private material, bypass review, merge without authorization, or announce pending Skill Workshop proposals as approved.

## Output contract
Return post brief, draft(s), evidence links, governance state, PR/release state, known limitations, authorization needed, and follow-up monitoring plan.

## Failure conditions
Fail when source evidence is unavailable, governance state is ambiguous, CI/PR state cannot be verified for a claim, privacy clearance is missing, or publication authority is absent.

## Worked example
For "announce this unmerged skill PR," state that it is a review PR, cite changed packages and validation evidence, avoid release language, and return draft-only copy plus PR URL.

## Provenance
Repo-owned portfolio-governance workflow maintained as public portable skill text with synthetic fixtures only.
