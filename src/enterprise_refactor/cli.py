"""Setup prompts, then run Analyze, Plan, or Implement."""

from __future__ import annotations

import argparse

from enterprise_refactor.banner import print_banner
from enterprise_refactor.config import (
    DEFAULT_ENV,
    DEFAULT_MODEL,
    DEFAULT_REF,
    resolve_config,
)
from enterprise_refactor.menu import choose_phase
from enterprise_refactor.state import load_state
from enterprise_refactor.workflows import analyze, implement, plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enterprise-refactor",
        description=(
            "Prompt for legacy repo, target repo, and Cursor env, "
            "then run Analyze, Plan, or Implement on a cloud agent."
        ),
    )
    parser.add_argument(
        "workflow",
        nargs="?",
        choices=("analyze", "plan", "implement"),
        help="Skip the menu and run this workflow",
    )
    parser.add_argument(
        "--legacy-repo",
        default=None,
        help="Legacy source git URL (or CURSOR_LEGACY_REPO / CURSOR_REPO / .env)",
    )
    parser.add_argument(
        "--modern-repo",
        default=None,
        help="Modern target git URL (or CURSOR_MODERN_REPO / .env)",
    )
    parser.add_argument(
        "--cursor-env",
        default=None,
        help=f"Cursor environment name (or CURSOR_ENV / .env; example: {DEFAULT_ENV})",
    )
    parser.add_argument(
        "--legacy-ref",
        default=None,
        help=f"Legacy starting git ref (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--modern-ref",
        default=None,
        help=f"Modern starting git ref (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model id (default: {DEFAULT_MODEL}, or CURSOR_MODEL / .env)",
    )
    args = parser.parse_args(argv)

    config = resolve_config(args)
    print_banner(
        legacy_repo=config.legacy_repo,
        modern_repo=config.modern_repo,
        cursor_env=config.cursor_env,
        model=config.model,
        ready=config.ready,
    )
    workflow = args.workflow or choose_phase()
    state = load_state()

    if workflow == "analyze":
        return analyze.run(config, state)
    if workflow == "plan":
        return plan.run(config, state)
    return implement.run(config, state)


if __name__ == "__main__":
    raise SystemExit(main())
