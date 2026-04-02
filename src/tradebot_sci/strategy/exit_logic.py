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
    strategy_name: str
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
    direction = open_position.get("direction", "long")
    
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
    
    
    # Ensure hard stop losses are ALWAYS respected regardless of strategy
    if stop_price > 0:
        if direction == "long" and current_price <= stop_price:
            return _hard_exit(snapshot, open_position, "Hard Stop Loss Hit")
        if direction == "short" and current_price >= stop_price:
            return _hard_exit(snapshot, open_position, "Hard Stop Loss Hit")

    decision = None
    
    for exit_strategy in active_strategies:
        exit_strategy = str(exit_strategy).lower()
        strat_decision = None
        
        if exit_strategy == "chandelier":
            strat_decision = _exit_chandelier(snapshot, open_position, current_price, direction, profile)
        elif exit_strategy == "scale_breakeven":
            strat_decision = _exit_scale_breakeven(snapshot, open_position, current_price, direction, r_multiple, stop_price, entry_price)
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
            strat_decision = _exit_ratchet(snapshot, open_position, current_price, direction, r_multiple, stop_price, entry_price, initial_risk)
        elif exit_strategy == "adx_death":
            strat_decision = _exit_adx_death(snapshot, open_position, current_price, direction, gates)
        elif exit_strategy == "structure_failure":
            strat_decision = _exit_structure_failure(snapshot, open_position, current_price, direction)
        elif exit_strategy == "trend_invalidation":
            strat_decision = _exit_trend_invalidation(snapshot, open_position, current_price, direction, gates)
        else:
            # Default: fixed_rr
            strat_decision = _exit_fixed_rr(snapshot, open_position, current_price, direction, target_price)

        if strat_decision:
            if getattr(strat_decision, "action", None) == "close_position":
                return strat_decision
            # Preserve hold decisions (trailing stops) if no hard exit triggered
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

def _exit_chandelier(snapshot, pos, current_price, direction, profile):
    """1. Chandelier Trailing - Highest high / Lowest low minus X ATR."""
    atr_mult = float(getattr(profile, "chandelier_atr_mult", 2.0))
    atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)
    
    current_stop = float(pos.get("stop_price", 0))
    entry_time_str = str(pos.get("entry_time", ""))
    
    if not entry_time_str: return None
    
    # Find highest/lowest price since entry (approximation via last 50 candles cache)
    lookback = min(len(snapshot.candles), 50)
    if lookback < 2: return None
    
    if direction == "long":
        hh = max(c.high for c in snapshot.candles[-lookback:])
        new_stop = hh - (atr * atr_mult)
        if new_stop > current_stop:
            return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Chandelier Trail ({atr_mult}x ATR)", stop_loss=new_stop)
    else:
        ll = min(c.low for c in snapshot.candles[-lookback:])
        new_stop = ll + (atr * atr_mult)
        if new_stop < current_stop or current_stop == 0:
            return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Chandelier Trail ({atr_mult}x ATR)", stop_loss=new_stop)
    return None

def _exit_scale_breakeven(snapshot, pos, current_price, direction, r_multiple, current_stop, entry_price):
    """2. Scale & Breakeven - Move to BE at 1R."""
    if r_multiple >= 1.0:
        # Check if already at breakeven
        if direction == "long" and current_stop < entry_price:
            return hold_decision(snapshot.symbol, snapshot.timeframe, reason="Breakeven Lock (1R+ Hit)", stop_loss=entry_price)
        elif direction == "short" and current_stop > entry_price:
            return hold_decision(snapshot.symbol, snapshot.timeframe, reason="Breakeven Lock (1R+ Hit)", stop_loss=entry_price)
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
        if sl_cand > current_stop * 1.0005:  # buffer
            return hold_decision(snapshot.symbol, snapshot.timeframe, reason="Swing Low Trail", stop_loss=sl_cand)
    else:
        sh_cand = max(c.high for c in snapshot.candles[-4:-1])
        if (sh_cand < current_stop * 0.9995) or current_stop == 0:
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

