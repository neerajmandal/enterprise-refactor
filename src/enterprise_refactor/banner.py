"""Home-screen chrome: pixel title, connection meta, and menu frame."""

from __future__ import annotations

import os
import re
import shutil
import sys
from urllib.parse import urlparse

RESET = "\033[0m"
GREEN = "\033[38;5;40m"
LIME = "\033[38;5;46m"
FOREST = "\033[38;5;34m"
MOSS = "\033[38;5;65m"
MINT = "\033[38;5;151m"
CYAN = "\033[38;5;81m"
AMBER = "\033[38;5;214m"
WHITE = "\033[38;5;255m"
DIM = "\033[38;5;245m"
MUTED = "\033[38;5;240m"
RULE = "\033[38;5;236m"
SELECT_FG = "\033[38;5;193m"
SELECT_BG = "\033[48;5;22m"
KEY_BG = "\033[48;5;236m"
ANSI = re.compile(r"\033\[[0-9;]*m|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b.")

VERSION = "v0.1.0"
TAGLINE_TOP = "Modernize with confidence."
TAGLINE_BOTTOM = "One step at a time."
FOOTER_HOME: tuple[tuple[str, str], ...] = (
    ("↑↓", "navigate"),
    ("enter", "select"),
    ("q", "quit"),
)
FOOTER_PAGE: tuple[tuple[str, str], ...] = (
    ("↑↓", "navigate"),
    ("enter", "select"),
    ("esc", "back"),
    ("q", "quit"),
)

# 5-row pixel glyphs. Last column is the letter gap.
_GLYPHS: dict[str, tuple[str, str, str, str, str]] = {
    "R": (
        "████ ",
        "█  █ ",
        "████ ",
        "█ █  ",
        "█  █ ",
    ),
    "E": (
        "████ ",
        "█    ",
        "███  ",
        "█    ",
        "████ ",
    ),
    "F": (
        "████ ",
        "█    ",
        "███  ",
        "█    ",
        "█    ",
    ),
    "A": (
        " ██  ",
        "█  █ ",
        "████ ",
        "█  █ ",
        "█  █ ",
    ),
    "C": (
        " ███ ",
        "█    ",
        "█    ",
        "█    ",
        " ███ ",
    ),
    "T": (
        "████ ",
        "  █  ",
        "  █  ",
        "  █  ",
        "  █  ",
    ),
    "O": (
        " ██  ",
        "█  █ ",
        "█  █ ",
        "█  █ ",
        " ██  ",
    ),
}


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _color_enabled():
        return text
    return f"{code}{text}{RESET}"


def _visible_len(text: str) -> int:
    return len(ANSI.sub("", text))


def term_size() -> tuple[int, int]:
    size = shutil.get_terminal_size((100, 32))
    return max(72, size.columns), max(24, size.lines)


def repo_label(url: str) -> str:
    raw = ANSI.sub("", url or "").strip()
    if not raw or raw in {"[A", "[B", "[C", "[D"}:
        return "(not connected)"
    if "://" not in raw and raw.count("/") == 1:
        return raw
    path = raw
    try:
        parsed = urlparse(raw)
        path = parsed.path.strip("/") or parsed.netloc or raw
    except ValueError:
        path = raw.split("://", 1)[-1].split("?", 1)[0].strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[0] if parts else raw


def _pixel_word(word: str) -> list[str]:
    rows = [""] * 5
    for ch in word.upper():
        glyph = _GLYPHS.get(ch)
        if glyph is None:
            continue
        for i, piece in enumerate(glyph):
            rows[i] += piece + " "
    return [row.rstrip() for row in rows]


def _join_ends(left: str, right: str, width: int) -> str:
    gap = width - _visible_len(left) - _visible_len(right)
    if gap < 1:
        return left[:width]
    return left + " " * gap + right


def _rule(width: int) -> str:
    return _c(RULE, "─" * width)


def _meta_row(label: str, value: str, width: int) -> str:
    label_w = 16
    left = f"  {_c(DIM, label.ljust(label_w))}"
    right = _c(WHITE, value)
    line = left + right
    pad = max(0, width - _visible_len(line))
    return line + " " * pad


