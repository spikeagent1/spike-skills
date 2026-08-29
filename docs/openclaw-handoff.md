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

29 of 31 skills installed under `dist/openclaw/workspace/skills/`, plus a
rendered `dist/openclaw/workspace/ADAPTER.md` and `adapter.resolved.yaml`.
`briefing` and `daily-task-manager` were **refused**, not staged — both
declare `task provider` and the openclaw adapter marks that term UNCONFIRMED
(see §4.1). `tools/check_staging.py` found 0 findings across the 29 staged
skills: 0 runtime-specific tokens leaked into a body, 0 backticked vocabulary
terms the adapter can't resolve, 0 `metadata.openclaw.requires.*` blocks out
of step with their own Dependencies line. `dist/` is gitignored, so none of
this is in git.

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
| `/home` | The launcher itself runs (it is staged and loads without a frontmatter warning). A bare invocation with nothing to route is expected to say so plainly — Task 23 found the launcher answers "there is no intent to route; say so and stop", not a domain index — so a Spike transcript matching that is correct, not a regression. |
| "brief me for today" | Routes to `briefing` if it were staged — but it is not (§4.1), so the honest outcome is either `home` naming that no briefing skill is installed, or (if the request routes to a skill that reads the `owner datastore` anyway) the OpenClaw verb map resolving it: `gbrain get`/`search`/`list --type <ns> -n <limit>`/`timeline`, never a claude-code path or an MCP call — this box has no gbrain MCP fallback (§adapter Notes on fallbacks). |
| "add a task: renew the domain" | `daily-task-manager` is not staged either (§4.1), so there is no task skill to route to at all. The expected, honest answer is that no task-management skill is installed on this box — not a fabricated Todoist write, and not a silent no-op. If some other skill picks up the request generically, it must still disclose mirror-only per the `task provider` binding, exactly as Task 23 got from `daily-task-manager` on claude-code. |

## 4. UNCONFIRMED — needs Spike's confirmation

Four notes in `adapters/openclaw/adapter.yaml` are marked UNCONFIRMED: no
git-owned file in the runtime states them, so they are assumptions, not
attested facts (F2). Each is a question the running deployment can answer.

### 4.1 `task provider`
> UNCONFIRMED — `runtime/openclaw.json` registers no Todoist connector, so
> tasks are mirror-only until one exists.

**Question:** does `/data/.openclaw/openclaw.json` (or the deep-merged
volume copy) register a Todoist connector today, under any key? **Value that
resolves it:** the connector's registry key, if one exists — bind
`task_provider` to it and `briefing`/`daily-task-manager` can be staged.
Absent that, confirm it is still unregistered so the mirror-only disclosure
stays correct.

### 4.2 `owner timezone`
> UNCONFIRMED — no git-owned runtime file records it; the owner sets it in
> the overrides file.

**Question:** does any workspace file (`USER.md`, a config) already record
the owner's timezone? **Value that resolves it:** an IANA timezone string
(e.g. `America/Los_Angeles`) — if Spike doesn't have one on file, this is a
value only the owner can supply, into `${HOME}/.config/spike-os/openclaw.local.yaml`'s
`OWNER_TZ` on the host that runs the installer.

### 4.3 `norms directory`
> UNCONFIRMED — no such directory exists in the repo yet; this is the agreed
> convention.

**Question:** does `.agents/behaviors/<name>/BEHAVIOR.md` exist anywhere in
the runtime repo tree yet? **Value that resolves it:** either a confirmed
example path (then the note can drop), or confirmation it is genuinely not
created yet (then skills citing it should treat it as aspirational, not
load-bearing).

### 4.4 Datastore verb spellings
> UNCONFIRMED — verb spellings were read from the GBrain 0.18.2 CLI on the
> owner's host; the volume runs 0.46.1, so re-check after the next runtime
> build. `conversations/` is a separate root and no private corpus has been
> imported yet.

**Question:** run `gbrain doctor --json` and confirm the verb syntax in
`ADAPTER.md`'s Datastore table (`get <slug>`, `search <query>`,
`list --type <ns> -n <limit>`, `timeline <slug>`, `put <slug>`,
`timeline-add <slug> <date> <text>`) against GBrain 0.46.1. **Value that
resolves it:** a yes/no per verb, and if `conversations/` has since been
populated, say so as well.

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
