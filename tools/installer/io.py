#!/usr/bin/env python3
"""Everything that touches a path outside the repository.

Writing a skill directory and its stamp, delivering the rendered adapter, and
editing the runtime's identity file between its markers -- the operations a
caller has to be able to preview before running.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

try:
    from tools import contracts_check, validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import contracts_check  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

from .render import (
    COMMIT_DISPLAY_CHARS, COPY_DIRS, EXCLUDED_NAMES, InstallError, LAUNCHER_INDEX, OS_NAME,
    PLACEHOLDER_RE, Rendered, Report, STAMP_NAME, annotate_index, declared, display_path,
    expand, repo_root, sha256_bytes, sha256_text
)


# A changelog nobody can derive says why, rather than printing an empty list.
CHANGELOG_UNKNOWN = "changes unknown"


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


def changes_since(commit: str, paths: Sequence[str]) -> tuple[list[str], str]:
    """`git log` from a stamp's commit to HEAD over `paths`, or why there is none.

    Returns the one-line log entries and an empty string, or an empty list and
    the reason nobody can derive them -- a stamp written before the field
    existed, a commit this clone does not have, no git at all. An update that
    cannot say what changed says that, rather than printing nothing and letting
    it read as "nothing changed".
    """
    if not str(commit or "").strip():
        return [], f"{CHANGELOG_UNKNOWN} -- pre-commit stamp"
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_root()), "log", "--oneline", "--no-decorate",
                f"{commit}..HEAD", "--", *paths,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return [], f"{CHANGELOG_UNKNOWN} -- git could not be run here ({exc})"
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        return [], (
            f"{CHANGELOG_UNKNOWN} -- git could not read "
            f"{commit[:COMMIT_DISPLAY_CHARS]}..HEAD "
            f"({stderr[0] if stderr else 'no output'})"
        )
    return [line for line in result.stdout.splitlines() if line.strip()], ""


def inside_git_work_tree(path: Path) -> bool:
    """True when `path` (or the nearest existing parent) sits in a git work tree.

    The nearest existing parent, because the directory the adapter renders into
    may not exist until this run creates it -- and a dry run has to reach the
    same verdict as the real one.
    """
    probe = Path(path)
    while not probe.is_dir() and probe != probe.parent:
        probe = probe.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_ignored(path: Path) -> bool:
    """True when git is configured to ignore `path`.

    `check-ignore` is pattern-based, so it answers for a file this run has not
    written yet and a dry run reaches the same verdict as the real one. A path
    outside any work tree is not ignored -- `inside_git_work_tree` is what
    decides that case.
    """
    target = Path(path)
    probe = target.parent
    while not probe.is_dir() and probe != probe.parent:
        probe = probe.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(probe), "check-ignore", "-q", "--", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def run_validator() -> int:
    """`tools/validate_repo.py`, run in-process; the install refuses on failure."""
    return validate_repo.main([])


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


def placeholder_note(
    overrides_path: Path,
    names: Sequence[str],
    absent: Sequence[str],
    unfilled: Sequence[str],
    created: bool,
    dry_run: bool,
) -> list[str]:
    """One note, or none: the file to edit and the keys to edit in it.

    They were two notes -- one naming the path, one listing the keys -- so the
    reader who found the key list had to hunt upwards for the file it belonged
    to. Everything about the local values now says its piece once.
    """
    display = display_path(str(overrides_path))
    fix = ". Fill them there and re-run, or run python3 tools/bootstrap.py"
    if not names:
        return []
    if created:
        # The template this run writes names every key with an empty value, so
        # `absent` describes nothing by the time the note is read.
        return [
            f"{'would create' if dry_run else 'created'} {display} with {len(names)} "
            f"placeholder keys; {len(names)} unfilled placeholders, left literal in "
            f"the render: {', '.join(names)}{fix}"
        ]
    if not unfilled:
        return []
    clauses = [
        f"{display}: {len(unfilled)} of {len(names)} unfilled placeholders, left "
        f"literal in the render: {', '.join(unfilled)}"
    ]
    if absent:
        clauses.append(
            f"{len(absent)} of them named nowhere in that file, to be added as "
            + "; ".join(f"{name}: ''" for name in absent)
        )
    return ["; ".join(clauses) + fix]


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


@dataclass(frozen=True)
class Planned:
    """One file an install writes: where it lands, what it holds, how it is read.

    `mode` is carried for a file copied out of `scripts/` or another supporting
    directory, which may be executed rather than read; a rendered or bundled
    file takes the default the filesystem gives it.
    """

    rel: str
    data: bytes
    mode: int | None = None


def planned_files(
    rendered: Rendered,
    statuses: dict[str, str] | None = None,
    skipped: list[str] | None = None,
) -> dict[str, Planned]:
    """Every file installing this render writes, keyed by its path in the skill dir.

    One reading of what an install puts in a directory, so the digests the stamp
    records, the bytes `write_skill` lays down, and the files `--update`
    compares against cannot drift apart. `skipped` collects any entry the skill
    carries that is neither rendered, copied, nor excluded by name. `statuses`
    maps a skill name to its state in this destination; where it is given, the
    bundled catalog index is annotated with that extra column rather than
    carried byte for byte.
    """
    skipped = [] if skipped is None else skipped
    planned: dict[str, Planned] = {"SKILL.md": Planned("SKILL.md", rendered.text.encode("utf-8"))}

    for source in sorted(rendered.source_dir.iterdir()):
        if source.name == "SKILL.md" or source.name in EXCLUDED_NAMES:
            continue  # rendered above, or eval material the install never carries
        if source.is_dir() and source.name in COPY_DIRS:
            for path in sorted(item for item in source.rglob("*") if item.is_file()):
                rel = path.relative_to(rendered.source_dir).as_posix()
                planned[rel] = Planned(rel, path.read_bytes(), path.stat().st_mode & 0o777)
        else:
            skipped.append(source.name)

    for bundle in rendered.bundles:
        rel = PurePosixPath(bundle.installed_rel).as_posix()
        if statuses is not None and bundle.repo_rel == LAUNCHER_INDEX:
            data = annotate_index(
                bundle.source.read_text(encoding="utf-8"), statuses
            ).encode("utf-8")
        else:
            data = bundle.source.read_bytes()
        # A bundle landing on a path a copied directory already filled replaces
        # it, and is still one file: the dict keeps the first position and the
        # last bytes, which is what the loops above wrote.
        planned[rel] = Planned(rel, data, planned[rel].mode if rel in planned else None)
    return planned


def file_digests(planned: dict[str, Planned]) -> dict[str, str]:
    """The stamp's per-file record: one digest per path this install writes."""
    return {rel: sha256_bytes(item.data) for rel, item in planned.items()}


