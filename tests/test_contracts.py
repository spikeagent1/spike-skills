from __future__ import annotations

import re
import unittest

import tools.contracts_check as contracts_check
import tools.validate_repo as validate_repo


CAPABILITIES = contracts_check.load_capabilities()
DATASTORE = contracts_check.load_datastore()
EFFECTS = CAPABILITIES["effects"]
NAMESPACES = DATASTORE["namespaces"]


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
            {"claim_class", "visibility", "confidence", "status", "origin", "session_kind"},
        )
        for name, values in enums.items():
            with self.subTest(enum=name):
                self.assertTrue(values)

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


if __name__ == "__main__":
    unittest.main()
