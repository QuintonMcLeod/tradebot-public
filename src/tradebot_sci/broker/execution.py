from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(Enum):
    EXECUTED = "executed"
    STAND_ASIDE = "stand_aside"
    RISK_SUPPRESSED = "risk_suppressed"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    UNSUPPORTED_SYMBOL_CONFIG = "unsupported_symbol_config"
    ERROR = "error"
    EXIT_SIGNAL = "exit_signal"


@dataclass
class ExecutionResult:
    status: ExecutionStatus
    symbol: str
    reason: str = ""


class ExecutionOutcomeType(Enum):
    SUCCESS_SUBMITTED = "success_submitted"
    BLOCKED_GUARD = "blocked_guard"
    BLOCKED_PDT = "blocked_pdt"
    BLOCKED_PDT_EXIT = "blocked_pdt_exit"
    BLOCKED_EXISTING = "blocked_existing"
    BLOCKED_MIN_HOLD = "blocked_min_hold"
    BLOCKED_INSUFFICIENT_EQUITY = "blocked_insufficient_equity"
    BLOCKED_SYMBOL_NOT_ALLOWED = "blocked_symbol_not_allowed"
    SKIPPED = "skipped"
    ERROR = "error"
    FAILED_OTHER = "failed_other"


@dataclass
class ExecutionOutcome:
    status: ExecutionOutcomeType
    symbol: str
    reason: str = ""
    detail: str | None = None
    order_ids: list[int] | None = None
