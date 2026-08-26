---
name: "owner-context-onboarding"
description: "Onboard a personal agent to its owner through staged interviews, privacy-safe memory, role alignment, and explicit completion checks."
---

# Owner context onboarding

Use when a personal agent is new, the owner says to continue onboarding, sends autobiographical notes, asks what questions remain, or wants the agent's role, voice, privacy, or autonomy boundaries aligned.

## Resume before asking

1. Search authorized memory and prior owner-session transcripts for completed topics, pauses, corrections, and open questions.
2. Read the deployment's identity, soul, user, agent, bootstrap, and handoff sources.
3. Distinguish durable owner memory from git-reseeded runtime instructions.
4. Build a private checklist with states: unknown, captured, confirmed, deferred, or declined.
5. Ask only for the highest-value unresolved item. Do not repeat questions already answered.

## Interview rhythm

Proceed one question at a time. Accept text, audio notes, documents, or a request to change topics. The owner can pause, skip, correct, or defer anything without losing progress.

Cover only what is useful:

- how the owner wants to be addressed and contacted;
- current goals, responsibilities, projects, and near-term priorities;
- the agent's roles and expected outcomes;
- decision authority, approval boundaries, and spending or publication limits;
- communication cadence, status-report preference, and writing style;
- privacy boundaries, off-limits topics, and what may become public;
- important people, organizations, terminology, and historical context;
- recovery expectations after restart or redeploy.

Do not force a life-story interview when a smaller operational answer is enough.

## Curate, do not dump

Treat owner messages as private unless the owner explicitly clears them for a named audience. Convert useful information into concise, attributed memory rather than copying raw transcripts. Separate:

- owner-stated fact;
- agent inference;
- unresolved or contradictory claim;
- public fact;
- private context;
- proposed worldview or role change.

Never store passwords, OTPs, OAuth callbacks, API keys, recovery codes, or unnecessary contact details in memory.

## Apply corrections

When the owner corrects a fact or operating assumption, record the newer statement as the current truth with provenance and preserve the contradiction only when it helps avoid recurrence. A correction to identity, roles, autonomy, privacy, or worldview may require a governed update to durable instructions; do not silently rewrite those contracts.

## Verify retention

After writing curated memory:

1. read back the exact saved entry;
2. run a narrow recall using neutral wording;
3. confirm the returned fact matches its privacy and provenance labels;
4. repair duplicates or stale contradictions;
5. report what was captured, what remains open, and the next question.

## Completion

Onboarding is complete only when the agreed topics are confirmed or explicitly deferred, curated memory is readable and recallable, privacy boundaries are recorded, and the owner receives a concise summary. A pause means `IN_PROGRESS`, not failed. Never block useful work merely because optional biography questions remain.

## Output

Report:

- state: `IN_PROGRESS`, `COMPLETE`, or `BLOCKED`;
- newly confirmed context;
- durable writes and recall evidence;
- deferred or declined topics;
- the single next question, if any.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.

## When to use
Use this skill to establish or refresh an agent-owner working relationship: goals, boundaries, preferences, durable memory policy, privacy constraints, and first operating context.

## When not to use
Do not use it to mine private transcripts wholesale, override existing owner policy, perform connector setup, or continue asking questions when the owner has paused or declined.

## Required inputs
Required inputs are owner identity label, intended agent role, working goals, authority boundaries, privacy preferences, memory/storage policy, and current onboarding state. If any safety-critical boundary is missing, ask one focused question before acting.

## Optional inputs
Optional inputs include communication style, recurring workflows, known people/projects, decision preferences, and handoff notes. Missing optional inputs should become future discovery items, not blockers.

## Workflow
1. Read existing durable owner context and handoff notes before asking.
2. Identify missing high-impact facts and ask one question at a time.
3. Separate raw transcript, summarized preference, durable memory, and authority rule.
4. Preview any durable write with provenance, scope, sensitivity, and expiry/review conditions.
5. Store only approved distilled context in the configured private location.
6. Verify retrieval or readback after a write.
7. Produce an owner context matrix and next onboarding gaps.

## Sources and freshness
Use the owner’s current answers as primary evidence and cite dates for durable preferences. Existing memory is context until verified; stale preferences should be marked for review rather than silently applied.

## Privacy and mutations
Interviewing and summarizing in-session can be non-mutating. Writing memory, handoff files, preferences, schedules, or policy is mutating and requires preview plus authorization. Never publish owner context or raw onboarding transcripts.

## Safety boundaries
Stop before irreversible action, external disclosure, credential handling, or authority changes without explicit owner consent. Minimize sensitive data and avoid storing unnecessary personal details.

## Output contract
Return current owner-context matrix, confirmed boundaries, durable writes performed or pending approval, provenance, unresolved questions, and next safe action.

## Failure conditions
Fail when the owner declines, durable storage cannot be verified, boundaries conflict, a requested memory is too sensitive to store safely, or the workflow would expose private context.

## Worked example
For "set up how you should work with me," ask for role and boundaries first, summarize back, preview the exact durable memory entries, write only after approval, and verify retrieval.

## Provenance
Repo-owned onboarding workflow maintained as public portable skill text with synthetic fixtures only.
