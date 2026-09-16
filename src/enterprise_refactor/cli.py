"""Setup prompts, then run Analyze, Plan, or Implement."""

from __future__ import annotations

import argparse

from enterprise_refactor.banner import print_banner
from enterprise_refactor.config import (
    DEFAULT_ENV,
    DEFAULT_MODEL,
    DEFAULT_REF,
    Config,
    resolve_config,
)
from enterprise_refactor.menu import choose_phase, leave_home_for_workflow, wait_for_menu
from enterprise_refactor.runs import show_runs
from enterprise_refactor.settings import edit_settings
from enterprise_refactor.state import WorkflowState, load_state
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
    parser.add_argument(
        "--prompt",
        default=None,
        help="Plan modernization ask (or CURSOR_PLAN_PROMPT; prompted if missing)",
    )
    parser.add_argument(
        "--analyze-branch",
        default=None,
        help="Legacy branch Plan should read (skips the branch picker)",
    )
    parser.add_argument(
        "--plan-branch",
        default=None,
        help="Target branch Implement should work on (skips the branch picker)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Stream thinking, tools, tasks, and assistant text (or CURSOR_VERBOSE)",
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
    if args.workflow:
        code = _run_workflow(
            args.workflow,
            config,
            load_state(),
            args.prompt,
            args.analyze_branch,
            args.plan_branch,
        )
        return 0 if code is None else code

    last = 0
    index = 0
    while True:
        workflow = choose_phase(
            legacy_repo=config.legacy_repo,
            modern_repo=config.modern_repo,
            cursor_env=config.cursor_env,
            model=config.model,
            index=index,
        )
        if workflow == "settings":
            edit_settings(config)
            index = 4
            continue
        if workflow == "runs":
            show_runs(config, load_state())
            index = 3
            continue
        if workflow not in {"plan", "implement"}:
            leave_home_for_workflow()
        last = _run_workflow(
            workflow,
            config,
            load_state(),
            args.prompt,
            args.analyze_branch,
            args.plan_branch,
        )
        if last is not None:
            wait_for_menu()
        index = {"analyze": 1, "plan": 2, "implement": 2}.get(workflow, 0)


def _run_workflow(
    workflow: str,
    config: Config,
    state: WorkflowState,
    prompt: str | None,
    analyze_branch: str | None,
    plan_branch: str | None,
) -> int | None:
    if workflow == "analyze":
        return analyze.run(config, state)
    if workflow == "plan":
        return plan.run(
            config, state, prompt=prompt, analyze_branch=analyze_branch
        )
    return implement.run(config, state, plan_branch=plan_branch)


if __name__ == "__main__":
    raise SystemExit(main())
