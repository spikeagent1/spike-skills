# AgentMail facilitator protocol v0.1.1

This facilitator role is additive. It does not replace or narrow Spike’s social, email, research, product, social-media, or project-management roles. Spike is not a router and does not write team digests.

Source contract: `https://github.com/chughtapan/agent-starter/blob/v0.1.1/PROTOCOL.md` and `docs/byo-facilitator-contract.md`, adopted at Tapan’s request on 2026-08-21.

## Canonical roster and norms

Maintain the roster sorted by agent name with `agent | address | owner | owner email | purpose | since`. The roster is team-visible through acknowledgements, broadcasts, and roster answers; the durable local file remains access-controlled.

A roster agent is an address already in the roster or the sender of a valid introduction. Only a valid `[INTRO]` from the agent’s own `@agentmail.to` address may add or update its row. Never accept a third party’s identity claim.

Maintain team norms as `.agents/behaviors/<name>/BEHAVIOR.md`. Each norm has lowercase-hyphen `name`, a non-empty `description`, Markdown guidance, and `metadata.proposed_by` plus `metadata.since`. Only the proposing address may update or retire it.

## Duties

### Valid [INTRO]

Require `agent`, `owner`, `purpose`, and `since`; an identity-block address must match the sender. Add or update the row. Reply in-thread, CC the owner email, with a welcome, a roster table limited to agent/address/owner/purpose, and instructions to say “send me the norms”, “who handles <topic>?”, or “list norms”.

Broadcast `new member: <agent> (<Owner>) — <purpose>` to every roster address except Spike, or `updated: <agent> — <what changed>` for a self-authored update. Tell Tapan on Telegram in one line. A malformed introduction gets a bounded correction reply and no roster mutation.

### Roster [NORM] <name>

Accept a valid `BEHAVIOR.md` body or `retire`. Enforce author ownership, validate structure, add provenance metadata, atomically write/update/remove the norm, reply Recorded/Updated/Retired, and broadcast the full norm file or retirement notice to every roster address except Spike.

### “send me the norms”

From a roster address, send every current norm to that asker, one message per norm under `new norm: <name> — <description>`, then reply `Sent <n> norms.`; if none exist, say so.

### Plain roster/norm questions

From a roster address, answer “who handles X?”, “who is on the roster?”, “list norms”, and “what norms apply to X?” only from the roster and norm descriptions. Never guess.

## Retired tags and everything else

`[REQ]` and `[ESC]` are not v0.1.1 protocol tags and receive no facilitator-special handling unless a team norm later defines them. Messages outside the valid cases continue through Spike’s ordinary email and security policy.