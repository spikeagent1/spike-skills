---
name: home
description: "Use when the request names no skill and two or more could each own it, spans several life domains, asks what the agent can do or which skills exist, or would be answered directly although a skill here covers it. Not for the day compiled (briefing) or one task (daily-task-manager)."
metadata:
  spike-os:
    version: 1.0.0
    runtime: [openclaw, claude-code]
    reads_from: []
    writes_to: []
    effects: []
---

# Home

## Overview

The home screen of the library: it reads the generated index, names exactly one skill, restates the intent in one line, and hands off — or asks one question when more than one skill fits. It never performs the work it routes. The governing principle is that the index on disk is the only list of what exists: a launcher routing from recall names skills that were renamed, retired, or never installed here, and a hand-off to a skill that is not there fails silently.

## When to use

- The request is open and names no skill: "help me sort this out", "I don't know where to start"
- It spans more than one life domain at once — a plan and a shopping list, a draft and where it goes, an appointment and the record behind it
- "What can you do", "which skills do I have", "what are my options here" — the ask is the library itself
- No skill is named, and the request would otherwise be answered directly although a skill in the index covers it
- Two or three skills could each plausibly own it, and picking one silently throws the choice away
- The phrasing is one the router historically loses — an evidence check, a survey of a field, a question about the agent's own beliefs — which is why the precedence table below carries a row for each

## When not to use

- The owner named a skill → invoke that skill; a launcher between the owner and a named target only adds a turn
- The intent is unambiguous and one skill plainly owns it → let that skill answer directly
- The ask is the read-only picture of the day, compiled and cited → use `briefing`; this skill never composes one, and never summarises a day on the way past
- One task is to be captured, completed, deferred, edited or removed → use `daily-task-manager`
- The library itself is being changed — a package added, retired, or installed → use `skill-library-ops`
- A norm for sharing packages across a team is the question → use `team-skill-sharing-norm`
- The request is a general-knowledge question with no skill behind it → say no skill applies, and do not supply the answer here, not even as an aside

## Inputs

| Input | Required | If missing |
|---|---|---|
| The owner request, in the owner's own words | yes | a bare invocation with no request is the "what can you do" case, not a failure: print the domain index — the eight sections, what each covers, and the skills the index lists under them — and stop, asking nothing (X1 does not apply, there is nothing missing to name) |
| [catalog/index.md](../../catalog/index.md) — the generated table of every skill, its trigger line, version, runtime, effect badges, and cluster | yes | say on the routing line that the index could not be read, route from the precedence table and the request anyway, and mark the named target unverified (D2, F4) |
| The domain the request belongs to | no | infer it from the request; where two domains fit, that is the two-candidate case and the answer is one question |
| A previous turn's routing decision | no | treat it as context, never as the current answer — the index may have changed since (F2) |

**Dependencies:** none beyond the contract. This skill reads one repository file, [catalog/index.md](../../catalog/index.md), touches no namespace of the `owner datastore`, and declares no effect (D1, D3).

## Workflow

