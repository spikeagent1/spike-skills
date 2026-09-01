#!/usr/bin/env python3
"""Resolve one action against the owner's `autonomy/` contracts (decision 2A/4A).

The one deterministic definition of "covered": `skills/autonomy`, the honoring
skills, and the tests all ask this module rather than each re-reading the
grammar. It is a pure library over records a caller hands it, plus a CLI that
reads record files from a directory for tests and ops -- it opens no datastore
and takes no fallback ladder, because the caller's runtime is what knows how to
read a namespace.

The grammar is `contracts/datastore.md`'s and no other: `skill-pattern` and
`object-pattern` are each an exact string, a `prefix/*`, or `*`, never a regular
expression. Everything that could widen autonomy fails closed instead
(`contracts/capabilities.yaml`, `on_ambiguity: fail_closed`):

- a pattern that is neither form parses to nothing, so its record matches nothing;
- a record past its `expires`, superseded, or not `active` never matches;
- a capability whose `contract_eligible` flag is false, or that the enum does not
  name at all, is refused before any record is read;
- a mutating capability aimed at `autonomy/` itself is always refused: no
  contract may widen the ring that holds it.

Where several live contracts match, any one of them authorizes (4A) -- `matches`
carries them all -- and `contract_id` is the one to cite: the longest
non-wildcard prefix across both patterns, ties broken lexicographically by id.
`Decision.contract_id` is the "contract id or none" the resolver promises; the
`reason` rides beside it because a refusal is disclosed in one line, and
`skipped` names each record that could not be read as live, so an expired or
malformed contract is visible rather than silent.

Usage:
  python3 tools/autonomy_check.py --records DIR --capability NAME --skill NAME \
      --object STRING [--now ISO-8601] [--json]

Exit status: 0 when a contract covers the action, 1 when none does.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Sequence

ROOT = Path(__file__).resolve().parents[1]

if __package__ in (None, ""):  # pragma: no cover - one branch always runs.
    sys.path.insert(0, str(ROOT))

from tools import contracts_check

KIND = "autonomy-contract"

# The contract's own name for the namespace field, and the name an adapter's
# `datastore.field_map` gives it (the claude-code vault calls it `type`). Both
# are read, so a record works whichever store it came out of.
NAMESPACE_FIELDS = ("namespace", "type")

# `status: active` is the envelope's word; the claude-code adapter maps it to
# `confirmed`, and a record read straight off that vault carries the mapped one.
LIVE_STATUSES = frozenset({"active", "confirmed"})

WILDCARD = "*"
PREFIX_WILDCARD = "/*"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):\s*(.*)$")


class Pattern(NamedTuple):
    """A parsed `skill-pattern` or `object-pattern`: its form and its literal part."""

    form: str  # "exact", "prefix", or "any"
    literal: str


class Decision(NamedTuple):
    """The resolution: what to cite, why, and what was passed over.

    `contract_id` is the contract to cite in the `activity/` record (M7), or
    None when nothing covers the action. `matches` holds every live match, since
    any one of them authorizes (4A). `reason` is the one-line disclosure, and
    `skipped` names each record read but not honored, with why.
    """

    contract_id: str | None
    reason: str
    matches: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def parse_pattern(pattern: object) -> Pattern | None:
    """One pattern in the grammar, or None when it is neither of the three forms.

    `*` is any; `prefix/*` is everything below `prefix/`; anything else must be a
    literal string with no `*` in it at all. A pattern outside the grammar is not
    guessed at -- it parses to None and matches nothing.
    """
    if not isinstance(pattern, str):
        return None
    text = pattern.strip()
    if not text:
        return None
    if text == WILDCARD:
        return Pattern("any", "")
    if text.endswith(PREFIX_WILDCARD):
        # The slash belongs to the literal: `tasks/*` requires `tasks/` in front
        # of whatever follows, and that is what its specificity counts.
        literal = text[: -1]
        if len(literal) > 1 and WILDCARD not in literal:
            return Pattern("prefix", literal)
        return None
    if WILDCARD in text:
        return None
    return Pattern("exact", text)


def pattern_matches(pattern: object, value: str) -> bool:
    """Whether `value` is covered by `pattern`; an unparsable pattern covers nothing."""
    parsed = parse_pattern(pattern)
    if parsed is None:
        return False
    if parsed.form == "any":
        return True
    if parsed.form == "prefix":
        return value.startswith(parsed.literal)
    return value == parsed.literal


def prefix_length(pattern: object) -> int:
    """How specific a pattern is: the length of its non-wildcard prefix."""
    parsed = parse_pattern(pattern)
    if parsed is None:
        return 0
    return len(parsed.literal)


def _instant(value: object) -> datetime | None:
    """An ISO-8601 date or datetime as a UTC instant, or None when unreadable.

    A naive value is read as UTC so every comparison is total: a record whose
    zone is unstated and a `now` that carries one still order against each other
    rather than raising.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def capability_entries(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """`contracts/capabilities.yaml`'s effect enum, by name."""
    capabilities = contracts_check.load_capabilities(root or ROOT)
    return {
        str(entry.get("name")): entry
        for entry in capabilities.get("effects") or []
        if isinstance(entry, dict) and entry.get("name")
    }


def never_eligible_namespace(root: Path | None = None) -> str:
    """The namespace no contract may authorize a write to, from the contract itself."""
    capabilities = contracts_check.load_capabilities(root or ROOT)
    block = capabilities.get("autonomy")
    value = (block or {}).get("never_eligible_namespace") if isinstance(block, dict) else None
    return str(value or "autonomy")


def _in_namespace(obj: str, namespace: str) -> bool:
    """Whether an object string names a record in `namespace`."""
    return obj == namespace or obj.startswith(namespace + "/")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or "").strip() or "<unnamed record>"


