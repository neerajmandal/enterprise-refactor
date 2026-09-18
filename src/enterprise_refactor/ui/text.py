"""Full-screen text field that can backspace across wrapped lines."""

from __future__ import annotations

import sys
import textwrap

from enterprise_refactor.config import Config, clean
from enterprise_refactor.ui.input import (
    hide_cursor,
    raw_text_input,
    read_edit_event,
    show_cursor,
)
from enterprise_refactor.ui.layout import (
    DIM,
    MUTED,
    WHITE,
    _c,
    print_screen,
    render_page,
    term_size,
)

FOOTER_EDIT: tuple[tuple[str, str], ...] = (
    ("type", "edit"),
    ("⌘v", "paste"),
    ("⌫", "delete"),
    ("enter", "continue"),
    ("esc", "back"),
)


def _wrap_field(text: str, width: int) -> list[str]:
    inner = max(20, width - 4)
    if not text:
        return [""]
    lines = textwrap.wrap(
        text,
        width=inner,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )
    return lines or [""]


def ask_long_text(
    config: Config,
    *,
    title: str,
    label: str,
) -> str | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit(f"{label} is missing. Pass --prompt or set CURSOR_PLAN_PROMPT.")

    buffer = ""
    hint = ""
    hide_cursor()
    try:
        with raw_text_input() as fd:
            while True:
                width, _height = term_size()
                wrapped = _wrap_field(buffer, width)
                if wrapped:
                    wrapped[-1] = wrapped[-1] + "_"
                else:
                    wrapped = ["_"]
                body = [
                    _c(WHITE, f"  {title}"),
                    _c(DIM, f"  {label}"),
                    "",
                ]
                if hint:
                    body.extend([_c(MUTED, f"  {hint}"), ""])
                body.extend(f"  {line}" for line in wrapped)
                print_screen(
                    render_page(
                        legacy_repo=config.legacy_repo,
                        modern_repo=config.modern_repo,
                        model=config.model,
                        body=body,
                        footer_actions=FOOTER_EDIT,
                    )
                )
                kind, payload = read_edit_event(fd)
                hint = ""
                if kind == "enter":
                    value = clean(buffer)
                    if value:
                        return value
                    hint = "Value required."
                    continue
                if kind == "cancel":
                    return None
                if kind == "ignore":
                    continue
                if kind == "backspace":
                    buffer = buffer[:-1]
                    continue
                if kind == "insert":
                    buffer += payload
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        show_cursor()
