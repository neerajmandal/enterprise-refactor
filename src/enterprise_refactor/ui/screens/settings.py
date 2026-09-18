"""Session-only overrides for repos and the API key."""

from __future__ import annotations

import sys
from getpass import getpass

from enterprise_refactor.config import Config, apply_session, clean, is_repo
from enterprise_refactor.ui.layout import (
    paint_menu_row,
    print_screen,
    render_page,
    repo_label,
    term_size,
)
from enterprise_refactor.ui.screens.home import MenuRow, choose_item

FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("legacy_repo", "1", "Legacy repo", "source git URL or owner/repo"),
    ("modern_repo", "2", "Modern repo", "target git URL or owner/repo"),
    ("api_key", "3", "API key", "session only — never written to .env"),
    ("back", "4", "Back", "return to the home menu"),
)


def _preview(config: Config, key: str) -> str:
    if key == "api_key":
        return "set" if config.api_key.strip() else "missing"
    if key == "back":
        return "return to the home menu"
    value = str(getattr(config, key) or "")
    return repo_label(value) if value else "(unset)"


def _edit_field(config: Config, key: str) -> None:
    if key == "api_key":
        raw = getpass("API key (blank keeps current; not saved to .env): ")
        value = clean(raw)
        if value:
            config.api_key = value
        apply_session(config)
        return

    current = str(getattr(config, key) or "")
    label = next(title for field, _, title, _ in FIELDS if field == key)
    raw = input(f"{label} [{current}]: ")
    value = clean(raw)
    if not value:
        return
    if not is_repo(value):
        print("Enter a git URL or owner/repo.", file=sys.stderr)
        input("Press enter to continue.")
        return
    setattr(config, key, value)
    apply_session(config)


def edit_settings(config: Config) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Settings needs a terminal.")

    index = 0
    while True:
        rows = [
            MenuRow(
                id=key,
                title=title,
                detail=_preview(config, key),
                number=number,
            )
            for key, number, title, _ in FIELDS
        ]

        def redraw(selected: int, rows: list[MenuRow] = rows) -> None:
            width, _ = term_size()
            body = [
                paint_menu_row(
                    number=row.number,
                    icon="·",
                    title=row.title,
                    detail=row.detail,
                    width=width,
                    selected=i == selected,
                )
                for i, row in enumerate(rows)
            ]
            print_screen(
                render_page(
                    legacy_repo=config.legacy_repo,
                    modern_repo=config.modern_repo,
                    cursor_env=config.cursor_env,
                    model=config.model,
                    body=body,
                )
            )

        choice = choose_item(rows, index=index, number_keys=True, redraw=redraw)
        if choice == "back":
            return
        index = next(i for i, (key, _, _, _) in enumerate(FIELDS) if key == choice)
        sys.stdout.write("\033[?25h")
        _edit_field(config, choice)
