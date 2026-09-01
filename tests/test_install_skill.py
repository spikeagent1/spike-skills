from __future__ import annotations

import contextlib
import importlib
import subprocess
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.install_skill as install_skill
import tools.validate_repo as validate_repo


class InstallSkillTest(unittest.TestCase):
    """`tools/install_skill.py` against a self-contained fixture repo.

    The fixture carries its own contracts, vocabulary and two adapters so the
    render matrix (hints, UNCONFIRMED terms, background skills) is pinned to
    values this file controls rather than to whatever the real library holds.
    `HOME` is redirected into the temporary tree, so every `${HOME}` the
    adapters name resolves inside it and no real dotfile is touched.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(parents=True)
        validate_repo.ROOT = self.root
        validate_repo.SKILLS = self.root / "skills"
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        # The installer refuses on a failing validator; the fixture repo is not
        # a valid library, so the gate itself is exercised in its own test.
        self._validator = mock.patch.object(install_skill, "run_validator", return_value=0)
        self.validator = self._validator.start()
        self._commit = mock.patch.object(
            install_skill, "repo_commit", return_value="0123456789abcdef"
        )
        self._commit.start()
        self._write_base_repo()

    def tearDown(self) -> None:
        self._commit.stop()
        self._validator.stop()
        self._env.stop()
        importlib.reload(validate_repo)
        importlib.reload(install_skill)
        self.tmp.cleanup()

    # -- fixture -------------------------------------------------------

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _skill_md(
        self,
        name: str,
        *,
        description: str = "Use when the fixture needs a body. Not for anything else.",
        capabilities: tuple[str, ...] = (),
        reads_from: tuple[str, ...] = (),
        writes_to: tuple[str, ...] = (),
        runtime: tuple[str, ...] = ("openclaw", "claude-code"),
        dependencies: str = "**Dependencies:** none beyond the contract.",
        body_extra: str = "",
    ) -> str:
        return (
            "---\n"
            f"name: {name}\n"
            f'description: "{description}"\n'
            "metadata:\n"
            "  spike-os:\n"
            "    version: 2.0.0\n"
            f"    runtime: [{', '.join(runtime)}]\n"
            f"    reads_from: [{', '.join(reads_from)}]\n"
            f"    writes_to: [{', '.join(writes_to)}]\n"
            f"    capabilities: [{', '.join(capabilities)}]\n"
            "---\n"
            "\n"
            f"# {name}\n"
            "\n"
            "## Inputs\n"
            "\n"
            f"{dependencies}\n"
            "\n"
            "## Workflow\n"
            "\n"
            f"1. Do the fixture thing.{body_extra}\n"
        )

    def _write_base_repo(self) -> None:
        self._write(
            "contracts/capabilities.yaml",
            "version: 1\n"
            "effects:\n"
            "  - name: datastore:read\n"
            "    readOnlyHint: true\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n"
            "    approval: never_require\n"
            "  - name: datastore:write\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n"
            "    approval: turn_scoped\n"
            "  - name: provider:read\n"
            "    readOnlyHint: true\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n"
            "    approval: never_require\n"
            "  - name: delete:external\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: true\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n"
            "    approval: preview_then_explicit\n"
            "  - name: notify:owner\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n"
            "    approval: never_require\n"
            "  - name: repo:merge\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: true\n"
            "    idempotentHint: false\n"
            "    openWorldHint: true\n"
            "    approval: never_autonomous\n",
        )
        self._write(
            "contracts/datastore.yaml",
            "version: 1\n"
            "namespaces:\n"
            "  - name: profile\n"
            "    status: active\n"
            "    system_of_record: datastore\n"
            "  - name: notes\n"
            "    status: active\n"
            "    system_of_record: datastore\n"
            "  - name: tasks\n"
            "    status: active\n"
            "    system_of_record: provider\n"
            "    sync:\n"
            "      kind: task\n"
            "      provider_role: task provider\n",
        )
        self._write(
            "adapters/vocabulary.yaml",
            "version: 1\n"
            "terms:\n"
            "  - term: owner datastore\n"
            "    key: owner_datastore\n"
            "    kind: datastore\n"
            "  - term: task provider\n"
            "    key: task_provider\n"
            "    kind: provider\n"
            "  - term: notification channel\n"
            "    key: notification_channel\n"
            "    kind: channel\n"
            "  - term: owner channel\n"
            "    key: owner_channel\n"
            "    kind: channel\n"
            "  - term: agent inbox\n"
            "    key: agent_inbox\n"
            "    kind: channel\n",
        )
        self._write_adapters()
        self._write("catalog/index.md", self.INDEX)
        self._write_skills()

    # A generated-index shape: header, separator, one backticked name per row.
    INDEX = (
        "# Index\n"
        "\n"
        "## fixtures\n"
        "\n"
        "| skill | use when | version |\n"
        "| --- | --- | --- |\n"
        "| `fixture-notes` | Use when notes are read. | 2.0.0 |\n"
        "| `fixture-tasks` | Use when one task is the ask. | 2.0.0 |\n"
        "| `fixture-background` | Use when background applies. | 2.0.0 |\n"
        "\n"
        "## Not yet available\n"
        "\n"
        "| namespace | status | system of record | authority |\n"
        "| --- | --- | --- | --- |\n"
        "| `calendar` | reserved | provider | none yet |\n"
    )

    def _write_adapters(
        self, *, claude_code_version: int = 1, task_provider_marker: str = "UNCONFIRMED"
    ) -> None:
        self._write(
            "adapters/claude-code/adapter.yaml",
            "runtime: claude-code\n"
            f"version: {claude_code_version}\n"
            "vocabulary:\n"
            "  owner_datastore:\n"
            "    value: the fixture vault at ${VAULT_ROOT}\n"
            "  task_provider:\n"
            "    value: mirror-only\n"
            f"    note: {task_provider_marker} - no task connector on this host.\n"
            "  notification_channel:\n"
            "    value: an in-session reply, then the agent inbox\n"
            "  owner_channel:\n"
            "    value: the interactive session\n"
            "  agent_inbox:\n"
            "    value: ${AGENT_INBOX}\n"
            "    note: UNCONFIRMED - no mail server on this host.\n"
            "datastore:\n"
            "  paths:\n"
            "    profile: profile/\n"
            "    notes: notes/\n"
            "    tasks: ops/tasks/\n"
            "  verbs:\n"
            "    read: get_page\n"
            "notification:\n"
            "  channels:\n"
            "    - an in-session reply\n"
            "    - the agent inbox\n"
            "  quiet_hours:\n"
            "    start: ${QUIET_START}\n"
            "    end: ${QUIET_END}\n"
            "    timezone_term: owner_timezone\n"
            "scheduler: fixture scheduler\n"
            "identity_files:\n"
            "  - ${HOME}/.claude/CLAUDE.md\n"
            "skills_dir: ${HOME}/.claude/skills\n"
            "adapter_file: ${HOME}/.claude/spike-os/ADAPTER.md\n"
            "identity_import:\n"
            "  file: ${HOME}/.claude/CLAUDE.md\n"
            '  line: "@~/.claude/spike-os/ADAPTER.md"\n'
            "  begin_marker: <!-- spike-os:begin -->\n"
            "  end_marker: <!-- spike-os:end -->\n"
            "render:\n"
            "  when_to_use: true\n"
            "  disable_model_invocation_on_approval: [never_autonomous]\n"
            "  user_invocable_default: true\n"
            "  background_skills: [fixture-background]\n"
            "  metadata_extra:\n"
            "    paths: file globs from the Inputs Dependencies line\n"
            "local_overrides_file: ${HOME}/.config/spike-os/claude-code.local.yaml\n",
        )
        self._write(
            "adapters/claude-code/ADAPTER.md",
            "# ADAPTER — claude-code\n"
            "\n"
            "## Vocabulary\n"
            "| Term | Value |\n"
            "|---|---|\n"
            "| `owner datastore` | the fixture vault at ${VAULT_ROOT} |\n"
            f"| `task provider` | mirror-only — **{task_provider_marker}** |\n"
            "| `notification channel` | an in-session reply, then the agent inbox |\n"
            "| `owner channel` | the interactive session |\n"
            "| `agent inbox` | ${AGENT_INBOX} — **UNCONFIRMED** |\n"
            "\n"
            "## Channels and quiet hours\n"
            "Quiet hours are ${QUIET_START}–${QUIET_END}.\n",
        )
        self._write(
            "adapters/openclaw/adapter.yaml",
            "runtime: openclaw\n"
            "version: 1\n"
            "vocabulary:\n"
            "  owner_datastore:\n"
            "    value: the GBrain store\n"
            "  task_provider:\n"
            "    value: the Todoist connector\n"
            "  notification_channel:\n"
            "    value: the owner DM\n"
            "  owner_channel:\n"
            "    value: the main session\n"
            "  agent_inbox:\n"
            "    value: the agent mailbox\n"
            "datastore:\n"
            "  paths:\n"
            "    profile: profile/\n"
            "    notes: notes/\n"
            "    tasks: tasks/\n"
            "  verbs:\n"
            "    read: gbrain get\n"
            "notification:\n"
            "  channels:\n"
            "    - the owner DM\n"
            "  quiet_hours:\n"
            "    start: ${QUIET_START}\n"
            "    end: ${QUIET_END}\n"
            "    timezone_term: owner_timezone\n"
            "scheduler: openclaw cron\n"
            "identity_files:\n"
            "  - AGENTS.md\n"
            "skills_dir: /data/.openclaw/workspace/skills\n"
            "adapter_file: dist/openclaw/workspace/ADAPTER.md\n"
            "identity_import:\n"
            "  file: runtime/workspace/AGENTS.md in ${DEPLOY_REPO}\n"
            '  line: "See `ADAPTER.md` for what the runtime terms resolve to."\n'
            "  begin_marker: <!-- spike-os:begin -->\n"
            "  end_marker: <!-- spike-os:end -->\n"
            "render:\n"
            "  when_to_use: false\n"
            "  disable_model_invocation_on_approval: []\n"
            "  user_invocable_default: true\n"
            "  metadata_extra:\n"
            "    metadata.openclaw.requires.env: backticked ALL_CAPS tokens\n"
            "    metadata.openclaw.requires.bins: backticked command or absolute path tokens\n"
            "    metadata.openclaw.requires.config: backticked connector registry keys\n"
            "local_overrides_file: ${HOME}/.config/spike-os/openclaw.local.yaml\n",
        )
        self._write(
            "adapters/openclaw/ADAPTER.md",
            "# ADAPTER — openclaw\n"
            "\n"
            "## Vocabulary\n"
            "| Term | Value |\n"
            "|---|---|\n"
            "| `owner datastore` | the GBrain store |\n"
            "| `task provider` | the Todoist connector |\n"
            "| `notification channel` | the owner DM |\n"
            "| `owner channel` | the main session |\n"
            "| `agent inbox` | the agent mailbox |\n",
        )

    def _write_skills(self) -> None:
        self._write(
            "skills/fixture-launcher/SKILL.md",
            self._skill_md(
                "fixture-launcher",
                description=(
                    "Use when the request names no skill and two could each own it. "
                    "Not for one task (fixture-tasks)."
                ),
                dependencies=(
                    "**Dependencies:** none beyond the contract. This skill reads one "
                    "repository file, [catalog/index.md](../../catalog/index.md), and "
                    "declares no effect."
                ),
            ),
        )
        self._write("skills/fixture-launcher/examples/evals.json", "{}\n")
        self._write("skills/fixture-launcher/routing-eval.jsonl", "{}\n")
        self._write("skills/fixture-launcher/references/detail.md", "detail\n")
        self._write("skills/fixture-launcher/scripts/run.sh", "echo hi\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when notes are read from the vault. Not for tasks.",
                capabilities=("datastore:read",),
                reads_from=("profile",),
                body_extra=" Reads the `owner datastore`.",
            ),
        )
        self._write(
            "skills/fixture-tasks/SKILL.md",
            self._skill_md(
                "fixture-tasks",
                description="Use when one task is the ask. Not for a whole day.",
                capabilities=("datastore:read", "provider:read", "delete:external"),
                reads_from=("tasks", "profile"),
                writes_to=("tasks",),
                body_extra=" Writes through the `task provider`.",
            ),
        )
        self._write(
            "skills/fixture-background/SKILL.md",
            self._skill_md(
                "fixture-background",
                description="Use when background knowledge applies. Not for anything else.",
                capabilities=("datastore:read",),
                reads_from=("profile",),
            ),
        )
        self._write(
            "skills/fixture-openclaw-only/SKILL.md",
            self._skill_md(
                "fixture-openclaw-only",
                description="Use when only openclaw can run it. Not for claude-code.",
                runtime=("openclaw",),
                dependencies=(
                    "**Dependencies:** the `GH_TOKEN` environment variable, the `gh` and "
                    "`git` commands, `/data/.local/bin/gbrain`, and the `todoist` connector."
                ),
            ),
        )
        self._write(
            "skills/fixture-destructive/SKILL.md",
            self._skill_md(
                "fixture-destructive",
                description="Use when a local record is deleted. Not for provider objects.",
                capabilities=("datastore:read", "delete:external"),
                reads_from=("profile",),
            ),
        )
        self._write(
            "skills/fixture-merger/SKILL.md",
            self._skill_md(
                "fixture-merger",
                description="Use when a change is landed on the trunk. Not for drafts.",
                capabilities=("datastore:read", "repo:merge"),
                reads_from=("profile",),
            ),
        )
        self._write(
            "skills/fixture-notifier/SKILL.md",
            self._skill_md(
                "fixture-notifier",
                description="Use when the owner must be told. Not for silent runs.",
                capabilities=("notify:owner",),
                body_extra=" Delivers on the `notification channel`.",
            ),
        )

    # -- helpers -------------------------------------------------------

    def _run(self, *argv: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = install_skill.main(list(argv))
        return code, stream.getvalue()

    @property
    def dest(self) -> Path:
        return self.home / ".claude" / "skills"

    def _installed(self, name: str) -> str:
        return (self.dest / name / "SKILL.md").read_text(encoding="utf-8")

    def _stamp(self, name: str) -> dict:
        return json.loads((self.dest / name / ".spike-os.json").read_text(encoding="utf-8"))

    def _frontmatter(self, name: str) -> dict:
        return validate_repo.parse_frontmatter(self._installed(name)) or {}

    def _configure(self, runtime: str = "claude-code") -> Path:
        """Fill every placeholder this runtime's adapter names.

        An install whose render would leave a `${NAME}` literal exits nonzero,
        so a test about anything else configures the host once, here, rather
        than asserting an exit code that is about the local file.
        """
        path = self.home / ".config" / "spike-os" / f"{runtime}.local.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        names = install_skill.placeholder_names(runtime)
        path.write_text(
            "\n".join(f"{name}: 'fixture-{name.lower()}'" for name in names) + "\n",
            encoding="utf-8",
        )
        return path

    # -- bundled repository inputs -------------------------------------

    def test_an_undeclared_repo_link_is_reported_rather_than_left_dangling(self) -> None:
        self._configure()
        # Task 25 item 28: only the Dependencies line's files are bundled, so a
        # body link to any other repository file would not resolve once installed.
        self._write("catalog/approved.yaml", "skills: []\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                body_extra=" See [the catalog](../../catalog/approved.yaml).",
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0)
        self.assertIn("../../catalog/approved.yaml", out)
        self.assertIn("not declared on the Dependencies line", out)

    def test_the_contract_link_every_skill_carries_is_not_reported(self) -> None:
        self._configure()
        self._write("contracts/skill-contract.md", "# Contract\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                body_extra=(
                    " Follows [contracts/skill-contract.md]"
                    "(../../contracts/skill-contract.md)."
                ),
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0)
        self.assertNotIn("not declared on the Dependencies line", out)

    def test_a_declared_input_is_rewritten_and_not_reported(self) -> None:
        self._configure()
        self._write("catalog/index.md", "# Index\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                dependencies=(
                    "**Dependencies:** reads "
                    "[catalog/index.md](../../catalog/index.md)."
                ),
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0)
        self.assertNotIn("not declared on the Dependencies line", out)
        self.assertIn("(references/index.md)", self._installed("fixture-notes"))

    # -- copied directories --------------------------------------------

    def test_a_templates_directory_is_installed_rather_than_skipped(self) -> None:
        self._configure()
        # Task 25 item 31: `templates/` is loaded content a skill links, so it
        # travels with the install like references/ and scripts/.
        self._write("skills/fixture-notes/templates/entry.yaml", "name: example\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                body_extra=" Shape: `templates/entry.yaml`.",
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0)
        self.assertTrue((self.dest / "fixture-notes" / "templates" / "entry.yaml").is_file())
        self.assertNotIn("is neither a rendered file", out)

    # -- the validator gate --------------------------------------------

    def test_refuses_to_install_when_the_validator_fails(self) -> None:
        self.validator.return_value = 1
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("validate_repo", out)
        self.assertFalse((self.dest / "fixture-notes").exists())

    # -- stamp ---------------------------------------------------------

    def test_install_writes_a_stamp_with_the_declared_fields(self) -> None:
        self._configure()
        code, _ = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 0)
        stamp = self._stamp("fixture-notes")
        self.assertEqual(
            set(stamp),
            {
                "name",
                "version",
                "commit",
                "adapter",
                "adapter_version",
                "sha256",
                "installed_at",
                "capabilities",
                "hints",
                "files",
            },
        )
        self.assertEqual(stamp["name"], "fixture-notes")
        self.assertEqual(stamp["version"], "2.0.0")
        self.assertEqual(stamp["adapter"], "claude-code")
        self.assertEqual(stamp["adapter_version"], 1)
        self.assertEqual(stamp["commit"], "0123456789abcdef")
        self.assertEqual(stamp["capabilities"], ["datastore:read"])
        self.assertTrue(stamp["hints"]["readOnlyHint"])
        self.assertEqual(
            stamp["sha256"], install_skill.sha256_text(self._installed("fixture-notes"))
        )

    def test_the_stamp_records_a_digest_for_every_installed_file(self) -> None:
        """Skill granularity could not tell an edited reference from a stale one.

        The stamp hashed the rendered SKILL.md and nothing else, so a bundled
        input, a copied script, or the annotated index could be replaced in the
        install and every reader of the stamp would still call the directory
        clean.
        """
        self._configure()
        code, out = self._run("--runtime", "claude-code", "fixture-launcher")
        self.assertEqual(code, 0, out)

        directory = self.dest / "fixture-launcher"
        stamp = self._stamp("fixture-launcher")
        on_disk = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        } - {".spike-os.json"}
        self.assertEqual(set(stamp["files"]), on_disk)
        self.assertIn("references/detail.md", stamp["files"])
        self.assertIn("references/index.md", stamp["files"])
        self.assertIn("scripts/run.sh", stamp["files"])
        for rel, digest in stamp["files"].items():
            with self.subTest(rel=rel):
                self.assertEqual(
                    digest, install_skill.sha256_bytes((directory / rel).read_bytes())
                )
        # The skill-level hash stays what it was, and agrees with the file it names.
        self.assertEqual(stamp["files"]["SKILL.md"], stamp["sha256"])

    def test_the_digest_of_a_bundled_index_is_the_annotated_one(self) -> None:
        """The index is rewritten on the way in, so the stamp hashes what landed."""
        self._configure()
        self._run("--runtime", "claude-code", "fixture-launcher")
        stamp = self._stamp("fixture-launcher")
        source = (self.root / "catalog" / "index.md").read_bytes()
        self.assertNotEqual(stamp["files"]["references/index.md"],
                            install_skill.sha256_bytes(source))

    def test_a_copied_script_keeps_the_mode_it_had_in_the_repository(self) -> None:
        """`scripts/run.sh` is run, not read; the executable bit travels with it."""
        self._configure()
        source = self.root / "skills" / "fixture-launcher" / "scripts" / "run.sh"
        source.chmod(0o755)
        self._run("--runtime", "claude-code", "fixture-launcher")
        installed = self.dest / "fixture-launcher" / "scripts" / "run.sh"
        self.assertTrue(os.access(installed, os.X_OK), oct(installed.stat().st_mode))

    def test_install_refuses_a_destination_directory_without_a_stamp(self) -> None:
        foreign = self.dest / "fixture-notes"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: health\n---\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("not installed by spike-os", out)
        self.assertEqual(
            (foreign / "SKILL.md").read_text(encoding="utf-8"), "---\nname: health\n---\n"
        )

    def test_reinstalling_over_its_own_stamp_is_allowed_and_idempotent(self) -> None:
        self._configure()
        self._run("--runtime", "claude-code", "fixture-notes")
        first = self._installed("fixture-notes")
        code, _ = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 0)
        self.assertEqual(self._installed("fixture-notes"), first)

    def test_install_refuses_a_skill_whose_runtime_excludes_the_target(self) -> None:
        code, out = self._run("--runtime", "claude-code", "fixture-openclaw-only")
        self.assertEqual(code, 1)
        self.assertIn("runtime", out)
        self.assertFalse((self.dest / "fixture-openclaw-only").exists())

    # -- claude-code render --------------------------------------------

    def test_claude_code_render_adds_when_to_use_and_keeps_the_os_metadata(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        meta = self._frontmatter("fixture-notes")
        self.assertEqual(meta["when_to_use"], "Use when notes are read from the vault.")
        self.assertEqual(meta["metadata"]["spike-os"]["version"], "2.0.0")
        self.assertEqual(meta["metadata"]["spike-os"]["capabilities"], ["datastore:read"])
        self.assertNotIn("disable-model-invocation", meta)
        self.assertNotIn("user-invocable", meta)

    def test_when_to_use_is_refused_when_it_breaks_the_combined_cap(self) -> None:
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when " + ("x" * 900) + ". Not for anything else.",
                capabilities=("datastore:read",),
                reads_from=("profile",),
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("1536", out)

    def test_disable_model_invocation_follows_the_approval_tier(self) -> None:
        """Only an effect the owner must authorize in the moment leaves the ballot.

        The trigger used to be `destructiveHint`, which took every reversible
        mutation off the native router with it -- a skill the owner could reach
        only by naming it. `never_autonomous` is the tier that actually means
        "no standing authority", and it is the one that disables invocation.
        """
        self._configure()
        code, out = self._run(
            "--runtime",
            "claude-code",
            "fixture-merger",
            "fixture-destructive",
            "fixture-notes",
        )
        self.assertEqual(code, 0, out)
        self.assertIn("disable-model-invocation: true", self._installed("fixture-merger"))
        # delete:external is destructive but previewable, so it stays routable.
        self.assertIs(self._stamp("fixture-destructive")["hints"]["destructiveHint"], True)
        self.assertNotIn(
            "disable-model-invocation", self._frontmatter("fixture-destructive")
        )
        self.assertNotIn("disable-model-invocation", self._frontmatter("fixture-notes"))

    def test_an_effect_outside_the_enum_is_scored_at_the_strictest_tier(self) -> None:
        """An unknown effect is scored pessimistically, as `derived_hints` does."""
        self._configure()
        self._write(
            "skills/fixture-unknown/SKILL.md",
            self._skill_md(
                "fixture-unknown",
                description="Use when an unlisted effect is taken. Not for listed ones.",
                capabilities=("datastore:read", "invented:effect"),
                reads_from=("profile",),
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-unknown")
        self.assertEqual(code, 0, out)
        self.assertIn("disable-model-invocation: true", self._installed("fixture-unknown"))

    def test_user_invocable_false_for_a_background_skill(self) -> None:
        self._run("--runtime", "claude-code", "fixture-background")
        self.assertIn("user-invocable: false", self._installed("fixture-background"))

    def test_paths_carries_a_glob_and_never_a_bundled_input(self) -> None:
        """`paths` hides a skill until a matching file is open, so only a real
        glob may go in it; a named repository file is bundled instead."""
        self._write(
            "skills/fixture-scoped/SKILL.md",
            self._skill_md(
                "fixture-scoped",
                description="Use when a spreadsheet is edited. Not for prose.",
                dependencies="**Dependencies:** the workbook files matching `*.csv`.",
            ),
        )
        self._run("--runtime", "claude-code", "fixture-scoped", "fixture-launcher")
        self.assertEqual(self._frontmatter("fixture-scoped")["paths"], ["*.csv"])
        self.assertNotIn("paths", self._frontmatter("fixture-launcher"))

    def test_a_declared_repo_input_is_bundled_and_its_links_rewritten(self) -> None:
        self._run("--runtime", "claude-code", "fixture-launcher", "fixture-notes")
        bundled = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        source = (self.root / "catalog" / "index.md").read_text(encoding="utf-8")
        # The index is the one bundle the installer annotates rather than copies;
        # every row of the source still has to survive that.
        for line in source.splitlines():
            self.assertIn(line.rstrip("|").rstrip(), bundled)
        body = self._installed("fixture-launcher")
        self.assertIn("(references/index.md)", body)
        self.assertNotIn("../../catalog/index.md", body)
        self.assertNotIn("paths", self._frontmatter("fixture-notes"))

    def test_supporting_directories_are_copied_and_eval_material_is_excluded(self) -> None:
        self._run("--runtime", "claude-code", "fixture-launcher")
        installed = self.dest / "fixture-launcher"
        self.assertTrue((installed / "references" / "detail.md").is_file())
        self.assertTrue((installed / "scripts" / "run.sh").is_file())
        self.assertFalse((installed / "examples").exists())
        self.assertFalse((installed / "routing-eval.jsonl").exists())

    def test_the_runtime_binding_trailer_is_appended_exactly_once(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        body = self._installed("fixture-notes")
        self.assertEqual(body.count("## Runtime binding"), 1)
        self.assertIn("Bound to adapter `claude-code` v1", body)
        self.assertIn("`~/.claude/spike-os/ADAPTER.md`", body)
        self.assertIn("spike-skills@01234567", body)
        self.assertIn("skill version 2.0.0", body)

    # -- openclaw render -----------------------------------------------

    def test_openclaw_render_declares_requires_and_omits_when_to_use(self) -> None:
        self._configure("openclaw")
        code, _ = self._run("--runtime", "openclaw", "fixture-openclaw-only")
        self.assertEqual(code, 0)
        staged = (
            self.root
            / "dist"
            / "openclaw"
            / "workspace"
            / "skills"
            / "fixture-openclaw-only"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("when_to_use:", staged)
        self.assertIn("  openclaw:\n    requires:\n", staged)
        self.assertIn("      env: [GH_TOKEN]", staged)
        self.assertIn("gh", staged.split("bins: ")[1].split("\n")[0])
        self.assertIn("/data/.local/bin/gbrain", staged.split("bins: ")[1].split("\n")[0])
        self.assertIn("      config: [todoist]", staged)
        self.assertIn("Bound to adapter `openclaw` v1", staged)

    def test_openclaw_requires_drops_what_the_library_already_defines(self) -> None:
        body = (
            "## Inputs\n\n**Dependencies:** the `gh` command, the `requests` package, "
            "`voice-profile` records, and the `tasks` namespace.\n"
        )
        requires = install_skill.openclaw_requires(
            body,
            install_skill.load_contract("vocabulary"),
            install_skill.load_contract("datastore"),
        )
        self.assertEqual(requires["bins"], ["gh"])
        self.assertEqual(requires["config"], [])
        self.assertEqual(requires["env"], [])

    def test_openclaw_requires_drops_a_python_package_marked_optional(self) -> None:
        """T24: `jsonschema` in skill-library-ops's own Dependencies line is a
        Python distribution the sentence marks optional, not a binary; a wrong
        `requires.bins` entry stops the real skill loading on the OpenClaw box."""
        body = (
            "## Inputs\n\n**Dependencies:** a local `git` checkout of this repository; "
            "`python3` for the unit tests; `jsonschema` optionally, because the "
            "validator carries a stock-library fallback and the two paths must be "
            "exercised separately; and the `gh` CLI only to open or read the state "
            "of a pull request.\n"
        )
        requires = install_skill.openclaw_requires(
            body,
            install_skill.load_contract("vocabulary"),
            install_skill.load_contract("datastore"),
        )
        self.assertEqual(requires["bins"], ["git", "python3", "gh"])
        self.assertNotIn("jsonschema", requires["bins"])

    def test_openclaw_staging_writes_the_adapter_and_prints_the_copy_step(self) -> None:
        _, out = self._run("--runtime", "openclaw", "fixture-openclaw-only")
        self.assertTrue(
            (self.root / "dist" / "openclaw" / "workspace" / "ADAPTER.md").is_file()
        )
        self.assertIn("railway", out.lower())

    # -- adapter binding -----------------------------------------------

    def test_adapter_is_rendered_with_local_values_and_unfilled_keys_reported(self) -> None:
        overrides = self.home / ".config" / "spike-os" / "claude-code.local.yaml"
        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertTrue(overrides.is_file())
        text = overrides.read_text(encoding="utf-8")
        for key in ("VAULT_ROOT", "AGENT_INBOX", "QUIET_START", "QUIET_END"):
            self.assertIn(f"{key}:", text)
        self.assertIn("VAULT_ROOT", out)
        rendered = (self.home / ".claude" / "spike-os" / "ADAPTER.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("${VAULT_ROOT}", rendered)

        overrides.write_text(
            "VAULT_ROOT: /tmp/vault\nAGENT_INBOX: ''\nQUIET_START: '22:00'\nQUIET_END: '07:00'\n",
            encoding="utf-8",
        )
        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        rendered = (self.home / ".claude" / "spike-os" / "ADAPTER.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("/tmp/vault", rendered)
        self.assertNotIn("${VAULT_ROOT}", rendered)
        self.assertIn("${AGENT_INBOX}", rendered)
        self.assertIn("AGENT_INBOX", out)
        resolved = (self.home / ".claude" / "spike-os" / "adapter.resolved.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("/tmp/vault", resolved)

    def test_identity_import_line_is_inserted_once_and_touches_nothing_else(self) -> None:
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        original = "# Owner instructions\n\n- keep this line\n"
        claude_md.write_text(original, encoding="utf-8")

        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        after_first = claude_md.read_text(encoding="utf-8")
        self.assertTrue(after_first.startswith(original))
        self.assertIn("<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->", after_first)
        self.assertIn(
            'git -C ~/.claude commit -m "registry: spike-os adapter" -- CLAUDE.md', out
        )
        self.assertNotIn("-am", out)

        self._run("--runtime", "claude-code", "fixture-launcher")
        after_second = claude_md.read_text(encoding="utf-8")
        self.assertEqual(after_first, after_second)
        self.assertEqual(after_second.count("@~/.claude/spike-os/ADAPTER.md"), 1)

    def test_a_fully_refused_run_leaves_the_identity_file_alone(self) -> None:
        # Task 25 item 27: the adapter is delivered for the skills it serves; a
        # run that renders none of them has nothing to bind.
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        original = "# Owner instructions\n\n- keep this line\n"
        claude_md.write_text(original, encoding="utf-8")

        code, out = self._run("--runtime", "claude-code", "no-such-skill")

        self.assertEqual(code, 1)
        self.assertEqual(claude_md.read_text(encoding="utf-8"), original)
        self.assertIn("no skill rendered", out)

    def test_a_fully_refused_run_writes_no_adapter_files(self) -> None:
        code, _ = self._run("--runtime", "claude-code", "no-such-skill")
        self.assertEqual(code, 1)
        self.assertFalse((self.home / ".claude" / "spike-os" / "ADAPTER.md").exists())

    def test_one_successful_render_still_delivers_the_adapter(self) -> None:
        code, _ = self._run("--runtime", "claude-code", "fixture-notes", "no-such-skill")
        self.assertEqual(code, 1)
        self.assertTrue((self.home / ".claude" / "spike-os" / "ADAPTER.md").is_file())

    def test_identity_import_line_is_repaired_inside_existing_markers(self) -> None:
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            "# Owner\n\n<!-- spike-os:begin -->\n@~/.claude/spike-os/OLD.md\n"
            "<!-- spike-os:end -->\n\n- keep this line\n",
            encoding="utf-8",
        )
        self._run("--runtime", "claude-code", "fixture-notes")
        text = claude_md.read_text(encoding="utf-8")
        self.assertIn(
            "<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->",
            text,
        )
        self.assertNotIn("OLD.md", text)
        self.assertIn("- keep this line", text)
        self.assertIn("# Owner", text)

    def test_the_git_commit_command_is_printed_and_not_run(self) -> None:
        with mock.patch.object(install_skill.subprocess, "run") as run:
            _, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertIn(
            'git -C ~/.claude commit -m "registry: spike-os adapter" -- CLAUDE.md', out
        )
        for call in run.call_args_list:
            self.assertNotIn("commit", call.args[0])

    def test_the_notes_lead_the_install_output(self) -> None:
        """A note about the host is read before the render dump, not after it.

        The placeholder and degraded notes are what a first install has to act
        on; printed under a hundred lines of frontmatter they were the last
        thing a reader reached, and the first thing they missed.
        """
        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        lines = out.splitlines()
        notes = [index for index, line in enumerate(lines) if line.startswith("note: ")]
        destination = [
            index for index, line in enumerate(lines)
            if line.startswith("claude-code: destination")
        ]
        self.assertTrue(notes, out)
        self.assertTrue(destination, out)
        self.assertLess(notes[0], destination[0], out)
        placeholder = [index for index in notes if "placeholder" in lines[index]]
        self.assertTrue(placeholder, out)
        self.assertLess(placeholder[0], destination[0], out)

    def test_one_note_carries_the_overrides_path_and_every_unfilled_key(self) -> None:
        """The file to edit and the keys to edit in it were two notes apart."""
        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        notes = [line for line in out.splitlines() if line.startswith("note: ")]
        placeholder = [note for note in notes if "placeholder" in note]
        self.assertEqual(len(placeholder), 1, notes)
        self.assertIn("unfilled placeholders", placeholder[0])
        self.assertIn("claude-code.local.yaml", placeholder[0])
        for key in ("AGENT_INBOX", "QUIET_END", "QUIET_START", "VAULT_ROOT"):
            with self.subTest(key=key):
                self.assertIn(key, placeholder[0])

    def test_a_render_that_leaves_a_placeholder_literal_exits_nonzero(self) -> None:
        """An install nobody configured is not an install that worked.

        The leading note has always named the file and the keys; the exit code
        said 0, so a caller reading the code rather than the output -- a script,
        a CI leg, a newcomer watching for a failure -- was told a render still
        carrying `${VAULT_ROOT}` had succeeded.
        """
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 1, out)
        refusals = [line for line in out.splitlines() if line.startswith("refused: ")]
        self.assertEqual(len(refusals), 1, out)
        self.assertIn("unfilled placeholder", refusals[0])
        self.assertIn("claude-code.local.yaml", refusals[0])
        self.assertIn("--allow-unconfigured", refusals[0])
        # The refusal is about the host, not about the skill: what rendered
        # cleanly is still installed.
        self.assertTrue((self.dest / "fixture-notes" / "SKILL.md").is_file())

    def test_a_configured_host_installs_and_exits_zero(self) -> None:
        self._configure()
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0, out)
        self.assertNotIn("unfilled placeholder", out)

    def test_allow_unconfigured_installs_the_same_run_and_exits_zero(self) -> None:
        """The opt-out is explicit, and it says so in the note it leaves behind."""
        code, out = self._run(
            "--runtime", "claude-code", "--allow-unconfigured", "fixture-notes"
        )

        self.assertEqual(code, 0, out)
        self.assertIn("unfilled placeholders", out)
        rendered = (self.home / ".claude" / "spike-os" / "ADAPTER.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("${VAULT_ROOT}", rendered)

    def test_a_dry_run_reaches_the_same_verdict_as_the_run_it_previews(self) -> None:
        code, out = self._run("--runtime", "claude-code", "--dry-run", "fixture-notes")
        self.assertEqual(code, 1, out)
        self.assertIn("unfilled placeholder", out)

    def test_a_note_raised_after_the_write_still_prints(self) -> None:
        """The lead block prints what is known before writing; the rest follows."""
        self._write("catalog/approved.yaml", "packages: []\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                body_extra=" See [approved](../../catalog/approved.yaml).",
            ),
        )
        _, out = self._run("--runtime", "claude-code", "fixture-notes")
        lines = out.splitlines()
        dangling = [
            index for index, line in enumerate(lines)
            if "not declared on the Dependencies line" in line
        ]
        wrote = [index for index, line in enumerate(lines) if line.strip().startswith("wrote ")]
        self.assertTrue(dangling, out)
        self.assertTrue(wrote, out)
        self.assertGreater(dangling[0], wrote[0], out)

    def _claude_md(self, text: str) -> Path:
        path = self.home / ".claude" / "CLAUDE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_an_orphan_begin_marker_is_refused_and_the_file_is_untouched(self) -> None:
        """A begin with no end has no block to replace: appending one would put
        every owner line between the two markers inside our block, and the next
        run would delete them."""
        original = (
            "# Owner\n\n<!-- spike-os:begin -->\n\n- keep this line\n- and this one\n"
        )
        path = self._claude_md(original)
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("spike-os:begin", out)
        self.assertIn("line 3", out)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_dry_run_refuses_a_malformed_identity_file_the_same_way_a_real_run_does(
        self,
    ) -> None:
        """The preview must go through the guarded path, or a malformed marker
        unwinds past the summary: no `would install:` line, no notes, and a
        refusal missing the path prefix the real run prints."""
        original = "# Owner\n\n<!-- spike-os:begin -->\n\n- keep this line\n"
        path = self._claude_md(original)
        code, out = self._run("--runtime", "claude-code", "--dry-run", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertIn("would install: fixture-notes", out)
        self.assertIn("unfilled placeholders", out)
        self.assertIn(
            "refused: ~/.claude/CLAUDE.md: identity file carries an unpaired marker: "
            "'<!-- spike-os:begin -->' at line 3 has no '<!-- spike-os:end -->'",
            out,
        )
        self.assertNotIn("git -C", out)

    def test_a_real_run_and_a_dry_run_print_the_same_identity_refusal(self) -> None:
        self._configure()
        original = "# Owner\n\n<!-- spike-os:begin -->\n\n- keep this line\n"
        self._claude_md(original)
        _, dry = self._run("--runtime", "claude-code", "--dry-run", "fixture-notes")
        self._claude_md(original)
        _, real = self._run("--runtime", "claude-code", "fixture-notes")
        refusal = [line for line in dry.splitlines() if line.startswith("refused: ~/")]
        self.assertEqual(
            refusal, [line for line in real.splitlines() if line.startswith("refused: ~/")]
        )
        self.assertEqual(len(refusal), 1)

    def test_a_marker_sharing_a_line_is_named_in_the_unpaired_message(self) -> None:
        self._claude_md(
            "# Owner\nsome text <!-- spike-os:begin --> more text\n"
            "@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->\n"
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("line 2", out)

    def test_a_second_marker_block_is_refused_and_the_file_is_untouched(self) -> None:
        original = (
            "# Owner\n"
            "<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->\n"
            "- keep this line\n"
            "<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->\n"
        )
        path = self._claude_md(original)
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("more than one", out)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_an_end_marker_before_its_begin_is_refused(self) -> None:
        original = "# Owner\n<!-- spike-os:end -->\n<!-- spike-os:begin -->\n"
        path = self._claude_md(original)
        code, _ = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_a_stray_import_line_outside_the_block_is_collapsed_into_one(self) -> None:
        self._configure()
        path = self._claude_md(
            "# Owner\n@~/.claude/spike-os/ADAPTER.md\n\n- keep this line\n"
        )
        code, _ = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 0)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("@~/.claude/spike-os/ADAPTER.md"), 1)
        self.assertIn(
            "<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->",
            text,
        )
        self.assertIn("- keep this line", text)
        self.assertIn("# Owner", text)

    def test_a_stray_import_line_after_the_block_is_removed_too(self) -> None:
        self._configure()
        self._claude_md(
            "# Owner\n"
            "<!-- spike-os:begin -->\n@~/.claude/spike-os/ADAPTER.md\n<!-- spike-os:end -->\n"
            "- keep this line\n@~/.claude/spike-os/ADAPTER.md\n"
        )
        code, _ = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("@~/.claude/spike-os/ADAPTER.md"), 1)
        self.assertIn("- keep this line", text)

    def test_a_failed_identity_write_leaves_the_original_bytes(self) -> None:
        original = "# Owner\n\n- keep this line\n"
        path = self._claude_md(original)
        with mock.patch.object(install_skill.os, "replace", side_effect=OSError("disk full")):
            code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertEqual(
            [entry.name for entry in path.parent.iterdir() if entry.name != "CLAUDE.md"
             and entry.is_file()],
            [],
        )

    def test_install_refuses_a_symlinked_destination_directory(self) -> None:
        real = Path(self.tmp.name) / "elsewhere"
        real.mkdir()
        (real / "keep.txt").write_text("keep\n", encoding="utf-8")
        self.dest.mkdir(parents=True, exist_ok=True)
        (self.dest / "fixture-notes").symlink_to(real, target_is_directory=True)
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("symlink", out)
        self.assertTrue((self.dest / "fixture-notes").is_symlink())
        self.assertTrue((real / "keep.txt").is_file())

    # -- UNCONFIRMED refusal -------------------------------------------

    def test_install_refuses_a_provider_skill_bound_to_an_unconfirmed_term(self) -> None:
        code, out = self._run("--runtime", "claude-code", "fixture-tasks", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("task provider", out)
        self.assertIn("UNCONFIRMED", out)
        self.assertFalse((self.dest / "fixture-tasks").exists())
        # The skills that pass are still installed; the refusal is per skill.
        self.assertTrue((self.dest / "fixture-notes" / "SKILL.md").is_file())

    def test_a_notify_skill_is_refused_when_the_first_channel_is_unconfirmed(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notifier")
        self.assertTrue((self.dest / "fixture-notifier" / "SKILL.md").is_file())
        text = (self.root / "adapters" / "claude-code" / "adapter.yaml").read_text(
            encoding="utf-8"
        )
        text = text.replace(
            "  notification_channel:\n    value: an in-session reply, then the agent inbox\n",
            "  notification_channel:\n    value: the agent inbox\n"
            "    note: UNCONFIRMED - no channel on this host.\n",
        )
        (self.root / "adapters" / "claude-code" / "adapter.yaml").write_text(
            text, encoding="utf-8"
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notifier")
        self.assertEqual(code, 1)
        self.assertIn("notification channel", out)

    def test_the_provider_refusal_is_skipped_for_a_runtime_that_confirms_the_term(
        self,
    ) -> None:
        self._configure("openclaw")
        code, _ = self._run("--runtime", "openclaw", "fixture-tasks")
        self.assertEqual(code, 0)

    # -- personal values in a watched directory -------------------------

    def test_a_resolved_adapter_in_a_git_work_tree_is_called_out(self) -> None:
        """The render is the one file that holds the owner's actual values."""
        self._configure()
        watched = self.home / ".claude"
        watched.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(watched)], check=True)
        code, out = self._run("--runtime", "claude-code", "fixture-notes")

        self.assertEqual(code, 0, out)
        self.assertIn("adapter.resolved.yaml", out)
        self.assertIn("git work tree", out)
        self.assertIn("personal values", out)

    def test_no_such_note_where_nothing_is_watching(self) -> None:
        self._configure()
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 0, out)
        self.assertNotIn("git work tree", out)

    # -- DEGRADED install ----------------------------------------------

    def test_a_degraded_term_installs_with_a_printed_note(self) -> None:
        """DEGRADED is a known absence the skill's contract already covers.

        contracts/sync.md's `tasks/` row: where no provider connector is
        authorized the system of record flips to the datastore and the skill
        discloses that the object is mirror-only. That is a disclosed fallback,
        so the skill installs; only an UNCONFIRMED binding is a refusal.
        """
        self._configure()
        self._write_adapters(task_provider_marker="DEGRADED")
        code, out = self._run("--runtime", "claude-code", "fixture-tasks")

        self.assertEqual(code, 0, out)
        self.assertIn("degraded:", out)
        self.assertIn("task provider", out)
        self.assertTrue((self.dest / "fixture-tasks" / "SKILL.md").is_file())

    def test_an_unconfirmed_term_still_refuses_after_the_degraded_split(self) -> None:
        code, out = self._run("--runtime", "claude-code", "fixture-tasks")
        self.assertEqual(code, 1)
        self.assertIn("UNCONFIRMED", out)
        self.assertNotIn("degraded:", out)
        self.assertFalse((self.dest / "fixture-tasks").exists())

    def test_check_reports_a_degraded_term_as_a_note_not_drift(self) -> None:
        self._write_adapters(task_provider_marker="DEGRADED")
        self._run("--runtime", "claude-code", "fixture-tasks")
        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 0, out)
        self.assertIn("no drift.", out)
        self.assertIn("degraded:", out)
        self.assertIn("task provider", out)

    # -- the launcher's installed-here column ---------------------------

    def test_the_bundled_index_marks_what_this_destination_carries(self) -> None:
        """A launcher must never route to a skill that is not installed here."""
        self._configure()
        code, out = self._run(
            "--runtime", "claude-code", "fixture-launcher", "fixture-notes"
        )
        self.assertEqual(code, 0, out)
        index = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        rows = {
            line.split("|")[1].strip().strip("`"): line.rsplit("|", 2)[1].strip()
            for line in index.splitlines()
            if line.startswith("| `")
        }
        self.assertEqual(rows["fixture-notes"], "installed")
        self.assertEqual(rows["fixture-tasks"], "refused: task provider")
        self.assertEqual(rows["fixture-background"], "not installed")
        self.assertIn("| skill | use when | version | installed here |", index)
        self.assertIn("| --- | --- | --- | --- |", index)

    def test_an_already_stamped_skill_counts_as_installed_in_the_index(self) -> None:
        self._run("--runtime", "claude-code", "fixture-background")
        self._run("--runtime", "claude-code", "fixture-launcher")
        index = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("| `fixture-background` | Use when background applies. | 2.0.0 | installed |", index)

    def test_a_degraded_target_reads_as_installed_in_the_index(self) -> None:
        self._write_adapters(task_provider_marker="DEGRADED")
        self._run("--runtime", "claude-code", "fixture-launcher", "fixture-tasks")
        index = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("| `fixture-tasks` | Use when one task is the ask. | 2.0.0 | installed |", index)

    def test_a_table_that_is_not_the_skill_table_is_left_alone(self) -> None:
        # The index also carries a reserved-namespace table. Widening its rows
        # past its own header would leave malformed Markdown in the launcher's
        # one input.
        self._run("--runtime", "claude-code", "fixture-launcher")
        index = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("| namespace | status | system of record | authority |\n", index)
        self.assertIn("| `calendar` | reserved | provider | none yet |\n", index)

    def test_the_index_note_explains_the_column(self) -> None:
        self._run("--runtime", "claude-code", "fixture-launcher")
        index = (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("installed here", index)
        self.assertIn("reported as unavailable", index)

    # -- check ---------------------------------------------------------

    def test_check_passes_a_clean_install(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 0, out)

    def test_check_reports_a_bundled_file_edited_in_place(self) -> None:
        """Per-file digests are what made a supporting file auditable at all."""
        self._run("--runtime", "claude-code", "fixture-launcher")
        (self.dest / "fixture-launcher" / "references" / "detail.md").write_text(
            "tampered\n", encoding="utf-8"
        )
        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 1, out)
        self.assertIn("references/detail.md", out)
        self.assertIn("edited in place", out)

    def test_check_reports_a_recorded_file_deleted_from_the_install(self) -> None:
        self._run("--runtime", "claude-code", "fixture-launcher")
        (self.dest / "fixture-launcher" / "scripts" / "run.sh").unlink()
        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 1, out)
        self.assertIn("scripts/run.sh", out)
        self.assertIn("missing", out)

    def test_check_reports_a_file_the_stamp_never_recorded(self) -> None:
        """The stamp is the manifest, so a file nobody recorded is the drift.

        A directory this installer owns holding a file no install wrote is
        exactly what a declared-vs-actual pass exists to find; it is never
        deleted, only reported.
        """
        self._run("--runtime", "claude-code", "fixture-launcher")
        stray = self.dest / "fixture-launcher" / "scripts" / "stray.sh"
        stray.write_text("echo surprise\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 1, out)
        self.assertIn("scripts/stray.sh", out)
        self.assertIn("not recorded by the stamp", out)
        self.assertTrue(stray.is_file())

    def test_check_degrades_on_a_stamp_written_before_per_file_digests(self) -> None:
        """An old stamp is read, not rejected: it says less, and says so."""
        self._run("--runtime", "claude-code", "fixture-launcher")
        stamp_file = self.dest / "fixture-launcher" / ".spike-os.json"
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        stamp.pop("files")
        stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True), encoding="utf-8")
        (self.dest / "fixture-launcher" / "references" / "detail.md").write_text(
            "tampered\n", encoding="utf-8"
        )
        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 0, out)
        self.assertIn("no per-file digests recorded (pre-digest stamp)", out)
        self.assertIn("re-install to upgrade the stamp", out)
        self.assertNotIn("drift:", out)

    def test_check_reports_a_rendered_file_edited_in_place(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        path = self.dest / "fixture-notes" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("sha256", out)

    def test_check_reports_capabilities_that_changed_in_the_repo(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when notes are read from the vault. Not for tasks.",
                capabilities=("datastore:read", "datastore:write"),
                reads_from=("profile",),
                writes_to=("notes",),
                body_extra=" Reads the `owner datastore`.",
            ),
        )
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("capabilities", out)

    def test_check_reports_an_adapter_version_bump(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        self._write_adapters(claude_code_version=2)
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("adapter_version", out)

    def test_check_reports_a_backticked_term_the_adapter_does_not_define(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        path = self.dest / "fixture-notes" / "SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "`owner datastore`", "`imaginary provider`"
            ),
            encoding="utf-8",
        )
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("imaginary provider", out)

    def test_check_reports_an_installed_skill_bound_to_an_unconfirmed_term(self) -> None:
        self._run("--runtime", "openclaw", "fixture-tasks")
        staged = self.root / "dist" / "openclaw" / "workspace" / "skills"
        code, out = self._run("--runtime", "openclaw", "--check", "--dest", str(staged))
        self.assertEqual(code, 0, out)
        # Rebind the openclaw task provider to an unconfirmed value: the very
        # same install is now a skill the adapter cannot honestly support.
        path = self.root / "adapters" / "openclaw" / "adapter.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  task_provider:\n    value: the Todoist connector\n",
                "  task_provider:\n    value: the Todoist connector\n"
                "    note: UNCONFIRMED - the connector is not registered.\n",
            ),
            encoding="utf-8",
        )
        code, out = self._run("--runtime", "openclaw", "--check", "--dest", str(staged))
        self.assertEqual(code, 1)
        self.assertIn("task provider", out)

    # -- update --------------------------------------------------------

    def _install_launcher(self) -> None:
        """A clean install of the one fixture that carries every file kind."""
        self._configure()
        code, out = self._run("--runtime", "claude-code", "fixture-launcher")
        self.assertEqual(code, 0, out)

    def _repo_detail(self, text: str) -> None:
        self._write("skills/fixture-launcher/references/detail.md", text)

    def test_update_re_renders_only_what_the_repository_changed(self) -> None:
        """The point of the digests: rewrite the changed file, not the directory."""
        self._install_launcher()
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        installed = self.dest / "fixture-launcher"
        self.assertEqual(
            (installed / "references" / "detail.md").read_text(encoding="utf-8"),
            "a second edition\n",
        )
        wrote = [line.strip() for line in out.splitlines() if line.strip().startswith("wrote ")]
        self.assertEqual(wrote, [f"wrote {installed / 'references' / 'detail.md'}"], out)

    def test_update_leaves_an_install_that_matches_this_tree_alone(self) -> None:
        self._install_launcher()
        before = self._stamp("fixture-launcher")
        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("no change", out)
        self.assertEqual(self._stamp("fixture-launcher"), before)

    def test_update_refuses_a_file_you_edited_and_shows_what_it_would_have_written(
        self,
    ) -> None:
        """B7's binding line: it refuses nothing silently, and overwrites nothing."""
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("my own notes\n", encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertEqual(detail.read_text(encoding="utf-8"), "my own notes\n")
        self.assertIn("references/detail.md", out)
        self.assertIn("edited in the install", out)
        self.assertIn("-my own notes", out)
        self.assertIn("+a second edition", out)
        self.assertIn("--overwrite", out)

    def test_update_overwrite_replaces_exactly_the_file_it_refused(self) -> None:
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("my own notes\n", encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 0, out)
        self.assertEqual(detail.read_text(encoding="utf-8"), "a second edition\n")
        self.assertEqual(
            self._stamp("fixture-launcher")["files"]["references/detail.md"],
            install_skill.sha256_bytes(b"a second edition\n"),
        )

    def test_update_refuses_a_recorded_file_you_deleted_rather_than_restoring_it(
        self,
    ) -> None:
        self._install_launcher()
        (self.dest / "fixture-launcher" / "scripts" / "run.sh").unlink()

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("scripts/run.sh", out)
        self.assertIn("missing from the install", out)
        self.assertFalse((self.dest / "fixture-launcher" / "scripts" / "run.sh").exists())

    def test_update_reports_a_file_the_stamp_never_recorded_and_never_deletes_it(
        self,
    ) -> None:
        self._install_launcher()
        stray = self.dest / "fixture-launcher" / "references" / "scratch.md"
        stray.write_text("mine\n", encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("references/scratch.md", out)
        self.assertIn("never deleted", out)
        self.assertTrue(stray.is_file())

    def test_update_reports_a_file_the_repository_no_longer_carries(self) -> None:
        self._install_launcher()
        (self.root / "skills" / "fixture-launcher" / "references" / "detail.md").unlink()

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("no longer part of this skill", out)
        self.assertTrue(
            (self.dest / "fixture-launcher" / "references" / "detail.md").is_file()
        )

    def test_the_pre_digest_refusal_names_what_the_re_install_costs(self) -> None:
        """The only escape it offers destroys exactly what it is protecting."""
        self._install_launcher()
        stamp_file = self.dest / "fixture-launcher" / ".spike-os.json"
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        stamp.pop("files")
        stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True), encoding="utf-8")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("replaces the whole directory", out)
        self.assertIn("copy", out)

    def test_overwrite_says_how_much_of_your_copy_it_discarded(self) -> None:
        """The destructive run printed the least of any run."""
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("mine\nand mine\n", encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 0, out)
        self.assertIn("2 installed lines discarded", out)

    def test_a_deleted_file_is_not_printed_back_as_a_whole_diff(self) -> None:
        self._write(
            "skills/fixture-launcher/references/detail.md", "alpha\nbeta\ngamma\n"
        )
        self._install_launcher()
        (self.dest / "fixture-launcher" / "references" / "detail.md").unlink()

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("3 lines would be restored", out)
        self.assertNotIn("+gamma", out)

    def test_update_refuses_a_pre_digest_stamp_rather_than_guessing(self) -> None:
        """Without per-file digests an edit of yours reads exactly like a stale render."""
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("my own notes\n", encoding="utf-8")
        stamp_file = self.dest / "fixture-launcher" / ".spike-os.json"
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        stamp.pop("files")
        stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True), encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("pre-digest stamp", out)
        self.assertEqual(detail.read_text(encoding="utf-8"), "my own notes\n")

    def test_update_refuses_one_skill_and_carries_on_to_the_next(self) -> None:
        """The error registry's row: nonzero, and every other skill still updated."""
        self._configure()
        code, out = self._run(
            "--runtime", "claude-code", "fixture-launcher", "fixture-notes"
        )
        self.assertEqual(code, 0, out)
        (self.dest / "fixture-launcher" / "references" / "detail.md").write_text(
            "my own notes\n", encoding="utf-8"
        )
        self._repo_detail("a second edition\n")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when notes are read from the vault. Not for tasks.",
                capabilities=("datastore:read",),
                reads_from=("profile",),
                body_extra=" Reads the `owner datastore` twice.",
            ),
        )

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("refused: fixture-launcher", out)
        self.assertIn("twice", self._installed("fixture-notes"))
        self.assertIn("updated: fixture-notes", out)

    def test_update_names_a_skill_that_is_not_installed_here(self) -> None:
        self._install_launcher()
        code, out = self._run("--runtime", "claude-code", "--update", "fixture-notes")

        self.assertEqual(code, 1, out)
        self.assertIn("fixture-notes", out)
        self.assertIn(".spike-os.json", out)

    def test_update_refuses_a_skill_the_adapter_can_no_longer_attest(self) -> None:
        """The install-time refusal is not one an update may walk past."""
        self._configure()
        self._write_adapters(task_provider_marker="DEGRADED")
        code, out = self._run("--runtime", "claude-code", "fixture-tasks")
        self.assertEqual(code, 0, out)
        self._write_adapters(task_provider_marker="UNCONFIRMED")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("UNCONFIRMED", out)

    def test_update_writes_nothing_on_a_dry_run(self) -> None:
        self._install_launcher()
        self._repo_detail("a second edition\n")
        before = self._stamp("fixture-launcher")

        code, out = self._run("--runtime", "claude-code", "--update", "--dry-run")

        self.assertEqual(code, 0, out)
        self.assertIn("would write", out)
        self.assertEqual(
            (self.dest / "fixture-launcher" / "references" / "detail.md").read_text(
                encoding="utf-8"
            ),
            "detail\n",
        )
        self.assertEqual(self._stamp("fixture-launcher"), before)

    def test_update_leaves_the_stamp_describing_what_it_actually_wrote(self) -> None:
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("my own notes\n", encoding="utf-8")
        self._repo_detail("a second edition\n")
        self._write("skills/fixture-launcher/scripts/run.sh", "echo two\n")
        before = self._stamp("fixture-launcher")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        stamp = self._stamp("fixture-launcher")
        # Written: the stamp records what landed. Refused: it still records what
        # the install put there, so the next --check reports the edit again.
        self.assertEqual(
            stamp["files"]["scripts/run.sh"], install_skill.sha256_bytes(b"echo two\n")
        )
        self.assertEqual(
            stamp["files"]["references/detail.md"], before["files"]["references/detail.md"]
        )

    def test_check_agrees_with_the_state_an_update_leaves(self) -> None:
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        detail.write_text("my own notes\n", encoding="utf-8")
        (self.dest / "fixture-launcher" / "references" / "scratch.md").write_text(
            "mine\n", encoding="utf-8"
        )
        self._write("skills/fixture-launcher/scripts/run.sh", "echo two\n")
        self._run("--runtime", "claude-code", "--update")

        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 1, out)
        self.assertIn("references/detail.md sha256 differs", out)
        self.assertIn("references/scratch.md is not recorded", out)
        self.assertNotIn("scripts/run.sh", out)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.email=fixture@example.com",
                "-c",
                "user.name=fixture",
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_update_prints_what_changed_between_the_stamped_commit_and_head(self) -> None:
        """The stamp records a commit; `git log` is what makes it mean something."""
        self._configure()
        self._git("init", "-q", "-b", "main")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "first")
        first = self._git("rev-parse", "HEAD")
        with mock.patch.object(install_skill, "repo_commit", return_value=first):
            self._run("--runtime", "claude-code", "fixture-launcher")
        self._repo_detail("a second edition\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "feat(fixture-launcher): a second edition")
        head = self._git("rev-parse", "HEAD")

        with mock.patch.object(install_skill, "repo_commit", return_value=head):
            code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn(f"changes since {first[:8]}", out)
        self.assertIn("feat(fixture-launcher): a second edition", out)

    def test_update_says_so_when_the_stamp_records_no_commit(self) -> None:
        self._install_launcher()
        stamp_file = self.dest / "fixture-launcher" / ".spike-os.json"
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        stamp["commit"] = ""
        stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True), encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("changes unknown -- pre-commit stamp", out)

    def test_update_says_so_when_git_cannot_read_the_stamped_commit(self) -> None:
        self._install_launcher()
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("changes unknown", out)

    def _case_insensitive(self) -> bool:
        probe = self.dest / "CaseProbe.tmp"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("x", encoding="utf-8")
        try:
            return (self.dest / "caseprobe.tmp").exists()
        finally:
            probe.unlink()

    def test_a_planned_write_onto_a_file_no_stamp_recorded_is_blocked(self) -> None:
        """The guard itself, on any filesystem: what is there is not ours to truncate.

        `installed_digests` keys the install by exact byte-name, so a file the
        filesystem resolves to the same entry under another name -- a case
        variant on APFS, a normalization variant -- is invisible to the
        classifier. The destination itself is asked instead.
        """
        self._install_launcher()
        directory = self.dest / "fixture-launcher"
        (directory / "references" / "probe.md").write_text("owner\n", encoding="utf-8")

        self.assertIsNotNone(
            install_skill.write_blocker(directory, "references/probe.md", {})
        )
        self.assertIsNone(
            install_skill.write_blocker(directory, "references/absent.md", {})
        )
        # A file the stamp does record is ours to rewrite, existing or not.
        self.assertIsNone(
            install_skill.write_blocker(
                directory, "references/probe.md", {"references/probe.md": "x"}
            )
        )

    def test_update_refuses_a_new_file_the_filesystem_already_holds_by_another_name(
        self,
    ) -> None:
        """A case-only collision truncated the owner's file and exited 0."""
        if not self._case_insensitive():
            self.skipTest("this filesystem is case-sensitive; the collision cannot arise")
        self._install_launcher()
        owner = self.dest / "fixture-launcher" / "references" / "Probe.md"
        owner.write_text("the owner's irreplaceable notes\n", encoding="utf-8")
        self._write("skills/fixture-launcher/references/probe.md", "probe body\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertEqual(
            owner.read_text(encoding="utf-8"), "the owner's irreplaceable notes\n"
        )
        self.assertIn("references/probe.md", out)
        self.assertIn("recorded by no stamp", out)

    def test_update_never_writes_through_a_symlink_even_when_told_to(self) -> None:
        """The installer does not follow a link out of the destination, on any flag."""
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        elsewhere = Path(self.tmp.name) / "outside.md"
        elsewhere.write_text("not ours\n", encoding="utf-8")
        detail.unlink()
        detail.symlink_to(elsewhere)
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 1, out)
        self.assertIn("symlink", out)
        self.assertEqual(elsewhere.read_text(encoding="utf-8"), "not ours\n")
        # Refused because it is a link: its target is not read out into the run.
        self.assertIn("neither read nor written", out)
        self.assertNotIn("not ours", out)

    def test_update_never_writes_through_a_symlinked_directory(self) -> None:
        """A link in any component of the path is still a link out of the install."""
        self._install_launcher()
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "probe.md").write_text("the owner's relocated file\n", encoding="utf-8")
        (self.dest / "fixture-launcher" / "references" / "sub").symlink_to(outside)
        self._write("skills/fixture-launcher/references/sub/probe.md", "from the repo\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertEqual(
            (outside / "probe.md").read_text(encoding="utf-8"),
            "the owner's relocated file\n",
        )
        self.assertIn("symlink", out)
        # Not written through, and not read through either: the diff would have
        # printed a file outside the destination.
        self.assertNotIn("the owner's relocated file", out)

    def test_overwrite_does_not_write_through_a_symlinked_directory_either(self) -> None:
        self._install_launcher()
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "probe.md").write_text("the owner's relocated file\n", encoding="utf-8")
        (self.dest / "fixture-launcher" / "references" / "sub").symlink_to(outside)
        self._write("skills/fixture-launcher/references/sub/probe.md", "from the repo\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 1, out)
        self.assertEqual(
            (outside / "probe.md").read_text(encoding="utf-8"),
            "the owner's relocated file\n",
        )

    def test_overwrite_never_claims_to_have_replaced_what_it_refused(self) -> None:
        """Claiming an action it did not take is the mirror of taking one silently."""
        self._install_launcher()
        detail = self.dest / "fixture-launcher" / "references" / "detail.md"
        elsewhere = Path(self.tmp.name) / "outside.md"
        elsewhere.write_text("not ours\n", encoding="utf-8")
        detail.unlink()
        detail.symlink_to(elsewhere)
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 1, out)
        self.assertNotIn("replaced it", out)
        self.assertIn("refused:", out)

    def _needs_unprivileged(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("running as root; a mode of 000 stops nothing")

    def _install_two(self) -> None:
        self._configure()
        code, out = self._run(
            "--runtime", "claude-code", "fixture-launcher", "fixture-notes"
        )
        self.assertEqual(code, 0, out)

    def _repo_notes_change(self) -> None:
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when notes are read from the vault. Not for tasks.",
                capabilities=("datastore:read",),
                reads_from=("profile",),
                body_extra=" Reads the `owner datastore` twice.",
            ),
        )

    def test_update_refuses_a_file_it_cannot_read_and_reaches_the_next_skill(
        self,
    ) -> None:
        """An owner-shaped filesystem state is a refusal, not a traceback.

        The error registry's row is "a refusal exits nonzero but continues to the
        next skill", and an unreadable file used to end the whole run before the
        skills after it were looked at.
        """
        self._needs_unprivileged()
        self._install_two()
        unreadable = self.dest / "fixture-launcher" / "references" / "detail.md"
        unreadable.chmod(0o000)
        self._repo_detail("a second edition\n")
        self._repo_notes_change()

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("references/detail.md", out)
        self.assertIn("could not be read", out)
        self.assertIn("twice", self._installed("fixture-notes"))
        # Named per file and survived per file: the diff must not read it either,
        # or the skill ends on the fallback guard with the rest of it unlooked at.
        self.assertNotIn("this skill was left as it is", out)
        self.assertIn("neither diffed nor written", out)

    def test_update_refuses_a_file_it_cannot_write_and_stamps_only_what_landed(
        self,
    ) -> None:
        self._needs_unprivileged()
        self._install_launcher()
        target = self.dest / "fixture-launcher" / "references" / "detail.md"
        before = self._stamp("fixture-launcher")["files"]["references/detail.md"]
        target.chmod(0o444)
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("could not be written", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "detail\n")
        self.assertEqual(
            self._stamp("fixture-launcher")["files"]["references/detail.md"], before
        )

    def test_update_refuses_a_path_where_a_file_stands_in_for_a_directory(self) -> None:
        self._install_launcher()
        (self.dest / "fixture-launcher" / "references" / "sub").write_text(
            "mine\n", encoding="utf-8"
        )
        self._write("skills/fixture-launcher/references/sub/probe.md", "from the repo\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("references/sub/probe.md", out)
        self.assertEqual(
            (self.dest / "fixture-launcher" / "references" / "sub").read_text(
                encoding="utf-8"
            ),
            "mine\n",
        )

    def test_check_reports_a_file_it_cannot_read_rather_than_ending_the_run(
        self,
    ) -> None:
        self._needs_unprivileged()
        self._install_two()
        unreadable = self.dest / "fixture-launcher" / "references" / "detail.md"
        unreadable.chmod(0o000)
        # The skill after it in the walk has its own drift, which is what shows
        # the check reached it at all.
        installed = self.dest / "fixture-notes" / "SKILL.md"
        installed.write_text(
            installed.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8"
        )

        code, out = self._run("--runtime", "claude-code", "--check")

        self.assertEqual(code, 1, out)
        self.assertIn("references/detail.md could not be read", out)
        self.assertNotIn("references/detail.md is recorded by the stamp and missing", out)
        self.assertIn("fixture-notes: SKILL.md sha256 differs", out)

    def test_update_and_check_refuse_a_symlinked_skill_directory(self) -> None:
        """The one component the containment walk never reached: the root itself.

        `install` refuses this shape by name; `stamped_installs` finds it through
        `is_dir()`, which follows links, so an update wrote the whole skill
        outside the destination and said nothing.
        """
        self._install_launcher()
        outside = Path(self.tmp.name) / "relocated"
        (self.dest / "fixture-launcher").rename(outside)
        (self.dest / "fixture-launcher").symlink_to(outside)
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update", "--overwrite")

        self.assertEqual(code, 1, out)
        self.assertIn("symlink", out)
        self.assertEqual(
            (outside / "references" / "detail.md").read_text(encoding="utf-8"), "detail\n"
        )

        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1, out)
        self.assertIn("symlink", out)

    def test_update_refuses_an_install_another_adapter_wrote(self) -> None:
        """An update is not a conversion: a runtime's install stays that runtime's."""
        self._install_launcher()
        stamp_file = self.dest / "fixture-launcher" / ".spike-os.json"
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
        stamp["adapter"] = "openclaw"
        stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True), encoding="utf-8")
        self._repo_detail("a second edition\n")

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 1, out)
        self.assertIn("openclaw", out)
        self.assertEqual(
            (self.dest / "fixture-launcher" / "references" / "detail.md").read_text(
                encoding="utf-8"
            ),
            "detail\n",
        )

    def test_update_says_the_adapter_file_is_behind_without_a_version_bump(self) -> None:
        """A binding can change without the version integer moving, and did.

        Every `SKILL.md` re-renders from the changed adapter while the rendered
        ADAPTER.md on disk keeps the old text; keying the staleness note on a
        hand-bumped `version:` reported none of it.
        """
        self._install_launcher()
        self._write(
            "adapters/claude-code/ADAPTER.md",
            (self.root / "adapters" / "claude-code" / "ADAPTER.md").read_text(
                encoding="utf-8"
            )
            + "\nQuiet hours are read in the owner's timezone.\n",
        )

        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("ADAPTER.md", out)
        self.assertIn("not what this tree renders", out)

    def test_update_and_check_say_the_adapter_still_carries_a_placeholder(self) -> None:
        """Neither renders the adapter, so neither can refuse -- but both can say."""
        code, out = self._run("--runtime", "claude-code", "fixture-launcher")
        self.assertEqual(code, 1, out)  # the unconfigured-host refusal

        for action in ("--update", "--check"):
            with self.subTest(action=action):
                _, out = self._run("--runtime", "claude-code", action)
                self.assertIn("unfilled placeholder", out)
                self.assertIn("VAULT_ROOT", out)

    def test_update_says_the_adapter_file_itself_is_not_refreshed(self) -> None:
        """`--update` re-renders skills; the ADAPTER.md they read is the install's job."""
        self._install_launcher()
        self._write_adapters(claude_code_version=2)
        code, out = self._run("--runtime", "claude-code", "--update")

        self.assertEqual(code, 0, out)
        self.assertIn("adapter_version 1", out)
        self.assertIn("re-run the install", out)

    def test_overwrite_without_update_is_a_usage_error(self) -> None:
        code, out = self._run("--runtime", "claude-code", "--overwrite", "fixture-notes")
        self.assertEqual(code, 2, out)
        self.assertIn("--update", out)

    def test_update_is_exclusive_with_the_other_actions(self) -> None:
        code, out = self._run("--runtime", "claude-code", "--update", "--check")
        self.assertEqual(code, 2, out)

    # -- list, uninstall, dry-run --------------------------------------

    def test_list_reads_the_stamps(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes", "fixture-launcher")
        code, out = self._run("--runtime", "claude-code", "--list")
        self.assertEqual(code, 0)
        self.assertIn("fixture-notes", out)
        self.assertIn("fixture-launcher", out)
        self.assertIn("2.0.0", out)

    def test_uninstall_removes_only_stamped_directories(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        foreign = self.dest / "health"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: health\n---\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "--uninstall", "--all")
        self.assertEqual(code, 0)
        self.assertFalse((self.dest / "fixture-notes").exists())
        self.assertTrue((foreign / "SKILL.md").is_file())

    def test_uninstall_refuses_an_unstamped_name(self) -> None:
        foreign = self.dest / "health"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: health\n---\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "--uninstall", "health")
        self.assertEqual(code, 1)
        self.assertTrue((foreign / "SKILL.md").is_file())

    def test_dry_run_shows_the_rendered_frontmatter_and_writes_nothing(self) -> None:
        # `--allow-unconfigured` rather than a filled local file: this test is
        # about the run writing nothing, and the file it would create is one of
        # the things it must not write.
        code, out = self._run(
            "--runtime", "claude-code", "--dry-run", "--allow-unconfigured", "fixture-notes"
        )
        self.assertEqual(code, 0)
        self.assertIn("when_to_use:", out)
        self.assertIn(str(self.dest / "fixture-notes" / "SKILL.md"), out)
        overrides = self.home / ".config" / "spike-os" / "claude-code.local.yaml"
        self.assertIn(f"would write {overrides}", out)
        self.assertNotIn("created", out)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.home / ".claude" / "spike-os").exists())
        self.assertFalse((self.home / ".config" / "spike-os").exists())

    def test_an_unexpected_supporting_entry_is_reported_and_not_copied(self) -> None:
        """`examples/`, `evals/` and `routing-eval.jsonl` are excluded by name;
        anything else the installer does not carry is named rather than dropped
        in silence."""
        self._configure()
        self._write("skills/fixture-launcher/notes/scratch.md", "scratch\n")
        code, out = self._run("--runtime", "claude-code", "fixture-launcher")
        self.assertEqual(code, 0)
        self.assertIn("notes", out)
        self.assertFalse((self.dest / "fixture-launcher" / "notes").exists())
        self.assertNotIn("examples", out)
        self.assertNotIn("routing-eval.jsonl", out)

    def test_a_skill_the_installer_cannot_read_is_named_not_swallowed(self) -> None:
        self._write("skills/fixture-broken/SKILL.md", "no frontmatter here\n")
        code, out = self._run("--runtime", "claude-code", "--all")
        self.assertIn("fixture-broken", out)

    def test_all_installs_every_skill_the_runtime_carries(self) -> None:
        code, out = self._run("--runtime", "claude-code", "--all")
        # fixture-tasks is refused (unconfirmed task provider), so the run fails,
        # but every skill that passes is installed.
        self.assertEqual(code, 1)
        for name in (
            "fixture-notes",
            "fixture-launcher",
            "fixture-background",
            "fixture-destructive",
        ):
            self.assertTrue((self.dest / name / "SKILL.md").is_file(), name)
        self.assertFalse((self.dest / "fixture-openclaw-only").exists())
        self.assertFalse((self.dest / "fixture-tasks").exists())


