"""Send a prompt and wait until the cloud run completes."""

from __future__ import annotations

import os
import sys
import time

from cursor_sdk import Agent, RunResult

from enterprise_refactor.cloud.feed import (
    _SPINNER,
    _SPIN_INTERVAL,
    _clear_spinner_line,
    _elapsed_clock,
    write_live_feed,
    write_quiet_feed,
)
from enterprise_refactor.cloud.result import contains_refactor_result
from enterprise_refactor.cloud.session import (
    _ACTIVE_STATUSES,
    get_agent_dashboard_url,
)

_POLL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 4 * 60 * 60


class RunFailed(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        self.run_id = run_id


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


def get_cloud_run_snapshot(active_run: object) -> RunResult | None:
    run_id = getattr(active_run, "id", "")
    agent_id = getattr(active_run, "agent_id", "")
    if not run_id:
        return None
    try:
        snapshot = Agent.get_run(
            run_id,
            {
                "api_key": getattr(active_run, "_api_key", None)
                or os.environ.get("CURSOR_API_KEY")
                or None,
                "agent_id": agent_id,
                "runtime": "cloud",
            },
        )
    except Exception:
        return None
    return _as_run_result(snapshot)


def recover_finished_run(active_run: object) -> RunResult | None:
    """Cloud wait() can report error after the agent has already finished."""
    snapshot = get_cloud_run_snapshot(active_run)
    if snapshot is None or snapshot.status != "finished":
        return None
    return snapshot


def get_completed_run_result(active_run: object) -> RunResult:
    snapshot = get_cloud_run_snapshot(active_run)
    if snapshot is not None and snapshot.status not in _ACTIVE_STATUSES and snapshot.status:
        return snapshot
    return poll_until_run_completes(active_run)


def poll_until_run_completes(active_run: object) -> RunResult:
    """Keep the CLI attached while the live feed ends before the cloud run does."""
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    started = time.monotonic()
    next_poll = started
    latest_snapshot = get_cloud_run_snapshot(active_run)
    frame = 0
    try:
        while latest_snapshot is None or latest_snapshot.status in _ACTIVE_STATUSES:
            now = time.monotonic()
            if now >= deadline:
                break
            if now >= next_poll:
                latest_snapshot = get_cloud_run_snapshot(active_run)
                next_poll = now + _POLL_SECONDS
                if latest_snapshot is not None and latest_snapshot.status not in _ACTIVE_STATUSES:
                    break
            if sys.stdout.isatty():
                mark = _SPINNER[frame % len(_SPINNER)]
                sys.stdout.write(
                    f"\r  {mark}  {_elapsed_clock(started, now)}  finishing"
                )
                sys.stdout.flush()
                frame += 1
            time.sleep(_SPIN_INTERVAL)
    finally:
        _clear_spinner_line()
    if latest_snapshot is None:
        raise RunFailed(getattr(active_run, "id", ""))
    return latest_snapshot


def run_agent_prompt(
    agent: Agent, prompt: str, *, verbose: bool = False
) -> RunResult:
    url = get_agent_dashboard_url(agent.agent_id)
    if url:
        print(f"url    {url}", flush=True)
    else:
        print(f"agent  {agent.agent_id}", flush=True)
    active_run = agent.send(prompt)
    if verbose:
        print(f"run    {active_run.id}", flush=True)
        print("", flush=True)
        streamed = write_live_feed(active_run.messages())
    else:
        streamed = write_quiet_feed(active_run.messages())
    completed_run = get_completed_run_result(active_run)
    if completed_run.status != "finished" and contains_refactor_result(
        completed_run.result or ""
    ):
        completed_run = RunResult(
            id=completed_run.id,
            agent_id=completed_run.agent_id,
            status="finished",
            result=completed_run.result,
            model=completed_run.model,
            duration_ms=completed_run.duration_ms,
            git=completed_run.git,
            created_at=completed_run.created_at,
            usage=completed_run.usage,
        )
    if completed_run.status != "finished":
        if completed_run.result:
            print(completed_run.result, flush=True)
        raise RunFailed(completed_run.id)
    if completed_run.result and not streamed:
        print(completed_run.result, flush=True)
    return completed_run
