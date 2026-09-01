#!/usr/bin/env python3
"""Turning one portable SKILL.md into the text a runtime installs.

The adapter decides which frontmatter keys exist, what the `## Runtime binding`
trailer says, and which skills are refused because a term they depend on is
UNCONFIRMED -- as against DEGRADED, a binding known absent whose contract already
says what the skill does without it, which installs with a note. Nothing here
touches the filesystem outside the repository.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from tools import contracts_check, validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import contracts_check  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]


OS_NAME = validate_repo.METADATA_NS


STAMP_NAME = f".{OS_NAME}.json"


RUNTIMES = contracts_check.RUNTIMES


# agentskills.io keeps the portable core; everything else is adapter-emitted.
COPY_DIRS = ("references", "scripts", "assets", "templates")


EXCLUDED_NAMES = ("examples", "evals", "routing-eval.jsonl")


BUNDLE_DIR = "references"


# Claude Code lists description + when_to_use together under one cap.
COMBINED_DESCRIPTION_MAX = 1536


TRAILER_HEADING = "## Runtime binding"


PROVIDER_EFFECTS = ("provider:read", "provider:write", "delete:external")


NOTIFY_EFFECT = "notify:owner"


# contracts/capabilities.yaml's approval ladder, strictest last. An effect
# outside the enum is scored at the strictest tier, the way `derived_hints`
# scores an unknown effect pessimistically.
APPROVAL_LADDER = (
    "never_require",
    "turn_scoped",
    "preview_then_explicit",
    "never_autonomous",
)


STRICTEST_APPROVAL = APPROVAL_LADDER[-1]


NOTIFICATION_TERM = "notification channel"


# Two ways an adapter can mark a binding it cannot fully honour. UNCONFIRMED is
# ignorance -- nobody knows whether the binding works, so a skill that depends on
# it is refused rather than installed on a guess. DEGRADED is knowledge: the
# binding is absent or partial, and the skill's own contract already states what
# it does in that case, so the install proceeds and says so. The authority for
# the distinction is contracts/sync.md's `tasks/` row: "Where no provider
# connector is authorized, `system_of_record` flips to `datastore` and the skill
# discloses that the object is mirror-only" -- a disclosed fallback, not an
# unknown, which is exactly what DEGRADED marks.
UNCONFIRMED = "UNCONFIRMED"


DEGRADED = "DEGRADED"


# The launcher's declared input. Its installed copy carries one extra column, so
# a launcher reading it can see which targets this destination actually holds.
LAUNCHER_INDEX = "catalog/index.md"


INSTALLED_HERE = "installed here"


STATUS_INSTALLED = "installed"


STATUS_NOT_INSTALLED = "not installed"


INDEX_NOTE = (
    "The `{column}` column is written at install time by `tools/install_skill.py`: "
    "`{installed}` means this destination carries the skill, `refused: <term>` means "
    "the runtime adapter cannot attest a term the skill depends on, and "
    "`{absent}` means it was never installed here. A target that is not "
    "`{installed}` is reported as unavailable rather than routed to."
)


INDEX_HEADER_RE = re.compile(r"^\|\s*skill\s*\|")


INDEX_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-{2,}:?\s*\|)+\s*$")


INDEX_ROW_RE = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|")


COMMIT_DISPLAY_CHARS = 8


DEPENDENCIES_RE = re.compile(r"^\*\*Dependencies:\*\*.*$", re.MULTILINE)


LINK_RE = re.compile(r"\[([^\]\n]+)\]\(((?:\.\./)*[^)\s]+)\)")


TRIGGER_RE = re.compile(r"\buse when\b", re.IGNORECASE)


SENTENCE_RE = re.compile(r"(.*?[.!?])(?:\s|$)", re.DOTALL)


PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


COMMAND_RE = re.compile(r"^[a-z][a-z0-9._+-]*$")


CONNECTOR_CONTEXT_RE = re.compile(r"^[\s,]*(?:connector|MCP|server)\b", re.IGNORECASE)


# A backtick the sentence itself calls a package, a record kind, or a field is
# not a binary the runtime has to carry.
NOT_A_BINARY_RE = re.compile(
    r"^\s*(?:package|library|module|records?|namespace|kind|field)\b", re.IGNORECASE
)


# A backtick the same clause calls a Python package/module/distribution, or
# marks optional, names something pip installs or skips -- never a binary the
# installed skill needs on PATH. Scoped to the clause up to the next `;` so an
# "optional" elsewhere on the Dependencies line cannot excuse a different token.
NOT_A_BINARY_CLAUSE_RE = re.compile(
    r"\bpython (?:package|module|distribution|library)\b|\boptional(?:ly)?\b",
    re.IGNORECASE,
)


TERM_SHAPED_RE = re.compile(r"^[a-z][a-z' ]*[a-z]$")


class InstallError(Exception):
    """A condition that stops the whole run rather than one skill."""


@dataclass(frozen=True)
class Bundle:
    """A repository file a skill declares as an input, carried into the install."""

    source: Path
    repo_rel: str
    installed_rel: str


@dataclass(frozen=True)
class Rendered:
    """One skill as it would land in the destination."""

    name: str
    version: str
    capabilities: tuple[str, ...]
    hints: dict[str, bool]
    frontmatter: str
    text: str
    bundles: tuple[Bundle, ...]
    source_dir: Path
    # Links out of the skill directory that no declared input covers; reported
    # rather than silently installed as dead links.
    dangling_links: tuple[str, ...] = ()


@dataclass
class Report:
    """What one run did, so the exit code and the summary agree."""

    installed: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # (identity file, before, after) when this run changes it -- set once, on the
    # guarded path, so a dry run previews exactly what a real run would do.
    identity_change: tuple[Path, str, str] | None = None


def repo_root() -> Path:
    """The repository being installed from; `validate_repo` owns the path."""
    return validate_repo.ROOT


def home() -> Path:
    """The install target's home directory, honouring a redirected `HOME`."""
    return Path(os.path.expanduser("~"))


