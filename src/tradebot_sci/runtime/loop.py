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
from datetime import datetime, timedelta, time as datetime_time, timezone
from zoneinfo import ZoneInfo
print("ANTIGRAVITY LOADED SRC/LOOP.PY")

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.broker.execution import ExecutionOutcomeType, ExecutionResult, ExecutionStatus
from tradebot_sci.config.loader import get_settings
from tradebot_sci.config.models import Settings
from tradebot_sci.logging.setup import setup_logging
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.runtime.universe import resolve_symbol_universe, instrument_classes_for_symbols
from tradebot_sci.runtime.provider_factory import build_exchange_broker, build_market_provider
from tradebot_sci.runtime.pair_selector import PairSelector
from tradebot_sci.runtime.friction import FrictionModel
from tradebot_sci.runtime.auto_schedule import select_auto_schedule_symbols
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.decisions import stand_aside_decision
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.market.symbols import AssetClass, MARKET_HOURS, MarketType, SYMBOL_METADATA, is_crypto
from tradebot_sci.broker.trade_result_store import TradeResultStore, TradeResult
from tradebot_sci.runtime.trackers import StrikeTracker
from tradebot_sci.runtime.sabbath import SabbathContext
from tradebot_sci.runtime.scheduling import (
    is_market_open,
    get_current_session,
    get_next_session_start,
)
from tradebot_sci.runtime.controller import RuntimeController
from tradebot_sci.runtime.cycle import (
    build_candidate_list,
    process_candidate_cycle,
    handle_execution_result,
)
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


def _maybe_connect_primary_ib(settings: Settings, execute_trades: bool, allowed_asset_classes: list[str] | None = None) -> object | None:
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
        
    # [ANTIGRAVITY] Asset Class Guard: Only connect if Forex or Equity/Metals are active
    if allowed_asset_classes:
        has_ib_class = any(ac in ("forex", "equity", "commodity") for ac in allowed_asset_classes)
        if not has_ib_class:
            logger.info("[IBKR] Skipping connection - no Forex or Equity symbols in active profile.")
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
    # Import moved to top of file
    symbols = resolve_symbol_universe(settings, profile_settings, profile_name)

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


# Snapshot fetching moved to cycle.py


# Sabbath logic moved to sabbath.py


# SabbathContext moved to sabbath.py


def _log_build_info(sabbath_context: SabbathContext) -> None:
    logger.info(
        "[BUILD] git=%s phase=3d sabbath=%s",
        _git_short_sha(),
        sabbath_context.enabled,
    )


# Candidate list building moved to cycle.py

