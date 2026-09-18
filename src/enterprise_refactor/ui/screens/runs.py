"""Read-only view of the last Analyze / Plan / Implement run."""

from __future__ import annotations

import sys

from enterprise_refactor.config import Config
from enterprise_refactor.state import WorkflowState
from enterprise_refactor.ui.input import hide_cursor, read_key, show_cursor
from enterprise_refactor.ui.layout import DIM, MUTED, WHITE, _c, print_screen, render_page


def _row(label: str, value: str) -> str:
    shown = value.strip() or "—"
    return f"  {_c(DIM, label.ljust(16))}{_c(WHITE, shown)}"


def show_runs(config: Config, state: WorkflowState) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Runs needs a terminal.")

    body = [
        _c(WHITE, "  Recent runs"),
        _c(MUTED, "  Agent IDs and branches from .refactor/state.json"),
        "",
        _row("Analyze agent", state.analyze_agent_id),
        _row("Analyze branch", state.analyze_branch),
        "",
        _row("Plan agent", state.plan_agent_id),
        _row("Plan branch", state.plan_branch),
        "",
        _row("Implement agent", state.implement_agent_id),
        _row("Implement branch", state.implement_branch),
        "",
        _c(DIM, "  Press enter or q to return."),
    ]
    print_screen(
        render_page(
            legacy_repo=config.legacy_repo,
            modern_repo=config.modern_repo,
            model=config.model,
            body=body,
        )
    )
    hide_cursor()
    try:
        while True:
            key = read_key()
            if key in {"enter", "quit", "esc", "back"}:
                return
    except KeyboardInterrupt:
        return
    finally:
        show_cursor()
