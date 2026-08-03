"""
  ForexStructureBreakoutV1 — Improved Structure Breakout Strategy

  Core logic:
  - Trade breakouts of swing structure in the direction of HTF trend
  - Uses ADX + volume + RSI + volatility regime to filter out chop
  - Adaptive exits: breakeven floor + chandelier trailing stop + time stop
  """
  from __future__ import annotations
  import logging
  from typing import Dict, List, Optional, Tuple
  import numpy as np
  from tradebot_sci.market.models import MarketSnapshot
  from tradebot_sci.strategy.decisions import AITradeDecision, hold_decision, scale_out_decision
  from tradebot_sci.strategy.variants.base import BaseStrategy

  logger = logging.getLogger(__name__)


  class ForexStructureBreakoutV1(BaseStrategy):
      """
      An improved breakout strategy that trades structure breaks in the direction
      of the trend with stricter filters to reduce false breakouts.

      Improvements over ForexStructureBreakout:
      - Stricter ADX threshold and volatility regime filter
      - RSI confirmation and overbought/oversold avoidance
      - Bollinger Band width / expansion confirmation
      - Wait for retest/close confirmation of breakout level
      - Session-aware filtering (avoid dead zones)
      - Multiple take-profit levels with time-based exit
      - Faster breakeven and tighter chandelier trailing stop
      - Dynamic position sizing based on ATR
      - Minimum R:R gate
      """

      def __init__(self, target_r: float = 2.0, **kwargs):
          super().__init__("ForexStructureBreakoutV1")
          logger.info(f"[SB_INIT] kwargs={kwargs}")

          self.target_r = float(kwargs.get("target_r", target_r))
          self.breakout_lookback = int(kwargs.get("breakout_lookback", 5))
          # Stricter ADX to avoid chop
          self.adx_min = float(kwargs.get("adx_min", 35.0))
          self.volume_min_ratio = float(kwargs.get("volume_min_ratio", 1.5))
          self.stop_floor_pct = float(kwargs.get("stop_floor_pct", 0.0015))
          self.stop_atr_mult = float(kwargs.get("stop_atr_mult", 1.0))
          self.score_threshold = float(kwargs.get("score_threshold", 75.0))

          # Exit-management parameters
          self.breakeven_arm_r = float(kwargs.get("breakeven_arm_r", 0.4))
          self.trailing_arm_r = float(kwargs.get("trailing_arm_r", 0.8))
          self.trailing_atr_mult = float(kwargs.get("trailing_atr_mult", 1.2))
          self.trailing_lookback = int(kwargs.get("trailing_lookback", 5))
          self.scale_out_fraction = float(kwargs.get("scale_out_fraction", 0.5))

          # ------------------------------------------------------------------
          # New filters to reduce false breakouts
          # ------------------------------------------------------------------
          # RSI period and trend-aligned zones
          self.rsi_period = int(kwargs.get("rsi_period", 14))
          self.rsi_long_min = float(kwargs.get("rsi_long_min", 50.0))
          self.rsi_long_max = float(kwargs.get("rsi_long_max", 75.0))
          self.rsi_short_min = float(kwargs.get("rsi_short_min", 25.0))
          self.rsi_short_max = float(kwargs.get("rsi_short_max", 50.0))

          # Bollinger Band expansion confirmation
          self.bb_period = int(kwargs.get("bb_period", 20))
          self.bb_mult = float(kwargs.get("bb_mult", 2.0))
          self.bb_min_width_pct = float(kwargs.get("bb_min_width_pct", 0.0010))

          # Volatility regime filter: avoid extremely low or high ATR
          self.atr_min_pct = float(kwargs.get("atr_min_pct", 0.0005))
          self.atr_max_pct = float(kwargs.get("atr_max_pct", 0.0150))

          # Trend alignment: fast EMA above/below slow EMA
          self.ema_fast = int(kwargs.get("ema_fast", 8))
          self.ema_slow = int(kwargs.get("ema_slow", 21))

          # Retest confirmation: require N closes beyond breakout level
          self.breakout_confirm_bars = int(kwargs.get("breakout_confirm_bars", 1))

          # Minimum risk:reward ratio allowed
          self.min_rr = float(kwargs.get("min_rr", 1.5))

          # Time stop: bars without hitting TP/BE after entry
          self.time_stop_bars = int(kwargs.get("time_stop_bars", 8))

          # Risk per trade in percent (for dynamic sizing)
          self.risk_per_trade_pct = float(kwargs.get("risk_per_trade_pct", 1.0))

          # Tracking live positions and state
          self._active_entry: Optional[Dict] = None
          self._pending_setup: Optional[Dict] = None

      # ------------------------------------------------------------------
      # Helpers
      # ------------------------------------------------------------------

      def _find_swing_high(self, candles: List) -> float:
          """Find highest high over lookback period (excluding current bar)."""
          lookback = min(self.breakout_lookback, len(candles) - 1)
          if lookback <= 0:
              return 0.0
          return max(c.high for c in candles[-lookback - 1 : -1])

      def _find_swing_low(self, candles: List) -> float:
          """Find lowest low over lookback period (excluding current bar)."""
          lookback = min(self.breakout_lookback, len(candles) - 1)
          if lookback <= 0:
              return 0.0
          return min(c.low for c in candles[-lookback - 1 : -1])

      def _current_atr(self, candles: List) -> float:
          """Simple ATR estimate from recent candles."""
          if len(candles) < 2:
              return 0.0005
          recent = candles[-20:]
          trs = []
          for i in range(1, len(recent)):
              c = recent[i]
              p = recent[i - 1]
              tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
              trs.append(tr)
          return np.mean(trs) if trs else 0.0005

      def _volume_ratio(self, candles: List) -> float:
          """Current volume vs average of lookback."""
          if len(candles) < 3:
              return 1.0
          lookback = min(self.breakout_lookback * 2, len(candles) - 1)
          recent = candles[-lookback - 1 : -1]
          if not recent:
              return 1.0
          vols = [getattr(c, "volume", 0) or 0.0 for c in recent]
          avg_vol = np.mean(vols) if vols else 1e-9
          current = getattr(candles[-1], "volume", 0) or 0.0
          return (current / avg_vol) if avg_vol > 0 else 1.0

      def _rsi(self, candles: List, period: Optional[int] = None) -> float:
          """Compute RSI from closing prices."""
          period = period or self.rsi_period
          if len(candles) < period + 1:
              return 50.0
          closes = np.array([c.close for c in candles[-period - 1 :]])
          deltas = np.diff(closes)
          gains = np.where(deltas > 0, deltas, 0.0)
          losses = np.where(deltas < 0, -deltas, 0.0)
          avg_gain = np.mean(gains)
          avg_loss = np.mean(losses)
          if avg_loss == 0:
              return 100.0
          rs = avg_gain / avg_loss
          return 100.0 - (100.0 / (1.0 + rs))

      def _ema(self, candles: List, period: int) -> float:
          """Compute EMA of closes."""
          if len(candles) < period:
              return candles[-1].close if candles else 0.0
          closes = np.array([c.close for c in candles[-period:]])
          weights = np.exp(np.linspace(-1.0, 0.0, period))
          weights /= weights.sum()
          return float(np.dot(closes, weights))

      def _bollinger_width_pct(self, candles: List) -> Tuple[float, float, float, float]:
          """Return (upper, middle, lower, width_pct) of Bollinger Bands."""
          if len(candles) < self.bb_period:
              mid = candles[-1].close if candles else 0.0
              return mid, mid, mid, 0.0
          closes = np.array([c.close for c in candles[-self.bb_period :]])
          mid = float(np.mean(closes))
          std = float(np.std(closes))
          upper = mid + self.bb_mult * std
          lower = mid - self.bb_mult * std
          width_pct = (upper - lower) / mid if mid > 0 else 0.0
          return upper, mid, lower, width_pct

      def _adx(self, candles: List, period: int = 14) -> float:
          """Compute ADX from recent candles."""
          if len(candles) < period + 1:
              return 0.0
          highs = np.array([c.high for c in candles[-period - 1 :]])
          lows = np.array([c.low for c in candles[-period - 1 :]])
          closes = np.array([c.close for c in candles[-period - 1 :]])

          plus_dm = np.maximum(0.0, highs[1:] - highs[:-1])
          minus_dm = np.maximum(0.0, lows[:-1] - lows[1:])
          tr1 = highs[1:] - lows[1:]
          tr2 = np.abs(highs[1:] - closes[:-1])
          tr3 = np.abs(lows[1:] - closes[:-1])
          tr = np.maximum(np.maximum(tr1, tr2), tr3)

          atr = np.mean(tr)
          plus_di = 100.0 * np.mean(plus_dm) / (atr + 1e-12)
          minus_di = 100.0 * np.mean(minus_dm) / (atr + 1e-12)
          dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-12)
          return dx

      def _is_dead_session(self, candle) -> bool:
          """Avoid entries during very low-liquidity sessions if timestamp available."""
          ts = getattr(candle, "timestamp", None)
          if ts is None:
              return False
          try:
              hour = ts.hour
              # Avoid entries in late NY / early Asian dead zone (roughly 22:00-02:00 UTC)
              if 22 <= hour or hour < 2:
                  return True
          except Exception:
              return False
          return False

      def _recent_closes_beyond(self, candles: List, level: float, direction: str) -> int:
          """Count how many recent closes are beyond a price level."""
          count = 0
          for c in candles[-self.breakout_confirm_bars :]:
              if direction == "long" and c.close > level:
                  count += 1
              elif direction == "short" and c.close < level:
                  count += 1
          return count

      def _score_setup(
          self,
          direction: str,
          adx: float,
          volume_ratio: float,
          rsi: float,
          bb_width_pct: float,
          ema_aligned: bool,
          confirmed: bool,
      ) -> float:
          """Score a setup 0-100; higher is stronger."""
          score = 0.0
          score += min(adx, 50.0)  # up to 50
          score += min(volume_ratio * 10.0, 20.0)  # up to 20
          if direction == "long" and self.rsi_long_min <= rsi <= self.rsi_long_max:
              score += 10.0
          if direction == "short" and self.rsi_short_min <= rsi <= self.rsi_short_max:
              score += 10.0
          if bb_width_pct >= self.bb_min_width_pct:
              score += 10.0
          if ema_aligned:
              score += 10.0
          if confirmed:
              score += 10.0
          return min(score, 100.0)

      def _dynamic_size(self, price: float, stop_distance: float, capital: float) -> float:
          """Return position size to risk self.risk_per_trade_pct of capital."""
          if stop_distance <= 0 or capital <= 0:
              return 0.0
          risk_amount = capital * (self.risk_per_trade_pct / 100.0)
          units = risk_amount / stop_distance
          return max(units, 0.0)

      # ------------------------------------------------------------------
      # Entry decision
      # ------------------------------------------------------------------

      def on_bar(self, snapshot: MarketSnapshot) -> AITradeDecision:
          """Evaluate a completed bar and emit an entry decision."""
          candles = getattr(snapshot, "candles", []) or []
          if len(candles) < max(self.breakout_lookback, self.rsi_period, self.bb_period, self.ema_slow) + 2:
              return hold_decision()

          current = candles[-1]
          atr = self._current_atr(candles)
          price = current.close

          # Volatility regime filter
          atr_pct = atr / price if price > 0 else 0.0
          if atr_pct < self.atr_min_pct or atr_pct > self.atr_max_pct:
              return hold_decision()

          # Session filter
          if self._is_dead_session(current):
              return hold_decision()

          swing_high = self._find_swing_high(candles)
          swing_low = self._find_swing_low(candles)
          if swing_high <= 0.0 or swing_low <= 0.0:
              return hold_decision()

          adx = self._adx(candles)
          if adx < self.adx_min:
              return hold_decision()

          volume_ratio = self._volume_ratio(candles)
          if volume_ratio < self.volume_min_ratio:
              return hold_decision()

          rsi = self._rsi(candles)
          _, _, _, bb_width_pct = self._bollinger_width_pct(candles)
          if bb_width_pct < self.bb_min_width_pct:
              return hold_decision()

          ema_fast = self._ema(candles, self.ema_fast)
          ema_slow = self._ema(candles, self.ema_slow)

          # HTF trend alignment via EMAs
          ema_bullish = ema_fast > ema_slow
          ema_bearish = ema_fast < ema_slow

          # Breakout detection
          long_break = current.close > swing_high
          short_break = current.close < swing_low

          if not long_break and not short_break:
              return hold_decision()

          direction = "long" if long_break else "short"
          ema_aligned = (direction == "long" and ema_bullish) or (direction == "short" and ema_bearish)

          # Require trend-aligned EMAs
          if not ema_aligned:
              return hold_decision()

          # RSI filter: long only in bullish RSI zone, short only in bearish
          if direction == "long" and not (self.rsi_long_min <= rsi <= self.rsi_long_max):
              return hold_decision()
          if direction == "short" and not (self.rsi_short_min <= rsi <= self.rsi_short_max):
              return hold_decision()

          # Breakout confirmation: require closes beyond level
          breakout_level = swing_high if direction == "long" else swing_low
          confirmed = self._recent_closes_beyond(candles, breakout_level, direction) >= self.breakout_confirm_bars

          score = self._score_setup(direction, adx, volume_ratio, rsi, bb_width_pct, ema_aligned, confirmed)
          if score < self.score_threshold:
              return hold_decision()

          # Stop placement
          if direction == "long":
              stop_base = min(swing_low, current.low - atr * self.stop_atr_mult)
              stop_distance = max(current.close - stop_base, price * self.stop_floor_pct)
          else:
              stop_base = max(swing_high, current.high + atr * self.stop_atr_mult)
              stop_distance = max(stop_base - current.close, price * self.stop_floor_pct)

          target_distance = stop_distance * self.target_r
          rr = target_distance / stop_distance if stop_distance > 0 else 0.0
          if rr < self.min_rr:
              return hold_decision()

          # Dynamic position sizing
          capital = getattr(snapshot, "capital", 10000.0) or 10000.0
          size = self._dynamic_size(price, stop_distance, capital)

          self._active_entry = {
              "direction": direction,
              "entry_price": price,
              "stop_price": price - stop_distance if direction == "long" else price + stop_distance,
              "target_price": price + target_distance if direction == "long" else price - target_distance,
              "size": size,
              "bars_in_trade": 0,
              "breakeven_moved": False,
              "trailing_active": False,
              "scale_done": False,
          }

          decision = AITradeDecision(
              action="enter",
              direction=direction,
              size=size,
              stop_loss=self._active_entry["stop_price"],
              take_profit=self._active_entry["target_price"],
              reason=f"SBv1 score={score:.1f} adx={adx:.1f} vol={volume_ratio:.2f} rsi={rsi:.1f}",
          )
          return decision

      # ------------------------------------------------------------------
      # Tick-level exit management
      # ------------------------------------------------------------------

      def on_tick(self, snapshot: MarketSnapshot) -> AITradeDecision:
          """Manage open position on each tick."""
          if self._active_entry is None:
              return hold_decision()

          candles = getattr(snapshot, "candles", []) or []
          if len(candles) < self.trailing_lookback + 1:
              return hold_decision()

          current = snapshot  # tick
          bid = getattr(current, "bid", None)
          ask = getattr(current, "ask", None)
          price = (bid + ask) / 2.0 if bid is not None and ask is not None else getattr(current, "price", 0.0)
          if price <= 0:
              return hold_decision()

          pos = self._active_entry
          direction = pos["direction"]
          entry = pos["entry_price"]
          stop = pos["stop_price"]
          target = pos["target_price"]
          size = pos["size"]

          # R multiple of current price
          if direction == "long":
              current_r = (price - entry) / (entry - stop) if (entry - stop) != 0 else 0.0
          else:
              current_r = (entry - price) / (stop - entry) if (stop - entry) != 0 else 0.0

          # Breakeven move
          if not pos["breakeven_moved"] and current_r >= self.breakeven_arm_r:
              pos["breakeven_moved"] = True
              # Move stop to entry minus a small buffer for fees/slippage
              buffer = abs(entry - stop) * 0.05
              if direction == "long":
                  pos["stop_price"] = entry - buffer
              else:
                  pos["stop_price"] = entry + buffer

          # Trailing stop activation
          recent = candles[-self.trailing_lookback :]
          atr = self._current_atr(candles)
          if pos["breakeven_moved"] and current_r >= self.trailing_arm_r:
              pos["trailing_active"] = True
              if direction == "long":
                  swing_low_trail = min(c.low for c in recent)
                  new_stop = swing_low_trail - atr * self.trailing_atr_mult
                  pos["stop_price"] = max(pos["stop_price"], new_stop)
              else:
                  swing_high_trail = max(c.high for c in recent)
                  new_stop = swing_high_trail + atr * self.trailing_atr_mult
                  pos["stop_price"] = min(pos["stop_price"], new_stop)

          # Hard stop hit
          if direction == "long" and price <= pos["stop_price"]:
              self._active_entry = None
              return AITradeDecision(action="exit", direction=direction, size=size, reason="stop_loss")
          if direction == "short" and price >= pos["stop_price"]:
              self._active_entry = None
              return AITradeDecision(action="exit", direction=direction, size=size, reason="stop_loss")

          # Take profit
          if direction == "long" and price >= target:
              self._active_entry = None
              return AITradeDecision(action="exit", direction=direction, size=size, reason="take_profit")
          if direction == "short" and price <= target:
              self._active_entry = None
              return AITradeDecision(action="exit", direction=direction, size=size, reason="take_profit")

          # Scale out at +1R
          if not pos["scale_done"] and current_r >= 1.0:
              pos["scale_done"] = True
              scale_size = size * self.scale_out_fraction
              return scale_out_decision(size=scale_size, reason="scale_out_1R")

          return hold_decision()

      # ------------------------------------------------------------------
      # Time-based and bar-based management
      # ------------------------------------------------------------------

      def on_candle(self, snapshot: MarketSnapshot) -> AITradeDecision:
          """Called on each new closed candle for time-stop and bar counting."""
          if self._active_entry is None:
              return hold_decision()

          candles = getattr(snapshot, "candles", []) or []
          if not candles:
              return hold_decision()

          pos = self._active_entry
          pos["bars_in_trade"] += 1

          # Time stop: close if trade hasn't made meaningful progress
          if pos["bars_in_trade"] >= self.time_stop_bars and not pos["breakeven_moved"]:
              size = pos["size"]
              self._active_entry = None
              return AITradeDecision(
                  action="exit",
                  direction=pos["direction"],
                  size=size,
                  reason="time_stop",
              )

          return self.on_bar(snapshot) if not pos else hold_decision()

      def reset(self):
          """Reset internal state."""
          self._active_entry = None
          self._pending_setup = None