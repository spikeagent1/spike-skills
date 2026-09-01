#!/usr/bin/env python3
"""Clone to a working `/home`: probe this host, fill the local values, install, verify.

`tools/install_skill.py` renders and installs; it assumes you already know
which skills you want and what the ten `${PLACEHOLDER}`s in the adapter mean.
This is the other half -- the one run a newcomer makes -- and it orchestrates
that installer rather than reimplementing it.

Five steps, in order:

1. **The host.** Live probes, not remembered facts: the interpreter, the agent
   CLI, and every provider the adapter names, checked against the connector
   registry this machine actually has. A probe that finds something absent
   names the fix for that probe and the run continues; the adapter's own note
   is a fact about the host it was written on, so where a probe disagrees with
   it, both readings are printed.
2. **Your local values.** The placeholders, asked one at a time with a gloss
   and an example, written to the local overrides file the adapter names --
   outside the repository, never committed. A run that ends with one still
   empty has configured nothing, says which keys, and exits nonzero.
3. **Install.** `home` plus a small starter set, through the installer.
4. **Verify.** One real invocation -- `claude -p "/home"` -- because an install
   that renders cleanly and answers nothing is not a working library. The run
   needs the CLI and a logged-in session; where either is missing, the manual
   step is printed rather than skipped in silence. `--no-smoke` says so too.
5. **Done.** What to type.

Usage:
  python3 tools/bootstrap.py [options]
    --runtime {claude-code,openclaw}   default claude-code
    --dest DIR                         override the runtime's default destination
    --local-overrides PATH             override the adapter's local_overrides_file
    --no-smoke                         do not spend the one paid invocation
"""

from __future__ import annotations

import sys
from pathlib import Path

# Runnable as `python3 tools/bootstrap.py` and importable as `tools.bootstrap`.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The floor, before the first import of ours: an interpreter below it reads the
# version it needs rather than whatever construct happens to fail first.
from tools.python_floor import MINIMUM_PYTHON, require_python  # noqa: E402

_TOO_OLD = require_python()
if _TOO_OLD:
    raise SystemExit(_TOO_OLD)

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Any, Callable, Sequence, TextIO  # noqa: E402

from tools.installer import cli, io, render  # noqa: E402

OK = "ok"
ABSENT = "absent"
DEGRADED = "degraded"
FAILED = "failed"
SKIPPED = "skipped"
# Only a verification that ran and came back wrong ends the run; everything else
# a probe finds is reported with its fix, and the safe steps carry on.
FATAL_STATUSES = frozenset({FAILED})

EXIT_OK = 0
EXIT_UNCONFIGURED = 1

# `home` is the entry point; the other three are the first things worth asking
# it for, and two of them are the ones that print a `degraded:` note on
# claude-code -- so a newcomer meets that word in a run rather than in a doc.
STARTER_SKILLS = ("home", "owner-context-onboarding", "briefing", "daily-task-manager")

SMOKE_PROMPT = "/home"
SMOKE_COMMAND = ("claude", "-p", SMOKE_PROMPT)
SMOKE_TIMEOUT = 180
PROBE_TIMEOUT = 30

# The CLI each runtime is driven by, and whether this host can reach it at all.
AGENT_CLI = {"claude-code": "claude", "openclaw": "openclaw"}
AGENT_LABEL = {"claude-code": "Claude Code", "openclaw": "OpenClaw"}

REGISTRY_LINE_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")
PROVIDER_SUFFIX = "_provider"

