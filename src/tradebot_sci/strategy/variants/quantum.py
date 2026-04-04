"""Quantum Forex Strategy — Trend-following with HTF alignment and LTF MA pullbacks.

Entry Logic:
    1. HTF and LTF trends must align (both long or both short) via engine consensus
    2. Price must pull back TO or THROUGH the SMA20, then bounce
    3. Bounce candle must show momentum (body > 0.3× ATR)
    4. Entry on the bounce candle close

This is designed for structural stability in high-volume Forex markets.
"""
from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision, hold_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class QuantumStrategy(BaseStrategy):
    """
    Quantum Forex Strategy: Trend-following with HTF alignment and LTF MA pullbacks.
    
    Requires:
    - HTF + LTF trend alignment (both long or both short)
    - Price pulled back to SMA20 zone
    - Bounce confirmation (strong body candle)
    """
    
    def __init__(self, sma_period=20, **kwargs):
        super().__init__("Project Quantum")
        self.sma_period = sma_period

    def check_entry_signal(
        self, snapshot: MarketSnapshot, gates: dict, 
        open_position: Optional[dict] = None, **kwargs
    ) -> Optional[AITradeDecision]:
        candles = snapshot.candles or []
        if len(candles) < self.sma_period + 5:
            return None

        # VOLUME GATE: Skip low volume — no trend in dead sessions
        recent_volumes = [c.volume for c in candles[-20:-1] if c.volume > 0]
        avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1.0
        if candles[-1].volume < avg_volume:
            return None
            
        # 1. Get trend direction from ENGINE consensus (not raw snapshot)
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        
        # Both timeframes must agree on direction
        if htf_dir not in ("long", "short"):
            return None
        if htf_dir != ltf_dir:
            return None

        # [HARDENED] Require strong HTF trend — no weak trend entries
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength < 0.3:
            return None  # Weak trend = don't enter
        
        # 2. Calculate SMA and ATR
        closes = [c.close for c in candles]
        sma = calculate_sma(closes, self.sma_period)
        if sma is None or sma <= 0:
            return None
            
        last_close = closes[-1]
        prev_close = closes[-2]
        prev2_close = closes[-3] if len(closes) >= 3 else prev_close
        atr = calculate_atr(candles, period=14) or (last_close * 0.001)
        
        # 3. Pullback + Bounce detection
        # The previous bar(s) must have been AT or THROUGH the SMA zone
        # Then the current bar bounces away from the SMA
        sma_zone = atr * 0.15  # Tight SMA zone for cleaner pullbacks
        
        action = None
        bias = None
        
        if htf_dir == "long":
            # LONG pullback: prev bar actually crossed below SMA, current bar bounces above
            was_near_sma = prev_close <= sma + sma_zone
            bounced = last_close > sma and last_close > prev_close
            # Momentum: current candle has a bullish body > 0.5 ATR
            body = candles[-1].close - candles[-1].open
            has_momentum = body > atr * 0.6
            
            if was_near_sma and bounced and has_momentum:
                action = "enter_long"
                bias = "long"
                
        elif htf_dir == "short":
            # SHORT pullback: prev bar actually crossed above SMA, current bar drops below
            was_near_sma = prev_close >= sma - sma_zone
            bounced = last_close < sma and last_close < prev_close
            # Momentum: current candle has a bearish body > 0.5 ATR
            body = candles[-1].open - candles[-1].close
            has_momentum = body > atr * 0.6
            
            if was_near_sma and bounced and has_momentum:
                action = "enter_short"
                bias = "short"
        
        if not action:
            return None
        
        logger.info(
            f"[QUANTUM] ENTRY: {snapshot.symbol} {action} "
            f"HTF={htf_dir} LTF={ltf_dir} SMA={sma:.5f} close={last_close:.5f} "
            f"ATR={atr:.5f}"
        )
        
        # 4. Stop/Target (2:1 R:R) — 2.0× ATR gives forex breathing room
        # (Swing stops tested in Round 12 but made it worse — too tight)
        stop_mult = 2.0
        stop_dist = max(atr * stop_mult, last_close * 0.0015)  # Min 15 pips
        
        if action == "enter_long":
            stop_loss = last_close - stop_dist
            take_profit = last_close + (stop_dist * 2.0)  # 2R
        else:
            stop_loss = last_close + stop_dist
            take_profit = last_close - (stop_dist * 2.0)  # 2R

        return AITradeDecision(
            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            bias=bias, phase="trend", action=action,
            entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=f"Quantum {action}: HTF/LTF Aligned + SMA{self.sma_period} Pullback Bounce",
            invalidation_conditions="HTF trend reversal",
            management_instructions="Target 2R. 2x ATR stop.",
            notes=f"Quantum Trend Entry (2x ATR stop)",
            urgency="medium"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """
        Chandelier Exit (proven for SMA pullback strategies): trail from
        highest high / lowest low minus ATR×2. Wider than fixed ATR trail
        to let trend moves run.
        """
        if not snapshot.candles or not open_position:
            return None

        entry_price = float(open_position.get("entry_price", 0))
        stop_price = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0))
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction", "long")

        if entry_price <= 0 or stop_price <= 0:
            return None

        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0:
            return None

        atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)

        if direction == "long":
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        r_multiple = profit / initial_risk

        if r_multiple < 1.0:
            return None

        # Chandelier Exit: trail from highest high / lowest low (last 10 bars)
        lookback = min(10, len(snapshot.candles))
        recent = snapshot.candles[-lookback:]
        chandelier_mult = 2.0

        if direction == "long":
            highest_high = max(c.high for c in recent)
            new_stop = highest_high - (atr * chandelier_mult)
            if new_stop > stop_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Quantum Chandelier: {new_stop:.5f} (HH={highest_high:.5f}, {r_multiple:.1f}R)",
                    stop_loss=new_stop,
                )
        else:
            lowest_low = min(c.low for c in recent)
            new_stop = lowest_low + (atr * chandelier_mult)
            if new_stop < stop_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Quantum Chandelier: {new_stop:.5f} (LL={lowest_low:.5f}, {r_multiple:.1f}R)",
                    stop_loss=new_stop,
                )

        return None
