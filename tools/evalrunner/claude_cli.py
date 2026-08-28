"""Headless Claude Code invoker: request/result types, stream-json parsing, and
the isolation-strategy table the doctor probes.

The subprocess read loop (select-driven line reading, `CLAUDECODE` env scrub,
early stop on the first `Skill` tool_use) follows the pattern in
`imports/anthropic-skill-creator/scripts/run_eval.py:83-177`, copied rather than
imported because `imports/` is vendored and never edited.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_BUDGET_EXCEEDED = "budget_exceeded"
STATUS_RATE_LIMITED = "rate_limited"
STATUSES = (STATUS_OK, STATUS_TIMEOUT, STATUS_ERROR, STATUS_BUDGET_EXCEEDED, STATUS_RATE_LIMITED)

# Env vars Claude Code sets for its own session; they make a nested `claude -p`
# refuse to start or inherit the parent session's identity.
NESTING_ENV_PREFIX = "CLAUDE_CODE_"
NESTING_ENV_EXACT = ("CLAUDECODE",)

RETRY_BACKOFFS_S = (5.0, 20.0)
RATE_LIMIT_MARKERS = ("rate_limit", "rate limit", "429", "overloaded", "529")
# HTTP statuses the CLI reports in `api_error_status` for throttling and overload.
RATE_LIMIT_HTTP_STATUSES = (429, 529)
BUDGET_MARKERS = ("max_budget", "maximum budget")
STDERR_TAIL_CHARS = 4000
READ_CHUNK_BYTES = 65536


@dataclass(frozen=True)
class ClaudeRequest:
    """A single headless invocation: full argv (argv[0] is the binary), cwd, env, deadline."""

    argv: List[str]
    cwd: Path
    env: Dict[str, str]
    timeout_s: float


@dataclass
class ClaudeResult:
    """Outcome of one invocation. `status` is one of `STATUSES`; `run()` never raises."""

    status: str
    text: str = ""
    tool_uses: List[Dict[str, Any]] = field(default_factory=list)
    result_event: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    returncode: Optional[int] = None
    duration_ms: int = 0
    stderr_tail: str = ""

    @property
    def cost_usd(self) -> float:
        """Cost reported by the result event, 0.0 when the run produced none."""
        if not self.result_event:
            return 0.0
        try:
            return float(self.result_event.get("total_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0


class ClaudeRunner(Protocol):
    """Anything that can execute a `ClaudeRequest`; lets tests swap in a fake."""

    def run(self, req: ClaudeRequest, *, early_stop_on_skill: bool = False) -> ClaudeResult: ...


@dataclass(frozen=True)
class IsolationStrategy:
    """One candidate way to keep the user's global config out of an eval run."""

    name: str
    flags: Tuple[str, ...]
    description: str
    forced_mode_only: bool = False
    requires_env: Tuple[str, ...] = ()


ISOLATION_STRATEGIES: Tuple[IsolationStrategy, ...] = (
    IsolationStrategy(
        name="project-sources",
        flags=("--setting-sources", "project"),
        description="Load only project settings; skip user and local settings, hooks, and plugins.",
    ),
    IsolationStrategy(
        name="fresh-home",
        flags=("--settings", "{workspace}/isolated-settings.json"),
        description="Point HOME at an empty workspace home and load empty settings.",
    ),
    IsolationStrategy(
        name="bare",
        flags=("--bare",),
        description="Minimal mode; API-key auth only, no keychain or OAuth.",
        requires_env=("ANTHROPIC_API_KEY",),
    ),
    IsolationStrategy(
        name="safe-mode",
        flags=("--safe-mode",),
        description="Disable all customizations; usable for forced load mode only.",
        forced_mode_only=True,
    ),
)

_STRATEGIES_BY_NAME = {strategy.name: strategy for strategy in ISOLATION_STRATEGIES}


def strategy_names() -> List[str]:
    """Strategy names in preference order."""
    return [strategy.name for strategy in ISOLATION_STRATEGIES]


def strategy_flags(name: str, ws: Path) -> List[str]:
    """CLI flags for an isolation strategy, with workspace-relative paths resolved."""
    strategy = _STRATEGIES_BY_NAME[name]
    return [flag.replace("{workspace}", str(ws)) for flag in strategy.flags]


