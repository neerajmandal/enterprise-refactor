"""Fetch and parse docs/refactor/plan.json. No terminal UI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from enterprise_refactor.integrations.git.remotes import github_owner_repo, remote_url

PLAN_JSON_PATH = "docs/refactor/plan.json"

_PHASE_NUM = re.compile(r"(?:phase\s*)?(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Phase:
    id: str
    title: str
    depends_on: tuple[str, ...] = ()
    status: str = "todo"
    test_command: str = ""
    done_when: str = ""

    @property
    def done(self) -> bool:
        return self.status.strip().lower() == "done"


def parse_plan_json(raw: str) -> list[Phase]:
    data = json.loads(raw)
    if isinstance(data, dict):
        items = data.get("phases")
        if items is None:
            items = data.get("items")
        if items is None:
            items = []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    phases: list[Phase] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        phase_id = str(item.get("id") or f"{index:02d}").strip()
        title = str(item.get("title") or phase_id).strip()
        depends = item.get("depends_on") or []
        if isinstance(depends, str):
            deps = (depends,) if depends.strip() else ()
        else:
            deps = tuple(str(dep).strip() for dep in depends if str(dep).strip())
        phases.append(
            Phase(
                id=phase_id,
                title=title,
                depends_on=deps,
                status=str(item.get("status") or "todo"),
                test_command=str(item.get("test_command") or ""),
                done_when=str(item.get("done_when") or ""),
            )
        )
    return phases


def pending_phases(phases: list[Phase]) -> list[Phase]:
    return [phase for phase in phases if not phase.done]


def _resolve_dep(dep: str, phases: list[Phase]) -> str | None:
    raw = dep.strip()
    by_id = {phase.id: phase for phase in phases}
    if raw in by_id:
        return raw
    lowered = raw.lower()
    for phase in phases:
        if phase.title.lower() == lowered:
            return phase.id
    match = _PHASE_NUM.fullmatch(raw.strip()) or _PHASE_NUM.search(raw)
    if match:
        number = int(match.group(1))
        if 1 <= number <= len(phases):
            return phases[number - 1].id
        padded = f"{number:02d}"
        for phase in phases:
            if phase.id == padded or phase.id.startswith(f"{padded}-"):
                return phase.id
    return None


def expand_dependencies(phases: list[Phase], selected: list[str]) -> list[str]:
    wanted = set(selected)
    by_id = {phase.id: phase for phase in phases}
    changed = True
    while changed:
        changed = False
        for phase_id in list(wanted):
            phase = by_id.get(phase_id)
            if phase is None:
                continue
            for dep in phase.depends_on:
                dep_id = _resolve_dep(dep, phases)
                if not dep_id:
                    continue
                dep_phase = by_id.get(dep_id)
                if dep_phase is None or dep_phase.done:
                    continue
                if dep_id not in wanted:
                    wanted.add(dep_id)
                    changed = True
    return [phase.id for phase in phases if phase.id in wanted]


def _run(command: list[str], *, env: dict[str, str] | None = None) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _plan_from_gh(url: str, branch: str) -> str | None:
    owner_repo = github_owner_repo(url)
    if owner_repo is None or shutil.which("gh") is None:
        return None
    owner, repo = owner_repo
    return _run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{owner}/{repo}/contents/{PLAN_JSON_PATH}?ref={branch}",
        ]
    )


def _plan_from_git(url: str, branch: str) -> str | None:
    if shutil.which("git") is None:
        return None
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    with tempfile.TemporaryDirectory(prefix="refactor-plan-") as tmp:
        if (
            _run(["git", "init", "--quiet", tmp], env=env) is None
            or _run(
                ["git", "-C", tmp, "remote", "add", "origin", remote_url(url)],
                env=env,
            )
            is None
        ):
            return None
        fetch = subprocess.run(
            [
                "git",
                "-C",
                tmp,
                "fetch",
                "--depth",
                "1",
                "--quiet",
                "origin",
                branch,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if fetch.returncode != 0:
            return None
        return _run(
            ["git", "-C", tmp, "show", f"FETCH_HEAD:{PLAN_JSON_PATH}"],
            env=env,
        )


def fetch_plan_json(url: str, branch: str) -> tuple[str | None, str]:
    for loader in (_plan_from_gh, _plan_from_git):
        raw = loader(url, branch)
        if raw:
            return raw, ""
    return None, f"Could not read {PLAN_JSON_PATH} on {branch}."


def load_phases(url: str, branch: str) -> tuple[list[Phase], str]:
    raw, error = fetch_plan_json(url, branch)
    if raw is None:
        return [], error
    try:
        phases = parse_plan_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        return [], f"Invalid {PLAN_JSON_PATH}: {err}"
    if not phases:
        return [], f"{PLAN_JSON_PATH} has no phases."
    return phases, ""
