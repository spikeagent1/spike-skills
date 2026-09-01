#!/usr/bin/env python3
"""SKILL.md frontmatter: the parser, the key allowlist, and the description rules.

Also the version and launcher-listing checks, which read nothing but the
frontmatter and the catalog entry beside it.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

from . import context
from .context import add_error, catalog_scalar

FRONTMATTER_ALLOWED_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)


METADATA_NS = "spike-os"


METADATA_KEYS = frozenset(
    {"version", "runtime", "reads_from", "writes_to", "capabilities"}
)


# A source SKILL.md nests exactly one level under `metadata`; `metadata` is 0,
# the namespace 1, its keys 2. Rendered runtime output may go one deeper, which
# only a caller that opts in with `parse_frontmatter(..., max_depth=...)` reads.
METADATA_MAX_DEPTH = 2


# Never valid: runtime coupling and a second version source of truth.
FRONTMATTER_REJECTED_KEYS = frozenset({"triggers", "tools", "version"})


FRONTMATTER_PARSE_ERRORS = "__parse_errors__"


DESCRIPTION_MAX_CHARS = 300


DESCRIPTION_TRIGGER_RE = re.compile(r"\buse when\b", re.IGNORECASE)


DESCRIPTION_FORBIDDEN_RE = re.compile(
    r"\b(spike|tapan)\b|\bI can\b|\byou can use\b", re.IGNORECASE
)


BLOCK_SCALAR_RE = re.compile(r"[|>][+-]?\d*")


# Every skill carries metadata.spike-os.version; flipped on in T25 with the v1
# path's deletion.
REQUIRE_VERSION = True


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


LISTING_BUDGET_WARN_RATIO = 0.8


SKILL_LISTING_MAX_CHARS = 1536


def _frontmatter_value(raw: str) -> Any:
    """A frontmatter scalar or flow list (`[a, b]`) from its raw right-hand side."""
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [catalog_scalar(item) for item in inner.split(",") if item.strip()]
    return catalog_scalar(value)


def parse_frontmatter(text: str, max_depth: int = METADATA_MAX_DEPTH) -> dict[str, Any] | None:
    """Every top-level frontmatter key, or None when the block is absent.

    This is not a YAML parser; it accepts the deliberately small subset the
    repository writes, and reports anything outside it rather than guessing:

    - two-space indentation, one step per nesting level;
    - scalars (quoted or bare, with a trailing ` # comment` stripped);
    - block lists (`- x`) and flow lists (`[a, b]`);
    - exactly one nesting level under `metadata`
      (`metadata: {spike-os: {...}}`), whose values are scalars or lists;
    - no block scalars (`>`, `|`), no anchors, no multi-document streams.

    Anything else -- deeper nesting, a nested map under a key other than
    `metadata`, a block scalar, an unparsable line -- is recorded under
    `FRONTMATTER_PARSE_ERRORS` so `validate_frontmatter` reports it verbatim
    without re-parsing.

    `max_depth` raises the nesting ceiling for a caller reading rendered runtime
    output rather than a source SKILL.md: `tools/check_staging.py` reads
    `metadata.<runtime>.requires.<bucket>`, one level past what a source file may
    write. A source skill is always parsed at the default.
    """
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None

    data: dict[str, Any] = {}
    problems: list[str] = []
    containers: dict[int, dict[str, Any]] = {0: data}
    open_key: dict[int, str] = {}
    # Indent of a rejected block scalar, whose continuation lines are skipped so
    # they do not each produce their own unparsable-line noise.
    skipped_indent: int | None = None

    for raw in match.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if skipped_indent is not None:
            if indent > skipped_indent:
                continue
            skipped_indent = None

        if stripped.startswith("- ") or stripped == "-":
            depth = max(indent // 2 - 1, 0)
            key = open_key.get(depth)
            container = containers.get(depth)
            if key is None or container is None:
                problems.append(f"list item {stripped!r} has no parent key")
                continue
            if not isinstance(container.get(key), list):
                container[key] = []
            container[key].append(_frontmatter_value(stripped[1:]))
            continue

        field = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", stripped)
        if field is None:
            problems.append(f"unparsable line {stripped!r}")
            continue

        depth = indent // 2
        if depth > max_depth:
            problems.append(f"key {field.group(1)!r} nests deeper than metadata.<namespace>")
            continue
        container = containers.get(depth)
        if container is None:
            problems.append(f"key {field.group(1)!r} is indented under no parent key")
            continue
        if depth >= 1 and open_key.get(0) != "metadata":
            problems.append(
                f"key {field.group(1)!r} nests under {open_key.get(0)!r}; "
                "only 'metadata' may hold a nested mapping"
            )
            continue

        key, raw_value = field.group(1), field.group(2)
        if key in container:
            problems.append(f"duplicate key {key!r}")
        if BLOCK_SCALAR_RE.fullmatch(raw_value.strip()):
            problems.append(
                f"key {key!r} uses a block scalar ({raw_value.strip()}); "
                f"block scalars (>, |) are not supported in frontmatter -- "
                f"put the value on one line, quoted if needed"
            )
            container[key] = ""
            containers.pop(depth + 1, None)
            skipped_indent = indent
        elif raw_value.strip():
            container[key] = _frontmatter_value(raw_value)
            containers.pop(depth + 1, None)
        else:
            # Empty right-hand side: a block list or a nested map follows.
            container[key] = {}
            containers[depth + 1] = container[key]
        open_key[depth] = key
        for deeper in [level for level in open_key if level > depth]:
            open_key.pop(deeper)

    # A key opened for a block list that never received items stays an empty
    # mapping; normalize it to the empty list the author meant.
    for container in list(containers.values()):
        for key, value in list(container.items()):
            if value == {} and key != "metadata":
                container[key] = []

    if problems:
        data[FRONTMATTER_PARSE_ERRORS] = problems
    return data


# Thin alias: `tools/evalrunner/cases.py` still imports this name. Removed in T25.
frontmatter = parse_frontmatter


def validate_frontmatter(
    rel: Path,
    meta: dict[str, Any],
    errors: list[str],
) -> None:
    """The frontmatter carries only the agentskills.io keys plus metadata.spike-os."""
    for problem in meta.get(FRONTMATTER_PARSE_ERRORS, []):
        add_error(errors, f"{rel}/SKILL.md: frontmatter {problem}")

    allowlist = ", ".join(sorted(FRONTMATTER_ALLOWED_KEYS))

    for key in sorted(k for k in meta if k != FRONTMATTER_PARSE_ERRORS):
        if key in FRONTMATTER_REJECTED_KEYS:
            add_error(
                errors,
                f"{rel}/SKILL.md: frontmatter key {key!r} is never allowed; "
                f"allowed keys are {allowlist}",
            )
        elif key in FRONTMATTER_ALLOWED_KEYS:
            continue
        else:
            add_error(
                errors,
                f"{rel}/SKILL.md: unknown frontmatter key {key!r}; "
                f"allowed keys are {allowlist}",
            )

    metadata = meta.get("metadata")
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        add_error(errors, f"{rel}/SKILL.md: frontmatter metadata must be a mapping")
        return
    for namespace in sorted(metadata):
        if namespace != METADATA_NS:
            add_error(
                errors,
                f"{rel}/SKILL.md: frontmatter metadata may only contain "
                f"{METADATA_NS!r}, found {namespace!r}",
            )
            continue
        block = metadata[namespace]
        if not isinstance(block, dict):
            add_error(
                errors,
                f"{rel}/SKILL.md: frontmatter metadata.{METADATA_NS} must be a mapping",
            )
            continue
        for key in sorted(set(block) - METADATA_KEYS):
            add_error(
                errors,
                f"{rel}/SKILL.md: frontmatter metadata.{METADATA_NS} key {key!r} is "
                f"not one of {', '.join(sorted(METADATA_KEYS))}",
            )


def validate_description(rel: Path, description: object, errors: list[str]) -> None:
    """The contract_version 2 description rule (design-hygiene 1)."""
    if not isinstance(description, str) or not description.strip():
        add_error(errors, f"{rel}/SKILL.md: description must be a non-empty string")
        return

    text = description.strip()
    if len(text) > DESCRIPTION_MAX_CHARS:
        add_error(
            errors,
            f"{rel}/SKILL.md: description is {len(text)} characters; "
            f"the limit is {DESCRIPTION_MAX_CHARS}",
        )
    if not DESCRIPTION_TRIGGER_RE.search(text):
        add_error(errors, f"{rel}/SKILL.md: description must name its triggers with 'Use when'")
    forbidden = DESCRIPTION_FORBIDDEN_RE.search(text)
    if forbidden is not None:
        add_error(
            errors,
            f"{rel}/SKILL.md: description uses forbidden phrasing {forbidden.group(0)!r}",
        )


def skill_body(text: str) -> str:
    """The SKILL.md below the frontmatter; the frontmatter has its own rules."""
    match = re.match(r"^---\n.*?\n---\n", text, re.DOTALL)
    return text[match.end():] if match else text


def without_fenced_blocks(body: str) -> str:
    """The body with every fenced code block's contents removed.

    A fenced block is rendered, not performed: a record template, a worked
    example, or another skill's object pattern quoted inside one is not this
    skill naming a thing it touches. The fence lines themselves stay, so line
    counts and anything that reads structure around them are unchanged.
    """
    kept: list[str] = []
    inside = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            kept.append(line)
            continue
        kept.append("" if inside else line)
    return "\n".join(kept)


def spike_os_block(meta: dict[str, Any]) -> dict[str, Any]:
    """`metadata.spike-os`, or an empty mapping when it is absent or malformed."""
    metadata = meta.get("metadata")
    block = metadata.get(METADATA_NS) if isinstance(metadata, dict) else None
    return block if isinstance(block, dict) else {}


def _declared_list(value: object) -> list[str]:
    """A frontmatter scalar or list read as a list of non-empty strings."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def validate_version(
    rel: Path, meta: dict[str, Any], entry: dict[str, str] | None, errors: list[str]
) -> None:
    """metadata.spike-os.version: semver, and the string catalog/approved.yaml carries."""
    version = spike_os_block(meta).get("version")
    declared = version.strip() if isinstance(version, str) else ""
    if not SEMVER_RE.match(declared):
        add_error(
            errors,
            f"{rel}/SKILL.md: metadata.{METADATA_NS}.version must be a semver like "
            f"1.0.0, found {version!r}",
        )
        return
    catalogued = str((entry or {}).get("version", "")).strip()
    if not catalogued:
        add_error(
            errors,
            f"catalog/approved.yaml: {rel.name} has no version to match "
            f"metadata.{METADATA_NS}.version {declared!r}",
        )
    elif declared != catalogued:
        add_error(
            errors,
            f"{rel}/SKILL.md: metadata.{METADATA_NS}.version {declared!r} does not "
            f"match catalog/approved.yaml version {catalogued!r}",
        )


