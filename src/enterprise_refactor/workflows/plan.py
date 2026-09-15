"""Write a modular phase plan on a new target-repo branch."""

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


def _prompt(config: Config, state: WorkflowState, stamp: str) -> str:
    return f"""You are running the Plan workflow of an enterprise refactor.

The cloud environment already has both repositories checked out:

- LEGACY (analysis): {config.legacy_repo} at {state.analyze_branch}
- TARGET (write the plan here): {config.modern_repo} at {config.modern_ref}

Read `docs/refactor/analysis.md` (and any sibling analysis files) on the legacy branch.

Do this:

1. Create and push a branch on the TARGET repo named `refactor/plan-{stamp}` (or continue on the branch this cloud run already opened if it is a refactor/plan-* branch). Do not open a pull request.
2. Write a modular implementation plan: small, independently shippable phases with clear dependencies.
3. Commit on the TARGET branch:
   - `docs/refactor/plan.md` (human-readable overview with unchecked boxes)
   - `docs/refactor/phases/NN-<slug>.md` one file per phase
   - `docs/refactor/plan.json` with this shape for every phase:
     {{"id": "01-...", "title": "...", "depends_on": [], "test_command": "...", "done_when": "...", "status": "todo"}}
4. Push the target branch.

When finished, end your last message with exactly this block (fill in real values):

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: <branch you pushed on the target repo>
artifacts: docs/refactor/plan.md, docs/refactor/plan.json
===END_REFACTOR_RESULT===
"""


def run(config: Config, state: WorkflowState) -> int:
    if not state.analyze_branch:
        print(
            "Plan needs Analyze first. Run Analyze so a legacy analysis branch exists.",
            file=sys.stderr,
        )
        return 1

    stamp = date.today().strftime("%Y%m%d")
    print("workflow  Plan", flush=True)
    try:
        with create_cloud_agent(
            config,
            name=f"Plan {stamp}",
            legacy_ref=state.analyze_branch,
            modern_ref=config.modern_ref,
        ) as agent:
            state.plan_agent_id = agent.agent_id
            save_state(state)
            result = send_and_stream(agent, _prompt(config, state, stamp))
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
    if parsed.modern_branch:
        state.plan_branch = parsed.modern_branch
    elif not state.plan_branch:
        state.plan_branch = f"refactor/plan-{stamp}"
    save_state(state)
    print(f"plan branch  {state.plan_branch}", flush=True)
    if parsed.artifacts:
        print(f"artifacts    {parsed.artifacts}", flush=True)
    return 0
