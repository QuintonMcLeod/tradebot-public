from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


CSI = "\x1b["

TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\b")
IBKR_ORDERID_RE = re.compile(r"\borderId=(?P<id>\d+)\b")
IBKR_ACTION_RE = re.compile(r"\baction='(?P<action>BUY|SELL)'")
IBKR_QTY_RE = re.compile(r"\btotalQuantity=(?P<qty>[-0-9.]+)")
IBKR_STATUS_RE = re.compile(r"\bstatus='(?P<status>[^']+)'")
IBKR_FILLED_RE = re.compile(r"\bfilled=(?P<filled>[-0-9.]+)")
IBKR_AVG_FILL_RE = re.compile(r"\bavgFillPrice=(?P<avg>[-0-9.]+)")
IBKR_ORDERTYPE_RE = re.compile(r"\border=(?P<type>[A-Za-z0-9_]+)\(")
IBKR_TIF_RE = re.compile(r"\btif='(?P<tif>[^']+)'")
IBKR_CONTRACT_SYM_RE = re.compile(r"\bcontract=.*?\bsymbol='(?P<sym>[^']+)'")
IBKR_CONTRACT_CUR_RE = re.compile(r"\bcurrency='(?P<cur>[^']+)'")


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
        visible = line
        if len(visible) > inner:
            visible = visible[:inner]
        pad = max(0, inner - len(visible))
        mid.append(f"│{visible}{' ' * pad}│")
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


@dataclass
class HoldingsState:
    updated_ts: float | None = None
    payload: dict | None = None
    last_error: str | None = None
    orders_by_id: dict[int, "OrderEvent"] | None = None


@dataclass
class OrderEvent:
    ts: str
    symbol: str
    order_id: int
    action: str | None = None
    qty: float | None = None
    order_type: str | None = None
    tif: str | None = None
    status: str | None = None
    filled: float | None = None
    avg_fill_price: float | None = None


def _format_age(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    try:
        s = max(0, int(seconds))
    except Exception:
        return "-"
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h}h{m:02d}m"
    d, h = divmod(h, 24)
    return f"{d}d{h:02d}h"


def _render(state: HoldingsState, *, color_on: bool) -> str:
    width = _term_width(120)
    now = time.time()
    age = None
    if state.updated_ts is not None:
        age = max(0.0, now - state.updated_ts)
    title = "HOLDINGS"
    meta = []
    if state.payload:
        meta.append(f"count={int(state.payload.get('count') or 0)}")
        reason = str(state.payload.get("reason") or "")
        if reason:
            meta.append(f"src={reason}")
    if age is None:
        meta.append("updated=never")
    else:
        meta.append(f"updated={int(age)}s ago")
    if state.last_error:
        meta.append(f"error={state.last_error}")
    title = f"{title}  {' · '.join(meta)}"

    positions = list((state.payload or {}).get("positions") or [])
    inferred_positions: list[dict] = []
    if not positions:
        inferred_positions = _infer_holdings_from_orders(state.orders_by_id)
    lines: list[str] = []
    if not positions and not inferred_positions:
        lines.append("No open positions detected yet.")
        lines.append("Tip: if IBKR isn't connected, this pane can still infer holdings from prior order fills in rotated logs.")
    else:
        if inferred_positions and not positions:
            lines.append(_style("Note: holdings inferred from order fills (no [HOLDINGS] snapshots found).", fg=39, dim=True, enable=color_on))
            positions = inferred_positions
        header = "SYMBOL   SIDE   SIZE        AVG        SL         TP         RISK     WORK  SYNTH  HOLD_AGE  HOLD_REM  STATUSES"
        lines.append(_style(header, fg=81, bold=True, enable=color_on))
        lines.append(_style("─" * min(len(header), width - 2), fg=39, dim=True, enable=color_on))
        for p in positions:
            if not isinstance(p, dict):
                continue
            sym = str(p.get("symbol") or "")[:10].ljust(10)
            side = str(p.get("side") or "")[:5].ljust(5)
            size = p.get("size")
            avg = p.get("avg_price")
            sl = p.get("stop_loss")
            tp = p.get("take_profit")
            risk = p.get("open_bracket_risk")
            work = p.get("working_orders")
            synth = "armed" if bool(p.get("synthetic_stop_armed")) else "-"
            hold_age = _format_age(p.get("hold_age_seconds"))
            hold_rem = _format_age(p.get("hold_remaining_seconds"))
            statuses = ", ".join([str(x) for x in (p.get("working_order_statuses") or [])]) or "-"

            def f4(v: object) -> str:
                if v is None:
                    return "-".rjust(10)
                try:
                    return f"{float(v):.4f}".rjust(10)
                except Exception:
                    return "-".rjust(10)

            def f2(v: object) -> str:
                if v is None:
                    return "-".rjust(8)
                try:
                    return f"{float(v):.2f}".rjust(8)
                except Exception:
                    return "-".rjust(8)

            def fq(v: object) -> str:
                if v is None:
                    return "-".rjust(10)
                try:
                    return f"{float(v):.4f}".rstrip("0").rstrip(".").rjust(10)
                except Exception:
                    return "-".rjust(10)

            work_s = str(int(work)).rjust(4) if work is not None else "   -"
            line = (
                f"{sym} {side} {fq(size)} {f4(avg)} {f4(sl)} {f4(tp)} {f2(risk)}  {work_s}  {synth:<5}  "
                f"{hold_age:>8}  {hold_rem:>8}  {statuses}"
            )
            lines.append(line[: width - 2])

    return _box(title, lines, width=width, color_on=color_on) + "\n"


