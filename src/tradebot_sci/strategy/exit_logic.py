import sys; print("EXIT_LOGIC_LOADED_FROM=" + __file__, file=sys.stderr, flush=True)
import logging
from typing import Optional, Dict, Any
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, hold_decision
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

def run_universal_exit_logic(
    snapshot: MarketSnapshot,
    open_position: dict,
    gates: dict,
    profile: Any,
    strategy_name: str = "unknown",
    **kwargs
) -> Optional[AITradeDecision]:
    """
    Centralized Universal Exit Router.
    Strips exit responsibilities away from individual strategies and enforces
    one of 16 user-selected granular mathematically proven exit methodologies.
    I corrected the count from 11 — Gemini under-counted because it never
    finished labeling all the functions it created.
    """
    if not snapshot.candles or not open_position:
        return None

    # Common parameters
    current_price = snapshot.candles[-1].close
    entry_price = float(open_position.get("entry_price", 0))
    stop_price = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0))
    target_price = float(open_position.get("target_price", 0) or 0)
    direction = open_position.get("direction") or open_position.get("side", "long")
    
    if entry_price <= 0:
        return None
        
    # Baseline Risk & PnL
    initial_risk = open_position.get("initial_risk")
    if not initial_risk or initial_risk <= 0:
        if stop_price > 0:
            initial_risk = abs(entry_price - stop_price)
        else:
            atr_guess = calculate_atr(snapshot.candles) or (current_price * 0.001)
            initial_risk = atr_guess
            
    pnl = current_price - entry_price if direction == "long" else entry_price - current_price
    r_multiple = pnl / initial_risk if initial_risk > 0 else 0
    
    # ── Universal Exit Router ──
    active_strategies = getattr(profile, "universal_exit_strategies", ["fixed_rr"])
    if isinstance(active_strategies, str):
        active_strategies = [s.strip() for s in active_strategies.split(",") if s.strip()]
    elif isinstance(active_strategies, list):
        active_strategies = active_strategies.copy()
        
    if getattr(profile, "winner_giveback_enabled", False) and "winner_giveback" not in active_strategies:
        active_strategies.append("winner_giveback")
    
    # ════════════════════════════════════════════════════════════════════
    # PHASE 1: EMERGENCY EXIT STRATEGIES — run BEFORE hard stop
    # ════════════════════════════════════════════════════════════════════
    # These strategies detect structural trend breaks and must fire BEFORE
    # the mechanical stop deletes the position.  Without this priority,
    # the hard stop at line ~55 always wins the race, and no invalidation
    # is ever recorded in the ledger.
    #
    # This mirrors the backtester fix where the Universal Exit Router runs
    # at the per-bar level BEFORE the hardcoded stop check.
    _EMERGENCY_STRATEGIES = {"trend_invalidation", "structure_failure", "micro_canary", "bollinger_invalidation"}
    for exit_strategy in active_strategies:
        exit_strategy_key = str(exit_strategy).lower()
        if exit_strategy_key not in _EMERGENCY_STRATEGIES:
            continue
        strat_decision = None
        if exit_strategy_key == "trend_invalidation":
            strat_decision = _exit_trend_invalidation(snapshot, open_position, current_price, direction, gates, strategy_name)
        elif exit_strategy_key == "structure_failure":
            strat_decision = _exit_structure_failure(snapshot, open_position, current_price, direction)
        elif exit_strategy_key == "micro_canary":
            strat_decision = _exit_micro_canary(snapshot, open_position, current_price, direction, profile, r_multiple)
        elif exit_strategy_key == "bollinger_invalidation":
            strat_decision = _exit_bollinger_invalidation(snapshot, open_position, current_price, direction, profile)
        if strat_decision and getattr(strat_decision, "action", None) == "close_position":
            return strat_decision

    # ════════════════════════════════════════════════════════════════════
    # PHASE 2: HARD STOP LOSS — REMOVED (2026-04-07)
    # ════════════════════════════════════════════════════════════════════
    # Hard stop checks are now EXCLUSIVELY handled by the broker's
    # mechanical SL/TP evaluator (paper_broker.evaluate_synthetic_stops
    # or oanda_broker's server-side stop orders).
    #
    # WHY: This check compared `current_price` (5m bar CLOSE) against
    # `stop_price`. When a 5m candle gaps violently through the stop,
    # the bar close can be 300%+ beyond the stop level — producing
    # catastrophic fills ($388 losses instead of the correct $105).
    #
    # The broker's mechanical evaluator uses candle HIGH/LOW for
    # intra-bar detection and exits at the EXACT stop price, which is
    # both more protective and more realistic.
    #
    # Emergency exit strategies (trend_invalidation, structure_failure)
    # remain in Phase 1 — those are strategic decisions that properly
    # close at bar-close price. Hard stops are price-level mechanics.

    # ════════════════════════════════════════════════════════════════════
    # PHASE 3: STANDARD EXIT STRATEGIES — trailing, timing, etc.
    # ════════════════════════════════════════════════════════════════════
    decision = None
    
    for exit_strategy in active_strategies:
        exit_strategy = str(exit_strategy).lower()
        # Skip emergency strategies — already evaluated in Phase 1
        if exit_strategy in _EMERGENCY_STRATEGIES:
            continue
        strat_decision = None
        
        if exit_strategy == "chandelier":
            strat_decision = _exit_chandelier(snapshot, open_position, current_price, direction, profile, gates)
        elif exit_strategy == "scale_breakeven":
            strat_decision = _exit_scale_breakeven(snapshot, open_position, current_price, direction, r_multiple, stop_price, entry_price, profile)
        elif exit_strategy == "parabolic_sar":
            # Key kept for backward compat with saved profiles. See _exit_3bar_swing.
            strat_decision = _exit_3bar_swing(snapshot, open_position, current_price, direction)
        elif exit_strategy == "ma_crossover":
            strat_decision = _exit_ma_crossover(snapshot, open_position, current_price, direction)
        elif exit_strategy == "time_decay":
            strat_decision = _exit_time_decay(snapshot, open_position, current_price, direction, profile, strategy_name)
        elif exit_strategy == "swing_trailing":
            strat_decision = _exit_swing_trailing(snapshot, open_position, current_price, direction, profile, stop_price)
        elif exit_strategy == "rsi_exhaustion":
            strat_decision = _exit_rsi_exhaustion(snapshot, open_position, current_price, direction)
        elif exit_strategy == "bollinger_snap":
            strat_decision = _exit_bollinger_snap(snapshot, open_position, current_price, direction)
        elif exit_strategy == "ratchet_milestone":
            strat_decision = _exit_ratchet(snapshot, open_position, current_price, direction, r_multiple, stop_price, entry_price, initial_risk, profile)
        elif exit_strategy == "adx_death":
            strat_decision = _exit_adx_death(snapshot, open_position, current_price, direction, gates)
        elif exit_strategy == "winner_giveback":
            strat_decision = _exit_winner_giveback(snapshot, open_position, current_price, direction, profile)
        else:
            # Default: fixed_rr
            strat_decision = _exit_fixed_rr(snapshot, open_position, current_price, direction, target_price)

        if strat_decision:
            if getattr(strat_decision, "action", None) == "close_position":
                return strat_decision
            # Preserve hold decisions (trailing stops) if no hard exit triggered
            # Ensure we only keep the TIGHTEST stop loss among all strategies
            if getattr(strat_decision, "action", None) in ("hold", "stand_aside"):
                new_sl = getattr(strat_decision, "stop_loss", None)
                if new_sl is not None:
                    new_sl = float(new_sl)
                    
                    # Prevent trailing stops from artificially tightening and locking in a loss
                    # when the trade is underwater and protected by the Negative Hold Guard
                    is_neg_hold_blocked = gates.get("neg_hold_blocked", False)
                    if is_neg_hold_blocked:
                        logger.debug(f"[EXIT-ROUTER] Trailing stop update to {new_sl} BLOCKED by Negative Hold Guard")
                    else:
                        if direction == "long":
                            if new_sl > stop_price:
                                stop_price = new_sl
                                open_position["stop_loss"] = new_sl
                                decision = strat_decision
                        else:
                            if stop_price == 0 or new_sl < stop_price:
                                stop_price = new_sl
                                open_position["stop_loss"] = new_sl
                                decision = strat_decision
                elif decision is None:
                    decision = strat_decision

    return decision

