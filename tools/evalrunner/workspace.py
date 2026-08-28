"""Workspace paths and run identity for eval artifacts.

Everything the harness writes lands under `evals/workspaces/`, which is
gitignored; only `evals/baseline.json` and `evals/reports/` are committed.
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "evals" / "workspaces"
PROBES = WORKSPACE / "probes"
FRESH_HOME = WORKSPACE / "home"
ISOLATED_SETTINGS = WORKSPACE / "isolated-settings.json"
DOTENV = ROOT / ".env"


def ensure_dirs() -> Path:
    """Create the workspace tree and return its root."""
    for path in (WORKSPACE, PROBES, FRESH_HOME, WORKSPACE / "runs", WORKSPACE / "cache"):
        path.mkdir(parents=True, exist_ok=True)
    if not ISOLATED_SETTINGS.exists():
        ISOLATED_SETTINGS.write_text("{}\n", encoding="utf-8")
    return WORKSPACE


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_commit_short() -> str:
    """Short SHA of HEAD, or "unknown" outside a git checkout."""
    return _git("rev-parse", "--short", "HEAD") or "unknown"


def git_dirty() -> bool:
    """True when the working tree has uncommitted tracked changes."""
    return bool(_git("status", "--porcelain"))


def git_config(key: str) -> str:
    """Value of a git config key in this checkout, or "" when it is unset."""
    return _git("config", "--get", key)


def claude_version(claude_bin: str) -> str:
    """Version string reported by the Claude Code CLI, or "unknown"."""
    try:
        completed = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    parts = completed.stdout.strip().split()
    return parts[0] if parts else "unknown"


def utc_stamp() -> str:
    """UTC timestamp in the compact form used by run ids."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")


def utc_iso() -> str:
    """UTC timestamp in ISO-8601 form for recorded artifacts."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def make_run_id(label: str | None = None) -> str:
    """Run id of the form `<stamp>-<sha>[-dirty][-<label>]`."""
    parts = [utc_stamp(), git_commit_short()]
    if git_dirty():
        parts.append("dirty")
    if label:
        parts.append(label)
    return "-".join(parts)


def dotenv_values(path: Optional[Path] = None) -> Dict[str, str]:
    """KEY=VALUE pairs from the gitignored `.env` file; a missing file yields {}."""
    target = DOTENV if path is None else path
    if not target.is_file():
        return {}
    values: Dict[str, str] = {}
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values
