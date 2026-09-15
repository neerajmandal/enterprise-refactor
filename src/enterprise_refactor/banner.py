"""Green terminal art for the refactor agent splash."""

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
MINT = "\033[38;5;121m"
CYAN = "\033[38;5;81m"
AMBER = "\033[38;5;214m"
WHITE = "\033[38;5;255m"
ANSI = re.compile(r"\033\[[0-9;]*m|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b.")

TITLE = [
    r"  ╦═╗╔═╗╔═╗╔═╗╔═╗╔╦╗╔═╗╦═╗   ╔═╗╔═╗╔═╗╔╗╔╔╦╗",
    r"  ╠╦╝║╣ ╠╣ ╠═╣║   ║ ║ ║╠╦╝   ╠═╣║ ╦║╣ ║║║ ║ ",
    r"  ╩╚═╚═╝╚  ╩ ╩╚═╝ ╩ ╚═╝╩╚═   ╩ ╩╚═╝╚═╝╝╚╝ ╩ ",
]


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


def _center_line(line: str, width: int) -> str:
    pad = max(0, width - _visible_len(line))
    return " " * (pad // 2) + line


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


def _box(title: str, status: str, detail: str, width: int) -> list[str]:
    inner = width - 2
    return [
        "┌" + "─" * inner + "┐",
        "│" + f" {title}"[:inner].ljust(inner) + "│",
        "│" + f" {status}"[:inner].ljust(inner) + "│",
        "│" + f" {detail}"[:inner].ljust(inner) + "│",
        "└" + "─" * inner + "┘",
    ]


def _color_box(lines: list[str], code: str) -> list[str]:
    return [_c(code, line) for line in lines]


def _fork(left_center: int, mid: int, right_center: int) -> list[str]:
    """Env drops from mid, then splits to both repos."""
    span = right_center - left_center
    stem = " " * mid + "│"
    bar = (
        " " * left_center
        + "┌"
        + "─" * (mid - left_center - 1)
        + "┴"
        + "─" * (right_center - mid - 1)
        + "┐"
    )
    drops = " " * left_center + "│" + " " * (span - 1) + "│"
    arrows = " " * left_center + "▼" + " " * (span - 1) + "▼"
    return [_c(LIME, stem), _c(LIME, bar), _c(LIME, drops), _c(LIME, arrows)]


def render(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    ready: bool,
) -> str:
    legacy_name = repo_label(legacy_repo)
    modern_name = repo_label(modern_repo)
    env_name = cursor_env.strip() or "Cursor Cloud"
    model_name = model.strip() or "(unset)"
    legacy_ok = bool(legacy_repo.strip())
    modern_ok = bool(modern_repo.strip())
    env_ok = bool(env_name)

    repo_w = 28
    gap = 6
    row_w = repo_w * 2 + gap
    env_w = 32
    left_center = repo_w // 2
    right_center = repo_w + gap + repo_w // 2
    mid = row_w // 2

    env_box = [
        _center_line(line, row_w)
        for line in _color_box(
            _box(
                "CURSOR ENV",
                "● connected" if env_ok else "○ missing",
                env_name,
                env_w,
            ),
            LIME,
        )
    ]
    legacy_box = _color_box(
        _box(
            "LEGACY SOURCE",
            "● connected" if legacy_ok else "○ missing",
            legacy_name,
            repo_w,
        ),
        FOREST,
    )
    modern_box = _color_box(
        _box(
            "MODERN TARGET",
            "● connected" if modern_ok else "○ missing",
            modern_name,
            repo_w,
        ),
        GREEN,
    )
    repos = [
        left + " " * gap + right for left, right in zip(legacy_box, modern_box)
    ]
    lines = ["", *(_c(LIME, line) for line in TITLE), ""]
    lines.append(_c(MINT, "           analyze · plan · implement"))
    lines.append("")
    lines.extend(env_box)
    lines.extend(_fork(left_center, mid, right_center))
    lines.extend(repos)
    lines.append("")
    lines.append(_center_line(_c(MINT, f"model  {model_name}"), row_w))
    lines.append("")
    if ready:
        lines.append(_c(LIME, "  status  CLI ready"))
    else:
        lines.append(_c(MOSS, "  status  waiting for connection details"))
    lines.append("")
    return "\n".join(lines)


def print_banner(**kwargs: str | bool) -> None:
    art = render(**kwargs)
    shutil.get_terminal_size((100, 24))
    sys.stdout.write(art)
    sys.stdout.flush()
