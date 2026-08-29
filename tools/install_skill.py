#!/usr/bin/env python3
"""Render every skill for one runtime, install it there, and audit what is installed.

An installed skill is not a copy. `skills/<name>/SKILL.md` is portable by
construction -- it names runtime facts only through the vocabulary terms
`adapters/vocabulary.yaml` fixes -- so the runtime-specific half is produced
here, from `adapters/<runtime>/adapter.yaml`: the Claude-Code-only frontmatter
keys, OpenClaw's `metadata.openclaw.requires.*`, the `## Runtime binding`
trailer, and the rendered `ADAPTER.md` the trailer points every backticked term
at. Each install carries a `.spike-os.json` stamp, which is what makes a
directory ours to overwrite and `--check` possible at all.

The refusals are the point of the tool, not its edge cases:

- a skill whose `metadata.spike-os.runtime` excludes the target;
- a destination directory holding somebody else's skill (no stamp);
- a skill whose adapter binding for a term it depends on is UNCONFIRMED --
  a `provider:*` skill whose namespaces resolve to an unattested provider, or
  a `notify:owner` skill whose first notification channel is unattested. The
  adapter is what the runtime can honestly do today, so installing past that
  would put a skill on the host that will claim a capability the host lacks.

Usage:
  python3 tools/install_skill.py --runtime {claude-code,openclaw} [options] [NAME...]
    --all                 every skill the runtime carries
    --check               declared-vs-actual over every stamped install; exit 1 on drift
    --uninstall           remove stamped installs (NAME... or --all)
    --list                read the stamps
    --dry-run             print what an install would write, and write nothing
    --dest DIR            override the runtime's default destination
    --local-overrides P   override the adapter's local_overrides_file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from tools import contracts_check, validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import contracts_check  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

OS_NAME = validate_repo.METADATA_NS
STAMP_NAME = f".{OS_NAME}.json"
RUNTIMES = contracts_check.RUNTIMES
# agentskills.io keeps the portable core; everything else is adapter-emitted.
COPY_DIRS = ("references", "scripts", "assets")
EXCLUDED_NAMES = ("examples", "evals", "routing-eval.jsonl")
BUNDLE_DIR = "references"
# Claude Code lists description + when_to_use together under one cap.
COMBINED_DESCRIPTION_MAX = 1536
TRAILER_HEADING = "## Runtime binding"
PROVIDER_EFFECTS = ("provider:read", "provider:write", "delete:external")
NOTIFY_EFFECT = "notify:owner"
NOTIFICATION_TERM = "notification channel"
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
    effects: tuple[str, ...]
    hints: dict[str, bool]
    frontmatter: str
    text: str
    bundles: tuple[Bundle, ...]
    source_dir: Path


@dataclass
class Report:
    """What one run did, so the exit code and the summary agree."""

    installed: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# -- repository access -------------------------------------------------


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


def repo_commit() -> str:
    """`HEAD` of the repository, or an empty string outside a checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def run_validator() -> int:
    """`tools/validate_repo.py`, run in-process; the install refuses on failure."""
    return validate_repo.main([])


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


# -- adapter ------------------------------------------------------------


def adapter_for(runtime: str, adapters: dict[str, Any]) -> dict[str, Any]:
    adapter = adapters.get(runtime)
    if not adapter:
        raise InstallError(f"adapters/{runtime}/adapter.yaml: not loaded")
    return adapter


def adapter_template(runtime: str) -> Path:
    return repo_root() / "adapters" / runtime / "ADAPTER.md"


def check_adapter_template(runtime: str, adapter: dict[str, Any]) -> None:
    """The ADAPTER.md render and adapter.yaml must bind the same term set.

    The rendered file is what a skill's backticked term resolves against, so a
    term bound in the machine-readable half and missing from the text half
    would be a binding the runtime never actually states.
    """
    path = adapter_template(runtime)
    if not path.is_file():
        raise InstallError(f"adapters/{runtime}/ADAPTER.md: missing")
    rendered = contracts_check.adapter_markdown_terms(runtime, repo_root())
    in_markdown = {contracts_check.term_key(term) for term in rendered}
    declared = set(adapter.get("vocabulary") or {})
    missing = sorted(declared - in_markdown)
    extra = sorted(in_markdown - declared)
    if missing or extra:
        raise InstallError(
            f"adapters/{runtime}/ADAPTER.md does not match adapter.yaml: "
            f"missing {missing}, unknown {extra}"
        )


