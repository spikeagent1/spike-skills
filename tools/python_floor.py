#!/usr/bin/env python3
"""The interpreter floor, stated once and checked before anything can fail on it.

Every line here is parseable by an interpreter far older than the floor,
because an entry point that gates on this module has to get through the import
before it can print anything. Nothing outside the standard library is imported,
for the same reason.
"""

import sys

# The version .github/workflows/validate.yml pins, and the one the library is
# written against; tests/test_python_floor.py holds the two together.
MINIMUM_PYTHON = (3, 11)
EXIT_TOO_OLD = 2


def floor_message(found):
    """What an interpreter below the floor is told, in place of a traceback."""
    want = "%d.%d" % MINIMUM_PYTHON
    have = "%d.%d" % (found[0], found[1])
    return (
        "spike-os needs Python %s or newer; this interpreter is Python %s.\n"
        "  The installer, the validator, the eval runner and tools/bootstrap.py\n"
        "  are all written against %s -- the version CI pins in\n"
        "  .github/workflows/validate.yml. Install it and re-run, for example\n"
        "  `python%s tools/bootstrap.py`.\n" % (want, have, want, want)
    )


def require_python(found=None, stream=None):
    """0 when this interpreter is new enough; EXIT_TOO_OLD, with the floor written, when not."""
    version = tuple(sys.version_info[:2]) if found is None else tuple(found)[:2]
    if version >= MINIMUM_PYTHON:
        return 0
    (stream if stream is not None else sys.stderr).write(floor_message(version))
    return EXIT_TOO_OLD
