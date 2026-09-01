#!/usr/bin/env python3
"""`tools/bootstrap.py` -- the paved road from a clone to a working `/home`.

The probes are live, so every one of them is exercised here against a stubbed
host rather than this machine: an absent CLI, a vault that is not there, a
connector the adapter still calls DEGRADED. The run's exit code is the other
subject -- a bootstrap that ends with a placeholder unfilled has not configured
anything, and says so.
"""

from __future__ import annotations

import io as _io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.bootstrap as bootstrap
import tools.install_skill as install_skill

ROOT = Path(__file__).resolve().parents[1]


class Result:
    """The subset of `subprocess.CompletedProcess` the probes read."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ProbeTest(unittest.TestCase):
    def test_python_probe_names_the_floor_it_cleared(self) -> None:
        step = bootstrap.probe_python()
        self.assertEqual(step.status, bootstrap.OK)
        self.assertIn("3.11", step.detail)

    def test_an_absent_agent_cli_is_named_with_its_fix_and_is_not_fatal(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value=None):
            step = bootstrap.probe_agent_cli("claude-code")
        self.assertEqual(step.status, bootstrap.ABSENT)
        self.assertIn("claude", step.fix)
        self.assertNotIn(step.status, bootstrap.FATAL_STATUSES)

    def test_a_present_agent_cli_reports_the_version_it_answered_with(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/usr/local/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "2.0.14\n")):
            step = bootstrap.probe_agent_cli("claude-code")
        self.assertEqual(step.status, bootstrap.OK)
        self.assertIn("2.0.14", step.detail)

    def test_a_vault_that_is_not_there_names_the_directory_to_make(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step = bootstrap.probe_vault(str(Path(tmp) / "absent-vault"))
        self.assertEqual(step.status, bootstrap.ABSENT)
        self.assertIn("mkdir", step.fix)
        self.assertIn("absent-vault", step.fix)

    def test_a_vault_with_no_value_at_all_says_which_key_is_empty(self) -> None:
        step = bootstrap.probe_vault("")
        self.assertEqual(step.status, bootstrap.ABSENT)
        self.assertIn("VAULT_ROOT", step.fix)

    def test_an_existing_vault_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step = bootstrap.probe_vault(tmp)
        self.assertEqual(step.status, bootstrap.OK)

    def test_the_registry_is_read_from_the_cli_and_the_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".claude.json"
            config.write_text('{"mcpServers": {"gbrain": {}}}', encoding="utf-8")
            with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
                 mock.patch.object(
                     bootstrap, "run_command",
                     return_value=Result(0, "todoist: npx todoist - Connected\n"),
                 ):
                servers, source = bootstrap.registry_servers("claude-code", home=Path(tmp))
        self.assertIn("todoist", servers)
        self.assertIn("gbrain", servers)
        self.assertIn("claude mcp list", source)

    def test_a_registered_connector_contradicts_a_frozen_degraded_note(self) -> None:
        """A10: the adapter's note is a fact about one host, and this is a probe."""
        step = bootstrap.probe_provider(
            "task provider",
            "the Todoist MCP server when the connector registry lists one, otherwise mirror-only",
            "DEGRADED - claude mcp list names no Todoist server on this host.",
            ("todoist",),
            "claude mcp list",
            "claude-code",
        )
        self.assertEqual(step.status, bootstrap.OK)
        self.assertIn("todoist", step.detail)
        self.assertIn("DEGRADED", step.fix)
        self.assertIn("adapters/claude-code/adapter.yaml", step.fix)

    def test_a_degraded_note_no_connector_contradicts_is_reported_as_degraded(self) -> None:
        step = bootstrap.probe_provider(
            "task provider",
            "the Todoist MCP server when the connector registry lists one, otherwise mirror-only",
            "DEGRADED - no Todoist server on this host.",
            ("gbrain",),
            "claude mcp list",
            "claude-code",
        )
        self.assertEqual(step.status, bootstrap.DEGRADED)
        self.assertIn("claude mcp list", step.detail)
        self.assertNotIn(step.status, bootstrap.FATAL_STATUSES)

    def test_a_binding_with_no_note_and_no_connector_is_named_as_a_claim(self) -> None:
        step = bootstrap.probe_provider(
            "calendar provider", "the Google Calendar MCP server", "",
            ("gbrain",), "claude mcp list", "claude-code",
        )
        self.assertEqual(step.status, bootstrap.ABSENT)
        self.assertIn("adapters/claude-code/adapter.yaml", step.fix)

    def test_a_binding_the_adapter_calls_none_needs_no_connector(self) -> None:
        step = bootstrap.probe_provider(
            "contacts provider", "none configured", "", (), "claude mcp list", "claude-code",
        )
        self.assertEqual(step.status, bootstrap.ABSENT)
        self.assertEqual(step.fix, "")

    def test_every_provider_the_shipped_adapters_name_is_probed(self) -> None:
        for runtime in ("claude-code", "openclaw"):
            with self.subTest(runtime=runtime):
                adapter = bootstrap.adapter(runtime)
                probed = {step.name for step in bootstrap.probe_providers(adapter, (), "x", runtime)}
                declared = {
                    key.replace("_", " ")
                    for key in (adapter.get("vocabulary") or {})
                    if key.endswith("_provider")
                }
                self.assertEqual(probed, declared)


