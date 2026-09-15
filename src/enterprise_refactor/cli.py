"""Send one prompt to a Cursor Cloud Agent and print the result."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b.|[\x00-\x08\x0b\x0c\x0e-\x1f]")

from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, CloudRepository, CursorAgentError

from enterprise_refactor.banner import print_banner

ENV_PATH = Path(".env")
DEFAULT_REF = "main"
DEFAULT_MODEL = "composer-2.5"
DEFAULT_ENV = "Cursor Cloud"


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


def _parse_dotenv(path: Path) -> dict[str, str]:
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
        values[key] = _clean(value)
    return values


def _clean(value: str) -> str:
    return _ANSI.sub("", value or "").strip()


def _is_repo(value: str) -> bool:
    value = _clean(value)
    if not value or value.startswith("Crsr_"):
        return False
    if value.startswith(("http://", "https://", "git@")):
        return True
    return "/" in value and " " not in value and "[" not in value


def _load_dotenv() -> None:
    for key, value in _parse_dotenv(ENV_PATH).items():
        os.environ.setdefault(key, value)


def _write_dotenv(updates: dict[str, str]) -> None:
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


def _ask(label: str, *, secret: bool = False) -> str:
    if not sys.stdin.isatty():
        raise SystemExit(
            f"{label} is missing. Add it to .env or run this command in a terminal."
        )
    while True:
        raw = getpass(f"{label}: ") if secret else input(f"{label}: ")
        value = _clean(raw)
        if value:
            return value
        print("Value required.", file=sys.stderr)


def _ask_repo(label: str) -> str:
    while True:
        value = _ask(label)
        if _is_repo(value):
            return value
        print("Enter a git URL or owner/repo. Arrow keys are ignored.", file=sys.stderr)


def _resolve_config(args: argparse.Namespace) -> Config:
    _load_dotenv()

    persist: dict[str, str] = {}
    api_key = _clean(os.environ.get("CURSOR_API_KEY", ""))
    legacy_repo = _clean(
        args.legacy_repo
        or os.environ.get("CURSOR_LEGACY_REPO")
        or os.environ.get("CURSOR_REPO")
        or ""
    )
    modern_repo = _clean(args.modern_repo or os.environ.get("CURSOR_MODERN_REPO") or "")
    if not _is_repo(legacy_repo):
        legacy_repo = ""
    if not _is_repo(modern_repo):
        modern_repo = ""
    legacy_ref = (
        args.legacy_ref or os.environ.get("CURSOR_LEGACY_REF") or DEFAULT_REF
    ).strip()
    modern_ref = (
        args.modern_ref or os.environ.get("CURSOR_MODERN_REF") or DEFAULT_REF
    ).strip()
    model = (args.model or os.environ.get("CURSOR_MODEL") or DEFAULT_MODEL).strip()
    cursor_env = (args.cursor_env or os.environ.get("CURSOR_ENV") or DEFAULT_ENV).strip()

    complete = bool(api_key and legacy_repo and modern_repo)
    if not complete:
        print_banner(
            legacy_repo=legacy_repo,
            modern_repo=modern_repo,
            cursor_env=cursor_env,
            model=model,
            ready=False,
        )
        if not api_key:
            api_key = _ask("CURSOR_API_KEY", secret=True)
            persist["CURSOR_API_KEY"] = api_key
            os.environ["CURSOR_API_KEY"] = api_key
        if not legacy_repo:
            legacy_repo = _ask_repo("CURSOR_LEGACY_REPO")
            persist["CURSOR_LEGACY_REPO"] = legacy_repo
            os.environ["CURSOR_LEGACY_REPO"] = legacy_repo
        if not modern_repo:
            modern_repo = _ask_repo("CURSOR_MODERN_REPO")
            persist["CURSOR_MODERN_REPO"] = modern_repo
            os.environ["CURSOR_MODERN_REPO"] = modern_repo
        persist.setdefault("CURSOR_ENV", cursor_env)
        persist.setdefault("CURSOR_LEGACY_REF", legacy_ref)
        persist.setdefault("CURSOR_MODERN_REF", modern_ref)
        persist.setdefault("CURSOR_MODEL", model)
        _write_dotenv(persist)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enterprise-refactor",
        description="Send one prompt to a Cursor Cloud Agent and print the result.",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="The single prompt to send (asked interactively if omitted)",
    )
    parser.add_argument(
        "--legacy-repo",
        default=None,
        help="Legacy source git URL (or CURSOR_LEGACY_REPO / CURSOR_REPO / .env)",
    )
    parser.add_argument(
        "--modern-repo",
        default=None,
        help="Modern target git URL (or CURSOR_MODERN_REPO / .env)",
    )
    parser.add_argument(
        "--cursor-env",
        default=None,
        help=f"Cursor environment label (default: {DEFAULT_ENV}, or CURSOR_ENV / .env)",
    )
    parser.add_argument(
        "--legacy-ref",
        default=None,
        help=f"Legacy starting git ref (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--modern-ref",
        default=None,
        help=f"Modern starting git ref (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model id (default: {DEFAULT_MODEL}, or CURSOR_MODEL / .env)",
    )
    args = parser.parse_args(argv)

    config = _resolve_config(args)
    print_banner(
        legacy_repo=config.legacy_repo,
        modern_repo=config.modern_repo,
        cursor_env=config.cursor_env,
        model=config.model,
        ready=config.ready,
    )
    prompt = (args.prompt or "").strip() or _ask("Prompt")

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=config.api_key,
                model=config.model,
                cloud=CloudAgentOptions(
                    repos=[
                        CloudRepository(
                            url=config.legacy_repo, starting_ref=config.legacy_ref
                        ),
                        CloudRepository(
                            url=config.modern_repo, starting_ref=config.modern_ref
                        ),
                    ],
                    skip_reviewer_request=True,
                ),
            ),
        )
    except CursorAgentError as err:
        print(
            f"startup failed: {err.message}, retryable={err.is_retryable}",
            file=sys.stderr,
        )
        return 1

    if result.status == "error":
        print(f"run failed: {result.id}", file=sys.stderr)
        return 2

    if result.result:
        print(result.result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
