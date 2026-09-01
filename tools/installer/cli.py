#!/usr/bin/env python3
"""The four actions and the argument parser: install, check, uninstall, list."""

from __future__ import annotations

import argparse
import difflib
import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from tools import validate_repo
except ImportError:  # pragma: no cover - one of the two branches always runs.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import validate_repo  # type: ignore[no-redef]

from .render import (
    COMMIT_DISPLAY_CHARS, COPY_DIRS, InstallError, OS_NAME, RUNTIMES, Rendered, Report,
    STAMP_NAME, STATUS_INSTALLED, STATUS_NOT_INSTALLED, TERM_SHAPED_RE, adapter_for,
    declared, degraded_notes, display_path, expand, fallback_warnings, load_contract,
    read_skill, render_skill, repo_root, sha256_bytes, sha256_text, unconfirmed_refusals,
    unconfirmed_term
)
from .io import (
    adapter_notes, check_adapter_template, default_dest, install_adapter,
    installed_digests, local_overrides_path, planned_files, print_diff, read_stamp,
    stamp_path, stamped_installs, write_planned, write_skill, write_stamp
)
from . import io

# What a stamp written before per-file digests can still be asked. It is read
# rather than rejected: the install it describes is ours, it just says less.
PRE_DIGEST_NOTE = (
    "no per-file digests recorded (pre-digest stamp); re-install to upgrade the stamp"
)


# An update's diff is there to be read, not scrolled: past this many lines it
# names the file and stops, because the file itself is the better place to look.
DIFF_PREVIEW_LINES = 40


CHANGELOG_MAX = 10


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
        commit=io.repo_commit(),
    )


def runtime_skills(runtime: str) -> list[str]:
    """Every repository skill whose declaration carries this runtime."""
    names: list[str] = []
    skills = repo_root() / "skills"
    for directory in sorted(path for path in skills.iterdir() if path.is_dir()):
        try:
            meta, _, _ = read_skill(directory.name)
        except InstallError as exc:
            print(f"note: {directory.name} is not installable: {exc}")
            continue
        if runtime in declared(meta, "runtime"):
            names.append(directory.name)
    return names


def install_statuses(context: Context, rendering: Sequence[str]) -> dict[str, str]:
    """Every repository skill's state in this destination, for the launcher's index.

    A term this adapter cannot attest is reported first and by name: the skill
    is one the runtime refuses, whatever a stale directory in the destination
    still holds. Otherwise a skill is `installed` when this run renders it or
    the destination already carries it stamped, and `not installed` when neither
    is true -- which is what stops the launcher routing to a skill that is not
    there.
    """
    statuses: dict[str, str] = {}
    stamped = {path.name for path in stamped_installs(context.dest)}
    rendering_set = set(rendering)
    skills = repo_root() / "skills"
    if not skills.is_dir():
        return statuses
    for directory in sorted(path for path in skills.iterdir() if path.is_dir()):
        name = directory.name
        try:
            meta, body, _ = read_skill(name)
        except InstallError:
            continue
        term = unconfirmed_term(
            name, meta, body, context.adapter, context.datastore, context.vocabulary
        )
        if term is not None:
            statuses[name] = f"refused: {term}"
        elif name in rendering_set or name in stamped:
            statuses[name] = STATUS_INSTALLED
        else:
            statuses[name] = STATUS_NOT_INSTALLED
    return statuses


def recorded_digests(stamp: dict[str, Any]) -> dict[str, str] | None:
    """The stamp's per-file record, or None where it was written without one."""
    files = stamp.get("files")
    if not isinstance(files, dict) or not files:
        return None
    return {str(key): str(value) for key, value in files.items()}


UNREADABLE = "could not be read"


UNWRITABLE = "could not be written"


