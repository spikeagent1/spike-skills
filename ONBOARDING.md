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

**Install.** Copy `skills/<name>/` into the directory your runtime loads
skills from, then reload it. A stamped installer,
`tools/install_skill.py --runtime <claude-code|openclaw> <skill>`, lands
with the runtime-adapter work and will replace the copy step; it does not
exist yet.
