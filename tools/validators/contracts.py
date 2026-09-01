#!/usr/bin/env python3
"""contracts/ and adapters/: loading them, and holding each skill to them.

Namespaces, the effect enum and the body keyword scan behind it, the
vocabulary binding every declared runtime has to resolve, and the adapter
files themselves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence


from . import context
from .context import add_error, load_json
from .frontmatter import (
    METADATA_NS,
    _declared_list,
    parse_frontmatter,
    skill_body,
    spike_os_block,
)

# The contract_version 2 rules below read the machine-readable contracts through
# tools/contracts_check.py (design-os-foundations 8).
DATASTORE_CONTRACT = "contracts/datastore.yaml"


# The two namespaces contracts/datastore.yaml binds to an effect rather than to a
# skill's own subject matter.
EFFECTS_LEDGER_NS = "effects"


NOTIFICATIONS_NS = "notifications"


NOTIFY_EFFECT = "notify:owner"


CAPABILITIES_CONTRACT = "contracts/capabilities.yaml"


VOCABULARY_CONTRACT = "adapters/vocabulary.yaml"


ADAPTERS_DIR = "adapters"


ADAPTER_SCHEMA = "adapters/adapter.schema.json"


ADAPTER_REQUIRED_KEYS = (
    "runtime",
    "version",
    "vocabulary",
    "datastore",
    "notification",
    "scheduler",
    "identity_files",
    "skills_dir",
    "adapter_file",
    "render",
    "local_overrides_file",
)


BACKTICKED_RE = re.compile(r"`([^`\n]+)`")


# A namespace token counts only where a path starts: a line start, whitespace, or
# an opening bracket, quote, or backtick. Without it `example.com/conversations/`,
# `../conversations/`, and `sub-projects/` all read as namespace uses.
NAMESPACE_BOUNDARY = r"(?:^|[\s(\[`\"'])"


SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


SENTENCE_SPLIT_RE = re.compile(r"[.;\n]")


# A comma or semicolon ends a clause; `read-only` describes the subject of the
# clause it sits in, not of every clause sharing the sentence.
CLAUSE_SPLIT_RE = re.compile(r"[;,]")


# Spans whose dots are part of a name, not a sentence end: a Markdown link (label
# and target), a backticked span, and a bare file name.
PROTECTED_SPAN_RE = re.compile(
    r"\[[^\]\n]*\]\([^)\s]*\)"
    r"|`[^`\n]+`"
    r"|[\w/.-]+\.(?:md|py|json|jsonl|yaml|yml|txt|sh)\b"
)


PROTECTED_DOT = "\x00"


EFFECT_NEGATION_RE = re.compile(
    r"\b(do not|does not|doesn't|cannot|can't|never|must not|refuse|is not|"
    r"not authorized)\b",
    re.IGNORECASE,
)


# Scoped to its own clause rather than the whole sentence.
CLAUSE_NEGATION_RE = re.compile(r"\bread-only\b", re.IGNORECASE)


# A backticked span names another package or a vocabulary term
# (`public-post-workshop` is not a post), never an action taken here.
BACKTICKED_SPAN_RE = re.compile(r"`[^`\n]+`")
# A quoted span is normally the owner's phrasing that a routing table matches on
# -- "post it for me later today" is the request, not the skill's own verb.
QUOTED_SPAN_RE = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")


# design-os-foundations 4.3: a body keyword and the effects that would cover it.
CAPABILITY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("post|publish|upload", ("publish:external",)),
    ("revoke|unpublish", ("publish:revoke",)),
    ("send|reply|email|DM|broadcast", ("message:send", "notify:owner")),
    ("delete|remove|trash", ("delete:external",)),
    ("schedule|cron job|recurrence", ("schedule:manage",)),
    ("merge", ("repo:merge",)),
    ("commit|push|pull request|PR", ("repo:write",)),
    ("OAuth|token|credential", ("credential:manage",)),
    ("paid|spend|cost cap", ("spend",)),
    ("advance.*cursor|checkpoint", ("checkpoint:advance",)),
    ("install", ("skill:install", "config:write")),
    ("write memory|durable write|store", ("datastore:write",)),
)


# The literal keywords CAPABILITY_HINTS scans for. A quoted span that is one of
# them bare is the skill naming the effect, and quoting it buys no exemption; the
# one pattern entry that is a regex rather than a literal is left out.
EFFECT_VERBS = frozenset(
    word.lower()
    for keywords, _effects in CAPABILITY_HINTS
    for word in keywords.split("|")
    if not set(word) & set(".*+?[]()\\")
)
CAPABILITY_HINT_RULES = tuple(
    (re.compile(rf"\b(?:{keywords})\b", re.IGNORECASE), effects)
    for keywords, effects in CAPABILITY_HINTS
)


# Values one runtime supplies. A portable skill names the adapters/vocabulary.yaml
# term instead and lets the adapter resolve it. Applies to skills/ only:
# adapters/ is where these values legitimately live -- with one exception, the
# owner's own tokens below, which are personal rather than runtime values and
# are checked in adapters/ too.
RUNTIME_SPECIFIC_TOKENS = (
    "Todoist",
    "America/Los_Angeles",
    "/data/.local/bin",
    "OpenClaw",
    "soul file",
    "Telegram",
    "Moltbook",
    "AgentMail",
    "ops/tasks.md",
    "gateway restart",
    "openclaw doctor",
    "Skill Workshop",
    "Spike",
    "Tapan",
    # One runtime's name for the `identity files` vocabulary term. `SKILL.md` is
    # deliberately absent: it is this repository's own filename, not a runtime's.
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "MEMORY.md",
)


# The owner's own tokens. A runtime's product name ("Todoist", "OpenClaw") is
# what an adapter exists to bind, but a personal path or handle in a git-tracked
# adapter is a personal value published to everyone who clones the repository.
# It belongs in the gitignored local_overrides_file, behind a ${PLACEHOLDER} the
# installer fills, so adapters/ gets no exemption for these.
PERSONAL_TOKENS = ("Tapan",)


PERSONAL_RE = re.compile(
    "|".join(
        rf"(?<![0-9A-Za-z_]){re.escape(token)}(?![0-9A-Za-z_])"
        for token in sorted(PERSONAL_TOKENS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


# `spike-os` is the metadata namespace every v2 skill declares and `spike-skills`
# is this repository; neither is a runtime value a skill should stop naming.
RUNTIME_SPECIFIC_EXCLUSIONS = {"Spike": r"(?!-os\b|-skills\b)"}


# Longest first: `re` takes the first alternative that matches, so `OpenClaw`
# ahead of `openclaw doctor` would make the longer token unreachable and report
# the wrong value.
RUNTIME_SPECIFIC_RE = re.compile(
    "|".join(
        rf"(?<![0-9A-Za-z_]){re.escape(token)}"
        rf"{RUNTIME_SPECIFIC_EXCLUSIONS.get(token, '')}(?![0-9A-Za-z_])"
        for token in sorted(RUNTIME_SPECIFIC_TOKENS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


class Vocabulary(NamedTuple):
    """adapters/vocabulary.yaml as the runtime-binding rule reads it."""

    terms: dict[str, str]  # canonical term -> the key an adapter binds it under
    aliases: dict[str, str]  # alias -> the canonical term to write instead


class Contracts(NamedTuple):
    """The machine-readable contracts, as loaded; empty when a file is missing."""

    datastore: dict[str, Any]
    capabilities: dict[str, Any]
    vocabulary: dict[str, Any]
    adapters: dict[str, dict[str, Any]]


def contracts_check_module() -> Any:
    """`tools/contracts_check.py`, imported lazily and from either entry point.

    `python3 tools/validate_repo.py` puts `tools/` on `sys.path`; importing the
    package works only when the repository root is on it.
    """
    try:
        from tools import contracts_check
    except ImportError:  # pragma: no cover - one of the two branches always runs.
        import contracts_check  # type: ignore[no-redef]
    return contracts_check


def _load_contract(
    rel: str,
    load: Callable[[Any], dict[str, Any]],
    errors: list[str],
    require: bool,
) -> dict[str, Any] | None:
    """One contract file, or None with the absence reported at the right level."""
    if not (context.ROOT / rel).exists():
        message = (
            f"{rel}: missing; contract_version 2 skills cannot be validated without it"
        )
        if require:
            add_error(errors, message)
        else:
            context.warnings.append(message)
        return None
    try:
        return load(contracts_check_module())
    except Exception as exc:  # noqa: BLE001 - report any contract parse failure.
        add_error(errors, f"{rel}: unreadable contract: {exc}")
        return None


def load_datastore_contract(
    errors: list[str], require: bool = True
) -> dict[str, Any] | None:
    """`contracts/datastore.yaml`: namespaces, envelope, enums, verbs."""
    return _load_contract(
        DATASTORE_CONTRACT, lambda module: module.load_datastore(context.ROOT), errors, require
    )


def load_capabilities(errors: list[str], require: bool = True) -> dict[str, Any] | None:
    """`contracts/capabilities.yaml`: the closed effect enum."""
    return _load_contract(
        CAPABILITIES_CONTRACT,
        lambda module: module.load_capabilities(context.ROOT),
        errors,
        require,
    )


def load_vocabulary(errors: list[str], require: bool = True) -> dict[str, Any] | None:
    """`adapters/vocabulary.yaml`: the neutral term list every adapter binds."""
    return _load_contract(
        VOCABULARY_CONTRACT, lambda module: module.load_vocabulary(context.ROOT), errors, require
    )


def load_adapters(errors: list[str], require: bool = True) -> dict[str, Any] | None:
    """Every declared `adapters/<runtime>/adapter.yaml`, keyed by runtime."""
    return _load_contract(
        ADAPTERS_DIR, lambda module: module.load_adapters(context.ROOT), errors, require
    )


def load_contracts(errors: list[str], require: bool) -> Contracts:
    """Every contract the contract_version 2 rules read."""
    return Contracts(
        datastore=load_datastore_contract(errors, require) or {},
        capabilities=load_capabilities(errors, require) or {},
        vocabulary=load_vocabulary(errors, require) or {},
        adapters=load_adapters(errors, require) or {},
    )


def namespace_statuses(datastore: dict[str, Any]) -> dict[str, str]:
    """Datastore namespace name -> declared status."""
    return {
        str(entry["name"]): str(entry.get("status"))
        for entry in (datastore.get("namespaces") or [])
        if entry.get("name")
    }


def effect_enum(capabilities: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Effect name -> its capabilities.yaml entry."""
    return {
        str(entry["name"]): entry
        for entry in (capabilities.get("effects") or [])
        if entry.get("name")
    }


