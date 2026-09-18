"""Cursor Cloud Agent session, prompt, and result helpers."""

from enterprise_refactor.cloud.feed import write_live_feed, write_quiet_feed
from enterprise_refactor.cloud.result import (
    WorkflowResult,
    contains_refactor_result,
    extract_workflow_result,
    find_branch_for_repository,
    find_pr_url_for_repository,
    normalize_repository_url,
    parse_refactor_result_block,
)
from enterprise_refactor.cloud.run import (
    RunFailed,
    get_cloud_run_snapshot,
    get_completed_run_result,
    poll_until_run_completes,
    recover_finished_run,
    run_agent_prompt,
)
from enterprise_refactor.cloud.session import (
    build_cloud_agent_options,
    close_agent_if_idle,
    cloud_agent_session,
    get_agent_dashboard_url,
    has_active_cloud_run,
)

__all__ = [
    "RunFailed",
    "WorkflowResult",
    "build_cloud_agent_options",
    "close_agent_if_idle",
    "cloud_agent_session",
    "contains_refactor_result",
    "extract_workflow_result",
    "find_branch_for_repository",
    "find_pr_url_for_repository",
    "get_agent_dashboard_url",
    "get_cloud_run_snapshot",
    "get_completed_run_result",
    "has_active_cloud_run",
    "normalize_repository_url",
    "parse_refactor_result_block",
    "poll_until_run_completes",
    "recover_finished_run",
    "run_agent_prompt",
    "write_live_feed",
    "write_quiet_feed",
]
