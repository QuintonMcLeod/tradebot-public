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
    one of 11 user-selected granular mathematically proven exit methodologies.
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
    _EMERGENCY_STRATEGIES = {"trend_invalidation", "structure_failure", "micro_canary"}
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
            strat_decision = _exit_parabolic_sar(snapshot, open_position, current_price, direction)
        elif exit_strategy == "ma_crossover":
            strat_decision = _exit_ma_crossover(snapshot, open_position, current_price, direction)
        elif exit_strategy == "time_decay":
            strat_decision = _exit_time_decay(snapshot, open_position, current_price, direction, profile)
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
    """5. Fixed Risk-Reward (The Sniper) - Touch the target line or die trying."""
    if target_price <= 0:
        return None
    if direction == "long" and current_price >= target_price:
        return _hard_exit(snapshot, pos, "Take Profit Target Hit (Fixed RR)")
    if direction == "short" and current_price <= target_price:
        return _hard_exit(snapshot, pos, "Take Profit Target Hit (Fixed RR)")
    return None

def _exit_chandelier(snapshot, pos, current_price, direction, profile, gates=None):
    """1. Chandelier Trailing - Highest high / Lowest low minus X ATR."""
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
    """2. Scale & Breakeven - Move to BE at dynamic arm_r (default 0.35R) with spread buffer."""
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

def _exit_parabolic_sar(snapshot, pos, current_price, direction):
    """3. Parabolic SAR Exit - Bails on momentum break. (Simplified via 3-bar swing break)"""
    if len(snapshot.candles) < 4: return None
    c1, c2, c3 = snapshot.candles[-1], snapshot.candles[-2], snapshot.candles[-3]
    
    if direction == "long" and c1.close < c2.low and c2.low < c3.low:
        return _hard_exit(snapshot, pos, "Parabolic Momentum Break (Long Exhaustion)")
    if direction == "short" and c1.close > c2.high and c2.high > c3.high:
        return _hard_exit(snapshot, pos, "Parabolic Momentum Break (Short Exhaustion)")
    return None

def _exit_ma_crossover(snapshot, pos, current_price, direction):
    """4. Moving Average Crossover - 9 EMA crosses 21 EMA."""
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

def _exit_time_decay(snapshot, pos, current_price, direction, profile):
    """6. Time-Decay (The Impatient) - Exits after X bars."""
    decay_bars = int(getattr(profile, "time_decay_bars", 24))
    bars_held = pos.get("bars_held", 0)  # Ideally updated by backend
    
    # Fallback to estimating time via entry timestamp
    entry_ts_str = pos.get("entry_time")
    if entry_ts_str:
        try:
            from datetime import datetime, timezone
            import dateutil.parser
            entry_dt = dateutil.parser.parse(str(entry_ts_str))
            if entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)
            now_dt = snapshot.candles[-1].timestamp
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=timezone.utc)
            diff_seconds = (now_dt - entry_dt).total_seconds()
            
            # Rough estimate: 24 bars of 5m = 120 mins = 7200 seconds
            # Without explicitly knowing timeframe here perfectly, we assume 15m average if not provided
            max_seconds = decay_bars * 15 * 60
            if "5m" in str(snapshot.timeframe): max_seconds = decay_bars * 5 * 60
            elif "1h" in str(snapshot.timeframe) or "H1" in str(snapshot.timeframe): max_seconds = decay_bars * 60 * 60
            
            if diff_seconds > max_seconds:
                return _hard_exit(snapshot, pos, f"Time Decay Reached ({decay_bars} bars)")
        except Exception as e:
            import traceback
            traceback.print_exc()
            pass
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
    """11. ADX Death - Immediate abortion if trend strength drops < 20"""
    ltf_adx = gates.get("ltf_adx", 0)
    # Require at least 4 bars held to let ADX stabilize from the initial breakout
    if ltf_adx > 0 and ltf_adx < 20:
        # Check if trade has enough profit to just scale out, or kill it
        return _hard_exit(snapshot, pos, f"Trend Death (ADX = {ltf_adx:.1f})")
    return None

def _exit_winner_giveback(snapshot, pos, current_price, direction, profile):
    """14. Winner Giveback Protection (MFE Trailing) — 
    Proactively protects profit after reaching a high-water mark.
    
    Logic: If MFE > 1.5R, exit if current PnL drops below a certain % of MFE.
    Default: Exit if 30% of peak profit is given back.
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
        
    # Current PnL (USD)
    pnl_usd = float(pos.get("unrealized_pnl", 0))
    if pos.get("unrealized_pnl") is None:
        # Fallback estimation if unrealized_pnl missing
        entry_price = float(pos.get("entry_price", 0))
        size = float(pos.get("size", 0))
        if entry_price > 0 and size != 0:
            # Note: This is an estimation that assumes Quote currency is USD.
            pnl_usd = (current_price - entry_price) * size
            
    # SPREAD AWARENESS
    net_pnl_usd = pnl_usd - est_spread_usd
            
    # Giveback calculation uses NET PnL to protect actual realizable profit
    giveback_usd = net_mfe_usd - net_pnl_usd
    
    # Threshold (e.g. 0.20 = 20% giveback allowed)
    threshold_pct = float(getattr(profile, "winner_giveback_pct", 0.20))
    allowed_giveback = net_mfe_usd * threshold_pct
    
    logger.info(f"[GIVEBACK] {pos.get('symbol')} net_mfe_usd=${net_mfe_usd:.2f}, net_pnl_usd=${net_pnl_usd:.2f}, giveback_usd=${giveback_usd:.2f}, allowed=${allowed_giveback:.2f} (pct={threshold_pct})")
    
    if giveback_usd > allowed_giveback:
        # Do not exit if protecting profit actually results in a net loss! Let it ride or hit standard stop loss.
        if net_pnl_usd < 0:
            logger.info(f"[GIVEBACK] {pos.get('symbol')} Ignoring signal: executing would result in a net loss of ${net_pnl_usd:.2f} (Spread: ${est_spread_usd:.2f})")
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
        import dateutil.parser
        entry_dt = dateutil.parser.parse(str(entry_ts_str))
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
            
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

    exempt_strategies = {"reversal", "counter_reversal", "london_sweep", "golden_pocket", "new_york_drive", "mean_reversion", "forex_conductor"}
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
    """Estimate how many bars the trade has been open."""
    bars_held = pos.get("bars_held", 0)
    if bars_held == 0:
        entry_ts_str = pos.get("entry_time")
        if entry_ts_str and snapshot.candles:
            try:
                from datetime import datetime, timezone
                import dateutil.parser
                entry_dt = dateutil.parser.parse(str(entry_ts_str))
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                now_dt = snapshot.candles[-1].timestamp
                if now_dt.tzinfo is None:
                    now_dt = now_dt.replace(tzinfo=timezone.utc)
                elapsed_seconds = (now_dt - entry_dt).total_seconds()
                if len(snapshot.candles) >= 2:
                    bar_seconds = abs((snapshot.candles[-1].timestamp - snapshot.candles[-2].timestamp).total_seconds())
                    if bar_seconds > 0:
                        bars_held = int(elapsed_seconds / bar_seconds)
            except Exception:
                pass
    return bars_held


def _exit_micro_canary(snapshot: MarketSnapshot, open_position: dict, current_price: float, direction: str, profile: Any, r_multiple: float) -> Optional[AITradeDecision]:
    """
    Micro-Canary Early Warning Exit
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
