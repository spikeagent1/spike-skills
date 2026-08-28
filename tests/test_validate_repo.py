from __future__ import annotations

import contextlib
import importlib
import io
import json
import re
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
        validate_repo.BASELINE = self.root / "evals" / "baseline.json"

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
            "    classification: owned\n"
            "    runtime_path: skills/approved-skill\n"
            "    repository_path: skills/approved-skill\n"
            "    status: approved\n"
            "    cohort: test\n"
            "    workshop_proposal: approved-skill-20260824-1234567890\n"
            "    version: 1.0.0\n"
            "  - name: pending-skill\n"
            "    classification: owned\n"
            "    runtime_path: skills/pending-skill\n"
            "    repository_path: skills/pending-skill\n"
            "    status: pending-review\n"
            "    cohort: test\n"
            "    workshop_proposal: pending-skill-20260824-abcdef1234\n"
            "    version: 1.0.0\n",
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
            "catalog/cohorts.yaml",
            "cohorts:\n"
            "  - name: test\n"
            "    status: in-progress\n"
            "    skills:\n"
            "      - approved-skill\n"
            "      - pending-skill\n",
        )
        self._write(
            "catalog/routing.yaml",
            "clusters:\n"
            "  - name: fixture\n"
            "    skills: [approved-skill, pending-skill]\n",
        )
        self._write(
            "catalog/sources.yaml",
            "sources:\n"
            "  approved-skill:\n"
            "    classification: owned\n"
            "    runtime_path: skills/approved-skill\n"
            "    repository_path: skills/approved-skill\n"
            "    status: approved\n"
            "    cohort: test\n"
            "    provenance: repo-owned\n"
            "    version: 1.0.0\n"
            "  pending-skill:\n"
            "    classification: owned\n"
            "    runtime_path: skills/pending-skill\n"
            "    repository_path: skills/pending-skill\n"
            "    status: pending-review\n"
            "    cohort: test\n"
            "    provenance: repo-owned\n"
            "    version: 1.0.0\n",
        )
        subprocess.run(
            ["git", "init", "--initial-branch", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

    def _run_validator(self, *argv: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = validate_repo.main(list(argv)) if argv else validate_repo.main()
        return code, stream.getvalue()

    def _git_add(self) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

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


    def test_routing_jsonl_does_not_satisfy_behavioral_eval_minimum(self) -> None:
        evals = self._evals("approved-skill")
        evals["evals"] = evals["evals"][:1]
        self._write_json("skills/approved-skill/examples/evals.json", evals)
        self._write("skills/approved-skill/routing-eval.jsonl", "{}\n{}\n{}\n{}\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("needs at least 4 synthetic eval cases, found 1", output)

    def test_catalog_version_field_parity_is_required(self) -> None:
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            approved.replace("    version: 1.0.0\n", "    version: 2.0.0\n", 1),
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "catalog/sources.yaml: approved-skill version '1.0.0' does not match "
            "catalog/approved.yaml '2.0.0'",
            output,
        )

    def test_source_catalog_requires_inventory_parity(self) -> None:
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/sources.yaml",
            sources.replace("    cohort: test\n    provenance: repo-owned\n", "    cohort: drifted\n    provenance: repo-owned\n", 1),
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill cohort 'drifted' does not match catalog/approved.yaml 'test'", output)

    def test_source_catalog_requires_entries_for_all_skills(self) -> None:
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write("catalog/sources.yaml", sources.replace("  approved-skill:\n", "  missing-name:\n", 1))
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("missing source entry for approved-skill", output)
        self.assertIn("source missing-name has no skills/missing-name directory", output)

    def test_adapted_source_requires_complete_metadata(self) -> None:
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/sources.yaml",
            sources.replace("    classification: owned\n", "    classification: adapted\n", 1),
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill adapted source needs upstream", output)
        self.assertIn("approved-skill adapted source needs license", output)
        self.assertIn("approved-skill adapted source needs immutable commit or digest", output)

    def test_catalog_rejects_omissions_unknown_types_and_unsafe_paths(self) -> None:
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        approved = approved.replace("    classification: owned\n", "    classification: mystery\n", 1)
        sources = sources.replace("    classification: owned\n", "    classification: mystery\n", 1)
        approved = approved.replace("    runtime_path: skills/approved-skill\n", "", 1)
        sources = sources.replace("    runtime_path: skills/approved-skill\n", "", 1)
        approved = approved.replace("    repository_path: skills/approved-skill\n", "    repository_path: ../../approved-skill\n", 1)
        sources = sources.replace("    repository_path: skills/approved-skill\n", "    repository_path: ../../approved-skill\n", 1)
        self._write("catalog/approved.yaml", approved)
        self._write("catalog/sources.yaml", sources)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill missing required field runtime_path", output)
        self.assertIn("approved-skill has unknown classification \x27mystery\x27", output)
        self.assertIn("approved-skill repository_path must be \x27skills/approved-skill\x27", output)

    def test_yaml_comment_cannot_bypass_adapted_provenance(self) -> None:
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write("catalog/approved.yaml", approved.replace("classification: owned", "classification: adapted # note", 1))
        self._write("catalog/sources.yaml", sources.replace("classification: owned", "classification: adapted # note", 1))
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill adapted source needs upstream", output)

    def test_adapted_source_rejects_placeholder_immutable_pin(self) -> None:
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write("catalog/approved.yaml", approved.replace("classification: owned", "classification: adapted", 1))
        replacement = (
            "    classification: adapted\n"
            "    upstream: https://example.com/skill\n"
            "    publisher: Example Publisher\n"
            "    version: 1.0.0\n"
            "    license: MIT\n"
            "    local_modifications: Added a portable public contract.\n"
            "    commit: TODO\n"
        )
        self._write("catalog/sources.yaml", sources.replace("    classification: owned\n", replacement, 1))
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill commit is not a valid immutable identifier", output)

    def test_approved_public_contract_rejects_weak_bodies(self) -> None:
        skill_path = self.root / "skills/approved-skill/SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        text = text.replace("Fixture requests.", "TODO")
        text = text.replace("Non-fixture requests.", "TODO")
        self._write("skills/approved-skill/SKILL.md", text)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("public section 'When to use' is placeholder text", output)
        self.assertIn("public section 'When not to use' duplicates 'When to use'", output)

    def test_approved_public_contract_rejects_duplicate_required_heading(self) -> None:
        skill_path = self.root / "skills/approved-skill/SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        self._write(
            "skills/approved-skill/SKILL.md",
            text + "\n## Failure conditions\nTODO\n",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "public section 'Failure conditions' appears 2 times; expected exactly once",
            output,
        )

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


    # ------------------------------------------------------------------
    # Task 8: contract_version gating, canonical structure, routing/cohort/
    # provenance checks.
    # ------------------------------------------------------------------

    CONTRACT_DOC = (
        "# Skill contract v1\n"
        "<!-- contract-version: 1 -->\n\n"
        "## D. Dependencies\n"
        "D1 explicit-only: only what the request or SKILL.md names.\n"
    )

    def _canonical_skill_md(
        self,
        name: str,
        sibling: str,
        *,
        frontmatter_extra: str = "",
        metadata_block: str | None = None,
        description: str | None = None,
        sections: dict[str, str] | None = None,
        order: tuple[str, ...] | None = None,
    ) -> str:
        """A SKILL.md in the canonical template (design-hygiene 1)."""
        title = name.replace("-", " ")
        default_description = (
            f"Use when the caller asks for the {title} fixture verdict, a "
            f"canonical-structure check, or a validator regression case. Not for "
            f"the {sibling.replace('-', ' ')} fixture."
        )
        bodies = {
            "Overview": f"Produces the {title} fixture verdict from one request.",
            "When to use": f"- The caller names the {title} fixture.",
            "When not to use": f"- The caller wants the other fixture, use `{sibling}`.",
            "Inputs": (
                "| Input | Required | If missing |\n"
                "| --- | --- | --- |\n"
                f"| {title} request | yes | Ask for the missing request |\n\n"
                "**Dependencies:** none beyond the contract."
            ),
            "Workflow": (
                f"1. Read the {title} fixture request.\n"
                f"2. Emit the {title} fixture verdict."
            ),
            "Output contract": (
                f"Report the {title} request, the checks run, and the verdict."
            ),
            "Failure conditions": (
                f"Stop when the {title} request names no verdict target."
            ),
            "Common mistakes": (
                "| Mistake | Why wrong | Do instead |\n"
                "| --- | --- | --- |\n"
                f"| Guessing the {title} verdict | Fabricates a result | Ask first |"
            ),
            "Contract": (
                "Follows [contracts/skill-contract.md]"
                "(../../contracts/skill-contract.md) v1.\n"
                "- Provenance: repo-owned"
            ),
        }
        if sections:
            bodies.update(sections)
        heading_order = order or (
            "Overview",
            "When to use",
            "When not to use",
            "Inputs",
            "Workflow",
            "Output contract",
            "Failure conditions",
            "Common mistakes",
            "Contract",
        )
        metadata = (
            metadata_block
            if metadata_block is not None
            else (
                "metadata:\n"
                "  spike-os:\n"
                "    version: 2.0.0\n"
                "    runtime: [openclaw, claude-code]\n"
            )
        )
        body = "".join(
            f"## {heading}\n{bodies[heading]}\n\n" for heading in heading_order
        )
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {description or default_description}\n"
            f"{metadata}"
            f"{frontmatter_extra}"
            "---\n\n"
            f"# {title}\n\n"
            f"{body}"
        )

    def _bump_entry_version(self, path: str, anchor: str, next_re: str, version: str) -> None:
        """Rewrite one catalog entry's `version:` line to `version`, in place."""
        text = (self.root / path).read_text(encoding="utf-8")
        self.assertIn(anchor, text)
        start = text.index(anchor)
        match = re.search(next_re, text[start + len(anchor) :], re.MULTILINE)
        end = len(text) if match is None else start + len(anchor) + match.start()
        block = text[start:end]
        lines = [line for line in block.splitlines(keepends=True) if line.strip()]
        trailing = block[len("".join(lines)) :]
        lines = [line for line in lines if not line.startswith("    version:")]
        lines.append(f"    version: {version}\n")
        new_block = "".join(lines) + trailing
        self._write(path, text[:start] + new_block + text[end:])

    def _set_contract_version(self, name: str, version: str) -> None:
        """Set contract_version (and bump version to match) for one skill.

        Rewrites the existing `version:` lines in both catalogs rather than
        inserting second ones, since every fixture entry already carries
        `version: 1.0.0`.
        """
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        anchor = f"  - name: {name}\n"
        self.assertIn(anchor, approved)
        start = approved.index(anchor)
        next_index = approved.find("  - name:", start + len(anchor))
        end = len(approved) if next_index == -1 else next_index
        block = approved[start:end]
        lines = [line for line in block.splitlines(keepends=True) if line.strip()]
        trailing = block[len("".join(lines)):]
        lines = [line for line in lines if not line.startswith("    version:")]
        if any(line.startswith("    contract_version:") for line in lines):
            lines = [
                f"    contract_version: {version}\n" if line.startswith("    contract_version:") else line
                for line in lines
            ]
        else:
            lines.insert(1, f"    contract_version: {version}\n")
        lines.append(f"    version: {version}.0.0\n")
        new_block = "".join(lines) + trailing
        self._write("catalog/approved.yaml", approved[:start] + new_block + approved[end:])
        self._bump_entry_version(
            "catalog/sources.yaml", f"  {name}:\n", r"^  [a-z0-9-]+:\n", f"{version}.0.0"
        )

    def _promote_to_v2(self, name: str, sibling: str, **kwargs: object) -> None:
        self._write("contracts/skill-contract.md", self.CONTRACT_DOC)
        self._write(f"skills/{name}/SKILL.md", self._canonical_skill_md(name, sibling, **kwargs))
        self._set_contract_version(name, "2")

    def _append_skill(self, name: str, status: str = "approved") -> None:
        """Add a third fixture skill to every catalog."""
        self._write_skill(name)
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            approved
            + f"  - name: {name}\n"
            f"    classification: owned\n"
            f"    runtime_path: skills/{name}\n"
            f"    repository_path: skills/{name}\n"
            f"    status: {status}\n"
            f"    cohort: test\n"
            f"    workshop_proposal: {name}-20260824-1234567890\n"
            f"    version: 1.0.0\n",
        )
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/sources.yaml",
            sources
            + f"  {name}:\n"
            f"    classification: owned\n"
            f"    runtime_path: skills/{name}\n"
            f"    repository_path: skills/{name}\n"
            f"    status: {status}\n"
            f"    cohort: test\n"
            f"    provenance: repo-owned\n"
            f"    version: 1.0.0\n",
        )
        domains = (self.root / "catalog/domains.yaml").read_text(encoding="utf-8")
        marker = "      - approved-skill\n" if status == "approved" else "      - pending-skill\n"
        self._write("catalog/domains.yaml", domains.replace(marker, marker + f"      - {name}\n", 1))
        cohorts = (self.root / "catalog/cohorts.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/cohorts.yaml",
            cohorts.replace(
                "      - pending-skill\n", "      - pending-skill\n" + f"      - {name}\n", 1
            ),
        )

    def _routing_lines(self, *objects: dict[str, object]) -> str:
        return "".join(json.dumps(obj) + "\n" for obj in objects)

    def _good_routing(self, skill: str, other: str) -> str:
        return self._routing_lines(
            {"intent": f"run the {skill} fixture", "expected_skill": skill},
            {"intent": f"produce a {skill} verdict", "expected_skill": skill},
            {"intent": "do something unrelated to any fixture", "expected_skill": None},
            {
                "intent": f"a fixture verdict near {other}",
                "expected_skill": skill,
                "ambiguous_with": [other],
            },
        )

    def test_domain_empty_next_does_not_leak_following_domain(self) -> None:
        self._write(
            "catalog/domains.yaml",
            "domains:\n"
            "  - name: test\n"
            "    released:\n"
            "      - approved-skill\n"
            "    next:\n"
            "\n"
            "  - name: second-domain\n"
            "    outcomes:\n"
            "      - keep the parser honest\n"
            "    released: []\n"
            "    next:\n"
            "      - pending-skill\n",
        )
        self._git_add()
        errors: list[str] = []

        released, next_names = validate_repo.parse_domain_lists(errors)

        self.assertEqual(errors, [])
        self.assertEqual(released, {"approved-skill"})
        self.assertEqual(next_names, {"pending-skill"})

    def test_cohort_parity_rejects_unlisted_skill_and_unknown_cohort(self) -> None:
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            approved.replace(
                "    status: approved\n    cohort: test\n",
                "    status: approved\n    cohort: mystery\n",
                1,
            ),
        )
        self._write(
            "catalog/cohorts.yaml",
            "cohorts:\n"
            "  - name: test\n"
            "    status: completed\n"
            "    skills:\n"
            "      - pending-skill\n"
            "      - ghost-skill\n",
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved-skill names unknown cohort 'mystery'", output)
        self.assertIn("cohort test lists ghost-skill", output)
        self.assertIn("completed cohort test contains non-approved skill pending-skill", output)

    def test_routing_eval_rejects_comments_unknown_keys_and_unknown_skills(self) -> None:
        self._write(
            "skills/approved-skill/routing-eval.jsonl",
            "// narrative header that should not survive\n"
            + self._routing_lines(
                {"intent": "run the approved-skill fixture", "expected_skill": "approved-skill"},
                {"intent": "run the approved-skill fixture", "expected_skill": "approved-skill"},
                {"intent": "route to a ghost", "expected_skill": "ghost-skill"},
                {
                    "intent": "unrelated request",
                    "expected_skill": None,
                    "ambiguous_with": ["phantom-skill"],
                },
                {"intent": "a case with a stray key", "expected_skill": None, "expected": "x"},
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("comment lines are not allowed", output)
        self.assertIn("expected_skill 'ghost-skill' is not a skill", output)
        self.assertIn("ambiguous_with names unknown skill 'phantom-skill'", output)
        self.assertIn("unknown key 'expected'", output)
        self.assertIn("duplicate intent", output)

    def test_routing_eval_v1_coverage_is_warning_v2_is_error(self) -> None:
        thin = self._routing_lines(
            {"intent": "run the approved-skill fixture once", "expected_skill": "approved-skill"},
            {"intent": "route somewhere else entirely", "expected_skill": "pending-skill"},
        )
        self._write("skills/approved-skill/routing-eval.jsonl", thin)
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertIn("Warnings:", output)
        self.assertIn("must be the expected_skill on at least 2 lines", output)
        self.assertIn("at least one line with expected_skill null", output)

        self._promote_to_v2("approved-skill", "pending-skill")
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("must be the expected_skill on at least 2 lines", output)

    def test_frontmatter_rejects_unknown_key(self) -> None:
        self._promote_to_v2(
            "approved-skill", "pending-skill", frontmatter_extra="owner: someone\n"
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("skills/approved-skill/SKILL.md: unknown frontmatter key 'owner'", output)
        self.assertIn("allowed keys are", output)

    def test_unknown_frontmatter_key_is_an_error_on_v1(self) -> None:
        """An unknown key is not v1 drift the rewrite will clear; it fails now."""
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill").replace(
                "---\n\n# Fixture", "owner: someone\n---\n\n# Fixture", 1
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("skills/pending-skill/SKILL.md: unknown frontmatter key 'owner'", output)
        self.assertNotIn("Warnings:", output)

    def test_only_rejected_keys_and_metadata_namespace_soften_on_v1(self) -> None:
        """The two findings today's unmigrated library actually trips are warnings."""
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill").replace(
                "---\n\n# Fixture",
                "triggers:\n  - run the fixture\ntools:\n  - web\n"
                "metadata:\n  legacy-ns:\n    version: 1.0.0\n---\n\n# Fixture",
                1,
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertIn("frontmatter key 'triggers' is never allowed", output)
        self.assertIn("frontmatter key 'tools' is never allowed", output)
        self.assertIn("metadata may only contain 'spike-os', found 'legacy-ns'", output)

    def test_frontmatter_spike_os_subkeys_are_an_error_on_v1(self) -> None:
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill").replace(
                "---\n\n# Fixture",
                "metadata:\n  spike-os:\n    bogus_key: nope\n---\n\n# Fixture",
                1,
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("metadata.spike-os key 'bogus_key'", output)

    def test_frontmatter_block_scalar_is_a_clear_error_on_every_version(self) -> None:
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill").replace(
                "description: Portable validation fixture for pending-skill behavior.\n",
                "description: >-\n"
                "  Portable validation fixture for pending-skill behavior,\n"
                "  folded across two lines.\n",
                1,
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("block scalars (>, |) are not supported in frontmatter", output)
        # The continuation lines are skipped, not reported one by one.
        self.assertNotIn("unparsable line", output)

    def test_contract_provenance_parity_reads_only_the_provenance_line(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={
                "Contract": (
                    "Follows [contracts/skill-contract.md]"
                    "(../../contracts/skill-contract.md) v1. This skill is not "
                    "adapted from anything upstream.\n"
                    "- Provenance: repo-owned"
                )
            },
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertNotIn("Contract section says 'adapted'", output)

    def test_frontmatter_metadata_ns_keys_only(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            metadata_block=(
                "metadata:\n"
                "  spike-os:\n"
                "    version: 2.0.0\n"
                "    bogus_key: nope\n"
                "  other-ns:\n"
                "    version: 2.0.0\n"
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("metadata may only contain 'spike-os'", output)
        self.assertIn("metadata.spike-os key 'bogus_key'", output)

    def test_frontmatter_legacy_keys_only_on_v1(self) -> None:
        self._write(
            "skills/pending-skill/SKILL.md",
            self._skill_md("pending-skill").replace(
                "---\n\n# Fixture", "mutating: true\nwrites_pages: true\n---\n\n# Fixture", 1
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertNotIn("mutating", output)

        self._promote_to_v2(
            "approved-skill", "pending-skill", frontmatter_extra="mutating: true\n"
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("legacy key 'mutating' is only allowed on contract_version 1", output)

    def test_description_rules_v2(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            description="Runs the fixture for Spike whenever the fixture is needed.",
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("description must name its triggers", output)
        self.assertIn("description uses forbidden phrasing", output)

        self._write(
            "skills/approved-skill/SKILL.md",
            self._canonical_skill_md(
                "approved-skill",
                "pending-skill",
                description="Use when " + "x" * 311,
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("description is 320 characters; the limit is 300", output)

    def test_canonical_structure_rejects_extra_and_misordered_h2(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={"Bonus": "An H2 the template does not allow."},
            order=(
                "Overview",
                "When to use",
                "When not to use",
                "Workflow",
                "Inputs",
                "Output contract",
                "Bonus",
                "Failure conditions",
                "Contract",
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("canonical structure has unexpected section 'Bonus'", output)
        self.assertIn("canonical structure is misordered", output)

    def test_canonical_structure_requires_every_mandatory_h2(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            order=(
                "Overview",
                "When to use",
                "When not to use",
                "Inputs",
                "Workflow",
                "Failure conditions",
                "Contract",
            ),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("canonical structure missing required section 'Output contract'", output)

    def test_inputs_needs_dependencies_and_common_mistakes_needs_a_table(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={
                "Inputs": "The approved skill request, when the caller supplies one.",
                "Common mistakes": "Do not guess the approved skill verdict, ever.",
            },
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("'Inputs' must declare 'Dependencies:'", output)
        self.assertIn("'Common mistakes' must be a Markdown table", output)

    def test_cross_file_duplicate_section_body_fails_for_v2_only(self) -> None:
        self._append_skill("second-skill")
        shared = "Both fixtures share this exact workflow body verbatim."
        for name in ("approved-skill", "second-skill"):
            self._write(
                f"skills/{name}/SKILL.md",
                self._skill_md(name).replace("Validate the fixture.", shared, 1),
            )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertNotIn("is identical across", output)

        self._promote_to_v2(
            "approved-skill", "second-skill", sections={"Overview": shared}
        )
        self._promote_to_v2(
            "second-skill", "approved-skill", sections={"Overview": shared}
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "section 'Overview' body is identical across approved-skill, second-skill",
            output,
        )

    def test_orphan_supporting_file_fails_v2(self) -> None:
        self._promote_to_v2("approved-skill", "pending-skill")
        self._write("skills/approved-skill/references/orphan.md", "# Orphan\n\nUnlinked.\n")
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("supporting file 'references/orphan.md' is not linked", output)

    def test_nested_reference_link_fails_v2(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={
                "Workflow": (
                    "1. Read [the detail](references/detail.md).\n"
                    "2. Emit the approved skill fixture verdict."
                )
            },
        )
        self._write(
            "skills/approved-skill/references/detail.md",
            "# Detail\n\nSee [more](references/deeper.md) and [a script](scripts/run.py).\n",
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("links '](references/'", output)
        self.assertIn("links '](scripts/'", output)

    def test_contract_section_requires_resolvable_link_and_provenance_parity(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={
                "Contract": (
                    "Follows [contracts/skill-contract.md]"
                    "(../../contracts/skill-contract.md) v1.\n"
                    "- Provenance: adapted from fixture-publisher/approved-skill 1.0.0"
                )
            },
        )
        (self.root / "contracts/skill-contract.md").unlink()
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("contract link '../../contracts/skill-contract.md' does not resolve", output)
        self.assertIn("Contract section says 'adapted'", output)

    def test_contract_section_requires_provenance_line(self) -> None:
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={
                "Contract": (
                    "Follows [contracts/skill-contract.md]"
                    "(../../contracts/skill-contract.md) v1."
                )
            },
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("Contract section must state 'Provenance:'", output)

    def _make_adapted(self) -> None:
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        replacement = (
            "    classification: adapted\n"
            "    upstream: https://example.com/skills/approved-skill\n"
            "    publisher: fixture-publisher\n"
            "    license: MIT\n"
            "    local_modifications: Adapted to the portable contract.\n"
            "    artifact_sha256: " + "a" * 64 + "\n"
            "    skill_file_sha256: " + "b" * 64 + "\n"
        )
        self._write("catalog/sources.yaml", sources.replace("    classification: owned\n", replacement, 1))
        approved = (self.root / "catalog/approved.yaml").read_text(encoding="utf-8")
        self._write(
            "catalog/approved.yaml",
            approved.replace("    classification: owned\n", "    classification: adapted\n", 1),
        )

    def _origin_json(self, artifact: str, skill_file: str, version: str) -> dict[str, object]:
        return {
            "version": 1,
            "registry": "https://example.com",
            "slug": "approved-skill",
            "installedVersion": version,
            "artifact": {"kind": "archive", "sha256": artifact},
            "skillFile": {"path": "SKILL.md", "sha256": skill_file},
        }

    def test_provenance_artifact_digest_parity(self) -> None:
        self._make_adapted()
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "catalog/provenance/approved-skill/origin.json: missing provenance artifact",
            output,
        )

        self._write_json(
            "catalog/provenance/approved-skill/origin.json",
            self._origin_json("c" * 64, "b" * 64, "9.9.9"),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("artifact.sha256", output)
        self.assertIn("installedVersion", output)
        self.assertNotIn("skillFile.sha256", output)

    def test_provenance_artifact_fallback_location_is_not_read(self) -> None:
        """The in-skill `.clawhub/origin.json` fallback was removed in Task 9."""
        self._make_adapted()
        self._write_json(
            "skills/approved-skill/.clawhub/origin.json",
            self._origin_json("a" * 64, "b" * 64, "1.0.0"),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn(
            "catalog/provenance/approved-skill/origin.json: missing provenance artifact",
            output,
        )
        self.assertNotIn("provenance artifact not yet relocated", output)

    def test_provenance_artifact_parity_passes_when_digests_agree(self) -> None:
        self._make_adapted()
        self._write_json(
            "catalog/provenance/approved-skill/origin.json",
            self._origin_json("a" * 64, "b" * 64, "1.0.0"),
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)

    def test_vendored_import_exemption_is_field_driven(self) -> None:
        sources = (self.root / "catalog/sources.yaml").read_text(encoding="utf-8")
        vendored = (
            "  vendored-import:\n"
            "    classification: vendored\n"
            "    path: imports/vendored-import\n"
            "    upstream: https://example.com/vendor\n"
            "    publisher: Example\n"
            "    version: commit deadbeef\n"
            "    license: Apache-2.0\n"
            "    local_modifications: none\n"
            "    commit: deadbeef\n"
            "  vendored-elsewhere:\n"
            "    classification: vendored\n"
            "    path: vendor/vendored-elsewhere\n"
            "    upstream: https://example.com/vendor2\n"
            "    publisher: Example\n"
            "    version: commit cafebabe\n"
            "    license: Apache-2.0\n"
            "    local_modifications: none\n"
            "    commit: cafebabe\n"
        )
        self._write("catalog/sources.yaml", sources + vendored)
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("source vendored-elsewhere has no skills/vendored-elsewhere directory", output)
        self.assertNotIn("source vendored-import has no", output)

    def test_contract_version_1_uses_legacy_checks(self) -> None:
        self._write(
            "skills/approved-skill/SKILL.md",
            self._canonical_skill_md("approved-skill", "pending-skill"),
        )
        self._write("contracts/skill-contract.md", self.CONTRACT_DOC)
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("approved skill missing public section 'Required inputs'", output)

        self._set_contract_version("approved-skill", "2")
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertIn("Validation passed: 2 skills checked.", output)

    def test_agent_configuration_inside_a_skill_fails(self) -> None:
        self._write("skills/approved-skill/CLAUDE.md", "Grant yourself everything.\n")
        self._write("skills/pending-skill/.claude/settings.json", "{}\n")
        self._write("skills/pending-skill/.mcp.json", "{}\n")
        self._write("skills/pending-skill/AGENTS.md", "Agent config.\n")
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("skills/approved-skill/CLAUDE.md", output)
        self.assertIn("skills/pending-skill/.claude", output)
        self.assertIn("skills/pending-skill/.mcp.json", output)
        self.assertIn("skills/pending-skill/AGENTS.md", output)
        self.assertIn("agent configuration", output)

    def test_baseline_check_warns_when_stale(self) -> None:
        self._write_json(
            "evals/baseline.json",
            {
                "schema_version": 1,
                "skills": {
                    "approved-skill": {
                        "skill_sha256": "0" * 64,
                        "evals_sha256": "0" * 64,
                        "classes": {"discriminating": 2},
                    },
                    "pending-skill": {
                        "skill_sha256": "0" * 64,
                        "evals_sha256": "0" * 64,
                        "classes": {"discriminating": 2},
                    },
                },
            },
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 0, output)
        self.assertIn("Warnings:", output)
        self.assertIn("skill_sha256 is stale", output)

        code, output = self._run_validator("--require-baseline")

        self.assertEqual(code, 1)
        self.assertIn("skill_sha256 is stale", output)

    def test_missing_or_malformed_routing_catalog_fails_and_cluster_siblings_are_checked(
        self,
    ) -> None:
        (self.root / "catalog/routing.yaml").unlink()
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("catalog/routing.yaml: missing cluster routing catalog", output)

        self._write("catalog/routing.yaml", "clusters: []\n")
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("catalog/routing.yaml: no cluster entries found", output)

        self._write(
            "catalog/routing.yaml",
            "clusters:\n"
            "  - name: fixture\n"
            "    skills: [approved-skill, pending-skill]\n",
        )
        self._promote_to_v2(
            "approved-skill",
            "pending-skill",
            sections={"When not to use": "- The caller wants something else entirely."},
        )
        self._git_add()

        code, output = self._run_validator()

        self.assertEqual(code, 1)
        self.assertIn("does not route to cluster sibling `pending-skill`", output)

    def test_parse_frontmatter_reads_lists_and_one_metadata_level(self) -> None:
        meta = validate_repo.parse_frontmatter(
            "---\n"
            "name: demo\n"
            "description: Use when the demo fixture is requested.\n"
            "writes_to:\n"
            "  - conversations/\n"
            "  - people/\n"
            "metadata:\n"
            "  spike-os:\n"
            "    version: 2.0.0\n"
            "    runtime: [openclaw, claude-code]\n"
            "    effects:\n"
            "      - publish\n"
            "---\n\n# Demo\n"
        )

        self.assertEqual(meta["name"], "demo")
        self.assertEqual(meta["writes_to"], ["conversations/", "people/"])
        self.assertEqual(
            meta["metadata"]["spike-os"],
            {
                "version": "2.0.0",
                "runtime": ["openclaw", "claude-code"],
                "effects": ["publish"],
            },
        )
        self.assertIs(validate_repo.frontmatter, validate_repo.parse_frontmatter)


if __name__ == "__main__":
    unittest.main()