def installed_digests(directory: Path) -> dict[str, str]:
    """Every file in an installed skill directory, by digest -- the stamp excluded.

    Symlinks are neither followed nor descended into: what they point at is not
    this install's, and reading through one would let a link outside the
    destination answer for a file inside it.
    """
    digests: dict[str, str] = {}
    for root, directories, names in os.walk(directory, followlinks=False):
        directories[:] = sorted(
            name for name in directories if not Path(root, name).is_symlink()
        )
        for name in sorted(names):
            path = Path(root, name)
            if path.is_symlink():
                continue
            rel = path.relative_to(directory).as_posix()
            if rel == STAMP_NAME:
                continue
            digests[rel] = sha256_bytes(path.read_bytes())
    return digests


def write_planned(target: Path, planned: dict[str, Planned],
                  only: Sequence[str] | None = None) -> list[Path]:
    """Lay down the planned files (or just `only` of them) and return their paths."""
    written: list[Path] = []
    wanted = None if only is None else set(only)
    for rel, item in planned.items():
        if wanted is not None and rel not in wanted:
            continue
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.data)
        if item.mode is not None:
            os.chmod(path, item.mode)
        written.append(path)
    return written


def write_stamp(target: Path, stamp: dict[str, Any]) -> Path:
    path = stamp_path(target)
    path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_skill(rendered: Rendered, dest: Path, runtime: str, adapter: dict[str, Any],
                commit: str, skipped: list[str] | None = None,
                statuses: dict[str, str] | None = None) -> list[Path]:
    """Replace the stamped directory with this render; report every path written."""
    target = dest / rendered.name
    if target.is_symlink():
        raise InstallError(f"{target}: is a symlink; refusing to remove or write through it")
    planned = planned_files(rendered, statuses, skipped)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    written = write_planned(target, planned)

    stamp = {
        "name": rendered.name,
        "version": rendered.version,
        "commit": commit,
        "adapter": runtime,
        "adapter_version": adapter.get("version"),
        "sha256": sha256_text(rendered.text),
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capabilities": list(rendered.capabilities),
        "hints": rendered.hints,
        # Per file, not per skill: a bundled input or a copied script edited in
        # the install is drift the skill-level hash could not see.
        "files": file_digests(planned),
    }
    written.append(write_stamp(target, stamp))
    return written


