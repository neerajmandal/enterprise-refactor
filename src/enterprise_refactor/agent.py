"""Shared Cursor Cloud Agent create / send / stream helpers."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from cursor_sdk import (
    Agent,
    CloudAgentOptions,
    CloudEnvironment,
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
    config: Config, *, legacy_ref: str, modern_ref: str
) -> CloudAgentOptions:
    return CloudAgentOptions(
        env=CloudEnvironment(type="cloud", name=config.cursor_env),
        repos=[
            CloudRepository(url=config.legacy_repo, starting_ref=legacy_ref),
            CloudRepository(url=config.modern_repo, starting_ref=modern_ref),
        ],
        skip_reviewer_request=True,
        auto_create_pr=False,
    )


def create_cloud_agent(
    config: Config, *, name: str, legacy_ref: str, modern_ref: str
) -> Agent:
    return Agent.create(
        model=config.model,
        api_key=config.api_key,
        name=name,
        cloud=cloud_options(config, legacy_ref=legacy_ref, modern_ref=modern_ref),
    )


def send_and_stream(agent: Agent, prompt: str) -> RunResult:
    run = agent.send(prompt)
    print(f"agent  {agent.agent_id}", flush=True)
    print(f"run    {run.id}", flush=True)
    print("", flush=True)
    streamed = False
    for chunk in run.iter_text():
        streamed = True
        sys.stdout.write(chunk)
        sys.stdout.flush()
    result = run.wait()
    if result.status == "error":
        raise RunFailed(result.id)
    if result.result and not streamed:
        print(result.result, flush=True)
    elif streamed:
        print("", flush=True)
    return result


def branch_for_repo(result: RunResult, repo_url: str) -> str:
    wanted = normalize_repo(repo_url)
    if result.git:
        for item in result.git.branches:
            if normalize_repo(item.repo_url) == wanted and item.branch:
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
    return parsed


def parsed_from_run(result: RunResult, config: Config) -> ParsedResult:
    block = parse_result_block(result.result or "")
    return ParsedResult(
        legacy_branch=branch_for_repo(result, config.legacy_repo)
        or block.legacy_branch,
        modern_branch=branch_for_repo(result, config.modern_repo)
        or block.modern_branch,
        artifacts=block.artifacts,
    )

