# OpenClaw staging and handoff

Status as of `2d27ce3`: staged and verified locally, **nothing pushed**. No
skill has been copied to a Railway volume, no commit or PR has touched
`chughtapan/vibe-blogging`, and no `claude` call has been made against the
running Spike agent. This document is the handoff — the exact steps for
whoever (Spike, or the owner) performs the copy, the smoke test they should
run afterward, and what in `adapters/openclaw/adapter.yaml` still needs
confirming from inside the running deployment.

## 1. What's staged

```
python3 tools/install_skill.py --runtime openclaw --all --dest dist/openclaw/workspace/skills
python3 tools/check_staging.py --runtime openclaw --dest dist/openclaw/workspace
```
(both wrapped as `make stage-openclaw`)

31 of 31 skills installed under `dist/openclaw/workspace/skills/`, plus a
rendered `dist/openclaw/workspace/ADAPTER.md` and `adapter.resolved.yaml`.
`briefing` and `daily-task-manager` stage with a printed `degraded:` note —
both declare `task provider`, which the openclaw adapter marks DEGRADED
(no Todoist connector in `runtime/openclaw.json`; the skills disclose
mirror-only, see §4.1). `tools/check_staging.py` found 0 findings across the
31 staged skills: 0 runtime-specific tokens leaked into a body, 0 backticked
vocabulary terms the adapter can't resolve, 0 `metadata.openclaw.requires.*`
blocks out of step with their own Dependencies line. `dist/` is gitignored,
so none of this is in git.

## 2. Copy steps

Two separate destinations — do not confuse them. The skills dir is an
ephemeral volume path (survives a restart, not a redeploy without this step);
`ADAPTER.md` has to go through git or every redeploy erases it.

### 2.1 Skills onto the Railway volume

Builds the new tree alongside the old one, then swaps in one step so a bad
copy never leaves `skills/` half-written:

```sh
tar -C dist/openclaw/workspace/skills -czf - . | \
  railway ssh --service spike -- \
    'rm -rf /data/.openclaw/workspace/skills.new && mkdir -p /data/.openclaw/workspace/skills.new && tar xzf - -C /data/.openclaw/workspace/skills.new'

railway ssh --service spike -- '
  set -e
  test -d /data/.openclaw/workspace/skills.new
  rm -rf /data/.openclaw/workspace/skills.prev-2026-08-29
  mv /data/.openclaw/workspace/skills /data/.openclaw/workspace/skills.prev-2026-08-29
  mv /data/.openclaw/workspace/skills.new /data/.openclaw/workspace/skills
'
```

