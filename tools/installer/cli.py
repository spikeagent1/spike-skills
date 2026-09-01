#!/usr/bin/env python3
"""The four actions and the argument parser: install, check, uninstall, list."""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
from dataclasses import dataclass
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
    read_skill, render_skill, repo_root, sha256_text, unconfirmed_refusals,
    unconfirmed_term
)
from .io import (
    check_adapter_template, default_dest, install_adapter, local_overrides_path,
    print_diff, read_stamp, stamp_path, stamped_installs, write_skill
)
from . import io

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
            continue
        if sha256_text(rendered.text) != stamp.get("sha256"):
            report.drift.append(
                f"{name}: a fresh render at the stamped commit has a different sha256; "
                "the source or the adapter changed since the install"
            )
        report.drift.extend(undefined_terms(name, actual, context))

    for note in report.notes:
        print(f"note: {note}")
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
            code = io.run_validator()
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
