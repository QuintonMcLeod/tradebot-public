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
_BAR_CLOSE_GATE_ENABLED = os.environ.get("BAR_CLOSE_GATE_ENABLED", "false").lower() in ("true", "1", "yes")

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
    """Removes the last candle if it hasn't closed yet (still forming).
    
    In replay mode (candle timestamps > 24h from wall clock), all candles
    are already closed historical bars — skip the strip entirely.
    """
    if not _BAR_CLOSE_GATE_ENABLED or not candles:
        return candles
    bar_secs = _parse_bar_seconds(timeframe)
    last = candles[-1]
    bar_close_time = last.timestamp + timedelta(seconds=bar_secs)
    now = datetime.now(timezone.utc)
    age = (now - bar_close_time).total_seconds()
    # Replay mode: candles are from months ago, all already closed
    if age > 86400:
        return candles
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
    mtf_timeframe = getattr(profile_settings, "mtf_timeframe", None) or "1h"
    ltf_timeframe = getattr(profile_settings, "ltf_timeframe", None) or timeframe
    max_candles = int(getattr(market_settings, "max_candles", 200) or 200)

    # First-time warmup: fetch extra candles to stabilize indicators
    if symbol not in _warmed_up_symbols:
        ltf_limit = max(max_candles, _WARMUP_LTF_CANDLES)
        htf_limit = max(max_candles, _WARMUP_HTF_CANDLES)
        mtf_limit = max(max_candles, _WARMUP_HTF_CANDLES)  # 1h needs similar depth
        logger.info(
            f"[WARMUP] {symbol}: First-time candle preload — "
            f"fetching {ltf_limit} LTF ({ltf_timeframe}) + "
            f"{mtf_limit} MTF ({mtf_timeframe}) + "
            f"{htf_limit} HTF ({htf_timeframe}) candles"
        )
        _warmed_up_symbols.add(symbol)
    else:
        ltf_limit = max_candles
        htf_limit = max_candles
        mtf_limit = max_candles

    key = (symbol, ltf_timeframe, mtf_timeframe, htf_timeframe, max_candles)
    if key not in cache:
        ltf_candles = provider.get_latest_candles(symbol, ltf_timeframe, limit=ltf_limit)
        mtf_candles = provider.get_latest_candles(symbol, mtf_timeframe, limit=mtf_limit)
        htf_candles = provider.get_latest_candles(symbol, htf_timeframe, limit=htf_limit)

        # Update chart candle cache so on_tick always has fresh data
        # We must pass the raw unstripped candle so the GUI chart isn't frozen!
        if ws_controller and ltf_candles and hasattr(ws_controller, 'update_candle_cache'):
            ws_controller.update_candle_cache(symbol, ltf_timeframe, ltf_candles[-1])

        # ── Retain Live Bar for Analysis, Strip for History ──
        # We preserve the fully forming currently-active candle for MarketSnapshot
        # so that the engine's internal cache reflects tick-by-tick MTF alignment changes.
        stripped_ltf = _strip_incomplete_bar(ltf_candles, ltf_timeframe)
        stripped_mtf = _strip_incomplete_bar(mtf_candles, mtf_timeframe)
        stripped_htf = _strip_incomplete_bar(htf_candles, htf_timeframe)

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
            trend_mtf=_neutral,
            trend_ltf=trend_ltf,
            htf_candles=htf_candles,
            mtf_candles=mtf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=htf_timeframe,
            mtf_timeframe=mtf_timeframe,
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
                record_snap = MarketSnapshot(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=stripped_ltf,
                    trend_htf=trend_htf,
                    trend_mtf=_neutral,
                    trend_ltf=trend_ltf,
                    htf_candles=stripped_htf,
                    mtf_candles=stripped_mtf,
                    ltf_candles=stripped_ltf,
                    htf_timeframe=htf_timeframe,
                    mtf_timeframe=mtf_timeframe,
                    ltf_timeframe=ltf_timeframe,
                )
                get_recorder().record(record_snap)
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
            # ── EVICTION SCAN: still scan for new entries to enable swaps ──
            # Even when slots are full, scan the universe so that
            # process_candidate_cycle can evict a loser for a better signal.
            for symbol in symbols:
                if symbol in [c[0] for c in position_candidates]: continue
                if strike_tracker and strike_tracker.is_skipped(symbol): continue
                try:
                    snap = fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings, ws_controller)
                    position_candidates.append((symbol, snap, 0.0, "eviction_scan"))
                except Exception:
                    continue
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
    global_equity = 0.0
    if executor and hasattr(executor, "get_total_balance_value"):
        try:
            global_equity = executor.get_total_balance_value()
        except:
            pass

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
                    
                    # Record Risk Sizing Vitals
                    if size != 0 and global_equity > 0:
                        entry = float(p.get("entry_price") or p.get("avg_price") or price)
                        sl = float(p.get("stop_loss") or 0.0)
                        
                        if "risk_usd" in p:
                            actual_risk_usd = float(p["risk_usd"])
                        else:
                            if sl <= 0 or entry <= 0:
                                # Snapshot null-safety grace period: skip record_risk_sizing if broker hasn't registered SL/entry yet
                                continue
                            actual_risk = abs(entry - sl) * abs(size)
                                
                            sym_upper = s.upper().replace("_", "")
                            is_jpy_quote = sym_upper.endswith("JPY") and not sym_upper.startswith("USD")
                            is_cad_quote = sym_upper.endswith("CAD") and not sym_upper.startswith("USD")
                            is_chf_quote = sym_upper.endswith("CHF") and not sym_upper.startswith("USD")
                            
                            if is_jpy_quote:
                                usdjpy_rate = 150.0
                                try:
                                    from tradebot_sci.market import oanda_provider
                                    usdjpy_rate = getattr(oanda_provider, '_last_usdjpy', 150.0) or 150.0
                                except Exception: pass
                                actual_risk_usd = actual_risk / usdjpy_rate if usdjpy_rate > 0 else actual_risk
                            elif is_cad_quote:
                                usdcad_rate = 1.35
                                try:
                                    from tradebot_sci.market import oanda_provider
                                    usdcad_rate = getattr(oanda_provider, '_last_usdcad', 1.35) or 1.35
                                except Exception: pass
                                actual_risk_usd = actual_risk / usdcad_rate if usdcad_rate > 0 else actual_risk
                            elif is_chf_quote:
                                usdchf_rate = 0.90
                                try:
                                    from tradebot_sci.market import oanda_provider
                                    usdchf_rate = getattr(oanda_provider, '_last_usdchf', 0.90) or 0.90
                                except Exception: pass
                                actual_risk_usd = actual_risk / usdchf_rate if usdchf_rate > 0 else actual_risk
                            elif sym_upper.startswith("USD") and not sym_upper.endswith("USD"):
                                actual_risk_usd = actual_risk / price if price > 0 else actual_risk
                            else:
                                actual_risk_usd = actual_risk

                        sizing_capital = global_equity
                            
                        cfg_risk_dollars = float(getattr(profile_settings, "risk_per_trade_dollars", 0.0))
                        if cfg_risk_dollars > 0 and sizing_capital > 0:
                            cfg_risk_pct = (cfg_risk_dollars / sizing_capital) * 100.0
                        else:
                            cfg_risk_pct = float(getattr(profile_settings, "risk_per_trade_pct", 0.01)) * 100.0
                            
                        try:
                            from tradebot_sci.runtime.health_monitor import health_monitor
                            leverage_capped = bool(p.get("leverage_capped", False))
                            health_monitor.record_risk_sizing(
                                cfg_risk_pct, actual_risk_usd, sizing_capital, s,
                                leverage_capped=leverage_capped, total_notional_sum=global_position_notional
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"[CYCLE] Global PnL fetch failed: {e}")

    evaluations = []
    
    # =========================================================================
    # PHASE 1: EVALUATE ALL CANDIDATES
    # =========================================================================
    for symbol, snapshot, score_placeholder, reason in candidates:
        if strike_tracker and (strike_tracker.is_skipped(symbol) or strike_tracker.is_guard_skipped(symbol)):
            skipped += 1
            continue

        attempts += 1
        pos = executor.get_open_position_snapshot(symbol) if executor else None
        
        # ── SL/TP Backfill ────────────────────────────────────────────────
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
            
            if decision and hasattr(engines[symbol], "last_gates"):
                decision.gates = engines[symbol].last_gates
            
            evaluations.append((symbol, snapshot, decision, reason))
            
            # Record Strategy Signal Vitals
            try:
                from tradebot_sci.runtime.health_monitor import health_monitor
                health_monitor.record_signal(decision.action if decision else "HOLD", symbol)
            except Exception:
                pass
            
            # If it's a hold action with a stop loss update, apply it immediately
            if not decision or decision.action in ("stand_aside", "hold"):
                reason_log = decision.notes if decision else "No strategy signal"
                d_score = (decision.score * 100.0) if (decision and decision.score is not None) else 0.0
                d_grade = (decision.grade) if (decision and decision.grade is not None) else "N/A"
                d_strat_name = engines[symbol].last_strat_name
                d_strat_grade = engines[symbol].last_strat_grade
                d_strat_score = engines[symbol].last_strat_score
                import json
                gates_str = "{}"
                if decision and getattr(decision, "gates", None):
                    _safe = {k: v for k, v in decision.gates.items() if k != "profile"}
                    try:
                        gates_str = json.dumps(_safe, default=str)
                    except Exception:
                        pass
                logger.info(f"[DECISION] symbol={symbol} action=HOLD score={d_score:.1f} grade={d_grade} strategy={d_strat_name} strat_score={d_strat_score:.1f} strat_grade={d_strat_grade} reason={reason_log} | gates={gates_str}")
                
                # ── Propagate stop modifications from hold decisions ──
                _d_sl = getattr(decision, "stop_loss", None) if decision else None
                _has_mod = hasattr(executor, "modify_stop_loss") if executor else False
                if decision and decision.action == "hold" and _d_sl is not None and executor and _has_mod:
                    try:
                        logger.info(f"[TRAIL] Calling modify_stop_loss({symbol}, {float(_d_sl)})")
                        executor.modify_stop_loss(symbol, float(_d_sl))
                    except Exception as e:
                        logger.warning(f"[TRAIL] Stop modification failed for {symbol}: {e}")

        except Exception as e:
            logger.error(f"[CYCLE] Engine evaluation failed for {symbol}: {e}")
            continue

    # =========================================================================
    # PHASE 2: RANK & EXECUTE
    # =========================================================================
    def _rank_decision(item):
        dec = item[2]
        is_manage = dec and dec.action in ("close_position", "scale_out", "scale_out_leg")
        d_score = getattr(dec, "score", 0.0) if dec else 0.0
        if d_score is None:
            d_score = 0.0
        return (not is_manage, -d_score)

    evaluations.sort(key=_rank_decision)

    for symbol, snapshot, decision, reason in evaluations:
        try:
            if not decision or decision.action in ("stand_aside", "hold", "none"):
                blocked += 1
                continue

            if executor:
                # ── OPPORTUNITY COST EVICTION ──────────────────────────
                if decision.action in ("enter_long", "enter_short", "go_long", "go_short"):
                    max_concurrent = getattr(profile_settings, "max_open_positions", 2)
                    if max_concurrent is None:
                        max_concurrent = 2
                    open_positions = executor.list_open_position_symbols() if hasattr(executor, 'list_open_position_symbols') else []
                    if len(open_positions) >= max_concurrent:
                        evict_min_hold = int(getattr(profile_settings, 'eviction_min_hold_minutes', 30)) * 60
                        worst_sym = None
                        worst_pnl = 0.0
                        for _os in open_positions:
                            _op = executor.get_open_position_snapshot(_os)
                            if not _op:
                                continue
                            _up = float(_op.get('unrealized_pnl', 0) or 0)
                            _et = _op.get('entry_time')
                            if _et:
                                if isinstance(_et, str):
                                    try:
                                        from datetime import datetime as dt
                                        _et = dt.fromisoformat(_et.replace('Z', '+00:00'))
                                    except (ValueError, TypeError):
                                        _et = None
                                if _et:
                                    _now_utc = datetime.now(timezone.utc)
                                    if _et.tzinfo is None:
                                        _et = _et.replace(tzinfo=timezone.utc)
                                    _held = (_now_utc - _et).total_seconds()
                                    if _held < evict_min_hold:
                                        continue
                            if _up < 0 and (worst_sym is None or _up < worst_pnl):
                                worst_sym = _os
                                worst_pnl = _up

                        if worst_sym is not None:
                            logger.info(
                                f"[EVICTION] Closing {worst_sym} (PnL=${worst_pnl:.2f}) "
                                f"→ making room for {symbol} ({decision.action})"
                            )
                            try:
                                from tradebot_sci.strategy.decisions import AITradeDecision as _AITD
                                evict_decision = _AITD(
                                    symbol=worst_sym,
                                    timeframe=snapshot.timeframe,
                                    bias="neutral",
                                    phase="eviction",
                                    action="close_position",
                                    entry_price=None,
                                    stop_loss=None,
                                    take_profit=None,
                                    notes=f"[EVICTION] Closed for {symbol} (score={decision.score:.2f})",
                                )
                                evict_result, evict_outcome = executor.execute_decision(evict_decision)
                                handle_execution_result(evict_outcome, strike_tracker)
                                if not (evict_result and evict_result.status.value == "executed"):
                                    logger.warning(f"[EVICTION] Failed to close {worst_sym}")
                                    blocked += 1
                                    continue
                            except Exception as e:
                                logger.error(f"[EVICTION] Error closing {worst_sym}: {e}")
                                blocked += 1
                                continue
                        else:
                            logger.info(
                                f"[EVICTION] {symbol} entry blocked — "
                                f"no evictable positions (all winning or too young)"
                            )
                            blocked += 1
                            continue

                # ── Broker-agnostic re-entry cooldown ──────────────────────
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
                if (
                    _BAR_CLOSE_GATE_ENABLED
                    and decision.action in ("go_long", "go_short", "enter_long", "enter_short")
                    and snapshot.ltf_candles
                ):
                    ltf_tf = getattr(snapshot, "ltf_timeframe", None) or "5m"
                    bar_secs = _parse_bar_seconds(ltf_tf)
                    last_close = snapshot.ltf_candles[-1].timestamp + timedelta(seconds=bar_secs)
                    age = (datetime.now(timezone.utc) - last_close).total_seconds()

                    # In replay mode, candle timestamps are from months ago (historical)
                    # so the age will be massive (>86400s).  Skip freshness check for
                    # replay — all replay candles are already closed historical bars.
                    _is_replay = age > 86400  # > 24 hours = clearly historical data

                    if not _is_replay and age > bar_secs:
                        logger.info(
                            f"[BAR-CLOSE] {symbol}: blocked {decision.action} — "
                            f"last {ltf_tf} bar closed {age:.0f}s ago (stale, max={bar_secs}s)"
                        )
                        blocked += 1
                        continue
                    elif not _is_replay:
                        logger.info(
                            f"[BAR-CLOSE] {symbol}: {decision.action} OK — "
                            f"last {ltf_tf} bar closed {age:.0f}s ago (fresh)"
                        )

                result, outcome = executor.execute_decision(decision)
                handle_execution_result(outcome, strike_tracker)
                if result and result.status.value == "executed":
                    success_symbol = symbol
                    fill_score = (decision.score * 100.0) if (decision.score is not None) else 0.0
                    fill_grade = decision.grade if (decision.grade is not None) else "N/A"
                    fill_strat_name = engines[symbol].last_strat_name if symbol in engines else "unknown"
                    fill_strat_grade = engines[symbol].last_strat_grade if symbol in engines else "N/A"
                    fill_strat_score = engines[symbol].last_strat_score if symbol in engines else 0.0
                    import json
                    gates_str = "{}"
                    if decision and getattr(decision, "gates", None):
                        _safe = {k: v for k, v in decision.gates.items() if k != "profile"}
                        try:
                            gates_str = json.dumps(_safe, default=str)
                        except Exception:
                            pass
                    logger.info(
                        f"[DECISION] symbol={symbol} action={decision.action.upper()} "
                        f"score={fill_score:.1f} grade={fill_grade} "
                        f"strategy={fill_strat_name} strat_score={fill_strat_score:.1f} "
                        f"strat_grade={fill_strat_grade} "
                        f"reason=FILL executed @ {decision.entry_price or 'market'} | gates={gates_str}"
                    )
                    from tradebot_sci.strategy.safety_guard import SafetyGuard
                    SafetyGuard.notify_entry(symbol)
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
                        broker_positions = getattr(executor, "positions", None)
                        if broker_positions and isinstance(broker_positions, dict) and symbol in broker_positions:
                            broker_positions[symbol]["strategy"] = strat_name
                    except Exception:
                        pass
                    if stop_after_submit:
                        break
        except Exception:
            logger.exception(f"[CYCLE] Fatal error processing {symbol}")
            continue

    return success_symbol, attempts, blocked, skipped
