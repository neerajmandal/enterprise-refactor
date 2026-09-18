"""Print the live or quiet stream from an in-progress cloud run."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from typing import Any

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPIN_INTERVAL = 0.1
_DETAIL_LIMIT = 160


def _clear_spinner_line() -> None:
    if sys.stdout.isatty():
        width = max(48, shutil.get_terminal_size((80, 24)).columns)
        sys.stdout.write("\r" + " " * width + "\r")
        sys.stdout.flush()


def _elapsed_clock(started: float, now: float | None = None) -> str:
    elapsed = max(0, int((now if now is not None else time.monotonic()) - started))
    minutes, seconds = divmod(elapsed, 60)
    return f"{minutes}:{seconds:02d}"


class _QuietProgress:
    """One-line spinner: elapsed time, cloud phase, last tool name."""

    def __init__(self) -> None:
        self._phase = "starting"
        self._tool = "waiting"
        self._started = time.monotonic()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._tty = sys.stdout.isatty()

    def start(self) -> None:
        if not self._tty:
            return
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def set_phase(self, status: str) -> None:
        value = " ".join(str(status or "").split()).lower()
        if not value:
            return
        with self._lock:
            self._phase = value
        if not self._tty:
            print(f"status {value}", flush=True)

    def set_tool(self, name: str) -> None:
        value = " ".join(str(name or "").split())
        if not value:
            return
        with self._lock:
            if value == self._tool:
                return
            self._tool = value
        if not self._tty:
            print(f"tool   {value}", flush=True)

    def _render(self, frame: int) -> str:
        mark = _SPINNER[frame % len(_SPINNER)]
        with self._lock:
            phase = self._phase
            tool = self._tool
        line = f"  {mark}  {_elapsed_clock(self._started)}  {phase}  ·  {tool}"
        width = max(48, shutil.get_terminal_size((80, 24)).columns)
        if len(line) > width:
            line = line[: width - 1] + "…"
        return line.ljust(width)

    def _spin(self) -> None:
        frame = 0
        while not self._stop.wait(_SPIN_INTERVAL):
            sys.stdout.write("\r" + self._render(frame))
            sys.stdout.flush()
            frame += 1

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        _clear_spinner_line()


def _one_line(value: object, limit: int = _DETAIL_LIMIT) -> str:
    text = " ".join(str(value).split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _tool_detail(args: object) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return _one_line(args)
    if isinstance(args, Mapping):
        for key in (
            "command",
            "path",
            "file_path",
            "pattern",
            "query",
            "url",
            "glob",
            "target_directory",
        ):
            found = args.get(key)
            if found:
                return _one_line(found)
        for found in args.values():
            if isinstance(found, str) and found.strip():
                return _one_line(found)
    return _one_line(args)


def _field(message: object, name: str, default: Any = "") -> Any:
    if isinstance(message, Mapping):
        return message.get(name, default)
    return getattr(message, name, default)


def _write_label(label: str, text: str) -> None:
    print(f"{label:<6} {text}".rstrip(), flush=True)


def _break_from_text(last_kind: str) -> None:
    if last_kind == "assistant":
        print("", flush=True)


def _assistant_texts(message: object) -> list[str]:
    inner = _field(message, "message", None)
    content = _field(inner, "content", ()) if inner is not None else ()
    texts: list[str] = []
    for block in content or ():
        text = _field(block, "text", "")
        if text:
            texts.append(str(text))
    return texts


def write_quiet_feed(messages: Iterator[Any]) -> bool:
    """Drain the stream; show a spinner plus the latest tool name."""
    progress = _QuietProgress()
    progress.start()
    streamed = False
    try:
        for message in messages:
            streamed = True
            kind = str(_field(message, "type", "") or "")
            if kind == "status":
                progress.set_phase(str(_field(message, "status", "") or ""))
            elif kind == "tool_call":
                progress.set_tool(str(_field(message, "name", "") or ""))
        return streamed
    finally:
        progress.close()


def write_live_feed(messages: Iterator[Any]) -> bool:
    """Print thinking, tools, tasks, status, usage, and assistant text."""
    last_kind = ""
    streamed = False
    for message in messages:
        kind = str(_field(message, "type", "") or "")
        if kind == "assistant":
            texts = _assistant_texts(message)
            if not texts:
                continue
            if last_kind and last_kind != "assistant":
                print("", flush=True)
            for text in texts:
                sys.stdout.write(text)
                sys.stdout.flush()
            last_kind = "assistant"
            streamed = True
            continue
        if kind == "thinking":
            text = _field(message, "text", "")
            if not text:
                continue
            _break_from_text(last_kind)
            duration = _field(message, "thinking_duration_ms", None)
            _write_label("think", f"{duration}ms" if duration else "")
            for line in str(text).splitlines() or [""]:
                print(f"       {line}", flush=True)
            last_kind = "thinking"
            streamed = True
            continue
        if kind == "tool_call":
            _break_from_text(last_kind)
            line = "  ".join(
                part
                for part in (
                    str(_field(message, "name", "") or ""),
                    str(_field(message, "status", "") or ""),
                    _tool_detail(_field(message, "args", None)),
                )
                if part
            )
            _write_label("tool", line)
            last_kind = "tool_call"
            streamed = True
            continue
        if kind == "task":
            _break_from_text(last_kind)
            _write_label(
                "task",
                "  ".join(
                    part
                    for part in (
                        str(_field(message, "status", "") or ""),
                        _one_line(_field(message, "text", "")),
                    )
                    if part
                ),
            )
            last_kind = "task"
            streamed = True
            continue
        if kind == "status":
            _break_from_text(last_kind)
            _write_label(
                "status",
                "  ".join(
                    part
                    for part in (
                        str(_field(message, "status", "") or ""),
                        _one_line(_field(message, "message", "")),
                    )
                    if part
                ),
            )
            last_kind = "status"
            streamed = True
            continue
        if kind == "usage":
            usage = _field(message, "usage", None)
            if usage is None:
                continue
            _break_from_text(last_kind)
            _write_label(
                "usage",
                (
                    f"in={_field(usage, 'input_tokens', 0)}  "
                    f"out={_field(usage, 'output_tokens', 0)}  "
                    f"total={_field(usage, 'total_tokens', 0)}"
                ),
            )
            last_kind = "usage"
            streamed = True
    if streamed:
        print("", flush=True)
    return streamed