# One line of what the value is, and one example of the shape it takes. The
# generated overrides file lists the keys; this is the only place that says
# what they mean, which is what a first install had no way to find out.
GLOSSES: dict[str, tuple[str, str]] = {
    "OWNER_NAME": (
        "the owner's name, as the agent should address them and record them",
        "Ada Lovelace",
    ),
    "OWNER_TZ": (
        "the IANA timezone the owner's day runs in; quiet hours are read in it",
        "America/Los_Angeles",
    ),
    "VAULT_ROOT": (
        "absolute path to the durable-memory vault -- the datastore every "
        "namespace is relative to",
        "~/Tapan-Brain",
    ),
    "CONVERSATIONS_ROOT": (
        "where raw conversation transcripts live; a separate root from the "
        "vault, and never inside it",
        "~/conversations",
    ),
    "AGENT_BIN": (
        "a directory of the agent's own binaries, added to the durable tool "
        "paths; 'none' if there is none",
        "~/dev/agent/bin",
    ),
    "AGENT_INBOX": (
        "the mailbox the agent itself reads, for notifications no session is "
        "open for; 'none' if there is none",
        "agent@example.com",
    ),
    "PUBLIC_SURFACES": (
        "the public places this agent may post to; 'none' blocks every skill "
        "declaring publish:external",
        "none",
    ),
    "QUIET_START": (
        "when quiet hours begin in the owner timezone -- delivery is held, "
        "execution is not",
        "22:00",
    ),
    "QUIET_END": ("when quiet hours end in the owner timezone", "07:30"),
    "REPO_IDENTITY": (
        "the forge account the agent commits, files issues, and opens pull "
        "requests as",
        "chughtapan",
    ),
    "DEPLOY_REPO": (
        "the repository holding the runtime's deploy tree, where the identity "
        "file lives",
        "chughtapan/openclaw-deploy",
    ),
    "OWNER_CHAT_ID": (
        "the owner's id on the runtime's messaging channel, so a notification "
        "reaches a person",
        "12345678",
    ),
}


@dataclass(frozen=True)
class Step:
    """One probe, install, or verification, and what to do when it is not `ok`."""

    name: str
    status: str
    detail: str
    fix: str = ""


# -- host access, in one place so a test can stand in for the machine ---------


def which(name: str) -> str | None:
    return shutil.which(name)


def run_command(command: Sequence[str], timeout: int = PROBE_TIMEOUT) -> Any:
    """Run a command and capture it; a failure to start is a returncode, not a raise."""
    try:
        return subprocess.run(
            list(command), capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))


def adapter(runtime: str) -> dict[str, Any]:
    return render.adapter_for(runtime, render.load_contract("adapters"))


# -- probes ------------------------------------------------------------------


def probe_python() -> Step:
    """The interpreter running this file, against the floor it already cleared."""
    found = "%d.%d.%d" % sys.version_info[:3]
    floor = "%d.%d" % MINIMUM_PYTHON
    return Step("python", OK, f"{found} at {sys.executable} (floor {floor})")


def probe_agent_cli(runtime: str) -> Step:
    """The runtime's CLI: the one thing the verification step cannot do without."""
    name = AGENT_CLI.get(runtime, "claude")
    path = which(name)
    if path is None:
        return Step(
            f"{name} CLI",
            ABSENT,
            "not on PATH",
            f"install it (https://claude.com/claude-code for {name}); every step "
            f"here runs without it except the `{name} -p \"{SMOKE_PROMPT}\"` "
            "verification, which is then yours to run",
        )
    result = run_command([name, "--version"])
    if result.returncode != 0:
        return Step(
            f"{name} CLI",
            DEGRADED,
            f"{path} exited {result.returncode} on --version",
            f"run `{name} --version` yourself and fix what it reports; the "
            "verification step needs a CLI that answers",
        )
    return Step(f"{name} CLI", OK, f"{result.stdout.strip() or 'present'} at {path}")


def probe_vault(root: str) -> Step:
    """The datastore root the adapter's namespaces are relative to."""
    if not str(root).strip():
        return Step(
            "vault",
            ABSENT,
            "no root configured",
            "VAULT_ROOT has no value; answer it above, or fill it in the "
            "overrides file and re-run",
        )
    path = Path(str(root)).expanduser()
    if path.is_dir():
        return Step("vault", OK, f"{path} exists")
    return Step(
        "vault",
        ABSENT,
        f"{path} is not a directory",
        f"mkdir -p {path} -- the skills create their own namespaces under it on "
        "first write, but the root itself has to be there",
    )