def vocabulary_view(vocabulary: dict[str, Any]) -> Vocabulary:
    """The term and alias maps the runtime-binding rule matches backticks against."""
    terms: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for entry in vocabulary.get("terms") or []:
        term = str(entry.get("term") or "")
        if not term:
            continue
        terms[term] = str(entry.get("key") or "")
        for alias in entry.get("aliases") or []:
            aliases[str(alias)] = term
    return Vocabulary(terms, aliases)


def capability_entries() -> dict[str, dict[str, Any]]:
    """The effect enum, loaded directly; for callers outside a validation run."""
    return effect_enum(contracts_check_module().load_capabilities(context.ROOT))


def derived_hints(
    effects: Sequence[str], entries: dict[str, dict[str, Any]] | None = None
) -> dict[str, bool]:
    """The four MCP hints a skill inherits from its declared effects.

    `capabilities.yaml` `derivation:`: read-only and idempotent hold only when
    every declared effect holds them, destructive and open-world when any does,
    and no declared effect is the read-only, non-destructive, idempotent,
    closed-world case. An effect outside the enum is scored pessimistically, the
    way the MCP spec defaults an unknown tool. `tools/install_skill.py` (T23)
    emits these; the validator exposes them so the two cannot drift.
    """
    known = capability_entries() if entries is None else entries
    declared = [known[name] for name in effects if name in known]
    unknown = any(name not in known for name in effects)
    return {
        "readOnlyHint": not unknown
        and all(bool(entry.get("readOnlyHint")) for entry in declared),
        "destructiveHint": unknown
        or any(bool(entry.get("destructiveHint")) for entry in declared),
        "idempotentHint": not unknown
        and all(bool(entry.get("idempotentHint")) for entry in declared),
        "openWorldHint": unknown
        or any(bool(entry.get("openWorldHint")) for entry in declared),
    }