def marker_block(adapter: dict[str, Any]) -> list[str]:
    """The three lines the identity file carries: begin, the import, end."""
    imports = adapter.get("identity_import") or {}
    return [str(imports["begin_marker"]), str(imports["line"]), str(imports["end_marker"])]


def marker_lines(lines: Sequence[str], marker: str) -> list[int]:
    """1-based line numbers where a line is exactly this marker."""
    return [number for number, line in enumerate(lines, 1) if line.strip() == marker]


def locate_block(lines: Sequence[str], begin: str, end: str) -> tuple[int, int] | None:
    """The one well-formed marker pair as 0-based indices, or None when absent.

    Anything else is refused rather than repaired. A begin without its end has
    no block to replace: appending one would swallow every owner line between
    the two markers, and the next run would delete them as ours.
    """
    begins, ends = marker_lines(lines, begin), marker_lines(lines, end)
    if not begins and not ends:
        return None
    if len(begins) > 1 or len(ends) > 1:
        raise InstallError(
            f"identity file carries more than one {OS_NAME} block: "
            f"{begin!r} at line {begins}, {end!r} at line {ends}; "
            "leave exactly one and re-run"
        )
    if not begins or not ends:
        marker, numbers = (begin, begins) if begins else (end, ends)
        missing = end if begins else begin
        buried = [
            number
            for number, line in enumerate(lines, 1)
            if missing in line and line.strip() != missing
        ]
        where = (
            f"{missing!r} shares line {buried[0]} with other text"
            if buried
            else f"{marker!r} at line {numbers[0]} has no {missing!r}"
        )
        raise InstallError(
            f"identity file carries an unpaired marker: {where}; the block is not "
            "ours to repair, so nothing was written"
        )
    if ends[0] < begins[0]:
        raise InstallError(
            f"identity file carries {end!r} (line {ends[0]}) before {begin!r} "
            f"(line {begins[0]}); nothing was written"
        )
    return begins[0] - 1, ends[0] - 1


def apply_identity_import(text: str, adapter: dict[str, Any]) -> str:
    """The import line between its markers, and not one other line changed.

    A bare import line loose in the file is removed, so exactly one survives:
    the one inside the block, where an uninstall can find it again.
    """
    imports = adapter.get("identity_import") or {}
    begin, end = str(imports["begin_marker"]), str(imports["end_marker"])
    import_line = str(imports["line"])
    block = marker_block(adapter)
    lines = text.splitlines()
    found = locate_block(lines, begin, end)

    def without_stray(rows: Sequence[str]) -> list[str]:
        return [row for row in rows if row.strip() != import_line]

    if found is not None:
        first, last = found
        kept = without_stray(lines[:first]) + block + without_stray(lines[last + 1:])
    else:
        kept = without_stray(lines)
        while kept and not kept[-1].strip():
            kept.pop()
        kept = kept + ([""] if kept else []) + block
    return "\n".join(kept) + "\n"


