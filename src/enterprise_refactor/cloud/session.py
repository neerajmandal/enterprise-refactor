"""Create a cloud agent session and close it only when idle."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from cursor_sdk import Agent, CloudAgentOptions, CloudRepository

from enterprise_refactor.git.remotes import remote_url
from enterprise_refactor.config import Config

_ACTIVE_STATUSES = {"running", "creating"}


def build_cloud_agent_options(
    config: Config,
    *,
    legacy_ref: str,
    modern_ref: str,
    auto_create_pr: bool = False,
) -> CloudAgentOptions:
    # Named cloud environments cannot be combined with explicit repos.
    # This CLI always needs both repos and starting refs, so skip env.name.
    return CloudAgentOptions(
        repos=[
            CloudRepository(
                url=remote_url(config.legacy_repo),
                starting_ref=legacy_ref,
            ),
            CloudRepository(
                url=remote_url(config.modern_repo),
                starting_ref=modern_ref,
            ),
        ],
        skip_reviewer_request=True,
        auto_create_pr=auto_create_pr,
    )


def get_agent_dashboard_url(agent_id: str) -> str:
    if (agent_id or "").startswith("bc-"):
        return f"https://cursor.com/agents/{agent_id}"
    return ""


def _agent_api_key(agent: Agent) -> str | None:
    return getattr(agent, "_api_key", None) or os.environ.get("CURSOR_API_KEY") or None


def has_active_cloud_run(agent: Agent) -> bool:
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


def close_agent_if_idle(agent: Agent) -> None:
    if has_active_cloud_run(agent):
        url = get_agent_dashboard_url(agent.agent_id) or agent.agent_id
        print(f"leaving  cloud agent running  {url}", flush=True)
        return
    try:
        agent.close()
    except Exception:
        return


@contextmanager
def cloud_agent_session(
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
        cloud=build_cloud_agent_options(
            config,
            legacy_ref=legacy_ref,
            modern_ref=modern_ref,
            auto_create_pr=auto_create_pr,
        ),
    )
    try:
        yield agent
    finally:
        close_agent_if_idle(agent)
