"""Raw terminal key reading and cursor visibility."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from contextlib import contextmanager

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
    seq = _read_csi(fd)
    key = _ARROW_KEYS.get(seq)
    if key:
        return key
    if len(seq) >= 3 and seq[-1:] == b"A":
        return "up"
    if len(seq) >= 3 and seq[-1:] == b"B":
        return "down"
    return "back"


def _read_csi(fd: int) -> bytes:
    """Read one ESC / CSI sequence. Do not swallow following pasted text."""
    seq = bytearray(b"\x1b")
    if not select.select([fd], [], [], 0.08)[0]:
        return bytes(seq)
    nxt = _read_byte(fd)
    if not nxt:
        return bytes(seq)
    seq.extend(nxt)
    if nxt == b"O":
        if select.select([fd], [], [], 0.08)[0]:
            seq.extend(_read_byte(fd))
        return bytes(seq)
    if nxt != b"[":
        return bytes(seq)
    while select.select([fd], [], [], 0.08)[0]:
        ch = _read_byte(fd)
        if not ch:
            break
        seq.extend(ch)
        if 0x40 <= ch[0] <= 0x7E:
            break
    return bytes(seq)


def _read_bracketed_paste(fd: int) -> str:
    buf = bytearray()
    end = b"\x1b[201~"
    while True:
        ch = _read_byte(fd)
        if not ch:
            break
        buf.extend(ch)
        if buf.endswith(end):
            buf = buf[: -len(end)]
            break
    return bytes(buf).decode("utf-8", "replace")


def _normalize_paste(text: str) -> str:
    return (
        text.replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )


def _drain_insert(fd: int, first: str) -> str:
    parts = [first]
    while select.select([fd], [], [], 0)[0]:
        nxt = _read_byte(fd)
        if not nxt:
            break
        if nxt == b"\x1b":
            seq = _read_csi(fd)
            if seq == b"\x1b[201~":
                break
            if seq == b"\x1b[200~":
                parts.append(_normalize_paste(_read_bracketed_paste(fd)))
                break
            continue
        if nxt in {b"\r", b"\n"}:
            parts.append(" ")
            continue
        if nxt in {b"\x7f", b"\x08", b"\x03"}:
            break
        parts.append(_read_utf8(fd, nxt))
    return "".join(parts)


def _read_utf8(fd: int, first: bytes) -> str:
    lead = first[0]
    extra = 0 if lead < 0x80 else 1 if lead < 0xE0 else 2 if lead < 0xF0 else 3
    buf = bytearray(first)
    for _ in range(extra):
        nxt = _read_byte(fd)
        if not nxt:
            break
        buf.extend(nxt)
    return bytes(buf).decode("utf-8", "replace")


@contextmanager
def raw_text_input():
    """Stay raw for the whole field so Cmd+V paste is not flushed."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd, when=termios.TCSANOW)
        attrs = termios.tcgetattr(fd)
        attrs[1] |= termios.OPOST | getattr(termios, "ONLCR", 0)
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()
        yield fd
    finally:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSANOW, old)


def read_edit_event(fd: int) -> tuple[str, str]:
    """One editor event. Returns (kind, payload). Assumes stdin is already raw."""
    first = _read_byte(fd)
    if first == b"\x03":
        raise KeyboardInterrupt
    if first in {b"\r", b"\n"}:
        return "enter", ""
    if first in {b"\x7f", b"\x08"}:
        return "backspace", ""
    if first == b"\x1b":
        seq = _read_csi(fd)
        if seq == b"\x1b":
            return "cancel", ""
        if seq == b"\x1b[200~":
            return "insert", _normalize_paste(_read_bracketed_paste(fd))
        if seq == b"\x1b[201~":
            return "ignore", ""
        if _ARROW_KEYS.get(seq) or (len(seq) >= 3 and seq[-1:] in b"ABCD"):
            return "ignore", ""
        return "ignore", ""
    if not first:
        return "ignore", ""
    text = _drain_insert(fd, _read_utf8(fd, first))
    printable = "".join(ch for ch in text if ch.isprintable() or ch == " ")
    if not printable:
        return "ignore", ""
    return "insert", printable


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
