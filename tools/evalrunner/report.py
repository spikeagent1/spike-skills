"""Markdown rendering for a run's `results.json`, and the committed baseline.

`check_baseline` is imported by `tools/validate_repo.py` (a later task), so this
module stays dependency-free: stdlib only, plus `. workspace` (itself
stdlib-only). No import of `tools.evalrunner.executor` or `.cases` — either one
pulls in `tools.validate_repo`, which would cycle back through this module when
the validator imports `check_baseline`. `CONFIG_WITH_SKILL`/`CONFIG_WITHOUT_SKILL`
are therefore duplicated as local constants rather than imported from `executor`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import workspace

SCHEMA_VERSION = 1
BASELINE_REL = Path("evals") / "baseline.json"

# Duplicated from `executor.py` (see module docstring) — must stay in sync.
CONFIG_WITH_SKILL = "with_skill"
CONFIG_WITHOUT_SKILL = "without_skill"

# The same candidates `tools.validate_repo.eval_files` recognizes, duplicated
# rather than imported so this module stays dependency-free (see module docstring).
CANDIDATE_EVAL_FILES = (
    Path("examples") / "evals.json",
    Path("routing-eval.jsonl"),
)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _pct(skill: Dict[str, Any], config: str) -> str:
    mean = ((skill.get("configs") or {}).get(config) or {}).get("pass_rate", {}).get("mean")
    return f"{mean * 100:.0f}%" if mean is not None else "n/a"


def _flags(skill: Dict[str, Any]) -> str:
    classes = skill.get("classes") or {}
    flags = []
    ungraded = skill.get("ungraded") or 0
    if ungraded > 0:
        # Spelled out, not the bare word "ungraded": a reader scanning the
        # scorecard has to see that assertions were dropped from the
        # denominator, not just that some caveat applies.
        flags.append(f"{ungraded} UNGRADED (excluded from denominator)")
    if classes.get("flaky", 0) > 0:
        flags.append("flaky")
    if classes.get("discriminating", 0) == 0:
        flags.append("no-signal")
    if skill.get("executor_issues"):
        flags.append("exec-issues")
    return ", ".join(flags) if flags else "-"


# Every report carries this: a reader who does not know the harness is text-only
# will read the `non_discriminating` column as a runner defect instead of the
# audit finding it is.
TEXT_ONLY_NOTE = """## How to read these numbers

Every case is answered twice — once with the skill's `SKILL.md` appended to the
executor's system prompt, once without — and a second, blind model grades both
responses against the same assertions. An assertion both configs satisfy is
classified `non_discriminating`: on this harness it measures the model, not the
skill.

The harness is text-only. The executor runs in an empty scratch project with
`Read,Glob,Grep` and nothing else: no calendar, no inbox, no brain, no
connector, no live tool of any kind. So an assertion of the form "no mutation",
"no message sent", "no page written", or "nothing overwritten" is satisfied by
both configs for free — there was nothing reachable to mutate. Those assertions
land in `non_discriminating`, and that is the audit signal this baseline exists
to produce, not a runner bug. A safety assertion that no reachable behavior can
violate does not test the skill; the rewrite has to replace it with one that is
gradeable from text.
"""

CONFOUND_LINE = (
    "- Confound: the CLI injects the operator identity and current date into every config "
    "(identity_leak=true)"
)


def confound_line(run_meta: Dict[str, Any]) -> Optional[str]:
    """Header line for a run whose doctor could not keep the CLI's identity block out.

    The block is identical in every config, so it cannot explain a with/without
    difference -- but a reader comparing runs has to know it was there.
    """
    isolation = run_meta.get("isolation") or {}
    confounds = run_meta.get("confounds") or []
    if isolation.get("identity_leak") or "cli-identity-block" in confounds:
        return CONFOUND_LINE
    return None


def zero_discriminating(results: Dict[str, Any]) -> List[str]:
    """Skills whose eval set separates nothing: no assertion is `discriminating`.

    Their cases cannot detect a regression, so a green run says nothing about
    them. Skills that were not graded at all are excluded — silence there is a
    grading failure, not a measured absence of signal.
    """
    skills = results.get("skills") or {}
    return [
        name
        for name in sorted(skills)
        if (skills[name].get("assertions") or 0) > 0
        and ((skills[name].get("classes") or {}).get("discriminating", 0) == 0)
    ]


def _class_mix(skill: Dict[str, Any]) -> str:
    """`5 broken, 9 non_discriminating`-style summary of one skill's class counts."""
    classes = skill.get("classes") or {}
    parts = [f"{count} {name}" for name, count in sorted(classes.items()) if count]
    return ", ".join(parts) if parts else "no classified assertions"


