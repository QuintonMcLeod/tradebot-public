"""ReplayProvider — replays exact candle observations recorded by CandleRecorder.

Instead of stepping through bar-close data, this provider feeds the backtester
exactly what the live bot saw at each decision point (including partial candles).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ReplayProvider:
    """Market data provider that replays recorded candle observations."""

    def __init__(self, symbol: str, start_date: str, end_date: str,
                 candle_history_dir: Optional[str] = None):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date

        if candle_history_dir:
            self._base = Path(candle_history_dir)
        else:
            from tradebot_sci.runtime.candle_recorder import _candle_history_dir
            self._base = _candle_history_dir()

        self._observations: list[dict] = []
        self._index = 0
        self._loaded = False

    def _load(self) -> None:
        """Load observations from disk."""
        if self._loaded:
            return

        sym_dir = self._base / self.symbol
        if not sym_dir.exists():
            logger.warning(f"[REPLAY] No recorded data for {self.symbol}")
            self._loaded = True
            return

        start_dt = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(self.end_date, "%Y-%m-%d").date()

        for f in sorted(sym_dir.iterdir()):
            if not f.suffix == ".jsonl":
                continue
            try:
                date_part = f.stem.split("_", 1)[1]
                file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
                if file_date < start_dt or file_date > end_dt:
                    continue
            except (IndexError, ValueError):
                continue

            with open(f, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._observations.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        self._observations.sort(key=lambda x: x.get("ts", ""))
        self._loaded = True
        logger.info(
            f"[REPLAY] Loaded {len(self._observations)} observations for "
            f"{self.symbol} ({self.start_date} → {self.end_date})"
        )

    @property
    def total_observations(self) -> int:
        self._load()
        return len(self._observations)

    @property
    def current_index(self) -> int:
        return self._index

    def has_next(self) -> bool:
        """Check if there are more observations to replay."""
        self._load()
        return self._index < len(self._observations)

    def get_next_observation(self) -> Optional[dict]:
        """Get the next recorded observation and advance the pointer."""
        self._load()
        if self._index >= len(self._observations):
            return None
        obs = self._observations[self._index]
        self._index += 1
        return obs

    def peek_observation(self) -> Optional[dict]:
        """Peek at the next observation without advancing."""
        self._load()
        if self._index >= len(self._observations):
            return None
        return self._observations[self._index]

    def reset(self) -> None:
        """Reset to the beginning."""
        self._index = 0

    def get_latest_snapshot(self, window: int = 200, settings=None):
        """Build a MarketSnapshot from the next recorded observation.

        This mimics the interface expected by the backtester's evaluation loop.
        """
        from tradebot_sci.market.models import Candle, MarketSnapshot
        from tradebot_sci.market.trend import TrendInfo, TrendDirection

        obs = self.get_next_observation()
        if obs is None:
            return None

        _neutral = TrendInfo(direction=TrendDirection.NEUTRAL, strength=0.0)

        def _dict_to_candle(d: dict) -> Candle:
            ts = d.get("t", "")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = datetime.utcnow()
            return Candle(
                timestamp=ts,
                open=float(d["o"]),
                high=float(d["h"]),
                low=float(d["l"]),
                close=float(d["c"]),
                volume=float(d.get("v", 0)),
            )

        ltf_candles = [_dict_to_candle(c) for c in obs.get("ltf", [])]
        htf_candles = [_dict_to_candle(c) for c in obs.get("htf", [])]

        return MarketSnapshot(
            symbol=obs.get("sym", self.symbol),
            timeframe=obs.get("tf", "5m"),
            candles=ltf_candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=obs.get("htf_tf"),
            ltf_timeframe=obs.get("ltf_tf"),
        )
