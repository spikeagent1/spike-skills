#!/usr/bin/env python3
"""Eval runner CLI for spike-skills.

Only `doctor` is wired in this build; the remaining subcommands are declared so
their flags stay stable while the case runner, grader, and routing modes land.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evalrunner import HARNESS_VERSION, doctor  # noqa: E402
from tools.evalrunner.claude_cli import strategy_names  # noqa: E402

DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_S = 180.0
DEFAULT_PROBE_BUDGET_USD = 0.05
NOT_IMPLEMENTED = ("run", "grade", "routing", "compare", "report", "baseline")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_evals.py", description="Behavioral and routing eval runner."
    )
    parser.add_argument("--version", action="version", version=f"harness {HARNESS_VERSION}")
    parser.add_argument(
        "--claude-bin", default="claude", help="Path to the Claude Code CLI (default: claude)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Probe auth, isolation, and structured output; write doctor.json."
    )
    doctor_parser.add_argument("--model", default=DEFAULT_MODEL)
    doctor_parser.add_argument(
        "--strategy", default="auto", choices=["auto", *strategy_names()],
        help="Probe only this isolation strategy instead of all of them in order.",
    )
    doctor_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    doctor_parser.add_argument(
        "--max-budget-usd", type=float, default=DEFAULT_PROBE_BUDGET_USD,
        help="Per-probe spend cap (default: 0.05).",
    )
    doctor_parser.set_defaults(handler=doctor.run_doctor)

    for name in NOT_IMPLEMENTED:
        stub = subparsers.add_parser(
            name, help=f"{name} (not implemented in this build)", add_help=False
        )
        stub.set_defaults(handler=_not_implemented, command_name=name)

    return parser


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"run_evals.py {args.command_name}: not implemented in this build", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Stub subcommands accept the flags they will eventually take, so callers get
    # the "not implemented" message rather than an argparse usage error.
    args, extra = parser.parse_known_args(argv)
    if getattr(args, "command_name", None):
        return _not_implemented(args)
    if extra:
        parser.error("unrecognized arguments: " + " ".join(extra))
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