def _ingest_line(state: HoldingsState, line: str) -> None:
    if "[HOLDINGS]" not in line:
        # Best-effort: also track IBKR orders from ib_insync logs (to infer holdings if needed).
        if "ib_insync" in line and ("placeOrder:" in line or "orderStatus:" in line):
            _ingest_order_line(state, line)
        return
    try:
        payload = line.split("[HOLDINGS]", 1)[1].strip()
        data = json.loads(payload) if payload else {}
        if not isinstance(data, dict):
            return
        state.payload = data
        state.updated_ts = time.time()
        state.last_error = None
    except Exception as exc:
        state.last_error = f"{type(exc).__name__}: {exc}"


def _ingest_order_line(state: HoldingsState, line: str) -> None:
    id_m = IBKR_ORDERID_RE.search(line)
    if not id_m:
        return
    order_id = int(id_m.group("id"))
    ts_m = TS_RE.search(line)
    ts = (ts_m.group("ts") if ts_m else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())).strip()

    sym_m = IBKR_CONTRACT_SYM_RE.search(line)
    cur_m = IBKR_CONTRACT_CUR_RE.search(line)
    contract_sym = (sym_m.group("sym") if sym_m else "").strip().upper()
    contract_cur = (cur_m.group("cur") if cur_m else "").strip().upper()
    symbol = contract_sym
    if contract_sym and contract_cur:
        symbol = f"{contract_sym}{contract_cur}"

    if state.orders_by_id is None:
        state.orders_by_id = {}
    existing = state.orders_by_id.get(order_id)
    evt = existing or OrderEvent(ts=ts, symbol=symbol or "?", order_id=order_id)
    evt.ts = ts
    if symbol:
        evt.symbol = symbol

    action_m = IBKR_ACTION_RE.search(line)
    qty_m = IBKR_QTY_RE.search(line)
    tif_m = IBKR_TIF_RE.search(line)
    status_m = IBKR_STATUS_RE.search(line)
    filled_m = IBKR_FILLED_RE.search(line)
    avg_m = IBKR_AVG_FILL_RE.search(line)
    order_type_m = IBKR_ORDERTYPE_RE.search(line)

    if action_m:
        evt.action = action_m.group("action")
    if qty_m:
        try:
            evt.qty = float(qty_m.group("qty"))
        except Exception:
            pass
    if tif_m:
        evt.tif = tif_m.group("tif")
    if status_m:
        evt.status = status_m.group("status")
    if filled_m:
        try:
            evt.filled = float(filled_m.group("filled"))
        except Exception:
            pass
    if avg_m:
        try:
            evt.avg_fill_price = float(avg_m.group("avg"))
        except Exception:
            pass
    if order_type_m:
        evt.order_type = order_type_m.group("type")

    state.orders_by_id[order_id] = evt


