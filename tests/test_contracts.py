from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import tools.contracts_check as contracts_check
import tools.validate_repo as validate_repo


CAPABILITIES = contracts_check.load_capabilities()
DATASTORE = contracts_check.load_datastore()
VOCABULARY = contracts_check.load_vocabulary()
ADAPTERS = contracts_check.load_adapters()
EFFECTS = CAPABILITIES["effects"]
NAMESPACES = DATASTORE["namespaces"]
TERMS = VOCABULARY["terms"]


class ParserTest(unittest.TestCase):
    def test_subset_round_trips(self) -> None:
        parsed = contracts_check.parse_contract_yaml(
            "# comment\n"
            "version: 1\n"
            "envelope:\n"
            "  required: [id, kind]\n"
            "  optional: []\n"
            "records:\n"
            "  - name: first\n"
            "    flag: true\n"
            "    tags: [a, b]\n"
            "    sync:\n"
            "      policy: provider-wins\n"
            "  - name: second\n"
            "    flag: false\n"
        )
        self.assertEqual(
            parsed,
            {
                "version": 1,
                "envelope": {"required": ["id", "kind"], "optional": []},
                "records": [
                    {
                        "name": "first",
                        "flag": True,
                        "tags": ["a", "b"],
                        "sync": {"policy": "provider-wins"},
                    },
                    {"name": "second", "flag": False},
                ],
            },
        )

    def test_unparsable_line_raises(self) -> None:
        with self.assertRaises(contracts_check.ContractParseError):
            contracts_check.parse_contract_yaml("version: 1\nnot a mapping\n")


class CapabilitiesTest(unittest.TestCase):
    def test_twenty_one_unique_effects(self) -> None:
        names = [entry["name"] for entry in EFFECTS]
        self.assertEqual(len(names), 21)
        self.assertEqual(len(set(names)), 21)

    def test_every_effect_is_fully_declared(self) -> None:
        for entry in EFFECTS:
            with self.subTest(effect=entry.get("name")):
                for hint in contracts_check.HINT_KEYS:
                    self.assertIsInstance(entry[hint], bool)
                self.assertIn(entry["approval"], contracts_check.APPROVALS)
                self.assertIn(entry["resource_class"], contracts_check.RESOURCE_CLASSES)
                self.assertTrue(entry["derived_from"])
                self.assertLessEqual(len(entry["summary"].split()), 15)

    def test_derived_from_entries_are_traceable(self) -> None:
        reference = re.compile(r"^skills/[a-z0-9-]+/SKILL\.md:\d+(-\d+)?$")
        for entry in EFFECTS:
            for source in entry["derived_from"]:
                with self.subTest(effect=entry["name"], source=source):
                    self.assertTrue(
                        source == "design-derived" or reference.match(source),
                        f"{source!r} is neither a SKILL.md line reference nor 'design-derived'",
                    )

    def test_derivation_and_promotion_gate_present(self) -> None:
        self.assertEqual(CAPABILITIES["version"], 1)
        for hint in contracts_check.HINT_KEYS:
            self.assertIn(hint, CAPABILITIES["derivation"])
        for approval in contracts_check.APPROVALS:
            self.assertIn(approval, CAPABILITIES["derivation"])
        self.assertEqual(
            set(CAPABILITIES["promotion_gate"]),
            {"source_text", "summary", "belief", "operating_instruction", "permission"},
        )


