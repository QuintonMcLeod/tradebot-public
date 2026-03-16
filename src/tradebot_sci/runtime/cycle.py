from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING

from tradebot_sci.market.models import MarketSnapshot, TrendState
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.runtime.trackers import StrikeTracker

if TYPE_CHECKING:
    from tradebot_sci.runtime.controller import RuntimeController

logger = logging.getLogger(__name__)

# ── First-run warmup ──
# Tracks which symbols have had their initial warmup fetch.
# On first fetch, we request extra candles to stabilize indicators
# (equivalent to the backtester's warmup_days feature).
_warmed_up_symbols: set[str] = set()

# 2016 five-minute candles = 7 calendar days of 5m data
_WARMUP_LTF_CANDLES = 2016
_WARMUP_HTF_CANDLES = 200  # 200 four-hour candles ≈ 33 days

# ── Bar-Close Confirmation Gate ──
# When enabled, strips incomplete (still-forming) candles before strategy
# evaluation — ensuring the live bot signals on closed bars only, matching
# the backtester's behavior.
_BAR_CLOSE_GATE_ENABLED = os.environ.get("BAR_CLOSE_GATE_ENABLED", "true").lower() in ("true", "1", "yes")

def _parse_bar_seconds(timeframe: str) -> int:
    """Converts a timeframe string (e.g. '5m', '1h', '4h') to seconds."""
    m = re.match(r'^(\d+)\s*(m|min|mins|h|hour|hours|d|day|days)$', timeframe.lower().strip())
    if not m:
        return 300  # fallback 5m
    val, unit = int(m.group(1)), m.group(2)
    if unit.startswith('m'):
        return val * 60
    elif unit.startswith('h'):
        return val * 3600
    elif unit.startswith('d'):
        return val * 86400
    return 300

def _strip_incomplete_bar(candles: list, timeframe: str) -> list:
    """Removes the last candle if it hasn't closed yet (still forming)."""
    if not _BAR_CLOSE_GATE_ENABLED or not candles:
        return candles
    bar_secs = _parse_bar_seconds(timeframe)
    last = candles[-1]
    bar_close_time = last.timestamp + timedelta(seconds=bar_secs)
    now = datetime.now(timezone.utc)
    if bar_close_time > now:
        remaining = int((bar_close_time - now).total_seconds())
        logger.info(
            f"[BAR-CLOSE] Stripped incomplete {timeframe} bar for "
            f"{getattr(candles[-1], 'symbol', '?')} (closes in {remaining}s)"
        )
        return candles[:-1]
    return candles

