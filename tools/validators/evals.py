#!/usr/bin/env python3
"""Eval fixtures: the behavioral `examples/evals.json` and `routing-eval.jsonl`.

Schema validation runs against jsonschema where it is installed and against
a hand-written fallback where it is not; both legs must reach the same
verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


from . import context
from .context import add_error, load_json
from .structure import normalized_body

ROUTING_REQUIRED_KEYS = frozenset({"intent", "expected_skill"})


ROUTING_OPTIONAL_KEYS = frozenset({"ambiguous_with", "note", "expect_question"})


NON_INFORMATIVE_ASSERTIONS = {
    "uses the skill",
    "uses the named skill",
    "meets the skill contract",
    "follows the skill",
    "does the task",
}


def load_eval_schema(errors: list[str]) -> dict[str, Any] | None:
    data = load_json(context.EVAL_SCHEMA, errors)
    if not isinstance(data, dict):
        add_error(errors, "schemas/skill-evals.schema.json: schema must contain an object")
        return None
    if data.get("type") != "object" or "evals" not in data.get("required", []):
        add_error(errors, "schemas/skill-evals.schema.json: schema must require evals object shape")
    return data


def validate_eval_schema_fallback(data: object, rel: Path, errors: list[str]) -> None:
    """Validate the subset expressed by schemas/skill-evals.schema.json.

    The repository intentionally avoids a package/toolchain. If the maintained
    jsonschema package is unavailable, this mirrors the committed schema fields
    that the repo uses so CI remains deterministic on stock Python.
    """
    if not isinstance(data, dict):
        add_error(errors, f"{rel}: schema violation: root must be an object")
        return

    if not isinstance(data.get("skill_name"), str) or not data["skill_name"].strip():
        add_error(errors, f"{rel}: schema violation: skill_name must be a non-empty string")

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        add_error(errors, f"{rel}: schema violation: evals must be a non-empty array")
        return

    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            add_error(errors, f"{rel}: schema violation: eval {index} must be an object")
            continue
        case_id = case.get("id")
        if case_id is None:
            add_error(errors, f"{rel}: schema violation: eval {index} needs id")
        elif isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} id must be a positive integer",
            )
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            add_error(errors, f"{rel}: schema violation: eval {index} prompt must be a non-empty string")
        if "expected_output" in case and (
            not isinstance(case["expected_output"], str) or not case["expected_output"].strip()
        ):
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} expected_output must be a non-empty string",
            )
        assertions = case.get("assertions")
        if (
            not isinstance(assertions, list)
            or len(assertions) < 2
            or not all(
                isinstance(item, str) and bool(item.strip()) for item in assertions
            )
        ):
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} assertions must be two or more strings",
            )


def validate_eval_schema(
    data: object,
    rel: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
) -> None:
    if context.jsonschema is None or schema is None:
        validate_eval_schema_fallback(data, rel, errors)
        return

    validator = context.jsonschema.Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    for error in schema_errors:
        location = ".".join(str(part) for part in error.path)
        suffix = f" at {location}" if location else ""
        add_error(errors, f"{rel}: schema violation{suffix}: {error.message}")


def eval_files(skill_dir: Path) -> list[Path]:
    candidates = (
        skill_dir / "examples" / "evals.json",
        skill_dir / "routing-eval.jsonl",
    )
    return [path for path in candidates if path.exists()]


def validate_routing_eval(
    rel: Path,
    lines: list[str],
    skill_names: set[str],
    errors: list[str],
) -> None:
    """Shape and coverage of a `routing-eval.jsonl` fixture.

    Coverage -- the owning skill expected on at least two lines and at least one
    null line -- is an error: without both, the fixture measures nothing about
    over- or under-triggering.
    """
    skill = Path(rel).parent.name
    expected_counts: dict[str | None, int] = {}
    intents: dict[str, int] = {}

    for index, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            add_error(errors, f"{rel}:{index}: comment lines are not allowed in routing fixtures")
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            add_error(errors, f"{rel}:{index}: invalid JSONL: {exc}")
            continue
        if not isinstance(case, dict):
            add_error(errors, f"{rel}:{index}: each line must be a JSON object")
            continue

        for key in sorted(ROUTING_REQUIRED_KEYS - set(case)):
            add_error(errors, f"{rel}:{index}: missing required key {key!r}")
        for key in sorted(set(case) - ROUTING_REQUIRED_KEYS - ROUTING_OPTIONAL_KEYS):
            add_error(errors, f"{rel}:{index}: unknown key {key!r}")

        intent = case.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            add_error(errors, f"{rel}:{index}: intent must be a non-empty string")
        else:
            key = normalized_body(intent)
            if key in intents:
                add_error(
                    errors,
                    f"{rel}:{index}: duplicate intent, first seen at line {intents[key]}",
                )
            else:
                intents[key] = index

        expected = case.get("expected_skill")
        if "expected_skill" not in case:
            pass  # already reported as a missing required key
        elif expected is None or isinstance(expected, str):
            expected_counts[expected] = expected_counts.get(expected, 0) + 1
            if isinstance(expected, str) and expected not in skill_names:
                add_error(
                    errors,
                    f"{rel}:{index}: expected_skill {expected!r} is not a skill in skills/",
                )
        else:
            add_error(errors, f"{rel}:{index}: expected_skill must be a skill name or null")

        ambiguous = case.get("ambiguous_with")
        if ambiguous is not None:
            if not isinstance(ambiguous, list) or not all(
                isinstance(item, str) for item in ambiguous
            ):
                add_error(errors, f"{rel}:{index}: ambiguous_with must be a list of skill names")
            else:
                for name in ambiguous:
                    if name not in skill_names:
                        add_error(
                            errors,
                            f"{rel}:{index}: ambiguous_with names unknown skill {name!r}",
                        )
        note = case.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            add_error(errors, f"{rel}:{index}: note must be a non-empty string")
        if "expect_question" in case and not isinstance(case["expect_question"], bool):
            add_error(errors, f"{rel}:{index}: expect_question must be a boolean")

    own = expected_counts.get(skill, 0)
    if own < 2:
        add_error(
            errors,
            f"{rel}: {skill} must be the expected_skill on at least 2 lines, found {own}",
        )
    if expected_counts.get(None, 0) < 1:
        add_error(errors, f"{rel}: needs at least one line with expected_skill null")


def eval_case_count(path: Path, errors: list[str]) -> int:
    if path.suffix == ".jsonl":
        # Routing JSONL has no behavioral assertion schema, so it cannot satisfy
        # the package-level synthetic behavioral-eval minimum.
        return 0

    data = load_json(path, errors)
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list):
        return 0
    return len(data["evals"])


def validate_eval_file(
    skill: str,
    path: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
    skill_names: set[str] | None = None,
) -> None:
    rel = path.relative_to(context.ROOT)

    if path.suffix == ".jsonl":
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            add_error(errors, f"{rel}: routing eval file is empty")
            return
        validate_routing_eval(rel, lines, skill_names or set(), errors)
        return

    data = load_json(path, errors)
    validate_eval_schema(data, rel, schema, errors)
    if not isinstance(data, dict):
        add_error(errors, f"{rel}: eval file must contain an object")
        return

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        add_error(errors, f"{rel}: missing non-empty evals array")
        return

    declared = data.get("skill_name")
    if declared and declared != skill:
        add_error(errors, f"{rel}: declared skill_name {declared!r} does not match {skill!r}")

    seen_ids: set[int] = set()
    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            add_error(errors, f"{rel}: eval {index} must be an object")
            continue
        prompt = case.get("prompt")
        assertions = case.get("assertions")
        if not isinstance(prompt, str) or not prompt.strip():
            add_error(errors, f"{rel}: eval {index} missing prompt")
        if not isinstance(assertions, list) or len(assertions) < 2:
            add_error(errors, f"{rel}: eval {index} needs at least two assertions")
        elif not all(
            isinstance(assertion, str) and bool(assertion.strip())
            for assertion in assertions
        ):
            add_error(errors, f"{rel}: eval {index} assertions must be non-empty strings")
        else:
            for assertion in assertions:
                normalized = re.sub(r"\s+", " ", assertion.strip().lower())
                if normalized in NON_INFORMATIVE_ASSERTIONS:
                    add_error(
                        errors,
                        f"{rel}: eval {index} uses non-informative assertion {assertion!r}",
                    )

        case_id = case.get("id")
        if case_id is None:
            add_error(errors, f"{rel}: eval {index} missing positive integer id")
        elif isinstance(case_id, int) and not isinstance(case_id, bool) and case_id > 0:
            if case_id in seen_ids:
                add_error(errors, f"{rel}: duplicate eval id {case_id}")
            seen_ids.add(case_id)

        expected_output = case.get("expected_output")
        if expected_output == "Meets the skill contract for this scenario.":
            add_error(errors, f"{rel}: eval {index} uses a non-informative expected_output")
