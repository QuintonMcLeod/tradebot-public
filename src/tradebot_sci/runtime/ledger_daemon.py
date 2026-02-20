"""
PnL Ledger Daemon — Background log scraper with sundown-based daily resets.

Runs as a background thread, tail-reading tradebot.log every 60 seconds.
Accumulates realized PnL, trade stats, and capital snapshots into a
persistent data/ledger.json. Resets daily at local sundown (via astral).

The UI reads this JSON instead of re-parsing the entire log on every refresh.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ── Astral import (optional) ──────────────────────────────────────────────
try:
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_AVAILABLE = True
except ImportError:
    LocationInfo = None  # type: ignore
    sun = None  # type: ignore
    ASTRAL_AVAILABLE = False

# ── Regex patterns for log scraping ───────────────────────────────────────
# [EXIT] Manual/Signal: USDCAD +$0.01 (Pct=0.01%) | Est. Spread Cost: $0.0180 (OANDA 1.5 pips)
RE_EXIT = re.compile(
    r"\[EXIT\]\s+(?P<reason>[^:]+):\s+"
    r"(?P<symbol>[A-Z_]{3,10})\s+"
    r"(?:(?P<pnl_sign>[+-])\$|(?:\$(?P<pnl_sign2>-)))(?P<pnl_val>[\d.]+)"
    r"(?:\s+\(Pct=(?P<pct>[+-]?[\d.]+)%\))?"
    r"(?:.*?Duration=(?P<duration>[^|]+))?"
    r"(?:.*?Est\.\s*Spread\s*Cost:\s*\$(?P<spread>[\d.]+))?"
)

# [OANDA] Account Summary: Balance=26.6995, NAV=26.0552
RE_ACCOUNT = re.compile(
    r"Account Summary.*?Balance=(?P<balance>[\d.]+).*?NAV=(?P<nav>[\d.]+)"
)

# Extract broker tag from log lines like [OANDA], [CCXT], [PAXOS]
RE_BROKER_TAG = re.compile(r"\[(?P<broker>OANDA|CCXT|PAXOS|KRAKEN|GEMINI|IBKR)\]")

# [HOLDINGS] {"count": 4, "positions": [...], "total_unrealized_pnl": -0.64}
RE_HOLDINGS = re.compile(
    r"\[HOLDINGS\]\s*(?P<json>\{.+\})"
)

# [HEARTBEAT] Capital available: $26.06
RE_HEARTBEAT = re.compile(
    r"\[HEARTBEAT\]\s*Capital available:\s*\$?(?P<capital>[\d.]+)"
)

# [META-SCI] Tournament Won by BEARISH_ENGULFING (Score: 42)
RE_TOURNAMENT = re.compile(
    r"Tournament Won by\s+(?P<strategy>\w+)"
)

# [PHOENIX] === ENGINE LOADED === Symbol: EURUSD | Variant: META_SCI
RE_PHOENIX = re.compile(
    r"\[PHOENIX\].*Symbol:\s*(?P<symbol>[A-Z_]{3,10}).*Variant:\s*(?P<variant>\w+)"
)

# position=SHORT or position=LONG embedded in EXIT lines
RE_SIDE = re.compile(r"position=(?P<side>SHORT|LONG)", re.IGNORECASE)

# Log timestamp: 2026-02-12 15:48:40
RE_TIMESTAMP = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")


def _parse_log_ts(line: str) -> Optional[datetime]:
    """Parse the timestamp from a log line (local time, no TZ in the log)."""
    m = RE_TIMESTAMP.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _compute_sundown(date_obj, lat: float, lon: float, tz_name: str) -> datetime:
    """Compute sunset time for a given date and location using astral."""
    tz = ZoneInfo(tz_name)
    if ASTRAL_AVAILABLE and LocationInfo is not None and sun is not None:
        try:
            loc = LocationInfo(
                name="ledger", region="", timezone=tz_name,
                latitude=lat, longitude=lon,
            )
            s = sun(loc.observer, date=date_obj, tzinfo=tz)
            return s["sunset"]
        except Exception as e:
            logger.debug(f"[LEDGER] Astral sundown calc failed: {e}; using 18:00 fallback")

    # Fallback: 6 PM local
    return datetime(date_obj.year, date_obj.month, date_obj.day, 18, 0, 0, tzinfo=tz)


def _empty_day(day_start_iso: str) -> dict:
    """Create an empty day record."""
    return {
        "day_start": day_start_iso,
        "pnl_realized": 0.0,
        "pnl_unrealized": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "capital_at_start": 0.0,
        "capital_now": 0.0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "by_symbol": {},
        "by_strategy": {},
        "spread_costs": 0.0,
        "trade_log": [],
        "capital_snapshots": [],
        "capital_snapshots_by_broker": {},
        "capital_by_broker": {},
    }


class LedgerDaemon:
    """Background thread that tail-reads tradebot.log and maintains ledger.json."""

    def __init__(
        self,
        log_path: str = "logs/tradebot.log",
        ledger_path: str = "data/ledger.json",
        interval: int = 60,
        lat: float = 33.764,
        lon: float = -84.386,
        tz_name: str = "America/New_York",
        default_strategy: str = "",
    ) -> None:
        self.log_path = Path(log_path)
        self.ledger_path = Path(ledger_path)
        self.interval = interval
        self.lat = lat
        self.lon = lon
        self.tz_name = tz_name
        self.tz = ZoneInfo(tz_name)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._file_offset: int = 0
        self._last_inode: int = 0

        # In-memory state
        self._ledger: dict = {
            "version": 1,
            "last_updated": "",
            "sundown_timezone": tz_name,
            "current_day": _empty_day(""),
            "days": [],
        }

        # Track the next sundown boundary
        self._next_sundown: Optional[datetime] = None
        self._last_strategy: str = ""  # last META tournament winner seen
        self._symbol_strategy: dict = {}  # per-symbol strategy from PHOENIX
        self._default_strategy: str = default_strategy  # fallback from profile
        self._paper_mode: bool = False  # When True, only process [PAPER] lines
        self._snapshot_ts_by_broker: dict = {}  # Per-broker throttle for capital snapshots
        self._exit_dedup: dict = {}  # Dedup cache: key -> timestamp

        # Load existing ledger if present
        self._load_ledger()

    # ── Capital Snapshots ─────────────────────────────────────────────

    def _maybe_snapshot(self, current: dict, nav: float, ts: Optional[datetime],
                        broker: str = "all") -> None:
        """Record a capital snapshot at most every 5 minutes per broker.
        
        broker: 'all' for combined heartbeat, or 'oanda'/'ccxt' etc. for per-broker.
        """
        SNAPSHOT_INTERVAL = 300  # seconds (5 min)
        MAX_SNAPSHOTS = 288     # 24h at 5-min intervals

        now = ts or datetime.now(self.tz)
        # Per-broker throttling so "all" heartbeat doesn't suppress broker-specific snapshots
        last_ts = self._snapshot_ts_by_broker.get(broker)
        if last_ts:
            elapsed = (now - last_ts).total_seconds()
            if elapsed < SNAPSHOT_INTERVAL:
                return

        entry = {"ts": now.isoformat(), "nav": round(nav, 4), "broker": broker}

        # Global snapshots (all sources)
        snaps = current.setdefault("capital_snapshots", [])
        snaps.append(entry)
        if len(snaps) > MAX_SNAPSHOTS:
            current["capital_snapshots"] = snaps[-MAX_SNAPSHOTS:]

        # Per-broker snapshots
        if broker != "all":
            by_broker = current.setdefault("capital_snapshots_by_broker", {})
            broker_snaps = by_broker.setdefault(broker, [])
            broker_snaps.append({"ts": now.isoformat(), "nav": round(nav, 4)})
            if len(broker_snaps) > MAX_SNAPSHOTS:
                by_broker[broker] = broker_snaps[-MAX_SNAPSHOTS:]

        self._snapshot_ts_by_broker[broker] = now

    # ── Persistence ───────────────────────────────────────────────────

    def _load_ledger(self) -> None:
        """Load ledger.json if it exists."""
        if self.ledger_path.exists():
            try:
                with self.ledger_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._ledger = data
                logger.info(f"[LEDGER] Loaded existing ledger: {len(data.get('days', []))} historical days")
            except Exception as e:
                logger.warning(f"[LEDGER] Failed to load ledger: {e}; starting fresh")

    def _save_ledger(self) -> None:
        """Atomic write ledger to disk."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ledger["last_updated"] = datetime.now(self.tz).isoformat()
        tmp = self.ledger_path.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self._ledger, f, indent=2)
            tmp.replace(self.ledger_path)
        except Exception as e:
            logger.error(f"[LEDGER] Failed to save: {e}")

    # ── Sundown Logic ─────────────────────────────────────────────────

    def _compute_next_sundown(self) -> datetime:
        """Compute the next sundown boundary from now."""
        now_local = datetime.now(self.tz)
        today_sundown = _compute_sundown(now_local.date(), self.lat, self.lon, self.tz_name)

        if now_local >= today_sundown:
            # Already past today's sundown — next is tomorrow
            tomorrow = now_local.date() + timedelta(days=1)
            return _compute_sundown(tomorrow, self.lat, self.lon, self.tz_name)
        return today_sundown

    def _check_sundown_rollover(self) -> None:
        """If we've passed sundown, archive the current day and reset."""
        if self._next_sundown is None:
            self._next_sundown = self._compute_next_sundown()
            # Initialize current_day's day_start if empty
            if not self._ledger["current_day"].get("day_start"):
                # Previous sundown was the start of current day
                now_local = datetime.now(self.tz)
                today_sundown = _compute_sundown(now_local.date(), self.lat, self.lon, self.tz_name)
                if now_local >= today_sundown:
                    self._ledger["current_day"]["day_start"] = today_sundown.isoformat()
                else:
                    yesterday = now_local.date() - timedelta(days=1)
                    prev_sundown = _compute_sundown(yesterday, self.lat, self.lon, self.tz_name)
                    self._ledger["current_day"]["day_start"] = prev_sundown.isoformat()
            return

        now_local = datetime.now(self.tz)
        if now_local >= self._next_sundown:
            logger.info(f"[LEDGER] ☀️ Sundown rollover at {self._next_sundown.isoformat()}")
            # Archive current day
            current = self._ledger["current_day"]
            current["day_end"] = self._next_sundown.isoformat()
            current["date"] = self._next_sundown.date().isoformat()

            # Only archive if there were trades or meaningful data
            if current.get("trades", 0) > 0 or current.get("capital_now", 0) > 0:
                # Deep copy to archive (keep trade_log for analytics)
                archived = dict(current)
                archived["trade_count"] = len(current.get("trade_log", []))
                self._ledger["days"].append(archived)

                # Keep last 365 days max
                if len(self._ledger["days"]) > 365:
                    self._ledger["days"] = self._ledger["days"][-365:]

            # Reset current day
            self._ledger["current_day"] = _empty_day(self._next_sundown.isoformat())
            # Carry forward capital
            self._ledger["current_day"]["capital_at_start"] = current.get("capital_now", 0.0)
            self._ledger["current_day"]["capital_now"] = current.get("capital_now", 0.0)

            # Compute next sundown
            self._next_sundown = self._compute_next_sundown()
            self._save_ledger()

    # ── Log Scraping ──────────────────────────────────────────────────

    def _tail_log(self) -> list[str]:
        """Read new lines from the log file since last read."""
        if not self.log_path.exists():
            return []

        try:
            stat = self.log_path.stat()
            current_inode = stat.st_ino

            # Detect log rotation (inode changed or file shrunk)
            if current_inode != self._last_inode or stat.st_size < self._file_offset:
                logger.info("[LEDGER] Log file rotated, resetting offset")
                self._file_offset = 0
                self._last_inode = current_inode

            if stat.st_size <= self._file_offset:
                return []  # No new data

            with self.log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._file_offset)
                new_lines = f.readlines()
                self._file_offset = f.tell()
                self._last_inode = current_inode

            return new_lines
        except Exception as e:
            logger.error(f"[LEDGER] Error tailing log: {e}")
            return []

    def _process_lines(self, lines: list[str]) -> None:
        """Process new log lines and update the current day's ledger."""
        current = self._ledger["current_day"]

        for line in lines:
            line = line.rstrip()
            ts = _parse_log_ts(line)

            # ── Track tournament winner for strategy attribution ──
            m_tour = RE_TOURNAMENT.search(line)
            if m_tour:
                self._last_strategy = m_tour.group("strategy")

            # ── Track per-symbol strategy from PHOENIX engine load ──
            m_phoenix = RE_PHOENIX.search(line)
            if m_phoenix:
                self._symbol_strategy[m_phoenix.group("symbol")] = m_phoenix.group("variant")

            # ── Route lines by mode: live skips [PAPER], paper only reads [PAPER] ──
            is_paper_line = "[PAPER]" in line
            if self._paper_mode and not is_paper_line:
                continue  # Paper ledger ignores non-paper lines
            if not self._paper_mode and is_paper_line:
                continue  # Live ledger ignores paper lines
            # Strip [PAPER] tag so downstream regexes match normally
            if is_paper_line:
                line = line.replace("[PAPER] ", "").replace("[PAPER]", "")

            # ── EXIT lines — closed trades ────────────────────────
            if "[EXIT]" in line:
                m = RE_EXIT.search(line)
                if m:
                    pnl_val = float(m.group("pnl_val"))
                    sign = m.group("pnl_sign") or m.group("pnl_sign2") or "+"
                    if sign == "-":
                        pnl_val = -pnl_val

                    symbol = m.group("symbol")
                    reason = m.group("reason").strip()

                    # ── Deduplication: skip if same symbol+pnl seen within 90s ──
                    dedup_key = f"{symbol}_{round(pnl_val * 100)}"
                    now = ts or datetime.now(self.tz)
                    last_seen = self._exit_dedup.get(dedup_key)
                    if last_seen and (now - last_seen).total_seconds() < 90:
                        logger.debug(f"[LEDGER] Skipping duplicate EXIT: {symbol} {pnl_val:+.4f} ({reason})")
                        continue

                    # ── Inherited position guard: skip if multiple exits for
                    #    the same symbol fire within 5s (inherited flattening) ──
                    sym_dedup_key = f"_multi_{symbol}"
                    sym_last = self._exit_dedup.get(sym_dedup_key)
                    if sym_last and (now - sym_last).total_seconds() < 5:
                        logger.info(f"[LEDGER] Skipping inherited position exit: {symbol} {pnl_val:+.4f} (multiple closes within 5s)")
                        continue
                    self._exit_dedup[sym_dedup_key] = now

                    self._exit_dedup[dedup_key] = now
                    # Prune old entries (> 5 min)
                    self._exit_dedup = {k: v for k, v in self._exit_dedup.items()
                                        if (now - v).total_seconds() < 300}

                    pct = float(m.group("pct")) if m.group("pct") else 0.0
                    spread = float(m.group("spread")) if m.group("spread") else 0.0

                    # Detect side
                    m_side = RE_SIDE.search(line)
                    side = m_side.group("side").lower() if m_side else "unknown"

                    # Update current day
                    current["pnl_realized"] += pnl_val
                    current["trades"] += 1
                    if pnl_val > 0:
                        current["wins"] += 1
                    elif pnl_val < 0:
                        current["losses"] += 1

                    current["spread_costs"] += spread

                    if pnl_val > current["best_trade"]:
                        current["best_trade"] = pnl_val
                    if pnl_val < current["worst_trade"]:
                        current["worst_trade"] = pnl_val

                    # Per-symbol stats
                    if symbol not in current["by_symbol"]:
                        current["by_symbol"][symbol] = {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
                    current["by_symbol"][symbol]["pnl"] += pnl_val
                    current["by_symbol"][symbol]["trades"] += 1
                    if pnl_val > 0:
                        current["by_symbol"][symbol]["wins"] += 1
                    elif pnl_val < 0:
                        current["by_symbol"][symbol]["losses"] += 1

                    # Per-strategy stats — priority: per-symbol PHOENIX > tournament > default > unknown
                    strat = (self._symbol_strategy.get(symbol)
                             or self._last_strategy
                             or self._default_strategy
                             or "unknown")
                    if strat not in current["by_strategy"]:
                        current["by_strategy"][strat] = {"pnl": 0.0, "wins": 0, "losses": 0}
                    current["by_strategy"][strat]["pnl"] += pnl_val
                    if pnl_val > 0:
                        current["by_strategy"][strat]["wins"] += 1
                    elif pnl_val < 0:
                        current["by_strategy"][strat]["losses"] += 1

                    # Trade log entry (keep last 200 trades per day max)
                    trade_entry = {
                        "time": ts.isoformat() if ts else "",
                        "symbol": symbol,
                        "pnl": round(pnl_val, 4),
                        "pct": round(pct, 2),
                        "side": side,
                        "reason": reason,
                        "strategy": strat,
                        "spread": round(spread, 4),
                        "duration": (m.group("duration") or "").strip() if m.group("duration") else None,
                    }
                    current["trade_log"].append(trade_entry)
                    if len(current["trade_log"]) > 200:
                        current["trade_log"] = current["trade_log"][-200:]

                    logger.debug(f"[LEDGER] Recorded trade: {symbol} {pnl_val:+.4f} ({strat})")

            # ── Account Summary — per-broker capital tracking ─────
            if "Account Summary" in line:
                m = RE_ACCOUNT.search(line)
                if m:
                    nav = float(m.group("nav"))
                    balance = float(m.group("balance"))
                    # Detect which broker this came from
                    broker_m = RE_BROKER_TAG.search(line)
                    broker_tag = broker_m.group("broker").lower() if broker_m else "unknown"
                    # Track per-broker capital
                    cap_by_broker = current.setdefault("capital_by_broker", {})
                    cap_by_broker[broker_tag] = round(nav, 4)
                    # Per-broker snapshot
                    self._maybe_snapshot(current, nav, ts, broker=broker_tag)

            # ── HEARTBEAT — combined capital tracking ─────────────
            if "[HEARTBEAT]" in line:
                m = RE_HEARTBEAT.search(line)
                if m:
                    cap = float(m.group("capital"))
                    current["capital_now"] = cap
                    if current["capital_at_start"] == 0:
                        current["capital_at_start"] = cap
                    self._maybe_snapshot(current, cap, ts, broker="all")

            # ── HOLDINGS — unrealized PnL ─────────────────────────
            if "[HOLDINGS]" in line:
                m = RE_HOLDINGS.search(line)
                if m:
                    try:
                        data = json.loads(m.group("json"))
                        current["pnl_unrealized"] = data.get("total_unrealized_pnl", 0.0)
                    except json.JSONDecodeError:
                        pass

        # Round accumulated floats
        current["pnl_realized"] = round(current["pnl_realized"], 4)
        current["spread_costs"] = round(current["spread_costs"], 4)
        current["best_trade"] = round(current["best_trade"], 4)
        current["worst_trade"] = round(current["worst_trade"], 4)

    # ── Thread Control ────────────────────────────────────────────────

    def _run(self) -> None:
        """Main daemon loop."""
        logger.info(f"[LEDGER] Daemon started — scraping every {self.interval}s, sundown via {'astral' if ASTRAL_AVAILABLE else 'fixed 18:00'}")
        logger.info(f"[LEDGER] Location: lat={self.lat}, lon={self.lon}, tz={self.tz_name}")

        # On first run after boot, do an initial catch-up scrape
        # (skip to end of file to avoid re-processing old data)
        if self._file_offset == 0 and self.log_path.exists():
            stat = self.log_path.stat()
            self._file_offset = stat.st_size
            self._last_inode = stat.st_ino
            logger.info(f"[LEDGER] Skipping to end of log ({self._file_offset} bytes) for fresh start")

        while not self._stop_event.is_set():
            try:
                # Check sundown rollover
                self._check_sundown_rollover()

                # Tail and process new lines
                new_lines = self._tail_log()
                if new_lines:
                    self._process_lines(new_lines)
                    self._save_ledger()

            except Exception as e:
                logger.error(f"[LEDGER] Daemon error: {e}", exc_info=True)

            self._stop_event.wait(self.interval)

        logger.info("[LEDGER] Daemon stopped")

    def start(self) -> None:
        """Start the daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("[LEDGER] Daemon already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="LedgerDaemon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the daemon thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_current_day(self) -> dict:
        """Get the current day's data (for WebSocket broadcasting)."""
        return self._ledger.get("current_day", {})

    def get_ledger(self) -> dict:
        """Get the full ledger (for IPC)."""
        return self._ledger
