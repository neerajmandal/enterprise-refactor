"""List and resolve legacy git branches for Plan."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from enterprise_refactor.banner import (
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
from enterprise_refactor.config import Config, ask, clean
from enterprise_refactor.menu import _hide_cursor, _read_key, _show_cursor
from enterprise_refactor.state import WorkflowState

_ANALYZE_PREFIX = "refactor/analyze-"


def github_owner_repo(url: str) -> tuple[str, str] | None:
    raw = (url or "").strip()
    if raw.endswith(".git"):
        raw = raw[:-4]
    if raw.startswith("git@"):
        path = raw.split(":", 1)[-1]
    elif "://" in raw:
        path = urlparse(raw).path.strip("/")
    else:
        path = raw
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def remote_url(url: str) -> str:
    value = (url or "").strip()
    if value.startswith(("http://", "https://", "git@")):
        return value
    owner_repo = github_owner_repo(value)
    if owner_repo is None:
        return value
    owner, repo = owner_repo
    return f"https://github.com/{owner}/{repo}.git"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _branches_from_gh(url: str) -> list[str] | None:
    owner_repo = github_owner_repo(url)
    if owner_repo is None or shutil.which("gh") is None:
        return None
    owner, repo = owner_repo
    output = _run(
        [
            "gh",
            "api",
            "--paginate",
            "-q",
            ".[].name",
            f"repos/{owner}/{repo}/branches?per_page=100",
        ]
    )
    if output is None:
        return None
    names = [line.strip() for line in output.splitlines() if line.strip()]
    return names or None


def _branches_from_ls_remote(url: str) -> list[str] | None:
    if shutil.which("git") is None:
        return None
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    output = _run(
        ["git", "ls-remote", "--heads", remote_url(url)],
        env=env,
    )
    if output is None:
        return None
    names: list[str] = []
    prefix = "refs/heads/"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[-1].startswith(prefix):
            continue
        names.append(parts[-1][len(prefix) :])
    return names or None


def sort_branch_names(names: list[str]) -> list[str]:
    analyze = sorted(
        (name for name in names if name.startswith(_ANALYZE_PREFIX)),
        reverse=True,
    )
    rest = sorted(name for name in names if not name.startswith(_ANALYZE_PREFIX))
    return analyze + rest


def list_remote_branches(url: str) -> tuple[list[str], str]:
    seen: set[str] = set()
    names: list[str] = []
    for group in (_branches_from_ls_remote(url), _branches_from_gh(url)):
        for name in group or ():
            if name not in seen:
                seen.add(name)
                names.append(name)
    if names:
        return sort_branch_names(names), ""
    return [], "Could not list remote branches on the legacy repo."


def default_branch_index(
    names: list[str], *, saved: str, fallback: str
) -> int:
    analyze = [name for name in names if name.startswith(_ANALYZE_PREFIX)]
    if analyze:
        return names.index(analyze[0])
    if saved and saved in names:
        return names.index(saved)
    if fallback and fallback in names:
        return names.index(fallback)
    if "main" in names:
        return names.index("main")
    return 0


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


def _analyze_when(name: str) -> str:
    stamp = name.removeprefix(_ANALYZE_PREFIX)
    if len(stamp) != 8 or not stamp.isdigit():
        return ""
    month = int(stamp[4:6])
    day = int(stamp[6:8])
    if month < 1 or month > 12 or day < 1 or day > 31:
        return ""
    return f"{day:>2} {_MONTHS[month - 1]} {stamp[:4]}"


def _badge(name: str, *, default: str, saved: str) -> str:
    if name == default and name.startswith(_ANALYZE_PREFIX):
        return "recommended"
    if name == saved:
        return "last used"
    if name.startswith(_ANALYZE_PREFIX):
        return "analyze"
    return ""


def _window(total: int, index: int, size: int) -> tuple[int, int]:
    if total <= size:
        return 0, total
    start = min(max(0, index - size // 2), total - size)
    return start, start + size


def _picker_window(height: int) -> int:
    return max(5, min(_PICKER_WINDOW, height - 26))


def _branch_detail(name: str, *, default: str, saved: str) -> str:
    parts = [part for part in (_analyze_when(name), _badge(name, default=default, saved=saved)) if part]
    return "   ".join(parts)


def render_branch_picker(
    *,
    legacy_repo: str,
    modern_repo: str,
    cursor_env: str,
    model: str,
    names: list[str],
    index: int,
    default: str,
    saved: str,
) -> str:
    width, height = term_size()
    analyze = [name for name in names if name.startswith(_ANALYZE_PREFIX)]
    count = f"{len(names)} branch" + ("es" if len(names) != 1 else "")
    extra = f"  ·  {len(analyze)} analyze" if analyze else ""
    start, end = _window(len(names), index if index < len(names) else 0, _picker_window(height))
    body = [
        _c(WHITE, "  Plan"),
        _c(DIM, "  Choose the legacy branch Plan will fetch and read."),
        "",
        f"  {_c(DIM, 'Remote'.ljust(16))}{_c(WHITE, count + extra)}",
        "",
    ]
    if start > 0:
        body.append(_c(MUTED, f"  ↑  {start} more"))

    last_kind = ""
    for i in range(start, end):
        name = names[i]
        kind = "Analyze" if name.startswith(_ANALYZE_PREFIX) else "Other"
        if kind != last_kind:
            if last_kind:
                body.append("")
            body.append(_c(MUTED, f"  {kind}"))
            last_kind = kind
        body.append(
            paint_menu_row(
                number="",
                icon="⌕" if name.startswith(_ANALYZE_PREFIX) else "·",
                title=name,
                detail=_branch_detail(name, default=default, saved=saved),
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
    default: str,
    saved: str,
    index: int,
) -> str | None:
    total = len(names) + 1
    index = index % total
    _hide_cursor()
    try:
        while True:
            print_screen(
                render_branch_picker(
                    legacy_repo=config.legacy_repo,
                    modern_repo=config.modern_repo,
                    cursor_env=config.cursor_env,
                    model=config.model,
                    names=names,
                    index=index,
                    default=default,
                    saved=saved,
                )
            )
            key = _read_key()
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
        _show_cursor()


def resolve_legacy_plan_branch(
    config: Config,
    state: WorkflowState,
    *,
    analyze_branch: str | None,
) -> str | None:
    flagged = clean(analyze_branch or "")
    if flagged:
        return flagged
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if state.analyze_branch:
            return state.analyze_branch
        raise SystemExit(
            "Pass --analyze-branch or run this command in a terminal "
            "to pick a legacy branch."
        )

    print_screen(
        render_page(
            legacy_repo=config.legacy_repo,
            modern_repo=config.modern_repo,
            cursor_env=config.cursor_env,
            model=config.model,
            body=[
                _c(WHITE, "  Plan"),
                _c(DIM, f"  Listing remotes on {repo_label(config.legacy_repo)}…"),
            ],
        )
    )
    names, error = list_remote_branches(config.legacy_repo)
    if not names:
        if error:
            print_screen(
                render_page(
                    legacy_repo=config.legacy_repo,
                    modern_repo=config.modern_repo,
                    cursor_env=config.cursor_env,
                    model=config.model,
                    body=[
                        _c(WHITE, "  Plan"),
                        _c(DIM, "  Could not list remote branches on the legacy repo."),
                        "",
                        _c(MUTED, f"  {error}"),
                        "",
                        _c(DIM, "  Enter a branch name to continue."),
                    ],
                )
            )
        return ask("Legacy branch")

    index = default_branch_index(
        names, saved=state.analyze_branch, fallback=config.legacy_ref
    )
    return choose_remote_branch(
        names,
        config=config,
        default=names[index],
        saved=state.analyze_branch,
        index=index,
    )
