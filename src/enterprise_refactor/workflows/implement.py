"""Unattended phase implementation, then a computer-use walkthrough."""

from __future__ import annotations

import sys
from datetime import date

from cursor_sdk import CursorAgentError

from enterprise_refactor.cloud import (
    RunFailed,
    cloud_agent_session,
    extract_workflow_result,
    run_agent_prompt,
)
from enterprise_refactor.config import Config
from enterprise_refactor.git.branch_list import IMPLEMENT_PREFIX
from enterprise_refactor.pickers.implement_branch import resolve_target_implement_branch
from enterprise_refactor.pickers.phases import choose_phases_or_fallback
from enterprise_refactor.plan.selection import PhaseSelection
from enterprise_refactor.ui.home import leave_home_for_workflow
from enterprise_refactor.state import WorkflowState, save_state


def _phase_work(phase_ids: tuple[str, ...] | None) -> str:
    if phase_ids:
        listed = "\n".join(f"- `{phase_id}`" for phase_id in phase_ids)
        return f"""Implement ONLY these phases, in this order. Do not implement any
other pending phase in this run:

{listed}

For each listed phase:
"""
    return "For each phase whose status is not `done`, in dependency order:\n"


def _implement_prompt(
    config: Config,
    state: WorkflowState,
    *,
    implement_branch: str,
    source_is_implement: bool,
    phase_ids: tuple[str, ...] | None,
) -> str:
    plan_ref = state.plan_branch or "any refactor/plan-* branch"
    if source_is_implement:
        checkout = f"""1. On the TARGET repo: `git fetch origin` and check out `{implement_branch}` (`git checkout -B {implement_branch} origin/{implement_branch}`).
2. Stay on `{implement_branch}`. Do not create a new implement branch.
3. Do not commit, amend, push, or check off phases on `{plan_ref}`. Leave any plan source exactly as you found it.
4. All implementation, plan check-offs, and later walkthrough files go on `{implement_branch}` only."""
    else:
        checkout = f"""1. On the TARGET repo: `git fetch origin` and check out `{state.plan_branch}` (`git checkout -B {state.plan_branch} origin/{state.plan_branch}`).
2. Create and push a branch named `{implement_branch}` from that plan source (or continue on the branch this cloud run already opened if it is a `{IMPLEMENT_PREFIX}*` branch).
3. Do not commit, amend, push, or check off phases on `{state.plan_branch}`. Leave the plan source exactly as you found it.
4. All implementation, plan check-offs, and later walkthrough files go on `{implement_branch}` only."""
    return f"""You are running the Implement workflow of an enterprise refactor.

The cloud environment has both repositories. Check out the remote branches
before you edit (the VM may still be on main):

- LEGACY: {config.legacy_repo} — `git fetch origin` and check out `{state.analyze_branch}`
- TARGET: {config.modern_repo} — `git fetch origin` and check out the source branch only to read it.

Do not wait for a human. There is no CLI confirmation between phases.

Operational steps (do these around the implementation work below):

{checkout}

Read `docs/refactor/plan.json` and `docs/refactor/plan.md` on the implement branch.

{_phase_work(phase_ids)}
1. Implement that phase on `{implement_branch}`.
2. Check it off: set `status` to `done` in `docs/refactor/plan.json`, tick the matching checkbox in `docs/refactor/plan.md` and the phase file, and commit the check-off with the implementation on `{implement_branch}`.
3. Run that phase's `test_command`. If tests fail, fix and retest in this same run until they pass. If you cannot make them pass, stop and fail the run.
4. Push `{implement_branch}` as you go, then move to the next listed (or remaining) phase. Do not ask the operator anything.

After the selected phases are checked off and tested, stop. Do not record a video in this turn.

When finished, end your last message with exactly this block:

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: {implement_branch}
artifacts: docs/refactor/plan.json
===END_REFACTOR_RESULT===
"""


def _video_prompt(config: Config, state: WorkflowState) -> str:
    implement_branch = state.implement_branch
    return f"""The selected refactor phases are implemented on the TARGET repo ({config.modern_repo} at {implement_branch}).

Now record a walkthrough, then open a pull request that includes the video. Do not wait for a human.

Stay on `{implement_branch}`. Do not check out, commit, or push `{state.plan_branch}`.

1. Start the app in this cloud VM (install/run as the target repo requires).
2. Use computer use (desktop and browser) to walk the main user flows that the refactor covered.
3. Record a screencast with ffmpeg/X11 or the equivalent available on this Debian/Ubuntu cloud desktop. Commit it on `{implement_branch}` as `docs/refactor/walkthrough.mp4` plus a short `docs/refactor/walkthrough.md` note (what you clicked, what passed).
4. Computer use works on dashboard/Dockerfile Debian–Ubuntu cloud environments. If this named Cursor env cannot record video, still complete the walkthrough with screenshots under `docs/refactor/walkthrough/`, explain the limitation in `walkthrough.md`, and commit those files.
5. Push `{implement_branch}`.
6. Open a pull request on the TARGET repo only from `{implement_branch}` (base `{config.modern_ref}`). Do not open a PR on the LEGACY repo. If a PR for this implement branch already exists, update that one instead of opening a second. Do not open or update a PR for `{state.plan_branch}`.
7. Put the walkthrough inside the PR:
   - PR description must have a Walkthrough section that embeds or links the committed `docs/refactor/walkthrough.mp4` (raw or blob URL on this branch) so reviewers can play it from the PR.
   - Also post a PR comment that embeds or links the same video (use `gh pr comment` if needed).
   - If you only have screenshots, include them in the description and the comment.
   - Do not finish without a TARGET PR URL.

When finished, end your last message with exactly this block:

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: {implement_branch}
artifacts: docs/refactor/walkthrough.mp4
pr_url: <target repo pull request URL>
===END_REFACTOR_RESULT===
"""


