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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from tools import contracts_check, validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import contracts_check  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

from .render import (
    COPY_DIRS, EXCLUDED_NAMES, InstallError, LAUNCHER_INDEX, OS_NAME, PLACEHOLDER_RE,
    Rendered, Report, STAMP_NAME, annotate_index, declared, display_path, expand,
    repo_root, sha256_text
)


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
                commit: str, skipped: list[str] | None = None,
                statuses: dict[str, str] | None = None) -> list[Path]:
    """Replace the stamped directory with this render; report every path written.

    `skipped` collects any entry the skill carries that is neither rendered,
    copied, nor excluded by name, so an unexpected file is reported rather than
    dropped in silence. `statuses` maps a skill name to its state in this
    destination; where it is given, the bundled catalog index is written with
    that extra column rather than copied byte for byte.
    """
    skipped = [] if skipped is None else skipped
    target = dest / rendered.name
    if target.is_symlink():
        raise InstallError(f"{target}: is a symlink; refusing to remove or write through it")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    written = [target / "SKILL.md"]
    (target / "SKILL.md").write_text(rendered.text, encoding="utf-8")

    for source in sorted(rendered.source_dir.iterdir()):
        if source.name == "SKILL.md" or source.name in EXCLUDED_NAMES:
            continue  # rendered above, or eval material the install never carries
        if source.is_dir() and source.name in COPY_DIRS:
            shutil.copytree(source, target / source.name)
            written.extend(
                sorted(path for path in (target / source.name).rglob("*") if path.is_file())
            )
        else:
            skipped.append(source.name)
    for bundle in rendered.bundles:
        destination = target / bundle.installed_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if statuses is not None and bundle.repo_rel == LAUNCHER_INDEX:
            destination.write_text(
                annotate_index(bundle.source.read_text(encoding="utf-8"), statuses),
                encoding="utf-8",
            )
        else:
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
) -> list[Path]:
    """Render ADAPTER.md and adapter.resolved.yaml, and bind them to the identity file."""
    names = placeholder_names(runtime)
    values = read_local_overrides(overrides_path)
    written: list[Path] = []

    if not overrides_path.is_file():
        report.notes.append(
            f"{'would create' if dry_run else 'created'} {overrides_path} with "
            f"{len(names)} placeholder keys"
        )
        written.append(overrides_path)
        if not dry_run:
            overrides_path.parent.mkdir(parents=True, exist_ok=True)
            overrides_path.write_text(local_overrides_template(runtime, names), encoding="utf-8")
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