Then reload so the running agent picks up the new tree: `openclaw doctor`
through the spike wrapper (the adapter's `runtime health check`), or a full
`railway ssh -- 'openclaw restart'` if the doctor reports a stale skill list.
See §5 for the rollback this pairs with.

### 2.2 `ADAPTER.md`, through the git seed

Spike's workspace is re-seeded from `chughtapan/vibe-blogging`'s
`runtime/workspace/` on every boot, so `ADAPTER.md` copied only onto the
volume is lost on the next deploy. It has to land in git:

1. In a checkout of `chughtapan/vibe-blogging`, copy the rendered file in:
   `cp <this repo>/dist/openclaw/workspace/ADAPTER.md runtime/workspace/ADAPTER.md`
2. In `runtime/workspace/AGENTS.md`, add the one-line reference between
   markers (the installer tried this automatically and printed this exact
   block, because `runtime/workspace/AGENTS.md in chughtapan/vibe-blogging`
   is not a path on the box running the installer):
   ```
   <!-- spike-os:begin -->
   See `ADAPTER.md` for what the runtime terms in your skills resolve to.
   <!-- spike-os:end -->
   ```
3. Commit both, open a PR against `chughtapan/vibe-blogging`, and get it
   merged through the normal review — this is a `proposal workflow`
   (Skill Workshop) change, applied only on explicit owner approval, same as
   any other write to that repo's `main`.
4. The next Railway deploy re-seeds the workspace with both files in place.

## 3. Smoke test

Three prompts, mirroring Task 23's claude-code smoke test, run against the
live Spike agent after the copy lands and the gateway reloads. Capture the
transcripts (redacted) and send them back — see the handoff email.

| Prompt | Expected |
|---|---|
| `/home` | The launcher itself runs (it is staged and loads without a frontmatter warning). A bare invocation with no request is the "what can you do" case per `skills/home/SKILL.md` (Inputs, owner-request row): it prints the domain index — the eight sections, what each covers, and the skills listed under them — from the bundled `references/index.md` (which carries an `installed here` column on OpenClaw) and stops, asking nothing. A transcript that prints that index is correct; one that says "no intent to route" is the pre-cleanup behaviour and is a regression. |
| "brief me for today" | Routes to `briefing`, now staged (§4.1). Expected: a cited, read-only picture built from what the datastore and the mail provider return, with the calendar and task providers reported as unavailable (`calendar provider` is none configured; `task provider` is DEGRADED — mirror-only) rather than invented. A briefing that claims meetings or due items it could not read is a regression. |
| "add a task: renew the domain" | Routes to `daily-task-manager`, now staged (§4.1). Expected: the skill's own Output-contract block with `target : task provider mirror-only — no connector registered`, a preview of the mirror record, and no claim of a provider write — the DEGRADED disclosure `contracts/sync.md` prescribes. A reply that says the task "was added to Todoist" is a regression. |

## 4. Adapter bindings checked against the runtime (2026-08-29)

Spike's review asked for the four assumptions in `adapters/openclaw/adapter.yaml`
to be reconciled with the runtime. They were checked against the git-owned
runtime files in `chughtapan/vibe-blogging` (`runtime/openclaw.json`,
`runtime/workspace/{HANDOFF,USER,SOUL,IDENTITY}.md`) and, for the datastore
verbs, against the GBrain source at the tag the volume runs. One remains a
question for Spike (4.4's live check); the others are settled.

### 4.1 `task provider` — DEGRADED (was UNCONFIRMED)
`runtime/openclaw.json` (keys: `agents`, `channels`, `commands`, `gateway`,
`plugins`) registers no Todoist connector. That is a *known* absence, and
`contracts/sync.md` already states the fallback: `system_of_record` flips to
the datastore and the skill discloses that the object is mirror-only. So the
binding is DEGRADED, not UNCONFIRMED, and `briefing` and `daily-task-manager`
now **stage** (31 of 31) with a printed `degraded:` note. **Spike:** if the
live volume copy of `openclaw.json` registers a task connector under some key,
say which — the note flips to a confirmed binding and the mirror-only
disclosure stops applying.

### 4.2 `owner timezone` — owner-supplied (was UNCONFIRMED)
No git-owned runtime file records a timezone. It is not a runtime fact to
confirm; it is the owner's value, filled as `OWNER_TZ` in
`${HOME}/.config/spike-os/openclaw.local.yaml` on the host that runs the
installer. Until then the rendered `ADAPTER.md` shows the literal
`${OWNER_TZ}` and skills treat the timezone as unknown (F2). Nothing for Spike
to confirm.

### 4.3 `norms directory` — convention, not yet created (was UNCONFIRMED)
`.agents/behaviors/<name>/BEHAVIOR.md` does not exist anywhere in
`chughtapan/vibe-blogging`. The path stays the agreed convention; skills that
cite it treat it as aspirational, not load-bearing. Nothing for Spike to
confirm until the first behavior file lands.

### 4.4 Datastore verb spellings — confirmed against the 0.46.1 source (was UNCONFIRMED)
The adapter's verb map was first read off GBrain 0.18.2 on the owner's host.
It was re-checked on 2026-08-29 against `src/core/operations.ts` at tag
`v0.46.1.0` of `garrytan/gbrain` (the version `HANDOFF.md` says the volume
runs): the CLI names are the ops' `cliHints.name` — `get <slug>`,
`put <slug>` (page on stdin), `list --type <ns> --limit <n>`,
`timeline <slug>`, `timeline-add <slug> <date> <summary> [--detail <text>]`,
`search <query>`. Two spellings were corrected (`--limit` instead of `-n`;
the third `timeline-add` positional is `summary`). **Spike:** the one live
check left is `gbrain --help` on the volume confirming those names and that
`/data/.local/bin/gbrain --version` is still 0.46.1.x; say if
`conversations/` has since been populated.

## 5. Rollback

The copy step in §2.1 already keeps the previous tree: `skills.prev-2026-08-29/`
sits next to the new `skills/` rather than being deleted. To roll back:

```sh
railway ssh --service spike -- '
  set -e
  test -d /data/.openclaw/workspace/skills.prev-2026-08-29
  rm -rf /data/.openclaw/workspace/skills.bad
  mv /data/.openclaw/workspace/skills /data/.openclaw/workspace/skills.bad
  mv /data/.openclaw/workspace/skills.prev-2026-08-29 /data/.openclaw/workspace/skills
'
```
then reload the same way as after the original copy. `ADAPTER.md` rolls back
through git — revert the merge commit in `chughtapan/vibe-blogging` and wait
for the next deploy to re-seed the previous version.

## 6. Not done here

No skill was copied to the Railway volume. No commit or PR touched
`chughtapan/vibe-blogging`. No `claude` call was made against the live Spike
agent — the smoke test in §3 is Spike's to run and report back. `dist/` is
gitignored and was never staged for commit.

See `contracts/skill-contract.md` section R for what every backticked term in
a skill body resolves against.
