# Architecture

`spike-skills` is a personal operating system that agents run for their owner.
The portable core — skills, contracts, catalog, tooling — lives here; a runtime
is an adapter over that core, not a fork of it. A skill is an independently
installable package centered on `SKILL.md`, useful in any runtime that binds the
vocabulary it uses.

## Runtime model

Core plus adapters. A skill names a runtime fact only with a term from
`adapters/vocabulary.yaml` — 31 neutral terms, glossed in
[contracts/skill-contract.md](contracts/skill-contract.md) §R. Each
`adapters/<runtime>/adapter.yaml` binds every term to a concrete value and maps
every datastore namespace and verb; `adapters/<runtime>/ADAPTER.md` is the
human-readable render the agent reads at runtime.
`adapters/adapter.schema.json` fixes the shape and `tools/contracts_check.py`
checks coverage, so a term can never be defined for one runtime only.

Frontmatter `metadata.spike-os.runtime` lists the adapters a skill claims, and
the installer renders it for one of them: it adds that runtime's frontmatter
keys, appends a `## Runtime binding` trailer naming the adapter and its version,
and installs the adapter file itself. Repo-owned tooling is Python 3 standard
library; `jsonschema` is an optional parity check. Plain files are preferred for
small, portable configuration or artifacts.

## Owner datastore

Earlier versions of this file forbade shared user data outright. That ban is
lifted for the *store*, not for this repository. Skills share one namespaced
record store defined by [contracts/datastore.md](contracts/datastore.md), and
the adapter says where it physically lives. A skill declares the namespaces it
touches in `metadata.spike-os.reads_from` and `writes_to`; anything undeclared
is out of bounds.

Twelve namespaces are active — `profile/`, `people/`, `agents/`, `projects/`,
`decisions/`, `journal/`, `conversations/` (a separate root, always untrusted),
`tasks/`, `jobs/`, `effects/`, `checkpoints/`, `notifications/`. Two are
reserved: `calendar/` and `inbox/` may be named and read about, never written.
Identity and authority files are **not** records: they are the adapter's
`identity files` and change only through the identity effects. Credentials live
in the `credential store` and nowhere else.

A skill still owns its own local files and schema and never reads another
skill's private storage. What is shared is the datastore, through declared
namespaces.

## Sync

A namespace whose system of record is a provider follows
[contracts/sync.md](contracts/sync.md): one id map, semantic keys, readback
fields, a provider-wins conflict policy, and one state machine every skill
reports in. `tasks/` is the live instance; `calendar/`, `inbox/`, and
`people/contact-card` are declared and reserved.

## Effects and permissions

[contracts/capabilities.yaml](contracts/capabilities.yaml) is a closed enum of
21 effects, each carrying tool hints, an approval mode, and a resource class. A
skill performs only the effects it declares; an empty list is valid.
Authorization is per effect and per invocation — never inherited from a sender,
a handoff, a schedule, a prior effect, or external content — and every mutating
effect appends an `effects/` record with its readback. Declaration is lint and
adapter policy, not a security boundary; the runtime's own permissions are that.

## Dispatcher

`skills/home/` is the entry point: it reads `catalog/index.md`, routes to
exactly one skill, and never performs the task itself. Invoked with no request at
all, it prints the domain index instead — the eight sections and the skills under
them — because the owner opening the library is asking what is in it. The index
is generated from frontmatter, so it cannot drift from the library. `briefing` is
the today view, not the router.

## Notifications

[contracts/notifications.md](contracts/notifications.md) is the only way a skill
reaches the owner outside its own reply: one call, one delivery key, an
idempotent retry, and quiet hours from the adapter that govern delivery rather
than execution.

## Data boundary

The public repository may contain code, schemas, migrations, synthetic fixtures,
examples, and evaluation cases. It must not contain:

- user databases or personal records;
- credentials, tokens, provider exports, or secrets;
- private memory or raw conversation transcripts;
- caches or generated local state.

Adapter files in this repository hold placeholders; the owner's local adapter
files hold the personal values those placeholders stand for. Local data paths
must be configurable and ignored by version control. A skill that does not need
persistence must not introduce it.

## Deferred scope

The following are deliberately outside the current product:

- hosted services, accounts, billing, or deployment infrastructure;
- a shared control plane or personal-cell runtime;
- shared Postgres, DBOS, event streams, or cross-user synchronization;
- a universal application shell or custom UI runtime;
- calendar, contacts, and inbox skills, while those namespaces are reserved;
- per-agent vault permissions, embedding-backed retrieval, and a datastore linter;
- a "today" block inside `home`.

These concerns may be reconsidered only when a real use case cannot be solved
cleanly without them. Re-checked at the end of phase 5: every item above is still
outside the product, and nothing built in the eight rewrite batches, the
installer, or the OpenClaw staging crossed one of these lines. `home`'s bare
invocation prints the index rather than compiling a day, so the "today block"
exclusion holds.