def placeholder_names(runtime: str) -> list[str]:
    """Every `${NAME}` the adapter and its render leave for the local file.

    Comment lines are skipped: both files explain the placeholder convention in
    prose, and a `${PLACEHOLDER}` written to illustrate it is not one to fill.
    """
    names: set[str] = set()
    for path in (
        repo_root() / "adapters" / runtime / "adapter.yaml",
        adapter_template(runtime),
    ):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("#"):
                names.update(PLACEHOLDER_RE.findall(line))
    names.discard("HOME")
    return sorted(names)


def local_overrides_path(adapter: dict[str, Any], override: str | None) -> Path:
    return expand(override) if override else expand(str(adapter["local_overrides_file"]))


def read_local_overrides(path: Path) -> dict[str, str]:
    """The owner's personal values, or an empty map when the file is absent."""
    if not path.is_file():
        return {}
    try:
        data = contracts_check.parse_contract_yaml(path.read_text(encoding="utf-8"))
    except contracts_check.ContractParseError as exc:
        raise InstallError(f"{path}: {exc}") from exc
    return {
        str(key): "" if value is None else str(value)
        for key, value in data.items()
        if isinstance(key, str)
    }


def local_overrides_template(runtime: str, names: Sequence[str]) -> str:
    """A placeholder-only local file: the repository never learns a personal value."""
    lines = [
        f"# Personal values for the {OS_NAME} {runtime} adapter.",
        "# Written by tools/install_skill.py with empty values only. Fill a key and",
        "# re-run the installer; an unfilled key stays a literal ${NAME} in the",
        "# rendered ADAPTER.md, which is how the owner can see what is still missing.",
        "",
    ]
    lines.extend(f"{name}: ''" for name in names)
    return "\n".join(lines) + "\n"


def substitute(text: str, values: dict[str, str]) -> str:
    """Fill `${NAME}` where the local file has a value; leave the rest literal.

    `${HOME}` becomes `~` rather than the absolute path: the render is a
    document the owner reads, and the home directory is a personal value.
    """
    filled = text.replace("${HOME}", "~")
    return PLACEHOLDER_RE.sub(
        lambda match: values.get(match.group(1)) or match.group(0), filled
    )


# -- frontmatter and body ----------------------------------------------


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
    the three, so it is dropped rather than declared as a missing binary.
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
    bundles: Sequence[Bundle],
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

    triggers = list(render.get("disable_model_invocation_on") or [])
    if any(hints.get(hint) for hint in triggers):
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
    effects = tuple(declared(meta, "effects"))
    hints = validate_repo.derived_hints(effects, capabilities)
    version = str(os_block(meta).get("version", ""))
    bundles = tuple(declared_repo_inputs(body))
    frontmatter = render_frontmatter(
        name, meta, body, runtime, adapter, hints, bundles, vocabulary, datastore
    )
    rendered_body = rewrite_links(body, bundles).rstrip("\n")
    trailer = render_trailer(runtime, adapter, commit, version)
    return Rendered(
        name=name,
        version=version,
        effects=effects,
        hints=hints,
        frontmatter=frontmatter,
        text=f"{frontmatter}{rendered_body}\n\n{trailer}",
        bundles=bundles,
        source_dir=skill_source(name),
    )


# -- refusals -----------------------------------------------------------


def unconfirmed_bindings(adapter: dict[str, Any]) -> dict[str, str]:
    """Adapter key -> the note, for every value this runtime cannot attest."""
    unconfirmed: dict[str, str] = {}
    for key, binding in (adapter.get("vocabulary") or {}).items():
        note = str((binding or {}).get("note") or "")
        if note.strip().upper().startswith("UNCONFIRMED"):
            unconfirmed[key] = note.strip()
    return unconfirmed


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
    effects = declared(meta, "effects")
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


def unconfirmed_refusals(
    name: str,
    meta: dict[str, Any],
    body: str,
    adapter: dict[str, Any],
    datastore: dict[str, Any],
    vocabulary: dict[str, Any],
) -> list[str]:
    """One message per term this skill needs and this adapter cannot attest."""
    unconfirmed = unconfirmed_bindings(adapter)
    messages: list[str] = []
    for term, why in sorted(required_terms(meta, body, adapter, datastore, vocabulary).items()):
        key = contracts_check.term_key(term)
        if key in unconfirmed:
            messages.append(
                f"{name}: `{term}` is UNCONFIRMED for {adapter['runtime']} "
                f"({why}) -- {unconfirmed[key]}"
            )
    return messages


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


