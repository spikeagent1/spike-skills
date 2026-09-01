#!/usr/bin/env python3
"""Rewrite a vault's ledger records from `effects` to `activity` (decision 9A).

The rename is record-level, never a directory move: a record names its namespace
in its own frontmatter, and the index is rebuilt from the Markdown afterwards.
So this walks the Markdown, rewrites the three fields the rename touches -- the
namespace field (`namespace`, or whatever `datastore.field_map.namespace` in the
runtime's adapter calls it), `kind`, and `effect_state` -- and prints what has to
happen next. Nothing else in the file is read or written: the body is left byte
for byte as it was, and a record whose frontmatter does not name the old ledger
is not rewritten at all.

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


def namespace_fields(adapter: dict[str, Any] | None) -> tuple[str, ...]:
    """The frontmatter keys that can carry a record's namespace, contract first.

    Both are always rewritten: one vault may hold records written before an
    adapter's field map was applied, and a key that is not there is a no-op.
    """
    mapped = str(
        ((adapter or {}).get("datastore") or {}).get("field_map", {}).get(NAMESPACE_FIELD)
        or ""
    ).strip()
    fields = [NAMESPACE_FIELD]
    if mapped and mapped != NAMESPACE_FIELD:
        fields.append(mapped)
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

    fields = namespace_fields(adapter)
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
