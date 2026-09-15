"""Shared Cursor Cloud Agent create / send / stream helpers."""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from cursor_sdk import (
    Agent,
    CloudAgentOptions,
    CloudRepository,
    RunResult,
)

from enterprise_refactor.config import Config

_RESULT_BLOCK = re.compile(
    r"===REFACTOR_RESULT===\s*(.*?)\s*===END_REFACTOR_RESULT===",
    re.DOTALL,
)


@dataclass
class ParsedResult:
    legacy_branch: str = ""
    modern_branch: str = ""
    artifacts: str = ""
    pr_url: str = ""


class RunFailed(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        self.run_id = run_id


def normalize_repo(url: str) -> str:
    value = (url or "").strip().lower().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def cloud_options(
    config: Config,
    *,
    legacy_ref: str,
    modern_ref: str,
    auto_create_pr: bool = False,
) -> CloudAgentOptions:
    return CloudAgentOptions(
        repos=[
            CloudRepository(url=config.legacy_repo, starting_ref=legacy_ref),
            CloudRepository(url=config.modern_repo, starting_ref=modern_ref),
        ],
        skip_reviewer_request=True,
        auto_create_pr=auto_create_pr,
    )


def agent_url(agent_id: str) -> str:
    if (agent_id or "").startswith("bc-"):
        return f"https://cursor.com/agents/{agent_id}"
    return ""


_ACTIVE_STATUSES = {"running", "creating"}
_POLL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 4 * 60 * 60
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPIN_INTERVAL = 0.1


def _agent_api_key(agent: Agent) -> str | None:
    return getattr(agent, "_api_key", None) or os.environ.get("CURSOR_API_KEY") or None


def cloud_agent_has_active_run(agent: Agent) -> bool:
    try:
        page = Agent.list_runs(
            agent.agent_id,
            {
                "api_key": _agent_api_key(agent),
                "runtime": "cloud",
            },
        )
    except Exception:
        return True
    for item in getattr(page, "items", ()):
        status = getattr(item, "status", None)
        if status in _ACTIVE_STATUSES or not status:
            return True
    return False


def close_cloud_agent(agent: Agent) -> None:
    if cloud_agent_has_active_run(agent):
        url = agent_url(agent.agent_id) or agent.agent_id
        print(f"leaving  cloud agent running  {url}", flush=True)
        return
    try:
        agent.close()
    except Exception:
        return


@contextmanager
def create_cloud_agent(
    config: Config,
    *,
    name: str,
    legacy_ref: str,
    modern_ref: str,
    auto_create_pr: bool = False,
) -> Iterator[Agent]:
    agent = Agent.create(
        model=config.model,
        api_key=config.api_key,
        name=name,
        cloud=cloud_options(
            config,
            legacy_ref=legacy_ref,
            modern_ref=modern_ref,
            auto_create_pr=auto_create_pr,
        ),
    )
    try:
        yield agent
    finally:
        close_cloud_agent(agent)


def _as_run_result(run: object) -> RunResult:
    return RunResult(
        id=getattr(run, "id", ""),
        agent_id=getattr(run, "agent_id", ""),
        status=getattr(run, "status", "error"),
        result=getattr(run, "result", "") or "",
        model=getattr(run, "model", None),
        duration_ms=getattr(run, "duration_ms", 0) or 0,
        git=getattr(run, "git", None),
        created_at=getattr(run, "created_at", None),
        usage=getattr(run, "usage", None),
    )


def _has_result_block(text: str) -> bool:
    parsed = parse_result_block(text)
    return bool(
        parsed.legacy_branch or parsed.modern_branch or parsed.pr_url or parsed.artifacts
    )


def fetch_run_snapshot(run: object) -> RunResult | None:
    run_id = getattr(run, "id", "")
    agent_id = getattr(run, "agent_id", "")
    if not run_id:
        return None
    try:
        snapshot = Agent.get_run(
            run_id,
            {
                "api_key": getattr(run, "_api_key", None)
                or os.environ.get("CURSOR_API_KEY")
                or None,
                "agent_id": agent_id,
                "runtime": "cloud",
            },
        )
    except Exception:
        return None
    return _as_run_result(snapshot)


def recover_finished_run(run: object) -> RunResult | None:
    """Cloud wait() can report error after the agent has already finished."""
    snapshot = fetch_run_snapshot(run)
    if snapshot is None or snapshot.status != "finished":
        return None
    return snapshot


def _clear_spinner_line() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\r" + " " * 48 + "\r")
        sys.stdout.flush()


def finish_cloud_run(run: object) -> RunResult:
    snapshot = fetch_run_snapshot(run)
    if snapshot is not None and snapshot.status not in _ACTIVE_STATUSES and snapshot.status:
        return snapshot
    return wait_for_cloud_run(run)


def wait_for_cloud_run(run: object) -> RunResult:
    """Keep the CLI attached while the live feed ends before the cloud run does."""
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    started = time.monotonic()
    next_poll = started
    last = fetch_run_snapshot(run)
    frame = 0
    try:
        while last is None or last.status in _ACTIVE_STATUSES:
            now = time.monotonic()
            if now >= deadline:
                break
            if now >= next_poll:
                last = fetch_run_snapshot(run)
                next_poll = now + _POLL_SECONDS
                if last is not None and last.status not in _ACTIVE_STATUSES:
                    break
            if sys.stdout.isatty():
                mark = _SPINNER[frame % len(_SPINNER)]
                elapsed = int(now - started)
                sys.stdout.write(f"\r  {mark}  cloud run  {elapsed:>4}s")
                sys.stdout.flush()
                frame += 1
            time.sleep(_SPIN_INTERVAL)
    finally:
        _clear_spinner_line()
    if last is None:
        raise RunFailed(getattr(run, "id", ""))
    return last


_DETAIL_LIMIT = 160


def _one_line(value: object, limit: int = _DETAIL_LIMIT) -> str:
    text = " ".join(str(value).split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _tool_detail(args: object) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return _one_line(args)
    if isinstance(args, Mapping):
        for key in (
            "command",
            "path",
            "file_path",
            "pattern",
            "query",
            "url",
            "glob",
            "target_directory",
        ):
            found = args.get(key)
            if found:
                return _one_line(found)
        for found in args.values():
            if isinstance(found, str) and found.strip():
                return _one_line(found)
    return _one_line(args)


def _field(message: object, name: str, default: Any = "") -> Any:
    if isinstance(message, Mapping):
        return message.get(name, default)
    return getattr(message, name, default)


def _write_label(label: str, text: str) -> None:
    print(f"{label:<6} {text}".rstrip(), flush=True)


def _break_from_text(last_kind: str) -> None:
    if last_kind == "assistant":
        print("", flush=True)


def _assistant_texts(message: object) -> list[str]:
    inner = _field(message, "message", None)
    content = _field(inner, "content", ()) if inner is not None else ()
    texts: list[str] = []
    for block in content or ():
        text = _field(block, "text", "")
        if text:
            texts.append(str(text))
    return texts


def write_live_feed(messages: Iterator[Any]) -> bool:
    """Print thinking, tools, tasks, status, usage, and assistant text."""
    last_kind = ""
    streamed = False
    for message in messages:
        kind = str(_field(message, "type", "") or "")
        if kind == "assistant":
            texts = _assistant_texts(message)
            if not texts:
                continue
            if last_kind and last_kind != "assistant":
                print("", flush=True)
            for text in texts:
                sys.stdout.write(text)
                sys.stdout.flush()
            last_kind = "assistant"
            streamed = True
            continue
        if kind == "thinking":
            text = _field(message, "text", "")
            if not text:
                continue
            _break_from_text(last_kind)
            duration = _field(message, "thinking_duration_ms", None)
            _write_label("think", f"{duration}ms" if duration else "")
            for line in str(text).splitlines() or [""]:
                print(f"       {line}", flush=True)
            last_kind = "thinking"
            streamed = True
            continue
        if kind == "tool_call":
            _break_from_text(last_kind)
            line = "  ".join(
                part
                for part in (
                    str(_field(message, "name", "") or ""),
                    str(_field(message, "status", "") or ""),
                    _tool_detail(_field(message, "args", None)),
                )
                if part
            )
            _write_label("tool", line)
            last_kind = "tool_call"
            streamed = True
            continue
        if kind == "task":
            _break_from_text(last_kind)
            _write_label(
                "task",
                "  ".join(
                    part
                    for part in (
                        str(_field(message, "status", "") or ""),
                        _one_line(_field(message, "text", "")),
                    )
                    if part
                ),
            )
            last_kind = "task"
            streamed = True
            continue
        if kind == "status":
            _break_from_text(last_kind)
            _write_label(
                "status",
                "  ".join(
                    part
                    for part in (
                        str(_field(message, "status", "") or ""),
                        _one_line(_field(message, "message", "")),
                    )
                    if part
                ),
            )
            last_kind = "status"
            streamed = True
            continue
        if kind == "usage":
            usage = _field(message, "usage", None)
            if usage is None:
                continue
            _break_from_text(last_kind)
            _write_label(
                "usage",
                (
                    f"in={_field(usage, 'input_tokens', 0)}  "
                    f"out={_field(usage, 'output_tokens', 0)}  "
                    f"total={_field(usage, 'total_tokens', 0)}"
                ),
            )
            last_kind = "usage"
            streamed = True
    if streamed:
        print("", flush=True)
    return streamed


def send_and_stream(agent: Agent, prompt: str) -> RunResult:
    print(f"agent  {agent.agent_id}", flush=True)
    url = agent_url(agent.agent_id)
    if url:
        print(f"url    {url}", flush=True)
    run = agent.send(prompt)
    print(f"run    {run.id}", flush=True)
    print("", flush=True)
    streamed = write_live_feed(run.messages())
    result = finish_cloud_run(run)
    if result.status != "finished" and _has_result_block(result.result or ""):
        result = RunResult(
            id=result.id,
            agent_id=result.agent_id,
            status="finished",
            result=result.result,
            model=result.model,
            duration_ms=result.duration_ms,
            git=result.git,
            created_at=result.created_at,
            usage=result.usage,
        )
    if result.status != "finished":
        if result.result:
            print(result.result, flush=True)
        raise RunFailed(result.id)
    if result.result and not streamed:
        print(result.result, flush=True)
    return result


def branch_for_repo(result: RunResult, repo_url: str) -> str:
    wanted = normalize_repo(repo_url)
    if result.git:
        for item in result.git.branches:
            if not item.branch:
                continue
            pr_url = item.pr_url or ""
            if pr_url and wanted in normalize_repo(pr_url):
                return item.branch
            if normalize_repo(item.repo_url) == wanted:
                return item.branch
    return ""


def parse_result_block(text: str) -> ParsedResult:
    match = _RESULT_BLOCK.search(text or "")
    if not match:
        return ParsedResult()
    parsed = ParsedResult()
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key in {"legacy_branch", "analyze_branch"}:
            parsed.legacy_branch = value
        elif key in {"modern_branch", "plan_branch", "target_branch"}:
            parsed.modern_branch = value
        elif key == "artifacts":
            parsed.artifacts = value
        elif key in {"pr_url", "pr"}:
            parsed.pr_url = value
    return parsed


def pr_url_for_repo(result: RunResult, repo_url: str) -> str:
    wanted = normalize_repo(repo_url)
    if result.git:
        for item in result.git.branches:
            pr_url = item.pr_url or ""
            if pr_url and wanted in normalize_repo(pr_url):
                return pr_url
            if normalize_repo(item.repo_url) == wanted and pr_url:
                return pr_url
    return ""


def parsed_from_run(result: RunResult, config: Config) -> ParsedResult:
    block = parse_result_block(result.result or "")
    return ParsedResult(
        legacy_branch=branch_for_repo(result, config.legacy_repo)
        or block.legacy_branch,
        modern_branch=branch_for_repo(result, config.modern_repo)
        or block.modern_branch,
        artifacts=block.artifacts,
        pr_url=pr_url_for_repo(result, config.modern_repo) or block.pr_url,
    )

