from __future__ import annotations

import collections
import inspect
import itertools
import json
import logging
import math
import os
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, time as datetime_time
from zoneinfo import ZoneInfo
print("ANTIGRAVITY LOADED SRC/LOOP.PY")

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.broker.execution import ExecutionOutcomeType, ExecutionResult, ExecutionStatus
from tradebot_sci.config.loader import get_settings
from tradebot_sci.config.models import Settings
from tradebot_sci.logging.setup import setup_logging
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.providers import MockMarketDataProvider
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.runtime.provider_factory import build_exchange_broker, build_market_provider
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.runtime.pair_selector import PairSelector
from tradebot_sci.runtime.friction import FrictionModel
from tradebot_sci.runtime.auto_schedule import select_auto_schedule_symbols
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.decisions import stand_aside_decision
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.market.symbols import AssetClass, MARKET_HOURS, MarketType, SYMBOL_METADATA, is_crypto
logger = logging.getLogger(__name__)


def _log_holdings_snapshot(executor, *, reason: str) -> None:
    """
    Emit a structured holdings snapshot for UI consumers (tmux/GUI).
    This line is JSON-only (no free-form filler) so it can be parsed reliably.
    """
    if not executor or not hasattr(executor, "list_open_position_symbols"):
        return
    try:
        symbols = list(executor.list_open_position_symbols() or [])
    except Exception:
        symbols = []
    positions: list[dict] = []
    for sym in symbols:
        try:
            snap = executor.get_open_position_snapshot(sym)
        except Exception as e:
            logger.debug(f"[HOLDINGS] Failed to get position snapshot for {sym}: {e}")
            snap = None
        if not snap:
            continue
        try:
            if abs(float(snap.get("size", 0) or 0)) < 1e-8:
                continue
        except Exception as e:
            logger.debug(f"[HOLDINGS] Failed to parse size for {sym}: {e}")
            pass
        positions.append({"symbol": sym, **snap})
    
    total_pnl = sum(p.get("unrealized_pnl", 0.0) or 0.0 for p in positions)
    payload = {
        "reason": reason,
        "count": len(positions),
        "total_unrealized_pnl": total_pnl,
        "positions": positions,
    }
    logger.info("[HOLDINGS] %s", json.dumps(payload, sort_keys=True))

def _engine_decide(engine, timeframe: str, open_position, snapshot, execution_capabilities: dict | None):
    decide_fn = getattr(engine, "decide", None)
    if not decide_fn:
        raise AttributeError("engine missing decide()")
    try:
        params = inspect.signature(decide_fn).parameters
    except (TypeError, ValueError):
        params = {}
    if "execution_capabilities" in params:
        return decide_fn(
            timeframe,
            open_position=open_position,
            snapshot=snapshot,
            execution_capabilities=execution_capabilities,
        )
    return decide_fn(
        timeframe,
        open_position=open_position,
        snapshot=snapshot,
    )

def _git_short_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=os.getcwd(), text=True)
            .strip()
        )
    except Exception as e:
        logger.debug(f"Failed to get git SHA: {e}")
        return "unknown"

try:
    from astral import LocationInfo
    from astral.sun import sun

    ASTRAL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    LocationInfo = None  # type: ignore[assignment]
    sun = None  # type: ignore[assignment]
    ASTRAL_AVAILABLE = False


def _maybe_connect_primary_ib(settings: Settings, execute_trades: bool) -> object | None:
    if not execute_trades:
        return None
    
    legacy_provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
    broker_mode = (os.getenv("BROKER_MODE") or settings.market.broker_mode or "").strip().lower()
    market_mode = (os.getenv("MARKET_DATA_MODE") or settings.market.market_data_mode or "").strip().lower()

    # [DEBUG] Trace mode resolution
    logger.info(f"DEBUG_CONNECT: provider={legacy_provider} broker={broker_mode} market={market_mode}")

    # Legacy fallback when explicit modes are not provided.

    # Legacy fallback when explicit modes are not provided.
    if not broker_mode and legacy_provider:
        broker_mode = legacy_provider
    if not market_mode and legacy_provider:
        market_mode = legacy_provider

    if broker_mode not in ("primary", "hybrid") and market_mode not in ("primary", "hybrid"):
        return None
    try:
        from ib_insync import IB  # type: ignore
    except Exception as exc:
        logger.error("IBKR init failed for exchange_provider=primary; missing ib_insync: %s", exc)
        raise SystemExit(1) from exc

    shared_ib = IB()
    connect_timeout = float(os.getenv("IBKR_CONNECT_TIMEOUT", "20") or 20)
    request_timeout = float(os.getenv("IBKR_REQUEST_TIMEOUT", "20") or 20)
    
    max_retries = int(os.getenv("IBKR_RETRY_COUNT", "15") or 15)
    retry_delay = int(os.getenv("IBKR_RETRY_DELAY", "60") or 60)

    for attempt in range(1, max_retries + 1):
        try:
            shared_ib.connect(
                settings.broker.host if settings.broker else "127.0.0.1",
                int(settings.broker.port) if settings.broker else 7497,
                clientId=int(getattr(settings.broker, "client_id", 101)) if settings.broker else 101,
                readonly=False,
                timeout=connect_timeout,
            )
            break
        except Exception as exc:
            if getattr(shared_ib, "isConnected", None) and shared_ib.isConnected():
                logger.warning("IBKR connect reported an error but session is connected: %s", exc)
                break
            
            if attempt < max_retries:
                logger.warning(
                    "IBKR init attempt %d/%d failed; retrying in %ds: %s",
                    attempt,
                    max_retries,
                    retry_delay,
                    exc,
                )
                time.sleep(retry_delay)
            else:
                logger.error("IBKR init failed for exchange_provider=primary after %d attempts; aborting: %s", max_retries, exc)
                raise SystemExit(1) from exc

    try:
        shared_ib.RequestTimeout = request_timeout
    except Exception:
        logger.debug("IBKR request timeout override not supported on this client")
    return shared_ib


class StrikeTracker:
    def __init__(
        self,
        max_consecutive: int,
        cooldown_cycles: int,
        guard_block_threshold: int,
        guard_block_cooldown: int,
    ) -> None:
        self.max_consecutive = max_consecutive
        self.cooldown_cycles = cooldown_cycles
        self.guard_block_threshold = guard_block_threshold
        self.guard_block_cooldown_cycles = guard_block_cooldown
        self.strikes: dict[str, int] = {}
        self.cooldowns: dict[str, int] = {}
        self.guard_block_streak: dict[str, int] = {}
        self.guard_block_cooldowns: dict[str, int] = {}
        self.cooldown_reasons: dict[str, str] = {}

    def advance_cycle(self) -> None:
        # Decrement cooldowns and remove expired ones
        # Note: Creating new dict to avoid mutation during iteration (cleaner pattern)
        self.cooldowns = {sym: count - 1 for sym, count in self.cooldowns.items() if count > 1}
        # Clean up reasons for expired cooldowns
        self.cooldown_reasons = {sym: reason for sym, reason in self.cooldown_reasons.items() if sym in self.cooldowns}

        # Same for guard block cooldowns
        self.guard_block_cooldowns = {sym: count - 1 for sym, count in self.guard_block_cooldowns.items() if count > 1}

    def is_skipped(self, symbol: str) -> bool:
        return self.cooldowns.get(symbol, 0) > 0

    def is_guard_skipped(self, symbol: str) -> bool:
        return self.guard_block_cooldowns.get(symbol, 0) > 0

    def guard_cooldown_remaining(self, symbol: str) -> int:
        return self.guard_block_cooldowns.get(symbol, 0)

    def record_risk_suppression(self, symbol: str) -> bool:
        if self.max_consecutive <= 0 or self.cooldown_cycles <= 0:
            return False
        current = self.strikes.get(symbol, 0) + 1
        self.strikes[symbol] = current
        if current >= self.max_consecutive:
            self._apply_cooldown(symbol, "risk_suppressed")
            self.strikes[symbol] = 0
            return True
        return False

    def record_guard_block(self, symbol: str) -> bool:
        if self.guard_block_threshold <= 0 or self.guard_block_cooldown_cycles <= 0:
            return False
        current = self.guard_block_streak.get(symbol, 0) + 1
        self.guard_block_streak[symbol] = current
        if current >= self.guard_block_threshold:
            self.guard_block_cooldowns[symbol] = self.guard_block_cooldown_cycles
            self.guard_block_streak[symbol] = 0
            return True
        return False

    def reset(self, symbol: str) -> None:
        self.strikes.pop(symbol, None)
        self.cooldowns.pop(symbol, None)
        self.guard_block_streak.pop(symbol, None)
        self.guard_block_cooldowns.pop(symbol, None)
        self.cooldown_reasons.pop(symbol, None)

    def cooldown_reason(self, symbol: str) -> str | None:
        return self.cooldown_reasons.get(symbol)

    def _apply_cooldown(self, symbol: str, reason: str | None) -> bool:
        if self.cooldown_cycles <= 0:
            self.cooldown_reasons.pop(symbol, None)
            return False
        self.cooldowns[symbol] = self.cooldown_cycles
        self.cooldown_reasons[symbol] = reason or "cooldown"
        return True

    def record_execution_success(self, symbol: str, reason: str | None = None) -> None:
        self.strikes.pop(symbol, None)
        self.guard_block_streak.pop(symbol, None)
        self.guard_block_cooldowns.pop(symbol, None)
        self._apply_cooldown(symbol, reason or "success")


