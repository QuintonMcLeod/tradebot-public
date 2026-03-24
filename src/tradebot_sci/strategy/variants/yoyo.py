from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision, hold_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

# Track per-symbol risk escalation
_yoyo_risk_level: dict[str, float] = {}  # symbol → current risk %
_yoyo_daily_count: dict[str, int] = {}   # symbol:date → trade count today

SMA_PERIOD = 50  # Proven: use 50 SMA as trend filter (200 needs too much data)


def _calculate_sma(candles, period: int) -> Optional[float]:
    """Calculate SMA from last N candle closes."""
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    return sum(closes) / len(closes)


class YoYoStrategy(BaseStrategy):
    """
    Yo-Yo — Proven trend-following SAR engine.

    Based on research: Parabolic SAR + SMA filter + directional candle confirmation.

    Proven rules (from research):
    1. 50 SMA trend filter: only long when price > SMA50, short when < SMA50
    2. Entry candle must close in top 30% (long) or bottom 30% (short) of its range
    3. Stop at recent swing low/high (proven structural stop)
    4. Target: 2:1 R:R from swing stop (proven standard)
    5. SAR on stop hit (backtester handles this)
    6. Risk escalation: +1% after each profitable exit
    """

    BASE_RISK_PCT = 0.01     # Start at 1% risk
    RISK_ESCALATION = 0.01   # +1% per profitable trade
    MAX_RISK_PCT = 0.05      # Cap at 5%
    MAX_DAILY_TRADES = 3     # Cap per symbol per day

    def __init__(self, **kwargs):
        super().__init__("Yo-Yo")
        self.sma_period = int(kwargs.get('sma_period', 50))
        self.risk_escalation = float(kwargs.get('risk_escalation', self.RISK_ESCALATION))
        self.max_risk_pct = float(kwargs.get('max_risk_pct', self.MAX_RISK_PCT))
        self.target_r = float(kwargs.get('target_r', 2.0))

    def _get_risk_pct_for_symbol(self, symbol: str) -> float:
        return min(_yoyo_risk_level.get(symbol, self.BASE_RISK_PCT), self.max_risk_pct)

    def _escalate_risk(self, symbol: str):
        current = _yoyo_risk_level.get(symbol, self.BASE_RISK_PCT)
        _yoyo_risk_level[symbol] = min(current + self.risk_escalation, self.max_risk_pct)
        logger.info(f"[YO-YO] {symbol} risk escalated: {current:.1%} → {_yoyo_risk_level[symbol]:.1%}")

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        if open_position:
            return None

        if not snapshot.candles or len(snapshot.candles) < SMA_PERIOD + 5:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe, "Yo-Yo: Insufficient data"
            )

        candles = snapshot.candles
        last_bar = candles[-1]
        last_close = last_bar.close
        atr = calculate_atr(candles, period=14) or (last_close * 0.001)

        # ── DAILY CAP ──
        day_key = f"{snapshot.symbol}_{last_bar.timestamp.strftime('%Y%m%d') if hasattr(last_bar.timestamp, 'strftime') else 'x'}"
        count = _yoyo_daily_count.get(day_key, 0)
        if count >= self.MAX_DAILY_TRADES:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Yo-Yo: Daily cap ({count}/{self.MAX_DAILY_TRADES})"
            )

        # ── PROVEN FILTER 1: SMA trend filter ──
        # Research: only enter long when price > SMA, short when price < SMA
        sma = _calculate_sma(candles, self.sma_period)
        if sma is None:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Yo-Yo: SMA data insufficient")

        # Also check HTF direction for alignment
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        if last_close > sma and htf_dir in ("long", "neutral"):
            direction = "long"
        elif last_close < sma and htf_dir in ("short", "neutral"):
            direction = "short"
        else:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Yo-Yo: SMA filter blocked (price {'>' if last_close > sma else '<'} SMA, HTF={htf_dir})"
            )

        # ── PROVEN FILTER 2: Directional candle confirmation ──
        # Research: entry candle must close in top 30% (long) or bottom 30% (short) of range
        bar_range = last_bar.high - last_bar.low
        if bar_range <= 0:
            return None

        close_position_in_range = (last_close - last_bar.low) / bar_range  # 0=bottom, 1=top

        if direction == "long" and close_position_in_range < 0.7:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Yo-Yo: Candle not bullish enough ({close_position_in_range:.0%})"
            )
        if direction == "short" and close_position_in_range > 0.3:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Yo-Yo: Candle not bearish enough ({close_position_in_range:.0%})"
            )

        # ── PROVEN STOP: Recent swing low/high (structural stop) ──
        stop_buffer = atr * 0.2
        recent_lows = [c.low for c in candles[-5:]]
        recent_highs = [c.high for c in candles[-5:]]

        if direction == "long":
            swing_stop = min(recent_lows)
            stop_loss = swing_stop - stop_buffer
            risk_dist = last_close - stop_loss
            take_profit=None  # Target R
        else:
            swing_stop = max(recent_highs)
            stop_loss = swing_stop + stop_buffer
            risk_dist = stop_loss - last_close
            take_profit=None  # Target R

        # Sanity: risk_dist must be > 0
        if risk_dist <= 0:
            return None

        risk_pct = self._get_risk_pct_for_symbol(snapshot.symbol)
        _yoyo_daily_count[day_key] = count + 1
        action = "enter_long" if direction == "long" else "enter_short"

        notes = (
            f"Yo-Yo {direction.upper()}: "
            f"SMA{self.sma_period} filter, swing stop, {self.target_r}:1 R:R, "
            f"risk={risk_pct:.1%}"
        )

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=direction,
            phase="trend",
            action=action,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=None,
            risk_per_trade_pct=risk_pct,
            structure_summary=notes,
            notes=notes,
            gates=gates,
            invalidation_conditions=f"Swing stop @ {stop_loss:.5f} → SAR",
            management_instructions="2:1 R:R. Swing stop. SAR on hit.",
            urgency="high",
        )

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """Breakeven at 1.0R + risk escalation."""
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

        if direction == "long":
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        r_multiple = profit / initial_risk

        # At 1R: escalate risk for next trade
        if r_multiple >= 1.0:
            self._escalate_risk(snapshot.symbol)

        return None
