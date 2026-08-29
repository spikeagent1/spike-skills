#!/usr/bin/env python3
"""The catalog/ files: parsing them, and holding them to each other.

`approved.yaml`, `sources.yaml`, `domains.yaml`, `cohorts.yaml`,
`routing.yaml`, the provenance artifacts, the generated index, and the
committed eval baseline.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from . import context
from .context import add_error, catalog_scalar, load_json
from .frontmatter import SEMVER_RE
from .structure import PLACEHOLDER_RE

CATALOG_PARITY_FIELDS = (
    "classification",
    "runtime_path",
    "repository_path",
    "status",
    "cohort",
    "version",
)


ADAPTED_SOURCE_FIELDS = (
    "upstream",
    "publisher",
    "version",
    "license",
    "local_modifications",
)


IMMUTABLE_SOURCE_FIELDS = ("commit", "artifact_sha256", "skill_file_sha256", "digest")


# Every key catalog/sources.yaml entries may carry. An unknown key is a typo or
# a field invented without a rule behind it; either way nothing reads it.
SOURCE_ENTRY_KEYS = frozenset(
    {
        "classification",
        "runtime_path",
        "repository_path",
        "path",
        "status",
        "cohort",
        "provenance",
        "version",
        "upstream",
        "upstream_version",
        "publisher",
        "license",
        "license_source",
        "local_modifications",
    }
    | set(IMMUTABLE_SOURCE_FIELDS)
)


ALLOWED_CLASSIFICATIONS = {"owned", "adapted", "vendored", "runtime-only"}


HEX_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


class DomainEntry(NamedTuple):
    """One `catalog/domains.yaml` domain, in file order."""

    name: str
    released: list[str]
    next: list[str]


def parse_list_catalog(path: Path, list_key: str, errors: list[str]) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    rel = path.relative_to(context.ROOT)

    for line in text.splitlines():
        name_match = re.match(r"^\s+- name: ([a-z0-9-]+)\s*$", line)
        if name_match:
            name = name_match.group(1)
            if name in entries:
                add_error(errors, f"{rel}: duplicate skill {name}")
            current = {"name": name}
            entries[name] = current
            continue

        field_match = re.match(r"^\s{4}([a-z0-9_]+):\s*(.*?)\s*$", line)
        if current is not None and field_match:
            field = field_match.group(1)
            if field in current:
                add_error(errors, f"{rel}: duplicate field {field} for {current['name']}")
            current[field] = catalog_scalar(field_match.group(2))

    if not entries:
        add_error(errors, f"{rel}: no {list_key} entries found")
    return entries


def parse_catalog_inventory(errors: list[str]) -> dict[str, dict[str, str]]:
    return parse_list_catalog(context.ROOT / "catalog" / "approved.yaml", "skill", errors)


def parse_source_entries(errors: list[str]) -> dict[str, dict[str, str]]:
    text = (context.ROOT / "catalog" / "sources.yaml").read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    current_field: str | None = None

    for line in text.splitlines():
        source_match = re.match(r"^  ([a-z0-9-]+):\s*$", line)
        if source_match:
            name = source_match.group(1)
            if name in entries:
                add_error(errors, f"catalog/sources.yaml: duplicate source {name}")
            current = {"name": name}
            entries[name] = current
            current_field = None
            continue

        field_match = re.match(r"^\s{4}([a-z0-9_]+):\s*(.*?)\s*$", line)
        if current is not None and field_match:
            current_field = field_match.group(1)
            if current_field in current:
                add_error(
                    errors,
                    f"catalog/sources.yaml: duplicate field {current_field} for {current['name']}",
                )
            current[current_field] = catalog_scalar(field_match.group(2))
            continue

        continuation_match = re.match(r"^\s{6,}(.+?)\s*$", line)
        if current is not None and current_field is not None and continuation_match:
            current[current_field] = (
                current[current_field] + " " + continuation_match.group(1).strip()
            ).strip()

    if not entries:
        add_error(errors, "catalog/sources.yaml: no source entries found")
    return entries


def parse_domains(path: Path) -> list[DomainEntry]:
    """Every `domains:` entry in a domains.yaml-shaped file, in file order.

    Indent-aware: a `- name:` line at any indent starts a new domain and
    closes whichever list was open, so a domain with an empty `next:` cannot
    swallow the domain that follows it. `parse_domain_lists` below derives its
    flat sets from this, and `tools/build_index.py` calls it directly for the
    per-domain grouping the flat sets can't express -- one scan, so a
    `domains.yaml` re-indent cannot make the two silently disagree.
    """
    text = path.read_text(encoding="utf-8")
    domains: list[DomainEntry] = []
    released: list[str] | None = None
    next_names: list[str] | None = None
    active: list[str] | None = None
    active_indent = -1

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        name_match = re.match(r"^\s*- name:\s*(.*)$", line)
        if name_match:
            released, next_names = [], []
            domains.append(DomainEntry(name_match.group(1).strip(), released, next_names))
            active = None
            continue
        if not domains:
            continue
        if stripped.startswith("released:"):
            active, active_indent = released, indent
            continue
        if stripped.startswith("next:"):
            active, active_indent = next_names, indent
            continue
        if active is not None and stripped.startswith("- ") and indent > active_indent:
            active.append(stripped[2:].strip())
            continue
        active = None

    return domains


def parse_domain_lists(errors: list[str]) -> tuple[set[str], set[str]]:
    """The released and next skill names from catalog/domains.yaml, flattened
    across every domain from `parse_domains`."""
    released: set[str] = set()
    next_names: set[str] = set()
    for domain in parse_domains(context.ROOT / "catalog" / "domains.yaml"):
        released.update(domain.released)
        next_names.update(domain.next)

    if not released:
        add_error(errors, "catalog/domains.yaml: no released skills found")
    return released, next_names


def parse_cohorts(errors: list[str]) -> dict[str, dict[str, Any]]:
    """Cohort name -> {"status", "skills"} from catalog/cohorts.yaml."""
    path = context.ROOT / "catalog" / "cohorts.yaml"
    if not path.exists():
        add_error(errors, "catalog/cohorts.yaml: missing cohort catalog")
        return {}

    cohorts: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    in_skills = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name_match = re.match(r"^\s+- name: ([a-z0-9-]+)\s*$", line)
        if name_match:
            name = name_match.group(1)
            if name in cohorts:
                add_error(errors, f"catalog/cohorts.yaml: duplicate cohort {name}")
            current = {"status": "", "skills": []}
            cohorts[name] = current
            in_skills = False
            continue
        if current is None:
            continue
        field_match = re.match(r"^\s{4}([a-z0-9_]+):\s*(.*?)\s*$", line)
        if field_match:
            field, raw = field_match.group(1), field_match.group(2)
            in_skills = False
            if field == "status":
                current["status"] = catalog_scalar(raw)
            elif field == "skills":
                value = raw.strip()
                if value.startswith("[") and value.endswith("]"):
                    current["skills"] = [
                        item.strip() for item in value[1:-1].split(",") if item.strip()
                    ]
                else:
                    in_skills = True
            continue
        stripped = line.strip()
        if in_skills and stripped.startswith("- "):
            current["skills"].append(stripped[2:].strip())

    if not cohorts:
        add_error(errors, "catalog/cohorts.yaml: no cohort entries found")
    return cohorts


def validate_cohort_parity(
    inventory: dict[str, dict[str, str]],
    cohorts: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """Every approved cohort names a real cohort that lists the skill, and back."""
    for name, entry in sorted(inventory.items()):
        cohort = entry.get("cohort", "")
        if not cohort:
            continue
        info = cohorts.get(cohort)
        if info is None:
            add_error(errors, f"catalog/approved.yaml: {name} names unknown cohort {cohort!r}")
            continue
        if name not in info["skills"]:
            add_error(errors, f"catalog/cohorts.yaml: cohort {cohort} does not list {name}")

    for cohort in sorted(cohorts):
        info = cohorts[cohort]
        for name in info["skills"]:
            entry = inventory.get(name)
            if entry is None:
                add_error(
                    errors,
                    f"catalog/cohorts.yaml: cohort {cohort} lists {name}, "
                    f"which has no catalog/approved.yaml entry",
                )
                continue
            if info["status"] == "completed" and entry.get("status") != "approved":
                add_error(
                    errors,
                    f"catalog/cohorts.yaml: completed cohort {cohort} contains "
                    f"non-approved skill {name}",
                )


def parse_routing_clusters(errors: list[str]) -> dict[str, list[str]]:
    """Cluster name -> sibling skill names from catalog/routing.yaml."""
    path = context.ROOT / "catalog" / "routing.yaml"
    if not path.exists():
        add_error(errors, "catalog/routing.yaml: missing cluster routing catalog")
        return {}

    clusters: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_skills = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name_match = re.match(r"^\s+- name: ([a-z0-9-]+)\s*$", line)
        if name_match:
            name = name_match.group(1)
            if name in clusters:
                add_error(errors, f"catalog/routing.yaml: duplicate cluster {name}")
            current = []
            clusters[name] = current
            in_skills = False
            continue
        if current is None:
            continue
        field_match = re.match(r"^\s{4}([a-z0-9_]+):\s*(.*?)\s*$", line)
        if field_match:
            in_skills = False
            if field_match.group(1) == "skills":
                value = field_match.group(2).strip()
                if value.startswith("[") and value.endswith("]"):
                    current.extend(
                        item.strip() for item in value[1:-1].split(",") if item.strip()
                    )
                else:
                    in_skills = True
            continue
        stripped = line.strip()
        if in_skills and stripped.startswith("- "):
            current.append(stripped[2:].strip())

    if not clusters:
        add_error(errors, "catalog/routing.yaml: no cluster entries found")
    return clusters


def validate_cluster_routing(
    clusters: dict[str, list[str]],
    section_bodies: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    """Each contract_version 2 skill routes to every sibling in its cluster."""
    for cluster in sorted(clusters):
        members = clusters[cluster]
        for name in members:
            bodies = section_bodies.get(name)
            if bodies is None:
                continue
            body = bodies.get("When not to use", "")
            for sibling in members:
                if sibling == name or f"`{sibling}`" in body:
                    continue
                add_error(
                    errors,
                    f"skills/{name}/SKILL.md: 'When not to use' does not route to "
                    f"cluster sibling `{sibling}` ({cluster})",
                )


def validate_provenance_artifacts(
    sources: dict[str, dict[str, str]], errors: list[str]
) -> None:
    """Every adapted source's install artifact agrees with catalog/sources.yaml.

    `version` is the repository's own skill version and moves with
    catalog/approved.yaml; the upstream package version the installer recorded
    is `upstream_version` where a rewrite has made the two differ.
    """
    for name, source in sorted(sources.items()):
        if source.get("classification") != "adapted":
            continue
        path = context.ROOT / "catalog" / "provenance" / name / "origin.json"
        if not path.exists():
            add_error(
                errors,
                f"catalog/provenance/{name}/origin.json: missing provenance "
                f"artifact for adapted source",
            )
            continue

        rel = path.relative_to(context.ROOT)
        data = load_json(path, errors)
        if not isinstance(data, dict):
            add_error(errors, f"{rel}: provenance artifact must contain an object")
            continue
        artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else {}
        skill_file = data.get("skillFile") if isinstance(data.get("skillFile"), dict) else {}
        checks = (
            ("artifact.sha256", artifact.get("sha256"), "artifact_sha256"),
            ("skillFile.sha256", skill_file.get("sha256"), "skill_file_sha256"),
            (
                "installedVersion",
                data.get("installedVersion"),
                "upstream_version" if source.get("upstream_version") else "version",
            ),
        )
        for label, actual, field in checks:
            expected = source.get(field, "")
            if actual != expected:
                add_error(
                    errors,
                    f"{rel}: {label} {actual!r} does not match catalog/sources.yaml "
                    f"{field} {expected!r}",
                )


def validate_baseline(errors: list[str], require_baseline: bool) -> None:
    """Hook (b) of design-eval-runner 11: the committed baseline still describes the repo."""
    if not context.BASELINE.exists():
        if require_baseline:
            add_error(errors, "evals/baseline.json: missing committed baseline")
        return

    data = load_json(context.BASELINE, errors)
    if not isinstance(data, dict):
        add_error(errors, "evals/baseline.json: baseline must contain an object")
        return

    # Imported lazily: the validator must still run without tools/evalrunner, and
    # a module-level import cycles back through this module.
    if str(context.SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(context.SOURCE_ROOT))
    try:
        from tools.evalrunner.report import check_baseline
    except Exception as exc:  # noqa: BLE001 - the validator runs without the runner.
        context.warnings.append(f"evals/baseline.json: baseline check unavailable ({exc})")
        return

    sink = errors if require_baseline else context.warnings
    for message in check_baseline(data, context.ROOT):
        sink.append(f"evals/baseline.json: {message}")


def validate_source_catalog(
    inventory: dict[str, dict[str, str]],
    sources: dict[str, dict[str, str]],
    skill_names: set[str],
    errors: list[str],
) -> None:
    for name in sorted(skill_names - set(sources)):
        add_error(errors, f"catalog/sources.yaml: missing source entry for {name}")
    vendored_imports = {
        name
        for name, source in sources.items()
        if source.get("classification") == "vendored"
        and source.get("path", "").startswith("imports/")
    }
    for name in sorted(set(sources) - skill_names - vendored_imports):
        add_error(errors, f"catalog/sources.yaml: source {name} has no skills/{name} directory")

    for name, entry in sorted(inventory.items()):
        source = sources.get(name)
        if source is None:
            continue
        for field in CATALOG_PARITY_FIELDS:
            if not entry.get(field):
                add_error(errors, f"catalog/approved.yaml: {name} missing required field {field}")
            if not source.get(field):
                add_error(errors, f"catalog/sources.yaml: {name} missing required field {field}")
            if entry.get(field) != source.get(field):
                add_error(
                    errors,
                    f"catalog/sources.yaml: {name} {field} {source.get(field)!r} "
                    f"does not match catalog/approved.yaml {entry.get(field)!r}",
                )

        classification = source.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            add_error(
                errors,
                f"catalog/sources.yaml: {name} has unknown classification {classification!r}",
            )
        for field in ("runtime_path", "repository_path"):
            value = source.get(field, "")
            parsed = PurePosixPath(value)
            expected = f"skills/{name}"
            if parsed.is_absolute() or ".." in parsed.parts or value != expected:
                add_error(
                    errors,
                    f"catalog/sources.yaml: {name} {field} must be {expected!r}",
                )

    for name, source in sorted(sources.items()):
        classification = source.get("classification")
        # "name" is synthesized by parse_source_entries from the mapping key,
        # not written in the file, so it is not part of the file's vocabulary.
        for key in sorted(set(source) - SOURCE_ENTRY_KEYS - {"name"}):
            add_error(
                errors,
                f"catalog/sources.yaml: {name} has unknown key {key!r}; allowed keys "
                f"are {', '.join(sorted(SOURCE_ENTRY_KEYS))}",
            )
        upstream_version = source.get("upstream_version", "")
        if upstream_version:
            if classification != "adapted":
                add_error(
                    errors,
                    f"catalog/sources.yaml: {name} is {classification!r} and may not "
                    f"carry upstream_version; only an adapted source has an upstream "
                    f"package version distinct from its own",
                )
            if not SEMVER_RE.match(upstream_version):
                add_error(
                    errors,
                    f"catalog/sources.yaml: {name} upstream_version "
                    f"{upstream_version!r} is not a semantic version",
                )
        if classification in {"adapted", "vendored"}:
            for field in ADAPTED_SOURCE_FIELDS:
                value = source.get(field, "")
                if field == "local_modifications" and value.strip().lower() == "none":
                    continue
                if not value or PLACEHOLDER_RE.search(value):
                    add_error(
                        errors,
                        f"catalog/sources.yaml: {name} {classification} source needs {field}",
                    )
            pins = {
                field: source.get(field, "")
                for field in IMMUTABLE_SOURCE_FIELDS
                if source.get(field, "")
            }
            for field, value in pins.items():
                valid = (
                    HEX_COMMIT_RE.fullmatch(value)
                    if field == "commit"
                    else SHA256_RE.fullmatch(value)
                )
                if not valid:
                    add_error(
                        errors,
                        f"catalog/sources.yaml: {name} {field} is not a valid immutable identifier",
                    )
            if not pins:
                add_error(
                    errors,
                    f"catalog/sources.yaml: {name} {classification} source needs immutable commit or digest",
                )


def validate_catalog_index(errors: list[str]) -> None:
    """catalog/index.md and catalog/index.json against tools/build_index.py.

    Silent until T21 landed build_index.py; the single drift gate for both
    generated files (T21 fix round 1 added the index.json half).
    """
    script = context.ROOT / "tools" / "build_index.py"
    if not script.exists():
        return
    spec = importlib.util.spec_from_file_location("spike_os_build_index", script)
    if spec is None or spec.loader is None:
        add_error(errors, "tools/build_index.py: cannot be imported")
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        rendered_md = module.render()
        rendered_json = module.render_json()
    except Exception as exc:  # noqa: BLE001 - a broken generator is a validation failure.
        add_error(errors, f"tools/build_index.py: render() failed: {exc}")
        return
    for name, rendered in (("index.md", rendered_md), ("index.json", rendered_json)):
        path = context.ROOT / "catalog" / name
        committed = path.read_text(encoding="utf-8") if path.exists() else ""
        if rendered != committed:
            add_error(
                errors,
                f"catalog/{name}: out of date; regenerate it with tools/build_index.py",
            )