class PlaceholderTest(unittest.TestCase):
    def test_every_shipped_placeholder_carries_a_gloss_and_an_example(self) -> None:
        for runtime in ("claude-code", "openclaw"):
            for name in install_skill.placeholder_names(runtime):
                with self.subTest(runtime=runtime, name=name):
                    self.assertIn(name, bootstrap.GLOSSES)
                    gloss, example = bootstrap.GLOSSES[name]
                    self.assertTrue(gloss.strip())
                    self.assertTrue(example.strip())

    def test_the_prompt_shows_the_gloss_and_the_example(self) -> None:
        out = _io.StringIO()
        asked: list[str] = []
        bootstrap.ask_placeholders(
            ["OWNER_TZ"], {}, lambda prompt: asked.append(prompt) or "Europe/Oslo", out
        )
        printed = out.getvalue()
        gloss, example = bootstrap.GLOSSES["OWNER_TZ"]
        self.assertIn(gloss, printed)
        self.assertIn(example, printed)
        self.assertIn("OWNER_TZ", asked[0])

    def test_an_empty_answer_keeps_the_value_already_there(self) -> None:
        values = bootstrap.ask_placeholders(
            ["OWNER_NAME"], {"OWNER_NAME": "Ada"}, lambda prompt: "", _io.StringIO()
        )
        self.assertEqual(values["OWNER_NAME"], "Ada")

    def test_end_of_input_ends_the_questions_rather_than_raising(self) -> None:
        def closed(prompt: str) -> str:
            raise EOFError

        values = bootstrap.ask_placeholders(
            ["OWNER_NAME", "OWNER_TZ"], {"OWNER_TZ": "UTC"}, closed, _io.StringIO()
        )
        self.assertEqual(values, {"OWNER_TZ": "UTC"})

    def test_unfilled_names_every_key_with_no_value(self) -> None:
        self.assertEqual(
            bootstrap.unfilled(["A", "B", "C"], {"A": "x", "B": "", "C": "  "}), ["B", "C"]
        )

    def test_the_written_file_reads_back_as_what_was_answered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude-code.local.yaml"
            values = {
                "OWNER_NAME": "Ada O'Brien",
                "OWNER_TZ": "Europe/London",
                "PUBLIC_SURFACES": "none",
            }
            bootstrap.write_overrides(path, "claude-code", sorted(values), values)
            self.assertEqual(install_skill.read_local_overrides(path), values)

    def test_a_key_the_adapter_no_longer_names_is_kept_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yaml"
            bootstrap.write_overrides(
                path, "claude-code", ["OWNER_TZ"], {"OWNER_TZ": "UTC", "OLD_KEY": "kept"}
            )
            self.assertEqual(install_skill.read_local_overrides(path)["OLD_KEY"], "kept")


