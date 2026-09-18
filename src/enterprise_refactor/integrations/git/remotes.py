"""Normalize git remotes to GitHub owner/repo and clone URLs."""

from __future__ import annotations

from urllib.parse import urlparse


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
