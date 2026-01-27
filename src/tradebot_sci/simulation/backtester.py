"""Historical simulation engine for backtesting ICC strategy.

This module provides a backtesting framework that replays historical market data
through the bot's existing strategy logic to validate performance without risking
real capital. It fetches historical candles from IBKR, simulates trade execution
with realistic fill assumptions, and tracks P&L over the specified timeframe.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, time as dt_time
import os
import random
from typing import Any, Dict, List, Optional
# Added os for optimization
from zoneinfo import ZoneInfo

from ib_insync import IB, util

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionOutcomeType
from tradebot_sci.broker.trade_result_store import TradeResult, TradeResultStore
from tradebot_sci.config.models import Settings
from tradebot_sci.market.contracts import build_contract
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.ai.client import TradeSciAIClient

logger = logging.getLogger(__name__)


def _calculate_pnl(entry_price: float, exit_price: float, size: float, direction: str) -> float:
    """Calculate PnL correctly for both long and short positions.

    Long: profit when price goes UP   -> (exit - entry) * size
    Short: profit when price goes DOWN -> (entry - exit) * size
    """
    if direction == "short":
        return (entry_price - exit_price) * size
    else:  # long
        return (exit_price - entry_price) * size


def _resample_candles(candles: List[Candle], target_seconds: int) -> List[Candle]:
    if not candles or target_seconds <= 0:
        return []

    resampled: List[Candle] = []
    current_bucket = None
    current_candle: Optional[Candle] = None

    for candle in candles:
        ts = candle.timestamp
        tzinfo = ts.tzinfo
        bucket_start = int(ts.timestamp() // target_seconds) * target_seconds

        if current_bucket != bucket_start:
            if current_candle is not None:
                resampled.append(current_candle)
            bucket_dt = datetime.fromtimestamp(bucket_start, tz=tzinfo) if tzinfo else datetime.fromtimestamp(bucket_start)
            current_candle = Candle(
                timestamp=bucket_dt,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            )
            current_bucket = bucket_start
        else:
            current_candle.high = max(current_candle.high, candle.high)
            current_candle.low = min(current_candle.low, candle.low)
            current_candle.close = candle.close
            current_candle.volume += candle.volume

    if current_candle is not None:
        resampled.append(current_candle)

    return resampled


def _timeframe_to_seconds(timeframe: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(timeframe, 0)


@dataclass
class SimulatedPosition:
    """Tracks an open position during simulation."""
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    size: float
    entry_time: datetime
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    pyramid_count: int = 1  # Number of entries (1 = initial, 2+ = pyramided)
    total_cost: float = 0.0  # Total capital deployed (for average price calc)
    htf_neutral_bars: int = 0  # Track how long HTF has been neutral
    entry_gates: Optional[dict] = None  # Score breakdown at entry time


@dataclass
class SimulatedTrade:
    """Record of a completed trade during simulation."""
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str  # "stop", "target", "signal", "eod"
    entry_gates: Optional[dict] = None  # Score breakdown at entry time


@dataclass
class BacktestResult:
    """Complete results from a backtest run."""
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_return_pct: float
    trades: List[SimulatedTrade] = field(default_factory=list)
    weekly_equity: Dict[str, float] = field(default_factory=dict)  # ISO week -> equity
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sharpe_ratio: float = 0.0
    potential_trades_blocked: int = 0
    potential_trade_block_reasons: Dict[str, int] = field(default_factory=dict)


class HistoricalMarketDataProvider:
    """Provides market data from historical candles for backtesting."""

    def __init__(self, ib: IB, settings: Settings):
        self.ib = ib
        self.settings = settings
        self._cache: Dict[str, List[Candle]] = {}

    def _summarize_signal_samples(
        self,
        samples: list[dict[str, Any]],
        all_candles: Dict[str, List[Candle]],
        hold_seconds: float,
    ) -> list[str]:
        def _exit_close(symbol: str, target_time: datetime) -> Optional[float]:
            candles = all_candles.get(symbol, [])
            for candle in candles:
                if candle.timestamp >= target_time:
                    return candle.close
            return None

        def _win(sample: dict[str, Any], exit_close: float) -> bool:
            entry_close = float(sample["close"])
            if sample["direction"] == "short":
                return exit_close < entry_close
            return exit_close > entry_close

        buckets: dict[str, list[bool]] = defaultdict(list)
        total = 0
        wins = 0
        for sample in samples:
            target_time = sample["time"] + timedelta(seconds=hold_seconds)
            exit_close = _exit_close(sample["symbol"], target_time)
            if exit_close is None:
                continue
            total += 1
            did_win = _win(sample, exit_close)
            wins += 1 if did_win else 0
            buckets[f"sweep={sample['sweep']}"].append(did_win)
            buckets[f"htf_align={sample['htf_align']}"].append(did_win)
            htf_strength = sample.get("htf_strength")
            phase = sample.get("phase") or "unknown"
            stack_label = sample.get("stack_label") or "unknown"
            buckets[f"sweep={sample['sweep']} phase={phase}"].append(did_win)
            if isinstance(htf_strength, (int, float)):
                htf_bucket = htf_strength >= 0.7
                buckets[f"htf_strength>=0.7={htf_bucket}"].append(did_win)
                buckets[f"htf_strength>=0.7={htf_bucket} phase={phase}"].append(did_win)
            buckets[f"phase={phase}"].append(did_win)
            buckets[f"stack={stack_label}"].append(did_win)

        if total == 0:
            return ["[BACKTEST] Signal analysis: no eligible signals with future candles."]
        lines = [f"[BACKTEST] Signal analysis: {wins}/{total} wins ({wins / total:.1%})"]
        for key, values in sorted(buckets.items()):
            if not values:
                continue
            win_count = sum(1 for v in values if v)
            win_rate = win_count / len(values)
            lines.append(f"[BACKTEST]   {key}: {win_count}/{len(values)} ({win_rate:.1%})")
        return lines

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        return _timeframe_to_seconds(timeframe)

    def _convert_timeframe_to_ibkr(self, timeframe: str) -> str:
        """Convert internal timeframe format (5m, 1h) to IBKR format (5 mins, 1 hour)."""
        # Map common formats
        mapping = {
            "1m": "1 min",
            "2m": "2 mins",
            "3m": "3 mins",
            "4m": "4 mins",
            "5m": "5 mins",
            "10m": "10 mins",
            "15m": "15 mins",
            "20m": "20 mins",
            "30m": "30 mins",
            "1h": "1 hour",
            "2h": "2 hours",
            "3h": "3 hours",
            "4h": "4 hours",
            "8h": "8 hours",
            "1d": "1 day",
            "1W": "1W",
            "1M": "1M",
        }
        return mapping.get(timeframe, timeframe)

    def fetch_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Candle]:
        """Fetch historical candles from IBKR for the specified date range."""
        cache_key = f"{symbol}:{timeframe}:{start_date.isoformat()}:{end_date.isoformat()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            contract = build_contract(symbol)
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                logger.warning(f"[BACKTEST] Could not qualify contract for {symbol}")
                return []

            # Determine whatToShow based on asset type
            what = "TRADES"
            if hasattr(qualified[0], "secType"):
                if qualified[0].secType in ("CRYPTO", "CASH"):
                    what = "MIDPOINT"

            # Calculate duration string for IBKR API
            duration_days = (end_date - start_date).days
            if duration_days > 365:
                duration = f"{min(2, duration_days // 365)} Y"
            elif duration_days > 30:
                weeks = max(2, int((duration_days + 6) // 7))
                duration = f"{min(52, weeks)} W"
            else:
                duration = f"{min(30, duration_days)} D"

            # Convert timeframe to IBKR format
            ibkr_timeframe = self._convert_timeframe_to_ibkr(timeframe)

            logger.info(f"[BACKTEST] Fetching {symbol} {ibkr_timeframe} bars (duration={duration})")

            # Use ib_insync's util.run to properly handle async requests
            from ib_insync import util

            # Start the event loop temporarily to fetch data
            bars = util.run(
                self.ib.reqHistoricalDataAsync(
                    qualified[0],
                    endDateTime=end_date.strftime("%Y%m%d %H:%M:%S"),
                    durationStr=duration,
                    barSizeSetting=ibkr_timeframe,
                    whatToShow=what,
                    useRTH=False,  # Include extended hours
                    formatDate=1,
                )
            )

            candles = [
                Candle(
                    timestamp=bar.date,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume),
                )
                for bar in bars
            ]

            self._cache[cache_key] = candles
            logger.info(f"[BACKTEST] Fetched {len(candles)} candles for {symbol}")
            return candles

        except Exception as e:
            logger.error(f"[BACKTEST] Error fetching historical data for {symbol}: {e}")
            return []

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        """Get the most recent N candles from the cache (used by strategy engine)."""
        # This is called by the strategy engine during simulation
        # We'll maintain a pointer to the current timestamp and return appropriate slice
        cache_key = f"{symbol}:{timeframe}_current"
        if cache_key not in self._cache:
            return []
        return self._cache[cache_key][-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        """Get market snapshot from cached candles."""
        profile = self.settings.get_active_profile()
        base_seconds = _timeframe_to_seconds(timeframe)
        htf_seconds = _timeframe_to_seconds(profile.htf_timeframe)
        ltf_seconds = _timeframe_to_seconds(profile.ltf_timeframe or timeframe)

        htf_window = profile.trend_window
        ltf_window = profile.ltf_trend_window or htf_window
        required_seconds = max(htf_window * htf_seconds, ltf_window * ltf_seconds)
        base_limit = max(200, math.ceil(required_seconds / base_seconds) + 10)

        candles = self.get_latest_candles(symbol, timeframe, limit=base_limit)

        # Get active profile
        profile = self.settings.get_active_profile()

        # Infer trends from swing structure using resampled HTF/LTF candles.
        htf_candles = (
            _resample_candles(candles, htf_seconds) if htf_seconds != base_seconds else candles
        )
        ltf_candles = (
            _resample_candles(candles, ltf_seconds) if ltf_seconds != base_seconds else candles
        )

        trend_htf = infer_trend_from_swings(
            htf_candles[-htf_window:] if len(htf_candles) >= htf_window else htf_candles,
            swing_lookback=profile.trend_swing_lookback,
            min_swings=profile.trend_min_swings,
            strength_floor=profile.trend_strength_floor,
        )

        trend_ltf = infer_trend_from_swings(
            ltf_candles[-ltf_window:] if len(ltf_candles) >= ltf_window else ltf_candles,
            swing_lookback=profile.trend_swing_lookback,
            min_swings=profile.trend_min_swings,
            strength_floor=profile.trend_strength_floor,
        )

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=htf_candles[-htf_window:] if len(htf_candles) >= htf_window else htf_candles,
            ltf_candles=ltf_candles[-ltf_window:] if len(ltf_candles) >= ltf_window else ltf_candles,
            htf_timeframe=profile.htf_timeframe,
            ltf_timeframe=profile.ltf_timeframe or timeframe,
        )


class Backtester:
    """Historical simulation engine for validating ICC strategy performance."""

    def __init__(self, ib: IB, settings: Settings, ai_client: TradeSciAIClient | None):
        self.ib = ib
        print("ALOHA FROM THE REAL BACKTESTER")
        self.settings = settings
        self.ai_client = ai_client
        self._cache: Dict[str, Any] = {}
        
        # [ANTIGRAVITY FIX] Use CCXT provider for crypto when IB is None
        self._is_crypto_backtest = False
        if ib is None:
            logger.info("[BACKTEST] Using CCXT Provider for Crypto Backtest")
            from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
            self.market_provider = CCXTHistoricalDataProvider(settings)
            self._is_crypto_backtest = True  # Crypto trades 24/7
        else:
            self.market_provider = HistoricalMarketDataProvider(ib, settings)

        # Also check profile crypto_only flag
        profile = settings.get_active_profile()
        if getattr(profile, "crypto_only", False):
            self._is_crypto_backtest = True

    def _is_market_hours_utc(self, ts: datetime) -> bool:
        # [ANTIGRAVITY FIX] Crypto trades 24/7 - skip market hours filter
        if self._is_crypto_backtest:
            return True

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_utc = ts.astimezone(timezone.utc)
        if ts_utc.weekday() >= 5:
            return False
        market_open = dt_time(14, 30)
        market_close = dt_time(21, 0)
        return market_open <= ts_utc.time() < market_close

    def run_backtest(
        self,
        initial_capital: float,
        start_date: datetime,
        end_date: datetime,
        symbols: Optional[List[str]] = None,
        wind_down_days: int = 0,
    ) -> BacktestResult:
        """Run a complete backtest over the specified date range.

        Args:
            initial_capital: Starting capital in dollars
            start_date: Backtest start date (UTC)
            end_date: Backtest end date (UTC) (Last day for NEW ENTRIES)
            symbols: List of symbols to trade (defaults to settings.market.symbols)
            wind_down_days: Days to continue simulation AFTER end_date to manage exits (no new entries)

        Returns:
            BacktestResult containing P&L, trades, and performance metrics
        """
        symbols = symbols or self.settings.market.symbols
        if not symbols:
            raise ValueError("No symbols specified for backtest")

        # [ANTIGRAVITY] Wind-Down Calculation
        simulation_end_date = end_date + timedelta(days=wind_down_days)
        logger.info(
            f"[BACKTEST] Starting backtest: {initial_capital:.2f} capital, "
            f"Entry Phase: {start_date.date()} to {end_date.date()}, "
            f"Wind-Down: {wind_down_days} days (until {simulation_end_date.date()}), "
            f"symbols={symbols}"
        )

        # Get active profile
        profile = self.settings.get_active_profile()

        # Fetch all historical data upfront
        # Need to fetch extra data BEFORE start_date to have enough candles for first decision
        # Strategy needs 200 candles minimum for trend analysis
        timeframe = profile.candle_timeframe
        tf_seconds = _timeframe_to_seconds(timeframe)
        htf_seconds = _timeframe_to_seconds(profile.htf_timeframe)
        ltf_seconds = _timeframe_to_seconds(profile.ltf_timeframe or timeframe)
        htf_window = profile.trend_window
        ltf_window = profile.ltf_trend_window or htf_window
        required_seconds = max(htf_window * htf_seconds, ltf_window * ltf_seconds)
        lookback_candles = max(250, math.ceil(required_seconds / tf_seconds) + 10)
        data_start_date = start_date - timedelta(seconds=tf_seconds * lookback_candles)

        all_candles: Dict[str, List[Candle]] = {}
        for symbol in symbols:
            # [ANTIGRAVITY] Fetch data up to simulation_end_date (includes wind-down)
            candles = self.market_provider.fetch_historical_candles(
                symbol, timeframe, data_start_date, simulation_end_date
            )
            if candles:
                all_candles[symbol] = candles
                logger.info(f"[BACKTEST] {symbol}: {len(candles)} candles from {candles[0].timestamp.date()} to {candles[-1].timestamp.date()}")

        if not all_candles:
            raise ValueError("No historical data available for any symbol")

        # Initialize simulation state
        capital = initial_capital
        positions: Dict[str, SimulatedPosition] = {}
        completed_trades: List[SimulatedTrade] = []
        equity_curve: List[tuple[datetime, float]] = [(start_date, capital)]
        
        # [ANTIGRAVITY] Memory-based trade results for strategy awareness
        trade_results_store = TradeResultStore(path="/tmp/backtest_results.json")
        trade_results_store.results = [] # Start fresh

        # Validate timeframe conversion
        if tf_seconds == 0:
            raise ValueError(f"Invalid timeframe conversion: '{timeframe}' -> 0 seconds")

        logger.info(f"[BACKTEST] Timeframe: {timeframe} = {tf_seconds} seconds")

        # Simulate bar-by-bar
        current_time = start_date
        processed_bar_index = 0
        total_decision_checks = 0
        total_ai_calls = 0
        auto_flatten_on_close = bool(getattr(profile, "auto_flatten_on_close", False))
        min_hold_seconds = max(0.0, float(getattr(profile, "min_hold_hours", 0.0)) * 3600.0)
        disable_stops = bool(getattr(profile, "backtest_disable_stops", False))
        profit_exit_after_hold = bool(getattr(profile, "profit_exit_after_hold", False))
        allow_loss_exit_after_hold = bool(getattr(profile, "allow_loss_exit_after_hold", False))
        max_hold_seconds = max(0.0, float(getattr(profile, "max_hold_hours", 0.0)) * 3600.0)
        last_flatten_date = None
        eastern_tz = ZoneInfo("America/New_York")
        signal_samples: list[dict[str, Any]] = []
        potential_trades_blocked = 0
        potential_trade_block_reasons: Dict[str, int] = defaultdict(int)

        logger.info(f"[BACKTEST] Starting simulation loop: {start_date} to {simulation_end_date}")

        while current_time <= simulation_end_date:
            # [ANTIGRAVITY] Wind-Down Logic: Stop loop early if past end_date AND no positions
            is_wind_down = current_time > end_date
            if is_wind_down and not positions:
                logger.info("[BACKTEST] Wind-down complete: No open positions. Terminating simulation.")
                break

            if not self._is_market_hours_utc(current_time):
                current_time += timedelta(seconds=tf_seconds)
                continue

            # [ANTIGRAVITY] Expose current capital to strategy/engine
            self.market_provider.current_capital = capital
            
            # Update current candles for each symbol
            for symbol, candles in all_candles.items():
                # Find candles up to current_time
                current_candles = [
                    c
                    for c in candles
                    if c.timestamp <= current_time and self._is_market_hours_utc(c.timestamp)
                ]
                cache_key = f"{symbol}:{timeframe}_current"
                self.market_provider._cache[cache_key] = current_candles

                # DEBUG: Log candle availability for first few bars
                if processed_bar_index < 3:
                    logger.info(
                        f"[BACKTEST] Bar {processed_bar_index}: {symbol} has {len(current_candles)} candles "
                        f"up to {current_time.strftime('%Y-%m-%d %H:%M')}"
                    )

            # Check stop/target hits for open positions
            for symbol, pos in list(positions.items()):
                if symbol not in all_candles:
                    continue
                current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
                if not current_candles:
                    continue

                current_bar = current_candles[-1]
                held_seconds = (current_time - pos.entry_time).total_seconds()

                if max_hold_seconds > 0 and held_seconds >= max_hold_seconds:
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl,
                        exit_reason="max_hold",
                        entry_gates=getattr(pos, "entry_gates", None),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital
                    ))
                    del positions[symbol]
                    logger.info(f"[BACKTEST] {symbol} max-hold exit: PnL=${pnl:.2f}")
                    continue

                if (
                    profit_exit_after_hold
                    and min_hold_seconds > 0
                    and held_seconds >= min_hold_seconds
                ):
                    mark_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, mark_price, pos.size, pos.direction)
                    if pnl > 0:
                        capital += pnl
                        completed_trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=mark_price,
                            size=pos.size,
                            entry_time=pos.entry_time,
                            exit_time=current_time,
                            pnl=pnl,
                            exit_reason="profit_hold",
                        entry_gates=getattr(pos, "entry_gates", None),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            is_win=pnl > 0,
                            tier="backtest",
                            capital_at_close=capital
                        ))
                        del positions[symbol]
                        logger.info(f"[BACKTEST] {symbol} profit-hold exit: PnL=${pnl:.2f}")
                        continue

                # Check stop loss
                if pos.stop_price is not None and not disable_stops:
                    if min_hold_seconds > 0 and held_seconds < min_hold_seconds:
                        continue
                    # Long: stop hit when price drops to/below stop
                    # Short: stop hit when price rises to/above stop
                    stop_hit = (
                        (pos.direction == "long" and current_bar.low <= pos.stop_price) or
                        (pos.direction == "short" and current_bar.high >= pos.stop_price)
                    )
                    if stop_hit:
                        exit_price = pos.stop_price
                        pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                        capital += pnl
                        completed_trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            size=pos.size,
                            entry_time=pos.entry_time,
                            exit_time=current_time,
                            pnl=pnl,
                            exit_reason="stop",
                        entry_gates=getattr(pos, "entry_gates", None),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            is_win=pnl > 0,
                            tier="backtest",
                            capital_at_close=capital
                        ))
                        del positions[symbol]
                        logger.info(f"[BACKTEST] {symbol} stop hit: PnL=${pnl:.2f}")
                        continue

                # Check take profit
                if pos.target_price is not None:
                    # Long: target hit when price rises to/above target
                    # Short: target hit when price drops to/below target
                    target_hit = (
                        (pos.direction == "long" and current_bar.high >= pos.target_price) or
                        (pos.direction == "short" and current_bar.low <= pos.target_price)
                    )
                    if target_hit:
                        if min_hold_seconds > 0 and held_seconds < min_hold_seconds:
                            continue
                        exit_price = pos.target_price
                        pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                        if pnl <= 0:
                            logger.info(f"[BACKTEST] {symbol} target hit but not profitable; holding.")
                            continue
                        capital += pnl
                        completed_trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            size=pos.size,
                            entry_time=pos.entry_time,
                            exit_time=current_time,
                            pnl=pnl,
                            exit_reason="target",
                        entry_gates=getattr(pos, "entry_gates", None),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            is_win=pnl > 0,
                            tier="backtest",
                            capital_at_close=capital
                        ))
                        del positions[symbol]
                        logger.info(f"[BACKTEST] {symbol} target hit: PnL=${pnl:.2f}")
                        continue

                # Update unrealized P&L
                positions[symbol].unrealized_pnl = _calculate_pnl(pos.entry_price, current_bar.close, pos.size, pos.direction)
                
                # [SOLUTION 2] Hard Max Loss Cap - Exit if loss exceeds configured maximum
                max_loss_dollars = getattr(profile, 'max_loss_per_trade_dollars', None)
                if max_loss_dollars and positions[symbol].unrealized_pnl < -abs(max_loss_dollars):
                    logger.warning(
                        f"[MAX LOSS CAP] {symbol} hit max loss cap: "
                        f"${positions[symbol].unrealized_pnl:.2f} < -${max_loss_dollars:.2f}"
                    )
                    # Execute immediate exit
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl,
                        exit_reason="max_loss_cap",
                        entry_gates=getattr(pos, "entry_gates", None),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital
                    ))
                    del positions[symbol]
                    logger.info(f"[BACKTEST] {symbol} max loss cap exit: Net PnL=${pnl:.2f}")
                    continue

                # Update HTF neutral bar counter
                # This tracks how long HTF has been neutral to trigger timeout exits
                snapshot = self.market_provider.get_latest_snapshot(symbol, timeframe)
                if snapshot and snapshot.trend_htf:
                    from tradebot_sci.market.trend_enums import TrendDirection
                    if snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
                        positions[symbol].htf_neutral_bars += 1
                    else:
                        # Reset counter when HTF becomes trending again
                        positions[symbol].htf_neutral_bars = 0
                htf_neutral_exit_bars = int(getattr(profile, "htf_neutral_exit_bars", 0) or 0)
                if (
                    htf_neutral_exit_bars > 0
                    and positions[symbol].htf_neutral_bars >= htf_neutral_exit_bars
                    and (min_hold_seconds <= 0 or held_seconds >= min_hold_seconds)
                ):
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl,
                        exit_reason="htf_neutral_timeout",
                        entry_gates=getattr(pos, "entry_gates", None),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital
                    ))
                    del positions[symbol]
                    logger.info(f"[BACKTEST] {symbol} HTF neutral timeout exit: PnL=${pnl:.2f}")
                    continue

            # End-of-day flatten (16:00 America/New_York) if enabled
            if auto_flatten_on_close and positions:
                sample_symbol = next(iter(all_candles.keys()), None)
                sample_candles = (
                    self.market_provider._cache.get(f"{sample_symbol}:{timeframe}_current", [])
                    if sample_symbol
                    else []
                )
                if sample_candles:
                    bar_time = sample_candles[-1].timestamp
                    if bar_time.tzinfo is None:
                        bar_time = bar_time.replace(tzinfo=timezone.utc)
                    eastern_time = bar_time.astimezone(eastern_tz)
                    if eastern_time.hour >= 16 and last_flatten_date != eastern_time.date():
                        for symbol, pos in list(positions.items()):
                            current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
                            if not current_candles:
                                continue
                            exit_price = current_candles[-1].close
                            pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                            capital += pnl
                            completed_trades.append(SimulatedTrade(
                                symbol=symbol,
                                direction=pos.direction,
                                entry_price=pos.entry_price,
                                exit_price=exit_price,
                                size=pos.size,
                                entry_time=pos.entry_time,
                                exit_time=current_time,
                                pnl=pnl,
                                exit_reason="eod",
                        entry_gates=getattr(pos, "entry_gates", None),
                            ))
                            trade_results_store.add_result(TradeResult(
                                symbol=symbol,
                                closed_at=current_time.isoformat(),
                                pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                                is_win=pnl > 0,
                                tier="backtest",
                                capital_at_close=capital
                            ))
                            del positions[symbol]
                            logger.info(f"[BACKTEST] {symbol} EOD flatten: PnL=${pnl:.2f}")
                        last_flatten_date = eastern_time.date()

            # Generate trading signals every decision interval
            # If decision interval is less than timeframe, check every bar
            decision_bar_interval = max(1, profile.ai_decision_interval_seconds // tf_seconds)
            if processed_bar_index % decision_bar_interval == 0:
                total_decision_checks += 1

                # DEBUG: Log decision check details
                if total_decision_checks <= 3:
                    logger.info(
                        f"[BACKTEST] Decision check #{total_decision_checks} at bar {processed_bar_index} "
                        f"({current_time.strftime('%Y-%m-%d %H:%M')}), "
                        f"capital=${capital:.2f}, positions={list(positions.keys())}"
                    )

                # [FIX] Stop trading if capital is depleted (account blown)
                if capital <= 0:
                    if not positions:  # No open positions to manage
                        logger.warning(f"[BACKTEST] Account depleted (capital=${capital:.2f}). Stopping backtest.")
                        break
                    # If we have positions, still need to process exits below

                for symbol in all_candles.keys():
                    # Always evaluate strategy, even when in position
                    # This allows for position management, exits, and multi-entry strategies

                    # [FIXED] Use current running capital for risk sizing
                    current_position = positions.get(symbol)
                    
                    # 1.5 Calculate Global Risk across all symbols
                    total_open_risk_dollars = 0.0
                    for s_name, s_pos in positions.items():
                        s_risk_per_share = abs(s_pos.entry_price - s_pos.stop_price)
                        total_open_risk_dollars += (s_risk_per_share * s_pos.size)
                    
                    global_risk_pct = total_open_risk_dollars / capital if capital > 0 else 0

                    # Check if we have enough capital for NEW entries
                    # Skip capital check if we already have a position (for exit/management signals)
                    if current_position is None:
                        # [ANTIGRAVITY] Wind-Down Block: No new entries after end_date
                        if current_time > end_date:
                            if total_decision_checks % 100 == 0: # Reduce log spam
                                logger.debug(f"[BACKTEST] {symbol}: Skipping entry (Wind-Down active)")
                            continue

                        # [FIX] Don't enter new trades with depleted capital
                        if capital <= 0:
                            continue

                        if min_hold_seconds > 0:
                            remaining_seconds = (end_date - current_time).total_seconds()
                            if remaining_seconds < min_hold_seconds:
                                if total_decision_checks <= 3:
                                    logger.info(
                                        f"[BACKTEST] {symbol}: Skipping entry (insufficient time for min hold)"
                                    )
                                continue
                        # Default risk to 0.0 - variant must specify or we use profile
                        risk_pct = 0.0
                        max_risk = capital * 1.0 # Buffer

                        # [REMOVED] Need at least $1 risk per trade
                        # Allows for Feet Wet scouts (0.25%) on small accounts ($100)
                        # if max_risk < 1.0:  
                        #     if total_decision_checks <= 3:
                        #         logger.info(f"[BACKTEST] {symbol}: Insufficient capital (max_risk=${max_risk:.2f} < $1)")
                        #     continue

                    try:
                        # Get strategy decision
                        engine = StrategyEngine(
                            ai_client=self.ai_client,
                            market_provider=self.market_provider,
                            profile=profile,
                            symbol=symbol,
                            trade_results=trade_results_store
                        )

                        snapshot = self.market_provider.get_latest_snapshot(symbol, timeframe)

                        # Convert SimulatedPosition to a format the engine expects (if we have one)
                        open_position = None
                        if current_position is not None:
                            # Create a minimal position dict for the engine
                            open_position = {
                                'symbol': current_position.symbol,
                                'direction': current_position.direction,
                                'entry_price': current_position.entry_price,
                                'size': current_position.size,
                                'stop_price': current_position.stop_price,
                                'target_price': current_position.target_price,
                                'pyramid_count': current_position.pyramid_count,
                                'htf_neutral_bars': current_position.htf_neutral_bars,
                            }

                        decision = engine.decide(
                            timeframe=timeframe,
                            open_position=open_position,
                            snapshot=snapshot,
                            current_bar_time=current_time,
                        )

                        # Increment AI call counter AFTER successful decision
                        total_ai_calls += 1
                        if total_ai_calls <= 10:  # Log first 10 AI calls
                            logger.info(f"[BACKTEST] AI call #{total_ai_calls}: {symbol} at {current_time.strftime('%Y-%m-%d %H:%M')}")

                        # Log ALL decisions for debugging
                        logger.info(
                            f"[BACKTEST] {current_time.strftime('%Y-%m-%d %H:%M')} {symbol}: "
                            f"action={decision.action}, urgency={decision.urgency}, "
                            f"notes={decision.notes[:100] if decision.notes else 'N/A'}"
                        )

                        gates = getattr(decision, "gates", None)
                        if gates and gates.get("continuation") and gates.get("continuation_dir"):
                            signal_samples.append(
                                {
                                    "symbol": symbol,
                                    "time": current_time,
                                    "direction": gates.get("continuation_dir"),
                                    "close": snapshot.candles[-1].close,
                                    "sweep": bool(gates.get("sweep")),
                                    "htf_align": bool(gates.get("htf_align")),
                                    "htf_strength": gates.get("htf_strength"),
                                    "phase": gates.get("phase"),
                                    "stack_label": gates.get("stack_label"),
                                    "score": gates.get("score"),
                                }
                            )

                        # Handle exit signals if we have an open position
                        if current_position is not None and decision.action in ("exit", "close_position"):
                            held_seconds = (current_time - current_position.entry_time).total_seconds()
                            if min_hold_seconds > 0 and held_seconds < min_hold_seconds:
                                continue
                            exit_price = snapshot.candles[-1].close
                            pnl = _calculate_pnl(current_position.entry_price, exit_price, current_position.size, current_position.direction)
                            if pnl <= 0 and not allow_loss_exit_after_hold:
                                logger.info(f"[BACKTEST] {symbol} exit signal ignored (not profitable).")
                                continue
                            if pnl <= 0 and allow_loss_exit_after_hold:
                                logger.info(f"[BACKTEST] {symbol} exit signal accepted after hold (loss allowed).")
                            capital += pnl
                            completed_trades.append(SimulatedTrade(
                                symbol=symbol,
                                direction=current_position.direction,
                                entry_price=current_position.entry_price,
                                exit_price=exit_price,
                                size=current_position.size,
                                entry_time=current_position.entry_time,
                                exit_time=current_time,
                                pnl=pnl,
                                exit_reason="signal",
                        entry_gates=getattr(pos, "entry_gates", None),
                            ))
                            del positions[symbol]
                            logger.info(f"[BACKTEST] {symbol} EXIT signal: PnL=${pnl:.2f}")
                            continue  # Skip to next symbol after exit

                        # Handle pyramid/add to position
                        if current_position is not None and decision.action in ("add_to_position", "scale_in"):
                            add_price = snapshot.candles[-1].close

                            # Calculate size for pyramid entry (same risk % as initial entry)
                            stop_price = decision.stop_loss or current_position.stop_price
                            risk_per_share = abs(add_price - stop_price)

                            # Use profile risk setting (same as initial entry)
                            if hasattr(decision, "risk_per_trade_pct") and decision.risk_per_trade_pct:
                                target_risk_pct = float(decision.risk_per_trade_pct)
                                risk_pct = target_risk_pct
                            else:
                                risk_pct = float(getattr(profile, "risk_per_trade_pct", 0.10))

                            # Use profile max loss cap, or broker setting, with sensible fallback
                            max_loss_cap = float(getattr(profile, "max_loss_per_trade_dollars", 0.0))
                            if max_loss_cap <= 0:
                                max_loss_cap = self.settings.broker.max_dollar_risk_per_symbol if self.settings.broker else 1000000.0
                            # [RISK SATURATION] Cap pyramid sizing at $750 base
                            compounding_capital = min(capital, 750.0)
                            max_risk = min(compounding_capital * risk_pct, max_loss_cap)

                            raw_add_size = max_risk / risk_per_share if risk_per_share > 0 else 0.0
                            add_size = raw_add_size
                            cap_reason = None

                            # Cap pyramid entry notional (Config 13: 100x)
                            # Default to 100x (Allow Profit Scaling)
                            lev_cap = float(os.getenv('RR_LEV_CAP', '100.0'))
                            max_add_notional = capital * lev_cap
                            max_add_shares = max_add_notional / add_price
                            
                            # Safety calculation matching initial entry for consistency
                            min_stop_distance = add_price * 0.001
                            if risk_per_share < min_stop_distance:
                                risk_per_share = min_stop_distance

                            if add_size > max_add_shares:
                                logger.warning(
                                    f"[BACKTEST] {symbol}: Pyramid size capped from {add_size:.2f} to {max_add_shares:.2f} shares "
                                    f"(max {lev_cap:.0f}× leverage = ${max_add_notional:.2f} notional on ${capital:.2f} capital)"
                                )
                                add_size = max_add_shares
                                cap_reason = "pyramid_max_leverage"

                            # [REMOVED] Cap total position at 3x initial size (Allows Scout -> Hammer scaling)
                            # max_total_size = current_position.size * 3
                            # if current_position.size + add_size > max_total_size:
                            #     add_size = max_total_size - current_position.size
                            #     cap_reason = "pyramid_max_total_size"

                            if add_size > 0:
                                # Update position with pyramid entry
                                current_position.size += add_size
                                current_position.total_cost += add_price * add_size
                                current_position.entry_price = current_position.total_cost / current_position.size  # Average price
                                current_position.pyramid_count += 1

                                # Update stop if provided
                                if decision.stop_loss is not None:
                                    current_position.stop_price = decision.stop_loss

                                logger.info(
                                    f"[BACKTEST] {symbol} PYRAMID #{current_position.pyramid_count}: "
                                    f"added {add_size:.2f} shares @ ${add_price:.2f}, "
                                    f"total={current_position.size:.2f}, avg=${current_position.entry_price:.2f}"
                                )
                            else:
                                if risk_per_share <= 0:
                                    reason = "pyramid_invalid_risk"
                                elif max_risk < 10.0:
                                    reason = "pyramid_risk_too_small"
                                elif cap_reason:
                                    reason = cap_reason
                                else:
                                    reason = "pyramid_blocked"
                                potential_trades_blocked += 1
                                potential_trade_block_reasons[reason] += 1
                                logger.info(
                                    f"[BACKTEST] {symbol} PYRAMID blocked ({reason}): "
                                    f"risk_per_share={risk_per_share:.4f}, max_risk=${max_risk:.2f}, "
                                    f"requested={raw_add_size:.2f}, allowed={add_size:.2f}"
                                )
                            continue  # Skip to next symbol after pyramid

                        # Handle position management (stop/target updates)
                        if current_position is not None and decision.action in ("hold", "scale_in", "scale_out"):
                            # Update stop/target if strategy provides new ones
                            if decision.stop_loss is not None and decision.stop_loss != current_position.stop_price:
                                old_stop = current_position.stop_price
                                current_position.stop_price = decision.stop_loss
                                logger.info(
                                    f"[BACKTEST] {symbol} stop updated: ${old_stop:.2f} -> ${decision.stop_loss:.2f}"
                                )
                            if decision.take_profit is not None and decision.take_profit != current_position.target_price:
                                old_target = current_position.target_price
                                current_position.target_price = decision.take_profit
                                logger.info(
                                    f"[BACKTEST] {symbol} target updated: ${old_target:.2f} -> ${decision.take_profit:.2f}"
                                )
                            # Continue to next symbol (don't attempt new entry)
                            continue

                        if current_position is not None and decision.action in ("enter_long", "enter_short"):
                            potential_trades_blocked += 1
                            potential_trade_block_reasons["already_in_position"] += 1
                            logger.info(
                                f"[BACKTEST] {symbol} potential entry blocked (already holding position)."
                            )
                            continue

                        # Execute entry if signal is valid (no confidence check - AI decides via action field)
                        # Only allow new entries if we don't already have a position
                        if current_position is None and decision.action in ("enter_long", "enter_short"):
                            # ENSURE Strategy-defined risk is used (Scout=0.25%, Hammer=60%)
                            if hasattr(decision, "risk_per_trade_pct") and decision.risk_per_trade_pct is not None:
                                risk_pct = float(decision.risk_per_trade_pct)
                            else:
                                # Fallback to Profile if variant forgot to specify
                                risk_pct = float(getattr(profile, "risk_per_trade_pct", 0.10))
                                
                            # [RISK SATURATION] Cap compounding at $750 to prevent Nuclear Blowout
                            compounding_capital = min(capital, 750.0)
                            max_risk = compounding_capital * risk_pct
                            logger.info(f"[BACKTEST] Entry: {symbol} using {risk_pct*100:.2f}% risk on ${compounding_capital:.2f} base (${max_risk:.2f})")

                            entry_price = snapshot.candles[-1].close

                            # Calculate position size with safety measures
                            stop_price = decision.stop_loss or (entry_price * 0.98 if decision.action == "enter_long" else entry_price * 1.02)
                            risk_per_share = abs(entry_price - stop_price)

                            # Safety 1: Enforce minimum stop distance (0.1% of entry - allows heavy scalping leverage)
                            min_stop_distance = entry_price * 0.001
                            if risk_per_share < min_stop_distance:
                                logger.warning(
                                    f"[BACKTEST] {symbol}: Stop too tight (${risk_per_share:.4f} < ${min_stop_distance:.4f}), "
                                    f"widening to minimum"
                                )
                                risk_per_share = min_stop_distance
                                # Adjust stop price to match minimum distance
                                if decision.action == "enter_long":
                                    stop_price = entry_price - min_stop_distance
                                else:
                                    stop_price = entry_price + min_stop_distance

                            # Calculate position size based on risk
                            # ICC methodology: size = risk_amount / stop_distance
                            # With tight stops (0.5%), this creates leverage which is intentional
                            # Example: $100 risk / $3 stop = 33 shares = $20k notional (20× leverage)
                            size = max_risk / risk_per_share if risk_per_share > 0 else 0

                            # Safety 2: Cap total notional (Config 13: 100x)
                            lev_cap = float(os.getenv('RR_LEV_CAP', '100.0'))
                            max_position_value = capital * lev_cap
                            max_shares = max_position_value / entry_price
                            if size > max_shares:
                                logger.warning(
                                    f"[BACKTEST] {symbol}: Position size capped from {size:.2f} to {max_shares:.2f} shares "
                                    f"(max 30× leverage = ${max_position_value:.2f} notional on ${capital:.2f} capital)"
                                )
                                size = max_shares

                            if size > 0:
                                positions[symbol] = SimulatedPosition(
                                    symbol=symbol,
                                    direction="long" if decision.action == "enter_long" else "short",
                                    entry_price=entry_price,
                                    size=size,
                                    entry_time=current_time,
                                    stop_price=stop_price,
                                    target_price=decision.take_profit,
                                    pyramid_count=1,
                                    total_cost=entry_price * size,
                                    htf_neutral_bars=0,
                                    entry_gates=getattr(decision, 'gates', None),  # Capture score breakdown
                                )
                                logger.info(
                                    f"[BACKTEST] {symbol} ENTRY {decision.action.upper()} @ ${entry_price:.2f}, "
                                    f"size={size:.2f}, stop=${stop_price:.2f}"
                                )

                    except Exception as e:
                        logger.error(
                            f"[BACKTEST] Error generating decision for {symbol} at {current_time.strftime('%Y-%m-%d %H:%M')}: {e}",
                            exc_info=True
                        )

            # Record equity curve
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions.values())
            total_equity = capital + unrealized_pnl
            equity_curve.append((current_time, total_equity))

            # Advance time
            current_time += timedelta(seconds=tf_seconds)
            processed_bar_index += 1

        # Close any remaining positions at end
        for symbol, pos in positions.items():
            current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
            if current_candles:
                exit_price = current_candles[-1].close
                pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction)
                capital += pnl
                completed_trades.append(SimulatedTrade(
                    symbol=symbol,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    size=pos.size,
                    entry_time=pos.entry_time,
                    exit_time=end_date,
                    pnl=pnl,
                    exit_reason="eod",
                        entry_gates=getattr(pos, "entry_gates", None),
                ))

        # Calculate performance metrics
        total_pnl = capital - initial_capital
        total_return_pct = (total_pnl / initial_capital) * 100

        # Calculate weekly equity snapshots
        weekly_equity: Dict[str, float] = {}
        for ts, equity in equity_curve:
            week_key = ts.strftime("%Y-W%W")
            weekly_equity[week_key] = equity  # Keep latest equity for each week

        # Calculate max drawdown
        peak = initial_capital
        max_dd = 0.0
        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Calculate win rate and avg win/loss
        wins = [t for t in completed_trades if t.pnl > 0]
        losses = [t for t in completed_trades if t.pnl < 0]
        win_rate = (len(wins) / len(completed_trades) * 100) if completed_trades else 0
        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0
        avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0

        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=capital,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            trades=completed_trades,
            weekly_equity=weekly_equity,
            max_drawdown_pct=max_dd,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            potential_trades_blocked=potential_trades_blocked,
            potential_trade_block_reasons=dict(potential_trade_block_reasons),
        )

        logger.info(
            f"[BACKTEST] Complete: {len(completed_trades)} trades, "
            f"PnL=${total_pnl:.2f} ({total_return_pct:.2f}%), "
            f"Win Rate={win_rate:.1f}%, Max DD={max_dd:.1f}%"
        )
        if potential_trades_blocked:
            logger.info(
                f"[BACKTEST] Potential trades blocked: {potential_trades_blocked} "
                f"({dict(potential_trade_block_reasons)})"
            )
        logger.info(
            f"[BACKTEST] Stats: {total_decision_checks} decision checks, "
            f"{total_ai_calls} AI calls made"
        )

        if signal_samples and min_hold_seconds > 0:
            logger.info(
                "[BACKTEST] Signal analysis (continuation-based, %dh hold):",
                int(min_hold_seconds / 3600),
            )
            for line in self._summarize_signal_samples(signal_samples, all_candles, min_hold_seconds):
                logger.info(line)

        return result

    def _summarize_signal_samples(
        self,
        samples: list[dict[str, Any]],
        all_candles: Dict[str, List[Candle]],
        hold_seconds: float,
    ) -> list[str]:
        def _exit_close(symbol: str, target_time: datetime) -> Optional[float]:
            candles = all_candles.get(symbol, [])
            for candle in candles:
                if candle.timestamp >= target_time:
                    return candle.close
            return None

        def _win(sample: dict[str, Any], exit_close: float) -> bool:
            entry_close = float(sample["close"])
            if sample["direction"] == "short":
                return exit_close < entry_close
            return exit_close > entry_close

        buckets: dict[str, list[bool]] = defaultdict(list)
        total = 0
        wins = 0
        for sample in samples:
            target_time = sample["time"] + timedelta(seconds=hold_seconds)
            exit_close = _exit_close(sample["symbol"], target_time)
            if exit_close is None:
                continue
            total += 1
            did_win = _win(sample, exit_close)
            wins += 1 if did_win else 0
            buckets[f"sweep={sample['sweep']}"].append(did_win)
            buckets[f"htf_align={sample['htf_align']}"].append(did_win)
            phase = sample.get("phase") or "unknown"
            stack_label = sample.get("stack_label") or "unknown"
            buckets[f"sweep={sample['sweep']} phase={phase}"].append(did_win)
            htf_strength = sample.get("htf_strength")
            if isinstance(htf_strength, (int, float)):
                htf_bucket = htf_strength >= 0.7
                buckets[f"htf_strength>=0.7={htf_bucket}"].append(did_win)
                buckets[f"htf_strength>=0.7={htf_bucket} phase={phase}"].append(did_win)
            buckets[f"phase={phase}"].append(did_win)
            buckets[f"stack={stack_label}"].append(did_win)

        if total == 0:
            return ["[BACKTEST] Signal analysis: no eligible signals with future candles."]
        lines = [f"[BACKTEST] Signal analysis: {wins}/{total} wins ({wins / total:.1%})"]
        for key, values in sorted(buckets.items()):
            if not values:
                continue
            win_count = sum(1 for v in values if v)
            win_rate = win_count / len(values)
            lines.append(f"[BACKTEST]   {key}: {win_count}/{len(values)} ({win_rate:.1%})")
        return lines

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """Convert timeframe string like '5m', '1h' to seconds."""
        if not timeframe:
            return 300  # Default 5 minutes

        timeframe_lower = timeframe.lower().strip()

        if timeframe_lower.endswith("m"):
            try:
                return int(timeframe_lower[:-1]) * 60
            except ValueError:
                return 300
        elif timeframe_lower.endswith("h"):
            try:
                return int(timeframe_lower[:-1]) * 3600
            except ValueError:
                return 3600
        elif timeframe_lower.endswith("d"):
            try:
                return int(timeframe_lower[:-1]) * 86400
            except ValueError:
                return 86400
        else:
            # Try to parse as minutes if it's just a number
            try:
                return int(timeframe_lower) * 60
            except ValueError:
                return 300  # Default 5 minutes
