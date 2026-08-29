from __future__ import annotations

import contextlib
import importlib
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
        effects: tuple[str, ...] = (),
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
            f"    effects: [{', '.join(effects)}]\n"
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
            "  - name: datastore:write\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n"
            "  - name: provider:read\n"
            "    readOnlyHint: true\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n"
            "  - name: delete:external\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: true\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n"
            "  - name: notify:owner\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n",
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
        self._write("catalog/index.md", "# Index\n\n| skill | use when |\n")
        self._write_skills()

    def _write_adapters(self, *, claude_code_version: int = 1) -> None:
        self._write(
            "adapters/claude-code/adapter.yaml",
            "runtime: claude-code\n"
            f"version: {claude_code_version}\n"
            "vocabulary:\n"
            "  owner_datastore:\n"
            "    value: the fixture vault at ${VAULT_ROOT}\n"
            "  task_provider:\n"
            "    value: mirror-only\n"
            "    note: UNCONFIRMED - no task connector on this host.\n"
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
            "  disable_model_invocation_on: [destructiveHint, openWorldHint]\n"
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
            "| `task provider` | mirror-only — **UNCONFIRMED** |\n"
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
            "  file: runtime/workspace/AGENTS.md in chughtapan/vibe-blogging\n"
            '  line: "See `ADAPTER.md` for what the runtime terms resolve to."\n'
            "  begin_marker: <!-- spike-os:begin -->\n"
            "  end_marker: <!-- spike-os:end -->\n"
            "render:\n"
            "  when_to_use: false\n"
            "  disable_model_invocation_on: []\n"
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
                effects=("datastore:read",),
                reads_from=("profile",),
                body_extra=" Reads the `owner datastore`.",
            ),
        )
        self._write(
            "skills/fixture-tasks/SKILL.md",
            self._skill_md(
                "fixture-tasks",
                description="Use when one task is the ask. Not for a whole day.",
                effects=("datastore:read", "provider:read", "delete:external"),
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
                effects=("datastore:read",),
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
                effects=("datastore:read", "delete:external"),
                reads_from=("profile",),
            ),
        )
        self._write(
            "skills/fixture-notifier/SKILL.md",
            self._skill_md(
                "fixture-notifier",
                description="Use when the owner must be told. Not for silent runs.",
                effects=("notify:owner",),
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

    # -- the validator gate --------------------------------------------

    def test_refuses_to_install_when_the_validator_fails(self) -> None:
        self.validator.return_value = 1
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("validate_repo", out)
        self.assertFalse((self.dest / "fixture-notes").exists())

    # -- stamp ---------------------------------------------------------

    def test_install_writes_a_stamp_with_the_declared_fields(self) -> None:
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
                "effects",
                "hints",
            },
        )
        self.assertEqual(stamp["name"], "fixture-notes")
        self.assertEqual(stamp["version"], "2.0.0")
        self.assertEqual(stamp["adapter"], "claude-code")
        self.assertEqual(stamp["adapter_version"], 1)
        self.assertEqual(stamp["commit"], "0123456789abcdef")
        self.assertEqual(stamp["effects"], ["datastore:read"])
        self.assertTrue(stamp["hints"]["readOnlyHint"])
        self.assertEqual(
            stamp["sha256"], install_skill.sha256_text(self._installed("fixture-notes"))
        )

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
        self.assertEqual(meta["metadata"]["spike-os"]["effects"], ["datastore:read"])
        self.assertNotIn("disable-model-invocation", meta)
        self.assertNotIn("user-invocable", meta)

    def test_when_to_use_is_refused_when_it_breaks_the_combined_cap(self) -> None:
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when " + ("x" * 900) + ". Not for anything else.",
                effects=("datastore:read",),
                reads_from=("profile",),
            ),
        )
        code, out = self._run("--runtime", "claude-code", "fixture-notes")
        self.assertEqual(code, 1)
        self.assertIn("1536", out)

    def test_disable_model_invocation_follows_the_derived_hints(self) -> None:
        code, out = self._run(
            "--runtime", "claude-code", "fixture-destructive", "fixture-notes"
        )
        self.assertEqual(code, 0, out)
        self.assertIn("disable-model-invocation: true", self._installed("fixture-destructive"))
        self.assertIs(self._stamp("fixture-destructive")["hints"]["destructiveHint"], True)
        self.assertNotIn("disable-model-invocation", self._frontmatter("fixture-notes"))

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
        self.assertEqual(
            (self.dest / "fixture-launcher" / "references" / "index.md").read_text(
                encoding="utf-8"
            ),
            (self.root / "catalog" / "index.md").read_text(encoding="utf-8"),
        )
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
        self.assertIn('git -C', out)
        self.assertIn('registry: spike-os adapter', out)

        self._run("--runtime", "claude-code", "fixture-launcher")
        after_second = claude_md.read_text(encoding="utf-8")
        self.assertEqual(after_first, after_second)
        self.assertEqual(after_second.count("@~/.claude/spike-os/ADAPTER.md"), 1)

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
        self.assertIn('git -C', out)
        for call in run.call_args_list:
            self.assertNotIn("commit", call.args[0])

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
        code, _ = self._run("--runtime", "openclaw", "fixture-tasks")
        self.assertEqual(code, 0)

    # -- check ---------------------------------------------------------

    def test_check_passes_a_clean_install(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 0, out)

    def test_check_reports_a_rendered_file_edited_in_place(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        path = self.dest / "fixture-notes" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("sha256", out)

    def test_check_reports_effects_that_changed_in_the_repo(self) -> None:
        self._run("--runtime", "claude-code", "fixture-notes")
        self._write(
            "skills/fixture-notes/SKILL.md",
            self._skill_md(
                "fixture-notes",
                description="Use when notes are read from the vault. Not for tasks.",
                effects=("datastore:read", "datastore:write"),
                reads_from=("profile",),
                writes_to=("notes",),
                body_extra=" Reads the `owner datastore`.",
            ),
        )
        code, out = self._run("--runtime", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertIn("effects", out)

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
        code, out = self._run("--runtime", "claude-code", "--dry-run", "fixture-notes")
        self.assertEqual(code, 0)
        self.assertIn("when_to_use:", out)
        self.assertIn(str(self.dest / "fixture-notes" / "SKILL.md"), out)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.home / ".claude" / "spike-os").exists())
        self.assertFalse((self.home / ".config" / "spike-os").exists())

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


if __name__ == "__main__":
    unittest.main()