def registry_servers(runtime: str, home: Path | None = None) -> tuple[tuple[str, ...], str]:
    """Every connector this host actually registers, and where that was read.

    Two halves, because neither is the whole registry: what the CLI lists, and
    the `mcpServers` blocks of its config. A host whose CLI is absent has no
    registry to read, and the caller is told that rather than told "none".
    """
    name = AGENT_CLI.get(runtime, "claude")
    if which(name) is None:
        return (), f"not read: {name} is not on PATH"
    servers: list[str] = []
    sources: list[str] = []
    result = run_command([name, "mcp", "list"])
    if result.returncode == 0:
        sources.append(f"{name} mcp list")
        for line in (result.stdout or "").splitlines():
            match = REGISTRY_LINE_RE.match(line.strip())
            if match is not None:
                servers.append(match.group(1))
    config = (home if home is not None else Path.home()) / f".{name}.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        blocks = [data.get("mcpServers")]
        projects = data.get("projects")
        if isinstance(projects, dict):
            blocks.extend(
                project.get("mcpServers") for project in projects.values()
                if isinstance(project, dict)
            )
        found = False
        for block in blocks:
            if isinstance(block, dict):
                servers.extend(str(key) for key in block)
                found = True
        if found:
            sources.append(str(config))
    ordered = tuple(dict.fromkeys(servers))
    return ordered, " and ".join(sources) if sources else f"nothing readable for {name}"


def adapter_state(note: str) -> str:
    """What the adapter claims about a binding: UNCONFIRMED, DEGRADED, or bound."""
    text = str(note or "").strip().upper()
    for marker in ("UNCONFIRMED", "DEGRADED"):
        if text.startswith(marker):
            return marker
    return "bound"


def matching_servers(value: str, servers: Sequence[str]) -> list[str]:
    """Registered connectors whose name appears in the binding's own text."""
    text = str(value or "").lower()
    matches = []
    for server in servers:
        needle = str(server).lower().replace("-", " ").replace("_", " ")
        if needle and needle in text:
            matches.append(str(server))
    return matches


def probe_provider(
    term: str,
    value: str,
    note: str,
    servers: Sequence[str],
    source: str,
    runtime: str,
) -> Step:
    """One provider binding, as the adapter states it and as this host answers.

    The adapter's note is a fact recorded on one machine at one time. Where the
    live registry disagrees with it -- a connector registered under a DEGRADED
    note, or nothing registered under a plain binding -- both readings are
    printed and the file to correct is named. Nothing here rewrites the adapter.
    """
    state = adapter_state(note)
    live = matching_servers(value, servers)
    yaml = f"adapters/{runtime}/adapter.yaml"
    if live:
        detail = f"{', '.join(live)} registered here; adapter says {state}"
        if state in ("DEGRADED", "UNCONFIRMED"):
            return Step(
                term,
                OK,
                detail,
                f"the note in {yaml} still calls this {state}, written on another "
                f"host; {', '.join(live)} is registered on this one, so correct the "
                "note if these skills run here",
            )
        return Step(term, OK, detail)
    if str(value or "").strip().lower().startswith("none"):
        return Step(term, ABSENT, f"the adapter binds it to \"{value}\"")
    if state in ("DEGRADED", "UNCONFIRMED"):
        return Step(
            term,
            DEGRADED,
            f"nothing in {source} matches this binding; adapter says {state}",
            "a skill naming it discloses the fallback its own contract states; "
            "register a connector for it to change that",
        )
    return Step(
        term,
        ABSENT,
        f"nothing in {source} matches this binding, which carries no note",
        f"{yaml} binds this term as available; register the connector, or add a "
        "DEGRADED note there, so no skill claims a provider this host lacks",
    )


def probe_providers(
    adapter_data: dict[str, Any], servers: Sequence[str], source: str, runtime: str
) -> list[Step]:
    vocabulary = adapter_data.get("vocabulary") or {}
    steps = []
    for key in sorted(vocabulary):
        if not key.endswith(PROVIDER_SUFFIX):
            continue
        binding = vocabulary[key] or {}
        steps.append(
            probe_provider(
                key.replace("_", " "),
                str(binding.get("value") or ""),
                str(binding.get("note") or ""),
                servers,
                source,
                runtime,
            )
        )
    return steps


# -- the local values --------------------------------------------------------


def ask_order(names: Sequence[str]) -> list[str]:
    """The keys in the order a person can answer them, not in the order they sort.

    Who the owner is, where their day runs, and where the vault lives are the
    three that decide most of the rendered adapter; alphabetical order opened
    with `AGENT_BIN`, which almost nobody has.
    """
    ranked = {name: index for index, name in enumerate(GLOSSES)}
    return sorted(names, key=lambda name: (ranked.get(name, len(ranked)), name))