def render_run_report(results: Dict[str, Any], run_meta: Dict[str, Any]) -> str:
    """Markdown report for one run: header, scorecard, per-skill findings, open issues."""
    skills = results.get("skills") or {}
    executor_model = run_meta.get("executor_model") or {}
    isolation = run_meta.get("isolation") or {}
    dirty_suffix = " (dirty)" if run_meta.get("dirty") else ""

    lines: List[str] = []
    run_id = results.get("run_id") or run_meta.get("run_id") or "unknown"
    lines.append(f"# Eval report: {run_id}")
    lines.append("")
    lines.append("## Run")
    lines.append("")
    lines.append(
        f"- Executor model: {executor_model.get('alias') or 'unknown'} "
        f"(resolved: {executor_model.get('resolved') or 'unknown'})"
    )
    lines.append(f"- Grader model: {run_meta.get('grader_model') or 'unknown'}")
    lines.append(f"- Claude Code version: {run_meta.get('claude_code_version') or 'unknown'}")
    lines.append(
        f"- Harness version: {results.get('harness_version') or run_meta.get('harness_version') or 'unknown'}"
    )
    lines.append(f"- Commit: {run_meta.get('commit') or 'unknown'}{dirty_suffix}")
    lines.append(f"- Date: {run_meta.get('started_at') or results.get('generated_at') or 'unknown'}")
    lines.append(f"- Isolation strategy: {isolation.get('strategy') or 'unknown'}")
    confound = confound_line(run_meta)
    if confound:
        lines.append(confound)
    lines.append(
        f"- Cost: ${float(run_meta.get('cost_usd_total') or 0.0):.4f} attributed / "
        f"${float(run_meta.get('spend_usd_total') or 0.0):.4f} spent this run"
    )
    lines.append("")

    lines.append("## Scorecard")
    lines.append("")
    lines.append("| Skill | Cases | With % | Without % | Delta | Discriminating/Total | Flags |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for name in sorted(skills):
        skill = skills[name]
        delta = skill.get("delta")
        delta_str = f"{delta * 100:+.0f}pp" if delta is not None else "n/a"
        classes = skill.get("classes") or {}
        total = skill.get("assertions") or 0
        lines.append(
            f"| {name} | {skill.get('cases', 0)} | {_pct(skill, CONFIG_WITH_SKILL)} | "
            f"{_pct(skill, CONFIG_WITHOUT_SKILL)} | {delta_str} | "
            f"{classes.get('discriminating', 0)}/{total} | {_flags(skill)} |"
        )
    if not skills:
        lines.append("| (no skills in this run) | | | | | | |")
    lines.append("")

    lines.append(TEXT_ONLY_NOTE)

    lines.append("## Skills with zero discriminating assertions")
    lines.append("")
    blind = zero_discriminating(results)
    if blind:
        lines.append(
            "No assertion in these skills' eval sets separates the with-skill answer "
            "from the without-skill answer, so their cases cannot detect a regression. "
            "Each gets new text-gradeable cases appended in its rewrite batch (existing "
            "cases untouched) and is re-baselined before the rewrite."
        )
        lines.append("")
        for name in blind:
            skill = skills[name]
            lines.append(
                f"- **{name}** — {skill.get('assertions', 0)} assertion(s): {_class_mix(skill)}"
            )
    else:
        lines.append("- none: every skill has at least one discriminating assertion")
    lines.append("")

    lines.append("## Per-skill findings")
    lines.append("")
    evidence_index = {(row["skill"], row.get("label")): row.get("evidence") for row in results.get("rows") or []}
    any_findings = False
    for name in sorted(skills):
        skill = skills[name]
        sections = (
            ("Non-discriminating", skill.get("non_discriminating") or []),
            ("Broken", skill.get("broken") or []),
            ("Harmful", skill.get("harmful") or []),
            ("Flaky", skill.get("flaky") or []),
        )
        if not any(items for _, items in sections):
            continue
        any_findings = True
        lines.append(f"### {name}")
        lines.append("")
        for title, items in sections:
            if not items:
                continue
            lines.append(f"**{title}:**")
            lines.append("")
            for label in items:
                evidence = evidence_index.get((name, label))
                lines.append(f"- {label} — {evidence}" if evidence else f"- {label}")
            lines.append("")
    if not any_findings:
        lines.append("- none")
        lines.append("")

    lines.append("## Structurally unsatisfiable assertions")
    lines.append("")
    unsatisfiable = results.get("structurally_unsatisfiable") or []
    if unsatisfiable:
        lines.append(
            "Assertions that failed in both configs and that the grader's `eval_feedback` "
            "named as unsatisfiable by any response the harness can produce. These are "
            "eval defects, not skill defects; the rewrite fixes the assertion."
        )
        lines.append("")
        lines.append("| Skill | Case | Assertion | Why it cannot be satisfied |")
        lines.append("| --- | --- | --- | --- |")
        for item in sorted(unsatisfiable, key=lambda row: (row["skill"], row["key"])):
            reason = str(item.get("reason") or "").replace("|", "\\|").replace("\n", " ")
            assertion = str(item.get("assertion") or "").replace("|", "\\|")
            lines.append(
                f"| {item['skill']} | {item['key']} (eval-{item['eval_id']}) | "
                f"{assertion} | {reason} |"
            )
    else:
        lines.append("- none flagged by the grader")
    lines.append("")

    lines.append("## Open issues")
    lines.append("")
    issue_lines: List[str] = []
    for name in sorted(skills):
        skill = skills[name]
        ungraded = skill.get("ungraded") or 0
        if ungraded:
            issue_lines.append(f"- {name}: {ungraded} ungraded grading result(s)")
        for kind, count in sorted((skill.get("executor_issues") or {}).items()):
            issue_lines.append(f"- {name}: {count} {kind} executor result(s)")
    lines.extend(issue_lines if issue_lines else ["- none"])
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Baseline read/merge/write/check
# ---------------------------------------------------------------------------


def baseline_path(root: Optional[Path] = None) -> Path:
    """Path to the committed `evals/baseline.json` under `root` (default: the repo)."""
    return Path(root) / BASELINE_REL if root else workspace.ROOT / BASELINE_REL


def load_baseline(root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Parsed `evals/baseline.json`, or None when it has not been committed yet."""
    path = baseline_path(root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(baseline: Dict[str, Any], root: Optional[Path] = None) -> Path:
    """Write `baseline` to `evals/baseline.json`, creating the directory if needed."""
    path = baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def skill_sha256(skill: str, root: Path) -> Optional[str]:
    """sha256 of `skills/<skill>/SKILL.md`, or None when the file is unreadable."""
    path = Path(root) / "skills" / skill / "SKILL.md"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def evals_sha256(skill: str, root: Path) -> Dict[str, str]:
    """Eval file rel path (relative to `skills/<skill>/`) -> sha256, for files that exist."""
    skill_dir = Path(root) / "skills" / skill
    digests: Dict[str, str] = {}
    for rel in CANDIDATE_EVAL_FILES:
        path = skill_dir / rel
        if path.is_file():
            digests[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _condensed_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pass_rate": (config.get("pass_rate") or {}).get("mean"),
        "tokens_mean": (config.get("tokens") or {}).get("mean"),
        "cost_usd": config.get("cost_usd_total"),
    }


def _condense_skill(
    name: str,
    full: Dict[str, Any],
    run_id: Optional[str],
    root: Path,
    source_commit: Optional[str] = None,
) -> Dict[str, Any]:
    """A run's rich per-skill stats, compacted to what `evals/baseline.json` commits.

    `source_commit` is the commit the run measured, kept per entry because the
    top-level `commit` is the tree the merged baseline describes, and a baseline
    is normally assembled from runs taken at several commits.
    """
    configs = full.get("configs") or {}
    entry: Dict[str, Any] = {
        "run_id": run_id,
        "source_commit": source_commit,
        "skill_sha256": skill_sha256(name, root),
        "evals_sha256": evals_sha256(name, root),
        "cases": full.get("cases"),
        "assertions": full.get("assertions"),
        "delta": full.get("delta"),
        "classes": full.get("classes"),
        "non_discriminating": full.get("non_discriminating"),
        "broken": full.get("broken"),
        "harmful": full.get("harmful"),
        "flaky": full.get("flaky"),
        "ungraded": full.get("ungraded"),
        # Additive alongside the count (task 13x fix round 1): lets
        # `analysis.compare` suppress only the ungraded case's own labels
        # instead of every label in the skill. Absent on an entry condensed
        # before this field existed, which `compare` treats as "unknown".
        "ungraded_keys": full.get("ungraded_keys"),
    }
    for cname in (CONFIG_WITH_SKILL, CONFIG_WITHOUT_SKILL):
        if cname in configs:
            entry[cname] = _condensed_config(configs[cname])
    return entry


def merge_baseline(
    existing: Optional[Dict[str, Any]],
    run_results: Dict[str, Any],
    run_meta: Dict[str, Any],
    skills_subset: Optional[Sequence[str]] = None,
    *,
    routing: Optional[Dict[str, Any]] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """New baseline: `existing`'s skills untouched except the ones this run covers.

    `skills_subset` narrows which of `run_results`'s skills are merged in
    (default: all of them); every other skill already in `existing` is carried
    over unchanged. `routing` is optional and tolerated absent; when omitted,
    `existing`'s routing section (if any) is carried over as-is. The top-level
    `commit`/`dirty` describe `root` at merge time; each merged entry records the
    commit its own run measured as `source_commit`.
    """
    root_path = Path(root) if root else workspace.ROOT
    baseline_skills: Dict[str, Any] = dict((existing or {}).get("skills") or {})
    run_skills = run_results.get("skills") or {}
    wanted = set(skills_subset) if skills_subset is not None else set(run_skills)
    run_id = run_results.get("run_id") or run_meta.get("run_id")
    source_commit = run_meta.get("commit")

    for name, full in run_skills.items():
        if name not in wanted:
            continue
        baseline_skills[name] = _condense_skill(name, full, run_id, root_path, source_commit)

    executor_model = run_meta.get("executor_model") or {}
    return {
        "schema_version": (existing or {}).get("schema_version") or SCHEMA_VERSION,
        "harness_version": run_results.get("harness_version") or run_meta.get("harness_version"),
        "generated_at": workspace.utc_iso(),
        # HEAD at merge time, not the source run's: the baseline describes the
        # tree it is committed alongside, and its entries carry `source_commit`.
        "commit": workspace.git_commit_short(root_path),
        "dirty": workspace.git_dirty(root_path),
        "evaluator": {
            "claude_code_version": run_meta.get("claude_code_version"),
            "executor_model": executor_model.get("resolved") or executor_model.get("alias"),
            "grader_model": run_meta.get("grader_model"),
            "load_mode": run_meta.get("load_mode"),
            "system_prompt_mode": run_meta.get("system_prompt_mode"),
            "repeats": run_meta.get("repeats"),
        },
        "skills": baseline_skills,
        "routing": routing if routing is not None else (existing or {}).get("routing"),
    }


def merge_routing_block(
    existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]
) -> Dict[str, Any]:
    """Fold a routing run's block into the committed one, per file.

    A routing run normally covers a subset of the fixtures, and replacing the
    whole block would silently drop every file it did not measure. Files the run
    covers are replaced; the rest are carried over. `phantom_targets` is unioned
    because the carried-over files still name theirs.
    """
    if not isinstance(existing, dict):
        return dict(incoming)
    files: Dict[str, Any] = dict(existing.get("files") or {})
    files.update(incoming.get("files") or {})
    phantom = set(existing.get("phantom_targets") or []) | set(
        incoming.get("phantom_targets") or []
    )
    merged = dict(incoming)
    merged["files"] = files
    merged["phantom_targets"] = sorted(phantom)
    return merged


def check_baseline(baseline: Dict[str, Any], root: Path) -> List[str]:
    """Problems in a committed baseline against the repo on disk; empty means clean.

    Flags a stale `skill_sha256`/`evals_sha256` (the skill or its evals changed
    since the baseline was recorded), a skill with zero discriminating
    assertions, and skills missing an entry in either direction.
    """
    root_path = Path(root)
    problems: List[str] = []
    skills = baseline.get("skills") or {}
    skills_dir = root_path / "skills"
    on_disk = (
        {p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}
        if skills_dir.is_dir()
        else set()
    )

    for name, entry in sorted(skills.items()):
        if name not in on_disk:
            problems.append(f"{name}: baseline entry has no skills/{name} directory on disk")
            continue
        if entry.get("skill_sha256") != skill_sha256(name, root_path):
            problems.append(f"{name}: skill_sha256 is stale (SKILL.md changed since the baseline)")
        if entry.get("evals_sha256") != evals_sha256(name, root_path):
            problems.append(f"{name}: evals_sha256 is stale (eval files changed since the baseline)")
        classes = entry.get("classes") or {}
        if classes.get("discriminating", 0) == 0:
            problems.append(f"{name}: zero discriminating assertions in the baseline")

    for name in sorted(on_disk - set(skills)):
        problems.append(f"{name}: no baseline entry")

    problems.extend(_check_routing(baseline.get("routing"), skills_dir, on_disk))
    return problems


def routing_case_count(path: Path) -> Optional[int]:
    """Data lines in a `routing-eval.jsonl`, or None when there is no such file.

    Comment and blank lines are stripped the same way `cases._routing_lines`
    strips them; the count is duplicated here rather than imported so this module
    stays dependency-free (see the module docstring).
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    return sum(
        1 for raw in text.splitlines() if raw.strip() and not raw.strip().startswith("//")
    )


def _check_routing(
    section: Any, skills_dir: Path, on_disk: Sequence[str]
) -> List[str]:
    """Problems in a baseline's `routing` section; empty when it has none or is absent.

    A baseline recorded before the routing runner existed has no routing section
    at all, which is not a problem — only a section that disagrees with the
    fixtures on disk is.
    """
    if not isinstance(section, dict):
        return []
    problems: List[str] = []
    files = section.get("files") or {}
    present = set(on_disk)

    for name, entry in sorted(files.items()):
        if name not in present:
            problems.append(f"{name}: baseline routing entry has no skills/{name} directory on disk")
            continue
        fixture_cases = routing_case_count(skills_dir / name / "routing-eval.jsonl")
        if fixture_cases is None:
            problems.append(
                f"{name}: baseline routing entry but no skills/{name}/routing-eval.jsonl on disk"
            )
        elif int((entry or {}).get("cases") or 0) != fixture_cases:
            problems.append(
                f"{name}: routing case count is stale (baseline "
                f"{(entry or {}).get('cases')}, fixture {fixture_cases})"
            )

    for name in sorted(present - set(files)):
        if (skills_dir / name / "routing-eval.jsonl").is_file():
            problems.append(f"{name}: has routing-eval.jsonl but no baseline routing entry")

    return problems
