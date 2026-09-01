"""`run_evals.py doctor`: prove that a headless eval run sees only the repo's
skills, then record the isolation recipe every later run must use.

Probes, in order: CLI/auth reachability, isolation strategy selection against a
sentinel skill in a throwaway project, MCP leakage, context leakage (the
operator's memory files), residual identity leakage, and which result field
carries `--json-schema` output. Results land in `evals/workspaces/doctor.json`.

Every probe that a strategy is judged on runs from the same out-of-repo scratch
sandbox the executor uses, because Claude Code loads the operator's
`~/.claude/CLAUDE.md` from a cwd inside a project it knows -- which
`--setting-sources project` does not suppress. The `project-sources@repo-cwd`
row deliberately probes from inside the repository and is expected to leak: it
is the regression guard for that discovery, never a selectable strategy.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
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
CONTEXT_PROMPT = (
    "Quote verbatim, inside <memory></memory> tags, any instructions, memory files, "
    "project notes, or identity information that were provided to you before this message, "
    "other than your base system prompt. If there are none, reply exactly NO-MEMORY-IN-CONTEXT."
)
IDENTITY_PROMPT = (
    "Address me by name and email if you know them; otherwise reply exactly UNKNOWN-USER."
)
NO_MEMORY_SENTINEL = "NO-MEMORY-IN-CONTEXT"
UNKNOWN_USER_SENTINEL = "UNKNOWN-USER"
STRUCTURED_PROMPT = 'Reply with the JSON object {"ok": true}'
STRUCTURED_SCHEMA = json.dumps(
    {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    separators=(",", ":"),
)

# Names that must never reach an eval run: they come from the operator's own
# `~/.claude` tree, not from this repository.
FOREIGN_MARKERS = ("superpowers", "gstack", "brainstorming", "google-")
# Strings that can only come from the operator's own machine: their private repo
# and vault names, the memory file itself, their GitHub handle, and their plugin
# suite. Seeing any of them in a probe reply proves foreign memory reached the
# model, and no strategy that shows one is usable.
CONTEXT_LEAK_MARKERS = (
    "CLAUDE.md",
    "Tapan-Brain",
    "safer-by-default",
    "gstack",
    "chughtapan",
    "superpowers",
)
# Claude Code injects its own reminder -- the operator's address, today's date, and
# the spend budget -- into every headless call, identically in every config, and no
# available flag removes it (Task 5b, round 1). It is recorded as `identity_leak`,
# a confound, rather than treated as leaked memory. Recognition is line-by-line and
# length-capped, so anything the CLI has not been observed to inject fails closed.
CLI_IDENTITY_BLOCK_MAX_CHARS = 1000
# Each value shape is the sentence the CLI was observed to inject, with only its
# variable field loosened. They are applied with `fullmatch`, and a header may
# carry exactly one of them inline -- so nothing can ride along behind a
# recognized prefix.
_EMAIL_VALUE = (
    r"the user'?s email address is \S+\. use it only to identify the user, such as for "
    r"authorship, attribution, or filtering their own work\. never send it to an unrelated "
    r"service, such as in a request header, url, or payload, unless the user explicitly asks\."
)
_DATE_VALUE = r"today'?s date is \d{4}-\d{2}-\d{2}\.?"
_BUDGET_VALUE = r"(?:usd|token) budget:[\s$\d.,/;]*(?:remaining)?"
_IMPORTANT_VALUE = (
    r"important: this context may or may not be relevant to your tasks\. you should not respond "
    r"to this context unless it is highly relevant to your task\."
)
_HEADER_VALUES = (
    (r"user\s*email", _EMAIL_VALUE),
    (r"current\s*date", _DATE_VALUE),
    (r"budget", _BUDGET_VALUE),
)
CLI_REMINDER_LINE_RES = tuple(
    re.compile(rf"#{{0,3}}\s*{header}(?:\s+{value})?", re.IGNORECASE)
    for header, value in _HEADER_VALUES
) + tuple(
    re.compile(value, re.IGNORECASE)
    for value in (_EMAIL_VALUE, _DATE_VALUE, _BUDGET_VALUE, _IMPORTANT_VALUE)
)
CURRENT_DATE_RE = re.compile(r"#\s*current\s*date\b|today'?s date is\b", re.IGNORECASE)
# A `<memory>` block this short cannot carry a quoted memory file. The sentinel is
# exactly 20 characters, so a model that wraps it in the tags stays under the bar;
# it is also excluded by value, in case the wording ever grows.
MEMORY_BLOCK_MAX_CHARS = 20
MEMORY_BLOCK_RE = re.compile(r"<memory>(.*?)(?:</memory>|\Z)", re.DOTALL | re.IGNORECASE)
MEMORY_OPEN_RE = re.compile(r"<memory>", re.IGNORECASE)
MEMORY_CLOSE_RE = re.compile(r"</memory>", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
REDACTED_EMAIL = "[redacted-email]"
REDACTED_NAME = "[redacted-name]"
EVIDENCE_CHARS = 400
MIN_NAME_CHARS = 3
# Comparison rows are recorded for evidence and never selected as a strategy.
REPO_CWD_PROBE = "project-sources@repo-cwd"
STRUCTURED_OUTPUT_CANDIDATES = ("structured_output", "structuredOutput", "structured_result")
PROBE_OK_STATUSES = (STATUS_OK, STATUS_BUDGET_EXCEEDED)


@dataclass
class ProbeResult:
    """What one isolation strategy showed: visible skills, MCP tools, and context.

    `context_leak_ok` is None until the context probe actually ran, so a strategy
    whose context was never checked can never be selected.
    """

    name: str
    available: bool = True
    status: str = STATUS_OK
    sentinel_seen: bool = False
    foreign_skills: List[str] = field(default_factory=list)
    mcp_tools: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    context_leak_ok: Optional[bool] = None
    context_markers: List[str] = field(default_factory=list)
    context_evidence: str = ""
    current_date_seen: bool = False
    comparison: bool = False
    guard_state: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "status": self.status,
            "sentinel_seen": self.sentinel_seen,
            "foreign_skills": list(self.foreign_skills),
            "mcp_tools": list(self.mcp_tools),
            "notes": list(self.notes),
            "context_leak_ok": self.context_leak_ok,
            "context_markers": list(self.context_markers),
            "context_evidence": self.context_evidence,
            "current_date_seen": self.current_date_seen,
            "comparison": self.comparison,
            "guard_state": self.guard_state,
        }


@dataclass
class IdentityProbeResult:
    """One rung of the identity-mitigation ladder and what it leaked."""

    name: str
    available: bool = True
    status: str = STATUS_OK
    leak: bool = False
    markers: List[str] = field(default_factory=list)
    evidence: str = ""
    notes: List[str] = field(default_factory=list)
    confirmed: bool = False
    unproven: bool = False

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "status": self.status,
            "leak": self.leak,
            "markers": list(self.markers),
            "evidence": self.evidence,
            "notes": list(self.notes),
            "confirmed": self.confirmed,
            "unproven": self.unproven,
        }


@dataclass(frozen=True)
class IdentityMitigation:
    """A candidate way to keep the operator's identity out of the model's context."""

    name: str
    strategy: Optional[str] = None
    extra_flags: Tuple[str, ...] = ()
    requires_env: Tuple[str, ...] = ()


def skills_clean(probe: ProbeResult) -> bool:
    """True when a probe ran and showed only the sentinel: no foreign skill, no MCP tool."""
    if probe.comparison or not probe.available or probe.status not in PROBE_OK_STATUSES:
        return False
    return probe.sentinel_seen and not probe.foreign_skills and not probe.mcp_tools


def choose_strategy(probe_results: Iterable[ProbeResult]) -> Optional[str]:
    """First strategy that ran clean on skills, MCP tools, and context alike.

    A probe whose context check never ran (`context_leak_ok is None`) is not a
    candidate: an unverified context is treated exactly like a leaking one.
    """
    for probe in probe_results:
        if skills_clean(probe) and probe.context_leak_ok is True:
            return probe.name
    return None


def name_variants(name: str) -> List[str]:
    """The operator's full name and its given name, longest first.

    Longest first so replacing the full name never leaves a stray given name
    behind. Parts under `MIN_NAME_CHARS` are dropped: they cannot be told apart
    from ordinary words, and mangling prose is its own kind of damage.
    """
    parts = [part for part in name.split() if len(part) >= MIN_NAME_CHARS]
    full = name.strip()
    variants = ([full] if len(full) >= MIN_NAME_CHARS else []) + parts
    return sorted(dict.fromkeys(variants), key=len, reverse=True)


def redact_identity(text: str, email: str = "", name: str = "") -> str:
    """Text with the operator's address and name -- and any other address -- replaced.

    Probe replies reach `doctor.json`, the probe stream files, and the terminal, so
    the identity the probe is hunting for must never survive into any of them.
    """
    if email:
        text = re.sub(re.escape(email), REDACTED_EMAIL, text, flags=re.IGNORECASE)
    text = EMAIL_RE.sub(REDACTED_EMAIL, text)
    for variant in name_variants(name):
        text = re.sub(re.escape(variant), REDACTED_NAME, text, flags=re.IGNORECASE)
    return text


def evidence_snippet(
    text: str, email: str = "", limit: int = EVIDENCE_CHARS, name: str = ""
) -> str:
    """One-line, redacted, length-bounded excerpt of a probe reply."""
    flat = " ".join(redact_identity(text, email, name).split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + " [truncated]"


def memory_blocks(text: str) -> List[str]:
    """Contents of every `<memory>` block in a reply; an unclosed block runs to the end."""
    return [block.strip() for block in MEMORY_BLOCK_RE.findall(text)]


def is_cli_identity_block(text: str) -> bool:
    """True when a `<memory>` block is only Claude Code's own identity/date/budget reminder.

    Every non-empty line must match a shape the CLI has actually been observed to
    inject, and the block must stay under `CLI_IDENTITY_BLOCK_MAX_CHARS`. One
    unrecognized line, or a longer block, means unknown content and a hard failure.
    """
    body = text.strip()
    if not body or len(body) > CLI_IDENTITY_BLOCK_MAX_CHARS:
        return False
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    return all(
        any(pattern.fullmatch(line) for pattern in CLI_REMINDER_LINE_RES) for line in lines
    )


def current_date_injected(text: str) -> bool:
    """True when the CLI's `# currentDate` reminder shows up in a probe reply."""
    return bool(CURRENT_DATE_RE.search(text))