def _record_source_branch(state: WorkflowState, source: str) -> bool:
    source_is_implement = source.startswith(IMPLEMENT_PREFIX)
    if source_is_implement:
        state.implement_branch = source
    else:
        state.plan_branch = source
        state.implement_branch = ""
    save_state(state)
    return source_is_implement


def _record_implement_branch(
    state: WorkflowState, modern_branch: str, stamp: str
) -> None:
    if modern_branch:
        state.implement_branch = modern_branch
    elif not state.implement_branch:
        state.implement_branch = f"{IMPLEMENT_PREFIX}{stamp}"
    save_state(state)


def _pick_source_and_phases(
    config: Config,
    state: WorkflowState,
    *,
    plan_branch: str | None,
    phase_ids: list[str] | None,
) -> tuple[str, PhaseSelection] | None:
    flagged_source = bool(plan_branch)
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    while True:
        source = resolve_target_implement_branch(
            config, state, plan_branch=plan_branch
        )
        if not source:
            return None
        selection = choose_phases_or_fallback(
            config=config,
            branch=source,
            flagged=phase_ids,
            allow_picker=tty and not phase_ids,
        )
        if selection is None:
            if flagged_source:
                return None
            plan_branch = None
            continue
        return source, selection


def run(
    config: Config,
    state: WorkflowState,
    *,
    plan_branch: str | None = None,
    phases: list[str] | None = None,
) -> int | None:
    picked = _pick_source_and_phases(
        config, state, plan_branch=plan_branch, phase_ids=phases
    )
    if not picked:
        return None
    source, selection = picked
    source_is_implement = _record_source_branch(state, source)

    if not state.analyze_branch:
        state.analyze_branch = config.legacy_ref

    stamp = date.today().strftime("%Y%m%d")
    if source_is_implement:
        intended = source
        modern_ref = source
    else:
        intended = f"{IMPLEMENT_PREFIX}{stamp}"
        modern_ref = state.plan_branch

    leave_home_for_workflow()
    print(f"plan branch      {state.plan_branch or "(unset)"}", flush=True)
    print(f"implement branch {intended}", flush=True)
    print(f"analyze branch   {state.analyze_branch}", flush=True)
    if selection.ids:
        print(f"phases           {', '.join(selection.ids)}", flush=True)
    else:
        print("phases           all remaining", flush=True)
    print("workflow  Implement", flush=True)
    try:
        with cloud_agent_session(
            config,
            name=f"Implement {stamp}",
            legacy_ref=state.analyze_branch,
            modern_ref=modern_ref,
            auto_create_pr=True,
        ) as agent:
            state.implement_agent_id = agent.agent_id
            save_state(state)
            print("step  implement remaining phases", flush=True)
            completed_run = run_agent_prompt(
                agent,
                _implement_prompt(
                    config,
                    state,
                    implement_branch=intended,
                    source_is_implement=source_is_implement,
                    phase_ids=selection.ids,
                ),
                verbose=config.verbose,
            )
            workflow_result = extract_workflow_result(completed_run, config)
            _record_implement_branch(state, workflow_result.modern_branch, stamp)
            print("step  computer-use walkthrough", flush=True)
            completed_video_run = run_agent_prompt(
                agent, _video_prompt(config, state), verbose=config.verbose
            )
            workflow_result = extract_workflow_result(completed_video_run, config)
            _record_implement_branch(state, workflow_result.modern_branch, stamp)
    except CursorAgentError as err:
        print(
            f"startup failed: {err.message}, retryable={err.is_retryable}",
            file=sys.stderr,
        )
        return 1
    except RunFailed as err:
        print(f"run failed: {err.run_id}", file=sys.stderr)
        return 2

    print(f"plan branch      {state.plan_branch}", flush=True)
    print(f"implement branch {state.implement_branch}", flush=True)
    if parsed.artifacts:
        print(f"artifacts        {parsed.artifacts}", flush=True)
    if parsed.pr_url:
        print(f"implement pr     {parsed.pr_url}", flush=True)
    return 0