def _exit_ratchet(snapshot, pos, current_price, direction, r_multiple, current_stop, entry_price, initial_risk):
    """10. Profit Protection Ratchet (0.5R steps)"""
    if r_multiple < 0.5: return None
    
    # 0.5->0R, 1.0->0.5R, 1.5->1.0R
    ratchet_floor_r = float(int(r_multiple * 2) - 1) / 2.0  
    
    if ratchet_floor_r >= 0:
        if direction == "long":
            new_stop = entry_price + (initial_risk * ratchet_floor_r)
            if new_stop > current_stop:
                return hold_decision(snapshot.symbol, snapshot.timeframe, reason=f"Ratchet Trail ({ratchet_floor_r:.1f}R Floor)", stop_loss=new_stop)
        else:
            new_stop = entry_price - (initial_risk * ratchet_floor_r)
            if new_stop < current_stop or current_stop == 0:
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
                return _hard_exit(snapshot, pos, "Structure Failure (Lower High)", is_emergency=True)
    else:
        min_l = min(c.low for c in trade_candles)
        c1, c2, c3 = trade_candles[-3], trade_candles[-2], trade_candles[-1]
        
        # Confirmed 3-bar Swing Low (c2 is the trough)
        if c2.low < c1.low and c2.low < c3.low:
            logger.info(f"[DEBUG STRUCTURE] Swing Low formed at {c2.low}. Min_L is {min_l}. Diff: {c2.low - min_l}")
            if c2.low > min_l * 1.005:
                return _hard_exit(snapshot, pos, "Structure Failure (Higher Low)", is_emergency=True)
                
    return None

# Module-level state for trend invalidation confirmation tracking.
# Maps "{symbol}_{layer}" → count of consecutive bars where direction has flipped.
_trend_inval_confirm: dict = {}
# Tracks whether a trade has ever been profitable (high-water-mark gate).
# Invalidation only fires AFTER the trade has been positive at least once.
_trend_inval_was_profitable: dict = {}

