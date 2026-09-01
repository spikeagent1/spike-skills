"""Blind grader: a second, tool-less headless call that judges one eval response
against its assertions and writes `grading.json`.

The grader never learns which config produced the response — the payload carries
only the prompt, the expected-output summary, the assertions, and the reply text.
Output shape stays byte-compatible with the vendored skill-creator aggregator and
eval viewer so their tooling runs unmodified on our workspaces.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .cases import BehavioralCase
from .claude_cli import ClaudeRequest, ClaudeResult, ClaudeRunner, scrub_env, strategy_env
from .doctor import probe_environ
from .executor import resolved_model, sandbox_cwd
from . import HARNESS_VERSION, workspace

PROMPTS = Path(__file__).resolve().parent / "prompts"
GRADER_BUDGET_USD = 0.25
DEFAULT_STRUCTURED_FIELD = "structured_output"

STATUS_OK = "ok"
STATUS_GRADER_ERROR = "grader_error"
STATUS_NO_RESPONSE = "no_response"

# Every property is required: the CLI's structured-output mode rejects optional
# keys, so "nothing to say" is expressed with empty values, not a missing key.
GRADING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "expectations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
                "required": ["text", "passed", "evidence"],
                "additionalProperties": False,
            },
        },
        "summary": {
            "type": "object",
            "properties": {
                "passed": {"type": "integer"},
                "failed": {"type": "integer"},
                "total": {"type": "integer"},
                "pass_rate": {"type": "number"},
            },
            "required": ["passed", "failed", "total", "pass_rate"],
            "additionalProperties": False,
        },
        "eval_feedback": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "assertion": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["assertion", "reason"],
                        "additionalProperties": False,
                    },
                },
                "overall": {"type": "string"},
            },
            "required": ["suggestions", "overall"],
            "additionalProperties": False,
        },
    },
    "required": ["expectations", "summary", "eval_feedback"],
    "additionalProperties": False,
}


def grader_prompt() -> str:
    """System prompt for the grading call."""
    return PROMPTS.joinpath("grader.md").read_text(encoding="utf-8").strip()


def structured_field(args: Any = None) -> str:
    """Result field carrying `--json-schema` output, as recorded by `doctor`."""
    configured = getattr(args, "structured_output_field", None)
    if configured:
        return str(configured)
    try:
        doctor_json = json.loads(
            (workspace.WORKSPACE / "doctor.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValueError):
        return DEFAULT_STRUCTURED_FIELD
    return str(doctor_json.get("structured_output_field") or DEFAULT_STRUCTURED_FIELD)


def build_payload(case: BehavioralCase, response: str) -> Dict[str, Any]:
    """User payload for the grading call. Never names the config under test."""
    return {
        "prompt": case.prompt,
        "expected_output": case.expected_output,
        "assertions": list(case.assertions),
        "response": response,
    }


def _grader_env(args: Any) -> Dict[str, str]:
    environ = probe_environ(os.environ)
    strategy = getattr(args, "isolation_strategy", None)
    if not strategy:
        return scrub_env(environ)
    return strategy_env(strategy, workspace.WORKSPACE, environ)


def build_grader_request(
    payload: Dict[str, Any],
    args: Any,
    isolation_flags: Sequence[str],
    run_dir: Optional[Path] = None,
) -> ClaudeRequest:
    """Tool-less structured-output invocation that grades one response.

    The grader runs from the same kind of out-of-repo scratch directory as the
    executor: a cwd inside the repository pulls the operator's `~/.claude/CLAUDE.md`
    into context, which would bias the verdicts just as it biased the responses.
    """
    argv = [
        args.claude_bin,
        "-p",
        json.dumps(payload, ensure_ascii=False),
        "--output-format",
        "json",
        "--model",
        getattr(args, "grader_model", None) or args.model,
        "--system-prompt",
        grader_prompt(),
        "--tools",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--json-schema",
        json.dumps(GRADING_SCHEMA, separators=(",", ":")),
        "--max-budget-usd",
        str(GRADER_BUDGET_USD),
        *isolation_flags,
    ]
    override = getattr(args, "grader_cwd", None)
    cwd = Path(override) if override else sandbox_cwd(run_dir or Path("grader"), args, leaf="grader")
    return ClaudeRequest(
        argv=argv,
        cwd=cwd,
        env=_grader_env(args),
        timeout_s=float(getattr(args, "timeout", 180.0)),
    )


def _normalize(text: str) -> str:
    """Assertion text reduced to what a reformatting grader cannot change."""
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def _first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """First balanced JSON object in a reply, fenced or bare."""
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for end in range(start, len(text)):
            current = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : end + 1])
                    except (json.JSONDecodeError, ValueError):
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
    return None


def summarize(expectations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Summary block recomputed from the verdicts rather than trusted from the model."""
    total = len(expectations)
    passed = sum(1 for item in expectations if item.get("passed") is True)
    return {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
    }


