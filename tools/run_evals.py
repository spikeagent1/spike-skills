#!/usr/bin/env python3
"""Eval runner CLI for spike-skills.

`doctor` probes isolation, `run` executes behavioral cases in paired configs and
grades them, and `grade` re-grades an existing run directory. The analysis,
reporting, comparison, baseline, and routing subcommands are declared so their
flags stay stable while they land.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evalrunner import HARNESS_VERSION, cache, cases, doctor, executor, grader, workspace  # noqa: E402
from tools.evalrunner.claude_cli import SubprocessClaudeRunner, strategy_flags, strategy_names  # noqa: E402

DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_S = 180.0
DEFAULT_PROBE_BUDGET_USD = 0.05
DEFAULT_RUN_BUDGET_USD = 0.50
DEFAULT_WORKERS = 4
NOT_IMPLEMENTED = ("routing", "compare", "report", "baseline")


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

    for name in NOT_IMPLEMENTED:
        stub = subparsers.add_parser(
            name, help=f"{name} (not implemented in this build)", add_help=False
        )
        stub.set_defaults(handler=_not_implemented, command_name=name)

    return parser


def _not_implemented(args: argparse.Namespace) -> int:
    name = getattr(args, "command_name", args.command)
    print(f"run_evals.py {name}: not implemented in this build", file=sys.stderr)
    return 2


def load_doctor(claude_bin: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validated `doctor.json`, or a message explaining why `run` must refuse.

    An eval run that cannot prove its isolation is worse than no run: it silently
    measures the operator's ~100 personal skills instead of this repo's.
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
    installed = workspace.claude_version(claude_bin)
    recorded = payload.get("claude_code_version")
    if installed != recorded:
        return None, (
            f"{path} was written for Claude Code {recorded} but {claude_bin} is {installed}; "
            "re-run `doctor`"
        )
    return payload, None


def _resolve_skills(args: argparse.Namespace) -> Optional[List[str]]:
    """Skill filter from `--skill` and `--cohort`, or None for no skill filter."""
    names: List[str] = []
    if args.skill:
        names.extend(name.strip() for name in args.skill.split(",") if name.strip())
    if args.cohort:
        names.extend(cases.cohort_skills(args.cohort))
    return names or None


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

    doctor_json, problem = load_doctor(args.claude_bin)
    if doctor_json is None:
        print(f"run_evals.py run: {problem}", file=sys.stderr)
        return 2

    try:
        configs = _parse_configs(args.configs)
        selected = cases.select_cases(
            cases.load_behavioral_cases(),
            skills=_resolve_skills(args),
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
        },
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
    print(f"wrote      : {run_root}")
    return 0


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Stub subcommands accept the flags they will eventually take, so callers get
    # the "not implemented" message rather than an argparse usage error.
    args, extra = parser.parse_known_args(argv)
    if getattr(args, "command_name", None):
        return _not_implemented(args)
    if extra:
        parser.error("unrecognized arguments: " + " ".join(extra))
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
