from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The epoch stamped on every result row this code writes.  It is bumped by hand
# when a defect that poisoned the forward paper record is repaired, so a reader
# can separate rows written by the repaired code from rows written by the broken
# one.  A row found on disk with no epoch at all was written before the first
# stamp existed, which is what LEGACY_RECORD_EPOCH records.
RECORD_EPOCH = "post-replay-fix"
LEGACY_RECORD_EPOCH = "pre-replay-fix"


def _parse_iso(value: str) -> datetime:
    """Parse an ISO timestamp, treating a missing offset as UTC."""
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    side: str | None = None              # Position direction: "long" or "short"
    spread_cost: float | None = None     # Estimated round-trip spread cost in USD
    mfe_usd: float | None = None         # Maximum Favorable Excursion (highest floating profit)
    mae_usd: float | None = None         # Maximum Adverse Excursion (lowest floating profit/drawdown)
    trade_id: str | None = None          # Exchange trade/order ID
    size: float | None = None            # Position size/units
    entry_price: float | None = None     # Average entry price
    exit_price: float | None = None      # Average exit price
    initial_stop: float | None = None    # Stop at entry, for R-multiple analysis
    risk_usd: float | None = None        # Initial risk in USD (entry to stop)
    mfe_r: float | None = None           # Peak favorable excursion in R
    pnl_r: float | None = None           # Realised result in R
    # Excursions measured NET of the modelled round trip. MFE/MAE are mid-price
    # excursions taken from the entry fill and do not include the cost of getting
    # out, which made the dashboard flatter trades: 43% of live paper trades went
    # positive and closed negative, with a median MFE of $10.99 against a realised
    # -$6.90 and $14.36 of round-trip cost. These fields answer "what could this
    # trade actually have captured", which is the number worth showing.
    mfe_net_usd: float | None = None     # MFE less the round-trip cost
    mae_net_usd: float | None = None     # MAE less the round-trip cost
    mfe_net_r: float | None = None       # MFE net, in R
    mae_net_r: float | None = None       # MAE net, in R
    # How long the trade really took, measured from the wall clock, as against
    # duration_seconds, which is the hold the strategy itself saw.  In replay the
    # two diverge by orders of magnitude: the cursor is advanced one candle per
    # decision cycle, so a 48-bar hold can elapse inside 20 milliseconds of real
    # time.  Recording only the simulated figure hid that, and a position
    # force-closed in the same real second books no price change and therefore a
    # loss equal to its costs.
    wall_duration_seconds: float | None = None
    # Which build wrote this row.  Rows recovered from before the stamp exist
    # are read back as LEGACY_RECORD_EPOCH rather than being silently adopted
    # into the clean record.
    record_epoch: str = RECORD_EPOCH

    def __post_init__(self):
        """Derive the net-of-cost excursions and the real hold.

        Centralised here rather than at each of the seven places a TradeResult is
        constructed, so no path can record a flattering MFE by omission.
        """
        cost = self.spread_cost or 0.0
        if self.mfe_usd is not None:
            if self.mfe_net_usd is None:
                self.mfe_net_usd = self.mfe_usd - cost
            if self.risk_usd and self.mfe_net_r is None:
                self.mfe_net_r = self.mfe_net_usd / self.risk_usd
        if self.mae_usd is not None:
            if self.mae_net_usd is None:
                self.mae_net_usd = self.mae_usd - cost
            if self.risk_usd and self.mae_net_r is None:
                self.mae_net_r = self.mae_net_usd / self.risk_usd
        if self.wall_duration_seconds is None and self.opened_at and self.closed_at:
            try:
                elapsed = (_parse_iso(self.closed_at) - _parse_iso(self.opened_at)).total_seconds()
                if elapsed >= 0:
                    self.wall_duration_seconds = elapsed
            except (ValueError, TypeError):
                pass

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        # ── Compatibility aliases ─────────────────────────────────────────
        # Conductor reads t.get("exit_time") to identify closed trades.
        # Engine SAR reads t.get("pnl") / t.get("pnl_usd") and t.get("side").
        # TradeResult uses "closed_at"/"opened_at" — add aliases here so
        # the engine/conductor loss-detection logic works without code churn.
        d.setdefault("exit_time",  d.get("closed_at"))
        d.setdefault("entry_time", d.get("opened_at"))
        d.setdefault("pnl",        d.get("pnl_usd", 0.0))
        d.setdefault("strategy_name", d.get("strategy"))
        return d


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
            exit_reason=data.get("exit_reason"),
            side=data.get("side"),
            spread_cost=float(data["spread_cost"]) if data.get("spread_cost") is not None else None,
            mfe_usd=float(data["mfe_usd"]) if data.get("mfe_usd") is not None else None,
            mae_usd=float(data["mae_usd"]) if data.get("mae_usd") is not None else None,
            trade_id=data.get("trade_id"),
            size=float(data["size"]) if data.get("size") is not None else None,
            entry_price=float(data["entry_price"]) if data.get("entry_price") is not None else None,
            exit_price=float(data["exit_price"]) if data.get("exit_price") is not None else None,
            initial_stop=float(data["initial_stop"]) if data.get("initial_stop") is not None else None,
            risk_usd=float(data["risk_usd"]) if data.get("risk_usd") is not None else None,
            mfe_net_usd=float(data["mfe_net_usd"]) if data.get("mfe_net_usd") is not None else None,
            mae_net_usd=float(data["mae_net_usd"]) if data.get("mae_net_usd") is not None else None,
            wall_duration_seconds=float(data["wall_duration_seconds"]) if data.get("wall_duration_seconds") is not None else None,
            record_epoch=data.get("record_epoch", LEGACY_RECORD_EPOCH),
        )