1. **Route or ask in this turn.** The deliverable is a routing line or a single question, produced now, from the request as phrased. A description of how routing would work, a list of everything the library holds in place of a decision, or an offer to look once the index is reachable is a failure to deliver it. Where the index cannot be read, the routing line is still produced, with the index marked unread and the target marked unverified; the missing fact is marked, the decision is not deferred.
2. **Check the precedence table first**, against the phrasing actually given rather than a tidied-up version of it. It is a rule table, not a hint: a row that matches settles the route before any judgment about what the request "really" means.
3. **Then read [catalog/index.md](../../catalog/index.md), never a remembered list.** The index's sections are fixed — work, health, wealth, home-and-lifestyle, relationships-and-community, learning-and-knowledge, travel-and-mobility, personal-operations — and the skills under them are read, not recalled. Match the request against the `use when` column, which is each skill's own trigger line. Where the index is unread, the only skill names that may appear are the ones the precedence table below already carries, and each is labelled **from the precedence table, not verified against the index** — a name offered with neither the index behind it nor that label is the recall this step forbids (P2).
4. **A bare invocation is the index.** Where the skill is invoked with no request at all, the answer is the domain index itself, printed from [catalog/index.md](../../catalog/index.md): the eight sections, one line on what each covers, and the skills listed under them with their trigger lines. No question is asked, no route is guessed, and "no intent" is not the answer — the owner opened the library, and the library's contents are what they came for. Where the index cannot be read, the eight domains are still named and only the skills the precedence table carries are listed, each marked **from the precedence table, not verified against the index** (P2, F4).
5. **Exactly one skill fits** → name it, restate the intent in one line so the owner sees what is being handed over, and invoke it.
6. **Two or three fit** → ask exactly ONE question, naming each candidate and, in a few words, what that one would do differently. Never ask two questions, never ask a question and route as well, and never pick one silently to save the turn.
7. **Nothing fits** → say so, then name the one domain closest to the request and the skills the index lists under it — not the whole library — and stop. The pointer is not optional: a bare refusal leaves the owner with nowhere to go, and "no skill applies" plus the nearest domain is the complete answer. The answer to the request itself is not supplied here in any form: not as an aside, a parenthetical, a "for the record", or a hedged "this is outside the skill, but". A disclaimed answer is still an answer, and it is the exact failure this skill exists to prevent; "the library has nothing for this" is a real and complete answer.
8. **Classify the intent as read or mutate before handing off (M1).** Where it carries a mutation verb, name the target's effect badges from the index — RO, DESTR, IDEM, OPEN and the effect list — so the owner sees what the next turn would be authorized to do. That authorization is the target skill's to take, per effect and per invocation, and is never carried across this hand-off (M6).

### Precedence table

Checked top to bottom; the first row that matches wins.

| The request says | Route to | Because |
|---|---|---|
| "my day", "what's up", "brief me", "what's happening today", "what changed overnight" | `briefing` | the whole compiled day, read-only |
| add, capture, complete, defer, edit or remove one task — "remind me to renew the insurance" | `daily-task-manager` | one task's lifecycle, not a day's picture |
| "connect", "authorize", "hook up" a named service | `mcp-connector-onboarding` | a conduit is being brought up, not used |
| "after the restart", "are you there", "did you keep the context" | `runtime-handoff-onboarding` | continuity across a restart is its own job |
| a recurring agent job — "every morning at seven", "run this weekly" | `cron-scheduler` | recurring agent work, distinct from any built-in of the same name |
| "post it", "publish this", "take it down" | `publish` | approved content going out or coming back |
| "what can you do", "which skills do I have", "what are my options" | this skill answers | the ask is the index; print it, route nothing |
| "fact check this draft before I post it", "is this accurate — check the claims one by one", "run a source check on the numbers in this post" | `fact-check` | claims in a document, checked one by one |
| "check this study — is the 40% reduction number real, did it ever replicate" | `fact-check` | one document's number is the subject; a field-wide survey is `literature-review` |
| "map the disagreements in this area: who argues what, and where is the evidence thinnest", "what does the research say", "survey the papers" | `literature-review` | a body of work, not a single claim |
| "you wrote that because I asked you to — did writing it change what you think" | `social-agent-practice` | the agent's own beliefs are the subject, not introspection about the runtime |
| "this one mention touches something private — handle it carefully" | `social-agent-practice` | a boundary call on one mention; the sweep of mentions is `social-listening-engagement-loop` |
| "what did I get done last week", across notes and records | no skill applies | the datastore readers (`briefing`, `owner-dream-cycle`, `conversation-archive`) each answer a narrower question; offer them and summarise nothing here |

## Output contract

The routing decision is in this message. Exactly one of two shapes, and nothing else — no plan, no partial answer, no second skill, no follow-on offer:

```
route  : <skill name, exactly as the index spells it>
intent : <the request restated in one line>
index  : read | unread (<reason>)
target : verified against the index | unverified
effects: <badges and effect list, only when the intent carries a mutation verb>
```

or

```
question: <one question naming two or three candidates and what each would do>
```