def installer_module() -> Any:
    """`tools/install_skill.py`, imported lazily.

    It imports this module, so the import cannot sit at the top of the file.
    """
    return importlib.import_module("tools.install_skill")


def rendered_listing_chars(description: str) -> int:
    """Characters an adapter that emits `when_to_use` spends listing one skill.

    The renderer is the installer's, not a proxy for it: the field is the
    description's own "Use when" clause, so twice the description was an
    over-estimate for a long description and an under-estimate for none at all.
    """
    try:
        clause = installer_module().trigger_clause(description)
    except (ImportError, AttributeError):  # pragma: no cover - installer present
        clause = None
    return len(description) + len(clause or "")


LISTING_BUDGET_KEY = "max_skills_prompt_chars"


VALIDATOR_BUDGET_SOURCE = "the validator's own LISTING_BUDGET_CHARS"


def listing_budget(adapters: dict[str, dict[str, Any]] | None) -> tuple[int, str]:
    """The library listing budget in force, and the source that set it.

    The number stands for a value the runtime configures -- OpenClaw's
    `skills.limits.maxSkillsPromptChars` -- so an adapter that declares
    `limits.max_skills_prompt_chars` is the authority for its own listing. Where
    more than one runtime declares one, the smallest applies: the library has to
    fit every runtime its skills claim. Where none does, the validator's own
    default applies, and the caller says which of the two it was.
    """
    declared: dict[str, int] = {}
    for runtime, adapter in (adapters or {}).items():
        value = ((adapter or {}).get("limits") or {}).get(LISTING_BUDGET_KEY)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            declared[str(runtime)] = value
    if not declared:
        return context.LISTING_BUDGET_CHARS, VALIDATOR_BUDGET_SOURCE
    runtime = min(declared, key=lambda name: (declared[name], name))
    return declared[runtime], f"adapters/{runtime}/adapter.yaml"


