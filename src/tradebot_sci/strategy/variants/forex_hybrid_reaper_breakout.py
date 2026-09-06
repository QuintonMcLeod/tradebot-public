from __future__ import annotations
import logging
from typing import Optional


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.market.indicators import calculate_bollinger_bands
logger = logging.getLogger(__name__)

class ForexHybridReaperStrategy(BaseStrategy):
    score_threshold = 72.0
    SESSION_PROFILE = ["forex_hybrid_scalper:hybrid_overlap", "forex_hybrid_scalper:london_open", "forex_hybrid_scalper:asian_open", "forex_hybrid_reaper_breakout:london_open", "forex_hybrid_reaper_breakout:us_open"]
    """
    Forex Hybrid Reaper — regime-router.

    Strong HTF trend  -> trend-following pullback (ride the wave).
    Choppy / neutral  -> mean-reversion scalp.
    """
    def __init__(self, target_r=1.0, **kwargs):
        super().__init__("ForexHybridReaper")
        self.target_r = target_r
        self._call_count = 0

        # Bollinger / RSI parameters
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 1.5))
        self.rsi_period = int(kwargs.get('rsi_period', 7))
        self.rsi_overbought = float(kwargs.get('rsi_overbought', 60))
        self.rsi_oversold = float(kwargs.get('rsi_oversold', 40))

        # Trend filter
        self.trend_ema_period = int(kwargs.get('trend_ema', 200))

        # Regime switch: strong HTF trend vs neutral/chop
        self.trend_adx_min = float(kwargs.get('trend_adx_min', 20.0))

        # Trend-mode parameters (ride the wave)
        self.trend_stop_atr_mult = float(kwargs.get('trend_stop_atr_mult', 2.5))
        self.trend_stop_floor = float(kwargs.get('trend_stop_floor', 0.0020))
        self.trend_target_r = float(kwargs.get('trend_target_r', 4.0))
        self.trend_rsi_long_min = float(kwargs.get('trend_rsi_long_min', 30.0))
        self.trend_rsi_long_max = float(kwargs.get('trend_rsi_long_max', 45.0))
        self.trend_rsi_short_min = float(kwargs.get('trend_rsi_short_min', 55.0))
        self.trend_rsi_short_max = float(kwargs.get('trend_rsi_short_max', 70.0))

        # Breakout mode parameters (optional)
        self.breakout_distance_pct = float(kwargs.get('breakout_distance_pct', 0.05))  # 0.5% default

        # Range-mode parameters (scalp)
        self.range_stop_atr_mult = float(kwargs.get('range_stop_atr_mult', 1.5))
        self.range_stop_floor = float(kwargs.get('range_stop_floor', 0.0008))
        self.range_target_r = float(kwargs.get('range_target_r', 1.0))

        # Shared filters
        self.price_hook_required = bool(kwargs.get('price_hook_required', True))
        self.rsi_hook_required = bool(kwargs.get('rsi_hook_required', True))

        logger.debug(
            f"Loaded ForexHybridReaper router trendADX>={self.trend_adx_min}"
        )

    def _price_hook(self, closes: list[float]) -> tuple[bool, bool]:
        if len(closes) < 2:
            return False, False
        return closes[-1] > closes[-2], closes[-1] < closes[-2]

    def _rsi_hook(self, closes: list[float]) -> tuple[bool, bool]:
        if len(closes) < 2:
            return False, False
        cur = calculate_rsi(closes, self.rsi_period)
        prev = calculate_rsi(closes[:-1], self.rsi_period)
        if cur is None or prev is None:
            return False, False
        return cur > prev, cur < prev

    def _three_bar_pullback(self, closes: list[float], is_long: bool) -> bool:
        """True if the last 3 completed bars moved against the intended direction."""
        if len(closes) < 4:
            return False
        deltas = [closes[-i] - closes[-i-1] for i in range(2, 4)]
        if is_long:
            return all(d < 0 for d in deltas)
        return all(d > 0 for d in deltas)

    def _three_bar_exhaustion(self, closes: list[float], is_long: bool) -> bool:
        """True if the 3 bars before current are all against the setup (exhaustion).

        Range-mode entries need this exhaustion before the current bar hooks back.
        """
        if len(closes) < 5:
            return False
        deltas = [closes[-i-1] - closes[-i-2] for i in range(1, 4)]
        if is_long:
            return all(d < 0 for d in deltas)
        return all(d > 0 for d in deltas)

    def _strong_momentum(self, candle) -> bool:
        """True when the current candle body is more than 50% of its full range."""
        range_ = candle.high - candle.low
        if range_ <= 0:
            return False
        body = abs(candle.close - candle.open)
        return body > range_ * 0.5

    def _structure_break(self, candles: list, is_long: bool) -> bool:
        """True when the current close breaks beyond the prior 3-bar structure.

        For longs: close > highest high of the previous 3 completed bars.
        For shorts: close < lowest low of the previous 3 completed bars.
        """
        if len(candles) < 4:
            return False
        prior_bars = candles[-4:-1]
        current_close = candles[-1].close
        if is_long:
            return current_close > max(c.high for c in prior_bars)
        return current_close < min(c.low for c in prior_bars)

    def score_signal(self, snapshot: MarketSnapshot, gates: dict, regime: str | None = None) -> tuple[float, str, str]:
        gates = gates or {}
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.trend_ema_period:
            return 0.0, "-", "HybridReaper: Insufficient data"

        last_close = closes[-1]
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        is_long_bias = last_close > trend_ema
        strat_bias = "long" if is_long_bias else "short"

        exec_bollinger = gates.get("exec_bollinger", {})
        lower_bb = exec_bollinger.get("lower", float('-inf'))
        mid_bb = exec_bollinger.get("middle", last_close)
        upper_bb = exec_bollinger.get("upper", float('inf'))
        rsi = gates.get("exec_rsi", 50.0)

        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()

        if regime is None:
            htf_adx = gates.get("htf_adx", 0) or 0
            ltf_adx = gates.get("ltf_adx", 0) or 0
            adx = max(htf_adx, ltf_adx)
            regime = "trend" if (htf_dir in ("long", "short") and adx >= self.trend_adx_min) else "range"

        score = 0.0
        breakdown = []

        # 1. HTF/LTF alignment (40 pts)
        if htf_dir == strat_bias:
            score += 20.0
            breakdown.append("HTF-Align(+20)")
        if ltf_dir == strat_bias:
            score += 20.0
            breakdown.append("LTF-Align(+20)")

        if regime == "trend":
            # 2. Pullback to value zone (30 pts)
            if is_long_bias:
                if lower_bb <= last_close <= mid_bb:
                    score += 30.0
                    breakdown.append("BB-Pullback(+30)")
            else:
                if mid_bb <= last_close <= upper_bb:
                    score += 30.0
                    breakdown.append("BB-Pullback(+30)")

            # 3. RSI in healthy pullback zone (30 pts)
            if is_long_bias:
                if self.trend_rsi_long_min <= rsi <= self.trend_rsi_long_max:
                    score += 30.0
                    breakdown.append(f"RSI-Pullback({rsi:.1f}=+30)")
            else:
                if self.trend_rsi_short_min <= rsi <= self.trend_rsi_short_max:
                    score += 30.0
                    breakdown.append(f"RSI-Pullback({rsi:.1f}=+30)")
        else:
            # Range mode: close-pierce / bounce off outer band (30 pts)
            prev_close = closes[-2] if len(closes) >= 2 else last_close
            recent = snapshot.candles[-3:] if len(snapshot.candles) >= 3 else snapshot.candles
            if is_long_bias:
                if (prev_close <= lower_bb or any(c.low <= lower_bb for c in recent)) and last_close > lower_bb:
                    score += 30.0
                    breakdown.append("BB-Bounce(+30)")
            else:
                if (prev_close >= upper_bb or any(c.high >= upper_bb for c in recent)) and last_close < upper_bb:
                    score += 30.0
                    breakdown.append("BB-Bounce(+30)")

            # Range mode: RSI extreme (30 pts)
            overbought = float(getattr(self._profile, 'rsi_overbought', self.rsi_overbought)) if getattr(self, '_profile', None) else self.rsi_overbought
            oversold = float(getattr(self._profile, 'rsi_oversold', self.rsi_oversold)) if getattr(self, '_profile', None) else self.rsi_oversold
            if is_long_bias and rsi <= oversold:
                score += 30.0
                breakdown.append(f"RSI-OS({rsi:.1f}=+30)")
            if not is_long_bias and rsi >= overbought:
                score += 30.0
                breakdown.append(f"RSI-OB({rsi:.1f}=+30)")

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"HybridReaper[{regime}] {score:.0f}/100: {', '.join(breakdown)}"
        return score, grade, summary

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'CALLED {snapshot.symbol}\n')

        candles = snapshot.candles
        if not candles:
            return None
        
        last_close = candles[-1].close
        current_atr = calculate_atr(candles, period=14)
        
        # ── Breakout Mode (only active when breakout_distance_pct > 0) ──
        with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'CHECKING {snapshot.symbol} pct={self.breakout_distance_pct} atr={current_atr:.5f} candles={len(candles)}\n')
        if self.breakout_distance_pct > 0 and current_atr > 0 and len(candles) >= 5:
            with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'REACHED {snapshot.symbol}\n')
            recent_high = max(c.high for c in candles[-6:-1])
            recent_low = min(c.low for c in candles[-6:-1])
            breakout_dist = last_close * self.breakout_distance_pct / 100
            with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'CANDLES {snapshot.symbol} last6=' + ','.join([f"({c.high:.5f},{c.low:.5f},{c.close:.5f})" for c in candles[-6:]]) + '\n')
            
            with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'LONG-CHECK {snapshot.symbol} close={last_close:.5f} high={recent_high:.5f} dist={breakout_dist:.5f} needed={recent_high + breakout_dist:.5f}\n')
            with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'LONG-CHECK {snapshot.symbol} close={last_close:.5f} high={recent_high:.5f} dist={breakout_dist:.5f} needed={recent_high + breakout_dist:.5f}\n')
            if last_close > recent_high + breakout_dist:
                stop_loss = recent_low - current_atr * 0.5
                stop_loss = min(stop_loss, last_close - current_atr * 2)
                target = last_close + (last_close - stop_loss) * self.trend_target_r
                return AITradeDecision(score=100, grade="A",
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="continuation", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Breakout Long (Score=N/A, Break={self.breakout_distance_pct:.2f}%)",
                    invalidation_conditions="Close below stop loss.",
                    management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                    urgency="high", strategy_name=self.name, regime="breakout"
                )
            
            with open('/tmp/strategy_debug.txt', 'a') as _f: _f.write(f'SHORT-CHECK {snapshot.symbol} close={last_close:.5f} low={recent_low:.5f} dist={breakout_dist:.5f} needed={recent_low - breakout_dist:.5f}\n')
            if last_close < recent_low - breakout_dist:
                stop_loss = recent_high + current_atr * 0.5
                stop_loss = max(stop_loss, last_close + current_atr * 2)
                target = last_close - (stop_loss - last_close) * self.trend_target_r
                return AITradeDecision(score=100, grade="A",
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="continuation", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Breakout Short (Score=N/A, Break={self.breakout_distance_pct:.2f}%)",
                    invalidation_conditions="Close above stop loss.",
                    management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                    urgency="high", strategy_name=self.name, regime="breakout"
                )
        
        # ── Original Hybrid Reaper Logic (trend/range regime routing) ──
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_adx = gates.get("htf_adx", 0) or 0
        ltf_adx = gates.get("ltf_adx", 0) or 0
        
        regime = "trend" if htf_adx >= self.trend_adx_min else "range"
        
        closes = [c.close for c in candles]
        prices_up, prices_down = self._price_hook(closes)
        rsi_up, rsi_down = self._rsi_hook(closes)
        
        if regime == "trend":
            # Trend-following pullback (ride the wave)
            if htf_dir == "long" and prices_down and rsi_down and len(candles) >= 5:
                tb = self._three_bar_pullback(closes, is_long=True)
                if tb:
                    if len(candles) < self.trend_ema_period + 1:
                        return None
                    ema = calculate_ema(closes, self.trend_ema_period)
                    if ema is None or last_close <= ema:
                        return None
                    rsi = calculate_rsi(closes, self.rsi_period)
                    if rsi is None or not (self.trend_rsi_long_min <= rsi <= self.trend_rsi_long_max):
                        return None
                    stop_dist = max(current_atr * self.trend_stop_atr_mult, self.trend_stop_floor)
                    stop_loss = last_close - stop_dist
                    target = last_close + stop_dist * self.trend_target_r
                    return AITradeDecision(
                        score=85, grade="A",
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="pullback", action="enter_long",
                        entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"HybridReaper Trend-Long (EMA={self.trend_ema_period}, RSI={self.rsi_period}, ADX={htf_adx:.1f})",
                        invalidation_conditions="Price closes below EMA or stop loss.",
                        management_instructions=f"Trend mode. Trail stop with EMA. Target {self.trend_target_r}R.",
                        urgency="medium", strategy_name=self.name, regime="trend"
                    )
            
            if htf_dir == "short" and prices_up and rsi_up and len(candles) >= 5:
                tb = self._three_bar_pullback(closes, is_long=False)
                if tb:
                    if len(candles) < self.trend_ema_period + 1:
                        return None
                    ema = calculate_ema(closes, self.trend_ema_period)
                    if ema is None or last_close >= ema:
                        return None
                    rsi = calculate_rsi(closes, self.rsi_period)
                    if rsi is None or not (self.trend_rsi_short_min <= rsi <= self.trend_rsi_short_max):
                        return None
                    stop_dist = max(current_atr * self.trend_stop_atr_mult, self.trend_stop_floor)
                    stop_loss = last_close + stop_dist
                    target = last_close - stop_dist * self.trend_target_r
                    return AITradeDecision(
                        score=85, grade="A",
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="pullback", action="enter_short",
                        entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"HybridReaper Trend-Short (EMA={self.trend_ema_period}, RSI={self.rsi_period}, ADX={htf_adx:.1f})",
                        invalidation_conditions="Price closes above EMA or stop loss.",
                        management_instructions=f"Trend mode. Trail stop with EMA. Target {self.trend_target_r}R.",
                        urgency="medium", strategy_name=self.name, regime="trend"
                    )
        
        else:
            # Range / mean-reversion scalp
            bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
            if bb_upper is None or bb_lower is None:
                return None
            rsi = calculate_rsi(closes, self.rsi_period)
            if rsi is None:
                return None
            
            is_near_bb_upper = last_close > bb_upper * 0.999
            is_near_bb_lower = last_close < bb_lower * 1.001
            
            if is_near_bb_lower and prices_down and rsi_down:
                oversold = self.rsi_oversold
                stop_dist = max(current_atr * self.range_stop_atr_mult, self.range_stop_floor)
                if (rsi <= oversold and is_near_bb_lower and last_close > bb_lower and
                    last_close < bb_middle):
                    stop_loss = last_close - stop_dist
                    target = last_close + stop_dist * self.range_target_r
                    return AITradeDecision(
                        score=80, grade="A",
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="mean_reversion", action="enter_long",
                        entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"HybridReaper Range-Long (BB={self.bb_period}, RSI={self.rsi_period})",
                        invalidation_conditions="Price breaks below lower Bollinger band.",
                        management_instructions=f"Range scalp. Quick target {self.range_target_r}R.",
                        urgency="high", strategy_name=self.name, regime="range"
                    )
            
            if is_near_bb_upper and prices_up and rsi_up:
                overbought = self.rsi_overbought
                stop_dist = max(current_atr * self.range_stop_atr_mult, self.range_stop_floor)
                if (rsi >= overbought and is_near_bb_upper and last_close < bb_upper and
                    last_close > bb_middle):
                    stop_loss = last_close + stop_dist
                    target = last_close - stop_dist * self.range_target_r
                    return AITradeDecision(
                        score=80, grade="A",
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="mean_reversion", action="enter_short",
                        entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"HybridReaper Range-Short (BB={self.bb_period}, RSI={self.rsi_period})",
                        invalidation_conditions="Price breaks above upper Bollinger band.",
                        management_instructions=f"Range scalp. Quick target {self.range_target_r}R.",
                        urgency="high", strategy_name=self.name, regime="range"
                    )
        
        return None


    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        return None
