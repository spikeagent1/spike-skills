"""`tools/autonomy_check.py`: the one deterministic matcher over `autonomy/`.

The grammar is `contracts/datastore.md`'s and no other -- an exact string, a
`prefix/*`, or `*` -- and every failure mode here is fail-closed: a pattern that
is neither form, an expired or superseded record, a capability whose
`contract_eligible` flag is false, and a write to `autonomy/` itself all resolve
to no contract rather than to a wider one.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import tools.autonomy_check as autonomy_check


NOW = "2026-09-01T10:00:00"


def contract(
    record_id: str,
    *,
    capability: str = "datastore:write",
    skill: str = "daily-task-manager",
    obj: str = "tasks/*",
    expires: object = "2026-12-31",
    superseded_by: object = None,
    status: str = "active",
    kind: str = "autonomy-contract",
    namespace: str = "autonomy",
) -> dict[str, object]:
    """One `autonomy-contract` record's frontmatter, in the contract's field names."""
    return {
        "id": record_id,
        "namespace": namespace,
        "kind": kind,
        "status": status,
        "capability": capability,
        "skill-pattern": skill,
        "object-pattern": obj,
        "granted-at": "2026-08-01",
        "expires": expires,
        "superseded-by": superseded_by,
    }


class PatternGrammarTest(unittest.TestCase):
    """Three forms, and nothing else parses (`contracts/datastore.md`)."""

    def test_exact_string_matches_only_itself(self) -> None:
        self.assertTrue(autonomy_check.pattern_matches("tasks/inbox", "tasks/inbox"))
        self.assertFalse(autonomy_check.pattern_matches("tasks/inbox", "tasks/inbox/x"))
        self.assertFalse(autonomy_check.pattern_matches("tasks/inbox", "tasks"))

    def test_prefix_wildcard_matches_below_the_slash_only(self) -> None:
        self.assertTrue(autonomy_check.pattern_matches("tasks/*", "tasks/inbox"))
        self.assertTrue(autonomy_check.pattern_matches("tasks/*", "tasks/inbox/today"))
        # The slash is part of the prefix: `tasksfoo` is not below `tasks/`.
        self.assertFalse(autonomy_check.pattern_matches("tasks/*", "tasksfoo"))
        self.assertFalse(autonomy_check.pattern_matches("tasks/*", "tasks"))

    def test_bare_star_matches_anything(self) -> None:
        self.assertTrue(autonomy_check.pattern_matches("*", "tasks/inbox"))
        self.assertTrue(autonomy_check.pattern_matches("*", ""))

    def test_a_pattern_that_is_neither_form_parses_to_nothing(self) -> None:
        for pattern in ("tasks/*/today", "task*", "*/inbox", "**", "", "tasks/**"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(autonomy_check.parse_pattern(pattern))
                self.assertFalse(autonomy_check.pattern_matches(pattern, "tasks/inbox"))

    def test_specificity_is_the_non_wildcard_prefix_length(self) -> None:
        self.assertEqual(autonomy_check.prefix_length("*"), 0)
        self.assertEqual(autonomy_check.prefix_length("tasks/*"), len("tasks/"))
        self.assertEqual(autonomy_check.prefix_length("tasks/inbox"), len("tasks/inbox"))
        self.assertEqual(autonomy_check.prefix_length("task*"), 0)


class MatchTest(unittest.TestCase):
    """`match(records, capability, skill, obj, now)` -- the whole resolution."""

    def test_an_exact_live_contract_authorizes_and_is_cited(self) -> None:
        record = contract("add-tasks", obj="tasks/inbox")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertEqual(decision.contract_id, "add-tasks")
        self.assertEqual(decision.matches, ("add-tasks",))

    def test_a_different_capability_is_not_covered(self) -> None:
        record = contract("add-tasks", capability="datastore:read")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertIn("no live contract", decision.reason)

    def test_a_different_skill_is_not_covered(self) -> None:
        record = contract("add-tasks", skill="daily-task-manager")
        decision = autonomy_check.match(
            [record], "datastore:write", "cron-scheduler", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)

    def test_a_skill_prefix_pattern_covers_the_family(self) -> None:
        record = contract("family", skill="social/*", obj="*")
        decision = autonomy_check.match(
            [record], "datastore:write", "social/listening", "tasks/inbox", NOW
        )
        self.assertEqual(decision.contract_id, "family")

    def test_an_unparsable_pattern_matches_nothing_and_is_disclosed(self) -> None:
        record = contract("broken", obj="tasks/*/today")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox/today", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("broken" in note for note in decision.skipped))
        self.assertTrue(any("object-pattern" in note for note in decision.skipped))

    def test_an_expired_contract_never_matches(self) -> None:
        record = contract("lapsed", expires="2026-08-31")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("expired" in note for note in decision.skipped))

    def test_expiry_is_inclusive_at_the_instant_itself(self) -> None:
        """`now >= expires` is expired: the contract does not cover its own end."""
        at_the_instant = contract("edge", expires=NOW)
        self.assertIsNone(
            autonomy_check.match(
                [at_the_instant], "datastore:write", "daily-task-manager", "tasks/x", NOW
            ).contract_id
        )
        later = contract("edge", expires="2026-09-01T10:00:01")
        self.assertEqual(
            autonomy_check.match(
                [later], "datastore:write", "daily-task-manager", "tasks/x", NOW
            ).contract_id,
            "edge",
        )

    def test_an_unparsable_expiry_fails_closed(self) -> None:
        record = contract("garbled", expires="whenever")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("garbled" in note for note in decision.skipped))

    def test_a_superseded_contract_never_matches(self) -> None:
        by_field = contract("revoked", superseded_by="revoked-2026-09-01")
        by_status = contract("stale", status="superseded")
        for record in (by_field, by_status):
            with self.subTest(record=record["id"]):
                decision = autonomy_check.match(
                    [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
                )
                self.assertIsNone(decision.contract_id)
                self.assertTrue(any("superseded" in note for note in decision.skipped))

    def test_a_record_with_no_status_is_not_live(self) -> None:
        record = contract("unstamped")
        del record["status"]
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)

    def test_the_vault_status_name_for_active_is_read_as_live(self) -> None:
        """The claude-code adapter maps `status: active` to `confirmed`."""
        record = contract("mapped", status="confirmed")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertEqual(decision.contract_id, "mapped")

    def test_a_record_of_another_kind_is_not_a_contract(self) -> None:
        for field, value in (("kind", "activity"), ("namespace", "profile")):
            with self.subTest(field=field):
                record = contract("intruder")
                record[field] = value
                decision = autonomy_check.match(
                    [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
                )
                self.assertIsNone(decision.contract_id)

    def test_any_live_match_authorizes_and_the_most_specific_is_cited(self) -> None:
        """4A: overlap is not ambiguity -- every match authorizes, one is cited."""
        broad = contract("broad", obj="*")
        narrow = contract("narrow", obj="tasks/inbox")
        middle = contract("middle", obj="tasks/*")
        decision = autonomy_check.match(
            [broad, narrow, middle],
            "datastore:write",
            "daily-task-manager",
            "tasks/inbox",
            NOW,
        )
        self.assertEqual(decision.contract_id, "narrow")
        self.assertEqual(decision.matches, ("broad", "middle", "narrow"))

    def test_a_specificity_tie_is_broken_lexicographically(self) -> None:
        first = contract("aaa", skill="*", obj="tasks/*")
        second = contract("bbb", skill="*", obj="tasks/*")
        decision = autonomy_check.match(
            [second, first], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertEqual(decision.contract_id, "aaa")
        self.assertEqual(decision.matches, ("aaa", "bbb"))

    def test_the_skill_pattern_counts_toward_specificity(self) -> None:
        by_skill = contract("named-skill", skill="daily-task-manager", obj="*")
        by_object = contract("named-object", skill="*", obj="tasks/*")
        decision = autonomy_check.match(
            [by_skill, by_object],
            "datastore:write",
            "daily-task-manager",
            "tasks/inbox",
            NOW,
        )
        self.assertEqual(decision.contract_id, "named-skill")


class EligibilityTest(unittest.TestCase):
    """The `contract_eligible` gate, read from `contracts/capabilities.yaml`."""

    def test_an_ineligible_capability_is_refused_whatever_the_record_says(self) -> None:
        for capability in (
            "identity:write",
            "repo:merge",
            "delete:external",
            "spend",
            "credential:manage",
            "publish:revoke",
        ):
            with self.subTest(capability=capability):
                record = contract("wide", capability=capability, skill="*", obj="*")
                decision = autonomy_check.match(
                    [record], capability, "daily-task-manager", "tasks/inbox", NOW
                )
                self.assertIsNone(decision.contract_id)
                self.assertIn("contract_eligible", decision.reason)

    def test_an_unknown_capability_fails_closed(self) -> None:
        record = contract("wide", capability="datastore:incinerate", skill="*", obj="*")
        decision = autonomy_check.match(
            [record], "datastore:incinerate", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertIn("contracts/capabilities.yaml", decision.reason)

    def test_a_write_to_autonomy_itself_is_never_covered(self) -> None:
        """No contract may widen the ring that holds it."""
        record = contract("wide", skill="*", obj="*")
        for target in ("autonomy", "autonomy/add-tasks-2026-09"):
            with self.subTest(target=target):
                decision = autonomy_check.match(
                    [record], "datastore:write", "autonomy", target, NOW
                )
                self.assertIsNone(decision.contract_id)
                self.assertIn("autonomy/", decision.reason)

    def test_reading_autonomy_is_not_the_excluded_write(self) -> None:
        record = contract("view", capability="datastore:read", skill="*", obj="*")
        decision = autonomy_check.match(
            [record], "datastore:read", "autonomy", "autonomy/add-tasks", NOW
        )
        self.assertEqual(decision.contract_id, "view")

    def test_a_namespace_that_merely_starts_with_the_letters_is_no_object_at_all(
        self,
    ) -> None:
        """The self-exclusion no longer prefix-tests, so a lookalike is refused.

        `autonomyish` is not a namespace `contracts/datastore.md` names, so the
        object does not parse and nothing is matched against it -- a refusal
        rather than the cover the raw prefix test used to give it.
        """
        record = contract("wide", skill="*", obj="*")
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "autonomyish/x", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertIn("autonomyish", decision.reason)


class ObjectConventionTest(unittest.TestCase):
    """`contracts/datastore.md`: an object is `<namespace>[/<path>]`, or nothing.

    The object is parsed before any pattern is matched against it, so the
    `autonomy/` exclusion holds on the shape of the string rather than on the
    caller spelling it the one way the exclusion recognizes (review I1).
    """

    def refuse(self, obj: str) -> autonomy_check.Decision:
        """The widest possible contract, against one object string."""
        record = contract("wide", skill="*", obj="*")
        return autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", obj, NOW
        )

    def test_an_object_rooted_in_a_known_namespace_parses(self) -> None:
        for obj in ("tasks", "tasks/inbox", "activity/2026-09-01--a1b2c3d4"):
            with self.subTest(obj=obj):
                self.assertEqual(autonomy_check.parse_object(obj), obj.split("/")[0])

    def test_every_spelling_that_reached_autonomy_is_now_a_refusal(self) -> None:
        """The nine bypasses the review found, under a `*`/`*` contract."""
        for obj in (
            "Autonomy/x",
            "AUTONOMY/x",
            "/autonomy/x",
            "./autonomy/x",
            "ops/autonomy/x",
            "~/Tapan-Brain/autonomy/x",
            " autonomy/x",
            "autonomy\\x",
            "projects/../autonomy/x",
        ):
            with self.subTest(obj=obj):
                self.assertIsNone(autonomy_check.parse_object(obj))
                self.assertIsNone(self.refuse(obj).contract_id)

    def test_the_refusal_names_the_convention_rather_than_the_patterns(self) -> None:
        decision = self.refuse("lists/inbox")
        self.assertIsNone(decision.contract_id)
        self.assertIn("lists/inbox", decision.reason)
        self.assertIn("<namespace>", decision.reason)

    def test_an_empty_or_non_string_object_parses_to_nothing(self) -> None:
        for obj in ("", "   ", "/", "tasks/", "tasks//inbox", None, 42):
            with self.subTest(obj=obj):
                self.assertIsNone(autonomy_check.parse_object(obj))

    def test_the_canonical_autonomy_write_is_still_the_named_refusal(self) -> None:
        """A parsing object in `autonomy/` is refused for the ring, not the shape."""
        decision = self.refuse("autonomy/add-tasks-2026-09")
        self.assertIsNone(decision.contract_id)
        self.assertIn("autonomy/", decision.reason)


class RequiredFieldsTest(unittest.TestCase):
    """`required_fields` in `contracts/datastore.yaml`: no field, no contract."""

    def test_a_contract_with_no_expiry_is_never_live(self) -> None:
        """M5 authorizes an *unexpired* contract, so an endless one is none (I3)."""
        for expires in (None, "", "   "):
            with self.subTest(expires=expires):
                record = contract("endless", expires=expires)
                decision = autonomy_check.match(
                    [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
                )
                self.assertIsNone(decision.contract_id)
                self.assertTrue(any("expires" in note for note in decision.skipped))

    def test_a_contract_missing_the_expiry_field_entirely_is_never_live(self) -> None:
        record = contract("endless")
        del record["expires"]
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("endless" in note for note in decision.skipped))

    def test_every_required_field_is_checked_the_same_way(self) -> None:
        for field in ("capability", "skill-pattern", "object-pattern", "granted-at"):
            with self.subTest(field=field):
                record = contract("partial")
                del record[field]
                decision = autonomy_check.match(
                    [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
                )
                self.assertIsNone(decision.contract_id)
                self.assertTrue(any(field in note for note in decision.skipped))

    def test_the_required_list_is_the_contracts_own(self) -> None:
        self.assertEqual(
            autonomy_check.required_fields(),
            ("capability", "skill-pattern", "object-pattern", "granted-at", "expires"),
        )

    def test_a_missing_expiry_fails_closed_even_when_the_required_list_degrades(self) -> None:
        """I3 holds in `_live` itself: `required=()` must not revive an endless record.

        `required_fields()` reads `contracts/datastore.yaml` and returns `()` on
        any failure -- a missing key, an unparsed shape, a foreign root. A lookup
        failure must never widen autonomy (2A), so the absent-expiry refusal
        cannot be mediated by that read.
        """
        now = autonomy_check._instant(NOW)
        assert now is not None
        missing = contract("endless")
        del missing["expires"]
        for record in (contract("endless", expires=None), missing):
            with self.subTest(has_key="expires" in record):
                reason = autonomy_check._live(record, now, required=())
                self.assertNotEqual(reason, "")
                self.assertIn("expires", reason)


class NotYetValidTest(unittest.TestCase):
    """`granted-at` is read, not just stored (review M3)."""

    def test_a_contract_granted_in_the_future_does_not_cover_today(self) -> None:
        record = contract("premature")
        record["granted-at"] = "2099-01-01"
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("not yet" in note for note in decision.skipped))

    def test_the_grant_instant_itself_is_live(self) -> None:
        record = contract("today")
        record["granted-at"] = NOW
        self.assertEqual(
            autonomy_check.match(
                [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
            ).contract_id,
            "today",
        )

    def test_an_unreadable_grant_date_fails_closed(self) -> None:
        record = contract("garbled-grant")
        record["granted-at"] = "sometime"
        decision = autonomy_check.match(
            [record], "datastore:write", "daily-task-manager", "tasks/inbox", NOW
        )
        self.assertIsNone(decision.contract_id)
        self.assertTrue(any("garbled-grant" in note for note in decision.skipped))


class RecordLoadingTest(unittest.TestCase):
    """`load_records`: Markdown frontmatter from a directory, for tests and ops."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.records = Path(self.tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.records / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_record_file_is_read_as_its_frontmatter(self) -> None:
        self.write(
            "add-tasks.md",
            "---\n"
            "id: add-tasks\n"
            "namespace: autonomy\n"
            "kind: autonomy-contract\n"
            "status: active\n"
            "capability: datastore:write\n"
            "skill-pattern: daily-task-manager\n"
            "object-pattern: tasks/*\n"
            "granted-at: 2026-08-01\n"
            "expires: 2026-12-31\n"
            "---\n\nThe owner wrote this on 2026-08-01.\n",
        )
        records = autonomy_check.load_records(self.records)
        self.assertEqual([record["id"] for record in records], ["add-tasks"])
        self.assertEqual(records[0]["expires"], "2026-12-31")
        self.assertEqual(
            autonomy_check.match(
                records, "datastore:write", "daily-task-manager", "tasks/inbox", NOW
            ).contract_id,
            "add-tasks",
        )

    def test_a_record_file_with_a_null_expiry_loads_and_covers_nothing(self) -> None:
        self.write(
            "endless.md",
            "---\nid: endless\nnamespace: autonomy\nkind: autonomy-contract\n"
            "status: active\ncapability: datastore:write\n"
            "skill-pattern: daily-task-manager\nobject-pattern: tasks/*\n"
            "granted-at: 2026-08-01\nexpires: null\n---\n",
        )
        records = autonomy_check.load_records(self.records)
        self.assertIsNone(records[0]["expires"])
        self.assertIsNone(
            autonomy_check.match(
                records, "datastore:write", "daily-task-manager", "tasks/inbox", NOW
            ).contract_id
        )

    def test_the_id_falls_back_to_the_file_name(self) -> None:
        self.write(
            "nested/no-id.md",
            "---\nnamespace: autonomy\nkind: autonomy-contract\nstatus: active\n"
            "capability: datastore:write\nskill-pattern: '*'\nobject-pattern: '*'\n---\n",
        )
        records = autonomy_check.load_records(self.records)
        self.assertEqual([record["id"] for record in records], ["no-id"])

    def test_a_file_without_frontmatter_is_skipped(self) -> None:
        self.write("note.md", "Just a note about autonomy contracts.\n")
        self.assertEqual(autonomy_check.load_records(self.records), [])

    def test_a_missing_directory_reads_as_no_records(self) -> None:
        self.assertEqual(autonomy_check.load_records(self.records / "absent"), [])