def file_drift(name: str, directory: Path, recorded: dict[str, str]) -> list[str]:
    """Every installed file that is not the file the stamp recorded.

    SKILL.md is left out: the stamp's own `sha256` reports it, in the words
    `--check` has always used. A file the stamp never recorded is drift too --
    the stamp is the manifest of what this installer wrote, and a directory it
    owns holding anything else is exactly what a declared-vs-actual pass exists
    to find. Nothing here removes a file.
    """
    unreadable: dict[str, str] = {}
    actual = installed_digests(directory, unreadable)
    problems = [
        f"{name}: {rel} {UNREADABLE} ({problem}); not checked"
        for rel, problem in sorted(unreadable.items())
    ]
    for rel, digest in sorted(recorded.items()):
        if rel == "SKILL.md" or rel in unreadable:
            continue  # rendered elsewhere, or already named as unreadable above
        if rel not in actual:
            problems.append(
                f"{name}: {rel} is recorded by the stamp and missing from the install"
            )
        elif actual[rel] != digest:
            problems.append(f"{name}: {rel} sha256 differs from the stamp; edited in place")
    for rel in sorted(set(actual) - set(recorded) - set(unreadable)):
        problems.append(
            f"{name}: {rel} is not recorded by the stamp; no install wrote it, and "
            "nothing here removes it"
        )
    return problems


def do_install(context: Context, names: Sequence[str], args: argparse.Namespace) -> int:
    report = Report()
    overrides = local_overrides_path(context.adapter, args.local_overrides)
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
        report.notes.extend(
            f"degraded: {note}"
            for note in degraded_notes(
                name, meta, body, context.adapter, context.datastore, context.vocabulary
            )
        )
        target = context.dest / name
        if target.is_symlink():
            report.refused.append(
                f"{name}: {target} is a symlink; refusing to write through it "
                "and never following it to whatever it points at"
            )
            continue
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
    if renders:
        written = install_adapter(
            context.runtime, context.adapter, overrides, args.dry_run, report,
            require_configured=not args.allow_unconfigured,
        )
    else:
        # The adapter (and the identity-file line that imports it) exists to serve
        # installed skills. A run that rendered none of them has nothing to bind,
        # and must not edit the owner's identity file on its way to exit 1.
        written = []
        report.notes.append(
            "no skill rendered; the adapter files and the identity file are untouched"
        )

    # The notes lead: a placeholder left literal or a binding running DEGRADED is
    # what this run needs the reader to act on, and under the render dump it was
    # the last thing printed. `finish` prints whatever the write loop adds after.
    for note in report.notes:
        print(f"note: {note}")
    report.printed_notes = len(report.notes)

    print(f"{context.runtime}: destination {context.dest}")
    for path in written:
        print(f"  {'would write' if args.dry_run else 'wrote'} {path}")

    statuses = install_statuses(context, [rendered.name for rendered in renders])
    for rendered in renders:
        print(f"\n--- {rendered.name} ---")
        print(rendered.frontmatter.rstrip("\n"))
        if args.dry_run:
            print(f"  would write {context.dest / rendered.name / 'SKILL.md'}")
            for bundle in rendered.bundles:
                print(f"  would write {context.dest / rendered.name / bundle.installed_rel}")
            print(f"  would write {stamp_path(context.dest / rendered.name)}")
        else:
            skipped: list[str] = []
            for path in write_skill(rendered, context.dest, context.runtime, context.adapter,
                                    context.commit, skipped, statuses):
                print(f"  wrote {path}")
            for name in skipped:
                report.notes.append(
                    f"{rendered.name}: {name} is neither a rendered file, a copied "
                    f"directory ({', '.join(COPY_DIRS)}), nor excluded by name; not installed"
                )
        for target in rendered.dangling_links:
            report.notes.append(
                f"{rendered.name}: body links {target}, a repository file not "
                f"declared on the Dependencies line; it is not bundled, so the "
                f"installed copy cannot read it"
            )
        report.installed.append(rendered.name)

    if report.identity_change is not None:
        path, before, after = report.identity_change
        print(f"\n--- {display_path(str(path))} ---")
        print_diff(path, before, after)

    return finish(context, report, args)


