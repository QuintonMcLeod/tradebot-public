"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CORE BACKTESTING ENGINE — SINGLE SOURCE OF TRUTH              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Historical simulation engine for backtesting trading strategies.

This module provides the ONLY backtesting framework for the project. It replays
historical market data through the bot's actual StrategyEngine to validate
performance without risking real capital. It handles: candle fetching (IBKR or
local JSON), trade execution simulation, stop/target logic, PnL tracking, and
performance metrics.

HOW TO USE:
    → Run via: python3 tools/mega_backtester.py <cartridge>
    → Create test configs as cartridges in tools/cartridges/
    → mega_backtester.py instantiates THIS engine with cartridge settings

╔══════════════════════════════════════════════════════════════════════════════╗
║  ⛔  ANTI-DUPLICATION RULES  ⛔                                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  This is the ONLY simulation engine. DO NOT:                               ║
║                                                                            ║
║  ✗ Create standalone scripts with their own PnL calculation                ║
║  ✗ Build separate "quick backtest" scripts with custom exit logic          ║
║  ✗ Write one-off scripts that bypass this engine                           ║
║  ✗ Add pyramiding/exits in a script that don't exist HERE                  ║
║                                                                            ║
║  If this engine is missing a feature you need (pyramiding, custom          ║
║  exits, structure-based stops), ADD IT HERE so ALL tests benefit.          ║
║                                                                            ║
║  HISTORY: 25+ standalone scripts were deleted because each had its        ║
║  own simulation logic. One showed +215% returns using features             ║
║  (SINGULARITY pyramiding, stagnation kills) that weren't in the            ║
║  production bot. This created false confidence and masked the              ║
║  bot's true performance. Never again.                                      ║
║                                                                            ║
║  AI ASSISTANTS: If asked to "run a quick backtest" or "write a test        ║
║  script", create a CARTRIDGE in tools/cartridges/ and use                  ║
║  mega_backtester.py. Do NOT create a new standalone script.                ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
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

try:
    from ib_insync import IB, util
    IB_AVAILABLE = True
except ImportError:
    IB = Any
    util = Any
    IB_AVAILABLE = False

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionOutcomeType
from tradebot_sci.broker.trade_result_store import TradeResult, TradeResultStore
from tradebot_sci.config.models import Settings
from tradebot_sci.market.contracts import build_contract
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.ai.client import TradeSciAIClient

logger = logging.getLogger(__name__)


def _jpy_adjust_risk(risk_per_share: float, symbol: str, price: float) -> float:
    """Convert JPY-denominated stop distance to USD per-unit.
    For JPY-quoted pairs (USDJPY, EURJPY), stop_dist is in JPY but risk is in USD.
    Divide by price to get USD per-unit risk."""
    sym = symbol.upper().replace("_", "")
    if "JPY" in sym and price > 0:
        return risk_per_share / price
    return risk_per_share


def _notional_per_unit(symbol: str, price: float) -> float:
    """Get USD notional value per unit for leverage cap calculations.
    For USD-base pairs (USDJPY, USDCHF), 1 unit = $1.
    For other pairs (EURUSD, GBPUSD), 1 unit = price in USD."""
    sym = symbol.upper().replace("_", "")
    if sym.startswith("USD"):
        return 1.0
    return price if price > 0 else 1.0


def _calculate_pnl(entry_price: float, exit_price: float, size: float, direction: str,
                   symbol: str = "") -> float:
    """Calculate PnL correctly for both long and short positions, MINUS fees.

    Long: profit when price goes UP   -> (exit - entry) * size - fees
    Short: profit when price goes DOWN -> (entry - exit) * size - fees
    
    For JPY-quoted pairs, the raw PnL is in JPY and must be converted to USD.
    
    Fees are deducted as round-trip spread/commission costs based on the
    symbol's asset class. This ensures backtests reflect real trading costs.
    """
    if direction == "short":
        raw_pnl = (entry_price - exit_price) * size
    else:  # long
        raw_pnl = (exit_price - entry_price) * size
    
    # JPY conversion: raw_pnl is in JPY for JPY-quoted pairs
    sym = symbol.upper().replace("_", "")
    if "JPY" in sym and exit_price > 0:
        raw_pnl = raw_pnl / exit_price
    
    # Deduct round-trip fees (spread + commission)
    if symbol:
        from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
        fee_pct = get_fee_for_symbol(symbol)
        notional = entry_price * abs(size)
        # For JPY pairs, notional per unit is $1 if USD-base, else price-converted
        if "JPY" in sym:
            if sym.startswith("USD"):
                notional = abs(size)  # 1 unit = $1
            else:
                notional = abs(size) * entry_price / entry_price  # cross-rate; approximate
        fee_cost = notional * fee_pct
        return raw_pnl - fee_cost
    return raw_pnl


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
    strategy_name: str = "unknown"  # Strategy that opened this trade
    cumulative_partial_pnl: float = 0.0  # Running total of partial close PnLs
    stop_was_trailed: bool = False  # True once stop moves from initial position (SAR gate)
    original_entry_price: Optional[float] = None
    initial_risk: Optional[float] = None

    def __post_init__(self):
        # Auto-resolve strategy_name from entry_gates if still defaulted
        if self.strategy_name == "unknown" and self.entry_gates:
            meta_src = self.entry_gates.get("meta_source")
            if meta_src:
                self.strategy_name = meta_src



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
    strategy_name: str = "unknown"  # Which strategy managed this trade

    def __post_init__(self):
        if self.strategy_name == "unknown" and self.entry_gates:
            meta_src = self.entry_gates.get("meta_source")
            if meta_src:
                self.strategy_name = meta_src


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

    def __init__(self, ib: IB | None, settings: Settings):
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
        file_path: str | None = None,
    ) -> List[Candle]:
        """Fetch historical candles from IBKR or local file for the specified date range."""
        cache_key = f"{symbol}:{timeframe}:{start_date.isoformat()}:{end_date.isoformat()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Local File Loading Support
        if file_path and os.path.exists(file_path):
            logger.info(f"[BACKTEST] Loading candles for {symbol} from local file: {file_path}")
            try:
                import json
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    candles = []
                    for c in raw_data:
                        # Handle multiple timestamp formats
                        ts_str = c["timestamp"]
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except ValueError:
                            # Try other common formats if needed
                            ts = datetime.fromisoformat(ts_str)
                            
                        if start_date <= ts <= end_date:
                            candles.append(Candle(
                                timestamp=ts,
                                open=float(c["open"]),
                                high=float(c["high"]),
                                low=float(c["low"]),
                                close=float(c["close"]),
                                volume=float(c.get("volume", 0.0)),
                            ))
                    
                    self._cache[cache_key] = candles
                    logger.info(f"[BACKTEST] Loaded {len(candles)} candles from file.")
                    return candles
            except Exception as e:
                logger.error(f"[BACKTEST] Failed to load candles from file {file_path}: {e}")
                return []

        if self.ib is None:
            logger.error(f"[BACKTEST] No IB connection and no file_path provided for {symbol}")
            return []

        try:
            if not IB_AVAILABLE:
                logger.error("[BACKTEST] ib_insync not installed. Cannot use IB provider.")
                return []
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

        # Indicators need MORE candles than the trend_window:
        # EMA55 needs 55, MACD needs 35, Bollinger needs 20.
        # Pass at least 60 candles so all indicator voters have enough data.
        INDICATOR_MIN_CANDLES = 60
        htf_indicator_window = max(htf_window, INDICATOR_MIN_CANDLES)
        ltf_indicator_window = max(ltf_window, INDICATOR_MIN_CANDLES)

        required_seconds = max(htf_indicator_window * htf_seconds, ltf_indicator_window * ltf_seconds)
        base_limit = max(200, math.ceil(required_seconds / base_seconds) + 10)

        candles = self.get_latest_candles(symbol, timeframe, limit=base_limit)

        # Get active profile
        profile = self.settings.get_active_profile()

        # Use NATIVE HTF candles from cache if available (loaded from Oanda),
        # otherwise fall back to resampling (legacy behavior).
        htf_cache_key = f"{symbol}:{profile.htf_timeframe}_current"
        native_htf = self._cache.get(htf_cache_key)
        if native_htf and len(native_htf) >= INDICATOR_MIN_CANDLES:
            htf_candles = native_htf
        else:
            htf_candles = (
                _resample_candles(candles, htf_seconds) if htf_seconds != base_seconds else candles
            )
        ltf_candles = (
            _resample_candles(candles, ltf_seconds) if ltf_seconds != base_seconds else candles
        )

        # Neutral defaults — engine.py's Trend Detection sets direction
        _neutral = TrendState(direction="neutral", strength=0.0)

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles[-htf_indicator_window:] if len(htf_candles) >= htf_indicator_window else htf_candles,
            ltf_candles=ltf_candles[-ltf_indicator_window:] if len(ltf_candles) >= ltf_indicator_window else ltf_candles,
            htf_timeframe=profile.htf_timeframe,
            ltf_timeframe=profile.ltf_timeframe or timeframe,
        )


# ── Multi-position helpers ─────────────────────────────────────────────
def _pos_key(symbol: str, meta_source: str | None) -> str:
    """Build a compound position key: 'EURUSD:london_breakout' for multi-position."""
    return f"{symbol}:{meta_source}" if meta_source else symbol

def _symbol_from_key(key: str) -> str:
    """Extract the real symbol from a position key."""
    return key.split(":")[0]

def _positions_for_symbol(positions: dict, symbol: str) -> list:
    """Return all (key, position) tuples for a given symbol."""
    return [(k, v) for k, v in positions.items() if _symbol_from_key(k) == symbol]

def _sub_strategy_from_key(key: str) -> str | None:
    """Extract the sub-strategy from a compound key, or None."""
    parts = key.split(":", 1)
    return parts[1] if len(parts) > 1 else None


