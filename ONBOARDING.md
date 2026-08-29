# Onboarding collection

Four skills bring an agent up, and each one is chosen by the moment that
prompted the request: a new working relationship to establish
(`owner-context-onboarding`), a service to connect or prove
(`mcp-connector-onboarding`), a restart, redeploy, migration, or
maintainer change to recover from (`runtime-handoff-onboarding`), or an
external identity to bring into existence (`social-agent-onboarding`).

Their own `description` and `## When not to use` sections are the routing
table — each names its three siblings with the condition that sends work
there. Read those rather than a copy here, which would be a fifth place
for the routing to drift out of step. Everything else these skills once
restated in common — secret handling, partial-success reporting, what may
be shared — lives in
[contracts/skill-contract.md](contracts/skill-contract.md) and
[contracts/datastore.md](contracts/datastore.md).

**Install.**

```sh
python3 tools/install_skill.py --runtime claude-code owner-context-onboarding
python3 tools/install_skill.py --runtime claude-code --check
```

The installer renders the portable `SKILL.md` for the runtime you name,
writes the adapter file the skill's backticked vocabulary terms resolve
against, and stamps the installed directory so `--check` can report drift
later. `--dry-run` prints what it would write. It refuses a skill whose
`metadata.spike-os.runtime` excludes the target, a destination directory
it did not install, and a skill that depends on a term the adapter marks
UNCONFIRMED. That last refusal is not one runtime's quirk: it applies on
both, wherever an adapter cannot attest a binding a skill's declaration
needs. It is what stops `daily-task-manager` and `briefing` installing on
OpenClaw today, where whether the runtime registers a task connector is
still an open question.

A binding the runtime knows to be absent or partial is the other case, and
it is marked DEGRADED rather than UNCONFIRMED: the skill's own contract
already states what it does without it, so the installer installs it and
prints a `degraded:` note naming the term. On claude-code both
`task provider` (no Todoist server; tasks are mirror-only) and
`mail provider` (no agentmail; the owner's Gmail and Google Calendar are
connected) are DEGRADED, so the same two skills install there and disclose
the reduced state at run time.
