"""List and sort remote branch names. No terminal UI."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence

from enterprise_refactor.integrations.git.remotes import github_owner_repo, remote_url

ANALYZE_PREFIX = "refactor/analyze-"
PLAN_PREFIX = "refactor/plan-"
IMPLEMENT_PREFIX = "refactor/implement-"


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


def _prefix_list(preferred_prefixes: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(preferred_prefixes, str):
        return (preferred_prefixes,)
    return tuple(preferred_prefixes)


def sort_branch_names(
    names: list[str], *, preferred_prefix: str | Sequence[str]
) -> list[str]:
    prefixes = _prefix_list(preferred_prefix)
    seen: set[str] = set()
    ordered: list[str] = []
    for prefix in prefixes:
        group = sorted(
            (name for name in names if name.startswith(prefix) and name not in seen),
            reverse=True,
        )
        ordered.extend(group)
        seen.update(group)
    rest = sorted(name for name in names if name not in seen)
    return ordered + rest


def list_remote_branches(
    url: str, *, preferred_prefix: str | Sequence[str]
) -> tuple[list[str], str]:
    seen: set[str] = set()
    names: list[str] = []
    for group in (_branches_from_ls_remote(url), _branches_from_gh(url)):
        for name in group or ():
            if name not in seen:
                seen.add(name)
                names.append(name)
    if names:
        return sort_branch_names(names, preferred_prefix=preferred_prefix), ""
    return [], "Could not list remote branches."


def default_branch_index(
    names: list[str],
    *,
    preferred_prefix: str | Sequence[str],
    saved: str,
    fallback: str,
) -> int:
    prefixes = _prefix_list(preferred_prefix)
    for prefix in prefixes:
        preferred = [name for name in names if name.startswith(prefix)]
        if preferred:
            return names.index(preferred[0])
    if saved and saved in names:
        return names.index(saved)
    if fallback and fallback in names:
        return names.index(fallback)
    if "main" in names:
        return names.index("main")
    return 0