class TradeResultStore:
    def __init__(self, path: str, max_results: int = 10000, skip_save: bool = False):
        self.path = Path(path)
        self.max_results = max_results
        self.results: List[TradeResult] = []
        self._skip_save = skip_save
        if not skip_save:
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
        if not self._skip_save:
            self.save()

    def clear(self) -> None:
        """Clear all stored trade results."""
        self.results = []
        if not self._skip_save:
            self.save()

    def get_recent_results(self, limit: int = 10) -> List[TradeResult]:
        return self.results[-limit:]

    def get_stats(self) -> dict:
        if not self.results:
            return {"total_trades": 0, "win_rate": 0.0, "pnl_usd": 0.0, "avg_mfe_usd": 0.0, "avg_mae_usd": 0.0, "max_mae_usd": 0.0}
        
        wins = sum(1 for r in self.results if r.is_win)
        total = len(self.results)
        total_pnl = sum(r.pnl_usd for r in self.results)
        
        mfe_values = [r.mfe_usd for r in self.results if getattr(r, 'mfe_usd', None) is not None]
        mae_values = [r.mae_usd for r in self.results if getattr(r, 'mae_usd', None) is not None]
        avg_mfe = sum(mfe_values) / len(mfe_values) if mfe_values else 0.0
        avg_mae = sum(mae_values) / len(mae_values) if mae_values else 0.0
        max_mae = min(mae_values) if mae_values else 0.0
        
        return {
            "total_trades": total,
            "wins": wins,
            "win_rate": wins / total,
            "pnl_usd": total_pnl,
            "avg_mfe_usd": avg_mfe,
            "avg_mae_usd": avg_mae,
            "max_mae_usd": max_mae
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
            return {"total_trades": 0, "win_rate": 0.0, "pnl_usd": 0.0, "avg_mfe_usd": 0.0, "avg_mae_usd": 0.0, "max_mae_usd": 0.0}

        wins = sum(1 for r in filtered if r.is_win)
        total = len(filtered)
        total_pnl = sum(r.pnl_usd for r in filtered)
        
        mfe_values = [r.mfe_usd for r in filtered if getattr(r, 'mfe_usd', None) is not None]
        mae_values = [r.mae_usd for r in filtered if getattr(r, 'mae_usd', None) is not None]
        avg_mfe = sum(mfe_values) / len(mfe_values) if mfe_values else 0.0
        avg_mae = sum(mae_values) / len(mae_values) if mae_values else 0.0
        max_mae = min(mae_values) if mae_values else 0.0

        return {
            "total_trades": total,
            "wins": wins,
            "win_rate": wins / total,
            "pnl_usd": total_pnl,
            "avg_mfe_usd": avg_mfe,
            "avg_mae_usd": avg_mae,
            "max_mae_usd": max_mae
        }