def _namespace_of(record: dict[str, Any]) -> str:
    for field in NAMESPACE_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_contract(record: dict[str, Any]) -> bool:
    """Whether a record is an `autonomy/` contract at all, rather than some other page."""
    if str(record.get("kind") or "").strip() != KIND:
        return False
    namespace = _namespace_of(record)
    return namespace in ("", "autonomy")


def _live(record: dict[str, Any], now: datetime) -> str:
    """Why a contract record is not live, or `""` when it is."""
    status = str(record.get("status") or "").strip()
    if not status:
        return "no status field, so nothing says it is live"
    if status != "superseded" and status not in LIVE_STATUSES:
        return f"status is {status!r}, not active"
    superseded_by = record.get("superseded-by")
    if status == "superseded" or (isinstance(superseded_by, str) and superseded_by.strip()):
        return "superseded"
    expires = record.get("expires")
    if expires is None or (isinstance(expires, str) and not expires.strip()):
        return ""
    instant = _instant(expires)
    if instant is None:
        return f"expires {expires!r} is not a readable date"
    if now >= instant:
        return f"expired at {expires}"
    return ""


def match(
    records: Iterable[dict[str, Any]],
    capability: str,
    skill: str,
    obj: str,
    now: str,
    *,
    root: Path | None = None,
) -> Decision:
    """Whether an owner-written contract covers this action, and which one to cite.

    `records` are `autonomy/` pages as their frontmatter mappings; anything else
    in the iterable is passed over. `now` is an ISO-8601 instant -- an unreadable
    one is refused rather than assumed, since every expiry is judged against it.
    """
    entries = capability_entries(root)
    entry = entries.get(capability)
    if entry is None:
        return Decision(
            None,
            f"contracts/capabilities.yaml names no capability {capability!r}",
        )
    if not entry.get("contract_eligible"):
        return Decision(
            None,
            f"{capability} is not contract_eligible in contracts/capabilities.yaml",
        )

    excluded = never_eligible_namespace(root)
    if not entry.get("readOnlyHint") and _in_namespace(obj, excluded):
        return Decision(
            None,
            f"a write to {excluded}/ is never covered by a contract",
        )

    instant = _instant(now)
    if instant is None:
        return Decision(None, f"the current instant {now!r} is not a readable date")

    matches: list[tuple[int, str]] = []
    skipped: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not _is_contract(record):
            continue
        record_id = _record_id(record)
        not_live = _live(record, instant)
        if not_live:
            skipped.append(f"{record_id}: {not_live}")
            continue
        if str(record.get("capability") or "").strip() != capability:
            continue
        unparsable = [
            field
            for field in ("skill-pattern", "object-pattern")
            if parse_pattern(record.get(field)) is None
        ]
        if unparsable:
            skipped.append(
                f"{record_id}: {' and '.join(unparsable)} is outside the grammar"
            )
            continue
        if not pattern_matches(record.get("skill-pattern"), skill):
            continue
        if not pattern_matches(record.get("object-pattern"), obj):
            continue
        specificity = prefix_length(record.get("skill-pattern")) + prefix_length(
            record.get("object-pattern")
        )
        matches.append((specificity, record_id))

    if not matches:
        return Decision(
            None,
            f"no live contract covers {capability} on {obj!r} for {skill!r}",
            (),
            tuple(skipped),
        )

    cited = sorted(matches, key=lambda item: (-item[0], item[1]))[0][1]
    names = tuple(sorted(name for _, name in matches))
    reason = (
        f"{cited} covers {capability} on {obj!r} for {skill!r}"
        if len(names) == 1
        else (
            f"{len(names)} live contracts cover {capability} on {obj!r} for "
            f"{skill!r}; {cited} is the most specific"
        )
    )
    return Decision(cited, reason, names, tuple(skipped))


