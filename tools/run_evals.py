#!/usr/bin/env python3
"""Eval runner CLI for spike-skills.

`doctor` probes isolation, `run` executes behavioral cases in paired configs and
grades them, `grade` re-grades an existing run directory, and `routing` measures
which skill the router picks for each intent. `compare`, `report`, and `baseline`
read what those wrote.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evalrunner import (  # noqa: E402
    HARNESS_VERSION,
    analysis,
    cache,
    cases,
    doctor,
    executor,
    grader,
    report,
    routing,
    workspace,
)
from tools.evalrunner.claude_cli import (  # noqa: E402
    ClaudeRequest,
    SubprocessClaudeRunner,
    strategy_flags,
    strategy_names,
)

DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_S = 180.0
DEFAULT_PROBE_BUDGET_USD = 0.05
DEFAULT_RUN_BUDGET_USD = 0.50
DEFAULT_WORKERS = 4
DEFAULT_ROUTING_REPEATS = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_evals.py", description="Behavioral and routing eval runner."
    )
    parser.add_argument("--version", action="version", version=f"harness {HARNESS_VERSION}")
    parser.add_argument(
        "--claude-bin", default="claude", help="Path to the Claude Code CLI (default: claude)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Probe auth, isolation, and structured output; write doctor.json."
    )
    doctor_parser.add_argument("--model", default=DEFAULT_MODEL)
    doctor_parser.add_argument(
        "--strategy", default="auto", choices=["auto", *strategy_names()],
        help="Probe only this isolation strategy instead of all of them in order.",
    )
    doctor_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    doctor_parser.add_argument(
        "--max-budget-usd", type=float, default=DEFAULT_PROBE_BUDGET_USD,
        help="Per-probe spend cap (default: 0.05).",
    )
    doctor_parser.set_defaults(handler=doctor.run_doctor)

    run_parser = subparsers.add_parser(
        "run", help="Execute behavioral cases in each config and grade the responses."
    )
    selection = run_parser.add_argument_group("case selection")
    selection.add_argument("--skill", help="Comma-separated skill names.")
    selection.add_argument("--cohort", help="Cohort name from catalog/cohorts.yaml.")
    selection.add_argument(
        "--case", action="append", default=[],
        help="A single case as skill:id (repeatable).",
    )
    selection.add_argument("--all", action="store_true", help="Every case in the repo.")
    selection.add_argument("--limit", type=int, help="Keep at most N cases.")
    selection.add_argument("--sample", type=int, help="Randomly sample N cases.")
    selection.add_argument("--seed", type=int, default=0, help="Seed for --sample (default: 0).")
    run_parser.add_argument("--model", default=DEFAULT_MODEL, help="Executor model.")
    run_parser.add_argument("--grader-model", help="Grader model (default: the executor model).")
    run_parser.add_argument(
        "--configs", default=",".join(executor.DEFAULT_CONFIGS),
        help="Comma-separated configs: with_skill, without_skill, old_skill@<git-ref>.",
    )
    run_parser.add_argument("--load-mode", default="forced", choices=["forced", "discover"])
    run_parser.add_argument(
        "--system-prompt-mode", default="minimal", choices=["minimal", "claude-code"]
    )
    run_parser.add_argument("--repeats", type=int, default=1)
    run_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    run_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    run_parser.add_argument(
        "--max-budget-usd", type=float, default=DEFAULT_RUN_BUDGET_USD,
        help="Per-executor-call spend cap (default: 0.50).",
    )
    run_parser.add_argument("--no-cache", action="store_true")
    run_parser.add_argument(
        "--refresh-config", action="append", default=[],
        help="Ignore cached results for this config (repeatable).",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Write request.json only.")
    run_parser.add_argument("--label", help="Suffix for the run id.")
    run_parser.add_argument(
        "--compare-baseline", action="store_true",
        help="Compare this run's results.json against the committed evals/baseline.json.",
    )
    run_parser.add_argument(
        "--fail-on-regression", action="store_true",
        help="Exit 1 when --compare-baseline finds a regression (implies --compare-baseline).",
    )
    run_parser.set_defaults(handler=cmd_run)

    grade_parser = subparsers.add_parser(
        "grade", help="Grade (or re-grade) the runs in an existing run directory."
    )
    grade_parser.add_argument("--run", required=True, help="Run id under evals/workspaces/runs/.")
    grade_parser.add_argument("--grader-model", default=DEFAULT_MODEL)
    grade_parser.add_argument("--model", default=DEFAULT_MODEL)
    grade_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    grade_parser.add_argument("--no-cache", action="store_true")
    grade_parser.add_argument(
        "--regrade", action="store_true", help="Re-grade runs that already have a grading.json."
    )
    grade_parser.set_defaults(handler=cmd_grade)

    compare_parser = subparsers.add_parser(
        "compare", help="Diff two runs (or a run against the committed baseline)."
    )
    compare_parser.add_argument(
        "--a", required=True, help="RUN_ID, or the literal 'baseline' for evals/baseline.json."
    )
    compare_parser.add_argument("--b", required=True, help="RUN_ID.")
    compare_parser.add_argument("--skill", help="Comma-separated skill names to restrict to.")
    compare_parser.add_argument(
        "--fail-on-regression", action="store_true", help="Exit 1 when any assertion regressed."
    )
    compare_parser.set_defaults(handler=cmd_compare)

    report_parser = subparsers.add_parser("report", help="Render a run's Markdown report.")
    report_parser.add_argument("--run", required=True, help="Run id under evals/workspaces/runs/.")
    report_parser.add_argument("--out", help="Write the report here instead of stdout.")
    report_parser.set_defaults(handler=cmd_report)

    baseline_parser = subparsers.add_parser("baseline", help="Read, update, or check evals/baseline.json.")
    baseline_sub = baseline_parser.add_subparsers(dest="baseline_command", required=True)

    baseline_update = baseline_sub.add_parser("update", help="Merge a run's results into the baseline.")
    baseline_update.add_argument(
        "--from", dest="from_run",
        help="Behavioral run id to merge in; optional when only --routing-from is given.",
    )
    baseline_update.add_argument(
        "--routing-from", help="Routing run id whose results.json fills the baseline's routing block.",
    )
    baseline_update.add_argument(
        "--require-clean", action="store_true", help="Refuse when the source run was recorded dirty."
    )
    baseline_update.set_defaults(handler=cmd_baseline_update)

    baseline_check = baseline_sub.add_parser("check", help="Report staleness against the repo on disk.")
    baseline_check.set_defaults(handler=cmd_baseline_check)

    routing_parser = subparsers.add_parser(
        "routing", help="Measure which skill the router picks for each routing intent."
    )
    routing_parser.add_argument("--skill", help="Comma-separated skill names (the file that owns the intents).")
    routing_parser.add_argument("--all", action="store_true", help="Every routing intent in the repo.")
    routing_parser.add_argument("--model", default=DEFAULT_MODEL)
    routing_parser.add_argument(
        "--mode", default=routing.MODE_NATIVE, choices=list(routing.MODES),
        help="native: Claude Code picks with every skill installed. classify: one tool-less call over the descriptions.",
    )
    routing_parser.add_argument("--repeats", type=int, default=DEFAULT_ROUTING_REPEATS)
    routing_parser.add_argument(
        "--descriptions-from", help="Build the ballot from the SKILL.md files committed at this git ref."
    )
    routing_parser.add_argument(
        "--extra-skill", action="append", default=[],
        help="Path to a skill directory to add to the ballot (repeatable).",
    )
    routing_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    routing_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    routing_parser.add_argument("--no-cache", action="store_true")
    routing_parser.add_argument("--dry-run", action="store_true", help="Write request.json only.")
    routing_parser.add_argument("--label", help="Suffix for the run id.")
    routing_parser.set_defaults(handler=cmd_routing)

    export_parser = subparsers.add_parser(
        "export-trigger-set",
        help="Write one skill's routing intents in skill-creator's trigger-eval format.",
    )
    export_parser.add_argument("--skill", required=True, help="Skill whose routing-eval.jsonl to export.")
    export_parser.add_argument("--out", required=True, help="Destination JSON file.")
    export_parser.set_defaults(handler=cmd_export_trigger_set)

    return parser


def _bad_repeats(command: str, repeats: int) -> bool:
    """True (after printing why) when `--repeats` would run nothing at all.

    `range(1, repeats + 1)` is empty for anything below 1, which would produce a
    complete-looking results.json — scored from no answers — without a single API
    call. A run that measures nothing must fail loudly, not report.
    """
    if repeats >= 1:
        return False
    print(
        f"run_evals.py {command}: --repeats must be at least 1 (got {repeats}); "
        "a run with no repeats measures nothing",
        file=sys.stderr,
    )
    return True


def load_doctor(claude_bin: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validated `doctor.json`, or a message explaining why `run` must refuse.

    An eval run that cannot prove its isolation is worse than no run: it silently
    measures the operator's ~100 personal skills, or their private memory files,
    instead of this repo's skills.
    """
    path = workspace.WORKSPACE / "doctor.json"
    if not path.is_file():
        return None, f"{path} is missing; run `python3 tools/run_evals.py doctor` first"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{path} is unreadable: {exc}"
    if not payload.get("strategy"):
        return None, f"{path} records no working isolation strategy; re-run `doctor`"
    if "context_leak_ok" not in payload:
        return None, (
            f"{path} predates the context-leak probe and cannot prove the operator's "
            "memory files stay out of the run; re-run `doctor`"
        )
    if payload.get("context_leak_ok") is not True:
        return None, (
            f"{path} records a context leak (context_leak_ok: false): the chosen strategy "
            "let foreign memory into the model's context; fix the isolation and re-run `doctor`"
        )
    installed = workspace.claude_version(claude_bin)
    recorded = payload.get("claude_code_version")
    if installed != recorded:
        return None, (
            f"{path} was written for Claude Code {recorded} but {claude_bin} is {installed}; "
            "re-run `doctor`"
        )
    return payload, None


