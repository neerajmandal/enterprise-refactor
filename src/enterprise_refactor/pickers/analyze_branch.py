"""TUI to pick the legacy analyze branch Plan will read."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from enterprise_refactor.config import Config, ask, clean
from enterprise_refactor.git.branch_list import (
    ANALYZE_PREFIX,
    default_branch_index,
    list_remote_branches,
)
from enterprise_refactor.state import WorkflowState
from enterprise_refactor.ui.banner import (
    DIM,
    MUTED,
    WHITE,
    _c,
    paint_menu_row,
    print_screen,
    render_page,
    repo_label,
    term_size,
)
from enterprise_refactor.ui.keys import hide_cursor, read_key, show_cursor

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_PICKER_WINDOW = 16


def _stamp_when(name: str, prefix: str) -> str:
    stamp = name.removeprefix(prefix)
    if len(stamp) != 8 or not stamp.isdigit():
        return ""
    month = int(stamp[4:6])
    day = int(stamp[6:8])
    if month < 1 or month > 12 or day < 1 or day > 31:
        return ""
    return f"{day:>2} {_MONTHS[month - 1]} {stamp[:4]}"


def _kind_for(
    name: str, kinds: Sequence[tuple[str, str, str]]
) -> tuple[str, str, str]:
    for prefix, label, badge in kinds:
        if name.startswith(prefix):
            return prefix, label, badge
    return "", "Other", ""


def _badge(
    name: str, *, prefix: str, default: str, saved: str, kind_badge: str
) -> str:
    if name == default and (not prefix or name.startswith(prefix)):
        return "recommended"
    if name == saved:
        return "last used"
    if prefix and name.startswith(prefix):
        return kind_badge
    return ""


def _window(total: int, index: int, size: int) -> tuple[int, int]:
    if total <= size:
        return 0, total
    start = min(max(0, index - size // 2), total - size)
    return start, start + size


def _picker_window(height: int) -> int:
    return max(5, min(_PICKER_WINDOW, height - 26))


def _branch_detail(
    name: str, *, prefix: str, default: str, saved: str, kind_badge: str
) -> str:
    parts = [
        part
        for part in (
            _stamp_when(name, prefix),
            _badge(
                name, prefix=prefix, default=default, saved=saved, kind_badge=kind_badge
            ),
        )
        if part
    ]
    return "   ".join(parts)


def _kinds(
    preferred_prefix: str,
    preferred_label: str,
    kind_badge: str,
    preferred_kinds: Sequence[tuple[str, str, str]] | None,
) -> tuple[tuple[str, str, str], ...]:
    if preferred_kinds:
        return tuple(preferred_kinds)
    return ((preferred_prefix, preferred_label, kind_badge),)


def render_branch_picker(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    title: str,
    subtitle: str,
    preferred_prefix: str,
    preferred_label: str,
    kind_badge: str,
    names: list[str],
    index: int,
    default: str,
    saved: str,
    preferred_kinds: Sequence[tuple[str, str, str]] | None = None,
) -> str:
    width, height = term_size()
    kinds = _kinds(preferred_prefix, preferred_label, kind_badge, preferred_kinds)
    bits: list[str] = []
    for prefix, _label, badge in kinds:
        n = sum(1 for name in names if name.startswith(prefix))
        if n:
            bits.append(f"{n} {badge}")
    count = f"{len(names)} branch" + ("es" if len(names) != 1 else "")
    extra = f"  ·  {' · '.join(bits)}" if bits else ""
    start, end = _window(
        len(names), index if index < len(names) else 0, _picker_window(height)
    )
    body = [
        _c(WHITE, f"  {title}"),
        _c(DIM, f"  {subtitle}"),
        "",
        f"  {_c(DIM, 'Remote'.ljust(16))}{_c(WHITE, count + extra)}",
        "",
    ]
    if start > 0:
        body.append(_c(MUTED, f"  ↑  {start} more"))

    last_kind = ""
    for i in range(start, end):
        name = names[i]
        prefix, kind, badge = _kind_for(name, kinds)
        if kind != last_kind:
            if last_kind:
                body.append("")
            body.append(_c(MUTED, f"  {kind}"))
            last_kind = kind
        body.append(
            paint_menu_row(
                number="",
                icon="⌕" if prefix else "·",
                title=name,
                detail=_branch_detail(
                    name,
                    prefix=prefix or preferred_prefix,
                    default=default,
                    saved=saved,
                    kind_badge=badge or kind_badge,
                ),
                width=width,
                selected=i == index,
                title_col=36,
            )
        )

    if end < len(names):
        body.append(_c(MUTED, f"  ↓  {len(names) - end} more"))

    body.append("")
    body.append(
        paint_menu_row(
            number="",
            icon="←",
            title="Back",
            detail="return to the home menu",
            width=width,
            selected=index == len(names),
            title_col=36,
        )
    )

    return render_page(
        legacy_repo=legacy_repo,
        modern_repo=modern_repo,
        cursor_env=cursor_env,
        model=model,
        body=body,
    )


def choose_remote_branch(
    names: list[str],
    *,
    config: Config,
    title: str,
    subtitle: str,
    preferred_prefix: str,
    preferred_label: str,
    kind_badge: str,
    default: str,
    saved: str,
    index: int,
    preferred_kinds: Sequence[tuple[str, str, str]] | None = None,
) -> str | None:
    total = len(names) + 1
    index = index % total
    hide_cursor()
    try:
        while True:
            print_screen(
                render_branch_picker(
                    legacy_repo=config.legacy_repo,
                    modern_repo=config.modern_repo,
                    cursor_env=config.cursor_env,
                    model=config.model,
                    title=title,
                    subtitle=subtitle,
                    preferred_prefix=preferred_prefix,
                    preferred_label=preferred_label,
                    kind_badge=kind_badge,
                    names=names,
                    index=index,
                    default=default,
                    saved=saved,
                    preferred_kinds=preferred_kinds,
                )
            )
            key = read_key()
            if key == "up":
                index = (index - 1) % total
            elif key == "down":
                index = (index + 1) % total
            elif key == "enter":
                if index == len(names):
                    return None
                return names[index]
            elif key in {"back", "esc"}:
                return None
            elif key == "quit":
                raise SystemExit(0)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        show_cursor()


def resolve_remote_branch(
    config: Config,
    *,
    title: str,
    subtitle: str,
    repo_url: str,
    preferred_prefix: str,
    preferred_label: str,
    kind_badge: str,
    saved: str,
    fallback: str,
    flagged: str | None,
    ask_label: str,
    missing_hint: str,
    preferred_kinds: Sequence[tuple[str, str, str]] | None = None,
) -> str | None:
    chosen = clean(flagged or "")
    if chosen:
        return chosen
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if saved:
            return saved
        raise SystemExit(missing_hint)

    kinds = _kinds(preferred_prefix, preferred_label, kind_badge, preferred_kinds)
    prefixes = tuple(prefix for prefix, _, _ in kinds)

    print_screen(
        render_page(
            legacy_repo=config.legacy_repo,
            modern_repo=config.modern_repo,
            cursor_env=config.cursor_env,
            model=config.model,
            body=[
                _c(WHITE, f"  {title}"),
                _c(DIM, f"  Listing remotes on {repo_label(repo_url)}…"),
            ],
        )
    )
    names, error = list_remote_branches(
        repo_url, preferred_prefix=prefixes
    )
    if not names:
        if error:
            print_screen(
                render_page(
                    legacy_repo=config.legacy_repo,
                    modern_repo=config.modern_repo,
                    cursor_env=config.cursor_env,
                    model=config.model,
                    body=[
                        _c(WHITE, f"  {title}"),
                        _c(DIM, f"  Could not list remote branches on {repo_label(repo_url)}."),
                        "",
                        _c(MUTED, f"  {error}"),
                        "",
                        _c(DIM, "  Enter a branch name to continue."),
                    ],
                )
            )
        return ask(ask_label)

    index = default_branch_index(
        names,
        preferred_prefix=prefixes,
        saved=saved,
        fallback=fallback,
    )
    return choose_remote_branch(
        names,
        config=config,
        title=title,
        subtitle=subtitle,
        preferred_prefix=preferred_prefix,
        preferred_label=preferred_label,
        kind_badge=kind_badge,
        default=names[index],
        saved=saved,
        index=index,
        preferred_kinds=kinds,
    )


def resolve_legacy_plan_branch(
    config: Config,
    state: WorkflowState,
    *,
    analyze_branch: str | None,
) -> str | None:
    return resolve_remote_branch(
        config,
        title="Plan",
        subtitle="Choose the legacy branch Plan will fetch and read.",
        repo_url=config.legacy_repo,
        preferred_prefix=ANALYZE_PREFIX,
        preferred_label="Analyze",
        kind_badge="analyze",
        saved=state.analyze_branch,
        fallback=config.legacy_ref,
        flagged=analyze_branch,
        ask_label="Legacy branch",
        missing_hint=(
            "Pass --analyze-branch or run this command in a terminal "
            "to pick a legacy branch."
        ),
    )