def _is_delegation(token: str) -> bool:
    """A backticked token that names another skill in `skills/`."""
    return bool(SKILL_NAME_RE.fullmatch(token)) and (context.SKILLS / token).is_dir()


def declared_effects(skill: str) -> set[str]:
    """`metadata.spike-os.effects` of another skill, read from its frontmatter."""
    path = context.SKILLS / skill / "SKILL.md"
    try:
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return set()
    return set(_declared_list(spike_os_block(meta or {}).get("effects")))


def delegated_effects(sentence: str) -> set[str]:
    """Effects the skills a sentence backticks declare for themselves.

    A delegator inherits the callee's authority only for what the callee actually
    declares: naming `publish` does not license the delegator's own scheduling in
    the same sentence.
    """
    lent: set[str] = set()
    for token in BACKTICKED_RE.findall(sentence):
        if _is_delegation(token):
            lent |= declared_effects(token)
    return lent


def scannable_text(clause: str) -> str:
    """`clause` with the spans that are not the skill's own verb removed.

    A backticked span always goes: it names a package or a vocabulary term. A
    quoted span goes only when it is the owner's phrasing rather than a bare
    effect verb, so `"publish" the entry` is still scanned while
    `"post it for me later today"` is not.
    """
    masked = BACKTICKED_SPAN_RE.sub(" ", clause)
    return QUOTED_SPAN_RE.sub(
        lambda match: match.group(0) if _is_bare_effect_verb(match.group(0)) else " ",
        masked,
    )


