from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import detect_no_trade_zone, detect_indication, calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class RobotEvolutionStrategy(BaseStrategy):
    """
    Optimized scalp strategy focusing on 2.0R targets and safe 1.5 ATR stops.
    Designed for account growth in ranging or choppy markets.
    """
    
    def __init__(self, **kwargs):
        super().__init__("Robot Evolution")
        self.stop_atr_mult = float(kwargs.get('stop_atr_mult', 1.0))
        self.target_r = float(kwargs.get('target_r', 2.0))
        self.chandelier_mult = float(kwargs.get('chandelier_mult', 2.0))

    def score_signal(self, snapshot, gates=None):
        """Evolution-specific scoring: NTZ(30) + Sweep(25) + Indication(25) + Candle(10) + ATR(10)."""
        if not snapshot.candles or len(snapshot.candles) < 20:
            return 0.0, "-", "Evolution: Insufficient data"

        htf_candles = snapshot.htf_candles or snapshot.candles
        ltf_candles = snapshot.ltf_candles or snapshot.candles

        score = 0.0
        breakdown = []

        # 1. NTZ Detection (30 pts)
        ntz = detect_no_trade_zone(htf_candles, swing_lookback=2)
        if ntz and not ntz.is_broken:
            score += 30.0
            breakdown.append("NTZ(+30)")

            ntz_range = ntz.high - ntz.low
            if ntz_range > 0:
                current_price = snapshot.candles[-1].close

                # 2. NTZ Sweep Proximity (25 pts)
                lowest_recent = min(c.low for c in snapshot.candles[-5:])
                highest_recent = max(c.high for c in snapshot.candles[-5:])

                if lowest_recent < ntz.low and current_price > ntz.low:
                    score += 25.0
                    breakdown.append("Sweep-Low(+25)")
                elif highest_recent > ntz.high and current_price < ntz.high:
                    score += 25.0
                    breakdown.append("Sweep-High(+25)")
                else:
                    # Partial credit: how close is price to an NTZ boundary?
                    dist_low = abs(current_price - ntz.low) / ntz_range
                    dist_high = abs(current_price - ntz.high) / ntz_range
                    closest = min(dist_low, dist_high)
                    pts = max(0, 25 * (1 - closest))
                    if pts > 5:
                        score += pts
                        breakdown.append(f"NTZ-Near(+{pts:.0f})")

        # 3. Directional Indication (25 pts)
        indication = detect_indication(ltf_candles, swing_lookback=1)
        if indication:
            score += 25.0
            breakdown.append(f"BOS-{indication.direction}(+25)")

        # 4. Candle Confirmation (10 pts)
        if snapshot.candles:
            last_bar = snapshot.candles[-1]
            if last_bar.close > last_bar.open:
                if indication and indication.direction == "long":
                    score += 10.0
                    breakdown.append("Bull-Candle(+10)")
            elif last_bar.close < last_bar.open:
                if indication and indication.direction == "short":
                    score += 10.0
                    breakdown.append("Bear-Candle(+10)")

        # 5. ATR Quality (10 pts)
        atr = calculate_atr(snapshot.candles, period=14)
        if atr and snapshot.candles:
            atr_pct = atr / snapshot.candles[-1].close
            if atr_pct >= 0.003:
                score += 10.0
                breakdown.append(f"ATR({atr_pct:.3f}=+10)")
            elif atr_pct >= 0.001:
                pts = 10 * (atr_pct / 0.003)
                score += pts
                breakdown.append(f"ATR({atr_pct:.3f}=+{pts:.0f})")

        # 6. Volume Confidence — delegates to BaseStrategy.score_volume() (up to 15 pts).
        vol_pts, vol_label = self.score_volume(snapshot.candles)
        score += vol_pts
        breakdown.append(vol_label)

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"Evolution {score:.0f}/100: {', '.join(breakdown)}" if breakdown else f"Evolution {score:.0f}/100"
        return score, grade, summary

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 20:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Insufficient candle history (<20)")

        # VOLUME GATE: delegates to BaseStrategy.check_volume_gate() — hard-rejects < 40% avg only.
        volume_gate = self.check_volume_gate(snapshot.candles, snapshot.symbol, snapshot.timeframe)
        if volume_gate is not None:
            return volume_gate
            
        htf_candles = snapshot.htf_candles or snapshot.candles
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        
        ntz = detect_no_trade_zone(htf_candles, swing_lookback=2)
        if not ntz or ntz.is_broken:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "No valid No-Trade-Zone (NTZ) detected or NTZ broken")
            
        current_price = snapshot.candles[-1].close
        last_bar = snapshot.candles[-1]
        ntz_range = ntz.high - ntz.low
        if ntz_range <= 0:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Invalid NTZ range (<=0)")

        indication = detect_indication(ltf_candles, swing_lookback=1)
        if not indication:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "No Directional Indication detected")
            
        atr = calculate_atr(snapshot.candles, period=14) or (ntz_range * 0.1)
        
        # ATR floor: minimum 0.2% of price to avoid degenerate micro-range stops
        atr_floor = current_price * 0.002
        effective_atr = max(atr, atr_floor)
        stop_dist = effective_atr * self.stop_atr_mult
        
        # [SPREAD-TO-ATR GUARD]
        # Reject entry when estimated spread consumes > 25% of the stop distance.
        # This is the structural fix for trades going immediately negative on entry.
        # Note: MAE-based stop widening was intentionally removed — it used a
        # corrupted (mostly-loss) baseline and caused stops to widen into bigger losses.
        estimated_spread_price = current_price * 0.0002
        if estimated_spread_price > (stop_dist * 0.25):
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Evolution: Spread/Volatility Guard — spread ({estimated_spread_price:.5f}) > 25% of stop ({stop_dist:.5f})"
            )
        
        
        rejection_reasons = []

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_strength = float(gates.get("htf_strength", 0))
        
        # Handle three cases: strong trend (follow direction), weak trend (stand aside), neutral (mean reversion)
        if htf_strength < 0.2:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Evolution: weak HTF trend")
        
        # When HTF is neutral but strong enough, allow mean-reversion trades within NTZ
        is_neutral_regime = (htf_dir == "neutral" and htf_strength >= 0.2)

        # Long: Sweep of NTZ Low + Bullish Indication (only when trend is long)
        lowest_recent = min(c.low for c in snapshot.candles[-5:])
        
        # Calculate candle anatomy for Momentum Confirmation
        body_size = abs(last_bar.close - last_bar.open)
        lower_wick = min(last_bar.open, last_bar.close) - last_bar.low
        upper_wick = last_bar.high - max(last_bar.open, last_bar.close)
        
        # In neutral regime, allow mean-reversion longs at NTZ low without strict HTF direction match
        if is_neutral_regime:
            # Mean reversion: buy at NTZ low with bullish indication
            if indication.direction == "long" and current_price <= ntz.low * 1.001:  # Within 0.1% of NTZ low
                if last_bar.close > last_bar.open and lower_wick >= body_size * 1.0:
                    stop_loss = lowest_recent - stop_dist
                    target = current_price + (stop_dist * self.target_r)
                    
                    notes = f"Robot Evolution Long (Neutral): {self.stop_atr_mult}ATR Stop / {self.target_r}R Target (ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="long", phase="chop", action="enter_long",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="medium", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close below sweep low.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
        
        if htf_dir == "long" and indication.direction == "long":
            if lowest_recent < ntz.low and current_price > ntz.low:
                if last_bar.close > last_bar.open and lower_wick >= body_size * 1.0:
                    stop_loss = lowest_recent - stop_dist
                    target = current_price + (stop_dist * self.target_r)
                    
                    notes = f"Robot Evolution Long: {self.stop_atr_mult}ATR Stop / {self.target_r}R Target (ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="long", phase="chop", action="enter_long",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="high", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close below sweep low.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
                else:
                    rejection_reasons.append("Long setup found but last candle lacks bullish wick rejection")
            else:
                rejection_reasons.append(f"Price not sweeping NTZ Low ({ntz.low:.2f}) correctly")

        # Short: Sweep of NTZ High + Bearish Indication (only when trend is short)
        highest_recent = max(c.high for c in snapshot.candles[-5:])
        
        # In neutral regime, allow mean-reversion shorts at NTZ high without strict HTF direction match
        if is_neutral_regime:
            # Mean reversion: sell at NTZ high with bearish indication
            if indication.direction == "short" and current_price >= ntz.high * 0.999:  # Within 0.1% of NTZ high
                if last_bar.close < last_bar.open and upper_wick >= body_size * 1.0:
                    stop_loss = highest_recent + stop_dist
                    target = current_price - (stop_dist * self.target_r)
                    
                    notes = f"Robot Evolution Short (Neutral): {self.stop_atr_mult}ATR Stop / {self.target_r}R Target (ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="short", phase="chop", action="enter_short",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="medium", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close above sweep high.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
        
        if htf_dir == "short" and indication.direction == "short":
            if highest_recent > ntz.high and current_price < ntz.high:
                if last_bar.close < last_bar.open and upper_wick >= body_size * 1.0:
                    stop_loss = highest_recent + stop_dist
                    target = current_price - (stop_dist * self.target_r)
                    
                    notes = f"Robot Evolution Short: {self.stop_atr_mult}ATR Stop / {self.target_r}R Target (ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="short", phase="chop", action="enter_short",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="high", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close above sweep high.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
                else:
                    rejection_reasons.append("Short setup found but last candle lacks bearish wick rejection")
            else:
                 rejection_reasons.append(f"Price not sweeping NTZ High ({ntz.high:.2f}) correctly")
        
        final_reason = f"Monitoring NTZ ({ntz.low:.2f}-{ntz.high:.2f}). " + "; ".join(rejection_reasons)
        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, final_reason)

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """
        Chandelier Exit (Charles Le Beau): trail from highest high / lowest low
        minus ATR×2. Proven for breakout strategies — gives room for pullbacks
        while protecting profits.
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

        # Calculate current R-multiple
        if direction == "long":
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        r_multiple = profit / initial_risk

        if r_multiple < 1.0:
            return None  # Not yet profitable enough to trail

        # Chandelier Exit: trail from highest high / lowest low (last 10 bars)
        lookback = min(10, len(snapshot.candles))
        recent = snapshot.candles[-lookback:]
        chandelier_mult = self.chandelier_mult

        from tradebot_sci.strategy.decisions import hold_decision

        if direction == "long":
            highest_high = max(c.high for c in recent)
            new_stop = highest_high - (atr * chandelier_mult)
            # Only move stop UP, never down
            if new_stop > stop_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Evolution Chandelier: {new_stop:.5f} (HH={highest_high:.5f}, {r_multiple:.1f}R)",
                    stop_loss=new_stop,
                )
        else:
            lowest_low = min(c.low for c in recent)
            new_stop = lowest_low + (atr * chandelier_mult)
            # Only move stop DOWN, never up
            if new_stop < stop_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Evolution Chandelier: {new_stop:.5f} (LL={lowest_low:.5f}, {r_multiple:.1f}R)",
                    stop_loss=new_stop,
                )

        return None

