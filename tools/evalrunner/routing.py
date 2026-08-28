"""Routing runner: which skill Claude Code picks for a stated intent.

Two modes answer the same question from different angles. `native` builds a
throwaway project holding every skill's SKILL.md, hands the intent to Claude Code
with its default system prompt and only the `Skill` tool, and watches the stream
for the first `Skill` tool_use — the router under test is the product's own.
`classify` asks one tool-less structured-output call to pick from the list of
`name: description` pairs, which isolates the descriptions from everything else
the native router sees (file layout, skill bodies, the CLI's own built-in skills).

Scoring implements the matrix in `design-eval-runner.md` §5. Fixture lines whose
`expected_skill` names a skill this repo has not built are phantoms: they are
downgraded to a weaker question ("did the owning skill correctly stay out of
it?") rather than dropped, so the corpus keeps its negative signal until the
fixtures are repaired.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import Counter
from itertools import zip_longest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tools import validate_repo

from .cases import CaseLoadError, RoutingCase, skill_dirs
from .claude_cli import ClaudeRequest, ClaudeResult
from .executor import executor_env, sandbox_cwd
from .report import confound_line
from . import cache, workspace

ROOT = workspace.ROOT
PROMPTS = Path(__file__).resolve().parent / "prompts"

MODE_NATIVE = "native"
MODE_CLASSIFY = "classify"
MODES = (MODE_NATIVE, MODE_CLASSIFY)

# Only the router's own decision is under test, so the native run gets exactly one
# tool and a budget that covers a single turn.
ROUTING_TOOLS = "Skill"
ROUTING_BUDGET_USD = 0.15
SKILL_TOOL_NAME = "Skill"
DEFAULT_STRUCTURED_FIELD = "structured_output"

OUTCOME_PASS = "pass"
OUTCOME_AMBIGUOUS = "ambiguous_pass"
OUTCOME_FAIL = "fail"
# A case the run produced no usable answer for. Not a fourth verdict in design
# §5's matrix — an admission that the matrix was never applied, so a silent run
# (no repeats, every call failed, a stream that never named the skill) can never
# be read as a passing negative case.
OUTCOME_UNANSWERED = "unanswered"
OUTCOMES = (OUTCOME_PASS, OUTCOME_AMBIGUOUS, OUTCOME_FAIL, OUTCOME_UNANSWERED)

# The router demonstrably invoked a skill, but the stream never carried its name.
UNNAMED_SKILL = "<unnamed-skill>"

RULE_EXPECTED = "expected"
RULE_NULL = "null"
RULE_SOFT = "soft"
RULE_MUST_NOT_ROUTE = "must_not_route"

# "no skill applies" travels as a sentinel string rather than JSON null: Claude
# Code 2.1.250 validates a required property with a null value as *missing*
# ("must have required property 'choice'"), so a nullable required field costs
# six retries and then `error_max_structured_output_retries` — measured, not
# assumed. `chosen_skill` still maps a literal null back to None, so a build that
# fixes this keeps working.
CLASSIFY_NONE = "none"
NO_SKILL_CHOICES = frozenset({"none", "null", "no skill", "no-skill", "nothing"})

CLASSIFY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "choice": {
            "type": "string",
            "description": f'The chosen skill name, or "{CLASSIFY_NONE}" when no skill applies.',
        },
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["choice", "alternatives", "reason"],
    "additionalProperties": False,
}


class RoutingError(ValueError):
    """A routing project the runner cannot build."""


# ---------------------------------------------------------------------------
# Project build
# ---------------------------------------------------------------------------


def _frontmatter(text: str) -> Dict[str, str]:
    """Frontmatter mapping for a SKILL.md body.

    Same shim as `cases._frontmatter`: `validate_repo` is growing a full
    `parse_frontmatter`, and until it lands the name/description-only
    `frontmatter` is what exists.
    """
    parser = getattr(validate_repo, "parse_frontmatter", None) or validate_repo.frontmatter
    return dict(parser(text) or {})


def _skill_md_at_ref(root: Path, skill: str, ref: str) -> Optional[str]:
    """SKILL.md as committed at `ref`, or None when the skill did not exist then."""
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
        raise RoutingError(f"cannot run git in {root}: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        # A path missing inside a ref that resolves just means the skill is newer
        # than the ref; anything else (an unresolvable ref, no repository) is an
        # operator error and must not be swallowed into a silently smaller ballot.
        if "does not exist in" in stderr:
            return None
        raise RoutingError(f"git show {ref}:{rel} failed: {stderr}")
    return completed.stdout


def build_routing_project(
    run_dir: Path,
    skills_root: Optional[Path] = None,
    descriptions_from: Optional[str] = None,
    extra_skills: Sequence[Path] = (),
    *,
    args: Any = None,
    warnings: Optional[List[str]] = None,
) -> Path:
    """Throwaway project holding every skill's SKILL.md, and nothing else.

    Only SKILL.md is copied: the router decides from name and description, so
    supporting files would only add noise (and reading cost) to the probe. There
    is no CLAUDE.md for the same reason.

    The project is built in a scratch directory outside the repository (see
    `executor.sandbox_cwd`): a cwd inside the repo pulls the operator's
    `~/.claude/CLAUDE.md` into context even under `--setting-sources project`,
    which would put ~100 personal skills next to this repo's on the ballot.
    """
    root_skills = Path(skills_root) if skills_root else ROOT / "skills"
    repo = root_skills.parent
    proj = sandbox_cwd(Path(run_dir), args, leaf="routing")
    target_root = proj / ".claude" / "skills"
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    for skill_dir in skill_dirs(root_skills):
        name = skill_dir.name
        if descriptions_from:
            text = _skill_md_at_ref(repo, name, descriptions_from)
            if text is None:
                if warnings is not None:
                    warnings.append(
                        f"{name}: no skills/{name}/SKILL.md at {descriptions_from}; "
                        "skill left out of the routing project"
                    )
                continue
        else:
            text = skill_dir.joinpath("SKILL.md").read_text(encoding="utf-8")
        target = target_root / name
        target.mkdir(parents=True, exist_ok=True)
        target.joinpath("SKILL.md").write_text(text, encoding="utf-8")

    for extra in extra_skills:
        path = Path(extra)
        source = path / "SKILL.md"
        if not source.is_file():
            raise RoutingError(f"--extra-skill {path}: no SKILL.md there")
        target = target_root / path.name
        target.mkdir(parents=True, exist_ok=True)
        target.joinpath("SKILL.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return proj


def project_descriptions(proj: Path) -> List[Tuple[str, str]]:
    """`(name, description)` for every skill in a built routing project.

    Read back from the project rather than from `skills/` so `classify` votes on
    exactly the ballot `native` sees, including `--extra-skill` additions and
    `--descriptions-from` substitutions.
    """
    skills_root = Path(proj) / ".claude" / "skills"
    if not skills_root.is_dir():
        return []
    pairs: List[Tuple[str, str]] = []
    for skill_dir in sorted(skills_root.iterdir(), key=lambda path: path.name):
        source = skill_dir / "SKILL.md"
        if not source.is_file():
            continue
        meta = _frontmatter(source.read_text(encoding="utf-8"))
        pairs.append((skill_dir.name, str(meta.get("description") or "").strip()))
    return pairs


def descriptions_digest(descriptions: Sequence[Tuple[str, str]]) -> str:
    """Hash of the whole ballot; part of every routing cache key."""
    material = "\n".join(f"{name}: {description}" for name, description in descriptions)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def routing_cache_key(
    *,
    claude_code_version: str,
    mode: str,
    model: str,
    descriptions_sha: str,
    intent: str,
    repeat: int,
) -> str:
    """Cache key for one routing invocation, keyed like an executor run.

    Native routing is the CLI's own router answering, so the CLI version is part
    of the question, not an incidental detail of how it was asked.
    """
    material = cache.key_material(
        kind="routing",
        claude_code_version=claude_code_version,
        mode=mode,
        model=model,
        descriptions_sha=descriptions_sha,
        intent=intent,
        repeat=repeat,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def classify_prompt(descriptions: Sequence[Tuple[str, str]]) -> str:
    """Router system prompt with the ballot appended as `name: description` lines."""
    header = PROMPTS.joinpath("router-classify.md").read_text(encoding="utf-8").strip()
    listing = "\n".join(f"- {name}: {description}" for name, description in descriptions)
    return f"{header}\n\n## Skills\n\n{listing}\n"


def native_request(
    intent: str, proj: Path, args: Any, isolation_flags: Sequence[str] = ()
) -> ClaudeRequest:
    """Claude Code answering the intent for real, with every skill on the ballot.

    No `--system-prompt`: the product's own router prompt is the thing under
    test. `--include-partial-messages` surfaces the tool_use block as soon as the
    model starts emitting it, which is what makes the early kill cheap.
    """
    argv = [
        args.claude_bin,
        "-p",
        intent,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        args.model,
        "--tools",
        ROUTING_TOOLS,
        "--strict-mcp-config",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        str(ROUTING_BUDGET_USD),
        *isolation_flags,
    ]
    return ClaudeRequest(
        argv=argv,
        cwd=Path(proj),
        env=executor_env(args),
        timeout_s=float(getattr(args, "timeout", 180.0)),
    )


def classify_request(
    intent: str,
    descriptions: Sequence[Tuple[str, str]],
    args: Any,
    isolation_flags: Sequence[str] = (),
    cwd: Optional[Path] = None,
) -> ClaudeRequest:
    """Tool-less structured-output call that picks one skill from the ballot."""
    argv = [
        args.claude_bin,
        "-p",
        intent,
        "--output-format",
        "json",
        "--model",
        args.model,
        "--system-prompt",
        classify_prompt(descriptions),
        "--tools",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--json-schema",
        json.dumps(CLASSIFY_SCHEMA, separators=(",", ":")),
        "--max-budget-usd",
        str(ROUTING_BUDGET_USD),
        *isolation_flags,
    ]
    return ClaudeRequest(
        argv=argv,
        cwd=Path(cwd) if cwd is not None else sandbox_cwd(Path("classify"), args, leaf="classify"),
        env=executor_env(args),
        timeout_s=float(getattr(args, "timeout", 180.0)),
    )


# ---------------------------------------------------------------------------
# Reading an answer
# ---------------------------------------------------------------------------


def normalize_skill_name(raw: Any) -> Optional[str]:
    """`plugin:name` and `plugin:sub:name` reduce to the bare skill name."""
    if not isinstance(raw, str):
        return None
    name = raw.strip().split(":")[-1].strip()
    return name or None


def chosen_skill(result: ClaudeResult, *, field: str = DEFAULT_STRUCTURED_FIELD) -> Optional[str]:
    """The skill this result routed to, or None when it routed to nothing.

    Native mode answers with the first `Skill` tool_use that names a skill;
    partial-message streams emit the block twice (an empty `content_block_start`
    then the complete assistant message), so a use with no skill in its input is
    skipped rather than read as "routed to nothing". A stream that carries a
    `Skill` use but never names the skill returns `UNNAMED_SKILL`, which scores
    `unanswered`: the router did route, and only the record of where is missing.
    Classify mode answers with `choice` from the structured output.
    """
    saw_skill_use = False
    for use in result.tool_uses:
        if use.get("name") != SKILL_TOOL_NAME:
            continue
        saw_skill_use = True
        name = normalize_skill_name((use.get("input") or {}).get("skill"))
        if name:
            return name
    if saw_skill_use:
        # The router did route somewhere — reporting None here would score a
        # broken stream as "correctly declined to route".
        return UNNAMED_SKILL

    event = result.result_event or {}
    structured = event.get(field)
    if isinstance(structured, dict):
        choice = normalize_skill_name(structured.get("choice"))
        return None if choice is None or choice.casefold() in NO_SKILL_CHOICES else choice
    return None


def majority(values: Sequence[Optional[str]]) -> Optional[str]:
    """Most common answer across repeats; ties go to whichever came first.

    A tie is a genuine "no majority", and the first answer is the one least
    influenced by the others — it is at least deterministic, which a scorer needs.
    """
    if not values:
        return None
    counts = Counter(values)
    best = max(counts.values())
    for value in values:
        if counts[value] == best:
            return value
    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_case(
    case: RoutingCase,
    chosen_by_repeat: Sequence[Optional[str]],
    *,
    statuses: Sequence[str] = (),
) -> Dict[str, Any]:
    """Verdict for one intent, per design §5's matrix, decided by majority vote.

    Phantom expectations cannot be tested directly — the skill they name does not
    exist — so they fall back to the weaker question the fixture still supports:
    a `soft` phantom accepts "nothing" or the owning skill, and a `must_not_route`
    phantom only asks that the owning skill not absorb the intent.

    `statuses` (one per repeat, when the caller has them) keeps a failed call from
    voting: a call that errored before answering says nothing about the router,
    and counting its silence as "routed to nothing" would turn a broken run into
    a passing negative case. When nothing usable is left to vote — no repeats ran
    at all, every repeat failed, or the router invoked a skill the stream never
    named — the case is `unanswered` and the matrix is not applied: "we did not
    measure this" must never be recorded as pass or fail.
    """
    votes = [
        chosen
        for chosen, status in zip_longest(chosen_by_repeat, statuses, fillvalue="ok")
        if status == "ok" or chosen is not None
    ]
    chosen = majority(votes)
    warnings = [
        f"{case.skill_file}:{case.line_no}: ambiguous_with entry {name!r} names no skill "
        "in this repo; dropped"
        for name in case.phantom_ambiguous
    ]

    if case.phantom_expected and case.soft:
        rule = RULE_SOFT
    elif case.phantom_expected:
        rule = RULE_MUST_NOT_ROUTE
    elif case.expected_skill is None:
        rule = RULE_NULL
    else:
        rule = RULE_EXPECTED

    if not votes:
        outcome = OUTCOME_UNANSWERED
        detail = (
            f"every repeat failed ({', '.join(sorted(set(statuses)))})"
            if statuses
            else "no repeat produced an answer"
        )
        warnings.append(
            f"{case.skill_file}:{case.line_no}: {detail}; scored {OUTCOME_UNANSWERED}, "
            "the routing matrix was not applied"
        )
    elif chosen == UNNAMED_SKILL:
        outcome = OUTCOME_UNANSWERED
        warnings.append(
            f"{case.skill_file}:{case.line_no}: the router invoked a skill but the stream "
            f"never named it; scored {OUTCOME_UNANSWERED}"
        )
    elif rule == RULE_SOFT:
        outcome = OUTCOME_PASS if chosen in (None, case.skill_file) else OUTCOME_FAIL
    elif rule == RULE_MUST_NOT_ROUTE:
        outcome = OUTCOME_FAIL if chosen == case.must_not_route else OUTCOME_PASS
    elif rule == RULE_NULL:
        outcome = OUTCOME_PASS if chosen is None else OUTCOME_FAIL
    elif chosen == case.expected_skill:
        outcome = OUTCOME_PASS
    elif chosen is not None and chosen in case.ambiguous_with:
        outcome = OUTCOME_AMBIGUOUS
    else:
        outcome = OUTCOME_FAIL

    return {
        "skill_file": case.skill_file,
        "line_no": case.line_no,
        "intent": case.intent,
        "expected_skill": case.expected_skill,
        "ambiguous_with": list(case.ambiguous_with),
        "chosen": chosen,
        "chosen_by_repeat": list(chosen_by_repeat),
        "statuses": list(statuses),
        "answered": len(votes),
        "outcome": outcome,
        "rule": rule,
        "phantom": bool(case.phantom_expected),
        "warnings": warnings,
    }


def _empty_counts() -> Dict[str, Any]:
    """Zeroed per-file counters; every outcome has a column so none can hide."""
    return {"cases": 0, "pass": 0, "ambiguous_pass": 0, "fail": 0, "unanswered": 0, "phantom": 0}


def _rate(numerator: int, denominator: int) -> Optional[float]:
    """Share of `denominator` that `numerator` covers, or None when nothing scored."""
    return round(numerator / denominator, 4) if denominator else None


def _add_rates(counts: Dict[str, Any]) -> None:
    """Attach both pass rates to one bucket of outcome counts.

    `pass_rate` is lenient: an intent that landed on a skill the fixture accepts
    as an alternative counts as a pass. `strict_pass_rate` counts only the exact
    expected target, so a skill that survives on ambiguity cannot hide behind the
    lenient number. Unanswered cases are in neither denominator.
    """
    scored = counts["pass"] + counts["ambiguous_pass"] + counts["fail"]
    counts["pass_rate"] = _rate(counts["pass"] + counts["ambiguous_pass"], scored)
    counts["strict_pass_rate"] = _rate(counts["pass"], scored)


def aggregate_routing(
    routing_cases: Sequence[RoutingCase],
    scores: Sequence[Dict[str, Any]],
    *,
    mode: Optional[str] = None,
    repeats: Optional[int] = None,
    run_id: Optional[str] = None,
    extra_warnings: Sequence[str] = (),
) -> Dict[str, Any]:
    """Per-file counts, the confusion list, and who absorbed whose intents.

    `hijacks` counts only outright failures: an intent that landed on a skill the
    fixture accepts as an alternative was not hijacked, it was shared.
    """
    files: Dict[str, Dict[str, Any]] = {}
    totals = {"pass": 0, "ambiguous_pass": 0, "fail": 0, "unanswered": 0, "phantom": 0}
    confusion: List[Dict[str, Any]] = []
    hijacks: Counter = Counter()
    warnings: List[str] = list(extra_warnings)
    phantom_targets: List[str] = []

    for score in scores:
        entry = files.setdefault(score["skill_file"], _empty_counts())
        entry["cases"] += 1
        entry[score["outcome"]] += 1
        totals[score["outcome"]] += 1
        if score["phantom"]:
            entry["phantom"] += 1
            totals["phantom"] += 1
            target = score.get("expected_skill")
            if target and target not in phantom_targets:
                phantom_targets.append(target)
        if score["outcome"] == OUTCOME_FAIL:
            confusion.append(
                {
                    "skill_file": score["skill_file"],
                    "line_no": score["line_no"],
                    "intent": score["intent"],
                    "expected": score["expected_skill"],
                    "chosen": score["chosen"],
                    "rule": score["rule"],
                }
            )
            if score["chosen"]:
                hijacks[score["chosen"]] += 1
        warnings.extend(score.get("warnings") or [])

    for case in routing_cases:
        files.setdefault(case.skill_file, _empty_counts())
    for counts in files.values():
        _add_rates(counts)

    # Unanswered cases are excluded from the denominator: a pass rate must be a
    # share of the cases the run actually measured.
    scored = totals["pass"] + totals["ambiguous_pass"] + totals["fail"]
    unanswered = [
        f"{score['skill_file']}:{score['line_no']}"
        for score in scores
        if score["outcome"] == OUTCOME_UNANSWERED
    ]
    return {
        "run_id": run_id,
        "mode": mode,
        "repeats": repeats,
        "cases": len(scores),
        "totals": totals,
        "unanswered": unanswered,
        "pass_rate": _rate(totals["pass"] + totals["ambiguous_pass"], scored),
        "strict_pass_rate": _rate(totals["pass"], scored),
        "files": files,
        "confusion": confusion,
        "hijacks": dict(hijacks.most_common()),
        "phantom_targets": sorted(phantom_targets),
        "warnings": warnings,
        "scores": list(scores),
    }


def baseline_routing_block(aggregate: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
    """The `routing` section design §7 commits to `evals/baseline.json`."""
    return {
        "run_id": run_id or aggregate.get("run_id"),
        "mode": aggregate.get("mode"),
        "repeats": aggregate.get("repeats"),
        "files": {name: dict(counts) for name, counts in sorted((aggregate.get("files") or {}).items())},
        "phantom_targets": list(aggregate.get("phantom_targets") or []),
    }


# ---------------------------------------------------------------------------
# Selection and export
# ---------------------------------------------------------------------------


def select_routing_cases(
    all_cases: Sequence[RoutingCase], *, skills: Optional[Sequence[str]] = None
) -> List[RoutingCase]:
    """Filter routing cases by the skill file that owns them.

    A selector that names nothing is an error, never "no filter": silently
    widening one skill into the whole corpus is the most expensive mistake this
    CLI can make (`cases.select_cases` refuses the same way).
    """
    picked = list(all_cases)
    if not skills:
        return picked
    wanted = [name for name in skills if name]
    known = {case.skill_file for case in picked}
    missing = [name for name in wanted if name not in known]
    if missing:
        raise CaseLoadError(f"no routing cases for skill(s): {', '.join(missing)}")
    return [case for case in picked if case.skill_file in set(wanted)]


def rewards_answering(case: RoutingCase, skill: str) -> bool:
    """True when this runner's scorer would reward `skill` answering `case`.

    Three ways to earn it: `skill` is the expected target, the fixture accepts
    `skill` as an ambiguous alternative, or the case is a soft phantom owned by
    `skill` (its expected target does not exist, and the owning skill is an
    accepted answer). A `must_not_route` phantom is the opposite and stays False.
    """
    if case.expected_skill is not None and case.expected_skill == skill:
        return True
    if skill in case.ambiguous_with:
        return True
    return case.soft and case.skill_file == skill


def trigger_set(routing_cases: Iterable[RoutingCase], skill: str) -> List[Dict[str, Any]]:
    """Routing intents in skill-creator's trigger-eval shape for one skill.

    A bare `[{"query", "should_trigger"}]` array — the shape
    `imports/anthropic-skill-creator/scripts/run_loop.py` reads. An intent
    another skill owns becomes a near-miss negative, which is exactly the hard
    case a description optimizer needs.
    """
    return [
        {"query": case.intent, "should_trigger": rewards_answering(case, skill)}
        for case in routing_cases
    ]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


# Native mode kills the call the moment the model names a skill, so the CLI
# never emits the `result` event that carries cost. Reported cost is therefore a
# floor, not a measurement.
NATIVE_COST_NOTE = (
    "- Cost note: native mode kills each call as soon as a skill is named, so the "
    "CLI emits no `result` event for it and the figure above is a lower bound."
)

FAILURE_SPLIT_HELP = (
    "Every failing intent lands in exactly one of three buckets, and they call for "
    "different fixes. (a) is a description that never triggered; (b) is two repo "
    "descriptions overlapping; (c) is a repo description losing to a CLI built-in "
    "the operator did not choose to put on the ballot."
)


def failure_split(
    aggregate: Dict[str, Any],
    ballot: Sequence[str],
    builtins: Sequence[str] = (),
) -> Dict[str, List[Dict[str, Any]]]:
    """Failing intents bucketed by who took them, per the routing-report contract.

    `answered_no_skill`: the model answered without invoking anything.
    `hijacked_by_repo_skill`: a skill in this repo absorbed the intent.
    `hijacked_by_builtin`: something outside the repo ballot did — a CLI built-in
    or an unnamed tool call. Anything not on the repo ballot counts here, so a
    name the built-in baseline missed is still reported as foreign, not as ours.
    """
    on_ballot = set(ballot)
    known_builtins = set(builtins)
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "answered_no_skill": [],
        "hijacked_by_repo_skill": [],
        "hijacked_by_builtin": [],
    }
    for row in aggregate.get("confusion") or []:
        chosen = row.get("chosen")
        if not chosen:
            buckets["answered_no_skill"].append(row)
        elif chosen in on_ballot:
            buckets["hijacked_by_repo_skill"].append(row)
        else:
            entry = dict(row)
            entry["known_builtin"] = chosen in known_builtins
            buckets["hijacked_by_builtin"].append(entry)
    return buckets


_SPLIT_TITLES = (
    ("answered_no_skill", "(a) Answered natively with no skill"),
    ("hijacked_by_repo_skill", "(b) Hijacked by a repo skill"),
    ("hijacked_by_builtin", "(c) Hijacked by a built-in or unnamed tool"),
)


def _pct(rate: Optional[float]) -> str:
    """Rate as a whole-percent cell, or `n/a` when nothing was scored."""
    return "n/a" if rate is None else f"{rate * 100:.0f}%"


def render_routing_report(aggregate: Dict[str, Any], run_meta: Dict[str, Any]) -> str:
    """Markdown report for one routing run: header, scorecard, confusion, hijacks."""
    model = run_meta.get("model") or {}
    isolation = run_meta.get("isolation") or {}
    dirty_suffix = " (dirty)" if run_meta.get("dirty") else ""
    files = aggregate.get("files") or {}

    lines: List[str] = []
    run_id = aggregate.get("run_id") or run_meta.get("run_id") or "unknown"
    lines.append(f"# Routing report: {run_id}")
    lines.append("")
    lines.append("## Run")
    lines.append("")
    lines.append(f"- Mode: {aggregate.get('mode') or 'unknown'}")
    lines.append(f"- Repeats: {aggregate.get('repeats') or 1}")
    lines.append(
        f"- Model: {model.get('alias') or 'unknown'} (resolved: {model.get('resolved') or 'unknown'})"
    )
    lines.append(f"- Claude Code version: {run_meta.get('claude_code_version') or 'unknown'}")
    lines.append(f"- Harness version: {run_meta.get('harness_version') or 'unknown'}")
    lines.append(f"- Commit: {run_meta.get('commit') or 'unknown'}{dirty_suffix}")
    lines.append(f"- Date: {run_meta.get('started_at') or 'unknown'}")
    lines.append(f"- Isolation strategy: {isolation.get('strategy') or 'unknown'}")
    confound = confound_line(run_meta)
    if confound:
        lines.append(confound)
    ballot = list(run_meta.get("ballot") or [])
    builtins = list(run_meta.get("builtin_skill_baseline") or [])
    lines.append(
        f"- Skills on the ballot: {run_meta.get('ballot_size') or 'unknown'} repo skill(s)"
        + (
            f", plus the CLI's own built-ins ({len(builtins)} known by name at doctor time)"
            if builtins
            else ""
        )
    )
    lines.append(f"- Cost: ${float(run_meta.get('cost_usd_total') or 0.0):.4f}")
    if aggregate.get("mode") == MODE_NATIVE:
        lines.append(NATIVE_COST_NOTE)
    lines.append("")

    totals = aggregate.get("totals") or {}
    rate = aggregate.get("pass_rate")
    lines.append("## Scorecard")
    lines.append("")
    lines.append(
        "| File | Cases | Pass | Ambiguous | Fail | Unanswered | Phantom | Lenient % | Strict % |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name in sorted(files):
        counts = files[name]
        lines.append(
            f"| {name} | {counts.get('cases', 0)} | {counts.get('pass', 0)} | "
            f"{counts.get('ambiguous_pass', 0)} | {counts.get('fail', 0)} | "
            f"{counts.get('unanswered', 0)} | {counts.get('phantom', 0)} | "
            f"{_pct(counts.get('pass_rate'))} | {_pct(counts.get('strict_pass_rate'))} |"
        )
    if not files:
        lines.append("| (no routing cases in this run) | | | | | | | | |")
    lines.append(
        f"| **total** | {aggregate.get('cases', 0)} | {totals.get('pass', 0)} | "
        f"{totals.get('ambiguous_pass', 0)} | {totals.get('fail', 0)} | "
        f"{totals.get('unanswered', 0)} | {totals.get('phantom', 0)} | "
        f"{_pct(rate)} | {_pct(aggregate.get('strict_pass_rate'))} |"
    )
    lines.append("")
    lines.append(
        f"Pass rate (lenient, pass + ambiguous): {_pct(rate)} · "
        f"strict (exact target only): {_pct(aggregate.get('strict_pass_rate'))}"
    )
    lines.append("")

    lines.append("## Confusion")
    lines.append("")
    confusion = aggregate.get("confusion") or []
    if confusion:
        lines.append("| File | Intent | Expected | Chosen | Rule |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in confusion:
            expected = row.get("expected") or "(none)"
            chosen = row.get("chosen") or "(none)"
            lines.append(
                f"| {row['skill_file']}:{row['line_no']} | {row['intent']} | {expected} | "
                f"{chosen} | {row.get('rule', '')} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Failure split")
    lines.append("")
    lines.append(FAILURE_SPLIT_HELP)
    lines.append("")
    split = failure_split(aggregate, ballot, builtins)
    for bucket, title in _SPLIT_TITLES:
        rows = split[bucket]
        lines.append(f"**{title}: {len(rows)}**")
        lines.append("")
        if rows:
            for row in rows:
                chosen = row.get("chosen") or "(none)"
                suffix = ""
                if bucket == "hijacked_by_builtin" and not row.get("known_builtin"):
                    suffix = " (not in the doctor built-in baseline)"
                lines.append(
                    f"- {row['skill_file']}:{row['line_no']} {row['intent']!r} "
                    f"-> {chosen}{suffix}"
                )
        else:
            lines.append("- none")
        lines.append("")

    lines.append("## Hijacks")
    lines.append("")
    hijacks = aggregate.get("hijacks") or {}
    if hijacks:
        lines.append("| Skill | Intents absorbed |")
        lines.append("| --- | ---: |")
        for name, count in hijacks.items():
            lines.append(f"| {name} | {count} |")
    else:
        lines.append("- none")
    lines.append("")

    unanswered = aggregate.get("unanswered") or []
    if unanswered:
        lines.append("## Unanswered")
        lines.append("")
        lines.append(
            "The run produced no usable answer for these intents, so the routing matrix "
            "was not applied to them; they count in neither the pass nor the fail column."
        )
        lines.append("")
        lines.extend(f"- {item}" for item in unanswered)
        lines.append("")

    lines.append("## Phantom targets")
    lines.append("")
    targets = aggregate.get("phantom_targets") or []
    lines.extend([f"- {name}" for name in targets] if targets else ["- none"])
    lines.append("")

    lines.append("## Warnings")
    lines.append("")
    warnings = aggregate.get("warnings") or []
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- none"])
    lines.append("")

    return "\n".join(lines)
