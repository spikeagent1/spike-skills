"""`run_evals.py doctor`: prove that a headless eval run sees only the repo's
skills, then record the isolation recipe every later run must use.

Probes, in order: CLI/auth reachability, isolation strategy selection against a
sentinel skill in a throwaway project, MCP leakage, and which result field
carries `--json-schema` output. Results land in `evals/workspaces/doctor.json`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import HARNESS_VERSION, workspace
from .claude_cli import (
    ISOLATION_STRATEGIES,
    STATUS_BUDGET_EXCEEDED,
    STATUS_OK,
    ClaudeRequest,
    ClaudeResult,
    SubprocessClaudeRunner,
    extract_result_object,
    format_argv,
    scrub_env,
    strategy_env,
    strategy_flags,
)

SENTINEL_PROMPT = "List every skill name available to you, one per line; do not invoke any skill."
SENTINEL_INTENT = "Run the eval sentinel probe so I can confirm harness isolation."
SENTINEL_DESCRIPTION = (
    "Sentinel probe for eval-harness isolation checks. Use when asked to run the eval "
    "sentinel probe, verify harness isolation, or confirm which skills are visible."
)
AUTH_PROMPT = "Reply with OK"
STRUCTURED_PROMPT = 'Reply with the JSON object {"ok": true}'
STRUCTURED_SCHEMA = json.dumps(
    {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    separators=(",", ":"),
)

# Names that must never reach an eval run: they come from the operator's own
# `~/.claude` tree, not from this repository.
FOREIGN_MARKERS = ("superpowers", "gstack", "brainstorming", "google-")
STRUCTURED_OUTPUT_CANDIDATES = ("structured_output", "structuredOutput", "structured_result")
PROBE_OK_STATUSES = (STATUS_OK, STATUS_BUDGET_EXCEEDED)


@dataclass
class ProbeResult:
    """What one isolation strategy showed when asked to list its visible skills."""

    name: str
    available: bool = True
    status: str = STATUS_OK
    sentinel_seen: bool = False
    foreign_skills: List[str] = field(default_factory=list)
    mcp_tools: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "status": self.status,
            "sentinel_seen": self.sentinel_seen,
            "foreign_skills": list(self.foreign_skills),
            "mcp_tools": list(self.mcp_tools),
            "notes": list(self.notes),
        }


def choose_strategy(probe_results: Iterable[ProbeResult]) -> Optional[str]:
    """First strategy that ran, saw the sentinel, and leaked no foreign skill or MCP tool."""
    for probe in probe_results:
        if not probe.available or probe.status not in PROBE_OK_STATUSES:
            continue
        if probe.sentinel_seen and not probe.foreign_skills and not probe.mcp_tools:
            return probe.name
    return None


def classify_skills(
    names: Iterable[str],
    sentinel: str,
    user_skill_names: Set[str],
    builtin_names: Optional[Set[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Split visible skill names into (leaked from the operator's config, everything else).

    A name leaked when it carries a known marker, is plugin-scoped (`plugin:skill`),
    or matches a directory in the operator's own skill tree. `builtin_names` is the
    empirically derived set of names this CLI build ships with; it settles collisions
    such as `debug`, which exists both as a built-in and in the operator's tree.
    """
    baseline = builtin_names or set()
    foreign: List[str] = []
    other: List[str] = []
    for name in names:
        if name == sentinel:
            continue
        lowered = name.lower()
        if any(marker in lowered for marker in FOREIGN_MARKERS) or ":" in name:
            foreign.append(name)
        elif name in baseline:
            other.append(name)
        elif name in user_skill_names:
            foreign.append(name)
        else:
            other.append(name)
    return foreign, other


def sentinel_in_text(text: str, sentinel: str) -> bool:
    """True when the model's reply names the sentinel skill."""
    return sentinel in text


def foreign_markers_in_text(text: str) -> List[str]:
    """Foreign-config markers that appear in the model's reply."""
    lowered = text.lower()
    return [marker for marker in FOREIGN_MARKERS if marker in lowered]


def structured_output_field(result_obj: Mapping[str, Any]) -> Optional[str]:
    """Name of the result field carrying a `--json-schema` object, if any."""
    for candidate in STRUCTURED_OUTPUT_CANDIDATES:
        if isinstance(result_obj.get(candidate), dict):
            return candidate
    raw = result_obj.get("result")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(parsed, dict):
            return "result"
    return None


