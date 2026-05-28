# CODING RULE: Do NOT insert watermark tags (e.g. [AGENT_NAME], [AI FIX], etc.)
# into comments, logs, or print statements. Write clean, professional comments only.
# See AGENTS.md for full guidelines.

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

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.broker.execution import ExecutionOutcomeType, ExecutionResult, ExecutionStatus
from tradebot_sci import paths as _paths
from tradebot_sci.config.loader import get_settings, reload_settings
from tradebot_sci.config.models import Settings
from tradebot_sci.logging.setup import setup_logging
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.runtime.universe import resolve_symbol_universe, instrument_classes_for_symbols
from tradebot_sci.runtime.provider_factory import build_exchange_broker, build_market_provider
from tradebot_sci.runtime.pair_selector import PairSelector
from tradebot_sci.runtime.auto_schedule import select_auto_schedule_symbols
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.decisions import stand_aside_decision
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.market.symbols import AssetClass, MARKET_HOURS, MarketType, SYMBOL_METADATA, is_crypto
from tradebot_sci.broker.trade_result_store import TradeResultStore, TradeResult
from tradebot_sci.runtime.trackers import StrikeTracker
from tradebot_sci.runtime.sabbath import SabbathContext
from tradebot_sci.runtime.ledger_daemon import LedgerDaemon
from tradebot_sci.ai.seasoned_trader import SeasonedTraderDaemon
from tradebot_sci.broker.paper_broker import PaperBroker
from tradebot_sci.market.replay_provider import ReplayMarketProvider
from tradebot_sci.runtime.scheduling import (
    is_market_open,
    get_current_session,
    get_next_session_start,
    get_schedule_status,
)
from tradebot_sci.runtime.controller import RuntimeController
from tradebot_sci.runtime.cycle import (
    build_candidate_list,
    process_candidate_cycle,
    handle_execution_result,
)
logger = logging.getLogger(__name__)


def _log_holdings_snapshot(executor, *, reason: str, tag: str = "", strategy_variant: str | None = None) -> None:
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
        # Merge SL/TP/opened_at from position_hold_store when snapshot misses them
        hold_store = getattr(executor, "position_hold_store", None)
        if hold_store:
            record = hold_store.get(sym)
            if record:
                if not snap.get("stop_loss") and record.stop_loss:
                    snap["stop_loss"] = record.stop_loss
                if not snap.get("take_profit") and record.take_profit:
                    snap["take_profit"] = record.take_profit
                if not snap.get("opened_at") and record.opened_at:
                    snap["opened_at"] = record.opened_at
                if not snap.get("entry_price") and record.entry_price:
                    snap["entry_price"] = record.entry_price
                if not snap.get("strategy") and record.strategy:
                    snap["strategy"] = record.strategy
        if strategy_variant and not snap.get("strategy"):
            snap["strategy"] = strategy_variant
            
        if "entry_time" in snap:
            try:
                from datetime import datetime as dt, timezone
                entry_dt = dt.fromisoformat(str(snap["entry_time"]).replace("Z", "+00:00"))
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                now_utc = dt.now(timezone.utc)
                snap["age_seconds"] = max(0, (now_utc - entry_dt).total_seconds())
            except Exception:
                pass
                
        positions.append({"symbol": sym, **snap})
    
    total_pnl = sum(p.get("unrealized_pnl", 0.0) or 0.0 for p in positions)
    payload = {
        "reason": reason,
        "count": len(positions),
        "total_unrealized_pnl": total_pnl,
        "positions": positions,
    }
    logger.info("%s[HOLDINGS] %s", tag, json.dumps(payload, sort_keys=True))

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

    # Check 5-lane routing configurations
    lanes = [
        os.getenv("BROKER_FOREX", settings.market.primary_forex).lower(),
        os.getenv("BROKER_EQUITIES", settings.market.primary_equities).lower(),
        os.getenv("BROKER_FUTURES", settings.market.primary_futures).lower(),
        os.getenv("BROKER_METALS", settings.market.primary_metals).lower(),
        os.getenv("BROKER_CRYPTO", settings.market.primary_crypto).lower()
    ]
    is_routed_to_ibkr = "ibkr" in lanes
    
    if broker_mode not in ("primary", "hybrid") and market_mode not in ("primary", "hybrid") and not is_routed_to_ibkr:
        return None

    # Only connect IBKR if it is actually the designated 'primary' provider, or if it is routed
    prime_m = settings.market.primary_market_provider.lower()
    prime_b = settings.market.primary_broker.lower()
    
    if prime_m != "ibkr" and prime_b != "ibkr" and not is_routed_to_ibkr:
        logger.info(f"[IBKR] Skipping connection - primary provider/broker is {prime_m}/{prime_b} and IBKR not in routed lanes")
        return None
        
    # Asset Class Guard: Only connect if Forex or Equity/Metals are active
    if allowed_asset_classes:
        has_ib_class = any(ac in ("forex", "equity", "commodity") for ac in allowed_asset_classes)
        if not has_ib_class:
            logger.info("[IBKR] Skipping connection - no Forex or Equity symbols in active profile.")
            return None
    try:
        from ib_insync import IB  # type: ignore
    except Exception as exc:
        logger.warning("IBKR init failed for exchange_provider=primary; missing ib_insync: %s", exc)
        return None

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
                logger.warning("IBKR init failed for exchange_provider=primary after %d attempts; running in dry-run/disconnected mode: %s", max_retries, exc)
                return None

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


def _confirm_trading_universe(
    symbols: list[str],
    profile_name: str,
    execute_trades: bool,
    settings: Settings,
) -> None:
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
    provided_confirmation = os.getenv("TRADING_CONFIRMATION") or settings.market.trading_confirmation
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
        with open(confirm_file, "w", encoding="utf-8") as f:
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


def _preflight_broker_check(settings) -> None:
    """Verify at least one broker has valid API credentials before starting.
    
    Checks all supported brokers (OANDA, CCXT, IBKR, Gemini, Kraken, Paxos)
    for valid API keys. If none are configured, prints a clear error message
    and exits with code 2.
    """
    # [RULE] If live-trading is disabled, skip preflight API validation.
    if not getattr(settings.runtime, "execute_trades", False):
        logger.info("[PREFLIGHT] Live trading disabled: skipping broker credential validation.")
        return

    configured_brokers = []
    
    # OANDA — needs api_key + account_id
    if hasattr(settings, 'oanda') and settings.oanda.api_key and settings.oanda.account_id:
        configured_brokers.append(f"OANDA ({settings.oanda.environment})")
    
    # CCXT — needs api_key (from env or config)
    ccxt_key = os.getenv("CCXT_API_KEY", "")
    if ccxt_key:
        exchange = os.getenv("CCXT_EXCHANGE", "unknown")
        configured_brokers.append(f"CCXT/{exchange}")
    
    # Gemini — needs api_key
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        configured_brokers.append("Gemini")
    
    # IBKR — considered configured if shared_ib is connected, or if config has an account_id 
    # (even if it's DU1234567, since single-account setups default to it).
    if hasattr(settings, 'broker') and settings.broker:
        mode = "paper" if settings.broker.use_paper_trading else "live"
        
        # Check if IBKR was actually connected during initialization
        import sys
        # shared_ib is created right before this is called in loop.py, but it's local there.
        # However, we can check if it's enabled in the 5-lane or primary setup and not explicitly disabled.
        # For simplicity, we just check if it's explicitly set to simulate=False, or if execute_trades=True and it's routed.
        if settings.broker.execution_mode != "simulate":
            configured_brokers.append(f"IBKR ({mode})")
    
    # Kraken — needs api_key
    if hasattr(settings, 'kraken') and settings.kraken.api_key:
        configured_brokers.append("Kraken")
    
    # Paxos — needs api_key
    if hasattr(settings, 'paxos') and settings.paxos.api_key:
        configured_brokers.append("Paxos")
    
    if configured_brokers:
        logger.info("[PREFLIGHT] ✅ Broker(s) configured: %s", ", ".join(configured_brokers))
        return
    
    # No broker found — refuse to start
    banner = (
        "\n"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║  ❌  NO BROKER CONFIGURED — CANNOT START                    ║\n"
        "╠══════════════════════════════════════════════════════════════╣\n"
        "║                                                            ║\n"
        "║  The bot requires at least ONE broker with valid API keys.  ║\n"
        "║                                                            ║\n"
        "║  Supported brokers:                                        ║\n"
        "║    • OANDA  → Settings → Brokers → OANDA (Account + Key)   ║\n"
        "║    • Gemini → Settings → Brokers → CCXT (Gemini exchange)   ║\n"
        "║    • CCXT   → Settings → Brokers → CCXT (Any exchange)     ║\n"
        "║    • IBKR   → Settings → Brokers → IBKR (TWS/Gateway)      ║\n"
        "║    • Kraken → Settings → Brokers → Kraken                  ║\n"
        "║                                                            ║\n"
        "║  Quick start: Open the GUI, go to Settings → Brokers,      ║\n"
        "║  and enter your API credentials for any broker above.       ║\n"
        "║                                                            ║\n"
        "║  See: Documentation/HOW_TO_USE.md (Step 2)                 ║\n"
        "║  See: Documentation/RTFM/08_API_SETUP.md                   ║\n"
        "║                                                            ║\n"
        "╚══════════════════════════════════════════════════════════════╝\n"
    )
    try:
        print(banner)
    except UnicodeEncodeError:
        print(banner.encode('ascii', 'ignore').decode('ascii'))
    
    logger.critical("[PREFLIGHT] No broker configured. Exiting.")
    sys.exit(2)



def _run_heartbeat_cycle(
    executor,
    executor_real,
    executor_paper,
    provider,
    profile_settings,
    strike_tracker,
    settings,
    start_ts: float,
    shared_ib,
    consecutive_errors: int,
    last_holdings_log_ts: float,
    last_capital_check_ts: float,
) -> tuple[float, float]:
    """Run per-loop heartbeat: holdings snapshot, capital pulse, synthetic stops.

    Returns updated (last_holdings_log_ts, last_capital_check_ts).
    """
    if executor:
        executor.refresh_account_summary()

        # Auto-restart check (real broker only)
        if executor == executor_real:
            reason = _auto_restart_reason(
                settings=settings,
                start_ts=start_ts,
                shared_ib=shared_ib,
                executor=executor,
                consecutive_errors=consecutive_errors,
            )
            if reason:
                _trigger_auto_restart(reason)

        now_ts = time.time()
        if now_ts - last_holdings_log_ts >= 5.0:
            if executor == executor_paper:
                _log_holdings_snapshot(executor, reason="heartbeat", tag="[PAPER] ", strategy_variant=getattr(settings, 'strategy_variant', None))
            else:
                _log_holdings_snapshot(executor, reason="heartbeat", strategy_variant=getattr(settings, 'strategy_variant', None))
            last_holdings_log_ts = now_ts

        if now_ts - last_capital_check_ts >= 15.0:
            try:
                cap = executor.get_total_balance_value()
                executor.summarize_pnl() # Sync closed trades
                if executor == executor_paper:
                    logger.info(f"[PAPER] [HEARTBEAT] Capital available: ${cap:.2f}")
                else:
                    logger.info(f"[HEARTBEAT] Capital available: ${cap:.2f}")
                last_capital_check_ts = now_ts
            except Exception as e:
                logger.warning(f"[HEARTBEAT] Failed to check capital: {e}")
                last_capital_check_ts = now_ts + 30

    if executor:
        try:
            for result in executor.evaluate_synthetic_stops(
                provider, profile_settings.candle_timeframe
            ):
                _handle_execution_result(result, strike_tracker)
        except Exception as e:
            logger.error(
                f"[CRASH_GUARD] Error in evaluate_synthetic_stops: {e}",
                exc_info=True,
            )
    strike_tracker.advance_cycle()
    return last_holdings_log_ts, last_capital_check_ts