def _log_state_snapshot(executor, symbol: str):
    """Logs the current open position snapshot for a symbol."""
    if not executor:
        logger.info("[STATE] %s open_position: none (no executor)", symbol)
        return None
    state = executor._fetch_symbol_state(symbol)
    open_pos = executor.get_open_position_snapshot(symbol)
    working_orders = state.get("working_orders", 0)
    statuses = state.get("working_order_statuses", [])
    synthetic_state = "armed" if state.get("synthetic_stop_armed") else "none"
    detail_parts: list[str] = []
    if working_orders:
        detail_parts.append(f"working_orders={working_orders}")
        if statuses:
            detail_parts.append(f"statuses={','.join(statuses)}")
    if synthetic_state == "armed":
        detail_parts.append("synthetic_stop=armed")
    suffix = f" {' '.join(detail_parts)}" if detail_parts else ""
    if open_pos:
        logger.info(
            "[STATE] %s open_position: side=%s size=%.2f avg=%.4f sl=%s tp=%s%s",
            symbol,
            open_pos.get("side"),
            open_pos.get("size"),
            open_pos.get("avg_price"),
            open_pos.get("stop_loss"),
            open_pos.get("take_profit"),
            suffix,
        )
    elif detail_parts:
        logger.info("[STATE] %s position=none%s", symbol, suffix)
    else:
        logger.info("[STATE] %s open_position: none", symbol)
    return open_pos


def _get_market_symbols(settings):
    from tradebot_sci.runtime.universe import get_market_symbols

    return get_market_symbols(settings)


def _filter_crypto_symbols(symbols: list[str], profile_name: str) -> list[str]:
    from tradebot_sci.runtime.universe import filter_crypto_symbols

    allowed = filter_crypto_symbols(symbols)
    blocked = [symbol for symbol in symbols if symbol not in set(allowed)]
    if blocked:
        logger.info(
            "[BLOCKED] profile=%s removed non-crypto symbols -> %s",
            profile_name,
            ", ".join(blocked),
        )
    return allowed


def _resolve_symbol_universe(settings, profile_settings, profile_name: str) -> list[str]:
    from tradebot_sci.runtime.universe import resolve_symbol_universe

    symbols = resolve_symbol_universe(settings, profile_settings, profile_name)
    if not symbols:
        logger.warning(
            "[STATE] profile=%s ended up with no symbols; falling back to default %s",
            profile_name,
            settings.market.default_symbol,
        )
        return [settings.market.default_symbol]
    return symbols


def _is_crypto_symbol(symbol: str) -> bool:
    metadata = SYMBOL_METADATA.get(symbol.upper())
    return bool(metadata and metadata.asset_class == AssetClass.CRYPTO)


def _should_flatten_symbol(
    symbol: str,
    profile_name: str,
    runtime,
    crypto_only_profile: bool = False,
) -> bool:
    if not (runtime.flatten_on_exit or runtime.intraday_flatten):
        return False
    if crypto_only_profile and _is_crypto_symbol(symbol):
        return False
    return True


def _flatten_symbols_at_shutdown(
    symbols: list[str],
    profile_name: str,
    runtime,
    crypto_only_profile: bool,
    executor,
) -> list[str]:
    """Runs the shared shutdown flatten loop so tests can exercise it."""
    if not executor or not symbols:
        return []
    flattened: list[str] = []
    for symbol in symbols:
        if not _should_flatten_symbol(symbol, profile_name, runtime, crypto_only_profile):
            continue
        executor.flatten_symbol(symbol)
        flattened.append(symbol)
    return flattened


def _instrument_classes_for_symbols(symbols: list[str]) -> list[str]:
    from tradebot_sci.runtime.universe import instrument_classes_for_symbols

    return instrument_classes_for_symbols(symbols)


def _confirm_trading_universe(symbols: list[str], profile_name: str, execute_trades: bool) -> None:
    universe = ",".join(symbols)
    instrument_classes = _instrument_classes_for_symbols(symbols)
    logger.info(
        "[PRECHECK] profile=%s will_trade=[%s] instrument_classes=[%s]",
        profile_name,
        universe,
        ",".join(instrument_classes),
    )
    if not execute_trades:
        logger.info("[PRECHECK] EXECUTE_TRADES!=true; skipping confirmation.")
        return
    expected_confirmation = f"YES:{universe}"
    provided_confirmation = os.getenv("TRADING_CONFIRMATION")
    if provided_confirmation == expected_confirmation or provided_confirmation == "YES":
        logger.info("[PRECHECK] TRADING_CONFIRMATION matched expected universe (or wildcard YES).")
        return

    # Auto-restart override: implicit approval if previously confirmed (even if universe shifted slightly)
    restart_count = int(os.getenv("TRADEBOT_AUTO_RESTART_COUNT", "0") or 0)
    if restart_count > 0 and provided_confirmation and provided_confirmation.startswith("YES:"):
        logger.warning(
            "[PRECHECK] Auto-restart detected. Implicitly trusting previous confirmation despite universe change (prev: %s, new: %s).",
            provided_confirmation,
            expected_confirmation,
        )
        _persist_trading_confirmation(expected_confirmation)
        return

    if not sys.stdin or not sys.stdin.isatty():
        logger.error(
            "[PRECHECK] Live trading requires confirmation but stdin is not interactive and TRADING_CONFIRMATION is missing or incorrect."
        )
        raise SystemExit(1)
    user_input = input(f"Type '{expected_confirmation}' to confirm trading universe: ").strip()
    if user_input != expected_confirmation:
        logger.error(
            "[PRECHECK] Confirmation mismatch (%s); expected %s. Aborting live trading startup.",
            user_input,
            expected_confirmation,
        )
        raise SystemExit(1)
    logger.info("[PRECHECK] User confirmation accepted.")
    _persist_trading_confirmation(expected_confirmation)


def _persist_trading_confirmation(expected_confirmation: str) -> None:
    # Keep confirmation in-process so auto-restarts via execv stay non-interactive.
    os.environ["TRADING_CONFIRMATION"] = expected_confirmation

    # Also persist to a file so external restarts (scripts/tradebot.sh --restart)
    # can pick it up.
    try:
        # Default to logs/ relative to root; if TRADEBOT_LOG is set, use that dir.
        log_file = os.getenv("TRADEBOT_LOG", "logs/tradebot.log")
        confirm_file = os.path.join(os.path.dirname(log_file), ".trading_confirmation")
        with open(confirm_file, "w") as f:
            f.write(expected_confirmation)
    except Exception as e:
        logger.debug(f"[PRECHECK] Failed to persist confirmation to file: {e}")

    # If running inside tmux, try to update the session environment so it survives pane respawn.
    session = os.getenv("SESSION_NAME")
    if session:
        try:
            subprocess.run(
                ["tmux", "set-environment", "-t", session, "TRADING_CONFIRMATION", expected_confirmation],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


def _fetch_snapshot(provider, cache, symbol, timeframe, profile_settings, market_settings):
    htf_timeframe = getattr(profile_settings, "htf_timeframe", None) or "4h"
    ltf_timeframe = getattr(profile_settings, "ltf_timeframe", None) or timeframe
    trend_window = int(getattr(profile_settings, "trend_window", 24) or 24)
    ltf_trend_window = getattr(profile_settings, "ltf_trend_window", None)
    ltf_window = int(ltf_trend_window) if ltf_trend_window else trend_window
    swing_lookback = int(getattr(profile_settings, "trend_swing_lookback", 2) or 2)
    min_swings = int(getattr(profile_settings, "trend_min_swings", 3) or 3)
    strength_floor = float(getattr(profile_settings, "trend_strength_floor", 0.5) or 0.5)
    max_candles = int(getattr(market_settings, "max_candles", 200) or 200)

    key = (symbol, ltf_timeframe, htf_timeframe, max_candles, trend_window, swing_lookback, min_swings, strength_floor)
    if key not in cache:
        ltf_candles = provider.get_latest_candles(symbol, ltf_timeframe, limit=max_candles)
        htf_candles = provider.get_latest_candles(symbol, htf_timeframe, limit=max_candles)
        trend_htf = infer_trend_from_swings(
            htf_candles,
            swing_lookback=swing_lookback,
            window=trend_window,
            min_swings=min_swings,
            strength_floor=strength_floor,
        )
        trend_ltf = infer_trend_from_swings(
            ltf_candles,
            swing_lookback=swing_lookback,
            window=ltf_window,
            min_swings=min_swings,
            strength_floor=strength_floor,
        )
        cache[key] = MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=ltf_candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=htf_timeframe,
            ltf_timeframe=ltf_timeframe,
        )
    return cache[key]


def _parse_local_time(value: str) -> tuple[int, int]:
    hour, minute = map(int, value.split(":"))
    return hour, minute


def _compute_sabbath_window(
    reference: datetime,
    profile: TradingProfileSettings,
    allow_astronomical: bool,
) -> tuple[datetime, datetime, bool, bool]:
    tz = ZoneInfo(profile.sabbath_timezone)
    local_ref = reference.astimezone(tz)
    days_since_friday = (local_ref.weekday() - 4) % 7
    friday_date = (local_ref - timedelta(days=days_since_friday)).date()
    start_hour, start_minute = _parse_local_time(profile.sabbath_start_local)
    end_hour, end_minute = _parse_local_time(profile.sabbath_end_local)
    start = datetime(
        friday_date.year,
        friday_date.month,
        friday_date.day,
        start_hour,
        start_minute,
        tzinfo=tz,
    )
    saturday_date = friday_date + timedelta(days=1)
    end_fixed = datetime(
        saturday_date.year,
        saturday_date.month,
        saturday_date.day,
        end_hour,
        end_minute,
        tzinfo=tz,
    )
    if (
        allow_astronomical
        and profile.sabbath_astronomical
        and profile.sabbath_lat is not None
        and profile.sabbath_lon is not None
        and ASTRAL_AVAILABLE
        and LocationInfo is not None
        and sun is not None
    ):
        try:
            location = LocationInfo(
                name="sabbath",
                region="",
                timezone=profile.sabbath_timezone,
                latitude=profile.sabbath_lat,
                longitude=profile.sabbath_lon,
            )
            friday_sun = sun(location.observer, date=friday_date, tzinfo=tz)
            saturday_sun = sun(location.observer, date=saturday_date, tzinfo=tz)
            return friday_sun["sunset"], saturday_sun["sunset"], True, False
        except Exception as e:
            logger.warning(f"Failed to compute astronomical sabbath window: {e}")
            return start, end_fixed, False, True
    return start, end_fixed, False, False


