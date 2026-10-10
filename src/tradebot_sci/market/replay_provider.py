"""ReplayMarketProvider — feeds historical candles during weekend Sabbath mode.

On construction, selects a random trading day from the available forex_backtest
data files and progressively reveals candles one at a time.  Each call to
``advance()`` (driven by the decision loop) reveals the next 5-minute bar,
simulating forward price movement at a pace the strategy can react to.
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from tradebot_sci.market.models import Candle, MarketSnapshot, Ticker, TrendState

logger = logging.getLogger(__name__)


class ReplayMarketProvider:
    """Market data provider that replays historical candles from JSON files.

    The replay advances **one 5-minute candle per ``advance()`` call** rather
    than mapping wall-clock time to simulated time.  This ensures the strategy
    engine sees a single new bar per decision cycle — matching how the live bot
    processes data — and prevents the "9-position avalanche" that occurs when
    many candles become visible at once.

    Compatible with OandaMarketDataProvider / CCXTMarketDataProvider interface.
    """

    def __init__(
        self,
        data_dir: str | Path,
        symbols: List[str],
        replay_date: datetime | None = None,
        time_offset: timedelta | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.symbols = [s.upper() for s in symbols]

        # Per-symbol candle stores: symbol -> {tf -> [Candle, ...]}
        self._candles: Dict[str, Dict[str, List[Candle]]] = {}
        # The replay date (the trading day being replayed)
        self.replay_date: Optional[datetime] = None
        self.original_replay_date: Optional[datetime] = None  # pre-shift date for chaining

        # Candle-index progression: how many replay-day candles have been revealed
        self._cursor: int = 0
        # Total number of 5m candles on the replay day (for progress %)
        self._total_day_candles: int = 0
        # Warmup candle count of the symbol that defines the cursor and the
        # simulated clock (candles before the replay day)
        self._warmup_count: int = 0
        # Warmup candle count per symbol.  Stores differ in length, so the
        # boundary where the replay day starts is a property of each symbol's
        # own file and cannot be shared.
        self._warmup_by_sym: Dict[str, int] = {}
        # The symbol the cursor and the simulated clock are read from
        self._ref_sym: Optional[str] = None

        # Replay warmup: skip first N candles of the day before allowing entries.
        # This gives indicators time to stabilise on the new day's context.
        self.REPLAY_WARMUP_CANDLES = 24  # 24 × 5m = 2 hours
        # Throughput counters for the replayed day.  How much forward-test
        # evidence a replay day is worth depends on how many times the strategy
        # actually saw a candle, and how many of those looks fell inside its own
        # entry hour.  The decision log cannot answer that: HOLD lines are
        # throttled to one per symbol per minute, so counting them measures the
        # throttle, not the evaluations.
        self.cursor_moves: int = 0
        self.decision_cycles: int = 0
        self.symbol_evaluations: int = 0
        self.in_window_evaluations: int = 0
        self.undeclared_evaluations: int = 0
        # Entry throttle: only one entry per advance() cycle
        self._entries_this_cycle: int = 0
        self._max_entries_per_cycle: int = 1

        self._load_data(replay_date, time_offset)

    # ── Data Loading ──────────────────────────────────────────────────

    def _load_data(self, requested_date: datetime | None = None, time_offset: timedelta | None = None) -> None:
        """Load candle data from JSON files and select a replay day."""
        available: Dict[str, Path] = {}
        for sym in self.symbols:
            path = self.data_dir / f"{sym}_5m.json"
            if path.exists():
                available[sym] = path

        if not available:
            logger.error("[REPLAY] No data files found in %s for symbols %s",
                         self.data_dir, self.symbols)
            return

        # Discover valid trading days by intersecting across ALL symbols.
        # Previously used only a reference symbol, but if some symbols have
        # extra data from live trading, the replay could pick a day where
        # most symbols have 0 candles (only 2/6 symbols showing in panel).
        # Cache loaded candles to avoid parsing 30k JSON strings repeatedly
        loaded_5m: Dict[str, List[Candle]] = {}
        loaded_5m_by_day: Dict[str, Dict[str, List[Candle]]] = {}
        per_symbol_days: Dict[str, set] = {}
        for sym, path in available.items():
            sym_candles = self._load_json_candles(path)
            loaded_5m[sym] = sym_candles
            day_set = set()
            by_day = {}
            for c in sym_candles:
                # Mon-Thu only (weekday 0-3). Fridays excluded because
                # the Conductor's Friday 5PM close fires immediately.
                if c.timestamp.weekday() < 4:
                    day_key = c.timestamp.strftime("%Y-%m-%d")
                    day_set.add(day_key)
                # Keep track of by-day lists for fast lookup
                by_day.setdefault(c.timestamp.strftime("%Y-%m-%d"), []).append(c)
            per_symbol_days[sym] = day_set
            loaded_5m_by_day[sym] = by_day

        # Use a majority threshold instead of strict ALL-symbol intersection.
        # One symbol with limited data (e.g., WTICOUSD with 5 days) should not
        # restrict the entire pool to those 5 days when 11 other symbols have 80+.
        # Require ≥ 80% of symbols to have data on a given day.
        all_days_union: set = set()
        for day_set in per_symbol_days.values():
            all_days_union.update(day_set)

        threshold = max(1, int(len(per_symbol_days) * 0.8))
        common_days = set()
        for day in all_days_union:
            coverage = sum(1 for ds in per_symbol_days.values() if day in ds)
            if coverage >= threshold:
                common_days.add(day)

        if not common_days:
            # Fallback to strict intersection
            common_days = set.intersection(*per_symbol_days.values()) if per_symbol_days else set()

        logger.info("[REPLAY] Day pool: %d days (threshold %d/%d symbols)",
                   len(common_days), threshold, len(per_symbol_days))

        # Filter: need at least 100 candles on the day for reference symbol
        ref_sym = next(iter(available))
        ref_candles = loaded_5m[ref_sym]
        if not ref_candles:
            logger.error("[REPLAY] Reference symbol %s has no candles", ref_sym)
            return

        day_groups: Dict[str, List[Candle]] = {}
        ref_by_day = loaded_5m_by_day[ref_sym]
        for d in common_days:
            if d in ref_by_day:
                day_groups[d] = ref_by_day[d]

        valid_days = [d for d, clist in day_groups.items() if len(clist) >= 100]
        if not valid_days:
            # Fallback: if intersection is empty, use reference symbol only
            logger.warning("[REPLAY] No days with data for ALL %d symbols. "
                          "Falling back to reference symbol %s days.",
                          len(available), ref_sym)
            day_groups = {}
            for day_key, clist in ref_by_day.items():
                if clist and clist[0].timestamp.weekday() < 4:
                    day_groups[day_key] = clist
            valid_days = [d for d, clist in day_groups.items() if len(clist) >= 100]

        if not valid_days:
            logger.error("[REPLAY] No valid trading days found in data")
            return

        # Pick a date
        if requested_date:
            target = requested_date.strftime("%Y-%m-%d")
            chosen_day = target if target in valid_days else random.choice(valid_days)
        else:
            # Pick the best TRENDING day across ALL symbols.
            # Old approach (single-symbol range) often picked days with spikes
            # but no directional trend — leading to choppy trades and losses.
            # New approach: score each day by avg directional move × trend quality
            # across all loaded symbols.
            best_day, best_score = valid_days[0], -1.0
            for d in valid_days:
                day_trend_score = 0.0
                sym_scored = 0
                for sym in available.keys():
                    day_c = loaded_5m_by_day[sym].get(d, [])
                    if len(day_c) < 20:
                        continue
                    h = max(float(c.high) for c in day_c)
                    l = min(float(c.low) for c in day_c)
                    o = float(day_c[0].open)
                    cl = float(day_c[-1].close)
                    mid = (h + l) / 2
                    if mid == 0:
                        continue
                    dir_pct = abs(cl - o) / mid
                    range_pct = (h - l) / mid
                    quality = dir_pct / range_pct if range_pct > 0 else 0
                    day_trend_score += dir_pct * quality
                    sym_scored += 1
                if sym_scored > 0:
                    avg_score = day_trend_score / sym_scored
                    if avg_score > best_score:
                        best_score = avg_score
                        best_day = d
            chosen_day = best_day
            logger.info("[REPLAY] Day selection: %s scored %.4f "
                       "(cross-symbol trending quality)", chosen_day, best_score)

        self.replay_date = datetime.strptime(chosen_day, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        logger.info("=" * 60)
        logger.info("[REPLAY] 🎬 WEEKEND REPLAY MODE ACTIVATED")
        logger.info("[REPLAY] Replaying: %s (%s)", chosen_day,
                    self.replay_date.strftime("%A"))
        logger.info("=" * 60)

        # Load candles for ALL symbols and ALL available timeframes
        day_end = self.replay_date + timedelta(days=1)

        for sym in self.symbols:
            self._candles[sym] = {}
            for tf in ["1m", "5m", "15m", "1h", "4h"]:
                path = self.data_dir / f"{sym}_{tf}.json"
                if not path.exists():
                    continue
                if tf == "5m" and sym in loaded_5m:
                    all_candles = loaded_5m[sym]
                else:
                    all_candles = self._load_json_candles(path)
                # Keep everything up to and including the replay day
                self._candles[sym][tf] = [
                    c for c in all_candles if c.timestamp < day_end
                ]
                day_count = sum(
                    1 for c in self._candles[sym][tf]
                    if c.timestamp.date() == self.replay_date.date()
                )
                # Per-symbol diagnostic detail (26 symbols x 2 timeframes per load).
                logger.debug(
                    "[REPLAY] Loaded %s %s: %d total (%d on replay day)",
                    sym, tf, len(self._candles[sym][tf]), day_count,
                )

        # Determine warmup boundary = number of 5m candles BEFORE the replay day.
        # Per symbol, because the candle stores are not the same length: the
        # files here run from 7,203 candles (EURUSD, from 2026-01-30) down to
        # 3,999 (the other 24, from 2026-02-16).  A single reference count used
        # for every symbol slices past the end of the shorter stores, which
        # hands that symbol the whole replay day at cursor 0 and freezes it at
        # the 23:55 candle for the rest of the day.
        ref_all = self._candles.get(ref_sym, {}).get("5m", [])
        self._warmup_count = sum(
            1 for c in ref_all
            if c.timestamp.date() < self.replay_date.date()
        )
        self._total_day_candles = sum(
            1 for c in ref_all
            if c.timestamp.date() == self.replay_date.date()
        )
        self._ref_sym = ref_sym
        self._warmup_by_sym = {}
        for sym in self.symbols:
            sym_all = self._candles.get(sym, {}).get("5m", [])
            self._warmup_by_sym[sym] = sum(
                1 for c in sym_all
                if c.timestamp.date() < self.replay_date.date()
            )

        # Start with cursor = 0 (only warmup candles visible)
        self._cursor = 0

        logger.info(
            "[REPLAY] Warmup candles: %d (reference %s) | Replay day candles: %d "
            "| Cursor starts at 0",
            self._warmup_count, ref_sym, self._total_day_candles,
        )

        # ── Shift candle timestamps to today ────────────────────────────
        # Replay candles have historical dates (e.g., 2026-02-18) which look
        # confusing in the UI chart and make trades appear "weeks old".
        # Shift all timestamps forward so the replay day maps to today,
        # preserving the time-of-day.
        if time_offset is not None:
            self._time_offset = time_offset
            now = datetime.now(timezone.utc)
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            now = datetime.now(timezone.utc)
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._time_offset = today - self.replay_date
        
        self.original_replay_date = self.replay_date  # preserve for day chaining
        logger.info("[REPLAY] Time shift: replay %s -> today %s (offset %s)",
                   self.replay_date.strftime("%Y-%m-%d"),
                   today.strftime("%Y-%m-%d"),
                   self._time_offset)

        for sym in list(self._candles.keys()):
            for tf in list(self._candles[sym].keys()):
                for c in self._candles[sym][tf]:
                    c.timestamp = c.timestamp + self._time_offset
        self.replay_date = self.replay_date + self._time_offset

    def _load_json_candles(self, path: Path) -> List[Candle]:
        """Load candles from a JSON file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            candles = []
            for item in data:
                ts = datetime.fromisoformat(item["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                candles.append(Candle(
                    timestamp=ts,
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume", 0)),
                ))
            return candles
        except Exception as e:
            logger.error("[REPLAY] Failed to load %s: %s", path, e)
            return []

    # ── Candle Progression ────────────────────────────────────────────

    def advance(self) -> None:
        """Reveal the next 5-minute candle.  Called once per decision cycle."""
        if self._cursor < self._total_day_candles:
            self._cursor += 1
            self.cursor_moves += 1
            self._entries_this_cycle = 0  # Reset entry throttle
            _pct = int(self._cursor / self._total_day_candles * 100) if self._total_day_candles else 0
            if _pct >= getattr(self, "_last_progress_pct", -1) + 10 or self._cursor == 1:
                self._last_progress_pct = _pct
                logger.info(
                    "[REPLAY] Advanced to candle %d / %d (%.0f%%)%s",
                    self._cursor, self._total_day_candles,
                    self._cursor / self._total_day_candles * 100
                    if self._total_day_candles else 0,
                    " [WARMUP - no entries]" if self._cursor <= self.REPLAY_WARMUP_CANDLES else "",
                )

    @property
    def in_warmup(self) -> bool:
        """True if the replay is still in the warmup phase (no entries allowed)."""
        return self._cursor <= self.REPLAY_WARMUP_CANDLES

    @property
    def data_revision(self) -> int:
        """Which bar the provider is currently revealing.

        Read by the runtime's snapshot cache: a snapshot taken at one cursor is
        wrong at the next one, and the cache's wall-clock expiry is far too slow
        to notice in a replay that covers a day in ten seconds.
        """
        return self._cursor

    def note_cycle(self, evaluations: int, in_window: int, undeclared: int = 0) -> None:
        """Record one completed decision cycle.

        ``evaluations`` is the number of symbols the strategy looked at on this
        candle and ``in_window`` how many of those the strategy itself judged to
        be inside its entry hour.  Called by the runtime loop after the cycle
        has run, so the count is of decisions actually taken and not of candles
        the cursor happened to pass.

        ``undeclared`` counts symbols whose strategy reported no entry window at
        all.  It is kept separate so a zero of ``in_window`` can be told apart
        from "the value never arrived", which is the failure that would make
        this counter quietly useless.
        """
        self.decision_cycles += 1
        self.symbol_evaluations += evaluations
        self.in_window_evaluations += in_window
        self.undeclared_evaluations += undeclared

    def throughput(self) -> dict:
        """Counters for the day that has just finished, and the per-day ratios."""
        return {
            "candles": self._total_day_candles,
            "cursor_moves": self.cursor_moves,
            "cycles": self.decision_cycles,
            "symbol_evaluations": self.symbol_evaluations,
            "in_window_evaluations": self.in_window_evaluations,
            "undeclared_evaluations": self.undeclared_evaluations,
        }

    def can_enter(self) -> bool:
        """Check if an entry is allowed this cycle (throttle + warmup)."""
        if self.in_warmup:
            return False
        if self._entries_this_cycle >= self._max_entries_per_cycle:
            return False
        return True

    def record_entry(self) -> None:
        """Record that an entry was taken this cycle."""
        self._entries_this_cycle += 1

    @property
    def sim_time(self) -> Optional[datetime]:
        """The simulated timestamp of the current cursor position.

        Used by the paper broker to set `opened_at` on positions so that
        safety guard time checks (bars_since, Churn Guard, Day Enforcer)
        operate in simulated time rather than wall-clock time.
        """
        return self._get_sim_time()

    def _visible_count(self, tf: str) -> int:
        """Number of candles to reveal for a given timeframe.

        For 5m this is warmup + cursor.  For coarser timeframes, calculate
        proportionally (e.g. 1h = cursor // 12).
        """
        if tf == "5m":
            return self._warmup_count + self._cursor

        # Map higher TFs: how many coarser candles correspond to cursor bars?
        ratio_map = {"15m": 3, "1h": 12, "4h": 48}
        ratio = ratio_map.get(tf, 1)
        # Always reveal at least 1 on the replay day, then scale up
        day_bars = max(1, self._cursor // ratio) if self._cursor > 0 else 0

        # We need to count the warmup candles for this TF
        # (all candles before the replay day in the stored data)
        return day_bars  # actual slicing uses _get_visible_candles

    def _get_visible_candles(
        self, symbol: str, tf: str
    ) -> List[Candle]:
        """Return the candles visible at the current cursor position."""
        sym = symbol.upper()
        sym_data = self._candles.get(sym, {})
        candles = sym_data.get(tf)
        fell_back_to_5m = False
        if not candles:
            candles = sym_data.get("5m", [])
            fell_back_to_5m = True
            if not candles:
                return []

        if tf == "5m" or fell_back_to_5m:
            # If the requested TF fell back to 5m data (e.g. 1m requested but
            # only 5m exists), use cursor-based slicing.  This ensures the
            # stop evaluator sees the same candle revelation rate as native 5m,
            # preventing 5m H/L ranges from causing premature stop hits.
            # The warmup boundary is this symbol's own, so every symbol reveals
            # exactly one replay-day candle per advance() regardless of how much
            # history its file happens to hold.
            warmup = self._warmup_by_sym.get(sym, self._warmup_count)
            end_idx = warmup + self._cursor
            return candles[:end_idx]

        # For higher TFs: determine the sim timestamp of the current cursor
        # and filter by that timestamp
        sim_time = self._get_sim_time()
        if sim_time is None:
            # Cursor is 0, show only warmup (pre-day) candles
            return [
                c for c in candles
                if c.timestamp.date() < self.replay_date.date()
            ]
        return [c for c in candles if c.timestamp <= sim_time]

    def _get_sim_time(self) -> Optional[datetime]:
        """The simulated timestamp of the current cursor position."""
        if self._cursor <= 0:
            return None
        ref_sym = self._ref_sym or next(iter(self._candles), None)
        if not ref_sym:
            return None
        five_m = self._candles[ref_sym].get("5m", [])
        idx = self._warmup_count + self._cursor - 1
        if idx < len(five_m):
            return five_m[idx].timestamp
        return None

    # ── Provider Interface ────────────────────────────────────────────

    def get_latest_candles(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> List[Candle]:
        """Return the last ``limit`` candles up to the current cursor."""
        visible = self._get_visible_candles(symbol, timeframe)
        return visible[-limit:] if len(visible) > limit else visible

    def get_ticker(self, symbol: str) -> Ticker | None:
        """Return a ticker from the most recent replayed candle, with NO invented spread.

        Until 2026-10-10 this returned a fixed synthetic quote for every symbol on
        every bar: ``spread = mid * 0.00003``, three basis points of price. The engine
        hands that difference to the strategy as ``gates["current_spread"]``, and the
        strategy reads it as the toll this entry will pay. The replay's own data files
        carry no spread field at all, so the number was never a quote: it worked out at
        0.17 to 0.63 pips where the measured round trip for the same pairs is 1.3 to 9.8
        pips, and it was below the 1.9-pip entry ceiling for every symbol in the profile.
        The ceiling shipped on 2026-10-10 (decision 28) was therefore inert in the only
        place the bot actually runs, and the entry-toll readout printed the fabricated
        number as though it were the cost.

        With bid equal to ask the spread reads as zero, and the strategy takes a
        non-positive reading as "no live quote", which is the truth here. It then falls
        back to the per-pair measured table, the same number the research charged, and a
        pair that is in neither is refused as unpriced instead of admitted as cheap.
        ``last`` is unchanged, so prices and fills are unaffected: the paper broker and
        the strategy both read ``last`` for price, not the quote.
        """
        candles = self.get_latest_candles(symbol, "5m", limit=1)
        if not candles:
            return None

        mid = candles[-1].close
        return Ticker(
            symbol=symbol,
            bid=mid,
            ask=mid,
            last=mid,
            volume_24h_quote_usd=None,
        )

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        """Build a snapshot from replayed candles with proper HTF/LTF/MTF data."""
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        _neutral = TrendState(direction="neutral", strength=0.0)

        # Try native HTF/LTF/MTF data first, else resample from 5m (mirrors backtester)
        htf_candles = self._get_visible_candles(symbol, "4h")
        if not htf_candles:
            # Resample 5m -> 4h (48 bars per 4h candle)
            htf_candles = self._resample(candles, 48)

        mtf_candles = self._get_visible_candles(symbol, "1h")
        if not mtf_candles:
            # Resample 5m -> 1h (12 bars per 1h candle)
            mtf_candles = self._resample(candles, 12)

        ltf_candles = self._get_visible_candles(symbol, "15m")
        if not ltf_candles:
            # Resample 5m -> 15m (3 bars per 15m candle)
            ltf_candles = self._resample(candles, 3)

        micro_candles = self._get_visible_candles(symbol, "1m")
        if not micro_candles:
            micro_candles = []

        INDICATOR_MIN = 60
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles[-INDICATOR_MIN:] if len(htf_candles) >= INDICATOR_MIN else htf_candles,
            mtf_candles=mtf_candles[-INDICATOR_MIN:] if len(mtf_candles) >= INDICATOR_MIN else mtf_candles,
            ltf_candles=ltf_candles[-INDICATOR_MIN:] if len(ltf_candles) >= INDICATOR_MIN else ltf_candles,
            micro_candles=micro_candles[-10:] if len(micro_candles) >= 10 else micro_candles,
            htf_timeframe="4h",
            mtf_timeframe="1h",
            ltf_timeframe="15m",
            micro_timeframe="1m",
        )

    @staticmethod
    def _resample(candles: list, factor: int) -> list:
        """Resample candles by grouping <factor> bars into one higher-TF bar."""
        if not candles or factor < 2:
            return candles
        result = []
        for i in range(0, len(candles), factor):
            chunk = candles[i:i + factor]
            if not chunk:
                break
            result.append(Candle(
                timestamp=chunk[0].timestamp,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(getattr(c, 'volume', 0) for c in chunk),
            ))
        return result

    def get_order_book(self, symbol: str, depth: int = 10):
        """Replay mode doesn't simulate order books."""
        return None

    def close(self) -> None:
        """Nothing to clean up."""
        pass

    # ── Status / UI ───────────────────────────────────────────────────

    @property
    def is_replay_complete(self) -> bool:
        """True if all replay-day candles have been revealed."""
        return self._cursor >= self._total_day_candles

    def get_replay_info(self) -> dict:
        """Return current replay status for the UI."""
        progress = (
            self._cursor / self._total_day_candles
            if self._total_day_candles > 0 else 0.0
        )
        sim_time = self._get_sim_time()

        return {
            "replay_active": True,
            "replay_date": self.replay_date.strftime("%Y-%m-%d") if self.replay_date else None,
            "replay_day": self.replay_date.strftime("%A") if self.replay_date else None,
            "replay_source_date": self.original_replay_date.strftime("%Y-%m-%d") if self.original_replay_date else None,
            "replay_candle": f"{self._cursor}/{self._total_day_candles}",
            "replay_progress": f"{progress * 100:.0f}%",
            "replay_sim_time": sim_time.strftime("%H:%M") if sim_time else "warmup",
            "replay_complete": self.is_replay_complete,
        }
