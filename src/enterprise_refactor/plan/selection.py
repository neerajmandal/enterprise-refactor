"""Phase selection values and --phases flag parsing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseSelection:
    ids: tuple[str, ...] | None
    all_remaining: bool = False


def parse_phase_flag(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    return [part.strip() for part in value.split(",") if part.strip()]
