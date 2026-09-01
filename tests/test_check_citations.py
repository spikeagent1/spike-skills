"""Unit tests for `tools/check_citations.py` against a throwaway repository."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import tools.check_citations as check_citations


SKILL = (
    "---\n"
    "name: alpha\n"
    "description: Fixture.\n"
    "---\n"
    "\n"
    "# Alpha\n"
    "\n"
    "## Overview\n"
    "\n"
    "The alpha fixture states the rule this anchor is about.\n"
)


class CheckCitationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._write("skills/alpha/SKILL.md", SKILL)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _run(self, *argv: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = check_citations.main(["--root", str(self.root), *argv])
        return code, stream.getvalue()

    def test_an_anchor_on_a_body_statement_passes(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:10`).\n")
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("1 anchor(s)", out)

    def test_an_anchor_on_a_blank_line_fails(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:9`).\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("line 9 is blank", out)

    def test_an_anchor_on_a_heading_fails(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:8`).\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("is structure, not a statement", out)

    def test_an_anchor_inside_the_frontmatter_fails(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:2`).\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("inside the frontmatter", out)

    def test_an_anchor_past_the_end_fails(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:900`).\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("past the end of the file", out)

    def test_an_anchor_naming_no_such_skill_fails(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/ghost/SKILL.md:10`).\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("no such file skills/ghost/SKILL.md", out)

    def test_anchors_inside_skills_are_not_collected(self) -> None:
        # A skill citing another skill's line number is the coupling this
        # repository exists to avoid; the checker does not legitimise it.
        self._write("skills/beta/SKILL.md", "See `skills/alpha/SKILL.md:9`.\n")
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("0 anchor(s)", out)

    def test_adapters_and_docs_are_searched_too(self) -> None:
        self._write("adapters/openclaw/adapter.yaml", "note: see skills/alpha/SKILL.md:9\n")
        self._write("docs/related-work.md", "See `skills/alpha/SKILL.md:10`.\n")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("adapters/openclaw/adapter.yaml:1", out)

    def test_show_prints_the_line_each_anchor_resolves_to(self) -> None:
        self._write("contracts/rules.md", "- **R1** A rule (`skills/alpha/SKILL.md:10`).\n")
        code, out = self._run("--show")
        self.assertEqual(code, 0, out)
        self.assertIn("The alpha fixture states the rule this anchor is about.", out)

    def test_the_real_repository_has_no_stale_anchor(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = check_citations.main([])
        self.assertEqual(code, 0, stream.getvalue())


if __name__ == "__main__":
    unittest.main()
