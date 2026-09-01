# Notification contract v1

<!-- contract-version: 1 -->

The only way a skill reaches the owner outside its own reply. Requires the
`notify:owner` effect; anyone other than the owner is `message:send`.

## Call

`notify(recipient=owner, payload, mode, delivery_key, urgency)`

- **mode** ∈ `immediate`, `held`, `summarized`, `silent`, `failure-only` (`skills/cron-scheduler/SKILL.md:83`).
- **delivery_key** = `<skill>/<subject-id>/<event>/<occurrence>`. A retry on the same key is a no-op, never a second message (`skills/cron-scheduler/SKILL.md:62`).
- **urgency** — the caller's claim; it never overrides quiet hours by itself.
- The channel is the adapter's `notification channel`; a skill never names a product.

## Quiet hours

Quiet hours come from the adapter (owner timezone plus a window). They govern
**delivery, not execution** — unless the job itself is unsafe to execute during
quiet hours, in which case execution is deferred too. A job that runs has its
notification held (`skills/cron-scheduler/SKILL.md:95`). Held messages are
released as one digest at the end of the window. Awake state is never inferred
from activity signals.

Exactly two overrides send during quiet hours
(`skills/owner-dream-cycle/SKILL.md:58`):

1. a privacy or security issue needing immediate owner attention;
2. a contradiction affecting active irreversible work.

## Ledger

Every call writes one `notifications/` record: `delivery_key`, `channel`,
`mode`, `state`, `sent_at`, `readback`. States are `QUEUED`, `HELD`, `SENT`,
`FAILED`, `SUPPRESSED`; report the state actually reached and no later one (O3).
Execution and delivery use separate idempotency keys
(`skills/cron-scheduler/SKILL.md:97`).

A request to tell the owner something on a named channel is
`notify(owner, mode=immediate)`; the adapter chooses the channel.
