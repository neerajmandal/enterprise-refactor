"""Unattended phase implementation, then a computer-use walkthrough."""

from __future__ import annotations

import sys

from cursor_sdk import CursorAgentError

from enterprise_refactor.agent import (
    RunFailed,
    create_cloud_agent,
    parsed_from_run,
    send_and_stream,
)
from enterprise_refactor.config import Config
from enterprise_refactor.state import WorkflowState, save_state


def _implement_prompt(config: Config, state: WorkflowState) -> str:
    return f"""You are running the Implement workflow of an enterprise refactor.

The cloud environment has both repositories. Check out the remote branches
before you edit (the VM may still be on main):

- LEGACY: {config.legacy_repo} — `git fetch origin` and check out `{state.analyze_branch}`
- TARGET: {config.modern_repo} — `git fetch origin` and check out `{state.plan_branch}`

Work on the TARGET branch. Do not wait for a human. There is no CLI confirmation between phases.

Read `docs/refactor/plan.json` and `docs/refactor/plan.md` on the target repo.

For each phase whose status is not `done`, in dependency order:

1. Implement that phase on the target branch.
2. Check it off: set `status` to `done` in `docs/refactor/plan.json`, tick the matching checkbox in `docs/refactor/plan.md` and the phase file, and commit the check-off with the implementation.
3. Run that phase's `test_command`. If tests fail, fix and retest in this same run until they pass. If you cannot make them pass, stop and fail the run.
4. Push as you go, then move to the next undone phase. Do not ask the operator anything.

After every remaining phase is checked off and tested, stop. Do not record a video in this turn.

When finished, end your last message with exactly this block:

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: {state.plan_branch}
artifacts: docs/refactor/plan.json
===END_REFACTOR_RESULT===
"""


def _video_prompt(config: Config, state: WorkflowState) -> str:
    return f"""The refactor phases are implemented on the TARGET repo ({config.modern_repo} at {state.plan_branch}).

Now record a walkthrough. Do not wait for a human.

1. Start the app in this cloud VM (install/run as the target repo requires).
2. Use computer use (desktop and browser) to walk the main user flows that the refactor covered.
3. Record a screencast with ffmpeg/X11 or the equivalent available on this Debian/Ubuntu cloud desktop. Commit or upload it on the TARGET branch as `docs/refactor/walkthrough.mp4` plus a short `docs/refactor/walkthrough.md` note (what you clicked, what passed).
4. Computer use works on dashboard/Dockerfile Debian–Ubuntu cloud environments. If this named Cursor env cannot record video, still complete the walkthrough with screenshots under `docs/refactor/walkthrough/`, explain the limitation in `walkthrough.md`, and push.
5. Push the target branch. Do not open a pull request.

When finished, end your last message with exactly this block:

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: {state.plan_branch}
artifacts: docs/refactor/walkthrough.mp4
===END_REFACTOR_RESULT===
"""


def run(config: Config, state: WorkflowState) -> int:
    if not state.analyze_branch or not state.plan_branch:
        print(
            "Implement needs Analyze and Plan first "
            "(legacy analysis branch and target plan branch).",
            file=sys.stderr,
        )
        return 1

    print("workflow  Implement", flush=True)
    try:
        with create_cloud_agent(
            config,
            name="Implement phases",
            legacy_ref=state.analyze_branch,
            modern_ref=state.plan_branch,
        ) as agent:
            state.implement_agent_id = agent.agent_id
            save_state(state)
            print("step  implement remaining phases", flush=True)
            result = send_and_stream(agent, _implement_prompt(config, state))
            parsed = parsed_from_run(result, config)
            if parsed.modern_branch:
                state.plan_branch = parsed.modern_branch
                save_state(state)
            print("step  computer-use walkthrough", flush=True)
            send_and_stream(agent, _video_prompt(config, state))
    except CursorAgentError as err:
        print(
            f"startup failed: {err.message}, retryable={err.is_retryable}",
            file=sys.stderr,
        )
        return 1
    except RunFailed as err:
        print(f"run failed: {err.run_id}", file=sys.stderr)
        return 2

    print(f"plan branch  {state.plan_branch}", flush=True)
    return 0