def _resolve_skills(args: argparse.Namespace) -> Optional[List[str]]:
    """Skill filter from `--skill` and `--cohort`, or None when neither was given.

    A selector that was given but names nothing is an error, never "no filter":
    `catalog/cohorts.yaml` ships queued cohorts with `skills: []`, and falling
    through to None would silently widen a one-cohort request into the whole
    corpus — the largest blast radius the CLI has.
    """
    skill = getattr(args, "skill", None)
    cohort = getattr(args, "cohort", None)
    # `is None` and not truthiness: `--skill ""` was given and names nothing, which
    # is an error, while an absent flag is the legitimate "no filter" case.
    if skill is None and cohort is None:
        return None

    names: List[str] = []
    if skill:
        names.extend(name.strip() for name in skill.split(",") if name.strip())
    if cohort:
        names.extend(cases.cohort_skills(cohort))
    if not names:
        given = " ".join(
            part
            for part in (
                f"--skill {skill!r}" if skill is not None else "",
                f"--cohort {cohort!r}" if cohort is not None else "",
            )
            if part
        )
        raise cases.CaseLoadError(f"{given} names no skills; refusing to run every case")
    return names


def _parse_configs(raw: str) -> List[str]:
    configs = [name.strip() for name in raw.split(",") if name.strip()]
    if not configs:
        raise cases.CaseLoadError("--configs is empty")
    for config in configs:
        if config in executor.DEFAULT_CONFIGS or config.startswith(executor.OLD_SKILL_PREFIX):
            continue
        raise cases.CaseLoadError(f"unknown config {config!r}")
    return configs