def fetch_snapshot(
    provider: Any, 
    cache: Dict[tuple, MarketSnapshot], 
    symbol: str, 
    timeframe: str, 
    profile_settings: Any, 
    market_settings: Any, 
    ws_controller: Optional[RuntimeController] = None
) -> MarketSnapshot:
    """Fetches high/low timeframe candles and builds a snapshot.

    NOTE: trend_htf and trend_ltf are initialised to NEUTRAL here.
    The actual trend direction is determined by the Trend Detection
    indicator consensus in StrategyEngine.decide() — the sole
    authority on trend direction.
    """
    htf_timeframe = getattr(profile_settings, "htf_timeframe", None) or "4h"
    ltf_timeframe = getattr(profile_settings, "ltf_timeframe", None) or timeframe
    max_candles = int(getattr(market_settings, "max_candles", 200) or 200)

    # First-time warmup: fetch extra candles to stabilize indicators
    if symbol not in _warmed_up_symbols:
        ltf_limit = max(max_candles, _WARMUP_LTF_CANDLES)
        htf_limit = max(max_candles, _WARMUP_HTF_CANDLES)
        logger.info(
            f"[WARMUP] {symbol}: First-time candle preload — "
            f"fetching {ltf_limit} LTF ({ltf_timeframe}) + "
            f"{htf_limit} HTF ({htf_timeframe}) candles"
        )
        _warmed_up_symbols.add(symbol)
    else:
        ltf_limit = max_candles
        htf_limit = max_candles

    key = (symbol, ltf_timeframe, htf_timeframe, max_candles)
    if key not in cache:
        ltf_candles = provider.get_latest_candles(symbol, ltf_timeframe, limit=ltf_limit)
        htf_candles = provider.get_latest_candles(symbol, htf_timeframe, limit=htf_limit)

        # ── Bar-Close Gate: strip incomplete candles ──
        ltf_candles = _strip_incomplete_bar(ltf_candles, ltf_timeframe)
        htf_candles = _strip_incomplete_bar(htf_candles, htf_timeframe)
        
        # Update chart candle cache so on_tick always has fresh data
        if ws_controller and ltf_candles and hasattr(ws_controller, 'update_candle_cache'):
            ws_controller.update_candle_cache(symbol, ltf_timeframe, ltf_candles[-1])

        # Neutral defaults — engine.py's Trend Detection sets direction
        _neutral = TrendState(direction="neutral", strength=0.0)

        # Providers (like Synthetic) may explicitly force certain trends
        try:
            native_snap = provider.get_latest_snapshot(symbol, ltf_timeframe)
            trend_htf = native_snap.trend_htf or _neutral
            trend_ltf = native_snap.trend_ltf or _neutral
        except Exception as e:
            trend_htf = _neutral
            trend_ltf = _neutral

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

        # Record snapshot for replay backtesting — but ONLY from live data.
        # Synthetic/Replay providers generate fake prices (e.g., EURJPY at 1.55
        # instead of 183) that corrupt the candle_history files.
        _is_live_data = not (
            hasattr(provider, 'replay_date')          # ReplayMarketProvider
            or type(provider).__name__ == 'SyntheticMarketProvider'
        )
        if _is_live_data:
            try:
                from tradebot_sci.runtime.candle_recorder import get_recorder
                get_recorder().record(cache[key])
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).debug(f"[RECORDER] Recording failed: {e}")

    # DEBUG
    logger.info(f"[CYCLE-DEBUG] Returning snapshot for {symbol} with trend_htf={cache[key].trend_htf}")

    return cache[key]


def _get_dynamic_max_concurrent(profile_settings: Any, now: datetime) -> int:
    """
    Get dynamic concurrent positions limit.
    Always respects the user's configured max_concurrent_positions setting.
    """
    val = getattr(profile_settings, "max_concurrent_positions", 1)
    if val is None:
        val = 1
    return int(val)


def build_candidate_list(
    executor: Any,
    engines: Dict[str, StrategyEngine],
    provider: Any,
    symbols: List[str],
    timeframe: str,
    profile_settings: Any,
    market_settings: Any,
    strike_tracker: Optional[StrikeTracker] = None,
    now: Optional[datetime] = None,
    ws_controller: Optional[RuntimeController] = None,
    allow_entries: bool = True,
) -> Tuple[List[Tuple[str, MarketSnapshot, float, str]], bool]:
    """Scans the universe and identifies positions to manage or new setups to trade."""
    logger.info(f"[CYCLE] Building candidate list for {len(symbols)} symbols")
    snapshot_cache: Dict[tuple, MarketSnapshot] = {}
    symbols = [symbol for symbol in symbols if symbol in engines]
    
    # 1. Handle Active Order Symbols (Campaign Blocking)
    if executor and hasattr(executor, "_fetch_symbol_state"):
        active_order_symbols: list[str] = []
        for symbol in symbols:
            try:
                state = executor._fetch_symbol_state(symbol)
                if not state: continue
                if state.get("working_orders", 0) or state.get("synthetic_stop_armed"):
                    active_order_symbols.append(symbol)
            except Exception as e:
                logger.error(f"[CYCLE] Failed to fetch symbol state for {symbol}: {e}")

        if active_order_symbols:
            multi_enabled = getattr(profile_settings, "multi_position_enabled", False)
            max_concurrent = _get_dynamic_max_concurrent(profile_settings, now or datetime.now())
            
            if not multi_enabled:
                symbol = active_order_symbols[0]
                try:
                    snap = fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings, ws_controller)
                    return [(symbol, snap, 0.0, "active campaign")], True
                except Exception:
                    return [], True

    # 2. Build Position Candidates
    position_candidates = []
    if executor:
        for symbol in symbols:
            pos = executor.get_open_position_snapshot(symbol)
            if pos and abs(pos.get("size", 0)) > 1e-8 and not pos.get("is_dust", False):
                try:
                    snap = fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings, ws_controller)
                    position_candidates.append((symbol, snap, 0.0, "existing position"))
                except Exception:
                    continue

    if position_candidates:
        multi_enabled = getattr(profile_settings, "multi_position_enabled", False)
        max_concurrent = _get_dynamic_max_concurrent(profile_settings, now or datetime.now())
        if not multi_enabled or len(position_candidates) >= max_concurrent:
            return position_candidates, True

    if not allow_entries:
        return position_candidates, True

    # 3. Scan for new setups
    # NOTE: No ICC pre-filter here. engine.decide() handles scoring,
    # trend detection, and filtering internally — same as the backtester.
    # The previous ICC gate ran score_icc_grade() on NEUTRAL-trend
    # snapshots (before trend detection), blocking most entries.
    candidates = position_candidates.copy()
    for symbol in symbols:
        if symbol in [c[0] for c in candidates]: continue
        if strike_tracker and strike_tracker.is_skipped(symbol): continue
        
        try:
            snap = fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings, ws_controller)
            candidates.append((symbol, snap, 0.0, "scan"))
        except Exception as e:
            logger.error(f"[CYCLE] Error fetching snapshot for {symbol}: {e}")
            continue
            
    return candidates, True


