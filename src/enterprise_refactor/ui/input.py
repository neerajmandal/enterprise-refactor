"""Raw terminal key reading and cursor visibility."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

_ARROW_KEYS = {
    b"\x1b[A": "up",
    b"\x1bOA": "up",
    b"\x1b[B": "down",
    b"\x1bOB": "down",
    b"\x1b[C": "right",
    b"\x1bOC": "right",
    b"\x1b[D": "back",
    b"\x1bOD": "back",
}


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _read_byte(fd: int) -> bytes:
    # os.read avoids TextIO buffering, which can swallow "[A" after ESC
    # and make select() think no arrow-key bytes remain.
    data = os.read(fd, 1)
    if not data:
        return b""
    return data


def _read_escape(fd: int) -> str:
    seq = bytearray(b"\x1b")
    while select.select([fd], [], [], 0.08)[0]:
        chunk = os.read(fd, 8)
        if not chunk:
            break
        seq.extend(chunk)
        if seq[-1:] in b"ABCD~" or (len(seq) >= 3 and seq[1:2] == b"O"):
            break
    key = _ARROW_KEYS.get(bytes(seq))
    if key:
        return key
    if len(seq) >= 3 and seq[-1:] == b"A":
        return "up"
    if len(seq) >= 3 and seq[-1:] == b"B":
        return "down"
    return "back"


def read_key(*, number_keys: int = 0) -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = _read_byte(fd)
        if first == b"\x03":
            raise KeyboardInterrupt
        if first in {b"\r", b"\n"}:
            return "enter"
        if first in {b"q", b"Q"}:
            return "quit"
        if first in {b"b", b"B"}:
            return "back"
        if number_keys and first in {str(i).encode() for i in range(1, number_keys + 1)}:
            return first.decode()
        if first in {b"k", b"K"}:
            return "up"
        if first in {b"j", b"J"}:
            return "down"
        if first == b"\x1b":
            return _read_escape(fd)
        return first.decode("utf-8", "replace")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