def ask_placeholders(
    names: Sequence[str],
    existing: dict[str, str],
    ask: Callable[[str], str],
    out: TextIO,
) -> dict[str, str]:
    """One question per placeholder, each with a gloss and an example.

    An empty answer keeps whatever the file already had, so a re-run is a
    review rather than a re-typing. End of input ends the questions: a run fed
    fewer answers than there are keys leaves the rest as they were, and the
    completeness check downstream is what reports it.
    """
    values = dict(existing)
    for name in ask_order(names):
        gloss, example = GLOSSES.get(
            name, (f"no gloss recorded; see adapters/*/adapter.yaml for {name}", "")
        )
        current = values.get(name, "")
        out.write(f"\n  {name} -- {gloss}\n")
        out.write(f"    example: {example}\n" if example else "")
        prompt = f"    {name} [{current}]: " if current else f"    {name}: "
        try:
            answer = ask(prompt)
        except EOFError:
            out.write("    (end of input; the remaining keys keep the values they had)\n")
            break
        answer = str(answer).strip()
        if answer:
            values[name] = answer
    return values


def unfilled(names: Sequence[str], values: dict[str, str]) -> list[str]:
    """Every placeholder with no value -- the ones left literal in the render."""
    return [name for name in names if not str(values.get(name, "")).strip()]


def quoted(value: str) -> str:
    """A scalar the contract YAML subset reads back as it was written."""
    text = " ".join(str(value).split())
    if "'" not in text:
        return f"'{text}'"
    return '"' + text.replace('"', "'") + '"'


def overrides_text(runtime: str, names: Sequence[str], values: dict[str, str]) -> str:
    keys = list(names) + [key for key in sorted(values) if key not in names]
    lines = [
        f"# Personal values for the {render.OS_NAME} {runtime} adapter.",
        "# Written by tools/bootstrap.py. These are yours: they live outside the",
        "# repository, they are never committed, and the installer reads them to fill",
        "# the ${NAME} placeholders in the rendered ADAPTER.md. An empty value stays a",
        "# literal ${NAME} there, which is how you can see what is still missing.",
        "",
    ]
    lines.extend(f"{key}: {quoted(values.get(key, ''))}" for key in keys)
    return "\n".join(lines) + "\n"