def _is_sabbath_now(
    now: datetime, profile: TradingProfileSettings, allow_astronomical: bool
) -> tuple[bool, datetime]:
    tz = ZoneInfo(profile.sabbath_timezone)
    local_now = now.astimezone(tz)
    start, end, _, _ = _compute_sabbath_window(local_now, profile, allow_astronomical)
    return start <= local_now < end, end


class SabbathContext:
    def __init__(self, profile: TradingProfileSettings, override: bool | None = None) -> None:
        self.profile = profile
        self.override = override
        self.timezone = ZoneInfo(profile.sabbath_timezone)
        self._log_counter = 0
        self._last_active: bool | None = None
        self._log_rate = 10
        self._astral_fallback_logged = False

    @property
    def enabled(self) -> bool:
        if self.override is not None:
            return self.override
        return bool(self.profile.sabbath_enabled)

    def log_startup(self) -> None:
        now = datetime.now(self.timezone)
        start, end, _, astral_failed = _compute_sabbath_window(
            now, self.profile, allow_astronomical=self.profile.sabbath_astronomical
        )
        logger.info(
            "[SABBATH] enabled=%s override=%s timezone=%s now=%s window_start=%s window_end=%s astral=%s lat=%s lon=%s",
            self.enabled,
            self.override,
            self.profile.sabbath_timezone,
            now.isoformat(),
            start.isoformat(),
            end.isoformat(),
            self.profile.sabbath_astronomical and ASTRAL_AVAILABLE,
            self.profile.sabbath_lat,
            self.profile.sabbath_lon,
        )
        if astral_failed and not self._astral_fallback_logged:
            logger.warning("[SABBATH] astral_unavailable=true; falling back to fixed window")
            self._astral_fallback_logged = True

    def evaluate(self, reference: datetime) -> tuple[bool, datetime, datetime]:
        if not self.enabled:
            return False, reference, reference
        local_ref = reference.astimezone(self.timezone)
        start, end, _, astral_failed = _compute_sabbath_window(
            local_ref, self.profile, allow_astronomical=self.profile.sabbath_astronomical
        )
        active = start <= local_ref < end
        remaining = max(0.0, (end - local_ref).total_seconds()) if active else 0.0
        if astral_failed and not self._astral_fallback_logged:
            logger.warning("[SABBATH] astral_unavailable=true; falling back to fixed window")
            self._astral_fallback_logged = True
        self._log_counter += 1
        if self._last_active is None or self._last_active != active or self._log_counter >= self._log_rate:
            logger.info(
                "[SABBATH] sabbath_active=%s time_now_local=%s window_start_local=%s window_end_local=%s remaining_block_duration=%.1f",
                active,
                local_ref.isoformat(),
                start.isoformat(),
                end.isoformat(),
                remaining,
            )
            self._log_counter = 0
            self._last_active = active
        return active, start, end


def _log_build_info(sabbath_context: SabbathContext) -> None:
    logger.info(
        "[BUILD] git=%s phase=3d sabbath=%s",
        _git_short_sha(),
        sabbath_context.enabled,
    )


def _build_candidate_list(
    executor,
    engines,
    provider,
    symbols,
    timeframe,
    structure_score_threshold: float,
    profile_settings,
    market_settings,
    strike_tracker: StrikeTracker | None,
    now: datetime,
    allow_entries: bool = True,
) -> tuple[list[tuple[str, object, float, str]], bool]:
    snapshot_cache: dict[tuple[object, ...], object] = {}
    symbols = [symbol for symbol in symbols if symbol in engines]
    # Single-ticker safety: if any symbol has working orders (entry bracket pending) or synthetic protection
    # armed, stick to that symbol and avoid placing new entry orders on other symbols.
    if executor and hasattr(executor, "_fetch_symbol_state") and hasattr(executor, "_has_active_orders_or_position"):
        active_order_symbols: list[str] = []
        for symbol in symbols:
            try:
                state = executor._fetch_symbol_state(symbol)
            except Exception as e:
                logger.error(f"Failed to fetch symbol state for {symbol}: {e}")
                continue
            if not state:
                continue
            pos_size = state.get("position_shares", 0)
            if abs(pos_size) > 0:
                # Filled position handling is covered below via get_open_position_snapshot().
                continue
            if state.get("working_orders", 0) or state.get("synthetic_stop_armed"):
                active_order_symbols.append(symbol)
        if active_order_symbols:
            # [ANTIGRAVITY FIX] Multi-position enhancement:
            # If multi-position is enabled, we only block IF we have already reached max_concurrent.
            # Otherwise, we allow scanning to continue.
            # [ANTIGRAVITY FIX] Robust multi-position check
            multi_enabled = False
            if profile_settings:
                multi_enabled = bool(getattr(profile_settings, "multi_position_enabled", False))
            if not multi_enabled:
                runtime = getattr(executor, "runtime", None)
                multi_enabled = bool(getattr(runtime, "multi_position_enabled", False))
            
            max_concurrent = 1
            if profile_settings:
                 max_concurrent = int(getattr(profile_settings, "max_concurrent_positions", 1) or 1)
            else:
                 max_concurrent = int(getattr(runtime, "max_concurrent_positions", 1) or 1)
            max_concurrent = max(1, max_concurrent)
            
            if len(active_order_symbols) > 1:
                logger.error(
                    "[GUARD] Multiple symbols have working orders/synthetic stops; refusing new entries until cleared: %s",
                    ", ".join(active_order_symbols),
                )
            
            # Still stick to the campaign symbol if multi-pos is disabled
            if not multi_enabled:
                if not allow_entries:
                    logger.info(
                        "[SABBATH] working orders present on %s; blocking new entries/decisions until sabbath ends",
                        active_order_symbols[0],
                    )
                    return [], True
                logger.info(
                    "[STATE] Skipping universe scan: sticking to symbol with working orders: %s",
                    ", ".join(active_order_symbols),
                )
                # Build only the active campaign candidate
                symbol = active_order_symbols[0]
                try:
                    snap = _fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings)
                    return [(symbol, snap, 0.0, "active campaign")], True
                except Exception:
                    return [], True
            else:
                logger.info(
                    "[STATE] Symbols with working orders: %s (continuing scan for other slots)",
                    ", ".join(active_order_symbols),
                )
    if executor:
        open_symbols: list[str] = []
        for symbol in symbols:
            pos = executor.get_open_position_snapshot(symbol)
            if pos and abs(pos.get("size", 0)) > 0:
                # [ANTIGRAVITY FIX] Ignore dust so bot doesn't get stuck managing $0.15 positions
                if pos.get("is_dust", False):
                    logger.info(f"[DUST] Ignoring {symbol} position (size={pos.get('size')}) to allow other trades")
                    continue
                open_symbols.append(symbol)
        
        # Build position candidates first
        position_candidates: list[tuple[str, object, float, str]] = []
        for symbol in open_symbols:
            try:
                snapshot = _fetch_snapshot(
                    provider,
                    snapshot_cache,
                    symbol,
                    timeframe,
                    profile_settings,
                    market_settings,
                )
                position_candidates.append((symbol, snapshot, 0.0, "existing position"))
            except Exception as exc:
                logger.info("[STRUCTURE] %s fetch failed during open position check; skipping (%s)", symbol, exc)

        if position_candidates:
            logger.info(
                "[STATE] Managing %s open position(s): %s",
                len(position_candidates),
                ", ".join(sym for sym, *_ in position_candidates),
            )
            
            # [ANTIGRAVITY FIX] If multi-position is enabled and we have slots, 
            # we want to continue to scanning to potentially enter a new symbol.
            # [ANTIGRAVITY FIX] Robust multi-position check
            multi_enabled = False
            if profile_settings:
                multi_enabled = bool(getattr(profile_settings, "multi_position_enabled", False))
            if not multi_enabled:
                runtime = getattr(executor, "runtime", None)
                multi_enabled = bool(getattr(runtime, "multi_position_enabled", False))
            
            max_concurrent = 1
            if profile_settings:
                 max_concurrent = int(getattr(profile_settings, "max_concurrent_positions", 1) or 1)
            else:
                 max_concurrent = int(getattr(runtime, "max_concurrent_positions", 1) or 1)
            max_concurrent = max(1, max_concurrent)
            
            if not multi_enabled or len(position_candidates) >= max_concurrent:
                return position_candidates, True

    if not allow_entries:
        return (position_candidates if 'position_candidates' in locals() and position_candidates else []), True

    candidates: list[tuple[str, object, float, str]] = (position_candidates if 'position_candidates' in locals() and position_candidates else [])
    best_score = 0.0
    for symbol in symbols:
        if strike_tracker:
            if strike_tracker.is_guard_skipped(symbol):
                remaining = strike_tracker.guard_cooldown_remaining(symbol)
                logger.info(
                    "[STATE] Skipping %s for %s cycles after guard block streak",
                    symbol,
                    remaining,
                )
                continue
            if strike_tracker.is_skipped(symbol):
                remaining = strike_tracker.cooldowns.get(symbol, 0)
                reason = strike_tracker.cooldown_reason(symbol) or "cooldown"
                logger.info(
                    "[COOLDOWN] skip symbol=%s remaining=%s reason=%s (excluded from candidates)",
                    symbol,
                    remaining,
                    reason,
                )
                continue
        state = None
        if executor:
            state = executor._fetch_symbol_state(symbol)
            if executor._has_active_orders_or_position(symbol, state):
                detail_parts: list[str] = []
                pos_size = state.get("position_shares", 0)
                if abs(pos_size) > 0:
                    detail_parts.append(f"position_size={pos_size}")
                working_count = state.get("working_orders", 0)
                if working_count:
                    statuses = "/".join(state.get("working_order_statuses", [])) or "unknown"
                    detail_parts.append(f"workingOrders={working_count} statuses={statuses}")
                if state.get("synthetic_stop_armed"):
                    detail_parts.append("synthetic_stop=armed")
                detail = " ".join(detail_parts) if detail_parts else "active orders/position"
                logger.info(
                    "[STATE] Skipping %s: %s",
                    symbol,
                    detail,
                )
                continue
        if not _is_market_open(symbol, now):
            logger.info("[STATE] Skipping %s: market currently closed", symbol)
            continue
        
        # Stagger requests to avoid hitting rate limits
        import time
        time.sleep(1.2)

        try:
            snapshot = _fetch_snapshot(
                provider,
                snapshot_cache,
                symbol,
                timeframe,
                profile_settings,
                market_settings,
            )
        except Exception as exc:
            logger.info("[STRUCTURE] %s fetch failed; skipping (%s)", symbol, exc)
            continue
        score, reason = engines[symbol].score_structure(snapshot)
        readiness, readiness_reason = engines[symbol].score_icc_readiness(snapshot)
        icc_score, icc_grade = engines[symbol].score_icc_grade(snapshot)
        watch_score, watch_grade, flip_watch = engines[symbol].score_icc_watch(snapshot)
        telemetry = engines[symbol].icc_gate_telemetry(snapshot) if hasattr(engines[symbol], "icc_gate_telemetry") else {}
        logger.info(
            "[STRUCTURE] %s selection_score=%.3f readiness=%.2f icc_score=%.2f icc_grade=%s watch_score=%.2f watch_grade=%s flip_watch=%s last_gate=%s since_sweep=%s since_cont=%s (%s; %s)",
            symbol,
            score,
            readiness,
            icc_score,
            icc_grade,
            watch_score,
            watch_grade,
            flip_watch,
            telemetry.get("last_gate_to_true"),
            _fmt_seconds(telemetry.get("time_since_sweep_s")),
            _fmt_seconds(telemetry.get("time_since_continuation_s")),
            reason,
            readiness_reason,
        )
        candidates.append((symbol, snapshot, score, reason))
        if score > best_score:
            best_score = score
    if not candidates:
        logger.info("[SELECT] No candidates built (threshold=%.2f)", structure_score_threshold)
        decision = stand_aside_decision("NONE", timeframe, "No candidates built")
        logger.info("Decision: %s", decision.summary())

        # [ANTIGRAVITY FIX] Do not flag as connection error just because candidates are empty.
        # If we had critical connection errors, they would likely be caught upstream or result in 0 successful fetches attempted.
        # But here 'continue' inside the loop might be due to 404s or other non-critical issues.
        # We'll treat this as "Success" (data_fetch_succeeded=True) to avoid endless restarting,
        # unless we want to implement a strict "active_symbols" count check.
        # For now, returning True prevents the false-positive restart loop.
        return [], True

    candidates.sort(key=lambda entry: entry[2], reverse=True)
    candidate_summary = ", ".join(f"{entry[0]}:{entry[2]:.3f}" for entry in candidates)
    logger.info(
        "[CYCLE] candidates=[%s] threshold=%.3f",
        candidate_summary,
        structure_score_threshold,
    )
    best_symbol = candidates[0][0]
    if best_score < structure_score_threshold:
        logger.info(
            "[SELECT] No symbol passed threshold=%.2f (best=%.3f). Standing aside this cycle.",
            structure_score_threshold,
            best_score,
        )
        reason = f"No symbol passed threshold={structure_score_threshold:.2f} (best={best_score:.3f})"
        decision = stand_aside_decision(best_symbol, timeframe, reason)
        logger.info("Decision: %s", decision.summary())
        return [], True  # Candidates built successfully but below threshold - NOT a connection error
    logger.info(
        "[SELECT] Active symbol: %s (score=%.3f threshold=%.2f)",
        best_symbol,
        best_score,
        structure_score_threshold,
    )
    return candidates, True  # Successfully built and filtered candidates


