from __future__ import annotations
import logging
from typing import Optional, Dict
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)


class CryptoGridStrategy(BaseStrategy):
    """
    Virtual Grid Trading — Crypto-Optimized.
    
    Places virtual grid levels based on ATR and triggers market entries 
    when price crosses levels. Profits from ranging/choppy markets.
    Disabled during strong trends to avoid trading against momentum.
    
    ⚠️ Designed for crypto markets. May not perform well on forex or equities.
    """
    ASSET_TAG = "crypto"

    def __init__(self, grid_atr_multiplier=1.5, num_levels=5, 
                 trend_guard_threshold=0.5, **kwargs):
        super().__init__("crypto_grid")
        self.grid_atr_multiplier = float(kwargs.get('grid_atr_mult', grid_atr_multiplier))
        self.num_levels = int(kwargs.get('grid_levels', num_levels))
        self.trend_guard_threshold = float(kwargs.get('trend_guard_threshold', trend_guard_threshold))
        # Track grid state per symbol
        self._grids: Dict[str, dict] = {}

    def _build_grid(self, symbol: str, anchor_price: float, atr: float):
        """Build or refresh grid levels around anchor price."""
        interval = atr * self.grid_atr_multiplier
        levels = []
        for i in range(-self.num_levels, self.num_levels + 1):
            if i == 0:
                continue
            levels.append({
                "price": anchor_price + (i * interval),
                "type": "buy" if i < 0 else "sell",
                "level": i,
            })
        self._grids[symbol] = {
            "anchor": anchor_price,
            "interval": interval,
            "levels": levels,
            "atr": atr,
        }

    def _get_nearest_buy_level(self, symbol: str, price: float) -> Optional[dict]:
        """Find nearest buy level below current price."""
        grid = self._grids.get(symbol)
        if not grid:
            return None
        buys = [l for l in grid["levels"] if l["type"] == "buy" and price <= l["price"]]
        if buys:
            return max(buys, key=lambda l: l["price"])  # Closest from below
        return None

    def _get_nearest_sell_level(self, symbol: str, price: float) -> Optional[dict]:
        """Find nearest sell level above current price."""
        grid = self._grids.get(symbol)
        if not grid:
            return None
        sells = [l for l in grid["levels"] if l["type"] == "sell" and price >= l["price"]]
        if sells:
            return min(sells, key=lambda l: l["price"])  # Closest from above
        return None

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        closes = [c.close for c in candles]

        if len(closes) < 20:
            return None

        last_close = closes[-1]
        prev_close = closes[-2]
        symbol = snapshot.symbol
        atr = calculate_atr(candles, period=14) or (last_close * 0.002)

        # Trend guard: skip during strong trends
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength >= self.trend_guard_threshold:
            return None

        # Build/refresh grid if price has moved too far from anchor
        grid = self._grids.get(symbol)
        if not grid or abs(last_close - grid["anchor"]) > grid["interval"] * self.num_levels:
            self._build_grid(symbol, last_close, atr)
            return None  # Skip first bar after grid rebuild

        interval = grid["interval"]

        # Handle pyramiding
        if open_position:
            max_entries = UserConfig.MAX_PYRAMID_ENTRIES
            if open_position.get("pyramid_count", 0) >= max_entries:
                return None
            if open_position.get("bars_since_scale", 0) < 3:
                return None

            pos_dir = open_position.get("direction")
            entry_price = open_position.get("entry_price", last_close)

            # Grid scale-in: price crossed another grid level in same direction
            if pos_dir == "long":
                buy_level = self._get_nearest_buy_level(symbol, last_close)
                if buy_level and prev_close > buy_level["price"] >= last_close and last_close < entry_price:
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="range", action="scale_in",
                        entry_price=last_close,
                        stop_loss=open_position.get("stop_loss"),
                        take_profit=grid["anchor"],
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"Grid Scale-in Level {buy_level['level']}",
                        invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                        management_instructions="Grid trading pyramid.",
                        urgency="medium", notes="Crypto Grid pyramid"
                    )
            if pos_dir == "short":
                sell_level = self._get_nearest_sell_level(symbol, last_close)
                if sell_level and prev_close < sell_level["price"] <= last_close and last_close > entry_price:
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="range", action="scale_in",
                        entry_price=last_close,
                        stop_loss=open_position.get("stop_loss"),
                        take_profit=grid["anchor"],
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"Grid Scale-in Level {sell_level['level']}",
                        invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                        management_instructions="Grid trading pyramid.",
                        urgency="medium", notes="Crypto Grid pyramid"
                    )
            return None

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # --- Initial Entry ---
        # BUY: Price crossed down through a buy level (lower grid) (only when trend allows)
        buy_level = self._get_nearest_buy_level(symbol, last_close)
        if htf_dir in ("long", "neutral") and buy_level and prev_close > buy_level["price"] >= last_close:
            stop_loss = last_close - (interval * 2)
            take_profit = buy_level["price"] + interval  # Target: next grid level up

            score = 55 + abs(buy_level["level"]) * 3  # Deeper levels = higher score

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="range", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Grid Buy Level {buy_level['level']} ({buy_level['price']:.5f})",
                invalidation_conditions=f"Close below {stop_loss:.5f}",
                management_instructions=f"Target next grid level (+{interval:.5f}). Stop at 2x interval.",
                urgency="medium",
                notes="Crypto Virtual Grid Trading",
                score=min(score, 85), grade="B"
            )

        # SELL: Price crossed up through a sell level (upper grid) (only when trend allows)
        sell_level = self._get_nearest_sell_level(symbol, last_close)
        if htf_dir in ("short", "neutral") and sell_level and prev_close < sell_level["price"] <= last_close:
            stop_loss = last_close + (interval * 2)
            take_profit = sell_level["price"] - interval

            score = 55 + abs(sell_level["level"]) * 3

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="range", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Grid Sell Level {sell_level['level']} ({sell_level['price']:.5f})",
                invalidation_conditions=f"Close above {stop_loss:.5f}",
                management_instructions=f"Target next grid level (-{interval:.5f}). Stop at 2x interval.",
                urgency="medium",
                notes="Crypto Virtual Grid Trading",
                score=min(score, 85), grade="B"
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, **kwargs) -> Optional[AITradeDecision]:
        from tradebot_sci.strategy.decisions import close_position_decision

        closes = [c.close for c in snapshot.candles]
        if len(closes) < 5:
            return None

        last_close = closes[-1]
        symbol = snapshot.symbol
        grid = self._grids.get(symbol)

        if not grid:
            return None

        direction = open_position.get("direction")
        anchor = grid["anchor"]

        # Exit when price reverts to anchor (grid center)
        if direction == "long" and last_close >= anchor:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Grid Exit Long (Reverted to anchor {anchor:.5f})"
            )

        if direction == "short" and last_close <= anchor:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Grid Exit Short (Reverted to anchor {anchor:.5f})"
            )

        # Safety: exit if trend guard activates while in position
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength >= self.trend_guard_threshold:
            htf_dir = str(gates.get("htf_dir", "neutral")).lower()
            if (direction == "long" and htf_dir == "short") or \
               (direction == "short" and htf_dir == "long"):
                return close_position_decision(
                    snapshot.symbol, snapshot.timeframe,
                    f"Grid Exit (Strong {htf_dir} trend detected, strength={htf_strength:.2f})"
                )

        return None
