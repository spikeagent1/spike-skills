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

A DEGRADED binding is the other half of that rule and not a refusal. UNCONFIRMED
is ignorance -- nobody knows whether the binding works, so a skill depending on
it cannot be installed honestly. DEGRADED is knowledge: the binding is absent or
partial, and the skill's own contract already says what it does in that state.
`contracts/sync.md`'s `tasks/` row is the authority -- "Where no provider
connector is authorized, `system_of_record` flips to `datastore` and the skill
discloses that the object is mirror-only" -- so such a skill installs, and the
run prints a `degraded:` note naming the term. `--check` reports it the same
way: a note, never drift.

`--update` is the same rules applied to an install that already exists. The
stamp records a digest per installed file, so the three readings of every path
-- what the stamp recorded, what is installed now, what this tree renders --
answer the only question that matters: a file the install still holds as we
wrote it, and the repository has since changed, is re-rendered; a file the owner
edited, deleted, or dropped in themselves is refused by name, with the diff of
what would have replaced it and the `--overwrite` line that would take it. A
refusal exits nonzero and the run continues to the next skill. Nothing is ever
deleted, and a stamp written before per-file digests is refused rather than
guessed at -- there, an edit and a stale render are the same bytes.

One more nonzero exit is not a refusal to install but a refusal to call the
host configured: a run whose rendered ADAPTER.md still carries a `${NAME}`
literal has left the file every installed skill resolves its terms against
half-written. The skills are installed, the note names the local file and the
keys, and the exit code says the setup is unfinished. `--allow-unconfigured` is
the explicit opt-out; `tools/bootstrap.py` passes it because it asks for those
values itself and fails on its own before it ever calls this.

Usage:
  python3 tools/install_skill.py --runtime {claude-code,openclaw} [options] [NAME...]
    --all                 every skill the runtime carries
    --check               declared-vs-actual over every stamped install; exit 1 on drift
    --update              re-render what this tree changed, per file, in every
                          stamped install (or NAME...); refuses a file you edited
    --overwrite           with --update: take this tree's render over that file
    --uninstall           remove stamped installs (NAME... or --all)
    --list                read the stamps
    --dry-run             print what an install would write, and write nothing
    --dest DIR            override the runtime's default destination
    --local-overrides P   override the adapter's local_overrides_file
    --allow-unconfigured  install although the render leaves a ${NAME} literal
"""

from __future__ import annotations

import os  # noqa: F401 - patched by callers that stub a filesystem failure
import subprocess  # noqa: F401 - patched by callers that assert nothing is run
import sys
import types
from pathlib import Path
from typing import Any

# Runnable as `python3 tools/install_skill.py` and importable as
# `tools.install_skill`; the three parts are a package either way.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The floor, before the first import of ours: an interpreter below it reads the
# version it needs rather than whatever construct happens to fail first.
from tools.python_floor import require_python  # noqa: E402

_TOO_OLD = require_python()
if _TOO_OLD:
    raise SystemExit(_TOO_OLD)

from tools.installer import cli, io, render  # noqa: E402,F401

# Re-exports: the whole installer surface, so importers name one module.
# ruff: noqa: F401
from tools.installer.render import (
    ALL_CAPS_RE, APPROVAL_LADDER, BUNDLE_DIR, Bundle, COMBINED_DESCRIPTION_MAX, COMMAND_RE,
    COMMIT_DISPLAY_CHARS, CONNECTOR_CONTEXT_RE, COPY_DIRS, DEPENDENCIES_RE, EXCLUDED_NAMES,
    InstallError, LINK_RE, NOTIFICATION_TERM, NOTIFY_EFFECT, NOT_A_BINARY_CLAUSE_RE,
    NOT_A_BINARY_RE, OS_NAME, PLACEHOLDER_RE, PROVIDER_EFFECTS, RUNTIMES, Rendered, Report,
    SENTENCE_RE, STAMP_NAME, STRICTEST_APPROVAL, TERM_SHAPED_RE, TRAILER_HEADING,
    TRIGGER_RE, adapter_for,
    channel_terms, declared, declared_approvals, declared_repo_inputs, dependencies_line,
    display_path, expand,
    fallback_warnings, home, library_tokens, load_contract, namespace_entries,
    openclaw_requires, os_block, path_globs, quoted, read_skill, render_frontmatter,
    render_skill, render_trailer, repo_root, required_terms, rewrite_links, sha256_bytes,
    sha256_text,
    skill_source, trigger_clause, unconfirmed_bindings, unconfirmed_refusals,
    undeclared_repo_links, yaml_flow, yaml_scalar
)
from tools.installer.io import (
    repo_commit, run_validator,
    CHANGELOG_UNKNOWN, Planned, adapter_template, apply_identity_import,
    bind_identity_file, changes_since,
    check_adapter_template, default_dest, file_digests, git_ignored, install_adapter,
    inside_git_work_tree, installed_digests, local_overrides_path,
    local_overrides_template, locate_block, marker_block, marker_lines, placeholder_names,
    planned_files, print_diff,
    read_local_overrides, read_stamp, stamp_path, stamped_installs, substitute,
    write_planned, write_skill, write_stamp, write_text_atomically
)
from tools.installer.cli import (
    CHANGELOG_MAX, Context, DIFF_PREVIEW_LINES, PRE_DIGEST_NOTE, build_context, classify,
    do_check, do_install, do_list, do_uninstall, do_update, file_drift, finish, main,
    parse_args, print_changelog, print_file_diff, recorded_digests, runtime_skills,
    undefined_terms, update_one, update_stamp
)


# The two host probes a caller stubs out (`mock.patch.object(install_skill,
# "run_validator", ...)`). The actions call them through `installer.io`, so the
# assignment has to land there rather than on a shadow attribute of this module.
_PROXIED = frozenset({"repo_commit", "run_validator"})


class _EntryModule(types.ModuleType):
    """This module, with the host probes forwarded to `installer.io`.

    The names stay in this module's own namespace as well, so a caller that
    stubs one (and later restores it) sees an ordinary module attribute.
    """

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PROXIED:
            setattr(io, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _EntryModule


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
