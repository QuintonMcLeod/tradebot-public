from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class TradeResult:
    symbol: str
    closed_at: str
    pnl_pct: float
    is_win: bool
    tier: str  # e.g. "10%", "20%", "1%"
    capital_at_close: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TradeResult:
        return TradeResult(
            symbol=data["symbol"],
            closed_at=data["closed_at"],
            pnl_pct=float(data["pnl_pct"]),
            is_win=bool(data["is_win"]),
            tier=data.get("tier", "unknown"),
            capital_at_close=float(data.get("capital_at_close", 0.0))
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
            return {"total_trades": 0, "win_rate": 0.0}
        
        wins = sum(1 for r in self.results if r.is_win)
        total = len(self.results)
        return {
            "total_trades": total,
            "wins": wins,
            "win_rate": wins / total
        }
