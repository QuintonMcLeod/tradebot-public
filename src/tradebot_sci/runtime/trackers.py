from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

class StrikeTracker:
    """Tracks consecutive risk suppressions and guard blocks to skip symbols temporarily."""
    def __init__(
        self,
        max_consecutive: int,
        cooldown_cycles: int,
        guard_block_threshold: int,
        guard_block_cooldown: int,
    ) -> None:
        self.max_consecutive = max_consecutive
        self.cooldown_cycles = cooldown_cycles
        self.guard_block_threshold = guard_block_threshold
        self.guard_block_cooldown_cycles = guard_block_cooldown
        self.strikes: dict[str, int] = {}
        self.cooldowns: dict[str, int] = {}
        self.guard_block_streak: dict[str, int] = {}
        self.guard_block_cooldowns: dict[str, int] = {}
        self.cooldown_reasons: dict[str, str] = {}

    def advance_cycle(self) -> None:
        # Decrement cooldowns and remove expired ones
        self.cooldowns = {sym: count - 1 for sym, count in self.cooldowns.items() if count > 1}
        self.cooldown_reasons = {sym: reason for sym, reason in self.cooldown_reasons.items() if sym in self.cooldowns}
        self.guard_block_cooldowns = {sym: count - 1 for sym, count in self.guard_block_cooldowns.items() if count > 1}

    def is_skipped(self, symbol: str) -> bool:
        return self.cooldowns.get(symbol, 0) > 0

    def is_guard_skipped(self, symbol: str) -> bool:
        return self.guard_block_cooldowns.get(symbol, 0) > 0

    def guard_cooldown_remaining(self, symbol: str) -> int:
        return self.guard_block_cooldowns.get(symbol, 0)

    def record_risk_suppression(self, symbol: str) -> bool:
        if self.max_consecutive <= 0 or self.cooldown_cycles <= 0:
            return False
        current = self.strikes.get(symbol, 0) + 1
        self.strikes[symbol] = current
        if current >= self.max_consecutive:
            self._apply_cooldown(symbol, "risk_suppressed")
            self.strikes[symbol] = 0
            return True
        return False

    def record_guard_block(self, symbol: str) -> bool:
        if self.guard_block_threshold <= 0 or self.guard_block_cooldown_cycles <= 0:
            return False
        current = self.guard_block_streak.get(symbol, 0) + 1
        self.guard_block_streak[symbol] = current
        if current >= self.guard_block_threshold:
            self.guard_block_cooldowns[symbol] = self.guard_block_cooldown_cycles
            self.guard_block_streak[symbol] = 0
            return True
        return False

    def reset(self, symbol: str) -> None:
        self.strikes.pop(symbol, None)
        self.cooldowns.pop(symbol, None)
        self.guard_block_streak.pop(symbol, None)
        self.guard_block_cooldowns.pop(symbol, None)
        self.cooldown_reasons.pop(symbol, None)

    def cooldown_reason(self, symbol: str) -> str | None:
        return self.cooldown_reasons.get(symbol)

    def _apply_cooldown(self, symbol: str, reason: str | None) -> bool:
        if self.cooldown_cycles <= 0:
            self.cooldown_reasons.pop(symbol, None)
            return False
        self.cooldowns[symbol] = self.cooldown_cycles
        self.cooldown_reasons[symbol] = reason or "cooldown"
        return True

    def record_execution_success(self, symbol: str, reason: str | None = None) -> None:
        self.strikes.pop(symbol, None)
        self.guard_block_streak.pop(symbol, None)
        self.guard_block_cooldowns.pop(symbol, None)
        self._apply_cooldown(symbol, reason or "success")