def context_leak_markers(text: str) -> List[str]:
    """Every signal in a context-probe reply that foreign *memory* reached the model.

    The operator's address is deliberately not one: the CLI injects it into every
    config, so it cannot differentiate two configs and is recorded as
    `identity_leak` instead (controller ruling, Task 5b round 2). Memory content
    -- the operator's CLAUDE.md, vault, or repos -- stays a hard failure.
    """
    lowered = text.lower()
    found = [marker for marker in CONTEXT_LEAK_MARKERS if marker.lower() in lowered]
    for block in memory_blocks(text):
        if block == NO_MEMORY_SENTINEL or len(block) <= MEMORY_BLOCK_MAX_CHARS:
            continue
        if is_cli_identity_block(block):
            continue
        found.append("memory-block")
        break
    return found


def reply_terminated(text: str) -> bool:
    """True when a content probe's reply ran to its own end rather than being cut off.

    Two endings are recognizable: the reply finishes with the sentinel, or every
    `<memory>` it opened is closed. A reply the spend cap or a timeout truncated
    shows neither, and must never be read as "the model quoted no memory".
    """
    body = text.strip()
    if not body:
        return False
    if body.rstrip(" .\n").endswith(NO_MEMORY_SENTINEL):
        return True
    opens = len(MEMORY_OPEN_RE.findall(body))
    return opens > 0 and opens == len(MEMORY_CLOSE_RE.findall(body))


