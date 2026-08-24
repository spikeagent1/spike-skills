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


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Spike skill synthetic evals",
    "type": "object",
    "required": ["evals"],
    "properties": {
        "skill_name": {"type": "string"},
        "evals": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "anyOf": [{"required": ["prompt"]}, {"required": ["input"]}],
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "assertions": {
                        "type": "array",
                        "minItems": 2,
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


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
            "Repo-owned synthetic fixture.\n"
        )

    def _evals(self, name: str) -> dict[str, object]:
        return {
            "skill_name": name,
            "evals": [
                {
                    "prompt": "Use the fixture skill.",
                    "assertions": ["Uses the named skill", "Avoids private state"],
                }
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
        self.assertIn("schema violation: eval 1 needs prompt or input", output)
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