def _is_bare_effect_verb(span: str) -> bool:
    """True when a quoted span is one effect keyword and nothing else."""
    return span.strip("\"\u201c\u201d").strip().strip(".,;:!?").lower() in EFFECT_VERBS


def split_sentences(body: str) -> list[str]:
    """Sentences of a SKILL.md body, with file names and Markdown links kept whole.

    Splitting on every `.` cut `catalog/index.md` in half and tore a negation off
    the clause it governed; the dots inside a protected span are masked first.
    """
    masked = PROTECTED_SPAN_RE.sub(
        lambda match: match.group(0).replace(".", PROTECTED_DOT), body
    )
    return [part.replace(PROTECTED_DOT, ".") for part in SENTENCE_SPLIT_RE.split(masked)]


def runtime_specific_hits(body: str) -> list[str]:
    """Runtime-specific values in a SKILL.md body, in file order."""
    return [match.group(0) for match in RUNTIME_SPECIFIC_RE.finditer(body)]


def personal_value_hits(text: str) -> list[str]:
    """The owner's own tokens in a tracked file, deduplicated in file order."""
    return list(dict.fromkeys(match.group(0) for match in PERSONAL_RE.finditer(text)))


def validate_namespaces(
    rel: Path,
    meta: dict[str, Any],
    text: str,
    namespaces: dict[str, str],
    errors: list[str],
    entries: dict[str, dict[str, Any]] | None = None,
) -> None:
    """reads_from/writes_to against contracts/datastore.yaml, and the body against both.

    A namespace the body names but the frontmatter does not declare is the
    failure this rule exists for: the installer grants access from the
    declaration, so undeclared use is access the adapter never granted.
    """
    block = spike_os_block(meta)
    reads = _declared_list(block.get("reads_from"))
    writes = _declared_list(block.get("writes_to"))
    effects = _declared_list(block.get("effects"))
    known = ", ".join(sorted(namespaces)) or "no namespaces"

    for key, names in (("reads_from", reads), ("writes_to", writes)):
        for name in names:
            if name not in namespaces:
                add_error(
                    errors,
                    f"{rel}/SKILL.md: metadata.{METADATA_NS}.{key} names unknown "
                    f"namespace {name!r}; {DATASTORE_CONTRACT} declares {known}",
                )
            elif key == "writes_to" and namespaces[name] != "active":
                add_error(
                    errors,
                    f"{rel}/SKILL.md: metadata.{METADATA_NS}.writes_to names "
                    f"{name!r}, whose {DATASTORE_CONTRACT} status is "
                    f"{namespaces[name]!r}; only an active namespace is writable",
                )

    body = skill_body(text)
    declared = set(reads) | set(writes)
    for name in sorted(namespaces):
        if name in declared:
            continue
        if re.search(rf"{NAMESPACE_BOUNDARY}{re.escape(name)}/", body, re.MULTILINE):
            add_error(
                errors,
                f"{rel}/SKILL.md: body names namespace {name + '/'!r} but "
                f"metadata.{METADATA_NS} declares it in neither reads_from nor "
                f"writes_to",
            )

    for key, declared_names, effect in (
        ("reads_from", reads, "datastore:read"),
        ("writes_to", writes, "datastore:write"),
    ):
        if declared_names and effect not in effects:
            add_error(
                errors,
                f"{rel}/SKILL.md: metadata.{METADATA_NS}.{key} is non-empty but "
                f"{effect} is not declared in metadata.{METADATA_NS}.effects",
            )

    validate_effect_ledgers(rel, effects, writes, errors, entries)