def strategy_env(name: str, ws: Path, environ: Mapping[str, str]) -> Dict[str, str]:
    """Scrubbed environment for an isolation strategy.

    `fresh-home` relocates HOME into the workspace so no user config is visible;
    it carries `CLAUDE_CODE_OAUTH_TOKEN` across when one is available, because a
    fresh HOME has no credentials of its own.
    """
    env = scrub_env(environ)
    if name == "fresh-home":
        env["HOME"] = str(Path(ws) / "home")
        token = environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def scrub_env(environ: Mapping[str, str]) -> Dict[str, str]:
    """Copy of `environ` without the vars that mark an enclosing Claude Code session."""
    return {
        key: value
        for key, value in environ.items()
        if key not in NESTING_ENV_EXACT and not key.startswith(NESTING_ENV_PREFIX)
    }


def _tool_uses_in_event(event: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Tool-use blocks carried by one stream event, from full or partial messages."""
    uses: List[Dict[str, Any]] = []
    if event.get("type") == "assistant":
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name", ""),
                        "input": block.get("input") or {},
                    }
                )
    elif event.get("type") == "stream_event":
        inner = event.get("event") or {}
        if inner.get("type") == "content_block_start":
            block = inner.get("content_block") or {}
            if block.get("type") == "tool_use":
                uses.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name", ""),
                        "input": block.get("input") or {},
                    }
                )
    return uses


def _partial_tool_input(event: Mapping[str, Any]) -> Optional[Tuple[Any, str]]:
    """`(block index, json fragment)` from an `input_json_delta`, else None."""
    if event.get("type") != "stream_event":
        return None
    inner = event.get("event") or {}
    if inner.get("type") != "content_block_delta":
        return None
    delta = inner.get("delta") or {}
    if delta.get("type") != "input_json_delta":
        return None
    return inner.get("index"), str(delta.get("partial_json") or "")


def parse_stream_lines(
    lines: Iterable[str],
) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fold stream-json lines into (assistant text, tool uses, result event, all events).

    Unparseable or truncated lines are dropped, so a killed process still yields
    whatever arrived before the kill.

    Under `--include-partial-messages` a tool_use arrives in three pieces: a
    `content_block_start` with an empty input, a run of `input_json_delta`
    fragments, and (on this CLI build) the completed assistant message. The
    fragments are accumulated per block index and parsed at the end, so the
    arguments are recoverable even if the completed message never arrives —
    the same reconstruction the vendored
    `imports/anthropic-skill-creator/scripts/run_eval.py:143-149` does inline.
    """
    text_parts: List[str] = []
    tool_uses: List[Dict[str, Any]] = []
    seen_tool_ids: Dict[str, int] = {}
    result_event: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = []
    # Block index -> position in `tool_uses`, and the JSON text streamed for it.
    index_positions: Dict[Any, int] = {}
    index_fragments: Dict[Any, List[str]] = {}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)

        if event.get("type") == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        elif event.get("type") == "result":
            result_event = event

        fragment = _partial_tool_input(event)
        if fragment is not None:
            index_fragments.setdefault(fragment[0], []).append(fragment[1])

        block_index = None
        if event.get("type") == "stream_event":
            inner = event.get("event") or {}
            if inner.get("type") == "content_block_start":
                block_index = inner.get("index")

        for use in _tool_uses_in_event(event):
            key = use.get("id")
            if key is not None and key in seen_tool_ids:
                # `--include-partial-messages` announces one tool_use twice: an
                # empty `content_block_start` first, then the complete assistant
                # message. The later, fuller block supersedes the placeholder, so
                # a caller reading `input` sees the arguments the model chose.
                position = seen_tool_ids[key]
                if use.get("input") and not tool_uses[position].get("input"):
                    tool_uses[position] = use
                if block_index is not None:
                    index_positions[block_index] = position
                continue
            if key is not None:
                seen_tool_ids[key] = len(tool_uses)
            if block_index is not None:
                index_positions[block_index] = len(tool_uses)
            tool_uses.append(use)

    _fill_inputs_from_fragments(tool_uses, index_positions, index_fragments)
    text = "".join(text_parts)
    if not text and result_event is not None and isinstance(result_event.get("result"), str):
        text = result_event["result"]
    return text, tool_uses, result_event, events


