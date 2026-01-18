from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
import textwrap
import atexit
from collections import deque
from pathlib import Path

CSI = "\x1b["
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

SELECT_RE = re.compile(r"\[SELECT\]\s+Active symbol:\s+(?P<symbol>[A-Z0-9]+)\s+\(")
LOG_PREFIX_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<level>\[[A-Z]+\])\s+(?P<module>[^-]+?)\s+-\s+(?P<rest>.*)$"
)
LOG_TIME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<rest>.*)$")


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    term = os.getenv("TERM", "")
    if term in ("dumb", ""):
        return False
    return True


def _style(
    text: str,
    *,
    fg: int | None = None,
    bg: int | None = None,
    bold: bool = False,
    dim: bool = False,
    enable: bool = True,
) -> str:
    if not enable:
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if fg is not None:
        codes.append(f"38;5;{fg}")
    if bg is not None:
        codes.append(f"48;5;{bg}")
    if not codes:
        return text
    return f"{CSI}{';'.join(codes)}m{text}{CSI}0m"


def _term_width(default: int = 100) -> int:
    try:
        return max(80, shutil.get_terminal_size((default, 24)).columns)
    except Exception:
        return default


def _box(title: str, body_lines: list[str], *, width: int, color_on: bool) -> str:
    inner = max(10, width - 2)
    t = f" {title} "
    t = t[: max(0, inner - 2)]
    top = "╭" + "─" * ((inner - len(t)) // 2) + t + "─" * (inner - ((inner - len(t)) // 2) - len(t)) + "╮"
    mid: list[str] = []
    for line in body_lines:
        visible = ANSI_RE.sub("", line)
        if len(visible) > inner:
            line = visible[:inner]
            visible = line
        pad = max(0, inner - len(visible))
        mid.append(f"│{line}{' ' * pad}│")
    bot = "╰" + "─" * inner + "╯"
    if not color_on:
        return "\n".join([top, *mid, bot])
    return "\n".join(
        [
            _style(top, fg=39, dim=True, enable=True),
            *[_style(l, fg=250, enable=True) for l in mid],
            _style(bot, fg=39, dim=True, enable=True),
        ]
    )


def _wrap_lines(text: str, *, width: int) -> list[str]:
    if not text.strip():
        return [""]
    out: list[str] = []
    for raw in text.splitlines():
        raw = raw.rstrip("\n")
        if len(raw) > 2000:
            raw = raw[:2000] + " …"
        if not raw:
            out.append("")
            continue
        out.extend(textwrap.wrap(raw, width=width, replace_whitespace=False, drop_whitespace=False))
    return out or [""]


def _highlight(line: str, *, color_on: bool) -> str:
    text = line.rstrip("\n")
    upper = text.upper()
    if " ERROR " in text or "[ERROR]" in upper or "TRACEBACK" in upper:
        return _style(text, fg=231, bg=124, bold=True, enable=color_on)
    if " WARNING " in text or "[WARNING]" in upper or "[WARN]" in upper:
        return _style(text, fg=231, bg=166, bold=True, enable=color_on)

    tag_colors = {
        "INFO": 81,
        "DEBUG": 244,
        "WARN": 214,
        "WARNING": 214,
        "ERROR": 196,
        "CRITICAL": 196,
        "STRUCTURE": 178,
        "SELECT": 81,
        "CYCLE": 141,
        "DECISION": 117,
        "EXEC": 79,
        "SABBATH": 135,
        "HOLDINGS": 110,
        "PAIR_SELECTOR": 69,
        "CCXT": 39,
        "COINBASE": 33,
        "HTTPX": 135,
        "OVERRIDE": 214,
    }

    def _color_tags(chunk: str) -> str:
        out = ""
        last = 0
        for m in re.finditer(r"\[([A-Z_]+)\]", chunk):
            out += chunk[last : m.start()]
            tag = m.group(1)
            color = tag_colors.get(tag, 252)
            out += _style(m.group(0), fg=color, bold=True, enable=color_on)
            last = m.end()
        out += chunk[last:]
        return out

    if "CONTINUATION" in upper and "NO_CONTINUATION" not in upper:
        last_bracket = text.rfind("]")
        if last_bracket != -1:
            head = text[: last_bracket + 1]
            tail = text[last_bracket + 1 :]
            head = _color_tags(head)
            tail = _style(tail, fg=228, enable=color_on)
            return head + tail

    return _style(_color_tags(text), fg=250, enable=color_on)


def _format_log_line(line: str) -> str:
    text = line.rstrip("\n")
    m = LOG_PREFIX_RE.match(text)
    if m:
        return f"{m.group('time')} {m.group('level')} {m.group('rest')}"
    m = LOG_TIME_RE.match(text)
    if m:
        return f"{m.group('time')} {m.group('rest')}"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Styled log tail view for the tmux left pane.")
    parser.add_argument("--log", default=os.getenv("TRADEBOT_LOG", "logs/tradebot.log"))
    parser.add_argument("--follow", action="store_true", help="Follow the log (tail -F style).")
    parser.add_argument("--interval", type=float, default=0.5, help="Refresh interval (seconds).")
    parser.add_argument("--lines", type=int, default=28, help="Recent log lines to display.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color rendering.")
    args = parser.parse_args()

    color_on = _supports_color() and not args.no_color
    path = Path(args.log)
    screen = _SmoothScreen()
    atexit.register(screen.close)

    if not path.exists():
        print(f"[LOG] waiting: log not found at {path}", file=sys.stderr)
        if not args.follow:
            return 2

    last_inode = None
    last_size = 0
    buffer: deque[str] = deque(maxlen=600)
    active_symbol: str | None = None
    last_event_lines: deque[str] = deque(maxlen=8)

    while True:
        try:
            if path.exists():
                stat = path.stat()
                if last_inode is None or stat.st_ino != last_inode or stat.st_size < last_size:
                    last_inode = stat.st_ino
                    last_size = 0
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    if last_size:
                        f.seek(last_size)
                    chunk = f.read()
                    last_size = f.tell()
            if chunk:
                for line in chunk.splitlines():
                    line = re.sub(r"httpx\s+-\s+", "[HTTPX] ", line)
                    buffer.append(line)
                    upper = line.upper()
                    if "[ERROR]" in upper or " ERROR " in line or "[WARNING]" in upper or "TRACEBACK" in upper:
                        last_event_lines.append(line)
                    if "[STRUCTURE]" in upper or "[SELECT]" in upper or "DECISION:" in upper:
                        last_event_lines.append(line)
                    m = SELECT_RE.search(line)
                    if m:
                        active_symbol = m.group("symbol")

            frame = _render(
                buffer,
                last_event_lines,
                log_path=str(path),
                active_symbol=active_symbol,
                color_on=color_on,
                lines=max(5, args.lines),
            )
            screen.draw(frame)
            if not args.follow:
                return 0
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


class _SmoothScreen:
    def __init__(self) -> None:
        self._last_lines: list[str] = []
        self._cursor_hidden = False

    def _hide_cursor(self) -> None:
        if self._cursor_hidden:
            return
        sys.stdout.write(f"{CSI}?25l")
        self._cursor_hidden = True

    def _show_cursor(self) -> None:
        if not self._cursor_hidden:
            return
        sys.stdout.write(f"{CSI}?25h")
        self._cursor_hidden = False

    def close(self) -> None:
        self._show_cursor()
        sys.stdout.flush()

    def draw(self, frame: str) -> None:
        self._hide_cursor()
        lines = frame.splitlines()
        max_lines = max(len(lines), len(self._last_lines))
        for i in range(max_lines):
            new = lines[i] if i < len(lines) else ""
            old = self._last_lines[i] if i < len(self._last_lines) else None
            if old is not None and new == old:
                continue
            sys.stdout.write(f"{CSI}{i+1};1H{CSI}2K{new}")
        self._last_lines = lines
        sys.stdout.flush()


def _render(
    buffer: deque[str],
    last_event_lines: deque[str],
    *,
    log_path: str,
    active_symbol: str | None,
    color_on: bool,
    lines: int,
) -> str:
    width = _term_width(110)
    title = _style(" TRADEBOT LOG ", fg=231, bg=60, bold=True, enable=color_on)
    subtitle = _style(" Live Tail ", fg=231, bg=237, bold=True, enable=color_on)
    out: list[str] = []
    out.append(title + subtitle)

    right = f"active={active_symbol or '<none>'}"
    left = f"log={Path(log_path).name}"
    gap = max(1, width - len(left) - len(right) - 1)
    out.append(_style(left, fg=252, bold=True, enable=color_on) + " " * gap + _style(right, fg=81, bold=True, enable=color_on))
    out.append(_style("─" * width, fg=238, enable=color_on))

    recent = list(buffer)[-lines:]
    recent_lines: list[str] = []
    for raw in recent:
        formatted = _format_log_line(raw)
        highlighted = _highlight(formatted, color_on=color_on)
        for w in _wrap_lines(highlighted, width=width - 4)[:2]:
            recent_lines.append(w)
    if not recent_lines:
        recent_lines = ["waiting: no log lines yet"]
    recent_lines = [ln[: width - 2] for ln in recent_lines]
    out.append(_box("RECENT LOG", recent_lines, width=width, color_on=color_on))
    out.append("")

    events = list(last_event_lines)[-8:]
    event_lines: list[str] = []
    for raw in events:
        formatted = _format_log_line(raw)
        event_lines.extend(_wrap_lines(_highlight(formatted, color_on=color_on), width=width - 4)[:2])
    if not event_lines:
        event_lines = ["(no recent noteworthy events)"]
    event_lines = [ln[: width - 2] for ln in event_lines]
    out.append(_box("HIGHLIGHTS", event_lines, width=width, color_on=color_on))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
