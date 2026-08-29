#!/usr/bin/env python3
"""Paths, tunables, and the warning sink every validator module shares.

One place holds the state a caller redirects: `tools/validate_repo.py`
forwards assignments to `ROOT`, `SKILLS`, `EVAL_SCHEMA`, `BASELINE`,
`LISTING_BUDGET_CHARS`, and `warnings` here, so pointing the entry point at a
fixture tree reaches every check rather than shadowing one name.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

# The optional schema library, held here so both legs that consult it -- the eval
# fixtures and the adapter files -- see the same value when a caller sets it to
# None to exercise the hand-written fallback.
try:
    import jsonschema
except ModuleNotFoundError:  # pragma: no cover - covered by fallback tests.
    jsonschema = None
_REAL_JSONSCHEMA = jsonschema


SOURCE_ROOT = Path(__file__).resolve().parents[2]


ROOT = SOURCE_ROOT


SKILLS = ROOT / "skills"


EVAL_SCHEMA = ROOT / "schemas" / "skill-evals.schema.json"


BASELINE = ROOT / "evals" / "baseline.json"


# Non-failing diagnostics, printed after errors. Reset by main().
warnings: list[str] = []


# A runtime lists a skill as `name: description`, and OpenClaw caps the whole
# listing at its configured maxSkillsPromptChars. Raised from 12,000 in T25: the
# 31-skill library at the 300-character description cap is 9,912 characters, so a
# 12,000 budget declared the library nearly full at its designed size; 16,000
# warns at 12,800, about nine more max-length skills away.
DEFAULT_LISTING_BUDGET_CHARS = 16000
LISTING_BUDGET_CHARS = DEFAULT_LISTING_BUDGET_CHARS


def reset() -> None:
    """Restore the defaults, the way re-importing a single module used to.

    `tools/validate_repo.py` calls this on import so a reload of the entry point
    still returns the validator to the real repository after a test pointed it
    at a fixture tree.
    """
    global ROOT, SKILLS, EVAL_SCHEMA, BASELINE, LISTING_BUDGET_CHARS, jsonschema
    ROOT = SOURCE_ROOT
    SKILLS = ROOT / "skills"
    EVAL_SCHEMA = ROOT / "schemas" / "skill-evals.schema.json"
    BASELINE = ROOT / "evals" / "baseline.json"
    LISTING_BUDGET_CHARS = DEFAULT_LISTING_BUDGET_CHARS
    jsonschema = _REAL_JSONSCHEMA
    warnings.clear()


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report every parse failure.
        add_error(errors, f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return None


def catalog_scalar(raw: str) -> str:
    """Parse the restricted scalar subset used by the committed catalogs."""
    value = raw.strip()
    if value[:1] in {"\"", "\x27"} and value[-1:] == value[:1]:
        return value[1:-1]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]
