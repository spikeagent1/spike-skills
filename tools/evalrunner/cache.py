"""Content-addressed cache for executor and grader calls.

Entries live at `evals/workspaces/cache/<sha256>.json`. Keys hash every input
that could change an answer — the harness version first, so bumping
`HARNESS_VERSION` invalidates the whole store rather than serving stale runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from . import HARNESS_VERSION, workspace


def cache_dir() -> Path:
    """Default cache directory, resolved lazily against `workspace.WORKSPACE`.

    A function rather than a module constant: tests relocate `workspace.WORKSPACE`
    after this module has already been imported, and a constant bound at import
    time would keep pointing at the old location.
    """
    return workspace.WORKSPACE / "cache"


# Field separator that cannot appear in a JSON-encoded component, so no two
# distinct inputs can serialize to the same key material.
_SEP = "\x1f"


def key_material(*, kind: str, **fields: Any) -> str:
    """Canonical string hashed into a cache key; readable so keys stay debuggable."""
    parts = [HARNESS_VERSION, kind]
    for name in sorted(fields):
        parts.append(name)
        parts.append(json.dumps(fields[name], sort_keys=True, ensure_ascii=False))
    return _SEP.join(parts)


def _digest(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def executor_key(
    *,
    claude_code_version: str,
    mode: str,
    model: str,
    system_prompt: str,
    skill_body: Optional[str],
    tools: str,
    prompt: str,
    repeat: int,
) -> str:
    """Cache key for one executor invocation.

    `claude_code_version` is part of the key because the CLI is the executor: a
    new build can change the system prompt it wraps around ours, the tool
    surface, or the router, so an answer recorded under one version is not an
    answer to the same question under the next.
    """
    return _digest(
        key_material(
            kind="executor",
            claude_code_version=claude_code_version,
            mode=mode,
            model=model,
            system_prompt=system_prompt,
            skill_body=skill_body,
            tools=tools,
            prompt=prompt,
            repeat=repeat,
        )
    )


def grader_key(
    *,
    claude_code_version: str,
    grader_model: str,
    grader_prompt: str,
    assertions: Sequence[str],
    expected_output: Optional[str],
    response: str,
) -> str:
    """Cache key for one grading invocation.

    Assertion order is part of the key: the grader must return verdicts in the
    order it was given, so a reordered list is a different question. The CLI
    version is in the key for the same reason it is in the executor key.
    """
    return _digest(
        key_material(
            kind="grader",
            claude_code_version=claude_code_version,
            grader_model=grader_model,
            grader_prompt=grader_prompt,
            assertions=list(assertions),
            expected_output=expected_output,
            response=response,
        )
    )


class Cache:
    """JSON entries keyed by content hash.

    `enabled=False` implements `--no-cache` (no reads, no writes).
    `refresh_configs` implements `--refresh-config NAME`: reads for that config
    miss so it is re-run, but the fresh answer is still written back.
    """

    def __init__(
        self,
        root: Optional[Path] = None,
        *,
        enabled: bool = True,
        refresh_configs: Iterable[str] = (),
    ) -> None:
        self.root = Path(root) if root else cache_dir()
        self.enabled = enabled
        self.refresh_configs = set(refresh_configs)
        self.hits = 0
        self.misses = 0
        # `run` drives this store from a thread pool, so the counters and the
        # temp-file names both have to tolerate concurrent callers.
        self._lock = threading.Lock()

    def path_for(self, key: str) -> Path:
        """File backing one cache key."""
        return self.root / f"{key}.json"

    def get(self, key: str, *, config: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Cached entry for `key`, or None on a miss, a disabled cache, or a refresh."""
        if not self.enabled or (config is not None and config in self.refresh_configs):
            self._count(hit=False)
            return None
        try:
            payload = json.loads(self.path_for(key).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            self._count(hit=False)
            return None
        if not isinstance(payload, dict):
            self._count(hit=False)
            return None
        self._count(hit=True)
        return payload

    def _count(self, *, hit: bool) -> None:
        with self._lock:
            if hit:
                self.hits += 1
            else:
                self.misses += 1

    def put(self, key: str, value: Dict[str, Any]) -> None:
        """Store an entry; a disabled cache silently drops it."""
        if not self.enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
