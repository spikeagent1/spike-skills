#!/usr/bin/env python3
"""Validate the portable skill library contract.

The rules live in `tools/validators/`, one module per family; this file composes
them, walks `skills/`, and prints the report. Every public name those modules
define is re-exported here, so `tools/build_index.py`, `tools/install_skill.py`,
`tools/check_staging.py`, and the eval runner keep importing one module.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Any

# Runnable as `python3 tools/validate_repo.py` and importable as
# `tools.validate_repo`; the rule modules are a package either way.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.validators import context

# Re-exports: the whole validator surface, so importers name one module. Every
# rule these back is defined in `tools/validators/`.
# ruff: noqa: F401
from tools.validators.context import (
    add_error, catalog_scalar, git_files, load_json
)
from tools.validators.frontmatter import (
    BLOCK_SCALAR_RE, DESCRIPTION_FORBIDDEN_RE, DESCRIPTION_MAX_CHARS, DESCRIPTION_TRIGGER_RE,
    FRONTMATTER_ALLOWED_KEYS, FRONTMATTER_PARSE_ERRORS, FRONTMATTER_REJECTED_KEYS,
    LISTING_BUDGET_WARN_RATIO, METADATA_KEYS, METADATA_NS, REQUIRE_VERSION, SEMVER_RE,
    SKILL_LISTING_MAX_CHARS, _declared_list, _frontmatter_value, frontmatter, installer_module,
    parse_frontmatter, rendered_listing_chars, skill_body, spike_os_block,
    validate_description, validate_frontmatter, validate_listing_budget, validate_version
)
from tools.validators.structure import (
    CANONICAL_MANDATORY, CANONICAL_OPTIONAL, CANONICAL_ORDER, CONTRACT_LINK,
    CROSS_FILE_DUPLICATE_EXEMPT, FORBIDDEN_SKILL_CONFIG, HIDDEN_DEP_RE, MARKDOWN_LINK_RE,
    MARKDOWN_TABLE_ROW_RE, PLACEHOLDER_RE, PRIVATE_PATH_RE, SECRET_RE, SUPPORTING_FILE_EXEMPT,
    normalized_body, section_body, validate_canonical_structure, validate_contract_section,
    validate_cross_file_duplicates, validate_privacy, validate_public_section_bodies,
    validate_skill_config, validate_supporting_files
)
from tools.validators.catalog import (
    ADAPTED_SOURCE_FIELDS, ALLOWED_CLASSIFICATIONS, CATALOG_PARITY_FIELDS, DomainEntry,
    HEX_COMMIT_RE, IMMUTABLE_SOURCE_FIELDS, SHA256_RE, SOURCE_ENTRY_KEYS,
    parse_catalog_inventory, parse_cohorts, parse_domain_lists, parse_domains,
    parse_list_catalog, parse_routing_clusters, parse_source_entries, validate_baseline,
    validate_catalog_index, validate_cluster_routing, validate_cohort_parity,
    validate_provenance_artifacts, validate_source_catalog
)
from tools.validators.contracts import (
    ADAPTERS_DIR, ADAPTER_REQUIRED_KEYS, ADAPTER_SCHEMA, BACKTICKED_RE, CAPABILITIES_CONTRACT,
    CAPABILITY_HINTS, CAPABILITY_HINT_RULES, CLAUSE_NEGATION_RE, CLAUSE_SPLIT_RE, Contracts,
    DATASTORE_CONTRACT, EFFECTS_LEDGER_NS, EFFECT_NEGATION_RE, NAMESPACE_BOUNDARY,
    BACKTICKED_SPAN_RE, EFFECT_VERBS, QUOTED_SPAN_RE, scannable_text, NOTIFICATIONS_NS, NOTIFY_EFFECT, PROTECTED_DOT, PROTECTED_SPAN_RE,
    RUNTIME_SPECIFIC_EXCLUSIONS, RUNTIME_SPECIFIC_RE, RUNTIME_SPECIFIC_TOKENS,
    SENTENCE_SPLIT_RE, SKILL_NAME_RE, VOCABULARY_CONTRACT, Vocabulary, _is_delegation,
    _load_contract, capability_entries, contracts_check_module, declared_effects,
    delegated_effects, derived_hints, effect_enum, load_adapters, load_capabilities,
    load_contracts, load_datastore_contract, load_vocabulary, namespace_statuses,
    personal_value_hits, runtime_specific_hits, split_sentences, validate_adapter_files,
    validate_effect_ledgers,
    validate_effects, validate_namespaces, validate_runtime_binding, vocabulary_view
)
from tools.validators.evals import (
    NON_INFORMATIVE_ASSERTIONS, ROUTING_OPTIONAL_KEYS, ROUTING_REQUIRED_KEYS, eval_case_count,
    eval_files, load_eval_schema, validate_eval_file, validate_eval_schema,
    validate_eval_schema_fallback, validate_routing_eval
)


# Names a caller redirects (every test points the validator at a fixture tree by
# assigning `validate_repo.ROOT`). The checks read them from
# `tools.validators.context`, so the assignment has to land there rather than on
# a shadow attribute of this module.
_SHARED_STATE = frozenset(
    {
        "SOURCE_ROOT",
        "ROOT",
        "SKILLS",
        "EVAL_SCHEMA",
        "BASELINE",
        "LISTING_BUDGET_CHARS",
        "warnings",
        "jsonschema",
    }
)


class _EntryModule(types.ModuleType):
    """This module, with the shared state forwarded to `validators.context`."""

    def __getattr__(self, name: str) -> Any:
        if name in _SHARED_STATE:
            return getattr(context, name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _SHARED_STATE:
            setattr(context, name, value)
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _EntryModule
# Importing (or reloading) the entry point returns the validator to the real
# repository, which is what a single-module reload used to do.
context.reset()


# The catalog field a skill's contract shape is read from, and the only value it
# may hold. Version 1 was deleted in T25; the field stays so a future bump has
# somewhere to declare itself.
SUPPORTED_CONTRACT_VERSION = "2"


def validate_skill(
    skill_dir: Path,
    inventory: dict[str, dict[str, str]],
    released: set[str],
    next_names: set[str],
    schema: dict[str, Any] | None,
    errors: list[str],
    sources: dict[str, dict[str, str]] | None = None,
    skill_names: set[str] | None = None,
    contracts: Contracts | None = None,
) -> tuple[str, dict[str, str]]:
    """Validate one skill; returns its contract version and its section bodies.

    `contract_version` comes from catalog/approved.yaml and defaults to the only
    version the validator knows. It stays a field so a future contract bump has
    somewhere to declare itself; a value that is not that version is an error,
    and the skill is still held to the canonical template so the report names the
    real structural gaps alongside it.
    """
    rel = skill_dir.relative_to(context.ROOT)
    skill_names = skill_names or set()

    validate_skill_config(skill_dir, errors)

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        add_error(errors, f"{rel}: missing SKILL.md")
        return SUPPORTED_CONTRACT_VERSION, {}

    text = skill_md.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    if meta is None:
        add_error(errors, f"{rel}/SKILL.md: missing or invalid frontmatter")
        return SUPPORTED_CONTRACT_VERSION, {}

    entry = inventory.get(skill_dir.name)
    contract_version = (
        str((entry or {}).get("contract_version", SUPPORTED_CONTRACT_VERSION)).strip()
        or SUPPORTED_CONTRACT_VERSION
    )
    if contract_version != SUPPORTED_CONTRACT_VERSION:
        add_error(
            errors,
            f"catalog/approved.yaml: {skill_dir.name} has unsupported "
            f"contract_version {contract_version!r}; the only supported version is "
            f"{SUPPORTED_CONTRACT_VERSION}",
        )
        contract_version = SUPPORTED_CONTRACT_VERSION

    validate_frontmatter(rel, meta, errors)

    name = meta.get("name")
    description = meta.get("description")
    if name != skill_dir.name:
        add_error(errors, f"{rel}/SKILL.md: frontmatter name {name!r} must match directory")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        add_error(errors, f"{rel}/SKILL.md: name must be kebab-case")

    validate_description(rel, description, errors)
    validate_contract_section(
        rel, text, skill_dir, (sources or {}).get(skill_dir.name), errors
    )
    # Each rule is skipped when its contract failed to load, so a missing
    # contract reports once instead of cascading through every skill.
    if contracts is not None and contracts.datastore:
        validate_namespaces(
            rel, meta, text, namespace_statuses(contracts.datastore), errors
        )
    if contracts is not None and contracts.capabilities:
        validate_effects(rel, meta, text, effect_enum(contracts.capabilities), errors)
    if contracts is not None and contracts.adapters and contracts.vocabulary:
        validate_runtime_binding(
            rel,
            meta,
            text,
            contracts.adapters,
            vocabulary_view(contracts.vocabulary),
            errors,
        )
    if REQUIRE_VERSION:
        validate_version(rel, meta, entry, errors)
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

        if status in {"approved", "pending-review"}:
            headings = validate_canonical_structure(rel, text, errors)
            section_bodies = validate_public_section_bodies(rel, text, headings, errors)
            validate_supporting_files(skill_dir, text, errors)

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
        validate_eval_file(skill_dir.name, path, schema, errors, skill_names)
    return contract_version, section_bodies


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or [])
    unknown = [argument for argument in arguments if argument != "--require-baseline"]
    if unknown:
        print(f"usage: validate_repo.py [--require-baseline] (unknown: {' '.join(unknown)})")
        return 2
    require_baseline = "--require-baseline" in arguments

    context.warnings.clear()
    errors: list[str] = []
    schema = load_eval_schema(errors)
    inventory = parse_catalog_inventory(errors)
    released, next_names = parse_domain_lists(errors)
    sources = parse_source_entries(errors)
    cohorts = parse_cohorts(errors)
    clusters = parse_routing_clusters(errors)
    tracked_paths = git_files()
    # Every skill is held to the canonical contract, so the contracts are always
    # required.
    contracts = load_contracts(errors, True)
    skill_dirs = sorted(path for path in context.SKILLS.iterdir() if path.is_dir())
    skill_names = {path.name for path in skill_dirs}

    canonical_bodies: dict[str, dict[str, str]] = {}
    for skill_dir in skill_dirs:
        _contract_version, section_bodies = validate_skill(
            skill_dir,
            inventory,
            released,
            next_names,
            schema,
            errors,
            sources,
            skill_names,
            contracts,
        )
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
    validate_adapter_files(contracts, errors)
    validate_listing_budget(inventory, errors, context.warnings)
    validate_catalog_index(errors)
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
    if not context.warnings:
        return
    print(f"Warnings: {len(context.warnings)}")
    for warning in context.warnings:
        print(f"- {warning}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
