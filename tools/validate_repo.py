#!/usr/bin/env python3
"""Validate the portable skill library contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import jsonschema
except ModuleNotFoundError:  # pragma: no cover - covered by fallback tests.
    jsonschema = None

SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SOURCE_ROOT
SKILLS = ROOT / "skills"
EVAL_SCHEMA = ROOT / "schemas" / "skill-evals.schema.json"
BASELINE = ROOT / "evals" / "baseline.json"

# Non-failing diagnostics, printed after errors. Reset by main().
warnings: list[str] = []

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
PENDING_REVIEW_SECTIONS = (
    "## When to use",
    "## Required inputs",
    "## Workflow",
    "## Sources and freshness",
    "## Privacy and mutations",
    "## Safety boundaries",
    "## Output contract",
    "## Failure conditions",
)
# Today's (contract_version 1) public contract. Deleted once every skill is v2.
PUBLIC_SKILL_SECTIONS_V1 = (
    "When to use",
    "When not to use",
    "Required inputs",
    "Optional inputs",
    "Workflow",
    "Sources and freshness",
    "Privacy and mutations",
    "Safety boundaries",
    "Output contract",
    "Failure conditions",
)
# The contract_version 2 template (design-hygiene 1).
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
FRONTMATTER_ALLOWED_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
METADATA_NS = "spike-os"
METADATA_KEYS = frozenset({"version", "runtime", "reads_from", "writes_to", "effects"})
# Tolerated only while a skill is still at contract_version 1.
FRONTMATTER_LEGACY_KEYS = frozenset({"mutating", "writes_to", "writes_pages"})
# Never valid: runtime coupling and a second version source of truth.
FRONTMATTER_REJECTED_KEYS = frozenset({"triggers", "tools", "version"})
FRONTMATTER_PARSE_ERRORS = "__parse_errors__"
DESCRIPTION_MAX_CHARS = 300
DESCRIPTION_TRIGGER_RE = re.compile(r"\buse when\b", re.IGNORECASE)
DESCRIPTION_FORBIDDEN_RE = re.compile(
    r"\b(spike|tapan)\b|\bI can\b|\byou can use\b", re.IGNORECASE
)
ROUTING_REQUIRED_KEYS = frozenset({"intent", "expected_skill"})
ROUTING_OPTIONAL_KEYS = frozenset({"ambiguous_with", "note", "expect_question"})
SUPPORTING_FILE_EXEMPT = frozenset({"SKILL.md", "examples/evals.json", "routing-eval.jsonl"})
# Agent configuration inside a skill would be granted by `--add-dir` on eval runs
# and by every install of the package.
FORBIDDEN_SKILL_CONFIG = frozenset({"CLAUDE.md", "AGENTS.md", ".mcp.json", ".claude"})
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
BLOCK_SCALAR_RE = re.compile(r"[|>][+-]?\d*")
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
ALLOWED_CLASSIFICATIONS = {"owned", "adapted", "vendored", "runtime-only"}
HEX_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
PLACEHOLDER_RE = re.compile(
    r"\b(todo|tbd|placeholder|coming soon|fill this in|to be written)\b|^\s*(n/?a|none)\s*\.?\s*$",
    re.IGNORECASE,
)
NON_INFORMATIVE_ASSERTIONS = {
    "uses the skill",
    "uses the named skill",
    "meets the skill contract",
    "follows the skill",
    "does the task",
}


def _frontmatter_value(raw: str) -> Any:
    """A frontmatter scalar or flow list (`[a, b]`) from its raw right-hand side."""
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [catalog_scalar(item) for item in inner.split(",") if item.strip()]
    return catalog_scalar(value)


def parse_frontmatter(text: str) -> dict[str, Any] | None:
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
        if depth > 2:
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


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report every parse failure.
        add_error(errors, f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return None


def catalog_scalar(raw: str) -> str:
    """Parse the restricted scalar subset used by the committed catalogs."""
    value = raw.strip()
    if value[:1] in {"\"", "\x27"} and value[-1:] == value[:1]:
        return value[1:-1]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def load_eval_schema(errors: list[str]) -> dict[str, Any] | None:
    data = load_json(EVAL_SCHEMA, errors)
    if not isinstance(data, dict):
        add_error(errors, "schemas/skill-evals.schema.json: schema must contain an object")
        return None
    if data.get("type") != "object" or "evals" not in data.get("required", []):
        add_error(errors, "schemas/skill-evals.schema.json: schema must require evals object shape")
    return data


def validate_eval_schema_fallback(data: object, rel: Path, errors: list[str]) -> None:
    """Validate the subset expressed by schemas/skill-evals.schema.json.

    The repository intentionally avoids a package/toolchain. If the maintained
    jsonschema package is unavailable, this mirrors the committed schema fields
    that the repo uses so CI remains deterministic on stock Python.
    """
    if not isinstance(data, dict):
        add_error(errors, f"{rel}: schema violation: root must be an object")
        return

    if not isinstance(data.get("skill_name"), str) or not data["skill_name"].strip():
        add_error(errors, f"{rel}: schema violation: skill_name must be a non-empty string")

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        add_error(errors, f"{rel}: schema violation: evals must be a non-empty array")
        return

    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            add_error(errors, f"{rel}: schema violation: eval {index} must be an object")
            continue
        case_id = case.get("id")
        if case_id is None:
            add_error(errors, f"{rel}: schema violation: eval {index} needs id")
        elif isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} id must be a positive integer",
            )
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            add_error(errors, f"{rel}: schema violation: eval {index} prompt must be a non-empty string")
        if "expected_output" in case and (
            not isinstance(case["expected_output"], str) or not case["expected_output"].strip()
        ):
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} expected_output must be a non-empty string",
            )
        assertions = case.get("assertions")
        if (
            not isinstance(assertions, list)
            or len(assertions) < 2
            or not all(
                isinstance(item, str) and bool(item.strip()) for item in assertions
            )
        ):
            add_error(
                errors,
                f"{rel}: schema violation: eval {index} assertions must be two or more strings",
            )


def validate_eval_schema(
    data: object,
    rel: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
) -> None:
    if jsonschema is None or schema is None:
        validate_eval_schema_fallback(data, rel, errors)
        return

    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    for error in schema_errors:
        location = ".".join(str(part) for part in error.path)
        suffix = f" at {location}" if location else ""
        add_error(errors, f"{rel}: schema violation{suffix}: {error.message}")


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def parse_list_catalog(path: Path, list_key: str, errors: list[str]) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    rel = path.relative_to(ROOT)

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
    return parse_list_catalog(ROOT / "catalog" / "approved.yaml", "skill", errors)


def parse_source_entries(errors: list[str]) -> dict[str, dict[str, str]]:
    text = (ROOT / "catalog" / "sources.yaml").read_text(encoding="utf-8")
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


def parse_domain_lists(errors: list[str]) -> tuple[set[str], set[str]]:
    """The released and next skill names from catalog/domains.yaml.

    Indent-aware: a `- name:` line starts a new domain and closes whichever list
    was open, so a domain with an empty `next:` no longer swallows the domain
    that follows it.
    """
    text = (ROOT / "catalog" / "domains.yaml").read_text(encoding="utf-8")
    released: set[str] = set()
    next_names: set[str] = set()
    active: set[str] | None = None
    active_indent = -1

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if re.match(r"^\s*- name:", line):
            active = None
            continue
        if stripped.startswith("released:"):
            active, active_indent = released, indent
            continue
        if stripped.startswith("next:"):
            active, active_indent = next_names, indent
            continue
        if active is None:
            continue
        if stripped.startswith("- ") and indent > active_indent:
            active.add(stripped[2:].strip())
            continue
        active = None

    if not released:
        add_error(errors, "catalog/domains.yaml: no released skills found")
    return released, next_names


def parse_cohorts(errors: list[str]) -> dict[str, dict[str, Any]]:
    """Cohort name -> {"status", "skills"} from catalog/cohorts.yaml."""
    path = ROOT / "catalog" / "cohorts.yaml"
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
    path = ROOT / "catalog" / "routing.yaml"
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
    """Every adapted source's install artifact agrees with catalog/sources.yaml."""
    for name, source in sorted(sources.items()):
        if source.get("classification") != "adapted":
            continue
        path = ROOT / "catalog" / "provenance" / name / "origin.json"
        if not path.exists():
            add_error(
                errors,
                f"catalog/provenance/{name}/origin.json: missing provenance "
                f"artifact for adapted source",
            )
            continue

        rel = path.relative_to(ROOT)
        data = load_json(path, errors)
        if not isinstance(data, dict):
            add_error(errors, f"{rel}: provenance artifact must contain an object")
            continue
        artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else {}
        skill_file = data.get("skillFile") if isinstance(data.get("skillFile"), dict) else {}
        checks = (
            ("artifact.sha256", artifact.get("sha256"), "artifact_sha256"),
            ("skillFile.sha256", skill_file.get("sha256"), "skill_file_sha256"),
            ("installedVersion", data.get("installedVersion"), "version"),
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
    if not BASELINE.exists():
        if require_baseline:
            add_error(errors, "evals/baseline.json: missing committed baseline")
        return

    data = load_json(BASELINE, errors)
    if not isinstance(data, dict):
        add_error(errors, "evals/baseline.json: baseline must contain an object")
        return

    # Imported lazily: the validator must still run without tools/evalrunner, and
    # a module-level import cycles back through this module.
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from tools.evalrunner.report import check_baseline
    except Exception as exc:  # noqa: BLE001 - the validator runs without the runner.
        warnings.append(f"evals/baseline.json: baseline check unavailable ({exc})")
        return

    sink = errors if require_baseline else warnings
    for message in check_baseline(data, ROOT):
        sink.append(f"evals/baseline.json: {message}")


def eval_files(skill_dir: Path) -> list[Path]:
    candidates = (
        skill_dir / "examples" / "evals.json",
        skill_dir / "routing-eval.jsonl",
    )
    return [path for path in candidates if path.exists()]


def has_heading(text: str, heading: str) -> bool:
    return re.search(rf"^##+\s+{re.escape(heading)}\s*$", text, re.MULTILINE) is not None


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


def validate_frontmatter(
    rel: Path,
    meta: dict[str, Any],
    contract_version: str,
    errors: list[str],
) -> None:
    """The frontmatter carries only the agentskills.io keys plus metadata.spike-os.

    Unknown top-level keys and parse problems are errors at every contract
    version. Exactly two findings soften to warnings while a skill is still at
    contract_version 1, because today's library still trips them and the rewrite
    batches clear them: a key in `FRONTMATTER_REJECTED_KEYS` (social-listening's
    `triggers`/`tools`) and a `metadata` namespace other than `METADATA_NS`
    (community-management's `metadata.version`). Legacy OS keys are simply
    allowed at version 1 and rejected at 2.
    """
    for problem in meta.get(FRONTMATTER_PARSE_ERRORS, []):
        add_error(errors, f"{rel}/SKILL.md: frontmatter {problem}")

    allowed = set(FRONTMATTER_ALLOWED_KEYS)
    if contract_version == "1":
        allowed |= FRONTMATTER_LEGACY_KEYS
    allowlist = ", ".join(sorted(FRONTMATTER_ALLOWED_KEYS))
    legacy_sink = warnings if contract_version == "1" else errors

    for key in sorted(k for k in meta if k != FRONTMATTER_PARSE_ERRORS):
        if key in FRONTMATTER_REJECTED_KEYS:
            legacy_sink.append(
                f"{rel}/SKILL.md: frontmatter key {key!r} is never allowed; "
                f"allowed keys are {allowlist}"
            )
        elif key in allowed:
            continue
        elif key in FRONTMATTER_LEGACY_KEYS:
            add_error(
                errors,
                f"{rel}/SKILL.md: frontmatter legacy key {key!r} is only allowed on "
                f"contract_version 1; move it under metadata.{METADATA_NS}",
            )
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
            legacy_sink.append(
                f"{rel}/SKILL.md: frontmatter metadata may only contain "
                f"{METADATA_NS!r}, found {namespace!r}"
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
    contract_version: str,
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
        if contract_version == "2":
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
        skills = groups[(heading, _body)]
        if len(skills) >= 2:
            add_error(
                errors,
                f"section {heading!r} body is identical across {', '.join(sorted(skills))}",
            )


def validate_supporting_files(
    skill_dir: Path, text: str, tracked_paths: list[Path], errors: list[str]
) -> None:
    """Every tracked supporting file is linked from SKILL.md, one level deep."""
    rel = skill_dir.relative_to(ROOT)
    prefix = rel.as_posix() + "/"

    for path in tracked_paths:
        relative = path.relative_to(ROOT).as_posix()
        if not relative.startswith(prefix):
            continue
        sub = relative[len(prefix):]
        if sub in SUPPORTING_FILE_EXEMPT:
            continue
        if sub not in text:
            add_error(
                errors,
                f"{rel}/SKILL.md: supporting file {sub!r} is not linked from SKILL.md",
            )
        if not sub.startswith("references/") or not path.exists():
            continue
        reference = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in ("](references/", "](scripts/"):
            if pattern in reference:
                add_error(
                    errors,
                    f"{relative}: reference file links {pattern!r}; supporting files "
                    f"must be reachable one level deep from SKILL.md",
                )


def validate_skill_config(skill_dir: Path, errors: list[str]) -> None:
    """No agent configuration inside a skill: installs and eval runs would grant it."""
    rel = skill_dir.relative_to(ROOT)
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


def validate_routing_eval(
    rel: Path,
    lines: list[str],
    skill_names: set[str],
    errors: list[str],
    warnings: list[str],
    contract_version: str = "1",
) -> None:
    """Shape and coverage of a `routing-eval.jsonl` fixture.

    Coverage (own skill twice, one null) is a warning while the skill is at
    contract_version 1 and an error once it is rewritten to 2.
    """
    skill = Path(rel).parent.name
    expected_counts: dict[str | None, int] = {}
    intents: dict[str, int] = {}

    for index, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            add_error(errors, f"{rel}:{index}: comment lines are not allowed in routing fixtures")
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            add_error(errors, f"{rel}:{index}: invalid JSONL: {exc}")
            continue
        if not isinstance(case, dict):
            add_error(errors, f"{rel}:{index}: each line must be a JSON object")
            continue

        for key in sorted(ROUTING_REQUIRED_KEYS - set(case)):
            add_error(errors, f"{rel}:{index}: missing required key {key!r}")
        for key in sorted(set(case) - ROUTING_REQUIRED_KEYS - ROUTING_OPTIONAL_KEYS):
            add_error(errors, f"{rel}:{index}: unknown key {key!r}")

        intent = case.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            add_error(errors, f"{rel}:{index}: intent must be a non-empty string")
        else:
            key = normalized_body(intent)
            if key in intents:
                add_error(
                    errors,
                    f"{rel}:{index}: duplicate intent, first seen at line {intents[key]}",
                )
            else:
                intents[key] = index

        expected = case.get("expected_skill")
        if "expected_skill" not in case:
            pass  # already reported as a missing required key
        elif expected is None or isinstance(expected, str):
            expected_counts[expected] = expected_counts.get(expected, 0) + 1
            if isinstance(expected, str) and expected not in skill_names:
                add_error(
                    errors,
                    f"{rel}:{index}: expected_skill {expected!r} is not a skill in skills/",
                )
        else:
            add_error(errors, f"{rel}:{index}: expected_skill must be a skill name or null")

        ambiguous = case.get("ambiguous_with")
        if ambiguous is not None:
            if not isinstance(ambiguous, list) or not all(
                isinstance(item, str) for item in ambiguous
            ):
                add_error(errors, f"{rel}:{index}: ambiguous_with must be a list of skill names")
            else:
                for name in ambiguous:
                    if name not in skill_names:
                        add_error(
                            errors,
                            f"{rel}:{index}: ambiguous_with names unknown skill {name!r}",
                        )
        note = case.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            add_error(errors, f"{rel}:{index}: note must be a non-empty string")
        if "expect_question" in case and not isinstance(case["expect_question"], bool):
            add_error(errors, f"{rel}:{index}: expect_question must be a boolean")

    sink = errors if contract_version == "2" else warnings
    own = expected_counts.get(skill, 0)
    if own < 2:
        sink.append(
            f"{rel}: {skill} must be the expected_skill on at least 2 lines, found {own}"
        )
    if expected_counts.get(None, 0) < 1:
        sink.append(f"{rel}: needs at least one line with expected_skill null")


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


def eval_case_count(path: Path, errors: list[str]) -> int:
    if path.suffix == ".jsonl":
        # Routing JSONL has no behavioral assertion schema, so it cannot satisfy
        # the package-level synthetic behavioral-eval minimum.
        return 0

    data = load_json(path, errors)
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list):
        return 0
    return len(data["evals"])


def validate_eval_file(
    skill: str,
    path: Path,
    schema: dict[str, Any] | None,
    errors: list[str],
    skill_names: set[str] | None = None,
    contract_version: str = "1",
) -> None:
    rel = path.relative_to(ROOT)

    if path.suffix == ".jsonl":
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            add_error(errors, f"{rel}: routing eval file is empty")
            return
        validate_routing_eval(
            rel, lines, skill_names or set(), errors, warnings, contract_version
        )
        return

    data = load_json(path, errors)
    validate_eval_schema(data, rel, schema, errors)
    if not isinstance(data, dict):
        add_error(errors, f"{rel}: eval file must contain an object")
        return

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        add_error(errors, f"{rel}: missing non-empty evals array")
        return

    declared = data.get("skill_name")
    if declared and declared != skill:
        add_error(errors, f"{rel}: declared skill_name {declared!r} does not match {skill!r}")

    seen_ids: set[int] = set()
    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            add_error(errors, f"{rel}: eval {index} must be an object")
            continue
        prompt = case.get("prompt")
        assertions = case.get("assertions")
        if not isinstance(prompt, str) or not prompt.strip():
            add_error(errors, f"{rel}: eval {index} missing prompt")
        if not isinstance(assertions, list) or len(assertions) < 2:
            add_error(errors, f"{rel}: eval {index} needs at least two assertions")
        elif not all(
            isinstance(assertion, str) and bool(assertion.strip())
            for assertion in assertions
        ):
            add_error(errors, f"{rel}: eval {index} assertions must be non-empty strings")
        else:
            for assertion in assertions:
                normalized = re.sub(r"\s+", " ", assertion.strip().lower())
                if normalized in NON_INFORMATIVE_ASSERTIONS:
                    add_error(
                        errors,
                        f"{rel}: eval {index} uses non-informative assertion {assertion!r}",
                    )

        case_id = case.get("id")
        if case_id is None:
            add_error(errors, f"{rel}: eval {index} missing positive integer id")
        elif isinstance(case_id, int) and not isinstance(case_id, bool) and case_id > 0:
            if case_id in seen_ids:
                add_error(errors, f"{rel}: duplicate eval id {case_id}")
            seen_ids.add(case_id)

        expected_output = case.get("expected_output")
        if expected_output == "Meets the skill contract for this scenario.":
            add_error(errors, f"{rel}: eval {index} uses a non-informative expected_output")


def validate_skill(
    skill_dir: Path,
    inventory: dict[str, dict[str, str]],
    released: set[str],
    next_names: set[str],
    schema: dict[str, Any] | None,
    errors: list[str],
    sources: dict[str, dict[str, str]] | None = None,
    tracked_paths: list[Path] | None = None,
    skill_names: set[str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Validate one skill; returns its contract version and its section bodies.

    `contract_version` comes from catalog/approved.yaml and defaults to "1", the
    shape every skill has before the hygiene rewrite. Version 1 keeps today's
    checks; version 2 is held to the canonical template.
    """
    rel = skill_dir.relative_to(ROOT)
    tracked_paths = tracked_paths or []
    skill_names = skill_names or set()

    validate_skill_config(skill_dir, errors)

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        add_error(errors, f"{rel}: missing SKILL.md")
        return "1", {}

    text = skill_md.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    if meta is None:
        add_error(errors, f"{rel}/SKILL.md: missing or invalid frontmatter")
        return "1", {}

    entry = inventory.get(skill_dir.name)
    contract_version = str((entry or {}).get("contract_version", "1")).strip() or "1"
    if contract_version not in {"1", "2"}:
        add_error(
            errors,
            f"catalog/approved.yaml: {skill_dir.name} has unsupported "
            f"contract_version {contract_version!r}",
        )
        contract_version = "1"

    validate_frontmatter(rel, meta, contract_version, errors)

    name = meta.get("name")
    description = meta.get("description")
    if name != skill_dir.name:
        add_error(errors, f"{rel}/SKILL.md: frontmatter name {name!r} must match directory")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        add_error(errors, f"{rel}/SKILL.md: name must be kebab-case")

    if contract_version == "2":
        validate_description(rel, description, errors)
        validate_contract_section(
            rel, text, skill_dir, (sources or {}).get(skill_dir.name), errors
        )
    else:
        if not isinstance(description, str) or len(description.strip()) < 24:
            add_error(errors, f"{rel}/SKILL.md: description must be a useful string")
        if "dependencies" not in text.lower():
            add_error(errors, f"{rel}/SKILL.md: must explicitly declare dependencies")
        if "provenance" not in text.lower():
            add_error(errors, f"{rel}/SKILL.md: must include provenance/attribution")
    if HIDDEN_DEP_RE.search(text):
        add_error(errors, f"{rel}/SKILL.md: contains suspicious hidden/private dependency language")

    section_bodies: dict[str, str] = {}
    if entry is None:
        add_error(errors, f"{rel}: missing catalog/approved.yaml entry")
    else:
        status = entry.get("status")
        proposal = entry.get("workshop_proposal", "")
        if status not in {"approved", "pending-review"}:
            add_error(errors, f"{rel}: catalog status must be approved or pending-review")
        if status == "approved":
            if skill_dir.name not in released:
                add_error(errors, f"{rel}: approved skill must be in catalog/domains.yaml released")
            if skill_dir.name in next_names:
                add_error(
                    errors,
                    f"{rel}: approved skill must not remain in catalog/domains.yaml next",
                )
        if status == "pending-review":
            if skill_dir.name in released:
                add_error(
                    errors,
                    f"{rel}: pending-review skill must not be in catalog/domains.yaml released",
                )
            if skill_dir.name not in next_names:
                add_error(
                    errors,
                    f"{rel}: pending-review skill must be in catalog/domains.yaml next",
                )
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-\d{8}-[a-z0-9]{10}", proposal):
                add_error(
                    errors,
                    f"{rel}: pending-review skill must have a real workshop_proposal ID",
                )

        if status in {"approved", "pending-review"} and contract_version == "2":
            headings = validate_canonical_structure(rel, text, errors)
            section_bodies = validate_public_section_bodies(
                rel, text, headings, contract_version, errors
            )
            validate_supporting_files(skill_dir, text, tracked_paths, errors)
        elif status == "approved":
            for heading in PUBLIC_SKILL_SECTIONS_V1:
                if not has_heading(text, heading):
                    add_error(
                        errors,
                        f"{rel}/SKILL.md: approved skill missing public section {heading!r}",
                    )
            section_bodies = validate_public_section_bodies(
                rel, text, PUBLIC_SKILL_SECTIONS_V1, contract_version, errors
            )
        elif status == "pending-review":
            for heading in PENDING_REVIEW_SECTIONS:
                if not has_heading(text, heading.removeprefix("## ")):
                    add_error(
                        errors,
                        f"{rel}/SKILL.md: pending-review skill missing section {heading!r}",
                    )

    files = eval_files(skill_dir)
    if not files:
        add_error(errors, f"{rel}: missing evals file")
    else:
        total_eval_cases = sum(eval_case_count(path, errors) for path in files)
        if total_eval_cases < 4:
            add_error(
                errors,
                f"{rel}: needs at least 4 synthetic eval cases, found {total_eval_cases}",
            )
    for path in files:
        validate_eval_file(
            skill_dir.name, path, schema, errors, skill_names, contract_version
        )
    return contract_version, section_bodies


def validate_privacy(errors: list[str], tracked_paths: list[Path] | None = None) -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in ("evals/workspaces/", ".env", "*.skill"):
        if required not in ignored:
            add_error(
                errors,
                f".gitignore: missing local/private generated-state pattern {required!r}",
            )

    for path in git_files() if tracked_paths is None else tracked_paths:
        rel = path.relative_to(ROOT).as_posix()
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


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or [])
    unknown = [argument for argument in arguments if argument != "--require-baseline"]
    if unknown:
        print(f"usage: validate_repo.py [--require-baseline] (unknown: {' '.join(unknown)})")
        return 2
    require_baseline = "--require-baseline" in arguments

    warnings.clear()
    errors: list[str] = []
    schema = load_eval_schema(errors)
    inventory = parse_catalog_inventory(errors)
    released, next_names = parse_domain_lists(errors)
    sources = parse_source_entries(errors)
    cohorts = parse_cohorts(errors)
    clusters = parse_routing_clusters(errors)
    tracked_paths = git_files()
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    skill_names = {path.name for path in skill_dirs}

    # Only contract_version 2 bodies are compared across files: the unmigrated
    # library shares many verbatim boilerplate bodies by design.
    canonical_bodies: dict[str, dict[str, str]] = {}
    for skill_dir in skill_dirs:
        contract_version, section_bodies = validate_skill(
            skill_dir,
            inventory,
            released,
            next_names,
            schema,
            errors,
            sources,
            tracked_paths,
            skill_names,
        )
        if contract_version == "2":
            canonical_bodies[skill_dir.name] = section_bodies

    for name in sorted(set(inventory) - skill_names):
        add_error(errors, f"catalog/approved.yaml: {name} has no skills/{name} directory")

    for name in sorted(released - set(inventory)):
        add_error(
            errors,
            f"catalog/domains.yaml: released skill {name} is missing catalog/approved.yaml entry",
        )

    validate_source_catalog(inventory, sources, skill_names, errors)
    validate_cross_file_duplicates(canonical_bodies, errors)
    validate_cohort_parity(inventory, cohorts, errors)
    validate_cluster_routing(clusters, canonical_bodies, errors)
    validate_provenance_artifacts(sources, errors)
    validate_baseline(errors, require_baseline)
    validate_privacy(errors, tracked_paths)

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        print_warnings()
        return 1

    print(f"Validation passed: {len(skill_dirs)} skills checked.")
    print_warnings()
    return 0


def print_warnings() -> None:
    if not warnings:
        return
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"- {warning}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
