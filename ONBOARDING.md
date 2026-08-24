# Onboarding collection

These skills turn recurring setup lessons into reusable, privacy-safe workflows.
Choose the narrowest skill that matches the job:

| Situation | Skill |
| --- | --- |
| Establish an agent owner relationship, goals, boundaries, and working style | `owner-context-onboarding` |
| Connect and verify an MCP or OAuth-backed service | `mcp-connector-onboarding` |
| Recover or transfer an agent across restart, redeploy, or operator handoff | `runtime-handoff-onboarding` |
| Establish a persistent social agent with accounts, identity, and communication boundaries | `social-agent-onboarding` |

## Install

Copy the selected directory from `skills/` into your agent skill directory, then
reload or restart the skill runtime. Each package includes `SKILL.md` and synthetic
evaluation cases in `examples/evals.json`.

The contracts are platform-portable. Where a skill names an OpenClaw command or
state check, use the equivalent native command in your own runtime while preserving
the same verification and completion semantics.

## Safety and sharing

- Do not publish raw onboarding transcripts, credentials, tokens, private memory,
  or owner-only context.
- Distinguish configuration from authorization, reachability, and verified use.
- Treat partial success as partial: report the achieved state and the remaining
  blocker instead of claiming completion.
- Keep durable identity and provenance, but minimize retained personal data.

The evaluation cases are synthetic and safe to share. They test privacy boundaries,
truthful state reporting, restart durability, and handoff completeness.
