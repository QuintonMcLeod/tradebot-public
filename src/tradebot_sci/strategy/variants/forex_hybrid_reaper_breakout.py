from __future__ import annotations
import logging
from typing import Optional


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
logger = logging.getLogger(__name__)

class ForexHybridReaperStrategy(BaseStrategy):
    score_threshold = 72.0
    SESSION_PROFILE = ["forex_hybrid_scalper:hybrid_overlap", "forex_hybrid_scalper:london_open", "forex_hybrid_scalper:asian_open"]
    """
    Forex Hybrid Reaper — regime-router.

    Strong HTF trend  -> trend-following pullback (ride the wave).
    Choppy / neutral  -> mean-reversion scalp.
    """
    def __init__(self, target_r=1.0, **kwargs):
        super().__init__("ForexHybridReaper")
        self.target_r = target_r

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
        self.breakout_distance_pct = float(kwargs.get('breakout_distance_pct', 0.0))  # 0 = disabled

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
        if len(closes) < 5:
            return False
        deltas = [closes[-i] - closes[-i-1] for i in range(2, 5)]
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
        if gates.get("is_synthetic_override") is True:
            return None

        candles = snapshot.candles
        if len(candles) < self.trend_ema_period or len(candles) < 40:
            return None

        # Volatility guard
        atr_history = [calculate_atr(candles[:i+1], period=14) for i in range(14, len(candles))]
        atr_history = [a for a in atr_history if a]
        if len(atr_history) < 20:
            return None
        avg_atr_20 = sum(atr_history[-20:]) / 20.0
        current_atr = calculate_atr(candles, period=14)
        if not current_atr or current_atr < (avg_atr_20 * 0.5):
            return None

        closes = [c.close for c in candles]
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        last_close = closes[-1]
        is_long_setup = last_close > trend_ema

        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_adx = gates.get("htf_adx", 0) or 0
        ltf_adx = gates.get("ltf_adx", 0) or 0
        adx = max(htf_adx, ltf_adx)

        # Regime routing
        # Trend only when HTF is clearly directional AND ADX confirms strength
        in_strong_trend = htf_dir in ("long", "short") and adx >= self.trend_adx_min
        regime = "trend" if in_strong_trend else "range"

        # In range mode, never fade a strong HTF trend. If HTF is strongly
        # directional but ADX is below threshold, stand aside.
        if regime == "range" and htf_dir in ("long", "short"):
            logger.info(f"[ForexHybridReaper] {snapshot.symbol} BLOCKED: range mode cannot fade HTF={htf_dir}")
            return None

        exec_bollinger = gates.get("exec_bollinger", {})
        lower_bb = exec_bollinger.get("lower", float('-inf'))
        mid_bb = exec_bollinger.get("middle", last_close)
        upper_bb = exec_bollinger.get("upper", float('inf'))
        rsi = gates.get("exec_rsi", 50.0)

        if open_position:
            return None

        score, grade, summary = self.score_signal(snapshot, gates, regime)

        logger.info(
            f"[HybridReaper Debug {snapshot.symbol}] Regime={regime} | Close={last_close:.5f} | "
            f"EMA={trend_ema:.5f} | RSI={rsi:.1f} | LBB={lower_bb:.5f} | UBB={upper_bb:.5f} | "
            f"HTF={htf_dir} | ADX={adx:.1f} | Score={score:.1f}"
        )

        price_long_hook, price_short_hook = self._price_hook(closes)
        rsi_long_hook, rsi_short_hook = self._rsi_hook(closes)

        if self.price_hook_required:
            if is_long_setup and not price_long_hook:
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no price long hook")
                return None
            if not is_long_setup and not price_short_hook:
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no price short hook")
                return None

        if self.rsi_hook_required:
            if is_long_setup and not rsi_long_hook:
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no RSI long hook")
                return None
            if not is_long_setup and not rsi_short_hook:
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no RSI short hook")
                return None

        if regime == "trend":
            # Trend mode: 3-bar pullback completed, current bar hooks back
            if not self._three_bar_pullback(closes, is_long_setup):
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: trend pullback not present")
                return None

            current_candle = candles[-1]
            if not self._strong_momentum(current_candle):
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no strong momentum candle")
                return None
            if not self._structure_break(candles, is_long_setup):
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no structure break")
                return None

            stop_dist = max(current_atr * self.trend_stop_atr_mult, last_close * self.trend_stop_floor)
            tr = self.trend_target_r
            recent_candles = candles[-3:] if len(candles) >= 3 else candles

            if (is_long_setup and
                self.trend_rsi_long_min <= rsi <= self.trend_rsi_long_max and
                lower_bb <= last_close <= mid_bb and
                score >= self.score_threshold):

                # Use the wider (lower) of structure support or the ATR-based floor;
                # never let the recent-candle override produce a stop inside the spread.
                stop_loss = min(min(c.low for c in recent_candles) - current_atr * 0.5,
                                last_close - stop_dist)
                target = last_close + (last_close - stop_loss) * tr
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="continuation", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Trend Long (RSI={rsi:.1f}, Pullback, Score={score:.0f})",
                    invalidation_conditions="Close below stop loss.",
                    management_instructions=f"Trend mode. Target {tr}R.",
                    urgency="high", strategy_name=self.name, regime="trend"
                )

            if (not is_long_setup and
                self.trend_rsi_short_min <= rsi <= self.trend_rsi_short_max and
                mid_bb <= last_close <= upper_bb and
                score >= self.score_threshold):

                # Use the wider (higher) of structure resistance or the ATR-based floor;
                # never let the recent-candle override produce a stop inside the spread.
                stop_loss = max(max(c.high for c in recent_candles) + current_atr * 0.5,
                                last_close + stop_dist)
                target = last_close - (stop_loss - last_close) * tr
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="continuation", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Trend Short (RSI={rsi:.1f}, Pullback, Score={score:.0f})",
                    invalidation_conditions="Close above stop loss.",
                    management_instructions=f"Trend mode. Target {tr}R.",
                    urgency="high", strategy_name=self.name, regime="trend"
                )

        else:
            # Range mode: never enter against a strong HTF trend (blocked above).
            # Only scalp when HTF is neutral/mild.
            if not self._three_bar_exhaustion(closes, is_long_setup):
                logger.info(f"[HybridReaper] {snapshot.symbol} BLOCKED: no 3-bar exhaustion")
                return None

            stop_dist = max(current_atr * self.range_stop_atr_mult, last_close * self.range_stop_floor)
            tr = float(getattr(self._profile, "target_r", self.range_target_r)) if getattr(self, "_profile", None) else self.range_target_r
            prev_close = closes[-2] if len(closes) >= 2 else last_close
            recent = candles[-3:] if len(candles) >= 3 else candles
            touched_lower = prev_close <= lower_bb or any(c.low <= lower_bb for c in recent)
            touched_upper = prev_close >= upper_bb or any(c.high >= upper_bb for c in recent)
            overbought = float(getattr(self._profile, 'rsi_overbought', self.rsi_overbought)) if getattr(self, '_profile', None) else self.rsi_overbought
            oversold = float(getattr(self._profile, 'rsi_oversold', self.rsi_oversold)) if getattr(self, '_profile', None) else self.rsi_oversold

            if (is_long_setup and rsi <= oversold and touched_lower and last_close > lower_bb and
                score >= self.score_threshold):
                stop_loss = last_close - stop_dist
                target = last_close + stop_dist * tr
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="correction", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Range Long (RSI={rsi:.1f}, Bounce, Score={score:.0f})",
                    invalidation_conditions="Close below stop loss.",
                    management_instructions=f"Range mode. Target {tr}R.",
                    urgency="high", strategy_name=self.name, regime="range"
                )

            if (not is_long_setup and rsi >= overbought and touched_upper and last_close < upper_bb and
                score >= self.score_threshold):
                stop_loss = last_close + stop_dist
                target = last_close - stop_dist * tr
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="correction", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Range Short (RSI={rsi:.1f}, Bounce, Score={score:.0f})",
                    invalidation_conditions="Close above stop loss.",
                    management_instructions=f"Range mode. Target {tr}R.",
                    urgency="high", strategy_name=self.name, regime="range"
                )

        # ── Breakout Mode ──────────────────────────────────────
        print(f"[DEBUG] Breakout check: candles={len(candles)}, atr={current_atr}, close={last_close}, score={score}", )
        if current_atr > 0 and len(candles) >= 5:
            recent_high = max(c.high for c in candles[-5:])
            recent_low = min(c.low for c in candles[-5:])
            breakout_dist = last_close * self.breakout_distance_pct / 100
            
            if last_close > recent_high + breakout_dist:
                stop_loss = recent_low - current_atr * 0.5
                stop_loss = min(stop_loss, last_close - current_atr * 2)
                target = last_close + (last_close - stop_loss) * self.trend_target_r
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="breakout", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Breakout Long (Score={score:.0f}, Break={self.breakout_distance_pct:.2f}%)",
                    invalidation_conditions="Close below stop loss.",
                    management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                    urgency="high", strategy_name=self.name, regime="breakout"
                )
            
            if last_close < recent_low - breakout_dist:
                stop_loss = recent_high + current_atr * 0.5
                stop_loss = max(stop_loss, last_close + current_atr * 2)
                target = last_close - (stop_loss - last_close) * self.trend_target_r
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="breakout", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Breakout Short (Score={score:.0f}, Break={self.breakout_distance_pct:.2f}%)",
                    invalidation_conditions="Close above stop loss.",
                    management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                    urgency="high", strategy_name=self.name, regime="breakout"
                )
        
        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        return None
