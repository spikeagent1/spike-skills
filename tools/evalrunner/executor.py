"""Behavioral executor: turn a case plus a config into a headless `claude` call
and persist the run in the skill-creator workspace layout.

The three configs differ only in what the model is told about the skill:
`with_skill` appends the current SKILL.md body, `old_skill@<ref>` appends the
body committed at that git ref, and `without_skill` appends nothing. Everything
else about the invocation is identical so a paired comparison isolates the skill.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import CONFIG_WITH_SKILL, CONFIG_WITHOUT_SKILL
from .cases import BehavioralCase
from .claude_cli import ClaudeRequest, ClaudeResult, ClaudeRunner, scrub_env, strategy_env
from .doctor import probe_environ
from . import workspace

ROOT = workspace.ROOT
PROMPTS = Path(__file__).resolve().parent / "prompts"

OLD_SKILL_PREFIX = "old_skill@"
DEFAULT_CONFIGS = (CONFIG_WITH_SKILL, CONFIG_WITHOUT_SKILL)

EXECUTOR_TOOLS = "Read,Glob,Grep"
# Scratch working directories live here, deliberately outside the repository.
SANDBOX_ENV_VAR = "SPIKE_EVAL_SANDBOX"
SANDBOX_DIRNAME = "spike-skills-evals"
SKILL_HEADER = (
    "The following skill is active for this task. Supporting files referenced below are "
    "readable under `{path}`.\n\n"
)
# The absolute paths of the granted repository directories, stated because the
# model runs from an empty sandbox: a relative link it cannot resolve reads as a
# missing file, and the branch that reads it never gets exercised.
REPO_INPUT_HEADER = (
    "Repository files this skill declares as inputs are readable under {paths}; a "
    "relative link in the body resolves from the skill directory named above.\n\n"
)
# The canonical template's Dependencies line is where a skill declares the
# repository files it reads; nothing outside that line grants anything.
DEPENDENCIES_LINE_RE = re.compile(r"^\s*\*\*Dependencies:\*\*.*$", re.MULTILINE)
MARKDOWN_LINK_TARGET_RE = re.compile(r"\]\(([^)\s]+)")


class ConfigError(ValueError):
    """A config name the executor cannot build a request for."""


def minimal_system_prompt() -> str:
    """Neutral executor system prompt used by `--system-prompt-mode minimal`."""
    return PROMPTS.joinpath("executor-minimal.md").read_text(encoding="utf-8").strip()


def strip_frontmatter(text: str) -> str:
    """SKILL.md body with a leading YAML frontmatter block removed.

    Only a block at the very start counts; a `---` rule later in the document is
    body content and is left alone.
    """
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---\n"):
        return stripped.strip()
    end = stripped.find("\n---", 4)
    if end == -1:
        return stripped.strip()
    rest = stripped[end + len("\n---") :]
    return rest.lstrip("\n").strip()


def config_dirname(config: str) -> str:
    """Directory name for a config; git refs may contain path separators."""
    return config.replace("/", "_")


def config_ref(config: str) -> Optional[str]:
    """Git ref carried by an `old_skill@<ref>` config, else None."""
    if config.startswith(OLD_SKILL_PREFIX):
        return config[len(OLD_SKILL_PREFIX) :]
    return None


def sandbox_cwd(run_dir: Path, args: Any = None, *, leaf: str = "proj") -> Path:
    """Empty working directory for one run, outside the repository.

    Claude Code loads the operator's `~/.claude/CLAUDE.md` whenever the working
    directory sits inside a project it already knows, and `--setting-sources
    project` does not suppress that. Running from a scratch directory outside the
    repo keeps the operator's personal memory out of the eval context; the skill's
    own files stay reachable through the explicit `--add-dir` grant. The scratch
    path mirrors the tail of the run directory so an artifact stays traceable to
    the process that produced it; `leaf` separates the executor's directory from
    the grader's for the same run.
    """
    configured = getattr(args, "sandbox_root", None) if args is not None else None
    root = Path(configured or os.environ.get(SANDBOX_ENV_VAR) or tempfile.gettempdir())
    if not configured:
        root = root / SANDBOX_DIRNAME
    run_dir = Path(run_dir)
    tail = Path(*run_dir.parts[-5:]) if len(run_dir.parts) >= 5 else Path(run_dir.name)
    cwd = root / tail / leaf
    cwd.mkdir(parents=True, exist_ok=True)
    return cwd


def repo_root(args: Any) -> Path:
    """Repository the skills are read from; tests point this at a fixture tree."""
    return Path(getattr(args, "repo_root", None) or ROOT)


def _skill_at_ref(root: Path, skill: str, ref: str) -> str:
    """SKILL.md as committed at `ref`."""
    rel = f"skills/{skill}/SKILL.md"
    try:
        completed = subprocess.run(
            ["git", "show", f"{ref}:{rel}"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ConfigError(f"cannot run git in {root}: {exc}") from exc
    if completed.returncode != 0:
        raise ConfigError(f"git show {ref}:{rel} failed: {completed.stderr.strip()}")
    return completed.stdout


def skill_body(config: str, skill: str, root: Path) -> Optional[str]:
    """Frontmatter-free SKILL.md body this config appends, or None for `without_skill`."""
    if config == CONFIG_WITHOUT_SKILL:
        return None
    if config == CONFIG_WITH_SKILL:
        path = root / "skills" / skill / "SKILL.md"
        try:
            return strip_frontmatter(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"cannot read {path}: {exc}") from exc
    ref = config_ref(config)
    if ref is None:
        raise ConfigError(
            f"unknown config {config!r}; expected {CONFIG_WITH_SKILL}, "
            f"{CONFIG_WITHOUT_SKILL}, or {OLD_SKILL_PREFIX}<git-ref>"
        )
    return strip_frontmatter(_skill_at_ref(root, skill, ref))


def repo_input_dirs(body: str, skill_dir: Path, root: Path) -> List[Path]:
    """Repository directories the Dependencies line links into, sorted and deduplicated.

    A skill that declares a repo file it reads -- `catalog/index.md` for the
    launcher, `contracts/datastore.md` for the datastore readers -- can only
    exercise that branch under eval when the directory is granted. The grant is
    derived from the declaration, so a link the skill did not declare reaches
    nothing, and neither does one that escapes the repository.
    """
    # normpath, not resolve: the grant has to spell the same path the skill's own
    # --add-dir does, and resolve() would rewrite a symlinked tmp root.
    skill_dir = Path(os.path.normpath(Path(skill_dir).absolute()))
    root = Path(os.path.normpath(Path(root).absolute()))
    granted: Dict[str, Path] = {}
    for line in DEPENDENCIES_LINE_RE.findall(body or ""):
        for target in MARKDOWN_LINK_TARGET_RE.findall(line):
            target = target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = Path(os.path.normpath(skill_dir / target))
            directory = resolved if target.endswith("/") else resolved.parent
            if not directory.is_dir():
                continue
            if directory == skill_dir or skill_dir in directory.parents:
                continue  # already reachable through the skill's own grant
            if directory != root and root not in directory.parents:
                continue  # outside the repository
            granted[str(directory)] = directory
    return [granted[key] for key in sorted(granted)]


def executor_env(args: Any) -> Dict[str, str]:
    """Environment for an executor call: nesting vars dropped, isolation applied."""
    environ = probe_environ(os.environ)
    strategy = getattr(args, "isolation_strategy", None)
    if not strategy:
        return scrub_env(environ)
    return strategy_env(strategy, workspace.WORKSPACE, environ)


def request_scaffold(body: Optional[str], skill: str, root: Path) -> Dict[str, Any]:
    """Cache-key material for the text `build_request` wraps around the skill body.

    The two header constants and the `--add-dir` grants named in them are text
    the model reads, so they are part of the question asked. They are derived
    from the SKILL.md, which the key already covers -- but the derivation is
    harness code, and editing a header constant or the grant rule changes the
    request without touching any skill. Recording them here means such an edit
    invalidates the entries it affects instead of replaying an answer given to
    different words.

    Directories are recorded relative to the repository root: the absolute
    prefix is a property of the checkout, not of the question. A leg with no
    skill body appends no header at all, and its scaffold is empty; a skill with
    no repo-input grant records no repo-input header, because `build_request`
    appends that header only when there is a grant to name in it.
    """
    empty = {"skill_header": "", "repo_input_header": "", "extra_dirs": []}
    if body is None:
        return empty
    root = Path(root)
    dirs = sorted(
        os.path.relpath(str(path), str(root))
        for path in repo_input_dirs(body, root / "skills" / skill, root)
    )
    return {
        "skill_header": SKILL_HEADER,
        "repo_input_header": REPO_INPUT_HEADER if dirs else "",
        "extra_dirs": dirs,
    }


def build_request(
    case: BehavioralCase,
    config: str,
    args: Any,
    isolation_flags: List[str],
    run_dir: Path,
) -> ClaudeRequest:
    """Full headless invocation for one (case, config) pair.

    `run_dir` is the `run-<k>/` directory that collects the artifacts; the model
    itself runs in an empty scratch directory outside the repository (see
    `sandbox_cwd`) so nothing is visible except an explicit `--add-dir`.
    """
    root = repo_root(args)
    body = skill_body(config, case.skill, root)

    argv = [
        args.claude_bin,
        "-p",
        case.prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        args.model,
    ]
    if getattr(args, "system_prompt_mode", "minimal") != "claude-code":
        argv += ["--system-prompt", minimal_system_prompt()]
    argv += [
        "--tools",
        EXECUTOR_TOOLS,
        "--strict-mcp-config",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        str(args.max_budget_usd),
    ]
    if body is not None:
        skill_dir = root / "skills" / case.skill
        extra_dirs = repo_input_dirs(body, skill_dir, root)
        header = SKILL_HEADER.format(path=skill_dir)
        if extra_dirs:
            header += REPO_INPUT_HEADER.format(
                paths=", ".join(f"`{path}`" for path in extra_dirs)
            )
        argv += [
            "--append-system-prompt",
            header + body,
            "--add-dir",
            str(skill_dir),
        ]
        for extra in extra_dirs:
            argv += ["--add-dir", str(extra)]
    argv += list(isolation_flags)

    return ClaudeRequest(
        argv=argv,
        cwd=sandbox_cwd(run_dir, args),
        env=executor_env(args),
        timeout_s=float(getattr(args, "timeout", 180.0)),
    )


def _sha256(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _flag_value(argv: List[str], flag: str) -> Optional[str]:
    """Value following `flag` in an argv, or None when the flag is absent."""
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def total_tokens(result_event: Optional[Dict[str, Any]]) -> int:
    """Every token the CLI billed for this turn, cache reads and writes included."""
    usage = (result_event or {}).get("usage") or {}
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    total = 0
    for field in fields:
        try:
            total += int(usage.get(field) or 0)
        except (TypeError, ValueError):
            continue
    return total


def resolved_model(result: ClaudeResult) -> Optional[str]:
    """Concrete model name behind the CLI alias.

    This build reports no `model` on the result event, so fall back to the
    assistant messages and then to the priciest `modelUsage` entry — the cheap
    entries are the CLI's own helper calls, not the model under test.
    """
    event = result.result_event or {}
    if isinstance(event.get("model"), str):
        return event["model"]
    for item in reversed(result.events):
        if item.get("type") == "assistant":
            name = (item.get("message") or {}).get("model")
            if isinstance(name, str):
                return name
    usage = event.get("modelUsage")
    if isinstance(usage, dict) and usage:
        def cost_of(entry: Any) -> float:
            try:
                return float((entry or {}).get("costUSD") or 0.0)
            except (TypeError, ValueError):
                return 0.0

        return max(usage.items(), key=lambda pair: cost_of(pair[1]))[0]
    return None


def write_eval_metadata(eval_dir: Path, case: BehavioralCase) -> Path:
    """`eval_metadata.json` the vendored aggregator and viewer read for prompts and ids."""
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / "eval_metadata.json"
    path.write_text(
        json.dumps(
            {
                "eval_id": case.eval_id,
                "eval_name": case.name,
                "prompt": case.prompt,
                "assertions": case.assertions,
                "key": case.key,
                "file": case.file_rel,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def render_transcript(prompt: str, result: ClaudeResult) -> str:
    """Prompt, tool calls, and response in the shape `generate_review.py` parses."""
    lines = ["# Eval Run", "", "## Eval Prompt", "", prompt.strip(), "", "## Tool Calls", ""]
    if result.tool_uses:
        for use in result.tool_uses:
            lines.append(f"- {use.get('name', '?')} {json.dumps(use.get('input') or {})}")
    else:
        lines.append("- (none)")
    lines += ["", "## Response", "", result.text.strip() or "(empty response)", ""]
    return "\n".join(lines)


def write_request_json(run_dir: Path, req: ClaudeRequest) -> Path:
    """Record the invocation without leaking secrets: env keys only, never values."""
    argv = list(req.argv)
    system_prompt = _flag_value(argv, "--system-prompt")
    appended = _flag_value(argv, "--append-system-prompt")
    path = run_dir / "request.json"
    path.write_text(
        json.dumps(
            {
                "argv": argv,
                "cwd": str(req.cwd),
                "timeout_s": req.timeout_s,
                "env_keys": sorted(req.env),
                "env_scrubbed": sorted(set(os.environ) - set(req.env)),
                "system_prompt_sha256": _sha256(system_prompt),
                "skill_body_sha256": _sha256(appended),
                "skill_chars": len(appended or ""),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def result_to_json(result: ClaudeResult) -> Dict[str, Any]:
    """Serialize a result for the cache; a cache hit must rebuild every artifact."""
    return {
        "status": result.status,
        "text": result.text,
        "tool_uses": result.tool_uses,
        "result_event": result.result_event,
        "events": result.events,
        "returncode": result.returncode,
        "duration_ms": result.duration_ms,
        "stderr_tail": result.stderr_tail,
    }


def result_from_json(payload: Dict[str, Any]) -> ClaudeResult:
    """Rebuild a cached result."""
    return ClaudeResult(
        status=str(payload.get("status") or "ok"),
        text=str(payload.get("text") or ""),
        tool_uses=list(payload.get("tool_uses") or []),
        result_event=payload.get("result_event"),
        events=list(payload.get("events") or []),
        returncode=payload.get("returncode"),
        duration_ms=int(payload.get("duration_ms") or 0),
        stderr_tail=str(payload.get("stderr_tail") or ""),
    )


def execute_case(runner: ClaudeRunner, req: ClaudeRequest, run_dir: Path) -> ClaudeResult:
    """Run one request and write `request.json`, `stream.jsonl`, outputs, and timing."""
    run_dir = Path(run_dir)
    write_request_json_at(run_dir, req)
    result = runner.run(req)
    persist_result(run_dir, req, result)
    return result


def write_request_json_at(run_dir: Path, req: ClaudeRequest) -> Path:
    """Create the run directory and record the invocation."""
    run_dir = Path(run_dir)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    return write_request_json(run_dir, req)


def persist_result(run_dir: Path, req: ClaudeRequest, result: ClaudeResult) -> None:
    """Write `stream.jsonl`, `outputs/response.md`, `transcript.md`, and `timing.json`."""
    run_dir = Path(run_dir)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    with (run_dir / "stream.jsonl").open("w", encoding="utf-8") as handle:
        for event in result.events:
            handle.write(json.dumps(event) + "\n")
    (run_dir / "outputs" / "response.md").write_text(result.text, encoding="utf-8")
    (run_dir / "transcript.md").write_text(
        render_transcript(_flag_value(list(req.argv), "-p") or "", result), encoding="utf-8"
    )

    result_event = result.result_event or {}
    (run_dir / "timing.json").write_text(
        json.dumps(
            {
                "total_tokens": total_tokens(result_event),
                "duration_ms": result.duration_ms,
                "total_duration_seconds": round(result.duration_ms / 1000.0, 3),
                "api_duration_ms": result_event.get("duration_ms"),
                "num_turns": result_event.get("num_turns"),
                "total_cost_usd": result.cost_usd,
                "model": resolved_model(result) or _flag_value(list(req.argv), "--model"),
                "model_alias": _flag_value(list(req.argv), "--model"),
                "status": result.status,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