def write_text_atomically(path: Path, text: str) -> None:
    """Write through a temporary file in the same directory, then rename over.

    The identity file is the owner's, and a half-written CLAUDE.md is worse
    than an unwritten one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{OS_NAME}.tmp"
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise InstallError(f"{display_path(str(path))}: not written ({exc})") from exc


def install_adapter(
    runtime: str,
    adapter: dict[str, Any],
    overrides_path: Path,
    dry_run: bool,
    report: Report,
    require_configured: bool = True,
) -> list[Path]:
    """Render ADAPTER.md and adapter.resolved.yaml, and bind them to the identity file.

    `require_configured` is the exit code the render earns: a run that leaves a
    `${NAME}` literal in the file every installed skill reads has not configured
    this host, and says so with a nonzero exit rather than a note under a
    successful one. `--allow-unconfigured` turns it off for a caller that means
    it -- `tools/bootstrap.py`, which asks for the values itself and fails on
    its own before it ever gets here.
    """
    names = placeholder_names(runtime)
    values = read_local_overrides(overrides_path)
    written: list[Path] = []

    created = not overrides_path.is_file()
    if created:
        written.append(overrides_path)
        if not dry_run:
            overrides_path.parent.mkdir(parents=True, exist_ok=True)
            overrides_path.write_text(local_overrides_template(runtime, names), encoding="utf-8")
    absent = [name for name in names if name not in values]
    unfilled = [name for name in names if not values.get(name)]
    report.notes.extend(placeholder_note(overrides_path, names, absent, unfilled, created, dry_run))

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

    if unfilled and require_configured:
        report.refused.append(
            f"{display_path(str(overrides_path))}: {len(unfilled)} of {len(names)} "
            f"unfilled placeholders, so {display_path(str(adapter_md))} -- the file "
            "every installed skill resolves its runtime terms against -- still "
            "carries them as literals; the note above names the keys. Fill them and "
            "re-run, run python3 tools/bootstrap.py, or pass --allow-unconfigured to "
            "install into an unconfigured host on purpose"
        )

    if inside_git_work_tree(adapter_md.parent) and not git_ignored(resolved):
        # The repository's own adapter carries only ${PLACEHOLDER}s; this render
        # is the one file where the owner's values are written out, and it lands
        # in a directory git is watching. A destination git already ignores --
        # `dist/`, which `make stage-openclaw` renders into -- is not one a
        # commit can carry, so it earns no note.
        report.notes.append(
            f"{display_path(str(resolved))} is inside a git work tree and holds the "
            "personal values from the overrides file; keep it out of a commit"
        )

    written.extend(bind_identity_file(adapter, dry_run, report))
    return written


def bind_identity_file(adapter: dict[str, Any], dry_run: bool, report: Report) -> list[Path]:
    """Insert the import line into the runtime's identity file, or print the manual step."""
    imports = adapter.get("identity_import") or {}
    raw = str(imports.get("file") or "")
    if not raw:
        return []
    # A file this installer edits has to be a path on this host. `${HOME}/x` is
    # one once the environment fills it; a placeholder the environment does not
    # know -- OpenClaw's identity file lives in another repository, named as
    # "runtime/workspace/AGENTS.md in ${DEPLOY_REPO}" -- leaves a string that is
    # a sentence rather than a path, and the run prints the manual step.
    if not os.path.expandvars(raw).startswith(("~", "/")):
        report.notes.append(
            f"identity file {raw!r} is not on this host: add the line "
            f"{imports['line']!r} between {imports['begin_marker']} and "
            f"{imports['end_marker']} there yourself"
        )
        return []

    path = expand(raw)
    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        after = apply_identity_import(before, adapter)
    except InstallError as exc:
        report.refused.append(f"{display_path(str(path))}: {exc}")
        return []
    if after == before:
        report.notes.append(f"{display_path(str(path))} already carries the import line")
        return []
    report.identity_change = (path, before, after)
    had_markers = str(imports["begin_marker"]) in before
    report.notes.append(
        f"{display_path(str(path))}: import line "
        f"{'refreshed between the' if had_markers else 'appended with new'} "
        f"{OS_NAME} markers"
    )
    if not dry_run:
        write_text_atomically(path, after)
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
