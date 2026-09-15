"""List and resolve legacy git branches for Plan."""

from __future__ import annotations

import shutil
import subprocess
import sys
from urllib.parse import urlparse

from enterprise_refactor.banner import CYAN, FOREST, LIME
from enterprise_refactor.config import Config, ask, clean
from enterprise_refactor.menu import MenuRow, choose_item
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


def _run(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
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
    output = _run(["git", "ls-remote", "--heads", remote_url(url)])
    if output is None:
        return None
    names: list[str] = []
    for line in output.splitlines():
        if "\t" not in line:
            continue
        _, ref = line.split("\t", 1)
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            names.append(ref[len(prefix) :])
    return names or None


def list_remote_branches(url: str) -> tuple[list[str], str]:
    names = _branches_from_gh(url)
    if names:
        return names, ""
    names = _branches_from_ls_remote(url)
    if names:
        return names, ""
    return [], "Could not list remote branches on the legacy repo."


def default_branch_index(
    names: list[str], *, saved: str, fallback: str
) -> int:
    if saved and saved in names:
        return names.index(saved)
    analyze = sorted(name for name in names if name.startswith(_ANALYZE_PREFIX))
    if analyze:
        return names.index(analyze[-1])
    if fallback and fallback in names:
        return names.index(fallback)
    if "main" in names:
        return names.index("main")
    return 0


def _branch_rows(names: list[str], *, default: str, saved: str) -> list[MenuRow]:
    rows: list[MenuRow] = []
    for name in names:
        hint = ""
        color = FOREST
        if name == default and (
            name == saved or name.startswith(_ANALYZE_PREFIX)
        ):
            hint = "analyze"
            color = LIME
        elif name.startswith(_ANALYZE_PREFIX):
            color = CYAN
        rows.append(MenuRow(id=name, title=name, detail=hint, color=color))
    return rows


def resolve_legacy_plan_branch(
    config: Config,
    state: WorkflowState,
    *,
    analyze_branch: str | None,
) -> str:
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

    print("legacy branch", flush=True)
    names, error = list_remote_branches(config.legacy_repo)
    if not names:
        if error:
            print(error, file=sys.stderr)
        return ask("Legacy branch")

    index = default_branch_index(
        names, saved=state.analyze_branch, fallback=config.legacy_ref
    )
    default = names[index]
    return choose_item(
        _branch_rows(names, default=default, saved=state.analyze_branch),
        index=index,
    )
