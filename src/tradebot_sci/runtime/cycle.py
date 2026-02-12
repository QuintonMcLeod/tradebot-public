from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.runtime.trackers import StrikeTracker

if TYPE_CHECKING:
    from tradebot_sci.runtime.controller import RuntimeController

logger = logging.getLogger(__name__)

def fetch_snapshot(
    provider: Any, 
    cache: Dict[tuple, MarketSnapshot], 
    symbol: str, 
    timeframe: str, 
    profile_settings: Any, 
    market_settings: Any, 
    ws_controller: Optional[RuntimeController] = None
) -> MarketSnapshot:
    """Fetches high/low timeframe candles and infers trends."""
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
        
        if ws_controller and ltf_candles:
            # [ANTIGRAVITY FIX] Broadcast last 2 candles to ensure transitions are captured
            # and verify no gaps even if bot was busy during the explicit close time.
            recent_candles = ltf_candles[-2:]
            for c in recent_candles:
                ws_controller.broadcast_candle(symbol, ltf_timeframe, c)

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


def _get_dynamic_max_concurrent(profile_settings: Any, now: datetime) -> int:
    """
    Get dynamic concurrent positions limit.
    For oanda_multi_asset:
    - 8 from Friday 17:00 ET to Sunday 17:00 ET
    - 4 otherwise
    """
    # Try to find profile name in settings or name attribute
    profile_name = getattr(profile_settings, "name", "")
    if not profile_name:
        if "oanda" in str(getattr(profile_settings, "runtime_overrides", "")).lower():
            profile_name = "oanda_multi_asset"
            
    val = getattr(profile_settings, "max_concurrent_positions", 1)
    if val is None:
        val = 1

    if profile_name != "oanda_multi_asset":
        return val

    # Convert now to America/New_York
    local_now = (now or datetime.now()).astimezone(ZoneInfo("America/New_York"))
    
    # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    wd = local_now.weekday()
    hr = local_now.hour
    
    is_weekend = False
    if wd == 4 and hr >= 17: # Friday after 5pm
        is_weekend = True
    elif wd == 5: # Saturday all day
        is_weekend = True
    elif wd == 6 and hr < 17: # Sunday before 5pm
        is_weekend = True
        
    return 8 if is_weekend else 4


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
    candidates = position_candidates.copy()
    for symbol in symbols:
        if symbol in [c[0] for c in candidates]: continue
        if strike_tracker and strike_tracker.is_skipped(symbol): continue
        
        try:
            snap = fetch_snapshot(provider, snapshot_cache, symbol, timeframe, profile_settings, market_settings, ws_controller)
            score, grade = engines[symbol].score_icc_grade(snap)
            if score >= profile_settings.structure_score_threshold:
                candidates.append((symbol, snap, score, grade))
            else:
                logger.info(f"[DECISION] symbol={symbol} action=HOLD score={score*100:.1f} grade={grade} reason=Score {score*100:.1f} ({grade}) below threshold {profile_settings.structure_score_threshold*100:.1f}")
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
                    # [ANTIGRAVITY FIX] Track total position notional value
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
        
        try:
            liq_cap = executor.get_liquid_capital(symbol) if executor else None
            
            decision = engines[symbol].decide(
                snapshot.timeframe, 
                open_position=pos, 
                snapshot=snapshot, 
                current_capital=liq_cap,
                execution_capabilities={
                    "total_unrealized_pnl": global_pnl,
                    "total_position_notional": global_position_notional,
                    "open_position_count": global_open_count
                }
            )
            # [ANTIGRAVITY FIX] Include 'hold' in decision logging to ensure the Decisions Panel is populated for existing positions
            if not decision or decision.action in ("stand_aside", "hold"):
                reason = decision.notes if decision else "No strategy signal"
                d_score = (decision.score * 100.0) if (decision and decision.score is not None) else 0.0
                d_grade = (decision.grade) if (decision and decision.grade is not None) else "N/A"
                logger.info(f"[DECISION] symbol={symbol} action=HOLD score={d_score:.1f} grade={d_grade} reason={reason}")
                blocked += 1
                continue
            
            if executor:
                result, outcome = executor.execute_decision(decision)
                handle_execution_result(outcome, strike_tracker)
                if result and result.status.value == "executed":
                    success_symbol = symbol
                    if stop_after_submit:
                        break
        except Exception:
            logger.exception(f"[CYCLE] Fatal error processing {symbol}")
            continue

    return success_symbol, attempts, blocked, skipped
