"""Aggregate a graded run directory into per-assertion classes and per-skill stats.

`aggregate_run` walks `<run>/<skill>/eval-N/<config>/run-K/{grading,timing}.json`
(the layout `executor.py` and `grader.py` write) and produces the `results.json`
shape: one row per (case, assertion) with each config's pass rate and a 2x2
discriminating-power class, plus a per-skill summary. `compare` diffs two such
summaries (or a run summary against the committed `evals/baseline.json`, which
carries the same `skills` shape) to find regressions between two points in time.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import HARNESS_VERSION, workspace
from .executor import CONFIG_WITH_SKILL, CONFIG_WITHOUT_SKILL
from .grader import STATUS_OK

CLASS_DISCRIMINATING = "discriminating"
CLASS_NON_DISCRIMINATING = "non_discriminating"
CLASS_BROKEN = "broken"
CLASS_HARMFUL = "harmful"
CLASS_FLAKY = "flaky"
CLASS_UNGRADED = "ungraded"
CLASSES = (CLASS_DISCRIMINATING, CLASS_NON_DISCRIMINATING, CLASS_BROKEN, CLASS_HARMFUL, CLASS_FLAKY)
_LABELED_CLASSES = (CLASS_NON_DISCRIMINATING, CLASS_BROKEN, CLASS_HARMFUL)


def classify_assertion(p_with: Optional[float], p_without: Optional[float], repeats: int) -> str:
    """One assertion's 2x2 discriminating-power class.

    `p_with`/`p_without` are each config's pass rate for this assertion, computed
    over graded repeats only (an all-ungraded config yields `None`, which this
    function reports as `ungraded` rather than guessing a class). When `repeats`
    is more than one and either rate lands strictly between 0 and 1, the repeats
    disagreed with each other, so the assertion is `flaky` regardless of the
    binarized 2x2 outcome.
    """
    if p_with is None or p_without is None:
        return CLASS_UNGRADED
    if repeats > 1 and (_is_mixed(p_with) or _is_mixed(p_without)):
        return CLASS_FLAKY
    with_pass = p_with >= 0.5
    without_pass = p_without >= 0.5
    if with_pass and without_pass:
        return CLASS_NON_DISCRIMINATING
    if with_pass and not without_pass:
        return CLASS_DISCRIMINATING
    if not with_pass and without_pass:
        return CLASS_HARMFUL
    return CLASS_BROKEN


def _is_mixed(p: float) -> bool:
    return 0.0 < p < 1.0


# Copied (not imported: `imports/` is vendored and never edited) from
# `imports/anthropic-skill-creator/scripts/aggregate_benchmark.py:44-63`, so
# results.json stats stay computed the same way the vendored viewer expects.
def calculate_stats(values: List[float]) -> Dict[str, float]:
    """Mean, stddev, min, max for a list of values."""
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}

    n = len(values)
    mean = sum(values) / n

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _eval_number(eval_dir: Path) -> int:
    try:
        return int(eval_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _label(key: str, eval_id: int, total_assertions: int, assertion: str) -> str:
    """Human-readable id for one assertion, e.g. `examples:1/4 No mutation`."""
    parts = key.split(":")
    file_part = parts[1] if len(parts) >= 3 else parts[0]
    return f"{file_part}:{eval_id}/{total_assertions} {assertion}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def _new_bucket() -> Dict[str, Any]:
    return {
        "case_ids": set(),
        "assertion_rows": 0,
        "configs": {},
        "classes": {},
        "non_discriminating": [],
        "broken": [],
        "harmful": [],
        "ungraded": 0,
        "executor_issues": {},
    }


def _config_entry(bucket: Dict[str, Any], config: str) -> Dict[str, Any]:
    return bucket["configs"].setdefault(
        config, {"pass_rates": [], "tokens": [], "time": [], "cost": 0.0}
    )


def _finalize_skill(bucket: Dict[str, Any]) -> Dict[str, Any]:
    configs: Dict[str, Any] = {}
    for config, data in bucket["configs"].items():
        configs[config] = {
            "pass_rate": calculate_stats(data["pass_rates"]),
            "tokens": calculate_stats(data["tokens"]),
            "time_seconds": calculate_stats(data["time"]),
            "cost_usd_total": round(data["cost"], 6),
        }
    with_mean = configs.get(CONFIG_WITH_SKILL, {}).get("pass_rate", {}).get("mean")
    without_mean = configs.get(CONFIG_WITHOUT_SKILL, {}).get("pass_rate", {}).get("mean")
    delta = round(with_mean - without_mean, 4) if with_mean is not None and without_mean is not None else None
    classes = {cls: bucket["classes"].get(cls, 0) for cls in CLASSES}
    return {
        "cases": len(bucket["case_ids"]),
        "assertions": bucket["assertion_rows"],
        "configs": configs,
        "delta": delta,
        "classes": classes,
        "non_discriminating": list(bucket["non_discriminating"]),
        "broken": list(bucket["broken"]),
        "harmful": list(bucket["harmful"]),
        "ungraded": bucket["ungraded"],
        "skill_invoked": None,  # populated once --load-mode discover lands
        "executor_issues": dict(bucket["executor_issues"]),
    }


def aggregate_run(run_dir: Path) -> Dict[str, Any]:
    """Aggregate one run directory into the `results.json` shape.

    Reads every `eval_metadata.json`, `grading.json`, and `timing.json` under
    `run_dir`; never calls `claude`. A `grading.json` whose `status` is not
    `"ok"` (grader_error, no_response) is excluded from pass rates and counted
    in the skill's `ungraded`, never scored as 0%.
    """
    run_dir = Path(run_dir)
    run_meta = _read_json(run_dir / "run.json") or {}
    repeats = int(run_meta.get("repeats") or 1)

    rows: List[Dict[str, Any]] = []
    skills: Dict[str, Dict[str, Any]] = {}
    structurally_unsatisfiable: List[Dict[str, Any]] = []

    metadata_paths = sorted(
        run_dir.glob("*/eval-*/eval_metadata.json"),
        key=lambda p: (p.parent.parent.name, _eval_number(p.parent)),
    )
    for metadata_path in metadata_paths:
        eval_dir = metadata_path.parent
        skill = eval_dir.parent.name
        metadata = _read_json(metadata_path) or {}
        assertions = [str(item) for item in metadata.get("assertions") or []]
        if not assertions:
            continue
        eval_id = int(metadata.get("eval_id") or 0)
        key = str(metadata.get("key") or f"{skill}:{eval_id}")

        bucket = skills.setdefault(skill, _new_bucket())
        bucket["case_ids"].add(eval_id)

        config_counts: Dict[str, List[Dict[str, int]]] = {}
        evidence_by_config: Dict[str, List[Optional[str]]] = {}
        case_suggestions: List[Dict[str, str]] = []

        for config_dir in sorted(p for p in eval_dir.iterdir() if p.is_dir()):
            run_paths = sorted(config_dir.glob("run-*"))
            if not run_paths:
                continue
            config = config_dir.name
            counts = [{"passed": 0, "total": 0} for _ in assertions]
            case_run_rates: List[float] = []
            evidence: List[Optional[str]] = [None] * len(assertions)
            config_entry = _config_entry(bucket, config)

            for run_path in run_paths:
                timing = _read_json(run_path / "timing.json")
                if timing:
                    config_entry["tokens"].append(float(timing.get("total_tokens") or 0))
                    config_entry["time"].append(float(timing.get("total_duration_seconds") or 0.0))
                    config_entry["cost"] += float(timing.get("total_cost_usd") or 0.0)
                    status = str(timing.get("status") or "ok")
                    if status != "ok":
                        bucket["executor_issues"][status] = bucket["executor_issues"].get(status, 0) + 1

                grading = _read_json(run_path / "grading.json")
                if grading is None:
                    continue
                config_entry["cost"] += float(grading.get("grader_cost_usd") or 0.0)
                expectations = grading.get("expectations") or []
                if grading.get("status") != STATUS_OK or len(expectations) != len(assertions):
                    bucket["ungraded"] += 1
                    continue

                run_passed = 0
                for idx, item in enumerate(expectations):
                    passed = bool(item.get("passed"))
                    counts[idx]["total"] += 1
                    if passed:
                        counts[idx]["passed"] += 1
                        run_passed += 1
                    if item.get("evidence"):
                        evidence[idx] = str(item["evidence"])
                case_run_rates.append(run_passed / len(assertions))

                feedback = grading.get("eval_feedback") or {}
                for sug in feedback.get("suggestions") or []:
                    if isinstance(sug, dict) and sug.get("assertion"):
                        case_suggestions.append(
                            {
                                "config": config,
                                "assertion": str(sug["assertion"]),
                                "reason": str(sug.get("reason") or ""),
                            }
                        )

            config_counts[config] = counts
            evidence_by_config[config] = evidence
            if case_run_rates:
                config_entry["pass_rates"].append(sum(case_run_rates) / len(case_run_rates))

        with_counts = config_counts.get(CONFIG_WITH_SKILL)
        without_counts = config_counts.get(CONFIG_WITHOUT_SKILL)

        for idx, assertion in enumerate(assertions):
            row_config: Dict[str, Any] = {}
            for config, counts in config_counts.items():
                c = counts[idx]
                p = (c["passed"] / c["total"]) if c["total"] else None
                row_config[config] = {"passed_runs": c["passed"], "total_runs": c["total"], "p": p}

            cls: Optional[str] = None
            if with_counts is not None and without_counts is not None:
                p_with = row_config[CONFIG_WITH_SKILL]["p"]
                p_without = row_config[CONFIG_WITHOUT_SKILL]["p"]
                if p_with is not None and p_without is not None:
                    cls = classify_assertion(p_with, p_without, repeats)

            evidence_text = None
            for config in (CONFIG_WITH_SKILL, CONFIG_WITHOUT_SKILL):
                candidates = evidence_by_config.get(config) or []
                if idx < len(candidates) and candidates[idx]:
                    evidence_text = candidates[idx]
                    break

            label = _label(key, eval_id, len(assertions), assertion)
            rows.append(
                {
                    "skill": skill,
                    "key": key,
                    "eval_id": eval_id,
                    "assertion_idx": idx,
                    "assertion": assertion,
                    "config": row_config,
                    "cls": cls,
                    "label": label,
                    "evidence": evidence_text,
                }
            )
            bucket["assertion_rows"] += 1

            if cls is not None:
                bucket["classes"][cls] = bucket["classes"].get(cls, 0) + 1
                if cls in _LABELED_CLASSES:
                    bucket[cls].append(label)
                if cls == CLASS_BROKEN:
                    for sug in case_suggestions:
                        if _norm(sug["assertion"]) == _norm(assertion):
                            structurally_unsatisfiable.append(
                                {
                                    "skill": skill,
                                    "key": key,
                                    "eval_id": eval_id,
                                    "assertion": assertion,
                                    "reason": sug["reason"],
                                }
                            )

    return {
        "run_id": run_meta.get("run_id"),
        "harness_version": HARNESS_VERSION,
        "generated_at": workspace.utc_iso(),
        "repeats": repeats,
        "rows": rows,
        "skills": {name: _finalize_skill(bucket) for name, bucket in skills.items()},
        "structurally_unsatisfiable": structurally_unsatisfiable,
    }


def compare(
    a: Dict[str, Any], b: Dict[str, Any], *, skills: Optional[Sequence[str]] = None
) -> Dict[str, Any]:
    """Per-skill delta between two aggregate-shaped results (or a baseline: same `skills` shape).

    The delta is the change in each skill's own with-minus-without `delta`
    between `a` and `b` (did the skill get more or less effective), converted to
    an assertion-count equivalent to flag a skill whose delta moved by less than
    one assertion as `noise` — real but too small to act on, not a failure.
    Itemized regressions/gains come from the `broken`/`harmful` label lists: an
    assertion that appears in one side's fail set and not the other's flipped.
    """
    skills_a = a.get("skills") or {}
    skills_b = b.get("skills") or {}
    names = sorted(set(skills_a) | set(skills_b))
    if skills is not None:
        wanted = set(skills)
        names = [name for name in names if name in wanted]

    per_skill: List[Dict[str, Any]] = []
    flips: List[Dict[str, Any]] = []

    for name in names:
        sa = skills_a.get(name) or {}
        sb = skills_b.get(name) or {}
        delta_a, delta_b = sa.get("delta"), sb.get("delta")
        skill_delta = None
        noise = False
        n_assertions = int(sb.get("assertions") or sa.get("assertions") or 0)
        if delta_a is not None and delta_b is not None:
            skill_delta = round(delta_b - delta_a, 4)
            noise = n_assertions > 0 and abs(skill_delta) * n_assertions < 1.0

        fail_a = set(sa.get("broken") or []) | set(sa.get("harmful") or [])
        fail_b = set(sb.get("broken") or []) | set(sb.get("harmful") or [])
        for label in sorted(fail_b - fail_a):
            flips.append({"skill": name, "assertion": label, "direction": "regression"})
        for label in sorted(fail_a - fail_b):
            flips.append({"skill": name, "assertion": label, "direction": "gain"})

        per_skill.append(
            {
                "skill": name,
                "delta_a": delta_a,
                "delta_b": delta_b,
                "delta": skill_delta,
                "assertions": n_assertions,
                "noise": noise,
            }
        )

    regressions = sum(1 for flip in flips if flip["direction"] == "regression")
    gains = sum(1 for flip in flips if flip["direction"] == "gain")
    return {"skills": per_skill, "flips": flips, "regressions": regressions, "gains": gains}
