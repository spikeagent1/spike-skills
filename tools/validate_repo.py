#!/usr/bin/env python3
"""Validate the portable skill library contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

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


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def parse_approved(errors: list[str]) -> set[str]:
    text = (ROOT / "catalog" / "approved.yaml").read_text(encoding="utf-8")
    names = set(re.findall(r"^\s+- name: ([a-z0-9-]+)\s*$", text, re.MULTILINE))
    if not names:
        add_error(errors, "catalog/approved.yaml: no approved skills found")
    return names


def parse_domain_releases(errors: list[str]) -> set[str]:
    text = (ROOT / "catalog" / "domains.yaml").read_text(encoding="utf-8")
    names: set[str] = set()
    in_released = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("released:"):
            in_released = True
            continue
        if in_released and stripped.startswith("- "):
            names.add(stripped[2:].strip())
            continue
        if in_released and stripped and not stripped.startswith("- "):
            in_released = False

    if not names:
        add_error(errors, "catalog/domains.yaml: no released skills found")
    return names


def eval_files(skill_dir: Path) -> list[Path]:
    candidates = (
        skill_dir / "examples" / "evals.json",
        skill_dir / "evals" / "evals.json",
        skill_dir / "routing-eval.jsonl",
    )
    return [path for path in candidates if path.exists()]


def validate_eval_file(skill: str, path: Path, errors: list[str]) -> None:
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


def validate_skill(
    skill_dir: Path,
    approved: set[str],
    released: set[str],
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
    if skill_dir.name not in approved:
        add_error(errors, f"{rel}: missing catalog/approved.yaml entry")
    if skill_dir.name != "skill-library-ops" and skill_dir.name not in released:
        add_error(errors, f"{rel}: missing catalog/domains.yaml released entry")

    files = eval_files(skill_dir)
    if not files:
        add_error(errors, f"{rel}: missing evals file")
    for path in files:
        validate_eval_file(skill_dir.name, path, errors)


def validate_privacy(errors: list[str]) -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in ("evals/workspaces/", ".env", "*.skill"):
        if required not in ignored:
            add_error(errors, f".gitignore: missing local/private generated-state pattern {required!r}")

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
    approved = parse_approved(errors)
    released = parse_domain_releases(errors)
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())

    for skill_dir in skill_dirs:
        validate_skill(skill_dir, approved, released, errors)

    for name in sorted(approved - {path.name for path in skill_dirs}):
        add_error(errors, f"catalog/approved.yaml: {name} has no skills/{name} directory")

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
