#!/usr/bin/env python3
"""Verify a staged runtime tree `tools/install_skill.py` already wrote.

The installer renders and stamps one skill at a time; nothing before this ran
its openclaw path over the whole library in a single pass. This re-reads what
is already on disk under `--dest` and checks the three things a bad render
would get wrong silently, without repeating install_skill's own logic:

- a runtime-specific value (`validate_repo.RUNTIME_SPECIFIC_RE`) leaking into
  a staged body, outside the `## Runtime binding` trailer the installer adds
  on purpose and which always names the runtime;
- a backticked vocabulary term the staged body uses that the target adapter
  binds no value for, or names by an alias rather than the canonical term
  (`install_skill.undefined_terms`);
- a `metadata.<runtime>.requires.*` block that disagrees with a fresh scan of
  its own Dependencies line (`install_skill.openclaw_requires`) -- the render
  and the bytes on disk drifting apart is exactly what a hand-edit or a stale
  stage would produce.

Exit 1 on any failure; stdlib only.

Usage:
  python3 tools/check_staging.py --runtime {openclaw,claude-code} --dest DIR
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, Sequence

try:
    from tools import install_skill, validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import install_skill  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
REQUIRES_BUCKETS = ("env", "bins", "config")
REQUIRES_LINE_RE = {
    bucket: re.compile(rf"^\s*{bucket}:\s*\[(.*)\]\s*$", re.MULTILINE)
    for bucket in REQUIRES_BUCKETS
}


class CheckContext(NamedTuple):
    """The three attributes `install_skill.undefined_terms` reads off a Context."""

    runtime: str
    adapter: dict[str, Any]
    vocabulary: dict[str, Any]


def staged_skills(dest: Path) -> list[Path]:
    """Every staged skill directory carrying a SKILL.md, under `dest/skills`."""
    skills_dir = dest / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(
        path for path in skills_dir.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
    )


def frontmatter_text(text: str) -> str | None:
    match = FRONTMATTER_RE.match(text)
    return match.group(1) if match else None


def staged_requires(frontmatter: str) -> dict[str, list[str]] | None:
    """The rendered `requires.{env,bins,config}` lists, read off the raw frontmatter.

    `validate_repo.parse_frontmatter` stops two levels under `metadata`, and
    `requires.*` is a third, so this reads the three fixed lines
    `install_skill.render_frontmatter` writes directly instead of reparsing.
    """
    buckets: dict[str, list[str]] = {}
    for bucket, pattern in REQUIRES_LINE_RE.items():
        match = pattern.search(frontmatter)
        if match is None:
            return None
        inner = match.group(1).strip()
        buckets[bucket] = [] if not inner else [item.strip() for item in inner.split(",")]
    return buckets


def check_runtime_specific(name: str, text: str) -> list[str]:
    """Zero `validate_repo.RUNTIME_SPECIFIC_RE` hits outside the rendered trailer.

    `## Runtime binding` is the installer's own addition and names the runtime
    by design ("Bound to adapter `openclaw`..."); scanning past it would flag
    every staged file for doing exactly what it is supposed to do.
    """
    body = validate_repo.skill_body(text)
    trailer_at = body.find(install_skill.TRAILER_HEADING)
    scoped = body if trailer_at < 0 else body[:trailer_at]
    return [
        f"{name}: runtime-specific token {hit!r} in the staged body"
        for hit in validate_repo.runtime_specific_hits(scoped)
    ]


def check_vocabulary_terms(name: str, text: str, context: CheckContext) -> list[str]:
    """Every backticked vocabulary term the staged body uses resolves in the adapter."""
    return install_skill.undefined_terms(name, text, context)


def check_requires(
    name: str,
    text: str,
    vocabulary: dict[str, Any],
    datastore: dict[str, Any],
    requires_declared: bool,
) -> list[str]:
    """The staged `requires.*` block matches a fresh scan of its own Dependencies line."""
    if not requires_declared:
        return []
    frontmatter = frontmatter_text(text)
    if frontmatter is None:
        return [f"{name}: staged SKILL.md has no frontmatter block"]
    staged = staged_requires(frontmatter)
    if staged is None:
        return [f"{name}: frontmatter carries no metadata.<runtime>.requires block"]
    expected = install_skill.openclaw_requires(
        validate_repo.skill_body(text), vocabulary, datastore
    )
    problems: list[str] = []
    for bucket in REQUIRES_BUCKETS:
        if staged[bucket] != expected[bucket]:
            problems.append(
                f"{name}: metadata.<runtime>.requires.{bucket} is {staged[bucket]} but "
                f"the Dependencies line implies {expected[bucket]}"
            )
    return problems


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_staging.py",
        description="Verify a staged runtime tree tools/install_skill.py already wrote.",
    )
    parser.add_argument("--runtime", required=True, choices=list(install_skill.RUNTIMES))
    parser.add_argument(
        "--dest", required=True, help="the staged workspace root, e.g. dist/openclaw/workspace"
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    dest = install_skill.expand(args.dest)
    skills = staged_skills(dest)
    if not skills:
        print(f"refused: no staged skills found under {dest / 'skills'}")
        return 1

    try:
        adapters = install_skill.load_contract("adapters")
        vocabulary = install_skill.load_contract("vocabulary")
        datastore = install_skill.load_contract("datastore")
    except install_skill.InstallError as exc:
        print(f"refused: {exc}")
        return 1

    adapter = adapters.get(args.runtime)
    if not adapter:
        print(f"refused: adapters/{args.runtime}/adapter.yaml: not loaded")
        return 1
    context = CheckContext(runtime=args.runtime, adapter=adapter, vocabulary=vocabulary)
    extra = (adapter.get("render") or {}).get("metadata_extra") or {}
    requires_declared = any(
        key.startswith(f"metadata.{args.runtime}.requires") for key in extra
    )

    runtime_findings: list[str] = []
    vocabulary_findings: list[str] = []
    requires_findings: list[str] = []
    for directory in skills:
        name = directory.name
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
        runtime_findings.extend(check_runtime_specific(name, text))
        vocabulary_findings.extend(check_vocabulary_terms(name, text, context))
        requires_findings.extend(
            check_requires(name, text, vocabulary, datastore, requires_declared)
        )

    findings = runtime_findings + vocabulary_findings + requires_findings
    for finding in findings:
        print(f"fail: {finding}")

    print(
        f"{args.runtime}: checked {len(skills)} staged skill(s) under {dest} -- "
        f"{len(runtime_findings)} runtime-specific hit(s), "
        f"{len(vocabulary_findings)} unresolved vocabulary term(s), "
        f"{len(requires_findings)} requires mismatch(es); "
        f"{len(findings)} finding(s) total"
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