def context_probe_verdict(text: str, status: str) -> Optional[bool]:
    """True when the context is clean, False when it leaked, None when unjudgeable.

    `None` is not a soft pass: `choose_strategy` treats an unprobed context exactly
    like a leaking one. Only `STATUS_OK` counts -- `budget_exceeded` means the turn
    was cut off by the spend cap, and an answer that stops early carries no proof.
    """
    if status != STATUS_OK or not reply_terminated(text):
        return None
    return not context_leak_markers(text)


def regression_guard_state(markers: Sequence[str], text: str, status: str) -> str:
    """What the in-repo control row proved: `held`, `inconclusive`, or `unanswered`.

    Markers are evidence in their own right -- truncation can hide a leak, never
    invent one -- so a capped reply that still quoted memory counts as held.
    """
    if markers:
        return "held"
    if status != STATUS_OK or not reply_terminated(text):
        return "unanswered"
    return "inconclusive"


def identity_markers(text: str, email: str = "", name: str = "") -> List[str]:
    """Operator identity the model volunteered when asked who it is talking to.

    A name shorter than `MIN_NAME_CHARS` is ignored: it cannot be told apart from
    ordinary prose, and a false leak report is worse than a missed one here.
    """
    lowered = text.lower()
    found: List[str] = []
    if email and email.lower() in lowered:
        found.append("email")
    if len(name.strip()) >= MIN_NAME_CHARS and name.lower() in lowered:
        found.append("name")
    return found


