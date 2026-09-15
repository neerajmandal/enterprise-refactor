"""Arrow-key picker for the Analyze / Plan / Implement phases."""

from __future__ import annotations

import sys
import termios
import tty
from collections.abc import Sequence
from dataclasses import dataclass

from enterprise_refactor.banner import AMBER, CYAN, LIME, MOSS, WHITE, _c

PHASES: tuple[tuple[str, str, str, str], ...] = (
    ("analyze", "Analyze", "branch the legacy repo and map the system", LIME),
    ("plan", "Plan", "ask for a goal, then write phased subtask plans", CYAN),
    ("implement", "Implement", "run every phase unattended, then record a walkthrough", AMBER),
    ("exit", "Exit", "leave the CLI", MOSS),
)


@dataclass(frozen=True)
class MenuRow:
    id: str
    title: str
    detail: str = ""
    color: str = WHITE


def _hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _read_key(*, number_keys: int = 0) -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = sys.stdin.read(1)
        if first == "\x03":
            raise KeyboardInterrupt
        if first in {"\r", "\n"}:
            return "enter"
        if first in {"q", "Q"}:
            return "quit"
        if number_keys and first in {str(i) for i in range(1, number_keys + 1)}:
            return first
        if first in {"k", "K"}:
            return "up"
        if first in {"j", "J"}:
            return "down"
        if first != "\x1b":
            return first
        rest = sys.stdin.read(2)
        if rest == "[A":
            return "up"
        if rest == "[B":
            return "down"
        return "esc"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _draw(rows: Sequence[MenuRow], index: int, *, first: bool) -> None:
    lines: list[str] = []
    for i, row in enumerate(rows):
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
) -> str:
    if not rows:
        raise ValueError("choose_item requires at least one row")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Pass a flag when stdin is not a terminal.")

    index = index % len(rows)
    numbered = min(9, len(rows)) if number_keys else 0
    _hide_cursor()
    try:
        _draw(rows, index, first=True)
        while True:
            key = _read_key(number_keys=numbered)
            if key == "up":
                index = (index - 1) % len(rows)
            elif key == "down":
                index = (index + 1) % len(rows)
            elif numbered and key in {str(i) for i in range(1, numbered + 1)}:
                index = int(key) - 1
            elif key == "enter":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return rows[index].id
            elif key == "quit":
                raise SystemExit(0)
            _draw(rows, index, first=False)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        _show_cursor()


def choose_phase(index: int = 0) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit(
            "Pass analyze, plan, or implement when stdin is not a terminal."
        )
    rows = [
        MenuRow(id=key, title=f"{title:<11}", detail=detail, color=color)
        for key, title, detail, color in PHASES
    ]
    return choose_item(rows, index=index, number_keys=True)
