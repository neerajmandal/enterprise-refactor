"""Arrow-key picker for the Analyze / Plan / Implement phases."""

from __future__ import annotations

import sys
import termios
import tty

from enterprise_refactor.banner import AMBER, CYAN, LIME, WHITE, _c

PHASES: tuple[tuple[str, str, str, str], ...] = (
    ("analyze", "Analyze", "branch the legacy repo and map the system", LIME),
    ("plan", "Plan", "write modular phase plans on a target-repo branch", CYAN),
    ("implement", "Implement", "run every phase unattended, then record a walkthrough", AMBER),
)


def _hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _read_key() -> str:
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
        if first in {"1", "2", "3"}:
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


def _draw(index: int, *, first: bool) -> None:
    rows: list[str] = []
    for i, (_, title, detail, color) in enumerate(PHASES):
        marker = ">" if i == index else " "
        rows.append(
            f"  {marker}  {_c(color, f'{title:<11}')} {_c(WHITE, detail)}"
        )
    block = "\n".join(rows)
    if not first:
        sys.stdout.write(f"\033[{len(rows)}A\r")
    sys.stdout.write(block)
    if not block.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def choose_phase() -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit(
            "Pass analyze, plan, or implement when stdin is not a terminal."
        )

    index = 0
    _hide_cursor()
    try:
        _draw(index, first=True)
        while True:
            key = _read_key()
            if key == "up":
                index = (index - 1) % len(PHASES)
            elif key == "down":
                index = (index + 1) % len(PHASES)
            elif key in {"1", "2", "3"}:
                index = int(key) - 1
            elif key == "enter":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return PHASES[index][0]
            elif key == "quit":
                raise SystemExit(0)
            _draw(index, first=False)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        _show_cursor()