class DeployRepoPlaceholderTest(unittest.TestCase):
    """The deploy-repo slug is a personal value, so the adapter carries a placeholder."""

    def test_the_openclaw_adapter_leaves_the_deploy_repo_to_the_local_file(self) -> None:
        self.assertIn("DEPLOY_REPO", install_skill.placeholder_names("openclaw"))

    def test_no_committed_openclaw_adapter_file_names_the_repository(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        for name in ("adapter.yaml", "ADAPTER.md"):
            text = (repo / "adapters" / "openclaw" / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotIn("vibe-blogging", text)
                self.assertIn("${DEPLOY_REPO}", text)


class IdentityFileOnThisHostTest(unittest.TestCase):
    """An identity file the installer edits has to be a path on this host.

    OpenClaw's is a file in another repository -- "runtime/workspace/AGENTS.md
    in <deploy repo>" -- and the run prints the manual step instead. The
    placeholder that stands for the deploy repo must not make that string read
    as a local path.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _bind(self, raw: str) -> tuple[list[str], object]:
        adapter = {
            "identity_import": {
                "file": raw,
                "line": "See `ADAPTER.md`.",
                "begin_marker": "<!-- spike-os:begin -->",
                "end_marker": "<!-- spike-os:end -->",
            }
        }
        report = install_skill.Report()
        install_skill.bind_identity_file(adapter, True, report)
        return report.notes, report.identity_change

    def test_a_path_in_another_repository_is_reported_not_edited(self) -> None:
        notes, change = self._bind("runtime/workspace/AGENTS.md in ${DEPLOY_REPO}")
        self.assertIsNone(change)
        self.assertTrue([note for note in notes if "is not on this host" in note], notes)

    def test_the_committed_openclaw_adapter_takes_that_path(self) -> None:
        adapter = install_skill.load_contract("adapters")["openclaw"]
        notes, change = self._bind(str(adapter["identity_import"]["file"]))
        self.assertIsNone(change)
        self.assertTrue([note for note in notes if "is not on this host" in note], notes)

    def test_a_home_placeholder_is_still_a_path_on_this_host(self) -> None:
        notes, _change = self._bind("${HOME}/.claude/CLAUDE.md")
        self.assertEqual([note for note in notes if "is not on this host" in note], [])


class GitIgnoredDestinationTest(unittest.TestCase):
    """The personal-values note is about a destination a commit could carry.

    `make stage-openclaw` renders into `dist/`, which `.gitignore` covers, so
    the note fired on every stage about a file git will never offer to commit.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "init", "-q", str(self.root)], check=True, capture_output=True
        )
        (self.root / ".gitignore").write_text("dist/\n", encoding="utf-8")
        (self.root / "dist").mkdir()
        (self.root / "adapters").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_destination_git_ignores_is_reported_ignored(self) -> None:
        self.assertTrue(
            install_skill.git_ignored(self.root / "dist" / "adapter.resolved.yaml")
        )

    def test_a_destination_git_watches_is_not(self) -> None:
        self.assertFalse(
            install_skill.git_ignored(self.root / "adapters" / "adapter.resolved.yaml")
        )

    def test_a_destination_outside_any_work_tree_is_not_ignored(self) -> None:
        outside = Path(self.tmp.name).parent / "not-a-repo-adapter.resolved.yaml"
        self.assertFalse(install_skill.git_ignored(outside))

    def _render_into(self, directory: Path) -> list[str]:
        """Notes from a dry-run adapter render whose output lands in `directory`."""
        adapters = install_skill.load_contract("adapters")
        adapter = dict(adapters["openclaw"])
        adapter["adapter_file"] = str(directory / "ADAPTER.md")
        report = install_skill.Report()
        install_skill.install_adapter(
            "openclaw", adapter, self.root / "overrides.yaml", True, report
        )
        return report.notes

    def test_a_render_into_an_ignored_directory_earns_no_note(self) -> None:
        """The whole point: `make stage-openclaw` should not warn about `dist/`."""
        notes = self._render_into(self.root / "dist")
        self.assertFalse(
            [note for note in notes if "git work tree" in note], notes
        )

    def test_a_render_into_a_watched_directory_still_earns_one(self) -> None:
        notes = self._render_into(self.root / "adapters")
        self.assertTrue([note for note in notes if "git work tree" in note], notes)


