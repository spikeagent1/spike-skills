---
name: "cron-scheduler"
description: "Make scheduled-job mutations explicit, idempotent, verified, and reversible."
mutating: true
---

# Cron Scheduler

Manage scheduled work without duplicating jobs, shifting requested timing, or confusing execution with notification delivery.

## Classify authority
Classify the request as inspect, create, update, pause, resume, test, or remove. Resolve the scheduler, owner, execution account, external side-effect scope, and delivery account. A request to inspect is read-only. A request to change an existing job authorizes only the resolved job and named fields. Deletion requires explicit intent.

## Discover before mutation
List authoritative scheduler capabilities and all relevant jobs, following pagination. Resolve by stable scheduler ID first, then an exact managed semantic key. Inspect the full current definition, version or fingerprint, recent runs, handler availability, resource locks, and delivery destination.

Never infer absence from a partial listing or create a second job because a display name is ambiguous.

## Normalize JobSpec
Resolve:

- stable job key and display name;
- scheduler, runner/handler, task or skill, version, and inputs;
- IANA timezone and schedule;
- daylight-saving and missed-run policy;
- start, end, and enabled state;
- timeout, retry/backoff, and overlap policy;
- execution target and account;
- output path and checkpoint state;
- delivery channel, recipient/account, mode, quiet-hours behavior, and failure escalation.

Clarify only material omissions that cannot be derived from trusted owner context. Preserve the requested time unless a demonstrated resource or concurrency conflict requires a change.

## Plan and validate
Compute create, update, no-op, pause, or delete. Show the exact material diff before mutation when ambiguity exists. Parse the schedule and preview upcoming occurrences in local time and UTC, including a daylight-saving boundary when relevant. Validate handler, credentials, permissions, target account, and checkpoint path.

Use a safe dry-run or representative one-shot proportional to side effects. Do not apply a fixed item-count rule to jobs that are not bulk workflows.

## Separate execution from delivery
Quiet hours govern delivery unless the job itself is unsafe to execute then. Never infer an awake-state override from weak activity signals. Define whether results are immediate, held, summarized, silent, or failure-only, and how held messages are released. Execution and delivery use separate idempotency keys.

## Idempotency
Use a definition key to prevent duplicate registration. Use an occurrence key based on the stable job key and scheduled instant to deduplicate runs. External mutations use stable domain keys, and notifications use delivery keys. Write checkpoints atomically only after terminal verification. A retry resumes incomplete work and never repeats verified mutations or deliveries.

## Mutate transactionally
Snapshot the prior definition and keep a rollback handle. Update by stable ID with optimistic version/fingerprint when supported. Do not delete and recreate merely to edit. For creation, retain the new ID so rollback can remove exactly that job.

## Verify and rollback
Read the job back from the authoritative scheduler and compare every normalized field. Confirm exactly one managed job, enabled state, handler availability, execution and delivery routing, and upcoming occurrences. A requested test is complete only after terminal run status and observable side effects are checked.

If verification fails, restore the prior definition or remove only the newly created job, then verify restoration. If rollback fails, disable the affected job when safe and report its exact residual state and manual recovery path.

## Report
Report action, stable ID/key, timezone and schedule, upcoming runs, runner, target account, delivery behavior, verification evidence, and rollback state. An accepted API request is not completion.

## Failure conditions
Fail review if the workflow mutates before discovery; creates a duplicate; uses an ambiguous timezone; silently changes requested timing; conflates execution and delivery; lacks occurrence-level idempotency; checkpoints before verification; claims success without readback; or cannot identify a precise rollback target.

## Dependencies

Use only the connectors, local files, scripts, or source material explicitly named by the user or by this skill. If a dependency is unavailable, report the blocked phase instead of fabricating completion. No hidden hosted dependency, shared user database, or cross-skill private storage.


## Provenance

Owned by Spike unless catalog metadata marks the skill as adapted. Public repository content is maintained as portable skill source with synthetic fixtures only.