def _process_candidate_cycle(
    executor,
    engines,
    profile: BaseProfile,
    profile_settings: TradingProfileSettings,
    settings: Settings,
    strike_tracker: StrikeTracker | None,
    candidates: list[tuple[str, object, float, str]],
    stop_after_submit: bool = True,
) -> tuple[str | None, int, int, int]:
    attempts = 0
    blocked = 0
    skipped = 0
    success_symbol: str | None = None
    # [ANTIGRAVITY FIX] Removed global capital_exhausted guard.
    # The broker now handles balance checks per-decision, allowing symbol-specific
    # recovery and avoiding global deadlocks on small accounts.
    friction = FrictionModel(
        max_spread_bps=getattr(profile_settings, "pair_selector_max_spread_bps", 25.0),
        min_rr=0.4,
    )
    # [ANTIGRAVITY FIX] Unify symbol state scanning to avoid redundant calls and inconsistent results
    pending_entry_symbols: set[str] = set()
    open_position_symbols_list: list[str] = []
    
    if executor and hasattr(executor, "_fetch_symbol_state"):
        for sym in engines.keys():
            try:
                state = executor._fetch_symbol_state(sym)
                if not state:
                    continue
                
                # Check for position (with hold store fallback)
                pos_shares = abs(state.get("position_shares", 0))
                has_pos = pos_shares > 0
                if not has_pos and executor.position_hold_store:
                    has_pos = executor.position_hold_store.get(sym) is not None
                
                if has_pos:
                    # Ignore dust positions
                    if not state.get("is_dust", False):
                        open_position_symbols_list.append(sym)
                elif state.get("working_orders", 0) or state.get("synthetic_stop_armed"):
                    # Only pending entry if NO position
                    pending_entry_symbols.add(sym)
            except Exception as e:
                logger.error(f"Failed to scan state for {sym}: {e}")

    open_position_symbols = set(open_position_symbols_list)
    
    # [ANTIGRAVITY FIX] Robust multi-position check
    multi_enabled = False
    if executor and hasattr(executor, "profile"):
        multi_enabled = bool(getattr(executor.profile, "multi_position_enabled", False))
    if not multi_enabled:
        runtime = getattr(executor, "runtime", None) if executor else None
        multi_enabled = bool(getattr(runtime, "multi_position_enabled", False))
    
    try:
        if executor and hasattr(executor, "profile"):
             max_concurrent = int(getattr(executor.profile, "max_concurrent_positions", 1) or 1)
        else:
             max_concurrent = int(getattr(runtime, "max_concurrent_positions", 1) or 1)
    except Exception:
        max_concurrent = 1
    max_concurrent = max(1, max_concurrent)
    
    # ... position verification already handled in unified scan ...

    for symbol, snapshot, _, _ in candidates:
        logger.debug(f"Processing candidate loop for: '{symbol}'")
        attempts += 1
        if executor and hasattr(executor, "_fetch_symbol_state"):
            _log_state_snapshot(executor, symbol)
        open_pos = executor.get_open_position_snapshot(symbol) if executor else None
        
        # [ANTIGRAVITY FIX] Mask dust positions
        # Check 1: Broker flag
        if open_pos and open_pos.get("is_dust", False):
            logger.info(f"[DUST-BROKER] Masking dust {symbol} size={open_pos.get('size')}")
            open_pos = None
        # Check 2: Calculated Value < $1.00
        elif open_pos and snapshot and snapshot.candles:
            try:
                val = abs(float(open_pos.get("size", 0)) * float(snapshot.candles[-1].close))
                if val < 1.0:
                    logger.info(f"[DUST-CALC] Masking dust {symbol} value=${val:.4f}")
                    open_pos = None
            except Exception:
                pass

        # Update position metadata (htf_neutral_bars counter) for open positions
        if open_pos and executor and hasattr(executor, "update_position_metadata"):
            executor.update_position_metadata(symbol, snapshot)
            # Refresh position snapshot after metadata update
            open_pos = executor.get_open_position_snapshot(symbol)

        engine = engines[symbol]
        execution_capabilities = (
            executor.get_execution_capabilities(symbol)
            if executor and hasattr(executor, "get_execution_capabilities")
            else None
        )
        if execution_capabilities is None:
            execution_capabilities = {}
        else:
            execution_capabilities = dict(execution_capabilities)
        execution_capabilities["flip_allowed"] = bool(getattr(profile_settings, "flip_actions_enabled", False))
        try:
            decision = _engine_decide(
                engine,
                profile.candle_timeframe,
                open_pos,
                snapshot,
                execution_capabilities,
            )
        except Exception as e:
            logger.error(f"[Loop] Strategy decision failed for {symbol}: {e}")
            blocked += 1
            continue
        if executor and hasattr(executor, "should_block_for_hold"):
            hold_blocked, _, _ = executor.should_block_for_hold(symbol, decision, open_pos)
            if hold_blocked:
                blocked += 1
                continue
        if not executor:
            skipped += 1
        decision = validate_decision(decision, settings=settings, execution_capabilities=execution_capabilities)
        action = getattr(decision, "action", None)
        if action in {"enter_long", "enter_short"}:
            # Avoid multi-ticker entry order collisions: if another symbol has a pending entry campaign,
            # suppress new entries until it resolves (prevents accidental multi-symbol fills).
            if pending_entry_symbols:
                other_pending = sorted(sym for sym in pending_entry_symbols if sym != symbol)
                if other_pending:
                    blocked += 1
                    logger.info(
                        "[GUARD] Blocked new entry on %s: pending working orders on %s",
                        symbol,
                        ", ".join(other_pending),
                    )
                    continue

            # Single-position default: do not open a second symbol while another position is open.
            if not multi_enabled:
                # [ANTIGRAVITY FIX] Ignore dust positions when checking for concurrent usage
                other_positions = sorted(
                    sym for sym in open_position_symbols 
                    if sym != symbol 
                    and not (executor.get_open_position_snapshot(sym) or {}).get("is_dust", False)
                )
                if other_positions:
                    blocked += 1
                    logger.info(
                        "[GUARD] Blocked new entry on %s: existing position(s) on %s (multi_position_enabled=false)",
                        symbol,
                        ", ".join(other_positions),
                    )
                    continue

            # Multi-position mode: enforce a maximum concurrent positions limit.
            # [ANTIGRAVITY FIX] Filter out dust from slot count
            active_holds = {
                s for s in open_position_symbols 
                if not (executor.get_open_position_snapshot(s) or {}).get("is_dust", False)
            }
            slots = active_holds | set(pending_entry_symbols)
            if symbol not in slots and len(slots) >= max_concurrent:
                blocked += 1
                logger.info(
                    "[GUARD] Blocked new entry on %s: max_concurrent_positions=%s reached (open=%s pending=%s)",
                    symbol,
                    max_concurrent,
                    len(open_position_symbols),
                    len(pending_entry_symbols),
                )
                continue
        logger.info("Decision: %s", decision.summary())
        print(_format_decision(decision))
        if not executor:
            continue
        market_provider = getattr(engine, "market_provider", None)
        if market_provider is not None:
            friction_decision = friction.evaluate(market_provider, decision)
            if not friction_decision.allow:
                blocked += 1
                logger.info(
                    "[FRICTION] blocked %s reason=%s spread_bps=%s rr=%s",
                    symbol,
                    friction_decision.reason,
                    f"{friction_decision.spread_bps:.2f}" if friction_decision.spread_bps is not None else "n/a",
                    f"{friction_decision.rr:.2f}" if friction_decision.rr is not None else "n/a",
                )
                continue
        execution_result, execution_outcome = executor.execute_decision(decision)
        _handle_execution_result(execution_result, strike_tracker, execution_outcome)
        outcome_status = execution_outcome.status
        logger.info("[EXEC] %s outcome=%s reason=%s", symbol, outcome_status.value, execution_outcome.reason)
        if outcome_status == ExecutionOutcomeType.SUCCESS_SUBMITTED:
            success_symbol = symbol
            if action in {"enter_long", "enter_short"}:
                pending_entry_symbols.add(symbol)
            if stop_after_submit:
                break
        if outcome_status in {
            ExecutionOutcomeType.BLOCKED_EXISTING,
            ExecutionOutcomeType.BLOCKED_GUARD,
            ExecutionOutcomeType.BLOCKED_PDT,
            ExecutionOutcomeType.BLOCKED_PDT_EXIT,
        }:
            blocked += 1
            if (
                outcome_status == ExecutionOutcomeType.BLOCKED_GUARD
                and execution_outcome.reason
                and "capital exhausted" in execution_outcome.reason
            ):
                if executor:
                    setattr(executor, "capital_exhausted", True)
                logger.info("[GUARD] Capital exhausted; pausing further entry attempts this cycle.")
                break
            continue
        skipped += 1
    return success_symbol, attempts, blocked, skipped