# -- destination --------------------------------------------------------


def default_dest(adapter: dict[str, Any]) -> Path:
    """`~/.claude/skills` for a host runtime; the staging tree for a shipped one."""
    adapter_file = str(adapter["adapter_file"])
    if PLACEHOLDER_RE.search(adapter_file) or adapter_file.startswith(("~", "/")):
        return expand(str(adapter["skills_dir"]))
    return expand(adapter_file).parent / "skills"


def stamp_path(directory: Path) -> Path:
    return directory / STAMP_NAME


def read_stamp(directory: Path) -> dict[str, Any] | None:
    path = stamp_path(directory)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def stamped_installs(dest: Path) -> list[Path]:
    if not dest.is_dir():
        return []
    return sorted(path for path in dest.iterdir() if path.is_dir() and read_stamp(path))


def write_skill(rendered: Rendered, dest: Path, runtime: str, adapter: dict[str, Any],
                commit: str) -> list[Path]:
    """Replace the stamped directory with this render; report every path written."""
    target = dest / rendered.name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    written = [target / "SKILL.md"]
    (target / "SKILL.md").write_text(rendered.text, encoding="utf-8")

    for name in COPY_DIRS:
        source = rendered.source_dir / name
        if source.is_dir():
            shutil.copytree(source, target / name)
            written.extend(sorted(path for path in (target / name).rglob("*") if path.is_file()))
    for bundle in rendered.bundles:
        destination = target / bundle.installed_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle.source, destination)
        if destination not in written:
            written.append(destination)

    stamp = {
        "name": rendered.name,
        "version": rendered.version,
        "commit": commit,
        "adapter": runtime,
        "adapter_version": adapter.get("version"),
        "sha256": sha256_text(rendered.text),
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "effects": list(rendered.effects),
        "hints": rendered.hints,
    }
    stamp_path(target).write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written.append(stamp_path(target))
    return written


# -- adapter delivery ---------------------------------------------------


def marker_block(adapter: dict[str, Any]) -> str:
    imports = adapter.get("identity_import") or {}
    return f"{imports['begin_marker']}\n{imports['line']}\n{imports['end_marker']}"


def apply_identity_import(text: str, adapter: dict[str, Any]) -> str:
    """The import line between its markers, and not one other byte changed."""
    imports = adapter.get("identity_import") or {}
    begin, end = str(imports["begin_marker"]), str(imports["end_marker"])
    block = marker_block(adapter)
    pattern = re.compile(
        rf"{re.escape(begin)}.*?{re.escape(end)}", re.DOTALL
    )
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return f"{text}{separator}{block}\n"


def install_adapter(
    runtime: str,
    adapter: dict[str, Any],
    overrides_path: Path,
    dry_run: bool,
    report: Report,
) -> list[Path]:
    """Render ADAPTER.md and adapter.resolved.yaml, and bind them to the identity file."""
    names = placeholder_names(runtime)
    values = read_local_overrides(overrides_path)
    written: list[Path] = []

    if not overrides_path.is_file():
        report.notes.append(f"created {overrides_path} with {len(names)} placeholder keys")
        if not dry_run:
            overrides_path.parent.mkdir(parents=True, exist_ok=True)
            overrides_path.write_text(local_overrides_template(runtime, names), encoding="utf-8")
            written.append(overrides_path)
    else:
        absent = [name for name in names if name not in values]
        if absent:
            report.notes.append(
                f"{overrides_path} names no key for {', '.join(absent)}; add "
                + "; ".join(f"{name}: ''" for name in absent)
            )

    unfilled = [name for name in names if not values.get(name)]
    if unfilled:
        report.notes.append(
            f"unfilled placeholders (left literal in the render): {', '.join(unfilled)}"
        )

    adapter_md = expand(str(adapter["adapter_file"]))
    resolved = adapter_md.parent / "adapter.resolved.yaml"
    rendered = substitute(adapter_template(runtime).read_text(encoding="utf-8"), values)
    source_yaml = (repo_root() / "adapters" / runtime / "adapter.yaml").read_text(encoding="utf-8")
    rendered_yaml = (
        f"# Rendered by tools/install_skill.py from adapters/{runtime}/adapter.yaml\n"
        f"# and {display_path(str(overrides_path))}. Personal values live only here.\n"
        + substitute(source_yaml, values)
    )
    if not dry_run:
        adapter_md.parent.mkdir(parents=True, exist_ok=True)
        adapter_md.write_text(rendered, encoding="utf-8")
        resolved.write_text(rendered_yaml, encoding="utf-8")
    written.extend([adapter_md, resolved])

    written.extend(bind_identity_file(adapter, dry_run, report))
    return written