class UsageDocTest(unittest.TestCase):
    """`--help` prints the module's own usage doc, not a second copy of it.

    The 42-line docstring at the top of `tools/install_skill.py` is the written
    explanation of the tool -- the refusals, the stamp, the DEGRADED rule. A
    hand-written `description=` on the parser was a second source that no reader
    could tell was shorter than the first.
    """

    def _help(self) -> str:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            with self.assertRaises(SystemExit) as raised:
                install_skill.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        return stream.getvalue()

    def test_help_prints_the_module_docstring(self) -> None:
        text = self._help()
        for line in (install_skill.__doc__ or "").strip().splitlines():
            with self.subTest(line=line):
                self.assertIn(line.strip(), text)

    def test_help_carries_the_refusals_and_the_degraded_rule(self) -> None:
        text = self._help()
        self.assertIn("The refusals are the point of the tool", text)
        self.assertIn("DEGRADED is knowledge", text)
        self.assertIn("--local-overrides", text)

    def test_the_parser_holds_no_second_description(self) -> None:
        parser_source = Path(install_skill.cli.__file__).read_text(encoding="utf-8")
        self.assertFalse(
            "description=\"Render and install skills" in parser_source,
            "installer/cli.py carries a second description; --help has one source",
        )


if __name__ == "__main__":
    unittest.main()
