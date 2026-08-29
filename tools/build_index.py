#!/usr/bin/env python3
"""Generate `catalog/index.md` and `catalog/index.json` — the launcher's runtime index.

Joins every `skills/*/SKILL.md` frontmatter with `catalog/domains.yaml` (domain
grouping), `catalog/approved.yaml` (approval status), and `catalog/routing.yaml`
(cluster membership) into one table per domain, plus a "Not yet available"
block built from `contracts/datastore.yaml` reserved namespaces and each
domain's `next:` list. A skill is `unassigned` when it is approved and on disk
but named by no domain's `released:` list; `render()` still renders it (in its
own section) but `--check` treats it as an error.

`render()` and `render_json()` take no arguments and read the repository at
`tools.validate_repo.ROOT`, so `tools/validate_repo.py`'s `validate_catalog_index`
hook can import this file and diff its output against the committed
`catalog/` files without either module writing anything.

Usage: python3 tools/build_index.py [--check] [--json]
  (no flags)  write catalog/index.md and catalog/index.json
  --check     diff the rendered output against the committed files and flag
              any unassigned skill; exit 1 if either problem exists
  --json      with --check, report as a JSON object instead of a unified diff
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from typing import Any

try:
    from tools import validate_repo
except ImportError:  # pragma: no cover - direct-script invocation path.
    import validate_repo  # type: ignore[no-redef]

BADGE_LABELS: tuple[tuple[str, str], ...] = (
    ("readOnlyHint", "RO"),
    ("destructiveHint", "DESTR"),
    ("idempotentHint", "IDEM"),
    ("openWorldHint", "OPEN"),
)

TABLE_HEADER = "| skill | use when | version | runtime | effects | cluster |"
TABLE_RULE = "| --- | --- | --- | --- | --- | --- |"


def _as_list(value: object) -> list[str]:
    """A frontmatter field read as a list of strings, tolerant of a bare scalar."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _required(errors: list[str], rel: str) -> None:
    if errors:
        raise RuntimeError(f"{rel}: {'; '.join(errors)}")


def _parse_domains() -> list[dict[str, Any]]:
    """`catalog/domains.yaml` `domains:` entries, in file order.

    Each entry is `{"name", "released": [...], "next": [...]}`. Indent-aware,
    mirroring `validate_repo.parse_domain_lists`: a `- name:` line at the
    domain-list indent starts a new domain and closes whichever list was open,
    so an empty `next:` cannot swallow the domain that follows it, and the
    trailing `release_order:` / `selection_rules:` top-level keys (which reuse
    `- name` shaped indentation for neither) are never mistaken for a domain.
    """
    path = validate_repo.ROOT / "catalog" / "domains.yaml"
    text = path.read_text(encoding="utf-8")
    domains: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    active: list[str] | None = None
    active_indent = -1

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        name_match = re.match(r"^  - name:\s*(.+)$", line)
        if name_match:
            current = {"name": name_match.group(1).strip(), "released": [], "next": []}
            domains.append(current)
            active = None
            continue
        if current is None:
            continue
        if stripped.startswith("released:"):
            active, active_indent = current["released"], indent
            continue
        if stripped.startswith("next:"):
            active, active_indent = current["next"], indent
            continue
        if active is not None and stripped.startswith("- ") and indent > active_indent:
            active.append(stripped[2:].strip())
            continue
        active = None

    if not domains:
        raise RuntimeError("catalog/domains.yaml: no domains found")
    return domains


def _clusters_by_skill(clusters: dict[str, list[str]]) -> dict[str, list[str]]:
    """Skill name -> the cluster names listing it, in `routing.yaml` order.

    A skill may sit in more than one cluster (e.g. `briefing` is in both the
    `day` and `datastore-readers` clusters), so this is a one-to-many index.
    """
    by_skill: dict[str, list[str]] = {}
    for cluster_name, members in clusters.items():
        for member in members:
            by_skill.setdefault(member, []).append(cluster_name)
    return by_skill


def _load_skill_frontmatter() -> dict[str, dict[str, Any]]:
    """Skill name -> parsed `SKILL.md` frontmatter, for every `skills/*` directory."""
    frontmatter: dict[str, dict[str, Any]] = {}
    skills_dir = validate_repo.ROOT / "skills"
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        parsed = validate_repo.parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        frontmatter[skill_dir.name] = parsed or {}
    return frontmatter


