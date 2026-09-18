"""TUI to choose which plan.json phases Implement should run."""

from __future__ import annotations

import sys

from enterprise_refactor.config import Config
from enterprise_refactor.plan.document import (
    PLAN_JSON_PATH,
    Phase,
    expand_dependencies,
    load_phases,
    pending_phases,
)
from enterprise_refactor.plan.selection import PhaseSelection
from enterprise_refactor.ui.input import hide_cursor, read_key, show_cursor
from enterprise_refactor.ui.layout import (
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


def _selection_for(
    phases: list[Phase], chosen: list[str], *, all_remaining: bool
) -> PhaseSelection:
    pending = {phase.id for phase in pending_phases(phases)}
    ids = tuple(chosen)
    if all_remaining:
        return PhaseSelection(ids=ids, all_remaining=True)
    return PhaseSelection(
        ids=ids, all_remaining=bool(pending) and pending <= set(ids)
    )


FOOTER_PHASES: tuple[tuple[str, str], ...] = (
    ("↑↓", "navigate"),
    ("space", "toggle"),
    ("a", "all remaining"),
    ("enter", "run"),
    ("esc", "back"),
    ("q", "quit"),
)


def _phase_detail(phase: Phase, selected: bool) -> str:
    if phase.is_computer_use:
        if phase.done:
            return "done"
        return "UI last" if selected else "UI after unit tests"
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
        else:
            icon = "☑" if phase.id in selected_ids else "☐"
        body.append(
            paint_menu_row(
                number=f"{i + 1}" if i < 9 else "",
                icon=icon,
                title=phase.title,
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
                "unit tests, then last-phase UI"
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
    hide_cursor()
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
            key = read_key(number_keys=min(9, len(phases)))
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
                return _selection_for(phases, remaining, all_remaining=True)
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
                        return _selection_for(phases, chosen, all_remaining=False)
                    if selected:
                        chosen = expand_dependencies(phases, list(selected))
                        return _selection_for(phases, chosen, all_remaining=False)
                    hint = "Toggle pending phases, or use Implement all remaining."
                    continue
                if index == len(phases):
                    if allow_unlisted:
                        return PhaseSelection(ids=None, all_remaining=True)
                    remaining = [phase.id for phase in pending_phases(phases)]
                    if not remaining:
                        hint = "Nothing pending to implement."
                        continue
                    return _selection_for(phases, remaining, all_remaining=True)
                if index == len(phases) + 1:
                    if not selected:
                        hint = "Toggle pending phases first."
                        continue
                    chosen = expand_dependencies(phases, list(selected))
                    return _selection_for(phases, chosen, all_remaining=False)
                return None
            elif key in {"back", "esc"}:
                return None
            elif key == "quit":
                raise SystemExit(0)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise
    finally:
        show_cursor()


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
            return _selection_for(
                phases, expand_dependencies(phases, flagged), all_remaining=False
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