def _run_dir_for(root: Path, case: cases.BehavioralCase, config: str, repeat: int) -> Path:
    return (
        root
        / case.skill
        / f"eval-{case.eval_id}"
        / executor.config_dirname(config)
        / f"run-{repeat}"
    )


def _write_run_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> int:
    """Execute and grade the selected cases; returns the process exit code."""
    if args.load_mode == "discover":
        print("run_evals.py run --load-mode discover: not implemented in this build", file=sys.stderr)
        return 2
    if not (args.skill or args.cohort or args.case or args.all):
        print("run_evals.py run: choose --skill, --cohort, --case, or --all", file=sys.stderr)
        return 2
    if _bad_repeats("run", args.repeats):
        return 2

    doctor_json, problem = load_doctor(args.claude_bin)
    if doctor_json is None:
        print(f"run_evals.py run: {problem}", file=sys.stderr)
        return 2

    try:
        configs = _parse_configs(args.configs)
        skill_filter = _resolve_skills(args)
        selected = cases.select_cases(
            cases.load_behavioral_cases(),
            skills=skill_filter,
            case_ids=args.case or None,
            limit=args.limit,
            sample=args.sample,
            seed=args.seed,
        )
    except cases.CaseLoadError as exc:
        print(f"run_evals.py run: {exc}", file=sys.stderr)
        return 2
    if not selected:
        print("run_evals.py run: no cases selected", file=sys.stderr)
        return 2

    args.grader_model = args.grader_model or args.model
    args.isolation_strategy = doctor_json["strategy"]
    args.claude_code_version = doctor_json["claude_code_version"]
    args.structured_output_field = doctor_json.get("structured_output_field")
    args.repo_root = None
    isolation_flags = strategy_flags(args.isolation_strategy, workspace.WORKSPACE)

    ws = workspace.ensure_dirs()
    run_id = workspace.make_run_id(args.label)
    run_root = ws / "runs" / run_id
    run_json_path = run_root / "run.json"
    run_json: Dict[str, Any] = {
        "run_id": run_id,
        "harness_version": HARNESS_VERSION,
        "claude_code_version": doctor_json["claude_code_version"],
        "executor_model": {"alias": args.model, "resolved": None},
        "grader_model": args.grader_model,
        "commit": workspace.git_commit_short(),
        "dirty": workspace.git_dirty(),
        "started_at": workspace.utc_iso(),
        "finished_at": None,
        "argv": list(sys.argv),
        "isolation": {
            "strategy": args.isolation_strategy,
            "flags": isolation_flags,
            "doctor_checked_at": doctor_json.get("checked_at"),
            "context_leak_ok": doctor_json.get("context_leak_ok"),
            # Carried from `doctor.json`: a CLI-injected identity signal is a
            # cross-config confound every reader of this run has to know about.
            "identity_leak": doctor_json.get("identity_leak"),
            "identity_mitigation": doctor_json.get("identity_mitigation"),
        },
        "confounds": list(doctor_json.get("confounds") or []),
        "load_mode": args.load_mode,
        "system_prompt_mode": args.system_prompt_mode,
        "configs": configs,
        "repeats": args.repeats,
        "filters": {
            "skill": args.skill,
            "cohort": args.cohort,
            "case": args.case,
            "all": args.all,
            "limit": args.limit,
            "sample": args.sample,
            "seed": args.seed,
        },
        "cases": len(selected),
        "dry_run": args.dry_run,
        "cost_usd_total": 0.0,
        "spend_usd_total": 0.0,
        # `SubprocessClaudeRunner.run()` returns only the last attempt's result, so a
        # rate-limited attempt that was retried contributes no cost here.
        "cost_usd_total_note": "lower bound: cost from retried attempts is not visible",
    }
    _write_run_json(run_json_path, run_json)

    for case in selected:
        executor.write_eval_metadata(run_root / case.skill / f"eval-{case.eval_id}", case)

    jobs = [
        (case, config, repeat)
        for case in selected
        for config in configs
        for repeat in range(1, args.repeats + 1)
    ]

    if args.dry_run:
        for case, config, repeat in jobs:
            run_dir = _run_dir_for(run_root, case, config, repeat)
            try:
                req = executor.build_request(case, config, args, isolation_flags, run_dir)
            except executor.ConfigError as exc:
                print(f"run_evals.py run: {exc}", file=sys.stderr)
                return 2
            executor.write_request_json_at(run_dir, req)
        run_json["finished_at"] = workspace.utc_iso()
        _write_run_json(run_json_path, run_json)
        print(f"run id     : {run_id}")
        print(f"dry run    : wrote {len(jobs)} request.json under {run_root}")
        return 0

    runner = SubprocessClaudeRunner(args.claude_bin)
    store = cache.Cache(enabled=not args.no_cache, refresh_configs=args.refresh_config)
    outcomes: List[Dict[str, Any]] = []

    def work(job: Tuple[cases.BehavioralCase, str, int]) -> Dict[str, Any]:
        # One broken case must not abandon the rest of the run; record it and move on.
        try:
            return _execute_and_grade(job, run_root, args, isolation_flags, runner, store)
        except Exception as exc:  # noqa: BLE001 - a worker never takes the run down.
            case, config, repeat = job
            print(f"  {case.key}: {config}: {exc}", file=sys.stderr)
            return {
                "key": case.key,
                "config": config,
                "repeat": repeat,
                "status": "harness_error",
                "grading_status": "not_run",
                "passed": 0,
                "total": len(case.assertions),
                "cost_usd": 0.0,
                "spend_usd": 0.0,
                "cached": False,
                "resolved_model": None,
            }

    # Grouped by skill (jobs are already in skill order) so consecutive calls reuse the
    # same prompt cache; grading runs inside the worker, so it overlaps other executions.
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for outcome in pool.map(work, jobs):
            outcomes.append(outcome)
            print(
                f"  {outcome['key']:38} {outcome['config']:26} "
                f"exec={outcome['status']:15} grade={outcome['grading_status']:13} "
                f"{outcome['passed']}/{outcome['total']}  ${outcome['cost_usd']:.4f}"
                + ("  (cached)" if outcome["cached"] else "")
            )

    resolved = next((o["resolved_model"] for o in outcomes if o.get("resolved_model")), None)
    run_json["executor_model"]["resolved"] = resolved
    run_json["finished_at"] = workspace.utc_iso()
    run_json["cost_usd_total"] = round(sum(o["cost_usd"] for o in outcomes), 6)
    run_json["spend_usd_total"] = round(sum(o.get("spend_usd", 0.0) for o in outcomes), 6)
    run_json["cache_hits"] = store.hits
    run_json["runs"] = len(outcomes)
    _write_run_json(run_json_path, run_json)

    graded = [o for o in outcomes if o["grading_status"] == grader.STATUS_OK]
    print(f"run id     : {run_id}")
    print(f"runs       : {len(outcomes)} ({store.hits} cache hits)")
    print(f"graded     : {len(graded)}/{len(outcomes)}")
    for config in configs:
        rows = [o for o in graded if o["config"] == config]
        total = sum(o["total"] for o in rows)
        passed = sum(o["passed"] for o in rows)
        rate = f"{passed / total:.0%}" if total else "n/a"
        print(f"  {config:26} {passed}/{total} assertions passed ({rate})")
    print(f"cost (usd) : {run_json['cost_usd_total']} attributed "
          f"/ {run_json['spend_usd_total']} spent this run (lower bound)")

    results = analysis.aggregate_run(run_root)
    (run_root / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (run_root / "report.md").write_text(report.render_run_report(results, run_json), encoding="utf-8")
    print(f"wrote      : {run_root} (results.json, report.md)")

    exit_code = 0
    if args.compare_baseline or args.fail_on_regression:
        baseline = report.load_baseline()
        if baseline is None:
            print("compare-baseline: no committed evals/baseline.json; skipping comparison")
        else:
            comparison = analysis.compare(baseline, results, skills=skill_filter)
            _print_compare(comparison, label_a="baseline", label_b=run_id)
            if args.fail_on_regression and comparison["regressions"] > 0:
                exit_code = 1
    return exit_code


def _execute_and_grade(
    job: Tuple[cases.BehavioralCase, str, int],
    run_root: Path,
    args: argparse.Namespace,
    isolation_flags: Sequence[str],
    runner: SubprocessClaudeRunner,
    store: cache.Cache,
) -> Dict[str, Any]:
    """Run one (case, config, repeat), grade it, and summarize what happened."""
    case, config, repeat = job
    run_dir = _run_dir_for(run_root, case, config, repeat)
    req = executor.build_request(case, config, args, list(isolation_flags), run_dir)

    body = executor.skill_body(config, case.skill, executor.repo_root(args))
    exec_key = cache.executor_key(
        claude_code_version=args.claude_code_version,
        mode=config,
        model=args.model,
        system_prompt=executor.minimal_system_prompt()
        if args.system_prompt_mode != "claude-code"
        else "",
        skill_body=body,
        tools=executor.EXECUTOR_TOOLS,
        prompt=case.prompt,
        repeat=repeat,
    )
    cached = store.get(exec_key, config=config)
    from_cache = cached is not None
    exec_spend = 0.0
    if cached is not None:
        result = executor.result_from_json(cached)
        executor.write_request_json_at(run_dir, req)
        executor.persist_result(run_dir, req, result)
    else:
        result = executor.execute_case(runner, req, run_dir)
        exec_spend = result.cost_usd
        if result.status == "ok":
            store.put(exec_key, executor.result_to_json(result))

    grade_key = cache.grader_key(
        claude_code_version=args.claude_code_version,
        grader_model=args.grader_model,
        grader_prompt=grader.grader_prompt(),
        assertions=case.assertions,
        expected_output=case.expected_output,
        response=result.text,
    )
    cached_grade = store.get(grade_key, config=config) if result.text.strip() else None
    grade_spend = 0.0
    if cached_grade is not None:
        grading = cached_grade
        grader.write_grading(run_dir, grading)
    else:
        grading = grader.grade_run(runner, run_dir, case, args, isolation_flags)
        grade_spend = float(grading.get("grader_cost_usd") or 0.0)
        if grading.get("status") == grader.STATUS_OK:
            store.put(grade_key, grading)

    summary = grading.get("summary") or {}
    return {
        "key": case.key,
        "config": config,
        "repeat": repeat,
        "status": result.status,
        "grading_status": grading.get("status", "unknown"),
        "passed": int(summary.get("passed") or 0),
        "total": int(summary.get("total") or 0),
        # `cost_usd` is what this case cost to produce (replayed from cache or not),
        # which is what per-skill reporting wants; `spend_usd` is what this run
        # actually billed, which is what a budget check wants.
        "cost_usd": result.cost_usd + float(grading.get("grader_cost_usd") or 0.0),
        "spend_usd": exec_spend + grade_spend,
        "cached": from_cache,
        "resolved_model": executor.resolved_model(result),
    }


def _routing_run_dir(root: Path, case: cases.RoutingCase, repeat: int) -> Path:
    """Artifacts for one (intent, repeat).

    The directory is named after the fixture line the intent came from, so a
    confusion-list row can be traced back to `routing-eval.jsonl` by line number.
    """
    return root / case.skill_file / f"intent-{case.line_no}" / f"run-{repeat}"


def _write_intent_metadata(intent_dir: Path, case: cases.RoutingCase) -> None:
    intent_dir.mkdir(parents=True, exist_ok=True)
    (intent_dir / "intent_metadata.json").write_text(
        json.dumps(
            {
                "skill_file": case.skill_file,
                "line_no": case.line_no,
                "intent": case.intent,
                "expected_skill": case.expected_skill,
                "ambiguous_with": case.ambiguous_with,
                "phantom_expected": case.phantom_expected,
                "phantom_ambiguous": case.phantom_ambiguous,
                "must_not_route": case.must_not_route,
                "soft": case.soft,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _routing_request(
    case: cases.RoutingCase,
    args: argparse.Namespace,
    isolation_flags: Sequence[str],
    proj: Path,
    descriptions: Sequence[Tuple[str, str]],
) -> ClaudeRequest:
    """The invocation this mode makes for one intent."""
    if args.mode == routing.MODE_CLASSIFY:
        return routing.classify_request(case.intent, descriptions, args, list(isolation_flags), proj)
    return routing.native_request(case.intent, proj, args, list(isolation_flags))


def cmd_routing(args: argparse.Namespace) -> int:
    """Run every selected routing intent in one mode and score the answers."""
    if not (args.skill or args.all):
        print("run_evals.py routing: choose --skill or --all", file=sys.stderr)
        return 2
    if _bad_repeats("routing", args.repeats):
        return 2

    doctor_json, problem = load_doctor(args.claude_bin)
    if doctor_json is None:
        print(f"run_evals.py routing: {problem}", file=sys.stderr)
        return 2

    try:
        skill_filter = _resolve_skills(args)
        selected = routing.select_routing_cases(cases.load_routing_cases(), skills=skill_filter)
    except cases.CaseLoadError as exc:
        print(f"run_evals.py routing: {exc}", file=sys.stderr)
        return 2
    if not selected:
        print("run_evals.py routing: no routing cases selected", file=sys.stderr)
        return 2

    args.isolation_strategy = doctor_json["strategy"]
    args.claude_code_version = doctor_json["claude_code_version"]
    args.structured_output_field = doctor_json.get("structured_output_field")
    args.repo_root = None
    isolation_flags = strategy_flags(args.isolation_strategy, workspace.WORKSPACE)

    ws = workspace.ensure_dirs()
    run_id = workspace.make_run_id(args.label)
    run_root = ws / "routing" / run_id

    warnings: List[str] = []
    try:
        proj = routing.build_routing_project(
            run_root,
            cases.SKILLS,
            args.descriptions_from,
            [Path(path) for path in args.extra_skill],
            args=args,
            warnings=warnings,
        )
    except (routing.RoutingError, OSError) as exc:
        print(f"run_evals.py routing: {exc}", file=sys.stderr)
        return 2
    descriptions = routing.project_descriptions(proj)
    digest = routing.descriptions_digest(descriptions)

    run_json: Dict[str, Any] = {
        "run_id": run_id,
        "harness_version": HARNESS_VERSION,
        "claude_code_version": doctor_json["claude_code_version"],
        "model": {"alias": args.model, "resolved": None},
        "commit": workspace.git_commit_short(),
        "dirty": workspace.git_dirty(),
        "started_at": workspace.utc_iso(),
        "finished_at": None,
        "argv": list(sys.argv),
        "isolation": {
            "strategy": args.isolation_strategy,
            "flags": isolation_flags,
            "doctor_checked_at": doctor_json.get("checked_at"),
            "context_leak_ok": doctor_json.get("context_leak_ok"),
            # Carried from `doctor.json`: a CLI-injected identity signal is a
            # cross-config confound every reader of this run has to know about.
            "identity_leak": doctor_json.get("identity_leak"),
            "identity_mitigation": doctor_json.get("identity_mitigation"),
        },
        "confounds": list(doctor_json.get("confounds") or []),
        "mode": args.mode,
        "repeats": args.repeats,
        "project_dir": str(proj),
        "ballot_size": len(descriptions),
        # The names on the ballot, so a report can tell a repo skill absorbing an
        # intent apart from a CLI built-in doing it.
        "ballot": [name for name, _ in descriptions],
        "builtin_skill_baseline": list(doctor_json.get("builtin_skill_baseline") or []),
        "descriptions_sha256": digest,
        "descriptions_from": args.descriptions_from,
        "extra_skills": list(args.extra_skill),
        "filters": {"skill": args.skill, "all": args.all},
        "cases": len(selected),
        "dry_run": args.dry_run,
        "cost_usd_total": 0.0,
    }
    _write_run_json(run_root / "run.json", run_json)
    for case in selected:
        _write_intent_metadata(run_root / case.skill_file / f"intent-{case.line_no}", case)

    jobs = [(case, repeat) for case in selected for repeat in range(1, args.repeats + 1)]

    if args.dry_run:
        for case, repeat in jobs:
            run_dir = _routing_run_dir(run_root, case, repeat)
            req = _routing_request(case, args, isolation_flags, proj, descriptions)
            executor.write_request_json_at(run_dir, req)
        run_json["finished_at"] = workspace.utc_iso()
        _write_run_json(run_root / "run.json", run_json)
        print(f"run id     : {run_id}")
        print(f"project    : {proj} ({len(descriptions)} skills on the ballot)")
        print(f"dry run    : wrote {len(jobs)} request.json under {run_root}")
        return 0

    runner = SubprocessClaudeRunner(args.claude_bin)
    store = cache.Cache(enabled=not args.no_cache)

    def work(job: Tuple[cases.RoutingCase, int]) -> Dict[str, Any]:
        # One failed intent must not abandon the run; record it and keep going.
        case, repeat = job
        try:
            return _route_one(
                job, run_root, args, isolation_flags, proj, descriptions, digest, runner, store
            )
        except Exception as exc:  # noqa: BLE001 - a worker never takes the run down.
            print(f"  {case.skill_file}:{case.line_no}: {exc}", file=sys.stderr)
            return {
                "skill_file": case.skill_file,
                "line_no": case.line_no,
                "repeat": repeat,
                "chosen": None,
                "status": "harness_error",
                "cost_usd": 0.0,
                "cached": False,
                "resolved_model": None,
            }

    outcomes: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for outcome in pool.map(work, jobs):
            outcomes.append(outcome)
            print(
                f"  {outcome['skill_file']}:{outcome['line_no']:<4} run-{outcome['repeat']} "
                f"{outcome['status']:15} chose={outcome['chosen'] or '(none)':30} "
                f"${outcome['cost_usd']:.4f}" + ("  (cached)" if outcome["cached"] else "")
            )

    by_case: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for outcome in sorted(outcomes, key=lambda row: row["repeat"]):
        by_case.setdefault((outcome["skill_file"], outcome["line_no"]), []).append(outcome)
    scores = []
    for case in selected:
        repeats = by_case.get((case.skill_file, case.line_no), [])
        scores.append(
            routing.score_case(
                case,
                [row["chosen"] for row in repeats],
                statuses=[row["status"] for row in repeats],
            )
        )
    aggregate = routing.aggregate_routing(
        selected, scores, mode=args.mode, repeats=args.repeats, run_id=run_id,
        extra_warnings=warnings,
    )

    resolved = next((o["resolved_model"] for o in outcomes if o.get("resolved_model")), None)
    run_json["model"]["resolved"] = resolved
    run_json["finished_at"] = workspace.utc_iso()
    run_json["cost_usd_total"] = round(sum(o["cost_usd"] for o in outcomes), 6)
    run_json["cache_hits"] = store.hits
    run_json["runs"] = len(outcomes)
    _write_run_json(run_root / "run.json", run_json)

    (run_root / "results.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    (run_root / "report.md").write_text(
        routing.render_routing_report(aggregate, run_json), encoding="utf-8"
    )

    totals = aggregate["totals"]
    print(f"run id     : {run_id}")
    print(f"mode       : {args.mode} (repeats {args.repeats}, ballot {len(descriptions)} skills)")
    print(f"runs       : {len(outcomes)} ({store.hits} cache hits)")
    print(
        f"outcome    : {totals['pass']} pass, {totals['ambiguous_pass']} ambiguous, "
        f"{totals['fail']} fail, {totals['phantom']} phantom of {aggregate['cases']} case(s)"
    )
    if aggregate["unanswered"]:
        print(f"unanswered : {', '.join(aggregate['unanswered'])} (every repeat failed)")
    print("confusion  :" + ("" if aggregate["confusion"] else " none"))
    for row in aggregate["confusion"]:
        print(
            f"  {row['skill_file']}:{row['line_no']:<4} {row['intent'][:60]!r} "
            f"expected={row['expected'] or '(none)'} chose={row['chosen'] or '(none)'}"
        )
    print("hijacks    :" + ("" if aggregate["hijacks"] else " none"))
    for name, count in aggregate["hijacks"].items():
        print(f"  {name}: {count}")
    for warning in aggregate["warnings"]:
        print(f"warning    : {warning}")
    print(f"cost (usd) : {run_json['cost_usd_total']}")
    print(f"wrote      : {run_root} (results.json, report.md)")
    return 0


def _route_one(
    job: Tuple[cases.RoutingCase, int],
    run_root: Path,
    args: argparse.Namespace,
    isolation_flags: Sequence[str],
    proj: Path,
    descriptions: Sequence[Tuple[str, str]],
    descriptions_sha: str,
    runner: SubprocessClaudeRunner,
    store: cache.Cache,
) -> Dict[str, Any]:
    """Run one intent once and record which skill it routed to."""
    case, repeat = job
    run_dir = _routing_run_dir(run_root, case, repeat)
    req = _routing_request(case, args, isolation_flags, proj, descriptions)

    key = routing.routing_cache_key(
        claude_code_version=args.claude_code_version,
        mode=args.mode,
        model=args.model,
        descriptions_sha=descriptions_sha,
        intent=case.intent,
        repeat=repeat,
    )
    cached = store.get(key)
    executor.write_request_json_at(run_dir, req)
    if cached is not None:
        result = executor.result_from_json(cached)
    else:
        # Native mode kills the call as soon as the model names a skill: the answer
        # is the choice, and running the skill would only add cost and latency.
        result = runner.run(req, early_stop_on_skill=args.mode == routing.MODE_NATIVE)
        if result.status == "ok":
            store.put(key, executor.result_to_json(result))
    executor.persist_result(run_dir, req, result)

    chosen = routing.chosen_skill(
        result, field=args.structured_output_field or routing.DEFAULT_STRUCTURED_FIELD
    )
    (run_dir / "chosen.json").write_text(
        json.dumps(
            {
                "skill_file": case.skill_file,
                "line_no": case.line_no,
                "intent": case.intent,
                "repeat": repeat,
                "mode": args.mode,
                "chosen": chosen,
                "status": result.status,
                "cached": cached is not None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "skill_file": case.skill_file,
        "line_no": case.line_no,
        "repeat": repeat,
        "chosen": chosen,
        "status": result.status,
        "cost_usd": result.cost_usd,
        "cached": cached is not None,
        "resolved_model": executor.resolved_model(result),
    }


def cmd_export_trigger_set(args: argparse.Namespace) -> int:
    """Write one skill's routing intents in skill-creator's trigger-eval format."""
    try:
        selected = routing.select_routing_cases(cases.load_routing_cases(), skills=[args.skill])
    except cases.CaseLoadError as exc:
        print(f"run_evals.py export-trigger-set: {exc}", file=sys.stderr)
        return 2
    payload = routing.trigger_set(selected, args.skill)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    positives = sum(1 for query in payload if query["should_trigger"])
    print(f"wrote trigger set: {out} ({len(payload)} queries, {positives} should-trigger)")
    return 0


def _case_from_metadata(path: Path, skill: str) -> Optional[cases.BehavioralCase]:
    """Rebuild the case a run directory was produced from."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return cases.BehavioralCase(
        skill=skill,
        file_rel=str(payload.get("file") or ""),
        eval_id=int(payload.get("eval_id") or 0),
        key=str(payload.get("key") or ""),
        name=payload.get("eval_name"),
        prompt=str(payload.get("prompt") or ""),
        expected_output=payload.get("expected_output"),
        assertions=[str(item) for item in payload.get("assertions") or []],
    )


def cmd_grade(args: argparse.Namespace) -> int:
    """Grade every ungraded run in a run directory (or all of them with --regrade)."""
    doctor_json, problem = load_doctor(args.claude_bin)
    if doctor_json is None:
        print(f"run_evals.py grade: {problem}", file=sys.stderr)
        return 2

    run_root = workspace.WORKSPACE / "runs" / args.run
    if not run_root.is_dir():
        print(f"run_evals.py grade: no run directory at {run_root}", file=sys.stderr)
        return 2

    args.isolation_strategy = doctor_json["strategy"]
    args.claude_code_version = doctor_json["claude_code_version"]
    args.structured_output_field = doctor_json.get("structured_output_field")
    args.repo_root = None
    isolation_flags = strategy_flags(args.isolation_strategy, workspace.WORKSPACE)
    runner = SubprocessClaudeRunner(args.claude_bin)
    store = cache.Cache(enabled=not args.no_cache)

    graded = 0
    skipped = 0
    for metadata_path in sorted(run_root.glob("*/eval-*/eval_metadata.json")):
        eval_dir = metadata_path.parent
        case = _case_from_metadata(metadata_path, eval_dir.parent.name)
        if case is None or not case.assertions:
            continue
        for run_dir in sorted(eval_dir.glob("*/run-*")):
            if (run_dir / "grading.json").is_file() and not args.regrade:
                skipped += 1
                continue
            response = grader.read_response(run_dir)
            grade_key = cache.grader_key(
                claude_code_version=args.claude_code_version,
                grader_model=args.grader_model,
                grader_prompt=grader.grader_prompt(),
                assertions=case.assertions,
                expected_output=case.expected_output,
                response=response,
            )
            cached = store.get(grade_key) if (response.strip() and not args.regrade) else None
            if cached is not None:
                grading = cached
                grader.write_grading(run_dir, grading)
            else:
                grading = grader.grade_run(runner, run_dir, case, args, isolation_flags)
                if grading.get("status") == grader.STATUS_OK:
                    store.put(grade_key, grading)
            graded += 1
            summary = grading.get("summary") or {}
            print(
                f"  {case.key:38} {run_dir.parent.name:26} "
                f"{grading.get('status', '?'):13} "
                f"{summary.get('passed', 0)}/{summary.get('total', 0)}"
            )

    print(f"graded     : {graded} run(s); {skipped} already had grading.json")
    return 0


def _split_csv(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or None


def _load_compare_side(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """`{"skills": ...}`-shaped dict for a compare `--a`/`--b` token, or an error message."""
    if token == "baseline":
        baseline = report.load_baseline()
        if baseline is None:
            return None, "no committed evals/baseline.json"
        return baseline, None
    run_root = workspace.WORKSPACE / "runs" / token
    if not run_root.is_dir():
        return None, f"no run directory at {run_root}"
    return analysis.aggregate_run(run_root), None


def _print_compare(comparison: Dict[str, Any], *, label_a: str, label_b: str) -> None:
    print(f"compare    : {label_a} -> {label_b}")
    for skill in comparison["skills"]:
        delta = skill["with_pass_rate_delta"]
        delta_str = f"{delta:+.4f}" if delta is not None else "n/a"
        flag = " REGRESSION" if skill["regression"] else (" (noise)" if skill["noise"] else "")
        print(f"  {skill['skill']:26} with_pass_rate_delta={delta_str}{flag}")
    for flip in comparison["flips"]:
        print(f"  {flip['direction']:10} {flip['skill']}: {flip['assertion']}")
    for entry in comparison.get("signal_lost") or []:
        print(f"  signal_lost  {entry['skill']}: {entry['assertion']}")
    for entry in comparison.get("signal_gained") or []:
        print(f"  signal_gained {entry['skill']}: {entry['assertion']}")
    if comparison.get("no_baseline"):
        print(f"  no_baseline (in {label_b} only): {', '.join(comparison['no_baseline'])}")
    if comparison.get("not_in_run"):
        print(f"  not_in_run (in {label_a} only): {', '.join(comparison['not_in_run'])}")
    print(f"regressions: {comparison['regressions']}  gains: {comparison['gains']}")


def cmd_compare(args: argparse.Namespace) -> int:
    """Diff two runs, or a run against the committed baseline."""
    a_dict, a_err = _load_compare_side(args.a)
    if a_err:
        print(f"run_evals.py compare: --a {args.a!r}: {a_err}", file=sys.stderr)
        return 2
    b_dict, b_err = _load_compare_side(args.b)
    if b_err:
        print(f"run_evals.py compare: --b {args.b!r}: {b_err}", file=sys.stderr)
        return 2

    comparison = analysis.compare(a_dict, b_dict, skills=_split_csv(args.skill))
    _print_compare(comparison, label_a=args.a, label_b=args.b)
    if args.fail_on_regression and comparison["regressions"] > 0:
        return 1
    return 0


def _run_meta(run_root: Path) -> Dict[str, Any]:
    path = run_root / "run.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def cmd_report(args: argparse.Namespace) -> int:
    """Render a run's Markdown report to stdout, or to --out.

    One run id can name a behavioral run, a routing run, or (with the same label)
    both; every section that exists for it is rendered.
    """
    run_root = workspace.WORKSPACE / "runs" / args.run
    routing_root = workspace.WORKSPACE / "routing" / args.run
    routing_results = routing_root / "results.json"
    if not run_root.is_dir() and not routing_results.is_file():
        print(
            f"run_evals.py report: no run directory at {run_root} and no routing "
            f"results at {routing_results}",
            file=sys.stderr,
        )
        return 2

    sections: List[str] = []
    if run_root.is_dir():
        sections.append(report.render_run_report(analysis.aggregate_run(run_root), _run_meta(run_root)))
    if routing_results.is_file():
        aggregate = json.loads(routing_results.read_text(encoding="utf-8"))
        sections.append(routing.render_routing_report(aggregate, _run_meta(routing_root)))
    text = "\n".join(sections)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote report: {args.out}")
    else:
        print(text)
    return 0


def cmd_baseline_update(args: argparse.Namespace) -> int:
    """Merge a behavioral run, a routing run, or both into evals/baseline.json."""
    if not args.from_run and not args.routing_from:
        print("run_evals.py baseline update: pass --from, --routing-from, or both", file=sys.stderr)
        return 2

    run_root: Optional[Path] = None
    run_meta: Dict[str, Any] = {}
    if args.from_run:
        run_root = workspace.WORKSPACE / "runs" / args.from_run
        if not run_root.is_dir():
            print(f"run_evals.py baseline update: no run directory at {run_root}", file=sys.stderr)
            return 2
        run_json_path = run_root / "run.json"
        if run_json_path.is_file():
            run_meta = json.loads(run_json_path.read_text(encoding="utf-8"))
    if args.require_clean and run_meta.get("dirty"):
        print(
            "run_evals.py baseline update: --require-clean was set and the source run "
            "was recorded dirty",
            file=sys.stderr,
        )
        return 2
    routing_block = None
    if args.routing_from:
        routing_block, routing_error = _load_routing_block(args.routing_from)
        if routing_block is None:
            print(f"run_evals.py baseline update: {routing_error}", file=sys.stderr)
            return 2

    existing = report.load_baseline()
    if run_root is None:
        # Routing-only update: the behavioral half of the baseline is untouched,
        # so nothing but the routing section (and its timestamp) may change.
        if existing is None:
            print(
                "run_evals.py baseline update: no committed evals/baseline.json to add a "
                "routing section to; pass --from as well",
                file=sys.stderr,
            )
            return 2
        merged = dict(existing)
        merged["routing"] = routing_block
        merged["generated_at"] = workspace.utc_iso()
    else:
        results = analysis.aggregate_run(run_root)
        merged = report.merge_baseline(
            existing, results, run_meta, routing=routing_block, root=workspace.ROOT
        )
    path = report.write_baseline(merged, root=workspace.ROOT)
    routing_note = f", routing from {args.routing_from}" if args.routing_from else ""
    print(f"wrote baseline: {path} ({len(merged.get('skills') or {})} skill(s){routing_note})")
    return 0


def _load_routing_block(run_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Baseline `routing` section from a routing run, or a message saying why not."""
    results_path = workspace.WORKSPACE / "routing" / run_id / "results.json"
    if not results_path.is_file():
        return None, f"no routing results at {results_path}"
    try:
        aggregate = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{results_path} is unreadable: {exc}"
    return routing.baseline_routing_block(aggregate, run_id), None


def cmd_baseline_check(args: argparse.Namespace) -> int:
    """Report staleness or zero-signal skills in the committed baseline."""
    baseline = report.load_baseline()
    if baseline is None:
        print("run_evals.py baseline check: no committed evals/baseline.json", file=sys.stderr)
        return 2
    problems = report.check_baseline(baseline, workspace.ROOT)
    if problems:
        print("baseline check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"baseline check passed: {len(baseline.get('skills') or {})} skill(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