def validate_effect_ledgers(
    rel: Path,
    effects: Sequence[str],
    writes: Sequence[str],
    errors: list[str],
    entries: dict[str, dict[str, Any]] | None = None,
) -> None:
    """The two namespaces an effect obliges a skill to declare it writes.

    `contracts/datastore.yaml` gives the `effects` namespace the authority "every
    mutating skill appends" and the `notifications` namespace "holders of
    notify:owner". A skill that declares the effect but not the namespace would
    be installed without the grant its own ledger write needs.

    `entries` is the effect enum the caller has already loaded; only a caller
    that has none falls back to reading the contract again.
    """
    known = capability_entries() if entries is None else entries
    written = set(writes)
    mutating = [
        name
        for name in effects
        if name in known and not known[name].get("readOnlyHint")
    ]
    if mutating and EFFECTS_LEDGER_NS not in written:
        add_error(
            errors,
            f"{rel}/SKILL.md: metadata.{METADATA_NS} declares mutating effect "
            f"{mutating[0]!r} but writes_to does not name {EFFECTS_LEDGER_NS!r}; "
            f"{DATASTORE_CONTRACT} has every mutating skill append to it",
        )
    if NOTIFY_EFFECT in effects and NOTIFICATIONS_NS not in written:
        add_error(
            errors,
            f"{rel}/SKILL.md: metadata.{METADATA_NS} declares {NOTIFY_EFFECT!r} but "
            f"writes_to does not name {NOTIFICATIONS_NS!r}, the namespace "
            f"{DATASTORE_CONTRACT} gives its holders",
        )


