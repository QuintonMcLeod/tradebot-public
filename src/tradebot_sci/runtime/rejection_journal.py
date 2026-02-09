"""Rejection Audit Log — tracks every blocked trade for diagnostic visibility.

Every safety gate, friction check, and score rejection is recorded here so
the operator can audit *why* the bot stood aside on a given opportunity.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Dedicated tag so the GUI WebSocket handler can whitelist it
REJECTION_TAG = "[REJECTION]"


@dataclass
class RejectionEntry:
    timestamp: datetime
    symbol: str
    timeframe: str
    gate_name: str
    reason: str
    score: Optional[float] = None
    grade: Optional[str] = None


class RejectionJournal:
    """Lightweight in-memory ring buffer of rejected trade opportunities.

    Usage::

        from tradebot_sci.runtime.rejection_journal import rejection_journal
        rejection_journal.log("EUR_USD", "5m", "Greed Guard", "Daily goal met")
    """

    _instance: Optional["RejectionJournal"] = None

    def __init__(self, maxlen: int = 500):
        self._buffer: deque[RejectionEntry] = deque(maxlen=maxlen)
        self._gate_counts: dict[str, int] = {}

    @classmethod
    def get(cls) -> "RejectionJournal":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log(
        self,
        symbol: str,
        timeframe: str,
        gate_name: str,
        reason: str,
        *,
        score: Optional[float] = None,
        grade: Optional[str] = None,
    ) -> None:
        """Record a rejected trade opportunity."""
        entry = RejectionEntry(
            timestamp=datetime.now(),
            symbol=symbol,
            timeframe=timeframe,
            gate_name=gate_name,
            reason=reason,
            score=score,
            grade=grade,
        )
        self._buffer.append(entry)
        self._gate_counts[gate_name] = self._gate_counts.get(gate_name, 0) + 1

        # Emit to the structured log so it shows up in tradebot.log and GUI
        score_str = f" score={score:.1f}" if score is not None else ""
        grade_str = f" grade={grade}" if grade else ""
        logger.info(
            f"{REJECTION_TAG} {symbol} {timeframe} | "
            f"Gate={gate_name} | {reason}{score_str}{grade_str}"
        )

    def get_summary(self) -> dict[str, int]:
        """Returns rejection count per gate for the current session."""
        return dict(self._gate_counts)

    def get_recent(self, n: int = 20) -> list[RejectionEntry]:
        """Returns the N most recent rejections."""
        items = list(self._buffer)
        return items[-n:]

    @property
    def total_rejections(self) -> int:
        return sum(self._gate_counts.values())

    def reset(self) -> None:
        """Clears all recorded rejections (e.g. on new trading day)."""
        self._buffer.clear()
        self._gate_counts.clear()


# Module-level singleton for convenient imports
rejection_journal = RejectionJournal.get()