def parse_grading(
    result: ClaudeResult, assertions: Sequence[str], *, field: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Grading object for `assertions`, or None when the grader's answer is unusable.

    A None here is an ungraded run (`grader_error`), never a failed one: the
    caller must not count an unparseable verdict as evidence about the skill.
    """
    name = field or DEFAULT_STRUCTURED_FIELD
    raw: Optional[Dict[str, Any]] = None
    event = result.result_event or {}
    if isinstance(event.get(name), dict):
        raw = event[name]
    if raw is None:
        raw = _first_json_object(result.text or "") or _first_json_object(
            event.get("result") if isinstance(event.get("result"), str) else ""
        )
    if raw is None:
        return None

    expectations = raw.get("expectations")
    if not isinstance(expectations, list) or len(expectations) != len(assertions):
        return None

    canonical: List[Dict[str, Any]] = []
    for item, assertion in zip(expectations, assertions):
        if not isinstance(item, dict) or not isinstance(item.get("passed"), bool):
            return None
        if _normalize(item.get("text", "")) != _normalize(assertion):
            return None
        canonical.append(
            {
                "text": assertion,
                "passed": item["passed"],
                "evidence": str(item.get("evidence") or ""),
            }
        )

    feedback = raw.get("eval_feedback")
    graded: Dict[str, Any] = {"expectations": canonical, "summary": summarize(canonical)}
    if isinstance(feedback, dict):
        graded["eval_feedback"] = feedback
    return graded


def _empty_grading(assertions: Sequence[str], status: str, note: str) -> Dict[str, Any]:
    """Ungraded placeholder so a run directory always has a `grading.json`.

    `summary.pass_rate` is `null` and `summary.status` is `"ungraded"`, not a
    fabricated `0.0`: the vendored `aggregate_benchmark.py` reads
    `summary.get("pass_rate", 0.0)`, and a present-but-null value stops it from
    silently reporting an ungraded run as a 0% pass rate.
    """
    return {
        "expectations": [],
        "summary": {
            "passed": 0,
            "failed": 0,
            "total": len(assertions),
            "pass_rate": None,
            "status": "ungraded",
        },
        "status": status,
        "note": note,
    }


def read_response(run_dir: Path) -> str:
    """Executor response text for a run directory."""
    try:
        return (Path(run_dir) / "outputs" / "response.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def write_grading(run_dir: Path, grading: Dict[str, Any]) -> Path:
    path = Path(run_dir) / "grading.json"
    path.write_text(json.dumps(grading, indent=2) + "\n", encoding="utf-8")
    return path


def grade_run(
    runner: ClaudeRunner,
    run_dir: Path,
    case: BehavioralCase,
    args: Any,
    isolation_flags: Sequence[str] = (),
) -> Dict[str, Any]:
    """Grade one executed run and write `grading.json`; returns what was written."""
    run_dir = Path(run_dir)
    response = read_response(run_dir)
    grader_status = "not_run"
    cost = 0.0
    resolved: Optional[str] = None

    if not response.strip():
        grading = _empty_grading(
            case.assertions, STATUS_NO_RESPONSE, "executor produced no response text"
        )
    else:
        payload = build_payload(case, response)
        result = runner.run(build_grader_request(payload, args, isolation_flags, run_dir))
        grader_status = result.status
        cost = result.cost_usd
        resolved = resolved_model(result)
        parsed = parse_grading(result, case.assertions, field=structured_field(args))
        if parsed is None:
            grading = _empty_grading(
                case.assertions,
                STATUS_GRADER_ERROR,
                f"grader status={result.status}; output did not match the assertions",
            )
        else:
            grading = dict(parsed)
            grading["status"] = STATUS_OK

    grading["grader_model"] = getattr(args, "grader_model", None) or args.model
    # The alias is what was asked for; an alias moves, and a baseline graded
    # before it moved cannot otherwise be told from one graded after. None when
    # no grading call was made, or when the reply named no model.
    grading["grader_model_resolved"] = resolved
    grading["grader_status"] = grader_status
    grading["grader_cost_usd"] = cost
    grading["harness_version"] = HARNESS_VERSION
    write_grading(run_dir, grading)
    return grading