def user_skill_names(home: Path) -> Set[str]:
    """Top-level skill directory names in the operator's own Claude config tree.

    Only depth-1 directories under `~/.claude/skills/` can be loaded unprefixed;
    plugin skills arrive as `plugin:skill` and are caught by the prefix rule.
    """
    root = home / ".claude" / "skills"
    if not root.is_dir():
        return set()
    return {child.name for child in root.iterdir() if (child / "SKILL.md").is_file()}


def init_event(events: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The `system/init` event, which lists the skills and MCP servers actually loaded."""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event
    return None


def mcp_tools_seen(
    events: Sequence[Mapping[str, Any]], tool_uses: Sequence[Mapping[str, Any]]
) -> List[str]:
    """MCP server or tool names visible to the run."""
    seen: List[str] = []
    init = init_event(events)
    if init:
        for server in init.get("mcp_servers") or []:
            label = server.get("name") if isinstance(server, dict) else str(server)
            if label:
                seen.append(f"mcp_server:{label}")
        for tool in init.get("tools") or []:
            if isinstance(tool, str) and tool.startswith("mcp__"):
                seen.append(tool)
    for use in tool_uses:
        name = str(use.get("name") or "")
        if name.startswith("mcp__"):
            seen.append(name)
    return sorted(set(seen))


def write_sentinel_project(root: Path, sentinel: str) -> Path:
    """Create a throwaway project whose only skill is the sentinel."""
    skill_dir = root / ".claude" / "skills" / sentinel
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {sentinel}\n"
        f"description: {SENTINEL_DESCRIPTION}\n"
        "---\n\n"
        "# Eval sentinel\n\n"
        "Reply with the single word SENTINEL-OK and stop.\n",
        encoding="utf-8",
    )
    return root


def base_argv(
    runner: SubprocessClaudeRunner, prompt: str, model: str, tools: str, budget: float
) -> List[str]:
    """Flags shared by every doctor probe."""
    return runner.argv(
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--tools",
        tools,
        "--strict-mcp-config",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        str(budget),
    )


def save_stream(path: Path, result: ClaudeResult) -> None:
    """Persist a probe's raw events and stderr for fixture capture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in result.events:
            handle.write(json.dumps(event) + "\n")
    if result.stderr_tail:
        path.with_suffix(".stderr.txt").write_text(result.stderr_tail, encoding="utf-8")


def probe_environ(
    environ: Mapping[str, str], dotenv: Optional[Mapping[str, str]] = None
) -> Dict[str, str]:
    """Process environment plus a `.env` OAuth token, used when HOME is relocated.

    Only the OAuth token is taken from `.env`; nothing else in that file is
    injected into a probe.
    """
    env = dict(environ)
    source = workspace.dotenv_values() if dotenv is None else dotenv
    token = source.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token and not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def run_doctor(args: Any) -> int:
    """Run every probe, write `doctor.json`, and print the summary. Returns the exit code."""
    ws = workspace.ensure_dirs()
    probes_dir = workspace.PROBES
    runner = SubprocessClaudeRunner(args.claude_bin)
    environ = probe_environ(os.environ)
    notes: List[str] = []
    costs: List[float] = []

    cc_version = workspace.claude_version(args.claude_bin)
    if cc_version == "unknown":
        print(f"doctor: cannot run `{args.claude_bin} --version`; is Claude Code installed?")
        return 1

    home = Path.home()
    known_user_skills = user_skill_names(home)
    notes.append(f"operator skill tree under {home}/.claude has {len(known_user_skills)} skills")

    with tempfile.TemporaryDirectory(prefix="eval-doctor-") as tmp:
        tmp_root = Path(tmp)

        auth_dir = tmp_root / "auth"
        auth_dir.mkdir()
        # Probed under the least-privileged strategy: OAuth lives in the CLI's own
        # credential store, not in user settings, so dropping user settings must not
        # break auth. If it does, that is itself the finding.
        auth_result = runner.run(
            ClaudeRequest(
                argv=base_argv(runner, AUTH_PROMPT, args.model, "", args.max_budget_usd)
                + strategy_flags("project-sources", ws),
                cwd=auth_dir,
                env=scrub_env(environ),
                timeout_s=args.timeout,
            )
        )
        save_stream(probes_dir / "auth.jsonl", auth_result)
        costs.append(auth_result.cost_usd)
        auth_ok = auth_result.status in PROBE_OK_STATUSES and bool(auth_result.text.strip())
        if not auth_ok:
            notes.append(
                f"auth probe status={auth_result.status} stderr={auth_result.stderr_tail[:200]!r}"
            )

        # Ground truth for "what does this CLI build ship with": HOME points at an
        # empty workspace home and the project has no skills, so every name the
        # init event lists is a built-in, not a leak. Auth fails here by design,
        # which costs nothing and still yields the init event.
        baseline_dir = tmp_root / "builtin-baseline"
        baseline_dir.mkdir()
        baseline_result = runner.run(
            ClaudeRequest(
                argv=base_argv(runner, SENTINEL_PROMPT, args.model, "Skill", args.max_budget_usd)
                + strategy_flags("fresh-home", ws),
                cwd=baseline_dir,
                env=strategy_env("fresh-home", ws, environ),
                timeout_s=args.timeout,
            )
        )
        save_stream(probes_dir / "builtin-baseline.jsonl", baseline_result)
        costs.append(baseline_result.cost_usd)
        baseline_init = init_event(baseline_result.events)
        builtin_names = set(baseline_init.get("skills") or []) if baseline_init else set()
        notes.append(
            f"CLI built-in skill baseline: {len(builtin_names)} names"
            + ("" if builtin_names else " (probe produced no init event)")
        )

        requested = getattr(args, "strategy", "auto") or "auto"
        wanted = (
            [strategy.name for strategy in ISOLATION_STRATEGIES]
            if requested == "auto"
            else [requested]
        )
        probes: List[ProbeResult] = []
        for strategy in ISOLATION_STRATEGIES:
            if strategy.name not in wanted:
                continue
            probe = ProbeResult(name=strategy.name)
            missing = [key for key in strategy.requires_env if not environ.get(key)]
            if missing:
                probe.available = False
                probe.notes.append(f"skipped: {', '.join(missing)} not set")
                probes.append(probe)
                continue
            if strategy.forced_mode_only:
                probe.notes.append("forced load mode only: disables project skills too")

            sentinel = f"zz-eval-sentinel-{uuid.uuid4().hex[:8]}"
            proj = write_sentinel_project(tmp_root / strategy.name, sentinel)
            argv = base_argv(
                runner, SENTINEL_PROMPT, args.model, "Skill", args.max_budget_usd
            ) + strategy_flags(strategy.name, ws)
            env = strategy_env(strategy.name, ws, environ)
            result = runner.run(
                ClaudeRequest(argv=argv, cwd=proj, env=env, timeout_s=args.timeout)
            )
            save_stream(probes_dir / f"isolation-{strategy.name}.jsonl", result)
            costs.append(result.cost_usd)

            init = init_event(result.events)
            loaded_skills = list(init.get("skills") or []) if init else []
            foreign, builtin = classify_skills(
                loaded_skills, sentinel, known_user_skills, builtin_names
            )
            for marker in foreign_markers_in_text(result.text):
                foreign.append(f"reply-text:{marker}")
            probe.status = result.status
            probe.sentinel_seen = bool(init and sentinel in loaded_skills) or sentinel_in_text(
                result.text, sentinel
            )
            probe.foreign_skills = sorted(set(foreign))
            probe.mcp_tools = mcp_tools_seen(result.events, result.tool_uses)
            probe.notes.append(
                f"loaded skills: {len(loaded_skills)} ({len(builtin)} CLI built-ins)"
            )
            if init is None:
                probe.notes.append("no init event: probe did not start")
            probes.append(probe)

        strategy_name = choose_strategy(probes)

        structured_field: Optional[str] = None
        if strategy_name:
            struct_dir = tmp_root / "structured"
            struct_dir.mkdir(exist_ok=True)
            struct_argv = (
                runner.argv(
                    "-p",
                    STRUCTURED_PROMPT,
                    "--output-format",
                    "json",
                    "--model",
                    args.model,
                    "--tools",
                    "",
                    "--strict-mcp-config",
                    "--permission-mode",
                    "dontAsk",
                    "--no-session-persistence",
                    "--max-budget-usd",
                    str(args.max_budget_usd),
                    "--json-schema",
                    STRUCTURED_SCHEMA,
                )
                + strategy_flags(strategy_name, ws)
            )
            struct_result = runner.run(
                ClaudeRequest(
                    argv=struct_argv,
                    cwd=struct_dir,
                    env=strategy_env(strategy_name, ws, environ),
                    timeout_s=args.timeout,
                )
            )
            # Written as a single-line JSON array, the shape `--output-format json` emits.
            probes_dir.joinpath("structured-output.json").write_text(
                json.dumps(struct_result.events) + "\n", encoding="utf-8"
            )
            costs.append(struct_result.cost_usd)
            result_obj = extract_result_object(struct_result.events)
            if result_obj:
                structured_field = structured_output_field(result_obj)
            else:
                notes.append(f"structured-output probe status={struct_result.status}")

            skill_dir = tmp_root / "skill-invoke"
            sentinel = f"zz-eval-sentinel-{uuid.uuid4().hex[:8]}"
            write_sentinel_project(skill_dir, sentinel)
            invoke_result = runner.run(
                ClaudeRequest(
                    argv=base_argv(
                        runner, SENTINEL_INTENT, args.model, "Skill", args.max_budget_usd
                    )
                    + strategy_flags(strategy_name, ws),
                    cwd=skill_dir,
                    env=strategy_env(strategy_name, ws, environ),
                    timeout_s=args.timeout,
                ),
                early_stop_on_skill=True,
            )
            save_stream(probes_dir / "skill-invoke.jsonl", invoke_result)
            costs.append(invoke_result.cost_usd)
            notes.append(
                "skill-invoke probe tool_uses: "
                + (", ".join(use.get("name", "") for use in invoke_result.tool_uses) or "none")
            )

        error_dir = tmp_root / "error"
        error_dir.mkdir(exist_ok=True)
        error_result = runner.run(
            ClaudeRequest(
                argv=base_argv(runner, AUTH_PROMPT, "zzz-not-a-model", "", args.max_budget_usd)
                + strategy_flags(strategy_name or "project-sources", ws),
                cwd=error_dir,
                env=strategy_env(strategy_name or "project-sources", ws, environ),
                timeout_s=args.timeout,
            )
        )
        save_stream(probes_dir / "error.jsonl", error_result)
        notes.append(f"invalid-model probe status={error_result.status}")

    chosen_flags = strategy_flags(strategy_name, ws) if strategy_name else []
    argv_template = format_argv(
        base_argv(runner, "<PROMPT>", args.model, "Read,Glob,Grep", 0.5) + chosen_flags
    )
    chosen_probe = next((p for p in probes if p.name == strategy_name), None)

    doctor_json = {
        "harness_version": HARNESS_VERSION,
        "claude_code_version": cc_version,
        "python_version": sys.version.split()[0],
        "commit": workspace.git_commit_short(),
        "dirty": workspace.git_dirty(),
        "checked_at": workspace.utc_iso(),
        "auth_ok": auth_ok,
        "strategy": strategy_name,
        "strategy_flags": chosen_flags,
        "foreign_skills_seen": chosen_probe.foreign_skills if chosen_probe else [],
        "mcp_tools_seen": chosen_probe.mcp_tools if chosen_probe else [],
        "structured_output_field": structured_field,
        "builtin_skill_baseline": sorted(builtin_names),
        "argv_template": argv_template,
        "model": args.model,
        "cost_usd_total": round(sum(costs), 6),
        "probes": [probe.to_json() for probe in probes],
        "notes": notes,
    }
    doctor_path = ws / "doctor.json"
    doctor_path.write_text(json.dumps(doctor_json, indent=2) + "\n", encoding="utf-8")

    print(f"claude code : {cc_version}")
    print(f"harness     : {HARNESS_VERSION}  python {doctor_json['python_version']}")
    print(f"commit      : {doctor_json['commit']}{' (dirty)' if doctor_json['dirty'] else ''}")
    print(f"auth        : {'ok' if auth_ok else 'FAILED'}")
    for probe in probes:
        verdict = "PASS" if probe.name == strategy_name else "fail"
        if not probe.available:
            verdict = "skip"
        print(
            f"  {verdict:4}  {probe.name:15} status={probe.status:15} "
            f"sentinel={'yes' if probe.sentinel_seen else 'no':3} "
            f"foreign={len(probe.foreign_skills)} mcp={len(probe.mcp_tools)}"
        )
        for note in probe.notes:
            print(f"          - {note}")
        if probe.foreign_skills:
            print(f"          - leaked: {', '.join(probe.foreign_skills[:10])}")
    print(f"strategy    : {strategy_name or 'NONE'}")
    print(f"structured  : {structured_field or 'unknown'}")
    print(f"cost (usd)  : {doctor_json['cost_usd_total']}")
    print(f"wrote       : {doctor_path}")
    print("argv template:")
    print(f"  {argv_template}")
    for note in notes:
        print(f"note        : {note}")

    if strategy_name is None:
        print("doctor: no isolation strategy passed; `run` will refuse to execute.")
        return 1
    return 0