def _infer_holdings_from_orders(orders_by_id: dict[int, OrderEvent] | None) -> list[dict]:
    if not orders_by_id:
        return []
    net_qty: dict[str, float] = {}
    last_avg: dict[str, float] = {}
    last_ts: dict[str, str] = {}

    for o in orders_by_id.values():
        status_u = (o.status or "").upper()
        if "FILLED" not in status_u:
            continue
        filled = float(o.filled or 0.0)
        if filled <= 0:
            continue
        sym = str(o.symbol or "").upper()
        if not sym:
            continue
        action = (o.action or "").upper()
        if action == "BUY":
            net_qty[sym] = net_qty.get(sym, 0.0) + filled
        elif action == "SELL":
            net_qty[sym] = net_qty.get(sym, 0.0) - filled
        else:
            continue
        ts = o.ts or ""
        if o.avg_fill_price is not None:
            prev_ts = last_ts.get(sym, "")
            if ts >= prev_ts:
                last_ts[sym] = ts
                last_avg[sym] = float(o.avg_fill_price)

    out: list[dict] = []
    for sym, qty in sorted(net_qty.items()):
        if abs(qty) < 1e-8:
            continue
        out.append(
            {
                "symbol": sym,
                "side": "long" if qty > 0 else "short",
                "size": abs(qty),
                "avg_price": last_avg.get(sym),
                "stop_loss": None,
                "take_profit": None,
                "open_bracket_risk": None,
                "working_orders": None,
                "synthetic_stop_armed": None,
                "hold_age_seconds": None,
                "hold_remaining_seconds": None,
                "working_order_statuses": [],
            }
        )
    return out


def _iter_rotated_log_paths(log_path: Path, *, max_files: int = 25) -> list[Path]:
    base = log_path.name
    parent = log_path.parent
    if not parent.exists():
        return [log_path]
    rx = re.compile(rf"^{re.escape(base)}(?:\.(?P<n>\d+))?$")
    candidates: list[tuple[int, Path]] = []
    for p in parent.glob(base + "*"):
        m = rx.match(p.name)
        if not m:
            continue
        n_s = m.group("n")
        n = int(n_s) if n_s is not None else 0
        candidates.append((n, p))
    candidates.sort(key=lambda t: t[0])
    if max_files and len(candidates) > max_files:
        candidates = candidates[:max_files]
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in candidates]


def main() -> int:
    parser = argparse.ArgumentParser(description="Holdings view (tails tradebot log for [HOLDINGS] snapshots).")
    parser.add_argument("--log", default=os.getenv("TRADEBOT_LOG", "logs/tradebot.log"))
    parser.add_argument("--follow", action="store_true", help="Follow the log (tail -F style).")
    parser.add_argument("--interval", type=float, default=3.0, help="Refresh interval (seconds).")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color rendering.")
    parser.add_argument(
        "--history-files",
        type=int,
        default=int(os.getenv("HOLDINGS_HISTORY_FILES", "25")),
        help="How many rotated log files to scan at startup for context.",
    )
    args = parser.parse_args()

    color_on = _supports_color() and not args.no_color
    path = Path(args.log)
    state = HoldingsState()
    screen = _SmoothScreen()
    last_inode: int | None = None
    last_size = 0

    try:
        # Startup: scan rotated logs for context so holdings/orders aren't blank after rotation.
        try:
            for p in _iter_rotated_log_paths(path, max_files=max(1, int(args.history_files))):
                if not p.exists():
                    continue
                with p.open("r", encoding="utf-8", errors="replace") as f:
                    for raw in f:
                        _ingest_line(state, raw.rstrip("\n"))
        except Exception:
            pass

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
                            _ingest_line(state, line)
                frame = _render(state, color_on=color_on)
                screen.draw(frame)
                if not args.follow:
                    return 0
                time.sleep(args.interval)
            except KeyboardInterrupt:
                return 0
    finally:
        screen.close()


if __name__ == "__main__":
    raise SystemExit(main())