def bind_identity_file(adapter: dict[str, Any], dry_run: bool, report: Report) -> list[Path]:
    """Insert the import line into the runtime's identity file, or print the manual step."""
    imports = adapter.get("identity_import") or {}
    raw = str(imports.get("file") or "")
    if not raw:
        return []
    if not (raw.startswith(("~", "/")) or PLACEHOLDER_RE.search(raw)):
        report.notes.append(
            f"identity file {raw!r} is not on this host: add the line "
            f"{imports['line']!r} between {imports['begin_marker']} and "
            f"{imports['end_marker']} there yourself"
        )
        return []

    path = expand(raw)
    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    after = apply_identity_import(before, adapter)
    if after == before:
        report.notes.append(f"{display_path(str(path))} already carries the import line")
        return []
    had_markers = str(imports["begin_marker"]) in before
    report.notes.append(
        f"{display_path(str(path))}: import line "
        f"{'refreshed between the' if had_markers else 'appended with new'} "
        f"{OS_NAME} markers"
    )
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
    return [path]


def print_diff(path: Path, before: str, after: str) -> None:
    import difflib

    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
    )
    for line in diff:
        print(line.rstrip("\n"))


# -- actions ------------------------------------------------------------


@dataclass(frozen=True)
class Context:
    runtime: str
    adapter: dict[str, Any]
    capabilities: dict[str, dict[str, Any]]
    datastore: dict[str, Any]
    vocabulary: dict[str, Any]
    dest: Path
    commit: str


def build_context(args: argparse.Namespace) -> Context:
    adapters = load_contract("adapters")
    adapter = adapter_for(args.runtime, adapters)
    check_adapter_template(args.runtime, adapter)
    dest = expand(args.dest) if args.dest else default_dest(adapter)
    return Context(
        runtime=args.runtime,
        adapter=adapter,
        capabilities=validate_repo.effect_enum(load_contract("capabilities")),
        datastore=load_contract("datastore"),
        vocabulary=load_contract("vocabulary"),
        dest=dest,
        commit=repo_commit(),
    )


def runtime_skills(runtime: str) -> list[str]:
    """Every repository skill whose declaration carries this runtime."""
    names: list[str] = []
    skills = repo_root() / "skills"
    for directory in sorted(path for path in skills.iterdir() if path.is_dir()):
        try:
            meta, _, _ = read_skill(directory.name)
        except InstallError:
            continue
        if runtime in declared(meta, "runtime"):
            names.append(directory.name)
    return names


def do_install(context: Context, names: Sequence[str], args: argparse.Namespace) -> int:
    report = Report()
    overrides = local_overrides_path(context.adapter, args.local_overrides)
    identity_path = expand(str((context.adapter.get("identity_import") or {}).get("file") or ""))
    identity_before = (
        identity_path.read_text(encoding="utf-8") if identity_path.is_file() else ""
    )

    renders: list[Rendered] = []
    for name in names:
        try:
            meta, body, _ = read_skill(name)
        except InstallError as exc:
            report.refused.append(str(exc))
            continue
        if context.runtime not in declared(meta, "runtime"):
            report.refused.append(
                f"{name}: metadata.{OS_NAME}.runtime is "
                f"{declared(meta, 'runtime')}, which excludes {context.runtime}"
            )
            continue
        refusals = unconfirmed_refusals(
            name, meta, body, context.adapter, context.datastore, context.vocabulary
        )
        if refusals:
            report.refused.extend(refusals)
            continue
        target = context.dest / name
        if target.exists() and read_stamp(target) is None:
            report.refused.append(
                f"{name}: {target} exists and was not installed by {OS_NAME} "
                f"(no {STAMP_NAME}); refusing to overwrite it"
            )
            continue
        try:
            renders.append(
                render_skill(
                    name,
                    context.runtime,
                    context.adapter,
                    context.capabilities,
                    context.commit,
                    context.vocabulary,
                    context.datastore,
                )
            )
        except InstallError as exc:
            report.refused.append(str(exc))

    report.notes.extend(fallback_warnings(context.adapter, context.vocabulary))
    written = install_adapter(context.runtime, context.adapter, overrides, args.dry_run, report)

    print(f"{context.runtime}: destination {context.dest}")
    for path in written:
        print(f"  {'would write' if args.dry_run else 'wrote'} {path}")

    for rendered in renders:
        print(f"\n--- {rendered.name} ---")
        print(rendered.frontmatter.rstrip("\n"))
        if args.dry_run:
            print(f"  would write {context.dest / rendered.name / 'SKILL.md'}")
            for bundle in rendered.bundles:
                print(f"  would write {context.dest / rendered.name / bundle.installed_rel}")
            print(f"  would write {stamp_path(context.dest / rendered.name)}")
        else:
            for path in write_skill(rendered, context.dest, context.runtime, context.adapter,
                                    context.commit):
                print(f"  wrote {path}")
        report.installed.append(rendered.name)

    if identity_path and str(identity_path) != str(repo_root()):
        identity_after = (
            identity_path.read_text(encoding="utf-8")
            if identity_path.is_file() and not args.dry_run
            else apply_identity_import(identity_before, context.adapter)
        )
        if identity_after != identity_before:
            print(f"\n--- {display_path(str(identity_path))} ---")
            print_diff(identity_path, identity_before, identity_after)

    return finish(context, report, args)


