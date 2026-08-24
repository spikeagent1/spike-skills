#!/usr/bin/env python3
"""Validate the portable skill library contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ModuleNotFoundError:  # pragma: no cover - covered by fallback tests.
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EVAL_SCHEMA = ROOT / "schemas" / "skill-evals.schema.json"

SECRET_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|private[_-]?key)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}",
    re.IGNORECASE,
)
PRIVATE_PATH_RE = re.compile(
    r"(^|/)(evals/workspaces|cache|caches|memory|memories|transcripts?|private-state|"
    r"local-state|runtime-state|\.env)(/|$)",
    re.IGNORECASE,
)
HIDDEN_DEP_RE = re.compile(
    r"\b(spike internal|private endpoint|production database|personal transcript)\b",
    re.IGNORECASE,
)
PENDING_REVIEW_SECTIONS = (
    "## When to use",
    "## Required inputs",
    "## Workflow",
    "## Sources and freshness",
    "## Privacy and mutations",
    "## Safety boundaries",
    "## Output contract",
    "## Failure conditions",
)


def frontmatter(text: str) -> dict[str, str] | None:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None

    data: dict[str, str] = {}
    for key in ("name", "description"):
        key_match = re.search(rf"^{key}:\s*(.+?)\s*$", match.group(1), re.MULTILINE)
        if key_match:
            data[key] = key_match.group(1).strip().strip("\"'")
    return data


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report every parse failure.
        add_error(errors, f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return None


def load_eval_schema(errors: list[str]) -> dict[str, Any] | None:
    data = load_json(EVAL_SCHEMA, errors)
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

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        add_error(errors, f"{rel}: schema violation: evals must be a non-empty array")
        return

    for key in ("skill_name", "skill", "version", "description"):
        if key in data and (
            not isinstance(data[key], str) or not data[key].strip()
        ):
            add_error(
                errors,
                f"{rel}: schema violation: {key} must be a non-empty string",
            )

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
        has_prompt = (
            isinstance(case.get("prompt"), str) and bool(case["prompt"].strip())
        )
        has_input = isinstance(case.get("input"), str) and bool(case["input"].strip())
        if not has_prompt and not has_input:
            add_error(errors, f"{rel}: schema violation: eval {index} needs prompt or input")
        for key in ("name", "expected_output"):
            if key in case and (
                not isinstance(case[key], str) or not case[key].strip()
            ):
                add_error(
                    errors,
                    f"{rel}: schema violation: eval {index} {key} must be a non-empty string",
                )
        for key in ("assertions", "expectations", "expect"):
            if key not in case:
                continue
            value = case[key]
            if (
                not isinstance(value, list)
                or len(value) < 2
                or not all(
                    isinstance(item, str) and bool(item.strip()) for item in value
                )
            ):
                add_error(
                    errors,
                    f"{rel}: schema violation: eval {index} {key} must be two or more strings",
                )


def validate_eval_schema(
    data: object,
    rel: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
) -> None:
    if jsonschema is None or schema is None:
        validate_eval_schema_fallback(data, rel, errors)
        return

    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    for error in schema_errors:
        location = ".".join(str(part) for part in error.path)
        suffix = f" at {location}" if location else ""
        add_error(errors, f"{rel}: schema violation{suffix}: {error.message}")


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def parse_catalog_inventory(errors: list[str]) -> dict[str, dict[str, str]]:
    text = (ROOT / "catalog" / "approved.yaml").read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None

    for line in text.splitlines():
        name_match = re.match(r"^\s+- name: ([a-z0-9-]+)\s*$", line)
        if name_match:
            name = name_match.group(1)
            if name in entries:
                add_error(errors, f"catalog/approved.yaml: duplicate skill {name}")
            current = {"name": name}
            entries[name] = current
            continue

        field_match = re.match(r"^\s{4}([a-z_]+):\s*(.*?)\s*$", line)
        if current is not None and field_match:
            current[field_match.group(1)] = field_match.group(2).strip().strip("\"'")

    if not entries:
        add_error(errors, "catalog/approved.yaml: no skill entries found")
    return entries


def parse_domain_lists(errors: list[str]) -> tuple[set[str], set[str]]:
    text = (ROOT / "catalog" / "domains.yaml").read_text(encoding="utf-8")
    released: set[str] = set()
    next_names: set[str] = set()
    active: set[str] | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("released:"):
            active = released
            continue
        if stripped.startswith("next:"):
            active = next_names
            continue
        if active is not None and stripped.startswith("- "):
            active.add(stripped[2:].strip())
            continue
        if active is not None and stripped and not stripped.startswith("- "):
            active = None

    if not released:
        add_error(errors, "catalog/domains.yaml: no released skills found")
    return released, next_names


def parse_source_statuses() -> dict[str, str]:
    text = (ROOT / "catalog" / "sources.yaml").read_text(encoding="utf-8")
    statuses: dict[str, str] = {}
    current: str | None = None

    for line in text.splitlines():
        source_match = re.match(r"^  ([a-z0-9-]+):\s*$", line)
        if source_match:
            current = source_match.group(1)
            continue
        status_match = re.match(r"^\s{4}status:\s*(\S+)\s*$", line)
        if current is not None and status_match:
            statuses[current] = status_match.group(1)

    return statuses


def eval_files(skill_dir: Path) -> list[Path]:
    candidates = (
        skill_dir / "examples" / "evals.json",
        skill_dir / "evals" / "evals.json",
        skill_dir / "routing-eval.jsonl",
    )
    return [path for path in candidates if path.exists()]


def validate_eval_file(
    skill: str,
    path: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
) -> None:
    rel = path.relative_to(ROOT)

    if path.suffix == ".jsonl":
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("//")
        ]
        if not lines:
            add_error(errors, f"{rel}: routing eval file is empty")
            return
        for index, line in enumerate(lines, 1):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                add_error(errors, f"{rel}:{index}: invalid JSONL: {exc}")
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

    declared = data.get("skill_name") or data.get("skill")
    if declared and declared != skill:
        add_error(errors, f"{rel}: declared skill {declared!r} does not match {skill!r}")

    seen_ids: set[int] = set()
    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            add_error(errors, f"{rel}: eval {index} must be an object")
            continue
        prompt = case.get("prompt") or case.get("input")
        expectations = case.get("assertions") or case.get("expectations") or case.get("expect")
        if not isinstance(prompt, str) or not prompt.strip():
            add_error(errors, f"{rel}: eval {index} missing prompt/input")
        if not isinstance(expectations, list) or len(expectations) < 2:
            add_error(errors, f"{rel}: eval {index} needs at least two assertions/expectations")
        elif not all(
            isinstance(expectation, str) and bool(expectation.strip())
            for expectation in expectations
        ):
            add_error(errors, f"{rel}: eval {index} assertions must be non-empty strings")

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


def validate_skill(
    skill_dir: Path,
    inventory: dict[str, dict[str, str]],
    released: set[str],
    next_names: set[str],
    schema: dict[str, Any] | None,
    errors: list[str],
) -> None:
    rel = skill_dir.relative_to(ROOT)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        add_error(errors, f"{rel}: missing SKILL.md")
        return

    text = skill_md.read_text(encoding="utf-8")
    meta = frontmatter(text)
    if meta is None:
        add_error(errors, f"{rel}/SKILL.md: missing or invalid frontmatter")
        return

    name = meta.get("name")
    description = meta.get("description")
    if name != skill_dir.name:
        add_error(errors, f"{rel}/SKILL.md: frontmatter name {name!r} must match directory")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        add_error(errors, f"{rel}/SKILL.md: name must be kebab-case")
    if not isinstance(description, str) or len(description.strip()) < 24:
        add_error(errors, f"{rel}/SKILL.md: description must be a useful string")
    if "dependencies" not in text.lower():
        add_error(errors, f"{rel}/SKILL.md: must explicitly declare dependencies")
    if "provenance" not in text.lower():
        add_error(errors, f"{rel}/SKILL.md: must include provenance/attribution")
    if HIDDEN_DEP_RE.search(text):
        add_error(errors, f"{rel}/SKILL.md: contains suspicious hidden/private dependency language")
    entry = inventory.get(skill_dir.name)
    if entry is None:
        add_error(errors, f"{rel}: missing catalog/approved.yaml entry")
    else:
        status = entry.get("status")
        proposal = entry.get("workshop_proposal", "")
        if status not in {"approved", "pending-review"}:
            add_error(errors, f"{rel}: catalog status must be approved or pending-review")
        if status == "approved":
            if skill_dir.name != "skill-library-ops" and skill_dir.name not in released:
                add_error(errors, f"{rel}: approved skill must be in catalog/domains.yaml released")
            if skill_dir.name in next_names:
                add_error(
                    errors,
                    f"{rel}: approved skill must not remain in catalog/domains.yaml next",
                )
        if status == "pending-review":
            if skill_dir.name in released:
                add_error(
                    errors,
                    f"{rel}: pending-review skill must not be in catalog/domains.yaml released",
                )
            if skill_dir.name not in next_names:
                add_error(
                    errors,
                    f"{rel}: pending-review skill must be in catalog/domains.yaml next",
                )
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-\d{8}-[a-z0-9]{10}", proposal):
                add_error(
                    errors,
                    f"{rel}: pending-review skill must have a real workshop_proposal ID",
                )
            for heading in PENDING_REVIEW_SECTIONS:
                if heading not in text:
                    add_error(
                        errors,
                        f"{rel}/SKILL.md: pending-review skill missing section {heading!r}",
                    )

    files = eval_files(skill_dir)
    if not files:
        add_error(errors, f"{rel}: missing evals file")
    for path in files:
        validate_eval_file(skill_dir.name, path, schema, errors)


def validate_privacy(errors: list[str]) -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in ("evals/workspaces/", ".env", "*.skill"):
        if required not in ignored:
            add_error(
                errors,
                f".gitignore: missing local/private generated-state pattern {required!r}",
            )

    for path in git_files():
        rel = path.relative_to(ROOT).as_posix()
        if PRIVATE_PATH_RE.search(rel):
            add_error(errors, f"{rel}: private/generated local-state path is tracked")
            continue
        if path.suffix.lower() not in {
            ".md",
            ".json",
            ".jsonl",
            ".yaml",
            ".yml",
            ".py",
            ".txt",
            ".gitignore",
            "",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if SECRET_RE.search(line):
                add_error(errors, f"{rel}:{line_no}: possible secret or credential")


def main() -> int:
    errors: list[str] = []
    schema = load_eval_schema(errors)
    inventory = parse_catalog_inventory(errors)
    released, next_names = parse_domain_lists(errors)
    source_statuses = parse_source_statuses()
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    skill_names = {path.name for path in skill_dirs}

    for skill_dir in skill_dirs:
        validate_skill(skill_dir, inventory, released, next_names, schema, errors)

    for name in sorted(set(inventory) - skill_names):
        add_error(errors, f"catalog/approved.yaml: {name} has no skills/{name} directory")

    for name in sorted(released - set(inventory)):
        add_error(
            errors,
            f"catalog/domains.yaml: released skill {name} is missing catalog/approved.yaml entry",
        )

    for name, entry in sorted(inventory.items()):
        source_status = source_statuses.get(name)
        if (
            entry.get("status") == "pending-review"
            and source_status not in {None, "pending-review"}
        ):
            add_error(
                errors,
                f"catalog/sources.yaml: pending-review skill {name} must not have status "
                f"{source_status}",
            )

    validate_privacy(errors)

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Validation passed: {len(skill_dirs)} skills checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
