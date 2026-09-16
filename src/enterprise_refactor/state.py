"""Persisted workflow IDs and branch names (not secrets)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_PATH = Path(".refactor/state.json")


@dataclass
class WorkflowState:
    analyze_agent_id: str = ""
    analyze_branch: str = ""
    plan_agent_id: str = ""
    plan_branch: str = ""
    implement_agent_id: str = ""
    implement_branch: str = ""


def load_state(path: Path = STATE_PATH) -> WorkflowState:
    if not path.is_file():
        return WorkflowState()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return WorkflowState()
    if not isinstance(raw, dict):
        return WorkflowState()
    return WorkflowState(
        analyze_agent_id=str(raw.get("analyze_agent_id") or ""),
        analyze_branch=str(raw.get("analyze_branch") or ""),
        plan_agent_id=str(raw.get("plan_agent_id") or ""),
        plan_branch=str(raw.get("plan_branch") or ""),
        implement_agent_id=str(raw.get("implement_agent_id") or ""),
        implement_branch=str(raw.get("implement_branch") or ""),
    )


def save_state(state: WorkflowState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n")