def finish(context: Context, report: Report, args: argparse.Namespace) -> int:
    print()
    if report.installed:
        verb = "would install" if args.dry_run else "installed"
        print(f"{verb}: {', '.join(report.installed)}")
    for note in report.notes:
        print(f"note: {note}")
    for refusal in report.refused:
        print(f"refused: {refusal}")

    identity = context.adapter.get("identity_import") or {}
    raw = str(identity.get("file") or "")
    if raw.startswith(("~", "/")) or PLACEHOLDER_RE.search(raw):
        target = expand(raw).parent
        print(
            f"\nRun this yourself if {display_path(str(target))} is a git repository "
            "(the installer never commits):"
        )
        print(f'  git -C {display_path(str(target))} commit -am "registry: {OS_NAME} adapter"')
    if context.runtime == "openclaw":
        staging = expand(str(context.adapter["adapter_file"])).parent
        print("\nCopy the staging tree onto the runtime volume, then reload it:")
        print(f"  railway ssh -- 'mkdir -p /data/.openclaw/workspace'")
        print(f"  # then copy {staging}/ to /data/.openclaw/workspace/")
    return 1 if report.refused else 0


def do_check(context: Context, names: Sequence[str]) -> int:
    report = Report()
    installs = stamped_installs(context.dest)
    if names:
        installs = [path for path in installs if path.name in set(names)]
    print(f"{context.runtime}: checking {len(installs)} stamped install(s) in {context.dest}")

    for directory in installs:
        name = directory.name
        stamp = read_stamp(directory) or {}
        actual = (directory / "SKILL.md").read_text(encoding="utf-8")
        if sha256_text(actual) != stamp.get("sha256"):
            report.drift.append(f"{name}: SKILL.md sha256 differs from the stamp; edited in place")
        if stamp.get("adapter_version") != context.adapter.get("version"):
            report.drift.append(
                f"{name}: stamp adapter_version {stamp.get('adapter_version')} but "
                f"adapters/{context.runtime}/adapter.yaml is v{context.adapter.get('version')}"
            )
        try:
            meta, body, _ = read_skill(name)
        except InstallError as exc:
            report.drift.append(f"{name}: {exc}")
            continue

        effects = declared(meta, "effects")
        if effects != list(stamp.get("effects") or []):
            report.drift.append(
                f"{name}: stamp effects {stamp.get('effects')} but the repository "
                f"declares {effects}"
            )
        hints = validate_repo.derived_hints(tuple(effects), context.capabilities)
        if hints != (stamp.get("hints") or {}):
            report.drift.append(f"{name}: derived hints {hints} differ from the stamp's")

        for message in unconfirmed_refusals(
            name, meta, body, context.adapter, context.datastore, context.vocabulary
        ):
            report.drift.append(message)

        try:
            rendered = render_skill(
                name,
                context.runtime,
                context.adapter,
                context.capabilities,
                str(stamp.get("commit") or ""),
                context.vocabulary,
                context.datastore,
            )
        except InstallError as exc:
            report.drift.append(f"{name}: {exc}")
            continue
        if sha256_text(rendered.text) != stamp.get("sha256"):
            report.drift.append(
                f"{name}: a fresh render at the stamped commit has a different sha256; "
                "the source or the adapter changed since the install"
            )
        report.drift.extend(undefined_terms(name, actual, context))

    for drift in report.drift:
        print(f"drift: {drift}")
    if not report.drift:
        print("no drift.")
    return 1 if report.drift else 0


