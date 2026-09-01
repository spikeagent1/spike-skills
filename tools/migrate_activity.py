#!/usr/bin/env python3
"""Rewrite a vault's ledger records from `effects` to `activity` (decision 9A).

The rename is record-level, never a directory move: a record names its namespace
in its own frontmatter, and the index is rebuilt from the Markdown afterwards.
So this walks the Markdown, rewrites the three fields the rename touches -- the
namespace field, `kind`, and `effect_state` -- and prints what has to happen
next. Nothing else in the file is read or written: the body is left byte for byte
as it was, and a record whose frontmatter does not name the old ledger is not
rewritten at all.

The namespace field is read from *every* adapter's `datastore.field_map`, not
only the selected runtime's: gbrain names it `type` (`gbrain list --type
<namespace>`), the claude-code adapter's field map says so, and the openclaw
adapter -- the default runtime, over the same gbrain -- declares no map at all.
Reading one adapter left `type: effects` behind while `kind` and the state moved,
which is a half-migrated record reported as a success.

The other half of that guard is failing closed: a record whose frontmatter
carries `kind: effect` or `effect_state` but no namespace field naming the old or
the new ledger cannot be migrated by this tool, so the run refuses -- naming the
record and writing nothing at all, rather than moving two fields out of three.

A run is a preview unless `--apply` is passed. It is idempotent: a second run
over a migrated vault reports no file to change.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Sequence

ROOT = Path(__file__).resolve().parents[1]

if __package__ in (None, ""):  # pragma: no cover - one branch always runs.
    sys.path.insert(0, str(ROOT))

from tools import contracts_check

OLD_NAMESPACE = "effects"
NEW_NAMESPACE = "activity"
OLD_KIND = "effect"
NEW_KIND = "activity"
OLD_STATE_FIELD = "effect_state"
NEW_STATE_FIELD = "activity_state"

# The contract's own name for the field. An adapter may rename it -- the
# claude-code vault calls it `type` -- and `datastore.field_map` is where it says
# so, which is why the field is resolved from the adapter rather than assumed.
NAMESPACE_FIELD = "namespace"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)


class FileChange(NamedTuple):
    """One record's rewrite: the file, and the frontmatter lines that changed."""

    path: Path
    changes: tuple[str, ...]
    text: str


def adapter_namespace_field(adapter: dict[str, Any] | None) -> str:
    """What one adapter's `datastore.field_map` calls the namespace field, or `""`."""
    mapped = str(
        ((adapter or {}).get("datastore") or {}).get("field_map", {}).get(NAMESPACE_FIELD)
        or ""
    ).strip()
    return "" if mapped == NAMESPACE_FIELD else mapped


def adapter_namespace_fields(root: Path | None = None) -> tuple[str, ...]:
    """Every runtime's name for the namespace field, not only the selected one's.

    An adapter that declares no field map contributes nothing, and one that
    declares the same name as another contributes it once. Reading only the
    selected runtime's map is what let an openclaw record keep `type: effects`
    while its `kind` moved: that adapter has no map, and the same gbrain names
    the field `type` on both runtimes.
    """
    mapped: list[str] = []
    for runtime in contracts_check.RUNTIMES:
        try:
            adapter = contracts_check.load_adapter(runtime, root or ROOT)
        except (OSError, contracts_check.ContractParseError):
            continue
        field = adapter_namespace_field(adapter)
        if field and field not in mapped:
            mapped.append(field)
    return tuple(mapped)


def namespace_fields(mapped: Sequence[str] = ()) -> tuple[str, ...]:
    """The frontmatter keys that can carry a record's namespace, contract first.

    Every one is rewritten: a vault may hold records written on either side of an
    adapter's field map, and a key that is not there is a no-op.
    """
    fields = [NAMESPACE_FIELD]
    fields.extend(name for name in mapped if name and name not in fields)
    return tuple(fields)


def _rewrite_value(line: str, key: str, old: str, new: str) -> str | None:
    """`key: old` -> `key: new` on one frontmatter line, quotes tolerated."""
    match = re.fullmatch(rf"(\s*{re.escape(key)}:\s*)([\"']?){re.escape(old)}\2(\s*)", line)
    return f"{match.group(1)}{match.group(2)}{new}{match.group(2)}{match.group(3)}" if match else None


def rewrite_frontmatter(text: str, fields: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    """The file's text with its ledger frontmatter renamed, and what changed.

    A file with no frontmatter, or whose frontmatter names no ledger field, comes
    back unchanged with an empty change list.
    """
    match = FRONTMATTER_RE.match(text)
    if match is None:
        return text, ()

    block = match.group(1)
    lines = block.split("\n")
    changes: list[str] = []
    for index, line in enumerate(lines):
        for field in fields:
            rewritten = _rewrite_value(line, field, OLD_NAMESPACE, NEW_NAMESPACE)
            if rewritten is not None:
                lines[index] = rewritten
                changes.append(f"{field}: {OLD_NAMESPACE} -> {NEW_NAMESPACE}")
                break
        else:
            rewritten = _rewrite_value(lines[index], "kind", OLD_KIND, NEW_KIND)
            if rewritten is not None:
                lines[index] = rewritten
                changes.append(f"kind: {OLD_KIND} -> {NEW_KIND}")
                continue
            key = re.fullmatch(rf"(\s*){OLD_STATE_FIELD}(:.*)", lines[index])
            if key is not None:
                lines[index] = f"{key.group(1)}{NEW_STATE_FIELD}{key.group(2)}"
                changes.append(f"{OLD_STATE_FIELD} -> {NEW_STATE_FIELD}")

    if not changes:
        return text, ()
    return text[: match.start(1)] + "\n".join(lines) + text[match.end(1) :], tuple(changes)


def plan(vault: Path, fields: Sequence[str]) -> list[FileChange]:
    """Every record under `vault` this migration would rewrite, in path order."""
    planned: list[FileChange] = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"skipped {path}: {exc}")
            continue
        rewritten, changes = rewrite_frontmatter(text, fields)
        if changes:
            planned.append(FileChange(path, changes, rewritten))
    return planned


