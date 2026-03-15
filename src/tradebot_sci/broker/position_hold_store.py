from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class PositionHoldRecord:
    symbol: str
    opened_at: str
    stop_loss: float | None = None
    entry_price: float | None = None
    take_profit: float | None = None
    size: float | None = None
    strategy: str | None = None
    original_entry_price: float | None = None
    initial_risk: float | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionHoldRecord":
        return PositionHoldRecord(
            symbol=data["symbol"],
            opened_at=data["opened_at"],
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") is not None else None,
            entry_price=float(data["entry_price"]) if data.get("entry_price") is not None else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") is not None else None,
            size=float(data["size"]) if data.get("size") is not None else None,
            strategy=data.get("strategy"),
            original_entry_price=float(data["original_entry_price"]) if data.get("original_entry_price") is not None else None,
            initial_risk=float(data["initial_risk"]) if data.get("initial_risk") is not None else None,
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


class PositionHoldStore:
    REENTRY_COOLDOWN = float(os.getenv("REENTRY_COOLDOWN_SECONDS", "300"))  # 5 min default

    def __init__(self, path: str):
        self.path = Path(path)
        self.records: Dict[str, PositionHoldRecord] = {}
        # In-memory exit cooldown tracking (not persisted — transient per session)
        self._exit_cooldowns: Dict[str, float] = {}       # symbol -> timestamp of last exit
        self._exit_strategies: Dict[str, str] = {}         # symbol -> strategy used at last exit
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
        except Exception as e:
            logger.warning(f"Failed to load position hold store from {self.path}: {e}")
            return
        if not isinstance(raw, list):
            return
        for entry in raw:
            try:
                record = PositionHoldRecord.from_dict(entry)
            except Exception as e:
                logger.warning(f"Failed to parse position hold record: {e}")
                continue
            self.records[record.symbol.upper()] = record

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = [record.to_dict() for record in self.records.values()]
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(self.path)

    def upsert(self, symbol: str, opened_at: datetime, stop_loss: float | None = None, entry_price: float | None = None, take_profit: float | None = None, size: float | None = None, strategy: str | None = None, original_entry_price: float | None = None, initial_risk: float | None = None) -> None:
        key = symbol.upper()
        
        # Merging Update: Retain existing fields if not explicitly overwritten (crucial for pyramiding stability)
        existing = self.records.get(key)
        
        if existing:
            # We don't overwrite opened_at unless we really want to, but standard behavior was to overwrite.
            existing.opened_at = opened_at.astimezone(timezone.utc).isoformat()
            if stop_loss is not None: existing.stop_loss = stop_loss
            if entry_price is not None: existing.entry_price = entry_price
            if take_profit is not None: existing.take_profit = take_profit
            if size is not None: existing.size = size
            if strategy is not None: existing.strategy = strategy
            if original_entry_price is not None: existing.original_entry_price = original_entry_price
            if initial_risk is not None: existing.initial_risk = initial_risk
            record = existing
        else:
            record = PositionHoldRecord(
                symbol=key, 
                opened_at=opened_at.astimezone(timezone.utc).isoformat(),
                stop_loss=stop_loss,
                entry_price=entry_price,
                take_profit=take_profit,
                size=size,
                strategy=strategy,
                original_entry_price=original_entry_price,
                initial_risk=initial_risk,
            )
            
        self.records[record.symbol] = record
        self.save()

    def remove(self, symbol: str) -> None:
        key = symbol.upper()
        if key in self.records:
            # Capture strategy before removing for exit tracking
            strategy = self.records[key].strategy
            self.records.pop(key, None)
            self.save()
            # Record exit ONLY if not already recorded via record_exit_with_result
            if not hasattr(self, '_exit_result_recorded'):
                self._exit_result_recorded = set()
            if key not in self._exit_result_recorded:
                self._record_exit(key, strategy)
            else:
                self._exit_result_recorded.discard(key)

    def _record_exit(self, symbol: str, strategy: str | None = None, is_win: bool = False) -> None:
        """Record an exit timestamp for re-entry cooldown tracking.
        
        Winning exits SKIP the cooldown so the bot can immediately
        re-enter on oscillation dips (profit at peak → re-enter at dip → repeat).
        Losing exits get the full cooldown to prevent death spirals.
        """
        import time
        if is_win:
            # Clear any existing cooldown on a win — allow immediate re-entry
            self._exit_cooldowns.pop(symbol.upper(), None)
            self._exit_strategies.pop(symbol.upper(), None)
            logger.info(f"[COOLDOWN] Exit recorded for {symbol} (WIN) — cooldown SKIPPED, immediate re-entry allowed")
            return
        self._exit_cooldowns[symbol.upper()] = time.time()
        if strategy:
            self._exit_strategies[symbol.upper()] = strategy
        logger.info(f"[COOLDOWN] Recorded exit for {symbol}, cooldown={self.REENTRY_COOLDOWN:.0f}s, strategy={strategy or 'unknown'}")

    def record_exit_with_result(self, symbol: str, is_win: bool, strategy: str | None = None) -> None:
        """External API: record exit with win/loss status for cooldown gating."""
        if not hasattr(self, '_exit_result_recorded'):
            self._exit_result_recorded = set()
        self._exit_result_recorded.add(symbol.upper())
        self._record_exit(symbol, strategy=strategy, is_win=is_win)

    def is_in_cooldown(self, symbol: str) -> tuple[bool, float]:
        """Check if symbol is in re-entry cooldown. Returns (is_blocked, remaining_seconds)."""
        import time
        key = symbol.upper()
        if key not in self._exit_cooldowns:
            return False, 0.0
        elapsed = time.time() - self._exit_cooldowns[key]
        remaining = self.REENTRY_COOLDOWN - elapsed
        if remaining <= 0:
            del self._exit_cooldowns[key]
            self._exit_strategies.pop(key, None)
            return False, 0.0
        return True, remaining

    def get_exit_strategy(self, symbol: str) -> str | None:
        """Get the strategy used for the most recent closed position on this symbol."""
        return self._exit_strategies.get(symbol.upper())

    def get(self, symbol: str) -> PositionHoldRecord | None:
        record = self.records.get(symbol.upper())
        # Filter out phantom positions (abs(size) == 0.0), but allow None for metadata-only records
        if record and record.size is not None and abs(record.size) < 1e-8:
            return None
        return record

    def load_all(self) -> Dict[str, PositionHoldRecord]:
        """Return all records (required by ccxt_broker)."""
        return self.records

    def items(self) -> Iterable[PositionHoldRecord]:
        return list(self.records.values())

    def __contains__(self, symbol: str) -> bool:
        return symbol.upper() in self.records

    def __getitem__(self, symbol: str) -> PositionHoldRecord:
        return self.records[symbol.upper()]