class MakeTargetTest(unittest.TestCase):
    """`make start` is the newcomer's one command, and it runs this tool."""

    def test_make_start_runs_the_bootstrap(self) -> None:
        recipe: list[str] = []
        inside = False
        for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
            if line.startswith("start:"):
                inside = True
                continue
            if inside:
                if line.startswith("\t"):
                    recipe.append(line[1:].strip())
                elif line.strip():
                    break
        self.assertEqual(recipe, ["python3 tools/bootstrap.py"])

    def test_the_gate_is_still_the_default_goal(self) -> None:
        targets = [
            line.split(":", 1)[0]
            for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
            if line and not line[0].isspace() and ":" in line
            and not line.startswith(("#", ".PHONY"))
        ]
        self.assertEqual(targets[0], "validate")


class RunTest(unittest.TestCase):
    """`main` end to end, with the installer and the host stubbed out."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(parents=True)
        self.dest = Path(self.tmp.name) / "skills"
        self.overrides = Path(self.tmp.name) / "local.yaml"
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        self.installed: list[list[str]] = []
        self.addCleanup(self._env.stop)
        self.addCleanup(self.tmp.cleanup)

    def _installer(self, argv: list[str]) -> int:
        self.installed.append(list(argv))
        return 0

    def _run(self, *argv: str, answers: str = "x", **kwargs: object) -> tuple[int, str]:
        out = _io.StringIO()
        code = bootstrap.main(
            ["--dest", str(self.dest), "--local-overrides", str(self.overrides), *argv],
            ask=lambda prompt: answers,
            out=out,
            installer=kwargs.get("installer", self._installer),
        )
        return code, out.getvalue()

    def test_a_full_run_installs_home_and_the_starter_set_and_says_type_home(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "ok\n")):
            code, out = self._run("--runtime", "claude-code")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.installed), 1, out)
        argv = self.installed[0]
        self.assertIn("home", argv)
        for name in bootstrap.STARTER_SKILLS:
            self.assertIn(name, argv)
        self.assertIn("--dest", argv)
        self.assertIn("type /home", out)

    def test_an_unanswered_placeholder_ends_the_run_nonzero_and_says_which(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "ok\n")):
            code, out = self._run("--runtime", "claude-code", answers="")
        self.assertEqual(code, bootstrap.EXIT_UNCONFIGURED, out)
        self.assertIn("OWNER_NAME", out)
        self.assertIn(str(self.overrides), out)

    def test_an_absent_cli_reports_the_manual_smoke_step_rather_than_skipping(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value=None), \
             mock.patch.object(bootstrap, "run_command") as run:
            code, out = self._run("--runtime", "claude-code")
        run.assert_not_called()
        self.assertEqual(code, 0, out)
        self.assertIn('claude -p "/home"', out)

    def test_no_smoke_says_it_was_skipped_and_names_the_step_to_run(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "ok\n")) as run:
            code, out = self._run("--runtime", "claude-code", "--no-smoke")
        self.assertEqual(code, 0, out)
        self.assertNotIn(bootstrap.SMOKE_PROMPT, [call.args[0][-1] for call in run.call_args_list])
        self.assertIn("--no-smoke", out)
        self.assertIn('claude -p "/home"', out)

    def test_a_failing_smoke_run_is_a_failure_with_the_first_line_of_the_error(self) -> None:
        def answer(command: list[str], **kwargs: object) -> Result:
            if command[:2] == ["claude", "-p"]:
                return Result(1, "", "Invalid API key\nrun /login\n")
            return Result(0, "2.0.14\n")

        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", side_effect=answer):
            code, out = self._run("--runtime", "claude-code")
        self.assertEqual(code, bootstrap.EXIT_UNCONFIGURED, out)
        self.assertIn("Invalid API key", out)

    def test_a_refusing_installer_ends_the_run_nonzero(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "ok\n")):
            code, out = self._run("--runtime", "claude-code", installer=lambda argv: 1)
        self.assertEqual(code, bootstrap.EXIT_UNCONFIGURED, out)

    def test_the_run_writes_only_where_it_was_told_to(self) -> None:
        with mock.patch.object(bootstrap, "which", return_value="/bin/claude"), \
             mock.patch.object(bootstrap, "run_command", return_value=Result(0, "ok\n")):
            self._run("--runtime", "claude-code")
        self.assertTrue(self.overrides.is_file())
        self.assertFalse((self.home / ".claude").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
