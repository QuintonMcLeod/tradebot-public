#!/usr/bin/env python3
"""
paper_replay.py — Live Engine Paper Replay

Feeds recorded historical candle data through the EXACT SAME live engine
code path (cycle.py → engine.decide() → PaperBroker) at accelerated speed.

Achieves 1:1 parity with live bot behaviour — no separate backtester path.
If a bug exists in live, it appears here too.

Usage:
    python tools/paper_replay.py [--days N] [--speed N] [--balance N] [--symbols SYM,SYM]
    python tools/paper_replay.py --days 4 --speed 50 --balance 5700
    python tools/paper_replay.py --days 4 --speed 0  # max speed (no sleep)
"""
from __future__ import annotations

import os
os.environ["BAR_CLOSE_GATE_ENABLED"] = "false"

import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ── Path setup ───────────────────────────────────────────────────────────────
_repo = Path(__file__).resolve().parents[1]
_src  = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# ── Imports ───────────────────────────────────────────────────────────────────
from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState
from tradebot_sci.broker.paper_broker import PaperBroker
from tradebot_sci.broker.trade_result_store import TradeResultStore
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.runtime.cycle import process_candidate_cycle
from tradebot_sci.config.loader import get_settings, load_config_json
from tradebot_sci.runtime.sabbath import SabbathContext

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
# Quieten noisy internal loggers
for _noisy in ("tradebot_sci", "httpcore", "httpx"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("paper_replay")

# ── Candle History Location ───────────────────────────────────────────────────
_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tradebot-sci"
_CANDLE_DIR = _CONFIG_DIR / "data" / "candle_history"


# ─────────────────────────────────────────────────────────────────────────────
# Replay Market Provider — serves pre-recorded snapshots to the engine
# ─────────────────────────────────────────────────────────────────────────────

def _dict_to_candle(d: dict) -> Candle:
    ts = datetime.fromisoformat(d["t"].replace("Z", "+00:00"))
    return Candle(
        timestamp=ts,
        open=float(d["o"]),
        high=float(d["h"]),
        low=float(d["l"]),
        close=float(d["c"]),
        volume=float(d.get("v", 0)),
    )


def _resample_ltf_to_htf(ltf_candles: list, period_minutes: int = 60) -> list:
    """Resample LTF (5m) candles into HTF candles by bucketing timestamps.

    The recorded data only stores ~31 HTF candles per symbol (snapshot only).
    This produces 200+ accurate 1h candles from the 967 LTF candles, giving
    ADX/EMA/MACD enough history to compute on the higher timeframe.
    """
    if not ltf_candles:
        return []
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for c in ltf_candles:
        ts = c.timestamp
        floored_min = (ts.hour * 60 + ts.minute) // period_minutes * period_minutes
        bucket_ts = ts.replace(
            hour=floored_min // 60,
            minute=floored_min % 60,
            second=0, microsecond=0,
        )
        buckets[bucket_ts].append(c)
    result = []
    for bucket_ts in sorted(buckets):
        grp = buckets[bucket_ts]
        result.append(Candle(
            timestamp=bucket_ts,
            open=grp[0].open,
            high=max(c.high for c in grp),
            low=min(c.low for c in grp),
            close=grp[-1].close,
            volume=sum(c.volume for c in grp),
        ))
    return result


class ReplayMarketProvider:
    """Serves the current replay snapshot on demand. Stateful — call set_snapshot() each tick.

    Pre-builds a full sorted candle timeline from all recordings per symbol.
    On each set_snapshot() call, looks up the last 200 candles up to the current
    tick's timestamp — exactly what the live bot fetches from Oanda each cycle.
    """

    _WINDOW = 200  # candles to serve per snapshot

    def __init__(self, candle_timeline: dict[str, list[Candle]] | None = None):
        """
        Args:
            candle_timeline: Pre-built dict of symbol -> sorted list of all Candle objects.
                             Call build_candle_timeline() to create this.
        """
        self._snapshot: Optional[MarketSnapshot] = None
        self._ltf_timeline: dict[str, list[Candle]] = candle_timeline or {}
        self._htf_timeline: dict[str, list[Candle]] = {}
        # Per-symbol last price — prevents cross-symbol price contamination in TP/SL evaluation
        self._last_price: dict[str, float] = {}
        # Per-symbol latest snapshot — for get_latest_snapshot(symbol) lookups
        self._sym_snapshot: dict[str, MarketSnapshot] = {}

    def set_htf_timeline(self, htf_timeline: dict[str, list[Candle]]):
        self._htf_timeline = htf_timeline

    def set_snapshot(self, snap: MarketSnapshot):
        """Build a 200-candle window snapshot for this tick using the pre-built timeline."""
        sym = snap.symbol
        raw_ltf = snap.ltf_candles or snap.candles or []

        # Find the current tick's latest candle timestamp
        current_ts = raw_ltf[-1].timestamp if raw_ltf else None

        # Serve the last 200 LTF candles up to (and including) current_ts
        if current_ts and sym in self._ltf_timeline:
            timeline = self._ltf_timeline[sym]
            # Binary search for position of current_ts
            import bisect
            idx = bisect.bisect_right([c.timestamp for c in timeline], current_ts)
            ltf_window = timeline[max(0, idx - self._WINDOW):idx]
        else:
            ltf_window = raw_ltf

        # Serve the last 500 HTF candles up to current_ts
        if current_ts and sym in self._htf_timeline:
            htf_timeline = self._htf_timeline[sym]
            import bisect
            idx = bisect.bisect_right([c.timestamp for c in htf_timeline], current_ts)
            htf_window = htf_timeline[max(0, idx - 500):idx]
        else:
            htf_window = snap.htf_candles or []

        from dataclasses import replace as _dc_replace
        enriched = _dc_replace(
            snap,
            candles=ltf_window,
            ltf_candles=ltf_window,
            htf_candles=htf_window,
        )
        self._snapshot = enriched
        self._sym_snapshot[sym] = enriched
        # Track last close price per symbol for TP/SL evaluation
        if ltf_window:
            self._last_price[sym] = float(ltf_window[-1].close)

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        return self._sym_snapshot.get(symbol) or self._snapshot

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        snap = self._sym_snapshot.get(symbol) or self._snapshot
        return (snap.candles or [])[-limit:] if snap else []

    def get_ticker(self, symbol: str):
        """Return per-symbol price — prevents cross-symbol price contamination."""
        price = self._last_price.get(symbol)
        if price:
            return type("Ticker", (), {"last": price, "bid": price, "ask": price})()
        return None

    # Minimal stubs so the engine doesn't crash on optional calls
    def get_htf_candles(self, symbol, timeframe, limit=200):
        snap = self._sym_snapshot.get(symbol) or self._snapshot
        return (snap.htf_candles or [])[-limit:] if snap else []

    def get_ltf_candles(self, symbol, timeframe, limit=200):
        snap = self._sym_snapshot.get(symbol) or self._snapshot
        return (snap.ltf_candles or [])[-limit:] if snap else []


# ─────────────────────────────────────────────────────────────────────────────
# Replay Paper Broker — extends PaperBroker to use replay candle prices
# ─────────────────────────────────────────────────────────────────────────────

class ReplayPaperBroker(PaperBroker):
    """PaperBroker that gets prices from the replay provider, not live ticker."""

    def __init__(self, profile_settings, provider: ReplayMarketProvider,
                 trade_results=None, initial_balance: float = 5700.0):
        self._provider = provider
        super().__init__(
            profile_settings=profile_settings,
            market_provider=provider,
            trade_results=trade_results,
            initial_balance=initial_balance,
        )
        # Don't restore persisted paper state for replay — fresh run each time
        self.balance = initial_balance
        self.positions = {}
        self._initial_balance = initial_balance  # Fixed sizing reference — never compounded
        self._total_pnl = 0.0  # Cumulative PnL tracker (separate from sizing balance)
        # REPLAY FIX: Use candle-time cooldown instead of wall-clock REENTRY_COOLDOWN.
        # Wall-clock 300s never expires when 90 days runs in 55 seconds. Instead we
        # track the last exit bar timestamp per-symbol and block for REPLAY_COOLDOWN_BARS
        # simulated bars (default 6 bars = 30 min on 5m).
        self.REENTRY_COOLDOWN = 0  # Disable wall-clock cooldown — we use candle time below
        self._REPLAY_COOLDOWN_BARS = 6   # Re-entry blocked for 6 bars (30 min on 5m) after any exit
        self._replay_exit_bar_time: dict[str, datetime] = {}  # symbol -> last exit bar time
        logger.info(f"[REPLAY] PaperBroker initialised — balance=${self.balance:.2f}")

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        """Return fixed initial balance for sizing — prevents compounding snowball."""
        return self._initial_balance

    def _save_state(self) -> None:
        """OVERRIDE: Prevent ReplayPaperBroker from writing to the live paper_state.json.
        This isolates the replay simulator from the live daemon, preventing cross-talk."""
        pass

    def _load_state(self) -> None:
        """OVERRIDE: Prevent ReplayPaperBroker from loading the live paper_state.json.
        Start fresh on every replay run."""
        pass

    def get_total_equity(self) -> float:
        """Return fixed initial balance for sizing — prevents SafetyGuard using inflated equity."""
        return self._initial_balance

    def execute_decision(self, decision, *args, **kwargs):
        """Intercept entries to enforce candle-time re-entry cooldown."""
        action = getattr(decision, 'action', None)
        symbol = getattr(decision, 'symbol', None)

        # Scale-out from Guillotine / struct_inval — PaperBroker has no handler for this
        if action in ('scale_out', 'partial_close', 'de_risk', 'pyramid_scale_out'):
            return self._handle_scale_out_decision(decision)

        if action in ('enter_long', 'enter_short') and symbol in self._replay_exit_bar_time:
            snap = self._provider._snapshot
            if snap and snap.candles:
                current_bar = snap.candles[-1].timestamp
                exit_bar = self._replay_exit_bar_time[symbol]
                # Compute bar-delta: each 5m bar = 300 seconds
                bar_delta = (current_bar - exit_bar).total_seconds() / 300.0
                if bar_delta < self._REPLAY_COOLDOWN_BARS:
                    from tradebot_sci.broker.execution import ExecutionResult, ExecutionStatus, ExecutionOutcome, ExecutionOutcomeType
                    bars_remaining = self._REPLAY_COOLDOWN_BARS - bar_delta
                    logger.debug(f"[REPLAY] [COOLDOWN] {symbol}: blocked re-entry, {bars_remaining:.1f} bars remaining")
                    return (
                        ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, f"Replay: cooldown {bars_remaining:.1f} bars"),
                        ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, "Replay: re-entry cooldown active")
                    )
                else:
                    # Cooldown expired — clear it
                    del self._replay_exit_bar_time[symbol]
        result, outcome = super().execute_decision(decision, *args, **kwargs)

        # HOLD_GUARD FIX: The engine uses (current_bar_time - opened_at) for
        # position age.  PaperBroker stamps opened_at = datetime.now() which is
        # wall-clock Mar 2026 while current_bar_time is historical Feb 2026 —
        # giving a large negative age that satisfies age < 300s, permanently
        # blocking Guillotine and all non-emergency exits.
        # Overwrite opened_at with the current replay bar's simulated timestamp
        # so the engine sees the correct candle-time age.
        if action in ('enter_long', 'enter_short') and symbol in self.positions:
            snap = self._provider._snapshot
            if snap and snap.candles:
                bar_ts = snap.candles[-1].timestamp
                bar_ts_str = bar_ts.isoformat() if hasattr(bar_ts, 'isoformat') else str(bar_ts)
                self.positions[symbol]["opened_at"] = bar_ts_str
                self.positions[symbol]["entry_time"] = bar_ts_str

        return result, outcome



    def execute_scale_out(self, symbol: str, scale_frac: float, exit_reason: str = "guillotine") -> None:
        """Reduce an open position by scale_frac (0.0–1.0), booking partial PnL.

        Called when the Guillotine or structure-invalidation exit fires a
        scale_out decision.  Equivalent to the live broker's partial-close
        order: it shrinks the position in-place rather than closing fully.
        """
        from tradebot_sci.broker.trade_result_store import TradeResult
        pos = self.positions.get(symbol)
        if not pos:
            return
        price = self._get_current_price(symbol)
        side = pos.get("side", "long")
        entry_p = float(pos.get("entry_price", 0) or 0)
        total_size = float(pos.get("size", 0) or 0)  # negative for short

        close_size = total_size * scale_frac           # same sign as total_size
        remain_size = total_size * (1.0 - scale_frac)  # residual (same sign)

        # Apply exit friction to the closed portion
        friction = self.HALF_SPREAD_PCT + self.SLIPPAGE_PCT
        fill_p = price * (1 - friction) if side == "long" else price * (1 + friction)

        # PnL for the closed portion
        pnl_usd = (fill_p - entry_p) * close_size
        fee_usd = abs(close_size * fill_p) * self._get_taker_fee(symbol)
        pnl_usd -= fee_usd

        # Track cumulative PnL (matches _record_exit pattern)
        self._total_pnl += pnl_usd
        running_balance = self._initial_balance + self._total_pnl
        # Keep self.balance at initial for fixed sizing (same as _record_exit)
        self.balance = self._initial_balance

        pnl_sign = "+" if pnl_usd >= 0 else "-"
        logger.info(
            f"[REPLAY] [SCALE-OUT] {symbol} Guillotine closed {scale_frac*100:.0f}% "
            f"({abs(close_size):.4f} units @ {fill_p:.5f}) → "
            f"PnL {pnl_sign}${abs(pnl_usd):.2f} | cumPnL=${self._total_pnl:+.2f}"
        )

        # Record as a trade event in the trade store
        if self.trade_results:
            opened_at = pos.get("opened_at", "")
            self.trade_results.add_result(TradeResult(
                symbol=symbol,
                closed_at=datetime.now(timezone.utc).isoformat(),
                pnl_pct=(pnl_usd / (entry_p * abs(close_size)) if entry_p and close_size else 0),
                pnl_usd=pnl_usd,
                is_win=pnl_usd > 0,
                tier=f"{scale_frac*100:.0f}%",
                capital_at_close=running_balance,
                opened_at=opened_at,
                strategy=pos.get("strategy", "unknown"),
                exit_reason=exit_reason,
                side=side,
            ))

        if abs(remain_size) < 1e-8:
            # Fully closed — remove position
            del self.positions[symbol]
        else:
            pos["size"] = remain_size
            pos["qty"]  = abs(remain_size)
            pos["unrealized_pnl"] = (price - entry_p) * remain_size

        # Stamp exit_bar_time on every Guillotine scale_out (not just full closes)
        # so the re-entry cooldown blocks new entries while the stub is managed
        snap = self._provider._snapshot
        if snap and snap.candles:
            self._replay_exit_bar_time[symbol] = snap.candles[-1].timestamp

        self._save_state()

    def _handle_scale_out_decision(self, decision) -> tuple:
        """Intercept a scale_out decision and apply as a partial close."""
        from tradebot_sci.broker.execution import (
            ExecutionResult, ExecutionStatus,
            ExecutionOutcome, ExecutionOutcomeType,
        )
        symbol = getattr(decision, "symbol", None)
        notes  = getattr(decision, "notes", "") or ""

        # Parse scale_frac from the reason string (e.g. "|scale_frac=0.80|")
        scale_frac = 0.80   # default
        import re as _re
        m = _re.search(r"scale_frac=([0-9.]+)", notes)
        if m:
            scale_frac = float(m.group(1))

        # Determine exit reason for trade store labeling
        if "Guillotine" in notes or "guillotine" in notes:
            exit_reason = "guillotine"
        elif "Lower-High" in notes or "Higher-Low" in notes or "Invalidat" in notes:
            exit_reason = "struct_inval"
        elif "de_risk" in notes.lower():
            exit_reason = "de_risk"
        else:
            exit_reason = "scale_out"

        self.execute_scale_out(symbol, scale_frac, exit_reason=exit_reason)
        return (
            ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Replay: {exit_reason} {scale_frac*100:.0f}%"),
            ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Replay: {exit_reason}"),
        )

    def _get_current_price(self, symbol: str) -> float:
        """Get price from the replay snapshot (not the live API)."""
        ticker = self._provider.get_ticker(symbol)
        if ticker and ticker.last:
            return float(ticker.last)
        return 1.0  # should never happen

    def modify_stop_loss(self, symbol: str, new_sl: float) -> None:
        """Update the SL stored in the paper position (ATR trailing)."""
        if symbol in self.positions:
            old_sl = self.positions[symbol].get("stop_loss")
            self.positions[symbol]["stop_loss"] = new_sl
            logger.debug(f"[REPLAY] {symbol}: SL trailed {old_sl} → {new_sl:.5f}")

    def evaluate_synthetic_stops(self, market_provider, timeframe):
        """Override to evaluate SL/TP at the candle's high/low, not just close."""
        results = []
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            # ── Get OHLC of the most recent candle ───────────────────────
            snap = self._provider._snapshot
            candle_high = None
            candle_low  = None
            if snap and snap.candles:
                last_c      = snap.candles[-1]
                candle_high = float(last_c.high)
                candle_low  = float(last_c.low)

            try:
                current_close = self._get_current_price(symbol)
            except Exception:
                continue

            sl   = pos.get("stop_loss")
            tp   = pos.get("take_profit")
            side = pos.get("side", "long")
            entry_p = pos.get("entry_price", 0)
            hit = None
            exit_px = current_close

            if side == "long":
                # SL: use candle LOW (worst intra-bar price against long)
                check_sl = candle_low if candle_low is not None else current_close
                # TP: use candle HIGH (best intra-bar price for long)
                check_tp = candle_high if candle_high is not None else current_close
                if sl and check_sl <= sl:
                    hit    = "SL"
                    exit_px = sl  # exit at SL level, not close
                elif tp and tp > entry_p and check_tp >= tp:
                    hit    = "TP"
                    exit_px = tp  # exit exactly at TP level
            else:  # short
                # SL: use candle HIGH (worst intra-bar price against short)
                check_sl = candle_high if candle_high is not None else current_close
                # TP: use candle LOW (best intra-bar price for short)
                check_tp = candle_low if candle_low is not None else current_close
                if sl and check_sl >= sl:
                    hit    = "SL"
                    exit_px = sl
                elif tp and tp < entry_p and check_tp <= tp:
                    hit    = "TP"
                    exit_px = tp

            if hit:
                self._record_exit(symbol, pos, exit_px, hit, results)

        # Refresh unrealized PnL using close price
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            try:
                cur = self._get_current_price(sym)
                pos["current_price"] = cur
                pos["unrealized_pnl"] = (cur - pos["entry_price"]) * pos["size"]
                pos["pnl_pct"] = (pos["unrealized_pnl"] / (pos["entry_price"] * abs(pos["size"])) * 100
                                  if pos["entry_price"] else 0)
            except Exception:
                pass

        return results

    def _record_exit(self, symbol, pos, exit_price, hit, results):
        """Override to prevent balance compounding — sizing stays fixed at initial_balance."""
        from tradebot_sci.broker.execution import ExecutionResult, ExecutionStatus
        from tradebot_sci.broker.trade_result_store import TradeResult

        side    = pos.get("side", "long")
        entry_p = pos.get("entry_price", 0)
        friction = self.HALF_SPREAD_PCT + self.SLIPPAGE_PCT
        if side == "long":
            fill_p = exit_price * (1 - friction)
        else:
            fill_p = exit_price * (1 + friction)

        pnl_usd = (fill_p - entry_p) * pos["size"]
        fee_usd = abs(pos.get("qty", abs(pos["size"])) * fill_p) * self._get_taker_fee(symbol)
        pnl_usd -= fee_usd

        # Track cumulative PnL without compounding the sizing balance
        self._total_pnl += pnl_usd
        running_balance = self._initial_balance + self._total_pnl
        # Keep self.balance at initial for sizing purposes (new positions use initial_balance)
        self.balance = self._initial_balance

        pnl_sign = "+" if pnl_usd >= 0 else "-"
        pnl_str  = f"{pnl_sign}${abs(pnl_usd):.2f}"
        logger.info(
            f"[REPLAY] [EXIT] {symbol} {hit}: {pnl_str} "
            f"| side={side} entry={entry_p:.5f} exit={fill_p:.5f} "
            f"| pnl=${self._total_pnl:+.2f} bal=${running_balance:.2f}"
        )

        if self.trade_results:
            opened_at = pos.get("opened_at", "")
            duration_secs = None
            if opened_at:
                try:
                    duration_secs = (
                        datetime.now(timezone.utc) -
                        datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                    ).total_seconds()
                except Exception:
                    pass
            self.trade_results.add_result(TradeResult(
                symbol=symbol,
                closed_at=datetime.now(timezone.utc).isoformat(),
                pnl_pct=(pnl_usd / (entry_p * abs(pos["size"])) if entry_p else 0),
                pnl_usd=pnl_usd,
                is_win=pnl_usd > 0,
                tier="100%",
                capital_at_close=running_balance,
                opened_at=opened_at,
                duration_seconds=duration_secs,
                strategy=pos.get("strategy", "unknown"),
                exit_reason=f"replay_{hit.lower()}",
                side=side,
            ))

        del self.positions[symbol]

        # Record the exit bar time for candle-time cooldown tracking
        snap = self._provider._snapshot
        if snap and snap.candles:
            self._replay_exit_bar_time[symbol] = snap.candles[-1].timestamp

        # REPLAY FIX: Clear wall-clock SafetyGuard cooldowns immediately so
        # the next entry on this symbol isn't permanently blocked (5-min timer
        # never expires when 90 days replay in ~90 seconds of real time).
        try:
            from tradebot_sci.strategy.safety_guard import SafetyGuard
            SafetyGuard._state.symbol_exit_cooldown.pop(symbol, None)
            SafetyGuard._state.symbol_loss_streaks.pop(symbol, None)
            SafetyGuard._state.symbol_pause_until.pop(symbol, None)
        except Exception:
            pass
        results.append(ExecutionResult(
            ExecutionStatus.EXIT_SIGNAL, symbol,
            f"Replay {hit}: {pnl_str}"
        ))

    @property
    def position_hold_store(self):
        return None  # No hold store in replay — keep it simple


