
from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_bollinger_bands, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr, detect_structure_invalidation

logger = logging.getLogger(__name__)

class RubberbandReaperStrategy(BaseStrategy):
    """
    Rubberband Reaper: CONFIG 20 (The Staircase Ratchet).
    - Strict Thresholds (Config 13 Quality).
    - Staircase Floor (User Milestones + 2x Cushion).
    - 20% Profit Scaling (The Hammer).
    """
    
    def __init__(self, bb_period=20, bb_std=2.5, rsi_period=7, rsi_overbought=75, rsi_oversold=25):
        logger.debug(f"Loaded RubberbandReaper from {__file__}")
        super().__init__("Rubberband Reaper")
        
        self.bb_period = 20
        self.bb_std = 2.5             # Strict (Quality)
        self.rsi_period = 7
        self.rsi_overbought = 80      # Hardened (was 75)
        self.rsi_oversold = 20        # Hardened (was 25)
        
        logger.debug(f"Reaper Config 20 (Staircase Ratchet) Loaded. BB={self.bb_std}, RSI={self.rsi_oversold}/{self.rsi_overbought}")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        # --- RISK GOVERNANCE ---
        # Use profile-configured risk (no more dynamic staircase/martingale)
        final_risk_pct = self.get_risk_pct()

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period:
            return None
            
        lower, mid, upper = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # [HARDENED] BB Squeeze Guard: If bands are very narrow, skip.
        # Narrow bands = low volatility = breakout imminent, NOT mean-reversion.
        bb_width = (upper - lower) / mid if mid > 0 else 0
        if bb_width < 0.01:  # Less than 1% band width = squeezed
            logger.debug(f"[REAPER] BB Squeeze detected for {snapshot.symbol} (width={bb_width:.4f}). Skipping.")
            return None

        # [HARDENED] HTF Trend Alignment Gate
        # Don't go long against a bearish HTF (catching a falling knife).
        # Don't go short against a bullish HTF (fighting the trend).
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        # Derive bias for gating (will be checked per-signal below)

        # 1. THE HAMMER (Scale-In / Pyramid)
        if open_position:
            if open_position.get("pyramid_count", 1) > 1:
                return None
            pos_dir = open_position.get("direction")
            
            # [HARDENED] Hammer requires RSI re-confirmation.
            # Long hammer needs RSI still below 30 (not just "price above lower band").
            # Short hammer needs RSI still above 70.
            is_long_hammer = pos_dir == "long" and last_close > lower and rsi < 30
            is_short_hammer = pos_dir == "short" and last_close < upper and rsi > 70

            if is_long_hammer or is_short_hammer:
                 target = upper if pos_dir == "long" else lower
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias=pos_dir, phase="continuation", action="scale_in",
                    entry_price=last_close, stop_loss=open_position.get("stop_loss") or open_position.get("stop_price") or (last_close - atr * 2.0 if pos_dir == "long" else last_close + atr * 2.0), take_profit=target,
                    risk_per_trade_pct=final_risk_pct,
                    structure_summary=f"STAIRCASE HAMMER ({final_risk_pct*100:.2f}%)",
                    urgency="high",
                    notes=f"Staircase Floor logic active. Risk={final_risk_pct*100:.2f}%",
                    invalidation_conditions="Price breaks structure.",
                    management_instructions="Aggressive TP."
                )
            return None

        # 2. THE SCOUT (Initial Entry)
        if last_close < lower and rsi < self.rsi_oversold:
            # [HARDENED] HTF Alignment: Don't go long against a bearish HTF
            if htf_dir == "short":
                logger.debug(f"[REAPER] Skipping long entry on {snapshot.symbol} — HTF is bearish.")
                return None
            # [ARMOR] 2x ATR Dynamic Stops
            stop_loss = last_close - (atr * 2.0)
            take_profit = last_close + (atr * 4.0)  # 2:1 R:R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Armor Entry (2x ATR). Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close below stop loss.",
                management_instructions="Net-Zero at 1xATR."
            )

        if last_close > upper and rsi > self.rsi_overbought:
            # [HARDENED] HTF Alignment: Don't go short against a bullish HTF
            if htf_dir == "long":
                logger.debug(f"[REAPER] Skipping short entry on {snapshot.symbol} — HTF is bullish.")
                return None
            # [ARMOR] 2x ATR Dynamic Stops
            stop_loss = last_close + (atr * 2.0)
            take_profit = last_close - (atr * 4.0)  # 2:1 R:R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Armor Entry (2x ATR). Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close above stop loss.",
                management_instructions="Net-Zero at 1xATR."
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Structure-based exit: close if the entry thesis is structurally invalid."""
        if not open_position or not snapshot.candles or len(snapshot.candles) < 20:
            return None

        pos_dir = open_position.get("direction") or open_position.get("side")
        if pos_dir not in {"long", "short"}:
            return None

        # Check for structure invalidation (swing level broken by ATR buffer)
        inval = detect_structure_invalidation(snapshot.candles, pos_dir, atr_mult=0.5)
        if inval:
            logger.warning(
                f"[REAPER] Structure Invalidation for {snapshot.symbol} ({pos_dir}): "
                f"close={inval.last_close:.4f} broke swing={inval.swing_level:.4f} "
                f"(buffer={inval.buffer:.4f})"
            )
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                reason=f"Reaper: Structure Invalidation (swing={inval.swing_level:.4f})",
                emergency_exit=True,
            )

        # [SAFETY] All other exits managed by StrategyEngine via SafetyGuard
        return None
