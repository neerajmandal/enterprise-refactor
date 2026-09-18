"""TUI to pick the target plan or implement branch."""

from __future__ import annotations

from enterprise_refactor.config import Config
from enterprise_refactor.git.branch_list import IMPLEMENT_PREFIX, PLAN_PREFIX
from enterprise_refactor.pickers.analyze_branch import resolve_remote_branch
from enterprise_refactor.state import WorkflowState


def resolve_target_implement_branch(
    config: Config,
    state: WorkflowState,
    *,
    plan_branch: str | None,
) -> str | None:
    return resolve_remote_branch(
        config,
        title="Implement",
        subtitle="Choose the target branch Implement will fetch and work on.",
        repo_url=config.modern_repo,
        preferred_prefix=IMPLEMENT_PREFIX,
        preferred_label="Implement",
        kind_badge="implement",
        saved=state.implement_branch or state.plan_branch,
        fallback=config.modern_ref,
        flagged=plan_branch,
        ask_label="Target branch",
        missing_hint=(
            "Pass --plan-branch or run this command in a terminal "
            "to pick a target branch."
        ),
        preferred_kinds=(
            (IMPLEMENT_PREFIX, "Implement", "implement"),
            (PLAN_PREFIX, "Plan", "plan"),
        ),
    )
