from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class TradeResult:
    symbol: str
    closed_at: str
    pnl_pct: float
    pnl_usd: float
    is_win: bool
    tier: str  # e.g. "10%", "20%", "1%"
    capital_at_close: float
    opened_at: str | None = None         # ISO timestamp of entry
    duration_seconds: float | None = None # How long the trade was held
    strategy: str | None = None          # Which strategy opened this trade
    exit_reason: str | None = None       # Why the trade was closed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TradeResult:
        return TradeResult(
            symbol=data["symbol"],
            closed_at=data["closed_at"],
            pnl_pct=float(data["pnl_pct"]),
            pnl_usd=float(data.get("pnl_usd", 0.0)),
            is_win=bool(data["is_win"]),
            tier=data.get("tier", "unknown"),
            capital_at_close=float(data.get("capital_at_close", 0.0)),
            opened_at=data.get("opened_at"),
            duration_seconds=float(data["duration_seconds"]) if data.get("duration_seconds") is not None else None,
            strategy=data.get("strategy"),
            exit_reason=data.get("exit_reason")
        )

class TradeResultStore:
    def __init__(self, path: str, max_results: int = 100):
        self.path = Path(path)
        self.max_results = max_results
        self.results: List[TradeResult] = []
        self._ensure_directory()
        self._load()

    def _ensure_directory(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
                if isinstance(raw, list):
                    self.results = [TradeResult.from_dict(r) for r in raw]
        except Exception as e:
            logger.warning(f"Failed to load trade results from {self.path}: {e}")

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            payload = [r.to_dict() for r in self.results]
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            tmp.replace(self.path)
        except Exception as e:
            logger.error(f"Failed to save trade results: {e}")

    def add_result(self, result: TradeResult) -> None:
        self.results.append(result)
        # Keep only the last max_results
        if len(self.results) > self.max_results:
            self.results = self.results[-self.max_results:]
        self.save()

    def get_recent_results(self, limit: int = 10) -> List[TradeResult]:
        return self.results[-limit:]

    def get_stats(self) -> dict:
        if not self.results:
            return {"total_trades": 0, "win_rate": 0.0, "pnl_usd": 0.0}
        
        wins = sum(1 for r in self.results if r.is_win)
        total = len(self.results)
        total_pnl = sum(r.pnl_usd for r in self.results)
        return {
            "total_trades": total,
            "wins": wins,
            "win_rate": wins / total,
            "pnl_usd": total_pnl
        }

    def get_stats_for_timeframe(self, timeframe_code: str) -> dict:
        """
        Calculates stats for a given timeframe ('24h', 'week', 'month', 'year', 'all').
        """
        if not self.results:
            return {"total_trades": 0, "win_rate": 0.0, "pnl_usd": 0.0}

        now = datetime.now(timezone.utc)
        if timeframe_code == '24h':
            delta = timedelta(days=1)
        elif timeframe_code == 'week':
            delta = timedelta(days=7)
        elif timeframe_code == 'month':
            delta = timedelta(days=30)
        elif timeframe_code == 'year':
            delta = timedelta(days=365)
        else: # 'all'
            delta = None

        filtered = []
        for r in self.results:
            try:
                # closed_at is expected to be ISO format
                closed_dt = datetime.fromisoformat(r.closed_at.replace("Z", "+00:00"))
                if closed_dt.tzinfo is None:
                    closed_dt = closed_dt.replace(tzinfo=timezone.utc)
                
                if delta is None or (now - closed_dt) <= delta:
                    filtered.append(r)
            except Exception:
                # If we can't parse date, assume it's old and ignore if delta is set
                if delta is None:
                    filtered.append(r)

        if not filtered:
            return {"total_trades": 0, "win_rate": 0.0, "pnl_usd": 0.0}

        wins = sum(1 for r in filtered if r.is_win)
        total = len(filtered)
        total_pnl = sum(r.pnl_usd for r in filtered)
        return {
            "total_trades": total,
            "wins": wins,
            "win_rate": wins / total,
            "pnl_usd": total_pnl
        }
