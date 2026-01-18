from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class SyntheticStopRecord:
    symbol: str
    side: str
    size: float
    stop_price: float
    tp_price: float | None
    parent_order_id: int | None
    tp_order_ids: list[int] | None
    status: str
    timestamp: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SyntheticStopRecord":
        return SyntheticStopRecord(
            symbol=data["symbol"],
            side=data["side"],
            size=float(data["size"]),
            stop_price=float(data["stop_price"]),
            tp_price=data.get("tp_price"),
            parent_order_id=data.get("parent_order_id"),
            tp_order_ids=data.get("tp_order_ids"),
            status=data.get("status", "ARMED"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


class SyntheticStopStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.records: dict[str, SyntheticStopRecord] = {}
        self._ensure_directory()
        self._load()

    def _ensure_directory(self) -> None:
        dir_path = self.path.parent
        dir_path.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception as e:
            logger.warning(f"Failed to load synthetic stop store from {self.path}: {e}")
            return
        if isinstance(raw, dict):
            items = raw.values()
        elif isinstance(raw, list):
            items = raw
        else:
            return
        for entry in items:
            record = SyntheticStopRecord.from_dict(entry)
            self.records[record.symbol] = record

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = [record.to_dict() for record in self.records.values()]
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(self.path)

    def upsert(self, record: SyntheticStopRecord) -> None:
        self.records[record.symbol] = record
        self.save()

    def remove(self, symbol: str) -> None:
        if symbol in self.records:
            self.records.pop(symbol, None)
            self.save()

    def items(self) -> Iterable[SyntheticStopRecord]:
        return list(self.records.values())
