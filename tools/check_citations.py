#!/usr/bin/env python3
"""Check every `skills/<name>/SKILL.md:<line>` anchor outside `skills/`.

The contracts, the adapters, and the docs cite the skill line that a rule was
derived from. A skill body is edited far more often than the rule it justifies,
and every edit above a cited line moves it, so an anchor that pointed at the
sentence carrying the evidence silently comes to point at whatever now sits at
that offset. This checks what a script honestly can:

- the cited file exists and the line number is inside it;
- the line is prose the anchor could be about -- not blank, not a heading, not a
  fence, not a table separator, not a bare frontmatter delimiter;
- the line sits below the frontmatter, since the evidence for a rule is in the
  body.

`--show` prints each anchor beside the line it resolves to, which is the audit a
reader does after a rewrite: the script cannot tell whether the sentence still
says what the rule claims, so it prints the sentence and lets them.

Usage:
  python3 tools/check_citations.py [--show] [--root DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Where citations live. `skills/` is excluded on purpose: a skill citing another
# skill's line number would be the coupling this repository exists to avoid.
SEARCH_DIRS = ("contracts", "adapters", "docs")
SEARCH_SUFFIXES = (".md", ".yaml", ".yml", ".json")
ANCHOR_RE = re.compile(r"skills/([a-z0-9]+(?:-[a-z0-9]+)*)/SKILL\.md:(\d+)")
# Lines an anchor cannot be about: structure rather than statement.
NON_PROSE_RE = re.compile(r"^(?:#{1,6}\s|```|---\s*$|\|\s*-{2,}|<!--)")
SNIPPET_CHARS = 96


def citation_files(root: Path) -> list[Path]:
    """Every file under the search directories that could carry an anchor."""
    found: list[Path] = []
    for name in SEARCH_DIRS:
        directory = root / name
        if not directory.is_dir():
            continue
        found.extend(
            path
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.suffix in SEARCH_SUFFIXES
        )
    return found


def body_start(lines: list[str]) -> int:
    """1-based line number of the first body line, past any frontmatter block."""
    if not lines or lines[0].strip() != "---":
        return 1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 2
    return 1


def check_anchor(skill: str, line_no: int, root: Path) -> tuple[str | None, str]:
    """`(problem, snippet)` for one anchor; `problem` is None when it resolves."""
    target = root / "skills" / skill / "SKILL.md"
    if not target.is_file():
        return f"no such file skills/{skill}/SKILL.md", ""
    lines = target.read_text(encoding="utf-8").splitlines()
    if not 1 <= line_no <= len(lines):
        return f"line {line_no} is past the end of the file ({len(lines)} lines)", ""
    text = lines[line_no - 1]
    snippet = text.strip()
    if not snippet:
        return f"line {line_no} is blank", ""
    if line_no < body_start(lines):
        return f"line {line_no} is inside the frontmatter, not the body", snippet
    if NON_PROSE_RE.match(snippet):
        return f"line {line_no} is structure, not a statement", snippet
    return None, snippet


def collect(root: Path) -> list[tuple[Path, int, str, int]]:
    """`(citing file, citing line, skill, cited line)` for every anchor found."""
    anchors: list[tuple[Path, int, str, int]] = []
    for path in citation_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in ANCHOR_RE.finditer(line):
                anchors.append((path, line_no, match.group(1), int(match.group(2))))
    return anchors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--show", action="store_true", help="Print every anchor beside the line it resolves to."
    )
    parser.add_argument("--root", default=str(ROOT), help="Repository root to check.")
    args = parser.parse_args(argv)
    root = Path(args.root)

    anchors = collect(root)
    problems: list[str] = []
    for path, citing_line, skill, cited_line in anchors:
        problem, snippet = check_anchor(skill, cited_line, root)
        rel = path.relative_to(root).as_posix()
        if problem is not None:
            problems.append(f"{rel}:{citing_line}: skills/{skill}/SKILL.md {problem}")
        elif args.show:
            trimmed = snippet if len(snippet) <= SNIPPET_CHARS else snippet[:SNIPPET_CHARS - 1] + "…"
            print(f"{rel}:{citing_line} -> skills/{skill}/SKILL.md:{cited_line}  {trimmed}")

    if problems:
        print("citation check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"citation check passed: {len(anchors)} anchor(s) resolve to a body statement.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
