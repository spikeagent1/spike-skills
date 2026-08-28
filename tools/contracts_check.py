#!/usr/bin/env python3
"""Load the machine-readable contracts under `contracts/`.

`tools/validate_repo.py` reads frontmatter with line regexes rather than a YAML
library, and CI runs stock Python. The contract files are written in the same
small subset so they load the same way: two-space indentation, scalars, block
lists, flow lists, and a mapping nested under a key or a list item. Whole-line
`#` comments are ignored; trailing comments are not supported, so no contract
value contains one.

Run it directly for a smoke report of what the contracts declare.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"

APPROVALS = frozenset({"never_require", "preview_then_explicit", "turn_scoped", "never_autonomous"})
RESOURCE_CLASSES = frozenset({"fs", "exec", "network", "classified"})
HINT_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
NAMESPACE_STATUSES = frozenset({"active", "reserved"})
SYSTEMS_OF_RECORD = frozenset({"datastore", "provider", "scheduler"})
AXES = ("authority", "scope", "mutability", "provenance", "recoverability", "actionability")

KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):\s*(.*)$")
HEADING_RE = re.compile(r"^##[ \t]+(.+?)\s*$", re.MULTILINE)
LITERALS: dict[str, Any] = {"true": True, "false": False, "null": None, "": None}


class ContractParseError(ValueError):
    """A contract file left the supported YAML subset."""


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [] if not inner else [_scalar(part) for part in inner.split(",")]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in LITERALS:
        return LITERALS[text]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_contract_yaml(text: str) -> dict[str, Any]:
    """The supported subset, as nested dicts and lists."""
    root: dict[str, Any] = {}
    frames: list[tuple[int, Any]] = [(-1, root)]
    pending: tuple[int, dict[str, Any], str] | None = None

    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))

        if pending is not None:
            open_indent, open_container, open_key = pending
            if indent > open_indent:
                child: Any = [] if stripped.startswith("- ") else {}
                open_container[open_key] = child
                frames.append((indent, child))
            else:
                open_container[open_key] = None
            pending = None

        while len(frames) > 1 and indent < frames[-1][0]:
            frames.pop()
        container = frames[-1][1]

        if stripped.startswith("- "):
            if not isinstance(container, list):
                raise ContractParseError(f"line {number}: list item outside a list")
            item = stripped[2:].strip()
            match = KEY_RE.match(item)
            if match is None:
                container.append(_scalar(item))
                continue
            record: dict[str, Any] = {}
            container.append(record)
            frames.append((indent + 2, record))
            key, value = match.group(1), match.group(2).strip()
            if value:
                record[key] = _scalar(value)
            else:
                pending = (indent + 2, record, key)
            continue

        match = KEY_RE.match(stripped)
        if match is None:
            raise ContractParseError(f"line {number}: unparsable line {stripped!r}")
        if not isinstance(container, dict):
            raise ContractParseError(f"line {number}: key {stripped!r} inside a list")
        key, value = match.group(1), match.group(2).strip()
        if value:
            container[key] = _scalar(value)
        else:
            pending = (indent, container, key)

    if pending is not None:
        pending[1][pending[2]] = None
    return root


def _load(path: Path) -> dict[str, Any]:
    return parse_contract_yaml(path.read_text(encoding="utf-8"))


def load_capabilities(root: Path | None = None) -> dict[str, Any]:
    """`contracts/capabilities.yaml`: the closed effect enum."""
    return _load((root or ROOT) / "contracts" / "capabilities.yaml")


def load_datastore(root: Path | None = None) -> dict[str, Any]:
    """`contracts/datastore.yaml`: the envelope, enums, verbs, and namespaces."""
    return _load((root or ROOT) / "contracts" / "datastore.yaml")


def template_headings(root: Path | None = None) -> list[str]:
    """The H2s of `contracts/SKILL.template.md`, in file order."""
    path = (root or ROOT) / "contracts" / "SKILL.template.md"
    return HEADING_RE.findall(path.read_text(encoding="utf-8"))


def main() -> int:
    capabilities = load_capabilities()
    datastore = load_datastore()
    effects = capabilities.get("effects") or []
    namespaces = datastore.get("namespaces") or []
    active = [entry for entry in namespaces if entry.get("status") == "active"]
    reserved = [entry for entry in namespaces if entry.get("status") == "reserved"]

    print(
        f"contracts/capabilities.yaml v{capabilities.get('version')}: "
        f"{len(effects)} effects, "
        f"{len({entry.get('approval') for entry in effects})} approval modes, "
        f"{len({entry.get('resource_class') for entry in effects})} resource classes"
    )
    print(
        f"contracts/datastore.yaml v{datastore.get('version')}: "
        f"{len(namespaces)} namespaces ({len(active)} active, {len(reserved)} reserved), "
        f"{len(datastore.get('verbs') or [])} verbs, "
        f"{len(datastore.get('enums') or {})} enums"
    )
    print(f"contracts/SKILL.template.md: {len(template_headings())} canonical H2s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