def write_overrides(
    path: Path, runtime: str, names: Sequence[str], values: dict[str, str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(overrides_text(runtime, names, values), encoding="utf-8")


# -- verification ------------------------------------------------------------


def verify(runtime: str, enabled: bool) -> Step:
    """The one real invocation: `claude -p "/home"`, or why it did not happen.

    Never a silent skip. A run without the CLI, without a logged-in session, or
    with `--no-smoke` prints the command to run by hand; only a run that
    actually answered wrong is a failure.
    """
    name = AGENT_CLI.get(runtime, "claude")
    manual = f'run `{name} -p "{SMOKE_PROMPT}"` yourself once; it needs an authenticated session'
    if runtime != "claude-code":
        return Step("smoke", SKIPPED, f"no defined invocation for {runtime} from this host", manual)
    if not enabled:
        return Step("smoke", SKIPPED, "--no-smoke was passed, so nothing was invoked", manual)
    if which(name) is None:
        return Step("smoke", SKIPPED, f"{name} is not on PATH, so nothing was invoked", manual)
    result = run_command(list(SMOKE_COMMAND), timeout=SMOKE_TIMEOUT)
    if result.returncode != 0:
        first = (result.stderr or result.stdout or "").strip().splitlines()
        return Step(
            "smoke",
            FAILED,
            f"`{' '.join(SMOKE_COMMAND)}` exited {result.returncode}: "
            f"{first[0] if first else 'no output'}",
            f"authenticate with `{name}` and run it again; an install that renders "
            "cleanly and answers nothing is not a working library",
        )
    answer = " ".join((result.stdout or "").split())
    return Step("smoke", OK, f"`{' '.join(SMOKE_COMMAND)}` answered: {answer[:160]}")


# -- the run -----------------------------------------------------------------


def report(step: Step, out: TextIO) -> None:
    out.write(f"  {step.status:<9}{step.name}: {step.detail}\n")
    if step.fix:
        out.write(f"           fix: {step.fix}\n")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description=__doc__ or "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--runtime", default="claude-code", choices=list(render.RUNTIMES))
    parser.add_argument("--dest", help="override the runtime's default destination")
    parser.add_argument("--local-overrides", help="override the adapter's local_overrides_file")
    parser.add_argument(
        "--no-smoke", action="store_true", help="do not spend the one paid invocation"
    )
    return parser.parse_args(list(argv))


def main(
    argv: Sequence[str] | None = None,
    ask: Callable[[str], str] | None = None,
    out: TextIO | None = None,
    installer: Callable[[list[str]], int] | None = None,
) -> int:
    args = parse_args(argv or [])
    ask = ask or input
    out = out or sys.stdout
    installer = installer or cli.main
    runtime = args.runtime
    adapter_data = adapter(runtime)
    overrides = io.local_overrides_path(adapter_data, args.local_overrides)
    names = io.placeholder_names(runtime)
    problems: list[Step] = []

    out.write(f"spike-os bootstrap -- {_REPO_ROOT}\n")
    out.write(f"  runtime {runtime}; local values in {overrides}\n")

    out.write("\n1/5  This host, probed now (not remembered)\n")
    servers, source = registry_servers(runtime)
    host_steps = [probe_python(), probe_agent_cli(runtime)]
    out.write(f"  {'read':<9}connector registry: {source}\n")
    out.write(f"           {', '.join(servers) if servers else 'no connectors registered'}\n")
    host_steps.extend(probe_providers(adapter_data, servers, source, runtime))
    for step in host_steps:
        report(step, out)

    out.write(f"\n2/5  Your {len(names)} local values\n")
    out.write(
        "  These are yours, not the repository's: they fill the ${NAME} placeholders\n"
        "  in the ADAPTER.md every installed skill reads, and they are written\n"
        "  outside the repository, to\n"
        f"    {overrides}\n"
        "  Press Enter to keep a value; answer 'none' where there is nothing to name.\n"
    )
    values = ask_placeholders(names, io.read_local_overrides(overrides), ask, out)
    write_overrides(overrides, runtime, names, values)
    out.write(f"\n  wrote {overrides}\n")
    report(probe_vault(values.get("VAULT_ROOT", "")), out)
    missing = unfilled(names, values)
    if missing:
        problems.append(
            Step(
                "local values",
                FAILED,
                f"{len(missing)} of {len(names)} still empty: {', '.join(missing)}",
                f"fill them in {overrides} and re-run this, or run it again and answer them",
            )
        )
        report(problems[-1], out)

    out.write(f"\n3/5  Installing {', '.join(STARTER_SKILLS)}\n")
    install_argv = ["--runtime", runtime]
    if args.dest:
        install_argv += ["--dest", str(args.dest)]
    if args.local_overrides:
        install_argv += ["--local-overrides", str(args.local_overrides)]
    install_argv += list(STARTER_SKILLS)
    out.write(f"  python3 tools/install_skill.py {' '.join(install_argv)}\n\n")
    code = installer(install_argv)
    if code != 0:
        problems.append(
            Step(
                "install",
                FAILED,
                f"tools/install_skill.py exited {code}",
                "read the refusals above; each one names the skill and the reason",
            )
        )

    out.write("\n4/5  Verifying with one real invocation\n")
    smoke = verify(runtime, not args.no_smoke)
    report(smoke, out)
    if smoke.status in FATAL_STATUSES:
        problems.append(smoke)

    out.write("\n5/5  Done\n")
    if problems:
        out.write("  Not finished -- these are still open:\n")
        for step in problems:
            report(step, out)
        out.write("  Fix them and run this again; it is safe to re-run.\n")
        return EXIT_UNCONFIGURED
    label = AGENT_LABEL.get(runtime, runtime)
    out.write(
        f"  type {SMOKE_PROMPT} in {label}. It reads catalog/index.md, names one\n"
        "  skill, and hands the request over; with no request at all it prints the\n"
        "  index itself, which is the fastest way to see what is installed.\n"
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