def _resolve_active_symbols(
    symbols: list[str],
    engines: dict,
    executor,
    executor_paper,
    provider,
    profile_settings,
    settings,
    controller,
    now: datetime,
    pair_selector,
    last_auto_mode: str | None,
    sabbath_active: bool,
) -> tuple[list[str], str | None, str | None]:
    """Determine which symbols to trade this cycle.

    Consolidates schedule evaluation, pair selection, open-position inclusion,
    WS subscription merging, and market-hours filtering.

    Returns (active_symbols, auto_mode, last_auto_mode).
    """
    active_symbols = list(symbols)
    auto_mode: str | None = None

    if pair_selector:
        selection = pair_selector.select(provider, active_symbols, now)
        if selection.selected:
            active_symbols = selection.selected
    else:
        logger.info("[LOOP_DEBUG] pair_selector is disabled or None; skipping extra selection")

    # Include symbols with open positions
    if executor and hasattr(executor, "list_open_position_symbols"):
        for sym in executor.list_open_position_symbols():
            if sym in engines and sym not in active_symbols:
                active_symbols.append(sym)

    # Live Chart Sync
    if controller.ws_server:
        snapshot_cache = {}
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
                            ws_controller=controller,
                        )
                    except Exception as e:
                        logger.debug(f"[LOOP] UI fetch failed for {sub_sym} {sub_tf}: {e}")

    # Sabbath restriction (no PaperBroker)
    if sabbath_active and (not executor_paper or executor != executor_paper):
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

    # Market hours filter (skip for paper trading and replay mode)
    _is_replay = hasattr(provider, 'replay_date') and provider.replay_date is not None
    if not (executor == executor_paper or _is_replay):
        symbols_with_positions = set()
        if executor:
            for sym in active_symbols:
                pos = executor.get_open_position_snapshot(sym)
                if pos and abs(pos.get("size", 0)) > 1e-8:
                    symbols_with_positions.add(sym)
        active_symbols = [
            s for s in active_symbols
            if s in symbols_with_positions or is_market_open(s, now, settings=profile_settings)
        ]

    return active_symbols, auto_mode, last_auto_mode


