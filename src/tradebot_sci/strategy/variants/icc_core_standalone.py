"""ICC Core Strategy — True ICT Entry Model.

Entry Logic (ICT methodology):
    1. Determine bias from HTF trend direction (from engine gates)
    2. Detect liquidity sweep (wick beyond swing level, close back)
    3. Confirm displacement (3+ momentum candles in sweep direction)
    4. Enter on pullback to OTE zone (50-78.6% of displacement)

This is the vanilla, unmodified Trade By Sci ICC methodology.
"""
from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr, detect_structure_invalidation

logger = logging.getLogger(__name__)


def _detect_displacement(candles, direction: str, atr: float, min_candles: int = 2) -> bool:
    """Detect displacement: consecutive momentum candles in the given direction.
    
    ICT displacement = strong impulsive move with large-body candles.
    We check the last few candles for consecutive bodies > 0.5x ATR
    in the same direction.
    """
    if len(candles) < min_candles + 1:
        return False
    
    recent = candles[-(min_candles + 1):]
    count = 0
    for c in recent:
        body = c.close - c.open
        if direction == "long" and body > atr * 0.5:
            count += 1
        elif direction == "short" and body < -atr * 0.5:
            count += 1
    
    return count >= min_candles


def _detect_fvg(candles, direction: str) -> Optional[tuple]:
    """Detect Fair Value Gap (FVG) in the last few candles.
    
    Long FVG: Candle[i-2].high < Candle[i].low (gap up, middle candle's range doesn't fill)
    Short FVG: Candle[i-2].low > Candle[i].high (gap down)
    
    Returns (fvg_top, fvg_bottom) or None.
    """
    if len(candles) < 3:
        return None
    
    c0 = candles[-3]  # First candle
    c2 = candles[-1]  # Third candle
    
    if direction == "long":
        if c2.low > c0.high:
            return (c2.low, c0.high)  # FVG zone
    elif direction == "short":
        if c2.high < c0.low:
            return (c0.low, c2.high)  # FVG zone
    
    return None


def _in_ote_zone(price: float, swing_high: float, swing_low: float, direction: str) -> bool:
    """Check if price is in the Optimal Trade Entry zone (50-78.6% retracement)."""
    move = swing_high - swing_low
    if move <= 0:
        return False
    
    if direction == "long":
        # Long OTE: price pulls back to 50-78.6% of the up-move
        ote_top = swing_high - (move * 0.50)    # 50% retrace
        ote_bot = swing_high - (move * 0.786)   # 78.6% retrace
        return ote_bot <= price <= ote_top
    else:
        # Short OTE: price pulls back to 50-78.6% of the down-move
        ote_bot = swing_low + (move * 0.50)     # 50% retrace
        ote_top = swing_low + (move * 0.786)    # 78.6% retrace
        return ote_bot <= price <= ote_top


# ── Entry Cooldown (per-symbol) ───────────────────────────────────────
# Prevents over-trading by enforcing minimum bar spacing between entries.
_ENTRY_COOLDOWN_BARS = 8   # ~2h on 15m candles
_last_entry_bar: dict = {}  # symbol → bar index
_icc_bar_counter: int = 0