def _resolve_active_symbol(
    executor,
    engines,
    provider,
    symbols,
    timeframe,
    structure_score_threshold: float,
    profile_settings,
    market_settings,
    strike_tracker: StrikeTracker | None = None,
    now: datetime | None = None,
):
    """Returns the symbol that should trade this cycle and its latest snapshot."""
    now = now or datetime.now(ZoneInfo("UTC"))
    snapshot_cache: dict[tuple[object, ...], object] = {}
    if executor:
        if hasattr(executor, "_fetch_symbol_state") and hasattr(executor, "_has_active_orders_or_position"):
            active_order_symbols: list[str] = []
            for symbol in symbols:
                try:
                    state = executor._fetch_symbol_state(symbol)
                except Exception as e:
                    logger.error(f"Failed to fetch symbol state for {symbol}: {e}")
                    continue
                if not state:
                    continue
                pos_size = state.get("position_shares", 0)
                if abs(pos_size) > 0:
                    continue
                if state.get("working_orders", 0) or state.get("synthetic_stop_armed"):
                    active_order_symbols.append(symbol)
            if active_order_symbols:
                if len(active_order_symbols) > 1:
                    logger.error(
                        "[GUARD] Multiple symbols have working orders/synthetic stops; refusing new entries until cleared: %s",
                        ", ".join(active_order_symbols),
                    )
                    return None, None
                symbol = active_order_symbols[0]
                try:
                    snapshot = _fetch_snapshot(
                        provider,
                        snapshot_cache,
                        symbol,
                        timeframe,
                        profile_settings,
                        market_settings,
                    )
                except Exception as exc:
                    logger.info(
                        "[STRUCTURE] %s fetch failed during working order check; skipping (%s)",
                        symbol,
                        exc,
                    )
                    return None, None
                logger.info("[STATE] Holding active campaign on %s (working orders present)", symbol)
                return symbol, snapshot
        for symbol in symbols:
            pos = executor.get_open_position_snapshot(symbol)
            if pos and abs(pos.get("size", 0)) > 0:
                try:
                    snapshot = _fetch_snapshot(
                        provider,
                        snapshot_cache,
                        symbol,
                        timeframe,
                        profile_settings,
                        market_settings,
                    )
                except Exception as exc:
                    logger.info(
                        "[STRUCTURE] %s fetch failed during open position check; skipping (%s)",
                        symbol,
                        exc,
                    )
                    return None, None
                logger.info("[STATE] Continuing existing position on %s", symbol)
                return symbol, snapshot
    if strike_tracker:
        strike_tracker.advance_cycle()
    best_score = 0.0
    best_symbol = None
    best_snapshot = None
    for symbol in symbols:
        if strike_tracker:
            if strike_tracker.is_guard_skipped(symbol):
                remaining = strike_tracker.guard_cooldown_remaining(symbol)
                logger.info(
                    "[STATE] Skipping %s for %s cycles after guard block streak",
                    symbol,
                    remaining,
                )
                continue
            if strike_tracker.is_skipped(symbol):
                remaining = strike_tracker.cooldowns.get(symbol, 0)
                logger.info(
                    "[STATE] Skipping %s for %s cycles after repeated risk vetoes",
                    symbol,
                    remaining,
                )
                continue
        if not _is_market_open(symbol, now):
            logger.info("[STATE] Skipping %s: market currently closed", symbol)
            continue
        try:
            snapshot = _fetch_snapshot(
                provider,
                snapshot_cache,
                symbol,
                timeframe,
                profile_settings,
                market_settings,
            )
        except Exception as exc:
            logger.info("[STRUCTURE] %s fetch failed; skipping (%s)", symbol, exc)
            continue
        score, reason = engines[symbol].score_structure(snapshot)
        readiness, readiness_reason = engines[symbol].score_icc_readiness(snapshot)
        icc_score, icc_grade = engines[symbol].score_icc_grade(snapshot)
        watch_score, watch_grade, flip_watch = engines[symbol].score_icc_watch(snapshot)
        telemetry = engines[symbol].icc_gate_telemetry(snapshot) if hasattr(engines[symbol], "icc_gate_telemetry") else {}
        logger.info(
            "[STRUCTURE] %s selection_score=%.3f readiness=%.2f icc_score=%.2f icc_grade=%s watch_score=%.2f watch_grade=%s flip_watch=%s last_gate=%s since_sweep=%s since_cont=%s (%s; %s)",
            symbol,
            score,
            readiness,
            icc_score,
            icc_grade,
            watch_score,
            watch_grade,
            flip_watch,
            telemetry.get("last_gate_to_true"),
            _fmt_seconds(telemetry.get("time_since_sweep_s")),
            _fmt_seconds(telemetry.get("time_since_continuation_s")),
            reason,
            readiness_reason,
        )
        if score > best_score:
            best_score = score
            best_symbol = symbol
            best_snapshot = snapshot
    if best_symbol is None or best_score < structure_score_threshold:
        logger.info(
            "[SELECT] No symbol passed threshold=%.2f (best=%.3f). Standing aside this cycle.",
            structure_score_threshold,
            best_score,
        )
        return None, None
    logger.info(
        "[SELECT] Active symbol: %s (score=%.3f threshold=%.2f)",
        best_symbol,
        best_score,
        structure_score_threshold,
    )
    return best_symbol, best_snapshot


def _handle_execution_result(
    result: ExecutionResult | None,
    strike_tracker: StrikeTracker | None,
    outcome: ExecutionOutcome | None = None,
) -> None:
    """Tracks strikes/cooldowns based on the latest execution outcome."""
    if not result or not strike_tracker:
        return
    if result.status == ExecutionStatus.RISK_SUPPRESSED:
        guard_triggered = strike_tracker.record_guard_block(result.symbol)
        if guard_triggered:
            logger.info(
                "[STATE] %s guard block: cooling for %s cycles after %s guard strikes",
                result.symbol,
                strike_tracker.guard_block_cooldown_cycles,
                strike_tracker.guard_block_threshold,
            )
        cooldown_triggered = strike_tracker.record_risk_suppression(result.symbol)
        if cooldown_triggered:
            logger.info(
                "[STATE] %s cooling for %s cycles after %s risk strikes",
                result.symbol,
                strike_tracker.cooldown_cycles,
                strike_tracker.max_consecutive,
            )
        return
    if result.status == ExecutionStatus.EXECUTED:
        reason = outcome.status.value if outcome else None
        strike_tracker.record_execution_success(result.symbol, reason)
        return
    if result.status in {
        ExecutionStatus.UNSUPPORTED_SYMBOL,
        ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG,
    }:
        logger.info("[GUARD] Unsupported symbol %s: %s", result.symbol, result.reason)


