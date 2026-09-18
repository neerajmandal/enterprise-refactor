"""Implement plan phases with unit tests, then a last-phase UI walkthrough."""

from __future__ import annotations

import sys

from cursor_sdk import CursorAgentError

from enterprise_refactor.integrations.cursor import (
    RunFailed,
    cloud_agent_session,
    extract_workflow_result,
    run_agent_prompt,
)
from enterprise_refactor.config import Config
from enterprise_refactor.integrations.git.branches import (
    IMPLEMENT_PREFIX,
    allocate_refactor_stamp,
)
from enterprise_refactor.pickers.implement_branch import resolve_target_implement_branch
from enterprise_refactor.pickers.phases import choose_phases_or_fallback
from enterprise_refactor.plan.selection import PhaseSelection
from enterprise_refactor.ui.screens.home import leave_home_for_workflow
from enterprise_refactor.state import WorkflowState, save_state


def _phase_work(phase_ids: tuple[str, ...] | None) -> str:
    if phase_ids:
        listed = "\n".join(f"- `{phase_id}`" for phase_id in phase_ids)
        return f"""Work ONLY these phases, in this order. Do not implement any
other pending phase in this run:

{listed}

For each listed phase:
"""
    return "For each phase whose status is not `done`, in dependency order:\n"


def _full_walkthrough_steps(config: Config, implement_branch: str, plan_ref: str) -> str:
    return f"""Last-phase UI test (`kind: computer_use` only, and only after
every implement-phase `test_command` in this run has passed):
- Do not write application features.
- Start the app. Use computer use to cover every earlier phase's
  `computer_use` flows, then the remaining main user paths.
- Record `docs/refactor/walkthrough.mp4` and `docs/refactor/walkthrough.md`
  on `{implement_branch}`. Screenshots under `docs/refactor/walkthrough/`
  are OK if video is not possible.
- Push `{implement_branch}`.
- Open or update a TARGET PR from `{implement_branch}` (base `{config.modern_ref}`).
  Do not open a PR on LEGACY or on `{plan_ref}`.
- PR description and a PR comment must embed or link the walkthrough.
- If `99-computer-use` (or the last `kind: computer_use` phase) is missing
  from `plan.json`, append it, then mark it `done`.
- If this run does not include the last `computer_use` phase, do not start
  the app, do not use a browser, and do not record a walkthrough."""


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
4. Implementation, plan check-offs, and the last-phase walkthrough files go on
   `{implement_branch}` only."""
    else:
        checkout = f"""1. On the TARGET repo: `git fetch origin` and check out `{state.plan_branch}` (`git checkout -B {state.plan_branch} origin/{state.plan_branch}`).
2. Create and push a branch named `{implement_branch}` from that plan source (or continue on the branch this cloud run already opened if it is a `{IMPLEMENT_PREFIX}*` branch). Use that exact name; do not force-push or overwrite an existing remote branch.
3. Do not commit, amend, push, or check off phases on `{state.plan_branch}`. Leave the plan source exactly as you found it.
4. Implementation, plan check-offs, and the last-phase walkthrough files go on
   `{implement_branch}` only."""
    return f"""You are running the Implement workflow of an enterprise refactor.

The cloud environment has both repositories. Check out the remote branches
before you edit (the VM may still be on main):

- LEGACY: {config.legacy_repo} — `git fetch origin` and check out `{state.analyze_branch}`
- TARGET: {config.modern_repo} — `git fetch origin` and check out the source branch only to read it.

Do not wait for a human. There is no CLI confirmation between phases.

Operational steps (do these around the work below):

{checkout}

Read `docs/refactor/plan.json` and `docs/refactor/plan.md` on the implement branch.
If the last `computer_use` phase is missing, treat `99-computer-use` as present.

{_phase_work(phase_ids)}
1. If the phase `kind` is `implement` (or omitted): implement it on `{implement_branch}`,
   check it off (`status` `done` in `plan.json` and the matching markdown
   checkboxes), and run that phase's `test_command`. If tests fail, fix and
   retest in this same run until they pass. If you cannot make them pass,
   stop and fail the run — do not start the UI test.
2. Do not start the app, use a browser, or use computer use during implement
   phases. Unit/`test_command` only.
3. If the phase `kind` is `computer_use` (last default phase): run it only
   after every implement phase in this run (and every earlier implement
   phase already marked `done`) has a passing `test_command`. Then do the
   UI walkthrough steps below, mark that phase `done`, and open/update the PR.
4. If `plan.json` has no last `computer_use` phase, append `99-computer-use`
   as the last item (depends on every earlier phase) when you reach it.
   Never put it before implement work.
5. Push `{implement_branch}` as you go. Do not ask the operator anything.

{_full_walkthrough_steps(config, implement_branch, plan_ref)}

When finished, end your last message with exactly this block:

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: {implement_branch}
artifacts: docs/refactor/plan.json
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
        config,
        state,
        plan_branch=plan_branch,
        phase_ids=phases,
    )
    if not picked:
        return None
    source, selection = picked
    source_is_implement = _record_source_branch(state, source)

    if not state.analyze_branch:
        state.analyze_branch = config.legacy_ref

    stamp = allocate_refactor_stamp(config.modern_repo, IMPLEMENT_PREFIX)
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
            if selection.all_remaining:
                step = "implement remaining phases (UI test last)"
            else:
                step = "implement selected phases"
            print(f"step  {step}", flush=True)
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
    if workflow_result.artifacts:
        print(f"artifacts        {workflow_result.artifacts}", flush=True)
    if workflow_result.pr_url:
        print(f"implement pr     {workflow_result.pr_url}", flush=True)
    return 0