def validate_listing_budget(
    inventory: dict[str, dict[str, str]],
    errors: list[str],
    warning_sink: list[str],
    adapters: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Each skill's launcher listing, and the library total, against the budget.

    A runtime lists a skill as `name: description`; an adapter that emits a
    separate `when_to_use` field also spends the description's "Use when" clause,
    and that pair is what the per-skill cap bounds. The library total is held to
    whichever budget `listing_budget` puts in force, and the message names it.
    """
    budget, source = listing_budget(adapters)
    total = 0
    for name in sorted(inventory):
        path = context.SKILLS / name / "SKILL.md"
        if not path.exists():
            continue
        meta = parse_frontmatter(path.read_text(encoding="utf-8")) or {}
        description = meta.get("description")
        if not isinstance(description, str):
            continue
        listing = rendered_listing_chars(description)
        if listing > SKILL_LISTING_MAX_CHARS:
            add_error(
                errors,
                f"skills/{name}/SKILL.md: listing entry is at most {listing} "
                f"characters; the per-skill budget is {SKILL_LISTING_MAX_CHARS}",
            )
        total += len(f"{name}: {description}")

    if total > budget:
        add_error(
            errors,
            f"catalog/approved.yaml: the library listing is {total} characters; "
            f"the budget is {budget}, from {source}",
        )
    elif total > budget * LISTING_BUDGET_WARN_RATIO:
        warning_sink.append(
            f"catalog/approved.yaml: the library listing is {total} characters, over "
            f"{int(LISTING_BUDGET_WARN_RATIO * 100)}% of the "
            f"{budget}-character budget from {source}"
        )