def run_bot(
    iterations: int | None = 20,
    skip_schedule: bool = False,
    sabbath_override: bool | None = None,
) -> None:
    """Runs a small sim loop so you can watch ideas roll in (None = infinite)."""
    settings = get_settings()
    setup_logging(settings.logging)

    profile_settings = settings.get_active_profile()
    profile_name = settings.app.profile_name
    crypto_only_profile = profile_settings.crypto_only
    auto_schedule_enabled = bool(getattr(profile_settings, "auto_schedule_enabled", False))
    sabbath_context = SabbathContext(profile_settings, sabbath_override)
    sabbath_context.log_startup()
    _log_build_info(sabbath_context)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    symbols = _resolve_symbol_universe(settings, profile_settings, profile_name)
    pair_selector = PairSelector(profile_settings) if getattr(profile_settings, "pair_selector_enabled", False) else None
    strike_tracker = StrikeTracker(
        settings.runtime.strike_max_consecutive,
        settings.runtime.strike_cooldown_cycles,
        settings.runtime.guard_block_threshold,
        settings.runtime.guard_block_cooldown_cycles,
    )
    execute_trades = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
    _confirm_trading_universe(symbols, profile_name, execute_trades)

    # If schedule sessions are configured, run the scheduled loop only in continuous mode.
    # (Scheduled mode is explicitly handled via `run_scheduled_bot()` / `--scheduled`.)
    if (
        settings.schedule.sessions
        and iterations is None
        and not skip_schedule
        and not os.getenv("BUG_BYPASS_SCHEDULE")
        and not auto_schedule_enabled
    ):
        run_scheduled_bot(sabbath_override=sabbath_override)
        return

    shared_ib = _maybe_connect_primary_ib(settings, execute_trades)
    provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib) if execute_trades else MockMarketDataProvider()
    ai_client = TradeSciAIClient(settings.ai)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
        )
        for symbol in symbols
    }

    executor = (
        build_exchange_broker(
            settings,
            profile_settings,
            shared_ib=shared_ib,
            allowed_symbols=set(symbols) if symbols else None,
        )
        if execute_trades
        else None
    )
    if executor and settings.runtime.cancel_orders_on_start:
        for symbol in symbols:
            executor.cancel_all_orders_for_symbol(symbol)
    if executor:
        for symbol in symbols:
            snapshot = _log_state_snapshot(executor, symbol)
            if not snapshot or settings.runtime.allow_inherited_position:
                continue
            if not _should_flatten_symbol(
                symbol,
                profile_name,
                settings.runtime,
                crypto_only_profile,
            ):
                logger.info(
                    "[GUARD] Skipping dev start flatten for %s (profile=%s)",
                    symbol,
                    profile_name,
                )
                continue
            logger.info(
                "[GUARD] Non-flat at dev start (%s, side=%s, size=%.2f, avg=%.4f)",
                symbol,
                snapshot.get("side"),
                snapshot.get("size"),
                snapshot.get("avg_price"),
            )
            executor.flatten_symbol(symbol)
            _log_state_snapshot(executor, symbol)

    poll_interval = profile_settings.market_poll_interval_seconds
    decision_interval = profile_settings.ai_decision_interval_seconds

    # CCXT Override: poll faster for live crypto markets
    _prov = os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider
    _alt_mk = os.getenv("ALTERNATIVE_MARKET_DATA") or settings.market.alternative_market_data
    _alt_br = os.getenv("ALTERNATIVE_BROKER") or settings.market.alternative_broker
    if _prov == "alternative" and ("coinbase" in _alt_mk or "ccxt" in _alt_br):
        poll_interval = 2
        decision_interval = 5
        logger.info("[OVERRIDE] CCXT/Coinbase active: polling every 2s")

    threshold = profile_settings.structure_score_threshold

    logger.info(
        "[STATE] structure_score_threshold=%.3f profile='%s'",
        threshold,
        profile_name,
    )
    next_decision_in = 0

    logger.info(
        "Starting simulation: profile=%s symbols=%s timeframe=%s",
        profile_name,
        ", ".join(symbols),
        profile_settings.candle_timeframe,
    )

    last_auto_mode: str | None = None
    last_holdings_log_ts = 0.0
    last_capital_check_ts = 0.0
    consecutive_error_iterations = 0
    loop_iter = itertools.count() if iterations is None else range(iterations)
    start_ts = time.time()
    try:
        for _ in loop_iter:
            now = datetime.now(ZoneInfo("UTC"))
            if executor:
                executor.refresh_account_summary()
                reason = _auto_restart_reason(
                    settings=settings,
                    start_ts=start_ts,
                    shared_ib=shared_ib,
                    executor=executor,
                    consecutive_errors=consecutive_error_iterations,
                )
                if reason:
                    _trigger_auto_restart(reason)
                now_ts = time.time()
                if now_ts - last_holdings_log_ts >= 5.0:
                    _log_holdings_snapshot(executor, reason="heartbeat")
                    last_holdings_log_ts = now_ts
                
                # [ANTIGRAVITY] Periodic Capital Check (15m)
                if now_ts - last_capital_check_ts >= 900.0:
                    try:
                         # Force a fresh check
                         cap = executor.get_liquid_capital()
                         logger.info(f"[HEARTBEAT] Capital available: ${cap:.2f}")
                         last_capital_check_ts = now_ts
                    except Exception as e:
                         logger.warning(f"[HEARTBEAT] Failed to check capital: {e}")
                         last_capital_check_ts = now_ts + 60 # Retry sooner on error
            if executor:
                for result in executor.evaluate_synthetic_stops(provider, profile_settings.candle_timeframe):
                    _handle_execution_result(result, strike_tracker)
            strike_tracker.advance_cycle()
            sabbath_active, _, _ = sabbath_context.evaluate(now)
            allow_entries = not sabbath_active
            if next_decision_in <= 0:
                active_symbols = symbols
                auto_mode: str | None = None
                if auto_schedule_enabled:
                    # [ANTIGRAVITY FIX] Override schedule for crypto-only mode to prevent blocking on equity hours
                    force_crypto = profile_settings.crypto_only
                    if force_crypto:
                        selection_symbols = [s for s in symbols if is_crypto(s)]
                        active_symbols = selection_symbols
                        auto_mode = "crypto"
                    else:
                        selection = select_auto_schedule_symbols(symbols, now)
                        active_symbols = selection.symbols
                        auto_mode = selection.mode
                    if auto_mode != last_auto_mode:
                        logger.info(
                            "[AUTO_SCHEDULE] mode=%s (equities during US market hours, crypto otherwise)",
                            auto_mode,
                        )
                        last_auto_mode = auto_mode
                    if executor:
                        for sym in symbols:
                            pos = executor.get_open_position_snapshot(sym)
                            if pos and abs(pos.get("size", 0)) > 0 and sym not in active_symbols:
                                active_symbols.append(sym)
                if pair_selector:
                    if not auto_schedule_enabled or auto_mode == "crypto":
                        selection = pair_selector.select(provider, active_symbols, now)
                        if selection.selected:
                            active_symbols = selection.selected
                else:
                    logger.debug("[LOOP_DEBUG] pair_selector is disabled or None; skipping extra selection")
                if executor and hasattr(executor, "list_open_position_symbols"):
                    for sym in executor.list_open_position_symbols():
                        if sym in engines and sym not in active_symbols:
                            active_symbols.append(sym)
                if sabbath_active:
                    if executor and hasattr(executor, "list_open_position_symbols"):
                        active_symbols = [sym for sym in executor.list_open_position_symbols() if sym in engines]
                    else:
                        active_symbols = [
                            sym
                            for sym in active_symbols
                            if executor
                            and (pos := executor.get_open_position_snapshot(sym))
                            and abs(pos.get("size", 0)) > 0
                        ]
                    if not active_symbols:
                        next_decision_in = decision_interval
                        time.sleep(poll_interval)
                        continue
                candidates, data_fetch_succeeded = _build_candidate_list(
                    executor,
                    engines,
                    provider,
                    active_symbols,
                    profile_settings.candle_timeframe,
                    profile_settings.structure_score_threshold,
                    profile_settings,
                    settings.market,
                    strike_tracker=strike_tracker,
                    now=now,
                    allow_entries=allow_entries,
                )
                if not candidates:
                    # Empty candidates can mean either:
                    # 1. All symbols failed to fetch (connection errors) - data_fetch_succeeded=False
                    # 2. Symbols fetched successfully but don't meet threshold - data_fetch_succeeded=True
                    # Only increment error counter for case 1 (actual connection failures)
                    if not data_fetch_succeeded:
                        consecutive_error_iterations += 1
                        if consecutive_error_iterations >= 3:
                            logger.warning(
                                "[AUTO_RESTART] Persistent connection errors detected (%d consecutive iterations)",
                                consecutive_error_iterations,
                            )
                    else:
                        # Data fetched successfully, just no qualified setups - reset counter
                        consecutive_error_iterations = 0
                    next_decision_in = decision_interval
                    time.sleep(poll_interval)
                    continue
                # Reset error counter when we successfully fetch at least one symbol
                consecutive_error_iterations = 0
                
                # [ANTIGRAVITY FIX] Strictly honor Sabbath: Do not even process candidates (which triggers flattening).
                # The user explicitly requested that NO actions (including flattening dust) occur during Sabbath.
                if sabbath_active:
                    logger.info("[SABBATH] Strict adherence active: Skipping candidate processing (no trades/flattens allowed).")
                    next_decision_in = decision_interval
                    time.sleep(poll_interval)
                    continue

                managing_positions = any(reason == "existing position" for _, _, _, reason in candidates)
                success_symbol, attempts, blocked, skipped = _process_candidate_cycle(
                    executor,
                    engines,
                    profile,
                    profile_settings,
                    settings,
                    strike_tracker,
                    candidates,
                    stop_after_submit=not managing_positions,
                )
                if success_symbol:
                    logger.info(
                        "[CYCLE] success=%s attempts=%s blocked=%s skipped=%s",
                        success_symbol,
                        attempts,
                        blocked,
                        skipped,
                    )
                next_decision_in = decision_interval
            else:
                next_decision_in -= poll_interval
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Shutting down simulation")
    except Exception as exc:
        logger.error("Fatal error in run_bot: %s", exc)
        raise SystemExit(1) from exc
    finally:
        if executor:
            if settings.runtime.cancel_orders_on_start:
                for symbol in symbols:
                    executor.cancel_all_orders_for_symbol(symbol)
            flattened_symbols = _flatten_symbols_at_shutdown(
                symbols,
                profile_name,
                settings.runtime,
                crypto_only_profile,
                executor,
            )
            for symbol in flattened_symbols:
                _log_state_snapshot(executor, symbol)
            if flattened_symbols:
                logger.info(
                    "Session '%s' complete; %s flat; no open orders.",
                    settings.app.profile_name,
                    ", ".join(flattened_symbols),
                )
            else:
                logger.info(
                    "Session '%s' complete; no symbols flattened (crypto-only or flatten disabled).",
                    settings.app.profile_name,
                )
            executor.summarize_pnl()