class DatastoreTest(unittest.TestCase):
    def test_fourteen_unique_namespaces(self) -> None:
        names = [entry["name"] for entry in NAMESPACES]
        self.assertEqual(len(names), 14)
        self.assertEqual(len(set(names)), 14)

    def test_every_namespace_answers_the_six_axes(self) -> None:
        for entry in NAMESPACES:
            with self.subTest(namespace=entry.get("name")):
                self.assertIn(entry["status"], contracts_check.NAMESPACE_STATUSES)
                self.assertIn(entry["system_of_record"], contracts_check.SYSTEMS_OF_RECORD)
                self.assertTrue(entry["kinds"])
                for axis in contracts_check.AXES:
                    self.assertTrue(entry[axis])

    def test_conversations_is_a_separate_root(self) -> None:
        entry = next(item for item in NAMESPACES if item["name"] == "conversations")
        self.assertTrue(entry["separate_root"])

    def test_enums_are_non_empty(self) -> None:
        enums = DATASTORE["enums"]
        self.assertEqual(
            set(enums),
            {
                "claim_class",
                "visibility",
                "confidence",
                "status",
                "origin",
                "session_kind",
                "effect_state",
            },
        )
        for name, values in enums.items():
            with self.subTest(enum=name):
                self.assertTrue(values)

    def test_effect_state_is_the_union_of_the_reporting_skills(self) -> None:
        """Every state a batch-5 skill reports is in the enum, and vice versa."""
        declared = DATASTORE["enums"]["effect_state"]
        self.assertEqual(len(declared), len(set(declared)), "effect_state has duplicates")
        reported: set[str] = set()
        for skill in ("publish", "cron-scheduler", "conversation-archive"):
            path = contracts_check.ROOT / "skills" / skill / "SKILL.md"
            body = path.read_text(encoding="utf-8")
            section = body.split("## Output contract", 1)[1].split("\n## ", 1)[0]
            names = set(re.findall(r"^- `([A-Z][A-Z_]+)`", section, re.MULTILINE))
            self.assertTrue(names, f"{skill} declares no effect_state names")
            self.assertLessEqual(
                names, set(declared), f"{skill} reports a state the enum omits"
            )
            reported |= names
        self.assertEqual(reported, set(declared))

    def test_envelope_fields_do_not_overlap(self) -> None:
        envelope = DATASTORE["envelope"]
        self.assertTrue(envelope["required"])
        self.assertTrue(envelope["optional"])
        self.assertFalse(set(envelope["required"]) & set(envelope["optional"]))

    def test_verbs_declare_mutation_and_readback(self) -> None:
        verbs = DATASTORE["verbs"]
        self.assertEqual(len(verbs), 7)
        for verb in verbs:
            with self.subTest(verb=verb.get("name")):
                self.assertIsInstance(verb["mutating"], bool)
                self.assertIsInstance(verb["readback"], bool)
                self.assertEqual(verb["mutating"], verb["readback"])


class TemplateTest(unittest.TestCase):
    def test_headings_match_the_validator_canonical_order(self) -> None:
        self.assertEqual(
            tuple(contracts_check.template_headings()), validate_repo.CANONICAL_ORDER
        )

    def test_template_carries_the_contract_hooks(self) -> None:
        text = (contracts_check.CONTRACTS / "SKILL.template.md").read_text(encoding="utf-8")
        self.assertIn("Dependencies:", validate_repo.section_body(text, "Inputs") or "")
        contract = validate_repo.section_body(text, "Contract") or ""
        self.assertIn(validate_repo.CONTRACT_LINK, contract)
        self.assertIn("Provenance:", contract)


class VocabularyTest(unittest.TestCase):
    def test_terms_match_the_contract_glossary(self) -> None:
        glossary = contracts_check.glossary_terms()
        self.assertEqual(len(glossary), 31)
        self.assertEqual([entry["term"] for entry in TERMS], glossary)

    def test_every_term_is_fully_declared(self) -> None:
        for entry in TERMS:
            with self.subTest(term=entry.get("term")):
                self.assertIn(entry["kind"], contracts_check.VOCABULARY_KINDS)
                self.assertTrue(entry["meaning"].strip())
                self.assertLessEqual(len(entry["meaning"].split()), 20)

    def test_keys_are_derived_from_terms_and_unique(self) -> None:
        keys = [entry["key"] for entry in TERMS]
        self.assertEqual(len(set(keys)), len(keys))
        for entry in TERMS:
            with self.subTest(term=entry["term"]):
                self.assertEqual(entry["key"], contracts_check.term_key(entry["term"]))

    def test_aliases_are_never_terms_in_their_own_right(self) -> None:
        terms = {entry["term"] for entry in TERMS}
        for entry in TERMS:
            for alias in entry.get("aliases") or []:
                with self.subTest(term=entry["term"], alias=alias):
                    self.assertNotIn(alias, terms)


