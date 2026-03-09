"""CandleRecorder — saves every MarketSnapshot the live bot evaluates.

Enables 1:1 replay backtesting by recording exactly what the bot saw
(including partial candles) at each decision point.

Storage: ~/.config/tradebot-sci/data/candle_history/{symbol}/
Format:  One JSONL file per day per symbol (e.g. EURUSD_2026-03-02.jsonl)
Pruning: Files older than 6 months are auto-deleted on startup.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# How many trailing candles to store per snapshot (needs 200 for indicator warmup)
_TAIL_CANDLES = 200
_PRUNE_DAYS = 180  # 6 months


def _config_dir() -> Path:
    """Resolve the user config directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "tradebot-sci"
    return Path.home() / ".config" / "tradebot-sci"


def _candle_history_dir() -> Path:
    return _config_dir() / "data" / "candle_history"


def _candle_to_dict(c) -> dict:
    return {
        "t": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
        "o": float(c.open),
        "h": float(c.high),
        "l": float(c.low),
        "c": float(c.close),
        "v": float(c.volume),
    }


class CandleRecorder:
    """Records MarketSnapshot observations to disk for replay backtesting."""

    def __init__(self, enabled: bool = True, tail: int = _TAIL_CANDLES):
        self._enabled = enabled
        self._tail = tail
        self._base_dir = _candle_history_dir()
        self._file_handles: dict[str, object] = {}  # symbol_date → file handle
        self._last_prune: float = 0
        if self._enabled:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[RECORDER] Candle recording enabled → {self._base_dir}")
            self._prune_old_files()

    def record(self, snapshot) -> None:
        """Record a single MarketSnapshot observation."""
        if not self._enabled or snapshot is None:
            return

        try:
            symbol = snapshot.symbol
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")

            # Build compact observation record
            ltf = snapshot.ltf_candles or snapshot.candles or []
            htf = snapshot.htf_candles or []

            record = {
                "ts": now.isoformat(),
                "sym": symbol,
                "tf": snapshot.timeframe,
                "htf_tf": getattr(snapshot, "htf_timeframe", None),
                "ltf_tf": getattr(snapshot, "ltf_timeframe", None),
                "ltf": [_candle_to_dict(c) for c in ltf[-self._tail:]],
                "htf": [_candle_to_dict(c) for c in htf[-self._tail:]],
            }

            # Write as JSONL (one JSON object per line)
            sym_dir = self._base_dir / symbol
            sym_dir.mkdir(exist_ok=True)
            file_path = sym_dir / f"{symbol}_{date_str}.jsonl"

            with open(file_path, "a") as f:
                f.write(json.dumps(record, separators=(",", ":")) + "\n")

        except Exception as e:
            logger.debug(f"[RECORDER] Write error: {e}")

        # Periodic prune check (once per hour)
        if time.time() - self._last_prune > 3600:
            self._prune_old_files()

    def _prune_old_files(self) -> None:
        """Delete recording files older than 6 months."""
        self._last_prune = time.time()
        cutoff = datetime.now(timezone.utc) - timedelta(days=_PRUNE_DAYS)
        pruned = 0
        try:
            for sym_dir in self._base_dir.iterdir():
                if not sym_dir.is_dir():
                    continue
                for f in sym_dir.iterdir():
                    if not f.suffix == ".jsonl":
                        continue
                    # Parse date from filename: EURUSD_2026-03-02.jsonl
                    try:
                        date_part = f.stem.split("_", 1)[1]
                        file_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if file_date < cutoff:
                            f.unlink()
                            pruned += 1
                    except (IndexError, ValueError):
                        continue
            if pruned:
                logger.info(f"[RECORDER] Pruned {pruned} files older than {_PRUNE_DAYS} days")
        except Exception as e:
            logger.debug(f"[RECORDER] Prune error: {e}")

    def get_available_symbols(self) -> list[str]:
        """Return symbols that have recorded data."""
        if not self._base_dir.exists():
            return []
        return sorted([d.name for d in self._base_dir.iterdir() if d.is_dir()])

    def get_date_range(self, symbol: str) -> tuple[Optional[str], Optional[str]]:
        """Return (earliest_date, latest_date) for a symbol's recordings."""
        sym_dir = self._base_dir / symbol
        if not sym_dir.exists():
            return None, None
        dates = []
        for f in sym_dir.iterdir():
            if f.suffix == ".jsonl":
                try:
                    date_part = f.stem.split("_", 1)[1]
                    dates.append(date_part)
                except (IndexError, ValueError):
                    continue
        if not dates:
            return None, None
        dates.sort()
        return dates[0], dates[-1]

    def load_observations(self, symbol: str, start_date: str, end_date: str) -> list[dict]:
        """Load all recorded observations for a symbol within a date range.

        Returns list of observation dicts sorted by timestamp.
        """
        sym_dir = self._base_dir / symbol
        if not sym_dir.exists():
            return []

        observations = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

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
                        observations.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        observations.sort(key=lambda x: x.get("ts", ""))
        return observations


# Singleton instance (created lazily)
_recorder: Optional[CandleRecorder] = None


def get_recorder(enabled: bool = True) -> CandleRecorder:
    """Get or create the singleton CandleRecorder."""
    global _recorder
    if _recorder is None:
        _recorder = CandleRecorder(enabled=enabled)
    return _recorder
