"""
  ForexStructureBreakoutV3 — Tighter Trend-Following Breakout Strategy

  Core logic:
  - Only trade breakouts aligned with the dominant HTF trend
  - Require multi-candle confirmation, volume expansion, and volatility regime
  - Wait for retest / pullback to broken structure before entry
  - Adaptive exits: quick breakeven, chandelier trail, time stop, partial scale-out
  """

  from __future__ import annotations
  import logging
  from typing import Dict, List, Optional, Tuple
  from datetime import datetime, time, timezone
  import numpy as np
  from tradebot_sci.market.models import MarketSnapshot
  from tradebot_sci.strategy.decisions import AITradeDecision, hold_decision, scale_out_decision
  from tradebot_sci.strategy.variants.base import BaseStrategy

  logger = logging.getLogger(__name__)


  class ForexStructureBreakoutV3(BaseStrategy):
      """
      Refined breakout strategy focused on filtering false breakouts and
      only entering in strongly trending, high-conviction conditions.
      """

      def __init__(self, target_r: float = 2.0, **kwargs):
          super().__init__("ForexStructureBreakoutV3")
          logger.info(f"[SB_INIT_V3] kwargs={kwargs}")

          self.target_r = float(kwargs.get("target_r", target_r))

          # Breakout definition
          self.breakout_lookback = int(kwargs.get("breakout_lookback", 10))
          self.breakout_confirm_bars = int(kwargs.get("breakout_confirm_bars", 2))
          self.retest_bars_max = int(kwargs.get("retest_bars_max", 5))

          # Trend filters
          self.adx_min = float(kwargs.get("adx_min", 40.0))
          self.ema_fast = int(kwargs.get("ema_fast", 8))
          self.ema_medium = int(kwargs.get("ema_medium", 21))
          self.ema_slow = int(kwargs.get("ema_slow", 50))
          self.trend_lookback = int(kwargs.get("trend_lookback", 20))

          # RSI
          self.rsi_period = int(kwargs.get("rsi_period", 14))
          self.rsi_long_min = float(kwargs.get("rsi_long_min", 55.0))
          self.rsi_long_max = float(kwargs.get("rsi_long_max", 75.0))
          self.rsi_short_min = float(kwargs.get("rsi_short_min", 25.0))
          self.rsi_short_max = float(kwargs.get("rsi_short_max", 45.0))

          # Bollinger Bands
          self.bb_period = int(kwargs.get("bb_period", 20))
          self.bb_mult = float(kwargs.get("bb_mult", 2.0))
          self.bb_min_width_pct = float(kwargs.get("bb_min_width_pct", 0.0012))
          self.bb_max_width_pct = float(kwargs.get("bb_max_width_pct", 0.0100))

          # Volatility regime
          self.atr_period = int(kwargs.get("atr_period", 14))
          self.atr_min_pct = float(kwargs.get("atr_min_pct", 0.0007))
          self.atr_max_pct = float(kwargs.get("atr_max_pct", 0.0120))
          self.atr_squeeze_pct = float(kwargs.get("atr_squeeze_pct", 0.0015))

          # Volume
          self.volume_min_ratio = float(kwargs.get("volume_min_ratio", 1.6))
          self.volume_lookback = int(kwargs.get("volume_lookback", 20))

          # Market quality
          self.max_spread_pct = float(kwargs.get("max_spread_pct", 0.0002))
          self.min_bar_size_pct = float(kwargs.get("min_bar_size_pct", 0.0003))

          # Risk management
          self.min_rr = float(kwargs.get("min_rr", 2.0))
          self.risk_per_trade_pct = float(kwargs.get("risk_per_trade_pct", 0.75))
          self.max_daily_trades = int(kwargs.get("max_daily_trades", 5))
          self.consec_loss_cooldown = int(kwargs.get("consec_loss_cooldown", 2))
          self.stop_atr_mult = float(kwargs.get("stop_atr_mult", 1.0))
          self.stop_floor_pct = float(kwargs.get("stop_floor_pct", 0.0010))
          self.scale_out_fraction = float(kwargs.get("scale_out_fraction", 0.5))
          self.scale_out_r = float(kwargs.get("scale_out_r", 1.0))

          # Exit management
          self.breakeven_arm_r = float(kwargs.get("breakeven_arm_r", 0.35))
          self.trailing_arm_r = float(kwargs.get("trailing_arm_r", 0.65))
          self.trailing_atr_mult = float(kwargs.get("trailing_atr_mult", 1.0))
          self.trailing_lookback = int(kwargs.get("trailing_lookback", 3))
          self.time_stop_bars = int(kwargs.get("time_stop_bars", 6))

          # Session filter (UTC)
          self.session_filter = bool(kwargs.get("session_filter", True))

          # Tracking
          self._active_entry: Optional[Dict] = None
          self._pending_setup: Optional[Dict] = None
          self._daily_trades: Dict[str, int] = {}
          self._consec_losses: int = 0
          self._last_trade_day: Optional[str] = None

      # ------------------------------------------------------------------
      # Helpers
      # ------------------------------------------------------------------

      def _day_key(self, ts: datetime) -> str:
          return ts.strftime("%Y-%m-%d")

      def _is_active_session(self, ts: datetime) -> bool:
          if not self.session_filter:
              return True
          t = ts.time()
          # Major FX sessions: London 08:00-17:00 UTC, NY 13:00-22:00 UTC
          return (
              (time(8, 0) <= t <= time(17, 0)) or
              (time(13, 0) <= t <= time(22, 0))
          )

      def _ema(self, values: List[float], period: int) -> Optional[float]:
          if len(values) < period:
              return None
          k = 2.0 / (period + 1)
          ema = values[0]
          for v in values[1:]:
              ema = v * k + ema * (1 - k)
          return ema

      def _rsi(self, closes: List[float], period: int) -> Optional[float]:
          if len(closes) < period + 1:
              return None
          deltas = np.diff(closes[-period - 1 :])
          gains = np.where(deltas > 0, deltas, 0.0)
          losses = np.where(deltas < 0, -deltas, 0.0)
          avg_gain = np.mean(gains)
          avg_loss = np.mean(losses)
          if avg_loss == 0:
              return 100.0
          rs = avg_gain / avg_loss
          return 100.0 - (100.0 / (1.0 + rs))

      def _atr(self, candles: List, period: int = 14) -> float:
          if len(candles) < period + 1:
              return 0.0005
          trs = []
          for i in range(1, len(candles[-period - 1 :])):
              c = candles[i]
              p = candles[i - 1]
              tr1 = c.high - c.low
              tr2 = abs(c.high - p.close)
              tr3 = abs(c.low - p.close)
              trs.append(max(tr1, tr2, tr3))
          return float(np.mean(trs)) if trs else 0.0005

      def _bbands(self, candles: List) -> Tuple[Optional[float], Optional[float], Optional[float]]:
          if len(candles) < self.bb_period:
              return None, None, None
          closes = [c.close for c in candles[-self.bb_period :]]
          mid = np.mean(closes)
          std = np.std(closes)
          upper = mid + self.bb_mult * std
          lower = mid - self.bb_mult * std
          return upper, mid, lower

      def _adx(self, candles: List, period: int = 14) -> Optional[float]:
          if len(candles) < period * 2:
              return None
          plus_dm = []
          minus_dm = []
          trs = []
          for i in range(1, period + 1):
              c = candles[-i]
              p = candles[-i - 1]
              up = c.high - p.high
              down = p.low - c.low
              plus_dm.append(max(up, 0) if up > down else 0)
              minus_dm.append(max(down, 0) if down > up else 0)
              tr1 = c.high - c.low
              tr2 = abs(c.high - p.close)
              tr3 = abs(c.low - p.close)
              trs.append(max(tr1, tr2, tr3))
          atr = np.mean(trs)
          plus_di = 100 * np.mean(plus_dm) / atr if atr else 0
          minus_di = 100 * np.mean(minus_dm) / atr if atr else 0
          dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) else 0
          return dx

      def _find_swing_high(self, candles: List) -> float:
          lookback = min(self.breakout_lookback, len(candles) - 1)
          if lookback <= 0:
              return 0.0
          return max(c.high for c in candles[-lookback - 1 : -1])

      def _find_swing_low(self, candles: List) -> float:
          lookback = min(self.breakout_lookback, len(candles) - 1)
          if lookback <= 0:
              return 0.0
          return min(c.low for c in candles[-lookback - 1 : -1])

      def _trend_aligned(self, candles: List, direction: str) -> bool:
          if len(candles) < self.ema_slow + 5:
              return False
          closes = [c.close for c in candles]
          fast = self._ema(closes, self.ema_fast)
          medium = self._ema(closes, self.ema_medium)
          slow = self._ema(closes, self.ema_slow)
          if fast is None or medium is None or slow is None:
              return False
          if direction == "long":
              return fast > medium > slow
          return fast < medium < slow

      def _volume_spike(self, candles: List) -> bool:
          if len(candles) < self.volume_lookback + 1:
              return True
          recent = [c.volume for c in candles[-self.volume_lookback : -1]]
          if not recent or np.mean(recent) == 0:
              return True
          return candles[-1].volume / np.mean(recent) >= self.volume_min_ratio

      def _is_volatility_ok(self, candles: List) -> bool:
          if len(candles) < self.atr_period + 1:
              return False
          atr = self._atr(candles, self.atr_period)
          mid = candles[-1].close
          pct = atr / mid if mid else 0
          return self.atr_min_pct <= pct <= self.atr_max_pct

      def _bb_expanding(self, candles: List) -> bool:
          if len(candles) < self.bb_period + 3:
              return False
          upper1, _, lower1 = self._bbands(candles[:-1])
          upper2, _, lower2 = self._bbands(candles[:-2])
          upper0, _, lower0 = self._bbands(candles)
          if None in (upper0, lower0, upper1, lower1, upper2, lower2):
              return False
          w0 = upper0 - lower0
          w1 = upper1 - lower1
          w2 = upper2 - lower2
          mid = candles[-1].close
          return (w0 / mid >= self.bb_min_width_pct) and (w0 > w1 > w2)

      def _spread_ok(self, snapshot: MarketSnapshot) -> bool:
          if not hasattr(snapshot, "spread") or snapshot.spread is None:
              return True
          mid = snapshot.price if hasattr(snapshot, "price") else 0
          if mid == 0:
              return True
          return snapshot.spread / mid <= self.max_spread_pct

      def _consecutive_loss_cooldown_active(self) -> bool:
          return self._consec_losses >= self.consec_loss_cooldown

      def _daily_limit_reached(self, ts: datetime) -> bool:
          key = self._day_key(ts)
          return self._daily_trades.get(key, 0) >= self.max_daily_trades

      def _position_size(self, capital: float, risk_pct: float, stop_distance: float, price: float) -> float:
          if stop_distance <= 0 or price <= 0 or capital <= 0:
              return 0.0
          risk_amount = capital * risk_pct / 100.0
          units = risk_amount / stop_distance
          notional = units * price
          return notional

      # ------------------------------------------------------------------
      # Bar handler
      # ------------------------------------------------------------------

      def on_bar(self, snapshot: MarketSnapshot, candles: List) -> AITradeDecision:
          if not candles or len(candles) < max(self.ema_slow, self.bb_period, self.atr_period) + 5:
              return hold_decision(reason="insufficient_data")

          ts = getattr(candles[-1], "timestamp", datetime.now(timezone.utc))
          if isinstance(ts, str):
              ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

          if not self._is_active_session(ts):
              return hold_decision(reason="outside_active_session")

          if self._daily_limit_reached(ts):
              return hold_decision(reason="daily_trade_limit_reached")

          if self._consecutive_loss_cooldown_active():
              return hold_decision(reason="consecutive_loss_cooldown")

          if not self._spread_ok(snapshot):
              return hold_decision(reason="spread_too_wide")

          atr = self._atr(candles, self.atr_period)
          mid = candles[-1].close
          atr_pct = atr / mid if mid else 0

          if not self._is_volatility_ok(candles):
              return hold_decision(reason="volatility_out_of_range")

          swing_high = self._find_swing_high(candles)
          swing_low = self._find_swing_low(candles)
          current_close = candles[-1].close
          current_high = candles[-1].high
          current_low = candles[-1].low

          adx = self._adx(candles)
          if adx is None or adx < self.adx_min:
              return hold_decision(reason="adx_too_low")

          closes = [c.close for c in candles]
          rsi = self._rsi(closes, self.rsi_period)
          if rsi is None:
              return hold_decision(reason="rsi_unavailable")

          # Determine trend direction
          trend_long = self._trend_aligned(candles, "long")
          trend_short = self._trend_aligned(candles, "short")

          long_valid = trend_long and self.rsi_long_min <= rsi <= self.rsi_long_max
          short_valid = trend_short and self.rsi_short_min <= rsi <= self.rsi_short_max

          if not long_valid and not short_valid:
              return hold_decision(reason="no_trend_rsi_alignment")

          if not self._volume_spike(candles):
              return hold_decision(reason="no_volume_confirmation")

          if not self._bb_expanding(candles):
              return hold_decision(reason="bb_not_expanding")

          # Breakout detection with confirmation
          long_breakout = current_close > swing_high and current_high > swing_high
          short_breakout = current_close < swing_low and current_low < swing_low

          # Require closes beyond level
          if long_breakout:
              bars_beyond = sum(1 for c in candles[-self.breakout_confirm_bars :] if c.close > swing_high)
              if bars_beyond < self.breakout_confirm_bars:
                  long_breakout = False
          if short_breakout:
              bars_beyond = sum(1 for c in candles[-self.breakout_confirm_bars :] if c.close < swing_low)
              if bars_beyond < self.breakout_confirm_bars:
                  short_breakout = False

          # No immediate entry; wait for retest / pullback
          if long_breakout and long_valid:
              self._pending_setup = {
                  "direction": "long",
                  "level": swing_high,
                  "sl": max(swing_low, current_close - atr * self.stop_atr_mult),
                  "atr": atr,
                  "bar_index": len(candles) - 1,
              }
          elif short_breakout and short_valid:
              self._pending_setup = {
                  "direction": "short",
                  "level": swing_low,
                  "sl": min(swing_high, current_close + atr * self.stop_atr_mult),
                  "atr": atr,
                  "bar_index": len(candles) - 1,
              }

          # Execute retest entry
          if self._pending_setup:
              setup = self._pending_setup
              age = len(candles) - 1 - setup["bar_index"]
              if age > self.retest_bars_max:
                  self._pending_setup = None
                  return hold_decision(reason="retest_window_expired")

              direction = setup["direction"]
              sl = setup["sl"]
              atr_s = setup["atr"]

              if direction == "long" and current_low <= setup["level"] <= current_close:
                  entry_price = current_close
                  stop_distance = max(entry_price - sl, atr_s, mid * self.stop_floor_pct)
                  tp = entry_price + stop_distance * self.target_r
                  rr = (tp - entry_price) / stop_distance if stop_distance else 0
                  if rr < self.min_rr:
                      return hold_decision(reason="rr_below_minimum")
                  self._active_entry = {
                      "direction": "long",
                      "entry": entry_price,
                      "sl": entry_price - stop_distance,
                      "tp": tp,
                      "atr": atr_s,
                      "bars_held": 0,
                      "scaled_out": False,
                      "breakeven_active": False,
                      "day": self._day_key(ts),
                  }
                  self._pending_setup = None
                  return self._build_entry_decision("long", entry_price, stop_distance, snapshot)

              if direction == "short" and current_close <= setup["level"] <= current_high:
                  entry_price = current_close
                  stop_distance = max(sl - entry_price, atr_s, mid * self.stop_floor_pct)
                  tp = entry_price - stop_distance * self.target_r
                  rr = (entry_price - tp) / stop_distance if stop_distance else 0
                  if rr < self.min_rr:
                      return hold_decision(reason="rr_below_minimum")
                  self._active_entry = {
                      "direction": "short",
                      "entry": entry_price,
                      "sl": entry_price + stop_distance,
                      "tp": tp,
                      "atr": atr_s,
                      "bars_held": 0,
                      "scaled_out": False,
                      "breakeven_active": False,
                      "day": self._day_key(ts),
                  }
                  self._pending_setup = None
                  return self._build_entry_decision("short", entry_price, stop_distance, snapshot)

          return hold_decision(reason="no_valid_setup")

      def _build_entry_decision(self, direction: str, entry: float, stop_distance: float, snapshot: MarketSnapshot) -> AITradeDecision:
          capital = getattr(snapshot, "capital", 10000.0)
          size = self._position_size(capital, self.risk_per_trade_pct, stop_distance, entry)
          reason = (
              f"breakout_{direction}_"
              f"adx={self._adx([snapshot]):.1f}_"
              f"atr_pct={stop_distance/entry:.4f}"
          )
          return AITradeDecision(
              action="ENTER",
              side=direction.upper(),
              price=entry,
              size=size,
              stop_loss=entry - stop_distance if direction == "long" else entry + stop_distance,
              take_profit=entry + stop_distance * self.target_r if direction == "long" else entry - stop_distance * self.target_r,
              reason=reason,
          )

      # ------------------------------------------------------------------
      # Tick handler — manage open position
      # ------------------------------------------------------------------

      def on_tick(self, snapshot: MarketSnapshot, candles: List) -> AITradeDecision:
          if self._active_entry is None:
              return hold_decision(reason="no_position")

          pos = self._active_entry
          pos["bars_held"] = pos.get("bars_held", 0) + 1
          price = snapshot.price if hasattr(snapshot, "price") else candles[-1].close
          direction = pos["direction"]
          entry = pos["entry"]
          sl = pos["sl"]
          tp = pos["tp"]
          atr = pos["atr"]

          current_r = (price - entry) / (entry - sl) if direction == "long" else (entry - price) / (sl - entry)
          if current_r is None or not np.isfinite(current_r):
              current_r = 0.0

          # Breakeven floor
          if not pos["breakeven_active"] and current_r >= self.breakeven_arm_r:
              pos["sl"] = entry
              pos["breakeven_active"] = True
              sl = entry

          # Trailing stop
          if current_r >= self.trailing_arm_r:
              lookback = min(self.trailing_lookback, len(candles) - 1)
              if direction == "long":
                  trail = max(c.low for c in candles[-lookback:]) - self.trailing_atr_mult * atr
                  new_sl = max(sl, trail)
                  pos["sl"] = new_sl
              else:
                  trail = min(c.high for c in candles[-lookback:]) + self.trailing_atr_mult * atr
                  new_sl = min(sl, trail)
                  pos["sl"] = new_sl
              sl = pos["sl"]

          # Scale out partial at 1R
          if not pos["scaled_out"] and current_r >= self.scale_out_r:
              pos["scaled_out"] = True
              return scale_out_decision(
                  side=direction.upper(),
                  fraction=self.scale_out_fraction,
                  price=price,
                  reason=f"scale_out_at_{self.scale_out_r}R",
              )

          # Hard stop / TP
          if direction == "long":
              if price <= sl:
                  return self._close_trade(price, "stop_loss")
              if price >= tp:
                  return self._close_trade(price, "take_profit")
          else:
              if price >= sl:
                  return self._close_trade(price, "stop_loss")
              if price <= tp:
                  return self._close_trade(price, "take_profit")

          # Time stop
          if pos["bars_held"] >= self.time_stop_bars:
              return self._close_trade(price, "time_stop")

          return hold_decision(reason="holding_position")

      def _close_trade(self, price: float, reason: str) -> AITradeDecision:
          pos = self._active_entry
          direction = pos["direction"]
          entry = pos["entry"]
          pnl = price - entry if direction == "long" else entry - price

          if pnl < 0:
              self._consec_losses += 1
          else:
              self._consec_losses = 0

          day = pos.get("day")
          if day:
              self._daily_trades[day] = self._daily_trades.get(day, 0) + 1

          self._active_entry = None
          self._pending_setup = None

          return AITradeDecision(
              action="CLOSE",
              side=direction.upper(),
              price=price,
              reason=reason,
          )