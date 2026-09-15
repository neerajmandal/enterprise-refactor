"""Analyze the legacy system and push a branch on the legacy repo."""

from __future__ import annotations

import sys
from datetime import date

from cursor_sdk import CursorAgentError

from enterprise_refactor.agent import (
    RunFailed,
    create_cloud_agent,
    parsed_from_run,
    send_and_stream,
)
from enterprise_refactor.config import Config
from enterprise_refactor.state import WorkflowState, save_state


def _prompt(config: Config, stamp: str) -> str:
    return f"""You are running the Analyze workflow of an enterprise refactor.

The cloud environment already has both repositories checked out:

- LEGACY (source of truth for this step): {config.legacy_repo} at {config.legacy_ref}
- TARGET (context only): {config.modern_repo} at {config.modern_ref}

Do this:

1. Create and push a branch on the LEGACY repo named `refactor/analyze-{stamp}` (or continue on the branch this cloud run already opened if it is a refactor/analyze-* branch). Do not open a pull request.
2. Use the TARGET repo only as context: existing stack, naming, and what is already modernized.
3. Inventory the legacy system: domains, entry points, data stores, jobs/cron, integrations, and risky coupling.
4. Commit analysis artifacts on the LEGACY branch, including `docs/refactor/analysis.md`.
5. Push the branch.

When finished, end your last message with exactly this block (fill in real values):

===REFACTOR_RESULT===
legacy_branch: <branch you pushed on the legacy repo>
modern_branch:
artifacts: docs/refactor/analysis.md
===END_REFACTOR_RESULT===
"""


def run(config: Config, state: WorkflowState) -> int:
    stamp = date.today().strftime("%Y%m%d")
    print("workflow  Analyze", flush=True)
    try:
        with create_cloud_agent(
            config,
            name=f"Analyze {stamp}",
            legacy_ref=config.legacy_ref,
            modern_ref=config.modern_ref,
        ) as agent:
            state.analyze_agent_id = agent.agent_id
            save_state(state)
            result = send_and_stream(agent, _prompt(config, stamp))
    except CursorAgentError as err:
        print(
            f"startup failed: {err.message}, retryable={err.is_retryable}",
            file=sys.stderr,
        )
        return 1
    except RunFailed as err:
        print(f"run failed: {err.run_id}", file=sys.stderr)
        return 2

    parsed = parsed_from_run(result, config)
    if parsed.legacy_branch:
        state.analyze_branch = parsed.legacy_branch
    elif not state.analyze_branch:
        state.analyze_branch = f"refactor/analyze-{stamp}"
    save_state(state)
    print(f"analyze branch  {state.analyze_branch}", flush=True)
    if parsed.artifacts:
        print(f"artifacts       {parsed.artifacts}", flush=True)
    return 0