def undefined_terms(name: str, text: str, context: Context) -> list[str]:
    """Term-shaped backticks in the installed body that the adapter binds nothing for."""
    vocab = validate_repo.vocabulary_view(context.vocabulary)
    heads = {str(term).split()[-1] for term in vocab.terms}
    bound = context.adapter.get("vocabulary") or {}
    problems: list[str] = []
    for token in dict.fromkeys(validate_repo.BACKTICKED_RE.findall(validate_repo.skill_body(text))):
        if token in vocab.aliases:
            problems.append(f"{name}: body uses the alias `{token}`, not `{vocab.aliases[token]}`")
            continue
        if token in vocab.terms:
            key = vocab.terms[token]
            if not str((bound.get(key) or {}).get("value") or "").strip():
                problems.append(
                    f"{name}: body uses `{token}` but adapters/{context.runtime}/"
                    "adapter.yaml binds no value for it"
                )
            continue
        words = token.split()
        if len(words) > 1 and TERM_SHAPED_RE.match(token) and words[-1] in heads:
            problems.append(
                f"{name}: body uses `{token}`, which adapters/vocabulary.yaml does not "
                "define, so the adapter binds nothing for it"
            )
    return problems


def do_uninstall(context: Context, names: Sequence[str], args: argparse.Namespace) -> int:
    report = Report()
    if args.all:
        targets = stamped_installs(context.dest)
    else:
        targets = []
        for name in names:
            directory = context.dest / name
            if read_stamp(directory) is None:
                report.refused.append(
                    f"{name}: {directory} carries no {STAMP_NAME}; only {OS_NAME} "
                    "installs are removed"
                )
                continue
            targets.append(directory)

    for directory in targets:
        print(f"{'would remove' if args.dry_run else 'removed'} {directory}")
        if not args.dry_run:
            shutil.rmtree(directory)
        report.installed.append(directory.name)
    for refusal in report.refused:
        print(f"refused: {refusal}")
    return 1 if report.refused else 0


def do_list(context: Context, names: Sequence[str]) -> int:
    installs = stamped_installs(context.dest)
    if names:
        installs = [path for path in installs if path.name in set(names)]
    print(f"{context.runtime}: {len(installs)} stamped install(s) in {context.dest}")
    for directory in installs:
        stamp = read_stamp(directory) or {}
        print(
            f"  {stamp.get('name', directory.name)}  v{stamp.get('version')}  "
            f"adapter {stamp.get('adapter')} v{stamp.get('adapter_version')}  "
            f"{str(stamp.get('commit'))[:COMMIT_DISPLAY_CHARS]}  "
            f"{stamp.get('installed_at')}  effects={stamp.get('effects')}"
        )
    return 0


# -- entry point --------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install_skill.py",
        description="Render and install skills for one runtime, and audit what is installed.",
    )
    parser.add_argument("--runtime", required=True, choices=list(RUNTIMES))
    parser.add_argument("--dest", help="override the runtime's default destination")
    parser.add_argument("--all", action="store_true", help="every skill the runtime carries")
    parser.add_argument("--check", action="store_true", help="declared-vs-actual; exit 1 on drift")
    parser.add_argument("--uninstall", action="store_true", help="remove stamped installs")
    parser.add_argument("--list", action="store_true", dest="list_", help="read the stamps")
    parser.add_argument("--dry-run", action="store_true", help="print, write nothing")
    parser.add_argument("--local-overrides", help="override the adapter's local_overrides_file")
    parser.add_argument("names", nargs="*", metavar="NAME")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    actions = [args.check, args.uninstall, args.list_]
    if sum(bool(action) for action in actions) > 1:
        print("usage: --check, --uninstall and --list are mutually exclusive")
        return 2
    installing = not any(actions)
    if installing and not args.names and not args.all:
        print("usage: name at least one skill, or pass --all")
        return 2

    try:
        if installing or args.check:
            code = run_validator()
            if code != 0:
                print(f"refused: tools/validate_repo.py exited {code}; the library is not valid")
                return 1
        context = build_context(args)
        names = list(args.names)
        if installing and args.all:
            names = runtime_skills(args.runtime)
        if args.check:
            return do_check(context, names)
        if args.uninstall:
            return do_uninstall(context, names, args)
        if args.list_:
            return do_list(context, names)
        return do_install(context, names, args)
    except InstallError as exc:
        print(f"refused: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
