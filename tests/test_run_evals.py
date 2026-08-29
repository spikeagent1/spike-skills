"""Unit tests for the eval runner's Claude Code invoker and isolation doctor.

Never invokes the real `claude` binary: subprocess paths run against tiny fake
`claude` scripts that replay captured stream fixtures.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
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
import tools.validate_repo as validate_repo
from tools.evalrunner import (
    HARNESS_VERSION,
    analysis,
    cache,
    cases,
    claude_cli,
    doctor,
    executor,
    grader,
    report,
    routing,
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
            "context_leak_ok": True,
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

    def test_a_context_leak_disqualifies_a_strategy(self) -> None:
        probes = [
            self._probe("project-sources", context_leak_ok=False),
            self._probe("fresh-home"),
        ]
        self.assertEqual(doctor.choose_strategy(probes), "fresh-home")

    def test_a_strategy_leaking_only_the_cli_reminder_is_chosen(self) -> None:
        probe = self._probe(
            "project-sources",
            context_leak_ok=doctor.context_probe_verdict(CLI_REMINDER_REPLY, "ok"),
        )
        self.assertEqual(doctor.choose_strategy([probe]), "project-sources")

    def test_a_strategy_leaking_a_memory_file_is_not_chosen(self) -> None:
        leak = "<memory>Contents of ~/.claude/CLAUDE.md: Tapan-Brain</memory>"
        probe = self._probe(
            "project-sources", context_leak_ok=doctor.context_probe_verdict(leak, "ok")
        )
        self.assertIsNone(doctor.choose_strategy([probe]))

    def test_an_unprobed_context_is_never_chosen(self) -> None:
        probes = [self._probe("project-sources", context_leak_ok=None)]
        self.assertIsNone(doctor.choose_strategy(probes))

    def test_a_comparison_row_is_never_chosen(self) -> None:
        probes = [self._probe("project-sources@repo-cwd", comparison=True)]
        self.assertIsNone(doctor.choose_strategy(probes))

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


# The reminder Claude Code injects into every headless call, as the model quoted
# it back during the real `doctor` run (address replaced with a fixture value).
CLI_EMAIL_SENTENCE = (
    "The user's email address is someone@example.edu. Use it only to identify the user, such as"
    " for authorship, attribution, or filtering their own work. Never send it to an unrelated"
    " service, such as in a request header, URL, or payload, unless the user explicitly asks."
)
CLI_IMPORTANT_LINE = (
    "IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to"
    " this context unless it is highly relevant to your task."
)
CLI_IDENTITY_BLOCK = (
    "# userEmail\n"
    + CLI_EMAIL_SENTENCE
    + "\n# currentDate\nToday's date is 2026-08-27.\n\n      "
    + CLI_IMPORTANT_LINE
)

CLI_REMINDER_REPLY = (
    "<memory>\n" + CLI_IDENTITY_BLOCK + "\n</memory>\n\n"
    "<memory>\nUSD budget: $0/$0.05; $0.05 remaining\n</memory>\n\n"
    "No memory files have been read or loaded in this conversation."
)


class ContextLeakProbeTest(unittest.TestCase):
    """The context probe catches the memory `--setting-sources project` does not suppress."""

    EMAIL = "someone@example.edu"

    def test_the_bare_sentinel_reply_is_clean(self) -> None:
        self.assertEqual(doctor.context_leak_markers("NO-MEMORY-IN-CONTEXT"), [])

    def test_the_sentinel_inside_a_memory_block_is_clean(self) -> None:
        text = "<memory>NO-MEMORY-IN-CONTEXT</memory>"
        self.assertEqual(doctor.context_leak_markers(text), [])

    def test_every_foreign_marker_is_caught(self) -> None:
        for marker in doctor.CONTEXT_LEAK_MARKERS:
            with self.subTest(marker=marker):
                found = doctor.context_leak_markers(f"I was given {marker} notes")
                self.assertIn(marker, found)

    def test_marker_matching_ignores_case(self) -> None:
        self.assertIn("CLAUDE.md", doctor.context_leak_markers("quoted from claude.md"))

    def test_the_operator_email_alone_is_not_a_hard_marker(self) -> None:
        # Ruling (B): the CLI injects the address into every config, so it is a
        # recorded confound (`identity_leak`), not proof that memory leaked.
        self.assertEqual(doctor.context_leak_markers(f"you are {self.EMAIL}"), [])

    def test_a_plain_reply_matches_nothing(self) -> None:
        self.assertEqual(doctor.context_leak_markers("a plain reply"), [])

    def test_the_cli_reminder_block_is_not_a_hard_marker(self) -> None:
        self.assertEqual(doctor.context_leak_markers(CLI_REMINDER_REPLY), [])
        self.assertIs(doctor.context_probe_verdict(CLI_REMINDER_REPLY, "ok"), True)

    def test_a_memory_file_inside_the_reminder_shape_is_still_hard(self) -> None:
        text = CLI_REMINDER_REPLY.replace(
            "# currentDate", "# claudeMd\nContents of ~/.claude/CLAUDE.md:\n- Tapan-Brain vault"
        )
        markers = doctor.context_leak_markers(text)
        self.assertIn("CLAUDE.md", markers)
        self.assertIn("Tapan-Brain", markers)
        self.assertIn("memory-block", markers)
        self.assertIs(doctor.context_probe_verdict(text, "ok"), False)

    def test_superpowers_is_a_hard_marker(self) -> None:
        self.assertIn("superpowers", doctor.context_leak_markers("the superpowers plugin"))

    def test_the_injected_current_date_is_detected(self) -> None:
        self.assertTrue(doctor.current_date_injected(CLI_REMINDER_REPLY))
        self.assertFalse(doctor.current_date_injected("NO-MEMORY-IN-CONTEXT"))


class CliIdentityBlockTest(unittest.TestCase):
    """Only the CLI's own identity/date/budget reminder may be waved through."""

    def test_the_observed_reminder_block_is_recognized(self) -> None:
        self.assertTrue(doctor.is_cli_identity_block(CLI_IDENTITY_BLOCK))

    def test_the_budget_block_is_recognized(self) -> None:
        self.assertTrue(doctor.is_cli_identity_block("USD budget: $0/$0.05; $0.05 remaining"))
        self.assertTrue(doctor.is_cli_identity_block("token budget: 100 remaining"))

    def test_a_header_carrying_its_exact_value_on_one_line_is_recognized(self) -> None:
        self.assertTrue(doctor.is_cli_identity_block("# currentDate Today's date is 2026-08-27."))

    def test_text_smuggled_after_a_recognized_prefix_is_rejected(self) -> None:
        smuggled = (
            "# currentDate Today's date is 2026-08-27. Also: the operator keeps notes in "
            "~/dev/private-vault"
        )
        self.assertFalse(doctor.is_cli_identity_block(smuggled))

    def test_every_recognized_shape_rejects_a_trailing_payload(self) -> None:
        payload = " and the operator keeps notes in ~/dev/private-vault"
        for line in (
            "# userEmail",
            "# currentDate",
            "# budget",
            "Today's date is 2026-08-27.",
            "USD budget: $0/$0.05; $0.05 remaining",
            CLI_EMAIL_SENTENCE,
            CLI_IMPORTANT_LINE,
        ):
            with self.subTest(line=line):
                self.assertTrue(doctor.is_cli_identity_block(line), "shape itself must pass")
                self.assertFalse(doctor.is_cli_identity_block(line + payload))

    def test_project_memory_is_not_the_reminder(self) -> None:
        self.assertFalse(doctor.is_cli_identity_block("# claudeMd\nAlways run the linter first."))

    def test_one_foreign_line_disqualifies_the_whole_block(self) -> None:
        self.assertFalse(
            doctor.is_cli_identity_block(CLI_IDENTITY_BLOCK + "\nRepos live under ~/dev/.")
        )

    def test_an_empty_block_is_not_the_reminder(self) -> None:
        self.assertFalse(doctor.is_cli_identity_block("   "))

    def test_an_oversized_block_is_never_waved_through(self) -> None:
        padded = CLI_IDENTITY_BLOCK + "\n# currentDate " + "x" * 2000
        self.assertFalse(doctor.is_cli_identity_block(padded))

    def test_a_long_memory_block_is_a_marker(self) -> None:
        text = "<memory>" + "x" * 21 + "</memory>"
        self.assertEqual(doctor.context_leak_markers(text), ["memory-block"])

    def test_a_short_memory_block_is_not_a_marker(self) -> None:
        self.assertEqual(doctor.context_leak_markers("<memory>none</memory>"), [])

    def test_an_unclosed_memory_block_still_counts(self) -> None:
        self.assertEqual(doctor.context_leak_markers("<memory>" + "y" * 40), ["memory-block"])

    def test_a_whole_reply_with_no_marker_is_clean(self) -> None:
        self.assertIs(doctor.context_probe_verdict("NO-MEMORY-IN-CONTEXT", "ok"), True)
        self.assertIs(doctor.context_probe_verdict(CLI_REMINDER_REPLY, "ok"), True)

    def test_a_whole_reply_with_a_marker_leaked(self) -> None:
        self.assertIs(
            doctor.context_probe_verdict("<memory>~/.claude/CLAUDE.md</memory>", "ok"), False
        )

    def test_a_truncated_reply_is_unprobed_rather_than_clean(self) -> None:
        # The spend cap cuts the turn off mid-answer: no marker yet is not "no leak".
        cut = "<memory>\n# claudeMd\nContents of /home/o/.clau"
        self.assertIsNone(doctor.context_probe_verdict(cut, "budget_exceeded"))
        self.assertIsNone(doctor.context_probe_verdict(cut, "ok"))
        self.assertIsNone(doctor.context_probe_verdict("NO-MEMORY-IN-CONTEXT", "budget_exceeded"))
        self.assertIsNone(doctor.context_probe_verdict("NO-MEMORY-IN-CONTEXT", "timeout"))
        self.assertIsNone(doctor.context_probe_verdict("", "ok"))

    def test_reply_termination_needs_the_sentinel_or_a_closed_block(self) -> None:
        self.assertTrue(doctor.reply_terminated("NO-MEMORY-IN-CONTEXT"))
        self.assertTrue(doctor.reply_terminated("NO-MEMORY-IN-CONTEXT."))
        self.assertTrue(doctor.reply_terminated(CLI_REMINDER_REPLY))
        self.assertFalse(doctor.reply_terminated("<memory>opened but never closed"))
        self.assertFalse(doctor.reply_terminated("<memory>a</memory><memory>b"))
        self.assertFalse(doctor.reply_terminated("I was given some notes about"))
        self.assertFalse(doctor.reply_terminated("   "))


class RedactionTest(unittest.TestCase):
    """Nothing the probes write to disk or print may carry the operator's address."""

    def test_the_operator_email_never_survives_redaction(self) -> None:
        redacted = doctor.redact_identity("hello me@example.edu.", "me@example.edu")
        self.assertNotIn("me@example.edu", redacted)
        self.assertIn(doctor.REDACTED_EMAIL, redacted)

    def test_redaction_ignores_case(self) -> None:
        redacted = doctor.redact_identity("ME@Example.EDU", "me@example.edu")
        self.assertNotIn("ME@Example.EDU", redacted)

    def test_the_full_name_is_redacted_before_its_parts(self) -> None:
        # Longest-first, or replacing "Pat" first would leave "Example" standing.
        self.assertEqual(
            doctor.redact_identity("from Pat Example today", "", "Pat Example"),
            "from [redacted-name] today",
        )

    def test_name_parts_too_short_to_tell_from_prose_are_dropped(self) -> None:
        # The full name stays distinctive even when neither part is on its own.
        self.assertEqual(doctor.name_variants("Al Bo"), ["Al Bo"])
        self.assertEqual(doctor.name_variants("Pat Example"), ["Pat Example", "Example", "Pat"])

    def test_any_other_address_is_redacted_too(self) -> None:
        redacted = doctor.redact_identity("write to other.person@example.com", "")
        self.assertNotIn("other.person@example.com", redacted)
        self.assertIn(doctor.REDACTED_EMAIL, redacted)

    def test_evidence_is_one_line_redacted_and_bounded(self) -> None:
        text = "first line\nsecond line me@example.edu " + "z" * 900
        snippet = doctor.evidence_snippet(text, "me@example.edu", limit=120)
        self.assertNotIn("\n", snippet)
        self.assertNotIn("me@example.edu", snippet)
        self.assertLess(len(snippet), 160)
        self.assertTrue(snippet.startswith("first line second line"))


class IdentityProbeTest(unittest.TestCase):
    EMAIL = "someone@example.edu"
    NAME = "Pat Example"

    def test_the_sentinel_reply_is_clean(self) -> None:
        self.assertEqual(doctor.identity_markers("UNKNOWN-USER", self.EMAIL, self.NAME), [])

    def test_the_email_is_evidence(self) -> None:
        found = doctor.identity_markers(f"You are {self.EMAIL}", self.EMAIL, self.NAME)
        self.assertEqual(found, ["email"])

    def test_the_name_is_evidence(self) -> None:
        found = doctor.identity_markers("Hello Pat Example!", self.EMAIL, self.NAME)
        self.assertEqual(found, ["name"])

    def test_empty_identity_values_match_nothing(self) -> None:
        self.assertEqual(doctor.identity_markers("anything at all", "", ""), [])

    def test_a_name_too_short_to_tell_from_prose_is_ignored(self) -> None:
        self.assertEqual(doctor.identity_markers("an ordinary reply", "", "an"), [])

    def test_the_ladder_runs_the_current_recipe_first_and_never_twice(self) -> None:
        names = [rung.name for rung in doctor.identity_ladder("project-sources")]
        self.assertEqual(
            names, ["project-sources@sandbox", "empty-setting-sources", "bare", "fresh-home"]
        )
        self.assertEqual(
            [rung.name for rung in doctor.identity_ladder("fresh-home")],
            ["fresh-home@sandbox", "empty-setting-sources", "bare"],
        )

    def test_the_bare_rung_declares_its_api_key_requirement(self) -> None:
        rungs = {rung.name: rung for rung in doctor.identity_ladder("project-sources")}
        self.assertEqual(rungs["bare"].requires_env, ("ANTHROPIC_API_KEY",))

    def test_a_mitigation_is_confirmed_only_by_the_context_probe(self) -> None:
        # A model can answer UNKNOWN-USER and still carry the identity in context,
        # so the rung's own reply is never enough to call the leak mitigated.
        self.assertTrue(doctor.mitigation_confirmed("NO-MEMORY-IN-CONTEXT", "ok", self.EMAIL))
        self.assertFalse(
            doctor.mitigation_confirmed(f"<memory># userEmail {self.EMAIL}</memory>", "ok", self.EMAIL)
        )

    def test_an_unusable_confirmation_never_confirms(self) -> None:
        self.assertFalse(doctor.mitigation_confirmed("NO-MEMORY-IN-CONTEXT", "error", self.EMAIL))
        self.assertFalse(doctor.mitigation_confirmed("   ", "ok", self.EMAIL))

    def test_the_first_confirmed_clean_rung_is_the_mitigation(self) -> None:
        probes = [
            doctor.IdentityProbeResult(name="project-sources@sandbox", leak=True),
            doctor.IdentityProbeResult(name="bare", available=False),
            doctor.IdentityProbeResult(name="fresh-home", leak=False, confirmed=True),
        ]
        self.assertEqual(doctor.choose_identity_mitigation(probes), "fresh-home")

    def test_no_clean_rung_means_no_mitigation(self) -> None:
        probes = [
            doctor.IdentityProbeResult(name="project-sources@sandbox", leak=True),
            doctor.IdentityProbeResult(
                name="fresh-home", leak=False, confirmed=True, status="error"
            ),
        ]
        self.assertIsNone(doctor.choose_identity_mitigation(probes))

    def test_an_unconfirmed_rung_is_never_the_mitigation(self) -> None:
        probes = [doctor.IdentityProbeResult(name="empty-setting-sources", leak=False)]
        self.assertIsNone(doctor.choose_identity_mitigation(probes))

    def test_an_unproven_rung_is_never_the_mitigation(self) -> None:
        probes = [
            doctor.IdentityProbeResult(
                name="empty-setting-sources", leak=False, confirmed=True, unproven=True
            )
        ]
        self.assertIsNone(doctor.choose_identity_mitigation(probes))

    def test_a_capped_or_failed_confirmation_never_yields_a_mitigation(self) -> None:
        # `budget_exceeded` is an ok-ish status elsewhere; for a claim of absence it is not.
        for status in ("budget_exceeded", "timeout", "error", "rate_limited"):
            with self.subTest(status=status):
                probes = [
                    doctor.IdentityProbeResult(
                        name="empty-setting-sources", leak=False, confirmed=True, status=status
                    )
                ]
                self.assertIsNone(doctor.choose_identity_mitigation(probes))
                self.assertFalse(
                    doctor.mitigation_confirmed("NO-MEMORY-IN-CONTEXT", status, self.EMAIL)
                )

    def test_a_confirmation_quoting_memory_content_is_not_a_mitigation(self) -> None:
        leaked = "<memory>Contents of ~/.claude/CLAUDE.md for the operator</memory>"
        self.assertFalse(doctor.mitigation_confirmed(leaked, "ok", self.EMAIL))

    def test_a_truncated_confirmation_is_not_a_mitigation(self) -> None:
        self.assertFalse(doctor.mitigation_confirmed("<memory>cut off here", "ok", self.EMAIL))