class AdapterTest(unittest.TestCase):
    def test_both_declared_runtimes_load(self) -> None:
        self.assertEqual(sorted(ADAPTERS), sorted(contracts_check.RUNTIMES))
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                self.assertEqual(adapter["runtime"], runtime)
                self.assertEqual(adapter["version"], 1)

    def test_every_adapter_binds_every_vocabulary_term(self) -> None:
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                self.assertEqual(contracts_check.missing_terms(adapter, VOCABULARY), [])
                self.assertEqual(contracts_check.extra_terms(adapter, VOCABULARY), [])
                for entry in TERMS:
                    binding = adapter["vocabulary"][entry["key"]]
                    self.assertTrue(str(binding["value"]).strip(), entry["term"])

    def test_every_adapter_maps_every_datastore_namespace(self) -> None:
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                self.assertEqual(contracts_check.missing_namespaces(adapter, DATASTORE), [])
                self.assertEqual(len(adapter["datastore"]["paths"]), len(NAMESPACES))

    def test_every_adapter_maps_every_datastore_verb(self) -> None:
        verbs = [verb["name"] for verb in DATASTORE["verbs"]]
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                self.assertEqual(sorted(adapter["datastore"]["verbs"]), sorted(verbs))

    def test_structured_keys_agree_with_the_vocabulary(self) -> None:
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                vocabulary = adapter["vocabulary"]
                self.assertEqual(adapter["skills_dir"], vocabulary["skills_dir"]["value"])
                stated = vocabulary["identity_files"]["value"]
                for path in adapter["identity_files"]:
                    self.assertIn(Path(path).name, stated)
                self.assertEqual(
                    adapter["notification"]["quiet_hours"]["timezone_term"], "owner_timezone"
                )

    def test_personal_values_stay_placeholders(self) -> None:
        forbidden = re.compile(
            r"(America/[A-Za-z_]+|\b\d{9,}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)"
        )
        for runtime in contracts_check.RUNTIMES:
            for name in ("adapter.yaml", "ADAPTER.md"):
                path = contracts_check.ADAPTERS_DIR / runtime / name
                with self.subTest(file=f"{runtime}/{name}"):
                    self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))

    def test_adapter_markdown_stays_readable(self) -> None:
        for runtime in contracts_check.RUNTIMES:
            path = contracts_check.ADAPTERS_DIR / runtime / "ADAPTER.md"
            lines = path.read_text(encoding="utf-8").splitlines()
            with self.subTest(runtime=runtime):
                self.assertLessEqual(len(lines), 90)
                for heading in contracts_check.ADAPTER_MD_SECTIONS:
                    self.assertIn(heading, lines)

    def test_adapters_match_the_json_schema(self) -> None:
        try:
            import jsonschema
        except ModuleNotFoundError:
            self.skipTest("optional jsonschema package is unavailable")
        schema = json.loads(
            (contracts_check.ADAPTERS_DIR / "adapter.schema.json").read_text(encoding="utf-8")
        )
        validator = jsonschema.Draft202012Validator(schema)
        for runtime, adapter in ADAPTERS.items():
            with self.subTest(runtime=runtime):
                self.assertEqual(list(validator.iter_errors(adapter)), [])