def _build_row(
    name: str,
    meta: dict[str, Any],
    approved: dict[str, dict[str, str]],
    clusters_by_skill: dict[str, list[str]],
    capability_entries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    spike_os = validate_repo.spike_os_block(meta)
    effects = _as_list(spike_os.get("effects"))
    return {
        "name": name,
        "description": str(meta.get("description", "")),
        "version": str(spike_os.get("version", "")),
        "runtime": _as_list(spike_os.get("runtime")),
        "effects": effects,
        "hints": validate_repo.derived_hints(effects, capability_entries),
        "contract_version": str(approved.get(name, {}).get("contract_version", "")),
        "cluster": clusters_by_skill.get(name, []),
    }


def collect_index_data() -> dict[str, Any]:
    """Assemble the index as plain, JSON-serializable data in a stable key order.

    Fails closed: a malformed catalog file raises rather than silently
    rendering a partial or misleading index, so `validate_repo`'s
    `validate_catalog_index` hook surfaces it as `render() failed: ...`.
    """
    errors: list[str] = []
    approved = validate_repo.parse_catalog_inventory(errors)
    _required(errors, "catalog/approved.yaml")
    clusters = validate_repo.parse_routing_clusters(errors)
    _required(errors, "catalog/routing.yaml")
    capabilities = validate_repo.load_capabilities(errors, require=True) or {}
    _required(errors, "contracts/capabilities.yaml")
    datastore = validate_repo.load_datastore_contract(errors, require=True) or {}
    _required(errors, "contracts/datastore.yaml")

    frontmatter = _load_skill_frontmatter()
    domains = _parse_domains()
    clusters_by_skill = _clusters_by_skill(clusters)
    capability_entries = validate_repo.effect_enum(capabilities)
    approved_names = {
        name for name, entry in approved.items() if entry.get("status") == "approved"
    }

    assigned: set[str] = set()
    domain_entries: list[dict[str, Any]] = []
    for domain in domains:
        rows = []
        for skill_name in domain["released"]:
            if skill_name not in frontmatter or skill_name not in approved_names:
                continue
            assigned.add(skill_name)
            rows.append(
                _build_row(
                    skill_name, frontmatter[skill_name], approved, clusters_by_skill, capability_entries
                )
            )
        domain_entries.append(
            {"name": domain["name"], "skills": rows, "next": list(domain["next"])}
        )

    unassigned_names = sorted((approved_names & set(frontmatter)) - assigned)
    unassigned_rows = [
        _build_row(name, frontmatter[name], approved, clusters_by_skill, capability_entries)
        for name in unassigned_names
    ]

    reserved_namespaces = [
        {
            "name": str(entry.get("name", "")),
            "status": str(entry.get("status", "")),
            "system_of_record": str(entry.get("system_of_record", "")),
            "authority": str(entry.get("authority", "")),
        }
        for entry in (datastore.get("namespaces") or [])
        if entry.get("status") == "reserved"
    ]

    return {
        "generated_by": "tools/build_index.py",
        "domains": domain_entries,
        "unassigned": unassigned_rows,
        "reserved_namespaces": reserved_namespaces,
    }


def _badges(hints: dict[str, bool]) -> str:
    labels = [label for key, label in BADGE_LABELS if hints.get(key)]
    return " ".join(labels) if labels else "—"


def _skill_row_md(row: dict[str, Any]) -> str:
    description = row["description"].replace("|", "\\|")
    runtime = ", ".join(row["runtime"]) if row["runtime"] else "—"
    effects = ", ".join(f"`{effect}`" for effect in row["effects"]) if row["effects"] else "—"
    cluster = ", ".join(row["cluster"]) if row["cluster"] else "—"
    return (
        f"| `{row['name']}` | {description} | {row['version']} | {runtime} | "
        f"{_badges(row['hints'])} · {effects} | {cluster} |"
    )


def _domain_section_md(domain: dict[str, Any]) -> list[str]:
    lines = [f"## {domain['name']}", ""]
    if not domain["skills"]:
        lines.append("_No skills released yet in this domain._")
    else:
        lines.append(TABLE_HEADER)
        lines.append(TABLE_RULE)
        lines.extend(_skill_row_md(row) for row in domain["skills"])
    lines.append("")
    return lines


def _render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "<!--",
        "Generated by tools/build_index.py from catalog/domains.yaml,",
        "catalog/approved.yaml, catalog/routing.yaml, contracts/datastore.yaml, and",
        "every skills/*/SKILL.md frontmatter. Do not hand-edit; regenerate with",
        "`python3 tools/build_index.py`.",
        "-->",
        "",
        "# Skill index",
        "",
    ]

    for domain in data["domains"]:
        lines.extend(_domain_section_md(domain))

    if data["unassigned"]:
        lines.append("## Unassigned")
        lines.append("")
        lines.append(
            "Approved skills named by no `catalog/domains.yaml` domain. Fix the "
            "catalog before shipping."
        )
        lines.append("")
        lines.append(TABLE_HEADER)
        lines.append(TABLE_RULE)
        lines.extend(_skill_row_md(row) for row in data["unassigned"])
        lines.append("")

    lines.append("## Not yet available")
    lines.append("")
    if data["reserved_namespaces"]:
        lines.append("| namespace | status | system of record | authority |")
        lines.append("| --- | --- | --- | --- |")
        for namespace in data["reserved_namespaces"]:
            lines.append(
                f"| `{namespace['name']}` | {namespace['status']} | "
                f"{namespace['system_of_record']} | {namespace['authority']} |"
            )
        lines.append("")
    else:
        lines.append("_No reserved namespaces declared._")
        lines.append("")

    planned = [domain for domain in data["domains"] if domain["next"]]
    if planned:
        lines.append("Planned skills by domain, not yet released:")
        lines.append("")
        for domain in planned:
            names = ", ".join(f"`{name}`" for name in domain["next"])
            lines.append(f"- **{domain['name']}**: {names}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render() -> str:
    """`catalog/index.md`'s full text. No side effects; reads `validate_repo.ROOT`."""
    return _render_markdown(collect_index_data())


def _render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_json() -> str:
    """`catalog/index.json`'s full text: `collect_index_data()` in stable key order."""
    return _render_json(collect_index_data())


def _unified_diff(rel: str, committed: str, rendered: str) -> str:
    return "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def _check(md_text: str, json_text: str, data: dict[str, Any], as_json: bool) -> int:
    problems: list[str] = []
    if data["unassigned"]:
        names = ", ".join(row["name"] for row in data["unassigned"])
        problems.append(f"catalog/index.md: unassigned skill(s) with no domain: {names}")

    diffs: dict[str, str] = {}
    for rel, rendered in (("catalog/index.md", md_text), ("catalog/index.json", json_text)):
        path = validate_repo.ROOT / rel
        committed = path.read_text(encoding="utf-8") if path.exists() else ""
        if committed != rendered:
            diffs[rel] = _unified_diff(rel, committed, rendered)

    if not problems and not diffs:
        print("catalog/index.md and catalog/index.json are up to date.")
        return 0

    if as_json:
        print(json.dumps({"problems": problems, "diffs": diffs}, indent=2))
    else:
        for problem in problems:
            print(problem)
        for diff in diffs.values():
            sys.stdout.write(diff if diff.endswith("\n") else diff + "\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="Diff against the committed files; write nothing."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --check, report as a JSON object instead of a unified diff.",
    )
    args = parser.parse_args(argv)
    if args.json and not args.check:
        parser.error("--json only changes --check's report format; pass --check too")

    try:
        data = collect_index_data()
        md_text = _render_markdown(data)
        json_text = _render_json(data)
    except Exception as exc:  # noqa: BLE001 - a broken catalog is a build failure, reported whole.
        print(f"tools/build_index.py: {exc}", file=sys.stderr)
        return 1

    if args.check:
        return _check(md_text, json_text, data, as_json=args.json)

    (validate_repo.ROOT / "catalog" / "index.md").write_text(md_text, encoding="utf-8")
    (validate_repo.ROOT / "catalog" / "index.json").write_text(json_text, encoding="utf-8")
    domain_count = len(data["domains"])
    skill_count = sum(len(domain["skills"]) for domain in data["domains"])
    print(
        f"wrote catalog/index.md and catalog/index.json "
        f"({domain_count} domains, {skill_count} skills)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