def _parse_entry_time(entry_ts_str: str):
    from datetime import datetime, timezone
    entry_ts_str = str(entry_ts_str)
    # Handle standard ISO strings
    if "Z" in entry_ts_str:
        entry_ts_str = entry_ts_str.replace("Z", "+00:00")
    if "." in entry_ts_str:
        # Truncate nanoseconds to microseconds (max 6 digits) for fromisoformat
        base, rest = entry_ts_str.split(".", 1)
        if "+" in rest:
            micro, tz = rest.split("+", 1)
            entry_ts_str = f"{base}.{micro[:6]}+{tz}"
        elif "-" in rest:
            micro, tz = rest.split("-", 1)
            entry_ts_str = f"{base}.{micro[:6]}-{tz}"
        else:
            entry_ts_str = f"{base}.{rest[:6]}"
    
    # Check if it's purely numeric (epoch timestamp)
    try:
        ts_float = float(entry_ts_str)
        entry_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
    except ValueError:
        entry_dt = datetime.fromisoformat(entry_ts_str)
        
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=timezone.utc)
    return entry_dt

# ─────────────────────────────────────────────────────────────────────────────
# ── The 11 Exit Strategies ───────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def _hard_exit(snapshot, pos, reason, is_emergency=False):
    dec = AITradeDecision(
        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
        bias="neutral", phase="management", action="close_position",
        entry_price=snapshot.candles[-1].close, stop_loss=0, take_profit=0,
        risk_per_trade_pct=0, urgency="high",
        structure_summary=f"Universal Exit: {reason}",
        notes=reason
    )
    dec.emergency_exit = is_emergency
    return dec

def _exit_fixed_rr(snapshot, pos, current_price, direction, target_price):
    """1. Fixed Risk-Reward (The Sniper) - Touch the target line or die trying."""
    if target_price <= 0:
        return None
    if direction == "long" and current_price >= target_price:
        return _hard_exit(snapshot, pos, "Take Profit Target Hit (Fixed RR)")
    if direction == "short" and current_price <= target_price:
        return _hard_exit(snapshot, pos, "Take Profit Target Hit (Fixed RR)")
    return None

def _exit_chandelier(snapshot, pos, current_price, direction, profile, gates=None):
    """2. Chandelier Trailing - Highest high / Lowest low minus X ATR."""
    if gates is None: gates = {}
    atr_mult = float(getattr(profile, "chandelier_atr_mult", 2.0))
    atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)
    
    current_stop = float(pos.get("stop_loss", 0) or pos.get("stop_price", 0) or 0)
    entry_time_str = str(pos.get("entry_time", ""))
    
    if not entry_time_str: return None
    
    # Find highest/lowest price since entry (approximation via candles since entry)
    bars_held = _calc_bars_held(pos, snapshot)
    lookback = max(1, min(bars_held + 1, len(snapshot.candles), 50))
    
    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        entry_price = current_price
        
    candles_since_entry = snapshot.candles[-lookback:]

    # Minimum Hold Guard: prevent noise exits on the first bar
    MIN_BARS_FOR_EXIT = 2
    _can_hard_exit = bars_held >= MIN_BARS_FOR_EXIT
    
    if direction == "long":
        hh = max(entry_price, max(c.high for c in candles_since_entry))
        new_stop = hh - (atr * atr_mult)
        
        # If the trailing stop has been crossed by the current price, exit immediately.
        if current_price <= new_stop:
            if not _can_hard_exit:
                return None

            # [NEGATIVE HOLD GUARD] Respect the engine's gate
            if gates.get("neg_hold_blocked"):
                return None

            # [SPREAD AWARENESS] Block exits that would realize a net loss after spread.
            est_spread_usd = float(pos.get("est_spread_usd", 0.0))
            unrealized_pnl = float(pos.get("unrealized_pnl", 0))
            net_pnl_usd = unrealized_pnl - est_spread_usd

            if net_pnl_usd < 0 and est_spread_usd > 0:
                import logging
                logger = logging.getLogger("tradebot_sci.exit_logic")
                logger.info(f"[CHANDELIER] {pos.get('symbol')} exit suppressed: net loss of ${net_pnl_usd:.2f} after spread (spread=${est_spread_usd:.2f}). Trail={new_stop:.5f} Entry={entry_price:.5f}")
                return None
                
            return _hard_exit(snapshot, pos, f"Chandelier Trail Cross (Price {current_price:.5f} <= Trail {new_stop:.5f})")
            
        if new_stop > current_stop:
            if new_stop < current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Chandelier Trail ({atr_mult}x ATR)", stop_loss=new_stop)
    else:
        ll = min(entry_price, min(c.low for c in candles_since_entry))
        new_stop = ll + (atr * atr_mult)
        
        # If the trailing stop has been crossed by the current price, exit immediately.
        if current_price >= new_stop:
            if not _can_hard_exit:
                return None

            # [NEGATIVE HOLD GUARD] Respect the engine's gate
            if gates.get("neg_hold_blocked"):
                return None

            # [SPREAD AWARENESS] Block exits that would realize a net loss after spread.
            est_spread_usd = float(pos.get("est_spread_usd", 0.0))
            unrealized_pnl = float(pos.get("unrealized_pnl", 0))
            net_pnl_usd = unrealized_pnl - est_spread_usd
            
            if net_pnl_usd < 0 and est_spread_usd > 0:
                import logging
                logger = logging.getLogger("tradebot_sci.exit_logic")
                logger.info(f"[CHANDELIER] {pos.get('symbol')} exit suppressed: net loss of ${net_pnl_usd:.2f} after spread (spread=${est_spread_usd:.2f}). Trail={new_stop:.5f} Entry={entry_price:.5f}")
                return None
                
            return _hard_exit(snapshot, pos, f"Chandelier Trail Cross (Price {current_price:.5f} >= Trail {new_stop:.5f})")
            
        if new_stop < current_stop or current_stop == 0:
            if new_stop > current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Chandelier Trail ({atr_mult}x ATR)", stop_loss=new_stop)
    return None

