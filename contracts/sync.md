# Provider sync contract v1

<!-- contract-version: 1 -->

How a namespace whose `system_of_record` is a provider stays in agreement with
that provider. Generalized from `skills/daily-task-manager/SKILL.md:17-58`.

## Instance declaration

A sync instance is one namespace (or one kind within it) bound to one provider.
It declares:

- **provider_role** — a `contracts/skill-contract.md` §R vocabulary term, never a product name.
- **system_of_record** — `provider` or `datastore`; the owner selects it per namespace (`skills/daily-task-manager/SKILL.md:41`) and the skill discloses the choice when it is not the provider (`skills/daily-task-manager/SKILL.md:42`).
- **id_map** — a stable internal UID against, per provider, `{external_id, version_token, last_synced_with}`. Provider identity is authoritative; never mint a second internal ID for an existing provider object (`skills/daily-task-manager/SKILL.md:53`).
- **semantic_key** — the normalized fields that identify an object before it has an `external_id` (`skills/daily-task-manager/SKILL.md:94`).
- **readback_fields** — the fields compared after every provider write (`skills/daily-task-manager/SKILL.md:56`).
- **conflict_policy** — provider-wins unless the owner explicitly chose the datastore (`skills/daily-task-manager/SKILL.md:52`). A divergence is surfaced as a ConflictSet or duplicated on both sides, never silently merged (design-derived).
- **pagination** — required on every listing; absence is never inferred from one page (`skills/daily-task-manager/SKILL.md:24`, `skills/cron-scheduler/SKILL.md:53`).
- **match_fallback** — semantic-key matching runs against active objects only and fails closed on zero or more than one match (`skills/daily-task-manager/SKILL.md:22`).
- **fast/slow rule** — per-record `dirty` and `deleted` flags are trusted only when `last_synced_with` equals the provider's current version token; otherwise do a full field compare.
- **command_ids** — every provider write carries an idempotent command UUID, and a locally created object carries a temp id mapped to the provider id on acceptance (`skills/publish/SKILL.md:58`).
- **replay** — local operations pending at the start of a run replay after the provider readback, never before it.

## States

`DRAFT_LOCAL → PROVIDER_ACCEPTED_UNVERIFIED → PROVIDER_VERIFIED_MIRROR_PENDING →
SYNCED_VERIFIED`. Terminal: `EXTERNAL_MISSING`, `AMBIGUOUS`, `NOT_FOUND`,
`FAILED`. `PENDING_EXTERNAL` is `DRAFT_LOCAL` plus a named blocked phase
(`skills/daily-task-manager/SKILL.md:56`). Run outcomes: `CONFLICT` (divergent
fields), `BLOCKED` (provider unreachable or unauthenticated), `READ_ONLY` (a
review operation). Stated once here; skills reference these names and add none
(`skills/daily-task-manager/SKILL.md:56`).

## Mutation order

1. Write to the provider.
2. Read the object back from the provider.
3. Verify every `readback_fields` entry.
4. Write the mirror with the provider id and timestamp.
5. Read the mirror back and confirm the id map.

If provider verification fails, the mirror is not marked active. If the mirror
write fails after provider success, report `PROVIDER_VERIFIED_MIRROR_PENDING`
and reconcile later. Never roll back a valid provider write because the mirror
failed, unless the owner asked for atomic behavior
(`skills/daily-task-manager/SKILL.md:40`). Serialize mutations against the same
object and re-read before writing the mirror (`skills/daily-task-manager/SKILL.md:45`).

## Reconciliation

Review from the provider first, then reconcile
(`skills/daily-task-manager/SKILL.md:57`):

| Case | Resolution |
|---|---|
| Provider-only object | Repair or create the mirror record (`skills/daily-task-manager/SKILL.md:57`). |
| Mirror-only active object | Mark `EXTERNAL_MISSING`; never present it as provider-visible (`skills/daily-task-manager/SKILL.md:51`). |
| Divergent fields | Apply `conflict_policy`; surface the ConflictSet either way (`skills/daily-task-manager/SKILL.md:52`). |
| Duplicate semantic keys | Report and request a merge decision; never auto-delete (`skills/daily-task-manager/SKILL.md:53`). |

## Instances

| Namespace | Status | Provider role | Notes |
|---|---|---|---|
| `tasks/` | active | `task provider` | The reference instance. Where no provider connector is authorized, `system_of_record` flips to `datastore` and the skill discloses that the object is mirror-only (`skills/daily-task-manager/SKILL.md:42`). |
| `calendar/` | reserved | `calendar provider` | Conduit will use vdirsyncer status semantics and RFC 6578 sync tokens. |
| `people/` contact-card | reserved | `contacts provider` | One facet of an existing `people/` entity, never a separate namespace. |
| `inbox/` | reserved | `mail provider` | Refs and triage state only; message bodies are never mirrored. |

## daily-task-manager as the reference instance

Moves here, and is cited rather than restated by that skill: the state enum, the
mutation order, the reconciliation cases, id-map and semantic-key mechanics,
pagination, match-fallback, and the never-roll-back rule.

Stays in the skill, because it is task-specific: mode classification across add,
review, complete, defer, edit, and remove
(`skills/daily-task-manager/SKILL.md:17`); the explicit-delete-language
requirement for remove (`skills/daily-task-manager/SKILL.md:54`); and the
mirror-only disclosure when no task provider is authorized
(`skills/daily-task-manager/SKILL.md:42`).
