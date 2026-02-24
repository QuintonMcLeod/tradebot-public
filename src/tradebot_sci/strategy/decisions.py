from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field

Bias = Literal["long", "short", "neutral"]
Phase = Literal["trend", "indication", "correction", "continuation", "chop", "range", "management"]
Action = Literal[
    "enter_long",
    "enter_short",
    "scale_in",
    "add_to_position",
    "scale_out",
    "scale_out_leg",
    "close_position",
    "hold",
    "stand_aside",
    "flip_to_long",
    "flip_to_short",
]


class AITradeDecision(BaseModel):
    """Holds the AI's grand plan so your executor doesn't panic."""

    symbol: str
    timeframe: str
    bias: Bias
    phase: Phase
    action: Action
    entry_price: Optional[float] = None
    entry_zone: Optional[Tuple[float, float]] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    risk_per_trade_dollars: Optional[float] = Field(default=None, ge=0.0)
    max_position_size_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    time_in_force_sec: Optional[int] = None
    urgency: Literal["low", "medium", "high"] = "medium"
    structure_summary: str = ""
    invalidation_conditions: str = ""
    management_instructions: str = ""
    notes: str = ""
    emergency_exit: bool = False
    gates: Optional[dict] = None
    decision_reason_codes: Optional[list[str]] = None
    score: Optional[float] = None
    grade: Optional[str] = None

    def validate_and_fix_rr(self, min_rr: float = 0.4) -> "AITradeDecision":
        """Validates and fixes risk/reward ratio to meet minimum requirements.

        If the AI set a target that doesn't meet minimum RR, this recalculates
        the target to ensure proper risk/reward.

        Args:
            min_rr: Minimum risk/reward ratio (default 0.4)

        Returns:
            Self (for chaining) with corrected take_profit if needed
        """
        import logging
        logger = logging.getLogger(__name__)

        # Only validate entry actions with prices set
        if self.action not in {"enter_long", "enter_short", "add_to_position", "scale_in"}:
            return self
        if self.entry_price is None or self.stop_loss is None:
            return self

        # Calculate risk and current reward
        risk = abs(self.entry_price - self.stop_loss)
        if risk <= 0:
            return self

        # Determine direction
        is_long = self.action in {"enter_long", "add_to_position"} or self.bias == "long"

        # Calculate current RR
        current_reward = None
        current_rr = None
        if self.take_profit is not None:
            current_reward = abs(self.take_profit - self.entry_price)
            if current_reward > 0:
                current_rr = current_reward / risk

        # If RR is already good, no changes needed
        if current_rr is not None and current_rr >= min_rr:
            return self

        # Calculate minimum required target
        min_reward = risk * min_rr
        new_target = (
            self.entry_price + min_reward if is_long
            else self.entry_price - min_reward
        )

        # Log the correction
        if current_rr is not None:
            logger.warning(
                f"AI target validation: {self.symbol} RR too low ({current_rr:.2f} < {min_rr:.2f}). "
                f"Correcting TP from {self.take_profit:.4f} to {new_target:.4f} "
                f"(entry={self.entry_price:.4f}, sl={self.stop_loss:.4f}, risk={risk:.4f})"
            )
        else:
            logger.info(
                f"AI target validation: {self.symbol} setting minimum RR target {new_target:.4f} "
                f"(entry={self.entry_price:.4f}, sl={self.stop_loss:.4f}, min_rr={min_rr:.1f})"
            )

        # Return updated decision
        return self.model_copy(update={"take_profit": new_target})

    def summary(self) -> str:
        """Summarizes the idea so humans can nod knowingly."""
        gate_bits = ""
        if self.gates:
            gate_bits = f" gates={self.gates}"
        code_bits = ""
        if self.decision_reason_codes:
            code_bits = f" codes={self.decision_reason_codes}"
        reason = (self.structure_summary or "").strip() or (self.notes or "").strip()
        reason = " ".join(reason.split())
        if len(reason) > 180:
            reason = reason[:177].rstrip() + "…"
        reason_bits = f" reason={reason}" if reason else ""
        return (
            f"Decision: {self.symbol} {self.timeframe} | bias={self.bias} phase={self.phase} action={self.action} "
            f"entry={self.entry_price or self.entry_zone} sl={self.stop_loss} tp={self.take_profit} "
            f"risk%={self.risk_per_trade_pct} maxpos%={self.max_position_size_pct} "
            f"urgency={self.urgency}{gate_bits}{code_bits}{reason_bits}"
        )


def stand_aside_decision(symbol: str, timeframe: str, reason: str) -> AITradeDecision:
    """Creates a neutral stand-aside idea when the AI has a bad hair day."""
    return AITradeDecision(
        symbol=symbol,
        timeframe=timeframe,
        bias="neutral",
        phase="chop",
        action="stand_aside",
        entry_price=None,
        entry_zone=None,
        stop_loss=None,
        take_profit=None,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="low",
        structure_summary=reason,
        invalidation_conditions="N/A",
        management_instructions="Do nothing but watch.",
        notes=reason,
    )


def close_position_decision(symbol: str, timeframe: str, reason: str, *, emergency_exit: bool = False) -> AITradeDecision:
    """Creates a close-position decision without relying on the LLM."""
    urgency = "high" if emergency_exit else "medium"
    return AITradeDecision(
        symbol=symbol,
        timeframe=timeframe,
        bias="neutral",
        phase="chop",
        action="close_position",
        entry_price=None,
        entry_zone=None,
        stop_loss=None,
        take_profit=None,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency=urgency,
        structure_summary=reason,
        invalidation_conditions=reason,
        management_instructions="Flatten the position.",
        notes=reason,
        emergency_exit=emergency_exit,
    )


def scale_out_decision(symbol: str, timeframe: str, reason: str) -> AITradeDecision:
    """Creates a scale-out decision to reduce risk without flattening."""
    return AITradeDecision(
        symbol=symbol,
        timeframe=timeframe,
        bias="neutral",
        phase="correction",
        action="scale_out",
        entry_price=None,
        entry_zone=None,
        stop_loss=None,
        take_profit=None,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary=reason,
        invalidation_conditions="N/A",
        management_instructions="Scale out a portion of the position.",
        notes=reason,
        emergency_exit=False,
    )


def scale_out_leg_decision(symbol: str, timeframe: str, reason: str) -> AITradeDecision:
    """Creates a scale-out decision for a specific pyramid leg."""
    return AITradeDecision(
        symbol=symbol,
        timeframe=timeframe,
        bias="neutral",
        phase="correction",
        action="scale_out_leg",
        entry_price=None,
        entry_zone=None,
        stop_loss=None,
        take_profit=None,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="high",
        structure_summary=reason,
        invalidation_conditions="N/A",
        management_instructions="Extract the most recent pyramid leg.",
        notes=reason,
        emergency_exit=False,
    )


def hold_decision(
    symbol: str,
    timeframe: str,
    *,
    bias: Bias = "neutral",
    phase: Phase = "chop",
    reason: str = "Holding position.",
    stop_loss: Optional[float] = None,
) -> AITradeDecision:
    """Creates a hold decision without relying on the LLM."""
    return AITradeDecision(
        symbol=symbol,
        timeframe=timeframe,
        bias=bias,
        phase=phase,
        action="hold",
        entry_price=None,
        entry_zone=None,
        stop_loss=stop_loss,
        take_profit=None,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="low",
        structure_summary=reason,
        invalidation_conditions="N/A",
        management_instructions="Hold; manage via existing protection unless invalidation triggers.",
        notes=reason,
    )
