"""SyntheticMarketProvider — generates infinite, high-volatility procedural candles.

This provider generates massive sine waves and directional drift to artificially
create "market on fire" conditions, ensuring constant trigger events for strategies
like Rubberband Reaper and Forex Conductor.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from tradebot_sci.market.models import Candle, MarketSnapshot, Ticker, TrendState

logger = logging.getLogger(__name__)

class SyntheticMarketProvider:
    """Market data provider that generates endless procedural candles."""

    def __init__(
        self,
        symbols: List[str],
    ):
        self.symbols = [s.upper() for s in symbols]

        # Start the synthetic simulation "today"
        self.sim_start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        self.current_sim_time = self.sim_start_time
        
        # Keep track of history per symbol and timeframe
        self._history: Dict[str, Dict[str, List[Candle]]] = {s: {"5m": [], "15m": [], "1h": [], "4h": []} for s in self.symbols}
        
        self._cursor: int = 0
        self.REPLAY_WARMUP_CANDLES = 24  # 2 hours of 5m
        self._entries_this_cycle: int = 0
        self._max_entries_per_cycle: int = 5  # Allow multiple entries to test back-to-back

        # Stateful volatility params
        self._base_prices = {s: 1.0 + random.random() for s in self.symbols}
        self._trends = {s: 0.0 for s in self.symbols}
        
    def _generate_next_candle(self) -> None:
        """Procedurally generate the next 5-minute candle for all symbols."""
        # Fast, massive sine waves: 15-minute cycles (very fast) with large amplitude
        elapsed_min = (self.current_sim_time - self.sim_start_time).total_seconds() / 60.0
        wave = math.sin(elapsed_min / 15.0 * 2 * math.pi) * 0.0050
        
        for sym in self.symbols:
            # Change trend randomly to simulate breakouts
            if random.random() < 0.05:
                self._trends[sym] = (random.random() - 0.5) * 0.0010
            
            self._base_prices[sym] += self._trends[sym]
            
            # Realistic volatility: 5-10 pips per 5m candle
            volatility = 0.0005 + random.random() * 0.0005
            
            # The Open of THIS candle should match the Close of the LAST candle
            # (unless it's the very first candle)
            last_candles = self._history[sym]["5m"]
            if last_candles:
                open_p = last_candles[-1].close
            else:
                open_p = self._base_prices[sym]
                
            # Target close incorporates the sine wave and the trend drift
            target_price = self._base_prices[sym] + wave
            
            # Close price drifts towards target
            close_p = open_p + (target_price - open_p) * 0.5 + (random.random() - 0.5) * volatility
            
            # High and Low must strictly envelop Open and Close
            high_p = max(open_p, close_p) + (random.random() * volatility)
            low_p = min(open_p, close_p) - (random.random() * volatility)
            
            c = Candle(
                timestamp=self.current_sim_time,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=random.randint(500, 10000)
            )
            self._history[sym]["5m"].append(c)
            
            # Maintain sliding window of 200 candles to avoid memory leaks
            if len(self._history[sym]["5m"]) > 200:
                self._history[sym]["5m"] = self._history[sym]["5m"][-200:]
            
            self._update_htf(sym)

    def _update_htf(self, sym: str) -> None:
        """Update 15m, 1h, 4h candles based on the 5m history."""
        five_m = self._history[sym]["5m"]
        if not five_m:
            return

        def build_htf(bars_per_htf: int) -> List[Candle]:
            result = []
            for i in range(0, len(five_m), bars_per_htf):
                chunk = five_m[i:i + bars_per_htf]
                if not chunk:
                    break
                result.append(Candle(
                    timestamp=chunk[-1].timestamp,  # HTF timestamp is the end of the period
                    open=chunk[0].open,             # Open is the first 5m open
                    high=max(c.high for c in chunk),
                    low=min(c.low for c in chunk),
                    close=chunk[-1].close,          # Close is the last 5m close
                    volume=sum(getattr(c, 'volume', 0) for c in chunk),
                ))
            return result

        self._history[sym]["15m"] = build_htf(3)
        self._history[sym]["1h"] = build_htf(12)
        self._history[sym]["4h"] = build_htf(48)

    # ── Candle Progression ────────────────────────────────────────────

    def advance(self) -> None:
        """Reveal the next 5-minute candle. Called once per decision cycle."""
        self._cursor += 1
        self._entries_this_cycle = 0
        self.current_sim_time += timedelta(minutes=5)
        self._generate_next_candle()
        
        if self._cursor % 12 == 0 or self._cursor == 1:
            logger.info(
                "[SYNTHETIC] Advanced to candle %d (Sim Time: %s)%s",
                self._cursor,
                self.current_sim_time.strftime("%H:%M:%S"),
                " [WARMUP]" if self.in_warmup else " [FIRE MODE ACTIVE]",
            )

    @property
    def in_warmup(self) -> bool:
        """True if the replay is still in the warmup phase."""
        return self._cursor <= self.REPLAY_WARMUP_CANDLES

    def can_enter(self) -> bool:
        """Check if an entry is allowed this cycle."""
        if self.in_warmup:
            return False
        if self._entries_this_cycle >= self._max_entries_per_cycle:
            return False
        return True

    def record_entry(self) -> None:
        """Record that an entry was taken this cycle."""
        self._entries_this_cycle += 1

    @property
    def sim_time(self) -> Optional[datetime]:
        """The simulated timestamp of the current cursor position."""
        return self.current_sim_time

    # ── Provider Interface ────────────────────────────────────────────

    def get_latest_candles(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> List[Candle]:
        """Return the last ``limit`` candles."""
        sym = symbol.upper()
        if sym not in self._history:
            return []
        candles = self._history[sym].get(timeframe, self._history[sym].get("5m", []))
        return candles[-limit:] if len(candles) > limit else candles

    def get_ticker(self, symbol: str) -> Ticker | None:
        """Return a ticker from the most recent generated candle."""
        candles = self.get_latest_candles(symbol, "5m", limit=1)
        if not candles:
            return None

        c = candles[-1]
        mid = c.close
        # Synthetic spread logic: slightly wider to test resilience
        spread = mid * 0.00010 
        return Ticker(
            symbol=symbol,
            bid=mid - spread / 2,
            ask=mid + spread / 2,
            last=mid,
            volume_24h_quote_usd=None,
        )

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        """Build a snapshot from generated candles."""
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        _neutral = TrendState(direction="neutral", strength=0.0)

        htf_candles = self.get_latest_candles(symbol, "1h", limit=60)
        ltf_candles = self.get_latest_candles(symbol, "15m", limit=60)

        # ── SYNTHETIC REGIME OVERRIDE ───────────────────────────────────────
        # Standard indicators (ADX, EMA55) are too slow to classify the
        # mathematical chaos of synthetic candles. We must manually force
        # the htf_strength and market_regime so Conductor takes trades.
        
        sym = symbol.upper()
        current_trend = self._trends.get(sym, 0.0)
        
        # Max drift generated in _generate_next_candle is 0.0005. 
        # Lower the thresholds to reliably trigger trend states.
        if abs(current_trend) >= 0.0003:  # High directional drift
            direction = "long" if current_trend > 0 else "short"
            strength = 0.8  # Strong trend
        elif abs(current_trend) >= 0.0001:  # Transitional drift
            direction = "long" if current_trend > 0 else "short"
            strength = 0.4  # Moderate trend
        else:
            direction = "long" if current_trend > 0 else "short"
            strength = 0.8  # ALWAYS trending to force entries

        forced_trend = TrendState(direction=direction, strength=strength)

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=forced_trend,  # <-- Injected directly into the Snapshot
            trend_ltf=forced_trend,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe="1h",
            ltf_timeframe="15m",
        )

    def get_order_book(self, symbol: str, depth: int = 10):
        return None

    def close(self) -> None:
        pass

    # ── Status / UI ───────────────────────────────────────────────────

    @property
    def is_replay_complete(self) -> bool:
        """Synthetic mode is infinite."""
        return False

    def get_replay_info(self) -> dict:
        """Return current replay status for the UI."""
        return {
            "replay_active": True,
            "replay_date": self.current_sim_time.strftime("%Y-%m-%d"),
            "replay_day": "SYNTHETIC",
            "replay_source_date": "SYNTHETIC",
            "replay_candle": f"{self._cursor}/∞",
            "replay_progress": "🔥 ∞%",
            "replay_sim_time": self.current_sim_time.strftime("%H:%M:%S"),
            "replay_complete": False,
        }