# ─────────────────────────────────────────────────────────────────────────────
# Observation Loader
# ─────────────────────────────────────────────────────────────────────────────

def load_observations(symbols: list[str], start_dt: datetime, end_dt: datetime, api_fallback: bool = False) -> dict[str, list[dict]]:
    """Load recorded observations for each symbol for the given date range.
    If api_fallback is True and no local data is found, it synthesizes observations from OANDA."""
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str   = end_dt.strftime("%Y-%m-%d")

    all_obs: dict[str, list[dict]] = {}
    for sym in symbols:
        sym_dir = _CANDLE_DIR / sym
        if not sym_dir.exists():
            logger.warning(f"[REPLAY] No candle history for {sym}")
            continue
        obs = []
        for f in sorted(sym_dir.glob("*.jsonl")):
            try:
                date_part = f.stem.split("_", 1)[1]
            except IndexError:
                continue
            if date_part < start_str or date_part > end_str:
                continue
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if not obs and api_fallback:
            try:
                from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
                from tradebot_sci import paths as _paths
                secrets_path = _paths.SECRETS_FILE
                account_id, api_key, env = None, None, "practice"
                if secrets_path.exists():
                    from dotenv import dotenv_values
                    from tradebot_sci.config.loader import load_config_json
                    secrets = dotenv_values(secrets_path)
                    config = load_config_json()
                    account_id = config.get("brokers", {}).get("oanda", {}).get("account_id")
                    api_key = secrets.get("OANDA_API_KEY") or secrets.get("OANDA_API_TOKEN")
                    env = config.get("brokers", {}).get("oanda", {}).get("environment", "practice")
                
                if account_id and api_key:
                    provider = OandaMarketDataProvider(account_id, api_key, env)
                    import oandapyV20.endpoints.instruments as instruments
                    oanda_sym = provider._normalize_symbol(sym)
                    
                    # Transferred start_dt and end_dt from method arguments
                    
                    logger.info(f"[API-FALLBACK] Fetching synthetic observations for {sym} from OANDA (Paginated)")
                    
                    def _fetch_paginated_candles(granularity: str, start: datetime, end: datetime) -> list:
                        all_candles = []
                        current_start = start
                        while current_start < end:
                            duration_seconds = (end - current_start).total_seconds()
                            if granularity == "M5":
                                needed = int(duration_seconds / 300) + 10
                            elif granularity == "H4":
                                needed = int(duration_seconds / 14400) + 10
                            else:
                                needed = 5000
                            
                            params = {
                                "granularity": granularity,
                                "price": "M",
                                "from": current_start.isoformat(),
                                "count": min(5000, max(1, needed))
                            }
                            try:
                                r = instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
                                provider.client.request(r)
                                batch = r.response.get("candles", [])
                                if not batch: break
                                all_candles.extend(batch)
                                
                                last_time_str = batch[-1]["time"]
                                if "." in last_time_str:
                                    base, rest = last_time_str.split(".", 1)
                                    rest = rest.replace("Z", "+00:00")
                                    last_time_str = f"{base}.{rest[:6]}"
                                else:
                                    last_time_str = last_time_str.replace("Z", "+00:00")
                                    
                                last_ts = datetime.fromisoformat(last_time_str).replace(tzinfo=timezone.utc)
                                if last_ts >= end: break
                                current_start = last_ts + timedelta(seconds=1)
                            except Exception as e:
                                logger.error(f"[API-FALLBACK] Pagination fail for {granularity}: {e}")
                                break
                        return [c for c in all_candles if datetime.fromisoformat(c["time"].split(".")[0].replace("Z", "+00:00")).replace(tzinfo=timezone.utc) <= end]

                    # ── Resolve HTF from active profile ───────────────────────
                    _active_prof_name = config.get("active_profile", "default")
                    _prof_data = config.get("profiles", {}).get(_active_prof_name, {})
                    _htf_setting = _prof_data.get("htf_timeframe") or config.get("global", {}).get("htf_timeframe") or "4h"

                    # Map common timeframes to OANDA granularity
                    _oanda_granularity_map = {
                        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
                        "1h": "H1", "4h": "H4", "1d": "D", "1w": "W"
                    }
                    oanda_htf_tf = _oanda_granularity_map.get(_htf_setting.lower(), "H1")
                    logger.info(f"[API-FALLBACK] Using mapped OANDA HTF Timeframe: {oanda_htf_tf} (from profile setting: {_htf_setting})")

                    ltf_raw = _fetch_paginated_candles("M5", start_dt, end_dt)
                    htf_raw = _fetch_paginated_candles(oanda_htf_tf, start_dt, end_dt)
                    
                    def _fmt(c):
                        ts_str = c["time"]
                        if "." in ts_str:
                            base, rest = ts_str.split(".", 1)
                            suffix = ""
                            if "Z" in rest: suffix = "Z"; rest = rest.replace("Z", "")
                            elif "+" in rest: rest, offset = rest.split("+", 1); suffix = "+" + offset
                            elif "-" in rest: rest, offset = rest.split("-", 1); suffix = "-" + offset
                            ts_str = f"{base}.{rest[:6]}{suffix}"
                        return {"t": ts_str, "o": c["mid"]["o"], "h": c["mid"]["h"], "l": c["mid"]["l"], "c": c["mid"]["c"], "v": c["volume"]}
                    
                    ltf_fmt = [_fmt(c) for c in ltf_raw if c.get("mid") and c.get("complete", True)]
                    htf_fmt = [_fmt(c) for c in htf_raw if c.get("mid") and c.get("complete", True)]
                    
                    if ltf_fmt:
                        for ltf_c in ltf_fmt:
                            c_ts = ltf_c["t"]
                            # Only include HTF candles up to this LTF timestamp
                            valid_htf = [h for h in htf_fmt if h["t"] <= c_ts]
                            
                            synth_obs = {
                                "sym": sym,
                                "tf": "5m",
                                "htf_tf": _htf_setting.lower(),
                                "ltf_tf": "5m",
                                "ltf": [ltf_c],  # current candle for this tick
                                "htf": valid_htf[-1:] if valid_htf else [], # current active HTF candle
                                "ts": c_ts.replace("Z", "+00:00")
                            }
                            obs.append(synth_obs)
                        logger.info(f"[API-FALLBACK] Created {len(obs)} synthetic snapshots from {len(ltf_fmt)} LTF + {len(htf_fmt)} HTF")
                    else:
                        logger.warning(f"[API-FALLBACK] No LTF candles generated for {sym} despite paginated fetch.")
            except Exception as e:
                logger.warning(f"[API-FALLBACK] Failed to simulate data for {sym}: {e}")

        obs.sort(key=lambda x: x.get("ts", ""))
        if obs:
            logger.info(f"[REPLAY] {sym}: loaded {len(obs)} observations ({start_str} → {end_str})")
            all_obs[sym] = obs
    return all_obs