class PersistedProbeTest(unittest.TestCase):
    """Nothing a probe writes to disk may carry the operator's identity."""

    EMAIL = "someone@example.edu"
    NAME = "Pat Example"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "probe.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _leaky_result(self) -> claude_cli.ClaudeResult:
        text = f"Hello Pat, you are {self.EMAIL}"
        return claude_cli.ClaudeResult(
            status="ok",
            text=text,
            events=[
                {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
                {"type": "result", "result": text, "total_cost_usd": 0.01},
            ],
            stderr_tail=f"warning for {self.EMAIL}",
        )

    def test_a_persisted_stream_is_redacted(self) -> None:
        doctor.save_stream(self.path, self._leaky_result(), self.EMAIL, self.NAME)
        written = self.path.read_text(encoding="utf-8")
        self.assertNotIn(self.EMAIL, written)
        self.assertNotIn("Pat", written)
        self.assertIn(doctor.REDACTED_EMAIL, written)
        self.assertIn(doctor.REDACTED_NAME, written)
        for line in written.splitlines():
            json.loads(line)

    def test_a_persisted_stderr_tail_is_redacted(self) -> None:
        doctor.save_stream(self.path, self._leaky_result(), self.EMAIL, self.NAME)
        stderr = self.path.with_suffix(".stderr.txt").read_text(encoding="utf-8")
        self.assertNotIn(self.EMAIL, stderr)

    def test_a_content_probe_record_never_stores_the_reply(self) -> None:
        result = claude_cli.ClaudeResult(
            status="ok",
            text="<memory>Contents of ~/.claude/CLAUDE.md for " + self.EMAIL + "</memory>",
            events=[{"type": "assistant", "message": {"content": []}}],
        )
        path = Path(self.tmp.name) / "context-probe.json"
        doctor.save_content_record(
            path, result, ["CLAUDE.md"], doctor.evidence_snippet(result.text, self.EMAIL, 40)
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(record), {"status", "markers", "evidence_redacted", "length"})
        self.assertEqual(record["markers"], ["CLAUDE.md"])
        self.assertEqual(record["length"], len(result.text))
        self.assertNotIn(self.EMAIL, json.dumps(record))
        self.assertFalse(path.with_suffix(".jsonl").exists())


class RegressionGuardTest(unittest.TestCase):
    """The in-repo control row has to say which of three things happened."""

    def test_markers_mean_the_guard_held(self) -> None:
        self.assertEqual(
            doctor.regression_guard_state(["CLAUDE.md"], "<memory>...</memory>", "ok"), "held"
        )

    def test_a_capped_reply_still_counts_as_held_when_it_leaked(self) -> None:
        # Truncation can hide a leak; it cannot invent one.
        self.assertEqual(
            doctor.regression_guard_state(["CLAUDE.md"], "<memory>cut", "budget_exceeded"), "held"
        )

    def test_a_whole_reply_with_no_marker_is_inconclusive(self) -> None:
        self.assertEqual(
            doctor.regression_guard_state([], "NO-MEMORY-IN-CONTEXT", "ok"), "inconclusive"
        )

    def test_an_unfinished_or_failed_reply_is_unanswered(self) -> None:
        self.assertEqual(doctor.regression_guard_state([], "<memory>cut", "ok"), "unanswered")
        self.assertEqual(doctor.regression_guard_state([], "", "ok"), "unanswered")
        self.assertEqual(
            doctor.regression_guard_state([], "NO-MEMORY-IN-CONTEXT", "error"), "unanswered"
        )


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
        self.assertEqual(HARNESS_VERSION, "0.1.4")


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


def _git_init(root: Path) -> None:
    """Initialize a throwaway git repo at `root` and commit everything under it."""
    for args in (
        ("init", "--initial-branch", "main"),
        ("config", "user.email", "eval@example.com"),
        ("config", "user.name", "Eval"),
        ("add", "."),
        ("commit", "-m", "fixture"),
    ):
        subprocess.run(
            ["git", *args], cwd=root, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


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
            examples={
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
        self.assertEqual(case.key, "beta:examples:1")

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
        # `validate_repo.eval_files` now discovers `examples/evals.json` only; the
        # per-file offset remains the loader's contract when it is given more.
        original = cases.validate_repo.eval_files
        cases.validate_repo.eval_files = lambda directory: [
            directory / "examples" / "evals.json",
            directory / "evals" / "evals.json",
        ]
        try:
            loaded = self._load()
        finally:
            cases.validate_repo.eval_files = original
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

    def test_repo_behavioral_files_all_live_in_examples_without_id_offsets(self) -> None:
        """Canary: one eval file per skill, so the second-file id offset never applies."""
        loaded = cases.load_behavioral_cases()
        cm = [c for c in loaded if c.skill == "community-management"]
        self.assertEqual([c.eval_id for c in cm], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(c.file_rel.endswith("/examples/evals.json") for c in loaded))
        self.assertTrue(all(c.eval_id < cases.EVAL_ID_FILE_OFFSET for c in loaded))
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

    def test_expect_question_defaults_to_false_and_is_read_when_present(self) -> None:
        self._routing(
            "alpha",
            '{"intent":"x","expected_skill":"alpha"}\n'
            '{"intent":"y","expected_skill":null,"expect_question":true}\n',
        )
        loaded = cases.load_routing_cases(self.root / "skills")
        self.assertFalse(loaded[0].expect_question)
        self.assertTrue(loaded[1].expect_question)

    def test_expect_question_must_be_a_boolean(self) -> None:
        self._routing("alpha", '{"intent":"x","expected_skill":null,"expect_question":"yes"}\n')
        with self.assertRaises(cases.CaseLoadError):
            cases.load_routing_cases(self.root / "skills")

    def test_repo_routing_files_name_only_real_skills(self) -> None:
        """Canary: the repaired corpus has one file per skill and no phantom targets."""
        loaded = cases.load_routing_cases()
        known = set(cases.skill_names())
        self.assertEqual(len(loaded), 200)
        self.assertEqual(len({c.skill_file for c in loaded}), len(known))
        self.assertEqual([c for c in loaded if c.phantom_expected], [])
        self.assertEqual([name for c in loaded for name in c.phantom_ambiguous], [])
        self.assertEqual([c for c in loaded if c.soft or c.must_not_route], [])
        for case in loaded:
            if case.expected_skill is not None:
                self.assertIn(case.expected_skill, known, case.intent)
            for name in case.ambiguous_with:
                self.assertIn(name, known, case.intent)

    def test_repo_routing_files_cover_own_skill_and_a_null_each(self) -> None:
        """Canary: every file keeps at least two positives and one unroutable intent."""
        loaded = cases.load_routing_cases()
        for skill in sorted({c.skill_file for c in loaded}):
            rows = [c for c in loaded if c.skill_file == skill]
            self.assertGreaterEqual(
                len([c for c in rows if c.expected_skill == skill]), 2, skill
            )
            self.assertGreaterEqual(
                len([c for c in rows if c.expected_skill is None]), 1, skill
            )


class CacheKeyTest(unittest.TestCase):
    EXECUTOR = {
        "claude_code_version": "2.1.248",
        "mode": "with_skill",
        "model": "sonnet",
        "system_prompt": "minimal",
        "skill_body": "# Briefing",
        "tools": "Read,Glob,Grep",
        "prompt": "Give me this morning's briefing.",
        "repeat": 1,
    }
    GRADER = {
        "claude_code_version": "2.1.248",
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

    def test_a_new_cli_build_invalidates_executor_and_grader_entries(self) -> None:
        """The CLI is the executor, so its version is part of the question asked."""
        self.assertNotEqual(
            cache.executor_key(**self.EXECUTOR),
            cache.executor_key(**dict(self.EXECUTOR, claude_code_version="2.1.249")),
        )
        self.assertNotEqual(
            cache.grader_key(**self.GRADER),
            cache.grader_key(**dict(self.GRADER, claude_code_version="2.1.249")),
        )
        self.assertIn(
            "2.1.248", cache.key_material(**self.EXECUTOR, kind="executor")
        )


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
        self.early_stops: list[bool] = []

    def argv(self, *args: str) -> list[str]:
        return ["claude", *args]

    def run(
        self, req: claude_cli.ClaudeRequest, *, early_stop_on_skill: bool = False
    ) -> claude_cli.ClaudeResult:
        self.requests.append(req)
        self.early_stops.append(early_stop_on_skill)
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
            "context_leak_ok": True,
            "identity_leak": False,
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

    def test_a_recorded_context_leak_is_refused(self) -> None:
        self._write_doctor(claude_code_version="2.1.250", context_leak_ok=False)
        payload, problem = run_evals.load_doctor(self._fake_claude("2.1.250"))
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("context", problem)

    def test_a_doctor_json_predating_the_context_probe_is_refused(self) -> None:
        (self.ws / "doctor.json").write_text(
            json.dumps({"strategy": "project-sources", "claude_code_version": "2.1.250"}),
            encoding="utf-8",
        )
        payload, problem = run_evals.load_doctor(self._fake_claude("2.1.250"))
        self.assertIsNone(payload)
        assert problem is not None
        self.assertIn("re-run `doctor`", problem)

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

    def test_routing_without_a_selection_exits_two(self) -> None:
        self.assertEqual(self._main_quietly(["routing", "--model", "sonnet"]), 2)

    def test_run_without_a_selection_exits_two(self) -> None:
        self.assertEqual(self._main_quietly(["run", "--model", "sonnet"]), 2)

    def test_discover_load_mode_is_not_implemented(self) -> None:
        self.assertEqual(
            self._main_quietly(["run", "--all", "--load-mode", "discover", "--model", "sonnet"]),
            2,
        )


class ReportDependencyFreeTest(unittest.TestCase):
    """`check_baseline` is imported by `tools/validate_repo.py` (T8), so
    `tools.evalrunner.report` must not import anything that imports
    `tools.validate_repo` back (executor.py -> cases.py -> `from tools import
    validate_repo`), or that import becomes a circular-import ImportError the
    moment the validator actually does the import. Checked in a fresh
    interpreter since an already-imported module would hide the cycle.
    """

    def test_importing_report_never_pulls_in_validate_repo(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import tools.evalrunner.report, sys; "
                "assert 'tools.validate_repo' not in sys.modules, sys.modules.keys()",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validate_repo_can_still_import_check_baseline_afterwards(self) -> None:
        # The actual T8 hook shape: validate_repo imports report.check_baseline.
        # This must not raise a partially-initialized-module ImportError.
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import tools.validate_repo\n"
                "from tools.evalrunner.report import check_baseline\n"
                "assert callable(check_baseline)\n",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class GraderUngradedShapeTest(unittest.TestCase):
    """`_empty_grading`'s summary must not read as a 0% pass rate (Task 4 addendum)."""

    def test_unusable_output_yields_a_null_pass_rate_and_ungraded_summary_status(self) -> None:
        run_dir = Path(tempfile.mkdtemp()) / "run-1"
        (run_dir / "outputs").mkdir(parents=True)
        (run_dir / "outputs" / "response.md").write_text("Some response.", encoding="utf-8")
        runner = FakeClaudeRunner([_grader_result(None, text="no json here")])
        grading = grader.grade_run(runner, run_dir, _behavioral_case(), _run_args())
        self.assertIsNone(grading["summary"]["pass_rate"])
        self.assertEqual(grading["summary"]["status"], "ungraded")
        self.assertEqual(grading["summary"]["total"], len(_behavioral_case().assertions))


class ClassifyAssertionTest(unittest.TestCase):
    def test_pass_pass_is_non_discriminating(self) -> None:
        self.assertEqual(analysis.classify_assertion(1.0, 1.0, 1), analysis.CLASS_NON_DISCRIMINATING)

    def test_pass_fail_is_discriminating(self) -> None:
        self.assertEqual(analysis.classify_assertion(1.0, 0.0, 1), analysis.CLASS_DISCRIMINATING)

    def test_fail_pass_is_harmful(self) -> None:
        self.assertEqual(analysis.classify_assertion(0.0, 1.0, 1), analysis.CLASS_HARMFUL)

    def test_fail_fail_is_broken(self) -> None:
        self.assertEqual(analysis.classify_assertion(0.0, 0.0, 1), analysis.CLASS_BROKEN)

    def test_mixed_with_rate_is_flaky_when_repeats_exceed_one(self) -> None:
        self.assertEqual(analysis.classify_assertion(0.5, 1.0, 2), analysis.CLASS_FLAKY)

    def test_mixed_without_rate_is_flaky_when_repeats_exceed_one(self) -> None:
        self.assertEqual(analysis.classify_assertion(1.0, 2 / 3, 3), analysis.CLASS_FLAKY)

    def test_a_mixed_rate_is_not_flaky_when_repeats_is_one(self) -> None:
        # Can't happen from real data (repeats=1 never produces a fractional rate),
        # but the gate is on `repeats`, not on whether the rate happens to be mixed.
        self.assertEqual(analysis.classify_assertion(0.5, 0.5, 1), analysis.CLASS_NON_DISCRIMINATING)

    def test_missing_data_on_either_side_is_ungraded(self) -> None:
        self.assertEqual(analysis.classify_assertion(None, 1.0, 1), analysis.CLASS_UNGRADED)
        self.assertEqual(analysis.classify_assertion(1.0, None, 1), analysis.CLASS_UNGRADED)


def _write_timing(run_dir: Path, *, tokens: float = 100, time_s: float = 1.0, cost: float = 0.02, status: str = "ok") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "timing.json",
        {
            "total_tokens": tokens,
            "duration_ms": int(time_s * 1000),
            "total_duration_seconds": time_s,
            "total_cost_usd": cost,
            "model": "claude-sonnet-5",
            "model_alias": "sonnet",
            "status": status,
        },
    )


def _write_grading(
    run_dir: Path,
    assertions: list[str],
    passed: list[bool],
    *,
    grader_cost: float = 0.01,
    suggestions: list[dict] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    expectations = [
        {"text": a, "passed": p, "evidence": f"evidence for {a} ({p})"} for a, p in zip(assertions, passed)
    ]
    _write_json(
        run_dir / "grading.json",
        {
            "expectations": expectations,
            "summary": {
                "passed": sum(passed),
                "failed": len(assertions) - sum(passed),
                "total": len(assertions),
                "pass_rate": round(sum(passed) / len(assertions), 4),
            },
            "eval_feedback": {"suggestions": suggestions or [], "overall": "ok"},
            "status": grader.STATUS_OK,
            "grader_model": "sonnet",
            "grader_status": "ok",
            "grader_cost_usd": grader_cost,
            "harness_version": HARNESS_VERSION,
        },
    )


def _write_ungraded(run_dir: Path, assertions: list[str], *, grader_cost: float = 0.005) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "grading.json",
        {
            "expectations": [],
            "summary": {"passed": 0, "failed": 0, "total": len(assertions), "pass_rate": None, "status": "ungraded"},
            "status": grader.STATUS_GRADER_ERROR,
            "note": "grader output did not match the assertions",
            "grader_model": "sonnet",
            "grader_status": "error",
            "grader_cost_usd": grader_cost,
            "harness_version": HARNESS_VERSION,
        },
    )


def _write_eval_metadata(eval_dir: Path, *, eval_id: int, key: str, assertions: list[str]) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        eval_dir / "eval_metadata.json",
        {
            "eval_id": eval_id,
            "eval_name": key,
            "prompt": "Do the thing.",
            "assertions": assertions,
            "key": key,
            "file": "skills/briefing/examples/evals.json",
        },
    )


class AggregateRunTest(unittest.TestCase):
    """`aggregate_run` over a hand-built run directory; every stat is hand-computed."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.tmp.name) / "runs" / "r1"
        _write_json(self.run_root / "run.json", {"run_id": "r1", "repeats": 2})

        # eval-1: one non-discriminating and one discriminating assertion.
        eval1 = self.run_root / "briefing" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["A1", "A2"])
        _write_timing(eval1 / "with_skill" / "run-1", cost=0.02)
        _write_grading(eval1 / "with_skill" / "run-1", ["A1", "A2"], [True, True])
        _write_timing(eval1 / "without_skill" / "run-1", cost=0.02)
        _write_grading(eval1 / "without_skill" / "run-1", ["A1", "A2"], [True, False])

        # eval-2: one harmful and one broken assertion; the broken one carries a suggestion.
        eval2 = self.run_root / "briefing" / "eval-2"
        _write_eval_metadata(eval2, eval_id=2, key="briefing:examples:2", assertions=["B1", "B2"])
        _write_timing(eval2 / "with_skill" / "run-1", cost=0.02)
        _write_grading(
            eval2 / "with_skill" / "run-1", ["B1", "B2"], [False, False],
            suggestions=[{"assertion": "B2", "reason": "assertion is structurally unsatisfiable"}],
        )
        _write_timing(eval2 / "without_skill" / "run-1", cost=0.02)
        _write_grading(eval2 / "without_skill" / "run-1", ["B1", "B2"], [True, False])

        # eval-3: repeats disagree on with_skill -> flaky.
        eval3 = self.run_root / "briefing" / "eval-3"
        _write_eval_metadata(eval3, eval_id=3, key="briefing:examples:3", assertions=["C1"])
        _write_timing(eval3 / "with_skill" / "run-1", cost=0.02)
        _write_grading(eval3 / "with_skill" / "run-1", ["C1"], [True])
        _write_timing(eval3 / "with_skill" / "run-2", cost=0.02)
        _write_grading(eval3 / "with_skill" / "run-2", ["C1"], [False])
        _write_timing(eval3 / "without_skill" / "run-1", cost=0.02)
        _write_grading(eval3 / "without_skill" / "run-1", ["C1"], [True])
        _write_timing(eval3 / "without_skill" / "run-2", cost=0.02)
        _write_grading(eval3 / "without_skill" / "run-2", ["C1"], [True])

        # eval-4: with_skill is ungraded (never scored as 0%); without_skill's executor timed out
        # but still produced a gradeable response.
        eval4 = self.run_root / "briefing" / "eval-4"
        _write_eval_metadata(eval4, eval_id=4, key="briefing:examples:4", assertions=["D1"])
        _write_timing(eval4 / "with_skill" / "run-1", cost=0.02)
        _write_ungraded(eval4 / "with_skill" / "run-1", ["D1"])
        _write_timing(eval4 / "without_skill" / "run-1", cost=0.02, status="timeout")
        _write_grading(eval4 / "without_skill" / "run-1", ["D1"], [True])

        self.results = analysis.aggregate_run(self.run_root)
        self.skill = self.results["skills"]["briefing"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_top_level_fields(self) -> None:
        self.assertEqual(self.results["run_id"], "r1")
        self.assertEqual(self.results["harness_version"], HARNESS_VERSION)
        self.assertEqual(self.results["repeats"], 2)

    def test_rows_carry_the_documented_schema(self) -> None:
        row = next(r for r in self.results["rows"] if r["key"] == "briefing:examples:1" and r["assertion_idx"] == 1)
        self.assertEqual(row["skill"], "briefing")
        self.assertEqual(row["eval_id"], 1)
        self.assertEqual(row["assertion"], "A2")
        self.assertEqual(row["config"]["with_skill"], {"passed_runs": 1, "total_runs": 1, "p": 1.0})
        self.assertEqual(row["config"]["without_skill"], {"passed_runs": 0, "total_runs": 1, "p": 0.0})
        self.assertEqual(row["cls"], analysis.CLASS_DISCRIMINATING)

    def test_ungraded_assertion_is_never_scored_as_a_fail(self) -> None:
        row = next(r for r in self.results["rows"] if r["key"] == "briefing:examples:4")
        self.assertEqual(row["config"]["with_skill"], {"passed_runs": 0, "total_runs": 0, "p": None})
        self.assertIsNone(row["cls"], "an all-ungraded config must not be classified as a fail")

    def test_case_and_assertion_counts(self) -> None:
        self.assertEqual(self.skill["cases"], 4)
        self.assertEqual(self.skill["assertions"], 6)

    def test_class_counts(self) -> None:
        self.assertEqual(
            self.skill["classes"],
            {"discriminating": 1, "non_discriminating": 1, "broken": 1, "harmful": 1, "flaky": 1},
        )

    def test_labeled_bucket_contents(self) -> None:
        self.assertEqual(self.skill["non_discriminating"], ["examples:1/2 A1"])
        self.assertEqual(self.skill["broken"], ["examples:2/2 B2"])
        self.assertEqual(self.skill["harmful"], ["examples:2/2 B1"])

    def test_ungraded_count_and_executor_issues(self) -> None:
        self.assertEqual(self.skill["ungraded"], 1)
        self.assertEqual(self.skill["executor_issues"], {"timeout": 1})

    def test_ungraded_keys_names_the_case_that_went_ungraded(self) -> None:
        # eval-4 is the only case with a non-ok grading in this fixture; its
        # key is what `compare()` later matches a label's case ref against.
        self.assertEqual(self.skill["ungraded_keys"], ["briefing:examples:4"])

    def test_structurally_unsatisfiable_pulls_the_grader_suggestion_for_the_broken_assertion(self) -> None:
        entries = self.results["structurally_unsatisfiable"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["skill"], "briefing")
        self.assertEqual(entries[0]["assertion"], "B2")
        self.assertEqual(entries[0]["reason"], "assertion is structurally unsatisfiable")

    def test_per_skill_stats_match_hand_computed_calculate_stats(self) -> None:
        # with_skill case pass rates: eval-1=1.0, eval-2=0.0, eval-3=mean(1.0, 0.0)=0.5;
        # eval-4 contributes nothing (all-ungraded).
        expected_with = analysis.calculate_stats([1.0, 0.0, 0.5])
        # without_skill: eval-1=0.5, eval-2=0.5, eval-3=mean(1.0, 1.0)=1.0, eval-4=1.0.
        expected_without = analysis.calculate_stats([0.5, 0.5, 1.0, 1.0])
        self.assertEqual(self.skill["configs"]["with_skill"]["pass_rate"], expected_with)
        self.assertEqual(self.skill["configs"]["without_skill"]["pass_rate"], expected_without)
        self.assertEqual(self.skill["delta"], round(expected_with["mean"] - expected_without["mean"], 4))
        self.assertEqual(self.skill["delta"], -0.25)

    def test_config_cost_totals_are_positive_and_include_grader_cost(self) -> None:
        # 4 with_skill executor calls (eval-3 has two repeats) + 4 grader calls.
        self.assertGreater(self.skill["configs"]["with_skill"]["cost_usd_total"], 0.0)
        self.assertGreater(self.skill["configs"]["without_skill"]["cost_usd_total"], 0.0)


class MissingGradingUngradedKeysTest(unittest.TestCase):
    """A `grading.json` missing entirely (harness crashed before grading) is not
    counted in `ungraded` (unchanged from before this fix round), but its case
    still lands in `ungraded_keys` — `compare()` must not treat its vanished
    labels as a fix any more than it does for a `grader_error` grading.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.tmp.name) / "runs" / "r1"
        _write_json(self.run_root / "run.json", {"run_id": "r1", "repeats": 1})
        eval1 = self.run_root / "briefing" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["A1"])
        _write_timing(eval1 / "with_skill" / "run-1")  # grading.json deliberately absent
        _write_timing(eval1 / "without_skill" / "run-1")
        _write_grading(eval1 / "without_skill" / "run-1", ["A1"], [True])
        self.skill = analysis.aggregate_run(self.run_root)["skills"]["briefing"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ungraded_count_is_unchanged(self) -> None:
        self.assertEqual(self.skill["ungraded"], 0)

    def test_ungraded_keys_still_names_the_case(self) -> None:
        self.assertEqual(self.skill["ungraded_keys"], ["briefing:examples:1"])


class AllUngradedConfigTest(unittest.TestCase):
    """A config with zero graded cases must report `pass_rate.mean: null`, never a
    fabricated 0.0 — `calculate_stats([])` returns a 0.0 mean, so `_finalize_skill`
    has to special-case the empty-list config rather than feed it straight through.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.tmp.name) / "runs" / "r1"
        _write_json(self.run_root / "run.json", {"run_id": "r1", "repeats": 1})
        eval1 = self.run_root / "briefing" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["A1"])
        _write_timing(eval1 / "with_skill" / "run-1")
        _write_ungraded(eval1 / "with_skill" / "run-1", ["A1"])
        _write_timing(eval1 / "without_skill" / "run-1")
        _write_grading(eval1 / "without_skill" / "run-1", ["A1"], [True])
        self.results = analysis.aggregate_run(self.run_root)
        self.skill = self.results["skills"]["briefing"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_all_ungraded_config_pass_rate_is_null_not_zero(self) -> None:
        self.assertIsNone(self.skill["configs"]["with_skill"]["pass_rate"]["mean"])
        self.assertIsNone(self.skill["configs"]["with_skill"]["pass_rate"]["stddev"])

    def test_delta_is_null_when_either_side_has_no_pass_rate(self) -> None:
        self.assertIsNone(self.skill["delta"])

    def test_report_pct_renders_n_a_not_0_percent(self) -> None:
        text = report.render_run_report(self.results, {"run_id": "r1"})
        self.assertIn("| n/a |", text)
        self.assertNotIn("| 0% |", text)

    def test_baseline_stores_a_null_pass_rate_not_zero(self) -> None:
        run_results = {"run_id": "r1", "skills": self.results["skills"]}
        run_meta = {"run_id": "r1"}
        merged = report.merge_baseline(None, run_results, run_meta, root=Path(self.tmp.name))
        self.assertIsNone(merged["skills"]["briefing"]["with_skill"]["pass_rate"])

    def test_report_scorecard_flags_the_ungraded_count_loudly(self) -> None:
        # A bare "ungraded" word reads as a minor caveat; a run that silently
        # dropped assertions from its denominator needs the count spelled out.
        text = report.render_run_report(self.results, {"run_id": "r1"})
        self.assertIn("1 UNGRADED (excluded from denominator)", text)


class CompareTest(unittest.TestCase):
    """`compare`'s regression signal is the with_skill pass rate, `b` minus `a`
    (a two-sided drop the old with-minus-without delta could hide), itemized
    flips come only from names present on both sides, and non_discriminating/
    flaky list diffs surface as non-failing `signal_lost`/`signal_gained`.
    """

    @staticmethod
    def _skill(
        *,
        with_rate: float | None,
        assertions: int,
        broken: list[str] | None = None,
        harmful: list[str] | None = None,
        non_discriminating: list[str] | None = None,
        flaky: list[str] | None = None,
    ) -> dict:
        entry: dict = {
            "assertions": assertions,
            "broken": broken or [],
            "harmful": harmful or [],
            "non_discriminating": non_discriminating or [],
            "flaky": flaky or [],
        }
        if with_rate is not None:
            entry["configs"] = {"with_skill": {"pass_rate": {"mean": with_rate}}}
        return entry

    def test_a_regression_is_an_assertion_that_moved_into_the_fail_set(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 X"])}}
        result = analysis.compare(a, b)
        self.assertEqual(result["regressions"], 1)
        self.assertEqual(result["gains"], 0)
        self.assertEqual(
            result["flips"], [{"skill": "briefing", "assertion": "examples:1/1 X", "direction": "regression"}]
        )

    def test_a_gain_is_an_assertion_that_left_the_fail_set(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 X"])}}
        b = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        result = analysis.compare(a, b)
        self.assertEqual(result["gains"], 1)
        self.assertEqual(result["regressions"], 0)

    def test_a_two_sided_drop_is_a_regression_even_though_the_old_delta_would_hide_it(self) -> None:
        # Both configs would drop together in a real run (the with-minus-without
        # gap stays flat), which is exactly the case the old with-minus-without
        # delta metric could not see.
        a = {"skills": {"briefing": self._skill(with_rate=0.90, assertions=20)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.50, assertions=20)}}
        result = analysis.compare(a, b)
        self.assertEqual(result["skills"][0]["with_pass_rate_delta"], -0.4)
        self.assertTrue(result["skills"][0]["regression"])
        self.assertFalse(result["skills"][0]["noise"])
        self.assertEqual(result["regressions"], 1)

    def test_a_sub_one_assertion_drop_is_flagged_as_noise_not_a_regression(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.50, assertions=20)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.48, assertions=20)}}
        result = analysis.compare(a, b)
        self.assertTrue(result["skills"][0]["noise"])
        self.assertFalse(result["skills"][0]["regression"])
        self.assertEqual(result["regressions"], 0)

    def test_a_full_assertion_drop_is_not_noise(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.50, assertions=10)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.30, assertions=10)}}
        result = analysis.compare(a, b)
        self.assertFalse(result["skills"][0]["noise"])
        self.assertTrue(result["skills"][0]["regression"])

    def test_a_rise_is_never_a_regression(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.30, assertions=10)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.90, assertions=10)}}
        result = analysis.compare(a, b)
        self.assertFalse(result["skills"][0]["regression"])
        self.assertEqual(result["regressions"], 0)

    def test_missing_pass_rate_data_on_either_side_is_not_a_regression(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=None, assertions=10)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.1, assertions=10)}}
        result = analysis.compare(a, b)
        self.assertIsNone(result["skills"][0]["with_pass_rate_delta"])
        self.assertFalse(result["skills"][0]["regression"])
        self.assertEqual(result["regressions"], 0)

    def test_a_skill_present_on_only_one_side_is_not_itemized_as_a_flip(self) -> None:
        # Not-yet-baselined (only in b) and dropped-from-this-run (only in a)
        # skills must not read as every one of their findings flipping.
        a = {
            "skills": {
                "briefing": self._skill(with_rate=0.9, assertions=10),
                "gamma": self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 Z"]),
            }
        }
        b = {
            "skills": {
                "briefing": self._skill(with_rate=0.9, assertions=10),
                "delta-skill": self._skill(with_rate=0.1, assertions=10, broken=["examples:1/1 Y"]),
            }
        }
        result = analysis.compare(a, b)
        self.assertEqual(result["flips"], [])
        self.assertEqual(result["regressions"], 0)
        self.assertEqual(result["gains"], 0)
        self.assertEqual(result["no_baseline"], ["delta-skill"])
        self.assertEqual(result["not_in_run"], ["gamma"])
        self.assertEqual([s["skill"] for s in result["skills"]], ["briefing"])

    def test_signal_lost_is_a_non_discriminating_or_flaky_list_diff_and_never_a_regression(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        b = {
            "skills": {
                "briefing": self._skill(
                    with_rate=0.9, assertions=10, non_discriminating=["examples:1/2 Y"]
                )
            }
        }
        result = analysis.compare(a, b)
        self.assertEqual(result["signal_lost"], [{"skill": "briefing", "assertion": "examples:1/2 Y"}])
        self.assertEqual(result["signal_gained"], [])
        self.assertEqual(result["regressions"], 0)

    def test_signal_gained_is_reported_when_a_soft_label_disappears(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, flaky=["examples:1/1 Z"])}}
        b = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        result = analysis.compare(a, b)
        self.assertEqual(result["signal_gained"], [{"skill": "briefing", "assertion": "examples:1/1 Z"}])

    def test_an_assertion_that_became_ungraded_is_no_signal_not_a_gain(self) -> None:
        # `broken` in `a`, absent from `b`'s list only because `b`'s grading
        # errored — not because the skill got fixed. A plain set diff would
        # read the disappearance as a gain; it must land in `no_signal` instead.
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 X"])}}
        b = dict(self._skill(with_rate=0.9, assertions=10), ungraded=1)
        result = analysis.compare(a, {"skills": {"briefing": b}})
        self.assertEqual(result["flips"], [])
        self.assertEqual(result["gains"], 0)
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:1/1 X"}])
        self.assertTrue(result["skills"][0]["no_signal"])

    def test_an_assertion_that_became_ungraded_is_no_signal_not_a_regression(self) -> None:
        # Same trap in the other direction: a newly-ungraded `b` must not read
        # as `a`'s clean assertion having broken.
        a_skill = self._skill(with_rate=0.9, assertions=10)
        b = dict(self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 X"]), ungraded=1)
        result = analysis.compare({"skills": {"briefing": a_skill}}, {"skills": {"briefing": b}})
        self.assertEqual(result["flips"], [])
        self.assertEqual(result["regressions"], 0)
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:1/1 X"}])

    def test_ungraded_on_the_a_side_alone_still_suppresses_the_diff(self) -> None:
        a = dict(self._skill(with_rate=0.9, assertions=10, non_discriminating=["examples:1/2 Y"]), ungraded=2)
        b = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        result = analysis.compare({"skills": {"briefing": a}}, b)
        self.assertEqual(result["signal_gained"], [])
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:1/2 Y"}])

    def test_no_ungraded_on_either_side_is_unaffected(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10)}}
        b = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:1/1 X"])}}
        result = analysis.compare(a, b)
        self.assertEqual(result["no_signal"], [])
        self.assertFalse(result["skills"][0]["no_signal"])
        self.assertEqual(result["regressions"], 1)

    # --- Fix round 1: per-case suppression, not whole-skill (reviewer's repro) ---

    def test_an_unrelated_ungraded_case_does_not_suppress_a_genuine_flip(self) -> None:
        # Reviewer's reproduction: a genuine broken flip in case 5, plus an
        # unrelated case (3) that went ungraded on the `b` side. Only case 3's
        # own label may be suppressed; case 5's flip must still count.
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:3/1 X"])}}
        b = dict(
            self._skill(with_rate=0.9, assertions=10, broken=["examples:5/1 Y"]),
            ungraded=1,
            ungraded_keys=["briefing:examples:3"],
        )
        result = analysis.compare(a, {"skills": {"briefing": b}})
        self.assertEqual(
            result["flips"], [{"skill": "briefing", "assertion": "examples:5/1 Y", "direction": "regression"}]
        )
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:3/1 X"}])
        self.assertEqual(result["regressions"], 1)
        self.assertEqual(result["gains"], 0)

    def test_the_ungraded_cases_own_gain_is_still_suppressed_with_known_keys(self) -> None:
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:3/1 X"])}}
        b = dict(
            self._skill(with_rate=0.9, assertions=10),
            ungraded=1,
            ungraded_keys=["briefing:examples:3"],
        )
        result = analysis.compare(a, {"skills": {"briefing": b}})
        self.assertEqual(result["flips"], [])
        self.assertEqual(result["gains"], 0)
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:3/1 X"}])

    def test_missing_ungraded_keys_falls_back_to_whole_skill_suppression(self) -> None:
        # A pre-fix results.json/baseline entry recorded only the count, not
        # which case it belongs to. Guessing would risk exactly the false
        # gain this whole mechanism exists to prevent, so both labels — the
        # genuinely unrelated one included — fall back to `no_signal`.
        a = {"skills": {"briefing": self._skill(with_rate=0.9, assertions=10, broken=["examples:3/1 X"])}}
        b = dict(self._skill(with_rate=0.9, assertions=10, broken=["examples:5/1 Y"]), ungraded=1)
        result = analysis.compare(a, {"skills": {"briefing": b}})
        self.assertEqual(result["flips"], [])
        self.assertEqual(result["regressions"], 0)
        self.assertEqual(
            sorted(item["assertion"] for item in result["no_signal"]),
            ["examples:3/1 X", "examples:5/1 Y"],
        )

    def test_an_empty_ungraded_keys_list_is_known_not_missing(self) -> None:
        # `ungraded_keys: []` on the side with `ungraded == 0` is the normal
        # new-schema shape, not an "unknown" marker — it must not force the
        # whole-skill fallback for the other, genuinely-ungraded side.
        a = dict(self._skill(with_rate=0.9, assertions=10, broken=["examples:3/1 X"]), ungraded=0, ungraded_keys=[])
        b = dict(
            self._skill(with_rate=0.9, assertions=10, broken=["examples:5/1 Y"]),
            ungraded=1,
            ungraded_keys=["briefing:examples:3"],
        )
        result = analysis.compare({"skills": {"briefing": a}}, {"skills": {"briefing": b}})
        self.assertEqual(
            result["flips"], [{"skill": "briefing", "assertion": "examples:5/1 Y", "direction": "regression"}]
        )
        self.assertEqual(result["no_signal"], [{"skill": "briefing", "assertion": "examples:3/1 X"}])

    def test_skill_filter_restricts_the_comparison(self) -> None:
        a = {
            "skills": {
                "briefing": self._skill(with_rate=0.9, assertions=10),
                "other": self._skill(with_rate=0.9, assertions=10),
            }
        }
        b = {
            "skills": {
                "briefing": self._skill(with_rate=0.9, assertions=10, broken=["x"]),
                "other": self._skill(with_rate=0.9, assertions=10, broken=["y"]),
            }
        }
        result = analysis.compare(a, b, skills=["briefing"])
        self.assertEqual([s["skill"] for s in result["skills"]], ["briefing"])
        self.assertEqual(result["regressions"], 1)


class CompareCLITest(unittest.TestCase):
    """`compare --fail-on-regression` is a real exit-code contract, not just a dict."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self._saved = run_evals.workspace.WORKSPACE
        self._saved_root = run_evals.workspace.ROOT
        run_evals.workspace.WORKSPACE = self.ws
        # ROOT too: `compare --a baseline` resolves `evals/baseline.json` against
        # it, and an unpatched ROOT reads the repository's committed baseline
        # instead of this fixture's empty one.
        run_evals.workspace.ROOT = self.ws

        for run_id, passed in (("runA", [True, False]), ("runB", [False, False])):
            run_root = self.ws / "runs" / run_id
            _write_json(run_root / "run.json", {"run_id": run_id, "repeats": 1})
            eval1 = run_root / "briefing" / "eval-1"
            _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["X1"])
            _write_timing(eval1 / "with_skill" / "run-1")
            _write_grading(eval1 / "with_skill" / "run-1", ["X1"], [passed[0]])
            _write_timing(eval1 / "without_skill" / "run-1")
            _write_grading(eval1 / "without_skill" / "run-1", ["X1"], [passed[1]])

    def tearDown(self) -> None:
        run_evals.workspace.WORKSPACE = self._saved
        run_evals.workspace.ROOT = self._saved_root
        self.tmp.cleanup()

    def _main_quietly(self, argv: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return run_evals.main(argv)

    def test_compare_without_the_flag_exits_zero(self) -> None:
        self.assertEqual(self._main_quietly(["compare", "--a", "runA", "--b", "runB"]), 0)

    def test_compare_with_a_regression_and_the_flag_exits_one(self) -> None:
        self.assertEqual(
            self._main_quietly(["compare", "--a", "runA", "--b", "runB", "--fail-on-regression"]), 1
        )

    def test_unknown_run_id_is_a_clean_error_not_a_crash(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(["compare", "--a", "runA", "--b", "no-such-run"])
        self.assertEqual(code, 2)

    def test_baseline_token_without_a_committed_baseline_is_a_clean_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(["compare", "--a", "baseline", "--b", "runA"])
        self.assertEqual(code, 2)


class RenderReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.tmp.name) / "runs" / "r1"
        _write_json(self.run_root / "run.json", {"run_id": "r1", "repeats": 1})
        eval1 = self.run_root / "briefing" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["A1", "A2"])
        _write_timing(eval1 / "with_skill" / "run-1")
        _write_grading(eval1 / "with_skill" / "run-1", ["A1", "A2"], [True, True])
        _write_timing(eval1 / "without_skill" / "run-1")
        _write_grading(eval1 / "without_skill" / "run-1", ["A1", "A2"], [True, False])

        eval2 = self.run_root / "owner-dream-cycle" / "eval-1"
        _write_eval_metadata(eval2, eval_id=1, key="owner-dream-cycle:examples:1", assertions=["E1"])
        _write_timing(eval2 / "with_skill" / "run-1")
        _write_grading(eval2 / "with_skill" / "run-1", ["E1"], [True])
        _write_timing(eval2 / "without_skill" / "run-1")
        _write_grading(eval2 / "without_skill" / "run-1", ["E1"], [True])

        self.results = analysis.aggregate_run(self.run_root)
        self.run_meta = {
            "run_id": "r1",
            "executor_model": {"alias": "sonnet", "resolved": "claude-sonnet-5"},
            "grader_model": "opus",
            "claude_code_version": "2.1.250",
            "harness_version": HARNESS_VERSION,
            "commit": "abc1234",
            "dirty": False,
            "started_at": "2026-08-27T12:00:00+00:00",
            "isolation": {"strategy": "project-sources"},
            "cost_usd_total": 0.5,
            "spend_usd_total": 0.5,
        }
        self.text = report.render_run_report(self.results, self.run_meta)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_header_carries_evaluator_model_harness_version_commit_and_date(self) -> None:
        self.assertIn("sonnet", self.text)
        self.assertIn("claude-sonnet-5", self.text)
        self.assertIn("opus", self.text)
        self.assertIn(HARNESS_VERSION, self.text)
        self.assertIn("abc1234", self.text)
        self.assertIn("2026-08-27T12:00:00+00:00", self.text)

    def test_a_clean_run_reports_no_confound(self) -> None:
        self.assertNotIn("Confound", self.text)

    def test_an_identity_leak_is_surfaced_as_a_confound(self) -> None:
        meta = dict(self.run_meta)
        meta["isolation"] = {"strategy": "project-sources", "identity_leak": True}
        meta["confounds"] = ["cli-identity-block"]
        text = report.render_run_report(self.results, meta)
        self.assertIn(
            "- Confound: the CLI injects the operator identity and current date into every "
            "config (identity_leak=true)",
            text,
        )

    def test_scorecard_has_one_row_per_skill(self) -> None:
        self.assertIn("| briefing |", self.text)
        self.assertIn("| owner-dream-cycle |", self.text)

    def test_non_discriminating_finding_is_listed_for_briefing(self) -> None:
        self.assertIn("examples:1/2 A1", self.text)

    def test_evidence_snippet_is_attached_to_a_listed_finding(self) -> None:
        self.assertIn("evidence for A1 (True)", self.text)

    def test_the_text_only_proxy_is_stated_as_an_audit_signal(self) -> None:
        """Without this paragraph a reader books `non_discriminating` as a runner bug."""
        self.assertIn("## How to read these numbers", self.text)
        self.assertIn("The harness is text-only", self.text)
        self.assertIn("no mutation", self.text)
        self.assertIn("not a runner bug", self.text)

    def test_zero_discriminating_skills_are_named(self) -> None:
        # owner-dream-cycle's only assertion passes in both configs.
        self.assertIn("## Skills with zero discriminating assertions", self.text)
        self.assertIn("- **owner-dream-cycle** — 1 assertion(s)", self.text)
        # briefing has A2 pass/fail, so it is not blind.
        self.assertNotIn("- **briefing**", self.text)

    def test_zero_discriminating_helper_skips_skills_with_no_assertions(self) -> None:
        results = {"skills": {"ghost": {"assertions": 0, "classes": {"discriminating": 0}}}}
        self.assertEqual(report.zero_discriminating(results), [])

    def test_a_run_with_signal_everywhere_says_so(self) -> None:
        text = report.render_run_report(
            {"skills": {"briefing": self.results["skills"]["briefing"]}, "rows": []},
            self.run_meta,
        )
        self.assertIn("every skill has at least one discriminating assertion", text)

    def test_structurally_unsatisfiable_renders_as_a_table(self) -> None:
        results = dict(self.results)
        results["structurally_unsatisfiable"] = [
            {
                "skill": "briefing",
                "key": "briefing:examples:1",
                "eval_id": 1,
                "assertion": "Calendar queried | authoritatively",
                "reason": "no connector is reachable\nfrom the harness",
            }
        ]
        text = report.render_run_report(results, self.run_meta)
        self.assertIn("| Skill | Case | Assertion | Why it cannot be satisfied |", text)
        self.assertIn(
            "| briefing | briefing:examples:1 (eval-1) | Calendar queried \\| authoritatively "
            "| no connector is reachable from the harness |",
            text,
        )

    def test_an_empty_unsatisfiable_section_is_still_present(self) -> None:
        self.assertIn("## Structurally unsatisfiable assertions", self.text)
        self.assertIn("- none flagged by the grader", self.text)


class BaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root, "briefing",
            examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
        )
        self.full_skill_stats = {
            "cases": 4,
            "assertions": 16,
            "configs": {
                "with_skill": {"pass_rate": {"mean": 0.81}, "tokens": {"mean": 2400}, "cost_usd_total": 0.06},
                "without_skill": {"pass_rate": {"mean": 0.56}, "tokens": {"mean": 1100}, "cost_usd_total": 0.03},
            },
            "delta": 0.25,
            "classes": {"discriminating": 5, "non_discriminating": 9, "broken": 2, "harmful": 0, "flaky": 0},
            "non_discriminating": ["examples:1/4 No mutation"],
            "broken": [],
            "harmful": [],
            "ungraded": 0,
        }
        self.run_results = {"run_id": "r1", "skills": {"briefing": self.full_skill_stats}}
        self.run_meta = {
            "run_id": "r1",
            "commit": "abc1234",
            "dirty": False,
            "claude_code_version": "2.1.250",
            "executor_model": {"alias": "sonnet", "resolved": "claude-sonnet-5"},
            "grader_model": "opus",
            "load_mode": "forced",
            "system_prompt_mode": "minimal",
            "repeats": 1,
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_condensed_entry_matches_the_design_baseline_schema(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        entry = merged["skills"]["briefing"]
        self.assertEqual(entry["run_id"], "r1")
        self.assertEqual(entry["cases"], 4)
        self.assertEqual(entry["assertions"], 16)
        self.assertEqual(entry["with_skill"], {"pass_rate": 0.81, "tokens_mean": 2400, "cost_usd": 0.06})
        self.assertEqual(entry["without_skill"], {"pass_rate": 0.56, "tokens_mean": 1100, "cost_usd": 0.03})
        self.assertEqual(entry["delta"], 0.25)
        self.assertEqual(entry["non_discriminating"], ["examples:1/4 No mutation"])

    def test_sha_fields_equal_hashlib_over_the_fixture_files(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        entry = merged["skills"]["briefing"]
        expected_skill_sha = hashlib.sha256(
            (self.root / "skills" / "briefing" / "SKILL.md").read_bytes()
        ).hexdigest()
        expected_evals_sha = hashlib.sha256(
            (self.root / "skills" / "briefing" / "examples" / "evals.json").read_bytes()
        ).hexdigest()
        self.assertEqual(entry["skill_sha256"], expected_skill_sha)
        self.assertEqual(entry["evals_sha256"], {"examples/evals.json": expected_evals_sha})

    def test_merge_only_touches_skills_present_in_the_run(self) -> None:
        existing = {
            "skills": {
                "briefing": {"stale": True},
                "owner-dream-cycle": {"cases": 9, "delta": 0.9},
            }
        }
        merged = report.merge_baseline(existing, self.run_results, self.run_meta, root=self.root)
        self.assertEqual(merged["skills"]["owner-dream-cycle"], {"cases": 9, "delta": 0.9})
        self.assertNotEqual(merged["skills"]["briefing"], {"stale": True})

    def test_skills_subset_narrows_a_multi_skill_run_further(self) -> None:
        run_results = dict(self.run_results)
        run_results["skills"] = dict(self.run_results["skills"], other={"delta": 0.1})
        merged = report.merge_baseline(None, run_results, self.run_meta, ["briefing"], root=self.root)
        self.assertIn("briefing", merged["skills"])
        self.assertNotIn("other", merged["skills"])

    def test_evaluator_block_is_populated_from_run_meta(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        self.assertEqual(merged["evaluator"]["executor_model"], "claude-sonnet-5")
        self.assertEqual(merged["evaluator"]["grader_model"], "opus")
        # The run's commit is the entry's provenance; the top-level `commit` is
        # the tree the merge happened against (task 25 item 6).
        self.assertEqual(merged["skills"]["briefing"]["source_commit"], "abc1234")

    def test_routing_is_carried_over_when_not_supplied(self) -> None:
        existing = {"skills": {}, "routing": {"mode": "native"}}
        merged = report.merge_baseline(existing, self.run_results, self.run_meta, root=self.root)
        self.assertEqual(merged["routing"], {"mode": "native"})

    def test_write_then_load_round_trips(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        path = report.write_baseline(merged, root=self.root)
        self.assertTrue(path.is_file())
        self.assertEqual(report.load_baseline(root=self.root), merged)

    def test_missing_baseline_loads_as_none(self) -> None:
        self.assertIsNone(report.load_baseline(root=self.root))


class CheckBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root, "briefing",
            examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
        )
        _write_skill_tree(
            self.root, "fact-check",
            examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
        )
        self.clean_entry = {
            "skill_sha256": report.skill_sha256("briefing", self.root),
            "evals_sha256": report.evals_sha256("briefing", self.root),
            "classes": {"discriminating": 3, "non_discriminating": 1, "broken": 0, "harmful": 0, "flaky": 0},
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_fresh_baseline_for_every_skill_on_disk_is_clean(self) -> None:
        baseline = {
            "skills": {
                "briefing": self.clean_entry,
                "fact-check": {
                    "skill_sha256": report.skill_sha256("fact-check", self.root),
                    "evals_sha256": report.evals_sha256("fact-check", self.root),
                    "classes": {"discriminating": 2, "non_discriminating": 0, "broken": 0, "harmful": 0, "flaky": 0},
                },
            }
        }
        self.assertEqual(report.check_baseline(baseline, self.root), [])

    def test_stale_skill_sha_is_reported(self) -> None:
        entry = dict(self.clean_entry, skill_sha256="0" * 64)
        problems = report.check_baseline({"skills": {"briefing": entry}}, self.root)
        self.assertTrue(any("briefing" in p and "skill_sha256" in p for p in problems))

    def test_stale_evals_sha_is_reported(self) -> None:
        entry = dict(self.clean_entry, evals_sha256={"examples/evals.json": "0" * 64})
        problems = report.check_baseline({"skills": {"briefing": entry}}, self.root)
        self.assertTrue(any("briefing" in p and "evals_sha256" in p for p in problems))

    def test_zero_discriminating_assertions_is_reported(self) -> None:
        entry = dict(self.clean_entry, classes={"discriminating": 0, "non_discriminating": 4, "broken": 0, "harmful": 0, "flaky": 0})
        problems = report.check_baseline({"skills": {"briefing": entry}}, self.root)
        self.assertTrue(any("briefing" in p and "discriminating" in p for p in problems))

    def test_a_skill_on_disk_with_no_baseline_entry_is_reported(self) -> None:
        problems = report.check_baseline({"skills": {"briefing": self.clean_entry}}, self.root)
        self.assertTrue(any("fact-check" in p and "no baseline entry" in p for p in problems))

    def test_a_baseline_entry_for_a_missing_skill_directory_is_reported(self) -> None:
        baseline = {"skills": {"briefing": self.clean_entry, "ghost-skill": dict(self.clean_entry)}}
        problems = report.check_baseline(baseline, self.root)
        self.assertTrue(any("ghost-skill" in p and "no skills/ghost-skill directory" in p for p in problems))


class BaselineCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._saved_ws = run_evals.workspace.WORKSPACE
        self._saved_root = run_evals.workspace.ROOT
        run_evals.workspace.WORKSPACE = self.root / "evals" / "workspaces"
        run_evals.workspace.ROOT = self.root
        _write_skill_tree(
            self.root, "briefing",
            examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
        )
        run_root = run_evals.workspace.WORKSPACE / "runs" / "r1"
        _write_json(run_root / "run.json", {"run_id": "r1", "repeats": 1, "commit": "abc1234", "dirty": False})
        eval1 = run_root / "briefing" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="briefing:examples:1", assertions=["a", "b"])
        _write_timing(eval1 / "with_skill" / "run-1")
        _write_grading(eval1 / "with_skill" / "run-1", ["a", "b"], [True, True])
        _write_timing(eval1 / "without_skill" / "run-1")
        _write_grading(eval1 / "without_skill" / "run-1", ["a", "b"], [True, False])

    def tearDown(self) -> None:
        run_evals.workspace.WORKSPACE = self._saved_ws
        run_evals.workspace.ROOT = self._saved_root
        self.tmp.cleanup()

    def _main_quietly(self, argv: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return run_evals.main(argv)

    def test_check_with_no_committed_baseline_is_a_clean_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(["baseline", "check"])
        self.assertEqual(code, 2)

    def test_update_then_check_round_trips(self) -> None:
        self.assertEqual(self._main_quietly(["baseline", "update", "--from", "r1"]), 0)
        path = run_evals.workspace.ROOT / "evals" / "baseline.json"
        self.assertTrue(path.is_file())
        self.assertEqual(self._main_quietly(["baseline", "check"]), 0)

    def test_require_clean_refuses_a_dirty_run(self) -> None:
        run_json_path = run_evals.workspace.WORKSPACE / "runs" / "r1" / "run.json"
        payload = json.loads(run_json_path.read_text(encoding="utf-8"))
        payload["dirty"] = True
        run_json_path.write_text(json.dumps(payload), encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(["baseline", "update", "--from", "r1", "--require-clean"])
        self.assertEqual(code, 2)

    def test_a_fully_graded_run_is_not_refused(self) -> None:
        # This fixture's run has zero ungraded assertions; the new refusal
        # check must not misfire on the ordinary, healthy path.
        self.assertEqual(self._main_quietly(["baseline", "update", "--from", "r1"]), 0)


def _write_response(run_dir: Path, text: str = "A graded response.") -> None:
    outputs = Path(run_dir) / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / "response.md").write_text(text, encoding="utf-8")


class UngradedHarnessTest(unittest.TestCase):
    """Task 13x fixture: run `r1` has one clean case, one `grader_error` case,
    and one case whose `with_skill` grading.json is missing entirely (the
    harness-crashed-before-grading shape) — the near-miss batch 1c found: a
    grader_error silently dropped from the printed denominator, `grade --run`
    a no-op on it by default, and `--regrade` never reaching `results.json`
    (which `baseline update` reads).
    """

    ASSERTIONS = {1: ["A1", "A2"], 2: ["B1", "B2"], 3: ["C1", "C2"]}

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._saved_ws = run_evals.workspace.WORKSPACE
        self._saved_root = run_evals.workspace.ROOT
        run_evals.workspace.WORKSPACE = self.root / "evals" / "workspaces"
        run_evals.workspace.ROOT = self.root
        _write_skill_tree(
            self.root, "alpha",
            examples={"evals": [{"id": i, "prompt": "p", "assertions": a} for i, a in self.ASSERTIONS.items()]},
        )

        script = FakeClaudeScript(self.root, 'echo "9.9.9 (Claude Code)"\n')
        self.claude_bin = str(script.path)
        _write_json(
            run_evals.workspace.WORKSPACE / "doctor.json",
            {
                "strategy": "project-sources",
                "claude_code_version": "9.9.9",
                "structured_output_field": "structured_output",
                "checked_at": "2026-08-28T00:00:00+00:00",
                "context_leak_ok": True,
            },
        )

        self.run_root = run_evals.workspace.WORKSPACE / "runs" / "r1"
        _write_json(self.run_root / "run.json", {"run_id": "r1", "repeats": 1, "commit": "abc1234", "dirty": False})

        eval1 = self.run_root / "alpha" / "eval-1"
        _write_eval_metadata(eval1, eval_id=1, key="alpha:examples:1", assertions=self.ASSERTIONS[1])
        _write_timing(eval1 / "with_skill" / "run-1")
        _write_response(eval1 / "with_skill" / "run-1")
        _write_grading(eval1 / "with_skill" / "run-1", self.ASSERTIONS[1], [True, True])
        _write_timing(eval1 / "without_skill" / "run-1")
        _write_response(eval1 / "without_skill" / "run-1")
        _write_grading(eval1 / "without_skill" / "run-1", self.ASSERTIONS[1], [True, False])

        eval2 = self.run_root / "alpha" / "eval-2"
        _write_eval_metadata(eval2, eval_id=2, key="alpha:examples:2", assertions=self.ASSERTIONS[2])
        _write_timing(eval2 / "with_skill" / "run-1")
        _write_response(eval2 / "with_skill" / "run-1")
        _write_ungraded(eval2 / "with_skill" / "run-1", self.ASSERTIONS[2])
        _write_timing(eval2 / "without_skill" / "run-1")
        _write_response(eval2 / "without_skill" / "run-1")
        _write_grading(eval2 / "without_skill" / "run-1", self.ASSERTIONS[2], [True, True])

        eval3 = self.run_root / "alpha" / "eval-3"
        _write_eval_metadata(eval3, eval_id=3, key="alpha:examples:3", assertions=self.ASSERTIONS[3])
        _write_timing(eval3 / "with_skill" / "run-1")
        _write_response(eval3 / "with_skill" / "run-1")  # grading.json deliberately absent
        _write_timing(eval3 / "without_skill" / "run-1")
        _write_response(eval3 / "without_skill" / "run-1")
        _write_grading(eval3 / "without_skill" / "run-1", self.ASSERTIONS[3], [True, True])

    def tearDown(self) -> None:
        run_evals.workspace.WORKSPACE = self._saved_ws
        run_evals.workspace.ROOT = self._saved_root
        self.tmp.cleanup()

    def _patch_runner(self, fake: "FakeClaudeRunner") -> None:
        run_evals.SubprocessClaudeRunner = lambda claude_bin: fake

    def _grading(self, *parts: str) -> dict:
        path = self.run_root.joinpath(*parts) / "grading.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_default_grade_regrades_only_missing_or_non_ok_gradings(self) -> None:
        fake = FakeClaudeRunner(
            [
                _grader_result(_grading_payload(self.ASSERTIONS[2], [True, False])),
                _grader_result(_grading_payload(self.ASSERTIONS[3], [True, True])),
            ]
        )
        self._patch_runner(fake)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = run_evals.main(["--claude-bin", self.claude_bin, "grade", "--run", "r1", "--no-cache"])
        self.assertEqual(code, 0)

        # Exactly the two broken run-dirs were regraded — the already-ok
        # eval-1 pair never called the (scripted, order-sensitive) runner.
        self.assertEqual(len(fake.requests), 2)

        case1_with = self._grading("alpha", "eval-1", "with_skill", "run-1")
        self.assertEqual([e["passed"] for e in case1_with["expectations"]], [True, True])

        case2_with = self._grading("alpha", "eval-2", "with_skill", "run-1")
        self.assertEqual(case2_with["status"], grader.STATUS_OK)
        self.assertEqual([e["passed"] for e in case2_with["expectations"]], [True, False])

        case3_with = self._grading("alpha", "eval-3", "with_skill", "run-1")
        self.assertEqual(case3_with["status"], grader.STATUS_OK)
        self.assertEqual([e["passed"] for e in case3_with["expectations"]], [True, True])

        # `results.json`/`report.md` are rewritten from the freshly-graded
        # data, not left stale from before the regrade.
        results = json.loads((self.run_root / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["skills"]["alpha"]["ungraded"], 0)
        self.assertTrue((self.run_root / "report.md").is_file())

    def test_regrade_flag_regrades_every_run_dir_including_ok_ones(self) -> None:
        fake = FakeClaudeRunner(
            [
                _grader_result(_grading_payload(self.ASSERTIONS[1], [True, True])),
                _grader_result(_grading_payload(self.ASSERTIONS[1], [False, False])),
                _grader_result(_grading_payload(self.ASSERTIONS[2], [True, False])),
                _grader_result(_grading_payload(self.ASSERTIONS[2], [True, True])),
                _grader_result(_grading_payload(self.ASSERTIONS[3], [True, True])),
                _grader_result(_grading_payload(self.ASSERTIONS[3], [True, True])),
            ]
        )
        self._patch_runner(fake)
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(
                ["--claude-bin", self.claude_bin, "grade", "--run", "r1", "--regrade", "--no-cache"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(len(fake.requests), 6)
        # The previously-clean case1/without_skill grading was overwritten too.
        case1_without = self._grading("alpha", "eval-1", "without_skill", "run-1")
        self.assertEqual([e["passed"] for e in case1_without["expectations"]], [False, False])

    def test_baseline_update_refuses_a_run_with_ungraded_assertions(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(["baseline", "update", "--from", "r1"])
        self.assertEqual(code, 2)
        message = stderr.getvalue()
        self.assertIn("alpha", message)
        self.assertIn("ungraded", message.lower())
        self.assertFalse((run_evals.workspace.ROOT / "evals" / "baseline.json").is_file())

    def test_baseline_update_allow_ungraded_merges_with_the_count(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(["baseline", "update", "--from", "r1", "--allow-ungraded"])
        self.assertEqual(code, 0)
        baseline = json.loads((run_evals.workspace.ROOT / "evals" / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["skills"]["alpha"]["ungraded"], 1)


class RunSummaryUngradedTest(unittest.TestCase):
    """`cmd_run`'s own printed summary line and `--fail-on-ungraded` exit code.

    A scripted `grader_error` on case 2's `with_skill` grading must show up
    inline in the per-config summary line (not just silently shrink the
    denominator), and `--fail-on-ungraded` must turn that into a distinct
    non-zero exit code without misfiring on a fully-graded run.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._saved = {
            "workspace.WORKSPACE": workspace.WORKSPACE,
            "workspace.ROOT": workspace.ROOT,
            "cases.ROOT": cases.ROOT,
            "cases.SKILLS": cases.SKILLS,
            "executor.ROOT": executor.ROOT,
            "run_evals.SubprocessClaudeRunner": run_evals.SubprocessClaudeRunner,
        }
        run_evals.workspace.WORKSPACE = self.root / "evals" / "workspaces"
        run_evals.workspace.ROOT = self.root
        cases.ROOT = self.root
        cases.SKILLS = self.root / "skills"
        executor.ROOT = self.root

        _write_skill_tree(
            self.root, "alpha",
            examples={
                "evals": [
                    {"id": 1, "prompt": "Case one.", "assertions": ["A1", "A2"]},
                    {"id": 2, "prompt": "Case two.", "assertions": ["B1", "B2"]},
                ]
            },
        )

        script = FakeClaudeScript(self.root, 'echo "9.9.9 (Claude Code)"\n')
        self.claude_bin = str(script.path)
        _write_json(
            run_evals.workspace.WORKSPACE / "doctor.json",
            {
                "strategy": "project-sources",
                "claude_code_version": "9.9.9",
                "structured_output_field": "structured_output",
                "checked_at": "2026-08-28T00:00:00+00:00",
                "context_leak_ok": True,
            },
        )

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            module_name, attr = name.split(".")
            setattr(
                {"workspace": workspace, "cases": cases, "executor": executor, "run_evals": run_evals}[module_name],
                attr,
                value,
            )
        self.tmp.cleanup()

    def _patch_runner(self, fake: "FakeClaudeRunner") -> None:
        run_evals.SubprocessClaudeRunner = lambda claude_bin: fake

    def _scripted(self, *, case2_grader_error: bool) -> list:
        # Job order: case1/with, case1/without, case2/with, case2/without;
        # each job is one executor call followed by one grader call.
        scripted = [
            _ok_result("Response 1 with", cost=0.01),
            _grader_result(_grading_payload(["A1", "A2"], [True, True]), cost=0.002),
            _ok_result("Response 1 without", cost=0.01),
            _grader_result(_grading_payload(["A1", "A2"], [False, True]), cost=0.002),
            _ok_result("Response 2 with", cost=0.01),
        ]
        if case2_grader_error:
            scripted.append(_grader_result(None, text="I refuse.", cost=0.001))
        else:
            scripted.append(_grader_result(_grading_payload(["B1", "B2"], [True, True]), cost=0.002))
        scripted += [
            _ok_result("Response 2 without", cost=0.01),
            _grader_result(_grading_payload(["B1", "B2"], [True, True]), cost=0.002),
        ]
        return scripted

    def _run(self, extra_args: list, *, case2_grader_error: bool = True) -> tuple:
        fake = FakeClaudeRunner(self._scripted(case2_grader_error=case2_grader_error))
        self._patch_runner(fake)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = run_evals.main(
                [
                    "--claude-bin", self.claude_bin,
                    "run", "--skill", "alpha", "--model", "sonnet", "--grader-model", "sonnet",
                    "--workers", "1", "--no-cache",
                    *extra_args,
                ]
            )
        return code, stream.getvalue()

    def test_summary_line_carries_ungraded_inline_and_exits_zero_by_default(self) -> None:
        code, out = self._run(["--label", "ge1"])
        self.assertEqual(code, 0)
        # with_skill: case1 graded (2/2), case2 ungraded (2 assertions) — the
        # exclusion must be spelled out inline, not just a smaller denominator.
        self.assertIn("2/2 graded", out)
        self.assertIn("2 UNGRADED (excluded from denominator)", out)

    def test_fail_on_ungraded_exits_with_the_distinct_code(self) -> None:
        code, _ = self._run(["--label", "ge2", "--fail-on-ungraded"])
        self.assertEqual(code, run_evals.EXIT_UNGRADED)
        self.assertNotEqual(run_evals.EXIT_UNGRADED, 1)  # distinct from --fail-on-regression's exit 1

    def test_fail_on_ungraded_does_not_misfire_on_a_fully_graded_run(self) -> None:
        code, out = self._run(["--label", "ge3", "--fail-on-ungraded"], case2_grader_error=False)
        self.assertEqual(code, 0)
        self.assertNotIn("UNGRADED", out)


class EndToEndRunTest(unittest.TestCase):
    """`run --all` through `baseline update` over a temp-repo fixture with FakeClaudeRunner.

    Exercises the whole pipeline `validate_repo` will eventually gate on: real
    skill-creator run-directory layout, `results.json`/`report.md` written by
    `run`, a `baseline update`, and `validate_repo` still passing with
    `evals/baseline.json` present. Also covers `run`'s dry-run and cache-hit
    paths, since both relocate the workspace the same way this test does.
    """

    SCHEMA = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas/skill-evals.schema.json").read_text(encoding="utf-8")
    )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._build_repo()

        self._saved = {
            "workspace.WORKSPACE": workspace.WORKSPACE,
            "workspace.ROOT": workspace.ROOT,
            "cases.ROOT": cases.ROOT,
            "cases.SKILLS": cases.SKILLS,
            "executor.ROOT": executor.ROOT,
            "validate_repo.ROOT": validate_repo.ROOT,
            "validate_repo.SKILLS": validate_repo.SKILLS,
            "validate_repo.EVAL_SCHEMA": validate_repo.EVAL_SCHEMA,
            "run_evals.SubprocessClaudeRunner": run_evals.SubprocessClaudeRunner,
        }
        run_evals.workspace.WORKSPACE = self.root / "evals" / "workspaces"
        run_evals.workspace.ROOT = self.root
        cases.ROOT = self.root
        cases.SKILLS = self.root / "skills"
        executor.ROOT = self.root
        validate_repo.ROOT = self.root
        validate_repo.SKILLS = self.root / "skills"
        validate_repo.EVAL_SCHEMA = self.root / "schemas" / "skill-evals.schema.json"

        script = FakeClaudeScript(self.root, 'echo "9.9.9 (Claude Code)"\n')
        self.claude_bin = str(script.path)
        _write_json(
            run_evals.workspace.WORKSPACE / "doctor.json",
            {
                "strategy": "project-sources",
                "claude_code_version": "9.9.9",
                "structured_output_field": "structured_output",
                "checked_at": "2026-08-28T00:00:00+00:00",
                "context_leak_ok": True,
                "identity_leak": True,
                "current_date_injected": True,
                "confounds": ["cli-identity-block"],
            },
        )

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            module_name, attr = name.split(".")
            setattr({"workspace": workspace, "cases": cases, "executor": executor, "validate_repo": validate_repo, "run_evals": run_evals}[module_name], attr, value)
        self.tmp.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _skill_md(self, name: str) -> str:
        """The canonical (contract_version 2) shape the validator holds every skill to."""
        return (
            "---\n"
            f"name: {name}\n"
            f"description: Use when the caller asks for the {name} fixture verdict "
            f"or a harness regression case. Not for anything else.\n"
            "metadata:\n"
            "  spike-os:\n"
            "    version: 2.0.0\n"
            "    runtime: [openclaw, claude-code]\n"
            "---\n\n"
            f"# {name}\n\n"
            f"## Overview\nProduces the {name} fixture verdict from one request.\n\n"
            f"## When to use\n- The caller names the {name} fixture.\n\n"
            f"## When not to use\n- The caller wants something other than {name}.\n\n"
            "## Inputs\n"
            "| Input | Required | If missing |\n"
            "| --- | --- | --- |\n"
            f"| {name} request | yes | Ask for the missing request |\n\n"
            "**Dependencies:** none beyond the contract.\n\n"
            f"## Workflow\n1. Read the {name} request.\n2. Emit the verdict.\n\n"
            "## Output contract\nReport the request, the checks run, and the verdict.\n\n"
            f"## Failure conditions\nStop when the {name} request names no target.\n\n"
            "## Common mistakes\n"
            "| Mistake | Why wrong | Do instead |\n"
            "| --- | --- | --- |\n"
            "| Guessing the verdict | Fabricates a result | Ask first |\n\n"
            "## Contract\n"
            "Follows [contracts/skill-contract.md](../../contracts/skill-contract.md) v1.\n"
            "- Provenance: repo-owned\n"
        )

    def _build_repo(self) -> None:
        self._write(".gitignore", "evals/workspaces/\n.env\n*.skill\n")
        self._write("schemas/skill-evals.schema.json", json.dumps(self.SCHEMA))
        repo = Path(__file__).resolve().parents[1]
        for rel in [
            *sorted(path.relative_to(repo).as_posix() for path in repo.glob("contracts/*.yaml")),
            "adapters/vocabulary.yaml",
            "adapters/adapter.schema.json",
            *sorted(path.relative_to(repo).as_posix() for path in repo.glob("adapters/*/adapter.yaml")),
        ]:
            self._write(rel, (repo / rel).read_text(encoding="utf-8"))
        self._write(
            "contracts/skill-contract.md",
            "# Skill contract v1\n<!-- contract-version: 1 -->\n\n"
            "## D. Dependencies\nD1 explicit-only: only what the request names.\n",
        )
        self._write(
            "skills/alpha/SKILL.md", self._skill_md("alpha")
        )
        _write_json(
            self.root / "skills" / "alpha" / "examples" / "evals.json",
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": index,
                        "prompt": f"Exercise fixture scenario {index} for alpha.",
                        "assertions": [
                            "Reports the fixture boundary and outcome",
                            "Avoids private state and hidden dependencies",
                        ],
                    }
                    for index in range(1, 5)
                ],
            },
        )
        self._write(
            "catalog/approved.yaml",
            "skills:\n"
            "  - name: alpha\n"
            "    contract_version: 2\n"
            "    classification: owned\n"
            "    runtime_path: skills/alpha\n"
            "    repository_path: skills/alpha\n"
            "    status: approved\n"
            "    cohort: test\n"
            "    workshop_proposal: alpha-20260824-1234567890\n"
            "    version: 2.0.0\n",
        )
        self._write(
            "catalog/domains.yaml",
            "domains:\n"
            "  - name: test\n"
            "    released:\n"
            "      - alpha\n"
            "    next: []\n",
        )
        self._write(
            "catalog/cohorts.yaml",
            "cohorts:\n"
            "  - name: test\n"
            "    status: completed\n"
            "    skills:\n"
            "      - alpha\n",
        )
        self._write(
            "catalog/routing.yaml",
            "clusters:\n"
            "  - name: fixture\n"
            "    skills: [alpha]\n",
        )
        self._write(
            "catalog/sources.yaml",
            "sources:\n"
            "  alpha:\n"
            "    classification: owned\n"
            "    runtime_path: skills/alpha\n"
            "    repository_path: skills/alpha\n"
            "    status: approved\n"
            "    cohort: test\n"
            "    provenance: repo-owned\n"
            "    version: 2.0.0\n",
        )
        subprocess.run(
            ["git", "init", "--initial-branch", "main"], cwd=self.root, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "config", "user.email", "eval@example.com"], cwd=self.root, check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "config", "user.name", "Eval"], cwd=self.root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(
            ["git", "commit", "-m", "fixture"], cwd=self.root, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _run_validator(self) -> int:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = validate_repo.main()
        return code

    def _scripted_results(self) -> list:
        # 4 cases x 2 configs x (1 executor + 1 grader) call, in job order:
        # with_skill always passes both assertions, without_skill fails the first.
        assertions = [
            "Reports the fixture boundary and outcome",
            "Avoids private state and hidden dependencies",
        ]
        scripted = []
        for case_id in range(1, 5):
            for config, passed in (("with_skill", [True, True]), ("without_skill", [False, True])):
                scripted.append(_ok_result(f"Response for case {case_id} ({config})", cost=0.01))
                scripted.append(
                    _grader_result(_grading_payload(assertions, passed), cost=0.002)
                )
        return scripted

    def _patch_runner(self, fake: "FakeClaudeRunner") -> None:
        run_evals.SubprocessClaudeRunner = lambda claude_bin: fake

    def test_dry_run_writes_request_json_without_calling_claude(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(
                ["--claude-bin", self.claude_bin, "run", "--all", "--model", "sonnet", "--dry-run", "--label", "dry"]
            )
        self.assertEqual(code, 0)
        run_dirs = list((run_evals.workspace.WORKSPACE / "runs").glob("*-dry"))
        self.assertEqual(len(run_dirs), 1)
        request_paths = list(run_dirs[0].glob("alpha/eval-*/with_skill/run-1/request.json"))
        self.assertEqual(len(request_paths), 4)

    def test_run_json_carries_the_doctor_identity_confound(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(
                ["--claude-bin", self.claude_bin, "run", "--all", "--model", "sonnet",
                 "--dry-run", "--label", "confound"]
            )
        self.assertEqual(code, 0)
        run_dirs = list((run_evals.workspace.WORKSPACE / "runs").glob("*-confound"))
        self.assertEqual(len(run_dirs), 1)
        run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
        self.assertIs(run_json["isolation"]["identity_leak"], True)
        self.assertIs(run_json["isolation"]["context_leak_ok"], True)
        self.assertEqual(run_json["confounds"], ["cli-identity-block"])

    def test_full_run_then_baseline_update_then_validate_repo(self) -> None:
        fake = FakeClaudeRunner(self._scripted_results())
        self._patch_runner(fake)

        with contextlib.redirect_stdout(io.StringIO()):
            code = run_evals.main(
                [
                    "--claude-bin", self.claude_bin,
                    "run", "--all", "--model", "sonnet", "--grader-model", "sonnet",
                    "--workers", "1", "--label", "e2e",
                ]
            )
        self.assertEqual(code, 0)

        run_dirs = list((run_evals.workspace.WORKSPACE / "runs").glob("*-e2e"))
        self.assertEqual(len(run_dirs), 1)
        run_dir = run_dirs[0]

        grading_paths = sorted(run_dir.glob("alpha/eval-*/with_skill/run-1/grading.json"))
        self.assertEqual(len(grading_paths), 4)
        self.assertTrue((run_dir / "results.json").is_file())
        self.assertTrue((run_dir / "report.md").is_file())
        # doctor.json -> run.json -> report.md: the confound survives the whole chain.
        self.assertIn(report.CONFOUND_LINE, (run_dir / "report.md").read_text(encoding="utf-8"))

        results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["skills"]["alpha"]["cases"], 4)
        self.assertEqual(results["skills"]["alpha"]["classes"]["discriminating"], 4)

        # Cache-hit path: a second identical run must not call the (now-empty) fake again.
        empty_fake = FakeClaudeRunner([])
        self._patch_runner(empty_fake)
        with contextlib.redirect_stdout(io.StringIO()):
            code2 = run_evals.main(
                [
                    "--claude-bin", self.claude_bin,
                    "run", "--all", "--model", "sonnet", "--grader-model", "sonnet",
                    "--workers", "1", "--label", "e2e2",
                ]
            )
        self.assertEqual(code2, 0)
        self.assertEqual(empty_fake.requests, [])

        run_id = run_dir.name
        with contextlib.redirect_stdout(io.StringIO()):
            baseline_code = run_evals.main(["baseline", "update", "--from", run_id])
        self.assertEqual(baseline_code, 0)
        baseline_path = run_evals.workspace.ROOT / "evals" / "baseline.json"
        self.assertTrue(baseline_path.is_file())
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        self.assertIn("alpha", baseline["skills"])

        problems = report.check_baseline(baseline, run_evals.workspace.ROOT)
        self.assertEqual(problems, [])

        self.assertEqual(self._run_validator(), 0)


def _routing_case(
    skill_file: str = "alpha",
    *,
    line_no: int = 1,
    intent: str = "do the alpha thing",
    expected_skill: str | None = "alpha",
    ambiguous_with: list[str] | None = None,
    phantom_expected: bool = False,
    phantom_ambiguous: list[str] | None = None,
    must_not_route: str | None = None,
    soft: bool = False,
    expect_question: bool = False,
) -> cases.RoutingCase:
    return cases.RoutingCase(
        skill_file=skill_file,
        line_no=line_no,
        intent=intent,
        expected_skill=expected_skill,
        ambiguous_with=list(ambiguous_with or []),
        phantom_expected=phantom_expected,
        phantom_ambiguous=list(phantom_ambiguous or []),
        must_not_route=must_not_route,
        soft=soft,
        expect_question=expect_question,
    )


def _skill_result(skill: str, *, cost: float = 0.002) -> claude_cli.ClaudeResult:
    """A native-mode result whose first tool_use is `Skill`."""
    result = _ok_result("", cost=cost)
    result.tool_uses = [{"id": "toolu_1", "name": "Skill", "input": {"skill": skill}}]
    return result


def _classify_result(
    choice: str | None, *, alternatives: list[str] | None = None, cost: float = 0.001
) -> claude_cli.ClaudeResult:
    """A classify-mode result carrying structured output."""
    result = _ok_result("", cost=cost)
    assert result.result_event is not None
    result.result_event["structured_output"] = {
        "choice": choice,
        "alternatives": list(alternatives or []),
        "reason": "fixture",
    }
    return result


class ChosenSkillTest(unittest.TestCase):
    def test_first_skill_tool_use_wins(self) -> None:
        result = _ok_result("")
        result.tool_uses = [
            {"id": "t1", "name": "Skill", "input": {"skill": "alpha"}},
            {"id": "t2", "name": "Skill", "input": {"skill": "beta"}},
        ]
        self.assertEqual(routing.chosen_skill(result), "alpha")

    def test_plugin_prefixed_name_is_normalized(self) -> None:
        self.assertEqual(routing.chosen_skill(_skill_result("superpowers:brainstorming")), "brainstorming")

    def test_non_skill_tool_uses_are_ignored(self) -> None:
        result = _ok_result("")
        result.tool_uses = [
            {"id": "t1", "name": "Read", "input": {"file_path": "/tmp/x"}},
            {"id": "t2", "name": "Skill", "input": {"skill": "beta"}},
        ]
        self.assertEqual(routing.chosen_skill(result), "beta")

    def test_no_tool_use_is_none(self) -> None:
        self.assertIsNone(routing.chosen_skill(_ok_result("I would just answer directly.")))

    def test_classify_choice_is_read_from_structured_output(self) -> None:
        self.assertEqual(routing.chosen_skill(_classify_result("alpha")), "alpha")

    def test_classify_null_choice_is_none(self) -> None:
        self.assertIsNone(routing.chosen_skill(_classify_result(None)))

    def test_classify_none_sentinel_is_no_skill(self) -> None:
        for sentinel in ("none", "None", "null", "no skill", ""):
            self.assertIsNone(routing.chosen_skill(_classify_result(sentinel)), sentinel)

    def test_skill_tool_use_from_a_partial_message_fixture(self) -> None:
        # `native` mode passes --include-partial-messages, so the Skill tool_use
        # arrives as a stream_event/content_block_start before the assistant message.
        lines = _fixture_lines("skill_tool_use_partial.jsonl")
        text, tool_uses, result_event, events = claude_cli.parse_stream_lines(lines)
        self.assertTrue(
            any(
                (event.get("event") or {}).get("type") == "content_block_start"
                for event in events
                if event.get("type") == "stream_event"
            )
        )
        self.assertEqual([use["name"] for use in tool_uses if use["name"] == "Skill"], ["Skill"])
        result = claude_cli.ClaudeResult(
            status="ok", text=text, tool_uses=tool_uses, result_event=result_event, events=events
        )
        self.assertEqual(routing.chosen_skill(result), "fact-check")

    def test_a_skill_use_with_no_name_is_the_unnamed_sentinel(self) -> None:
        # Not None: the router did route, and reading that as "declined to route"
        # would score a broken stream as a passing negative case.
        self.assertEqual(routing.chosen_skill(_skill_result("")), routing.UNNAMED_SKILL)


class RoutingMajorityTest(unittest.TestCase):
    def test_majority_over_three_repeats(self) -> None:
        self.assertEqual(routing.majority(["alpha", "beta", "alpha"]), "alpha")

    def test_majority_can_be_none(self) -> None:
        self.assertIsNone(routing.majority([None, "alpha", None]))

    def test_tie_breaks_on_first_occurrence(self) -> None:
        self.assertEqual(routing.majority(["beta", "alpha"]), "beta")

    def test_no_repeats_is_none(self) -> None:
        self.assertIsNone(routing.majority([]))


class RoutingScoringTest(unittest.TestCase):
    def _score(self, case: cases.RoutingCase, chosen: list) -> dict:
        return routing.score_case(case, chosen)

    def test_expected_skill_chosen_is_a_pass(self) -> None:
        score = self._score(_routing_case(), ["alpha"])
        self.assertEqual(score["outcome"], "pass")
        self.assertEqual(score["chosen"], "alpha")
        self.assertEqual(score["rule"], "expected")

    def test_ambiguous_alternative_is_an_ambiguous_pass(self) -> None:
        score = self._score(_routing_case(ambiguous_with=["beta"]), ["beta"])
        self.assertEqual(score["outcome"], "ambiguous_pass")

    def test_unrelated_skill_is_a_fail(self) -> None:
        score = self._score(_routing_case(ambiguous_with=["beta"]), ["gamma"])
        self.assertEqual(score["outcome"], "fail")

    def test_no_skill_for_an_expected_case_is_a_fail(self) -> None:
        self.assertEqual(self._score(_routing_case(), [None])["outcome"], "fail")

    def test_null_expected_passes_only_when_nothing_routed(self) -> None:
        null_case = _routing_case(expected_skill=None)
        self.assertEqual(self._score(null_case, [None])["outcome"], "pass")
        self.assertEqual(self._score(null_case, ["alpha"])["outcome"], "fail")
        self.assertEqual(self._score(null_case, [None])["rule"], "null")

    def test_majority_decides_the_outcome(self) -> None:
        score = self._score(_routing_case(), ["alpha", "beta", "alpha"])
        self.assertEqual(score["outcome"], "pass")
        self.assertEqual(score["chosen_by_repeat"], ["alpha", "beta", "alpha"])

    def test_soft_phantom_passes_on_nothing_or_the_owning_skill(self) -> None:
        soft = _routing_case(
            expected_skill="ghost", ambiguous_with=[], phantom_expected=True, soft=True
        )
        self.assertEqual(self._score(soft, [None])["outcome"], "pass")
        self.assertEqual(self._score(soft, ["alpha"])["outcome"], "pass")
        self.assertEqual(self._score(soft, ["beta"])["outcome"], "fail")
        self.assertEqual(self._score(soft, [None])["rule"], "soft")
        self.assertTrue(self._score(soft, [None])["phantom"])

    def test_must_not_route_phantom_fails_only_when_the_owner_hijacks(self) -> None:
        strict = _routing_case(
            expected_skill="ghost", phantom_expected=True, must_not_route="alpha"
        )
        self.assertEqual(self._score(strict, ["alpha"])["outcome"], "fail")
        self.assertEqual(self._score(strict, ["beta"])["outcome"], "pass")
        self.assertEqual(self._score(strict, [None])["outcome"], "pass")
        self.assertEqual(self._score(strict, [None])["rule"], "must_not_route")

    def test_a_failed_repeat_does_not_vote(self) -> None:
        # A call that errored before answering says nothing about the router;
        # counting its silence as "routed to nothing" would flip the verdict.
        score = routing.score_case(
            _routing_case(), [None, "alpha", None], statuses=["error", "ok", "timeout"]
        )
        self.assertEqual(score["chosen"], "alpha")
        self.assertEqual(score["outcome"], "pass")
        self.assertEqual(score["answered"], 1)

    def test_an_answer_from_a_failed_call_still_counts(self) -> None:
        score = routing.score_case(
            _routing_case(), ["alpha", None], statuses=["budget_exceeded", "ok"]
        )
        self.assertEqual(score["chosen"], "alpha")
        self.assertEqual(score["answered"], 2)

    def test_a_case_where_every_repeat_failed_is_unanswered_not_a_pass(self) -> None:
        null_case = _routing_case(expected_skill=None)
        score = routing.score_case(null_case, [None, None], statuses=["error", "error"])
        self.assertEqual(score["answered"], 0)
        # A `null`-expected case would otherwise "pass" on the silence of two
        # failed calls; the matrix must not be applied to what was not measured.
        self.assertEqual(score["outcome"], "unanswered")
        self.assertEqual(score["rule"], "null")
        self.assertTrue(any("every repeat failed" in item for item in score["warnings"]))

        aggregate = routing.aggregate_routing([null_case], [score])
        self.assertEqual(aggregate["unanswered"], ["alpha:1"])
        self.assertEqual(aggregate["totals"]["unanswered"], 1)
        self.assertEqual(aggregate["totals"]["pass"], 0)
        self.assertIsNone(aggregate["pass_rate"])
        self.assertIn("## Unanswered", routing.render_routing_report(aggregate, {}))

    def test_statuses_are_optional(self) -> None:
        score = routing.score_case(_routing_case(), [None])
        self.assertEqual(score["answered"], 1)
        self.assertEqual(routing.aggregate_routing([_routing_case()], [score])["unanswered"], [])

    def test_expect_question_passes_only_when_the_router_asked(self) -> None:
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(
            asking, [None], replies=["Meals for the week, or the shopping list?"]
        )
        self.assertEqual(score["outcome"], "pass")
        self.assertEqual(score["rule"], "question")
        self.assertTrue(score["asked_question"])
        # Declining to route without asking is not the behaviour under test.
        silent = routing.score_case(asking, [None], replies=["No skill applies."])
        self.assertEqual(silent["outcome"], "fail")
        self.assertFalse(silent["asked_question"])

    def test_expect_question_fails_when_the_router_picked_one_side(self) -> None:
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(asking, ["meal-planner"], replies=[""])
        self.assertEqual(score["outcome"], "fail")

    def test_expect_question_accepts_a_listed_alternative_as_ambiguous(self) -> None:
        asking = _routing_case(
            expected_skill=None, ambiguous_with=["beta"], expect_question=True
        )
        score = routing.score_case(asking, ["beta"], replies=[""])
        self.assertEqual(score["outcome"], "ambiguous_pass")

    def test_expect_question_needs_a_majority_of_asking_repeats(self) -> None:
        # One repeat out of three asking is not the router's behaviour, it is noise;
        # every other rule in the matrix is decided by majority and this one is too.
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(
            asking,
            [None, None, None],
            statuses=["ok", "ok", "ok"],
            replies=["Which one?", "No skill applies.", "Nothing in the library fits."],
        )
        self.assertEqual(score["outcome"], "fail")
        self.assertFalse(score["asked_question"])

    def test_expect_question_passes_on_a_majority_of_asking_repeats(self) -> None:
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(
            asking,
            [None, None, "meal-planner"],
            statuses=["ok", "ok", "ok"],
            replies=["Which one?", "Meals or the list?", ""],
        )
        self.assertEqual(score["outcome"], "pass")
        self.assertTrue(score["asked_question"])

    def test_an_errored_repeats_reply_does_not_count_as_asking(self) -> None:
        # A call that died mid-stream can leave a partial sentence with a question
        # mark in it; counting that as "the router asked" turns a broken run into a
        # passing one.
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(
            asking,
            [None, None, None],
            statuses=["error", "ok", "ok"],
            replies=["Which one of these did you...?", "No skill applies.", "No skill applies."],
        )
        self.assertEqual(score["answered"], 2)
        self.assertFalse(score["asked_question"])
        self.assertEqual(score["outcome"], "fail")

    def test_expect_question_with_no_answer_stays_unanswered(self) -> None:
        asking = _routing_case(expected_skill=None, expect_question=True)
        score = routing.score_case(asking, [None], statuses=["error"], replies=["?"])
        self.assertEqual(score["outcome"], "unanswered")

    def test_dropped_phantom_ambiguous_entries_are_warned_about(self) -> None:
        score = self._score(
            _routing_case(ambiguous_with=["beta"], phantom_ambiguous=["ghost"]), ["beta"]
        )
        self.assertEqual(score["outcome"], "ambiguous_pass")
        self.assertEqual(len(score["warnings"]), 1)
        self.assertIn("ghost", score["warnings"][0])
        self.assertIn("alpha:1", score["warnings"][0])


class AggregateRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = [
            _routing_case("alpha", line_no=1, intent="alpha one"),
            _routing_case("alpha", line_no=2, intent="alpha two"),
            _routing_case("alpha", line_no=3, intent="alpha three", expected_skill=None),
            _routing_case(
                "beta", line_no=1, intent="beta one", expected_skill="beta",
                ambiguous_with=["alpha"],
            ),
            _routing_case(
                "beta", line_no=2, intent="beta ghost", expected_skill="ghost",
                phantom_expected=True, must_not_route="beta",
            ),
        ]
        self.chosen = {
            ("alpha", 1): ["alpha"],
            ("alpha", 2): ["gamma"],
            ("alpha", 3): ["gamma"],
            ("beta", 1): ["alpha"],
            ("beta", 2): ["beta"],
        }
        self.scores = [
            routing.score_case(case, self.chosen[(case.skill_file, case.line_no)])
            for case in self.cases
        ]

    def test_per_file_counts(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        self.assertEqual(
            agg["files"]["alpha"],
            {"cases": 3, "pass": 1, "ambiguous_pass": 0, "fail": 2, "unanswered": 0,
             "phantom": 0, "pass_rate": 0.3333, "strict_pass_rate": 0.3333},
        )
        self.assertEqual(
            agg["files"]["beta"],
            {"cases": 2, "pass": 0, "ambiguous_pass": 1, "fail": 1, "unanswered": 0,
             "phantom": 1, "pass_rate": 0.5, "strict_pass_rate": 0.0},
        )

    def test_totals_cover_every_case(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        self.assertEqual(agg["cases"], 5)
        self.assertEqual(agg["totals"]["pass"], 1)
        self.assertEqual(agg["totals"]["ambiguous_pass"], 1)
        self.assertEqual(agg["totals"]["fail"], 3)
        self.assertEqual(agg["totals"]["phantom"], 1)

    def test_strict_pass_rate_refuses_credit_for_ambiguous_answers(self) -> None:
        """Lenient counts `ambiguous_pass`; strict counts only the exact target."""
        agg = routing.aggregate_routing(self.cases, self.scores)
        # 5 scored cases: 1 pass, 1 ambiguous_pass, 3 fail.
        self.assertEqual(agg["pass_rate"], 0.4)
        self.assertEqual(agg["strict_pass_rate"], 0.2)

    def test_both_rates_are_none_when_nothing_scored(self) -> None:
        agg = routing.aggregate_routing([_routing_case()], [])
        self.assertIsNone(agg["pass_rate"])
        self.assertIsNone(agg["strict_pass_rate"])
        self.assertIsNone(agg["files"]["alpha"]["strict_pass_rate"])

    def test_the_baseline_block_carries_both_rates(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        block = routing.baseline_routing_block(agg, run_id="r1")
        self.assertEqual(block["files"]["beta"]["pass_rate"], 0.5)
        self.assertEqual(block["files"]["beta"]["strict_pass_rate"], 0.0)

    def test_the_report_shows_both_rates_per_file_and_in_total(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        rendered = routing.render_routing_report(agg, {})
        self.assertIn("| Lenient % | Strict % |", rendered)
        # beta: 1 ambiguous_pass + 1 fail -> 50% lenient, 0% strict.
        self.assertIn("| beta | 2 | 0 | 1 | 1 | 0 | 1 | 50% | 0% |", rendered)
        self.assertIn("| **total** | 5 | 1 | 1 | 3 | 0 | 1 | 40% | 20% |", rendered)
        self.assertIn(
            "Pass rate (lenient, pass + ambiguous): 40% \u00b7 strict (exact target only): 20%",
            rendered,
        )

    def test_failures_split_by_who_took_the_intent(self) -> None:
        """(a) nobody, (b) a repo skill, (c) something off the repo ballot."""
        agg = routing.aggregate_routing(self.cases, self.scores)
        split = routing.failure_split(agg, ballot=["alpha", "beta"], builtins=["debug"])
        self.assertEqual(
            [row["intent"] for row in split["hijacked_by_builtin"]],
            ["alpha two", "alpha three"],
        )
        self.assertEqual([row["intent"] for row in split["hijacked_by_repo_skill"]], ["beta ghost"])
        self.assertEqual(split["answered_no_skill"], [])
        # `gamma` is on neither the repo ballot nor the built-in baseline.
        self.assertFalse(split["hijacked_by_builtin"][0]["known_builtin"])

    def test_an_unanswered_style_failure_with_no_choice_is_bucket_a(self) -> None:
        case = _routing_case("alpha", line_no=9, intent="who does this", expected_skill="alpha")
        agg = routing.aggregate_routing([case], [routing.score_case(case, [None, None, None])])
        split = routing.failure_split(agg, ballot=["alpha"])
        self.assertEqual([row["intent"] for row in split["answered_no_skill"]], ["who does this"])

    def test_the_report_shows_the_split_and_the_native_cost_floor(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores, mode="native")
        rendered = routing.render_routing_report(
            agg,
            {"ballot": ["alpha", "beta"], "ballot_size": 2, "builtin_skill_baseline": ["debug"]},
        )
        self.assertIn("## Failure split", rendered)
        self.assertIn("**(a) Answered natively with no skill: 0**", rendered)
        self.assertIn("**(b) Hijacked by a repo skill: 1**", rendered)
        self.assertIn("**(c) Hijacked by a built-in or unnamed tool: 2**", rendered)
        self.assertIn("not in the doctor built-in baseline", rendered)
        self.assertIn("the figure above is a lower bound", rendered)
        self.assertIn("2 repo skill(s), plus the CLI's own built-ins (1 known by name", rendered)

    def test_the_report_adds_the_compare_run_as_extra_columns(self) -> None:
        """`--compare-run` renders a second mode beside the primary scorecard."""
        agg = routing.aggregate_routing(self.cases, self.scores, mode="native")
        compare = routing.aggregate_routing(self.cases, self.scores, mode="classify")
        compare["run_id"] = "rid-classify"
        rendered = routing.render_routing_report(
            agg, {}, compare=compare, compare_meta={"claude_code_version": "9.9.9"}
        )
        self.assertIn("| Lenient % | Strict % | Classify lenient % | Classify strict % |", rendered)
        self.assertIn("| beta | 2 | 0 | 1 | 1 | 0 | 1 | 50% | 0% | 50% | 0% |", rendered)
        self.assertIn(
            "| **total** | 5 | 1 | 1 | 3 | 0 | 1 | 40% | 20% | 40% | 20% |", rendered
        )
        self.assertIn("rid-classify", rendered)
        self.assertIn("9.9.9", rendered)

    def test_a_file_missing_from_the_compare_run_renders_as_not_available(self) -> None:
        """The compare run need not cover the same files; absent cells say so."""
        agg = routing.aggregate_routing(self.cases, self.scores, mode="native")
        alpha_only = [case for case in self.cases if case.skill_file == "alpha"]
        alpha_scores = [
            routing.score_case(case, self.chosen[(case.skill_file, case.line_no)])
            for case in alpha_only
        ]
        compare = routing.aggregate_routing(alpha_only, alpha_scores, mode="classify")
        rendered = routing.render_routing_report(agg, {}, compare=compare)
        self.assertIn("| beta | 2 | 0 | 1 | 1 | 0 | 1 | 50% | 0% | n/a | n/a |", rendered)

    def test_without_a_compare_run_the_scorecard_keeps_its_original_columns(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores, mode="native")
        rendered = routing.render_routing_report(agg, {})
        self.assertIn("| Lenient % | Strict % |\n", rendered)
        self.assertNotIn("lenient %", rendered.replace("Lenient %", ""))

    def test_classify_mode_makes_no_lower_bound_claim(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores, mode="classify")
        self.assertNotIn(
            "lower bound", routing.render_routing_report(agg, {"ballot": ["alpha"]})
        )

    def test_confusion_list_maps_intent_to_what_was_chosen(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        confusion = [(row["intent"], row["expected"], row["chosen"]) for row in agg["confusion"]]
        self.assertEqual(
            confusion,
            [
                ("alpha two", "alpha", "gamma"),
                ("alpha three", None, "gamma"),
                ("beta ghost", "ghost", "beta"),
            ],
        )

    def test_hijack_counts_name_the_absorbing_skill(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        self.assertEqual(agg["hijacks"], {"gamma": 2, "beta": 1})

    def test_warnings_are_collected_once_per_case(self) -> None:
        cases_with_phantom = [_routing_case("alpha", phantom_ambiguous=["ghost"])]
        scores = [routing.score_case(cases_with_phantom[0], ["alpha"])]
        agg = routing.aggregate_routing(cases_with_phantom, scores)
        self.assertEqual(len(agg["warnings"]), 1)

    def test_phantom_targets_are_listed(self) -> None:
        agg = routing.aggregate_routing(self.cases, self.scores)
        self.assertEqual(agg["phantom_targets"], ["ghost"])


class BuildRoutingProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sandbox = self.root / "sandbox"
        self.args = _run_args(repo_root=self.root, sandbox_root=self.sandbox)
        self.run_dir = self.root / "evals" / "workspaces" / "routing" / "run-1"
        _write_skill_tree(self.root, "alpha", examples={"skill_name": "alpha", "evals": []})
        _write_skill_tree(self.root, "beta")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self, **kwargs: object) -> Path:
        return routing.build_routing_project(
            self.run_dir, self.root / "skills", args=self.args, **kwargs
        )

    def test_every_skill_contributes_only_its_skill_md(self) -> None:
        proj = self._build()
        skills_dir = proj / ".claude" / "skills"
        self.assertEqual(sorted(p.name for p in skills_dir.iterdir()), ["alpha", "beta"])
        self.assertTrue((skills_dir / "alpha" / "SKILL.md").is_file())
        self.assertEqual([p.name for p in (skills_dir / "alpha").iterdir()], ["SKILL.md"])
        self.assertFalse((proj / "CLAUDE.md").exists())

    def test_project_is_built_outside_the_repository(self) -> None:
        proj = self._build()
        self.assertFalse(proj.is_relative_to(workspace.ROOT))
        self.assertTrue(proj.is_relative_to(self.sandbox))

    def test_extra_skill_is_added_under_its_directory_name(self) -> None:
        extra = self.root / "outside" / "gamma"
        extra.mkdir(parents=True)
        extra.joinpath("SKILL.md").write_text(
            "---\nname: gamma\ndescription: Outside skill.\n---\n\n# Gamma\n", encoding="utf-8"
        )
        proj = self._build(extra_skills=[extra])
        self.assertTrue((proj / ".claude" / "skills" / "gamma" / "SKILL.md").is_file())

    def test_extra_skill_without_a_skill_md_is_an_error(self) -> None:
        empty = self.root / "outside" / "delta"
        empty.mkdir(parents=True)
        with self.assertRaises(routing.RoutingError):
            self._build(extra_skills=[empty])

    def test_descriptions_from_ref_materializes_the_committed_skill_md(self) -> None:
        _git_init(self.root)
        self.root.joinpath("skills", "alpha", "SKILL.md").write_text(
            "---\nname: alpha\ndescription: The new description.\n---\n\n# Alpha\n",
            encoding="utf-8",
        )
        proj = self._build(descriptions_from="HEAD")
        text = (proj / ".claude" / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Fixture skill alpha.", text)
        self.assertNotIn("The new description.", text)

    def test_descriptions_from_an_unknown_ref_is_an_error(self) -> None:
        _git_init(self.root)
        with self.assertRaises(routing.RoutingError):
            self._build(descriptions_from="no-such-ref")

    def test_descriptions_read_back_from_the_built_project(self) -> None:
        proj = self._build()
        self.assertEqual(
            routing.project_descriptions(proj),
            [("alpha", "Fixture skill alpha."), ("beta", "Fixture skill beta.")],
        )


class NativeRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        self.proj = self.root / "sandbox" / "proj"
        self.proj.mkdir(parents=True)
        self.req = routing.native_request(
            "fact check this draft", self.proj, self.args, ["--setting-sources", "project"]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_only_the_skill_tool_is_offered(self) -> None:
        self.assertEqual(self.req.argv[self.req.argv.index("--tools") + 1], "Skill")

    def test_partial_messages_are_requested(self) -> None:
        self.assertIn("--include-partial-messages", self.req.argv)
        self.assertEqual(self.req.argv[self.req.argv.index("--output-format") + 1], "stream-json")

    def test_the_default_claude_code_system_prompt_is_kept(self) -> None:
        # The product's own router prompt is the thing under test.
        self.assertNotIn("--system-prompt", self.req.argv)
        self.assertNotIn("--append-system-prompt", self.req.argv)

    def test_budget_and_isolation_flags_are_set(self) -> None:
        self.assertEqual(self.req.argv[self.req.argv.index("--max-budget-usd") + 1], "0.15")
        for flag in ("--strict-mcp-config", "--no-session-persistence", "--setting-sources"):
            self.assertIn(flag, self.req.argv)

    def test_it_runs_in_the_routing_project(self) -> None:
        self.assertEqual(self.req.cwd, self.proj)

    def test_nesting_env_is_scrubbed(self) -> None:
        self.assertNotIn("CLAUDECODE", self.req.env)


class ClassifyRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.args = _run_args(repo_root=self.root, sandbox_root=self.root / "sandbox")
        self.descriptions = [("alpha", "Does alpha things."), ("beta", "Does beta things.")]
        self.req = routing.classify_request(
            "do an alpha", self.descriptions, self.args, ["--setting-sources", "project"]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_call_is_tool_less_and_structured(self) -> None:
        self.assertEqual(self.req.argv[self.req.argv.index("--tools") + 1], "")
        schema = json.loads(self.req.argv[self.req.argv.index("--json-schema") + 1])
        self.assertEqual(schema, routing.CLASSIFY_SCHEMA)
        self.assertEqual(sorted(schema["required"]), ["alternatives", "choice", "reason"])
        # A required property with a JSON null reads as missing to this CLI's
        # structured-output validator, so "no skill" is a sentinel string.
        self.assertEqual(schema["properties"]["choice"]["type"], "string")

    def test_every_skill_is_listed_in_the_system_prompt(self) -> None:
        prompt = self.req.argv[self.req.argv.index("--system-prompt") + 1]
        self.assertIn("alpha: Does alpha things.", prompt)
        self.assertIn("beta: Does beta things.", prompt)
        self.assertIn(routing.CLASSIFY_NONE, prompt)

    def test_classify_does_not_stream_partial_messages(self) -> None:
        self.assertNotIn("--include-partial-messages", self.req.argv)
        self.assertEqual(self.req.argv[self.req.argv.index("--output-format") + 1], "json")

    def test_cwd_defaults_outside_the_repository(self) -> None:
        self.assertTrue(self.req.cwd.is_relative_to(self.root / "sandbox"))
        self.assertFalse(self.req.cwd.is_relative_to(workspace.ROOT))


class RoutingEarlyStopTest(unittest.TestCase):
    """The native runner must return as soon as the model names a skill."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_partial_stream_stops_before_eof_and_names_the_skill(self) -> None:
        script = FakeClaudeScript(
            self.tmpdir,
            f'cat "{FIXTURES / "skill_tool_use_partial.jsonl"}"\n'
            f'{sys.executable} -c "import time; time.sleep(10)"\n'
            'echo \'{"type":"result","subtype":"success","is_error":false}\'\n',
        )
        runner = claude_cli.SubprocessClaudeRunner(str(script.path))
        req = claude_cli.ClaudeRequest(
            argv=runner.argv("-p", "fact check this draft"),
            cwd=self.tmpdir,
            env=claude_cli.scrub_env(os.environ),
            timeout_s=30.0,
        )
        started = time.monotonic()
        result = runner.run(req, early_stop_on_skill=True)
        elapsed = time.monotonic() - started

        self.assertEqual(result.status, "ok")
        self.assertLess(elapsed, 10.0)
        self.assertIsNone(result.result_event, "returned before the process reached its result event")
        self.assertEqual(routing.chosen_skill(result), "fact-check")

    def test_the_empty_partial_block_does_not_trigger_the_stop(self) -> None:
        # Stopping at `content_block_start` would kill the call before the skill
        # name arrives in the input_json_deltas, and the name is the whole answer.
        starts, completed = [], []
        for line in _fixture_lines("skill_tool_use_partial.jsonl"):
            event = json.loads(line)
            uses = claude_cli._tool_uses_in_event(event)
            if not any(use.get("name") == "Skill" for use in uses):
                continue
            (starts if event.get("type") == "stream_event" else completed).append(line)
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(completed), 1)
        self.assertFalse(claude_cli._line_has_skill_tool_use(starts[0]))
        self.assertTrue(claude_cli._line_has_skill_tool_use(completed[0]))

    def test_a_partial_block_is_superseded_by_the_complete_one(self) -> None:
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(
            _fixture_lines("skill_tool_use_partial.jsonl")
        )
        skill_uses = [use for use in tool_uses if use["name"] == "Skill"]
        self.assertEqual(len(skill_uses), 1, "the same block must not be counted twice")
        self.assertEqual(skill_uses[0]["input"]["skill"], "fact-check")


class RoutingCacheKeyTest(unittest.TestCase):
    BASE = {
        "claude_code_version": "2.1.248",
        "mode": "native",
        "model": "sonnet",
        "descriptions_sha": "abc",
        "intent": "fact check this",
        "repeat": 1,
    }

    def test_key_is_stable(self) -> None:
        self.assertEqual(
            routing.routing_cache_key(**self.BASE), routing.routing_cache_key(**self.BASE)
        )

    def test_every_input_changes_the_key(self) -> None:
        base = routing.routing_cache_key(**self.BASE)
        for field, value in (
            ("claude_code_version", "2.1.249"),
            ("mode", "classify"),
            ("model", "opus"),
            ("descriptions_sha", "def"),
            ("intent", "something else"),
            ("repeat", 2),
        ):
            changed = dict(self.BASE)
            changed[field] = value
            self.assertNotEqual(base, routing.routing_cache_key(**changed), field)

    def test_harness_version_is_part_of_the_key(self) -> None:
        self.assertIn(HARNESS_VERSION, cache.key_material(kind="routing", **self.BASE))

    def test_the_ballot_digest_tracks_the_descriptions(self) -> None:
        first = routing.descriptions_digest([("alpha", "one"), ("beta", "two")])
        self.assertEqual(first, routing.descriptions_digest([("alpha", "one"), ("beta", "two")]))
        self.assertNotEqual(first, routing.descriptions_digest([("alpha", "one"), ("beta", "three")]))


class TriggerSetTest(unittest.TestCase):
    """`should_trigger` mirrors the routing scorer: would it reward this skill answering?"""

    def test_export_is_a_bare_array_in_run_loop_shape(self) -> None:
        payload = routing.trigger_set(
            [_routing_case("alpha", line_no=1, intent="do alpha", expected_skill="alpha")],
            "alpha",
        )
        self.assertEqual(payload, [{"query": "do alpha", "should_trigger": True}])

    def test_the_three_ways_a_skill_earns_should_trigger(self) -> None:
        payload = routing.trigger_set(
            [
                # (1) owns the intent outright
                _routing_case("alpha", line_no=1, intent="do alpha", expected_skill="alpha"),
                # (2) named as an accepted alternative on another file's intent
                _routing_case(
                    "beta", line_no=1, intent="shared work",
                    expected_skill="beta", ambiguous_with=["alpha"],
                ),
                # (3) soft phantom owned by alpha: the target does not exist and
                # alpha answering is an accepted outcome
                _routing_case(
                    "alpha", line_no=2, intent="ghost work",
                    expected_skill="ghost-skill", ambiguous_with=["alpha"],
                    phantom_expected=True, soft=True,
                ),
            ],
            "alpha",
        )
        self.assertEqual([row["should_trigger"] for row in payload], [True, True, True])

    def test_intents_another_skill_owns_are_negatives(self) -> None:
        payload = routing.trigger_set(
            [
                _routing_case("alpha", line_no=1, intent="do beta", expected_skill="beta"),
                _routing_case("alpha", line_no=2, intent="chit chat", expected_skill=None),
                # A must-not-route phantom is the opposite of a soft one: alpha
                # answering is the failure the fixture is watching for.
                _routing_case(
                    "alpha", line_no=3, intent="ghost work",
                    expected_skill="ghost-skill", phantom_expected=True,
                    must_not_route="alpha", soft=False,
                ),
            ],
            "alpha",
        )
        self.assertEqual(
            payload,
            [
                {"query": "do beta", "should_trigger": False},
                {"query": "chit chat", "should_trigger": False},
                {"query": "ghost work", "should_trigger": False},
            ],
        )


class RoutingSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = [
            _routing_case("alpha", line_no=1),
            _routing_case("beta", line_no=1, expected_skill="beta"),
        ]

    def test_no_filter_keeps_everything(self) -> None:
        self.assertEqual(len(routing.select_routing_cases(self.cases)), 2)

    def test_filter_keeps_only_the_named_files(self) -> None:
        picked = routing.select_routing_cases(self.cases, skills=["beta"])
        self.assertEqual([case.skill_file for case in picked], ["beta"])

    def test_a_skill_without_routing_cases_is_an_error(self) -> None:
        with self.assertRaises(cases.CaseLoadError):
            routing.select_routing_cases(self.cases, skills=["gamma"])


class RenderRoutingReportTest(unittest.TestCase):
    def test_report_carries_the_run_facts_and_the_confusion_rows(self) -> None:
        aggregate = routing.aggregate_routing(
            [_routing_case("alpha", line_no=2, intent="do alpha")],
            [routing.score_case(_routing_case("alpha", line_no=2, intent="do alpha"), ["gamma"])],
            mode="native",
            repeats=3,
            run_id="20260827T000000-abc123-routing",
        )
        text = routing.render_routing_report(
            aggregate,
            {
                "model": {"alias": "sonnet", "resolved": "claude-sonnet-5"},
                "claude_code_version": "2.1.250",
                "harness_version": HARNESS_VERSION,
                "commit": "abc123",
                "started_at": "2026-08-27T00:00:00+00:00",
                "isolation": {"strategy": "project-sources"},
                "ballot_size": 30,
                "cost_usd_total": 0.1234,
            },
        )
        self.assertIn("# Routing report: 20260827T000000-abc123-routing", text)
        self.assertIn("claude-sonnet-5", text)
        self.assertIn("2.1.250", text)
        self.assertIn(HARNESS_VERSION, text)
        self.assertIn("abc123", text)
        self.assertIn("| alpha | 1 | 0 | 0 | 1 | 0 | 0 |", text)
        self.assertIn("do alpha", text)
        self.assertIn("gamma", text)
        self.assertNotIn("Confound", text)

    def test_the_identity_confound_reaches_the_routing_header(self) -> None:
        aggregate = routing.aggregate_routing([], [], mode="native", repeats=1, run_id="r1")
        text = routing.render_routing_report(
            aggregate,
            {
                "isolation": {"strategy": "project-sources", "identity_leak": True},
                "confounds": ["cli-identity-block"],
            },
        )
        self.assertIn(
            "- Confound: the CLI injects the operator identity and current date into every "
            "config (identity_leak=true)",
            text,
        )


class CheckBaselineRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root,
            "alpha",
            routing='// comment\n{"intent":"one","expected_skill":"alpha"}\n\n'
            '{"intent":"two","expected_skill":null}\n',
        )
        self.baseline = {
            "schema_version": 1,
            "skills": {
                "alpha": {
                    "skill_sha256": report.skill_sha256("alpha", self.root),
                    "evals_sha256": report.evals_sha256("alpha", self.root),
                    "classes": {"discriminating": 3},
                }
            },
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_absent_routing_section_is_not_a_problem(self) -> None:
        self.assertEqual(report.check_baseline(self.baseline, self.root), [])

    def test_matching_routing_section_is_clean(self) -> None:
        self.baseline["routing"] = {
            "run_id": "r1",
            "files": {"alpha": {"cases": 2, "pass": 2, "ambiguous_pass": 0, "fail": 0, "phantom": 0}},
        }
        self.assertEqual(report.check_baseline(self.baseline, self.root), [])

    def test_a_stale_case_count_is_reported(self) -> None:
        self.baseline["routing"] = {"files": {"alpha": {"cases": 5}}}
        problems = report.check_baseline(self.baseline, self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("routing case count is stale", problems[0])

    def test_a_skill_with_a_fixture_but_no_entry_is_reported(self) -> None:
        self.baseline["routing"] = {"files": {}}
        problems = report.check_baseline(self.baseline, self.root)
        self.assertEqual(problems, ["alpha: has routing-eval.jsonl but no baseline routing entry"])

    def test_an_entry_for_a_deleted_skill_is_reported(self) -> None:
        self.baseline["routing"] = {"files": {"ghost": {"cases": 1}}}
        problems = report.check_baseline(self.baseline, self.root)
        self.assertIn("ghost: baseline routing entry has no skills/ghost directory on disk", problems)

    def test_case_count_ignores_comments_and_blank_lines(self) -> None:
        self.assertEqual(
            report.routing_case_count(self.root / "skills" / "alpha" / "routing-eval.jsonl"), 2
        )
        self.assertIsNone(report.routing_case_count(self.root / "skills" / "alpha" / "nope.jsonl"))


class RoutingCLITest(unittest.TestCase):
    """`routing` end to end over a temp repo with `FakeClaudeRunner`.

    Covers both modes, the run-directory layout, scoring through the CLI, the
    cache, `report`, `baseline update --routing-from`, and `export-trigger-set`.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root,
            "alpha",
            routing=(
                "// alpha intents\n"
                '{"intent":"do the alpha thing","expected_skill":"alpha"}\n'
                '{"intent":"ghost work","expected_skill":"ghost-skill"}\n'
            ),
        )
        _write_skill_tree(
            self.root,
            "beta",
            routing='{"intent":"nothing to do here","expected_skill":null}\n',
        )

        self._saved = {
            "workspace.WORKSPACE": workspace.WORKSPACE,
            "workspace.ROOT": workspace.ROOT,
            "cases.ROOT": cases.ROOT,
            "cases.SKILLS": cases.SKILLS,
            "executor.ROOT": executor.ROOT,
            "routing.ROOT": routing.ROOT,
            "run_evals.SubprocessClaudeRunner": run_evals.SubprocessClaudeRunner,
        }
        workspace.WORKSPACE = self.root / "evals" / "workspaces"
        workspace.ROOT = self.root
        cases.ROOT = self.root
        cases.SKILLS = self.root / "skills"
        executor.ROOT = self.root
        routing.ROOT = self.root
        self.sandbox = self.root / "sandbox"
        self._saved_env = os.environ.get(executor.SANDBOX_ENV_VAR)
        os.environ[executor.SANDBOX_ENV_VAR] = str(self.sandbox)

        script = FakeClaudeScript(self.root, 'echo "9.9.9 (Claude Code)"\n')
        self.claude_bin = str(script.path)
        _write_json(
            workspace.WORKSPACE / "doctor.json",
            {
                "strategy": "project-sources",
                "claude_code_version": "9.9.9",
                "structured_output_field": "structured_output",
                "checked_at": "2026-08-28T00:00:00+00:00",
                "context_leak_ok": True,
                "identity_leak": True,
                "current_date_injected": True,
                "confounds": ["cli-identity-block"],
            },
        )

    def tearDown(self) -> None:
        modules = {
            "workspace": workspace, "cases": cases, "executor": executor,
            "routing": routing, "run_evals": run_evals,
        }
        for name, value in self._saved.items():
            module_name, attr = name.split(".")
            setattr(modules[module_name], attr, value)
        if self._saved_env is None:
            os.environ.pop(executor.SANDBOX_ENV_VAR, None)
        else:
            os.environ[executor.SANDBOX_ENV_VAR] = self._saved_env
        self.tmp.cleanup()

    def _patch_runner(self, fake: "FakeClaudeRunner") -> None:
        run_evals.SubprocessClaudeRunner = lambda claude_bin: fake

    def _main(self, argv: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = run_evals.main(["--claude-bin", self.claude_bin, *argv])
        self.stdout = out.getvalue()
        return code

    def _native_answers(self) -> list:
        # Job order is (case, repeat): alpha:2 x3, alpha:3 x3, beta:2 x3.
        return [
            _skill_result("alpha"), _skill_result("alpha"), _skill_result("beta"),
            _skill_result("alpha"), _skill_result("alpha"), _skill_result("alpha"),
            _ok_result("I can answer that directly."),
            _ok_result("I can answer that directly."),
            _ok_result("I can answer that directly."),
        ]

    def _routing_run_dir(self, label: str) -> Path:
        matches = list((workspace.WORKSPACE / "routing").glob(f"*-{label}"))
        self.assertEqual(len(matches), 1, f"expected one routing run for label {label}")
        return matches[0]

    def test_the_reply_text_reaches_the_scorer_for_expect_question_cases(self) -> None:
        # The router's own words are the only evidence that it asked rather than
        # routed, so they have to survive the trip from the CLI to score_case.
        answers = [
            _skill_result("alpha"), _skill_result("alpha"), _skill_result("alpha"),
            _skill_result("alpha"), _skill_result("alpha"), _skill_result("alpha"),
            _ok_result("Which did you mean?"),
            _ok_result("Which did you mean?"),
            _ok_result("Which did you mean?"),
        ]
        self._patch_runner(FakeClaudeRunner(answers))
        code = self._main(
            ["routing", "--all", "--model", "sonnet", "--mode", "native",
             "--repeats", "3", "--workers", "1", "--label", "reply"]
        )
        self.assertEqual(code, 0)
        results = json.loads(
            (self._routing_run_dir("reply") / "results.json").read_text(encoding="utf-8")
        )
        by_file = {score["skill_file"]: score for score in results["scores"]}
        self.assertTrue(by_file["beta"]["asked_question"])
        self.assertFalse(by_file["alpha"]["asked_question"])

    def test_the_ballot_is_persisted_beside_run_json(self) -> None:
        # Task 25 item 7: `descriptions_sha256` alone cannot be re-read; the run
        # has to carry the ballot it actually voted on.
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(
                ["routing", "--all", "--model", "sonnet", "--mode", "native",
                 "--repeats", "3", "--workers", "1", "--label", "ballot"]
            ),
            0,
        )
        run_dir = self._routing_run_dir("ballot")
        ballot = (run_dir / "descriptions.txt").read_text(encoding="utf-8")
        self.assertEqual(
            ballot.splitlines(),
            ["alpha: Fixture skill alpha.", "beta: Fixture skill beta."],
        )

    def test_the_persisted_ballot_hashes_to_the_recorded_digest(self) -> None:
        # Task 25 item 26: the file and the digest are two views of one ballot.
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(
                ["routing", "--all", "--model", "sonnet", "--mode", "native",
                 "--repeats", "3", "--workers", "1", "--label", "digest"]
            ),
            0,
        )
        run_dir = self._routing_run_dir("digest")
        material = (run_dir / "descriptions.txt").read_text(encoding="utf-8").rstrip("\n")
        run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(material.encode("utf-8")).hexdigest(),
            run_json["descriptions_sha256"],
        )

    def test_an_expect_question_case_runs_to_completion_in_native_mode(self) -> None:
        # Task 25 item 24: early-stopping on the first Skill tool_use throws away
        # the reply, which is the only evidence an `expect_question` case scores on.
        (self.root / "skills" / "beta" / "routing-eval.jsonl").write_text(
            '{"intent":"nothing to do here","expected_skill":null,"expect_question":true}\n',
            encoding="utf-8",
        )
        fake = FakeClaudeRunner(self._native_answers())
        self._patch_runner(fake)
        self.assertEqual(
            self._main(
                ["routing", "--all", "--model", "sonnet", "--mode", "native",
                 "--repeats", "3", "--workers", "1", "--label", "q"]
            ),
            0,
        )
        by_intent = {
            req.argv[req.argv.index("-p") + 1]: stop
            for req, stop in zip(fake.requests, fake.early_stops)
        }
        self.assertFalse(by_intent["nothing to do here"], "expect_question must run to completion")
        self.assertTrue(by_intent["do the alpha thing"], "ordinary native cases still early-stop")

    def test_native_run_writes_the_layout_and_scores_the_intents(self) -> None:
        fake = FakeClaudeRunner(self._native_answers())
        self._patch_runner(fake)
        code = self._main(
            ["routing", "--all", "--model", "sonnet", "--mode", "native",
             "--repeats", "3", "--workers", "1", "--label", "nat"]
        )
        self.assertEqual(code, 0)
        run_dir = self._routing_run_dir("nat")

        self.assertTrue((run_dir / "run.json").is_file())
        self.assertTrue((run_dir / "results.json").is_file())
        self.assertTrue((run_dir / "report.md").is_file())
        # doctor.json -> run.json -> report.md: the confound survives the whole chain.
        self.assertIn(report.CONFOUND_LINE, (run_dir / "report.md").read_text(encoding="utf-8"))
        self.assertTrue((run_dir / "alpha" / "intent-2" / "run-1" / "stream.jsonl").is_file())
        self.assertTrue((run_dir / "alpha" / "intent-2" / "run-3" / "chosen.json").is_file())
        self.assertTrue((run_dir / "alpha" / "intent-2" / "intent_metadata.json").is_file())
        self.assertTrue((run_dir / "beta" / "intent-1" / "run-1" / "request.json").is_file())

        results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["cases"], 3)
        self.assertEqual(
            results["totals"],
            {"pass": 2, "ambiguous_pass": 0, "fail": 1, "unanswered": 0, "phantom": 1},
        )
        self.assertEqual(results["hijacks"], {"alpha": 1})
        self.assertEqual([row["intent"] for row in results["confusion"]], ["ghost work"])
        self.assertEqual(results["mode"], "native")
        self.assertEqual(results["repeats"], 3)
        self.assertEqual(results["phantom_targets"], ["ghost-skill"])
        # Majority over repeats, not last-write-wins.
        first = [score for score in results["scores"] if score["line_no"] == 2][0]
        self.assertEqual(first["chosen_by_repeat"], ["alpha", "alpha", "beta"])
        self.assertEqual(first["chosen"], "alpha")

    def test_native_run_requests_the_early_kill_and_a_project_outside_the_repo(self) -> None:
        fake = FakeClaudeRunner(self._native_answers())
        self._patch_runner(fake)
        self.assertEqual(
            self._main(
                ["routing", "--all", "--model", "sonnet", "--repeats", "3",
                 "--workers", "1", "--label", "kill"]
            ),
            0,
        )
        self.assertEqual(fake.early_stops, [True] * 9)

        run_json = json.loads((self._routing_run_dir("kill") / "run.json").read_text(encoding="utf-8"))
        proj = Path(run_json["project_dir"])
        self.assertFalse(proj.is_relative_to(self.root / "skills"))
        self.assertTrue(proj.is_relative_to(self.sandbox))
        self.assertTrue((proj / ".claude" / "skills" / "alpha" / "SKILL.md").is_file())
        self.assertEqual(run_json["ballot_size"], 2)
        self.assertEqual(fake.requests[0].cwd, proj)

    def test_second_identical_run_is_served_from_the_cache(self) -> None:
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                        "--workers", "1", "--label", "c1"]),
            0,
        )
        empty = FakeClaudeRunner([])
        self._patch_runner(empty)
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                        "--workers", "1", "--label", "c2"]),
            0,
        )
        self.assertEqual(empty.requests, [])
        results = json.loads(
            (self._routing_run_dir("c2") / "results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(results["totals"]["pass"], 2)

    def test_classify_mode_reads_the_structured_choice(self) -> None:
        fake = FakeClaudeRunner(
            [_classify_result("alpha"), _classify_result("beta"), _classify_result(None)]
        )
        self._patch_runner(fake)
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--mode", "classify",
                        "--repeats", "1", "--workers", "1", "--label", "cls"]),
            0,
        )
        self.assertEqual(fake.early_stops, [False] * 3)
        argv = fake.requests[0].argv
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        prompt = argv[argv.index("--system-prompt") + 1]
        self.assertIn("alpha: Fixture skill alpha.", prompt)
        self.assertIn("beta: Fixture skill beta.", prompt)

        results = json.loads(
            (self._routing_run_dir("cls") / "results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            results["totals"],
            {"pass": 3, "ambiguous_pass": 0, "fail": 0, "unanswered": 0, "phantom": 1},
        )

    def test_dry_run_writes_requests_without_calling_claude(self) -> None:
        empty = FakeClaudeRunner([])
        self._patch_runner(empty)
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "2",
                        "--dry-run", "--label", "dry"]),
            0,
        )
        self.assertEqual(empty.requests, [])
        run_dir = self._routing_run_dir("dry")
        self.assertEqual(len(list(run_dir.glob("*/intent-*/run-*/request.json"))), 6)
        self.assertFalse((run_dir / "results.json").exists())

    def test_skill_filter_selects_one_file_and_an_unknown_one_exits_two(self) -> None:
        fake = FakeClaudeRunner([_skill_result("alpha"), _skill_result("alpha")])
        self._patch_runner(fake)
        self.assertEqual(
            self._main(["routing", "--skill", "alpha", "--model", "sonnet", "--repeats", "1",
                        "--workers", "1", "--label", "one"]),
            0,
        )
        results = json.loads(
            (self._routing_run_dir("one") / "results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sorted(results["files"]), ["alpha"])
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(
                ["--claude-bin", self.claude_bin, "routing", "--skill", "ghost", "--model", "sonnet"]
            )
        self.assertEqual(code, 2)

    def test_report_renders_the_routing_section_for_a_routing_run(self) -> None:
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                        "--workers", "1", "--label", "rep"]),
            0,
        )
        run_id = self._routing_run_dir("rep").name
        self.assertEqual(self._main(["report", "--run", run_id]), 0)
        self.assertIn("# Routing report:", self.stdout)
        self.assertIn("ghost work", self.stdout)

    def test_report_compare_run_adds_the_second_routing_column(self) -> None:
        self._patch_runner(FakeClaudeRunner(self._native_answers() + self._native_answers()))
        for label in ("primary", "second"):
            self.assertEqual(
                self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                            "--workers", "1", "--label", label]),
                0,
            )
        run_id = self._routing_run_dir("primary").name
        compare_id = self._routing_run_dir("second").name
        self.assertEqual(
            self._main(["report", "--run", run_id, "--compare-run", compare_id]), 0
        )
        self.assertIn("Native lenient %", self.stdout)
        self.assertIn(compare_id, self.stdout)

    def test_report_compare_run_with_an_unknown_id_exits_two(self) -> None:
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                        "--workers", "1", "--label", "solo"]),
            0,
        )
        run_id = self._routing_run_dir("solo").name
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(
                ["--claude-bin", self.claude_bin, "report", "--run", run_id,
                 "--compare-run", "no-such-run"]
            )
        self.assertEqual(code, 2)

    def test_baseline_update_fills_the_routing_block(self) -> None:
        self._patch_runner(FakeClaudeRunner(self._native_answers()))
        self.assertEqual(
            self._main(["routing", "--all", "--model", "sonnet", "--repeats", "3",
                        "--workers", "1", "--label", "base"]),
            0,
        )
        run_id = self._routing_run_dir("base").name

        # No committed baseline yet: a routing-only update has nothing to merge into.
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                run_evals.main(["baseline", "update", "--routing-from", run_id]), 2
            )

        report.write_baseline({"schema_version": 1, "skills": {}}, root=self.root)
        self.assertEqual(self._main(["baseline", "update", "--routing-from", run_id]), 0)
        baseline = json.loads(
            (self.root / "evals" / "baseline.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline["routing"]["run_id"], run_id)
        self.assertEqual(baseline["routing"]["mode"], "native")
        self.assertEqual(baseline["routing"]["repeats"], 3)
        self.assertEqual(
            baseline["routing"]["files"]["alpha"],
            {"cases": 2, "pass": 1, "ambiguous_pass": 0, "fail": 1, "unanswered": 0,
             "phantom": 1, "pass_rate": 0.5, "strict_pass_rate": 0.5},
        )
        self.assertEqual(baseline["routing"]["phantom_targets"], ["ghost-skill"])
        # The behavioral half of this fixture baseline is deliberately empty, so
        # only the routing problems are meaningful here.
        problems = [item for item in report.check_baseline(baseline, self.root) if "routing" in item]
        self.assertEqual(problems, [])

    def test_baseline_update_rejects_a_missing_routing_run(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                run_evals.main(["baseline", "update", "--routing-from", "no-such-run"]), 2
            )

    def test_baseline_update_without_any_source_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_evals.main(["baseline", "update"]), 2)

    def test_export_trigger_set_writes_skill_creator_shape(self) -> None:
        out = self.root / "exports" / "alpha-triggers.json"
        self.assertEqual(self._main(["export-trigger-set", "--skill", "alpha", "--out", str(out)]), 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(
            payload,
            [
                {"query": "do the alpha thing", "should_trigger": True},
                {"query": "ghost work", "should_trigger": False},
            ],
        )

    def test_export_trigger_set_rejects_a_skill_without_routing_cases(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = run_evals.main(
                ["export-trigger-set", "--skill", "ghost", "--out", str(self.root / "x.json")]
            )
        self.assertEqual(code, 2)


class RepeatsGuardTest(unittest.TestCase):
    """`--repeats 0` used to write a fully-scored run after zero API calls."""

    @staticmethod
    def _main_quietly(argv: list[str]) -> int:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = run_evals.main(argv)
        RepeatsGuardTest.stderr = err.getvalue()
        return code

    def test_routing_rejects_zero_and_negative_repeats(self) -> None:
        for repeats in ("0", "-1"):
            self.assertEqual(
                self._main_quietly(["routing", "--all", "--model", "sonnet", "--repeats", repeats]),
                2,
                repeats,
            )
            self.assertIn("--repeats must be at least 1", self.stderr)

    def test_run_rejects_zero_repeats(self) -> None:
        self.assertEqual(
            self._main_quietly(["run", "--all", "--model", "sonnet", "--repeats", "0"]), 2
        )
        self.assertIn("--repeats must be at least 1", self.stderr)

    def test_the_guard_fires_before_any_doctor_or_case_loading(self) -> None:
        # Nothing may be written or called on the way to this refusal.
        self.assertEqual(
            self._main_quietly(
                ["routing", "--skill", "no-such-skill", "--model", "sonnet", "--repeats", "0"]
            ),
            2,
        )
        self.assertIn("--repeats must be at least 1", self.stderr)

    def test_scoring_zero_repeats_is_unanswered_not_a_verdict(self) -> None:
        for case in (
            _routing_case(expected_skill=None),
            _routing_case(),
            _routing_case(expected_skill="ghost", phantom_expected=True, must_not_route="alpha"),
        ):
            score = routing.score_case(case, [])
            self.assertEqual(score["outcome"], "unanswered", case.expected_skill)
            self.assertEqual(score["answered"], 0)
            self.assertTrue(any("no repeat produced an answer" in w for w in score["warnings"]))

    def test_an_all_unanswered_aggregate_has_no_pass_rate(self) -> None:
        cases_list = [_routing_case(expected_skill=None), _routing_case(line_no=2)]
        scores = [routing.score_case(case, []) for case in cases_list]
        aggregate = routing.aggregate_routing(cases_list, scores, mode="native", repeats=0)
        self.assertEqual(aggregate["totals"]["unanswered"], 2)
        self.assertEqual(aggregate["totals"]["pass"], 0)
        self.assertEqual(aggregate["totals"]["fail"], 0)
        self.assertIsNone(aggregate["pass_rate"])
        self.assertEqual(aggregate["unanswered"], ["alpha:1", "alpha:2"])
        self.assertEqual(aggregate["files"]["alpha"]["unanswered"], 2)


class PartialToolInputTest(unittest.TestCase):
    """The skill name must survive without the completed assistant message.

    The parser used to read the name only from the completed block this CLI build
    happens to re-emit. A build that stops doing so would make every native
    intent read as "routed to nothing", and `null`-expected cases would pass on
    the strength of a parsing gap.
    """

    def _fixture_events(self) -> list[dict]:
        return [json.loads(line) for line in _fixture_lines("skill_tool_use_partial.jsonl")]

    @staticmethod
    def _lines(events: list[dict]) -> list[str]:
        return [json.dumps(event) for event in events]

    @staticmethod
    def _has_skill_tool_use(event: dict) -> bool:
        return any(use.get("name") == "Skill" for use in claude_cli._tool_uses_in_event(event))

    def _without_completed_block(self) -> list[str]:
        """The real stream with the completed assistant tool_use message removed."""
        return self._lines(
            [
                event
                for event in self._fixture_events()
                if not (event.get("type") == "assistant" and self._has_skill_tool_use(event))
            ]
        )

    def test_the_name_is_rebuilt_from_the_input_json_deltas(self) -> None:
        lines = self._without_completed_block()
        self.assertTrue(any('"input_json_delta"' in line for line in lines))
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(lines)
        skill_uses = [use for use in tool_uses if use["name"] == "Skill"]
        self.assertEqual(len(skill_uses), 1)
        self.assertEqual(skill_uses[0]["input"]["skill"], "fact-check")
        result = claude_cli.ClaudeResult(status="ok", tool_uses=tool_uses)
        self.assertEqual(routing.chosen_skill(result), "fact-check")

    def test_a_stream_with_neither_deltas_nor_a_completed_block_is_unanswered(self) -> None:
        lines = [
            line
            for line in self._without_completed_block()
            if '"input_json_delta"' not in line
        ]
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(lines)
        self.assertTrue(any(use["name"] == "Skill" for use in tool_uses))
        result = claude_cli.ClaudeResult(status="ok", tool_uses=tool_uses)
        self.assertEqual(routing.chosen_skill(result), routing.UNNAMED_SKILL)

        score = routing.score_case(
            _routing_case(expected_skill=None), [routing.UNNAMED_SKILL], statuses=["ok"]
        )
        self.assertEqual(score["outcome"], "unanswered")
        self.assertTrue(any("never named it" in item for item in score["warnings"]))

    def test_a_truncated_delta_run_leaves_the_input_empty(self) -> None:
        # Half-parsed arguments would be worse than an admitted gap.
        events = [
            event
            for event in self._fixture_events()
            if not (event.get("type") == "assistant" and self._has_skill_tool_use(event))
        ]
        trimmed = []
        for event in events:
            fragment = claude_cli._partial_tool_input(event)
            if fragment is not None and fragment[1].rstrip().endswith("}"):
                continue
            trimmed.append(event)
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(self._lines(trimmed))
        skill_uses = [use for use in tool_uses if use["name"] == "Skill"]
        self.assertEqual(skill_uses[0]["input"], {})

    def test_the_completed_block_still_wins_when_it_arrives(self) -> None:
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(
            _fixture_lines("skill_tool_use_partial.jsonl")
        )
        skill_uses = [use for use in tool_uses if use["name"] == "Skill"]
        self.assertEqual(len(skill_uses), 1)
        self.assertEqual(skill_uses[0]["input"]["skill"], "fact-check")
        self.assertIn("args", skill_uses[0]["input"])

    def test_delta_accumulation_does_not_disturb_a_non_partial_stream(self) -> None:
        _, tool_uses, _, _ = claude_cli.parse_stream_lines(_fixture_lines("skill_tool_use.jsonl"))
        self.assertEqual([use["name"] for use in tool_uses], ["Skill"])
        self.assertEqual(tool_uses[0]["input"], {"skill": "zz-eval-sentinel-fa2a907f"})


class BaselineCommitProvenanceTest(unittest.TestCase):
    """Task 25 item 6: the baseline records the tree it describes, not the run's."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_skill_tree(
            self.root, "briefing",
            examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
        )
        _git_init(self.root)
        self.head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(self.root), capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.run_results = {"run_id": "r1", "skills": {"briefing": {"cases": 4, "configs": {}}}}
        self.run_meta = {"run_id": "r1", "commit": "abc1234", "dirty": False}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_top_level_commit_is_head_at_merge_time_not_the_runs(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        self.assertEqual(merged["commit"], self.head)
        self.assertNotEqual(merged["commit"], "abc1234")

    def test_each_entry_keeps_the_commit_its_run_measured(self) -> None:
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        entry = merged["skills"]["briefing"]
        self.assertEqual(entry["run_id"], "r1")
        self.assertEqual(entry["source_commit"], "abc1234")

    def test_dirty_is_the_worktree_at_merge_time(self) -> None:
        (self.root / "skills" / "briefing" / "SKILL.md").write_text("changed\n", encoding="utf-8")
        merged = report.merge_baseline(None, self.run_results, self.run_meta, root=self.root)
        self.assertTrue(merged["dirty"], "a dirty tree at merge time is a dirty baseline")

    def test_carried_over_entries_keep_their_own_source_commit(self) -> None:
        existing = {"skills": {"owner-dream-cycle": {"run_id": "r0", "source_commit": "0000000"}}}
        merged = report.merge_baseline(existing, self.run_results, self.run_meta, root=self.root)
        self.assertEqual(merged["skills"]["owner-dream-cycle"]["source_commit"], "0000000")
        self.assertEqual(merged["skills"]["briefing"]["source_commit"], "abc1234")

    def test_a_root_outside_git_records_unknown_rather_than_the_repos_head(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            _write_skill_tree(Path(outside), "briefing", examples={"evals": []})
            merged = report.merge_baseline(
                None, self.run_results, self.run_meta, root=Path(outside)
            )
        self.assertEqual(merged["commit"], "unknown")
        self.assertFalse(merged["dirty"])


class MergeRoutingBlockTest(unittest.TestCase):
    """Task 25 item 13: a routing run covering some files must not erase the rest."""

    EXISTING = {
        "run_id": "r0",
        "mode": "native",
        "repeats": 3,
        "files": {
            "alpha": {"cases": 2, "pass": 2, "pass_rate": 1.0},
            "beta": {"cases": 1, "pass": 0, "pass_rate": 0.0},
        },
        "phantom_targets": ["ghost-skill"],
    }
    INCOMING = {
        "run_id": "r1",
        "mode": "native",
        "repeats": 1,
        "files": {"beta": {"cases": 1, "pass": 1, "pass_rate": 1.0}},
        "phantom_targets": ["other-ghost"],
    }

    def test_files_absent_from_the_run_are_preserved(self) -> None:
        merged = report.merge_routing_block(self.EXISTING, self.INCOMING)
        self.assertEqual(merged["files"]["alpha"], self.EXISTING["files"]["alpha"])

    def test_files_present_in_the_run_are_replaced(self) -> None:
        merged = report.merge_routing_block(self.EXISTING, self.INCOMING)
        self.assertEqual(merged["files"]["beta"], {"cases": 1, "pass": 1, "pass_rate": 1.0})

    def test_the_run_id_and_mode_come_from_the_incoming_run(self) -> None:
        merged = report.merge_routing_block(self.EXISTING, self.INCOMING)
        self.assertEqual(merged["run_id"], "r1")
        self.assertEqual(merged["repeats"], 1)

    def test_phantom_targets_are_unioned_because_the_kept_files_still_name_theirs(self) -> None:
        merged = report.merge_routing_block(self.EXISTING, self.INCOMING)
        self.assertEqual(merged["phantom_targets"], ["ghost-skill", "other-ghost"])

    def test_no_existing_block_is_the_incoming_block(self) -> None:
        self.assertEqual(report.merge_routing_block(None, self.INCOMING), self.INCOMING)


class BaselineUpdateFlagsTest(unittest.TestCase):
    """Task 25 items 13 and 15: `--skill`, per-file routing merge, `--replace-routing`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._saved_ws = run_evals.workspace.WORKSPACE
        self._saved_root = run_evals.workspace.ROOT
        run_evals.workspace.WORKSPACE = self.root / "evals" / "workspaces"
        run_evals.workspace.ROOT = self.root
        for name in ("alpha", "beta"):
            _write_skill_tree(
                self.root, name,
                examples={"evals": [{"id": 1, "prompt": "p", "assertions": ["a", "b"]}]},
                routing='{"intent":"do it","expected_skill":"%s"}\n' % name,
            )
        run_root = run_evals.workspace.WORKSPACE / "runs" / "r1"
        _write_json(run_root / "run.json", {"run_id": "r1", "repeats": 1, "commit": "abc1234"})
        for name in ("alpha", "beta"):
            eval_dir = run_root / name / "eval-1"
            _write_eval_metadata(eval_dir, eval_id=1, key=f"{name}:examples:1", assertions=["a", "b"])
            for config, marks in (("with_skill", [True, True]), ("without_skill", [True, False])):
                _write_timing(eval_dir / config / "run-1")
                _write_grading(eval_dir / config / "run-1", ["a", "b"], marks)
        _write_json(
            run_evals.workspace.WORKSPACE / "routing" / "rt1" / "results.json",
            {
                "run_id": "rt1", "mode": "native", "repeats": 1,
                "files": {"beta": {"cases": 1, "pass": 1, "pass_rate": 1.0}},
                "phantom_targets": [],
            },
        )

    def tearDown(self) -> None:
        run_evals.workspace.WORKSPACE = self._saved_ws
        run_evals.workspace.ROOT = self._saved_root
        self.tmp.cleanup()

    def _main_quietly(self, argv: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return run_evals.main(argv)

    def _baseline(self) -> dict:
        return json.loads(
            (self.root / "evals" / "baseline.json").read_text(encoding="utf-8")
        )

    def test_skill_flag_merges_only_the_named_entries(self) -> None:
        code = self._main_quietly(["baseline", "update", "--from", "r1", "--skill", "alpha"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(self._baseline()["skills"]), ["alpha"])

    def test_skill_flag_takes_a_comma_separated_list(self) -> None:
        self.assertEqual(
            self._main_quietly(["baseline", "update", "--from", "r1", "--skill", "alpha,beta"]), 0
        )
        self.assertEqual(sorted(self._baseline()["skills"]), ["alpha", "beta"])

    def test_a_skill_the_run_never_covered_is_refused(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = run_evals.main(["baseline", "update", "--from", "r1", "--skill", "ghost"])
        self.assertEqual(code, 2)
        self.assertIn("ghost", err.getvalue())

    def test_the_ungraded_refusal_is_scoped_to_the_named_skills(self) -> None:
        # A run covering two skills, one of them degraded: merging the healthy one
        # by name must not be refused for the other skill's ungraded case.
        grading = run_evals.workspace.WORKSPACE / "runs" / "r1" / "beta" / "eval-1"
        _write_ungraded(grading / "with_skill" / "run-1", ["a", "b"])

        code = self._main_quietly(["baseline", "update", "--from", "r1", "--skill", "alpha"])

        self.assertEqual(code, 0)
        self.assertEqual(sorted(self._baseline()["skills"]), ["alpha"])

    def test_a_degraded_named_skill_is_still_refused(self) -> None:
        grading = run_evals.workspace.WORKSPACE / "runs" / "r1" / "beta" / "eval-1"
        _write_ungraded(grading / "with_skill" / "run-1", ["a", "b"])
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = run_evals.main(["baseline", "update", "--from", "r1", "--skill", "beta"])
        self.assertEqual(code, 2)
        self.assertIn("beta", err.getvalue())

    def test_routing_from_merges_per_file_and_keeps_the_others(self) -> None:
        self.assertEqual(self._main_quietly(["baseline", "update", "--from", "r1"]), 0)
        seeded = self._baseline()
        seeded["routing"] = {
            "run_id": "rt0", "mode": "native", "repeats": 3,
            "files": {
                "alpha": {"cases": 1, "pass": 0, "pass_rate": 0.0},
                "beta": {"cases": 1, "pass": 0, "pass_rate": 0.0},
            },
            "phantom_targets": [],
        }
        report.write_baseline(seeded, root=self.root)
        self.assertEqual(self._main_quietly(["baseline", "update", "--routing-from", "rt1"]), 0)
        routing_block = self._baseline()["routing"]
        self.assertEqual(routing_block["files"]["alpha"]["pass_rate"], 0.0)
        self.assertEqual(routing_block["files"]["beta"]["pass_rate"], 1.0)
        self.assertEqual(routing_block["run_id"], "rt1")

    def test_replace_routing_restores_whole_block_replacement(self) -> None:
        self.assertEqual(self._main_quietly(["baseline", "update", "--from", "r1"]), 0)
        seeded = self._baseline()
        seeded["routing"] = {
            "run_id": "rt0", "mode": "native", "repeats": 3,
            "files": {"alpha": {"cases": 1, "pass": 0}, "beta": {"cases": 1, "pass": 0}},
            "phantom_targets": [],
        }
        report.write_baseline(seeded, root=self.root)
        self.assertEqual(
            self._main_quietly(
                ["baseline", "update", "--routing-from", "rt1", "--replace-routing"]
            ),
            0,
        )
        self.assertEqual(sorted(self._baseline()["routing"]["files"]), ["beta"])


class RepoInputGrantTest(unittest.TestCase):
    """Task 25 item 25: a repo file named on the Dependencies line is readable under eval."""

    DEPS = (
        "---\n"
        "name: home\n"
        "description: Fixture launcher.\n"
        "---\n"
        "\n"
        "# Home\n"
        "\n"
        "## Inputs\n"
        "\n"
        "**Dependencies:** none beyond the contract. This skill reads one repository "
        "file, [catalog/index.md](../../catalog/index.md), and touches no namespace.\n"
    )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "catalog").mkdir(parents=True, exist_ok=True)
        (self.root / "catalog" / "index.md").write_text("# index\n", encoding="utf-8")
        _write_skill_tree(self.root, "home", body=self.DEPS)
        _write_skill_tree(self.root, "alpha")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _argv(self, skill: str, config: str) -> list[str]:
        case = _behavioral_case(skill=skill)
        args = _run_args(repo_root=str(self.root), sandbox_root=str(self.root / "sandbox"))
        return executor.build_request(case, config, args, [], self.root / "run").argv

    def test_the_declared_repo_directory_is_granted(self) -> None:
        argv = self._argv("home", executor.CONFIG_WITH_SKILL)
        self.assertIn(str(self.root / "catalog"), argv)

    def test_the_grant_is_an_add_dir_value(self) -> None:
        argv = self._argv("home", executor.CONFIG_WITH_SKILL)
        index = argv.index(str(self.root / "catalog"))
        self.assertEqual(argv[index - 1], "--add-dir")

    def test_a_skill_declaring_nothing_gets_no_extra_grant(self) -> None:
        argv = self._argv("alpha", executor.CONFIG_WITH_SKILL)
        self.assertEqual(argv.count("--add-dir"), 1)

    def test_the_without_skill_leg_gets_no_grant(self) -> None:
        argv = self._argv("home", executor.CONFIG_WITHOUT_SKILL)
        self.assertNotIn("--add-dir", argv)

    def test_the_granted_directory_is_named_in_the_system_prompt(self) -> None:
        # A grant the model cannot find is not coverage: the first run looked for
        # `catalog/index.md` relative to the empty sandbox and reported it missing.
        case = _behavioral_case(skill="home")
        args = _run_args(repo_root=str(self.root), sandbox_root=str(self.root / "sandbox"))
        argv = executor.build_request(
            case, executor.CONFIG_WITH_SKILL, args, [], self.root / "run"
        ).argv
        prompt = argv[argv.index("--append-system-prompt") + 1]
        self.assertIn(str(self.root / "catalog"), prompt)

    def test_a_skill_declaring_nothing_gets_no_repo_input_sentence(self) -> None:
        case = _behavioral_case(skill="alpha")
        args = _run_args(repo_root=str(self.root), sandbox_root=str(self.root / "sandbox"))
        argv = executor.build_request(
            case, executor.CONFIG_WITH_SKILL, args, [], self.root / "run"
        ).argv
        prompt = argv[argv.index("--append-system-prompt") + 1]
        self.assertNotIn("declares as inputs", prompt)

    def test_repo_input_dirs_ignores_links_outside_the_repository(self) -> None:
        body = "**Dependencies:** see [docs](https://example.com/x.md) and [up](../../../etc/passwd)."
        self.assertEqual(
            executor.repo_input_dirs(body, self.root / "skills" / "home", self.root), []
        )

    def test_repo_input_dirs_ignores_links_outside_the_dependencies_line(self) -> None:
        body = "Some prose citing [catalog/index.md](../../catalog/index.md).\n"
        self.assertEqual(
            executor.repo_input_dirs(body, self.root / "skills" / "home", self.root), []
        )

    def test_a_link_back_into_the_skill_is_not_repeated(self) -> None:
        body = "**Dependencies:** [ref](reference.md) only.\n"
        self.assertEqual(
            executor.repo_input_dirs(body, self.root / "skills" / "home", self.root), []
        )


if __name__ == "__main__":
    unittest.main()
