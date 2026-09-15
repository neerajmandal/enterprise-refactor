"""Send one prompt to a Cursor Cloud Agent and print the result."""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass
from pathlib import Path

from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, CloudRepository, CursorAgentError

ENV_PATH = Path(".env")
DEFAULT_REF = "main"
DEFAULT_MODEL = "composer-2.5"


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
        values[key] = value
    return values


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
        value = raw.strip()
        if value:
            return value
        print("Value required.", file=sys.stderr)


def _resolve_config(args: argparse.Namespace) -> tuple[str, str, str, str]:
    _load_dotenv()

    persist: dict[str, str] = {}
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    repo = (args.repo or os.environ.get("CURSOR_REPO", "")).strip()
    ref = (args.ref or os.environ.get("CURSOR_REPO_REF") or DEFAULT_REF).strip()
    model = (args.model or os.environ.get("CURSOR_MODEL") or DEFAULT_MODEL).strip()

    if api_key and repo:
        print("CLI ready (.env loaded).")
    else:
        if not api_key:
            api_key = _ask("CURSOR_API_KEY", secret=True)
            persist["CURSOR_API_KEY"] = api_key
            os.environ["CURSOR_API_KEY"] = api_key
        if not repo:
            repo = _ask("CURSOR_REPO")
            persist["CURSOR_REPO"] = repo
            os.environ["CURSOR_REPO"] = repo
        persist.setdefault("CURSOR_REPO_REF", ref)
        persist.setdefault("CURSOR_MODEL", model)
        _write_dotenv(persist)
        print(f"Saved missing values to {ENV_PATH}. CLI ready.")

    return api_key, repo, ref, model


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
        "--repo",
        default=None,
        help="Git URL to clone in the cloud VM (or CURSOR_REPO / .env)",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help=f"Starting git ref (default: {DEFAULT_REF}, or CURSOR_REPO_REF / .env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model id (default: {DEFAULT_MODEL}, or CURSOR_MODEL / .env)",
    )
    args = parser.parse_args(argv)

    api_key, repo, ref, model = _resolve_config(args)
    prompt = (args.prompt or "").strip() or _ask("Prompt")

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                cloud=CloudAgentOptions(
                    repos=[CloudRepository(url=repo, starting_ref=ref)],
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