def expand(value: str) -> Path:
    """`${HOME}/x` and `~/x` as an absolute path; anything else stays repo-relative."""
    text = os.path.expandvars(str(value))
    path = Path(os.path.expanduser(text))
    return path if path.is_absolute() else repo_root() / path


def display_path(value: str) -> str:
    """A path written the way the owner reads it: `${HOME}/x` and `/home/x` as `~/x`."""
    text = str(value).replace("${HOME}/", "~/")
    prefix = f"{home()}/"
    return f"~/{text[len(prefix):]}" if text.startswith(prefix) else text


def sha256_text(text: str) -> str:
    """The digest the stamp records for a rendered SKILL.md."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_contract(name: str) -> dict[str, Any]:
    """One contract, with its load errors raised rather than collected."""
    errors: list[str] = []
    loaders = {
        "capabilities": validate_repo.load_capabilities,
        "datastore": validate_repo.load_datastore_contract,
        "vocabulary": validate_repo.load_vocabulary,
        "adapters": validate_repo.load_adapters,
    }
    data = loaders[name](errors, True)
    if errors or data is None:
        raise InstallError("; ".join(errors) or f"{name}: unreadable")
    return data


def adapter_for(runtime: str, adapters: dict[str, Any]) -> dict[str, Any]:
    adapter = adapters.get(runtime)
    if not adapter:
        raise InstallError(f"adapters/{runtime}/adapter.yaml: not loaded")
    return adapter


def skill_source(name: str) -> Path:
    return repo_root() / "skills" / name


def read_skill(name: str) -> tuple[dict[str, Any], str, str]:
    """One repository skill as (frontmatter, body, full text)."""
    path = skill_source(name) / "SKILL.md"
    if not path.is_file():
        raise InstallError(f"skills/{name}/SKILL.md: no such skill")
    text = path.read_text(encoding="utf-8")
    meta = validate_repo.parse_frontmatter(text)
    if meta is None:
        raise InstallError(f"skills/{name}/SKILL.md: no frontmatter")
    return meta, validate_repo.skill_body(text), text


def os_block(meta: dict[str, Any]) -> dict[str, Any]:
    return validate_repo.spike_os_block(meta)


def declared(meta: dict[str, Any], key: str) -> list[str]:
    value = os_block(meta).get(key)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value] if isinstance(value, list) else []


def trigger_clause(description: str) -> str | None:
    """The description's own "Use when ..." sentence, which is `when_to_use`."""
    match = TRIGGER_RE.search(description)
    if match is None:
        return None
    rest = description[match.start():]
    sentence = SENTENCE_RE.match(rest)
    return (sentence.group(1) if sentence else rest).strip()


