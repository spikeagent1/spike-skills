"""Eval case loading, normalization, and selection.

Behavioral cases come from the two `evals.json` dialects the repo carries
(`{id,prompt,expected_output,assertions}` and `{id,name,input,expect}`); routing
cases come from `routing-eval.jsonl`. Discovery reuses
`tools.validate_repo.eval_files` so the runner and the validator always agree on
which files are evals.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tools import validate_repo

from . import workspace

ROOT = workspace.ROOT
SKILLS = ROOT / "skills"
COHORTS = ROOT / "catalog" / "cohorts.yaml"

# Second eval file in a skill gets its ids shifted so `(skill, eval_id)` stays
# unique; community-management's two files both number their cases from 1.
EVAL_ID_FILE_OFFSET = 100

PROMPT_KEYS = ("prompt", "input")
ASSERTION_KEYS = ("assertions", "expectations", "expect")

_COHORT_NAME_RE = re.compile(r"^\s*-\s+name:\s*(\S+)\s*$")
_YAML_KEY_RE = re.compile(r"^\s*([A-Za-z_][\w-]*):")
_YAML_ITEM_RE = re.compile(r"^\s*-\s+(\S.*?)\s*$")


class CaseLoadError(ValueError):
    """An eval file, filter, or cohort name the runner cannot turn into cases."""


@dataclass(frozen=True)
class BehavioralCase:
    """One behavioral eval: the prompt to run and the assertions to grade it against."""

    skill: str
    file_rel: str
    eval_id: int
    key: str
    name: Optional[str]
    prompt: str
    expected_output: Optional[str]
    assertions: List[str]

    def __hash__(self) -> int:
        """Hash on the unique key; the generated hash would choke on `assertions`."""
        return hash(self.key)


@dataclass(frozen=True)
class RoutingCase:
    """One routing intent plus the classification the scorer needs.

    `skill_file` is the skill that owns the `routing-eval.jsonl` the line came
    from. Phantom fields record targets that name skills this repo does not have;
    the loader only classifies them, scoring lives in the routing runner.
    `expect_question` marks an intent whose correct answer is a disambiguating
    question rather than any skill at all.
    """

    skill_file: str
    line_no: int
    intent: str
    expected_skill: Optional[str]
    ambiguous_with: List[str]
    phantom_expected: bool
    phantom_ambiguous: List[str]
    must_not_route: Optional[str]
    soft: bool
    expect_question: bool = False

    def __hash__(self) -> int:
        """Hash on the fixture line; the generated hash would choke on the name lists."""
        return hash((self.skill_file, self.line_no))


def _frontmatter(text: str) -> Dict[str, str]:
    """Frontmatter mapping for a SKILL.md body.

    `validate_repo` is growing a full `parse_frontmatter`; until it lands, fall
    back to the name/description-only `frontmatter`.
    """
    parser = getattr(validate_repo, "parse_frontmatter", None) or validate_repo.frontmatter
    return dict(parser(text) or {})


def skill_dirs(skills_root: Optional[Path] = None) -> List[Path]:
    """Skill directories under `skills/`, sorted by name."""
    root = Path(skills_root) if skills_root else SKILLS
    if not root.is_dir():
        return []
    return sorted(
        (child for child in root.iterdir() if (child / "SKILL.md").is_file()),
        key=lambda path: path.name,
    )


def skill_names(skills_root: Optional[Path] = None) -> List[str]:
    """Every name a skill in this repo answers to.

    A routing fixture may name a skill by its declared frontmatter `name` rather
    than its directory, so both count as existing; otherwise a real skill would
    be misread as a phantom target.
    """
    names: List[str] = []
    for path in skill_dirs(skills_root):
        names.append(path.name)
        try:
            declared = _frontmatter(path.joinpath("SKILL.md").read_text(encoding="utf-8")).get("name")
        except OSError:
            declared = None
        if declared and declared not in names:
            names.append(declared)
    return names


def _first_key(raw: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if raw.get(key):
            return raw[key]
    return None


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CaseLoadError(f"{path}: cannot read eval file: {exc}") from exc


def load_behavioral_file(path: Path, skill: str, offset: int, root: Path) -> List[BehavioralCase]:
    """Normalize one `evals.json` into `BehavioralCase`s, both dialects."""
    payload = _load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("evals"), list):
        raise CaseLoadError(f"{path}: expected an object with an `evals` list")
    file_rel = path.relative_to(root).as_posix()
    # `examples/evals.json` and `evals/evals.json` share a basename; the parent
    # directory is what makes a key readable and unique.
    file_stem_dir = path.parent.name

    loaded: List[BehavioralCase] = []
    for index, raw in enumerate(payload["evals"], start=1):
        if not isinstance(raw, dict):
            raise CaseLoadError(f"{file_rel}: eval {index} is not an object")
        try:
            case_id = int(raw.get("id", index))
        except (TypeError, ValueError) as exc:
            raise CaseLoadError(f"{file_rel}: eval {index} has a non-integer id") from exc

        prompt = _first_key(raw, PROMPT_KEYS)
        if not isinstance(prompt, str) or not prompt.strip():
            raise CaseLoadError(f"{file_rel}: eval {case_id} has no `prompt` or `input`")

        assertions = _first_key(raw, ASSERTION_KEYS)
        if not isinstance(assertions, list) or not assertions:
            raise CaseLoadError(
                f"{file_rel}: eval {case_id} has no `assertions`, `expectations`, or `expect`"
            )
        texts = [str(item).strip() for item in assertions]
        if not all(texts):
            raise CaseLoadError(f"{file_rel}: eval {case_id} has an empty assertion")

        expected = raw.get("expected_output")
        loaded.append(
            BehavioralCase(
                skill=skill,
                file_rel=file_rel,
                eval_id=offset + case_id,
                key=f"{skill}:{file_stem_dir}:{case_id}",
                name=str(raw["name"]) if raw.get("name") else f"{skill}-{case_id}",
                prompt=prompt,
                expected_output=str(expected) if isinstance(expected, str) and expected else None,
                assertions=texts,
            )
        )
    return loaded


def load_behavioral_cases(skills_root: Optional[Path] = None) -> List[BehavioralCase]:
    """Every behavioral case in the repo, in skill then file then id order."""
    root_skills = Path(skills_root) if skills_root else SKILLS
    root = root_skills.parent
    loaded: List[BehavioralCase] = []
    for skill_dir in skill_dirs(root_skills):
        json_files = [path for path in validate_repo.eval_files(skill_dir) if path.suffix == ".json"]
        for file_index, path in enumerate(json_files):
            loaded.extend(
                load_behavioral_file(path, skill_dir.name, file_index * EVAL_ID_FILE_OFFSET, root)
            )
    return loaded


def _routing_lines(path: Path) -> List[tuple[int, Dict[str, Any]]]:
    """Data lines of a routing-eval file with their 1-based line numbers.

    `//` comment lines and blank lines are dropped; the line number is kept so a
    failure can be pointed at the exact fixture line.
    """
    rows: List[tuple[int, Dict[str, Any]]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        try:
            row = json.loads(stripped)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CaseLoadError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise CaseLoadError(f"{path}:{line_no}: expected a JSON object")
        rows.append((line_no, row))
    return rows


def load_routing_cases(
    skills_root: Optional[Path] = None, known_skills: Optional[Iterable[str]] = None
) -> List[RoutingCase]:
    """Every routing intent in the repo, classified against the skills that exist.

    A routing fixture may name a skill this repo has not built yet. Those lines
    stay in the corpus: an expected target that does not exist becomes either a
    `soft` case (the owning skill is an accepted answer) or a `must_not_route`
    case (the owning skill must not hijack the intent).
    """
    root_skills = Path(skills_root) if skills_root else SKILLS
    existing = set(known_skills) if known_skills is not None else set(skill_names(root_skills))

    loaded: List[RoutingCase] = []
    for skill_dir in skill_dirs(root_skills):
        for path in validate_repo.eval_files(skill_dir):
            if path.suffix != ".jsonl":
                continue
            owner = skill_dir.name
            for line_no, row in _routing_lines(path):
                intent = row.get("intent")
                if not isinstance(intent, str) or not intent.strip():
                    raise CaseLoadError(f"{path}:{line_no}: missing `intent`")
                expected = row.get("expected_skill")
                if expected is not None and not isinstance(expected, str):
                    raise CaseLoadError(f"{path}:{line_no}: `expected_skill` must be a string or null")

                raw_ambiguous = row.get("ambiguous_with") or []
                if not isinstance(raw_ambiguous, list):
                    raise CaseLoadError(f"{path}:{line_no}: `ambiguous_with` must be a list")
                expect_question = row.get("expect_question", False)
                if not isinstance(expect_question, bool):
                    raise CaseLoadError(
                        f"{path}:{line_no}: `expect_question` must be true or false"
                    )
                ambiguous = [str(name) for name in raw_ambiguous if str(name) in existing]
                phantom_ambiguous = [str(name) for name in raw_ambiguous if str(name) not in existing]

                phantom_expected = bool(expected) and expected not in existing
                soft = phantom_expected and owner in [str(name) for name in raw_ambiguous]
                must_not_route = owner if (phantom_expected and not soft) else None

                loaded.append(
                    RoutingCase(
                        skill_file=owner,
                        line_no=line_no,
                        intent=intent,
                        expected_skill=expected,
                        ambiguous_with=ambiguous,
                        phantom_expected=phantom_expected,
                        phantom_ambiguous=phantom_ambiguous,
                        must_not_route=must_not_route,
                        soft=soft,
                        expect_question=expect_question,
                    )
                )
    return loaded


def parse_cohort_lists(text: str) -> Dict[str, List[str]]:
    """Cohort name -> skill names, read line-wise in the style of `parse_domain_lists`.

    Only the `skills:` list of each cohort is collected; `acceptance:` items and
    folded prose blocks are skipped.
    """
    cohorts: Dict[str, List[str]] = {}
    current: Optional[str] = None
    collecting = False

    for line in text.splitlines():
        name_match = _COHORT_NAME_RE.match(line)
        if name_match:
            current = name_match.group(1)
            cohorts.setdefault(current, [])
            collecting = False
            continue
        key_match = _YAML_KEY_RE.match(line)
        if key_match:
            collecting = key_match.group(1) == "skills"
            continue
        item_match = _YAML_ITEM_RE.match(line)
        if item_match and collecting and current:
            cohorts[current].append(item_match.group(1))
    return cohorts


def cohort_skills(name: str, path: Optional[Path] = None) -> List[str]:
    """Skill names listed by one cohort in `catalog/cohorts.yaml`."""
    target = Path(path) if path else COHORTS
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseLoadError(f"{target}: cannot read cohorts file: {exc}") from exc
    cohorts = parse_cohort_lists(text)
    if name not in cohorts:
        raise CaseLoadError(f"unknown cohort {name!r}; known: {', '.join(sorted(cohorts))}")
    return cohorts[name]


def _matches_selector(case: BehavioralCase, selector: str) -> bool:
    """True when `skill:id` or a full `skill:file:id` key names this case."""
    if selector == case.key:
        return True
    skill, _, rest = selector.partition(":")
    if skill != case.skill or not rest:
        return False
    return rest == str(case.eval_id)


def select_cases(
    all_cases: Sequence[BehavioralCase],
    *,
    skills: Optional[Sequence[str]] = None,
    case_ids: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    sample: Optional[int] = None,
    seed: Optional[int] = None,
) -> List[BehavioralCase]:
    """Apply the CLI's filters in order: skill, case, sample, limit.

    Sampling happens before the limit so `--sample N --seed S` stays reproducible
    regardless of how the corpus is truncated afterwards.
    """
    picked = list(all_cases)

    if skills:
        wanted = [name for name in skills if name]
        known = {case.skill for case in picked}
        missing = [name for name in wanted if name not in known]
        if missing:
            raise CaseLoadError(f"no eval cases for skill(s): {', '.join(missing)}")
        picked = [case for case in picked if case.skill in set(wanted)]

    if case_ids:
        selected: List[BehavioralCase] = []
        for selector in case_ids:
            matched = [case for case in picked if _matches_selector(case, selector)]
            if not matched:
                raise CaseLoadError(f"no eval case matches {selector!r}")
            selected.extend(case for case in matched if case not in selected)
        picked = selected

    if sample is not None and sample < len(picked):
        rng = random.Random(seed)
        picked = sorted(rng.sample(picked, sample), key=lambda case: (case.skill, case.eval_id))

    if limit is not None:
        picked = picked[:limit]
    return picked