def obs_to_snapshot(obs: dict) -> Optional[MarketSnapshot]:
    """Convert a recorded observation back into a MarketSnapshot."""
    try:
        ltf = [_dict_to_candle(c) for c in obs.get("ltf", [])]
        htf = [_dict_to_candle(c) for c in obs.get("htf", [])]
        if not ltf:
            return None
        tf     = obs.get("tf", "15m")
        htf_tf = obs.get("htf_tf", "4h")
        ltf_tf = obs.get("ltf_tf", tf)
        _neutral = TrendState(direction="neutral", strength=0.0)
        return MarketSnapshot(
            symbol=obs["sym"],
            timeframe=tf,
            candles=ltf,
            htf_candles=htf,
            ltf_candles=ltf,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_timeframe=htf_tf,
            ltf_timeframe=ltf_tf,
        )
    except Exception as e:
        logger.debug(f"[REPLAY] obs_to_snapshot failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Replay Loop
# ─────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# Per-Symbol Worker (must be top-level for ProcessPoolExecutor pickling)
# ───────────────────────────────────────────────────────────────────────────────

def _worker_replay_symbol(args: tuple) -> dict:
    """Runs the full replay for ONE symbol in an isolated subprocess.
    Args: (sym, all_obs, ltf_raw, htf_raw, initial_balance, speed, src_path, strategy)
    All state is local — no shared memory contention.
    Returns a plain dict (picklable).
    """
    import sys, time, logging
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    import json

    if len(args) == 9:
        sym, obs_list, ltf_raw, htf_raw, initial_balance, speed, src_path, args_strategy, sim_start_dt = args
    elif len(args) == 8:
        sym, obs_list, ltf_raw, htf_raw, initial_balance, speed, src_path, args_strategy = args
        sim_start_dt = None
    else:
        sym, obs_list, ltf_raw, htf_raw, initial_balance, speed, src_path = args
        args_strategy = None
        sim_start_dt = None
    src_path = str(Path(__file__).resolve().parents[1] / "src")

    if src_path not in sys.path:
        sys.path.insert(0, src_path)
        
    # Worker processes are silent — all output goes through main process
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    for _ln in list(logging.Logger.manager.loggerDict.keys()):
        logging.getLogger(_ln).setLevel(logging.INFO) # Keep libs quiet, script loud
    
    if not obs_list:
        return {"sym": sym, "error": "No data", "trades": [], "total_pnl": 0.0, "ticks": 0, "elapsed": 0.0}

    # Reconstruct raw candles for the provider timeline if not already provided
    if not ltf_raw:
        seen_ltf = set()
        seen_htf = set()
        for o in obs_list:
            for c in o.get("ltf", []):
                t_val = c.get("t", c.get("time"))
                if t_val not in seen_ltf:
                    seen_ltf.add(t_val)
                    ltf_raw.append(c)
            for c in o.get("htf", []):
                t_val = c.get("t", c.get("time"))
                if t_val not in seen_htf:
                    seen_htf.add(t_val)
                    htf_raw.append(c)

    from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState
    from tradebot_sci.broker.trade_result_store import TradeResultStore
    from tradebot_sci.strategy.engine import StrategyEngine
    from tradebot_sci.runtime.cycle import process_candidate_cycle
    from tradebot_sci.config.loader import get_settings

    settings = get_settings()
    profile  = settings.get_active_profile()

    def _dc(d: dict) -> Candle:
        ts = datetime.fromisoformat(d.get("t", d.get("time")).replace("Z", "+00:00"))
        return Candle(timestamp=ts, open=float(d.get("o", d.get("mid", {}).get("o", 0))), 
                      high=float(d.get("h", d.get("mid", {}).get("h", 0))),
                      low=float(d.get("l", d.get("mid", {}).get("l", 0))), 
                      close=float(d.get("c", d.get("mid", {}).get("c", 0))), 
                      volume=float(d.get("v", d.get("volume", 0))))

    ltf_timeline = sorted([_dc(c) for c in ltf_raw], key=lambda c: c.timestamp)
    htf_timeline = sorted([_dc(c) for c in htf_raw], key=lambda c: c.timestamp)
    
    if len(ltf_timeline) > 0:
        logging.info(f"[REPLAY] {sym} timelines generated. LTF count: {len(ltf_timeline)}, HTF count: {len(htf_timeline)}")

    provider = ReplayMarketProvider(candle_timeline={sym: ltf_timeline})
    provider.set_htf_timeline({sym: htf_timeline})

    # In-memory trade store — no disk I/O between workers
    trade_store = TradeResultStore(path=f"/tmp/_replay_{sym}.json", skip_save=True)

    # ── Replay-specific profile: disable SAR/CR ──────────────────────────
    # The engine's SAR cooldown uses wall-clock datetime.now() — but replay
    # compresses 14 days into ~12 seconds.  A "4-hour SAR cooldown" that starts
    # at 18:00 real-time expires at 22:00 (real), but replay finishes at 18:00:12.
    # In practice the cooldown NEVER fires, so every losing trade triggers a new
    # SAR entry in the opposite direction, and that also loses, and so on:
    #   long → SL → SAR short → SL → SAR long → SL → … (58 EURJPY trades in 14 days)
    # This creates a systematic 0% WR that has nothing to do with strategy quality.
    # Solution: disable SAR+CR in replay so we measure the BASE strategy performance.
    update_args = {
        "stop_and_reverse_enabled": True,
        "counter_reversal_enabled": True,
    }
    if args_strategy:
        update_args["strategy_variant"] = args_strategy
        update_args["strategies"] = None

    try:
        replay_profile = profile.model_copy(update=update_args)
    except AttributeError:
        # Pydantic v1 fallback
        replay_profile = profile.copy(update=update_args)

    broker = ReplayPaperBroker(
        profile_settings=replay_profile,
        provider=provider,
        trade_results=trade_store,
        initial_balance=initial_balance,
    )

    try:
        engine = StrategyEngine(
            ai_client=None,
            market_provider=provider,
            profile=replay_profile,
            symbol=sym,
            settings=settings,
            trade_results=trade_store,
        )
    except Exception as exc:
        return {"sym": sym, "error": str(exc), "trades": [], "total_pnl": 0.0, "ticks": 0, "elapsed": 0.0}


    # Reset SafetyGuard wall-clock state — replay runs 90 days in 90 seconds so exit
    # cooldowns (5-min timer) would never expire, permanently blocking re-entry.
    from tradebot_sci.strategy.safety_guard import SafetyGuard
    SafetyGuard.reset_state()

    engines    = {sym: engine}
    _WARMUP    = 200  # need 200 LTF candles in window before indicators are meaningful
    warmup     = 0
    tick_count = 0
    start_real = time.perf_counter()
    _neutral   = TrendState(direction="neutral", strength=0.0)

    import bisect as _bisect
    ltf_timestamps = [c.timestamp for c in ltf_timeline]
    htf_timestamps = [c.timestamp for c in htf_timeline]

    # Speed governor: only sleep when the candle bar CHANGES, not every raw tick.
    # With ~13,000 raw obs/day but only ~288 unique 5m bars, this reduces sleeps
    # from 13,000 to ~288, making speed=2 take ~2.4 min/day instead of ~110 min.
    _last_bar_ts = None
    
    logging.info(f"[REPLAY] {sym} starting loop with {len(obs_list)} synthetic obs. Timestamps: LTF={len(ltf_timestamps)}, HTF={len(htf_timestamps)}.")

    for obs in obs_list:
        try:
            raw_ts = obs.get("ts", "")
            if not raw_ts: continue
            
            # Normalize timestamp to UTC datetime for accurate bisect sorting
            if "Z" in raw_ts: raw_ts = raw_ts.replace("Z", "+00:00")
            tick_dt = datetime.fromisoformat(raw_ts)

            if sim_start_dt and tick_dt < sim_start_dt:
                continue

            # Full rolling window: last 500 LTF candles up to this tick
            ltf_idx = _bisect.bisect_right(ltf_timestamps, tick_dt)
            ltf = ltf_timeline[max(0, ltf_idx - 500): ltf_idx]

            # Full rolling window: last 500 HTF candles up to this tick
            # (gives ADX/EMA/MACD enough history to compute proper htf_strength)
            htf_idx = _bisect.bisect_right(htf_timestamps, tick_dt)
            htf = htf_timeline[max(0, htf_idx - 500): htf_idx]
        except Exception as e:
            logging.error(f"[REPLAY] Exception in bisect loop: {e}")
            continue

        # Skip until we have enough LTF candles for indicators (EMA55 needs 55)
        if len(ltf) < 55:
            # logging.info(f"[REPLAY] Skipped tick at {tick_ts}. ltf len: {len(ltf)}. Need 55.")
            continue
        if not ltf:
            continue

        tf     = obs.get("tf", "5m")
        htf_tf = obs.get("htf_tf", "4h")
        snap = MarketSnapshot(
            symbol=sym, timeframe=tf,
            candles=ltf, htf_candles=htf, ltf_candles=ltf,
            trend_htf=_neutral, trend_ltf=_neutral,
            htf_timeframe=htf_tf, ltf_timeframe=tf,
        )
        provider.set_snapshot(snap)

        tick_count += 1
        broker.evaluate_synthetic_stops(provider, snap.timeframe)
        candidates = [(sym, provider._snapshot or snap, 0.0, "replay")]
        try:
            process_candidate_cycle(
                executor=broker, engines=engines,
                profile=None, profile_settings=profile,
                settings=settings, strike_tracker=None,
                candidates=candidates, stop_after_submit=False,
            )
        except Exception:
            pass

        # Speed governor: sleep only when we cross into a new candle bar
        if speed > 0 and ltf:
            current_bar_ts = ltf[-1].timestamp
            if current_bar_ts != _last_bar_ts:
                _last_bar_ts = current_bar_ts
                time.sleep(1.0 / speed)
                
        # Emit progress JSON for UI
        if tick_count % 250 == 0:
            pct = int((tick_count / len(obs_list)) * 100)
            import json as _json
            print(_json.dumps({
                "_type": "progress",
                "symbol": sym,
                "pct": pct,
                "ticks": tick_count,
                "total": len(obs_list)
            }), flush=True, file=sys.stderr)

    # Emit final 100%
    import json as _json
    print(_json.dumps({
        "_type": "progress",
        "symbol": sym,
        "pct": 100,
        "ticks": tick_count,
        "total": len(obs_list)
    }), flush=True, file=sys.stderr)

    elapsed = time.perf_counter() - start_real

    trades = []
    for r in trade_store.results:
        trades.append({
            "symbol":      r.symbol,
            "closed_at":   getattr(r, "closed_at", None),
            "pnl_usd":     float(r.pnl_usd),
            "is_win":      bool(r.is_win),
            "side":        getattr(r, "side", "?"),
            "exit_reason": getattr(r, "exit_reason", ""),
            "strategy":    getattr(r, "strategy", ""),
        })

    return {
        "sym":       sym,
        "trades":    trades,
        "total_pnl": broker._total_pnl,
        "ticks":     tick_count,
        "elapsed":   elapsed,
        "error":     None,
    }


# ───────────────────────────────────────────────────────────────────────────────
# Main Replay Orchestrator (dispatches symbol workers in parallel)
# ───────────────────────────────────────────────────────────────────────────────

def run_replay(start_dt: datetime, end_dt: datetime, speed: float, initial_balance: float,
               symbols_filter: Optional[list] = None,
               max_workers: Optional[int] = None,
               strategy: Optional[str] = None) -> dict:
    # ── Bootstrap ────────────────────────────────────────────────────────────
    settings = get_settings()
    profile_name = getattr(settings, "profile", "forex_continuous")
    logger.info(f"[REPLAY] Profile: {profile_name}")

    if not _CANDLE_DIR.exists():
        logger.error(f"[REPLAY] No candle history at {_CANDLE_DIR}. Run the live bot first.")
        sys.exit(1)

    available_syms = sorted([d.name for d in _CANDLE_DIR.iterdir() if d.is_dir()])
    if symbols_filter:
        available_syms = [s for s in available_syms if s in symbols_filter]
    if not available_syms:
        logger.error("[REPLAY] No symbols found in candle history.")
        sys.exit(1)

    logger.info(f"[REPLAY] Symbols: {', '.join(available_syms)}")

    # ── Load observations ──────────────────────────────────────────────
    fetch_start = start_dt - timedelta(days=50)
    all_obs = load_observations(available_syms, fetch_start, end_dt, api_fallback=True)
    if not all_obs:
        logger.error("[REPLAY] No observations loaded — nothing to replay.")
        sys.exit(1)

    # ── Build per-symbol candle timeline (resampled HTF) ──────────────────
    logger.info("[REPLAY] Building candle timelines…")
    ltf_raw_by_sym: dict = {}
    htf_raw_by_sym: dict = {}
    total_ticks = 0
    for sym, obs_list in all_obs.items():
        ltf_all: dict = {}
        htf_all: dict = {}
        for obs in obs_list:
            if "ltf" in obs:
                for c in obs.get("ltf", []):
                    t_val = c.get("t", c.get("time"))
                    if t_val: ltf_all[t_val] = c
                for c in obs.get("htf", []):
                    t_val = c.get("t", c.get("time"))
                    if t_val: htf_all[t_val] = c
                
                # BIG MEMORY & IPC SAVER: drop massive arrays before pickling to workers
                obs.pop("ltf", None)
                obs.pop("htf", None)
            else:
                # Direct CCXT candle format
                c = {"t": obs["time"], "o": obs["open"], "h": obs["high"], "l": obs["low"], "c": obs["close"], "v": obs["volume"]}
                ltf_all[obs["time"]] = c
                obs["ts"] = obs["time"]
                obs["tf"] = "5m"
        ltf_raw_by_sym[sym] = list(ltf_all.values())
        # Resample LTF → HTF so workers get rich HTF indicator history
        ltf_tmp = sorted([_dict_to_candle(c) for c in ltf_all.values()], key=lambda c: c.timestamp)
        htf_resampled = _resample_ltf_to_htf(ltf_tmp, period_minutes=60)
        if len(htf_resampled) >= 15:
            htf_raw_by_sym[sym] = [
                {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high,
                 "l": c.low, "c": c.close, "v": c.volume}
                for c in htf_resampled
            ]
        else:
            htf_raw_by_sym[sym] = list(htf_all.values())
        logger.info(f"[REPLAY] {sym}: {len(ltf_raw_by_sym[sym])} LTF + "
                    f"{len(htf_raw_by_sym[sym])} HTF  | {len(obs_list)} obs")
        total_ticks += len(obs_list)

    n_workers = min(len(all_obs), multiprocessing.cpu_count())
    if max_workers:
        n_workers = min(n_workers, max_workers)
    else:
        n_workers = min(n_workers, 4)  # Default cap to prevent resource exhaustion
        
    logger.info(f"[REPLAY] Total ticks: {total_ticks}  | Workers: {n_workers} CPUs")
    logger.info("─" * 70)

    # ── Dispatch all symbols in parallel ───────────────────────────────
    src_path   = str(_repo / "src")
    start_real = time.perf_counter()
    all_results: list = []
    failed_syms: list = []

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _worker_replay_symbol,
                (sym,
                all_obs[sym],
                ltf_raw_by_sym[sym],
                htf_raw_by_sym[sym],
                initial_balance,
                speed,
                src_path,
                strategy,
                start_dt)
            ): sym
            for sym in all_obs
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                res = fut.result()
                if res.get("error"):
                    logger.warning(f"[REPLAY] {sym}: worker error — {res['error']}")
                    failed_syms.append(sym)
                else:
                    logger.info(
                        f"[REPLAY] [{sym}] done — {res['ticks']} ticks  "
                        f"{len(res['trades'])} trades  PnL=${res['total_pnl']:+.2f}  "
                        f"({res['elapsed']:.1f}s)"
                    )
                    all_results.append(res)
            except Exception as exc:
                logger.warning(f"[REPLAY] {sym}: future error — {exc}")
                failed_syms.append(sym)

    elapsed = time.perf_counter() - start_real

    # ── Aggregate ────────────────────────────────────────────────────────────
    all_trades: list = []
    for res in all_results:
        all_trades.extend(res["trades"])
    all_trades.sort(key=lambda t: t.get("closed_at") or "")

    total_pnl  = sum(r["total_pnl"] for r in all_results)
    tick_count = sum(r["ticks"] for r in all_results)

    wins   = [t for t in all_trades if t["is_win"]]
    losses = [t for t in all_trades if not t["is_win"]]
    wr        = len(wins) / len(all_trades) * 100 if all_trades else 0
    avg_win   = sum(t["pnl_usd"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss  = sum(t["pnl_usd"] for t in losses) / len(losses) if losses else 0
    gross_win  = sum(t["pnl_usd"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl_usd"] for t in losses)) if losses else 0
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0

    running_bal = initial_balance
    peak = initial_balance
    max_dd_pct = 0.0
    for t in all_trades:
        running_bal += t["pnl_usd"]
        if running_bal > peak:
            peak = running_bal
        dd = (peak - running_bal) / peak * 100 if peak > 0 else 0
        if dd > max_dd_pct:
            max_dd_pct = dd

    final_bal = initial_balance + total_pnl

    logger.info("─" * 70)
    logger.info(f"[REPLAY] ✅ Done in {elapsed:.1f}s  ({n_workers} workers in parallel)")
    if failed_syms:
        logger.warning(f"[REPLAY] Failed symbols: {failed_syms}")
    logger.info(f"[REPLAY] Trades: {len(all_trades)}  (W={len(wins)} L={len(losses)})  WR={wr:.0f}%")
    logger.info(f"[REPLAY] PnL: ${total_pnl:+.2f}  AvgWin=${avg_win:+.2f}  AvgLoss=${avg_loss:+.2f}")
    logger.info(f"[REPLAY] Final Balance: ${final_bal:.2f}  (started ${initial_balance:.2f}, Δ${total_pnl:+.2f})")
    logger.info(f"[REPLAY] ProfitFactor={profit_factor}  MaxDD={max_dd_pct:.1f}%  "
                f"RR={round(avg_win/abs(avg_loss),2) if avg_loss else 0}")

    if all_trades:
        logger.info("─" * 70)
        logger.info(f"{'#':<4} {'Symbol':<10} {'Side':<6} {'PnL':>8}  {'Exit Reason'}")
        for i, t in enumerate(all_trades, 1):
            logger.info(
                f"  [{t['closed_at']}] {t['symbol']:>8s} "
                f"{t['side']:>5s} "
                f"${t['pnl_usd']:>+7.2f}  {t['exit_reason']}"
            )

    # Calculate Recommended Payout parameters
    pnl_for_payout = total_pnl
    velocity = (pnl_for_payout / initial_balance) * 100 if initial_balance > 0 else 0
    payout_pct = 0.75 if velocity >= 2.5 else 0.50
    payout_usd = pnl_for_payout * payout_pct if pnl_for_payout > 0 else 0

    if all_trades:
        logger.info(f"┌─────────────────────────────────────────┐")
        logger.info(f"│        RECOMMENDED PAYOUT CARD          │")
        logger.info(f"├─────────────────────────────────────────┤")
        logger.info(f"│ Net Profit:      ${pnl_for_payout:<10.2f}           │")
        logger.info(f"│ Velocity:        {velocity:<5.2f}%                  │")
        logger.info(f"│ Payout Ratio:    {payout_pct * 100:<5.0f}%                  │")
        logger.info(f"│ Recommended:     ${payout_usd:<10.2f}           │")
        logger.info(f"│ Compounded:      ${pnl_for_payout - payout_usd:<10.2f}           │")
        logger.info(f"└─────────────────────────────────────────┘")

    return {
        "total_trades":    len(all_trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "win_rate":        round(wr, 1),
        "total_pnl":       round(total_pnl, 2),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
        "profit_factor":   profit_factor,
        "max_drawdown":    round(max_dd_pct, 2),
        "final_balance":   round(final_bal, 2),
        "initial_balance": initial_balance,
        "payout_usd":      round(payout_usd, 2),
        "payout_pct":      round(payout_pct * 100, 0),
        "risk_reward":     round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0,
        "elapsed_seconds": round(elapsed, 1),
        "ticks_replayed":  tick_count,
        "workers_used":    n_workers,
        "trades": [
            {
                "time":   t.get("closed_at"),
                "symbol": t["symbol"],
                "side":   t["side"],
                "pnl":    round(t["pnl_usd"], 2),
                "reason": t["exit_reason"],
                "strategy": t.get("strategy", ""),
            }
            for t in all_trades
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run the live bot engine against recorded candles using PaperBroker."
    )
    parser.add_argument("--days",       type=int,   default=4,
                        help="Days of history to replay (default: 4). Overridden by --start-date/--end-date.")
    parser.add_argument("--start-date", type=str,   default=None,
                        help="Start date YYYY-MM-DD (inclusive). Takes priority over --days.")
    parser.add_argument("--end-date",   type=str,   default=None,
                        help="End date YYYY-MM-DD (inclusive, defaults to today).")
    parser.add_argument("--speed",      type=float, default=50,
                        help="Ticks per second (0=max). Default: 50")
    parser.add_argument("--balance",    type=float, default=5700.0,
                        help="Starting paper balance (default: 5700)")
    parser.add_argument("--symbols",    type=str,   default=None,
                        help="Comma-separated symbols to replay (default: all recorded)")
    parser.add_argument(
        "--no-parallel", action="store_true",
        help="Disable multi-core parallelism (force single-threaded)"
    )
    parser.add_argument(
        "--api-fallback", action="store_true",
        help="Fetch missing historical data from OANDA API if local data is unavailable"
    )
    parser.add_argument("--strategy", type=str, default=None,
                        help="Strategy to force override")
    parser.add_argument("--max-workers", type=int, default=None,
                        help="Limit the number of CPU cores used. Defaults to 4 to prevent resource exhaustion.")
    parser.add_argument("--json-output", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    # Resolve date range
    def parse_cli_date(d_str: str) -> datetime:
        try:
            return datetime.strptime(d_str, "%Y-%m-%d")
        except ValueError:
            return datetime.strptime(d_str, "%m/%d/%Y")

    if args.start_date:
        try:
            start_dt = parse_cli_date(args.start_date).replace(tzinfo=timezone.utc)
            end_dt = parse_cli_date(args.end_date).replace(tzinfo=timezone.utc) if args.end_date else datetime.now(timezone.utc)
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            sys.exit(1)
    else:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=args.days)

    syms = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    
    # Run the replay in an infinite loop so it continues as new days pass
    while True:
        # ── 1. Reload Configuration on each pass to check for break conditions ──
        try:
            raw_cfg = load_config_json()
            settings = get_settings() # ensure we have a model mapping for sabbath context
            
            # Identify core modes
            execute_trades = raw_cfg.get("global", {}).get("execute_trades", False)
            paper_replay_mode = raw_cfg.get("global", {}).get("replay_mode", False)
            
            # For back-compat with older config setups that pushed replay modes directly into profiles
            active_profile_str = raw_cfg.get("active_profile", "default")
            prof_dict = raw_cfg.get("profiles", {}).get(active_profile_str, {})
            if "replay_mode" in prof_dict:
                paper_replay_mode = prof_dict["replay_mode"]

            sabbath_replay_mode = prof_dict.get("sabbath_replay_mode", True)
            
            # Evaluate current Sabbath status
            profile_model = settings.profiles.get(active_profile_str) or list(settings.profiles.values())[0]
            sabbath_context = SabbathContext(profile_model)
            sabbath_active, _, _ = sabbath_context.evaluate(datetime.now(timezone.utc))
            
            # ── Evaluate Break Conditions ──
            if execute_trades and not sabbath_active:
                logger.info("[REPLAY] BYPASS: Live Trading is enabled and Sabbath is inactive, but bypassing for manual run.")
                # break
                
            if not paper_replay_mode and not sabbath_active:
                logger.info("[REPLAY] BYPASS: Paper Replay Mode is disabled and Sabbath is inactive, bypassing for manual run.")
                # break
                
            if not sabbath_active and sabbath_replay_mode and not paper_replay_mode:
                logger.info("[REPLAY] BYPASS: Sabbath has ended, bypassing for manual run.")
                # break

        except Exception as e:
            logger.error(f"[REPLAY] Failed to reload configuration for break check: {e}")

        logger.info(f"\n[REPLAY] Starting continuous replay cycle...")
        result = run_replay(start_dt, end_dt, speed=args.speed,
                            initial_balance=args.balance, symbols_filter=syms,
                            max_workers=args.max_workers,
                            strategy=args.strategy)

        # ── Emit JSON summary for UI consumption ─────────────────────────────
        if args.json_output and result:
            import json as _json
            print(_json.dumps(result), flush=True)
            
        logger.info(f"[REPLAY] Cycle complete. Exiting single-pass replay.")
        break


if __name__ == "__main__":
    main()
