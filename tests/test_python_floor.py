#!/usr/bin/env python3
"""The interpreter floor is stated once, and reached before anything can fail on it.

A too-old interpreter used to meet whatever the first unsupported construct
was. `tools/python_floor.py` is the one place the floor is written down, and
both entry points run it before importing anything of ours -- which only works
while every line they parse on the way there is parseable by that older
interpreter too.
"""

from __future__ import annotations

import ast
import io
import unittest
from pathlib import Path

from tools import python_floor

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = ("tools/install_skill.py", "tools/python_floor.py")
# The entry points that run the gate themselves, rather than defining it.
GATED_ENTRY_POINTS = ("tools/install_skill.py",)
# The oldest interpreter that might read these files far enough to print the floor.
OLDEST_READER = (3, 8)


class PythonFloorTest(unittest.TestCase):
    def test_the_floor_matches_the_version_ci_pins(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        major, minor = python_floor.MINIMUM_PYTHON
        self.assertIn(f"python-version: '{major}.{minor}'", workflow)

    def test_a_current_interpreter_passes_silently(self) -> None:
        stream = io.StringIO()
        self.assertEqual(python_floor.require_python((3, 11), stream), 0)
        self.assertEqual(stream.getvalue(), "")

    def test_an_old_interpreter_is_told_the_floor_and_what_it_is_running(self) -> None:
        stream = io.StringIO()
        code = python_floor.require_python((3, 9), stream)
        self.assertEqual(code, python_floor.EXIT_TOO_OLD)
        message = stream.getvalue()
        self.assertIn("3.11", message)
        self.assertIn("3.9", message)
        self.assertIn("spike-os", message)

    def test_the_live_interpreter_is_the_default_subject(self) -> None:
        stream = io.StringIO()
        self.assertEqual(python_floor.require_python(stream=stream), 0)
        self.assertEqual(stream.getvalue(), "")


class EntryPointGateTest(unittest.TestCase):
    def _module(self, relative: str) -> ast.Module:
        return ast.parse((ROOT / relative).read_text(encoding="utf-8"))

    def test_every_entry_point_parses_under_the_oldest_reader(self) -> None:
        for relative in ENTRY_POINTS:
            with self.subTest(entry=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                ast.parse(source, feature_version=OLDEST_READER)

    def test_the_gate_runs_before_any_import_of_ours(self) -> None:
        for relative in GATED_ENTRY_POINTS:
            with self.subTest(entry=relative):
                body = self._module(relative).body
                gate = [
                    index
                    for index, node in enumerate(body)
                    if "require_python" in ast.dump(node) and not isinstance(node, ast.ImportFrom)
                ]
                ours = [
                    index
                    for index, node in enumerate(body)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    and "tools." in (getattr(node, "module", "") or "")
                    and "python_floor" not in (getattr(node, "module", "") or "")
                ]
                self.assertTrue(gate, f"{relative} never calls require_python at module level")
                self.assertTrue(ours, f"{relative} imports nothing of ours")
                self.assertLess(gate[0], ours[0], f"{relative} imports before it gates")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
