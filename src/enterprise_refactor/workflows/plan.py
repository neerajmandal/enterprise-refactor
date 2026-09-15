"""Write a modular phase plan on a new target-repo branch."""

from __future__ import annotations

import os
import sys
from datetime import date

from cursor_sdk import CursorAgentError

from enterprise_refactor.agent import (
    RunFailed,
    create_cloud_agent,
    parsed_from_run,
    send_and_stream,
)
from enterprise_refactor.branches import resolve_legacy_plan_branch
from enterprise_refactor.config import Config, ask, clean
from enterprise_refactor.state import WorkflowState, save_state


def resolve_modernization_ask(prompt_arg: str | None) -> str:
    value = clean(prompt_arg or os.environ.get("CURSOR_PLAN_PROMPT") or "")
    if value:
        return value
    if not sys.stdin.isatty():
        raise SystemExit(
            "Modernization prompt is missing. Pass --prompt, set "
            "CURSOR_PLAN_PROMPT, or run this command in a terminal."
        )
    return ask("Modernization prompt")


def _prompt(
    config: Config, state: WorkflowState, stamp: str, modernization_ask: str
) -> str:
    return f"""You are running the Plan workflow of an enterprise refactor.

The cloud environment already has both repositories checked out:

- LEGACY (analysis): {config.legacy_repo} at {state.analyze_branch}
- TARGET (write the plan here): {config.modern_repo} at {config.modern_ref}

Operational steps (do these around the planning work below):

1. Create and push a branch on the TARGET repo named `refactor/plan-{stamp}` (or continue on the branch this cloud run already opened if it is a refactor/plan-* branch).
2. Do not modify application code on either repo. Planning artifacts only.
3. Commit on the TARGET branch:
   - `docs/refactor/plan.md`
   - `docs/refactor/phases/NN-<slug>.md` one file per phase
   - `docs/refactor/plan.json`
4. Push the target branch and open a pull request on the TARGET repo only. Do not open a PR on the LEGACY repo.

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
- Each phase has concrete subtasks (checkbox work items).
- Call out risk areas from the analysis that a phase must not break.
- Subtasks should be specific enough that an implementer can execute them
  without re-discovering the system.

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
- `done_when`
- `test_command`

Also create `docs/refactor/plan.json` as a list (or {{"phases": [...]}}) of
Implement-compatible phase objects. Every phase must include:

{{
  "id": "01-...",
  "title": "...",
  "depends_on": [],
  "subtasks": ["...", "..."],
  "test_command": "...",
  "done_when": "...",
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
) -> int:
    state.analyze_branch = resolve_legacy_plan_branch(
        config, state, analyze_branch=analyze_branch
    )
    save_state(state)

    modernization_ask = resolve_modernization_ask(prompt)
    stamp = date.today().strftime("%Y%m%d")
    print(f"analyze branch  {state.analyze_branch}", flush=True)
    print("workflow  Plan", flush=True)
    try:
        with create_cloud_agent(
            config,
            name=f"Plan {stamp}",
            legacy_ref=state.analyze_branch,
            modern_ref=config.modern_ref,
            auto_create_pr=False,
        ) as agent:
            state.plan_agent_id = agent.agent_id
            save_state(state)
            result = send_and_stream(
                agent, _prompt(config, state, stamp, modernization_ask)
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

    parsed = parsed_from_run(result, config)
    if parsed.modern_branch:
        state.plan_branch = parsed.modern_branch
    elif not state.plan_branch:
        state.plan_branch = f"refactor/plan-{stamp}"
    save_state(state)
    print(f"plan branch  {state.plan_branch}", flush=True)
    if parsed.artifacts:
        print(f"artifacts    {parsed.artifacts}", flush=True)
    if parsed.pr_url:
        print(f"plan pr      {parsed.pr_url}", flush=True)
    return 0