def run_bot(
    iterations: int | None = None,
    sabbath_override: bool | None = None,
):
    settings = get_settings()
    setup_logging(settings.logging)
    profile_settings = settings.get_active_profile()
    profile_name = settings.app.profile_name
    auto_schedule_enabled = bool(getattr(profile_settings, "auto_schedule_enabled", False))
    sabbath_context = SabbathContext(profile_settings, sabbath_override)
    _log_build_info(sabbath_context)
    sabbath_context.log_startup()
    symbols = _resolve_symbol_universe(settings, profile_settings, profile_name)
    pair_selector = PairSelector(profile_settings) if getattr(profile_settings, "pair_selector_enabled", False) else None
    crypto_only_profile = profile_settings.crypto_only
    strike_tracker = StrikeTracker(
        settings.runtime.strike_max_consecutive,
        settings.runtime.strike_cooldown_cycles,
        settings.runtime.guard_block_threshold,
        settings.runtime.guard_block_cooldown_cycles,
    )
    execute_trades = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
    _confirm_trading_universe(symbols, profile_name, execute_trades)

    # Removed blocking run_scheduled_bot check here.
    # The main loop now handles per-symbol market hours filtering.

    allowed_asset_classes = instrument_classes_for_symbols(symbols) if symbols else []

    shared_ib = _maybe_connect_primary_ib(settings, execute_trades, allowed_asset_classes)
    provider = build_market_provider(
        settings, 
        profile_settings, 
        shared_ib=shared_ib,
        allowed_symbols=set(symbols) if symbols else None
    )
    ai_client = TradeSciAIClient(settings.ai)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    trade_results = TradeResultStore(os.path.join("data", "trade_results.json"))
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
            trade_results=trade_results,
        )
        for symbol in symbols
    }

    # [ANTIGRAVITY] Prominent Strategy & MOTD Display
    print("\n" + "="*60)
    motd_path = os.path.join(os.getcwd(), "Documentation", "motd.txt")
    if os.path.exists(motd_path):
        with open(motd_path, "r") as f:
            print(f.read())
    else:
        print("Welcome to Tradebot SCI! (Documentation/motd.txt not found)")
    print("="*60 + "\n")

    logger.info("[PHOENIX] === ACTIVE STRATEGIES SUMMARY ===")
    for sym, engine in engines.items():
        logger.info(f"[PHOENIX]   {sym.ljust(10)} -> Strategy: {engine._strategy.name.upper()}")
    logger.info("[PHOENIX] ==================================" + "\n")

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

    # [ANTIGRAVITY] Explicit profile log for UI parsing
    logger.info(f"[PROFILE] Active profile={profile_name}")
    
    logger.info(
        "Starting simulation: profile=%s symbols=%s timeframe=%s",
        profile_name,
        ", ".join(symbols),
        profile_settings.candle_timeframe,
    )

    controller = RuntimeController(settings, profile_settings)

    # Bridge logs to WS
    from tradebot_sci.runtime.cycle import handle_execution_result # reload check
    ws_handler = WSLoggingHandler(controller)
    ws_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(ws_handler)
    
    def on_subscribe(symbol, tf):
        logger.info(f"[WS] Subscription for {symbol} ({tf})")
        # Sync current state
        controller.broadcast_state(executor, force=True)
        # Push history
        hist = provider.get_latest_candles(symbol, tf, limit=200)
        if hist:
            formatted = [{"time": int(c.timestamp.timestamp()), "open": c.open, "high": c.high, "low": c.low, "close": c.close} for c in hist]
            controller.ws_server.broadcast_history_sync(symbol, tf, formatted)

    controller.start_ws_server()
    controller.ws_server.set_on_subscribe_callback(on_subscribe)

    last_auto_mode: str | None = None
    last_holdings_log_ts = 0.0
    last_capital_check_ts = 0.0
    consecutive_error_iterations = 0
    loop_iter = itertools.count() if iterations is None else range(iterations)
    start_ts = time.time()
    try:
        for _ in loop_iter:
            # [ANTIGRAVITY] Check for Halt Signal
            if controller.is_halted():
                logger.debug("[LOOP] Bot is HALTED via signal. Waiting...")
                time.sleep(poll_interval)
                continue

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
                
                # [ANTIGRAVITY] Periodic Capital Check (Increased frequency to 30s)
                if now_ts - last_capital_check_ts >= 30.0:
                    try:
                         # Force a fresh check
                         cap = executor.get_liquid_capital()
                         logger.info(f"[HEARTBEAT] Capital available: ${cap:.2f}")
                         last_capital_check_ts = now_ts
                    except Exception as e:
                         logger.warning(f"[HEARTBEAT] Failed to check capital: {e}")
                         last_capital_check_ts = now_ts + 60 # Retry sooner on error
            if executor:
                try:
                    for result in executor.evaluate_synthetic_stops(provider, profile_settings.candle_timeframe):
                        _handle_execution_result(result, strike_tracker)
                except Exception as e:
                    logger.error(f"[CRASH_GUARD] Error in evaluate_synthetic_stops: {e}", exc_info=True)
            strike_tracker.advance_cycle()
            
            # [ANTIGRAVITY FIX] Evaluate Sabbath Status ALWAYS (every loop tick)
            # This ensures we enter Sabbath mode immediately when the time comes,
            # regardless of whether a trading decision is pending.
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
                    logger.info("[LOOP_DEBUG] pair_selector is disabled or None; skipping extra selection")
                if executor and hasattr(executor, "list_open_position_symbols"):
                    for sym in executor.list_open_position_symbols():
                        if sym in engines and sym not in active_symbols:
                            active_symbols.append(sym)

                # [ANTIGRAVITY] Live Chart Sync: Ensure viewed symbols/timeframes are fetched
                if controller.ws_server:
                    for sub_sym, sub_tf in controller.ws_server.get_subscriptions():
                        if sub_sym in engines:
                            if sub_sym not in active_symbols:
                                active_symbols.append(sub_sym)
                            
                            if sub_tf != profile_settings.candle_timeframe:
                                try:
                                    fetch_snapshot(
                                        provider, 
                                        snapshot_cache, 
                                        sub_sym, 
                                        sub_tf, 
                                        profile_settings, 
                                        settings.market, 
                                        ws_controller=controller
                                    )
                                except Exception as e:
                                    logger.debug(f"[LOOP] UI fetch failed for {sub_sym} {sub_tf}: {e}")
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
                # [ANTIGRAVITY FIX] Filter by market hours (OANDA weekend halt protection)
                active_symbols = [s for s in active_symbols if is_market_open(s, now, settings=profile_settings)]
                if not active_symbols:
                    logger.info("[SCHEDULE] No symbols have open markets. Skipping cycle.")
                    next_decision_in = decision_interval
                    time.sleep(poll_interval)
                    continue

                candidates, data_fetch_succeeded = build_candidate_list(
                    executor,
                    engines,
                    provider,
                    active_symbols,
                    profile_settings.candle_timeframe,
                    profile_settings,
                    settings.market,
                    strike_tracker=strike_tracker,
                    now=now,
                    ws_controller=controller,
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
                
                # [ANTIGRAVITY FIX] Strictly honor Sabbath: 
                # Block BOTH entries and exits (Zero Action).
                if sabbath_active:
                    controller.broadcast_state(executor, force=True)
                    logger.info("[SABBATH] Strict adherence active: Skipping candidate processing.")
                    next_decision_in = decision_interval
                    time.sleep(poll_interval)
                    continue


                managing_positions = any(reason == "existing position" for _, _, _, reason in candidates)
                success_symbol, attempts, blocked, skipped = process_candidate_cycle(
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
                
                # [ANTIGRAVITY] AI Commentary: Update the UI with market insights
                try:
                    # Identify active strategy for context
                    active_strategy = "supply_demand"
                    if active_symbols:
                        first_engine = engines.get(active_symbols[0])
                        if first_engine and hasattr(first_engine, "_strategy"):
                            active_strategy = first_engine._strategy.name.lower()

                    # Build state context for AI
                    state_lines = [
                        f"Profile: {profile_name}",
                        f"Active Strategy: {active_strategy.upper()}",
                        f"Active Symbols: {', '.join(active_symbols)}",
                        f"Candidates Analyzed: {len(candidates)}",
                        f"Success: {success_symbol or 'none'}",
                        f"Blocked: {blocked}, Skipped: {skipped}",
                    ]
                    if executor:
                        cap = executor.get_liquid_capital()
                        state_lines.append(f"Available Capital: ${cap:.2f}")
                    
                    # Get recent logs for context (last 10 lines from this session)
                    recent_logs = []  # Could extract from ws_handler buffer
                    controller.broadcast_commentary(
                        state_context="\n".join(state_lines),
                        strategy_name=active_strategy,
                        recent_logs=recent_logs,
                        recent_errors=None
                    )
                except Exception as e:
                    logger.debug(f"[COMMENTARY] Trigger skipped: {e}")
                
                next_decision_in = decision_interval
            else:
                next_decision_in -= poll_interval
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Shutting down simulation")
    except Exception as exc:
        # [ANTIGRAVITY FIX] enhanced crash logging
        logger.critical(f"[FATAL] Bot process crashed: {exc}", exc_info=True)
        # Force flush to ensure log is written before death
        for handler in logger.handlers:
            handler.flush()
        if sys.stderr:
            print(f"[FATAL] {exc}", file=sys.stderr, flush=True)
            traceback.print_exc()
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

    controller = RuntimeController(settings, profile_settings)
    
    # Bridge logs to WS
    ws_handler = WSLoggingHandler(controller)
    ws_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(ws_handler)

    controller.start_ws_server()

    shared_ib = _maybe_connect_primary_ib(settings, execute_trades)
    provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib)
    ai_client = TradeSciAIClient(settings.ai)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    trade_results = TradeResultStore(os.path.join("data", "trade_results.json"))
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
            trade_results=trade_results,
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
            # [ANTIGRAVITY] Check for Halt Signal
            if controller.is_halted():
                logger.debug("[LOOP] Bot is HALTED via signal. Waiting...")
                time.sleep(poll_interval)
                continue

            now = datetime.now(tz)
            session = get_current_session(now, settings.schedule.sessions, tz)
            if session:
                current_session_name = session["name"]
            if not session:
                next_start, next_session = get_next_session_start(now, settings.schedule.sessions, tz)
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
                next_start, _ = get_next_session_start(datetime.now(tz), settings.schedule.sessions, tz)
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
                    candidates = build_candidate_list(
                        executor,
                        engines,
                        provider,
                        active_symbols,
                        profile.candle_timeframe,
                        profile_settings,
                        settings.market,
                        strike_tracker=scheduled_strike_tracker,
                        now=loop_now,
                        ws_controller=controller,
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
                    process_candidate_cycle(
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


# Scheduling helpers moved to scheduling.py




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
    except Exception:
        return "-"
class WSLoggingHandler(logging.Handler):
    """Bridges internal engine logs to the WebSocket UI."""
    def __init__(self, controller: RuntimeController):
        super().__init__()
        self.controller = controller

    def emit(self, record):
        try:
            msg = self.format(record)
            if self.controller.ws_server and any(marker in msg for marker in ["[STATE]", "[CYCLE]", "[RESULT]", "[AUTO-ENTRY]", "[ROBOCOP]", "[EXIT]", "[PROFILE]", "[HEARTBEAT]", "[DECISION]", "[STRUCTURE]"]):
                self.controller.ws_server.broadcast_log_sync(record.levelname, msg)
        except Exception:
            self.handleError(record)


def _engine_decide(engine, timeframe: str, open_position, snapshot, execution_capabilities: dict | None):
    # This remains for backward compatibility or direct engine calls
    return engine.decide(timeframe, open_position=open_position, snapshot=snapshot, execution_capabilities=execution_capabilities)

# Backward compatibility aliases for tests
def _build_candidate_list(*args, **kwargs):
    from tradebot_sci.runtime.cycle import build_candidate_list
    import datetime
    
    # Map legacy test calls (8 arguments) to new signature (12 arguments)
    if len(args) >= 8 and isinstance(args[5], (float, int)):
        # Old: (executor, engines, provider, symbols, timeframe, threshold, strike_tracker, now)
        executor, engines, provider, symbols, timeframe, threshold, strike_tracker, now = args[:8]
        # Mock profile_settings and market_settings
        from types import SimpleNamespace
        profile_settings = SimpleNamespace(structure_score_threshold=threshold, multi_position_enabled=False, max_concurrent_positions=1)
        market_settings = SimpleNamespace(max_candles=200)
        candidates, success = build_candidate_list(
            executor, engines, provider, symbols, timeframe, 
            profile_settings, market_settings, strike_tracker, now
        )
        return candidates
    return build_candidate_list(*args, **kwargs)
_process_candidate_cycle = process_candidate_cycle
_handle_execution_result = handle_execution_result
_is_market_open = is_market_open

def _is_sabbath_now(dt, profile_settings, override=None):
    from tradebot_sci.runtime.sabbath import SabbathContext
    active, end_ts, _ = SabbathContext(profile_settings, override).evaluate(dt)
    return active, end_ts

# Legacy helpers moved or removed
