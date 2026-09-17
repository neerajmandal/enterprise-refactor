"""Fetch plan.json from a target branch and pick which phases to implement."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from enterprise_refactor.banner import (
    DIM,
    MUTED,
    WHITE,
    _c,
    paint_menu_row,
    print_screen,
    render_page,
    repo_label,
    term_size,
)
from enterprise_refactor.branches import github_owner_repo, remote_url
from enterprise_refactor.config import Config
from enterprise_refactor.menu import _hide_cursor, _read_key, _show_cursor

PLAN_JSON_PATH = "docs/refactor/plan.json"

FOOTER_PHASES: tuple[tuple[str, str], ...] = (
    ("↑↓", "navigate"),
    ("space", "toggle"),
    ("a", "all remaining"),
    ("enter", "run"),
    ("esc", "back"),
    ("q", "quit"),
)

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


@dataclass(frozen=True)
class PhaseSelection:
    ids: tuple[str, ...] | None
    all_remaining: bool = False


def parse_phase_flag(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


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


def _phase_detail(phase: Phase, selected: bool) -> str:
    if phase.done:
        return "done"
    return "selected" if selected else "pending"


def render_phase_picker(
    *,
    config: Config,
    branch: str,
    phases: list[Phase],
    selected_ids: set[str],
    index: int,
    error: str = "",
    hint: str = "",
) -> str:
    width, height = term_size()
    pending = pending_phases(phases)
    done_count = len(phases) - len(pending)
    count = (
        f"{len(pending)} pending"
        + (f"  ·  {done_count} done" if done_count else "")
    )
    body = [
        _c(WHITE, "  Implement"),
        _c(DIM, f"  Phases on {branch}  ·  {repo_label(config.modern_repo)}"),
        "",
        f"  {_c(DIM, 'Plan'.ljust(16))}{_c(WHITE, count)}",
        "",
    ]
    if error:
        body.extend([_c(MUTED, f"  {error}"), ""])
    if hint:
        body.extend([_c(DIM, f"  {hint}"), ""])

    for i, phase in enumerate(phases):
        if phase.done:
            icon = "✓"
            title = phase.title
        else:
            icon = "☑" if phase.id in selected_ids else "☐"
            title = phase.title
        body.append(
            paint_menu_row(
                number=f"{i + 1}" if i < 9 else "",
                icon=icon,
                title=title,
                detail=_phase_detail(phase, phase.id in selected_ids),
                width=width,
                selected=i == index,
                title_col=36,
            )
        )

    body.append("")
    action_start = len(phases)
    all_enabled = bool(pending)
    selected_enabled = bool(selected_ids)
    body.append(
        paint_menu_row(
            number="a",
            icon="▸",
            title="Implement all remaining",
            detail=(
                "every pending phase"
                if all_enabled or (error and not phases)
                else "nothing pending"
            ),
            width=width,
            selected=index == action_start,
            title_col=36,
        )
    )
    body.append(
        paint_menu_row(
            number="",
            icon="▸",
            title="Implement selected",
            detail=(
                f"{len(selected_ids)} phase"
                + ("s" if len(selected_ids) != 1 else "")
                if selected_enabled
                else "toggle pending phases first"
            ),
            width=width,
            selected=index == action_start + 1,
            title_col=36,
        )
    )
    body.append(
        paint_menu_row(
            number="",
            icon="←",
            title="Back",
            detail="return to the branch list",
            width=width,
            selected=index == action_start + 2,
            title_col=36,
        )
    )
    return render_page(
        legacy_repo=config.legacy_repo,
        modern_repo=config.modern_repo,
        cursor_env=config.cursor_env,
        model=config.model,
        body=body,
        footer_actions=FOOTER_PHASES,
    )


def choose_phases(
    phases: list[Phase],
    *,
    config: Config,
    branch: str,
    error: str = "",
) -> PhaseSelection | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return PhaseSelection(ids=None, all_remaining=True)

    selected: set[str] = set()
    total = len(phases) + 3
    index = 0 if phases else 0
    hint = ""
    allow_unlisted = bool(error) and not phases
    _hide_cursor()
    try:
        while True:
            print_screen(
                render_phase_picker(
                    config=config,
                    branch=branch,
                    phases=phases,
                    selected_ids=selected,
                    index=index,
                    error=error,
                    hint=hint,
                )
            )
            key = _read_key(number_keys=min(9, len(phases)))
            hint = ""
            if key == "up":
                index = (index - 1) % total
            elif key == "down":
                index = (index + 1) % total
            elif key in {str(i) for i in range(1, min(9, len(phases)) + 1)}:
                index = int(key) - 1
            elif key in {"a", "A"}:
                if allow_unlisted:
                    return PhaseSelection(ids=None, all_remaining=True)
                remaining = [phase.id for phase in pending_phases(phases)]
                if not remaining:
                    hint = "Nothing pending to implement."
                    continue
                return PhaseSelection(ids=tuple(remaining), all_remaining=True)
            elif key == " ":
                if index < len(phases) and not phases[index].done:
                    phase_id = phases[index].id
                    if phase_id in selected:
                        selected.discard(phase_id)
                    else:
                        selected.add(phase_id)
            elif key == "enter":
                if index < len(phases):
                    phase = phases[index]
                    if phase.done:
                        hint = "That phase is already done."
                        continue
                    if phase.id not in selected and not selected:
                        chosen = expand_dependencies(phases, [phase.id])
                        return PhaseSelection(ids=tuple(chosen), all_remaining=False)
                    if selected:
                        chosen = expand_dependencies(phases, list(selected))
                        return PhaseSelection(ids=tuple(chosen), all_remaining=False)
                    hint = "Toggle pending phases, or use Implement all remaining."
                    continue
                if index == len(phases):
                    if allow_unlisted:
                        return PhaseSelection(ids=None, all_remaining=True)
                    remaining = [phase.id for phase in pending_phases(phases)]
                    if not remaining:
                        hint = "Nothing pending to implement."
                        continue
                    return PhaseSelection(ids=tuple(remaining), all_remaining=True)
                if index == len(phases) + 1:
                    if not selected:
                        hint = "Toggle pending phases first."
                        continue
                    chosen = expand_dependencies(phases, list(selected))
                    return PhaseSelection(ids=tuple(chosen), all_remaining=False)
                return None
            elif key in {"back", "esc"}:
                return None
            elif key == "quit":
                raise SystemExit(0)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        _show_cursor()


def choose_phases_or_fallback(
    *,
    config: Config,
    branch: str,
    flagged: list[str] | None,
    allow_picker: bool,
) -> PhaseSelection | None:
    if flagged:
        phases, error = load_phases(config.modern_repo, branch)
        if phases:
            known = {phase.id for phase in phases}
            missing = [phase_id for phase_id in flagged if phase_id not in known]
            if missing:
                raise SystemExit(
                    "Unknown --phases id(s): " + ", ".join(missing)
                )
            return PhaseSelection(
                ids=tuple(expand_dependencies(phases, flagged)),
                all_remaining=False,
            )
        return PhaseSelection(ids=tuple(flagged), all_remaining=False)

    if not allow_picker:
        return PhaseSelection(ids=None, all_remaining=True)

    print_screen(
        render_page(
            legacy_repo=config.legacy_repo,
            modern_repo=config.modern_repo,
            cursor_env=config.cursor_env,
            model=config.model,
            body=[
                _c(WHITE, "  Implement"),
                _c(DIM, f"  Reading {PLAN_JSON_PATH} on {branch}…"),
            ],
        )
    )
    phases, error = load_phases(config.modern_repo, branch)
    if not phases:
        return choose_phases([], config=config, branch=branch, error=error)
    return choose_phases(phases, config=config, branch=branch, error="")
