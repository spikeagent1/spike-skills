from __future__ import annotations

import contextlib
import importlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tools.validate_repo as validate_repo


SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas/skill-evals.schema.json").read_text(
        encoding="utf-8"
    )
)


class ValidateRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._write_base_repo()
        self._patch_validator_root()

    def tearDown(self) -> None:
        importlib.reload(validate_repo)
        self.tmp.cleanup()

    def _patch_validator_root(self) -> None:
        validate_repo.ROOT = self.root
        validate_repo.SKILLS = self.root / "skills"
        validate_repo.EVAL_SCHEMA = self.root / "schemas" / "skill-evals.schema.json"

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_json(self, rel: str, data: object) -> None:
        self._write(rel, json.dumps(data, indent=2) + "\n")

    def _skill_md(self, name: str) -> str:
        return (
            "---\n"
            f"name: {name}\n"
            f"description: Portable validation fixture for {name} behavior.\n"
            "---\n\n"
            "# Fixture\n\n"
            "## Dependencies\n"
            "None.\n\n"
            "## Provenance\n"
            "Repo-owned synthetic fixture.\n\n"
            "## When to use\nFixture requests.\n\n"
            "## When not to use\nNon-fixture requests.\n\n"
            "## Required inputs\nFixture input.\n\n"
            "## Optional inputs\nFixture options.\n\n"
            "## Workflow\nValidate the fixture.\n\n"
            "## Sources and freshness\nNo current sources required.\n\n"
            "## Privacy and mutations\nNo mutation.\n\n"
            "## Safety boundaries\nStop on invalid input.\n\n"
            "## Output contract\nValidation result.\n\n"
            "## Failure conditions\nInvalid fixture.\n"
        )

    def _evals(self, name: str) -> dict[str, object]:
        return {
            "skill_name": name,
            "evals": [
                {
                    "id": index,
                    "prompt": f"Exercise fixture scenario {index} for {name}.",
                    "assertions": [
                        "Reports the fixture boundary and outcome",
                        "Avoids private state and hidden dependencies",
                    ],
                }
                for index in range(1, 5)
            ],
        }

    def _write_skill(self, name: str) -> None:
        self._write(f"skills/{name}/SKILL.md", self._skill_md(name))
        self._write_json(f"skills/{name}/examples/evals.json", self._evals(name))

    def _write_base_repo(self) -> None:
        self._write(".gitignore", "evals/workspaces/\n.env\n*.skill\n")
        self._write_json("schemas/skill-evals.schema.json", SCHEMA)
        self._write_skill("approved-skill")
        self._write_skill("pending-skill")
        self._write(
            "catalog/approved.yaml",
            "skills:\n"
            "  - name: approved-skill\n"
            "    status: approved\n"
            "    workshop_proposal: approved-skill-20260824-1234567890\n"
            "  - name: pending-skill\n"
            "    status: pending-review\n"
            "    workshop_proposal: pending-skill-20260824-abcdef1234\n",
        )
        self._write(
            "catalog/domains.yaml",
            "domains:\n"
            "  - name: test\n"
            "    released:\n"
            "      - approved-skill\n"
            "    next:\n"
            "      - pending-skill\n",
        )
        self._write(
            "catalog/sources.yaml",
            "sources:\n"
            "  pending-skill:\n"
            "    status: pending-review\n",
        )
        subprocess.run(
            ["git", "init", "--initial-branch", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

    def _run_validator(self) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = validate_repo.main()
        return code, stream.getvalue()

    def test_valid_approved_and_pending_governance_passes(self) -> None:
        code, output = self._run_validator()
        self.assertEqual(code, 0, output)
        self.assertIn("Validation passed: 2 skills checked.", output)

    def test_pending_skill_cannot_be_released_or_use_fake_proposal(self) -> None:
        catalog = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            catalog.replace("pending-skill-20260824-abcdef1234", "pending-skill"),
        )
        domains = (self.root / "catalog/domains.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/domains.yaml",
            domains.replace(
                "      - approved-skill\n",
                "      - approved-skill\n      - pending-skill\n",
            ),
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("pending-review skill must not be in catalog/domains.yaml released", output)
        self.assertIn("pending-review skill must have a real workshop_proposal ID", output)

    def test_schema_and_eval_malformed_cases_fail(self) -> None:
        self._write_json(
            "skills/approved-skill/examples/evals.json",
            {"evals": [{"assertions": ["only one"]}]},
        )
        self._write_json("schemas/skill-evals.schema.json", {"type": "array"})
        self._write("skills/pending-skill/routing-eval.jsonl", "{bad json}\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("schema must require evals object shape", output)
        self.assertIn("eval 1 missing prompt/input", output)
        self.assertIn("invalid JSONL", output)

    def test_privacy_secret_dependency_and_catalog_cases_fail(self) -> None:
        self._write(
            "skills/approved-skill/SKILL.md",
            self._skill_md("approved-skill").replace("## Dependencies\nNone.", ""),
        )
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill") + "Uses a private endpoint.\n",
        )
        secret_line = "api" + "_key = 'abcdefghijklmnopqrstuvwxyz'\n"
        self._write("notes.md", secret_line)
        self._write("local-state/session.md", "private generated state\n")
        approved_catalog = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            approved_catalog + "  - name: missing-skill\n    status: approved\n",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("must explicitly declare dependencies", output)
        self.assertIn("contains suspicious hidden/private dependency language", output)
        self.assertIn("possible secret or credential", output)
        self.assertIn("private/generated local-state path is tracked", output)
        self.assertIn("missing-skill has no skills/missing-skill directory", output)

    def test_eval_quality_cases_fail(self) -> None:
        self._write_json(
            "skills/approved-skill/examples/evals.json",
            {
                "skill_name": "approved-skill",
                "evals": [
                    {
                        "id": 1,
                        "prompt": "First case",
                        "expected_output": "Meets the skill contract for this scenario.",
                        "assertions": ["Useful assertion", "   "],
                    },
                    {
                        "id": 1,
                        "prompt": "Second case",
                        "assertions": ["One", "Two"],
                    },
                    {
                        "prompt": "Missing ID case",
                        "assertions": ["One", "Two"],
                    },
                ],
            },
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("assertions must be non-empty strings", output)
        self.assertIn("duplicate eval id 1", output)
        self.assertIn("missing positive integer id", output)
        self.assertIn("uses a non-informative expected_output", output)

    def test_pending_skill_requires_candidate_contract(self) -> None:
        skill_path = self.root / "skills/pending-skill/SKILL.md"
        self._write(
            "skills/pending-skill/SKILL.md",
            skill_path.read_text(encoding="utf-8").replace("## Workflow", "## Steps"),
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "pending-review skill missing section '## Workflow'",
            output,
        )

    def test_approved_skill_requires_public_operator_contract(self) -> None:
        skill_path = self.root / "skills/approved-skill/SKILL.md"
        self._write(
            "skills/approved-skill/SKILL.md",
            skill_path.read_text(encoding="utf-8").replace("## When to use", "## Trigger"),
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved skill missing public section 'When to use'", output)

    def test_non_informative_eval_assertions_fail(self) -> None:
        evals = self._evals("approved-skill")
        evals["evals"][0]["assertions"] = [
            "Uses the skill",
            "Avoids private state",
        ]
        self._write_json("skills/approved-skill/examples/evals.json", evals)
        subprocess.run(
            ["git", "add", "."],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("uses non-informative assertion 'Uses the skill'", output)

    def test_skill_requires_four_eval_cases_across_files(self) -> None:
        self._write_json(
            "skills/approved-skill/examples/evals.json",
            {
                "skill_name": "approved-skill",
                "evals": [
                    {
                        "id": 1,
                        "prompt": "Only one behavioral case",
                        "assertions": ["Names the exact boundary checked", "Reports the blocker clearly"],
                    }
                ],
            },
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("needs at least 4 synthetic eval cases, found 1", output)

    def test_schema_fallback_enforces_quality(self) -> None:
        errors: list[str] = []
        original_jsonschema = validate_repo.jsonschema
        validate_repo.jsonschema = None
        try:
            validate_repo.validate_eval_schema(
                {
                    "skill_name": "",
                    "evals": [
                        {
                            "id": 0,
                            "prompt": "Fallback case",
                            "expected_output": " ",
                            "assertions": ["Useful", " "],
                        }
                    ],
                },
                Path("examples/evals.json"),
                SCHEMA,
                errors,
            )
        finally:
            validate_repo.jsonschema = original_jsonschema

        joined = "\n".join(errors)
        self.assertIn("skill_name must be a non-empty string", joined)
        self.assertIn("id must be a positive integer", joined)
        self.assertIn("expected_output must be a non-empty string", joined)
        self.assertIn("must be two or more strings", joined)

    def test_jsonschema_and_fallback_reject_same_whitespace_case(self) -> None:
        if validate_repo.jsonschema is None:
            self.skipTest("optional jsonschema package is unavailable")

        data = {
            "skill_name": " ",
            "evals": [
                {
                    "id": 1,
                    "prompt": " ",
                    "expected_output": " ",
                    "assertions": ["Useful", " "],
                }
            ],
        }
        schema_errors: list[str] = []
        validate_repo.validate_eval_schema(
            data,
            Path("examples/evals.json"),
            SCHEMA,
            schema_errors,
        )

        fallback_errors: list[str] = []
        original_jsonschema = validate_repo.jsonschema
        validate_repo.jsonschema = None
        try:
            validate_repo.validate_eval_schema(
                data,
                Path("examples/evals.json"),
                SCHEMA,
                fallback_errors,
            )
        finally:
            validate_repo.jsonschema = original_jsonschema

        self.assertTrue(schema_errors)
        self.assertTrue(fallback_errors)

    def test_error_order_is_deterministic(self) -> None:
        self._write_json("skills/approved-skill/examples/evals.json", {"evals": []})
        self._write("skills/pending-skill/SKILL.md", "not frontmatter\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        first = self._run_validator()
        second = self._run_validator()

        self.assertEqual(first, second)
        self.assertEqual(first[0], 1)


if __name__ == "__main__":
    unittest.main()