class Backtester:
    """Historical simulation engine for validating ICC strategy performance."""

    def __init__(self, ib: Optional[IB], settings: Settings, ai_client: TradeSciAIClient | None):
        self.ib = ib
        self.settings = settings
        self.ai_client = ai_client
        self._cache: Dict[str, Any] = {}
        
        # Use HistoricalMarketDataProvider for local files + IB
        # It now handles the file_path override natively.
        self.market_provider = HistoricalMarketDataProvider(ib, settings)
        self._is_crypto_backtest = False
        
        # Check profile crypto_only flag
        profile = settings.get_active_profile()
        if getattr(profile, "crypto_only", False):
            self._is_crypto_backtest = True
            if ib is None:
                # Fallback to CCXT for crypto if no files provided (legacy behavior)
                # But typically we want the file-capable provider if files are present.
                pass 

        # Also check profile crypto_only flag
        profile = settings.get_active_profile()
        if getattr(profile, "crypto_only", False):
            self._is_crypto_backtest = True

    def _is_market_hours_utc(self, ts: datetime) -> bool:
        # Crypto trades 24/7 - skip market hours filter
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
        data_paths: Optional[Dict[str, str]] = None,
        htf_data_paths: Optional[Dict[str, str]] = None,
        warmup_days: int = 0,
    ) -> BacktestResult:
        """Run a complete backtest over the specified date range.

        Args:
            initial_capital: Starting capital in dollars
            start_date: Backtest start date (UTC)
            end_date: Backtest end date (UTC) (Last day for NEW ENTRIES)
            symbols: List of symbols to trade (defaults to settings.market.symbols)
            wind_down_days: Days to continue simulation AFTER end_date to manage exits (no new entries)
            data_paths: Optional map of symbol to local JSON data file path
            htf_data_paths: Optional map of symbol to local JSON HTF data file path
                (e.g., native 4h candles from Oanda). If provided, these are used
                instead of resampling LTF candles, matching live bot behavior.
            warmup_days: Days to run the engine BEFORE start_date for indicator
                stabilization. During warmup, the engine processes candles and
                computes indicators but blocks ALL new trade entries.

        Returns:
            BacktestResult containing P&L, trades, and performance metrics
        """
        symbols = symbols or self.settings.market.symbols
        if not symbols:
            raise ValueError("No symbols specified for backtest")

        # Wind-Down Calculation
        simulation_end_date = end_date + timedelta(days=wind_down_days)
        # Warmup: run engine N days before start_date to stabilize indicators
        warmup_start = start_date - timedelta(days=warmup_days) if warmup_days > 0 else start_date

        logger.info(
            f"[BACKTEST] Starting backtest: {initial_capital:.2f} capital, "
            f"Warmup: {warmup_days} days (from {warmup_start.date()}), "
            f"Entry Phase: {start_date.date()} to {end_date.date()}, "
            f"Wind-Down: {wind_down_days} days (until {simulation_end_date.date()}), "
            f"symbols={symbols}"
        )

        # Get active profile
        profile = self.settings.get_active_profile()

        # Per-symbol SAR chain counter — tracks how many consecutive SAR-on-SAR
        # stop-outs happened without a winning exit in between.  Prevents the
        # GBPUSD ping-pong pattern where the bot just oscillates at the same
        # price level taking identical losses.
        _sar_consecutive: dict[str, int] = {}

        # Per-symbol CR chain counter — tracks how many consecutive CR stop-outs
        # happened. Resets on any winning trade for that symbol.
        _cr_consecutive: dict[str, int] = {}

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
        # Use warmup_start (not start_date) so indicators have data from first warmup bar
        data_start_date = warmup_start - timedelta(seconds=tf_seconds * lookback_candles)

        all_candles: Dict[str, List[Candle]] = {}
        for symbol in symbols:
            # Fetch data up to simulation_end_date (includes wind-down)
            file_path = data_paths.get(symbol) if data_paths else None
            candles = self.market_provider.fetch_historical_candles(
                symbol, timeframe, data_start_date, simulation_end_date, file_path=file_path
            )
            if candles:
                all_candles[symbol] = candles
                logger.info(f"[BACKTEST] {symbol}: {len(candles)} candles from {candles[0].timestamp.date()} to {candles[-1].timestamp.date()}")

        # Load native HTF candles (e.g., real 4h from Oanda) if provided
        # Load ALL candles from the file — don't date-filter here.
        # The per-bar cache update handles time-based filtering.
        # We need 60+ HTF candles for reliable ADX/indicator computation.
        all_htf_candles: Dict[str, List[Candle]] = {}
        if htf_data_paths:
            htf_tf = profile.htf_timeframe
            for symbol in symbols:
                htf_path = htf_data_paths.get(symbol)
                if htf_path and os.path.exists(htf_path):
                    import json as _json
                    with open(htf_path) as _f:
                        raw_htf = _json.load(_f)
                    htf_candles_loaded = []
                    for r in raw_htf:
                        ts_str = r["timestamp"]
                        ts_str = ts_str.replace("000000000Z", "Z")
                        if ts_str.endswith("Z"):
                            ts_str = ts_str[:-1] + "+00:00"
                        htf_candles_loaded.append(Candle(
                            timestamp=datetime.fromisoformat(ts_str),
                            open=float(r["open"]), high=float(r["high"]),
                            low=float(r["low"]), close=float(r["close"]),
                            volume=int(r.get("volume", 0)),
                        ))
                    if htf_candles_loaded:
                        all_htf_candles[symbol] = htf_candles_loaded
                        logger.info(f"[BACKTEST] {symbol} HTF ({htf_tf}): {len(htf_candles_loaded)} native candles loaded")

        if not all_candles:
            raise ValueError("No historical data available for any symbol")

        # Initialize simulation state
        capital = initial_capital
        positions: Dict[str, SimulatedPosition] = {}
        completed_trades: List[SimulatedTrade] = []
        equity_curve: List[tuple[datetime, float]] = [(start_date, capital)]
        
        # Detect multi-position strategy
        is_multi_position = False
        _reg_entry = StrategyEngine.STRATEGY_REGISTRY.get(profile.strategy_variant)
        if _reg_entry:
            import importlib
            _mod = importlib.import_module(_reg_entry[0])
            _cls = getattr(_mod, _reg_entry[1], None)
            if _cls and getattr(_cls, 'multi_position', False):
                is_multi_position = True
        if is_multi_position:
            logger.info(f"[BACKTEST] Multi-position mode ENABLED for {profile.strategy_variant}")
        
        # Memory-based trade results for strategy awareness
        trade_results_store = TradeResultStore(path="/tmp/backtest_results.json", skip_save=True)
        trade_results_store.results = [] # Start fresh

        # Validate timeframe conversion
        if tf_seconds == 0:
            raise ValueError(f"Invalid timeframe conversion: '{timeframe}' -> 0 seconds")

        logger.info(f"[BACKTEST] Timeframe: {timeframe} = {tf_seconds} seconds")

        # Simulate bar-by-bar (start from warmup_start if warmup enabled)
        current_time = warmup_start
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

        # ── Pre-build StrategyEngine cache per symbol ──────────────────
        # Avoids re-creating the engine (module imports, strategy init,
        # context mask application) on every single bar.
        _engine_cache: Dict[str, Any] = {}
        for _sym in symbols:
            if _sym in all_candles:
                _engine_cache[_sym] = StrategyEngine(
                    ai_client=self.ai_client,
                    market_provider=self.market_provider,
                    profile=profile,
                    symbol=_sym,
                    trade_results=trade_results_store
                )

        logger.info(f"[BACKTEST] Starting simulation loop: {start_date} to {simulation_end_date}")

        while current_time <= simulation_end_date:
            # Wind-Down Logic: Stop loop early if past end_date AND no positions
            is_wind_down = current_time > end_date
            if is_wind_down and not positions:
                logger.info("[BACKTEST] Wind-down complete: No open positions. Terminating simulation.")
                break

            if not self._is_market_hours_utc(current_time):
                current_time += timedelta(seconds=tf_seconds)
                continue

            # Expose current capital to strategy/engine
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

                # Also update native HTF candle cache if available
                if symbol in all_htf_candles:
                    htf_tf = profile.htf_timeframe
                    htf_current = [
                        c for c in all_htf_candles[symbol]
                        if c.timestamp <= current_time
                    ]
                    htf_cache_key = f"{symbol}:{htf_tf}_current"
                    self.market_provider._cache[htf_cache_key] = htf_current

                # DEBUG: Log candle availability for first few bars
                if processed_bar_index < 3:
                    htf_count = len(self.market_provider._cache.get(f"{symbol}:{profile.htf_timeframe}_current", []))
                    logger.info(
                        f"[BACKTEST] Bar {processed_bar_index}: {symbol} has {len(current_candles)} LTF candles, "
                        f"{htf_count} HTF candles up to {current_time.strftime('%Y-%m-%d %H:%M')}"
                    )

            # Check stop/target hits for open positions
            for pos_key, pos in list(positions.items()):
                symbol = _symbol_from_key(pos_key)
                if symbol not in all_candles:
                    continue
                current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
                if not current_candles:
                    continue

                current_bar = current_candles[-1]
                held_seconds = (current_time - pos.entry_time).total_seconds()

                if max_hold_seconds > 0 and held_seconds >= max_hold_seconds:
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                        exit_reason="max_hold",
                        entry_gates=getattr(pos, "entry_gates", None),
                        strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        pnl_usd=pnl,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital,
                        strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                        exit_reason="max_hold",
                        side=pos.direction,
                    ))
                    del positions[pos_key]
                    logger.info(f"[BACKTEST] {symbol} max-hold exit: PnL=${pnl:.2f}")
                    continue

                if (
                    profit_exit_after_hold
                    and min_hold_seconds > 0
                    and held_seconds >= min_hold_seconds
                ):
                    mark_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, mark_price, pos.size, pos.direction, symbol=symbol)
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
                            pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                            exit_reason="profit_hold",
                            entry_gates=getattr(pos, "entry_gates", None),
                            strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            pnl_usd=pnl,
                            is_win=pnl > 0,
                            tier="backtest",
                            capital_at_close=capital,
                            strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                            exit_reason="profit_hold",
                            side=pos.direction,
                        ))
                        del positions[pos_key]
                        logger.info(f"[BACKTEST] {symbol} profit-hold exit: PnL=${pnl:.2f}")
                        continue

                # Check stop loss
                if pos.stop_price is not None and not disable_stops:
                    if min_hold_seconds > 0 and held_seconds < min_hold_seconds:
                        continue
                    # Stop can ONLY trigger if the candle actually traded at the stop price.
                    stop_in_range = current_bar.low <= pos.stop_price <= current_bar.high
                    stop_hit = stop_in_range and (
                        (pos.direction == "long" and current_bar.low <= pos.stop_price) or
                        (pos.direction == "short" and current_bar.high >= pos.stop_price)
                    )
                    if stop_hit:
                        # ── TIERED GUILLOTINE ─────────────────────────────────
                        # Before the stop fires, cascade partial closes through
                        # -0.15R and -0.3R price levels IF those levels fell inside
                        # the candle's range (price passed through them on the way
                        # to the stop). This simulates intra-candle scale-outs that
                        # the single-candle backtester would otherwise miss.
                        #
                        # Tier 1  @ -0.15R → close 80%  (20% remaining)
                        # Tier 2  @ -0.3R  → close 80%  ( 4% remaining)
                        # Stop    @ full   → close  4%  (final remnant)
                        #
                        # Profile flags (all default ON to match Guillotine intent):
                        #   tiered_guillotine_enabled    (default True)
                        #   tier1_r_threshold            (default -0.15)
                        #   tier1_cut_fraction           (default  0.80)
                        #   tier2_r_threshold            (default -0.30)
                        #   tier2_cut_fraction           (default  0.80)
                        tiered_enabled = bool(getattr(profile, 'tiered_guillotine_enabled', True))
                        if tiered_enabled and pos.size > 0:
                            t1_r  = float(getattr(profile, 'tier1_r_threshold',  -0.15))
                            t1_cut = float(getattr(profile, 'tier1_cut_fraction',  0.80))
                            t2_r  = float(getattr(profile, 'tier2_r_threshold',  -0.30))
                            t2_cut = float(getattr(profile, 'tier2_cut_fraction',  0.80))

                            risk_dist = abs(pos.entry_price - pos.stop_price)

                            # Price levels that correspond to each R threshold
                            if pos.direction == "long":
                                t1_price = pos.entry_price + risk_dist * t1_r   # e.g. entry - 0.15R
                                t2_price = pos.entry_price + risk_dist * t2_r
                                t1_breached = current_bar.low <= t1_price
                                t2_breached = current_bar.low <= t2_price
                            else:
                                t1_price = pos.entry_price - risk_dist * t1_r
                                t2_price = pos.entry_price - risk_dist * t2_r
                                t1_breached = current_bar.high >= t1_price
                                t2_breached = current_bar.high >= t2_price

                            # Fire each tier that hasn't been fired yet
                            for tier_label, tier_price, tier_cut, tier_attr in [
                                ("T1", t1_price, t1_cut, "_guillotine_tier1_fired"),
                                ("T2", t2_price, t2_cut, "_guillotine_tier2_fired"),
                            ]:
                                already_fired = getattr(pos, tier_attr, False)
                                in_range = (t1_breached if tier_label == "T1" else t2_breached)
                                if not already_fired and in_range and pos.size > 0:
                                    cut_size = pos.size * tier_cut
                                    tier_pnl = _calculate_pnl(
                                        pos.entry_price, tier_price,
                                        cut_size, pos.direction, symbol=symbol,
                                    )
                                    capital += tier_pnl
                                    pos.cumulative_partial_pnl = getattr(pos, 'cumulative_partial_pnl', 0.0) + tier_pnl
                                    pos.size -= cut_size
                                    setattr(pos, tier_attr, True)
                                    logger.info(
                                        f"[GUILLOTINE-{tier_label}] {symbol}: "
                                        f"cut {tier_cut*100:.0f}% at {tier_price:.5f} "
                                        f"(PnL=${tier_pnl:.2f}, remaining={pos.size:.0f} units)"
                                    )

                        # Final stop on whatever remnant remains
                        exit_price = pos.stop_price
                        pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                        capital += pnl
                        completed_trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            size=pos.size,
                            entry_time=pos.entry_time,
                            exit_time=current_time,
                            pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                            exit_reason="stop",
                            entry_gates=getattr(pos, "entry_gates", None),
                            strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            pnl_usd=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                            is_win=(pnl + getattr(pos, "cumulative_partial_pnl", 0.0)) > 0,
                            tier="backtest",
                            capital_at_close=capital,
                            strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                            exit_reason="stop",
                            side=pos.direction,
                        ))
                        del positions[pos_key]
                        logger.info(f"[BACKTEST] {symbol} stop hit: PnL=${pnl:.2f} (remnant only)")



                        # ── STOP-AND-REVERSE ──────────────────────────
                        # Read from profile settings (non-exclusive).
                        sar_enabled = bool(getattr(profile, 'stop_and_reverse_enabled', False))
                        max_consecutive_sar = int(getattr(profile, 'max_consecutive_sar', 1))
                        # SAR fires on initial stops; B/E exit logic handles risk management
                        if sar_enabled and not pos.stop_was_trailed and pos_key not in positions:
                            # ── Consecutive SAR chain guard ──────────────
                            chain_count = _sar_consecutive.get(symbol, 0)
                            is_sar_trade = getattr(pos, 'strategy_name', '') == 'reversal'
                            if is_sar_trade:
                                chain_count += 1
                                _sar_consecutive[symbol] = chain_count
                                logger.info(
                                    f"[BACKTEST] {symbol} SAR chain stop #{chain_count} "
                                    f"(max={max_consecutive_sar})"
                                )
                            else:
                                _sar_consecutive[symbol] = 0
                                _cr_consecutive[symbol] = 0  # CR chain also resets on normal stop
                                chain_count = 0

                            if chain_count >= max_consecutive_sar:
                                logger.info(
                                    f"[BACKTEST] {symbol} SAR chain blocked — "
                                    f"{chain_count} consecutive SAR losses (limit={max_consecutive_sar}). "
                                    f"Checking CR (Counter-Reversal)..."
                                )

                                # ── COUNTER-REVERSAL (CR) ─────────────────────────
                                # An SAR just failed (was stopped out). Rather than
                                # cooling off entirely, CR flips BACK to the original
                                # direction — the market may be resuming its prior trend
                                # after the whipsaw. Sized identically to SAR (tiny remnant
                                # risk). Gated by `counter_reversal_enabled` (default True).
                                cr_enabled = bool(getattr(profile, 'counter_reversal_enabled', True))
                                max_consecutive_cr = int(getattr(profile, 'max_consecutive_cr', 1))
                                cr_chain = _cr_consecutive.get(symbol, 0)
                                if cr_enabled and cr_chain < max_consecutive_cr and pos_key not in positions:
                                    # pos.direction is the SAR direction; original = opposite
                                    cr_dir = pos.direction  # SAR reversed; CR reverses back
                                    cr_entry = exit_price
                                    risk_dist = abs(pos.entry_price - pos.stop_price)
                                    min_stop_dist = cr_entry * 0.001
                                    if risk_dist < min_stop_dist:
                                        risk_dist = min_stop_dist

                                    cr_tp_r = float(getattr(profile, 'counter_reversal_tp_r',
                                                    getattr(profile, 'reversal_tp_r', 1.0)))
                                    tp_dist = risk_dist * cr_tp_r
                                    if bool(getattr(profile, 'reversal_cost_aware_tp', True)):
                                        from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                                        fee_pct = get_fee_for_symbol(symbol)
                                        tp_dist += cr_entry * fee_pct

                                    if cr_dir == "long":
                                        cr_sl = cr_entry - risk_dist
                                        cr_tp = cr_entry + tp_dist
                                    else:
                                        cr_sl = cr_entry + risk_dist
                                        cr_tp = cr_entry - tp_dist

                                    # Same micro risk as SAR
                                    _explicit_cr_risk = float(getattr(profile, 'counter_reversal_risk_per_trade', 0) or 0)
                                    if _explicit_cr_risk > 0:
                                        cr_risk_pct = _explicit_cr_risk
                                    else:
                                        _scale_out = float(getattr(profile, 'scale_out_fraction', 0.95))
                                        _base_risk = float(getattr(profile, 'risk_per_trade_pct', 0.01))
                                        cr_risk_pct = (1.0 - _scale_out) * _base_risk
                                        if cr_risk_pct <= 0:
                                            cr_risk_pct = 0.01

                                    cr_max_risk = capital * cr_risk_pct
                                    cr_size = cr_max_risk / _jpy_adjust_risk(risk_dist, symbol, cr_entry) if risk_dist > 0 else 0

                                    if cr_size > 0:
                                        _cr_consecutive[symbol] = cr_chain + 1
                                        positions[pos_key] = type(pos)(
                                            symbol=symbol,
                                            direction=cr_dir,
                                            entry_price=cr_entry,
                                            size=cr_size,
                                            stop_price=cr_sl,
                                            target_price=cr_tp,
                                            entry_time=current_time,
                                            strategy_name="counter_reversal",
                                            total_cost=cr_entry * cr_size,
                                        )
                                        logger.info(
                                            f"[BACKTEST] {symbol} COUNTER-REVERSAL → "
                                            f"{cr_dir} @ {cr_entry:.5f}, "
                                            f"SL={cr_sl:.5f}, TP={cr_tp:.5f} "
                                            f"({cr_tp_r}R, risk={cr_risk_pct*100:.3f}%)"
                                        )
                                else:
                                    if not cr_enabled:
                                        logger.info(f"[BACKTEST] {symbol} CR disabled by profile")
                                    else:
                                        logger.info(
                                            f"[BACKTEST] {symbol} CR chain blocked — "
                                            f"{cr_chain} consecutive CR losses. Full cool-off."
                                        )
                            else:
                                rev_dir = "short" if pos.direction == "long" else "long"
                                rev_entry = exit_price
                                risk_dist = abs(pos.entry_price - pos.stop_price)
                                # Enforce minimum stop distance for SAR (same as normal entries)
                                min_stop_dist = rev_entry * 0.001
                                if risk_dist < min_stop_dist:
                                    risk_dist = min_stop_dist
                                # Fixed 1R target
                                rev_tp_r = float(getattr(profile, 'reversal_tp_r', 1.0))
                                tp_dist = risk_dist * rev_tp_r
                                if bool(getattr(profile, 'reversal_cost_aware_tp', True)):
                                    from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                                    fee_pct = get_fee_for_symbol(symbol)
                                    tp_dist += rev_entry * fee_pct  # Add spread buffer
                                if rev_dir == "long":
                                    rev_sl = rev_entry - risk_dist
                                    rev_tp = rev_entry + tp_dist
                                else:
                                    rev_sl = rev_entry + risk_dist
                                    rev_tp = rev_entry - tp_dist
                                # SAR reversal risk: use the REMNANT after Guillotine scale-out
                                # Guillotine cuts `scale_out_fraction` (default 95%) of the
                                # position, leaving (1 - scale_out_fraction) = 5% in the market.
                                # The SAR reversal should match that 5% — it's a tiny counter-
                                # attack on the residual, NOT a full new entry.
                                #
                                # Resolution order:
                                #   1. `reversal_risk_per_trade` if explicitly set in profile
                                #   2. (1 - scale_out_fraction) × risk_per_trade_pct  (the remnant)
                                #   3. Fallback: 0.01 (1%)
                                _explicit_sar_risk = float(getattr(profile, 'reversal_risk_per_trade', 0) or 0)
                                if _explicit_sar_risk > 0:
                                    rev_risk_pct = _explicit_sar_risk
                                else:
                                    _scale_out = float(getattr(profile, 'scale_out_fraction', 0.95))
                                    _base_risk = float(getattr(profile, 'risk_per_trade_pct', 0.01))
                                    rev_risk_pct = (1.0 - _scale_out) * _base_risk  # e.g. 0.05 * 4.5% = 0.225%
                                    if rev_risk_pct <= 0:
                                        rev_risk_pct = 0.01  # absolute fallback
                                rev_max_risk = capital * rev_risk_pct

                                rev_size = rev_max_risk / _jpy_adjust_risk(risk_dist, symbol, rev_entry) if risk_dist > 0 else 0
                                if rev_size > 0:
                                    positions[pos_key] = type(pos)(
                                        symbol=symbol,
                                        direction=rev_dir,
                                        entry_price=rev_entry,
                                        size=rev_size,
                                        stop_price=rev_sl,
                                        target_price=rev_tp,
                                        entry_time=current_time,
                                        strategy_name="reversal",
                                        total_cost=rev_entry * rev_size,
                                    )
                                    logger.info(
                                        f"[BACKTEST] {symbol} REVERSE → "
                                        f"{rev_dir} @ {rev_entry:.5f}, "
                                        f"SL={rev_sl:.5f}, "
                                        f"TP={rev_tp:.5f} ({rev_tp_r}R)"
                                    )
                        continue


                # Check take profit
                if pos.target_price is not None:
                    # TP can ONLY trigger if the candle actually traded at the target price.
                    target_in_range = current_bar.low <= pos.target_price <= current_bar.high
                    target_hit = target_in_range and (
                        (pos.direction == "long" and current_bar.high >= pos.target_price) or
                        (pos.direction == "short" and current_bar.low <= pos.target_price)
                    )
                    if target_hit:
                        if min_hold_seconds > 0 and held_seconds < min_hold_seconds:
                            continue
                        exit_price = pos.target_price
                        pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
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
                            pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                            exit_reason="target",
                            entry_gates=getattr(pos, "entry_gates", None),
                            strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                        ))
                        trade_results_store.add_result(TradeResult(
                            symbol=symbol,
                            closed_at=current_time.isoformat(),
                            pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                            pnl_usd=pnl,
                            is_win=pnl > 0,
                            tier="backtest",
                            capital_at_close=capital,
                            strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                            exit_reason="target",
                            side=pos.direction,
                        ))
                        del positions[pos_key]
                        logger.info(f"[BACKTEST] {symbol} target hit: PnL=${pnl:.2f}")
                        continue

                # Update unrealized P&L
                pos.unrealized_pnl = _calculate_pnl(pos.entry_price, current_bar.close, pos.size, pos.direction, symbol=symbol)

                # NOTE: Counter-Reversal (CR) is handled in the stop-hit block above.
                # CR fires after an SAR stop-out (chain guard triggers), going back
                # to the original direction at the same micro risk (~0.225%).
                # There is no mid-trade CR management needed here.


                # [SOLUTION 2] Hard Max Loss Cap - Exit if loss exceeds configured maximum
                max_loss_dollars = getattr(profile, 'max_loss_per_trade_dollars', None)
                if max_loss_dollars and pos.unrealized_pnl < -abs(max_loss_dollars):
                    logger.warning(
                        f"[MAX LOSS CAP] {symbol} hit max loss cap: "
                        f"${pos.unrealized_pnl:.2f} < -${max_loss_dollars:.2f}"
                    )
                    # Execute immediate exit
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                        exit_reason="max_loss_cap",
                        entry_gates=getattr(pos, "entry_gates", None),
                        strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        pnl_usd=pnl,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital,
                        strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                        exit_reason="max_loss_cap",
                        side=pos.direction,
                    ))
                    del positions[pos_key]
                    logger.info(f"[BACKTEST] {symbol} max loss cap exit: Net PnL=${pnl:.2f}")
                    continue

                # Update HTF neutral bar counter
                # This tracks how long HTF has been neutral to trigger timeout exits
                snapshot = self.market_provider.get_latest_snapshot(symbol, timeframe)
                if snapshot and snapshot.trend_htf:
                    from tradebot_sci.market.trend_enums import TrendDirection
                    if snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
                        pos.htf_neutral_bars += 1
                    else:
                        # Reset counter when HTF becomes trending again
                        pos.htf_neutral_bars = 0
                htf_neutral_exit_bars = int(getattr(profile, "htf_neutral_exit_bars", 0) or 0)
                if (
                    htf_neutral_exit_bars > 0
                    and pos.htf_neutral_bars >= htf_neutral_exit_bars
                    and (min_hold_seconds <= 0 or held_seconds >= min_hold_seconds)
                ):
                    exit_price = current_bar.close
                    pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                    capital += pnl
                    completed_trades.append(SimulatedTrade(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                        exit_reason="htf_neutral_timeout",
                        entry_gates=getattr(pos, "entry_gates", None),
                        strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                    ))
                    trade_results_store.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=current_time.isoformat(),
                        pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                        pnl_usd=pnl,
                        is_win=pnl > 0,
                        tier="backtest",
                        capital_at_close=capital,
                        strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                        exit_reason="htf_neutral_timeout",
                        side=pos.direction,
                    ))
                    del positions[pos_key]
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
                        for pos_key, pos in list(positions.items()):
                            symbol = _symbol_from_key(pos_key)
                            current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
                            if not current_candles:
                                continue
                            exit_price = current_candles[-1].close
                            pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                            capital += pnl
                            completed_trades.append(SimulatedTrade(
                                symbol=symbol,
                                direction=pos.direction,
                                entry_price=pos.entry_price,
                                exit_price=exit_price,
                                size=pos.size,
                                entry_time=pos.entry_time,
                                exit_time=current_time,
                                pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                                exit_reason="eod",
                        entry_gates=getattr(pos, "entry_gates", None),
                                strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                            ))
                            trade_results_store.add_result(TradeResult(
                                symbol=symbol,
                                closed_at=current_time.isoformat(),
                                pnl_pct=(pnl / (pos.entry_price * pos.size)) if (pos.entry_price * pos.size) != 0 else 0,
                                pnl_usd=pnl,
                                is_win=pnl > 0,
                                tier="backtest",
                                capital_at_close=capital,
                                strategy=(getattr(pos, 'entry_gates', None) or {}).get('meta_source') or getattr(pos, 'strategy_name', 'unknown'),
                                exit_reason="eod",
                                side=pos.direction,
                            ))
                            del positions[pos_key]
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
                reconciled_capital = initial_capital + sum(t.pnl for t in completed_trades)
                if reconciled_capital <= 0:
                    if not positions:
                        logger.warning(f"[BACKTEST] Account depleted (capital=${reconciled_capital:.2f}). Stopping backtest.")
                        break

                # ── SIGNAL RANKING: Deferred entry list for position-limited mode ──
                # When max_open_positions caps concurrent entries, we collect
                # all entry signals first, rank them by quality, then execute
                # only the top-N (vs first-come-first-served by dict order).
                _max_concurrent = int(getattr(profile, 'max_open_positions', None) or 999)
                _pending_entries = []  # list of (ranking_score, symbol, decision, snapshot, engine) tuples

                for symbol in all_candles.keys():

                    # Always evaluate strategy, even when in position
                    # This allows for position management, exits, and multi-entry strategies

                    # [FIXED] Use current running capital for risk sizing
                    # Multi-position: find all sub-positions for this symbol
                    symbol_positions = _positions_for_symbol(positions, symbol)
                    
                    # For multi-position strategies, current_position is None
                    # (we handle per-sub-strategy lock after getting the decision)
                    if is_multi_position:
                        current_position = None  # Allow entry evaluation
                    else:
                        current_position = positions.get(symbol)
                    
                    # 1.5 Calculate Global Risk across all symbols
                    total_open_risk_dollars = 0.0
                    for s_name, s_pos in positions.items():
                        s_risk_per_share = abs(s_pos.entry_price - s_pos.stop_price)
                        total_open_risk_dollars += (s_risk_per_share * s_pos.size)
                    
                    global_risk_pct = total_open_risk_dollars / capital if capital > 0 else 0

                    # Check if we have enough capital for NEW entries
                    # Skip capital check if we already have a position (for exit/management signals)
                    if current_position is None and not symbol_positions:
                        # Warmup Block: No new entries before start_date (indicators stabilizing)
                        if current_time < start_date:
                            continue

                        # Wind-Down Block: No new entries after end_date
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
                        # Get strategy decision (cached per symbol)
                        engine = _engine_cache.get(symbol)
                        if not engine:
                            engine = StrategyEngine(
                                ai_client=self.ai_client,
                                market_provider=self.market_provider,
                                profile=profile,
                                symbol=symbol,
                                trade_results=trade_results_store
                            )
                            _engine_cache[symbol] = engine

                        snapshot = self.market_provider.get_latest_snapshot(symbol, timeframe)

                        # Convert SimulatedPosition to a format the engine expects (if we have one)
                        open_position = None

                        # ── Multi-position: per-sub-strategy exit loop ──────────
                        if is_multi_position and symbol_positions:
                            # Check exits for EACH sub-position independently
                            for sp_key, sp_pos in list(symbol_positions):
                                sp_meta = _sub_strategy_from_key(sp_key)
                                last_close = snapshot.candles[-1].close
                                sp_pnl = _calculate_pnl(
                                    sp_pos.entry_price, last_close,
                                    sp_pos.size, sp_pos.direction, symbol=symbol
                                )
                                sp_open_pos = {
                                    'symbol': sp_pos.symbol,
                                    'direction': sp_pos.direction,
                                    'entry_price': sp_pos.entry_price,
                                    'size': sp_pos.size,
                                    'stop_price': sp_pos.stop_price,
                                    'stop_loss': sp_pos.stop_price,
                                    'target_price': sp_pos.target_price,
                                    'take_profit': sp_pos.target_price,
                                    'entry_time': sp_pos.entry_time.isoformat() if sp_pos.entry_time else None,
                                    'unrealized_pnl': sp_pnl,
                                    'pyramid_count': sp_pos.pyramid_count,
                                    'htf_neutral_bars': sp_pos.htf_neutral_bars,
                                    'meta_source': sp_meta,
                                }
                                # Engine call for exit check on this sub-position
                                sp_engine = _engine_cache.get(symbol) or StrategyEngine(
                                    ai_client=self.ai_client,
                                    market_provider=self.market_provider,
                                    profile=profile,
                                    symbol=symbol,
                                    trade_results=trade_results_store
                                )
                                sp_decision = sp_engine.decide(
                                    timeframe=timeframe,
                                    open_position=sp_open_pos,
                                    snapshot=snapshot,
                                    current_bar_time=current_time,
                                )
                                if sp_decision and sp_decision.action in ("exit_position", "close", "close_position", "exit_long", "exit_short"):
                                    exit_price = snapshot.candles[-1].close
                                    pnl = _calculate_pnl(sp_pos.entry_price, exit_price, sp_pos.size, sp_pos.direction, symbol=symbol)
                                    capital += pnl
                                    actual_reason = getattr(sp_decision, 'notes', 'signal') or 'signal'
                                    completed_trades.append(SimulatedTrade(
                                        symbol=symbol,
                                        direction=sp_pos.direction,
                                        entry_price=sp_pos.entry_price,
                                        exit_price=exit_price,
                                        size=sp_pos.size,
                                        entry_time=sp_pos.entry_time,
                                        exit_time=current_time,
                                        pnl=pnl + getattr(sp_pos, "cumulative_partial_pnl", 0.0),
                                        exit_reason=actual_reason,
                                        entry_gates=getattr(sp_pos, "entry_gates", None),
                                        strategy_name=getattr(sp_pos, 'strategy_name', 'unknown'),
                                    ))
                                    trade_results_store.add_result(TradeResult(
                                        symbol=symbol,
                                        closed_at=current_time.isoformat(),
                                        pnl_pct=(pnl / (sp_pos.entry_price * sp_pos.size)) if (sp_pos.entry_price * sp_pos.size) != 0 else 0,
                                        pnl_usd=pnl,
                                        is_win=pnl > 0,
                                        tier="backtest",
                                        capital_at_close=capital,
                                        strategy=sp_meta or getattr(sp_pos, 'strategy_name', 'unknown'),
                                        exit_reason='signal',
                                        side=sp_pos.direction,
                                    ))
                                    if sp_key in positions:
                                        del positions[sp_key]
                                    logger.info(f"[BACKTEST] {symbol}:{sp_meta} multi-pos EXIT: PnL=${pnl:.2f}")

                                # ── Handle stop/target management + pyramiding ──
                                elif sp_decision and sp_decision.action in ("hold", "scale_in", "scale_out"):
                                    # Update stop if provided
                                    if sp_decision.stop_loss is not None and sp_decision.stop_loss != sp_pos.stop_price:
                                        old_stop = sp_pos.stop_price
                                        sp_pos.stop_price = sp_decision.stop_loss
                                        sp_pos.stop_was_trailed = True
                                        logger.info(
                                            f"[BACKTEST] {symbol}:{sp_meta} stop updated: "
                                            f"${old_stop:.5f} -> ${sp_decision.stop_loss:.5f} "
                                            f"({getattr(sp_decision, 'notes', '')[:60]})"
                                        )
                                    if sp_decision.take_profit is not None and sp_decision.take_profit != sp_pos.target_price:
                                        old_tp = sp_pos.target_price
                                        sp_pos.target_price = sp_decision.take_profit
                                        logger.info(
                                            f"[BACKTEST] {symbol}:{sp_meta} target updated: "
                                            f"${old_tp} -> ${sp_decision.take_profit:.5f}"
                                        )

                                    # ── Execute pyramid sizing on scale_in ──
                                    if sp_decision.action == "scale_in":
                                        add_price = snapshot.candles[-1].close
                                        stop_price = sp_decision.stop_loss or sp_pos.stop_price
                                        risk_per_share = abs(add_price - stop_price)

                                        if hasattr(sp_decision, "risk_per_trade_pct") and sp_decision.risk_per_trade_pct:
                                            risk_pct = float(sp_decision.risk_per_trade_pct)
                                        else:
                                            risk_pct = float(getattr(profile, "risk_per_trade_pct", 0.10))

                                        min_stop_distance = add_price * 0.001
                                        if risk_per_share < min_stop_distance:
                                            risk_per_share = min_stop_distance

                                        compounding_capital = min(capital, 10000.0)
                                        max_risk = compounding_capital * risk_pct
                                        add_size = max_risk / risk_per_share if risk_per_share > 0 else 0

                                        if add_size > 0:
                                            sp_pos.size += add_size
                                            sp_pos.total_cost += add_price * add_size
                                            sp_pos.entry_price = sp_pos.total_cost / sp_pos.size
                                            sp_pos.pyramid_count += 1
                                            logger.info(
                                                f"[BACKTEST] {symbol}:{sp_meta} PYRAMID #{sp_pos.pyramid_count}: "
                                                f"+{add_size:.0f} units @ {add_price:.5f} "
                                                f"(avg={sp_pos.entry_price:.5f}, total={sp_pos.size:.0f})"
                                            )

                            # Build combined position info so sub-strategies can pyramid
                            # Each sub-strategy only sees ITS OWN position via meta_source
                            combined_open_pos = None
                            if symbol_positions:
                                # Pass all sub-position info; the Conductor routes to the
                                # correct sub-strategy which checks its own position
                                last_close = snapshot.candles[-1].close
                                all_subs = {}
                                for sp_key, sp_pos in symbol_positions:
                                    sp_meta = _sub_strategy_from_key(sp_key)
                                    sp_pnl = _calculate_pnl(
                                        sp_pos.entry_price, last_close,
                                        sp_pos.size, sp_pos.direction, symbol=symbol
                                    )
                                    all_subs[sp_meta] = {
                                        'symbol': sp_pos.symbol,
                                        'direction': sp_pos.direction,
                                        'entry_price': sp_pos.entry_price,
                                        'size': sp_pos.size,
                                        'stop_price': sp_pos.stop_price,
                                        'stop_loss': sp_pos.stop_price,
                                        'target_price': sp_pos.target_price,
                                        'take_profit': sp_pos.target_price,
                                        'entry_time': sp_pos.entry_time.isoformat() if sp_pos.entry_time else None,
                                        'unrealized_pnl': sp_pnl,
                                        'pyramid_count': sp_pos.pyramid_count,
                                        'htf_neutral_bars': sp_pos.htf_neutral_bars,
                                        'meta_source': sp_meta,
                                    }
                                # Pass combined as open_position with _sub_positions for routing
                                combined_open_pos = {
                                    '_sub_positions': all_subs,
                                    # Also set top-level fields from first sub-position for engine compatibility
                                    **list(all_subs.values())[0],
                                }

                            decision = engine.decide(
                                timeframe=timeframe,
                                open_position=combined_open_pos,
                                snapshot=snapshot,
                                current_bar_time=current_time,
                            )
                        elif current_position is not None:
                            # [FIXED] Strategy needs to know its profit to pyramid!
                            last_close = snapshot.candles[-1].close
                            pnl = _calculate_pnl(
                                current_position.entry_price, 
                                last_close, 
                                current_position.size, 
                                current_position.direction,
                                symbol=symbol
                            )
                            # Create a minimal position dict for the engine
                            open_position = {
                                'symbol': current_position.symbol,
                                'direction': current_position.direction,
                                'entry_price': current_position.entry_price,
                                'size': current_position.size,
                                'stop_price': current_position.stop_price,
                                'stop_loss': current_position.stop_price, # Mapping for RoboCop
                                'target_price': current_position.target_price,
                                'unrealized_pnl': pnl,
                                'pyramid_count': current_position.pyramid_count,
                                'htf_neutral_bars': current_position.htf_neutral_bars,
                                'entry_time': current_position.entry_time,
                                'strategy_name': getattr(current_position, 'strategy_name', 'unknown'),
                                'original_entry_price': getattr(current_position, 'original_entry_price', current_position.entry_price),
                                'initial_risk': getattr(current_position, 'initial_risk', None),
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
                            # 5-MINUTE HOLD GUARD: Match engine.py
                            HOLD_GUARD_SECONDS = 300
                            is_sl_tp = getattr(decision, 'emergency_exit', False)
                            if held_seconds < HOLD_GUARD_SECONDS and not is_sl_tp:
                                logger.info(
                                    f"[BACKTEST] [HOLD GUARD] {symbol} exit blocked — "
                                    f"age {held_seconds:.0f}s < {HOLD_GUARD_SECONDS}s "
                                    f"(only SL/TP exits allowed)"
                                )
                                continue
                            exit_price = snapshot.candles[-1].close
                            pnl = _calculate_pnl(current_position.entry_price, exit_price, current_position.size, current_position.direction, symbol=symbol)
                            if pnl <= 0 and not allow_loss_exit_after_hold:
                                logger.info(f"[BACKTEST] {symbol} exit signal ignored (not profitable).")
                                continue
                            if pnl <= 0 and allow_loss_exit_after_hold:
                                logger.info(f"[BACKTEST] {symbol} exit signal accepted after hold (loss allowed).")
                            capital += pnl
                            # Propagate actual exit reason from decision
                            actual_reason = (
                                getattr(decision, 'notes', None)
                                or getattr(decision, 'structure_summary', None)
                                or "signal"
                            )
                            completed_trades.append(SimulatedTrade(
                                symbol=symbol,
                                direction=current_position.direction,
                                entry_price=current_position.entry_price,
                                exit_price=exit_price,
                                size=current_position.size,
                                entry_time=current_position.entry_time,
                                exit_time=current_time,
                                pnl=pnl + getattr(current_position, "cumulative_partial_pnl", 0.0),
                                exit_reason=actual_reason,
                                entry_gates=getattr(current_position, "entry_gates", None),
                                strategy_name=getattr(current_position, 'strategy_name', 'unknown'),
                            ))
                            # For multi-position, delete by the sub-strategy key
                            if is_multi_position:
                                meta_src = (getattr(current_position, 'entry_gates', None) or {}).get('meta_source')
                                del_key = _pos_key(symbol, meta_src)
                                if del_key in positions:
                                    del positions[del_key]
                            else:
                                del positions[symbol]
                            logger.info(f"[BACKTEST] {symbol} EXIT ({actual_reason[:50]}): PnL=${pnl:.2f}")
                            continue  # Skip to next symbol after exit

                        # Handle pyramid/add to position
                        if current_position is not None and decision.action in ("add_to_position", "scale_in"):
                            # ── PYRAMID LIMIT GUARD ──────────────────────
                            max_pyramids = int(getattr(profile, 'max_pyramid_entries', 1))
                            if current_position.pyramid_count >= max_pyramids:
                                logger.info(
                                    f"[BACKTEST] {symbol} PYRAMID BLOCKED: "
                                    f"already at {current_position.pyramid_count}/{max_pyramids} entries"
                                )
                                continue

                            # ── DUST GUARD (pre-pyramid) ──────────────────────
                            # If existing position is dust (< 100 units), close it first.
                            # Pyramiding onto dust corrupts entry_price via weighted average
                            # (e.g. $0.037 instead of $1.18 → phantom -$264K PnL).
                            MIN_PYRAMID_BASE = 10
                            if current_position.size < MIN_PYRAMID_BASE:
                                exit_price = snapshot.candles[-1].close
                                dust_pnl = _calculate_pnl(
                                    current_position.entry_price, exit_price,
                                    current_position.size, current_position.direction,
                                    symbol=symbol,
                                )
                                capital += dust_pnl
                                completed_trades.append(SimulatedTrade(
                                    symbol=symbol,
                                    direction=current_position.direction,
                                    entry_price=current_position.entry_price,
                                    exit_price=exit_price,
                                    size=current_position.size,
                                    entry_time=current_position.entry_time,
                                    exit_time=current_time,
                                    pnl=dust_pnl + getattr(current_position, "cumulative_partial_pnl", 0.0),
                                    exit_reason="dust_before_pyramid",
                                    entry_gates=getattr(current_position, "entry_gates", None),
                                    strategy_name=getattr(current_position, 'strategy_name', 'unknown'),
                                ))
                                pos_key = next((k for k, v in positions.items() if v is current_position), None)
                                if pos_key:
                                    del positions[pos_key]
                                logger.info(
                                    f"[BACKTEST] {symbol} DUST GUARD (pre-pyramid): closed {current_position.size:.0f} "
                                    f"dust units @ ${exit_price:.6f}, PnL=${dust_pnl:.2f}"
                                )
                                current_position = None
                                # Fall through to new entry logic below (don't pyramid onto dust)
                                continue

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
                            # [RISK SATURATION] Cap pyramid sizing to full capital
                            # (leverage cap on the entry itself prevents over-exposure)
                            py_cap = compounding_capital
                            if getattr(profile, 'nuclear_overrides_enabled', False):
                                py_cap = getattr(profile, 'pyramid_cap_override', compounding_capital)

                            compounding_capital_py = min(capital, py_cap)
                            max_risk = min(compounding_capital_py * risk_pct, max_loss_cap)

                            raw_add_size = max_risk / _jpy_adjust_risk(risk_per_share, symbol, add_price) if risk_per_share > 0 else 0.0
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
                                    current_position.stop_was_trailed = True

                                # Push target if provided
                                if getattr(decision, "take_profit", None) is not None:
                                    current_position.target_price = decision.take_profit

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
                            # ── PARTIAL CLOSE on scale_out ──────────────────
                            if decision.action == "scale_out" and current_position.size > 0:
                                # Read from runtime settings (non-exclusive)
                                _rt = getattr(self.settings, 'runtime', None)
                                close_frac = float(getattr(_rt, 'scale_out_fraction', 0.95)) if _rt else 0.95  # Guillotine: 95%
                                close_size = current_position.size * close_frac
                                exit_price = snapshot.candles[-1].close
                                partial_pnl = _calculate_pnl(
                                    current_position.entry_price, exit_price,
                                    close_size, current_position.direction,
                                    symbol=symbol,
                                )
                                capital += partial_pnl
                                current_position.cumulative_partial_pnl += partial_pnl
                                current_position.size -= close_size
                                current_position.total_cost = (
                                    current_position.entry_price * current_position.size
                                )
                                logger.info(
                                    f"[BACKTEST] {symbol} PARTIAL CLOSE: "
                                    f"closed {close_size:.0f} units "
                                    f"({close_frac*100:.0f}%), "
                                    f"PnL=${partial_pnl:.2f}, "
                                    f"remaining={current_position.size:.0f}"
                                )

                                # ── DUST GUARD: Auto-close position if remainder is negligible ──
                                # After a 95% partial close, the leftover can be tiny (e.g. 12 units).
                                # Subsequent pyramids on these remnants corrupt the average entry_price
                                # (e.g. $0.48 instead of $1.18), causing catastrophic PnL errors.
                                # Close the dust remainder entirely to keep accounting clean.
                                MIN_REMAINING_UNITS = 100
                                if current_position.size < MIN_REMAINING_UNITS:
                                    dust_pnl = _calculate_pnl(
                                        current_position.entry_price, exit_price,
                                        current_position.size, current_position.direction,
                                        symbol=symbol,
                                    )
                                    capital += dust_pnl
                                    logger.info(
                                        f"[BACKTEST] {symbol} DUST CLOSE: "
                                        f"auto-closed {current_position.size:.0f} remaining units, "
                                        f"PnL=${dust_pnl:.2f}"
                                    )
                                    # Record trade with combined partial + dust PnL
                                    total_pnl = partial_pnl + dust_pnl
                                    completed_trades.append(SimulatedTrade(
                                        symbol=symbol,
                                        direction=current_position.direction,
                                        entry_price=current_position.entry_price,
                                        exit_price=exit_price,
                                        size=close_size + current_position.size,
                                        entry_time=current_position.entry_time,
                                        exit_time=current_time,
                                        pnl=total_pnl,
                                        exit_reason=decision.notes or "partial_close_dust",
                                        entry_gates=getattr(current_position, "entry_gates", None),
                                        strategy_name=getattr(current_position, 'strategy_name', 'unknown'),
                                    ))
                                    # Remove position
                                    pos_key = next((k for k, v in positions.items() if v is current_position), None)
                                    if pos_key:
                                        del positions[pos_key]
                                    continue  # Skip further processing for this symbol

                            # Update stop/target if strategy provides new ones
                            if decision.stop_loss is not None and decision.stop_loss != current_position.stop_price:
                                # ── Breakeven Stop Guard ────────────────────────────
                                # Strategies often set stop_loss=entry_price (breakeven)
                                # immediately. On 15m forex this triggers on the next
                                # candle's noise, producing 0-pip exits with fee-only
                                # losses (-$9 each). Block the move until the trade has
                                # enough unrealized profit to survive the stop.
                                allow_move = True
                                new_stop = decision.stop_loss
                                entry = current_position.entry_price
                                direction = current_position.direction
                                cur_price = current_bar.close

                                # Is this a breakeven move? (new stop within 0.1% of entry)
                                is_be_move = abs(new_stop - entry) / entry < 0.001

                                if is_be_move:
                                    # Calculate unrealized profit in price terms
                                    if direction == "long":
                                        unrealized = cur_price - entry
                                    else:
                                        unrealized = entry - cur_price

                                    # Need at least 1.5× the fee cost in profit before moving to BE
                                    # This prevents noise from immediately hitting the BE stop
                                    from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                                    fee_pct = get_fee_for_symbol(symbol)
                                    min_profit = entry * fee_pct * 3.0  # 3× fee to cover round-trip + buffer
                                    if unrealized < min_profit:
                                        allow_move = False

                                if allow_move:
                                    old_stop = current_position.stop_price
                                    current_position.stop_price = decision.stop_loss
                                    current_position.stop_was_trailed = True
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

                        if current_position is not None and not is_multi_position and decision.action in ("enter_long", "enter_short"):
                            potential_trades_blocked += 1
                            potential_trade_block_reasons["already_in_position"] += 1
                            logger.info(
                                f"[BACKTEST] {symbol} potential entry blocked (already holding position)."
                            )
                            continue

                        # Execute entry if signal is valid (no confidence check - AI decides via action field)
                        # Only allow new entries if we don't already have a position
                        # Multi-position: allow entry if this sub-strategy doesn't already have a position
                        can_enter = False

                        # ── Handle pyramiding (scale_in) in multi-position mode ──
                        if decision.action in ("scale_in", "add_to_position") and is_multi_position:
                            meta_src = (getattr(decision, 'gates', None) or {}).get('meta_source')
                            sub_key = _pos_key(symbol, meta_src)
                            existing = positions.get(sub_key)
                            if existing:
                                add_price = snapshot.candles[-1].close
                                stop_price = decision.stop_loss or existing.stop_price
                                risk_per_share = abs(add_price - stop_price)

                                if hasattr(decision, "risk_per_trade_pct") and decision.risk_per_trade_pct:
                                    risk_pct = float(decision.risk_per_trade_pct)
                                else:
                                    risk_pct = float(getattr(profile, "risk_per_trade_pct", 0.10))

                                min_stop_distance = add_price * 0.001
                                if risk_per_share < min_stop_distance:
                                    risk_per_share = min_stop_distance

                                compounding_capital = min(capital, 10000.0)
                                max_risk = compounding_capital * risk_pct
                                add_size = max_risk / _jpy_adjust_risk(risk_per_share, symbol, add_price) if risk_per_share > 0 else 0

                                if add_size > 0:
                                    existing.size += add_size
                                    existing.total_cost += add_price * add_size
                                    existing.entry_price = existing.total_cost / existing.size
                                    existing.pyramid_count += 1
                                    if decision.stop_loss is not None:
                                        existing.stop_price = decision.stop_loss
                                        existing.stop_was_trailed = True
                                    if decision.take_profit is not None:
                                        existing.target_price = decision.take_profit
                                    logger.info(
                                        f"[BACKTEST] {symbol}:{meta_src} PYRAMID #{existing.pyramid_count}: "
                                        f"+{add_size:.0f} units @ {add_price:.5f} "
                                        f"(avg={existing.entry_price:.5f}, total={existing.size:.0f})"
                                    )
                            continue  # Don't fall through to new entry logic

                        if decision.action in ("enter_long", "enter_short"):
                            if is_multi_position:
                                meta_src = (getattr(decision, 'gates', None) or {}).get('meta_source')
                                sub_key = _pos_key(symbol, meta_src)
                                if sub_key not in positions:
                                    can_enter = True
                                else:
                                    potential_trades_blocked += 1
                                    potential_trade_block_reasons["sub_strategy_in_position"] += 1
                                    logger.info(f"[BACKTEST] {symbol}:{meta_src} multi-pos blocked (sub-strategy already in position)")
                            elif current_position is None:
                                can_enter = True

                        # ── MAX CONCURRENT POSITIONS — DEFER FOR RANKING ──
                        # When a position cap is active and slots are full,
                        # instead of blocking outright, defer the entry into
                        # a candidate list so we can rank ALL signals and
                        # pick the best N at the end of the symbol loop.
                        if can_enter and len(positions) >= _max_concurrent:
                            # Compute ranking score for this candidate
                            # decision.score is set by engine (0-100 ICC grade)
                            # snapshot.trend_htf has .strength and .direction
                            _dec_score = float(getattr(decision, 'score', 0) or 0)
                            _htf_obj = getattr(snapshot, 'trend_htf', None)
                            _htf_str = float(getattr(_htf_obj, 'strength', 0) or 0) if _htf_obj else 0.0

                            # Extract regime from Conductor tag in decision notes
                            # Format: "[Conductor:strategy|regime]"
                            _regime = 'unknown'
                            _notes = getattr(decision, 'notes', '') or ''
                            if '|' in _notes:
                                import re as _re
                                _regime_match = _re.search(r'\|(\w+)\]', _notes)
                                if _regime_match:
                                    _regime = _regime_match.group(1)

                            _urgency = getattr(decision, 'urgency', 'medium') or 'medium'

                            _regime_bonus = {'trending': 20, 'transitional': 10, 'ranging': 5}.get(_regime, 0)
                            _urgency_bonus = 5 if _urgency == 'high' else 0
                            _ranking_score = (_htf_str * 40) + (_dec_score * 0.35) + _regime_bonus + _urgency_bonus

                            _pending_entries.append((
                                _ranking_score, symbol, decision, snapshot, engine
                            ))
                            logger.info(
                                f"[BACKTEST] {symbol} DEFERRED for ranking "
                                f"(score={_ranking_score:.1f}, htf={_htf_str:.2f}, "
                                f"dec_score={_dec_score:.0f}, regime={_regime}, "
                                f"{len(positions)}/{_max_concurrent} slots full)"
                            )
                            can_enter = False  # Don't execute now

                        if can_enter:
                            # ── CONSECUTIVE-LOSS COOLDOWN ─────────────────
                            # After 2 consecutive losses on a symbol, sit out
                            # for 4 bars to avoid churn on choppy pairs.
                            if not hasattr(self, '_symbol_cooldown'):
                                self._symbol_cooldown = {}  # symbol → resume_bar_idx
                                self._bar_counter = 0
                            self._bar_counter += 1

                            # Count consecutive recent losses for this symbol
                            sym_trades = [t for t in completed_trades if t.symbol == symbol]
                            consec_losses = 0
                            for t in reversed(sym_trades):
                                if t.pnl <= 0:
                                    consec_losses += 1
                                else:
                                    break

                            # Start cooldown after 2 consecutive losses
                            if consec_losses >= 2 and symbol not in self._symbol_cooldown:
                                self._symbol_cooldown[symbol] = self._bar_counter + 4
                                logger.info(
                                    f"[BACKTEST] {symbol} COOLDOWN STARTED: "
                                    f"{consec_losses} consecutive losses, "
                                    f"sitting out 4 bars"
                                )

                            # Check if in cooldown (SAR reversals bypass)
                            is_sar = getattr(decision, 'notes', '') and 'reversal' in str(getattr(decision, 'notes', '')).lower()
                            resume_bar = self._symbol_cooldown.get(symbol, 0)
                            if resume_bar > self._bar_counter and not is_sar:
                                can_enter = False
                                logger.info(
                                    f"[BACKTEST] {symbol} ENTRY BLOCKED (cooldown): "
                                    f"{resume_bar - self._bar_counter} bars remaining"
                                )
                            elif resume_bar > 0 and self._bar_counter >= resume_bar:
                                # Cooldown expired — clear it
                                del self._symbol_cooldown[symbol]

                        if can_enter:
                            # Use strategy-defined risk, but profile risk acts as FLOOR
                            profile_risk = float(getattr(profile, "risk_per_trade_pct", 0.015))
                            if hasattr(decision, "risk_per_trade_pct") and decision.risk_per_trade_pct is not None:
                                risk_pct = max(float(decision.risk_per_trade_pct), profile_risk)
                            else:
                                risk_pct = profile_risk

                            # ── Per-Symbol Risk Caps ──────────────────────────
                            # Read from profile `symbol_risk_overrides` dict.
                            # Cartridges and live profiles can define per-symbol
                            # scaling; if not set, full risk applies to every pair.
                            sym_overrides = getattr(profile, 'symbol_risk_overrides', None) or {}
                            sym_scale = sym_overrides.get(symbol, 1.0)
                            if sym_scale < 1.0:
                                risk_pct *= sym_scale
                                logger.info(f"[RISK-CAP] {symbol} scaled to {sym_scale:.0%} → risk={risk_pct*100:.2f}%")

                            # ── Compound Flywheel ──────────────────────────────
                            # Only active when `flywheel_enabled=True` in profile/cartridge.
                            # Every $50 cumulative profit → +0.1% risk, capped at +2%.
                            if bool(getattr(profile, 'flywheel_enabled', False)):
                                cumulative_pnl = capital - initial_capital
                                if cumulative_pnl > 0:
                                    flywheel_milestone = float(getattr(profile, 'flywheel_milestone_usd', 50.0))
                                    flywheel_step = float(getattr(profile, 'flywheel_step_pct', 0.001))
                                    flywheel_cap = float(getattr(profile, 'flywheel_cap_pct', 0.02))
                                    flywheel_boost = (cumulative_pnl // flywheel_milestone) * flywheel_step
                                    flywheel_boost = min(flywheel_boost, flywheel_cap)
                                    risk_pct += flywheel_boost
                                    if flywheel_boost > 0:
                                        logger.info(f"[FLYWHEEL] +{flywheel_boost*100:.1f}% boost (cum PnL=${cumulative_pnl:.2f}) → risk={risk_pct*100:.2f}%")

                            # ── Performance Multipliers ───────────────────────
                            # Each multiplier reads its own profile gate.
                            # In live mode these are controlled by the same profile flags.
                            boost_label = []

                            # A. REGIME SYNC (1.5× when HTF trend strongly aligned)
                            if bool(getattr(profile, 'performance_regime_sync_enabled', False)):
                                htf_strength = getattr(snapshot, 'trend_htf', None)
                                if htf_strength:
                                    strength_val = getattr(htf_strength, 'strength', 0.0)
                                    htf_dir = getattr(htf_strength, 'direction', 'neutral')
                                    trade_dir = "long" if decision.action == "enter_long" else "short"
                                    reg_mult = float(getattr(profile, 'performance_regime_multiplier', 1.5))
                                    reg_threshold = float(getattr(profile, 'performance_regime_threshold', 0.7))
                                    if strength_val >= reg_threshold and htf_dir == trade_dir:
                                        risk_pct *= reg_mult
                                        boost_label.append(f"Regime({htf_dir} {strength_val:.2f})={reg_mult}×")

                            # B. GAMMA SQUEEZE (1.2× on 4-bar price velocity > 0.1%)
                            if bool(getattr(profile, 'performance_gamma_enabled', False)):
                                if len(snapshot.candles) >= 5:
                                    start_price = snapshot.candles[-5].close
                                    end_price = snapshot.candles[-1].close
                                    velocity = abs(end_price - start_price) / start_price
                                    gamma_threshold = float(getattr(profile, 'performance_gamma_threshold', 0.001))
                                    gamma_mult = float(getattr(profile, 'performance_gamma_multiplier', 1.2))
                                    if velocity > gamma_threshold:
                                        risk_pct *= gamma_mult
                                        boost_label.append(f"Gamma({velocity*100:.2f}%)={gamma_mult}×")

                            # C. COIL BREAKOUT (2.0× on ATR compression)
                            if bool(getattr(profile, 'performance_coil_enabled', False)):
                                if len(snapshot.candles) >= 100:
                                    from tradebot_sci.strategy.safety_guard import calculate_atr
                                    recent_atr = calculate_atr(snapshot.candles[-14:], period=14)
                                    hist_atr = calculate_atr(snapshot.candles, period=100)
                                    coil_threshold = float(getattr(profile, 'performance_coil_threshold', 0.6))
                                    coil_mult = float(getattr(profile, 'performance_coil_multiplier', 2.0))
                                    if recent_atr and hist_atr and recent_atr < (hist_atr * coil_threshold):
                                        risk_pct *= coil_mult
                                        boost_label.append(f"Coil({recent_atr/hist_atr:.2f})={coil_mult}×")

                            if boost_label:
                                logger.info(f"[PERF] {symbol} {' | '.join(boost_label)} → risk={risk_pct*100:.2f}%")

                            # ── HARD MAX RISK CAP ─────────────────────────────
                            # Read from profile `max_risk_pct_hard_cap`.
                            # Defaults to the profile's own risk_per_trade_pct * 3
                            # so the cap is proportional, not a stale hardcoded 2%.
                            MAX_RISK_PCT = float(getattr(profile, 'max_risk_pct_hard_cap', None) or
                                                 (float(getattr(profile, 'risk_per_trade_pct', 0.045)) * 3))
                            if risk_pct > MAX_RISK_PCT:
                                logger.info(
                                    f"[RISK-CAP] {symbol}: risk {risk_pct*100:.2f}% → "
                                    f"capped at {MAX_RISK_PCT*100:.1f}%"
                                )
                                risk_pct = MAX_RISK_PCT


                            # [RISK SATURATION] Cap compounding to prevent Nuclear Blowout
                            comp_cap = 10000.0  # Conservative cap for consistency
                            if getattr(profile, 'nuclear_overrides_enabled', False):
                                comp_cap = getattr(profile, 'compounding_cap_override', 10000.0)

                            compounding_capital = min(capital, comp_cap)

                            # [PORTFOLIO RISK] Scale risk capital using sqrt(N) to balance
                            # pyramid growth against concentration risk.
                            # sqrt(12) ≈ 3.46 → each symbol gets ~29% of capital
                            # (vs 8% with 1/N or 100% with no division).
                            num_symbols = max(len(symbols), 1)
                            per_symbol_capital = compounding_capital / (num_symbols ** 0.5)

                            max_risk = per_symbol_capital * risk_pct
                            logger.info(f"[BACKTEST] Entry: {symbol} using {risk_pct*100:.2f}% risk on ${per_symbol_capital:.2f} base (${max_risk:.2f}) [Cap: ${comp_cap}]")

                            entry_price = snapshot.candles[-1].close

                            # Calculate position size with safety measures
                            stop_price = decision.stop_loss or (entry_price * 0.98 if decision.action == "enter_long" else entry_price * 1.02)
                            risk_per_share = abs(entry_price - stop_price)

                            # Safety 1: Enforce minimum stop distance (0.1% of entry - allows heavy scalping leverage)
                            min_stop_distance = entry_price * 0.001
                            if risk_per_share < min_stop_distance:
                                # Compute original R:R so we can preserve it after widening
                                original_rr = 2.5  # Default R:R
                                if decision.take_profit and risk_per_share > 0:
                                    tp_dist = abs(decision.take_profit - entry_price)
                                    original_rr = tp_dist / risk_per_share

                                logger.warning(
                                    f"[BACKTEST] {symbol}: Stop too tight (${risk_per_share:.4f} < ${min_stop_distance:.4f}), "
                                    f"widening to minimum (preserving {original_rr:.1f}R target)"
                                )
                                risk_per_share = min_stop_distance
                                # Adjust stop price to match minimum distance
                                if decision.action == "enter_long":
                                    stop_price = entry_price - min_stop_distance
                                else:
                                    stop_price = entry_price + min_stop_distance

                                # Scale take_profit to preserve original R:R
                                if decision.take_profit:
                                    if decision.action == "enter_long":
                                        decision.take_profit = entry_price + (min_stop_distance * original_rr)
                                    else:
                                        decision.take_profit = entry_price - (min_stop_distance * original_rr)

                            # Calculate position size based on risk
                            # ICC methodology: size = risk_amount / stop_distance
                            # With tight stops (0.5%), this creates leverage which is intentional
                            # Example: $100 risk / $3 stop = 33 shares = $20k notional (20× leverage)
                            size = max_risk / _jpy_adjust_risk(risk_per_share, symbol, entry_price) if risk_per_share > 0 else 0

                            # Safety 2: Cap total notional to REALISTIC broker leverage
                            # OANDA forex = 30:1, Crypto spot (Gemini/Kraken) = no margin = 1:1,
                            # IBKR stocks = 4:1 day / 2:1 overnight
                            from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
                            asset_class = classify_symbol(symbol)
                            REALISTIC_LEVERAGE = {
                                AssetClass.FOREX: 30.0,    # OANDA retail max
                                AssetClass.CRYPTO: 3.0,    # Gemini spot (no real margin)
                                AssetClass.STOCKS: 4.0,    # IBKR reg-T day trading
                                AssetClass.ETF: 4.0,       # Same as stocks
                                AssetClass.METALS: 20.0,   # OANDA metals
                                AssetClass.FUTURES: 15.0,  # IBKR futures margin
                            }
                            lev_cap = REALISTIC_LEVERAGE.get(asset_class, 5.0)
                            # Allow env override for testing only
                            if os.getenv('RR_LEV_CAP'):
                                lev_cap = float(os.environ['RR_LEV_CAP'])
                            max_position_value = per_symbol_capital * lev_cap
                            npu = _notional_per_unit(symbol, entry_price)
                            max_shares = max_position_value / npu
                            if size > max_shares:
                                logger.warning(
                                    f"[BACKTEST] {symbol}: Position size capped from {size:.2f} to {max_shares:.2f} shares "
                                    f"(max {lev_cap:.0f}× leverage = ${max_position_value:.2f} notional on ${compounding_capital:.2f} capital, "
                                    f"notional/unit={'$1' if npu == 1.0 else f'${npu:.4f}'})"
                                )
                                size = max_shares

                            if size > 0:
                                # Build position key: compound for multi-position, simple otherwise
                                meta_src = (getattr(decision, 'gates', None) or {}).get('meta_source')
                                entry_pos_key = _pos_key(symbol, meta_src) if is_multi_position else symbol

                                positions[entry_pos_key] = SimulatedPosition(
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
                                    entry_gates=getattr(decision, 'gates', None),
                                    strategy_name=(
                                        # 1. Sub-strategy name from Meta-SCI gate
                                        (getattr(decision, 'gates', None) or {}).get('meta_source')
                                        # 2. Engine's loaded strategy name
                                        or getattr(getattr(engine, '_strategy', None), 'name', None)
                                        # 3. Strategy variant from profile
                                        or getattr(profile, 'strategy_variant', 'untagged')
                                    ),
                                    original_entry_price=entry_price,
                                    initial_risk=abs(entry_price - float(stop_price)) if stop_price else None,
                                )
                                sub_tag = f":{meta_src}" if meta_src else ""
                                logger.info(
                                    f"[BACKTEST] {symbol}{sub_tag} ENTRY {decision.action.upper()} @ ${entry_price:.2f}, "
                                    f"size={size:.2f}, stop=${stop_price:.2f}"
                                )

                    except Exception as e:
                        logger.error(
                            f"[BACKTEST] Error generating decision for {symbol} at {current_time.strftime('%Y-%m-%d %H:%M')}: {e}",
                            exc_info=True
                        )
                # ── SIGNAL RANKING: Execute top-N deferred entries ─────────
                # After evaluating all symbols, sort deferred candidates by
                # ranking score and execute the best available entries.
                if _pending_entries:
                    _pending_entries.sort(key=lambda x: x[0], reverse=True)
                    _available_slots = _max_concurrent - len(positions)

                    logger.info(
                        f"[RANKING] {len(_pending_entries)} candidates for "
                        f"{_available_slots} slot(s): "
                        + ", ".join(f"{sym}({sc:.1f})" for sc, sym, *_ in _pending_entries)
                    )

                    for _rank_idx, (_score, _r_sym, _r_dec, _r_snap, _r_eng) in enumerate(_pending_entries):
                        if len(positions) >= _max_concurrent:
                            # ── OPPORTUNITY COST EVICTION ────────────────
                            # Slots full — but if the best pending signal is
                            # stronger than our worst LOSING position, swap.
                            # RULE: never evict a winning position.
                            _worst_key = None
                            _worst_pnl = 0.0
                            _worst_sym = None
                            for _pk, _pp in positions.items():
                                _sym_for_pos = _symbol_from_key(_pk)
                                # Anti-churn: position must be held ≥N min before eviction
                                _evict_min_sec = int(getattr(profile, 'eviction_min_hold_minutes', 30)) * 60
                                _held_sec = (current_time - _pp.entry_time).total_seconds() if _pp.entry_time else 0
                                if _held_sec < _evict_min_sec:
                                    continue  # Too young to evict
                                # Get current price for this position's symbol
                                _pos_candles = all_candles.get(_sym_for_pos, [])
                                if not _pos_candles:
                                    continue
                                # Find the candle at current_time
                                _pos_price = None
                                for _c in reversed(_pos_candles):
                                    if _c.timestamp <= current_time:
                                        _pos_price = _c.close
                                        break
                                if _pos_price is None:
                                    _pos_price = _pos_candles[-1].close
                                _pos_pnl = _calculate_pnl(
                                    _pp.entry_price, _pos_price,
                                    _pp.size, _pp.direction,
                                    symbol=_sym_for_pos
                                )
                                # Only consider LOSING positions for eviction
                                if _pos_pnl < 0 and (_worst_key is None or _pos_pnl < _worst_pnl):
                                    _worst_key = _pk
                                    _worst_pnl = _pos_pnl
                                    _worst_sym = _sym_for_pos

                            if _worst_key is None:
                                # All positions are winning or too young — don't evict
                                _remaining = len(_pending_entries) - _rank_idx
                                potential_trades_blocked += _remaining
                                potential_trade_block_reasons["all_positions_winning"] += _remaining
                                logger.info(
                                    f"[EVICTION] Blocked {_remaining} entries — "
                                    f"no evictable positions (all winning or too young)"
                                )
                                break

                            # Close the worst loser to make room
                            _evicted = positions.pop(_worst_key)
                            _evict_sym = _symbol_from_key(_worst_key)
                            _evict_candles = all_candles.get(_evict_sym, [])
                            _evict_price = _evict_candles[-1].close if _evict_candles else _evicted.entry_price
                            for _ec in reversed(_evict_candles):
                                if _ec.timestamp <= current_time:
                                    _evict_price = _ec.close
                                    break
                            _evict_pnl = _calculate_pnl(
                                _evicted.entry_price, _evict_price,
                                _evicted.size, _evicted.direction,
                                symbol=_evict_sym
                            )
                            capital += _evict_pnl

                            # Record the evicted trade
                            _evict_duration = (current_time - _evicted.entry_time).total_seconds() if _evicted.entry_time else 0
                            completed_trades.append(SimulatedTrade(
                                symbol=_evict_sym,
                                direction=_evicted.direction,
                                entry_price=_evicted.entry_price,
                                exit_price=_evict_price,
                                size=_evicted.size,
                                entry_time=_evicted.entry_time,
                                exit_time=current_time,
                                pnl=_evict_pnl,
                                exit_reason=f"Evicted for {_r_sym} (score={_score:.1f})",
                                entry_gates=getattr(_evicted, "entry_gates", None),
                                strategy_name=getattr(_evicted, 'strategy_name', 'unknown'),
                            ))
                            trade_results_store.add_result(TradeResult(
                                symbol=_evict_sym,
                                closed_at=current_time.isoformat(),
                                pnl_pct=(_evict_pnl / (_evicted.entry_price * _evicted.size)) if (_evicted.entry_price * _evicted.size) != 0 else 0,
                                pnl_usd=_evict_pnl,
                                is_win=_evict_pnl > 0,
                                tier="backtest",
                                capital_at_close=capital,
                                strategy=(getattr(_evicted, 'entry_gates', None) or {}).get('meta_source') or getattr(_evicted, 'strategy_name', 'unknown'),
                                exit_reason=f"Evicted for {_r_sym}",
                                side=_evicted.direction,
                            ))

                            logger.info(
                                f"[EVICTION] Closed {_evict_sym} (PnL=${_evict_pnl:.2f}, "
                                f"held {_evict_duration/60:.0f}m) "
                                f"→ making room for {_r_sym} (score={_score:.1f})"
                            )
                            # Now a slot is free — fall through to entry logic below

                        # ── Apply the same entry pipeline as normal entries ──
                        # Cooldown check
                        _r_can_enter = True
                        if hasattr(self, '_symbol_cooldown'):
                            _is_sar_r = getattr(_r_dec, 'notes', '') and 'reversal' in str(getattr(_r_dec, 'notes', '')).lower()
                            _resume_bar_r = self._symbol_cooldown.get(_r_sym, 0)
                            if _resume_bar_r > self._bar_counter and not _is_sar_r:
                                _r_can_enter = False
                                logger.info(
                                    f"[RANKING] {_r_sym} SKIPPED (cooldown), "
                                    f"score={_score:.1f}"
                                )

                        if not _r_can_enter:
                            potential_trades_blocked += 1
                            potential_trade_block_reasons["ranked_cooldown"] += 1
                            continue

                        # ── Risk sizing (mirrors the standard entry path) ──
                        profile_risk = float(getattr(profile, "risk_per_trade_pct", 0.015))
                        if hasattr(_r_dec, "risk_per_trade_pct") and _r_dec.risk_per_trade_pct is not None:
                            _r_risk_pct = max(float(_r_dec.risk_per_trade_pct), profile_risk)
                        else:
                            _r_risk_pct = profile_risk

                        # Per-symbol risk overrides
                        sym_overrides = getattr(profile, 'symbol_risk_overrides', None) or {}
                        _r_sym_scale = sym_overrides.get(_r_sym, 1.0)
                        if _r_sym_scale < 1.0:
                            _r_risk_pct *= _r_sym_scale

                        # Hard max risk cap
                        MAX_RISK_PCT = float(getattr(profile, 'max_risk_pct_hard_cap', None) or
                                             (float(getattr(profile, 'risk_per_trade_pct', 0.045)) * 3))
                        if _r_risk_pct > MAX_RISK_PCT:
                            _r_risk_pct = MAX_RISK_PCT

                        # Risk saturation
                        comp_cap = 10000.0
                        if getattr(profile, 'nuclear_overrides_enabled', False):
                            comp_cap = getattr(profile, 'compounding_cap_override', 10000.0)
                        compounding_capital = min(capital, comp_cap)
                        num_symbols = max(len(symbols), 1)
                        per_symbol_capital = compounding_capital / (num_symbols ** 0.5)

                        max_risk = per_symbol_capital * _r_risk_pct
                        entry_price = _r_snap.candles[-1].close

                        # Position sizing
                        stop_price = _r_dec.stop_loss or (entry_price * 0.98 if _r_dec.action == "enter_long" else entry_price * 1.02)
                        risk_per_share = abs(entry_price - stop_price)

                        # Min stop distance
                        min_stop_distance = entry_price * 0.001
                        if risk_per_share < min_stop_distance:
                            original_rr = 2.5
                            if _r_dec.take_profit and risk_per_share > 0:
                                tp_dist = abs(_r_dec.take_profit - entry_price)
                                original_rr = tp_dist / risk_per_share
                            risk_per_share = min_stop_distance
                            if _r_dec.action == "enter_long":
                                stop_price = entry_price - min_stop_distance
                            else:
                                stop_price = entry_price + min_stop_distance
                            if _r_dec.take_profit:
                                if _r_dec.action == "enter_long":
                                    _r_dec.take_profit = entry_price + (min_stop_distance * original_rr)
                                else:
                                    _r_dec.take_profit = entry_price - (min_stop_distance * original_rr)

                        size = max_risk / _jpy_adjust_risk(risk_per_share, _r_sym, entry_price) if risk_per_share > 0 else 0

                        # Leverage cap
                        from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
                        asset_class = classify_symbol(_r_sym)
                        REALISTIC_LEVERAGE = {
                            AssetClass.FOREX: 30.0,
                            AssetClass.CRYPTO: 3.0,
                            AssetClass.STOCKS: 4.0,
                            AssetClass.ETF: 4.0,
                            AssetClass.METALS: 20.0,
                            AssetClass.FUTURES: 15.0,
                        }
                        lev_cap = REALISTIC_LEVERAGE.get(asset_class, 5.0)
                        if os.getenv('RR_LEV_CAP'):
                            lev_cap = float(os.environ['RR_LEV_CAP'])
                        max_position_value = per_symbol_capital * lev_cap
                        npu = _notional_per_unit(_r_sym, entry_price)
                        max_shares = max_position_value / npu
                        if size > max_shares:
                            size = max_shares

                        if size > 0:
                            meta_src = (getattr(_r_dec, 'gates', None) or {}).get('meta_source')
                            entry_pos_key = _pos_key(_r_sym, meta_src) if is_multi_position else _r_sym

                            positions[entry_pos_key] = SimulatedPosition(
                                symbol=_r_sym,
                                direction="long" if _r_dec.action == "enter_long" else "short",
                                entry_price=entry_price,
                                size=size,
                                entry_time=current_time,
                                stop_price=stop_price,
                                target_price=_r_dec.take_profit,
                                pyramid_count=1,
                                total_cost=entry_price * size,
                                htf_neutral_bars=0,
                                entry_gates=getattr(_r_dec, 'gates', None),
                                strategy_name=(
                                    (getattr(_r_dec, 'gates', None) or {}).get('meta_source')
                                    or getattr(getattr(_r_eng, '_strategy', None), 'name', None)
                                    or getattr(profile, 'strategy_variant', 'untagged')
                                ),
                                original_entry_price=entry_price,
                                initial_risk=abs(entry_price - float(stop_price)) if stop_price else None,
                            )
                            logger.info(
                                f"[RANKING] #{_rank_idx+1} {_r_sym} ENTRY {_r_dec.action.upper()} "
                                f"@ ${entry_price:.5f}, score={_score:.1f}, "
                                f"size={size:.0f}, stop=${stop_price:.5f}"
                            )

            # Record equity curve
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions.values())
            total_equity = capital + unrealized_pnl
            equity_curve.append((current_time, total_equity))

            # Advance time
            current_time += timedelta(seconds=tf_seconds)
            processed_bar_index += 1

        # Close any remaining positions at end
        for pos_key, pos in positions.items():
            symbol = _symbol_from_key(pos_key)
            current_candles = self.market_provider._cache.get(f"{symbol}:{timeframe}_current", [])
            if current_candles:
                exit_price = current_candles[-1].close
                pnl = _calculate_pnl(pos.entry_price, exit_price, pos.size, pos.direction, symbol=symbol)
                capital += pnl
                completed_trades.append(SimulatedTrade(
                    symbol=symbol,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    size=pos.size,
                    entry_time=pos.entry_time,
                    exit_time=end_date,
                    pnl=pnl + getattr(pos, "cumulative_partial_pnl", 0.0),
                    exit_reason="eod",
                    entry_gates=getattr(pos, "entry_gates", None),
                    strategy_name=getattr(pos, 'strategy_name', 'unknown'),
                ))

        # Calculate performance metrics
        # Use authoritative trade PnL sum instead of running capital variable,
        # which can drift due to partial close accounting interactions.
        trade_pnl_sum = sum(t.pnl for t in completed_trades)
        capital = initial_capital + trade_pnl_sum  # Reconcile capital
        total_pnl = trade_pnl_sum
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
