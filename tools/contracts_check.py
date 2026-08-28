#!/usr/bin/env python3
"""Load the machine-readable contracts under `contracts/` and `adapters/`.

`tools/validate_repo.py` reads frontmatter with line regexes rather than a YAML
library, and CI runs stock Python. The contract files are written in the same
small subset so they load the same way: two-space indentation, scalars, block
lists, flow lists, and a mapping nested under a key or a list item. Whole-line
`#` comments are ignored; trailing comments are not supported, so no contract
value contains one.

Run it directly for a smoke report of what the contracts declare. The report
fails when a runtime adapter leaves a vocabulary term unbound or a datastore
namespace unmapped, so a term can never be defined for one runtime only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
ADAPTERS_DIR = ROOT / "adapters"

APPROVALS = frozenset({"never_require", "preview_then_explicit", "turn_scoped", "never_autonomous"})
RESOURCE_CLASSES = frozenset({"fs", "exec", "network", "classified"})
HINT_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
NAMESPACE_STATUSES = frozenset({"active", "reserved"})
SYSTEMS_OF_RECORD = frozenset({"datastore", "provider", "scheduler"})
AXES = ("authority", "scope", "mutability", "provenance", "recoverability", "actionability")
RUNTIMES = ("openclaw", "claude-code")
VOCABULARY_KINDS = frozenset(
    {"datastore", "provider", "channel", "path", "identity", "runtime", "governance"}
)
ADAPTER_MD_SECTIONS = (
    "## Vocabulary",
    "## Datastore",
    "## Providers",
    "## Channels and quiet hours",
    "## Identity files",
    "## Skills dir",
    "## Notes on fallbacks",
)
GLOSSARY_HEADING = "## R. Runtime vocabulary"

KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):\s*(.*)$")
BACKTICKED_RE = re.compile(r"`([^`]+)`")
NON_KEY_RE = re.compile(r"[^a-z0-9]+")
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


def load_vocabulary(root: Path | None = None) -> dict[str, Any]:
    """`adapters/vocabulary.yaml`: the neutral term list every adapter binds."""
    return _load((root or ROOT) / "adapters" / "vocabulary.yaml")


def load_adapter(runtime: str, root: Path | None = None) -> dict[str, Any]:
    """One `adapters/<runtime>/adapter.yaml`."""
    return _load((root or ROOT) / "adapters" / runtime / "adapter.yaml")


def load_adapters(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Every declared runtime adapter, keyed by runtime name."""
    return {runtime: load_adapter(runtime, root) for runtime in RUNTIMES}


def term_key(term: str) -> str:
    """The adapter mapping key for a vocabulary term: `agent's public journal` -> `agents_public_journal`."""
    return NON_KEY_RE.sub("_", term.lower().replace("'", "")).strip("_")


def glossary_terms(root: Path | None = None) -> list[str]:
    """The backticked terms of `contracts/skill-contract.md` section R, in file order.

    Backticked tokens holding a `/` are file or namespace paths, not terms.
    """
    path = (root or ROOT) / "contracts" / "skill-contract.md"
    text = path.read_text(encoding="utf-8")
    start = text.find(GLOSSARY_HEADING)
    if start < 0:
        raise ContractParseError(f"{path.name}: no {GLOSSARY_HEADING!r} section")
    body = text[start + len(GLOSSARY_HEADING) :]
    end = body.find("\n## ")
    if end >= 0:
        body = body[:end]
    ordered: list[str] = []
    for token in BACKTICKED_RE.findall(body):
        if "/" in token or token in ordered:
            continue
        ordered.append(token)
    return ordered


def missing_terms(adapter: dict[str, Any], vocabulary: dict[str, Any]) -> list[str]:
    """Vocabulary keys the adapter does not bind."""
    bound = adapter.get("vocabulary") or {}
    return [
        entry["key"] for entry in (vocabulary.get("terms") or []) if entry["key"] not in bound
    ]


def extra_terms(adapter: dict[str, Any], vocabulary: dict[str, Any]) -> list[str]:
    """Adapter bindings with no vocabulary term behind them."""
    declared = {entry["key"] for entry in (vocabulary.get("terms") or [])}
    return sorted(set(adapter.get("vocabulary") or {}) - declared)


def missing_namespaces(adapter: dict[str, Any], datastore: dict[str, Any]) -> list[str]:
    """Datastore namespaces the adapter gives no path for."""
    paths = (adapter.get("datastore") or {}).get("paths") or {}
    return [
        entry["name"]
        for entry in (datastore.get("namespaces") or [])
        if not str(paths.get(entry["name"]) or "").strip()
    ]


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

    vocabulary = load_vocabulary()
    terms = vocabulary.get("terms") or []
    kinds = {entry.get("kind") for entry in terms}
    print(
        f"adapters/vocabulary.yaml v{vocabulary.get('version')}: "
        f"{len(terms)} terms across {len(kinds)} kinds, "
        f"{sum(len(entry.get('aliases') or []) for entry in terms)} aliases"
    )

    gaps: list[str] = []
    glossary = glossary_terms()
    if [entry["term"] for entry in terms] != glossary:
        gaps.append(
            "adapters/vocabulary.yaml: terms do not match contracts/skill-contract.md section R"
        )
    for runtime, adapter in load_adapters().items():
        absent = missing_terms(adapter, vocabulary)
        unknown = extra_terms(adapter, vocabulary)
        unmapped = missing_namespaces(adapter, datastore)
        print(
            f"adapters/{runtime}/adapter.yaml v{adapter.get('version')}: "
            f"{len(adapter.get('vocabulary') or {})} terms bound, "
            f"{len((adapter.get('datastore') or {}).get('paths') or {})} namespaces mapped, "
            f"{len((adapter.get('datastore') or {}).get('verbs') or {})} verbs mapped"
        )
        for label, names in (
            ("unbound term", absent),
            ("unknown term", unknown),
            ("unmapped namespace", unmapped),
        ):
            gaps.extend(f"adapters/{runtime}/adapter.yaml: {label} {name}" for name in names)

    if gaps:
        print("Contract coverage failed:")
        for gap in gaps:
            print(f"- {gap}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
