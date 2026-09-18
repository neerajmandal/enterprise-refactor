"""Write a modular phase plan on a new target-repo branch."""

from __future__ import annotations

import os
import sys
from datetime import date

from cursor_sdk import CursorAgentError

from enterprise_refactor.integrations.cursor import (
    RunFailed,
    cloud_agent_session,
    extract_workflow_result,
    run_agent_prompt,
)
from enterprise_refactor.pickers.analyze_branch import resolve_legacy_plan_branch
from enterprise_refactor.config import Config, clean
from enterprise_refactor.state import WorkflowState, save_state
from enterprise_refactor.ui.screens.home import leave_home_for_workflow
from enterprise_refactor.ui.text import ask_long_text


def resolve_modernization_ask(
    config: Config, prompt_arg: str | None
) -> str | None:
    value = clean(prompt_arg or os.environ.get("CURSOR_PLAN_PROMPT") or "")
    if value:
        return value
    if not sys.stdin.isatty():
        raise SystemExit(
            "Modernization prompt is missing. Pass --prompt, set "
            "CURSOR_PLAN_PROMPT, or run this command in a terminal."
        )
    return ask_long_text(
        config, title="Plan", label="Modernization prompt"
    )


def _prompt(
    config: Config, state: WorkflowState, stamp: str, modernization_ask: str
) -> str:
    return f"""You are running the Plan workflow of an enterprise refactor.

The cloud environment has both repositories. You must put LEGACY on the
selected remote analyze branch before you read current-state docs. Do not
trust that the VM is already on that branch (it may be on main).

- LEGACY (analysis): {config.legacy_repo} — required branch `{state.analyze_branch}`
- TARGET (write the plan here): {config.modern_repo} at {config.modern_ref}

Operational steps (do these around the planning work below):

1. On the LEGACY repo: `git fetch origin` and check out the remote branch `{state.analyze_branch}` (`git checkout -B {state.analyze_branch} origin/{state.analyze_branch}`). If that ref is missing, fail — do not invent analysis, do not stay on main, and do not create a new `refactor/analyze-*` branch.
2. Create and push a branch on the TARGET repo named `refactor/plan-{stamp}` (or continue on the branch this cloud run already opened if it is a refactor/plan-* branch).
3. Do not modify application code on either repo. Planning artifacts only.
4. Commit on the TARGET branch:
   - `docs/refactor/plan.md`
   - `docs/refactor/phases/NN-<slug>.md` one file per phase
   - `docs/refactor/plan.json`
5. Push the target branch and open a pull request on the TARGET repo only. Do not open a PR on the LEGACY repo.

You are performing the planning phase of a
legacy-system modernization.

Your task is to turn evidence about the current system plus the operator's
modernization ask into a phased implementation plan.

IMPORTANT:
- Do NOT implement application code.
- Do NOT refactor code.
- Do NOT invent current-state facts.
- Do NOT redesign beyond what the ask and current-state evidence support.
- Do NOT recommend a greenfield rewrite unless the ask explicitly says so.
- Preserve external contracts unless the ask explicitly changes them.
- Identify unknowns instead of guessing.
- If the analysis is thin, say so in the plan and keep phases conservative.

MODERNIZATION ASK (this drives scope; do not ignore it):

{modernization_ask}

GROUNDING (read these first):

On the LEGACY repo at {state.analyze_branch}:
- `docs/modernization/CURRENT_STATE_ANALYSIS.md`
- `docs/modernization/current-state.md`
- fallback: `docs/refactor/analysis.md` if the newer files are missing

On the TARGET repo:
- existing stack, naming, modules, and what is already modernized

Use the current-state analysis and Mermaid diagram as the source of truth
for how the system works today. Use the TARGET repo as destination
constraints. Use the modernization ask to decide what to change and in
what order.

PLANNING RULES:
- Phases are independently shippable, dependency-ordered, and small enough
  for Implement to finish one phase per loop.
- Each implement phase has concrete subtasks (checkbox work items).
- Call out risk areas from the analysis that a phase must not break.
- Subtasks should be specific enough that an implementer can execute them
  without re-discovering the system.
- Every implement phase must list `test_command` (unit/integration) and
  `computer_use` flows. Those flows are scripts for the LAST phase only,
  after every `test_command` has passed. Do not plan mid-phase UI tests.
- The LAST phase is always the default computer-use UI walkthrough. Do not
  omit it. It is not application work. `kind` must be `computer_use`,
  `id` should be `NN-computer-use` (highest NN), and `depends_on` must
  list every earlier phase. No implement phase may come after it.

OUTPUT

Create `docs/refactor/plan.md` with a short overview, then phases in this shape:

## Phase 1: <title>
Goal: ...
Depends on: none
- [ ] <subtask>
- [ ] <subtask>

## Phase 2: <title>
Goal: ...
Depends on: Phase 1
- [ ] <subtask>
- [ ] <subtask>

Also create `docs/refactor/phases/NN-<slug>.md` for every phase, including:
- goal
- evidence from current-state (files, flows, risks)
- subtasks
- `computer_use` flows (used only in the last UI phase, after unit tests)
- `done_when`
- `test_command`

Write a last `docs/refactor/phases/NN-computer-use.md` for the walkthrough.

Also create `docs/refactor/plan.json` as a list (or {{"phases": [...]}}) of
Implement-compatible phase objects. Every implement phase must include:

{{
  "id": "01-...",
  "title": "...",
  "kind": "implement",
  "depends_on": [],
  "subtasks": ["...", "..."],
  "test_command": "...",
  "computer_use": ["open …", "exercise the flow this phase added (last UI phase)"],
  "done_when": "...",
  "status": "todo"
}}

The final object must be the default computer-use phase:

{{
  "id": "0N-computer-use",
  "title": "Computer-use walkthrough",
  "kind": "computer_use",
  "depends_on": ["01-...", "02-..."],
  "subtasks": ["Confirm every earlier test_command passed", "Start the app", "Record walkthrough.mp4"],
  "test_command": "computer-use",
  "computer_use": ["end-to-end tour of every phase flow"],
  "done_when": "End-to-end computer-use walkthrough recorded and linked from the implement PR.",
  "status": "todo"
}}

Implement is phase-grained: it marks `status` per phase, not per subtask.
Subtasks are checklists for humans and for the implementer to complete
inside that phase.

When finished, end your last message with exactly this block (fill in real values):

===REFACTOR_RESULT===
legacy_branch: {state.analyze_branch}
modern_branch: <branch you pushed on the target repo>
artifacts: docs/refactor/plan.md, docs/refactor/plan.json
pr_url: <target repo pull request URL>
===END_REFACTOR_RESULT===
"""


