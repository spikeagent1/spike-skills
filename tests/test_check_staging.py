from __future__ import annotations

import contextlib
import importlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.install_skill as install_skill
import tools.validate_repo as validate_repo


class CheckStagingTest(unittest.TestCase):
    """`tools/check_staging.py` against staged output the real installer wrote.

    T24: `tools/install_skill.py`'s openclaw path was unit-tested but never run
    over the whole library, so this stages fixture skills with the real
    installer (mirroring tests/test_install_skill.py's fixture shape) and then
    runs the checker against the bytes actually on disk under `dist/`, not
    against anything reconstructed in memory.
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
        self._validator = mock.patch.object(install_skill, "run_validator", return_value=0)
        self._validator.start()
        self._commit = mock.patch.object(
            install_skill, "repo_commit", return_value="0123456789abcdef"
        )
        self._commit.start()
        self._write_repo()

    def tearDown(self) -> None:
        self._commit.stop()
        self._validator.stop()
        self._env.stop()
        importlib.reload(validate_repo)
        importlib.reload(install_skill)
        try:
            import tools.check_staging as check_staging

            importlib.reload(check_staging)
        except ImportError:
            pass
        self.tmp.cleanup()

    # -- fixture ---------------------------------------------------------

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _skill_md(
        self,
        name: str,
        *,
        description: str,
        dependencies: str,
        body_extra: str = "",
    ) -> str:
        return (
            "---\n"
            f"name: {name}\n"
            f'description: "{description}"\n'
            "metadata:\n"
            "  spike-os:\n"
            "    version: 2.0.0\n"
            "    runtime: [openclaw]\n"
            "    reads_from: [profile]\n"
            "    writes_to: []\n"
            "    capabilities: [datastore:read]\n"
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

    def _write_repo(self) -> None:
        self._write(
            "contracts/capabilities.yaml",
            "version: 1\n"
            "effects:\n"
            "  - name: datastore:read\n"
            "    readOnlyHint: true\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n",
        )
        self._write(
            "contracts/datastore.yaml",
            "version: 1\n"
            "namespaces:\n"
            "  - name: profile\n"
            "    status: active\n"
            "    system_of_record: datastore\n",
        )
        self._write(
            "adapters/vocabulary.yaml",
            "version: 1\n"
            "terms:\n"
            "  - term: owner datastore\n"
            "    key: owner_datastore\n"
            "    kind: datastore\n",
        )
        self._write(
            "adapters/claude-code/adapter.yaml",
            "runtime: claude-code\n"
            "version: 1\n"
            "vocabulary:\n"
            "  owner_datastore:\n"
            "    value: the fixture vault\n"
            "datastore:\n"
            "  paths:\n"
            "    profile: profile/\n"
            "  verbs:\n"
            "    read: get_page\n"
            "notification:\n"
            "  channels: []\n"
            "  quiet_hours:\n"
            "    start: '22:00'\n"
            "    end: '07:00'\n"
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
            "  disable_model_invocation_on_approval: []\n"
            "  user_invocable_default: true\n"
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
            "| `owner datastore` | the fixture vault |\n",
        )
        self._write(
            "adapters/openclaw/adapter.yaml",
            "runtime: openclaw\n"
            "version: 1\n"
            "vocabulary:\n"
            "  owner_datastore:\n"
            "    value: the GBrain store\n"
            "datastore:\n"
            "  paths:\n"
            "    profile: profile/\n"
            "  verbs:\n"
            "    read: gbrain get\n"
            "notification:\n"
            "  channels: []\n"
            "  quiet_hours:\n"
            "    start: '22:00'\n"
            "    end: '07:00'\n"
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
            "| `owner datastore` | the GBrain store |\n",
        )

        self._write(
            "skills/fixture-clean/SKILL.md",
            self._skill_md(
                "fixture-clean",
                description="Use when the fixture needs a clean body. Not for anything else.",
                dependencies=(
                    "**Dependencies:** the `GH_TOKEN` environment variable and the `gh` "
                    "command."
                ),
                body_extra=" Reads the `owner datastore`.",
            ),
        )
        self._write(
            "skills/fixture-runtime-leak/SKILL.md",
            self._skill_md(
                "fixture-runtime-leak",
                description="Use when the fixture needs a leaky body. Not for anything else.",
                dependencies="**Dependencies:** none beyond the contract.",
                body_extra=" Sends the reply over Telegram directly.",
            ),
        )
        self._write(
            "skills/fixture-bad-term/SKILL.md",
            self._skill_md(
                "fixture-bad-term",
                description="Use when the fixture needs a bad term. Not for anything else.",
                dependencies="**Dependencies:** none beyond the contract.",
                body_extra=" Reads the `spike datastore` instead.",
            ),
        )

    # -- helpers -----------------------------------------------------------

    def _install(self, *names: str) -> None:
        # `--allow-unconfigured`: a staging render leaves `${DEPLOY_REPO}` for the
        # deploy tree to fill, and an unfilled placeholder is a nonzero exit. What
        # this file checks is the staged tree, so the flag says which exit code
        # these tests are asserting about.
        argv = [
            "--runtime",
            "openclaw",
            "--allow-unconfigured",
            "--dest",
            str(self.root / "dist" / "openclaw" / "workspace" / "skills"),
            *names,
        ]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = install_skill.main(argv)
        self.assertEqual(code, 0, stream.getvalue())

    def _check(self) -> tuple[int, str]:
        import tools.check_staging as check_staging

        argv = [
            "--runtime",
            "openclaw",
            "--dest",
            str(self.root / "dist" / "openclaw" / "workspace"),
        ]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = check_staging.main(argv)
        return code, stream.getvalue()

    # -- tests ---------------------------------------------------------

    def test_a_clean_staged_skill_passes_all_three_checks(self) -> None:
        self._install("fixture-clean")
        code, out = self._check()
        self.assertEqual(code, 0, out)
        self.assertIn("0 finding", out)

    def test_a_runtime_specific_token_in_the_staged_body_is_reported(self) -> None:
        self._install("fixture-runtime-leak")
        code, out = self._check()
        self.assertEqual(code, 1)
        self.assertIn("Telegram", out)

    def test_the_runtime_binding_trailer_itself_is_not_flagged(self) -> None:
        """The trailer names the runtime (`Bound to adapter \\`openclaw\\``) by
        design; that is not the leak the runtime-specific check exists for."""
        self._install("fixture-clean")
        code, out = self._check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("fail:", out)
        self.assertIn("0 runtime-specific hit", out)

    def test_an_undefined_vocabulary_term_is_reported(self) -> None:
        self._install("fixture-bad-term")
        code, out = self._check()
        self.assertEqual(code, 1)
        self.assertIn("spike datastore", out)

    def test_a_requires_block_edited_out_of_step_with_its_own_body_is_reported(self) -> None:
        """Simulates on-disk drift: something hand-edited the staged frontmatter
        after install, and the requires block no longer matches the Dependencies
        line it was rendered from."""
        self._install("fixture-clean")
        staged = (
            self.root
            / "dist"
            / "openclaw"
            / "workspace"
            / "skills"
            / "fixture-clean"
            / "SKILL.md"
        )
        text = staged.read_text(encoding="utf-8")
        self.assertIn("bins: [gh]", text)
        staged.write_text(text.replace("bins: [gh]", "bins: []"), encoding="utf-8")
        code, out = self._check()
        self.assertEqual(code, 1)
        self.assertIn("requires.bins", out)

    def test_no_staged_skills_is_refused(self) -> None:
        (self.root / "dist" / "openclaw" / "workspace").mkdir(parents=True)
        code, out = self._check()
        self.assertEqual(code, 1)
        self.assertIn("refused", out)


class StagedRequiresParsingTest(unittest.TestCase):
    """The staged `requires` block is read by the frontmatter parser, not a regex.

    The regex matched `env:`/`bins:`/`config:` anywhere in the frontmatter, so a
    key of the same name outside `metadata.<runtime>.requires` shadowed the block
    the check is about.
    """

    STAGED = (
        "---\n"
        "name: fixture\n"
        "description: \"A skill.\"\n"
        "metadata:\n"
        "  spike-os:\n"
        "    env: [DECOY]\n"
        "  openclaw:\n"
        "    requires:\n"
        "      env: [REAL_TOKEN]\n"
        "      bins: [gh]\n"
        "      config: []\n"
        "---\n"
        "\n# Fixture\n"
    )

    def test_the_requires_block_of_the_named_runtime_wins(self) -> None:
        import tools.check_staging as check_staging

        parsed = check_staging.staged_requires(self.STAGED, "openclaw")
        self.assertEqual(
            parsed, {"env": ["REAL_TOKEN"], "bins": ["gh"], "config": []}
        )

    def test_a_missing_requires_block_reads_as_absent(self) -> None:
        import tools.check_staging as check_staging

        self.assertIsNone(
            check_staging.staged_requires(
                "---\nname: fixture\n---\n\n# Fixture\n", "openclaw"
            )
        )


if __name__ == "__main__":
    unittest.main()