class AdapterMarkdownTest(unittest.TestCase):
    def test_binding_markers_match_the_yaml_notes(self) -> None:
        for runtime, adapter in ADAPTERS.items():
            rendered = contracts_check.adapter_markdown_terms(runtime)
            self.assertEqual(sorted(rendered), sorted(entry["term"] for entry in TERMS))
            for entry in TERMS:
                note = str(adapter["vocabulary"][entry["key"]].get("note") or "").strip()
                # Only a note that *opens* with the marker declares the state; a
                # note that merely mentions one is prose.
                declared = next(
                    (
                        marker
                        for marker in contracts_check.BINDING_MARKERS
                        if note.upper().startswith(marker)
                    ),
                    "",
                )
                with self.subTest(runtime=runtime, term=entry["term"]):
                    self.assertEqual(rendered[entry["term"]], declared)

    def test_a_degraded_note_is_not_read_as_unconfirmed(self) -> None:
        self.assertEqual(contracts_check.binding_marker("DEGRADED - mirror-only"), "DEGRADED")
        self.assertEqual(contracts_check.binding_marker("UNCONFIRMED - unknown"), "UNCONFIRMED")
        self.assertEqual(contracts_check.binding_marker("a plain caveat"), "")


class CoverageGapTest(unittest.TestCase):
    """The loader has to fail on a gap, not only pass on a complete pair."""

    def test_missing_terms_reports_a_dropped_binding(self) -> None:
        broken = {"vocabulary": dict(ADAPTERS["openclaw"]["vocabulary"])}
        del broken["vocabulary"]["scheduler"]
        self.assertEqual(contracts_check.missing_terms(broken, VOCABULARY), ["scheduler"])

    def test_a_blank_value_counts_as_missing(self) -> None:
        # Parity with the jsonschema leg, which enforces minLength 1 on `value`.
        broken = {"vocabulary": dict(ADAPTERS["openclaw"]["vocabulary"])}
        broken["vocabulary"]["scheduler"] = {"value": "   "}
        self.assertEqual(contracts_check.missing_terms(broken, VOCABULARY), ["scheduler"])

    def test_a_binding_with_no_value_key_counts_as_missing(self) -> None:
        broken = {"vocabulary": dict(ADAPTERS["openclaw"]["vocabulary"])}
        broken["vocabulary"]["scheduler"] = {"note": "still to decide"}
        self.assertEqual(contracts_check.missing_terms(broken, VOCABULARY), ["scheduler"])

    def test_a_non_mapping_binding_counts_as_missing(self) -> None:
        broken = {"vocabulary": dict(ADAPTERS["openclaw"]["vocabulary"])}
        broken["vocabulary"]["scheduler"] = "cron"
        self.assertEqual(contracts_check.missing_terms(broken, VOCABULARY), ["scheduler"])

    def test_extra_terms_reports_an_unknown_binding(self) -> None:
        broken = {"vocabulary": dict(ADAPTERS["openclaw"]["vocabulary"])}
        broken["vocabulary"]["invented_term"] = {"value": "x"}
        self.assertEqual(contracts_check.extra_terms(broken, VOCABULARY), ["invented_term"])

    def test_missing_namespaces_reports_a_dropped_path(self) -> None:
        paths = dict(ADAPTERS["claude-code"]["datastore"]["paths"])
        del paths["calendar"]
        paths["jobs"] = "   "
        broken = {"datastore": {"paths": paths}}
        self.assertEqual(
            contracts_check.missing_namespaces(broken, DATASTORE), ["calendar", "jobs"]
        )

    def test_main_exits_one_on_a_broken_adapter_tree(self) -> None:
        original_root = contracts_check.ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(contracts_check.CONTRACTS, root / "contracts")
            shutil.copytree(contracts_check.ADAPTERS_DIR, root / "adapters")
            path = root / "adapters" / "openclaw" / "adapter.yaml"
            text = path.read_text(encoding="utf-8")
            text = text.replace("  contacts_provider:\n    value: none configured\n", "")
            text = text.replace("    calendar: ops/calendar/\n", "")
            path.write_text(text, encoding="utf-8")

            contracts_check.ROOT = root
            try:
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    status = contracts_check.main()
            finally:
                contracts_check.ROOT = original_root

        report = buffer.getvalue()
        self.assertEqual(status, 1)
        self.assertIn("Contract coverage failed:", report)
        self.assertIn("unbound term contacts_provider", report)
        self.assertIn("unmapped namespace calendar", report)

    def test_main_passes_on_the_committed_tree(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status = contracts_check.main()
        self.assertEqual(status, 0)
        self.assertNotIn("Contract coverage failed:", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
