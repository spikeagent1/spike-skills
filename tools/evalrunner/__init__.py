"""Eval runner package for the spike-skills behavioral and routing harness.

`HARNESS_VERSION` is part of every cache key and every recorded artifact; bump it
whenever a change would invalidate previously recorded results.
"""

from __future__ import annotations

HARNESS_VERSION = "0.1.3"

__all__ = ["HARNESS_VERSION"]
