# Architecture contract

`spike-skills` is a public library of portable agent skills. It is not a hosted
personal-data platform.

## Runtime model

- A skill is an independently installable package centered on `SKILL.md`.
- Skills may declare connectors, command-line tools, or language runtimes as
  dependencies, but must remain useful outside Spike's deployment.
- TypeScript and Effect are the default for repository-owned executable tooling.
- Plain files are preferred for small, portable configuration or artifacts.
- SQLite may be used when a skill genuinely needs structured local persistence.
- A skill owns its own local files, SQLite schema, and migrations.
- Skills do not read or write another skill's private storage.
- Cross-skill composition uses explicit inputs and outputs, never a shared user
  database.

## Data boundary

The public repository may contain code, schemas, migrations, synthetic fixtures,
examples, and evaluation cases. It must not contain:

- user databases or personal records;
- credentials, tokens, provider exports, or secrets;
- private memory or raw conversation transcripts;
- caches or generated local state.

Local data paths must be configurable and ignored by version control. A skill
that does not need persistence must not introduce it.

## Deferred scope

The following are deliberately outside the current product:

- hosted services, accounts, billing, or deployment infrastructure;
- a shared control plane or personal-cell runtime;
- shared Postgres, DBOS, event streams, or cross-user synchronization;
- a universal application shell or custom UI runtime.

These concerns may be reconsidered only when a real shared-skill use case cannot
be solved cleanly without them.