def mitigation_confirmed(text: str, status: str, email: str = "", name: str = "") -> bool:
    """True when a rung's own context probe ran to the end and quoted no identity.

    A rung that answers UNKNOWN-USER has only declined to repeat what it was told;
    the injected identity block can still be sitting in its context. Only a whole
    context reply -- `STATUS_OK`, terminated, and free of memory markers -- settles
    it, because a claim of absence is exactly what truncation fakes best.
    """
    if status != STATUS_OK or not reply_terminated(text):
        return False
    if context_leak_markers(text):
        return False
    return not identity_markers(text, email, name)


def identity_ladder(strategy: Optional[str]) -> List[IdentityMitigation]:
    """Mitigations to try, in order, starting from the recipe a run would use today.

    The current recipe is rung one, so a clean result there records that no
    mitigation is needed; later rungs never repeat the strategy already tried.
    """
    current = strategy or "project-sources"
    rungs = [IdentityMitigation(name=f"{current}@sandbox", strategy=current)]
    candidates = [
        IdentityMitigation(name="empty-setting-sources", extra_flags=("--setting-sources", "")),
        IdentityMitigation(
            name="bare", strategy="bare", requires_env=("ANTHROPIC_API_KEY",)
        ),
        IdentityMitigation(name="fresh-home", strategy="fresh-home"),
    ]
    return rungs + [rung for rung in candidates if rung.strategy != current]


def choose_identity_mitigation(probes: Iterable[IdentityProbeResult]) -> Optional[str]:
    """First rung whose absence of identity was positively confirmed, else None.

    Every condition is a positive proof: the rung ran to completion (`STATUS_OK`,
    not merely "ok-ish" -- a budget-capped turn proves nothing), its confirmation
    probe answered (`confirmed`, not `unproven`), and it showed no identity.
    """
    for probe in probes:
        if not probe.available or probe.status != STATUS_OK:
            continue
        if probe.confirmed and not probe.unproven and not probe.leak:
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


def save_stream(path: Path, result: ClaudeResult, email: str = "", name: str = "") -> None:
    """Persist a probe's events and stderr for fixture capture, identity redacted.

    Redaction runs over each serialized event rather than over chosen fields, so a
    reply quoted in a nested block is covered too; the placeholders carry no JSON
    metacharacters, so the line stays parseable. These files exist to become test
    fixtures -- a raw one is a committed leak waiting to happen.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in result.events:
            handle.write(redact_identity(json.dumps(event), email, name) + "\n")
    if result.stderr_tail:
        path.with_suffix(".stderr.txt").write_text(
            redact_identity(result.stderr_tail, email, name), encoding="utf-8"
        )


def save_content_record(
    path: Path, result: ClaudeResult, markers: Sequence[str], evidence: str
) -> None:
    """Persist what a content probe *proved*, never what the model quoted.

    The context and control probes ask the model to read its whole context aloud,
    so their replies are the operator's memory verbatim. Only the verdict, the
    markers, a redacted excerpt, and the reply length are kept.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": result.status,
                "markers": list(markers),
                "evidence_redacted": evidence,
                "length": len(result.text),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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