LEDGER_KIND_RE = re.compile(rf"^\s*kind:\s*[\"']?{OLD_KIND}[\"']?\s*$", re.MULTILINE)
LEDGER_STATE_RE = re.compile(rf"^\s*{OLD_STATE_FIELD}:", re.MULTILINE)


def unmigratable(text: str, fields: Sequence[str]) -> str:
    """Why this record cannot be migrated, or `""` when it can.

    A record that says `kind: effect` or carries an `effect_state` field is a
    ledger record; if none of the known namespace fields names the old ledger or
    the new one, this tool has nothing to move it to, and moving the other two
    fields would leave the record half-renamed. That is the case to refuse.
    """
    match = FRONTMATTER_RE.match(text)
    if match is None:
        return ""
    block = match.group(1)
    if not (LEDGER_KIND_RE.search(block) or LEDGER_STATE_RE.search(block)):
        return ""
    for field in fields:
        found = re.search(
            rf"^\s*{re.escape(field)}:\s*[\"']?([^\"'\s]+)[\"']?\s*$", block, re.MULTILINE
        )
        if found is None:
            continue
        if found.group(1) in (OLD_NAMESPACE, NEW_NAMESPACE):
            return ""
        return (
            f"is a ledger record ({OLD_KIND}/{OLD_STATE_FIELD}) whose {field} says "
            f"{found.group(1)!r}, neither {OLD_NAMESPACE!r} nor {NEW_NAMESPACE!r}"
        )
    return (
        f"is a ledger record ({OLD_KIND}/{OLD_STATE_FIELD}) with no namespace field "
        f"({', '.join(fields)}) to rewrite"
    )


def refusals(vault: Path, fields: Sequence[str]) -> list[tuple[Path, str]]:
    """Every record under `vault` this migration refuses to touch, in path order."""
    found: list[tuple[Path, str]] = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        reason = unmigratable(text, fields)
        if reason:
            found.append((path, reason))
    return found


def body_mentions(vault: Path) -> list[Path]:
    """Records whose body still says `effect_state` after the frontmatter moves.

    The migration rewrites frontmatter only, so these are reported rather than
    edited: prose is the author's, and a body sentence is not a record field.
    """
    found: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        match = FRONTMATTER_RE.match(text)
        body = text[match.end() :] if match else text
        if OLD_STATE_FIELD in body:
            found.append(path)
    return found


def reindex_reminder(runtime: str, adapter: dict[str, Any] | None) -> list[str]:
    """What the operator has to do after the files change, quoted from the adapter.

    `adapters/<runtime>/adapter.yaml` attests no reindex subcommand, so none is
    printed: the reminder names the store and the health check the adapter does
    attest, and leaves the rebuild step to the runtime that owns it (F2).
    """
    vocabulary = (adapter or {}).get("vocabulary") or {}

    def bound(key: str) -> str:
        return str((vocabulary.get(key) or {}).get("value") or "").strip() or "unknown"

    return [
        "",
        "Reindex, then verify:",
        f"- The Markdown is canonical and the index is rebuilt from it, so rebuild",
        f"  the index of {bound('owner_datastore')} before trusting search.",
        f"- Confirm with the {runtime} runtime health check: {bound('runtime_health_check')}.",
        f"- adapters/{runtime}/adapter.yaml attests no reindex subcommand; run the"
        " rebuild",
        "  step the runtime itself documents rather than a command invented here.",
    ]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate_activity.py",
        description="Rewrite effects/ ledger records to activity/ in a vault (9A).",
    )
    parser.add_argument("--vault", required=True, help="the vault root to walk")
    parser.add_argument(
        "--runtime",
        default="openclaw",
        choices=list(contracts_check.RUNTIMES),
        help="whose adapter names the namespace field and the reindex step",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the changes; otherwise preview only"
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(list(argv or []))
    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        print(f"migrate_activity.py: {vault} is not a directory", file=sys.stderr)
        return 2

    try:
        adapter = contracts_check.load_adapter(args.runtime, ROOT)
    except (OSError, contracts_check.ContractParseError) as exc:
        print(f"migrate_activity.py: adapters/{args.runtime}: {exc}", file=sys.stderr)
        return 2

    fields = namespace_fields(adapter_namespace_fields())
    refused = refusals(vault, fields)
    if refused:
        print(
            "migrate_activity.py: refusing to migrate; nothing was written",
            file=sys.stderr,
        )
        for path, reason in refused:
            print(f"- {path} {reason}", file=sys.stderr)
        return 1

    planned = plan(vault, fields)
    verb = "rewrote" if args.apply else "would rewrite"
    for change in planned:
        if args.apply:
            change.path.write_text(change.text, encoding="utf-8")
        print(f"{verb} {change.path}: {', '.join(change.changes)}")

    print(f"\n{len(planned)} record(s) {verb}; namespace field(s) read: {', '.join(fields)}")
    if not args.apply:
        print("preview only; pass --apply to write")
    for path in body_mentions(vault):
        print(f"note: {path} still says {OLD_STATE_FIELD} in its body; left as written")
    for line in reindex_reminder(args.runtime, adapter):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
