"""Analyze the legacy system and push a branch on the legacy repo."""

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
from enterprise_refactor.state import WorkflowState, save_state


def build_analysis_prompt(config: Config, stamp: str) -> str:
    return f"""You are running the Analyze workflow of an enterprise refactor.

The cloud environment already has both repositories checked out:

- LEGACY (source of truth for this step): {config.legacy_repo} at {config.legacy_ref}
- TARGET (context only): {config.modern_repo} at {config.modern_ref}

Operational steps (do these around the discovery work below):

1. Create and push a branch on the LEGACY repo named `refactor/analyze-{stamp}` (or continue on the branch this cloud run already opened if it is a refactor/analyze-* branch). Do not open a pull request.
2. Use the TARGET repo only as context: existing stack, naming, and what is already modernized.
3. Commit analysis artifacts on the LEGACY branch:
   - `docs/modernization/CURRENT_STATE_ANALYSIS.md`
   - `docs/modernization/current-state.md`
4. Push the branch.

You are performing the discovery phase of a
legacy-system modernization.

Your task is to understand the existing system accurately before proposing
any changes.

IMPORTANT:
- Do NOT modify code.
- Do NOT refactor code.
- Do NOT design the target architecture yet.
- Do NOT assume the README accurately represents the implementation.
- Base conclusions on evidence from the repository.
- Clearly identify unknowns instead of guessing.

Explore the entire repository and build a factual model of how the system
currently works.

Analyze the following:

1. SYSTEM PURPOSE
   - What business capability does this system provide?
   - What are its primary user-facing workflows?
   - What are the major entry points?

2. ARCHITECTURE
   Identify:
   - applications/services
   - modules
   - background workers
   - queues/event systems
   - APIs
   - databases
   - external integrations
   - shared libraries

   Explain how these components communicate.

3. EXECUTION FLOWS
   Trace the major workflows end-to-end.

   For each flow identify:
   Entry point
      →
   application/service
      →
   business logic
      →
   messaging/events
      →
   persistence
      →
   external systems
      →
   response/output

4. DEPENDENCY MAP
   Identify important dependencies between modules and services.

   Highlight:
   - tight coupling
   - circular dependencies
   - shared state
   - shared databases
   - synchronous dependencies
   - asynchronous dependencies

5. DATA MODEL
   Identify:
   - major entities
   - databases/tables
   - ownership of data
   - where important state is created or mutated
   - cross-component data dependencies

6. BUSINESS LOGIC
   Identify important business rules encoded in the implementation,
   especially rules that are not obvious from documentation.

7. LEGACY COMPLEXITY
   Identify evidence of:
   - architectural complexity
   - unnecessary indirection
   - outdated frameworks/libraries
   - distributed coordination
   - duplicated logic
   - fragile integrations
   - hard-to-test areas
   - dead or potentially unused components

   Do not recommend fixes yet.

8. TEST AND SAFETY SURFACE
   Identify:
   - current tests
   - integration tests
   - contract tests
   - important behaviors with little/no coverage
   - interfaces whose behavior must be preserved during modernization

9. EXTERNAL CONTRACTS
   Document interfaces that consumers may rely on:
   - REST APIs
   - event schemas
   - database contracts
   - file formats
   - CLI interfaces
   - configuration formats

10. CURRENT-STATE ARCHITECTURE

Create a component-level representation of the existing architecture.

For each component include:
- responsibility
- technology
- dependencies
- inputs
- outputs
- persistence
- communication mechanism

11. MODERNIZATION RISK AREAS

Identify components that appear high-risk to change based on:
- coupling
- complexity
- missing tests
- number of dependencies
- critical business logic
- shared data ownership

Do not propose the replacement yet.

OUTPUT

Create:

docs/modernization/CURRENT_STATE_ANALYSIS.md

with sections:

# Executive Summary
# System Purpose
# Repository Structure
# Current Architecture
# Component Inventory
# Key Execution Flows
# Dependency Map
# Data Model
# Business Rules
# External Contracts
# Testing / Validation Surface
# Complexity & Technical Debt
# Modernization Risk Areas
# Open Questions

Also create:

docs/modernization/current-state.md

containing a Mermaid component/flow diagram representing the current system.

Before finishing, perform a second pass over the repository and identify
important files/components that were missed during the first analysis.

When finished, end your last message with exactly this block (fill in real values):

===REFACTOR_RESULT===
legacy_branch: <branch you pushed on the legacy repo>
modern_branch:
artifacts: docs/modernization/CURRENT_STATE_ANALYSIS.md, docs/modernization/current-state.md
===END_REFACTOR_RESULT===
"""


def run_analysis_workflow(config: Config, state: WorkflowState) -> int:
    stamp = date.today().strftime("%Y%m%d")
    print("workflow  Analyze", flush=True)
    try:
        with cloud_agent_session(
            config,
            name=f"Analyze {stamp}",
            legacy_ref=config.legacy_ref,
            modern_ref=config.modern_ref,
        ) as agent:
            state.analyze_agent_id = agent.agent_id
            save_state(state)
            completed_run = run_agent_prompt(
                agent, build_analysis_prompt(config, stamp), verbose=config.verbose
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
    if workflow_result.legacy_branch:
        state.analyze_branch = workflow_result.legacy_branch
    elif not state.analyze_branch:
        state.analyze_branch = f"refactor/analyze-{stamp}"
    save_state(state)
    print(f"analyze branch  {state.analyze_branch}", flush=True)
    if workflow_result.artifacts:
        print(f"artifacts       {workflow_result.artifacts}", flush=True)
    return 0