def dependencies_line(body: str) -> str:
    match = DEPENDENCIES_RE.search(body)
    return match.group(0) if match else ""


def declared_repo_inputs(body: str) -> list[Bundle]:
    """Repository files the Inputs>Dependencies line names as this skill's inputs.

    The contract links every skill carries are provenance, not inputs, so they
    are left alone; anything else the line links to is a file the skill reads at
    run time and must therefore travel with the install, or the installed copy
    is a skill whose required input does not exist.
    """
    bundles: list[Bundle] = []
    for _, target in LINK_RE.findall(dependencies_line(body)):
        rel = re.sub(r"^(?:\.\./)+", "", target)
        if rel.startswith("contracts/") or not (repo_root() / rel).is_file():
            continue
        installed = f"{BUNDLE_DIR}/{Path(rel).name}"
        if all(bundle.repo_rel != rel for bundle in bundles):
            bundles.append(Bundle(repo_root() / rel, rel, installed))
    return bundles


def undeclared_repo_links(body: str, bundles: Sequence[Bundle]) -> list[str]:
    """Body links to repository files that are not declared inputs.

    Only `declared_repo_inputs` travels with the install, so any other link out
    of the skill directory resolves to nothing once the copy is in a `skills
    dir`. The contract link every skill carries is provenance, not an input, and
    is left alone the same way `declared_repo_inputs` leaves it.
    """
    declared_targets = {bundle.repo_rel for bundle in bundles}
    dangling: list[str] = []
    for _, target in LINK_RE.findall(body):
        if "://" in target or not target.startswith("../"):
            continue
        rel = re.sub(r"^(?:\.\./)+", "", target).split("#", 1)[0]
        if rel.startswith("contracts/") or rel in declared_targets:
            continue
        if target not in dangling:
            dangling.append(target)
    return dangling


def rewrite_links(body: str, bundles: Sequence[Bundle]) -> str:
    """Point the body at the bundled copy, so the installed skill can read it."""
    for bundle in bundles:
        pattern = re.compile(
            rf"\[([^\]\n]+)\]\((?:\.\./)*{re.escape(bundle.repo_rel)}\)"
        )

        def replace(match: re.Match[str], target: str = bundle.installed_rel) -> str:
            label = match.group(1)
            text = target if label == bundle.repo_rel else label
            return f"[{text}]({target})"

        body = pattern.sub(replace, body)
    return body


def path_globs(body: str) -> list[str]:
    """Glob-shaped tokens on the Dependencies line: the skill's file scope.

    `paths` narrows a Claude Code skill to conversations already touching
    matching files, so only an actual glob belongs in it. A named repository
    file is an input, not a scope -- it is bundled into the install instead,
    and putting it here would hide the skill until that file were open.
    """
    line = dependencies_line(body)
    globs: list[str] = []
    for token in re.findall(r"`([^`\n]+)`", line):
        if "*" in token and token not in globs:
            globs.append(token)
    return globs


