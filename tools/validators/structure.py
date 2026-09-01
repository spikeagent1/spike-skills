#!/usr/bin/env python3
"""The canonical section structure of a SKILL.md, and the files around it.

Section presence and order, body quality, the Contract section, cross-file
duplicate bodies, supporting files, in-skill agent configuration, and the
repository privacy sweep.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import context
from .context import add_error, git_files

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


# The contract_version 2 template (design-hygiene 1); the only shape the
# validator knows. `contract_version` stays a catalog field so a future bump has
# somewhere to declare itself.
CANONICAL_MANDATORY = (
    "Overview",
    "When to use",
    "When not to use",
    "Inputs",
    "Workflow",
    "Output contract",
    "Failure conditions",
    "Contract",
)


CANONICAL_OPTIONAL = (
    "Worked example",
    "Sources and freshness",
    "Privacy and mutations",
    "Safety boundaries",
    "Common mistakes",
)


CANONICAL_ORDER = (
    "Overview",
    "When to use",
    "When not to use",
    "Inputs",
    "Workflow",
    "Output contract",
    "Worked example",
    "Sources and freshness",
    "Privacy and mutations",
    "Safety boundaries",
    "Failure conditions",
    "Common mistakes",
    "Contract",
)


CROSS_FILE_DUPLICATE_EXEMPT = frozenset({"Contract"})


CONTRACT_LINK = "contracts/skill-contract.md"


SUPPORTING_FILE_EXEMPT = frozenset({"SKILL.md", "examples/evals.json", "routing-eval.jsonl"})


# Agent configuration inside a skill would be granted by `--add-dir` on eval runs
# and by every install of the package.
FORBIDDEN_SKILL_CONFIG = frozenset({"CLAUDE.md", "AGENTS.md", ".mcp.json", ".claude"})


MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


MARKDOWN_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)


PLACEHOLDER_RE = re.compile(
    r"\b(todo|tbd|placeholder|coming soon|fill this in|to be written)\b|^\s*(n/?a|none)\s*\.?\s*$",
    re.IGNORECASE,
)


def section_body(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^##+\s+{re.escape(heading)}\s*$\n(.*?)(?=^##+\s+|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return None
    return match.group(1).strip()


def normalized_body(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def validate_canonical_structure(rel: Path, text: str, errors: list[str]) -> list[str]:
    """The H2s of a contract_version 2 SKILL.md, in file order.

    Every mandatory section must be present, every section must come from
    `CANONICAL_ORDER`, and the order must be a subsequence of it.
    """
    headings = re.findall(r"^##[ \t]+(.+?)\s*$", text, re.MULTILINE)

    seen: set[str] = set()
    for heading in headings:
        if heading in seen:
            add_error(
                errors,
                f"{rel}/SKILL.md: canonical structure repeats section {heading!r}",
            )
        seen.add(heading)
    for heading in CANONICAL_MANDATORY:
        if heading not in seen:
            add_error(
                errors,
                f"{rel}/SKILL.md: canonical structure missing required section {heading!r}",
            )
    for heading in headings:
        if heading not in CANONICAL_ORDER:
            add_error(
                errors,
                f"{rel}/SKILL.md: canonical structure has unexpected section {heading!r}",
            )

    known = [heading for heading in headings if heading in CANONICAL_ORDER]
    expected = [heading for heading in CANONICAL_ORDER if heading in set(known)]
    if known != expected:
        add_error(
            errors,
            f"{rel}/SKILL.md: canonical structure is misordered: {' -> '.join(known)}; "
            f"expected {' -> '.join(expected)}",
        )
    return headings


def validate_public_section_bodies(
    rel: Path,
    text: str,
    sections: tuple[str, ...] | list[str],
    errors: list[str],
) -> dict[str, str]:
    """Body-quality checks for the public sections; returns their normalized bodies.

    The returned mapping feeds the repo-wide cross-file duplicate pass.
    """
    seen: dict[str, str] = {}
    bodies: dict[str, str] = {}
    for heading in dict.fromkeys(sections):
        occurrences = re.findall(
            rf"^##+\s+{re.escape(heading)}\s*$", text, re.MULTILINE
        )
        if len(occurrences) > 1:
            add_error(
                errors,
                f"{rel}/SKILL.md: public section {heading!r} appears "
                f"{len(occurrences)} times; expected exactly once",
            )
            continue
        body = section_body(text, heading)
        if body is None:
            continue
        normalized = normalized_body(body)
        if not normalized:
            add_error(errors, f"{rel}/SKILL.md: public section {heading!r} is blank")
            continue
        bodies[heading] = normalized
        if len(normalized) < 12 or PLACEHOLDER_RE.search(normalized):
            add_error(errors, f"{rel}/SKILL.md: public section {heading!r} is placeholder text")
        if heading == "Inputs" and "dependencies:" not in normalized:
            add_error(
                errors,
                f"{rel}/SKILL.md: public section 'Inputs' must declare 'Dependencies:'",
            )
        if heading == "Common mistakes" and not MARKDOWN_TABLE_ROW_RE.search(body):
            add_error(
                errors,
                f"{rel}/SKILL.md: public section 'Common mistakes' must be a "
                f"Markdown table",
            )
        previous = seen.get(normalized)
        if previous is not None:
            add_error(
                errors,
                f"{rel}/SKILL.md: public section {heading!r} duplicates {previous!r}",
            )
        else:
            seen[normalized] = heading
    return bodies


def validate_contract_section(
    rel: Path,
    text: str,
    skill_dir: Path,
    sources_entry: dict[str, str] | None,
    errors: list[str],
) -> None:
    """The contract_version 2 `## Contract` section: shared contract link + provenance."""
    body = section_body(text, "Contract")
    if body is None:
        add_error(errors, f"{rel}/SKILL.md: missing 'Contract' section")
        return

    if CONTRACT_LINK not in body:
        add_error(errors, f"{rel}/SKILL.md: Contract section must cite {CONTRACT_LINK}")
    else:
        targets = [
            target
            for target in MARKDOWN_LINK_RE.findall(body)
            if CONTRACT_LINK in target.split("#", 1)[0]
        ]
        if not targets:
            add_error(errors, f"{rel}/SKILL.md: Contract section must link to {CONTRACT_LINK}")
        for target in targets:
            resolved = (skill_dir / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                add_error(
                    errors,
                    f"{rel}/SKILL.md: contract link {target!r} does not resolve",
                )

    if "Provenance:" not in body:
        add_error(errors, f"{rel}/SKILL.md: Contract section must state 'Provenance:'")
        return

    classification = (sources_entry or {}).get("classification", "")
    # Read the provenance claim off the `Provenance:` line only: prose elsewhere in
    # the Contract section ("not adapted from anything") is not a classification.
    provenance = [
        line.split("Provenance:", 1)[1]
        for line in body.splitlines()
        if "Provenance:" in line
    ]
    says_adapted = any(
        re.search(r"\badapted\b", line, re.IGNORECASE) for line in provenance
    )
    if says_adapted and classification != "adapted":
        add_error(
            errors,
            f"{rel}/SKILL.md: Contract section says 'adapted' but catalog/sources.yaml "
            f"classification is {classification!r}",
        )
    if not says_adapted and classification == "adapted":
        add_error(
            errors,
            f"{rel}/SKILL.md: catalog/sources.yaml classifies this skill as 'adapted' "
            f"but the Contract section does not say so",
        )


def validate_cross_file_duplicates(
    section_bodies: dict[str, dict[str, str]], errors: list[str]
) -> None:
    """One error per section body that is verbatim identical in two or more skills.

    Callers pass contract_version 2 skills only: today's unmigrated library shares
    many verbatim `Dependencies`/`Provenance` bodies, and comparing those would
    turn the repo red before the rewrite lands.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for skill in sorted(section_bodies):
        for heading, body in sorted(section_bodies[skill].items()):
            if heading in CROSS_FILE_DUPLICATE_EXEMPT:
                continue
            groups.setdefault((heading, body), []).append(skill)

    for heading, _body in sorted(groups, key=lambda key: (key[0], key[1])):
        skills = sorted(groups[(heading, _body)])
        if len(skills) >= 2:
            # Prefixed with a file the way every other finding is, so the report
            # sorts and greps by path instead of hiding one class of error.
            add_error(
                errors,
                f"skills/{skills[0]}/SKILL.md: section {heading!r} body is "
                f"identical across {', '.join(skills)}",
            )


