---
name: "daily-task-manager"
description: "Make task state owner-visible, provider-verified, idempotent, and reconciled."
mutating: true
---

# Daily Task Manager

Manage add, review, complete, defer, and remove operations without creating tasks the owner cannot see or letting a local mirror masquerade as the external source of truth.

## Choose the system of record
Use the task system the owner selected. For Tapan, Todoist is primary when its connector is installed and authenticated. The brain page at ops/tasks.md is a searchable mirror and recovery ledger, not proof that a Todoist task exists.

If the requested provider tool is unavailable or authentication is unverified, do not claim setup or task creation is complete. Report the exact blocked phase and keep any local draft visibly marked PENDING_EXTERNAL rather than saved as an active provider task.

## Mode and scope
Classify add, review, complete, defer/reschedule, edit, or remove before mutation. Review is read-only. Resolve provider account, project/list, exact task identity, description, priority, due date/timezone, labels, recurrence, and reminder only when supplied or trusted defaults exist. Never invent due dates, recurrence, reminders, projects, or priorities.

Remove requires explicit delete language; suggest complete or defer when intent is ambiguous.

## Discover before mutation
Read the provider account and target project/list. For edits, completion, deferral, or removal, resolve by provider task ID first and stable local mapping second. Description matching is restricted to active tasks and must fail closed on zero or multiple matches.

Follow pagination and do not infer absence from the first page.

## Stable identity and idempotency
Maintain a mapping between provider task ID and local mirror ID. Use a semantic creation key from normalized description, target project, due data, and owner account. An identical retry returns the existing verified task rather than creating another.

Provider identity is authoritative. Never mint a second local ID for an existing provider task.

## Mutation order
For externally visible operations:

1. write to the provider;
2. read the task back from the provider;
3. verify account, project, content, status, priority, due/timezone, recurrence, and labels;
4. update the brain mirror with the verified provider ID and timestamp;
5. read the mirror back and confirm the mapping.

If provider verification fails, do not update the mirror as active. If mirror update fails after provider success, report PROVIDER_VERIFIED_MIRROR_PENDING and reconcile from the provider later. Never roll back a valid provider task merely because the optional mirror failed unless the owner requested atomic behavior.

For a brain-only task explicitly requested by the owner, say that it will not appear in Todoist.

## Concurrency
Serialize mutations against the same provider task and local mirror. Before writing the mirror, re-read provider state and the page, preserve unknown sections, and update only the mapped task. If version checks are available, use them.

## Review and reconciliation
Review from the provider first, then reconcile the local mirror:

- provider-only task: add or repair the mirror;
- mirror-only active task: mark EXTERNAL_MISSING and investigate, never present it as provider-visible;
- divergent fields: provider wins unless the owner explicitly chose the brain as source;
- duplicate semantic keys: report and request a merge decision rather than deleting automatically.

## Completion states
Use exact states: DRAFT_LOCAL, PROVIDER_ACCEPTED_UNVERIFIED, PROVIDER_VERIFIED_MIRROR_PENDING, SYNCED_VERIFIED, EXTERNAL_MISSING, AMBIGUOUS, NOT_FOUND, or FAILED.

A task operation is complete only when the authoritative provider readback matches the intended state. Return action, provider task ID, mirror ID, provider account/project, state, verified fields, and any reconciliation remainder.

## Failure conditions
Fail review if a brain write is reported as Todoist success; authentication is assumed from configuration alone; an identical retry creates a duplicate; a partial list is treated as complete; ambiguity mutates a task; provider state is not read back; or the owner cannot locate the task in the named account/project.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.
