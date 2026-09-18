"""Parse ===REFACTOR_RESULT=== blocks and git metadata from a completed run."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cursor_sdk import RunResult

from enterprise_refactor.config import Config

_RESULT_BLOCK = re.compile(
    r"===REFACTOR_RESULT===\s*(.*?)\s*===END_REFACTOR_RESULT===",
    re.DOTALL,
)


@dataclass
class WorkflowResult:
    legacy_branch: str = ""
    modern_branch: str = ""
    artifacts: str = ""
    pr_url: str = ""


def normalize_repository_url(url: str) -> str:
    value = (url or "").strip().lower().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def contains_refactor_result(text: str) -> bool:
    workflow_result = parse_refactor_result_block(text)
    return bool(
        workflow_result.legacy_branch
        or workflow_result.modern_branch
        or workflow_result.pr_url
        or workflow_result.artifacts
    )


def find_branch_for_repository(completed_run: RunResult, repo_url: str) -> str:
    normalized_repo_url = normalize_repository_url(repo_url)
    if completed_run.git:
        for item in completed_run.git.branches:
            if not item.branch:
                continue
            pr_url = item.pr_url or ""
            if pr_url and normalized_repo_url in normalize_repository_url(pr_url):
                return item.branch
            if normalize_repository_url(item.repo_url) == normalized_repo_url:
                return item.branch
    return ""


def parse_refactor_result_block(text: str) -> WorkflowResult:
    match = _RESULT_BLOCK.search(text or "")
    if not match:
        return WorkflowResult()
    workflow_result = WorkflowResult()
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key in {"legacy_branch", "analyze_branch"}:
            workflow_result.legacy_branch = value
        elif key in {
            "modern_branch",
            "plan_branch",
            "target_branch",
            "implement_branch",
        }:
            workflow_result.modern_branch = value
        elif key == "artifacts":
            workflow_result.artifacts = value
        elif key in {"pr_url", "pr"}:
            workflow_result.pr_url = value
    return workflow_result


def find_pr_url_for_repository(completed_run: RunResult, repo_url: str) -> str:
    normalized_repo_url = normalize_repository_url(repo_url)
    if completed_run.git:
        for item in completed_run.git.branches:
            pr_url = item.pr_url or ""
            if pr_url and normalized_repo_url in normalize_repository_url(pr_url):
                return pr_url
            if normalize_repository_url(item.repo_url) == normalized_repo_url and pr_url:
                return pr_url
    return ""


def extract_workflow_result(completed_run: RunResult, config: Config) -> WorkflowResult:
    result_block = parse_refactor_result_block(completed_run.result or "")
    return WorkflowResult(
        legacy_branch=find_branch_for_repository(completed_run, config.legacy_repo)
        or result_block.legacy_branch,
        modern_branch=find_branch_for_repository(completed_run, config.modern_repo)
        or result_block.modern_branch,
        artifacts=result_block.artifacts,
        pr_url=find_pr_url_for_repository(completed_run, config.modern_repo)
        or result_block.pr_url,
    )