def _scalar(raw: str) -> Any:
    """One frontmatter value: a quoted or bare scalar, with `null` read as None."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("null", "~", ""):
        return None
    if text in ("true", "false"):
        return text == "true"
    return text


def read_record(path: Path) -> dict[str, Any] | None:
    """One record file as its frontmatter mapping, or None when it carries none.

    Only the flat scalar fields a contract is made of are read; a nested block
    (`provenance:`) is left out rather than half-parsed, because nothing here
    matches on one.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    found = FRONTMATTER_RE.match(text)
    if found is None:
        return None
    record: dict[str, Any] = {}
    for line in found.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t", "-", "#")):
            continue
        key_value = KEY_RE.match(line)
        if key_value is None:
            continue
        record[key_value.group(1)] = _scalar(key_value.group(2))
    if not record:
        return None
    record.setdefault("id", path.stem)
    if not str(record.get("id") or "").strip():
        record["id"] = path.stem
    return record


def load_records(directory: Path) -> list[dict[str, Any]]:
    """Every Markdown record under a directory, as frontmatter mappings.

    A missing directory reads as no records: an unreadable store is the
    fail-closed case (2A), and no contract is exactly what no contract means.
    """
    path = Path(directory)
    if not path.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for file in sorted(path.rglob("*.md")):
        record = read_record(file)
        if record is not None:
            records.append(record)
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autonomy_check.py",
        description="Resolve one action against the owner's autonomy contracts.",
    )
    parser.add_argument(
        "--records", required=True, help="Directory of autonomy/ record files."
    )
    parser.add_argument(
        "--capability", required=True, help="An effect name from contracts/capabilities.yaml."
    )
    parser.add_argument("--skill", required=True, help="The skill about to act.")
    parser.add_argument("--object", required=True, dest="obj", help="What it would act on.")
    parser.add_argument(
        "--now",
        help="ISO-8601 instant expiries are judged against (default: now, UTC).",
    )
    parser.add_argument("--json", action="store_true", help="Print the decision as JSON.")
    parser.add_argument("--root", help="Repository root holding contracts/ (default: this one).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = args.now or datetime.now(timezone.utc).isoformat()
    decision = match(
        load_records(Path(args.records)),
        args.capability,
        args.skill,
        args.obj,
        now,
        root=Path(args.root) if args.root else None,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "contract_id": decision.contract_id,
                    "reason": decision.reason,
                    "matches": list(decision.matches),
                    "skipped": list(decision.skipped),
                },
                indent=2,
            )
        )
    else:
        covered = "covered" if decision.contract_id else "not covered"
        print(f"{covered}: {decision.reason}")
        for note in decision.skipped:
            print(f"  passed over -- {note}")
    return 0 if decision.contract_id else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    raise SystemExit(main())
