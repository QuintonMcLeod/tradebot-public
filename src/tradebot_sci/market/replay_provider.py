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
        # Warmup candle count (candles before the replay day)
        self._warmup_count: int = 0

        # Replay warmup: skip first N candles of the day before allowing entries.
        # This gives indicators time to stabilise on the new day's context.
        self.REPLAY_WARMUP_CANDLES = 24  # 24 × 5m = 2 hours
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
        per_symbol_days: Dict[str, set] = {}
        for sym, path in available.items():
            sym_candles = self._load_json_candles(path)
            day_set = set()
            for c in sym_candles:
                # Mon-Thu only (weekday 0-3). Fridays excluded because
                # the Conductor's Friday 5PM close fires immediately.
                if c.timestamp.weekday() < 4:
                    day_key = c.timestamp.strftime("%Y-%m-%d")
                    day_set.add(day_key)
            per_symbol_days[sym] = day_set

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
        ref_candles = self._load_json_candles(available[ref_sym])
        if not ref_candles:
            logger.error("[REPLAY] Reference symbol %s has no candles", ref_sym)
            return

        day_groups: Dict[str, List[Candle]] = {}
        for c in ref_candles:
            day_key = c.timestamp.strftime("%Y-%m-%d")
            if day_key in common_days:
                day_groups.setdefault(day_key, []).append(c)

        valid_days = [d for d, clist in day_groups.items() if len(clist) >= 100]
        if not valid_days:
            # Fallback: if intersection is empty, use reference symbol only
            logger.warning("[REPLAY] No days with data for ALL %d symbols. "
                          "Falling back to reference symbol %s days.",
                          len(available), ref_sym)
            day_groups = {}
            for c in ref_candles:
                day_key = c.timestamp.strftime("%Y-%m-%d")
                if c.timestamp.weekday() < 4:
                    day_groups.setdefault(day_key, []).append(c)
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
                for sym, path in available.items():
                    sym_candles = self._load_json_candles(path)
                    day_c = [c for c in sym_candles
                             if c.timestamp.strftime("%Y-%m-%d") == d]
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
            for tf in ["5m", "15m", "1h", "4h"]:
                path = self.data_dir / f"{sym}_{tf}.json"
                if not path.exists():
                    continue
                all_candles = self._load_json_candles(path)
                # Keep everything up to and including the replay day
                self._candles[sym][tf] = [
                    c for c in all_candles if c.timestamp < day_end
                ]
                day_count = sum(
                    1 for c in self._candles[sym][tf]
                    if c.timestamp.date() == self.replay_date.date()
                )
                logger.info(
                    "[REPLAY] Loaded %s %s: %d total (%d on replay day)",
                    sym, tf, len(self._candles[sym][tf]), day_count,
                )

        # Determine warmup boundary = number of 5m candles BEFORE the replay day
        ref_all = self._candles.get(ref_sym, {}).get("5m", [])
        self._warmup_count = sum(
            1 for c in ref_all
            if c.timestamp.date() < self.replay_date.date()
        )
        self._total_day_candles = sum(
            1 for c in ref_all
            if c.timestamp.date() == self.replay_date.date()
        )

        # Start with cursor = 0 (only warmup candles visible)
        self._cursor = 0

        logger.info(
            "[REPLAY] Warmup candles: %d | Replay day candles: %d | Cursor starts at 0",
            self._warmup_count, self._total_day_candles,
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
        logger.info("[REPLAY] Time shift: %s (offset %s)",
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
            self._entries_this_cycle = 0  # Reset entry throttle
            if self._cursor % 12 == 0 or self._cursor == 1:
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
            end_idx = self._warmup_count + self._cursor
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
        ref_sym = next(iter(self._candles), None)
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
        """Return a ticker from the most recent replayed candle."""
        candles = self.get_latest_candles(symbol, "5m", limit=1)
        if not candles:
            return None

        c = candles[-1]
        mid = c.close
        spread = mid * 0.00003  # ~0.5 pip spread for majors
        return Ticker(
            symbol=symbol,
            bid=mid - spread / 2,
            ask=mid + spread / 2,
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
            htf_timeframe="4h",
            mtf_timeframe="1h",
            ltf_timeframe="15m",
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