class CommandLineTest(unittest.TestCase):
    """The CLI over a record directory: exit 0 covered, 1 not covered."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.records = Path(self.tmp.name)
        (self.records / "add-tasks.md").write_text(
            "---\n"
            "id: add-tasks\n"
            "namespace: autonomy\n"
            "kind: autonomy-contract\n"
            "status: active\n"
            "capability: datastore:write\n"
            "skill-pattern: daily-task-manager\n"
            "object-pattern: tasks/*\n"
            "granted-at: 2026-08-01\n"
            "expires: 2026-12-31\n"
            "---\n",
            encoding="utf-8",
        )

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = autonomy_check.main(list(args))
        return code, out.getvalue()

    def test_a_covered_action_exits_zero_and_names_the_contract(self) -> None:
        code, out = self.run_cli(
            "--records", str(self.records),
            "--capability", "datastore:write",
            "--skill", "daily-task-manager",
            "--object", "tasks/inbox",
            "--now", NOW,
        )
        self.assertEqual(code, 0)
        self.assertIn("add-tasks", out)

    def test_an_uncovered_action_exits_one_with_the_reason(self) -> None:
        code, out = self.run_cli(
            "--records", str(self.records),
            "--capability", "datastore:write",
            "--skill", "cron-scheduler",
            "--object", "tasks/inbox",
            "--now", NOW,
        )
        self.assertEqual(code, 1)
        self.assertIn("no live contract", out)

    def test_json_output_carries_the_decision(self) -> None:
        code, out = self.run_cli(
            "--records", str(self.records),
            "--capability", "datastore:write",
            "--skill", "daily-task-manager",
            "--object", "tasks/inbox",
            "--now", NOW,
            "--json",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["contract_id"], "add-tasks")
        self.assertEqual(payload["matches"], ["add-tasks"])
        self.assertIn("reason", payload)

    def test_an_ineligible_capability_exits_one_from_the_cli_too(self) -> None:
        code, out = self.run_cli(
            "--records", str(self.records),
            "--capability", "spend",
            "--skill", "daily-task-manager",
            "--object", "tasks/inbox",
            "--now", NOW,
        )
        self.assertEqual(code, 1)
        self.assertIn("contract_eligible", out)


if __name__ == "__main__":
    unittest.main()