def validate_effects(
    rel: Path,
    meta: dict[str, Any],
    text: str,
    effects_enum: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """Declared effects against the enum, and the body against CAPABILITY_HINTS.

    The keyword scan runs per sentence so one mutating sentence cannot be hidden
    inside a read-only section. A sentence that negates the effect states a
    boundary rather than performing it; `read-only` is narrower and covers only
    the clause it sits in. A sentence naming another skill in backticks delegates,
    but only for the effects that callee declares for itself -- the delegator's
    own effect keywords in the same sentence still need declaring.
    """
    declared = _declared_list(spike_os_block(meta).get("effects"))
    for name in declared:
        if name not in effects_enum:
            add_error(
                errors,
                f"{rel}/SKILL.md: metadata.{METADATA_NS}.effects names unknown "
                f"effect {name!r}; {CAPABILITIES_CONTRACT} declares "
                f"{', '.join(sorted(effects_enum))}",
            )

    for sentence in split_sentences(skill_body(text)):
        stripped = sentence.strip()
        if not stripped or EFFECT_NEGATION_RE.search(stripped):
            continue
        lent = delegated_effects(stripped)
        reported: set[tuple[str, ...]] = set()
        for clause in CLAUSE_SPLIT_RE.split(stripped):
            if CLAUSE_NEGATION_RE.search(clause):
                continue
            scannable = scannable_text(clause)
            for pattern, implied in CAPABILITY_HINT_RULES:
                if implied in reported or not pattern.search(scannable):
                    continue
                if any(effect in declared or effect in lent for effect in implied):
                    continue
                reported.add(implied)
                snippet = stripped if len(stripped) <= 120 else stripped[:117] + "..."
                add_error(
                    errors,
                    f"{rel}/SKILL.md: sentence implies {' or '.join(implied)}, which "
                    f"metadata.{METADATA_NS}.effects does not declare: {snippet!r}",
                )


def validate_runtime_binding(
    rel: Path,
    meta: dict[str, Any],
    text: str,
    adapters: dict[str, dict[str, Any]],
    vocab: Vocabulary,
    errors: list[str],
) -> None:
    """The runtime list, the vocabulary terms the body backticks, and stray values.

    Binding is textual, so a term the body names has to resolve in every runtime
    the skill claims; an alias resolves nowhere and names the canonical term in
    the fix.
    """
    runtimes = _declared_list(spike_os_block(meta).get("runtime"))
    if not runtimes:
        add_error(
            errors,
            f"{rel}/SKILL.md: metadata.{METADATA_NS}.runtime must name at least one "
            f"adapter under {ADAPTERS_DIR}/",
        )
    listed: list[str] = []
    for runtime in runtimes:
        if runtime in adapters:
            listed.append(runtime)
        else:
            add_error(
                errors,
                f"{rel}/SKILL.md: metadata.{METADATA_NS}.runtime names {runtime!r}, "
                f"which has no {ADAPTERS_DIR}/{runtime}/adapter.yaml",
            )

    body = skill_body(text)
    for token in dict.fromkeys(BACKTICKED_RE.findall(body)):
        if token in vocab.aliases:
            add_error(
                errors,
                f"{rel}/SKILL.md: use `{vocab.aliases[token]}`, not `{token}`",
            )
            continue
        key = vocab.terms.get(token)
        if key is None:
            continue
        for runtime in listed:
            binding = (adapters[runtime].get("vocabulary") or {}).get(key) or {}
            if not str(binding.get("value") or "").strip():
                add_error(
                    errors,
                    f"{rel}/SKILL.md: body uses `{token}` but "
                    f"{ADAPTERS_DIR}/{runtime}/adapter.yaml binds no value for it",
                )

    for hit in runtime_specific_hits(body):
        add_error(
            errors,
            f"{rel}/SKILL.md: runtime-specific value {hit!r}; name the "
            f"{VOCABULARY_CONTRACT} term instead",
        )


def validate_adapter_files(contracts: Contracts, errors: list[str]) -> None:
    """Every adapters/<runtime>/adapter.yaml: shape, term coverage, namespace map.

    Coverage is `tools/contracts_check.py`'s, so the validator and the standalone
    contract report cannot disagree about what a complete adapter is.
    """
    directory = context.ROOT / ADAPTERS_DIR
    if not directory.is_dir() or not contracts.adapters:
        return  # load_adapters already reported the absence at the right level.

    module = contracts_check_module()
    schema: dict[str, Any] | None = None
    schema_path = context.ROOT / ADAPTER_SCHEMA
    if context.jsonschema is not None and schema_path.exists():
        loaded = load_json(schema_path, errors)
        schema = loaded if isinstance(loaded, dict) else None

    for present in sorted(path.parent.name for path in directory.glob("*/adapter.yaml")):
        if present not in contracts.adapters:
            add_error(
                errors,
                f"{ADAPTERS_DIR}/{present}/adapter.yaml: {present!r} is not a "
                f"declared runtime",
            )

    for runtime in sorted(contracts.adapters):
        for name in ("adapter.yaml", "ADAPTER.md"):
            path = directory / runtime / name
            if not path.is_file():
                continue
            for hit in personal_value_hits(path.read_text(encoding="utf-8")):
                add_error(
                    errors,
                    f"{ADAPTERS_DIR}/{runtime}/{name}: personal value {hit!r}; put it "
                    f"in the local_overrides_file behind a ${{PLACEHOLDER}}",
                )

    for runtime, adapter in sorted(contracts.adapters.items()):
        rel = f"{ADAPTERS_DIR}/{runtime}/adapter.yaml"
        if schema is not None:
            validator = context.jsonschema.Draft202012Validator(schema)
            for problem in sorted(
                validator.iter_errors(adapter), key=lambda error: list(error.path)
            ):
                location = ".".join(str(part) for part in problem.path)
                suffix = f" at {location}" if location else ""
                add_error(errors, f"{rel}: schema violation{suffix}: {problem.message}")
        else:
            for key in ADAPTER_REQUIRED_KEYS:
                if not adapter.get(key):
                    add_error(
                        errors, f"{rel}: schema violation: missing required key {key!r}"
                    )
        if contracts.vocabulary:
            for key in module.missing_terms(adapter, contracts.vocabulary):
                add_error(errors, f"{rel}: binds no value for vocabulary term {key!r}")
            for key in module.extra_terms(adapter, contracts.vocabulary):
                add_error(errors, f"{rel}: binds unknown vocabulary term {key!r}")
        if contracts.datastore:
            for name in module.missing_namespaces(adapter, contracts.datastore):
                add_error(errors, f"{rel}: maps no path for namespace {name!r}")
