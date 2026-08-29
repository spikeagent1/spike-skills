#!/usr/bin/env python3
"""CI runs the same gate the Makefile defines.

The workflow used to list its own copy of the commands, so a check added to
`make validate` was a check CI never ran. These tests pin the two files to each
other: the workflow calls the target, and the target still carries every gate.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
MAKEFILE = ROOT / "Makefile"

RUN_RE = re.compile(r"^\s*run:\s*(.+?)\s*$")

# Every command `make validate` has to reach, directly or through `test`.
REQUIRED_GATES = (
    "python3 -m unittest discover -s tests",
    "python3 tools/validate_repo.py",
    "python3 tools/check_citations.py",
    "python3 tools/build_index.py --check",
)


def workflow_runs() -> list[str]:
    """The `run:` command of every step, in file order."""
    return [
        match.group(1)
        for match in (RUN_RE.match(line) for line in WORKFLOW.read_text(encoding="utf-8").splitlines())
        if match is not None
    ]


def make_recipe(target: str) -> list[str]:
    """Recipe lines of one Makefile target, comments and blank lines dropped."""
    lines: list[str] = []
    inside = False
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{target}:"):
            inside = True
            continue
        if inside:
            if line.startswith("\t"):
                lines.append(line[1:].strip())
            elif line.strip():
                break
    return lines


class CiParityTest(unittest.TestCase):
    def test_ci_calls_make_validate_on_both_legs(self) -> None:
        runs = workflow_runs()
        self.assertEqual(
            [command for command in runs if command.startswith("make ")],
            ["make validate", "make validate"],
            f"the workflow's run steps are {runs}",
        )

    def test_the_jsonschema_leg_sits_between_the_two_calls(self) -> None:
        runs = workflow_runs()
        install = [index for index, command in enumerate(runs) if "jsonschema==" in command]
        calls = [index for index, command in enumerate(runs) if command == "make validate"]
        self.assertEqual(len(install), 1, f"expected one jsonschema install in {runs}")
        self.assertLess(calls[0], install[0], "the stock-Python leg must run first")
        self.assertLess(install[0], calls[-1], "the second leg must run after the install")

    def test_the_workflow_lists_no_gate_of_its_own(self) -> None:
        # A step spelling out a tool call is the drift this pair exists to stop.
        for command in workflow_runs():
            with self.subTest(command=command):
                self.assertNotIn("tools/", command)

    def test_make_validate_reaches_every_gate(self) -> None:
        recipe = make_recipe("validate") + make_recipe("test")
        for gate in REQUIRED_GATES:
            with self.subTest(gate=gate):
                self.assertIn(gate, recipe)

    def test_the_compile_step_globs_rather_than_lists(self) -> None:
        compile_lines = [line for line in make_recipe("test") if "py_compile" in line]
        self.assertEqual(len(compile_lines), 1)
        self.assertIn("tools/*.py tools/*/*.py", compile_lines[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