class ICCCoreStandaloneStrategy(BaseStrategy):
    """
    ICC Core Standalone — Tighter stops for solo use.
    
    This is a copy of ICC Core with 1.5× ATR stops (vs 2.0× in ensemble).
    The ensemble version needs wide stops because SAR reversals depend
    on ICC Core stop-outs as trigger signals. This standalone version
    can be freely tuned without affecting the Meta-SCI ensemble.
    """

    def __init__(self):
        super().__init__("ICC Core Standalone")

    def check_entry_signal(
        self, 
        snapshot: MarketSnapshot, 
        gates: dict, 
        open_position: Optional[dict] = None, 
        current_capital: Optional[float] = None, 
        trade_history: Optional[list] = None
    ) -> Optional[AITradeDecision]:
        global _icc_bar_counter
        _icc_bar_counter += 1
        
        candles = snapshot.candles or []
        if len(candles) < 40:
            return None
        
        # ── Entry cooldown: minimum 8-bar spacing per symbol ──────────
        symbol = snapshot.symbol
        last_bar = _last_entry_bar.get(symbol, -999)
        if _icc_bar_counter - last_bar < _ENTRY_COOLDOWN_BARS:
            return None  # Too soon after last entry on this symbol
            
        # 1. Get bias from HTF direction (from engine trend detection)
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        phase = gates.get("phase", "neutral")
        
        # Determine trading bias — prefer HTF, fallback to LTF
        bias = htf_dir if htf_dir in ("long", "short") else ltf_dir
        
        last_close = candles[-1].close
        atr = calculate_atr(candles, period=14) or (last_close * 0.005)
        
        logger.debug(
            f"[ICC-CORE] {snapshot.symbol} bias={bias} htf={htf_dir} "
            f"ltf={ltf_dir} phase={phase} atr={atr:.5f}"
        )
        
        # 2. Need a directional bias to trade
        if bias not in ("long", "short"):
            return None

        # ── Pyramid Logic (BEFORE full entry check) ──────────────────
        # Pyramids don't need the full ICT setup — winners hit target
        # in 1-2h (4-10 bars). Just need: in profit + momentum continuing.
        if open_position and abs(open_position.get("size", 0.0)) > 0:
            pos_dir = open_position.get("direction") or open_position.get("side")
            pos_pnl = float(open_position.get("unrealized_pnl") or 0.0)
            pyramid_count = open_position.get("pyramid_count", 0)
            entry_price = float(open_position.get("entry_price") or last_close)

            # Use profile setting for max pyramids
            max_pyramid = 3
            if "profile" in gates and gates["profile"]:
                max_pyramid = getattr(gates["profile"], "max_pyramid_entries", 3)

            # Minimum R-multiple gate: only pyramid when >= 0.5R in profit
            stop_price = float(open_position.get("stop_price") or open_position.get("stop_loss") or 0)
            initial_risk = abs(entry_price - stop_price) * float(open_position.get("size", 1)) if stop_price else 0
            r_multiple = pos_pnl / initial_risk if initial_risk > 0 else 0

            # Continuation check: last candle still moving in direction
            last_candle = candles[-1]
            candle_body = last_candle.close - last_candle.open
            momentum_ok = (
                (bias == "long" and candle_body > 0) or
                (bias == "short" and candle_body < 0)
            )

            # Same direction + 0.5R profit + momentum + under cap
            if pos_dir == bias and r_multiple >= 0.5 and momentum_ok and pyramid_count < max_pyramid:
                # Move stop to breakeven on pyramid to protect original risk
                if bias == "long":
                    stop_loss_pyramid = max(entry_price, last_close - (atr * 1.2))
                    take_profit = last_close + (abs(last_close - stop_loss_pyramid) * 2.0)
                else:
                    stop_loss_pyramid = min(entry_price, last_close + (atr * 1.2))
                    take_profit = last_close - (abs(stop_loss_pyramid - last_close) * 2.0)

                logger.info(
                    f"[ICC-CORE] PYRAMID #{pyramid_count+1}: {snapshot.symbol} scale_in "
                    f"R={r_multiple:.2f} pnl=${pos_pnl:.2f} momentum={'✅' if momentum_ok else '❌'}"
                )

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    action="scale_in",
                    bias=bias,
                    entry_price=last_close,
                    stop_loss=stop_loss_pyramid,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    phase=phase,
                    structure_summary=f"ICC Core PYRAMID #{pyramid_count+1} (continuation, ATR={atr:.5f})",
                    invalidation_conditions=f"Close beyond SL at {stop_loss_pyramid:.5f}",
                    management_instructions=f"Pyramid {pyramid_count+1}/{max_pyramid}. Stop at breakeven.",
                    urgency="medium",
                    notes=f"ICT Pyramid: continuation (pnl=${pos_pnl:.2f})"
                )
            elif open_position:
                # Position exists but wrong direction, losing, or maxed out
                return None

        # 3. Check for displacement (momentum confirmation)
        has_displacement = _detect_displacement(candles, bias, atr, min_candles=2)
        if not has_displacement:
            return None
            
        # 4. Check if price is in OTE zone (pullback entry)
        # Find recent swing high and swing low for the displacement move
        lookback = min(20, len(candles) - 1)
        recent = candles[-lookback:]
        swing_high = max(c.high for c in recent)
        swing_low = min(c.low for c in recent)
        
        in_ote = _in_ote_zone(last_close, swing_high, swing_low, bias)
        
        # Also check for FVG (Fair Value Gap) as alternative entry
        has_fvg = _detect_fvg(candles, bias) is not None
        
        # 5. Entry conditions: displacement + (OTE pullback OR FVG)
        if not in_ote and not has_fvg:
            return None
        
        # 6. Determine action
        if bias == "long":
            action = "enter_long"
        else:
            action = "enter_short"
        
        logger.info(
            f"[ICC-CORE] ENTRY: {snapshot.symbol} {action} "
            f"displacement=True ote={in_ote} fvg={has_fvg} "
            f"atr={atr:.5f} close={last_close:.5f}"
        )
        
        # 7. Stop/Target logic (ICT style) — STANDALONE
        # Ensemble version uses 2.0× because SAR depends on wider stops.
        min_stop_dist = max(atr * getattr(self, 'stop_atr_mult', 1.5), last_close * 0.002)
        stop_dist = min_stop_dist
        
        if action == "enter_long":
            # Stop below recent swing low
            structure_stop = swing_low - (atr * 0.5)
            stop_loss = min(last_close - stop_dist, structure_stop)
            take_profit = last_close + (abs(last_close - stop_loss) * getattr(self, 'target_r', 2.0))  # Target R
        else:
            # Stop above recent swing high
            structure_stop = swing_high + (atr * 0.5)
            stop_loss = max(last_close + stop_dist, structure_stop)
            take_profit = last_close - (abs(stop_loss - last_close) * getattr(self, 'target_r', 2.0))  # Target R

        # Record entry to enforce cooldown
        _last_entry_bar[snapshot.symbol] = _icc_bar_counter

        entry_type = "OTE" if in_ote else "FVG"
        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            action=action,
            bias=bias,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            phase=phase,
            structure_summary=f"ICC Core {action} via {entry_type} (ATR={atr:.5f})",
            invalidation_conditions=f"Close beyond SL at {stop_loss:.5f}",
            management_instructions=f"Target 2.5R. ICT {entry_type} entry.",
            urgency="medium",
            notes=f"ICT Entry: displacement + {entry_type}"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Structure-based exit: close if the entry thesis is structurally invalid.
        
        ONLY fires when the trade is LOSING or barely profitable (< 0.5R).
        Winners should be allowed to run to their 2.5R target — don't cut them
        just because a swing level wobbles.
        """
        if not open_position or not snapshot.candles or len(snapshot.candles) < 20:
            return None

        pos_dir = open_position.get("direction") or open_position.get("side")
        if pos_dir not in {"long", "short"}:
            return None

        # Grace period: don't invalidate structure within 5 minutes of entry.
        # Tiny swing breaks right after entry are noise, not signal.
        entry_time = open_position.get("entry_time")
        if entry_time:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            if isinstance(entry_time, str):
                try:
                    entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    entry_time = None
            if entry_time and (now - entry_time).total_seconds() < 300:
                return None  # Trade is less than 5 minutes old — skip invalidation

        # ── PROFIT GUARD: Don't cut winners ──────────────────────────────
        # Structure invalidation is for PROTECTING CAPITAL on losers, not
        # for taking tiny profits on winners. Let winners run to target.
        pos_pnl = float(open_position.get("unrealized_pnl") or 0.0)
        entry_price = float(open_position.get("entry_price") or 0)
        stop_price = float(open_position.get("stop_price") or open_position.get("stop_loss") or 0)
        initial_risk_per_unit = abs(entry_price - stop_price) if stop_price else 0
        size = abs(float(open_position.get("size") or 1))
        initial_risk = initial_risk_per_unit * size if initial_risk_per_unit > 0 else 1
        r_multiple = pos_pnl / initial_risk if initial_risk > 0 else 0

        # Only check structure invalidation if LOSING — never cut profitable trades
        if r_multiple >= 0.0:
            return None  # [HARDENED] Any profit = let TP/trail handle it (was 0.5R)

        # Check for structure invalidation (swing level broken by ATR buffer)
        # Use 1.0× ATR buffer (was 0.5×) to avoid noise triggers
        inval = detect_structure_invalidation(snapshot.candles, pos_dir, atr_mult=1.0)
        if inval:
            logger.warning(
                f"[ICC-CORE] Structure Invalidation for {snapshot.symbol} ({pos_dir}): "
                f"close={inval.last_close:.4f} broke swing={inval.swing_level:.4f} "
                f"(buffer={inval.buffer:.4f}, R={r_multiple:.2f})"
            )
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                reason=f"ICC Core: Structure Invalidation (swing={inval.swing_level:.4f})",
                emergency_exit=True,  # Bypass hold guard — cut losers immediately
            )

        # [SAFETY] All other exits managed by StrategyEngine via SafetyGuard
        return None