def run(
    config: Config,
    state: WorkflowState,
    *,
    prompt: str | None = None,
    analyze_branch: str | None = None,
) -> int | None:
    analyze_ref = resolve_legacy_plan_branch(
        config, state, analyze_branch=analyze_branch
    )
    if not analyze_ref:
        return None
    state.analyze_branch = analyze_ref
    save_state(state)

    modernization_ask = resolve_modernization_ask(config, prompt)
    if not modernization_ask:
        return None
    stamp = date.today().strftime("%Y%m%d")
    leave_home_for_workflow()
    print(f"analyze branch  {state.analyze_branch}", flush=True)
    print("workflow  Plan", flush=True)
    try:
        with cloud_agent_session(
            config,
            name=f"Plan {stamp}",
            legacy_ref=state.analyze_branch,
            modern_ref=config.modern_ref,
            auto_create_pr=False,
        ) as agent:
            state.plan_agent_id = agent.agent_id
            save_state(state)
            completed_run = run_agent_prompt(
                agent,
                _prompt(config, state, stamp, modernization_ask),
                verbose=config.verbose,
            )
    except CursorAgentError as err:
        print(
            f"startup failed: {err.message}, retryable={err.is_retryable}",
            file=sys.stderr,
        )
        return 1
    except RunFailed as err:
        print(f"run failed: {err.run_id}", file=sys.stderr)
        return 2

    workflow_result = extract_workflow_result(completed_run, config)
    if workflow_result.modern_branch:
        state.plan_branch = workflow_result.modern_branch
    elif not state.plan_branch:
        state.plan_branch = f"refactor/plan-{stamp}"
    save_state(state)
    print(f"plan branch  {state.plan_branch}", flush=True)
    if workflow_result.artifacts:
        print(f"artifacts    {workflow_result.artifacts}", flush=True)
    if workflow_result.pr_url:
        print(f"plan pr      {workflow_result.pr_url}", flush=True)
    return 0
