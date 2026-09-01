# Onboarding — the first hour

[README.md](README.md#start-here) has the three commands. This is what happens
between them: what each step writes, what the first two invocations should look
like, and what to read when a run says something you have not seen before.

You need **Python 3.11 or newer** — the version CI pins. An older interpreter is
told the floor and stops, rather than failing on whatever construct it reached
first.

## Minute 0 — `make start`

```sh
git clone https://github.com/spikeagent1/spike-skills.git
cd spike-skills
make start
```

It asks for ten values — your name, your timezone, where your vault lives, when
your quiet hours run, the forge account the agent commits as, and four you can
answer `none` to. Each question carries a gloss and an example. Nothing is
guessed from your machine: the host timezone is not authoritative, and the
repository never learns a personal value.

Four things get written, all outside this repository:

| Path | What it is |
| --- | --- |
| `~/.config/spike-os/claude-code.local.yaml` | Your ten values. The only file that holds them. Never committed. |
| `~/.claude/spike-os/ADAPTER.md` | The rendered adapter: what every backticked term in an installed skill resolves to on **this** host. |
| `~/.claude/spike-os/adapter.resolved.yaml` | The same bindings, machine-readable, with your values filled in. Keep it out of any commit. |
| `~/.claude/CLAUDE.md` | One import line, between `<!-- spike-os:begin -->` and `<!-- spike-os:end -->`. Nothing else in the file is touched, and an unpaired marker is refused rather than repaired. |

Then `~/.claude/skills/<name>/` for each installed skill, each carrying a
`.spike-os.json` stamp. The installer writes only into directories carrying that
stamp — a skill you wrote yourself, or one another tool installed, is never
overwritten.

`~/.claude` is a git repository on some machines. The installer never commits;
it prints the `git -C ~/.claude commit` command and leaves it to you.

## Minute 3 — the verification

The last step of `make start` runs one real invocation:

```sh
claude -p "/home"
```

It costs pennies and needs an authenticated session. If the CLI is missing, if
you passed `--no-smoke`, or if the runtime is not `claude-code`, the run prints
that command for you to run by hand — it is never skipped in silence. A run that
renders four skills cleanly and answers nothing is not a working library, which
is the whole reason this step exists.

## Minute 5 — the first `/home`

Open Claude Code and type `/home` with nothing after it:

```
/home
```

A bare invocation is the index. `home` prints the eight domains and the skills
under each, read from [catalog/index.md](catalog/index.md) — not from memory. If
the column says `not installed` next to a skill, that is the launcher telling
you it will not hand work to something that is not there.

Then give it something real and open:

```
/home I've got a doctor's appointment Thursday and I don't know what to bring
```

`home` names exactly one skill, restates your intent in one line so you can see
what is being handed over, and invokes it. It never does the work itself, and
where two skills could each own the request it asks exactly one question rather
than picking silently.

## Minute 10 — the first real skill

```
/owner-context-onboarding
```

This is the one to run first. It establishes the working relationship: how to
address you, what is off limits, what may be remembered, what may never be
written down. It writes the `profile` namespace in your vault and an `activity/`
record of having done so, and it is deliberately narrow — it records what you
stated, in the turn you stated it, and derives nothing.

Expect a matrix in that same turn, not a promise of one: every topic agreed,
the state each is in, the exact text of any record about to be stored shown
before it is stored, and a single next question. A run state of `IN_PROGRESS`
means topics are still open — stopping halfway is a pause, not a failure.

Then try `/briefing` ("what's happening today") and `/daily-task-manager`
("remind me to renew the insurance next Tuesday"). Both are installed by
`make start`, and both will disclose a reduced state on a fresh machine — which
is the next section.

## When a run says `DEGRADED`, `UNCONFIRMED`, or `unfilled`

These are the three things a first hour meets, and they mean different things.

**`unfilled placeholders`** — a value you have not given. One note names the
file and every key: `~/.config/spike-os/claude-code.local.yaml: 3 of 10
unfilled placeholders …`. An unfilled key stays a literal `${OWNER_TZ}` in the
ADAPTER.md your agent reads, which is how it stays visible. Fill it there and
re-run the installer, or re-run `make start` and answer the questions. The
installer exits nonzero while any key is still empty — the skills are installed,
the host is not configured — and `make start` says that once, in its own words,
rather than twice.

**`degraded: <term>`** — a binding this runtime is *known* to lack or half-have.
The skill still installs, because its own contract already states what it does
without it. On claude-code today, two are DEGRADED:

- `task provider` — no Todoist connector in the registry, so
  [contracts/sync.md](contracts/sync.md)'s `tasks/` row applies:
  `system_of_record` flips to the datastore and `daily-task-manager` discloses
  that the task is mirror-only.
- `mail provider` — no agentmail server, so the agent half is absent; the
  owner's Gmail is connected, and a mail read is disclosed as a partial source
  rather than a missing one.

`make start` also probes these **live** rather than trusting the note, and where
your machine disagrees with the adapter — a Todoist server registered under a
`DEGRADED` note — it prints both readings and names the file to correct.

**`refused: … UNCONFIRMED`** — nobody can attest the binding on this host, so a
skill depending on it is not installed at all. Ignorance, not absence: the
adapter cannot honestly promise a capability, so the install stops rather than
putting a skill on your machine that will claim one. As of this commit **no
skill is refused on either runtime**. The last instance was `daily-task-manager`
and `briefing` on OpenClaw, and it was resolved by checking the live deployment
rather than the git seed — §4.1 of
[docs/openclaw-handoff.md](docs/openclaw-handoff.md) is the record, and the
authority on what OpenClaw binds today.

## Minute 30 — checking what you have

```sh
python3 tools/install_skill.py --runtime claude-code --list     # name, version, commit, stamp time
python3 tools/install_skill.py --runtime claude-code --check    # installed vs. this tree
python3 tools/install_skill.py --runtime claude-code --update   # bring them up to this tree
```

`--check` reports **drift**: a body edited in place, a supporting file that no
longer matches the digest the stamp recorded, a file no install wrote, a stamp
older than the adapter, a declaration that no longer matches this repository. It
is not a health check — it says nothing about whether a skill works.

`--update` is what resolves the *rest* of the drift when you have edited
something and want to keep it. It rewrites only the files you have not touched
and this repository has changed, prints what changed in each from `git log`, and
names — never overwrites — anything of yours, with the diff and the `--overwrite`
line that would take the repository's version instead. It exits nonzero on such a
refusal and carries on to the next skill, and it deletes nothing.

So the drift on your own files stays: an edited file is drift until you take the
repository's version or re-install, and a file you added is drift for as long as
you keep it — no `--update` removes it. Re-installing is the other option, and it
replaces the whole directory, so copy anything of yours out of it first.

## The four onboarding skills

Four skills bring an agent up, and each one is chosen by the moment that
prompted the request: a new working relationship to establish
(`owner-context-onboarding`), a service to connect or prove
(`mcp-connector-onboarding`), a restart, redeploy, migration, or maintainer
change to recover from (`runtime-handoff-onboarding`), or an external identity
to bring into existence (`social-agent-onboarding`).

Their own `description` and `## When not to use` sections are the routing table
— each names its three siblings with the condition that sends work there. Read
those rather than a copy here, which would be a fifth place for the routing to
drift out of step. Everything else these skills once restated in common — secret
handling, partial-success reporting, what may be shared — lives in
[contracts/skill-contract.md](contracts/skill-contract.md) and
[contracts/datastore.md](contracts/datastore.md).

Only `owner-context-onboarding` is installed by `make start`. Add another by
name when its moment arrives:

```sh
python3 tools/install_skill.py --runtime claude-code mcp-connector-onboarding
```

## After the first hour

- `/home` with no request, whenever you want to see what is installed.
- [README.md](README.md#words-this-repository-uses) for the vocabulary — runtime,
  adapter, vocabulary term, rule ID, capability, `activity/`, stamp.
- Standing permission — "stop asking me every time" — is `skills/autonomy`, with
  its own contract under the `autonomy/` namespace. Install it when you want it;
  nothing above needs it.
