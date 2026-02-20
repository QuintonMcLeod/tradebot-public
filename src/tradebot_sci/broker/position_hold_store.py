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

    def upsert(self, symbol: str, opened_at: datetime, stop_loss: float | None = None, entry_price: float | None = None, take_profit: float | None = None, size: float | None = None, strategy: str | None = None) -> None:
        record = PositionHoldRecord(
            symbol=symbol.upper(), 
            opened_at=opened_at.astimezone(timezone.utc).isoformat(),
            stop_loss=stop_loss,
            entry_price=entry_price,
            take_profit=take_profit,
            size=size,
            strategy=strategy,
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
            # Record exit for re-entry cooldown
            self._record_exit(key, strategy)

    def _record_exit(self, symbol: str, strategy: str | None = None) -> None:
        """Record an exit timestamp for re-entry cooldown tracking."""
        import time
        self._exit_cooldowns[symbol.upper()] = time.time()
        if strategy:
            self._exit_strategies[symbol.upper()] = strategy
        logger.info(f"[COOLDOWN] Recorded exit for {symbol}, cooldown={self.REENTRY_COOLDOWN:.0f}s, strategy={strategy or 'unknown'}")

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
        # Filter out phantom positions (size=0.0)
        if record and (record.size is None or record.size <= 0):
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

