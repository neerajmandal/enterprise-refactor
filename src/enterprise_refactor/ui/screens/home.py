"""Home menu: choose a workflow and return from a finished run."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from enterprise_refactor.ui.input import hide_cursor, read_key, show_cursor
from enterprise_refactor.ui.layout import WHITE, _c, paint_menu_row, pin_banner, print_home

HOME_ITEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("analyze", "1", "⌕", "Analyze", "Understand the legacy codebase"),
    ("plan", "2", "≡", "Plan", "Create a phased migration plan"),
    ("implement", "3", "▸", "Implement", "Execute the plan with automation"),
    ("runs", "4", "◷", "Runs", "View past runs and results"),
    ("settings", "5", "⚙", "Settings", "Configure environment and preferences"),
)


@dataclass(frozen=True)
class MenuRow:
    id: str
    title: str
    detail: str = ""
    color: str = WHITE
    number: str = ""
    icon: str = ""


def _draw(rows: Sequence[MenuRow], index: int, *, first: bool, width: int) -> None:
    lines: list[str] = []
    for i, row in enumerate(rows):
        if row.number:
            lines.append(
                paint_menu_row(
                    number=row.number,
                    icon=row.icon or "·",
                    title=row.title.strip(),
                    detail=row.detail,
                    width=width,
                    selected=i == index,
                )
            )
        else:
            marker = ">" if i == index else " "
            detail = f" {_c(WHITE, row.detail)}" if row.detail else ""
            lines.append(f"  {marker}  {_c(row.color, row.title)}{detail}")
    block = "\n".join(lines)
    if not first:
        sys.stdout.write(f"\033[{len(lines)}A\r")
    sys.stdout.write(block)
    if not block.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def choose_item(
    rows: Sequence[MenuRow],
    *,
    index: int = 0,
    number_keys: bool = False,
    redraw: Callable[[int], None] | None = None,
    width: int = 80,
) -> str:
    if not rows:
        raise ValueError("choose_item requires at least one row")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Pass a flag when stdin is not a terminal.")

    index = index % len(rows)
    numbered = min(9, len(rows)) if number_keys else 0
    hide_cursor()
    try:
        if redraw:
            redraw(index)
        else:
            _draw(rows, index, first=True, width=width)
        while True:
            key = read_key(number_keys=numbered)
            if key == "up":
                index = (index - 1) % len(rows)
            elif key == "down":
                index = (index + 1) % len(rows)
            elif numbered and key in {str(i) for i in range(1, numbered + 1)}:
                index = int(key) - 1
            elif key == "enter":
                return rows[index].id
            elif key in {"back", "esc"} and any(row.id == "back" for row in rows):
                return "back"
            elif key == "quit":
                raise SystemExit(0)
            if redraw:
                redraw(index)
            else:
                _draw(rows, index, first=False, width=width)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        show_cursor()


def leave_home_for_workflow() -> None:
    """Keep the banner pinned so Analyze / Plan / Implement logs scroll under it."""
    pin_banner()


def wait_for_menu() -> None:
    """Keep the workflow log visible until the operator dismisses it."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return
    print("", flush=True)
    print("Press enter to return to the menu.", flush=True)
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


def choose_phase(
    *,
    legacy_repo: str,
    modern_repo: str,
    model: str,
    index: int = 0,
) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit(
            "Pass analyze, plan, or implement when stdin is not a terminal."
        )
    rows = [
        MenuRow(
            id=key,
            title=title,
            detail=detail,
            number=number,
            icon=icon,
        )
        for key, number, icon, title, detail in HOME_ITEMS
    ]
    menu_rows = [(number, icon, title, detail) for _, number, icon, title, detail in HOME_ITEMS]

    def redraw(selected: int) -> None:
        print_home(
            legacy_repo=legacy_repo,
            modern_repo=modern_repo,
            model=model,
            menu_rows=menu_rows,
            selected=selected,
        )

    return choose_item(rows, index=index, number_keys=True, redraw=redraw)
