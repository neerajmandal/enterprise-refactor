"""Load, prompt for, and persist CLI connection settings."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from enterprise_refactor.banner import print_banner

ENV_PATH = Path(".env")
DEFAULT_REF = "main"
DEFAULT_MODEL = "composer-2.5"
DEFAULT_ENV = "inds-support-agent"

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b.|[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class Config:
    api_key: str
    legacy_repo: str
    modern_repo: str
    legacy_ref: str
    modern_ref: str
    model: str
    cursor_env: str
    ready: bool


def clean(value: str) -> str:
    return _ANSI.sub("", value or "").strip()


def is_repo(value: str) -> bool:
    value = clean(value)
    if not value or value.startswith("Crsr_"):
        return False
    if value.startswith(("http://", "https://", "git@")):
        return True
    return "/" in value and " " not in value and "[" not in value


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = clean(value)
    return values


def load_dotenv() -> None:
    for key, value in parse_dotenv(ENV_PATH).items():
        os.environ.setdefault(key, value)


def write_dotenv(updates: dict[str, str]) -> None:
    existing = ENV_PATH.read_text().splitlines() if ENV_PATH.is_file() else []
    written: set[str] = set()
    lines: list[str] = []
    for line in existing:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        lines.append(line)
    for key, value in updates.items():
        if key not in written:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n")


def ask(label: str, *, secret: bool = False) -> str:
    if not sys.stdin.isatty():
        raise SystemExit(
            f"{label} is missing. Add it to .env or run this command in a terminal."
        )
    while True:
        raw = getpass(f"{label}: ") if secret else input(f"{label}: ")
        value = clean(raw)
        if value:
            return value
        print("Value required.", file=sys.stderr)


def ask_repo(label: str) -> str:
    while True:
        value = ask(label)
        if is_repo(value):
            return value
        print("Enter a git URL or owner/repo. Arrow keys are ignored.", file=sys.stderr)


def resolve_config(args: argparse.Namespace) -> Config:
    load_dotenv()

    persist: dict[str, str] = {}
    api_key = clean(os.environ.get("CURSOR_API_KEY", ""))
    legacy_repo = clean(
        args.legacy_repo
        or os.environ.get("CURSOR_LEGACY_REPO")
        or os.environ.get("CURSOR_REPO")
        or ""
    )
    modern_repo = clean(args.modern_repo or os.environ.get("CURSOR_MODERN_REPO") or "")
    if not is_repo(legacy_repo):
        legacy_repo = ""
    if not is_repo(modern_repo):
        modern_repo = ""
    legacy_ref = (
        args.legacy_ref or os.environ.get("CURSOR_LEGACY_REF") or DEFAULT_REF
    ).strip()
    modern_ref = (
        args.modern_ref or os.environ.get("CURSOR_MODERN_REF") or DEFAULT_REF
    ).strip()
    model = (args.model or os.environ.get("CURSOR_MODEL") or DEFAULT_MODEL).strip()
    cursor_env = clean(args.cursor_env or os.environ.get("CURSOR_ENV") or "")

    complete = bool(api_key and legacy_repo and modern_repo and cursor_env)
    if not complete:
        print_banner(
            legacy_repo=legacy_repo,
            modern_repo=modern_repo,
            cursor_env=cursor_env,
            model=model,
            ready=False,
        )
        if not api_key:
            api_key = ask("CURSOR_API_KEY", secret=True)
            persist["CURSOR_API_KEY"] = api_key
            os.environ["CURSOR_API_KEY"] = api_key
        if not legacy_repo:
            legacy_repo = ask_repo("CURSOR_LEGACY_REPO")
            persist["CURSOR_LEGACY_REPO"] = legacy_repo
            os.environ["CURSOR_LEGACY_REPO"] = legacy_repo
        if not modern_repo:
            modern_repo = ask_repo("CURSOR_MODERN_REPO")
            persist["CURSOR_MODERN_REPO"] = modern_repo
            os.environ["CURSOR_MODERN_REPO"] = modern_repo
        if not cursor_env:
            cursor_env = ask("CURSOR_ENV")
            persist["CURSOR_ENV"] = cursor_env
            os.environ["CURSOR_ENV"] = cursor_env
        persist.setdefault("CURSOR_ENV", cursor_env)
        persist.setdefault("CURSOR_LEGACY_REF", legacy_ref)
        persist.setdefault("CURSOR_MODERN_REF", modern_ref)
        persist.setdefault("CURSOR_MODEL", model)
        write_dotenv(persist)
        print(f"Saved missing values to {ENV_PATH}.")

    return Config(
        api_key=api_key,
        legacy_repo=legacy_repo,
        modern_repo=modern_repo,
        legacy_ref=legacy_ref,
        modern_ref=modern_ref,
        model=model,
        cursor_env=cursor_env,
        ready=True,
    )


def apply_session(config: Config) -> None:
    """Use these values for the rest of this process. Do not write .env."""
    os.environ["CURSOR_API_KEY"] = config.api_key
    os.environ["CURSOR_LEGACY_REPO"] = config.legacy_repo
    os.environ["CURSOR_MODERN_REPO"] = config.modern_repo
    os.environ["CURSOR_LEGACY_REF"] = config.legacy_ref
    os.environ["CURSOR_MODERN_REF"] = config.modern_ref
    os.environ["CURSOR_MODEL"] = config.model
    os.environ["CURSOR_ENV"] = config.cursor_env
    config.ready = bool(
        config.api_key and config.legacy_repo and config.modern_repo and config.cursor_env
    )