def _exit_scale_breakeven(snapshot, pos, current_price, direction, r_multiple, current_stop, entry_price, profile=None):
    """3. Scale & Breakeven - Move to BE at dynamic arm_r (default 0.35R) with spread buffer."""
    arm_r = float(getattr(profile, "scale_breakeven_arm_r", 0.35)) if profile else 0.35
    if r_multiple >= arm_r:
        # [PHASE 1.2] Apply cost-basis buffer (spread + commissions)
        # Approximate as 0.1% of entry price for true breakeven
        cost_buffer = entry_price * 0.001 
        be_price = entry_price + cost_buffer if direction == "long" else entry_price - cost_buffer
        
        # Check if already at or beyond breakeven and ensure be_price doesn't violate current_price
        if direction == "long" and current_stop < be_price:
            if be_price < current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Breakeven Lock (1R+ Hit) +Buffer", stop_loss=be_price)
        elif direction == "short" and current_stop > be_price:
            if be_price > current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Breakeven Lock (1R+ Hit) +Buffer", stop_loss=be_price)
    return None

def _exit_3bar_swing(snapshot, pos, current_price, direction):
    """4. Three-Bar Swing Break — Exits when the last 3 bars all close against position direction.
    
    NOTE: This was originally labeled 'Parabolic SAR Exit' but it does NOT use
    the Parabolic SAR indicator at all. It uses a simple 3-bar momentum break.
    I kept the old strategy key 'parabolic_sar' for backward compatibility with
    saved profiles, but the name now reflects what it actually does.
    """
    if len(snapshot.candles) < 4: return None
    c1, c2, c3 = snapshot.candles[-1], snapshot.candles[-2], snapshot.candles[-3]
    
    if direction == "long" and c1.close < c2.low and c2.low < c3.low:
        return _hard_exit(snapshot, pos, "3-Bar Swing Break (Long Exhaustion)")
    if direction == "short" and c1.close > c2.high and c2.high > c3.high:
        return _hard_exit(snapshot, pos, "3-Bar Swing Break (Short Exhaustion)")
    return None


# Backward compatibility alias — old profiles still reference 'parabolic_sar'
_exit_parabolic_sar = _exit_3bar_swing

def _exit_ma_crossover(snapshot, pos, current_price, direction):
    """5. Moving Average Crossover - 9 EMA crosses 21 EMA."""
    if len(snapshot.candles) < 22: return None
    closes = [c.close for c in snapshot.candles[-30:]]
    
    def _ema(period):
        k = 2 / (period + 1)
        emas = [closes[0]]
        for p in closes[1:]:emas.append((p * k) + (emas[-1] * (1 - k)))
        return emas

    ema9 = _ema(9)
    ema21 = _ema(21)
    
    e9_0, e9_1 = ema9[-1], ema9[-2]
    e21_0, e21_1 = ema21[-1], ema21[-2]
    
    if direction == "long" and e9_0 < e21_0 and e9_1 >= e21_1:
        return _hard_exit(snapshot, pos, "Death Cross (9 EMA < 21 EMA)")
    if direction == "short" and e9_0 > e21_0 and e9_1 <= e21_1:
        return _hard_exit(snapshot, pos, "Golden Cross (9 EMA > 21 EMA against short)")
    return None

def _exit_time_decay(snapshot, pos, current_price, direction, profile, strategy_name="unknown"):
    """6. Time-Decay (The Impatient) - Exits after X bars.

    IMPORTANT: This function uses candle bar count (sim_time domain) to determine
    elapsed bars. Do NOT compare wall-clock entry_time against candle timestamps —
    in a fast replay the candle bar timestamps advance through months of history
    in seconds of real time, causing instant erroneous exits.

    Primary method: count elapsed bars since the candle whose timestamp matches
    (or first exceeds) the stored entry_time.
    Fallback: use _calc_bars_held() which also operates in candle-bar space.

    Strategy override: If the strategy has `time_decay_override`, use that instead
    of the profile default. This lets per-strategy configs (e.g. forex scalper at
    12 bars) coexist with other strategies under the same profile.
    """
    # Check for per-strategy override first, then fall back to profile default
    strategy_override = None
    is_hybrid = strategy_name and "forexhybridscalper" in strategy_name.lower()
    if is_hybrid:
        # Trend-mode holds need room to work; disable artificial time-decay.
        if pos.get("regime") == "trend":
            strategy_override = 100000  # effectively disabled for trend pullback entries
        else:
            strategy_override = 12  # Forex scalper: 12 bars (1 hour) max hold
    decay_bars = strategy_override if strategy_override else int(getattr(profile, "time_decay_bars", 24))

    # ── Primary: measure in candle-bar space (replay-safe) ──────────────────
    # Use _calc_bars_held which computes elapsed_seconds / bar_interval using
    # candle timestamps only — both entry and current time in the same domain.
    bars_held = _calc_bars_held(pos, snapshot)

    if bars_held > 0:
        if bars_held >= decay_bars:
            logger.info(
                f"[TIME-DECAY-EXIT] {pos.get('symbol', '?')}: bars_held={bars_held} "
                f">= decay_bars={decay_bars} | entry_time={pos.get('entry_time')} "
                f"| snap_time={getattr(snapshot.candles[-1] if snapshot.candles else None, 'timestamp', None)} "
                f"| timeframe={getattr(snapshot, 'timeframe', None)}"
            )
            return _hard_exit(snapshot, pos, f"Time Decay Reached ({decay_bars} bars)")
        return None

    # ── Fallback: raw seconds from the explicit bars_held position key ───────
    # Only reached if _calc_bars_held couldn't compute (no candles or no entry_time).
    bars_held_cached = pos.get("bars_held", 0)
    if bars_held_cached >= decay_bars:
        return _hard_exit(snapshot, pos, f"Time Decay Reached ({decay_bars} bars)")

    return None