def _exit_trend_invalidation(snapshot, pos, current_price, direction, gates):
    """13. Trend Invalidation — 3-layer tiered cascade using gate signals.

    Each layer reads the directional output already computed by trend_consensus
    and checks whether the timeframe has flipped against the trade.

      Layer 1 (EXEC — 5m):  Fastest reaction.  Grace: 5 bars, Confirm: 3 bars.
      Layer 2 (LTF — 15m):  Mid-tier signal.   Grace: 8 bars, Confirm: 3 bars.
      Layer 3 (MTF — 1H):   Kill shot.          Grace: 0 bars, Confirm: 2 bars.

    All layers fire independently — the fastest one that confirms wins.
    Profit-gated: only fires when the trade is currently at a LOSS.
    """
    import logging
    logger = logging.getLogger("tradebot_sci")

    # ── "Was meaningfully profitable" high-water-mark gate ──
    # Invalidation is a PROFIT PROTECTION tool. It should only fire after
    # the trade has reached meaningful profit (≥ 0.3R), not just a 1-pip
    # wiggle into the green. Trades that never reach 0.3R profit will
    # hit their normal stop/target instead.
    entry_price = float(pos.get("entry_price", 0))
    sym = snapshot.symbol
    _stop_price = float(pos.get("stop_loss", 0) or pos.get("stop_price", 0) or 0)
    _init_risk = abs(entry_price - _stop_price) if _stop_price > 0 else 0
    if _init_risk < (entry_price * 0.0001):
        _atr_est = calculate_atr(snapshot.candles, period=14) if snapshot.candles else None
        _init_risk = _atr_est if _atr_est and _atr_est > 0 else (entry_price * 0.002)
    _arm_threshold = _init_risk * 0.3  # Need 0.3R profit to arm invalidation

    _meaningful_profit = False
    if entry_price > 0:
        if direction == "long" and current_price >= (entry_price + _arm_threshold):
            _meaningful_profit = True
        elif direction == "short" and current_price <= (entry_price - _arm_threshold):
            _meaningful_profit = True

    if _meaningful_profit:
        _trend_inval_was_profitable[sym] = True

    if not _trend_inval_was_profitable.get(sym, False):
        # Trade has NEVER reached 0.3R profit — skip invalidation entirely.
        # Let the hard stop or other exit strategies handle it.
        return None

    # ── Profit gate: never kill a meaningfully profitable trade ──
    # If the trade is currently in strong profit (>0.5R), spare it for this bar.
    # Importantly, we DO NOT wipe the confirmation counters. If the trend 
    # remains structurally broken and drops back into a loss, it will exit.
    _stop_price = float(pos.get("stop_loss", 0) or pos.get("stop_price", 0) or 0)
    _initial_risk = abs(entry_price - _stop_price) if _stop_price > 0 else 0
    if _initial_risk < (entry_price * 0.0001):  # Less than ~1 pip for forex
        # Fallback to ATR-based risk estimate  
        _atr_risk = calculate_atr(snapshot.candles, period=14) if snapshot.candles else None
        _initial_risk = _atr_risk if _atr_risk and _atr_risk > 0 else (entry_price * 0.002)
    _profit_threshold = _initial_risk * 0.5  # Need 0.5R profit to suppress invalidation
    if entry_price > 0:
        if direction == "long" and current_price >= (entry_price + _profit_threshold):
            return None
        if direction == "short" and current_price <= (entry_price - _profit_threshold):
            return None

    # ── Compute bars held ──
    bars_held = _calc_bars_held(pos, snapshot)
    sym = snapshot.symbol

    # Read gate directions (populated by engine.py from trend_consensus)
    exec_dir = gates.get("exec_dir", "neutral")   # 5m execution TF
    ltf_dir  = gates.get("ltf_dir",  "neutral")   # 15m lower TF
    mtf_dir  = gates.get("mtf_dir",  "neutral")   # 1H mid TF

    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: EXEC (5m) — Fastest invalidation
    # ═══════════════════════════════════════════════════════════════
    # The execution timeframe is where the entry thesis lives.
    # If the 5m flips against the trade, the micro-trend is broken.
    EXEC_GRACE   = 5   # Let the trade breathe for 5 bars before checking
    EXEC_CONFIRM = 2   # 2 consecutive bars of confirmed flip (was 3, lowered after diagnostics showed flips never sustained 3 bars before stop)

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
                    f"Trend Invalidation: 5m flipped {exec_dir.upper()} vs {direction.upper()} trade",
                    is_emergency=True
                )
            else:
                logger.info(
                    f"[TREND-INVAL] {sym}: EXEC flip detected ({exec_dir}) — "
                    f"confirm {_trend_inval_confirm[key]}/{EXEC_CONFIRM}"
                )
        elif exec_dir == direction:
            # Trend reassumed our thesis — reset the confirmation countdown
            _trend_inval_confirm.pop(key, None)

    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: LTF (15m) — Mid-tier invalidation
    # ═══════════════════════════════════════════════════════════════
    # A 15m flip is a stronger structural signal.  Slightly longer grace
    # than exec because the 15m smooths noise, but once it confirms,
    # the trade thesis is clearly broken.
    LTF_GRACE   = 5   # Match EXEC_GRACE — 5 bars before checking (was 8)
    LTF_CONFIRM = 2   # 2 consecutive bars (was 3)

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
                    f"Trend Invalidation: 15m flipped {ltf_dir.upper()} vs {direction.upper()} trade",
                    is_emergency=True
                )
            else:
                logger.info(
                    f"[TREND-INVAL] {sym}: LTF flip detected ({ltf_dir}) — "
                    f"confirm {_trend_inval_confirm[key]}/{LTF_CONFIRM}"
                )
        elif ltf_dir == direction:
            # Trend reassumed our thesis
            _trend_inval_confirm.pop(key, None)

    # ═══════════════════════════════════════════════════════════════
    # LAYER 3: MTF (1H) — Kill shot
    # ═══════════════════════════════════════════════════════════════
    # If the 1H timeframe flips against the trade, the macro thesis
    # is dead.  No grace period — just 2 bars of confirmation to
    # filter a single-bar spike, then hard exit.
    MTF_CONFIRM = 2

    key = f"{sym}_mtf"
    if _is_flipped(direction, mtf_dir):
        _trend_inval_confirm[key] = _trend_inval_confirm.get(key, 0) + 1
        if _trend_inval_confirm[key] >= MTF_CONFIRM:
            _clear_confirm(sym)
            logger.info(
                f"[TREND-INVAL] {sym}: MTF KILL SHOT — 1H flipped {mtf_dir.upper()} "
                f"(held {bars_held} bars)"
            )
            return _hard_exit(
                snapshot, pos,
                f"Trend Invalidation: 1H flipped {mtf_dir.upper()} vs {direction.upper()} trade (kill shot)",
                is_emergency=True
            )
        else:
            logger.info(
                f"[TREND-INVAL] {sym}: MTF flip detected ({mtf_dir}) — "
                f"confirm {_trend_inval_confirm[key]}/{MTF_CONFIRM}"
            )
    elif mtf_dir == direction:
        # Trend reassumed our thesis
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



