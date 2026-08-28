"""Unit tests for the eval runner's Claude Code invoker and isolation doctor.

Never invokes the real `claude` binary: subprocess paths run against tiny fake
`claude` scripts that replay captured stream fixtures.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tools.evalrunner import HARNESS_VERSION, claude_cli, doctor, workspace


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "stream"


def _fixture_lines(name: str) -> list[str]:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8").splitlines()


class FakeClaudeScript:
    """Writes an executable stand-in for the `claude` binary."""

    def __init__(self, tmpdir: Path, body: str) -> None:
        self.path = tmpdir / "fake-claude.sh"
        self.path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)


class ParseStreamLinesTest(unittest.TestCase):
    def test_extracts_text_and_result_from_assistant_fixture(self) -> None:
        lines = _fixture_lines("assistant_result.jsonl")
        text, tool_uses, result_event, events = claude_cli.parse_stream_lines(lines)
        self.assertIn("OK", text)
        self.assertEqual(tool_uses, [])
        self.assertIsNotNone(result_event)
        assert result_event is not None
        self.assertEqual(result_event["subtype"], "success")
        self.assertIs(result_event["is_error"], False)
        self.assertIn("total_cost_usd", result_event)
        self.assertEqual(len(events), len([line for line in lines if line.strip()]))

    def test_thinking_blocks_are_not_part_of_text(self) -> None:
        lines = _fixture_lines("assistant_result.jsonl")
        text, _, _, _ = claude_cli.parse_stream_lines(lines)
        self.assertNotIn("signature", text)

    def test_extracts_skill_tool_use(self) -> None:
        lines = _fixture_lines("skill_tool_use.jsonl")
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(lines)
        self.assertTrue(tool_uses)
        self.assertEqual(tool_uses[0]["name"], "Skill")
        self.assertIsInstance(tool_uses[0]["input"], dict)

    def test_truncated_and_garbage_lines_are_ignored(self) -> None:
        clean = _fixture_lines("assistant_result.jsonl")
        expected = claude_cli.parse_stream_lines(clean)
        noisy = [clean[0], '{"type": "assist', "", "   ", "not json at all"] + clean[1:]
        actual = claude_cli.parse_stream_lines(noisy)
        self.assertEqual(actual[0], expected[0])
        self.assertEqual(actual[2], expected[2])
        self.assertEqual(len(actual[3]), len(expected[3]))

    def test_error_stream_is_classified_as_an_error(self) -> None:
        lines = _fixture_lines("error_result.jsonl")
        _, _, result_event, events = claude_cli.parse_stream_lines(lines)
        self.assertTrue(events)
        self.assertIsNotNone(result_event)
        assert result_event is not None
        self.assertIs(result_event["is_error"], True)
        self.assertEqual(claude_cli.classify_status(result_event, 1, ""), "error")

    def test_stream_without_a_result_event_falls_back_to_the_exit_code(self) -> None:
        self.assertEqual(claude_cli.classify_status(None, 0, ""), "ok")
        self.assertEqual(claude_cli.classify_status(None, 1, ""), "error")
        self.assertEqual(
            claude_cli.classify_status(None, 1, "API Error: 429 rate_limit_error"), "rate_limited"
        )

    def test_extract_result_object_handles_json_output_array(self) -> None:
        raw = FIXTURES.joinpath("json_schema_result.json").read_text(encoding="utf-8")
        payload = json.loads(raw)
        result_obj = claude_cli.extract_result_object(payload)
        self.assertIsNotNone(result_obj)
        assert result_obj is not None
        self.assertEqual(result_obj["type"], "result")
        self.assertEqual(doctor.structured_output_field(result_obj), "structured_output")
        self.assertEqual(result_obj["structured_output"], {"ok": True})

    def test_parse_output_falls_back_to_a_whole_blob_json_array(self) -> None:
        # `--output-format json` emits one JSON array, not one event per line.
        blob = FIXTURES.joinpath("json_schema_result.json").read_text(encoding="utf-8")
        text, tool_uses, result_event, events = claude_cli.parse_output(blob.splitlines())
        self.assertIsNotNone(result_event)
        assert result_event is not None
        self.assertEqual(result_event["type"], "result")
        self.assertEqual(result_event["structured_output"], {"ok": True})
        self.assertTrue(events)
        self.assertIsInstance(tool_uses, list)
        self.assertTrue(text)

    def test_parse_output_matches_the_line_parser_for_streams(self) -> None:
        lines = _fixture_lines("assistant_result.jsonl")
        self.assertEqual(claude_cli.parse_output(lines), claude_cli.parse_stream_lines(lines))

    def test_extract_result_object_handles_single_object(self) -> None:
        obj = {"type": "result", "subtype": "success"}
        self.assertEqual(claude_cli.extract_result_object(obj), obj)
        self.assertIsNone(claude_cli.extract_result_object([]))


class ScrubEnvTest(unittest.TestCase):
    def test_drops_nesting_vars_and_keeps_the_rest(self) -> None:
        environ = {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "CLAUDE_CODE_SESSION_ID": "abc",
            "CLAUDE_CONFIG_DIR": "/somewhere",
            "PATH": "/usr/bin",
            "HOME": "/home/tapan",
        }
        scrubbed = claude_cli.scrub_env(environ)
        self.assertNotIn("CLAUDECODE", scrubbed)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", scrubbed)
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", scrubbed)
        self.assertEqual(scrubbed["CLAUDE_CONFIG_DIR"], "/somewhere")
        self.assertEqual(scrubbed["PATH"], "/usr/bin")
        self.assertEqual(scrubbed["HOME"], "/home/tapan")

    def test_does_not_mutate_the_source_mapping(self) -> None:
        environ = {"CLAUDECODE": "1", "PATH": "/usr/bin"}
        claude_cli.scrub_env(environ)
        self.assertIn("CLAUDECODE", environ)


class StrategyFlagsTest(unittest.TestCase):
    def test_known_strategies_expose_flags(self) -> None:
        ws = Path("/tmp/ws")
        self.assertEqual(
            claude_cli.strategy_flags("project-sources", ws), ["--setting-sources", "project"]
        )
        self.assertEqual(claude_cli.strategy_flags("bare", ws), ["--bare"])
        self.assertEqual(claude_cli.strategy_flags("safe-mode", ws), ["--safe-mode"])
        self.assertEqual(
            claude_cli.strategy_flags("fresh-home", ws),
            ["--settings", str(ws / "isolated-settings.json")],
        )

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            claude_cli.strategy_flags("nope", Path("/tmp/ws"))

    def test_strategy_env_points_fresh_home_at_the_workspace(self) -> None:
        ws = Path("/tmp/ws")
        env = claude_cli.strategy_env("fresh-home", ws, {"HOME": "/home/tapan"})
        self.assertEqual(env["HOME"], str(ws / "home"))
        unchanged = claude_cli.strategy_env("project-sources", ws, {"HOME": "/home/tapan"})
        self.assertEqual(unchanged["HOME"], "/home/tapan")

    def test_strategy_order_is_the_documented_preference_order(self) -> None:
        self.assertEqual(
            [s.name for s in claude_cli.ISOLATION_STRATEGIES],
            ["project-sources", "fresh-home", "bare", "safe-mode"],
        )


class SubprocessRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runner(self, body: str) -> claude_cli.SubprocessClaudeRunner:
        script = FakeClaudeScript(self.tmpdir, body)
        return claude_cli.SubprocessClaudeRunner(str(script.path), sleep=lambda _s: None)

    def test_ok_path_replays_a_captured_stream(self) -> None:
        runner = self._runner(f'cat "{FIXTURES / "assistant_result.jsonl"}"\n')
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "Reply with OK"),
            cwd=self.tmpdir,
            env=claude_cli.scrub_env(os.environ),
            timeout_s=30.0,
        )
        result = runner.run(req)
        self.assertEqual(result.status, "ok")
        self.assertIn("OK", result.text)
        self.assertEqual(result.returncode, 0)
        self.assertIsNotNone(result.result_event)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_timeout_path_kills_the_process(self) -> None:
        runner = self._runner(f'{sys.executable} -c "import time; time.sleep(5)"\n')
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "hang"),
            cwd=self.tmpdir,
            env=claude_cli.scrub_env(os.environ),
            timeout_s=1.0,
        )
        started = time.monotonic()
        result = runner.run(req)
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, "timeout")
        self.assertLess(elapsed, 5.0)
        self.assertIsNotNone(result.returncode)

    def test_error_stream_and_stderr_are_reported(self) -> None:
        runner = self._runner(
            f'cat "{FIXTURES / "error_result.jsonl"}"\n'
            f'cat "{FIXTURES / "error_stderr.txt"}" >&2\n'
            "exit 1\n"
        )
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "boom", "--model", "zzz-not-a-model"),
            cwd=self.tmpdir,
            env=claude_cli.scrub_env(os.environ),
            timeout_s=30.0,
        )
        result = runner.run(req)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unrecognized_model", result.stderr_tail)

    def test_budget_exhaustion_is_its_own_status(self) -> None:
        stream = self.tmpdir / "budget.jsonl"
        stream.write_text(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error_max_budget_usd",
                    "is_error": True,
                    "errors": ["Reached maximum budget ($0.05)"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        runner = self._runner(f'cat "{stream}"\n')
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "spendy"),
            cwd=self.tmpdir,
            env={},
            timeout_s=30.0,
        )
        self.assertEqual(runner.run(req).status, "budget_exceeded")

    def test_missing_binary_returns_error_instead_of_raising(self) -> None:
        runner = claude_cli.SubprocessClaudeRunner(
            str(self.tmpdir / "does-not-exist"), sleep=lambda _s: None
        )
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "hi"), cwd=self.tmpdir, env={}, timeout_s=5.0
        )
        result = runner.run(req)
        self.assertEqual(result.status, "error")
        self.assertIsNone(result.result_event)

    def test_early_stop_on_skill_stops_reading(self) -> None:
        runner = self._runner(
            f'cat "{FIXTURES / "skill_tool_use.jsonl"}"\n'
            f'{sys.executable} -c "import time; time.sleep(10)"\n'
        )
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "run the sentinel probe"),
            cwd=self.tmpdir,
            env=claude_cli.scrub_env(os.environ),
            timeout_s=30.0,
        )
        started = time.monotonic()
        result = runner.run(req, early_stop_on_skill=True)
        elapsed = time.monotonic() - started
        # Early stop is a caller-requested kill, not a failure, so it stays "ok".
        self.assertEqual(result.status, "ok")
        self.assertLess(elapsed, 10.0)
        self.assertTrue(result.tool_uses)
        self.assertEqual(result.tool_uses[0]["name"], "Skill")

    def test_rate_limited_result_is_retried_then_reported(self) -> None:
        stream = self.tmpdir / "ratelimit.jsonl"
        stream.write_text(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "errors": ["API Error: 429 rate_limit_error"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        counter = self.tmpdir / "attempts"
        runner = self._runner(f'echo x >> "{counter}"\ncat "{stream}"\n')
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "hi"), cwd=self.tmpdir, env={}, timeout_s=30.0
        )
        result = runner.run(req)
        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(
            len(counter.read_text(encoding="utf-8").split()),
            1 + len(claude_cli.RETRY_BACKOFFS_S),
        )


class ChooseStrategyTest(unittest.TestCase):
    @staticmethod
    def _probe(name: str, **kwargs: object) -> doctor.ProbeResult:
        defaults: dict[str, object] = {
            "name": name,
            "available": True,
            "status": "ok",
            "sentinel_seen": True,
            "foreign_skills": [],
            "mcp_tools": [],
            "notes": [],
        }
        defaults.update(kwargs)
        return doctor.ProbeResult(**defaults)  # type: ignore[arg-type]

    def test_first_clean_probe_wins(self) -> None:
        probes = [
            self._probe("project-sources"),
            self._probe("fresh-home"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "project-sources")

    def test_leaked_foreign_skill_disqualifies_a_strategy(self) -> None:
        probes = [
            self._probe("project-sources", foreign_skills=["superpowers:brainstorming"]),
            self._probe("fresh-home"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "fresh-home")

    def test_missing_sentinel_disqualifies_a_strategy(self) -> None:
        probes = [
            self._probe("project-sources", sentinel_seen=False),
            self._probe("fresh-home"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "fresh-home")

    def test_leaked_mcp_tool_disqualifies_a_strategy(self) -> None:
        probes = [
            self._probe("project-sources", mcp_tools=["mcp__gbrain__search"]),
            self._probe("fresh-home"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "fresh-home")

    def test_unavailable_and_failed_probes_are_skipped(self) -> None:
        probes = [
            self._probe("project-sources", available=False),
            self._probe("fresh-home", status="timeout"),
            self._probe("bare", status="error"),
            self._probe("safe-mode", status="budget_exceeded"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "safe-mode")

    def test_no_clean_probe_returns_none(self) -> None:
        probes = [
            self._probe("project-sources", foreign_skills=["gstack"]),
            self._probe("fresh-home", sentinel_seen=False),
        ]
        self.assertIsNone(doctor.choose_strategy(probes))


class ClassifySkillsTest(unittest.TestCase):
    def test_marker_and_known_user_skills_are_foreign(self) -> None:
        foreign, other = doctor.classify_skills(
            ["zz-eval-sentinel-ab12", "superpowers:brainstorming", "my-local-skill", "code-review"],
            sentinel="zz-eval-sentinel-ab12",
            user_skill_names={"my-local-skill"},
        )
        self.assertEqual(foreign, ["superpowers:brainstorming", "my-local-skill"])
        self.assertEqual(other, ["code-review"])

    def test_plugin_prefixed_names_are_foreign(self) -> None:
        foreign, _ = doctor.classify_skills(
            ["some-plugin:helper"], sentinel="s", user_skill_names=set()
        )
        self.assertEqual(foreign, ["some-plugin:helper"])

    def test_builtin_baseline_wins_over_a_user_skill_name_collision(self) -> None:
        # `debug` is both a CLI built-in and a directory in the operator's skill
        # tree; the empirically derived baseline settles the collision.
        foreign, other = doctor.classify_skills(
            ["debug", "my-local-skill"],
            sentinel="s",
            user_skill_names={"debug", "my-local-skill"},
            builtin_names={"debug"},
        )
        self.assertEqual(foreign, ["my-local-skill"])
        self.assertEqual(other, ["debug"])

    def test_markers_beat_the_builtin_baseline(self) -> None:
        foreign, _ = doctor.classify_skills(
            ["gstack-thing"], sentinel="s", user_skill_names=set(), builtin_names={"gstack-thing"}
        )
        self.assertEqual(foreign, ["gstack-thing"])

    def test_sentinel_is_never_foreign(self) -> None:
        foreign, other = doctor.classify_skills(
            ["zz-eval-sentinel-ab12"], sentinel="zz-eval-sentinel-ab12", user_skill_names=set()
        )
        self.assertEqual(foreign, [])
        self.assertEqual(other, [])


class SentinelTextTest(unittest.TestCase):
    def test_sentinel_and_foreign_names_are_found_in_reply_text(self) -> None:
        text = "zz-eval-sentinel-ab12\ncode-review\nsuperpowers:brainstorming\n"
        self.assertTrue(doctor.sentinel_in_text(text, "zz-eval-sentinel-ab12"))
        self.assertEqual(
            doctor.foreign_markers_in_text(text), ["superpowers", "brainstorming"]
        )

    def test_clean_reply_has_no_markers(self) -> None:
        text = "zz-eval-sentinel-ab12\ncode-review\ndataviz\n"
        self.assertEqual(doctor.foreign_markers_in_text(text), [])


class DotenvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parses_pairs_and_ignores_comments(self) -> None:
        self.path.write_text(
            "# a comment\n"
            "\n"
            "CLAUDE_CODE_OAUTH_TOKEN=sk-oauth-123\n"
            "export QUOTED=\"with spaces\"\n"
            "SINGLE='single'\n"
            "  SPACED  =  padded  \n"
            "NOT_A_PAIR\n",
            encoding="utf-8",
        )
        values = workspace.dotenv_values(self.path)
        self.assertEqual(values["CLAUDE_CODE_OAUTH_TOKEN"], "sk-oauth-123")
        self.assertEqual(values["QUOTED"], "with spaces")
        self.assertEqual(values["SINGLE"], "single")
        self.assertEqual(values["SPACED"], "padded")
        self.assertNotIn("NOT_A_PAIR", values)

    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(workspace.dotenv_values(self.path.with_name("absent")), {})


class ProbeEnvironTest(unittest.TestCase):
    def test_dotenv_token_fills_in_when_the_process_has_none(self) -> None:
        env = doctor.probe_environ({"PATH": "/usr/bin"}, {"CLAUDE_CODE_OAUTH_TOKEN": "sk-1"})
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "sk-1")

    def test_process_env_wins_and_other_dotenv_keys_are_ignored(self) -> None:
        env = doctor.probe_environ(
            {"CLAUDE_CODE_OAUTH_TOKEN": "sk-real"},
            {"CLAUDE_CODE_OAUTH_TOKEN": "sk-file", "SECRET": "nope"},
        )
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "sk-real")
        self.assertNotIn("SECRET", env)


class HarnessVersionTest(unittest.TestCase):
    def test_version_is_pinned(self) -> None:
        self.assertEqual(HARNESS_VERSION, "0.1.0")


if __name__ == "__main__":
    unittest.main()