def handle_execution_result(outcome: ExecutionOutcome, strike_tracker: Optional[StrikeTracker]):
    """Processes outcome of an execution attempt and updates trackers."""
    if not outcome: return
    if not strike_tracker: return
    
    symbol = outcome.symbol
    from tradebot_sci.broker.execution import ExecutionOutcomeType
    if outcome.status == ExecutionOutcomeType.SUCCESS_SUBMITTED:
        strike_tracker.record_execution_success(symbol)
    elif outcome.status == ExecutionOutcomeType.BLOCKED_GUARD:
        strike_tracker.record_guard_block(symbol)
    # ... handle other outcomes if needed


def process_candidate_cycle(
    executor: Any,
    engines: Dict[str, StrategyEngine],
    profile: Any,
    profile_settings: Any,
    settings: Any,
    strike_tracker: Optional[StrikeTracker],
    candidates: List[Tuple[str, MarketSnapshot, float, str]],
    stop_after_submit: bool = True,
) -> Tuple[Optional[str], int, int, int]:
    """Iterates through candidates and executes decisions."""
    success_symbol = None
    attempts = 0
    blocked = 0
    skipped = 0

    # Sort by score descending (if score is present)
    sorted_candidates = sorted(candidates, key=lambda x: x[2], reverse=True)

    # [OPTIMIZATION] Pre-fetch open positions and API state ONCE per cycle
    # to avoid slamming the API with requests inside the loop (N * 3 calls).
    global_pnl = 0.0
    global_open_count = 0
    global_position_notional = 0.0
    if executor and hasattr(executor, "list_open_position_symbols"):
        try:
            open_syms = executor.list_open_position_symbols()
            global_open_count = len(open_syms)
            for s in open_syms:
                p = executor.get_open_position_snapshot(s)
                if p:
                    global_pnl += (p.get("unrealized_pnl", 0.0) or 0.0)
                    # Track total position notional value
                    # On spot exchanges, capital in positions IS equity.
                    price = float(p.get("current_price") or p.get("avg_price") or p.get("entry_price") or 0)
                    size = abs(float(p.get("size") or 0))
                    global_position_notional += (price * size)
        except Exception as e:
            logger.warning(f"[CYCLE] Global PnL fetch failed: {e}")

    for symbol, snapshot, score, reason in sorted_candidates:
        if strike_tracker and (strike_tracker.is_skipped(symbol) or strike_tracker.is_guard_skipped(symbol)):
            skipped += 1
            continue

        attempts += 1
        pos = executor.get_open_position_snapshot(symbol) if executor else None
        # ── SL/TP Backfill ────────────────────────────────────────────────
        # If Oanda didn't return a stopLossOrder (e.g. no SL bracket was set,
        # or the API call for trade details failed), the snapshot has
        # stop_loss=None.  The Conductor's R-milestone block (Guillotine, ATR
        # trail, SAR) is gated on current_stop > 0, so a missing SL silently
        # disables ALL exit management.  Backfill from hold_store here so the
        # decision path always has the best known SL price.
        if pos is not None:
            hold_store = getattr(executor, "position_hold_store", None)
            if hold_store:
                record = hold_store.get(symbol)
                if record:
                    if not pos.get("stop_loss") and record.stop_loss:
                        pos["stop_loss"] = record.stop_loss
                        logger.debug(
                            "[CYCLE] %s: backfilled stop_loss=%.5f from hold_store",
                            symbol, float(record.stop_loss),
                        )
                    if not pos.get("entry_price") and record.entry_price:
                        pos["entry_price"] = record.entry_price
                    if not pos.get("original_entry_price") and getattr(record, "original_entry_price", None) is not None:
                        pos["original_entry_price"] = record.original_entry_price
                    if not pos.get("initial_risk") and getattr(record, "initial_risk", None) is not None:
                        pos["initial_risk"] = record.initial_risk

        
        try:
            liq_cap = executor.get_liquid_capital(symbol) if executor else None
            total_equity = executor.get_total_equity() if executor and hasattr(executor, "get_total_equity") else (liq_cap or 0.0)
            
            decision = engines[symbol].decide(
                snapshot.timeframe, 
                open_position=pos, 
                snapshot=snapshot, 
                current_capital=liq_cap,
                execution_capabilities={
                    "total_unrealized_pnl": global_pnl,
                    "total_position_notional": global_position_notional,
                    "open_position_count": global_open_count,
                    "total_equity": total_equity,
                    "open_symbols": open_syms if 'open_syms' in locals() else []
                }
            )
            # Include 'hold' in decision logging to ensure the Decisions Panel is populated for existing positions
            if not decision or decision.action in ("stand_aside", "hold"):
                reason = decision.notes if decision else "No strategy signal"
                d_score = (decision.score * 100.0) if (decision and decision.score is not None) else 0.0
                d_grade = (decision.grade) if (decision and decision.grade is not None) else "N/A"
                d_strat_name = engines[symbol].last_strat_name
                d_strat_grade = engines[symbol].last_strat_grade
                d_strat_score = engines[symbol].last_strat_score
                logger.info(f"[DECISION] symbol={symbol} action=HOLD score={d_score:.1f} grade={d_grade} strategy={d_strat_name} strat_score={d_strat_score:.1f} strat_grade={d_strat_grade} reason={reason}")

                # ── Propagate stop modifications from hold decisions ──
                # The Conductor returns hold+stop_loss to trail stops.
                # Forward to broker so OANDA actually moves the stop.
                _d_sl = getattr(decision, "stop_loss", None) if decision else None
                _has_mod = hasattr(executor, "modify_stop_loss") if executor else False
                logger.info(
                    f"[TRAIL-DEBUG] {symbol}: action={decision.action if decision else 'None'} "
                    f"stop_loss={_d_sl} executor={bool(executor)} has_modify={_has_mod}"
                )
                if (
                    decision
                    and decision.action == "hold"
                    and _d_sl is not None
                    and executor
                    and _has_mod
                ):
                    try:
                        logger.info(f"[TRAIL] Calling modify_stop_loss({symbol}, {float(_d_sl)})")
                        executor.modify_stop_loss(symbol, float(_d_sl))
                    except Exception as e:
                        logger.warning(f"[TRAIL] Stop modification failed for {symbol}: {e}")

                blocked += 1
                continue
            
            if executor:
                # ── Broker-agnostic re-entry cooldown ──────────────────────
                # Block entry if this symbol recently closed (prevents churn)
                hold_store = getattr(executor, "position_hold_store", None)
                if hold_store and decision.action not in ("scale_in", "add_to_position", "scale_out", "scale_out_leg", "close_position"):
                    in_cooldown, remaining = hold_store.is_in_cooldown(symbol)
                    if in_cooldown:
                        exit_strat = hold_store.get_exit_strategy(symbol) or "unknown"
                        logger.info(
                            f"[COOLDOWN] {symbol}: blocked re-entry, "
                            f"{remaining:.0f}s remaining (last strategy: {exit_strat})"
                        )
                        blocked += 1
                        continue

                # ── Bar-Close Freshness Gate ──────────────────────────
                # Only allow NEW entries if the last completed LTF bar
                # closed recently (within one bar duration). This prevents
                # stale signals from firing mid-candle.
                if (
                    _BAR_CLOSE_GATE_ENABLED
                    and decision.action in ("go_long", "go_short")
                    and snapshot.ltf_candles
                ):
                    ltf_tf = getattr(snapshot, "ltf_timeframe", None) or "5m"
                    bar_secs = _parse_bar_seconds(ltf_tf)
                    last_close = snapshot.ltf_candles[-1].timestamp + timedelta(seconds=bar_secs)
                    age = (datetime.now(timezone.utc) - last_close).total_seconds()
                    if age > bar_secs:
                        logger.info(
                            f"[BAR-CLOSE] {symbol}: blocked {decision.action} — "
                            f"last {ltf_tf} bar closed {age:.0f}s ago (stale, max={bar_secs}s)"
                        )
                        blocked += 1
                        continue
                    else:
                        logger.info(
                            f"[BAR-CLOSE] {symbol}: {decision.action} OK — "
                            f"last {ltf_tf} bar closed {age:.0f}s ago (fresh)"
                        )

                result, outcome = executor.execute_decision(decision)
                handle_execution_result(outcome, strike_tracker)
                if result and result.status.value == "executed":
                    success_symbol = symbol
                    # ── Log a [DECISION] line for fills so the GUI Decision Panel gets score/grade ──
                    fill_score = (decision.score * 100.0) if (decision.score is not None) else 0.0
                    fill_grade = decision.grade if (decision.grade is not None) else "N/A"
                    fill_strat_name = engines[symbol].last_strat_name if symbol in engines else "unknown"
                    fill_strat_grade = engines[symbol].last_strat_grade if symbol in engines else "N/A"
                    fill_strat_score = engines[symbol].last_strat_score if symbol in engines else 0.0
                    logger.info(
                        f"[DECISION] symbol={symbol} action={decision.action.upper()} "
                        f"score={fill_score:.1f} grade={fill_grade} "
                        f"strategy={fill_strat_name} strat_score={fill_strat_score:.1f} "
                        f"strat_grade={fill_strat_grade} "
                        f"reason=FILL executed @ {decision.entry_price or 'market'}"
                    )
                    # [CHURN BURNER] Only count ACTUAL fills, not signals
                    from tradebot_sci.strategy.safety_guard import SafetyGuard
                    SafetyGuard.notify_entry(symbol)
                    # Tag position_hold_store with winning strategy name
                    try:
                        strat_name = getattr(engines.get(symbol), "last_strat_name", None) or "unknown"
                        hold_store = getattr(executor, "position_hold_store", None)
                        if hold_store:
                            rec = hold_store.get(symbol)
                            if rec:
                                rec.strategy = strat_name
                                hold_store.save()
                            else:
                                hold_store.upsert(symbol, datetime.now(timezone.utc), strategy=strat_name)
                        # Also tag broker's internal position dict (Paper broker compatibility)
                        broker_positions = getattr(executor, "positions", None)
                        if broker_positions and isinstance(broker_positions, dict) and symbol in broker_positions:
                            broker_positions[symbol]["strategy"] = strat_name
                    except Exception:
                        pass  # non-critical — don't break trade flow
                    if stop_after_submit:
                        break
        except Exception:
            logger.exception(f"[CYCLE] Fatal error processing {symbol}")
            continue

    return success_symbol, attempts, blocked, skipped