def openclaw_requires(
    body: str, vocabulary: dict[str, Any] | None = None, datastore: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """`requires.{env,bins,config}` from the Dependencies line's backticked tokens.

    The convention is the openclaw adapter's `render.metadata_extra`: ALL_CAPS is
    an environment variable, a token the line calls a connector, an MCP or a
    server is a registry key, and a command word or an absolute path is a binary.
    A backtick that names something the library already defines -- a vocabulary
    term, a datastore namespace, a sibling skill, a repository path -- is none of
    the three, so it is dropped rather than declared as a missing binary. So is
    one the same clause calls a Python package/module/distribution or marks
    optional: pip installs or skips it, but it never lands on PATH.
    """
    line = dependencies_line(body)
    known = library_tokens(vocabulary, datastore)
    requires: dict[str, list[str]] = {"env": [], "bins": [], "config": []}
    for match in re.finditer(r"`([^`\n]+)`", line):
        token = match.group(1)
        after = line[match.end():]
        if ALL_CAPS_RE.match(token):
            bucket = "env"
        elif CONNECTOR_CONTEXT_RE.match(after):
            bucket = "config"
        elif token in known or NOT_A_BINARY_RE.match(after):
            continue
        elif NOT_A_BINARY_CLAUSE_RE.search(after.split(";", 1)[0]):
            continue
        elif "/" in token and not token.startswith("/"):
            continue
        elif token.startswith("/") or COMMAND_RE.match(token):
            bucket = "bins"
        else:
            continue
        if token not in requires[bucket]:
            requires[bucket].append(token)
    return requires


def library_tokens(
    vocabulary: dict[str, Any] | None, datastore: dict[str, Any] | None
) -> set[str]:
    """Backticks the library itself defines, which are never runtime dependencies."""
    known: set[str] = set()
    for entry in ((vocabulary or {}).get("terms") or []):
        known.add(str(entry.get("term")))
        known.update(str(alias) for alias in (entry.get("aliases") or []))
    for entry in namespace_entries(datastore or {}).values():
        known.add(str(entry.get("name")))
        known.update(str(kind) for kind in (entry.get("kinds") or []))
    skills = repo_root() / "skills"
    if skills.is_dir():
        known.update(path.name for path in skills.iterdir() if path.is_dir())
    return known


def yaml_flow(values: Iterable[str]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return yaml_flow(value)
    return str(value)


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_frontmatter(
    name: str,
    meta: dict[str, Any],
    body: str,
    runtime: str,
    adapter: dict[str, Any],
    hints: dict[str, bool],
    approvals: frozenset[str] = frozenset(),
    vocabulary: dict[str, Any] | None = None,
    datastore: dict[str, Any] | None = None,
) -> str:
    """The portable core, plus exactly the keys this adapter says to emit."""
    render = adapter.get("render") or {}
    description = str(meta.get("description", ""))
    lines = [f"name: {name}", f"description: {quoted(description)}"]

    if render.get("when_to_use"):
        clause = trigger_clause(description)
        if clause:
            combined = len(description) + len(clause)
            if combined > COMBINED_DESCRIPTION_MAX:
                raise InstallError(
                    f"{name}: description + when_to_use is {combined} characters, over "
                    f"the {COMBINED_DESCRIPTION_MAX} Claude Code lists them under"
                )
            lines.append(f"when_to_use: {quoted(clause)}")

    # The approval tier, not the hint: `destructiveHint` took every reversible
    # mutation off the native router with it, and a skill the owner can reach
    # only by naming it is one the launcher cannot hand work to.
    # `never_autonomous` is the tier that means no standing authority.
    triggers = list(render.get("disable_model_invocation_on_approval") or [])
    if any(tier in approvals for tier in triggers):
        lines.append("disable-model-invocation: true")

    background = list(render.get("background_skills") or [])
    if not render.get("user_invocable_default", True) or name in background:
        lines.append("user-invocable: false")

    if "paths" in (render.get("metadata_extra") or {}):
        globs = path_globs(body)
        if globs:
            lines.append(f"paths: {yaml_flow(globs)}")

    for key in ("license", "compatibility", "allowed-tools"):
        if key in meta:
            lines.append(f"{key}: {yaml_scalar(meta[key])}")

    lines.append("metadata:")
    lines.append(f"  {OS_NAME}:")
    for key, value in os_block(meta).items():
        lines.append(f"    {key}: {yaml_scalar(value)}")

    extra = render.get("metadata_extra") or {}
    if any(key.startswith(f"metadata.{runtime}.requires") for key in extra):
        requires = openclaw_requires(body, vocabulary, datastore)
        lines.append(f"  {runtime}:")
        lines.append("    requires:")
        for bucket in ("env", "bins", "config"):
            lines.append(f"      {bucket}: {yaml_flow(requires[bucket])}")

    return "---\n" + "\n".join(lines) + "\n---\n"


def render_trailer(runtime: str, adapter: dict[str, Any], commit: str, version: str) -> str:
    """design-os-foundations 3.2: where every backticked term in this file resolves."""
    return (
        f"{TRAILER_HEADING}\n\n"
        f"Bound to adapter `{runtime}` v{adapter.get('version')} "
        f"(`{display_path(str(adapter['adapter_file']))}`). Installed from "
        f"spike-skills@{commit[:COMMIT_DISPLAY_CHARS]}, skill version {version}. "
        "Backticked terms such as `owner datastore` resolve there.\n"
    )


def declared_approvals(
    effects: Sequence[str], capabilities: dict[str, dict[str, Any]]
) -> frozenset[str]:
    """The approval tier every declared effect carries.

    An effect the enum does not list is scored at `never_autonomous`: the
    installer knows nothing about it, and the strictest tier is the only honest
    reading of an effect nobody declared the ladder for.
    """
    tiers: set[str] = set()
    for name in effects:
        entry = capabilities.get(name)
        tier = str((entry or {}).get("approval") or "")
        tiers.add(tier if tier in APPROVAL_LADDER else STRICTEST_APPROVAL)
    return frozenset(tiers)


def render_skill(
    name: str,
    runtime: str,
    adapter: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    commit: str,
    vocabulary: dict[str, Any] | None = None,
    datastore: dict[str, Any] | None = None,
) -> Rendered:
    meta, body, _ = read_skill(name)
    effects = tuple(declared(meta, "capabilities"))
    hints = validate_repo.derived_hints(effects, capabilities)
    approvals = declared_approvals(effects, capabilities)
    version = str(os_block(meta).get("version", ""))
    bundles = tuple(declared_repo_inputs(body))
    frontmatter = render_frontmatter(
        name, meta, body, runtime, adapter, hints, approvals, vocabulary, datastore
    )
    rendered_body = rewrite_links(body, bundles).rstrip("\n")
    trailer = render_trailer(runtime, adapter, commit, version)
    return Rendered(
        name=name,
        version=version,
        capabilities=effects,
        hints=hints,
        frontmatter=frontmatter,
        text=f"{frontmatter}{rendered_body}\n\n{trailer}",
        bundles=bundles,
        source_dir=skill_source(name),
        dangling_links=tuple(undeclared_repo_links(body, bundles)),
    )


def marked_bindings(adapter: dict[str, Any], marker: str) -> dict[str, str]:
    """Adapter key -> the note, for every binding whose note declares `marker`.

    `contracts_check.binding_marker` is the one reader of a note's marker, so the
    rendered ADAPTER.md cell and the adapter.yaml note are always read the same
    way: a DEGRADED note that names UNCONFIRMED in its prose is DEGRADED on both
    sides.
    """
    marked: dict[str, str] = {}
    for key, binding in (adapter.get("vocabulary") or {}).items():
        note = str((binding or {}).get("note") or "").strip()
        if contracts_check.binding_marker(note) == marker:
            marked[key] = note
    return marked


def unconfirmed_bindings(adapter: dict[str, Any]) -> dict[str, str]:
    """Adapter key -> the note, for every value this runtime cannot attest."""
    return marked_bindings(adapter, UNCONFIRMED)


def degraded_bindings(adapter: dict[str, Any]) -> dict[str, str]:
    """Adapter key -> the note, for every binding known absent or partial.

    Unlike an UNCONFIRMED one, this is a fact the runtime knows and the skill's
    own contract already covers -- contracts/sync.md's `tasks/` row: "Where no
    provider connector is authorized, `system_of_record` flips to `datastore`
    and the skill discloses that the object is mirror-only". So the install
    proceeds, and the run prints the note instead of a refusal.
    """
    return marked_bindings(adapter, DEGRADED)


def namespace_entries(datastore: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry["name"]): entry
        for entry in (datastore.get("namespaces") or [])
        if entry.get("name")
    }


def required_terms(
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
) -> dict[str, str]:
    """Vocabulary term -> why this skill's declaration depends on it.

    A provider effect depends on the provider role of every provider-backed
    namespace the skill declares, and on any provider term the body names.
    `notify:owner` depends on the notification channel and on whatever term the
    adapter's first channel resolves to -- the later channels are fallbacks, so
    an unattested one is a warning rather than a refusal.
    """
    terms = {str(entry["term"]): entry for entry in (vocabulary.get("terms") or [])}
    effects = declared(meta, "capabilities")
    needed: dict[str, str] = {}

    if any(effect in effects for effect in PROVIDER_EFFECTS):
        entries = namespace_entries(datastore)
        for namespace in declared(meta, "reads_from") + declared(meta, "writes_to"):
            entry = entries.get(namespace) or {}
            if str(entry.get("system_of_record")) != "provider":
                continue
            role = str((entry.get("sync") or {}).get("provider_role") or "").strip()
            if role in terms:
                needed.setdefault(role, f"the {namespace} namespace resolves to it")
        for token in dict.fromkeys(validate_repo.BACKTICKED_RE.findall(body)):
            if token in terms and str(terms[token].get("kind")) == "provider":
                needed.setdefault(token, "the body names it")

    if NOTIFY_EFFECT in effects:
        if NOTIFICATION_TERM in terms:
            needed.setdefault(NOTIFICATION_TERM, f"the skill declares {NOTIFY_EFFECT}")
        channels = list((adapter.get("notification") or {}).get("channels") or [])
        for term in channel_terms(channels[:1], terms):
            needed.setdefault(term, "it is the adapter's first notification channel")
    return needed


def channel_terms(channels: Sequence[str], terms: dict[str, Any]) -> list[str]:
    """Vocabulary terms named by a notification channel's text."""
    found: list[str] = []
    for channel in channels:
        for term in terms:
            if re.search(rf"\b{re.escape(term)}\b", str(channel)) and term not in found:
                found.append(term)
    return found


def marked_terms(
    name: str,
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
    marker: str,
) -> list[tuple[str, str]]:
    """`(term, message)` per term this skill needs whose binding carries `marker`."""
    marked = marked_bindings(adapter, marker)
    found: list[tuple[str, str]] = []
    for term, why in sorted(required_terms(meta, body, adapter, datastore, vocabulary).items()):
        key = contracts_check.term_key(term)
        if key in marked:
            found.append(
                (
                    term,
                    f"{name}: `{term}` is {marker} for {adapter['runtime']} "
                    f"({why}) -- {marked[key]}",
                )
            )
    return found


def unconfirmed_refusals(
    name: str,
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
) -> list[str]:
    """One message per term this skill needs and this adapter cannot attest."""
    return [
        message
        for _, message in marked_terms(
            name, meta, body, adapter, datastore, vocabulary, UNCONFIRMED
        )
    ]


def unconfirmed_term(
    name: str,
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
) -> str | None:
    """The first term this skill would be refused over, for the launcher's index."""
    found = marked_terms(name, meta, body, adapter, datastore, vocabulary, UNCONFIRMED)
    return found[0][0] if found else None


def degraded_notes(
    name: str,
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
) -> list[str]:
    """One message per term this skill needs that is bound but known degraded.

    The skill installs: its contract already states what it does without the
    binding, and the note says which term is in that state.
    """
    return [
        message
        for _, message in marked_terms(
            name, meta, body, adapter, datastore, vocabulary, DEGRADED
        )
    ]


def annotate_index(text: str, statuses: dict[str, str]) -> str:
    """The generated index with one `installed here` column added to every table.

    A launcher routes from this file, so a target the destination does not carry
    -- refused over an UNCONFIRMED term, or never installed -- has to be visible
    in the same table the route is read from. Rows are matched on the backticked
    skill name the index's first column carries; a skill the map does not name is
    reported as not installed rather than silently left blank.
    """
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        row = line.rstrip()
        if INDEX_HEADER_RE.match(row) and row.endswith("|"):
            # Only a table whose first column is `skill` gets the column. The
            # index carries a reserved-namespace table too, and widening its
            # rows past its own header would leave malformed Markdown.
            inside = True
            cell = INSTALLED_HERE
        elif not row.startswith("|"):
            inside = False
            lines.append(line)
            continue
        elif not inside:
            lines.append(line)
            continue
        elif INDEX_SEPARATOR_RE.match(row):
            cell = "---"
        elif INDEX_ROW_RE.match(row) and row.endswith("|"):
            name = INDEX_ROW_RE.match(row).group(1)  # type: ignore[union-attr]
            cell = statuses.get(name, STATUS_NOT_INSTALLED)
        else:
            lines.append(line)
            continue
        lines.append(f"{row} {cell} |")
    note = INDEX_NOTE.format(
        column=INSTALLED_HERE, installed=STATUS_INSTALLED, absent=STATUS_NOT_INSTALLED
    )
    return "\n".join(lines).rstrip("\n") + f"\n\n{note}\n"


def fallback_warnings(adapter: dict[str, Any], vocabulary: dict[str, Any]) -> list[str]:
    """Unattested values in a channel chain past the first: a caveat, not a refusal."""
    terms = {str(entry["term"]): entry for entry in (vocabulary.get("terms") or [])}
    unconfirmed = unconfirmed_bindings(adapter)
    channels = list((adapter.get("notification") or {}).get("channels") or [])
    return [
        f"notification fallback `{term}` is UNCONFIRMED; only the first channel is attested"
        for term in channel_terms(channels[1:], terms)
        if contracts_check.term_key(term) in unconfirmed
    ]