def run_bot(
    iterations: int | None = None,
    sabbath_override: bool | None = None,
    skip_schedule: bool = False,
):
    settings = get_settings()
    setup_logging(settings.logging)
    _preflight_broker_check(settings)

    # ── Display Message of the Day ──
    try:
        from tradebot_sci import paths as _paths
        motd_path = _paths.APP_DIR / "Documentation" / "motd.txt"
        if motd_path.is_file():
            motd_text = motd_path.read_text(encoding="utf-8").strip()
            logger.info("[MOTD] " + "═" * 50)
            for line in motd_text.splitlines():
                logger.info("[MOTD] %s", line)
            logger.info("[MOTD] " + "═" * 50)
    except Exception:
        pass  # MOTD is optional — never block startup

    profile_settings = settings.get_active_profile()
    profile_name = settings.app.profile_name
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
    execute_trades = settings.runtime.execute_trades
    _confirm_trading_universe(symbols, profile_name, execute_trades, settings)

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
    trade_results = TradeResultStore(str(_paths.DATA_DIR / "trade_results.json"))

    # [LEDGER] Select the correct log file for the daemon to scrape.
    # Priority: bot_stdout.log (launcher redirect — has [EXIT] lines in
    # human-readable format) > user-data tradebot.log > project-root log.
    # The project-root logs/tradebot.log is JSON-formatted and contains NO
    # [EXIT] lines, so it must only be a last-resort fallback.
    _ledger_log_candidates = [
        _paths.LOG_DIR / "bot_stdout.log",        # ← primary: launcher stdout capture
        _paths.LOG_DIR / "tradebot.log",           # ← user-data plaintext log
        _paths.APP_DIR / "logs" / "tradebot.log",  # ← last resort (often JSON)
    ]
    _ledger_log_path = str(_paths.LOG_DIR / "tradebot.log")  # default
    for _cand in _ledger_log_candidates:
        try:
            if _cand.exists() and _cand.stat().st_size > 0:
                _ledger_log_path = str(_cand)
                break  # use first existing, non-empty candidate
        except OSError:
            pass
    logger.info(f"[LEDGER] Using log source: {_ledger_log_path}")

    ledger = LedgerDaemon(
        log_path=_ledger_log_path,
        ledger_path=str(_paths.DATA_DIR / "ledger.json"),
        interval=60,
        lat=getattr(profile_settings, "sabbath_lat", 33.764),
        lon=getattr(profile_settings, "sabbath_lon", -84.386),
        tz_name=getattr(profile_settings, "sabbath_timezone", "America/New_York"),
        default_strategy=getattr(profile_settings, "strategy_variant", ""),
    )
    ledger.start()
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
            trade_results=trade_results,
            settings=settings,
        )
        for symbol in symbols
    }

    # Prominent Strategy & MOTD Display
    print("\n" + "="*60)
    motd_path = os.path.join(os.getcwd(), "Documentation", "motd.txt")
    if os.path.exists(motd_path):
        try:
            with open(motd_path, "r", encoding="utf-8") as f:
                print(f.read())
        except UnicodeEncodeError:
            # Fallback for Windows consoles that don't support UTF-8 stickers/emojis
            with open(motd_path, "r", encoding="utf-8") as f:
                content = f.read()
                print(content.encode('ascii', 'ignore').decode('ascii'))
        except Exception as e:
            logger.debug(f"[MINOVSKY] MOTD load failed: {e}")
    else:
        print("Welcome to Tradebot SCI! (Documentation/motd.txt not found)")
    print("="*60 + "\n")

    logger.info("[MINOVSKY] === ACTIVE STRATEGIES SUMMARY ===")
    for sym, engine in engines.items():
        logger.info(f"[MINOVSKY]   {sym.ljust(10)} -> Strategy: {engine._strategy.name.upper()}")
    logger.info("[MINOVSKY] ==================================" + "\n")

    executor_real = (
        build_exchange_broker(
            settings,
            profile_settings,
            shared_ib=shared_ib,
            allowed_symbols=set(symbols) if symbols else None,
            trade_results=trade_results,
        )
        if execute_trades
        else None
    )

    if executor_real:
        # ── Preflight Authorization Check ──
        # Force a connection test to ensure at least one underlying broker is authenticated.
        _auth_count = 0
        try:
            executor_real.refresh_account_summary()
            executor_real.get_liquid_capital()  # forces CCXT to fetch balance
        except Exception:
            pass

        if hasattr(executor_real, "brokers"):
            # Routed broker
            for _b in set(executor_real.brokers.values()):
                if type(_b).__name__ != "NoOpExchangeBroker":
                    if getattr(_b, "_authorized", True):
                        _auth_count += 1
        else:
            # Single broker
            if type(executor_real).__name__ != "NoOpExchangeBroker":
                if getattr(executor_real, "_authorized", True):
                    _auth_count += 1
        
        if _auth_count == 0:
            logger.critical("[PREFLIGHT] ❌ FATAL: All configured tracking brokers failed authentication (no API data). Halting bot.")
            sys.exit(2)

    # ── Paper Broker ──
    # Create PaperBroker if:
    #   (a) execute_trades is disabled (user wants paper/simulation mode), OR
    #   (b) Sabbath mode is enabled (needs paper fallback during Sabbath hours)
    executor_paper = None
    paper_ledger = None
    if not execute_trades or sabbath_context.enabled:
        paper_trade_results = TradeResultStore(str(_paths.DATA_DIR / "paper_trade_results.json"))
        executor_paper = PaperBroker(
            profile_settings,
            market_provider=provider,
            trade_results=paper_trade_results
        )
        if not execute_trades:
            logger.info("[PAPER] 📝 Paper Trading mode active (Live Trading disabled).")
        else:
            logger.info("[PAPER] Sabbath-mode Paper Broker initialized (standby).")
        # Separate paper ledger — never pollutes the live ledger
        paper_ledger = LedgerDaemon(
            log_path=_ledger_log_path,
            ledger_path=str(_paths.DATA_DIR / "paper_ledger.json"),
            interval=60,
            lat=getattr(profile_settings, "sabbath_lat", 33.764),
            lon=getattr(profile_settings, "sabbath_lon", -84.386),
            tz_name=getattr(profile_settings, "sabbath_timezone", "America/New_York"),
            default_strategy=getattr(profile_settings, "strategy_variant", ""),
        )
        # Override: paper ledger only processes [PAPER] lines (inverse of live)
        paper_ledger._paper_mode = True
        paper_ledger.start()
        logger.info(f"[PAPER] Paper ledger daemon started -> {_paths.DATA_DIR / 'paper_ledger.json'}")
    else:
        logger.info("[PAPER] Paper Broker disabled (Live Trading enabled, Sabbath not active).")

    # Initial Sabbath Check to set correct executor reference
    now_init = datetime.now(ZoneInfo("UTC"))
    sabbath_active_init, _, _ = sabbath_context.evaluate(now_init)
    
    # ── Replay provider for weekend paper trading ──
    provider_real = provider  # keep a reference to the real provider
    replay_provider = None    # lazily created on first Sabbath activation
    _replay_data_dir = _paths.APP_DIR / "data" / "forex_backtest"

    # Priority: if live trading is off, ALWAYS use paper broker
    if not execute_trades and executor_paper:
        executor = executor_paper
    elif sabbath_active_init and executor_paper:
        executor = executor_paper
    else:
        executor = executor_real

    # ── Startup Pending Order Sweep ──────────────────────────────────────────
    # Always cancel ALL pending orders on the OANDA account before the main
    # loop begins. This prevents stale LIMIT orders left by a previous pod
    # instance from silently filling and appearing as ghost trades with
    # strategy="unknown". Runs only in live mode (execute_trades=True).
    if execute_trades and executor_real:
        _oanda_broker = executor_real
        # If using a routed multi-broker, unwrap the OANDA sub-broker
        if hasattr(executor_real, "brokers"):
            for _b in set(executor_real.brokers.values()):
                if type(_b).__name__ == "OandaBroker":
                    _oanda_broker = _b
                    break
        if hasattr(_oanda_broker, "cancel_all_pending_orders_on_startup"):
            _oanda_broker.cancel_all_pending_orders_on_startup()

    # Legacy per-symbol cancel (controlled by CANCEL_ORDERS_ON_START env var)
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

    # If replay is active, ignore all other intervals and run at 1 candle / sec
    if replay_provider is not None:
        poll_interval = 1
        decision_interval = 1

    threshold = profile_settings.structure_score_threshold

    logger.info(
        "[STATE] structure_score_threshold=%.3f profile='%s'",
        threshold,
        profile_name,
    )
    next_decision_in = 0

    # Explicit profile log for UI parsing
    logger.info(f"[PROFILE] Active profile={profile_name}")
    
    logger.info(
        "Starting simulation: profile=%s symbols=%s timeframe=%s",
        profile_name,
        ", ".join(symbols),
        profile_settings.candle_timeframe,
    )

    controller = RuntimeController(settings, profile_settings)
    if executor_paper:
        executor_paper.controller = controller
    # Wire paper ledger to controller for PnL display
    # Paper mode activates via Sabbath OR when live trading is disabled.
    if (sabbath_context.enabled or not execute_trades) and paper_ledger:
        controller.paper_ledger = paper_ledger

    # Bridge logs to WS
    from tradebot_sci.runtime.cycle import handle_execution_result # reload check
    ws_handler = WSLoggingHandler(controller)
    ws_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(ws_handler)
    
    # Candle cache to avoid concurrent CCXT access.
    # The main trading loop and the WS tick handler share the same CCXT exchange
    # instance, which is NOT thread-safe.  Instead of making a live API call from
    # on_tick (which runs in the asyncio event loop), we cache the latest candle
    # per symbol and broadcast from cache.
    _candle_cache: dict = {}  # key: (symbol, tf) → Candle

    # Dedicated OANDA provider for chart tick fetches (forex).
    # The main OANDA provider MUST NOT be shared across threads.
    _forex_chart_provider = None
    try:
        from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
        # Use Oanda for charts even if Live Trading is disabled (Paper mode needs real data)
        # We check settings.oanda and fallback to env via factory if needed
        oanda_id = getattr(settings.oanda, "account_id", os.getenv("OANDA_ACCOUNT_ID", ""))
        oanda_key = getattr(settings.oanda, "api_key", os.getenv("OANDA_API_KEY", ""))
        oanda_env = getattr(settings.oanda, "environment", "practice")
        
        if oanda_key:
            _forex_chart_provider = OandaMarketDataProvider(oanda_id, oanda_key, oanda_env)
            logger.info("[WS] Created dedicated OANDA chart provider for forex ticks")
        else:
            logger.info("[WS] Dedicated OANDA chart provider skipped (No API key)")
    except Exception as e:
        logger.warning(f"[WS] Dedicated OANDA chart provider failed: {e}")

    # Dedicated CCXT provider for chart history fetches.
    # Uses PUBLIC Kraken (no API key needed) — supports all standard timeframes
    # including 4h, which Gemini lacks. The main trading loop's provider
    # MUST NOT be used from the WS handler because CCXT exchange objects
    # are not thread-safe.
    _chart_provider = None
    try:
        import ccxt
        from tradebot_sci.market.providers import CCXTMarketDataProvider
        _chart_exchange = ccxt.kraken({'enableRateLimit': True})
        _chart_exchange.load_markets()
        # Build symbol map for Kraken normalization (ZECUSD → ZEC/USD, etc.)
        _kraken_symbol_map = {}
        for m in _chart_exchange.markets:
            base_quote = m.replace("/", "")
            _kraken_symbol_map[base_quote] = m
            
        # [RESILIENCE] Use Oanda as a fallback for chart fetches too
        _chart_provider = CCXTMarketDataProvider(
            _chart_exchange, 
            _kraken_symbol_map, 
            fallback_provider=_forex_chart_provider
        )
        logger.info("[WS] Created dedicated chart provider (public Kraken — supports 4h) with Oanda fallback")
    except Exception as e:
        logger.warning(f"[WS] Dedicated chart provider failed, falling back to shared: {e}")
        _chart_provider = provider
        logger.warning(f"[WS] Dedicated OANDA chart provider failed: {e}")

    def on_subscribe(symbol, tf, since=None):
        from tradebot_sci.runtime.provider_factory import _get_asset_key
        asset_key = _get_asset_key(symbol)
        logger.info(f"[WS-DEBUG] Subscription for {symbol} ({tf}) | AssetKey: {asset_key}{f' | since={since}' if since else ''}")
        
        # Sync current state
        try:
            controller.broadcast_state(executor, force=True, executor_real=executor_real)
            # Push history using DEDICATED provider for crypto (thread-safe),
            # but use the main hybrid provider for forex (OANDA) since the
            # CCXT chart provider only has crypto data.
            # If we are in Replay Mode, we MUST use the replay provider to show
            # the simulation history instead of the live market flatline.
            if replay_provider is not None:
                chart_prov = replay_provider
            elif asset_key == "forex":
                chart_prov = _forex_chart_provider or _chart_provider or provider
            else:
                chart_prov = _chart_provider or provider

            if since:
                # ── Historical date navigation (calendar pick) ──
                # Calculate how many candles we need from 'since' epoch to now
                import re as _re
                tf_seconds = 300  # default 5m
                _m = _re.match(r"(\d+)([smhd])", tf.lower())
                if _m:
                    _v, _u = int(_m.group(1)), _m.group(2)
                    tf_seconds = _v * {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(_u, 60)
                
                now_epoch = int(datetime.now(ZoneInfo("UTC")).timestamp())
                candles_needed = max(100, min(5000, (now_epoch - int(since)) // max(tf_seconds, 1)))
                logger.info(f"[WS-CHART] Calendar navigation: {symbol} {tf} from epoch {since} ({candles_needed} candles)")
                
                # Try to use 'since' parameter for providers that support it
                hist = None
                since_ms = int(since) * 1000  # CCXT uses milliseconds
                
                # OANDA: use 'from' parameter
                if hasattr(chart_prov, '_normalize_symbol') and hasattr(chart_prov, '_map_timeframe'):
                    try:
                        import oandapyV20.endpoints.instruments as oanda_instruments
                        oanda_sym = chart_prov._normalize_symbol(symbol)
                        oanda_tf = chart_prov._map_timeframe(tf)
                        from_time = datetime.fromtimestamp(int(since), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        params = {
                            "from": from_time,
                            "count": candles_needed,
                            "granularity": oanda_tf,
                            "price": "M",
                            "alignmentTimezone": "UTC"
                        }
                        r = oanda_instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
                        chart_prov.client.request(r)
                        raw_candles = r.response.get("candles", [])
                        from tradebot_sci.market.models import Candle as _Candle
                        hist = []
                        for c in raw_candles:
                            mid = c.get("mid")
                            if not mid:
                                continue
                            raw_time = c["time"]
                            if "." in raw_time:
                                base, rest = raw_time.split(".", 1)
                                suffix = ""
                                if "Z" in rest:
                                    suffix = "Z"
                                    rest = rest.replace("Z", "")
                                raw_time = f"{base}.{rest[:6]}{suffix}"
                            if raw_time.endswith("Z"):
                                ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                            else:
                                ts = datetime.fromisoformat(raw_time)
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            hist.append(_Candle(
                                timestamp=ts,
                                open=float(mid["o"]),
                                high=float(mid["h"]),
                                low=float(mid["l"]),
                                close=float(mid["c"]),
                                volume=float(c.get("volume", 0))
                            ))
                        logger.info(f"[WS-CHART] OANDA historical fetch: {len(hist)} candles from {from_time}")
                    except Exception as e:
                        logger.warning(f"[WS-CHART] OANDA historical fetch failed, falling back to standard: {e}")
                        hist = None
                
                # CCXT fallback: use 'since' parameter  
                if hist is None and hasattr(chart_prov, '_exchange'):
                    try:
                        sym_norm = chart_prov._normalize_ccxt_symbol(symbol) if hasattr(chart_prov, '_normalize_ccxt_symbol') else symbol
                        ohlcv = chart_prov._exchange.fetch_ohlcv(sym_norm, tf, since=since_ms, limit=candles_needed)
                        from tradebot_sci.market.models import Candle as _Candle
                        hist = []
                        for row in ohlcv:
                            ts = datetime.fromtimestamp(row[0] / 1000.0, tz=timezone.utc)
                            hist.append(_Candle(
                                timestamp=ts,
                                open=float(row[1]), high=float(row[2]),
                                low=float(row[3]), close=float(row[4]),
                                volume=float(row[5])
                            ))
                        logger.info(f"[WS-CHART] CCXT historical fetch: {len(hist)} candles since {since}")
                    except Exception as e:
                        logger.warning(f"[WS-CHART] CCXT historical fetch failed, falling back to standard: {e}")
                        hist = None
                
                # Final fallback: just get latest candles with a large limit
                if hist is None:
                    hist = chart_prov.get_latest_candles(symbol, tf, limit=candles_needed)
            else:
                # ── Standard subscription (latest data) ──
                hist = chart_prov.get_latest_candles(symbol, tf, limit=500)

            logger.info(f"[WS-DEBUG] Received {len(hist) if hist else 0} candles for {symbol}")
            if hist:
                logger.info(f"[WS-DEBUG] {symbol} First: {hist[0].timestamp.isoformat()} | Last: {hist[-1].timestamp.isoformat()}")
                formatted = [
                    {
                        "time": int(c.timestamp.timestamp()),
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(getattr(c, "volume", 0) or 0)
                    }
                    for c in hist
                ]
                controller.ws_server.broadcast_history_sync(symbol, tf, formatted)
                # Populate cache with the latest candle
                _candle_cache[(symbol.upper(), tf.lower())] = hist[-1]
                logger.info(f"[WS-CACHE] Cached: {symbol} {tf} → {hist[-1].timestamp.isoformat()}")
                
                # Immediately push current health vitals, state, holdings, and commentary to the newly subscribed client
                controller.broadcast_health(force=True)
                controller.broadcast_holdings(executor, executor_real=executor_real)
                last_comm, _ = controller.get_last_commentary()
                if last_comm:
                    controller.ws_server.broadcast_commentary_sync(last_comm, datetime.now(timezone.utc).strftime("%I:%M %p"), 300)
            else:
                logger.warning(f"[WS] No history found for {symbol} ({tf})")
        except Exception as e:
            logger.error(f"[WS] Error during subscription sync for {symbol}: {e}", exc_info=True)

    def on_tick(symbol, tf):
        """Fetch fresh candle from dedicated chart provider for live chart updates."""
        from tradebot_sci.runtime.provider_factory import _get_asset_key
        key = (symbol.upper(), tf.lower())
        # Use main provider for forex (OANDA), dedicated CCXT for crypto
        # If we are in Replay Mode, we MUST use the replay provider.
        if replay_provider is not None:
            chart_prov = replay_provider
        elif _get_asset_key(symbol) == "forex":
            chart_prov = _forex_chart_provider or _chart_provider or provider
        else:
            chart_prov = _chart_provider or provider
        try:
            fresh = chart_prov.get_latest_candles(symbol, tf, limit=2)
            if fresh:
                candle = fresh[-1]
                _candle_cache[key] = candle
                controller.broadcast_candle(symbol, tf, candle)
                return
        except Exception as e:
            logger.warning(f"[WS-TICK] Live fetch failed for {symbol} {tf}: {e}")

        # Fallback to cache if live fetch fails
        cached = _candle_cache.get(key)
        if cached:
            controller.broadcast_candle(symbol, tf, cached)

    def update_candle_cache(symbol, tf, candle):
        """Called from the trading cycle to update the cache with fresh data."""
        _candle_cache[(symbol.upper(), tf.lower())] = candle

    controller.start_ws_server()
    controller.ws_server.set_on_subscribe_callback(on_subscribe)
    controller.ws_server.set_on_tick_callback(on_tick)

    # ── Manual Cash-Out from GUI ─────────────────────────────────────
    def on_flatten(symbol: str):
        """Handle manual position close from the GUI Cash Out button."""
        _exec = executor  # closure captures the live/paper executor reference
        if not _exec:
            logger.warning(f"[MANUAL EXIT] Cannot flatten {symbol} — no executor available")
            return
        try:
            logger.info(f"[MANUAL EXIT] ⚡ User cashed out {symbol} via GUI")
            _exec.flatten_symbol(symbol)
        except Exception as e:
            logger.error(f"[MANUAL EXIT] Failed to flatten {symbol}: {e}", exc_info=True)

    controller.ws_server.set_on_flatten_callback(on_flatten)

    # ── Remote Paper Trading Reset from GUI ──────────────────────────
    def on_reset_paper():
        """Handle paper trading reset from the GUI."""
        logger.info("[PAPER RESET] ⚡ User requested paper trading reset via GUI")
        init_bal = float(os.environ.get("PAPER_BALANCE", 10000.0))
        if executor_paper:
            executor_paper.reset(initial_balance=init_bal)
        if paper_ledger:
            paper_ledger.reset(initial_balance=init_bal)
        controller.broadcast_state(executor, force=True, executor_real=executor_real)
        controller.broadcast_holdings(executor, executor_real=executor_real)
        logger.info("[PAPER RESET] Successfully reset paper trading state.")

    controller.ws_server.set_on_reset_paper_callback(on_reset_paper)

    # Expose cache updater so the trading cycle can refresh the chart cache
    controller.update_candle_cache = update_candle_cache

    # ── Seasoned Trader Autopilot Daemon ──────────────────────────────────
    # Reads AI_SEASONED_TRADER_ENABLED from config.json (set by GUI toggle).
    # The GUI stores toggle keys in the active profile as lowercase, e.g.
    # config.profiles[active].ai_seasoned_trader_enabled
    # The daemon runs as a background thread, calling the LLM on its own interval.
    seasoned_daemon = None
    def _maybe_start_seasoned_daemon():
        nonlocal seasoned_daemon
        try:
            import json as _json
            _cfg_path = _paths.CONFIG_FILE
            if _cfg_path.exists():
                with open(_cfg_path, "r") as f:
                    _raw = _json.load(f)

                # The GUI stores Autopilot settings in the active profile (lowercase keys)
                # or as a fallback in the "ai" section or "global" section.
                active_name = _raw.get("active_profile", "")
                _prof = _raw.get("profiles", {}).get(active_name, {}) if active_name else {}
                _ai = _raw.get("ai", {})
                _global = _raw.get("global", {})

                # Check multiple locations (profile first, then ai section, then global)
                enabled = (
                    str(_prof.get("ai_seasoned_trader_enabled",
                        _ai.get("AI_SEASONED_TRADER_ENABLED",
                        _ai.get("ai_seasoned_trader_enabled",
                        _global.get("ai_seasoned_trader_enabled", "false"))))
                    ).lower() == "true"
                )

                # [RULE] Autopilot must NOT poll live data if Live Trading is disabled.
                if not execute_trades:
                    if seasoned_daemon and seasoned_daemon.running:
                        seasoned_daemon.stop()
                        logger.info("[AUTOPILOT] Seasoned Trader Daemon STOPPED (Live Trading disabled).")
                        seasoned_daemon = None
                    return

                if enabled:
                    autopilot_cfg = {
                        "AI_MONETARY_PATH": _prof.get("ai_monetary_path",
                            _ai.get("AI_MONETARY_PATH", "balanced")),
                        "AI_PERSONALITY": _prof.get("ai_personality",
                            _ai.get("AI_PERSONALITY", "veteran")),
                        "AI_AUTOPILOT_INTERVAL_MINS": _prof.get("ai_autopilot_interval_mins",
                            _ai.get("AI_AUTOPILOT_INTERVAL_MINS", 30)),
                    }
                    
                    if seasoned_daemon and seasoned_daemon.running:
                        # Ensure hot-reloaded parameters apply to daemon
                        if getattr(seasoned_daemon, "cfg", {}) != autopilot_cfg:
                            logger.info("[AUTOPILOT] Configuration changed! Restarting Seasoned Trader Daemon...")
                            seasoned_daemon.stop()
                            seasoned_daemon = None
                            
                    if seasoned_daemon is None or not seasoned_daemon.running:
                        seasoned_daemon = SeasonedTraderDaemon(
                            ai_client=ai_client,
                            config_payload=autopilot_cfg,
                            controller=controller,
                        )
                        seasoned_daemon.start()
                        logger.info("[AUTOPILOT] 🤖 Seasoned Trader Daemon STARTED (interval=%sm)", autopilot_cfg["AI_AUTOPILOT_INTERVAL_MINS"])
                elif not enabled and seasoned_daemon and seasoned_daemon.running:
                    seasoned_daemon.stop()
                    logger.info("[AUTOPILOT] Seasoned Trader Daemon STOPPED (disabled by user).")
                    seasoned_daemon = None
        except Exception as e:
            logger.warning(f"[AUTOPILOT] Failed to check/start Seasoned Trader: {e}")

    _maybe_start_seasoned_daemon()

    last_auto_mode: str | None = None
    last_holdings_log_ts = 0.0
    last_capital_check_ts = 0.0
    consecutive_error_iterations = 0
    # Continuous mode: GUI toggle (profile_settings.continuous_mode) OR CLI --continuous (iterations=None)
    if iterations is None or getattr(profile_settings, 'continuous_mode', False):
        loop_iter = itertools.count()
        logger.info("[LOOP] Continuous mode ENABLED — running indefinitely")
    else:
        loop_iter = range(iterations)
        logger.info("[LOOP] Fixed iteration mode — %d iterations", iterations)
    start_ts = time.time()
    
    # Hot-Reload State
    config_path = _paths.CONFIG_FILE
    last_config_mtime = config_path.stat().st_mtime if config_path.exists() else 0

    # UI Settings for Paper Trading
    paper_sim_enabled = True
    paper_replay_mode = False
    paper_synthetic_mode = False
    sabbath_replay_mode = True
    paper_eval_mode = False
    paper_eval_target_pct = 8.0
    paper_eval_daily_loss_pct = 5.0
    paper_eval_max_loss_pct = 10.0
    
    eval_state_path = _paths.DATA_DIR / "eval_state.json"
    eval_initial_balance = None
    eval_day_start_balance = None
    eval_last_day = None
    try:
        if eval_state_path.exists():
            import json
            with open(eval_state_path, "r") as f:
                _es = json.load(f)
                eval_initial_balance = _es.get("eval_initial_balance")
                eval_day_start_balance = _es.get("eval_day_start_balance")
                eval_last_day_str = _es.get("eval_last_day")
                if eval_last_day_str:
                    eval_last_day = datetime.fromisoformat(eval_last_day_str).date()
    except Exception as e:
        logger.warning(f"[EVAL] Failed to load eval state: {e}")

    def _update_paper_settings():
        nonlocal paper_sim_enabled, paper_replay_mode, paper_synthetic_mode, sabbath_replay_mode
        nonlocal paper_eval_mode, paper_eval_target_pct, paper_eval_daily_loss_pct, paper_eval_max_loss_pct
        import json
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    _raw = json.load(f)
                    _p = _raw.get("paper", {})
                    _s = _raw.get("safety", {})
                    paper_sim_enabled = _p.get("enabled", True)
                    paper_replay_mode = _p.get("replay_mode", False)
                    paper_synthetic_mode = _p.get("synthetic_mode", False)
                    sabbath_replay_mode = _s.get("sabbath_replay_mode", True)
                    paper_eval_mode = str(_p.get("eval_mode", "false")).lower() == "true"
                    paper_eval_target_pct = float(_p.get("eval_target_pct", 8.0))
                    paper_eval_daily_loss_pct = float(_p.get("eval_daily_loss_pct", 5.0))
                    paper_eval_max_loss_pct = float(_p.get("eval_max_loss_pct", 10.0))
                    
                    # Sync UI balance to os.environ so PaperBroker can read it
                    os.environ["PAPER_BALANCE"] = str(_p.get("balance", 10000.0))

        except Exception as e:
            logger.warning(f"Failed to read raw config for paper settings: {e}")

    _update_paper_settings()

    # ── Health Monitor: Boot events ──
    controller.health_monitor.add_event(f"Bot started — profile: {profile_name}", "info")
    controller.health_monitor.record_config(True, profile_name)
    if executor:
        controller.health_monitor.record_broker(True, broker_name=getattr(executor, 'name', 'OANDA'))

    try:
        for _ in loop_iter:

            # Hot-Reload Check
            try:
                if config_path.exists():
                    current_mtime = config_path.stat().st_mtime
                    if current_mtime > last_config_mtime:
                        last_config_mtime = current_mtime
                        logger.info("[HOT-RELOAD] Detected configuration change. Reloading...")
                        controller.health_monitor.add_event("Config hot-reloaded", "info")
                        
                        old_paper_eval_mode = paper_eval_mode
                        
                        # 1. Reload Settings
                        settings = reload_settings()
                        
                        # Fetch pure UI variables that aren't in Pydantic models
                        _update_paper_settings()
                        
                        if old_paper_eval_mode != paper_eval_mode:
                            logger.info(f"[EVAL] Prop Firm Mode changed to {paper_eval_mode}. Resetting anchors.")
                            eval_initial_balance = None
                            eval_day_start_balance = None
                            eval_last_day = None
                            try:
                                eval_state_path.unlink(missing_ok=True)
                            except:
                                pass

                        # Check Autopilot toggle on hot-reload
                        _maybe_start_seasoned_daemon()

                        # 2. Update Profile & Context
                        # We assume the profile name doesn't change mid-stream, just its content
                        profile_settings = settings.get_active_profile()
                        controller.settings = settings
                        controller.profile_settings = profile_settings
                        
                        # Sync Profile to Brokers (Hot-Reload)
                        if hasattr(executor, "sync_profile"):
                            executor.sync_profile(profile_settings)
                        
                        # Sync ALL settings to OS Environment so any code
                        # reading os.getenv() (UserConfig, Fee Shield, etc.)
                        # picks up changes immediately on hot-plug.
                        logger.info("[HOT-RELOAD] Syncing new settings to OS Environment...")
                        
                        # Dynamically sync every field from safety and performance
                        synced_count = 0
                        for section_name, section_obj in [("safety", settings.safety),
                                                          ("performance", settings.performance)]:
                            for field_name in section_obj.model_fields:
                                val = getattr(section_obj, field_name, None)
                                if val is None:
                                    continue
                                env_key = field_name.upper()
                                os.environ[env_key] = str(val).lower() if isinstance(val, bool) else str(val)
                                synced_count += 1
                        
                        # Profile-level keys consumed via os.getenv() elsewhere
                        profile_env_keys = {
                            "BREAKEVEN_TRAIL_PCT": str(getattr(profile_settings, "breakeven_trail_pct", 0.0)),
                            "TRAILING_STOP_ENABLED": str(getattr(profile_settings, "trailing_stop_enabled", False)).lower(),
                            "RISK_REWARD_RATIO": str(getattr(profile_settings, "risk_reward_ratio", 0.0)),
                            "ICC_ENTRY_SCORE_THRESHOLD": str(getattr(profile_settings, "structure_score_threshold", 75.0)),
                            "ICC_HIGH_SCORE_OVERRIDE_THRESHOLD": str(getattr(profile_settings, "high_score_override_threshold", 85.0)),
                        }
                        for key, val in profile_env_keys.items():
                            os.environ[key] = val
                        
                        logger.info(f"[HOT-RELOAD] Environment Synced: {synced_count} safety/performance keys + {len(profile_env_keys)} profile keys")

                        # 2b. Re-read Execute Trades toggle (master ON/OFF)
                        old_execute = execute_trades
                        execute_trades = settings.runtime.execute_trades
                        if execute_trades != old_execute:
                            logger.info(
                                "[HOT-RELOAD] 🔄 EXECUTE_TRADES changed: %s → %s",
                                old_execute, execute_trades,
                            )
                            if not execute_trades:
                                # Switched OFF → force Paper Broker immediately
                                if not executor_paper:
                                    logger.info("[HOT-RELOAD] Building Paper Broker dynamically...")
                                    paper_trade_results = TradeResultStore(str(_paths.DATA_DIR / "paper_trade_results.json"))
                                    executor_paper = PaperBroker(
                                        profile_settings,
                                        market_provider=provider,
                                        trade_results=paper_trade_results,
                                        controller=controller
                                    )
                                    if not paper_ledger:
                                        paper_ledger = LedgerDaemon(
                                            log_path=_ledger_log_path,
                                            ledger_path=str(_paths.DATA_DIR / "paper_ledger.json"),
                                            interval=60,
                                            lat=getattr(profile_settings, "sabbath_lat", 33.764),
                                            lon=getattr(profile_settings, "sabbath_lon", -84.386),
                                            tz_name=getattr(profile_settings, "sabbath_timezone", "America/New_York"),
                                            default_strategy=getattr(profile_settings, "strategy_variant", ""),
                                        )
                                        paper_ledger._paper_mode = True
                                        paper_ledger.start()
                                        if hasattr(controller, 'paper_ledger'):
                                            controller.paper_ledger = paper_ledger
                                        logger.info(f"[PAPER] Paper ledger daemon dynamically started -> {_paths.DATA_DIR / 'paper_ledger.json'}")
                                executor = executor_paper
                                logger.info("[HOT-RELOAD] Switched to Paper Broker (Live Trading disabled).")
                            else:
                                # Switched ON → restore real broker (unless Sabbath)
                                if not executor_real:
                                    logger.info("[HOT-RELOAD] Building Real Exchange Broker dynamically...")
                                    executor_real = build_exchange_broker(
                                        settings,
                                        profile_settings,
                                        shared_ib=shared_ib,
                                        allowed_symbols=set(symbols) if symbols else None,
                                        trade_results=trade_results,
                                    )
                                if executor_real and not sabbath_active:
                                    executor = executor_real
                                    logger.info("[HOT-RELOAD] Restored real Exchange Broker (Live Trading enabled).")

                        # 3. Resolve New Symbols
                        new_symbols = _resolve_symbol_universe(settings, profile_settings, profile_name)
                        
                        # 4. Update Engine Map
                        # Add new symbols
                        for sym in new_symbols:
                            if sym not in engines:
                                logger.info(f"[HOT-RELOAD] Initializing engine for NEW symbol: {sym}")
                                engines[sym] = StrategyEngine(
                                    ai_client=ai_client,
                                    market_provider=provider,
                                    profile=profile_settings,
                                    symbol=sym,
                                    trade_results=trade_results,
                                    settings=settings,
                                )
                            else:
                                # Sync profile to EXISTING engines
                                engines[sym].sync_profile(profile_settings, settings)
                        
                        # Remove dropped symbols (optional, but good for cleanup)
                        current_keys = list(engines.keys())
                        for sym in current_keys:
                            if sym not in new_symbols:
                                logger.info(f"[HOT-RELOAD] Removing engine for DROPPED symbol: {sym}")
                                del engines[sym]
                                
                        symbols = new_symbols
                        
                        # 5. Broadcast new state to UI
                        controller.broadcast_state(executor, force=True, executor_real=executor_real)
                        logger.info(f"[HOT-RELOAD] Complete. Active symbols: {len(symbols)}")
            except Exception as e:
                logger.error(f"[HOT-RELOAD] Failed to reload settings: {e}")

            # Check for Halt Signal
            if controller.is_halted():
                logger.debug("[LOOP] Bot is HALTED via signal. Waiting...")
                controller.health_monitor.set_halted(True)
                controller.broadcast_health()
                # Force a 1s sleep regardless of poll_interval to prevent CPU pin
                time.sleep(1.0 if poll_interval <= 0 else poll_interval)
                continue
            else:
                controller.health_monitor.set_halted(False)

            # ── 1. Base Schedule & Sabbath Evaluation ──
            now = datetime.now(ZoneInfo("UTC"))
            is_scheduled, paper_trade_off_hours, sessions = get_schedule_status(profile_name, now, settings)
            sabbath_active, _, _ = sabbath_context.evaluate(now)
            force_paper_broker = False

            # ── 2. Determine Execution State ──
            if not execute_trades:
                # [RULE 1] Live Trading DISABLED (Paper Mode)
                # Ignore the scheduler entirely; run if Paper Simulator is Enabled.
                is_scheduled = paper_sim_enabled
                # In paper-sim mode, we MUST use a safe market provider (Replay or NoOp).
                # Live exchange APIs are hard-blocked by the factory.
            else:
                # [RULE 2] Live Trading ENABLED
                # (a) If no schedules exist for the profile, default to 24/7 Live.
                if not sessions:
                    is_scheduled = True
                # (b) If off-hours, activate paper trading only if 'Paper Off-Hours' is enabled on the card.
                elif not is_scheduled and paper_trade_off_hours and paper_sim_enabled:
                    force_paper_broker = True

            # ── 3. Sabbath Master Override ──
            # Sabbath overrides everything, including the rules above.
            if sabbath_active:
                is_scheduled = False
                # Paper trading only runs during Sabbath if 'Sabbath Replay' is enabled.
                force_paper_broker = sabbath_replay_mode
                if not force_paper_broker:
                    # Explicitly silence any activity if Sabbath is active and Replay is disabled.
                    is_scheduled = False
                    logger.debug("[SABBATH] Entry suppressed (Replay mode disabled)")

            # ── 4. Replay Technical Override ──
            # Replay mode must always be 'scheduled' to process historical data.
            if replay_provider is not None:
                is_scheduled = True

            true_sabbath_active = sabbath_active

            # ── 5. Master Executor Selection ──
            # Fail-safe: Ensure the correct broker is active based on the rules evaluated above.
            # If live-trading is disabled, we MUST swap to paper broker.
            if not execute_trades or force_paper_broker or sabbath_active:
                if not executor_paper:
                    logger.info("[PAPER] 🛠️  Fail-safe: Initializing Paper Broker dynamically for simulation.")
                    paper_trade_results = TradeResultStore(str(_paths.DATA_DIR / "paper_trade_results.json"))
                    executor_paper = PaperBroker(
                        profile_settings,
                        market_provider=provider,
                        trade_results=paper_trade_results,
                        controller=controller
                    )
                    # Start paper ledger if missing
                    if not paper_ledger:
                        paper_ledger = LedgerDaemon(
                            log_path=_ledger_log_path,
                            ledger_path=str(_paths.DATA_DIR / "paper_ledger.json"),
                            interval=60,
                            lat=getattr(profile_settings, "sabbath_lat", 33.764),
                            lon=getattr(profile_settings, "sabbath_lon", -84.386),
                            tz_name=getattr(profile_settings, "sabbath_timezone", "America/New_York"),
                            default_strategy=getattr(profile_settings, "strategy_variant", ""),
                        )
                        paper_ledger._paper_mode = True
                        paper_ledger.start()
                        if hasattr(controller, 'paper_ledger'):
                            controller.paper_ledger = paper_ledger

                if executor != executor_paper:
                    logger.info("[PAPER] 🛡️  Fail-safe: Forcing Paper Broker activation for total isolation.")
                    executor = executor_paper
            elif executor_real and executor != executor_real:
                # Only restore real broker if we are NOT in Sabbath and NOT forcing paper AND execute_trades is True
                if not sabbath_active and not force_paper_broker and execute_trades:
                    logger.info("[LIVE] 🚀  Fail-safe: Restoring Real Broker connection.")
                    executor = executor_real

            # Activate replay mode for paper trading based on UI configuration.
            _want_replay = False
            if executor == executor_paper and paper_sim_enabled:
                if paper_replay_mode:
                    _want_replay = True
                elif true_sabbath_active and sabbath_replay_mode:
                    _want_replay = True
            if _want_replay and executor == executor_paper:
                want_synthetic = paper_synthetic_mode
                needs_rebuild = False
                
                if replay_provider is None:
                    needs_rebuild = True
                else:
                    is_synthetic = getattr(replay_provider, "__class__", None).__name__ == "SyntheticMarketProvider"
                    if want_synthetic and not is_synthetic:
                        needs_rebuild = True
                    elif not want_synthetic and is_synthetic:
                        needs_rebuild = True
                        
                if needs_rebuild:
                    if want_synthetic or _replay_data_dir.is_dir():
                        try:
                            if want_synthetic:
                                from tradebot_sci.market.synthetic_provider import SyntheticMarketProvider
                                replay_provider = SyntheticMarketProvider(symbols=symbols)
                                logger.info("[REPLAY] 💥 Synthetic Fire Mode Activated!")
                            else:
                                _rp = ReplayMarketProvider(
                                    data_dir=_replay_data_dir,
                                    symbols=symbols,
                                )
                                if _rp.replay_date is None:
                                    raise ValueError(f"No replay data found in {_replay_data_dir} for symbols {symbols}")
                                replay_provider = _rp
                            provider = replay_provider
                            # Give paper broker the replay provider for pricing
                            executor_paper.market_provider = provider
                            controller.replay_provider = replay_provider
                            # Swap engine trade_results → paper store so SAR sees paper losses
                            for eng in engines.values():
                                eng.trade_results = paper_trade_results
                                eng.market_provider = provider
                            logger.info("[REPLAY] Replay provider activated (engines swapped to paper store)")
                            # User requested a speed that doesn't feel like a broken standstill. 
                            poll_interval = 0
                            decision_interval = 0
                            logger.info("[REPLAY] Replay running at maximum CPU speed: poll=%ds decision=%ds", poll_interval, decision_interval)
                        except Exception as e:
                            logger.warning("[REPLAY] Failed to create replay provider: %s", e)
                # Flag for GUI: switch to paper ledger
                try:
                    Path("data/.sabbath_active").touch()
                except Exception:
                    pass
            elif not _want_replay:
                # Always restore real data provider if we don't want replay anymore
                if replay_provider is not None:
                    provider = provider_real
                    if executor_paper:
                        executor_paper.market_provider = provider_real
                        # Evict any cooldown entries written during replay so they
                        # cannot block re-entry in the live paper session.
                        if hasattr(executor_paper, "_exit_cooldowns"):
                            executor_paper._exit_cooldowns.clear()
                            logger.info("[REPLAY] Exit cooldowns cleared on replay teardown.")
                    controller.replay_provider = None
                    replay_provider = None
                    # Swap engines back to live data stream
                    for eng in engines.values():
                        eng.market_provider = provider_real
                        eng.trade_results = trade_results if executor != executor_paper else paper_trade_results
                    logger.info("[REPLAY] Replay provider deactivated, engines restored to live data stream")
                    # Restore default poll intervals
                    poll_interval = profile_settings.market_poll_interval_seconds
                    decision_interval = profile_settings.ai_decision_interval_seconds

                # Check if Sabbath/Off-Hours have ended and we need to drop the Paper Broker
                if executor_paper and executor == executor_paper and not (true_sabbath_active or force_paper_broker):
                    if execute_trades and executor_real:
                        logger.info("[SABBATH] Sabbath ended. Restoring real Exchange Broker connection.")
                        executor = executor_real
                        for eng in engines.values():
                            eng.trade_results = trade_results
                    elif not execute_trades:
                        logger.debug("[SABBATH] Sabbath ended, but Live Trading is off — staying on Paper Broker.")
                    
                # Flag for GUI: switch back to live ledger
                try:
                    Path("data/.sabbath_active").unlink(missing_ok=True)
                except Exception:
                    pass

            # ── Health Monitor: Record heartbeat at cycle start ──
            any_market_open = any(is_market_open(sym, now, settings=profile_settings) for sym in symbols)
            controller.health_monitor.record_heartbeat(sabbath_active)
            controller.health_monitor.set_market_hours((not sabbath_active) and any_market_open)
            if controller.health_monitor.is_warming_up:
                logger.info(f"[WARM-UP] Strategy warm-up active (Cycle {controller.health_monitor._cycle_count}/10). Suppressing health warnings.")

            last_holdings_log_ts, last_capital_check_ts = _run_heartbeat_cycle(
                executor=executor,
                executor_real=executor_real,
                executor_paper=executor_paper,
                provider=provider,
                profile_settings=profile_settings,
                strike_tracker=strike_tracker,
                settings=settings,
                start_ts=start_ts,
                shared_ib=shared_ib,
                consecutive_errors=consecutive_error_iterations,
                last_holdings_log_ts=last_holdings_log_ts,
                last_capital_check_ts=last_capital_check_ts,
            )
            # ── Prop Firm Evaluation Monitor ──
            # (Execute BEFORE broadcast so UI receives populated state dictionary immediately)
            if executor == executor_paper and paper_eval_mode and not controller.is_halted():
                try:
                    _eq = getattr(executor, "get_total_balance_value", lambda: 0.0)()
                    _changed = False
                    
                    if eval_initial_balance is None:
                        eval_initial_balance = _eq
                        eval_day_start_balance = _eq
                        eval_last_day = datetime.now().date()
                        _changed = True
                        
                    today = datetime.now().date()
                    if today != eval_last_day:
                        if eval_day_start_balance is not None and _eq > eval_day_start_balance:
                            # Prop firm resets only on new day
                            pass
                        eval_day_start_balance = _eq
                        eval_last_day = today
                        _changed = True

                    if _changed:
                        import json
                        try:
                            with open(eval_state_path, "w") as f:
                                json.dump({
                                    "eval_initial_balance": eval_initial_balance,
                                    "eval_day_start_balance": eval_day_start_balance,
                                    "eval_last_day": eval_last_day.isoformat() if eval_last_day else None
                                }, f)
                        except Exception as e:
                            logger.error(f"[EVAL] Failed to save state to disk: {e}")
                        
                    if eval_initial_balance > 0:
                        current_gain_pct = max(0.0, ((_eq - eval_initial_balance) / eval_initial_balance) * 100.0)
                        current_drawdown_pct = max(0.0, ((eval_initial_balance - _eq) / eval_initial_balance) * 100.0)
                        
                        daily_drawdown_pct = 0.0
                        if eval_day_start_balance > 0:
                            daily_drawdown_pct = max(0.0, ((eval_day_start_balance - _eq) / eval_day_start_balance) * 100.0)
                        
                        # Store metrics globally for GUI rendering
                        controller.eval_metrics = {
                            "gain_pct": current_gain_pct,
                            "target_pct": paper_eval_target_pct,
                            "daily_drawdown_pct": daily_drawdown_pct,
                            "daily_loss_pct": paper_eval_daily_loss_pct,
                            "current_drawdown_pct": current_drawdown_pct,
                            "max_loss_pct": paper_eval_max_loss_pct,
                            "initial_balance": eval_initial_balance,
                            "day_start_balance": eval_day_start_balance,
                            "current_balance": _eq
                        }
                except Exception as e:
                    logger.error(f"[EVAL] Error evaluating prop firm rules: {e}")

            # Push holdings + state + health to GUI via dedicated WS messages (not log parsing)
            controller.broadcast_holdings(executor, executor_real=executor_real)
            controller.broadcast_state(executor, executor_real=executor_real)
            controller.broadcast_health()
            
            if executor == executor_paper and paper_eval_mode and not controller.is_halted():
                try:
                    if eval_initial_balance is not None and eval_initial_balance > 0:
                        
                        failed = False
                        reason = ""
                        
                        if current_drawdown_pct >= paper_eval_max_loss_pct:
                            failed = True
                            reason = f"Max Drawdown Exceeded ({current_drawdown_pct:.1f}% >= {paper_eval_max_loss_pct}%)"
                        elif daily_drawdown_pct >= paper_eval_daily_loss_pct:
                            failed = True
                            reason = f"Daily Loss Exceeded ({daily_drawdown_pct:.1f}% >= {paper_eval_daily_loss_pct}%)"
                            
                        passed = False
                        if current_gain_pct >= paper_eval_target_pct:
                            passed = True
                            
                        if failed:
                            logger.error(f"[EVAL] PROP FIRM EVALUATION FAILED: {reason}")
                            controller.health_monitor.add_event(f"Eval Failed: {reason}", "critical")
                            controller.halt("PROP FIRM EVALUATION FAILED")
                        elif passed:
                            logger.info(f"[EVAL] PROP FIRM EVALUATION PASSED! Target {paper_eval_target_pct}% reached.")
                            controller.health_monitor.add_event("Eval Passed!", "healthy")
                            controller.halt("PROP FIRM EVALUATION PASSED")
                except Exception as e:
                    logger.error(f"[EVAL] Error evaluating prop firm rules: {e}")
            
            # Sabbath Paper Trading: Allow scanning and trading 
            # if we have successfully swapped to the local PaperBroker.
            allow_entries = not sabbath_active or executor == executor_paper
            if not is_scheduled and not force_paper_broker:
                allow_entries = False
            # Replay mode: block entries during warmup, throttle after warmup
            if replay_provider is not None:
                if replay_provider.in_warmup:
                    allow_entries = False
                elif not replay_provider.can_enter():
                    allow_entries = False

            if next_decision_in <= 0:
                # Advance the replay cursor if in replay mode
                if replay_provider is not None and getattr(replay_provider, "replay_date", None) is not None:
                    # Auto-chain: when this day finishes, load the next day
                    if replay_provider.is_replay_complete:
                        _prev_day = replay_provider.original_replay_date or replay_provider.replay_date
                        _next = _prev_day + timedelta(days=1)
                        # Skip weekends (Sat=5, Sun=6) and Fridays (4)
                        while _next.weekday() >= 4:
                            _next += timedelta(days=1)
                        logger.info("[REPLAY] Day complete! Chaining to next day: %s (%s)",
                                    _next.strftime('%Y-%m-%d'), _next.strftime('%A'))
                        try:
                            # ── Close all open positions before switching days ──
                            # Positions from day N use day N's candle data.
                            # Carrying them into day N+1 produces nonsensical PnL.
                            if executor_paper:
                                executor_paper.close_all_positions("Day Chain Reset")

                            # ── Reset all module-level strategy state ──
                            # Without this, cooldowns, loss streaks, trend
                            # invalidation memory, and indicator caches from
                            # day N leak into day N+1, causing duplicate trades.
                            try:
                                from tradebot_sci.strategy.variants.forex_conductor import reset_module_state as _reset_conductor
                                _reset_conductor()
                            except ImportError:
                                pass
                            try:
                                from tradebot_sci.strategy.exit_logic import reset_state as _reset_exit
                                _reset_exit()
                            except ImportError:
                                pass
                            try:
                                from tradebot_sci.market.trend_consensus import clear_cache as _clear_trend
                                _clear_trend()
                            except ImportError:
                                pass

                            # Reset instance-level state on each engine's strategy
                            for eng in engines.values():
                                strat = getattr(eng, 'strategy', None)
                                if hasattr(strat, 'reset_instance_state'):
                                    strat.reset_instance_state()

                            _old_offset = replay_provider._time_offset
                            _rp = ReplayMarketProvider(
                                data_dir=_replay_data_dir,
                                symbols=symbols,
                                replay_date=_next,
                                time_offset=_old_offset,
                            )
                            if _rp.replay_date is None:
                                raise ValueError(f"No replay data found in {_replay_data_dir} for symbols {symbols} on {_next}")
                            replay_provider = _rp
                            provider = replay_provider
                            executor_paper.market_provider = provider
                            controller.replay_provider = replay_provider
                            for eng in engines.values():
                                eng.market_provider = provider
                        except Exception as e:
                            logger.warning("[REPLAY] Failed to chain next day: %s", e)
                    replay_provider.advance()

                active_symbols, auto_mode, last_auto_mode = _resolve_active_symbols(
                    symbols=symbols if (is_scheduled or force_paper_broker or execute_trades) else [],
                    engines=engines,
                    executor=executor,
                    executor_paper=executor_paper,
                    provider=provider,
                    profile_settings=profile_settings,
                    settings=settings,
                    controller=controller,
                    now=now,
                    pair_selector=pair_selector,
                    last_auto_mode=last_auto_mode,
                    sabbath_active=sabbath_active,
                )
                if not active_symbols:
                    next_decision_in = decision_interval
                    time.sleep(0.001 if (replay_provider and getattr(replay_provider, 'in_warmup', False)) else poll_interval)
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
                        controller.health_monitor.record_data_feed('__all__', success=False)
                        if consecutive_error_iterations >= 3:
                            logger.warning(
                                "[AUTO_RESTART] Persistent connection errors detected (%d consecutive iterations)",
                                consecutive_error_iterations,
                            )
                    else:
                        # Data fetched successfully, just no qualified setups - reset counter
                        consecutive_error_iterations = 0
                        controller.health_monitor.record_pipeline(0)
                    next_decision_in = decision_interval
                    time.sleep(0.001 if (replay_provider and getattr(replay_provider, 'in_warmup', False)) else poll_interval)
                    continue
                # Reset error counter when we successfully fetch at least one symbol
                consecutive_error_iterations = 0
                controller.health_monitor.record_pipeline(len(candidates))
                controller.health_monitor.set_active_symbols(active_symbols)
                for _sym in active_symbols:
                    controller.health_monitor.record_data_feed(_sym, success=True)
                
                # Strictly honor Sabbath: 
                # Block BOTH entries and exits (Zero Action) if NO PaperBroker is active.
                if sabbath_active and executor != executor_paper:
                    controller.broadcast_state(executor, force=True, executor_real=executor_real)
                    logger.info("[SABBATH] Strict adherence active (no PaperBroker): Skipping candidate processing.")
                    next_decision_in = decision_interval
                    time.sleep(0.001 if (replay_provider and getattr(replay_provider, 'in_warmup', False)) else poll_interval)
                    continue


                # The live bot's cycle.py now evaluates all candidates in two phases,
                # respects maximum slots dynamically, and ranks entries by score.
                # Therefore, we no longer artificially restrict the cycle to 1 entry here.
                success_symbol, attempts, blocked, skipped = process_candidate_cycle(
                    executor,
                    engines,
                    profile,
                    profile_settings,
                    settings,
                    strike_tracker,
                    candidates,
                    stop_after_submit=False,
                )
                if success_symbol:
                    logger.info(
                        "[CYCLE] success=%s attempts=%s blocked=%s skipped=%s",
                        success_symbol,
                        attempts,
                        blocked,
                        skipped,
                    )
                    # Record entry in replay throttle
                    if replay_provider is not None:
                        replay_provider.record_entry()
                
                # AI Commentary: Update the UI with market insights
                try:
                    # Identify active strategy for context
                    active_strategy = "supply_demand"
                    if active_symbols:
                        first_engine = engines.get(active_symbols[0])
                        if first_engine and hasattr(first_engine, "_strategy"):
                            active_strategy = first_engine._strategy.name.lower()

                    # Build COMPREHENSIVE state context for AI
                    from datetime import datetime as _dt, timezone as _tz
                    state_lines = [
                        f"Timestamp: {_dt.now(_tz.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                        f"Profile: {profile_name}",
                        f"Active Strategy: {active_strategy.upper()}",
                        f"Watchlist: {', '.join(active_symbols)}",
                        "",
                    ]

                    # --- Account & Capital ---
                    state_lines.append("--- ACCOUNT ---")
                    if executor:
                        cap = executor.get_liquid_capital()
                        state_lines.append(f"Free Cash (Available): ${cap:.2f}")
                        if hasattr(executor, "get_total_equity"):
                            eq = executor.get_total_equity() 
                            state_lines.append(f"Total Equity (Cash + Positions): ${eq:.2f}")
                        if hasattr(executor, "get_total_balance_value"):
                            nav = executor.get_total_balance_value()
                            state_lines.append(f"NAV: ${nav:.2f}")

                    # --- Open Positions ---
                    state_lines.append("")
                    state_lines.append("--- OPEN POSITIONS ---")
                    pos_count = 0
                    for sym in active_symbols:
                        try:
                            pos = executor.get_open_position_snapshot(sym) if executor else None
                            if pos and pos.get("qty", 0) != 0:
                                pos_count += 1
                                side = pos.get("side", "unknown")
                                qty = pos.get("qty", 0)
                                entry = pos.get("entry_price", 0)
                                pnl = pos.get("unrealized_pnl", 0)
                                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                                strategy = pos.get("strategy_used", "unknown")
                                state_lines.append(
                                    f"  {sym}: {side} {abs(qty)} @ {entry} | "
                                    f"P&L: ${pnl:.2f} ({pnl_pct:.1f}%) | Strategy: {strategy}"
                                )
                        except Exception:
                            pass
                    if pos_count == 0:
                        state_lines.append("  No open positions")

                    # --- Scan Results (this cycle) ---
                    state_lines.append("")
                    state_lines.append("--- LAST SCAN ---")
                    state_lines.append(f"Candidates Analyzed: {len(candidates)}")
                    state_lines.append(f"Trade Submitted: {success_symbol or 'none'}")
                    state_lines.append(f"Blocked by Safety: {blocked}, Skipped: {skipped}")
                    # Include candidate details
                    for sym, snap, score_info, reason in candidates[:6]:
                        state_lines.append(f"  {sym}: {reason} (score={score_info})")

                    # --- Recent Trade History ---
                    state_lines.append("")
                    state_lines.append("--- RECENT CLOSED TRADES (last 5) ---")
                    try:
                        recent = trade_results.get_recent_results(5)
                        if recent:
                            for tr in recent:
                                w_l = "WIN" if tr.is_win else "LOSS"
                                strat = tr.strategy or "unknown"
                                exit_r = tr.exit_reason or "unknown"
                                dur_str = ""
                                if tr.duration_seconds:
                                    hours = tr.duration_seconds / 3600
                                    dur_str = f" | held {hours:.1f}h"
                                state_lines.append(
                                    f"  {tr.symbol}: {w_l} ${tr.pnl_usd:+.2f} ({tr.pnl_pct:+.1f}%) "
                                    f"| {strat} | exit: {exit_r}{dur_str}"
                                )
                        else:
                            state_lines.append("  No closed trades yet")
                    except Exception:
                        state_lines.append("  Trade history unavailable")

                    # --- Performance Stats ---
                    state_lines.append("")
                    state_lines.append("--- PERFORMANCE ---")
                    try:
                        stats_24h = trade_results.get_stats_for_timeframe("24h")
                        stats_week = trade_results.get_stats_for_timeframe("week")
                        stats_all = trade_results.get_stats()
                        state_lines.append(
                            f"Today: {stats_24h['total_trades']} trades, "
                            f"{stats_24h['win_rate']:.0%} win rate, ${stats_24h['pnl_usd']:+.2f}"
                        )
                        state_lines.append(
                            f"This Week: {stats_week['total_trades']} trades, "
                            f"{stats_week['win_rate']:.0%} win rate, ${stats_week['pnl_usd']:+.2f}"
                        )
                        state_lines.append(
                            f"All Time: {stats_all['total_trades']} trades, "
                            f"{stats_all['win_rate']:.0%} win rate, ${stats_all['pnl_usd']:+.2f}"
                        )
                    except Exception:
                        state_lines.append("  Stats unavailable")

                    # --- Market Regime (from latest engine) ---
                    state_lines.append("")
                    state_lines.append("--- MARKET REGIME ---")
                    try:
                        for sym in active_symbols[:3]:
                            eng = engines.get(sym)
                            if eng and hasattr(eng, "_last_snapshot") and eng._last_snapshot:
                                snap = eng._last_snapshot
                                if snap.trend_htf:
                                    state_lines.append(
                                        f"  {sym} HTF Trend: {snap.trend_htf.get('direction', 'unknown')} "
                                        f"(strength: {snap.trend_htf.get('strength', 0):.2f})"
                                    )
                                if snap.trend_ltf:
                                    state_lines.append(
                                        f"  {sym} LTF Trend: {snap.trend_ltf.get('direction', 'unknown')}"
                                    )
                    except Exception:
                        state_lines.append("  Regime data unavailable")

                    # Get recent logs for context from ws_handler buffer
                    recent_logs = []
                    if controller and hasattr(controller, 'ws_server') and controller.ws_server:
                        try:
                            buf = getattr(controller.ws_server, '_log_buffer', [])
                            recent_logs = list(buf)[-15:] if buf else []
                        except Exception:
                            pass

                    # Detect Session Lockout for commentary gating
                    session_locked = False
                    try:
                        safety_settings = getattr(profile_settings, 'safety', None) or profile_settings
                        lockout_enabled = getattr(safety_settings, 'safety_session_lockout_enabled', False)
                        lockout_hour = getattr(safety_settings, 'safety_session_lockout_hour', 16)
                        if lockout_enabled:
                            est_hour = _dt.now(ZoneInfo("America/New_York")).hour
                            session_locked = est_hour >= lockout_hour
                    except Exception:
                        pass

                    controller.broadcast_commentary(
                        state_context="\n".join(state_lines),
                        strategy_name=active_strategy,
                        recent_logs=recent_logs,
                        recent_errors=None,
                        session_locked=session_locked,
                    )
                except Exception as e:
                    logger.debug(f"[COMMENTARY] Trigger skipped: {e}")
                
                # Push immediate post-entry holding state so rapid Replay Mode doesn't flash past trades
                controller.broadcast_holdings(executor, executor_real=executor_real)
                controller.broadcast_state(executor, executor_real=executor_real)
                
                next_decision_in = decision_interval
            else:
                next_decision_in -= poll_interval
            time.sleep(0.001 if (replay_provider and getattr(replay_provider, 'in_warmup', False)) else poll_interval)
    except KeyboardInterrupt:
        logger.info("Shutting down simulation")
    except Exception as exc:
        # enhanced crash logging
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
    _preflight_broker_check(settings)

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
    execute_trades = settings.runtime.execute_trades
    _confirm_trading_universe(symbols, profile_name, execute_trades, settings)

    # ── Paper Trading & Sabbath Settings (Shared with run_bot) ──
    paper_sim_enabled = True
    paper_replay_mode = False
    paper_synthetic_mode = False
    sabbath_replay_mode = True
    
    config_path = _paths.CONFIG_FILE
    last_config_mtime = config_path.stat().st_mtime if config_path.exists() else 0

    def _update_paper_settings():
        nonlocal paper_sim_enabled, paper_replay_mode, paper_synthetic_mode, sabbath_replay_mode
        import json
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    _raw = json.load(f)
                    _p = _raw.get("paper", {})
                    _s = _raw.get("safety", {})
                    paper_sim_enabled = _p.get("enabled", True)
                    paper_replay_mode = _p.get("replay_mode", False)
                    paper_synthetic_mode = _p.get("synthetic_mode", False)
                    sabbath_replay_mode = _s.get("sabbath_replay_mode", True)
        except Exception as e:
            logger.debug(f"[PAPER] Failed to update paper settings: {e}")

    _update_paper_settings()

    controller = RuntimeController(settings, profile_settings)
    
    # Bridge logs to WS
    ws_handler = WSLoggingHandler(controller)
    ws_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(ws_handler)

    controller.start_ws_server()

    # [SILENCE] If live trading is disabled, neutralize the dedicated OANDA chart provider
    # that typically runs alongside the WS server for candlestick streaming.
    if not execute_trades:
        logger.info("[SILENCE] Live trading disabled: silencing OANDA background chart provider.")
        # OANDA credentials from env (checked by factory)
    
    shared_ib = _maybe_connect_primary_ib(settings, execute_trades)
    
    # [RULE] If live trading is disabled, we MUST use a safe market provider.
    # If paper simulation is enabled, we use ReplayMarketProvider (accelerated).
    # Otherwise, we use NoOp to ensure zero API interaction.
    if not execute_trades:
        # Check profile-level paper simulator setting
        is_paper_sim = getattr(profile_settings, "paper_simulator_enabled", True)
        if is_paper_sim:
             _replay_data_dir = os.path.join(os.getcwd(), "Data", "forex_backtest")
             logger.info(f"[PAPER] Initializing ReplayMarketProvider for paper simulation (Safe Mode).")
             _rp = ReplayMarketProvider(data_dir=_replay_data_dir, symbols=symbols)
             if _rp.replay_date is None:
                 logger.warning(f"[PAPER] No replay data found in {_replay_data_dir} for symbols {symbols}. Using NoOpMarketDataProvider.")
                 provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib)
             else:
                 provider = _rp
        else:
             logger.info("[SILENCE] Paper simulation disabled: using NoOpMarketDataProvider.")
             provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib) # returns NoOp due to factory
    else:
        provider = build_market_provider(settings, profile_settings, shared_ib=shared_ib)

    ai_client = TradeSciAIClient(settings.ai)
    profile = BaseProfile(
        name=profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    trade_results = TradeResultStore(str(_paths.DATA_DIR / "trade_results.json"))
    engines = {
        symbol: StrategyEngine(
            ai_client=ai_client,
            market_provider=provider,
            profile=profile_settings,
            symbol=symbol,
            trade_results=trade_results,
            settings=settings,
        )
        for symbol in symbols
    }

    executor_real = (
        build_exchange_broker(
            settings,
            profile_settings,
            shared_ib=shared_ib,
            trade_results=trade_results,
            allowed_symbols=set(symbols) if symbols else None,
        )
        if execute_trades
        else None
    )

    # ── Paper Broker ──
    # Create PaperBroker if:
    #   (a) execute_trades is disabled (user wants paper/simulation mode), OR
    #   (b) Sabbath mode is enabled (needs paper fallback during Sabbath hours)
    executor_paper = None
    if not execute_trades or sabbath_context.enabled:
        paper_trade_results = TradeResultStore(str(_paths.DATA_DIR / "paper_trade_results.json"))
        executor_paper = PaperBroker(
            profile_settings, 
            market_provider=provider, 
            trade_results=paper_trade_results,
            controller=controller
        )
        if not execute_trades:
            logger.info("[PAPER] 📝 Paper Trading mode active (Live Trading disabled).")
        else:
            logger.info("[PAPER] Sabbath-mode Paper Broker initialized (standby).")
    else:
        logger.info("[PAPER] Paper Broker disabled (Live Trading enabled, Sabbath not active).")
    
    # Active executor reference — paper broker takes priority when live trading is off
    if not execute_trades and executor_paper:
        executor = executor_paper
    else:
        executor = executor_real

    # ── Replay provider for weekend paper trading ──
    provider_real = provider  # keep a reference to the real provider
    replay_provider = None    # lazily created on first Sabbath activation

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
        f"{sess.profile_name} {sess.start_time}-{sess.end_time}" for sess in settings.schedule.sessions
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
        # ── Startup Pending Order Sweep ──────────────────────────────────────
        # Cancel ALL pending OANDA orders before the main loop begins.
        # Prevents stale limit orders from a prior pod from filling as ghost trades.
        if execute_trades and executor_real:
            _oanda_broker_sched = executor_real
            if hasattr(executor_real, "brokers"):
                for _b in set(executor_real.brokers.values()):
                    if type(_b).__name__ == "OandaBroker":
                        _oanda_broker_sched = _b
                        break
            if hasattr(_oanda_broker_sched, "cancel_all_pending_orders_on_startup"):
                _oanda_broker_sched.cancel_all_pending_orders_on_startup()

        if executor and settings.runtime.cancel_orders_on_start:
            for symbol in symbols:
                executor.cancel_all_orders_for_symbol(symbol)
                _log_state_snapshot(executor, symbol)
        last_auto_mode: str | None = None
        last_holdings_log_ts = 0.0
        consecutive_error_iterations = 0

        # ── Health Monitor: Boot events ──
        controller.health_monitor.add_event(f"Scheduled bot started — profile: {profile_name}", "info")
        controller.health_monitor.record_config(True, profile_name)
        if executor:
            controller.health_monitor.record_broker(True, broker_name=getattr(executor, 'name', 'OANDA'))
        controller.broadcast_health(force=True)

        while True:
            # Check for Halt Signal
            if controller.is_halted():
                logger.debug("[LOOP] Bot is HALTED via signal. Waiting...")
                controller.health_monitor.set_halted(True)
                controller.broadcast_health()
                time.sleep(poll_interval)
                continue
            else:
                controller.health_monitor.set_halted(False)

            # Hot-reload check for paper settings
            if config_path.exists():
                mtime = config_path.stat().st_mtime
                if mtime > last_config_mtime:
                    _update_paper_settings()
                    last_config_mtime = mtime

            now = datetime.now(tz)
            sabbath_active, _, _ = sabbath_context.evaluate(now)
            execute_trades = getattr(settings.runtime, "execute_trades", False)

            session = get_current_session(now, settings.schedule.sessions, tz)
            
            # [RULE] If live trading is disabled, ignore the scheduler and run if paper simulation is enabled.
            # [RULE] If Sabbath is active, ignore the scheduler and run if Sabbath Replay is enabled.
            if not session:
                if not execute_trades and paper_sim_enabled:
                    session = {"name": "paper_sim", "end": now + timedelta(hours=1)}
                elif sabbath_active and sabbath_replay_mode:
                    session = {"name": "sabbath_replay", "end": now + timedelta(hours=1)}

            if session:
                current_session_name = session["name"]
            
            if not session:
                controller.health_monitor.set_market_hours(False)
                next_start, next_session = get_next_session_start(now, settings.schedule.sessions, tz)
                if not next_start or not next_session:
                    logger.info("[STATE] No upcoming sessions; idling")
                    time.sleep(poll_interval)
                    continue
                logger.info(
                    "[STATE] Next session '%s' starts at %s (%s)",
                    next_session.profile_name,
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

                # Evaluate Sabbath Status FIRST
                sabbath_active, _, _ = sabbath_context.evaluate(loop_now)

                # ── [MASTER FAIL-SAFE] ──
                # Hard-coded gating to ensure Paper Broker is exclusive when live trading is disabled or Sabbath is active.
                execute_trades = getattr(settings.runtime, "execute_trades", True)
                if not execute_trades or sabbath_active:
                    if not executor_paper:
                        logger.info("[PAPER] Initializing Paper Broker dynamically for scheduled simulation.")
                        local_paper_results = TradeResultStore(str(_paths.DATA_DIR / "paper_trade_results.json"))
                        executor_paper = PaperBroker(
                            profile_settings,
                            market_provider=provider,
                            trade_results=local_paper_results,
                            controller=controller
                        )
                    if executor != executor_paper:
                        logger.info("[PAPER] 🛡️  Fail-safe: Forcing Paper Broker activation for scheduled isolation.")
                        executor = executor_paper
                elif executor_real and executor != executor_real:
                    # Only restore real broker if we are NOT in Sabbath AND execute_trades is True
                    if not sabbath_active and execute_trades:
                        logger.info("[LIVE] 🚀  Fail-safe: Restoring Real Broker connection for scheduled session.")
                        executor = executor_real

                # ── Health Monitor: Record heartbeat at cycle start ──
                any_market_open = any(is_market_open(sym, loop_now, settings=profile_settings) for sym in symbols)
                controller.health_monitor.record_heartbeat(sabbath_active)
                controller.health_monitor.set_market_hours((not sabbath_active) and any_market_open)
                if controller.health_monitor.is_warming_up:
                    logger.info(f"[WARM-UP] Strategy warm-up active (Cycle {controller.health_monitor._cycle_count}/10). Suppressing health warnings.")

                # Replay/Synthetic mode for scheduled sessions (Sabbath or Simulation)
                _want_replay = False
                if executor == executor_paper and (paper_sim_enabled or (sabbath_active and sabbath_replay_mode)):
                    _want_replay = True

                if _want_replay and executor == executor_paper:
                    if replay_provider is None:
                        if paper_synthetic_mode:
                            from tradebot_sci.market.synthetic_provider import SyntheticMarketProvider
                            replay_provider = SyntheticMarketProvider(symbols=symbols)
                            logger.info("[REPLAY] Synthetic mode activated for scheduled session.")
                        elif _replay_data_dir.is_dir():
                            try:
                                _rp = ReplayMarketProvider(data_dir=_replay_data_dir, symbols=symbols)
                                if _rp.replay_date is None:
                                    raise ValueError(f"No replay data found in {_replay_data_dir} for symbols {symbols}")
                                replay_provider = _rp
                                logger.info("[REPLAY] Replay provider activated for scheduled session.")
                            except Exception as e:
                                logger.warning("[REPLAY] Failed to create replay provider: %s", e)
                        
                        if replay_provider:
                            provider = replay_provider
                            executor_paper.market_provider = provider
                            controller.replay_provider = replay_provider
                            for eng in engines.values():
                                eng.trade_results = paper_trade_results
                                eng.market_provider = provider
                elif not _want_replay and replay_provider is not None:
                    # Restore live data stream
                    provider = provider_real
                    if executor_paper:
                        executor_paper.market_provider = provider_real
                    controller.replay_provider = None
                    replay_provider = None
                    for eng in engines.values():
                        eng.trade_results = trade_results if executor != executor_paper else paper_trade_results
                        eng.market_provider = provider_real
                    logger.info("[REPLAY] Replay provider deactivated, scheduled session restored to live data stream")

                if executor:
                    executor.refresh_account_summary()
                    
                    # Only check auto-restart for REAL broker
                    reason = None
                    if executor == executor_real:
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
                        _log_holdings_snapshot(executor, reason="heartbeat", strategy_variant=getattr(profile_settings, 'strategy_variant', None))
                        last_holdings_log_ts = now_ts

                # During Sabbath, we allow entries because they will be paper-traded.
                allow_entries = execute_trades
                # Replay mode: block entries during warmup, throttle after warmup
                if replay_provider is not None:
                    if replay_provider.in_warmup:
                        allow_entries = False
                    elif not replay_provider.can_enter():
                        allow_entries = False
                else:
                    # Live simulation / paper mode: check Forex weekend block to prevent ghost trade attempts
                    try:
                        import zoneinfo
                        est_tz = zoneinfo.ZoneInfo("America/New_York")
                        now_est = datetime.now(est_tz)
                        if now_est.weekday() == 4 and now_est.hour >= 17:
                            allow_entries = False
                        elif now_est.weekday() == 5:
                            allow_entries = False
                        elif now_est.weekday() == 6 and now_est.hour < 17:
                            allow_entries = False
                    except Exception:
                        pass
                if next_decision_in <= 0:
                    # Advance the replay cursor if in weekend replay mode
                    if replay_provider is not None and getattr(replay_provider, "replay_date", None) is not None:
                        replay_provider.advance()

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
                                        settings=settings,
                                    )
                                active_symbols.append(sym)
                    candidates, data_fetch_succeeded = build_candidate_list(
                        executor,
                        engines,
                        provider,
                        symbols,
                        profile.candle_timeframe,
                        profile_settings,
                        settings.market,
                        strike_tracker=scheduled_strike_tracker,
                        now=loop_now,
                        ws_controller=controller,
                        allow_entries=allow_entries,
                    )
                    if not candidates:
                        # Empty candidates can mean either:
                        # 1. All symbols failed to fetch (connection errors) - data_fetch_succeeded=False
                        # 2. Symbols fetched successfully but don't meet threshold - data_fetch_succeeded=True
                        if not data_fetch_succeeded:
                            consecutive_error_iterations += 1
                            controller.health_monitor.record_data_feed('__all__', success=False)
                            if consecutive_error_iterations >= 3:
                                logger.warning(
                                    "[AUTO_RESTART] Persistent connection errors detected (%d consecutive iterations)",
                                    consecutive_error_iterations,
                                )
                        else:
                            consecutive_error_iterations = 0
                            logger.warning(
                                "[AUTO_RESTART] Persistent connection errors detected (%d consecutive iterations)",
                                consecutive_error_iterations,
                            )
                        next_decision_in = decision_interval
                        time.sleep(poll_interval)
                        continue
                    controller.health_monitor.record_pipeline(len(candidates))
                    for _sym in symbols:
                        controller.health_monitor.record_data_feed(_sym, success=data_fetch_succeeded)
                    # Replay mode: limit to 1 new-entry candidate per cycle
                    if replay_provider is not None and candidates:
                        manage_cands = [(s, snap, sc, r) for s, snap, sc, r in candidates if r == "existing position"]
                        entry_cands = [(s, snap, sc, r) for s, snap, sc, r in candidates if r != "existing position"]
                        if entry_cands:
                            entry_cands.sort(key=lambda x: x[2], reverse=True)
                            candidates = manage_cands + entry_cands[:1]

                    managing_positions = any(reason == "existing position" for _, _, _, reason in candidates)
                    process_candidate_cycle(
                        executor,
                        engines,
                        profile,
                        profile_settings,
                        settings,
                        scheduled_strike_tracker,
                        candidates,
                        # During replay, always stop after first entry to prevent avalanche
                        stop_after_submit=True if replay_provider is not None else (not managing_positions),
                    )
                    next_decision_in = decision_interval
                else:
                    next_decision_in -= poll_interval
                # ── Health Monitor: Broadcast vitals to GUI ──
                controller.broadcast_health()
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

    # Strict guard against IBKR connection in alternative mode
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
            if self.controller.ws_server and any(marker in msg for marker in ["[STATE]", "[CYCLE]", "[RESULT]", "[AUTO-ENTRY]", "[ROBOCOP]", "[EXIT]", "[PROFILE]", "[HEARTBEAT]", "[DECISION]", "[STRUCTURE]", "[SAFETY]", "[MINOVSKY]", "[ENTRY]", "[FILL]", "[HOLD]", "[SIGNAL]", "[TRADE]", "[SCAN]", "[HOLDINGS]", "[TREND-DATA]", "[TREND-GATE]"]):
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