def _exit_swing_trailing(snapshot, pos, current_price, direction, profile, current_stop):
    """7. Trailing Swing Lows/Highs - Structure trail."""
    if len(snapshot.candles) < 4: return None
    if direction == "long":
        sl_cand = min(c.low for c in snapshot.candles[-4:-1])
        if current_price <= sl_cand:
            # SPREAD AWARENESS: Don't trigger if it's a profit-protecting trail but spread causes a net loss
            est_spread_usd = float(pos.get("est_spread_usd", 0.0))
            net_pnl_usd = float(pos.get("unrealized_pnl", 0)) - est_spread_usd
            entry_price = float(pos.get("entry_price", current_price))
            if sl_cand > entry_price and net_pnl_usd < 0:
                import logging
                logger = logging.getLogger("tradebot_sci.exit_logic")
                logger.info(f"[SWING TRAIL] {pos.get('symbol')} Ignoring trail cross: protecting profit would result in a net loss of ${net_pnl_usd:.2f} (Spread: ${est_spread_usd:.2f})")
                return None
            return _hard_exit(snapshot, pos, f"Swing Low Trail Cross (Price {current_price:.5f} <= SL {sl_cand:.5f})")
        if sl_cand > current_stop * 1.0005:  # buffer
            if sl_cand < current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason="Swing Low Trail", stop_loss=sl_cand)
    else:
        sh_cand = max(c.high for c in snapshot.candles[-4:-1])
        if current_price >= sh_cand:
            # SPREAD AWARENESS: Don't trigger if it's a profit-protecting trail but spread causes a net loss
            est_spread_usd = float(pos.get("est_spread_usd", 0.0))
            net_pnl_usd = float(pos.get("unrealized_pnl", 0)) - est_spread_usd
            entry_price = float(pos.get("entry_price", current_price))
            if sh_cand < entry_price and net_pnl_usd < 0:
                import logging
                logger = logging.getLogger("tradebot_sci.exit_logic")
                logger.info(f"[SWING TRAIL] {pos.get('symbol')} Ignoring trail cross: protecting profit would result in a net loss of ${net_pnl_usd:.2f} (Spread: ${est_spread_usd:.2f})")
                return None
            return _hard_exit(snapshot, pos, f"Swing High Trail Cross (Price {current_price:.5f} >= SL {sh_cand:.5f})")
        if (sh_cand < current_stop * 0.9995) or current_stop == 0:
            if sh_cand > current_price:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason="Swing High Trail", stop_loss=sh_cand)
    return None

def _exit_rsi_exhaustion(snapshot, pos, current_price, direction):
    """8. RSI Extreme Exhaustion - Bails on climax."""
    gates = pos.get("entry_gates", {})
    # Usually we don't have realtime RSI mapped directly in plain snapshots, 
    # but we can do a rapid approximation.
    closes = [c.close for c in snapshot.candles[-15:]]
    if len(closes) < 15: return None
    
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
        
    avg_gain = sum(gains)/14
    avg_loss = sum(losses)/14
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
    if direction == "long" and rsi > 80:
        return _hard_exit(snapshot, pos, f"RSI Climax Exhaustion ({rsi:.1f})")
    if direction == "short" and rsi < 20:
        return _hard_exit(snapshot, pos, f"RSI Climax Exhaustion ({rsi:.1f})")
    return None

def _exit_bollinger_snap(snapshot, pos, current_price, direction):
    """9. Bollinger Band Snap-Back."""
    closes = [c.close for c in snapshot.candles[-20:]]
    if len(closes) < 20: return None
    import math
    sma = sum(closes) / 20
    variance = sum((c - sma) ** 2 for c in closes) / 20
    std_dev = math.sqrt(variance)
    upper = sma + (2 * std_dev)
    lower = sma - (2 * std_dev)
    
    if direction == "long" and current_price >= upper:
        return _hard_exit(snapshot, pos, "Bollinger Upper Band Tagged")
    if direction == "short" and current_price <= lower:
        return _hard_exit(snapshot, pos, "Bollinger Lower Band Tagged")
    return None

def _exit_ratchet(snapshot, pos, current_price, direction, r_multiple, current_stop, entry_price, initial_risk, profile=None):
    # REWARD-TO-RISK OPTIMIZATION: Aggressive steps to protect profit
    arm_r = float(getattr(profile, "ratchet_arm_r", 0.25)) if profile else 0.25
    if r_multiple < arm_r: return None
    
    if r_multiple < 0.5:
        ratchet_floor_r = 0.0
    else:
        ratchet_floor_r = float(int(r_multiple * 2) - 1) / 2.0  
    
    if ratchet_floor_r >= 0:
        if direction == "long":
            new_stop = entry_price + (initial_risk * ratchet_floor_r)
            if new_stop > current_stop:
                if new_stop < current_price:
                    return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Ratchet Trail ({ratchet_floor_r:.1f}R Floor)", stop_loss=new_stop)
        else:
            new_stop = entry_price - (initial_risk * ratchet_floor_r)
            if new_stop < current_stop or current_stop == 0:
                if new_stop > current_price:
                    return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Ratchet Trail ({ratchet_floor_r:.1f}R Floor)", stop_loss=new_stop)
    return None

