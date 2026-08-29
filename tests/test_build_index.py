from __future__ import annotations

import contextlib
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import tools.build_index as build_index
import tools.validate_repo as validate_repo


class BuildIndexTest(unittest.TestCase):
    """`tools/build_index.py` against a minimal, self-contained fixture repo.

    The fixture declares its own tiny `contracts/capabilities.yaml` and
    `contracts/datastore.yaml` (rather than copying the real ones) so the
    badge-derivation matrix is pinned to effects this file controls, not to
    whatever the real capabilities enum happens to contain.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_index.validate_repo.ROOT = self.root
        validate_repo.ROOT = self.root
        validate_repo.SKILLS = self.root / "skills"
        self._write_base_repo()

    def tearDown(self) -> None:
        importlib.reload(validate_repo)
        importlib.reload(build_index)
        self.tmp.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _skill_md(self, name: str, description: str, effects: list[str]) -> str:
        effects_line = ", ".join(effects)
        return (
            "---\n"
            f"name: {name}\n"
            f'description: "{description}"\n'
            "metadata:\n"
            "  spike-os:\n"
            "    version: 1.0.0\n"
            "    runtime: [openclaw, claude-code]\n"
            "    reads_from: []\n"
            "    writes_to: []\n"
            f"    effects: [{effects_line}]\n"
            "---\n\n"
            "# Fixture\n"
        )

    def _approved_entry(self, name: str, status: str = "approved") -> str:
        return (
            f"  - name: {name}\n"
            "    classification: owned\n"
            f"    runtime_path: skills/{name}\n"
            f"    repository_path: skills/{name}\n"
            f"    status: {status}\n"
            "    cohort: test\n"
            f"    workshop_proposal: {name}-20260824-1234567890\n"
            "    contract_version: 2\n"
            "    version: 1.0.0\n"
        )

    def _write_base_repo(self) -> None:
        # A closed effect enum with exactly one destructive, open-world effect
        # (delete:external) and two calm ones, so badge derivation is pinned.
        self._write(
            "contracts/capabilities.yaml",
            "effects:\n"
            "  - name: read:only\n"
            "    readOnlyHint: true\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n"
            "  - name: write:mutate\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: false\n"
            "    idempotentHint: true\n"
            "    openWorldHint: false\n"
            "  - name: delete:external\n"
            "    readOnlyHint: false\n"
            "    destructiveHint: true\n"
            "    idempotentHint: true\n"
            "    openWorldHint: true\n",
        )
        self._write(
            "contracts/datastore.yaml",
            "namespaces:\n"
            "  - name: notes\n"
            "    status: active\n"
            "    system_of_record: datastore\n"
            "  - name: calendar\n"
            "    status: reserved\n"
            "    system_of_record: provider\n"
            "    authority: none yet\n",
        )
        self._write_skill_files()
        self._write(
            "catalog/approved.yaml",
            "skills:\n"
            + self._approved_entry("reader-skill")
            + self._approved_entry("writer-skill")
            + self._approved_entry("deleter-skill")
            + self._approved_entry("orphan-skill")
            + self._approved_entry("pending-skill", status="pending-review"),
        )
        self._write(
            "catalog/domains.yaml",
            "domains:\n"
            "  - name: alpha\n"
            "    outcomes:\n"
            "      - do alpha things\n"
            "    released:\n"
            "      - reader-skill\n"
            "      - writer-skill\n"
            "    next:\n"
            "      - alpha-next-skill\n"
            "\n"
            "  - name: beta\n"
            "    outcomes:\n"
            "      - do beta things\n"
            "    released:\n"
            "      - deleter-skill\n"
            "    next:\n"
            "\n"
            "  - name: gamma\n"
            "    released: []\n"
            "    next:\n"
            "      - gamma-next-skill\n",
        )
        self._write(
            "catalog/routing.yaml",
            "clusters:\n"
            "  - name: fixture-cluster\n"
            "    skills: [reader-skill, writer-skill]\n",
        )

    def _write_skill_files(self) -> None:
        self._write(
            "skills/reader-skill/SKILL.md",
            self._skill_md("reader-skill", "Use when reading fixture state.", ["read:only"]),
        )
        self._write(
            "skills/writer-skill/SKILL.md",
            self._skill_md(
                "writer-skill", "Use when writing fixture state.", ["read:only", "write:mutate"]
            ),
        )
        self._write(
            "skills/deleter-skill/SKILL.md",
            self._skill_md(
                "deleter-skill",
                "Use when deleting fixture state.",
                ["read:only", "delete:external"],
            ),
        )
        self._write(
            "skills/orphan-skill/SKILL.md",
            self._skill_md("orphan-skill", "Use when nothing else fits.", ["read:only"]),
        )
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill", "Not yet approved.", ["read:only"]),
        )

    def _run_main(self, *argv: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = build_index.main(list(argv))
        return code, stream.getvalue()

    # -- render determinism --------------------------------------------

    def test_render_is_deterministic(self) -> None:
        first = build_index.render()
        second = build_index.render()
        self.assertEqual(first, second)

    def test_render_json_is_deterministic_and_valid_json(self) -> None:
        first = build_index.render_json()
        second = build_index.render_json()
        self.assertEqual(first, second)
        json.loads(first)  # does not raise

    def test_domain_indent_variation_parses_identically_via_shared_parser(self) -> None:
        """`build_index` reads domains.yaml through validate_repo.parse_domains,
        the same ordered parser catalog/domain_lists derives its flat sets from,
        so a re-indent of the `- name:` markers cannot change what's assigned."""
        baseline = build_index.collect_index_data()

        self._write(
            "catalog/domains.yaml",
            "domains:\n"
            "    - name: alpha\n"
            "      outcomes:\n"
            "        - do alpha things\n"
            "      released:\n"
            "        - reader-skill\n"
            "        - writer-skill\n"
            "      next:\n"
            "        - alpha-next-skill\n"
            "\n"
            "    - name: beta\n"
            "      outcomes:\n"
            "        - do beta things\n"
            "      released:\n"
            "        - deleter-skill\n"
            "      next:\n"
            "\n"
            "    - name: gamma\n"
            "      released: []\n"
            "      next:\n"
            "        - gamma-next-skill\n",
        )

        reindented = build_index.collect_index_data()

        self.assertEqual(reindented, baseline)

    # -- shape of the rendered markdown ----------------------------------

    def test_render_groups_by_domain_in_file_order_with_reserved_block(self) -> None:
        text = build_index.render()
        alpha_pos = text.index("## alpha")
        beta_pos = text.index("## beta")
        gamma_pos = text.index("## gamma")
        self.assertLess(alpha_pos, beta_pos)
        self.assertLess(beta_pos, gamma_pos)
        self.assertIn("`reader-skill`", text)
        self.assertIn("`writer-skill`", text)
        self.assertIn("`deleter-skill`", text)
        self.assertIn("_No skills released yet in this domain._", text)  # gamma is empty
        self.assertIn("## Not yet available", text)
        self.assertIn("`calendar`", text)
        self.assertIn("reserved", text)
        self.assertIn("`alpha-next-skill`", text)
        self.assertIn("`gamma-next-skill`", text)
        # pending-skill is not approved: never rendered anywhere.
        self.assertNotIn("pending-skill", text)

    def test_cluster_membership_rendered_for_clustered_skills(self) -> None:
        text = build_index.render()
        self.assertIn("fixture-cluster", text)

    # -- unassigned-domain error ------------------------------------------

    def test_unassigned_skill_appears_in_its_own_section(self) -> None:
        text = build_index.render()
        self.assertIn("## Unassigned", text)
        self.assertIn("`orphan-skill`", text)

    def test_check_fails_on_unassigned_skill_even_when_committed_file_matches(self) -> None:
        # Commit the exact current render (no drift) and confirm --check still
        # fails, because orphan-skill has no domain.
        self._write("catalog/index.md", build_index.render())
        self._write("catalog/index.json", build_index.render_json())

        code, output = self._run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("orphan-skill", output)

    def test_check_json_reports_unassigned_as_json(self) -> None:
        self._write("catalog/index.md", build_index.render())
        self._write("catalog/index.json", build_index.render_json())

        code, output = self._run_main("--check", "--json")

        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertTrue(any("orphan-skill" in problem for problem in payload["problems"]))

    # -- drift detection ---------------------------------------------------

    def test_check_detects_stale_committed_index(self) -> None:
        self._write("catalog/index.md", "# Skill index\n\nstale content\n")
        self._write("catalog/index.json", "{}\n")

        code, output = self._run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("catalog/index.md", output)
        self.assertIn("-stale content", output)

        code, _ = self._run_main()  # regenerate for real
        self.assertEqual(code, 0)

        # Fix domains.yaml so the unassigned-skill error no longer blocks --check.
        domains = (self.root / "catalog/domains.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/domains.yaml",
            domains.replace("      - deleter-skill\n", "      - deleter-skill\n      - orphan-skill\n"),
        )
        self._write("catalog/index.md", build_index.render())
        self._write("catalog/index.json", build_index.render_json())

        code, output = self._run_main("--check")
        self.assertEqual(code, 0, output)

    def test_main_writes_both_files(self) -> None:
        code, output = self._run_main()

        self.assertEqual(code, 0, output)
        self.assertTrue((self.root / "catalog/index.md").exists())
        self.assertTrue((self.root / "catalog/index.json").exists())
        self.assertEqual((self.root / "catalog/index.md").read_text(encoding="utf-8"), build_index.render())
        self.assertEqual(
            (self.root / "catalog/index.json").read_text(encoding="utf-8"), build_index.render_json()
        )

    # -- badge derivation ---------------------------------------------------

    def test_badge_derivation_for_three_skills_including_one_destructive(self) -> None:
        data = build_index.collect_index_data()
        rows = {row["name"]: row for domain in data["domains"] for row in domain["skills"]}

        reader = rows["reader-skill"]["hints"]
        self.assertEqual(
            reader,
            {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        )

        writer = rows["writer-skill"]["hints"]
        self.assertEqual(
            writer,
            {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        )

        deleter = rows["deleter-skill"]["hints"]
        self.assertEqual(
            deleter,
            {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        )

        text = build_index.render()
        self.assertIn("RO IDEM", text)  # reader-skill
        self.assertIn("DESTR IDEM OPEN", text)  # deleter-skill

    # -- validate_repo's drift hook, exercised against the real module ------

    def test_validate_repo_hook_flags_drift_against_the_real_build_index_module(self) -> None:
        import shutil

        (self.root / "tools").mkdir(parents=True, exist_ok=True)
        shutil.copy(
            Path(__file__).resolve().parents[1] / "tools" / "build_index.py",
            self.root / "tools" / "build_index.py",
        )
        self._write("catalog/index.md", "# Skill index\n\nstale\n")
        self._write("catalog/index.json", "{}\n")

        errors: list[str] = []
        validate_repo.validate_catalog_index(errors)

        self.assertTrue(any("catalog/index.md: out of date" in error for error in errors))
        self.assertTrue(any("catalog/index.json: out of date" in error for error in errors))

        self._write("catalog/index.md", build_index.render())
        errors = []
        validate_repo.validate_catalog_index(errors)
        self.assertTrue(any("catalog/index.json: out of date" in error for error in errors))
        self.assertFalse(any("catalog/index.md: out of date" in error for error in errors))

        self._write("catalog/index.json", build_index.render_json())
        errors = []
        validate_repo.validate_catalog_index(errors)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