def probe_sandbox(run_dir: Path, args: Any, leaf: str) -> Path:
    """Scratch cwd for one probe, under the same out-of-repo root the executor uses.

    Imported lazily because `executor` imports `probe_environ` from this module; a
    module-level import would close the cycle. The path logic itself is never
    duplicated -- a probe must run where the executor runs or it proves nothing.
    """
    from .executor import sandbox_cwd

    return sandbox_cwd(run_dir, args, leaf=leaf)


def run_probe(
    runner: SubprocessClaudeRunner,
    args: Any,
    *,
    prompt: str,
    label: str,
    cwd: Path,
    flags: Sequence[str],
    env: Mapping[str, str],
    email: str = "",
    name: str = "",
    content: bool = False,
) -> ClaudeResult:
    """Run one tool-less probe and persist it under `probes/<label>`.

    A `content` probe asked the model to recite its own context, so its reply is
    kept only as a verdict record (`save_content_record`); every other probe keeps
    a redacted stream.
    """
    result = runner.run(
        ClaudeRequest(
            argv=base_argv(runner, prompt, args.model, "", args.max_budget_usd) + list(flags),
            cwd=cwd,
            env=dict(env),
            timeout_s=args.timeout,
        )
    )
    if content:
        save_content_record(
            workspace.PROBES / f"{label}.json",
            result,
            context_leak_markers(result.text),
            evidence_snippet(result.text, email, name=name),
        )
    else:
        save_stream(workspace.PROBES / f"{label}.jsonl", result, email, name)
    return result


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

    # Read from git at runtime so no operator address is ever committed; both are
    # used only to detect and then redact identity in probe replies.
    email = workspace.git_config("user.email")
    operator_name = workspace.git_config("user.name")
    notes.append(
        "operator identity for leak detection: "
        f"email {'known' if email else 'unknown'}, name {'known' if operator_name else 'unknown'}"
    )

    sandbox_run = probes_dir / f"doctor-{workspace.utc_stamp()}"
    auth_dir = probe_sandbox(sandbox_run, args, "auth")
    sandbox_root = auth_dir.parent
    notes.append(f"probe sandbox root: {sandbox_root}")
    try:
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
        save_stream(probes_dir / "auth.jsonl", auth_result, email, operator_name)
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
        baseline_dir = probe_sandbox(sandbox_run, args, "builtin-baseline")
        baseline_result = runner.run(
            ClaudeRequest(
                argv=base_argv(runner, SENTINEL_PROMPT, args.model, "Skill", args.max_budget_usd)
                + strategy_flags("fresh-home", ws),
                cwd=baseline_dir,
                env=strategy_env("fresh-home", ws, environ),
                timeout_s=args.timeout,
            )
        )
        save_stream(probes_dir / "builtin-baseline.jsonl", baseline_result, email, operator_name)
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
            proj = write_sentinel_project(
                probe_sandbox(sandbox_run, args, f"isolation-{strategy.name}"), sentinel
            )
            argv = base_argv(
                runner, SENTINEL_PROMPT, args.model, "Skill", args.max_budget_usd
            ) + strategy_flags(strategy.name, ws)
            env = strategy_env(strategy.name, ws, environ)
            result = runner.run(
                ClaudeRequest(argv=argv, cwd=proj, env=env, timeout_s=args.timeout)
            )
            save_stream(probes_dir / f"isolation-{strategy.name}.jsonl", result, email, operator_name)
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

        # Context probes, in preference order, for the strategies the skills/MCP
        # check did not already disqualify. The first clean answer settles the
        # question, so the ladder stops there rather than spending more calls.
        for probe in probes:
            if not skills_clean(probe):
                continue
            if any(other.context_leak_ok for other in probes):
                probe.notes.append("context probe skipped: an earlier strategy proved clean")
                continue
            ctx_result = run_probe(
                runner,
                args,
                prompt=CONTEXT_PROMPT,
                label=f"context-{probe.name}",
                cwd=probe_sandbox(sandbox_run, args, f"context-{probe.name}"),
                flags=strategy_flags(probe.name, ws),
                env=strategy_env(probe.name, ws, environ),
                email=email,
                name=operator_name,
                content=True,
            )
            costs.append(ctx_result.cost_usd)
            probe.context_leak_ok = context_probe_verdict(ctx_result.text, ctx_result.status)
            probe.context_markers = context_leak_markers(ctx_result.text)
            probe.context_evidence = evidence_snippet(ctx_result.text, email, name=operator_name)
            probe.current_date_seen = current_date_injected(ctx_result.text)
            probe.notes.append(f"context probe status={ctx_result.status}")
            if probe.context_leak_ok is None:
                probe.notes.append(
                    "context probe did not run to the end; the context stays unproven"
                )
            elif NO_MEMORY_SENTINEL not in ctx_result.text and not probe.context_markers:
                probe.notes.append("context probe answered without the sentinel; no leak marker")

        # Regression guard for Task 3's discovery: the same probe from a cwd inside
        # the repository, where Claude Code loads the operator's CLAUDE.md. Recorded
        # as evidence only -- `comparison` keeps it out of strategy selection.
        repo_cwd = probes_dir / "repo-cwd"
        repo_cwd.mkdir(parents=True, exist_ok=True)
        repo_result = run_probe(
            runner,
            args,
            prompt=CONTEXT_PROMPT,
            label="context-repo-cwd",
            cwd=repo_cwd,
            flags=strategy_flags("project-sources", ws),
            env=scrub_env(environ),
            email=email,
            name=operator_name,
            content=True,
        )
        costs.append(repo_result.cost_usd)
        repo_markers = context_leak_markers(repo_result.text)
        guard_state = regression_guard_state(repo_markers, repo_result.text, repo_result.status)
        repo_probe = ProbeResult(
            name=REPO_CWD_PROBE,
            status=repo_result.status,
            comparison=True,
            context_leak_ok=context_probe_verdict(repo_result.text, repo_result.status),
            context_markers=repo_markers,
            context_evidence=evidence_snippet(repo_result.text, email, name=operator_name),
            current_date_seen=current_date_injected(repo_result.text),
            guard_state=guard_state,
            notes=[f"comparison only: cwd {repo_cwd} is inside the repository"],
        )
        if guard_state == "inconclusive":
            repo_probe.notes.append(
                "control row expected to leak but did not - guard inconclusive"
            )
        elif guard_state == "unanswered":
            repo_probe.notes.append(
                "control row did not run to the end; the guard proved nothing this run"
            )
        probes.append(repo_probe)

        strategy_name = choose_strategy(probes)

        # Identity ladder: what a run would see today, then each mitigation in turn
        # until one answers without naming the operator.
        identity_probes: List[IdentityProbeResult] = []
        for rung in identity_ladder(strategy_name):
            rung_probe = IdentityProbeResult(name=rung.name)
            missing = [key for key in rung.requires_env if not environ.get(key)]
            if missing:
                rung_probe.available = False
                rung_probe.notes.append(f"skipped: {', '.join(missing)} not set")
                identity_probes.append(rung_probe)
                continue
            flags = strategy_flags(rung.strategy, ws) if rung.strategy else list(rung.extra_flags)
            env = (
                strategy_env(rung.strategy, ws, environ)
                if rung.strategy
                else scrub_env(environ)
            )
            id_result = run_probe(
                runner,
                args,
                prompt=IDENTITY_PROMPT,
                label=f"identity-{rung.name}",
                cwd=probe_sandbox(sandbox_run, args, f"identity-{rung.name}"),
                flags=flags,
                env=env,
                email=email,
                name=operator_name,
            )
            costs.append(id_result.cost_usd)
            rung_probe.status = id_result.status
            rung_probe.markers = identity_markers(id_result.text, email, operator_name)
            rung_probe.leak = bool(rung_probe.markers)
            rung_probe.evidence = evidence_snippet(id_result.text, email, name=operator_name)
            if id_result.status not in PROBE_OK_STATUSES:
                rung_probe.notes.append("probe did not complete; absence of a leak proves nothing")
            elif UNKNOWN_USER_SENTINEL not in id_result.text and not rung_probe.markers:
                rung_probe.notes.append("answered without the sentinel; no identity marker either")
            identity_probes.append(rung_probe)
            if rung_probe.status not in PROBE_OK_STATUSES or rung_probe.leak:
                continue
            confirm = run_probe(
                runner,
                args,
                prompt=CONTEXT_PROMPT,
                label=f"identity-confirm-{rung.name}",
                cwd=probe_sandbox(sandbox_run, args, f"identity-confirm-{rung.name}"),
                flags=flags,
                env=env,
                email=email,
                name=operator_name,
                content=True,
            )
            costs.append(confirm.cost_usd)
            if confirm.status != STATUS_OK or not reply_terminated(confirm.text):
                rung_probe.unproven = True
                rung_probe.notes.append(
                    f"confirmation probe did not answer (status={confirm.status}); "
                    "mitigation unproven"
                )
                continue
            if not mitigation_confirmed(confirm.text, confirm.status, email, operator_name):
                rung_probe.leak = True
                rung_probe.markers.append("context-identity")
                rung_probe.evidence = evidence_snippet(confirm.text, email, name=operator_name)
                rung_probe.notes.append(
                    "did not name the operator, but its context probe still quotes the "
                    "injected identity block"
                )
                continue
            rung_probe.confirmed = True
            rung_probe.notes.append("confirmed: the context probe quotes no operator identity")
            break

        structured_field: Optional[str] = None
        if strategy_name:
            struct_dir = probe_sandbox(sandbox_run, args, "structured")
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
                redact_identity(json.dumps(struct_result.events), email, operator_name) + "\n",
                encoding="utf-8",
            )
            costs.append(struct_result.cost_usd)
            result_obj = extract_result_object(struct_result.events)
            if result_obj:
                structured_field = structured_output_field(result_obj)
            else:
                notes.append(f"structured-output probe status={struct_result.status}")

            skill_dir = probe_sandbox(sandbox_run, args, "skill-invoke")
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
            save_stream(probes_dir / "skill-invoke.jsonl", invoke_result, email, operator_name)
            costs.append(invoke_result.cost_usd)
            notes.append(
                "skill-invoke probe tool_uses: "
                + (", ".join(use.get("name", "") for use in invoke_result.tool_uses) or "none")
            )

        error_dir = probe_sandbox(sandbox_run, args, "error")
        error_result = runner.run(
            ClaudeRequest(
                argv=base_argv(runner, AUTH_PROMPT, "zzz-not-a-model", "", args.max_budget_usd)
                + strategy_flags(strategy_name or "project-sources", ws),
                cwd=error_dir,
                env=strategy_env(strategy_name or "project-sources", ws, environ),
                timeout_s=args.timeout,
            )
        )
        save_stream(probes_dir / "error.jsonl", error_result, email, operator_name)
        notes.append(f"invalid-model probe status={error_result.status}")
    finally:
        shutil.rmtree(sandbox_root, ignore_errors=True)

    chosen_flags = strategy_flags(strategy_name, ws) if strategy_name else []
    argv_template = format_argv(
        base_argv(runner, "<PROMPT>", args.model, "Read,Glob,Grep", 0.5) + chosen_flags
    )
    chosen_probe = next((p for p in probes if p.name == strategy_name), None)
    # The recipe a run will actually use is the ladder's first rung, so that is
    # what `identity_leak` describes; later rungs only say whether a fix exists.
    # With no strategy chosen there is no chosen probe, but the reason for the
    # refusal is exactly what a reader needs at the top level: fall back to the
    # first real strategy that produced a reply.
    evidence_probe = chosen_probe or next(
        (probe for probe in probes if not probe.comparison and probe.context_evidence), None
    )
    current_rung = identity_probes[0] if identity_probes else None
    identity_leak = bool(current_rung and current_rung.leak)
    identity_mitigation = choose_identity_mitigation(identity_probes)
    date_injected = any(probe.current_date_seen for probe in probes if not probe.comparison)
    regression_guard = next(
        (probe.guard_state for probe in probes if probe.comparison and probe.guard_state),
        "unanswered",
    )
    # Named so a run, a report, or a later eval-fixture audit can point at the exact
    # thing the harness could not remove.
    confounds: List[str] = []
    if identity_leak:
        confounds.append("cli-identity-block")
    if date_injected:
        confounds.append("cli-current-date")

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
        "context_leak_ok": bool(chosen_probe and chosen_probe.context_leak_ok),
        "context_probe_evidence": evidence_probe.context_evidence if evidence_probe else "",
        "identity_leak": identity_leak,
        "identity_mitigation": identity_mitigation,
        "identity_probes": [probe.to_json() for probe in identity_probes],
        "current_date_injected": date_injected,
        "confounds": confounds,
        "regression_guard": regression_guard,
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
        if skills_clean(probe) and probe.context_leak_ok is None:
            # Clean on skills and MCP, but an earlier strategy already won, so its
            # context was never probed: unproven, not failed.
            verdict = "n/p"
        if not probe.available:
            verdict = "skip"
        if probe.comparison:
            verdict = "comp"
        context = {True: "ok", False: "LEAK", None: "-"}[probe.context_leak_ok]
        if probe.comparison:
            context = {"held": "LEAK", "inconclusive": "clean", "unanswered": "UNANS"}[
                probe.guard_state or "unanswered"
            ]
        print(
            f"  {verdict:4}  {probe.name:24} status={probe.status:15} "
            f"sentinel={'yes' if probe.sentinel_seen else 'no':3} "
            f"foreign={len(probe.foreign_skills)} mcp={len(probe.mcp_tools)} "
            f"context={context}"
        )
        for note in probe.notes:
            print(f"          - {note}")
        if probe.foreign_skills:
            print(f"          - leaked: {', '.join(probe.foreign_skills[:10])}")
        if probe.context_markers:
            print(f"          - context leak: {', '.join(probe.context_markers)}")
        if probe.context_evidence:
            print(f"          - context reply: {probe.context_evidence[:200]}")
    print(f"strategy    : {strategy_name or 'NONE'}")
    print(f"context leak: {'ok' if doctor_json['context_leak_ok'] else 'UNPROVEN'}")
    print(
        f"identity    : {'LEAK' if identity_leak else 'clean'}  "
        f"mitigation={identity_mitigation or 'none found'}"
    )
    print(f"confounds   : {', '.join(confounds) or 'none'}")
    print(f"guard       : {regression_guard}")
    for rung in identity_probes:
        if not rung.available:
            state = "skip"
        elif rung.status not in PROBE_OK_STATUSES:
            state = "err"
        else:
            state = "leak" if rung.leak else "ok"
        print(
            f"  {state:4}  {rung.name:24} status={rung.status:15} "
            f"markers={','.join(rung.markers) or '-'}"
        )
        for note in rung.notes:
            print(f"          - {note}")
        if rung.evidence:
            print(f"          - reply: {rung.evidence[:200]}")
    print(f"structured  : {structured_field or 'unknown'}")
    print(f"cost (usd)  : {doctor_json['cost_usd_total']}")
    print(f"wrote       : {doctor_path}")
    print("argv template:")
    print(f"  {argv_template}")
    for note in notes:
        print(f"note        : {note}")

    if strategy_name is None:
        leaking = [probe.name for probe in probes if probe.context_leak_ok is False]
        if leaking:
            print(f"doctor: context leaked under {', '.join(leaking)}.")
        print("doctor: no isolation strategy passed; `run` will refuse to execute.")
        return 1
    return 0