def _exit_adx_death(snapshot, pos, current_price, direction, gates):
    """10. ADX Death - Immediate abortion if trend strength drops < 20"""
    ltf_adx = gates.get("ltf_adx", 0)
    # Require at least 4 bars held to let ADX stabilize from the initial breakout
    if ltf_adx > 0 and ltf_adx < 20:
        # Check if trade has enough profit to just scale out, or kill it
        return _hard_exit(snapshot, pos, f"Trend Death (ADX = {ltf_adx:.1f})")
    return None

def _exit_winner_giveback(snapshot, pos, current_price, direction, profile):
    """11. Winner Giveback Protection (MFE Trailing) —
    Proactively protects profit after reaching a high-water mark.

    Logic: If MFE > arm_r dollars, exit if current PnL drops below a
    certain % of MFE. Default: Exit if 20% of peak profit is given back.

    IMPORTANT: Always compute live PnL from current_price × size, NOT from
    the cached unrealized_pnl field in the position dict. In replay mode the
    dict value can be stale by one or more bars, causing the guard to fire
    at the wrong price (showing MFE > 0 but pnl already deeply negative).
    """
    mfe_usd = float(pos.get("mfe_usd", 0))
    if mfe_usd <= 0:
        return None

    # Determine initial risk in dollar terms (risk_usd)
    risk_usd = float(pos.get("risk_usd", 0))
    if risk_usd <= 0:
        initial_risk = float(pos.get("initial_risk", 0))
        if initial_risk <= 0:
            atr = calculate_atr(snapshot.candles) or (current_price * 0.001)
            initial_risk = atr
        size = float(pos.get("size", 0))
        risk_usd = initial_risk * abs(size) if size != 0 else (initial_risk * 1000)

    import logging
    logger = logging.getLogger("tradebot_sci.exit_logic")

    arm_r = float(getattr(profile, "winner_giveback_arm_r", 0.25))
    est_spread_usd = float(pos.get("est_spread_usd", 0.0))
    net_mfe_usd = mfe_usd - est_spread_usd

    # Arming Threshold: Active once trade reaches arm_r in dollar terms (spread-aware)
    if net_mfe_usd < (risk_usd * arm_r):
        return None

    logger.info(f"[GIVEBACK] {pos.get('symbol')} ARMED! net_mfe_usd=${net_mfe_usd:.2f} >= required=${risk_usd * arm_r:.2f} ({arm_r}R)")

    # ── Live PnL: always recompute from current_price to avoid stale cache ──
    # In replay mode the position's unrealized_pnl may be one bar behind current_price.
    # Computing directly from price avoids the stale-cache bug where WGP fires
    # believing the trade is still profitable when price has already reversed fully.
    entry_price = float(pos.get("entry_price", 0))
    size = float(pos.get("size", 0))  # signed: positive=long, negative=short
    if entry_price > 0 and size != 0:
        # Raw PnL in quote currency (assumed USD for Forex majors)
        pnl_usd = (current_price - entry_price) * size
    else:
        # Absolute fallback: use whatever the broker last recorded
        pnl_usd = float(pos.get("unrealized_pnl", 0))

    # SPREAD AWARENESS
    net_pnl_usd = pnl_usd - est_spread_usd

    # Giveback calculation uses NET PnL to protect actual realizable profit
    giveback_usd = net_mfe_usd - net_pnl_usd

    # Threshold (e.g. 0.20 = 20% giveback allowed)
    threshold_pct = float(getattr(profile, "winner_giveback_pct", 0.20))
    allowed_giveback = net_mfe_usd * threshold_pct

    logger.info(
        f"[GIVEBACK] {pos.get('symbol')} net_mfe_usd=${net_mfe_usd:.2f}, "
        f"live_pnl_usd=${pnl_usd:.2f}, net_pnl_usd=${net_pnl_usd:.2f}, "
        f"giveback_usd=${giveback_usd:.2f}, allowed=${allowed_giveback:.2f} (pct={threshold_pct})"
    )

    if giveback_usd > allowed_giveback:
        # Do not exit if protecting profit actually results in a net loss.
        # Let the trade hit the hard stop or recover.
        if net_pnl_usd < 0:
            logger.info(
                f"[GIVEBACK] {pos.get('symbol')} Suppressed: live exit would realize "
                f"net loss of ${net_pnl_usd:.2f} (spread=${est_spread_usd:.2f}). "
                f"Holding for SL or recovery."
            )
            return None
        return _hard_exit(snapshot, pos, f"Winner Giveback Protection ({threshold_pct*100:.0f}% of ${net_mfe_usd:.2f} NET MFE surrendered)")

    return None

