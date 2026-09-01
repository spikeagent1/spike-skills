"""`tools/migrate_activity.py` against a fixture vault, never a live one."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import tools.migrate_activity as migrate


LEDGER_RECORD = """---
id: publish--2026-08-30--01
namespace: effects
kind: effect
title: one publication
operation_key: publish/2026-08-30/01
effect_state: PUBLISHED_VERIFIED
status: active
---

The readback matched. The earlier effect_state name stays in this sentence.
"""

CLAUDE_CODE_RECORD = """---
id: cron--2026-08-30--02
type: "effects"
kind: effect
title: one scheduled change
effect_state: VERIFIED
---

Body left alone.
"""

PROFILE_RECORD = """---
id: owner--timezone
namespace: profile
kind: owner-fact
title: the owner's timezone
---

Not a ledger record.
"""

NO_FRONTMATTER = "Just a note about effects, with no frontmatter at all.\n"


class MigrateActivityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        self._write("ops/effects/publish--2026-08-30--01.md", LEDGER_RECORD)
        self._write("ops/effects/cron--2026-08-30--02.md", CLAUDE_CODE_RECORD)
        self._write("profile/owner--timezone.md", PROFILE_RECORD)
        self._write("ops/effects/README.md", NO_FRONTMATTER)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _read(self, rel: str) -> str:
        return (self.vault / rel).read_text(encoding="utf-8")

    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = migrate.main(["--vault", str(self.vault), *argv])
        return code, buffer.getvalue()

    def test_the_namespace_field_comes_from_the_adapter(self) -> None:
        """The claude-code vault calls it `type`; the contract calls it `namespace`."""
        self.assertEqual(migrate.namespace_fields({}), ("namespace",))
        self.assertEqual(
            migrate.namespace_fields(
                {"datastore": {"field_map": {"namespace": "type"}}}
            ),
            ("namespace", "type"),
        )

    def test_a_preview_writes_nothing(self) -> None:
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("would rewrite", out)
        self.assertIn("preview only", out)
        self.assertEqual(self._read("ops/effects/publish--2026-08-30--01.md"), LEDGER_RECORD)

    def test_apply_rewrites_the_three_fields_and_nothing_else(self) -> None:
        code, out = self._run("--runtime", "claude-code", "--apply")
        self.assertEqual(code, 0)
        migrated = self._read("ops/effects/publish--2026-08-30--01.md")
        self.assertIn("namespace: activity", migrated)
        self.assertIn("kind: activity", migrated)
        self.assertIn("activity_state: PUBLISHED_VERIFIED", migrated)
        # The body is the author's; only frontmatter moves.
        self.assertIn(
            "The readback matched. The earlier effect_state name stays in this sentence.",
            migrated,
        )
        self.assertNotIn("operation_key: publish/2026-08-30/01\neffect_state", migrated)
        self.assertIn("operation_key: publish/2026-08-30/01", migrated)
        self.assertIn("2 record(s) rewrote", out)

    def test_the_adapters_own_namespace_field_is_rewritten_too(self) -> None:
        self._run("--runtime", "claude-code", "--apply")
        migrated = self._read("ops/effects/cron--2026-08-30--02.md")
        self.assertIn('type: "activity"', migrated)
        self.assertIn("kind: activity", migrated)
        self.assertIn("activity_state: VERIFIED", migrated)

    def test_a_record_in_another_namespace_is_untouched(self) -> None:
        self._run("--apply")
        self.assertEqual(self._read("profile/owner--timezone.md"), PROFILE_RECORD)
        self.assertEqual(self._read("ops/effects/README.md"), NO_FRONTMATTER)

    def test_a_second_run_changes_nothing(self) -> None:
        self._run("--runtime", "claude-code", "--apply")
        after_first = self._read("ops/effects/publish--2026-08-30--01.md")
        code, out = self._run("--runtime", "claude-code", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("0 record(s) rewrote", out)
        self.assertEqual(self._read("ops/effects/publish--2026-08-30--01.md"), after_first)

    def test_a_body_that_still_says_effect_state_is_reported_not_edited(self) -> None:
        _, out = self._run("--apply")
        self.assertIn("still says effect_state in its body", out)

    def test_the_reminder_quotes_the_adapter_and_invents_no_command(self) -> None:
        _, out = self._run()
        adapter = migrate.contracts_check.load_adapter("openclaw", migrate.ROOT)
        self.assertIn("Reindex, then verify:", out)
        self.assertIn(adapter["vocabulary"]["runtime_health_check"]["value"], out)
        self.assertIn("attests no reindex subcommand", out)
        self.assertNotIn("gbrain reindex", out)

    def test_a_missing_vault_is_refused(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = migrate.main(["--vault", str(self.vault / "nowhere")])
        self.assertEqual(code, 2)
        self.assertIn("is not a directory", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
