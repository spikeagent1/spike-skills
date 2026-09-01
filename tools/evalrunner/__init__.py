"""Eval runner package for the spike-skills behavioral and routing harness.

`HARNESS_VERSION` is part of every cache key and every recorded artifact; bump it
whenever a change would invalidate previously recorded results.

`CONFIG_WITH_SKILL`/`CONFIG_WITHOUT_SKILL` live here rather than in `executor`:
`report` needs them too and cannot import `executor`, which reaches
`tools.validate_repo` and would cycle back through `report.check_baseline`. The
package root is stdlib-only, so both sides read one definition.
"""

from __future__ import annotations

HARNESS_VERSION = "0.1.4"

CONFIG_WITH_SKILL = "with_skill"
CONFIG_WITHOUT_SKILL = "without_skill"

__all__ = ["HARNESS_VERSION", "CONFIG_WITH_SKILL", "CONFIG_WITHOUT_SKILL"]