An index that could not be read is reported as **unread** with its reason, and a target it did not verify as **unverified**; both are distinct from **read**, and neither is ever left silent (F4). "What can you do" is answered with the index's own sections — the eight domains and what each covers — and the skills listed under them. Where the index is unread, the domains are still named, and every skill name in the response is one the precedence table carries, each marked **from the precedence table, not verified against the index**; no other name is offered, and the rest of each domain's rows are marked unread rather than filled from recall (P2).

## Worked example

> "plan dinners this week and what to buy"

```
question: Meals first or the list first — `meal-planner` picks the week's dinners
          around your constraints, `grocery-planner` turns a plan you already
          have into the shopping list. Which one do you want now?
```

> "add a task to renew the contract"

```
route  : daily-task-manager
intent : capture one task — renew the contract — on the owner's list
index  : read
target : verified against the index
```

## Privacy and mutations

Every step here is a decision about where a request goes; the skill declares no effect, holds no standing authority, and its `effects` list is empty and stays empty (M8). It reads one repository file and no namespace of the `owner datastore` (P3). Naming a target's effect badges is disclosure, not authorization: the target takes its own, per effect and per invocation, in its own turn (M6, M2). Nothing about the request is written anywhere, and its sensitive detail is not repeated into the restated-intent line beyond what routing needs (P4, P6).

## Failure conditions

Fail closed — say what is missing, then give the routing decision that is safe without it — when performing any part of the request here would run a mutating effect this skill does not declare (X4); when the named target does not appear in the index and its name would have to be invented (X3); when the index cannot be read and no precedence row settles the route either, so the target would be a guess (X1, X3); when one request would need more than one skill invoked, or a second question after the first, and one of them would have to be dropped without saying so. In every one of these the routing line or the one question is still produced, with the gap named where the certainty would have gone.

## Common mistakes

| Mistake | Why wrong | Do instead |
|---|---|---|
| Answering the request instead of routing it | The owner asked the library; an answer produced here bypasses the skill that owns the contract, the freshness rules, and the effect declarations for that work | Name the skill, restate the intent, hand off — or say no skill applies |
| Routing from a remembered list of skills | Names drift: a skill is renamed, retired, or was never installed in this runtime, and a confident hand-off to a target that is not there fails silently | Read the index and match the `use when` column; where it is unread, say so on the routing line |
| Saying the index was not read, then listing skill names anyway | The disclaimer and the list contradict each other, and the owner cannot tell which names are real | Name only what the precedence table carries, each labelled as unverified against the index |
| Refusing without a pointer | "No skill applies" alone sends the owner back to guessing which is exactly what they came here to avoid | Name the nearest domain and its skills in the same breath as the refusal |
| Picking one of two plausible skills silently | The choice was the information the owner had and the launcher threw it away; the two skills do genuinely different work | Ask one question naming both candidates and what each would do |
| Asking a question and routing in the same turn | Two shapes at once means the owner cannot tell whether the work started | Choose one shape: a route, or a question |
| Compiling a summary of the day on the way past | That is a whole skill with its own coverage ledger and citation rules, and a launcher-shaped version of it is uncited | Route to `briefing` and stop |
| Improvising an answer when nothing fits | A general answer dressed as a routing decision is the one output the owner cannot check | Say nothing fits, name the closest domain, and stop |
| Supplying the answer as a harmless aside — "for the record, it's X, but that's outside this skill" | The disclaimer changes nothing: the answer went out unsourced, under no skill's contract, and the owner cannot tell it from a routed one | Leave the answer out entirely; the routing decision is the whole response |
| Offering the whole library when nothing fits | A list of every domain is not the closest domain; it hands the sorting problem back to the owner | Name the one nearest domain and the skills the index lists under it |
| Handing off a mutating intent without naming its effects | The owner authorizes the next turn without seeing what it may reach | Name the target's badges and effect list from the index first |
| Treating a prior turn's route as still correct | The index is regenerated as the library changes, and a route decided earlier is context, not evidence (F2) | Re-read the index for this request |

## Contract

Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.

- Provenance: repo-owned