def finish(context: Context, report: Report, args: argparse.Namespace) -> int:
    print()
    if report.installed:
        verb = "would install" if args.dry_run else "installed"
        print(f"{verb}: {', '.join(report.installed)}")
    for note in report.notes[report.printed_notes:]:
        print(f"note: {note}")
    for refusal in report.refused:
        print(f"refused: {refusal}")

    if report.identity_change is not None:
        identity_file = report.identity_change[0]
        target = identity_file.parent
        print(
            f"\nRun this yourself if {display_path(str(target))} is a git repository "
            "(the installer never commits):"
        )
        # Path-scoped on purpose: `-am` would sweep in whatever else the owner
        # has modified in that repository.
        print(
            f'  git -C {display_path(str(target))} commit '
            f'-m "registry: {OS_NAME} adapter" -- {identity_file.name}'
        )
    if context.runtime == "openclaw":
        staging = expand(str(context.adapter["adapter_file"])).parent
        print("\nCopy the staging tree onto the runtime volume, then reload it:")
        print(f"  railway ssh -- 'mkdir -p /data/.openclaw/workspace'")
        print(f"  # then copy {staging}/ to /data/.openclaw/workspace/")
    return 1 if report.refused else 0


def classify(
    planned: dict[str, Any], recorded: dict[str, str], actual: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Split this render's files into the ones to write and the ones that are yours.

    Three readings of every path -- what the stamp recorded, what is installed
    now, and what this repository would render -- and only one combination is
    safe to write: the install still holds what we put there, and the repository
    has moved since. Anything else is the owner's, and is named rather than
    replaced.
    """
    write: list[str] = []
    blocked: dict[str, str] = {}
    for rel, item in planned.items():
        want = sha256_bytes(item.data)
        have = actual.get(rel)
        was = recorded.get(rel)
        if have is None and was is None:
            write.append(rel)  # new in this render, never installed
        elif have is None:
            blocked[rel] = "recorded by the stamp and missing from the install"
        elif was is None:
            blocked[rel] = "in the install and recorded by no stamp"
        elif have != was:
            blocked[rel] = "edited in the install since it was written"
        elif want != have:
            write.append(rel)  # the repository moved and the install did not
    return write, blocked


def linked_component(directory: Path, rel: str) -> Path | None:
    """The first link on the way from the install root down to `rel`, or None.

    Checking the file itself is not enough: a link is a link wherever it sits in
    the path, and `references -> ~/vault/notes` puts every file under it outside
    the install while each of their own names looks ordinary. The whole descent
    is walked, and a link anywhere in it disqualifies the path -- including one
    that happens to point back inside, because an install is a tree this
    installer wrote and a path travelling through something it did not is not
    part of it.
    """
    probe = directory / rel
    while probe != directory:
        if probe.is_symlink():
            return probe
        probe = probe.parent
    return None


def write_blocker(directory: Path, rel: str, recorded: dict[str, str]) -> str | None:
    """Why this render's file is not the update's to write here, or None.

    Two ways it is not ours. A link anywhere in the path leads out of the tree
    this installer wrote. And the classifier reads the install through
    `installed_digests`, which keys it by exact byte-name where a filesystem does
    not: APFS resolves `Probe.md` and `probe.md` to one entry, and normalization
    variants collide the same way, so a file the owner wrote can be invisible to
    the comparison and still be the thing a write would truncate. The destination
    itself is asked instead.
    """
    linked = linked_component(directory, rel)
    if linked is not None:
        return (
            f"reached through the symlink {linked.relative_to(directory).as_posix()}; "
            "never written through, whatever it points at"
        )
    path = directory / rel
    if recorded.get(rel) is None and (path.exists() or path.is_symlink()):
        return (
            "already in the install under a name this filesystem treats as the "
            "same one, and recorded by no stamp"
        )
    return None


def discarded(path: Path) -> str:
    """What an overwrite costs the owner, in the only unit the run still knows."""
    try:
        return f"{len(path.read_bytes().splitlines())} installed lines discarded"
    except OSError:
        return "nothing was installed at that path"


def print_file_diff(rel: str, installed: bytes, rendered: bytes) -> None:
    """Your copy against what the update would have written in its place."""
    if b"\0" in installed or b"\0" in rendered:
        print(
            f"    (binary: {len(installed)} bytes installed, {len(rendered)} rendered)"
        )
        return
    lines = list(
        difflib.unified_diff(
            installed.decode("utf-8", "replace").splitlines(keepends=True),
            rendered.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile=f"a/{rel} (installed)",
            tofile=f"b/{rel} (this repository)",
        )
    )
    for line in lines[:DIFF_PREVIEW_LINES]:
        print(f"    {line.rstrip(chr(10))}")
    if len(lines) > DIFF_PREVIEW_LINES:
        print(f"    ... {len(lines) - DIFF_PREVIEW_LINES} more diff lines")


def print_changelog(name: str, commit: str, runtime: str) -> None:
    """What landed in this skill between the stamp's commit and HEAD."""
    paths = [f"skills/{name}", f"adapters/{runtime}"]
    entries, problem = io.changes_since(commit, paths)
    where = ", ".join(paths)
    if problem:
        print(f"  {problem}")
        return
    if not entries:
        print(f"  no commit since {commit[:COMMIT_DISPLAY_CHARS]} touches {where}")
        return
    print(f"  changes since {commit[:COMMIT_DISPLAY_CHARS]} in {where}:")
    for line in entries[:CHANGELOG_MAX]:
        print(f"    {line}")
    if len(entries) > CHANGELOG_MAX:
        print(f"    ... {len(entries) - CHANGELOG_MAX} more commits")


def report_skill(
    context: Context,
    name: str,
    directory: Path,
    notes: Sequence[str],
    blocked: dict[str, str],
    planned: dict[str, Any],
) -> list[str]:
    """This skill's notes, its per-file refusals with their diffs, and the offer.

    The offer is the point: a run that leaves a file alone prints the one command
    that would take this tree's render instead, so skipping and overwriting are
    both choices the owner makes, and neither is one the tool makes quietly.
    """
    for note in notes:
        print(f"  note: {note}")
    refusals: list[str] = []
    for rel, reason in blocked.items():
        refusal = f"{name}: {rel} {reason}; not overwritten"
        refusals.append(refusal)
        print(f"  refused: {refusal}")
        path = directory / rel
        linked = linked_component(directory, rel)
        if linked is not None:
            # Refused because a link stands in the path, so it is not read
            # through either -- the diff would print a file outside the install.
            print(
                f"    ({linked.relative_to(directory).as_posix()} -> "
                f"{os.readlink(linked)}; neither read nor written)"
            )
        elif not path.exists():
            # A file the owner removed: the diff would be the whole render as
            # additions, which says less than one line about what is missing.
            lines = len(planned[rel].data.splitlines())
            print(f"    (deleted from the install; {lines} lines would be restored)")
        else:
            print_file_diff(rel, path.read_bytes(), planned[rel].data)
    if blocked:
        print(
            f"  {len(blocked)} file(s) skipped -- what is installed is yours. To take "
            "this repository's render instead, discarding the above:"
        )
        print(
            f"    python3 tools/install_skill.py --runtime {context.runtime} "
            f"--update --overwrite {name}"
        )
    return refusals


def update_one(
    context: Context,
    directory: Path,
    statuses: dict[str, str],
    args: argparse.Namespace,
    report: Report,
) -> None:
    """Bring one stamped install up to this tree, file by file."""
    name = directory.name
    stamp = read_stamp(directory) or {}
    print(f"\n--- {name} ---")
    notes: list[str] = []
    refusals: list[str] = []

    def finish_skill() -> None:
        for note in notes:
            print(f"  note: {note}")
        for refusal in refusals:
            print(f"  refused: {refusal}")
        report.refused.extend(refusals)

    recorded = recorded_digests(stamp)
    if recorded is None:
        refusals.append(
            f"{name}: {PRE_DIGEST_NOTE}. Until it is, an edit of yours reads exactly "
            "like a stale render, so nothing here was rewritten -- and that re-install "
            "replaces the whole directory, so copy anything of yours out of it first"
        )
        finish_skill()
        return
    installed_by = str(stamp.get("adapter") or "")
    if installed_by and installed_by != context.runtime:
        refusals.append(
            f"{name}: {directory} was installed by the {installed_by} adapter, not "
            f"{context.runtime}; --update brings an install up to date, it never "
            "converts one between runtimes"
        )
        finish_skill()
        return
    if stamp.get("adapter_version") != context.adapter.get("version"):
        # The trailer in every re-rendered body will name the new version; the
        # ADAPTER.md it points at is delivered by an install, not by this.
        notes.append(
            f"{name}: stamp adapter_version {stamp.get('adapter_version')} but "
            f"adapters/{context.runtime}/adapter.yaml is "
            f"v{context.adapter.get('version')}; --update re-renders skills only, so "
            "re-run the install to refresh the rendered ADAPTER.md they read"
        )
    try:
        meta, body, _ = read_skill(name)
    except InstallError as exc:
        refusals.append(str(exc))
        finish_skill()
        return
    if context.runtime not in declared(meta, "runtime"):
        refusals.append(
            f"{name}: metadata.{OS_NAME}.runtime is {declared(meta, 'runtime')}, "
            f"which excludes {context.runtime}"
        )
        finish_skill()
        return
    unconfirmed = unconfirmed_refusals(
        name, meta, body, context.adapter, context.datastore, context.vocabulary
    )
    if unconfirmed:
        refusals.extend(unconfirmed)
        finish_skill()
        return
    notes.extend(
        f"degraded: {note}"
        for note in degraded_notes(
            name, meta, body, context.adapter, context.datastore, context.vocabulary
        )
    )
    try:
        rendered = render_skill(
            name,
            context.runtime,
            context.adapter,
            context.capabilities,
            context.commit,
            context.vocabulary,
            context.datastore,
        )
    except InstallError as exc:
        refusals.append(str(exc))
        finish_skill()
        return

    skipped: list[str] = []
    planned = planned_files(rendered, statuses, skipped)
    notes.extend(
        f"{name}: {entry} is neither a rendered file, a copied directory "
        f"({', '.join(COPY_DIRS)}), nor excluded by name; not installed"
        for entry in skipped
    )
    unreadable: dict[str, str] = {}
    actual = installed_digests(directory, unreadable)
    write, blocked = classify(planned, recorded, actual)
    for rel, problem in sorted(unreadable.items()):
        # Unread is not absent: the classifier saw no digest for this file, and
        # what it holds is unknown rather than gone.
        if rel in write:
            write.remove(rel)
        if rel in planned:
            blocked[rel] = f"{UNREADABLE} ({problem}); left alone"
        else:
            notes.append(f"{name}: {rel} {UNREADABLE} ({problem}); left alone")
    for rel in sorted(set(recorded) - set(planned)):
        notes.append(
            f"{name}: {rel} is recorded by the stamp and no longer part of this "
            "skill; left in place, never deleted"
        )
    for rel in sorted(set(actual) - set(planned) - set(recorded) - set(unreadable)):
        notes.append(
            f"{name}: {rel} is not recorded by the stamp; left in place, never "
            "deleted -- --check reads it as drift"
        )
    promoted: dict[str, str] = {}
    if args.overwrite:
        # The explicit choice, taken: the files the run would otherwise have
        # left alone join the write list, and the stamp records what lands.
        promoted = blocked
        write = [rel for rel in planned if rel in set(write) | set(blocked)]
        blocked = {}
    # Last, and independent of the flags: what is not ours to write is not ours
    # on request either. This runs after the promotion so that no file is
    # reported replaced and refused in the same run.
    for rel in list(write):
        reason = write_blocker(directory, rel, recorded)
        if reason is not None:
            write.remove(rel)
            blocked[rel] = reason
    notes.extend(
        f"{name}: {rel} {reason}; --overwrite "
        f"{'would replace' if args.dry_run else 'replaced'} it "
        f"({discarded(directory / rel)})"
        for rel, reason in promoted.items()
        if rel in write
    )
    refusals.extend(report_skill(context, name, directory, notes, blocked, planned))
    report.refused.extend(refusals)

    if write or blocked:
        print_changelog(name, str(stamp.get("commit") or ""), context.runtime)
    if not write:
        if not blocked:
            print("  no change: every recorded file matches this tree")
        return
    if args.dry_run:
        for rel in write:
            print(f"  would write {directory / rel}")
        report.installed.append(name)
        return
    failed: dict[str, str] = {}
    for path in write_planned(directory, planned, only=write, failed=failed):
        print(f"  wrote {path}")
    for rel, problem in failed.items():
        refusal = f"{name}: {rel} {UNWRITABLE} ({problem}); left alone"
        refusals.append(refusal)
        report.refused.append(refusal)
        print(f"  refused: {refusal}")
    landed = [rel for rel in write if rel not in failed]
    if landed:
        update_stamp(context, directory, stamp, rendered, planned, recorded, landed)
        report.installed.append(name)


def update_stamp(
    context: Context,
    directory: Path,
    stamp: dict[str, Any],
    rendered: Rendered,
    planned: dict[str, Any],
    recorded: dict[str, str],
    write: Sequence[str],
) -> None:
    """Record what this run actually wrote, and nothing it did not.

    A refused file keeps the digest the install gave it, so the next `--check`
    reports the edit again rather than blessing it. The stamp's `commit` follows
    SKILL.md alone, because the commit is written into that file's trailer: a
    run that could not replace the body has not moved the install to HEAD.
    """
    digests = dict(recorded)
    digests.update({rel: sha256_bytes(planned[rel].data) for rel in write})
    stamp["files"] = digests
    stamp["installed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "SKILL.md" in write:
        stamp.update(
            {
                "name": rendered.name,
                "version": rendered.version,
                "commit": context.commit,
                "adapter": context.runtime,
                "adapter_version": context.adapter.get("version"),
                "sha256": sha256_text(rendered.text),
                "capabilities": list(rendered.capabilities),
                "hints": rendered.hints,
            }
        )
    write_stamp(directory, stamp)


def do_update(context: Context, names: Sequence[str], args: argparse.Namespace) -> int:
    """Bring every stamped install up to this tree, refusing per file, never per run."""
    report = Report()
    installs = stamped_installs(context.dest)
    if names:
        wanted = set(names)
        present = {path.name for path in installs}
        installs = [path for path in installs if path.name in wanted]
        for name in sorted(wanted - present):
            report.refused.append(
                f"{name}: {context.dest / name} carries no {STAMP_NAME}; --update reads "
                "what this installer wrote, so install it before updating it"
            )
    print(f"{context.runtime}: updating {len(installs)} stamped install(s) in {context.dest}")
    # The notes lead, as they do on an install: what is wrong with the adapter
    # every one of these skills reads is read before the per-skill blocks.
    for note in adapter_notes(
        context.runtime,
        context.adapter,
        local_overrides_path(context.adapter, args.local_overrides),
    ):
        print(f"note: {note}")

    statuses = install_statuses(context, [path.name for path in installs])
    for directory in installs:
        try:
            update_one(context, directory, statuses, args, report)
        except OSError as exc:
            # Whatever one install's filesystem does, the next one is still due
            # an update: the row is "nonzero, and on to the next skill".
            refusal = f"{directory.name}: {exc}; this skill was left as it is"
            print(f"  refused: {refusal}")
            report.refused.append(refusal)

    print()
    if report.installed:
        verb = "would update" if args.dry_run else "updated"
        print(f"{verb}: {', '.join(report.installed)}")
    for refusal in report.refused:
        print(f"refused: {refusal}")
    return 1 if report.refused else 0


def do_check(context: Context, names: Sequence[str], args: argparse.Namespace) -> int:
    report = Report()
    installs = stamped_installs(context.dest)
    if names:
        installs = [path for path in installs if path.name in set(names)]
    print(f"{context.runtime}: checking {len(installs)} stamped install(s) in {context.dest}")
    report.notes.extend(
        adapter_notes(
            context.runtime,
            context.adapter,
            local_overrides_path(context.adapter, args.local_overrides),
        )
    )

    for directory in installs:
        try:
            check_one(context, directory, report)
        except OSError as exc:
            report.drift.append(f"{directory.name}: {exc}; not checked")

    for note in report.notes:
        print(f"note: {note}")
    for drift in report.drift:
        print(f"drift: {drift}")
    if not report.drift:
        print("no drift.")
    return 1 if report.drift else 0


def check_one(context: Context, directory: Path, report: Report) -> None:
    """One stamped install, declared against actual."""
    name = directory.name
    stamp = read_stamp(directory) or {}
    actual = (directory / "SKILL.md").read_text(encoding="utf-8")
    if sha256_text(actual) != stamp.get("sha256"):
        report.drift.append(f"{name}: SKILL.md sha256 differs from the stamp; edited in place")
    recorded = recorded_digests(stamp)
    if recorded is None:
        report.notes.append(f"{name}: {PRE_DIGEST_NOTE}")
    else:
        report.drift.extend(file_drift(name, directory, recorded))
    if stamp.get("adapter_version") != context.adapter.get("version"):
        report.drift.append(
            f"{name}: stamp adapter_version {stamp.get('adapter_version')} but "
            f"adapters/{context.runtime}/adapter.yaml is v{context.adapter.get('version')}"
        )
    try:
        meta, body, _ = read_skill(name)
    except InstallError as exc:
        report.drift.append(f"{name}: {exc}")
        return

    capabilities = declared(meta, "capabilities")
    if capabilities != list(stamp.get("capabilities") or []):
        report.drift.append(
            f"{name}: stamp capabilities {stamp.get('capabilities')} but the "
            f"repository declares {capabilities}"
        )
    hints = validate_repo.derived_hints(tuple(capabilities), context.capabilities)
    if hints != (stamp.get("hints") or {}):
        report.drift.append(f"{name}: derived hints {hints} differ from the stamp's")

    for message in unconfirmed_refusals(
        name, meta, body, context.adapter, context.datastore, context.vocabulary
    ):
        report.drift.append(message)
    report.notes.extend(
        f"degraded: {note}"
        for note in degraded_notes(
            name, meta, body, context.adapter, context.datastore, context.vocabulary
        )
    )

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
        return
    if sha256_text(rendered.text) != stamp.get("sha256"):
        report.drift.append(
            f"{name}: a fresh render at the stamped commit has a different sha256; "
            "the source or the adapter changed since the install"
        )
    report.drift.extend(undefined_terms(name, actual, context))


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
            f"{stamp.get('installed_at')}  capabilities={stamp.get('capabilities')}"
        )
    return 0


def usage_doc() -> str:
    """The entry module's own docstring -- what `--help` prints.

    `tools/install_skill.py` carries the written explanation of the tool: the
    three refusals, the stamp, and why DEGRADED is not one of them. A
    hand-written `description=` here was a second, shorter account of the same
    thing that no reader of either could tell was incomplete.
    """
    module = sys.modules.get("tools.install_skill") or sys.modules.get("install_skill")
    if module is None:  # imported without the entry module ever being loaded
        module = importlib.import_module("tools.install_skill")
    return (module.__doc__ or "").strip()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install_skill.py",
        description=usage_doc(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--runtime", required=True, choices=list(RUNTIMES))
    parser.add_argument("--dest", help="override the runtime's default destination")
    parser.add_argument("--all", action="store_true", help="every skill the runtime carries")
    parser.add_argument("--check", action="store_true", help="declared-vs-actual; exit 1 on drift")
    parser.add_argument(
        "--update",
        action="store_true",
        help="re-render what this tree changed in every stamped install (or NAME...)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="with --update: take this tree's render over a file edited in the install",
    )
    parser.add_argument("--uninstall", action="store_true", help="remove stamped installs")
    parser.add_argument("--list", action="store_true", dest="list_", help="read the stamps")
    parser.add_argument("--dry-run", action="store_true", help="print, write nothing")
    parser.add_argument("--local-overrides", help="override the adapter's local_overrides_file")
    parser.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="install even though the render leaves a ${NAME} literal",
    )
    parser.add_argument("names", nargs="*", metavar="NAME")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    actions = [args.check, args.uninstall, args.list_, args.update]
    if sum(bool(action) for action in actions) > 1:
        print("usage: --check, --update, --uninstall and --list are mutually exclusive")
        return 2
    if args.overwrite and not args.update:
        print("usage: --overwrite is read only with --update")
        return 2
    installing = not any(actions)
    if installing and not args.names and not args.all:
        print("usage: name at least one skill, or pass --all")
        return 2

    try:
        if installing or args.check or args.update:
            code = io.run_validator()
            if code != 0:
                print(f"refused: tools/validate_repo.py exited {code}; the library is not valid")
                return 1
        context = build_context(args)
        names = list(args.names)
        if installing and args.all:
            names = runtime_skills(args.runtime)
        if args.check:
            return do_check(context, names, args)
        if args.update:
            return do_update(context, names, args)
        if args.uninstall:
            return do_uninstall(context, names, args)
        if args.list_:
            return do_list(context, names)
        return do_install(context, names, args)
    except InstallError as exc:
        print(f"refused: {exc}")
        return 1