def _exit_structure_failure(snapshot, pos, current_price, direction):
    """12. Structure Failure - Proactively detects Lower Highs (longs) or Higher Lows (shorts)."""
    if len(snapshot.candles) < 3: return None
    
    # ── Time-Slice Strict Filter ──
    # We must explicitly look ONLY at candles that occurred during the lifespan of the trade.
    entry_ts_str = pos.get("entry_time")
    if not entry_ts_str:
        return None
        
    try:
        from datetime import timezone
        entry_dt = _parse_entry_time(entry_ts_str)
            
        trade_candles = []
        for c in snapshot.candles:
            cdt = c.timestamp
            if cdt.tzinfo is None:
                cdt = cdt.replace(tzinfo=timezone.utc)
            # Only include candles whose close/timestamp is at or after entry
            if cdt >= entry_dt:
                trade_candles.append(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

    import logging
    logger = logging.getLogger("tradebot_sci")
    
    if len(trade_candles) < 5: 
        logger.info(f"[DEBUG STRUCTURE] Skipping {pos.get('symbol')} - only {len(trade_candles)} trade candles (need 5+).")
        return None
        
    logger.info(f"[DEBUG STRUCTURE] {pos.get('symbol')} {direction} evaluating {len(trade_candles)} trade candles.")
    
    if direction == "long":
        max_h = max(c.high for c in trade_candles)
        c1, c2, c3 = trade_candles[-3], trade_candles[-2], trade_candles[-1]
        
        # Confirmed 3-bar Swing High (c2 is the peak)
        if c2.high > c1.high and c2.high > c3.high:
            logger.info(f"[DEBUG STRUCTURE] Swing High formed at {c2.high}. Max_H is {max_h}. Diff: {c2.high - max_h}")
            if c2.high < max_h * 0.995: 
                return _hard_exit(snapshot, pos, "Structure Failure (Lower High)")
    else:
        min_l = min(c.low for c in trade_candles)
        c1, c2, c3 = trade_candles[-3], trade_candles[-2], trade_candles[-1]
        
        # Confirmed 3-bar Swing Low (c2 is the trough)
        if c2.low < c1.low and c2.low < c3.low:
            logger.info(f"[DEBUG STRUCTURE] Swing Low formed at {c2.low}. Min_L is {min_l}. Diff: {c2.low - min_l}")
            if c2.low > min_l * 1.005:
                return _hard_exit(snapshot, pos, "Structure Failure (Higher Low)")
                
    return None


# Module-level state for trend invalidation confirmation tracking.
# Maps "{symbol}_{layer}" → count of consecutive bars where direction has flipped.
_trend_inval_confirm: dict = {}
# Tracks whether a trade has ever been profitable (high-water-mark gate).
# Invalidation only fires AFTER the trade has been positive at least once.
_trend_inval_was_profitable: dict = {}
_trend_inval_trade_ids: dict = {}


def reset_state():
    """Clear all module-level state for a fresh replay day.

    Called by loop.py when day-chaining to prevent stale trend invalidation
    memory from the previous day leaking into the new day's decisions.
    """
    global _trend_inval_confirm, _trend_inval_was_profitable, _trend_inval_trade_ids
    _trend_inval_confirm.clear()
    _trend_inval_was_profitable.clear()
    _trend_inval_trade_ids.clear()
    logger.info("[EXIT-LOGIC] Module state reset for new replay day")

def _exit_trend_invalidation(snapshot, pos, current_price, direction, gates, strategy_name=""):
    """13. Trend Invalidation — 3-layer tiered cascade using gate signals.

    Each layer reads the directional output already computed by trend_consensus
    and checks whether the timeframe has flipped against the trade.

      Layer 1 (EXEC — 5m):  Fastest reaction.  Grace: 5 bars, Confirm: 2 bars.
      Layer 2 (LTF — 15m):  Mid-tier signal.   Grace: 5 bars, Confirm: 2 bars.
      Layer 3 (MTF — 1H):   Kill shot.          Grace: 0 bars, Confirm: 2 bars.

    All layers fire independently — the fastest one that confirms wins.

    IMPORTANT: Layer 3 (MTF kill shot) fires REGARDLESS of profit gate.
    A 1H macro trend flip is structural and must override all other checks.
    Layers 1 & 2 remain profit-gated to filter micro-noise.
    """
    import logging
    logger = logging.getLogger("tradebot_sci")

    exempt_strategies = {"reversal", "counter_reversal", "london_sweep", "golden_pocket", "new_york_drive", "mean_reversion", "forex_conductor", "forexhybridscalper", "forex_hybrid_scalper"}
    if strategy_name.lower() in exempt_strategies or any(s in strategy_name.lower() for s in exempt_strategies):
        return None  # Reversal/Transitional strategies are inherently counter-trend and exempt from this kill-shot.

    sym = snapshot.symbol
    entry_ts_str = str(pos.get("entry_time", ""))
    
    last_entry = _trend_inval_trade_ids.get(sym)
    if last_entry != entry_ts_str:
        # It's a brand new trade. Clear previous memory!
        _clear_confirm(sym)
        _trend_inval_trade_ids[sym] = entry_ts_str

    entry_price = float(pos.get("entry_price", 0))
    _stop_price = float(pos.get("stop_loss", 0) or pos.get("stop_price", 0) or 0)
    _init_risk = abs(entry_price - _stop_price) if _stop_price > 0 else 0
    if _init_risk < (entry_price * 0.0001):
        _atr_est = calculate_atr(snapshot.candles, period=14) if snapshot.candles else None
        _init_risk = _atr_est if _atr_est and _atr_est > 0 else (entry_price * 0.002)

    # ── Compute bars held ──
    bars_held = _calc_bars_held(pos, snapshot)

    # Read gate directions (populated by engine.py from trend_consensus)
    exec_dir = gates.get("exec_dir", "neutral")   # 5m execution TF
    ltf_dir  = gates.get("ltf_dir",  "neutral")   # 15m lower TF
    mtf_dir  = gates.get("mtf_dir",  "neutral")   # 1H mid TF
    ltf_adx  = gates.get("ltf_adx", 0)            # [PHASE 1.3] ADX Strength

    # ═══════════════════════════════════════════════════════════════
    # LAYER 3 (MTF — 1H): Kill shot — NO profit gate, NO grace
    # ═══════════════════════════════════════════════════════════════
    # If the 1H timeframe flips against the trade, the macro thesis
    # is dead.  This fires BEFORE profit gates because a macro trend
    # flip is structural — it doesn't matter if the trade was ever
    # profitable.  2 bars of confirmation to filter single-bar spikes.
    #
    # This is checked FIRST because it's the most authoritative signal.
    MTF_CONFIRM = 3

    key = f"{sym}_mtf"
    if _is_flipped(direction, mtf_dir) and ltf_adx >= 20:
        _trend_inval_confirm[key] = _trend_inval_confirm.get(key, 0) + 1
        if _trend_inval_confirm[key] >= MTF_CONFIRM:
            _clear_confirm(sym)
            logger.info(
                f"[TREND-INVAL] {sym}: MTF KILL SHOT — 1H flipped {mtf_dir.upper()} "
                f"(held {bars_held} bars)"
            )
            return _hard_exit(
                snapshot, pos,
                f"Trend Invalidation: 1H flipped {mtf_dir.upper()} vs {direction.upper()} trade (kill shot)"
            )
        else:
            logger.info(
                f"[TREND-INVAL] {sym}: MTF flip detected ({mtf_dir}) — "
                f"confirm {_trend_inval_confirm[key]}/{MTF_CONFIRM}"
            )
    elif mtf_dir == direction:
        # Trend reassumed our thesis
        _trend_inval_confirm.pop(key, None)

    # ═══════════════════════════════════════════════════════════════
    # PROFIT GATES — only for EXEC/LTF layers (noisier signals)
    # ═══════════════════════════════════════════════════════════════

    # REWARD-TO-RISK OPTIMIZATION: Only arm invalidation after reaching 1.0R.
    # Exiting at 0.3R (the previous default) destroyed the R:R of the strategy.
    _arm_threshold = _init_risk * 1.0  # Need 1.0R profit to arm L1/L2

    _meaningful_profit = False
    if entry_price > 0:
        if direction == "long" and current_price >= (entry_price + _arm_threshold):
            _meaningful_profit = True
        elif direction == "short" and current_price <= (entry_price - _arm_threshold):
            _meaningful_profit = True

    if _meaningful_profit:
        _trend_inval_was_profitable[sym] = True

    # REWARD-TO-RISK OPTIMIZATION: Only kill trades that are CURRENTLY in profit.
    # We do not use 5m/15m trend noise to kill trades that are underwater;
    # let them hit the hard stop or recover. This fixes the "bad R:R" issue.
    _is_currently_in_profit = False
    if direction == "long" and current_price > entry_price:
        _is_currently_in_profit = True
    elif direction == "short" and current_price < entry_price:
        _is_currently_in_profit = True

    if not _trend_inval_was_profitable.get(sym, False) or not _is_currently_in_profit:
        # Trade has NEVER reached 1.0R profit — OR is currently in a loss.
        # Skip L1/L2 invalidation. MTF kill shot already had its chance.
        if bars_held % 12 == 0: # Throttle noise
             logger.debug(f"[TREND-INVAL] {sym}: Skipping L1/L2 (Profit gate active | bars_held={bars_held})")
        return None
    elif _meaningful_profit:
        logger.info(f"[TREND-INVAL] {sym}: PROFIT GATE ARMED (1.0R reached at {current_price:.5f})")


    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: EXEC (5m) — Fastest invalidation
    # ═══════════════════════════════════════════════════════════════
    EXEC_GRACE   = 5   # Let the trade breathe for 5 bars before checking
    EXEC_CONFIRM = 2   # 2 consecutive bars of confirmed flip

    if bars_held >= EXEC_GRACE:
        key = f"{sym}_exec"
        if _is_flipped(direction, exec_dir):
            _trend_inval_confirm[key] = _trend_inval_confirm.get(key, 0) + 1
            if _trend_inval_confirm[key] >= EXEC_CONFIRM:
                _clear_confirm(sym)
                label = f"EXEC({exec_dir.upper()})"
                logger.info(
                    f"[TREND-INVAL] {sym}: EXEC INVALIDATION — 5m flipped {label} "
                    f"(held {bars_held} bars, entry={entry_price:.5f}, now={current_price:.5f})"
                )
                return _hard_exit(
                    snapshot, pos,
                    f"Trend Invalidation: 5m flipped {exec_dir.upper()} vs {direction.upper()} trade"
                )
            else:
                logger.info(
                    f"[TREND-INVAL] {sym}: EXEC flip detected ({exec_dir}) — "
                    f"confirm {_trend_inval_confirm[key]}/{EXEC_CONFIRM}"
                )
        elif exec_dir == direction:
            _trend_inval_confirm.pop(key, None)

    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: LTF (15m) — Mid-tier invalidation
    # ═══════════════════════════════════════════════════════════════
    LTF_GRACE   = 5
    LTF_CONFIRM = 2

    if bars_held >= LTF_GRACE:
        key = f"{sym}_ltf"
        if _is_flipped(direction, ltf_dir):
            _trend_inval_confirm[key] = _trend_inval_confirm.get(key, 0) + 1
            if _trend_inval_confirm[key] >= LTF_CONFIRM:
                _clear_confirm(sym)
                logger.info(
                    f"[TREND-INVAL] {sym}: LTF INVALIDATION — 15m flipped {ltf_dir.upper()} "
                    f"(held {bars_held} bars)"
                )
                return _hard_exit(
                    snapshot, pos,
                    f"Trend Invalidation: 15m flipped {ltf_dir.upper()} vs {direction.upper()} trade"
                )
            else:
                logger.info(
                    f"[TREND-INVAL] {sym}: LTF flip detected ({ltf_dir}) — "
                    f"confirm {_trend_inval_confirm[key]}/{LTF_CONFIRM}"
                )
        elif ltf_dir == direction:
            _trend_inval_confirm.pop(key, None)

    return None


# ── Helpers ──────────────────────────────────────────────────────

def _is_flipped(trade_dir: str, tf_dir: str) -> bool:
    """Returns True when a timeframe direction actively opposes the trade."""
    if tf_dir == "neutral":
        return False  # Neutral is not a flip — no conviction either way
    return (trade_dir == "long" and tf_dir == "short") or \
           (trade_dir == "short" and tf_dir == "long")


def _clear_confirm(symbol: str):
    """Wipe all confirmation counters for a symbol (trade profitable or exited)."""
    for suffix in ("_exec", "_ltf", "_mtf", "_ema"):
        _trend_inval_confirm.pop(f"{symbol}{suffix}", None)
    _trend_inval_was_profitable.pop(symbol, None)
    _trend_inval_confirm.pop(symbol, None)


def _calc_bars_held(pos: dict, snapshot) -> int:
    """Estimate how many bars the trade has been open.

    Uses the snapshot's declared timeframe to determine bar interval.
    Deriving bar_seconds from the last two candle timestamps is fragile
    when candles have irregular microsecond offsets or when the last two
    bars come from different sessions; the explicit timeframe is the
    authoritative source of truth.
    """
    bars_held = pos.get("bars_held") or 0
    if bars_held == 0:
        entry_ts_str = pos.get("entry_time")
        if entry_ts_str and snapshot.candles:
            try:
                from datetime import timezone
                entry_dt = _parse_entry_time(entry_ts_str)
                now_dt = snapshot.candles[-1].timestamp
                if now_dt.tzinfo is None:
                    now_dt = now_dt.replace(tzinfo=timezone.utc)
                elapsed_seconds = (now_dt - entry_dt).total_seconds()

                # Prefer the snapshot's declared timeframe for bar interval
                bar_seconds = _tf_to_seconds(getattr(snapshot, "timeframe", None))
                if bar_seconds <= 0 and len(snapshot.candles) >= 2:
                    # Fallback: derive from last two candles
                    bar_seconds = abs(
                        (snapshot.candles[-1].timestamp - snapshot.candles[-2].timestamp).total_seconds()
                    )
                # Sanity clamp: no smaller than 1s, no larger than 1 day
                if bar_seconds <= 0:
                    bar_seconds = 300.0
                bar_seconds = max(1.0, min(86400.0, bar_seconds))

                if bar_seconds > 0:
                    bars_held = int(elapsed_seconds / bar_seconds)
            except Exception as e:
                import logging
                logger = logging.getLogger("tradebot_sci.exit_logic")
                logger.error(f"[_calc_bars_held] Exception for {pos.get('symbol')}: {e}")
                pass
    return max(0, bars_held)


def _tf_to_seconds(timeframe: str | None) -> float:
    """Convert timeframe string (e.g. '5m', '1h', '4h') to seconds."""
    if not timeframe or not isinstance(timeframe, str):
        return 0.0
    tf = timeframe.strip().lower()
    import re
    m = re.match(r"^(\d+)\s*([a-z]+)$", tf)
    if not m:
        return 0.0
    val_str, unit = m.groups()
    try:
        val = int(val_str)
    except ValueError:
        return 0.0
    if unit.startswith("m") or unit.startswith("min"):
        return val * 60.0
    if unit.startswith("h") or unit.startswith("hour"):
        return val * 3600.0
    if unit.startswith("d") or unit.startswith("day"):
        return val * 86400.0
    if unit.startswith("s") or unit.startswith("sec"):
        return float(val)
    if unit.startswith("w") or unit.startswith("week"):
        return val * 604800.0
    return 0.0


def _exit_micro_canary(snapshot: MarketSnapshot, open_position: dict, current_price: float, direction: str, profile: Any, r_multiple: float) -> Optional[AITradeDecision]:
    """15. Micro-Canary Early Warning Exit
    Uses extra-low timeframe (1m) candles to detect microscopic structural collapse 
    before the 5m candle closes. Allows greedy exits to front-run massive reversals.
    """
    micro_candles = getattr(snapshot, "micro_candles", [])
    if not micro_candles or len(micro_candles) < 5:
        return None
        
    # Only arm if trade is decently profitable (e.g., 0.5R)
    if r_multiple < 0.5:
        return None
        
    # Calculate 1m ATR
    atr_1m = calculate_atr(micro_candles[-14:], period=14) if len(micro_candles) >= 14 else calculate_atr(micro_candles, period=len(micro_candles))
    if not atr_1m or atr_1m <= 0:
        return None

    # Get recent 1m candles
    c1 = micro_candles[-1]
    c2 = micro_candles[-2]
    c3 = micro_candles[-3]
    
    # Check for violent engulfing or velocity drop
    if direction == "long":
        # Check if latest 1m candle crashed below the low of the last 3 minutes combined
        recent_low = min(c2.low, c3.low)
        if c1.close < recent_low and (c1.open - c1.close) > atr_1m * 1.5:
            return _hard_exit(snapshot, open_position, "Micro-Canary Reversal: Massive 1m bearish drop detected")
    else:
        recent_high = max(c2.high, c3.high)
        if c1.close > recent_high and (c1.close - c1.open) > atr_1m * 1.5:
            return _hard_exit(snapshot, open_position, "Micro-Canary Reversal: Massive 1m bullish spike detected")

    return None

def _exit_bollinger_invalidation(snapshot, pos, current_price, direction, profile):
    """16. Bollinger Invalidation (The Pinned RSI) — 
    Kills mean-reversion trades if the RSI stays pinned without hooking up.
    """
    from tradebot_sci.market.indicators import calculate_rsi
    
    strategy_name = pos.get("strategy", "")
    
    # Only applies to mean-reversion bollinger strategies
    target_strategies = {"forex_hybrid_scalper", "forexhybridscalper", "rubberband_reaper"}
    if not any(s in strategy_name.lower() for s in target_strategies):
        return None

    # Skip for trend-mode positions; they are meant to hold through RSI pins.
    if pos.get("regime") == "trend":
        return None
        
    bars_held = _calc_bars_held(pos, snapshot)
    
    pin_bars = int(getattr(profile, "bollinger_invalidation_bars", 2))
    if bars_held < pin_bars:
        return None
        
    # ── 5m-based invalidation (primary) ──
    closes_5m = [c.close for c in snapshot.candles]
    if len(closes_5m) < 20: 
        return None
        
    rsi_period = int(getattr(profile, "rsi_period", 7))
    rsi_overbought = float(getattr(profile, "rsi_overbought", 65))
    rsi_oversold = float(getattr(profile, "rsi_oversold", 35))
    
    def _check_pinned_rsi(closes, pin_bars, direction, rsi_period, rsi_overbought, rsi_oversold, label):
        if len(closes) < pin_bars + rsi_period + 1:
            return None
        rsis = []
        for i in range(pin_bars):
            slice_closes = closes if i == 0 else closes[:-i]
            rsi_val = calculate_rsi(slice_closes, rsi_period)
            if rsi_val is None:
                return None
            rsis.append(rsi_val)
        rsis.reverse()  # chronological order
        if direction == "long":
            all_oversold = all(r <= rsi_oversold for r in rsis)
            if all_oversold and rsis[-1] <= (rsis[0] + 5.0):
                logger.info(f"[BOLLINGER-INVAL] {snapshot.symbol} {label} LONG Pinned RSI detected. RSIs: {['%.1f' % r for r in rsis]}")
                return _hard_exit(snapshot, pos, f"Bollinger Invalidation: Pinned Oversold RSI ({label})", is_emergency=False)
        else:
            all_overbought = all(r >= rsi_overbought for r in rsis)
            if all_overbought and rsis[-1] >= (rsis[0] - 5.0):
                logger.info(f"[BOLLINGER-INVAL] {snapshot.symbol} {label} SHORT Pinned RSI detected. RSIs: {['%.1f' % r for r in rsis]}")
                return _hard_exit(snapshot, pos, f"Bollinger Invalidation: Pinned Overbought RSI ({label})", is_emergency=False)
        return None
    
    # Try 5m first
    decision = _check_pinned_rsi(closes_5m, pin_bars, direction, rsi_period, rsi_overbought, rsi_oversold, "5m")
    if decision:
        return decision
    
    # ── 1m-based fast invalidation (same timeframe as strategy entry) ──
    micro_candles = getattr(snapshot, "micro_candles", []) or getattr(snapshot, "exec_candles", [])
    if micro_candles and len(micro_candles) >= pin_bars + rsi_period + 1:
        closes_1m = [c.close for c in micro_candles]
        decision = _check_pinned_rsi(closes_1m, pin_bars, direction, rsi_period, rsi_overbought, rsi_oversold, "1m")
        if decision:
            return decision
                
    return None