def validate_supporting_files(skill_dir: Path, text: str, errors: list[str]) -> None:
    """Every supporting file on disk is linked from SKILL.md, one level deep.

    The walk is the filesystem, not `git ls-files`: a new reference file that has
    not been staged yet is exactly the one an author forgets to link, and reading
    the index would let it pass locally and fail in CI. Dot-entries are skipped
    -- they are tooling artefacts, not content the skill loads.
    """
    rel = skill_dir.relative_to(context.ROOT)

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(skill_dir).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        sub = "/".join(relative_parts)
        if sub in SUPPORTING_FILE_EXEMPT:
            continue
        if sub not in text:
            add_error(
                errors,
                f"{rel}/SKILL.md: supporting file {sub!r} is not linked from SKILL.md",
            )
        if not sub.startswith("references/"):
            continue
        reference = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in ("](references/", "](scripts/"):
            if pattern in reference:
                add_error(
                    errors,
                    f"{rel.as_posix()}/{sub}: reference file links {pattern!r}; "
                    f"supporting files must be reachable one level deep from SKILL.md",
                )


def validate_skill_config(skill_dir: Path, errors: list[str]) -> None:
    """No agent configuration inside a skill: installs and eval runs would grant it."""
    rel = skill_dir.relative_to(context.ROOT)
    for path in sorted(skill_dir.rglob("*")):
        relative = path.relative_to(skill_dir)
        if path.name not in FORBIDDEN_SKILL_CONFIG:
            continue
        if any(part in FORBIDDEN_SKILL_CONFIG for part in relative.parts[:-1]):
            continue
        add_error(
            errors,
            f"{rel}/{relative.as_posix()}: agent configuration must not live inside a "
            f"skill directory",
        )


def validate_privacy(errors: list[str], tracked_paths: list[Path] | None = None) -> None:
    ignored = (context.ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in ("evals/workspaces/", ".env", "*.skill"):
        if required not in ignored:
            add_error(
                errors,
                f".gitignore: missing local/private generated-state pattern {required!r}",
            )

    for path in git_files() if tracked_paths is None else tracked_paths:
        rel = path.relative_to(context.ROOT).as_posix()
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