def run_scheduled_bot(sabbath_override: bool | None = None) -> None:
    """Runs the bot only during configured schedule windows so cron isn't required."""
    settings = get_settings()
    setup_logging(settings.logging)

    profile_settings = settings.get_active_profile()
    profile_name = settings.app.profile_name
    auto_schedule_enabled = bool(getattr(profile_settings, "auto_schedule_enabled", False))
    sabbath_context = SabbathContext(profile_settings, sabbath_override)
    sabbath_context.log_startup()
    tz = ZoneInfo(settings.schedule.timezone)
    symbols = _resolve_symbol_universe(settings, profile_settings, profile_name)
    pair_selector = PairSelector(profile_settings) if getattr(profile_settings, "pair_selector_enabled", False) else None
    crypto_only_profile = profile_settings.crypto_only
    scheduled_strike_tracker = StrikeTracker(
        settings.runtime.strike_max_consecutive,
        settings.runtime.strike_cooldown_cycles,
        settings.runtime.guard_block_threshold,
        settings.runtime.guard_block_cooldown_cycles,
    )
    execute_trades = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
    _confirm_trading_universe(symbols, profile_name, execute_trades)

    shared_ib = _maybe_connect_primary_ib(settings, execute_trades)
    provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib) if execute_trades else MockMarketDataProvider()
    ai_client = TradeSciAIClient(settings.ai)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
        )
        for symbol in symbols
    }

    executor = (
        build_exchange_broker(
            settings,
            profile_settings,
            shared_ib=shared_ib,
            allowed_symbols=set(symbols) if symbols else None,
        )
        if execute_trades
        else None
    )

    poll_interval = profile_settings.market_poll_interval_seconds
    decision_interval = profile_settings.ai_decision_interval_seconds

    # CCXT Override: poll faster for live crypto markets
    _prov = os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider
    _alt_mk = os.getenv("ALTERNATIVE_MARKET_DATA") or settings.market.alternative_market_data
    _alt_br = os.getenv("ALTERNATIVE_BROKER") or settings.market.alternative_broker
    if _prov == "alternative" and ("coinbase" in _alt_mk or "ccxt" in _alt_br):
        poll_interval = 2
        decision_interval = 5
        logger.info("[OVERRIDE] CCXT/Coinbase active: polling every 2s")

    threshold = profile_settings.structure_score_threshold

    logger.info(
        "Scheduled mode: %s sessions in %s",
        len(settings.schedule.sessions),
        settings.schedule.timezone,
    )

    schedule_windows = [
        f"{sess.name} {sess.start}-{sess.end}" for sess in settings.schedule.sessions
    ]
    logger.info(
        "[STATE] Schedule (%s): %s",
        settings.schedule.timezone,
        ", ".join(schedule_windows) if schedule_windows else "no sessions configured",
    )
    logger.info(
        "[STATE] structure_score_threshold=%.3f profile='%s'",
        threshold,
        profile_name,
    )
    current_session_name = "scheduled"
    start_ts = time.time()
    try:
        if executor and settings.runtime.cancel_orders_on_start:
            for symbol in symbols:
                executor.cancel_all_orders_for_symbol(symbol)
                _log_state_snapshot(executor, symbol)
        last_auto_mode: str | None = None
        last_holdings_log_ts = 0.0
        consecutive_error_iterations = 0
        while True:
            now = datetime.now(tz)
            session = _current_session(now, settings.schedule.sessions, tz)
            if session:
                current_session_name = session["name"]
            if not session:
                next_start, next_session = _next_session_start(now, settings.schedule.sessions, tz)
                if not next_start or not next_session:
                    logger.info("[STATE] No upcoming sessions; idling")
                    time.sleep(poll_interval)
                    continue
                logger.info(
                    "[STATE] Next session '%s' starts at %s (%s)",
                    next_session.name,
                    next_start.time().isoformat(timespec="minutes"),
                    settings.schedule.timezone,
                )
                _sleep_until(
                    next_start,
                    settings.runtime.keep_alive_interval_seconds,
                    shared_ib,
                    logger,
                    settings,
                )
                continue
            end_ts = session["end"]
            if shared_ib and not shared_ib.isConnected():
                _reconnect_ib(shared_ib, settings, logger)
            if shared_ib and not shared_ib.isConnected():
                logger.warning(
                    "[GUARD] Cannot start session '%s': IBKR not connected; skipping this session",
                    session["name"],
                )
                next_start, _ = _next_session_start(datetime.now(tz), settings.schedule.sessions, tz)
                _sleep_until(
                    next_start,
                    settings.runtime.keep_alive_interval_seconds,
                    shared_ib,
                    logger,
                    settings,
                )
                continue
            logger.info(
                "Starting session '%s' until %s (%s)",
                session["name"],
                end_ts.time().isoformat(timespec="minutes"),
                settings.schedule.timezone,
            )

            next_decision_in = 0
            while datetime.now(tz) < end_ts:
                loop_now = datetime.now(tz)
                if executor:
                    executor.refresh_account_summary()
                    reason = _auto_restart_reason(
                        settings=settings,
                        start_ts=start_ts,
                        shared_ib=shared_ib,
                        executor=executor,
                        consecutive_errors=consecutive_error_iterations,
                    )
                    if reason:
                        _trigger_auto_restart(reason)
                    now_ts = time.time()
                    # Fixed heartbeat: 60s
                    if now_ts - last_holdings_log_ts >= 5.0:
                        _log_holdings_snapshot(executor, reason="heartbeat")
                        last_holdings_log_ts = now_ts
                sabbath_active, _, _ = sabbath_context.evaluate(loop_now)
                allow_entries = not sabbath_active
                if next_decision_in <= 0:
                    active_symbols = symbols
                    auto_mode: str | None = None
                    if auto_schedule_enabled:
                        selection = select_auto_schedule_symbols(
                            symbols,
                            loop_now.astimezone(ZoneInfo("UTC")),
                        )
                        active_symbols = selection.symbols
                        auto_mode = selection.mode
                        if auto_mode != last_auto_mode:
                            logger.info(
                                "[AUTO_SCHEDULE] mode=%s (equities during US market hours, crypto otherwise)",
                                auto_mode,
                            )
                            last_auto_mode = auto_mode
                        if executor:
                            for sym in symbols:
                                pos = executor.get_open_position_snapshot(sym)
                                if pos and abs(pos.get("size", 0)) > 0 and sym not in active_symbols:
                                    active_symbols.append(sym)
                    if pair_selector:
                        if not auto_schedule_enabled or auto_mode == "crypto":
                            selection = pair_selector.select(
                                provider,
                                active_symbols,
                                loop_now.astimezone(ZoneInfo("UTC")),
                            )
                            if selection.selected:
                                active_symbols = selection.selected
                    if executor and hasattr(executor, "list_open_position_symbols"):
                        for sym in executor.list_open_position_symbols():
                            if sym not in active_symbols:
                                if sym not in engines:
                                    logger.info(f"[DISCOVERY] Found inherited position in {sym}; initializing strategy engine.")
                                    engines[sym] = StrategyEngine(
                                        ai_client=ai_client,
                                        market_provider=provider,
                                        profile=profile_settings,
                                        symbol=sym,
                                    )
                                active_symbols.append(sym)
                    if sabbath_active:
                        if executor and hasattr(executor, "list_open_position_symbols"):
                            active_symbols = [sym for sym in executor.list_open_position_symbols() if sym in engines]
                        else:
                            active_symbols = [
                                sym
                                for sym in active_symbols
                                if executor
                                and (pos := executor.get_open_position_snapshot(sym))
                                and abs(pos.get("size", 0)) > 0
                            ]
                        if not active_symbols:
                            next_decision_in = decision_interval
                            time.sleep(poll_interval)
                            continue
                    candidates = _build_candidate_list(
                        executor,
                        engines,
                        provider,
                        active_symbols,
                        profile.candle_timeframe,
                        threshold,
                        profile_settings,
                        settings.market,
                        strike_tracker=scheduled_strike_tracker,
                        now=loop_now,
                        allow_entries=allow_entries,
                    )
                    if not candidates:
                        # No candidates means all symbols failed to fetch (connection errors)
                        consecutive_error_iterations += 1
                        if consecutive_error_iterations >= 3:
                            logger.warning(
                                "[AUTO_RESTART] Persistent connection errors detected (%d consecutive iterations)",
                                consecutive_error_iterations,
                            )
                        next_decision_in = decision_interval
                        time.sleep(poll_interval)
                        continue
                    # Reset error counter when we successfully fetch at least one symbol
                    consecutive_error_iterations = 0
                    managing_positions = any(reason == "existing position" for _, _, _, reason in candidates)
                    _process_candidate_cycle(
                        executor,
                        engines,
                        profile,
                        profile_settings,
                        settings,
                        scheduled_strike_tracker,
                        candidates,
                        stop_after_submit=not managing_positions,
                    )
                    next_decision_in = decision_interval
                else:
                    next_decision_in -= poll_interval
                time.sleep(poll_interval)

            if executor:
                flattened_symbols = _flatten_symbols_at_shutdown(
                    symbols,
                    profile_name,
                    settings.runtime,
                    profile_settings.crypto_only,
                    executor,
                )
                if flattened_symbols:
                    logger.info(
                        "[GUARD] intraday_flatten: closing symbols %s at session end",
                        ", ".join(flattened_symbols),
                    )
                    for symbol in flattened_symbols:
                        _log_state_snapshot(executor, symbol)
                    logger.info(
                        "Session '%s' complete; %s flat; no open orders.",
                        session["name"],
                        ", ".join(flattened_symbols),
                    )
                else:
                    logger.info(
                        "Session '%s' complete; no symbols flattened (crypto-only or flatten disabled).",
                        session["name"],
                    )
            else:
                logger.info("Session '%s' complete; waiting for next window", session["name"])
    except KeyboardInterrupt:
        logger.info("Shutting down scheduled run")
    except Exception as exc:
        logger.error("Fatal error in run_scheduled_bot: %s", exc)
        raise SystemExit(1) from exc
    finally:
        if executor:
            if settings.runtime.cancel_orders_on_start:
                for symbol in symbols:
                    executor.cancel_all_orders_for_symbol(symbol)
            flattened_symbols = _flatten_symbols_at_shutdown(
                symbols,
                profile_name,
                settings.runtime,
                crypto_only_profile,
                executor,
            )
            if flattened_symbols:
                logger.info(
                    "Session '%s' finalizing; %s flat; no open orders.",
                    current_session_name,
                    ", ".join(flattened_symbols),
                )
            else:
                logger.info(
                    "Session '%s' finalizing; no symbols flattened (crypto-only or flatten disabled).",
                    current_session_name,
                )
            executor.summarize_pnl()