def _fill_inputs_from_fragments(
    tool_uses: List[Dict[str, Any]],
    index_positions: Mapping[Any, int],
    index_fragments: Mapping[Any, Sequence[str]],
) -> None:
    """Rebuild a tool_use `input` the completed message never delivered.

    A truncated or unparseable fragment run is left alone: an empty input is a
    readable "we do not know", where half-parsed arguments would be a lie.
    """
    for index, position in index_positions.items():
        if position >= len(tool_uses) or tool_uses[position].get("input"):
            continue
        blob = "".join(index_fragments.get(index) or []).strip()
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict) and parsed:
            tool_uses[position]["input"] = parsed


def parse_output(
    lines: Sequence[str],
) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse CLI stdout in either output format.

    `--output-format stream-json` is one event per line; `--output-format json`
    is a single JSON array of the same events, so fall back to a whole-blob parse
    when the line parser found nothing.
    """
    parsed = parse_stream_lines(lines)
    if parsed[3]:
        return parsed
    blob = "\n".join(lines).strip()
    if not blob:
        return parsed
    try:
        payload = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return parsed
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return parsed
    return parse_stream_lines(json.dumps(event) for event in payload if isinstance(event, dict))


def extract_result_object(payload: Any) -> Optional[Dict[str, Any]]:
    """Result event from an `--output-format json` payload.

    This build emits a JSON array of events rather than a single result object,
    so accept either shape.
    """
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for item in reversed(payload):
            if isinstance(item, dict) and item.get("type") == "result":
                return item
    return None


def _line_has_skill_tool_use(line: str) -> bool:
    """True when this line carries a `Skill` tool_use that names the skill.

    The name is required, not incidental: under `--include-partial-messages` the
    first announcement of the block has an empty `input`, and stopping there
    would kill the process before the answer — which skill was picked — arrives.
    """
    if "Skill" not in line:
        return False
    try:
        event = json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(event, dict):
        return False
    return any(
        use.get("name") == "Skill" and (use.get("input") or {}).get("skill")
        for use in _tool_uses_in_event(event)
    )


def _is_rate_limit_http_status(value: Any) -> bool:
    """True when `api_error_status` names a throttling or overload response."""
    try:
        return int(value) in RATE_LIMIT_HTTP_STATUSES
    except (TypeError, ValueError):
        return False


def classify_status(
    result_event: Optional[Mapping[str, Any]], returncode: Optional[int], stderr_tail: str
) -> str:
    """Map a finished invocation onto one of `STATUSES`.

    A failed turn does not always carry an `errors` list: the CLI reports many
    failures as `subtype: "success"` with `is_error: true`, the HTTP status in
    `api_error_status`, and the message in `result`. All of those are scanned.
    The model's own reply text and stderr are read only when the CLI flagged an
    error, so a successful answer that happens to discuss HTTP 429 stays `ok`.
    """
    if result_event is not None:
        is_error = bool(result_event.get("is_error"))
        parts = [
            str(result_event.get("subtype") or ""),
            str(result_event.get("terminal_reason") or ""),
        ]
        parts.extend(str(err) for err in (result_event.get("errors") or []))
        if is_error:
            message = result_event.get("result")
            if isinstance(message, str):
                parts.append(message)
            parts.append(stderr_tail)
        blob = " ".join(parts).lower()
        if any(marker in blob for marker in BUDGET_MARKERS):
            return STATUS_BUDGET_EXCEEDED
        if _is_rate_limit_http_status(result_event.get("api_error_status")) or any(
            marker in blob for marker in RATE_LIMIT_MARKERS
        ):
            return STATUS_RATE_LIMITED
        return STATUS_ERROR if is_error else STATUS_OK
    lowered = stderr_tail.lower()
    if any(marker in lowered for marker in RATE_LIMIT_MARKERS):
        return STATUS_RATE_LIMITED
    return STATUS_OK if returncode == 0 else STATUS_ERROR


class SubprocessClaudeRunner:
    """Runs `claude` as a subprocess and folds its stream-json output into a `ClaudeResult`."""

    def __init__(self, claude_bin: str = "claude", sleep=time.sleep) -> None:
        self.claude_bin = claude_bin
        self._sleep = sleep

    def argv(self, *args: str) -> List[str]:
        """Full argv for this runner's binary."""
        return [self.claude_bin, *args]

    def run(self, req: ClaudeRequest, *, early_stop_on_skill: bool = False) -> ClaudeResult:
        """Execute `req`, retrying on rate limits. Never raises."""
        result = self._run_once(req, early_stop_on_skill)
        for backoff in RETRY_BACKOFFS_S:
            if result.status != STATUS_RATE_LIMITED:
                return result
            self._sleep(backoff)
            result = self._run_once(req, early_stop_on_skill)
        return result

    def _run_once(self, req: ClaudeRequest, early_stop_on_skill: bool) -> ClaudeResult:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                list(req.argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(req.cwd),
                env=dict(req.env),
                start_new_session=True,
            )
        except OSError as exc:
            return ClaudeResult(
                status=STATUS_ERROR,
                stderr_tail=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        lines, stderr_text, timed_out, stopped_early = self._read_streams(
            process, req, early_stop_on_skill
        )
        self._terminate(process)
        self._close_streams(process)

        text, tool_uses, result_event, events = parse_output(lines)
        stderr_tail = stderr_text[-STDERR_TAIL_CHARS:]
        if timed_out:
            status = STATUS_TIMEOUT
        elif stopped_early:
            status = STATUS_OK
        else:
            status = classify_status(result_event, process.returncode, stderr_tail)
        return ClaudeResult(
            status=status,
            text=text,
            tool_uses=tool_uses,
            result_event=result_event,
            events=events,
            returncode=process.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            stderr_tail=stderr_tail,
        )

    @staticmethod
    def _read_streams(
        process: "subprocess.Popen[bytes]", req: ClaudeRequest, early_stop_on_skill: bool
    ) -> Tuple[List[str], str, bool, bool]:
        """Drain stdout and stderr until EOF, deadline, or the first `Skill` tool_use.

        Both pipes are read from this one loop rather than a reader thread: a
        surviving grandchild can hold a pipe open past the child's death, and a
        blocked reader thread would then deadlock the close that follows.
        """
        stdout, stderr = process.stdout, process.stderr
        open_streams = [stream for stream in (stdout, stderr) if stream is not None]
        deadline = time.monotonic() + req.timeout_s
        buffer = ""
        lines: List[str] = []
        stderr_parts: List[str] = []
        timed_out = False
        stopped_early = False

        while open_streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready, _, _ = select.select(open_streams, [], [], min(0.5, remaining))
            if not ready:
                # The process is gone and the pipes are quiet: nothing more is coming,
                # even if a grandchild is still holding a write end open.
                if process.poll() is not None:
                    break
                continue
            for stream in list(ready):
                try:
                    chunk = os.read(stream.fileno(), READ_CHUNK_BYTES)
                except (OSError, ValueError):
                    chunk = b""
                if not chunk:
                    open_streams.remove(stream)
                    continue
                decoded = chunk.decode("utf-8", errors="replace")
                if stream is stderr:
                    stderr_parts.append(decoded)
                    continue
                buffer += decoded
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    lines.append(line)
                    if early_stop_on_skill and _line_has_skill_tool_use(line):
                        stopped_early = True
                        break
                if stopped_early:
                    break
            if stopped_early:
                break

        if buffer.strip():
            lines.append(buffer)
        return lines, "".join(stderr_parts), timed_out, stopped_early

    @staticmethod
    def _terminate(process: "subprocess.Popen[bytes]") -> None:
        """Kill the whole process group, so a shell wrapper's children die too."""
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    process.kill()
                except OSError:
                    pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _close_streams(process: "subprocess.Popen[bytes]") -> None:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass


def format_argv(argv: Sequence[str]) -> str:
    """Shell-ish rendering of an argv for human-readable summaries."""
    parts = []
    for arg in argv:
        parts.append(f"'{arg}'" if (not arg or any(ch.isspace() for ch in arg)) else arg)
    return " ".join(parts)
