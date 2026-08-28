"""Unit tests for the eval runner's Claude Code invoker and isolation doctor.

Never invokes the real `claude` binary: subprocess paths run against tiny fake
`claude` scripts that replay captured stream fixtures.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import tools.run_evals as run_evals
from tools.evalrunner import (
    HARNESS_VERSION,
    cache,
    cases,
    claude_cli,
    doctor,
    executor,
    grader,
    workspace,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "stream"


def _fixture_lines(name: str) -> list[str]:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8").splitlines()


def _captured_error_event() -> dict:
    """The real result event the CLI emits for a failed turn.

    Shape matters: `subtype` is "success", there is no `errors` key, the message
    lives in `result`, and the HTTP status is in `api_error_status`.
    """
    _, _, result_event, _ = claude_cli.parse_stream_lines(_fixture_lines("error_result.jsonl"))
    assert result_event is not None
    return dict(result_event)


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

    def test_real_shaped_rate_limit_event_drives_the_retry_loop(self) -> None:
        # Same shape the binary emits: subtype "success", no `errors` key, HTTP
        # status in `api_error_status`. This is what the retry must actually fire on.
        event = _captured_error_event()
        event["api_error_status"] = 429
        event["result"] = "API Error: 429 rate_limit_error. Please retry shortly."
        stream = self.tmpdir / "real-ratelimit.jsonl"
        stream.write_text(json.dumps(event) + "\n", encoding="utf-8")
        counter = self.tmpdir / "real-attempts"
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


class RateLimitDetectionTest(unittest.TestCase):
    """Rate-limit detection against the shape the binary actually emits."""

    def test_the_captured_error_event_has_the_shape_these_tests_assume(self) -> None:
        event = _captured_error_event()
        self.assertEqual(event["subtype"], "success")
        self.assertIs(event["is_error"], True)
        self.assertNotIn("errors", event)
        self.assertIsInstance(event["result"], str)
        self.assertEqual(event["api_error_status"], 404)

    def test_real_shaped_429_is_rate_limited(self) -> None:
        event = _captured_error_event()
        event["api_error_status"] = 429
        event["result"] = "API Error: 429 rate_limit_error. Please retry shortly."
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "rate_limited")

    def test_http_status_alone_is_enough(self) -> None:
        event = _captured_error_event()
        event["api_error_status"] = 429
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "rate_limited")

    def test_overloaded_529_is_rate_limited(self) -> None:
        event = _captured_error_event()
        event["api_error_status"] = 529
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "rate_limited")

    def test_result_text_is_scanned_when_no_status_is_present(self) -> None:
        event = _captured_error_event()
        event.pop("api_error_status")
        event["result"] = "The model is overloaded right now."
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "rate_limited")

    def test_stderr_is_scanned_even_when_a_result_event_exists(self) -> None:
        event = _captured_error_event()
        event.pop("api_error_status")
        event["result"] = "Something went wrong."
        self.assertEqual(
            claude_cli.classify_status(event, 1, "API Error: 429 rate_limit_error"), "rate_limited"
        )

    def test_the_captured_404_event_is_still_a_plain_error(self) -> None:
        self.assertEqual(claude_cli.classify_status(_captured_error_event(), 1, ""), "error")

    def test_a_successful_reply_about_rate_limits_stays_ok(self) -> None:
        # The model's own answer is never scanned unless the CLI flagged an error,
        # so an eval response that discusses HTTP 429 is not a rate limit.
        event = _captured_error_event()
        event["is_error"] = False
        event.pop("api_error_status")
        event["terminal_reason"] = "end_turn"
        event["result"] = "A 429 means rate_limit_error; retry with backoff."
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "ok")

    def test_budget_exhaustion_still_wins_over_rate_limit_markers(self) -> None:
        event = _captured_error_event()
        event["subtype"] = "error_max_budget_usd"
        event["api_error_status"] = 429
        self.assertEqual(claude_cli.classify_status(event, 0, ""), "budget_exceeded")


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
        self.assertEqual(HARNESS_VERSION, "0.1.2")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_skill_tree(
    root: Path,
    name: str,
    *,
    examples: object | None = None,
    evals: object | None = None,
    routing: str | None = None,
    body: str | None = None,
) -> Path:
    """Write a throwaway `skills/<name>/` tree for loader and executor tests."""
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        body
        or (
            "---\n"
            f"name: {name}\n"
            f"description: Fixture skill {name}.\n"
            "---\n"
            "\n"
            f"# {name}\n"
            "\n"
            f"Do the {name} thing.\n"
        ),
        encoding="utf-8",
    )
    if examples is not None:
        _write_json(skill_dir / "examples" / "evals.json", examples)
    if evals is not None:
        _write_json(skill_dir / "evals" / "evals.json", evals)
    if routing is not None:
        skill_dir.joinpath("routing-eval.jsonl").write_text(routing, encoding="utf-8")
    return skill_dir


class CaseLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _load(self) -> list[cases.BehavioralCase]:
        return cases.load_behavioral_cases(self.root / "skills")

    def test_prompt_and_assertions_dialect_is_loaded(self) -> None:
        _write_skill_tree(
            self.root,
            "alpha",
            examples={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": 1,
                        "prompt": "Do the alpha thing.",
                        "expected_output": "Alpha happens.",
                        "assertions": ["Alpha is reported", "No mutation"],
                    }
                ],
            },
        )
        loaded = self._load()
        self.assertEqual(len(loaded), 1)
        case = loaded[0]
        self.assertEqual(case.skill, "alpha")
        self.assertEqual(case.file_rel, "skills/alpha/examples/evals.json")
        self.assertEqual(case.eval_id, 1)
        self.assertEqual(case.key, "alpha:examples:1")
        self.assertEqual(case.name, "alpha-1")
        self.assertEqual(case.prompt, "Do the alpha thing.")
        self.assertEqual(case.expected_output, "Alpha happens.")
        self.assertEqual(case.assertions, ["Alpha is reported", "No mutation"])

    def test_input_and_expect_dialect_normalizes_to_the_same_shape(self) -> None:
        _write_skill_tree(
            self.root,
            "beta",
            evals={
                "skill": "beta",
                "evals": [
                    {
                        "id": 1,
                        "name": "happy-path",
                        "input": "Do the beta thing.",
                        "expect": ["Beta is reported", "No mutation"],
                    }
                ],
            },
        )
        case = self._load()[0]
        self.assertEqual(case.prompt, "Do the beta thing.")
        self.assertEqual(case.assertions, ["Beta is reported", "No mutation"])
        self.assertEqual(case.name, "happy-path")
        self.assertIsNone(case.expected_output)
        self.assertEqual(case.key, "beta:evals:1")

    def test_expectations_key_is_also_accepted(self) -> None:
        _write_skill_tree(
            self.root,
            "gamma",
            examples={
                "evals": [
                    {"id": 3, "prompt": "Do gamma.", "expectations": ["Gamma is reported"]}
                ]
            },
        )
        self.assertEqual(self._load()[0].assertions, ["Gamma is reported"])

    def test_second_eval_file_in_a_skill_is_offset_by_one_hundred(self) -> None:
        _write_skill_tree(
            self.root,
            "delta",
            examples={"evals": [{"id": n, "prompt": f"e{n}", "assertions": ["a"]} for n in (1, 2)]},
            evals={"evals": [{"id": n, "input": f"v{n}", "expect": ["a"]} for n in (1, 2)]},
        )
        loaded = self._load()
        self.assertEqual([c.eval_id for c in loaded], [1, 2, 101, 102])
        self.assertEqual(
            [c.key for c in loaded],
            ["delta:examples:1", "delta:examples:2", "delta:evals:1", "delta:evals:2"],
        )

    def test_missing_assertions_is_a_load_error(self) -> None:
        _write_skill_tree(
            self.root, "eps", examples={"evals": [{"id": 1, "prompt": "p", "assertions": []}]}
        )
        with self.assertRaises(cases.CaseLoadError):
            self._load()

    def test_missing_prompt_is_a_load_error(self) -> None:
        _write_skill_tree(self.root, "zeta", examples={"evals": [{"id": 1, "assertions": ["a"]}]})
        with self.assertRaises(cases.CaseLoadError):
            self._load()

    def test_repo_community_management_has_both_files_with_offset_ids(self) -> None:
        loaded = cases.load_behavioral_cases()
        cm = [c for c in loaded if c.skill == "community-management"]
        self.assertEqual([c.eval_id for c in cm], [1, 2, 3, 4, 5, 6, 101, 102, 103, 104, 105, 106, 107, 108])
        self.assertEqual(len({c.key for c in cm}), len(cm))
        self.assertEqual(len({(c.skill, c.eval_id) for c in loaded}), len(loaded))
        self.assertTrue(all(c.prompt and c.assertions for c in loaded))


class CaseFilterTest(unittest.TestCase):
    @staticmethod
    def _case(skill: str, eval_id: int) -> cases.BehavioralCase:
        return cases.BehavioralCase(
            skill=skill,
            file_rel=f"skills/{skill}/examples/evals.json",
            eval_id=eval_id,
            key=f"{skill}:examples:{eval_id}",
            name=f"{skill}-{eval_id}",
            prompt="p",
            expected_output=None,
            assertions=["a"],
        )

    def setUp(self) -> None:
        self.all = [self._case(s, n) for s in ("alpha", "beta", "gamma") for n in (1, 2, 3)]

    def test_skill_filter_keeps_only_named_skills(self) -> None:
        picked = cases.select_cases(self.all, skills=["alpha", "gamma"])
        self.assertEqual(sorted({c.skill for c in picked}), ["alpha", "gamma"])

    def test_case_filter_selects_one_case_by_skill_and_id(self) -> None:
        picked = cases.select_cases(self.all, case_ids=["beta:2"])
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0].key, "beta:examples:2")

    def test_case_filter_accepts_a_full_key(self) -> None:
        picked = cases.select_cases(self.all, case_ids=["beta:examples:3"])
        self.assertEqual([c.eval_id for c in picked], [3])

    def test_unknown_case_selector_is_an_error(self) -> None:
        with self.assertRaises(cases.CaseLoadError):
            cases.select_cases(self.all, case_ids=["beta:99"])

    def test_unknown_skill_selector_is_an_error(self) -> None:
        with self.assertRaises(cases.CaseLoadError):
            cases.select_cases(self.all, skills=["nope"])

    def test_limit_truncates_in_stable_order(self) -> None:
        picked = cases.select_cases(self.all, limit=4)
        self.assertEqual([c.key for c in picked], [c.key for c in self.all[:4]])

    def test_sample_is_deterministic_for_a_seed_and_stays_sorted(self) -> None:
        first = cases.select_cases(self.all, sample=4, seed=7)
        second = cases.select_cases(self.all, sample=4, seed=7)
        other = cases.select_cases(self.all, sample=4, seed=8)
        self.assertEqual([c.key for c in first], [c.key for c in second])
        self.assertEqual(len(first), 4)
        self.assertEqual([c.key for c in first], sorted(c.key for c in first))
        self.assertNotEqual([c.key for c in first], [c.key for c in other])

    def test_sample_larger_than_the_pool_returns_everything(self) -> None:
        self.assertEqual(len(cases.select_cases(self.all, sample=99, seed=1)), len(self.all))


class CohortListTest(unittest.TestCase):
    YAML = (
        "cohorts:\n"
        "  - name: audience\n"
        "    status: completed\n"
        "    rationale: >-\n"
        "      Some prose that mentions skills and lists things.\n"
        "    skills:\n"
        "      - alpha\n"
        "      - beta\n"
        "    acceptance:\n"
        "      - not a skill name\n"
        "  - name: owner-operations\n"
        "    skills:\n"
        "      - gamma\n"
    )

    def test_only_the_skills_list_of_the_named_cohort_is_returned(self) -> None:
        parsed = cases.parse_cohort_lists(self.YAML)
        self.assertEqual(parsed["audience"], ["alpha", "beta"])
        self.assertEqual(parsed["owner-operations"], ["gamma"])

    def test_repo_cohorts_resolve_to_real_skill_directories(self) -> None:
        names = cases.cohort_skills("owner-operations")
        self.assertEqual(names, ["daily-task-manager", "briefing", "owner-dream-cycle"])

    def test_unknown_cohort_is_an_error(self) -> None:
        with self.assertRaises(cases.CaseLoadError):
            cases.cohort_skills("no-such-cohort")


class RoutingLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _routing(self, name: str, text: str) -> None:
        _write_skill_tree(self.root, name, routing=text)

    def test_comments_and_blank_lines_are_stripped_and_line_numbers_kept(self) -> None:
        self._routing(
            "alpha",
            "// a comment\n"
            "\n"
            '{"intent":"do alpha","expected_skill":"alpha"}\n'
            "// another\n"
            '{"intent":"not alpha","expected_skill":null}\n',
        )
        loaded = cases.load_routing_cases(self.root / "skills")
        self.assertEqual([c.line_no for c in loaded], [3, 5])
        self.assertEqual(loaded[0].expected_skill, "alpha")
        self.assertIsNone(loaded[1].expected_skill)
        self.assertEqual(loaded[1].ambiguous_with, [])

    def test_phantom_expected_without_self_ambiguity_becomes_must_not_route(self) -> None:
        self._routing("alpha", '{"intent":"x","expected_skill":"ghost-skill"}\n')
        case = cases.load_routing_cases(self.root / "skills")[0]
        self.assertTrue(case.phantom_expected)
        self.assertEqual(case.must_not_route, "alpha")
        self.assertFalse(case.soft)

    def test_phantom_expected_with_self_in_ambiguous_with_is_soft(self) -> None:
        self._routing(
            "alpha",
            '{"intent":"x","expected_skill":"ghost-skill","ambiguous_with":["alpha"]}\n',
        )
        case = cases.load_routing_cases(self.root / "skills")[0]
        self.assertTrue(case.phantom_expected)
        self.assertTrue(case.soft)
        self.assertIsNone(case.must_not_route)

    def test_phantom_ambiguous_entries_are_dropped_from_ambiguous_with(self) -> None:
        _write_skill_tree(self.root, "beta", routing=None)
        self._routing(
            "alpha",
            '{"intent":"x","expected_skill":"alpha","ambiguous_with":["beta","ghost"]}\n',
        )
        case = [c for c in cases.load_routing_cases(self.root / "skills") if c.skill_file == "alpha"][0]
        self.assertEqual(case.ambiguous_with, ["beta"])
        self.assertEqual(case.phantom_ambiguous, ["ghost"])
        self.assertFalse(case.phantom_expected)

    def test_repo_routing_files_classify_the_known_phantoms(self) -> None:
        loaded = cases.load_routing_cases()
        self.assertEqual(len(loaded), 32)
        phantoms = {
            (c.skill_file, c.expected_skill): c for c in loaded if c.phantom_expected
        }
        self.assertEqual(
            sorted(phantoms),
            [
                ("draft-in-voice", "reports"),
                ("draft-in-voice", "voice-note-ingest"),
                ("fact-check", "academic-verify"),
                ("fact-check", "citation-fixer"),
            ],
        )
        self.assertTrue(phantoms[("fact-check", "academic-verify")].soft)
        self.assertEqual(
            phantoms[("fact-check", "citation-fixer")].must_not_route, "fact-check"
        )
        dropped = sorted(
            {name for c in loaded for name in c.phantom_ambiguous}
        )
        self.assertEqual(dropped, ["bulk-ingestion", "daily-task-prep", "voice-note-ingest"])


class CacheKeyTest(unittest.TestCase):
    EXECUTOR = {
        "mode": "with_skill",
        "model": "sonnet",
        "system_prompt": "minimal",
        "skill_body": "# Briefing",
        "tools": "Read,Glob,Grep",
        "prompt": "Give me this morning's briefing.",
        "repeat": 1,
    }
    GRADER = {
        "grader_model": "opus",
        "grader_prompt": "grade it",
        "assertions": ["a", "b"],
        "expected_output": "something",
        "response": "the answer",
    }

    def test_executor_key_is_stable_and_input_sensitive(self) -> None:
        base = cache.executor_key(**self.EXECUTOR)
        self.assertEqual(base, cache.executor_key(**self.EXECUTOR))
        for field in self.EXECUTOR:
            changed = dict(self.EXECUTOR)
            changed[field] = 2 if field == "repeat" else str(self.EXECUTOR[field]) + "-x"
            self.assertNotEqual(base, cache.executor_key(**changed), field)

    def test_grader_key_is_stable_and_input_sensitive(self) -> None:
        base = cache.grader_key(**self.GRADER)
        self.assertEqual(base, cache.grader_key(**self.GRADER))
        for field in self.GRADER:
            changed = dict(self.GRADER)
            changed[field] = ["z"] if field == "assertions" else str(self.GRADER[field]) + "-x"
            self.assertNotEqual(base, cache.grader_key(**changed), field)

    def test_assertion_order_changes_the_grader_key(self) -> None:
        flipped = dict(self.GRADER, assertions=["b", "a"])
        self.assertNotEqual(cache.grader_key(**self.GRADER), cache.grader_key(**flipped))

    def test_harness_version_is_part_of_every_key(self) -> None:
        self.assertIn(HARNESS_VERSION, cache.key_material(**self.EXECUTOR, kind="executor"))
        self.assertIn(HARNESS_VERSION, cache.key_material(**self.GRADER, kind="grader"))


class CacheStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_put_then_get_is_a_hit(self) -> None:
        store = cache.Cache(self.root)
        store.put("k1", {"status": "ok"})
        self.assertEqual(store.get("k1"), {"status": "ok"})
        self.assertTrue(store.path_for("k1").is_file())

    def test_unknown_key_is_a_miss(self) -> None:
        self.assertIsNone(cache.Cache(self.root).get("nope"))

    def test_corrupt_entry_is_a_miss_not_a_crash(self) -> None:
        store = cache.Cache(self.root)
        store.put("k1", {"status": "ok"})
        store.path_for("k1").write_text("{not json", encoding="utf-8")
        self.assertIsNone(store.get("k1"))

    def test_disabled_cache_neither_reads_nor_writes(self) -> None:
        store = cache.Cache(self.root, enabled=False)
        store.put("k1", {"status": "ok"})
        self.assertIsNone(store.get("k1"))
        self.assertFalse(store.path_for("k1").exists())

    def test_refresh_config_misses_that_config_but_still_writes(self) -> None:
        store = cache.Cache(self.root, refresh_configs=["with_skill"])
        store.put("k1", {"status": "ok"})
        self.assertIsNone(store.get("k1", config="with_skill"))
        self.assertEqual(store.get("k1", config="without_skill"), {"status": "ok"})
        self.assertEqual(store.get("k1"), {"status": "ok"})
        self.assertTrue(store.path_for("k1").is_file())

    def test_entries_are_namespaced_by_key_only(self) -> None:
        store = cache.Cache(self.root)
        store.put("k1", {"n": 1})
        store.put("k2", {"n": 2})
        self.assertEqual(store.get("k1"), {"n": 1})
        self.assertEqual(store.get("k2"), {"n": 2})


class FakeClaudeRunner:
    """Scripted stand-in for `SubprocessClaudeRunner`; records every request it saw."""

    def __init__(self, results: list) -> None:
        self.results = list(results)
        self.requests: list[claude_cli.ClaudeRequest] = []

    def argv(self, *args: str) -> list[str]:
        return ["claude", *args]

    def run(
        self, req: claude_cli.ClaudeRequest, *, early_stop_on_skill: bool = False
    ) -> claude_cli.ClaudeResult:
        self.requests.append(req)
        if not self.results:
            raise AssertionError("FakeClaudeRunner ran out of scripted results")
        scripted = self.results.pop(0)
        return scripted(req) if callable(scripted) else scripted


def _ok_result(text: str, *, cost: float = 0.01, tool_uses: list | None = None) -> claude_cli.ClaudeResult:
    return claude_cli.ClaudeResult(
        status="ok",
        text=text,
        tool_uses=list(tool_uses or []),
        result_event={
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "total_cost_usd": cost,
            "duration_ms": 1234,
            "num_turns": 2,
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_read_input_tokens": 40,
            },
            "result": text,
        },
        events=[{"type": "result", "result": text}],
        returncode=0,
        duration_ms=1500,
    )


def _run_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "claude_bin": "claude",
        "model": "sonnet",
        "grader_model": "sonnet",
        "max_budget_usd": 0.5,
        "timeout": 180.0,
        "system_prompt_mode": "minimal",
        "isolation_strategy": "project-sources",
        "repo_root": None,
        "sandbox_root": None,
        "structured_output_field": "structured_output",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _behavioral_case(skill: str = "alpha", eval_id: int = 1) -> cases.BehavioralCase:
    return cases.BehavioralCase(
        skill=skill,
        file_rel=f"skills/{skill}/examples/evals.json",
        eval_id=eval_id,
        key=f"{skill}:examples:{eval_id}",
        name=f"{skill}-{eval_id}",
        prompt="Give me this morning's briefing.",
        expected_output="A cited briefing.",
        assertions=["Sources are cited", "No mutation"],
    )


class StripFrontmatterTest(unittest.TestCase):
    def test_leading_frontmatter_block_is_removed(self) -> None:
        text = "---\nname: alpha\ndescription: d\n---\n\n# Alpha\n\nBody.\n"
        self.assertEqual(executor.strip_frontmatter(text), "# Alpha\n\nBody.")

    def test_text_without_frontmatter_is_returned_unchanged(self) -> None:
        self.assertEqual(executor.strip_frontmatter("# Alpha\n"), "# Alpha")

    def test_a_later_horizontal_rule_is_not_treated_as_frontmatter(self) -> None:
        text = "# Alpha\n\n---\n\nMore.\n"
        self.assertEqual(executor.strip_frontmatter(text), text.strip())


class BuildRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root,
            "alpha",
            body=(
                "---\nname: alpha\ndescription: Fixture skill alpha.\n---\n\n"
                "# Alpha\n\nAlways cite sources.\n"
            ),
        )
        self.run_dir = self.root / "runs" / "r1"
        self.sandbox = self.root / "sandbox"
        self.args = _run_args(repo_root=self.root, sandbox_root=self.sandbox)
        self.case = _behavioral_case()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self, config: str) -> claude_cli.ClaudeRequest:
        return executor.build_request(
            self.case, config, self.args, ["--setting-sources", "project"], self.run_dir / config
        )

    def test_with_and_without_differ_only_by_the_skill_flags(self) -> None:
        with_argv = self._build("with_skill").argv
        without_argv = self._build("without_skill").argv
        header = executor.SKILL_HEADER.format(path=self.root / "skills" / "alpha")
        appended = with_argv[with_argv.index("--append-system-prompt") + 1]
        add_dir = with_argv[with_argv.index("--add-dir") + 1]
        stripped = [
            arg
            for arg in with_argv
            if arg not in {"--append-system-prompt", appended, "--add-dir", add_dir}
        ]
        self.assertEqual(stripped, without_argv)
        self.assertNotIn("--append-system-prompt", without_argv)
        self.assertNotIn("--add-dir", without_argv)
        self.assertTrue(appended.startswith(header))
        self.assertEqual(add_dir, str(self.root / "skills" / "alpha"))

    def test_mandatory_isolation_and_shape_flags_are_present(self) -> None:
        argv = self._build("without_skill").argv
        self.assertEqual(argv[:3], ["claude", "-p", self.case.prompt])
        for flag in ("--strict-mcp-config", "--no-session-persistence", "--verbose"):
            self.assertIn(flag, argv)
        for flag, value in (
            ("--output-format", "stream-json"),
            ("--tools", "Read,Glob,Grep"),
            ("--permission-mode", "dontAsk"),
            ("--model", "sonnet"),
            ("--max-budget-usd", "0.5"),
        ):
            self.assertEqual(argv[argv.index(flag) + 1], value, flag)
        self.assertEqual(argv[-2:], ["--setting-sources", "project"])

    def test_minimal_system_prompt_is_passed_and_claude_code_mode_omits_it(self) -> None:
        minimal = self._build("without_skill").argv
        self.assertEqual(
            minimal[minimal.index("--system-prompt") + 1], executor.minimal_system_prompt()
        )
        self.args.system_prompt_mode = "claude-code"
        self.assertNotIn("--system-prompt", self._build("without_skill").argv)

    def test_appended_body_has_no_frontmatter(self) -> None:
        argv = self._build("with_skill").argv
        appended = argv[argv.index("--append-system-prompt") + 1]
        self.assertNotIn("description: Fixture skill alpha.", appended)
        self.assertIn("Always cite sources.", appended)

    def test_env_is_scrubbed_of_nesting_variables(self) -> None:
        req = self._build("with_skill")
        self.assertNotIn("CLAUDECODE", req.env)
        self.assertFalse([key for key in req.env if key.startswith("CLAUDE_CODE_")])
        self.assertIn("PATH", req.env)

    def test_cwd_is_an_empty_scratch_dir_outside_the_repository(self) -> None:
        # Claude Code loads the operator's ~/.claude/CLAUDE.md whenever the working
        # directory sits inside a known project, and --setting-sources project does
        # not suppress it. Running from outside the repo is what keeps that memory
        # out of the eval context.
        req = self._build("with_skill")
        self.assertTrue(req.cwd.is_dir())
        self.assertEqual(list(req.cwd.iterdir()), [])
        self.assertFalse(req.cwd.is_relative_to(executor.ROOT))
        self.assertFalse(req.cwd.is_relative_to(self.run_dir))
        self.assertTrue(req.cwd.is_relative_to(self.sandbox))

    def test_each_run_gets_its_own_scratch_dir(self) -> None:
        first = executor.build_request(
            self.case, "with_skill", self.args, [], self.run_dir / "with_skill" / "run-1"
        )
        second = executor.build_request(
            self.case, "with_skill", self.args, [], self.run_dir / "with_skill" / "run-2"
        )
        self.assertNotEqual(first.cwd, second.cwd)

    def test_timeout_comes_from_args(self) -> None:
        self.args.timeout = 42.0
        self.assertEqual(self._build("with_skill").timeout_s, 42.0)

    def test_unknown_config_is_rejected(self) -> None:
        with self.assertRaises(executor.ConfigError):
            self._build("sideways_skill")


class OldSkillConfigTest(unittest.TestCase):
    """`old_skill@REF` grades the committed SKILL.md at a git ref, not the worktree."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._git("init", "--initial-branch", "main")
        self._git("config", "user.email", "eval@example.com")
        self._git("config", "user.name", "Eval")
        _write_skill_tree(
            self.root,
            "alpha",
            body="---\nname: alpha\ndescription: d\n---\n\n# Alpha v1\n\nOld guidance.\n",
        )
        self._git("add", ".")
        self._git("commit", "-m", "v1")
        (self.root / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: d\n---\n\n# Alpha v2\n\nNew guidance.\n",
            encoding="utf-8",
        )
        self._git("add", ".")
        self._git("commit", "-m", "v2")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=self.root, check=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_old_skill_ref_materializes_the_previous_body(self) -> None:
        args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        req = executor.build_request(
            _behavioral_case(), "old_skill@HEAD~1", args, [], self.root / "runs" / "old"
        )
        appended = req.argv[req.argv.index("--append-system-prompt") + 1]
        self.assertIn("Old guidance.", appended)
        self.assertNotIn("New guidance.", appended)
        self.assertNotIn("description: d", appended)

    def test_head_ref_matches_the_current_body(self) -> None:
        args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        req = executor.build_request(
            _behavioral_case(), "old_skill@HEAD", args, [], self.root / "runs" / "head"
        )
        appended = req.argv[req.argv.index("--append-system-prompt") + 1]
        self.assertIn("New guidance.", appended)

    def test_missing_ref_is_a_config_error(self) -> None:
        args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        with self.assertRaises(executor.ConfigError):
            executor.build_request(
                _behavioral_case(), "old_skill@no-such-ref", args, [], self.root / "runs" / "bad"
            )

    def test_config_dirname_is_filesystem_safe(self) -> None:
        self.assertEqual(executor.config_dirname("with_skill"), "with_skill")
        self.assertEqual(executor.config_dirname("old_skill@origin/main"), "old_skill@origin_main")


class ExecuteCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(self.root, "alpha")
        self.run_dir = self.root / "runs" / "r1" / "alpha" / "eval-1" / "with_skill" / "run-1"
        self.args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        self.case = _behavioral_case()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_artifacts_are_written_in_the_skill_creator_layout(self) -> None:
        req = executor.build_request(self.case, "with_skill", self.args, [], self.run_dir)
        runner = FakeClaudeRunner([_ok_result("Here is the briefing.", cost=0.02)])
        result = executor.execute_case(runner, req, self.run_dir)

        self.assertEqual(result.status, "ok")
        request_json = json.loads((self.run_dir / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request_json["argv"], req.argv)
        self.assertEqual(request_json["cwd"], str(req.cwd))
        self.assertEqual(len(request_json["system_prompt_sha256"]), 64)
        self.assertEqual(len(request_json["skill_body_sha256"]), 64)
        self.assertGreater(request_json["skill_chars"], 0)

        response = (self.run_dir / "outputs" / "response.md").read_text(encoding="utf-8")
        self.assertIn("Here is the briefing.", response)
        transcript = (self.run_dir / "transcript.md").read_text(encoding="utf-8")
        self.assertIn("## Eval Prompt", transcript)
        self.assertIn(self.case.prompt, transcript)
        self.assertIn("Here is the briefing.", transcript)

        timing = json.loads((self.run_dir / "timing.json").read_text(encoding="utf-8"))
        self.assertEqual(timing["total_tokens"], 100)
        self.assertEqual(timing["total_cost_usd"], 0.02)
        self.assertEqual(timing["model"], "claude-sonnet-5")
        self.assertGreater(timing["total_duration_seconds"], 0)

        stream = (self.run_dir / "stream.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(stream[0])["type"], "result")

    def test_request_json_records_env_keys_but_no_values(self) -> None:
        req = executor.build_request(self.case, "with_skill", self.args, [], self.run_dir)
        runner = FakeClaudeRunner([_ok_result("ok")])
        executor.execute_case(runner, req, self.run_dir)
        request_json = json.loads((self.run_dir / "request.json").read_text(encoding="utf-8"))
        self.assertIn("PATH", request_json["env_keys"])
        self.assertNotIn("env", request_json)
        blob = json.dumps(request_json)
        for key in ("PATH", "HOME", "USER"):
            if os.environ.get(key):
                self.assertNotIn(os.environ[key], blob, key)

    def test_without_skill_records_a_null_skill_body_sha(self) -> None:
        req = executor.build_request(self.case, "without_skill", self.args, [], self.run_dir)
        executor.execute_case(FakeClaudeRunner([_ok_result("ok")]), req, self.run_dir)
        request_json = json.loads((self.run_dir / "request.json").read_text(encoding="utf-8"))
        self.assertIsNone(request_json["skill_body_sha256"])
        self.assertEqual(request_json["skill_chars"], 0)

    def test_eval_metadata_is_written_at_the_eval_dir(self) -> None:
        eval_dir = self.run_dir.parent.parent
        executor.write_eval_metadata(eval_dir, self.case)
        metadata = json.loads((eval_dir / "eval_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["eval_id"], 1)
        self.assertEqual(metadata["eval_name"], "alpha-1")
        self.assertEqual(metadata["prompt"], self.case.prompt)
        self.assertEqual(metadata["assertions"], self.case.assertions)
        self.assertEqual(metadata["key"], self.case.key)
        self.assertEqual(metadata["file"], self.case.file_rel)


def _grading_payload(assertions: list[str], verdicts: list[bool]) -> dict:
    return {
        "expectations": [
            {"text": text, "passed": passed, "evidence": f"evidence for {text}"}
            for text, passed in zip(assertions, verdicts)
        ],
        "summary": {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0},
        "eval_feedback": {"suggestions": [], "overall": "No suggestions."},
    }


def _grader_result(structured: dict | None, *, text: str = "", cost: float = 0.005):
    event = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "total_cost_usd": cost,
        "duration_ms": 900,
        "model": "claude-sonnet-5",
        "usage": {"input_tokens": 5, "output_tokens": 6},
        "result": text,
    }
    if structured is not None:
        event["structured_output"] = structured
    return claude_cli.ClaudeResult(
        status="ok", text=text, result_event=event, events=[event], returncode=0, duration_ms=950
    )


class GraderRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = _behavioral_case()
        self.args = _run_args(grader_model="opus")

    def test_payload_is_blind_to_the_config(self) -> None:
        payload = grader.build_payload(self.case, "The response body.")
        self.assertEqual(
            sorted(payload), ["assertions", "expected_output", "prompt", "response"]
        )
        blob = json.dumps(payload)
        for leak in ("with_skill", "without_skill", "old_skill", "SKILL.md"):
            self.assertNotIn(leak, blob, leak)

    def test_request_is_tool_less_and_uses_structured_output(self) -> None:
        payload = grader.build_payload(self.case, "The response body.")
        req = grader.build_grader_request(payload, self.args, ["--setting-sources", "project"])
        argv = req.argv
        self.assertEqual(argv[:2], ["claude", "-p"])
        self.assertEqual(json.loads(argv[2]), payload)
        for flag, value in (
            ("--output-format", "json"),
            ("--model", "opus"),
            ("--tools", ""),
            ("--max-budget-usd", str(grader.GRADER_BUDGET_USD)),
            ("--json-schema", json.dumps(grader.GRADING_SCHEMA, separators=(",", ":"))),
            ("--system-prompt", grader.grader_prompt()),
        ):
            self.assertEqual(argv[argv.index(flag) + 1], value, flag)
        self.assertIn("--strict-mcp-config", argv)
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(argv[-2:], ["--setting-sources", "project"])
        self.assertNotIn("CLAUDECODE", req.env)

    def test_grader_cwd_is_an_empty_scratch_dir_outside_the_repository(self) -> None:
        # Same leak as the executor: a cwd inside the repo pulls the operator's
        # ~/.claude/CLAUDE.md into context, and the grader sees the response text.
        payload = grader.build_payload(self.case, "The response body.")
        req = grader.build_grader_request(payload, self.args, [])
        self.assertTrue(req.cwd.is_dir())
        self.assertFalse(req.cwd.is_relative_to(executor.ROOT))
        self.assertEqual(list(req.cwd.iterdir()), [])

    def test_grader_scratch_dir_is_distinct_from_the_executor_scratch_dir(self) -> None:
        run_dir = Path("/tmp/runs/r1/alpha/eval-1/with_skill/run-1")
        payload = grader.build_payload(self.case, "The response body.")
        graded = grader.build_grader_request(payload, self.args, [], run_dir=run_dir)
        executed = executor.build_request(self.case, "without_skill", self.args, [], run_dir)
        self.assertNotEqual(graded.cwd, executed.cwd)
        self.assertFalse(graded.cwd.is_relative_to(executor.ROOT))


class ParseGradingTest(unittest.TestCase):
    ASSERTIONS = ["Sources are cited", "No mutation"]

    def test_structured_output_is_parsed_and_the_summary_recomputed(self) -> None:
        raw = _grading_payload(self.ASSERTIONS, [True, False])
        parsed = grader.parse_grading(_grader_result(raw), self.ASSERTIONS)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual([e["text"] for e in parsed["expectations"]], self.ASSERTIONS)
        self.assertEqual([e["passed"] for e in parsed["expectations"]], [True, False])
        self.assertEqual(
            parsed["summary"], {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5}
        )
        self.assertEqual(parsed["eval_feedback"]["overall"], "No suggestions.")

    def test_a_wrong_number_of_expectations_is_rejected(self) -> None:
        raw = _grading_payload(self.ASSERTIONS[:1], [True])
        self.assertIsNone(grader.parse_grading(_grader_result(raw), self.ASSERTIONS))

    def test_reordered_or_invented_texts_are_rejected(self) -> None:
        reordered = _grading_payload(list(reversed(self.ASSERTIONS)), [True, True])
        self.assertIsNone(grader.parse_grading(_grader_result(reordered), self.ASSERTIONS))
        invented = _grading_payload(["Something else", "No mutation"], [True, True])
        self.assertIsNone(grader.parse_grading(_grader_result(invented), self.ASSERTIONS))

    def test_whitespace_and_case_differences_are_tolerated_and_canonicalized(self) -> None:
        loose = _grading_payload(["  sources   are cited ", "NO MUTATION"], [True, True])
        parsed = grader.parse_grading(_grader_result(loose), self.ASSERTIONS)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual([e["text"] for e in parsed["expectations"]], self.ASSERTIONS)

    def test_fenced_json_in_the_reply_text_is_the_fallback(self) -> None:
        raw = _grading_payload(self.ASSERTIONS, [True, True])
        text = "Here you go:\n```json\n" + json.dumps(raw) + "\n```\nDone."
        parsed = grader.parse_grading(_grader_result(None, text=text), self.ASSERTIONS)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["summary"]["passed"], 2)

    def test_bare_json_object_in_the_reply_text_is_the_fallback(self) -> None:
        raw = _grading_payload(self.ASSERTIONS, [False, False])
        parsed = grader.parse_grading(
            _grader_result(None, text="Result: " + json.dumps(raw)), self.ASSERTIONS
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["summary"]["pass_rate"], 0.0)

    def test_unparseable_output_returns_none(self) -> None:
        self.assertIsNone(
            grader.parse_grading(_grader_result(None, text="I refuse."), self.ASSERTIONS)
        )

    def test_a_non_boolean_verdict_is_rejected(self) -> None:
        raw = _grading_payload(self.ASSERTIONS, [True, True])
        raw["expectations"][1]["passed"] = "yes"
        self.assertIsNone(grader.parse_grading(_grader_result(raw), self.ASSERTIONS))

    def test_the_configured_structured_field_name_is_honored(self) -> None:
        raw = _grading_payload(self.ASSERTIONS, [True, True])
        result = _grader_result(None)
        assert result.result_event is not None
        result.result_event["structuredOutput"] = raw
        self.assertIsNone(grader.parse_grading(result, self.ASSERTIONS))
        parsed = grader.parse_grading(result, self.ASSERTIONS, field="structuredOutput")
        self.assertIsNotNone(parsed)


class GradeRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run-1"
        (self.run_dir / "outputs").mkdir(parents=True)
        (self.run_dir / "outputs" / "response.md").write_text(
            "Cited briefing, read-only.", encoding="utf-8"
        )
        self.case = _behavioral_case()
        self.args = _run_args()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_grading_json_is_written_with_the_recomputed_summary(self) -> None:
        raw = _grading_payload(self.case.assertions, [True, False])
        runner = FakeClaudeRunner([_grader_result(raw, cost=0.004)])
        grading = grader.grade_run(runner, self.run_dir, self.case, self.args)
        on_disk = json.loads((self.run_dir / "grading.json").read_text(encoding="utf-8"))
        self.assertEqual(grading, on_disk)
        self.assertEqual(on_disk["summary"], {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5})
        self.assertEqual(on_disk["status"], "ok")
        self.assertEqual(on_disk["grader_model"], "sonnet")
        self.assertEqual(on_disk["harness_version"], HARNESS_VERSION)
        self.assertEqual(on_disk["grader_cost_usd"], 0.004)
        payload_sent = json.loads(runner.requests[0].argv[2])
        self.assertEqual(payload_sent["response"], "Cited briefing, read-only.")

    def test_unusable_grader_output_is_recorded_as_grader_error(self) -> None:
        runner = FakeClaudeRunner([_grader_result(None, text="no json here")])
        grading = grader.grade_run(runner, self.run_dir, self.case, self.args)
        self.assertEqual(grading["status"], "grader_error")
        self.assertEqual(grading["expectations"], [])
        self.assertEqual(grading["summary"]["total"], len(self.case.assertions))
        self.assertEqual(grading["summary"]["passed"], 0)
        self.assertTrue((self.run_dir / "grading.json").is_file())

    def test_a_missing_response_is_recorded_without_calling_the_grader(self) -> None:
        (self.run_dir / "outputs" / "response.md").write_text("", encoding="utf-8")
        runner = FakeClaudeRunner([])
        grading = grader.grade_run(runner, self.run_dir, self.case, self.args)
        self.assertEqual(grading["status"], "no_response")
        self.assertEqual(runner.requests, [])


class RunCommandGuardTest(unittest.TestCase):
    """`run` must refuse rather than measure the operator's own configuration."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self._saved = run_evals.workspace.WORKSPACE
        run_evals.workspace.WORKSPACE = self.ws

    def tearDown(self) -> None:
        run_evals.workspace.WORKSPACE = self._saved
        self.tmp.cleanup()

    def _write_doctor(self, **overrides: object) -> None:
        payload: dict[str, object] = {
            "strategy": "project-sources",
            "claude_code_version": "9.9.9",
            "structured_output_field": "structured_output",
            "checked_at": "2026-08-28T00:00:00+00:00",
        }
        payload.update(overrides)
        (self.ws / "doctor.json").write_text(json.dumps(payload), encoding="utf-8")

    def _fake_claude(self, version: str) -> str:
        script = FakeClaudeScript(self.ws, f'echo "{version} (Claude Code)"\n')
        return str(script.path)

    def test_missing_doctor_json_is_refused(self) -> None:
        payload, problem = run_evals.load_doctor("claude")
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("is missing", problem)

    def test_null_strategy_is_refused(self) -> None:
        self._write_doctor(strategy=None)
        payload, problem = run_evals.load_doctor("claude")
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("no working isolation strategy", problem)

    def test_a_cli_version_drift_is_refused(self) -> None:
        self._write_doctor(claude_code_version="1.0.0")
        payload, problem = run_evals.load_doctor(self._fake_claude("2.0.0"))
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("re-run `doctor`", problem)

    def test_a_matching_doctor_json_is_accepted(self) -> None:
        self._write_doctor(claude_code_version="2.1.250")
        payload, problem = run_evals.load_doctor(self._fake_claude("2.1.250"))
        self.assertIsNone(problem)
        assert payload is not None
        self.assertEqual(payload["strategy"], "project-sources")

    def test_unreadable_doctor_json_is_refused(self) -> None:
        (self.ws / "doctor.json").write_text("{ broken", encoding="utf-8")
        payload, problem = run_evals.load_doctor("claude")
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("unreadable", problem)


class RunCommandPlumbingTest(unittest.TestCase):
    def test_configs_are_parsed_and_validated(self) -> None:
        self.assertEqual(
            run_evals._parse_configs("with_skill,without_skill"), ["with_skill", "without_skill"]
        )
        self.assertEqual(run_evals._parse_configs("old_skill@HEAD~2"), ["old_skill@HEAD~2"])
        with self.assertRaises(cases.CaseLoadError):
            run_evals._parse_configs("sideways")
        with self.assertRaises(cases.CaseLoadError):
            run_evals._parse_configs("")

    def test_run_directory_follows_the_skill_creator_layout(self) -> None:
        case = _behavioral_case("briefing", 3)
        path = run_evals._run_dir_for(Path("/runs/r1"), case, "with_skill", 2)
        self.assertEqual(path, Path("/runs/r1/briefing/eval-3/with_skill/run-2"))

    def test_old_skill_config_directory_is_filesystem_safe(self) -> None:
        case = _behavioral_case("briefing", 1)
        path = run_evals._run_dir_for(Path("/runs/r1"), case, "old_skill@origin/main", 1)
        self.assertEqual(path, Path("/runs/r1/briefing/eval-1/old_skill@origin_main/run-1"))

    def test_cohort_and_skill_filters_combine(self) -> None:
        args = argparse.Namespace(skill="fact-check", cohort="owner-operations")
        self.assertEqual(
            run_evals._resolve_skills(args),
            ["fact-check", "daily-task-manager", "briefing", "owner-dream-cycle"],
        )

    def test_no_selection_means_no_skill_filter(self) -> None:
        self.assertIsNone(
            run_evals._resolve_skills(argparse.Namespace(skill=None, cohort=None))
        )

    def test_a_cohort_that_lists_no_skills_is_an_error_not_everything(self) -> None:
        # catalog/cohorts.yaml ships `routing-overlap-and-long-tail` with `skills: []`.
        # Falling through to "no filter" would silently run all 146 cases.
        self.assertEqual(
            cases.cohort_skills("routing-overlap-and-long-tail"), [], "fixture assumption"
        )
        with self.assertRaises(cases.CaseLoadError):
            run_evals._resolve_skills(
                argparse.Namespace(skill=None, cohort="routing-overlap-and-long-tail")
            )

    def test_a_skill_filter_of_only_separators_is_an_error(self) -> None:
        for raw in (",", "", "  ", ",,"):
            with self.assertRaises(cases.CaseLoadError, msg=raw):
                run_evals._resolve_skills(argparse.Namespace(skill=raw, cohort=None))

    @staticmethod
    def _main_quietly(argv: list[str]) -> int:
        """Run the CLI with its diagnostics captured, so test output stays clean."""
        with contextlib.redirect_stderr(io.StringIO()):
            return run_evals.main(argv)

    def test_unimplemented_subcommands_still_exit_two(self) -> None:
        for name in run_evals.NOT_IMPLEMENTED:
            self.assertEqual(self._main_quietly([name]), 2, name)

    def test_run_without_a_selection_exits_two(self) -> None:
        self.assertEqual(self._main_quietly(["run", "--model", "sonnet"]), 2)

    def test_discover_load_mode_is_not_implemented(self) -> None:
        self.assertEqual(
            self._main_quietly(["run", "--all", "--load-mode", "discover", "--model", "sonnet"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