def header_lines(
    *,
    width: int,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
) -> list[str]:
    env_name = cursor_env.strip() or "(unset)"
    model_name = model.strip() or "(unset)"
    source = repo_label(legacy_repo) if legacy_repo.strip() else "(not connected)"
    target = repo_label(modern_repo) if modern_repo.strip() else "(not connected)"

    title = _pixel_word("REFACTOR")
    col_w = max(len(VERSION), len(TAGLINE_TOP), len(TAGLINE_BOTTOM))
    right = [
        _c(DIM, VERSION.ljust(col_w)),
        "",
        _c(DIM, TAGLINE_TOP.ljust(col_w)),
        _c(DIM, TAGLINE_BOTTOM.ljust(col_w)),
        "",
    ]
    title_block = [
        _join_ends("  " + _c(LIME, title[i]), right[i] + "  ", width)
        for i in range(5)
    ]
    subtitle = (
        "  "
        + _c(LIME, "analyze")
        + _c(MUTED, "  →  ")
        + _c(CYAN, "plan")
        + _c(MUTED, "  →  ")
        + _c(AMBER, "implement")
    )
    return [
        "",
        *title_block,
        "",
        subtitle,
        "",
        _rule(width),
        "",
        _meta_row("Environment", env_name, width),
        _meta_row("Model", model_name, width),
        _meta_row("Source repo", source, width),
        _meta_row("Target repo", target, width),
        "",
        _rule(width),
        "",
    ]


def footer_line(
    width: int,
    *,
    actions: tuple[tuple[str, str], ...] = FOOTER_HOME,
) -> str:
    parts = [
        f"{_c(KEY_BG + WHITE, f' {key} ')} {_c(DIM, label)}"
        for key, label in actions
    ]
    left = "  " + "   ".join(parts)
    return left + " " * max(0, width - _visible_len(left))


def paint_menu_row(
    *,
    number: str,
    icon: str,
    title: str,
    detail: str,
    width: int,
    selected: bool,
    title_col: int = 28,
) -> str:
    if number.strip():
        left_plain = f"  {number}  {icon}  {title}"
        painted_left = f"  {_c(MUTED, number)}  {_c(DIM, icon)}  {_c(WHITE, title)}"
    else:
        left_plain = f"  {icon}  {title}"
        painted_left = f"  {_c(DIM, icon)}  {_c(WHITE, title)}"
    left_plain += " " * max(1, title_col - _visible_len(left_plain))
    painted_left += " " * max(1, title_col - _visible_len(painted_left))
    body = f"{left_plain}{detail}"
    pad = max(0, width - _visible_len(body))
    body = body + " " * pad
    if selected:
        return _c(SELECT_BG + SELECT_FG, body)
    painted = painted_left + _c(DIM, detail)
    return painted + " " * max(0, width - _visible_len(painted))


def frame_screen(
    body: list[str],
    *,
    width: int,
    height: int,
    footer_actions: tuple[tuple[str, str], ...] = FOOTER_HOME,
) -> str:
    lines = list(body)
    while len(lines) < height - 2:
        lines.append("")
    lines.append(_rule(width))
    lines.append(footer_line(width, actions=footer_actions))
    if len(lines) > height:
        lines = lines[: height - 2] + lines[-2:]
    return "\n".join(lines) + "\n"


def render(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    ready: bool,
) -> str:
    width, height = term_size()
    lines = header_lines(
        width=width,
        legacy_repo=legacy_repo,
        modern_repo=modern_repo,
        cursor_env=cursor_env,
        model=model,
    )
    if ready:
        lines.append(_c(MOSS, "  Use the menu to continue."))
    else:
        lines.append(_c(MOSS, "  Waiting for connection details."))
    return frame_screen(lines, width=width, height=height)


def render_home(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    menu_rows: list[tuple[str, str, str, str]],
    selected: int,
) -> str:
    width, height = term_size()
    lines = header_lines(
        width=width,
        legacy_repo=legacy_repo,
        modern_repo=modern_repo,
        cursor_env=cursor_env,
        model=model,
    )
    for i, (number, icon, title, detail) in enumerate(menu_rows):
        lines.append(
            paint_menu_row(
                number=number,
                icon=icon,
                title=title,
                detail=detail,
                width=width,
                selected=i == selected,
            )
        )
    return frame_screen(lines, width=width, height=height)


def render_page(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    body: list[str],
    footer_actions: tuple[tuple[str, str], ...] = FOOTER_PAGE,
) -> str:
    width, height = term_size()
    lines = header_lines(
        width=width,
        legacy_repo=legacy_repo,
        modern_repo=modern_repo,
        cursor_env=cursor_env,
        model=model,
    )
    lines.extend(body)
    return frame_screen(
        lines, width=width, height=height, footer_actions=footer_actions
    )


def clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def print_screen(text: str) -> None:
    clear_screen()
    sys.stdout.write(text)
    sys.stdout.flush()


def print_banner(**kwargs: str | bool) -> None:
    print_screen(render(**kwargs))


def print_home(**kwargs: object) -> None:
    print_screen(render_home(**kwargs))