def _format_decision(decision) -> str:
    """Formats a decision so humans can read it without scrolling JSON."""
    return (
        f"[SIM] {decision.symbol} | bias={decision.bias} | action={decision.action} | "
        f"entry={decision.entry_price or decision.entry_zone} | sl={decision.stop_loss} | tp={decision.take_profit} | "
        f"risk%={decision.risk_per_trade_pct} | maxpos%={decision.max_position_size_pct} | "
        f"urgency={decision.urgency} | notes={decision.notes[:120]}"
    )


def _is_market_open(symbol: str, now: datetime) -> bool:
    # [ANTIGRAVITY FIX] Treat all crypto/Coinbase Derivatives as 24/7 markets
    if is_crypto(symbol):
        return True

    metadata = SYMBOL_METADATA.get(symbol)
    if not metadata:
        logger.warning(f"[SCHEDULE-DEBUG] No metadata for {symbol}")
        return False
    # logger.info(f"[SCHEDULE-DEBUG] {symbol} Type={metadata.market_type} Asset={metadata.asset_class}")
    if metadata.market_type == MarketType.CRYPTO:
        return True
    hours = MARKET_HOURS.get(metadata.market_type)
    if not hours:
        return False
    if metadata.market_type == MarketType.FOREX:
        return _is_forex_open(now)
    tz = ZoneInfo(hours["timezone"])
    local = now.astimezone(tz)
    if metadata.market_type in {MarketType.US_EQUITY, MarketType.EU_EQUITY, MarketType.APAC_EQUITY}:
        if local.weekday() >= 5:
            return False
    open_hour, open_minute = map(int, hours["open"].split(":"))
    close_hour, close_minute = map(int, hours["close"].split(":"))
    open_dt = local.replace(
        hour=open_hour,
        minute=open_minute,
        second=0,
        microsecond=0,
    )
    close_dt = local.replace(
        hour=close_hour,
        minute=close_minute,
        second=0,
        microsecond=0,
    )
    if open_dt <= close_dt:
        return open_dt <= local < close_dt
    return local >= open_dt or local < close_dt


def _is_forex_open(now: datetime) -> bool:
    utc = now.astimezone(ZoneInfo("UTC"))
    cutoff = datetime_time(22, 0)
    current = utc.time()
    weekday = utc.weekday()
    if weekday == 5:  # Saturday
        return False
    if weekday == 6:  # Sunday
        return current >= cutoff
    if weekday == 4:  # Friday
        return current < cutoff
    return True


def _current_session(now: datetime, sessions, tz: ZoneInfo):
    for sess in sessions:
        start_h, start_m = map(int, sess.start.split(":"))
        end_h, end_m = map(int, sess.end.split(":"))
        start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start_dt <= now < end_dt:
            return {"name": sess.name, "end": end_dt}
    return None


def _next_session_start(now: datetime, sessions, tz: ZoneInfo):
    upcoming: list[tuple[datetime, object]] = []
    for sess in sessions:
        sh, sm = map(int, sess.start.split(":"))
        start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if start_dt <= now:
            start_dt = start_dt + timedelta(days=1)
        upcoming.append((start_dt, sess))
    if not upcoming:
        return None, None
    next_start, sess = min(upcoming, key=lambda pair: pair[0])
    return next_start, sess


def _sleep_until(
    target_time: datetime,
    keep_alive_interval: int,
    ib_client,
    logger: logging.Logger,
    settings: Settings | None = None,
) -> None:
    if not target_time:
        return
    tz = target_time.tzinfo
    now = datetime.now(tz)
    if now >= target_time:
        return
    if keep_alive_interval <= 0 or ib_client is None:
        remaining = (target_time - now).total_seconds()
        if remaining > 0:
            time.sleep(remaining)
        return
    while datetime.now(tz) < target_time:
        remaining = (target_time - datetime.now(tz)).total_seconds()
        chunk = min(keep_alive_interval, max(remaining, 0))
        if chunk <= 0:
            break
        time.sleep(chunk)
        try:
            ib_client.reqCurrentTime()
            logger.info("[KEEPALIVE] Pinged IBKR API")
        except Exception as exc:  # pragma: no cover
            logger.warning("[GUARD] KEEPALIVE: ping failed (%s); attempting reconnect...", exc)
            if settings is not None:
                _reconnect_ib(ib_client, settings, logger)


def _reconnect_ib(ib_client, settings: Settings, logger: logging.Logger) -> None:
    try:
        ib_client.disconnect()
    except Exception as e:
        logger.debug(f"[KEEPALIVE] Error during disconnect (continuing): {e}")
        pass
    time.sleep(2)
    time.sleep(2)

    # [ANTIGRAVITY FIX] Strict guard against IBKR connection in alternative mode
    # Even if we ended up here, we must not connect if mode is wrong.
    provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
    if provider == "alternative":
        logger.warning("[GUARD] _reconnect_ib blocked because provider=alternative")
        return

    try:
        ib_client.connect(
            settings.broker.host if settings.broker else "127.0.0.1",
            int(settings.broker.port) if settings.broker else 7497,
            clientId=int(getattr(settings.broker, "client_id", 101)) if settings.broker else 101,
            readonly=False,
        )
        if ib_client.isConnected():
            logger.info("[STATE] KEEPALIVE: IBKR reconnected successfully")
            return
    except Exception as exc:
        logger.warning("[GUARD] KEEPALIVE: reconnect failed (%s)", exc)
    if not ib_client.isConnected():
        logger.warning("[GUARD] KEEPALIVE: reconnect failed; will retry next tick")


def _auto_restart_reason(
    *,
    settings: Settings,
    start_ts: float,
    shared_ib,
    executor,
    consecutive_errors: int = 0,
) -> str | None:
    """Check if the bot should auto-restart due to errors or staleness.

    Args:
        settings: Bot configuration settings
        start_ts: Timestamp when bot started (to enforce min uptime)
        shared_ib: IBKR client connection (if available)
        executor: Broker executor (if available)
        consecutive_errors: Number of consecutive iterations with errors

    Returns:
        Restart reason string if restart should trigger, None otherwise
    """
    if not settings.runtime.auto_restart_on_error:
        return None
    now_ts = time.time()
    if now_ts - start_ts < settings.runtime.auto_restart_min_uptime_seconds:
        return None
    last_restart_ts = float(os.getenv("TRADEBOT_AUTO_RESTART_LAST_TS", "0") or 0)
    if settings.runtime.auto_restart_cooldown_seconds > 0:
        if now_ts - last_restart_ts < settings.runtime.auto_restart_cooldown_seconds:
            return None

    # Check for IBKR client disconnection (immediate restart trigger)
    if shared_ib and hasattr(shared_ib, "isConnected") and not shared_ib.isConnected():
        return "ibkr_disconnected"

    # Check for persistent connection errors (3+ consecutive iterations with errors)
    # This catches cases where isConnected() returns True but data fetches fail
    if consecutive_errors >= 3:
        return f"persistent_connection_errors count={consecutive_errors}"

    # Check for stale account summary (original staleness detection)
    if executor and hasattr(executor, "account_summary_age_seconds"):
        age = executor.account_summary_age_seconds()
        if age is None:
            if now_ts - start_ts >= settings.runtime.auto_restart_stale_seconds:
                return "account_summary_never_succeeded"
        elif age >= settings.runtime.auto_restart_stale_seconds:
            return f"account_summary_stale age={age:.0f}s"
    return None


def _trigger_auto_restart(reason: str) -> None:
    now_ts = int(time.time())
    count = int(os.getenv("TRADEBOT_AUTO_RESTART_COUNT", "0") or 0) + 1
    os.environ["TRADEBOT_AUTO_RESTART_LAST_TS"] = str(now_ts)
    os.environ["TRADEBOT_AUTO_RESTART_COUNT"] = str(count)
    logger.warning("[AUTO_RESTART] Triggered (%s). Restarting bot process now.", reason)
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _fmt_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    try:
        if value < 0:
            return "-"
        if value < 60:
            return f"{value:.0f}s"
        if value < 3600:
            return f"{value/60.0:.0f}m"
        return f"{value/3600.0:.1f}h"
    except Exception as e:
        logger.debug(f"Failed to format duration {value}: {e}")
        return "-"
