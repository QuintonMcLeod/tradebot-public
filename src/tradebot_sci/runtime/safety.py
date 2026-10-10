from __future__ import annotations

import logging
import math
from typing import Optional

from tradebot_sci.config.models import Settings
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision

logger = logging.getLogger(__name__)

ALLOWED_BIAS = {"long", "short", "neutral"}
# Mirrors AITradeDecision's Phase literal, which is the contract the response schema
# and the prompt's JSON contract both narrow to the same ICC labels. The old set
# dropped "indication" (and the internal "range"/"management" labels mechanical
# strategies emit), so a correctly labelled decision was silently downgraded to
# stand_aside. Anything outside this set is not a phase the model can represent and
# is still rejected.
ALLOWED_PHASE = {"trend", "indication", "correction", "continuation", "chop", "range", "management"}
ALLOWED_ACTION = {
    "enter_long",
    "enter_short",
    "scale_in",
    "add_to_position",
    "scale_out",
    "close_position",
    "hold",
    "stand_aside",
    "flip_to_long",
    "flip_to_short",
}


def validate_decision(
    decision: AITradeDecision,
    settings: Optional[Settings] = None,
    execution_capabilities: Optional[dict] = None,
) -> AITradeDecision:
    """Sanity-checks the AI so it doesn't YOLO your account into oblivion."""
    max_sim_risk = 1.0
    if settings and hasattr(settings, "runtime"):
        # Use configured cap or default to 100% (no cap)
        max_sim_risk = float(getattr(settings.runtime, "simulation_risk_cap", 1.0) or 1.0)

    if decision.bias not in ALLOWED_BIAS:
        return _downgrade(decision, "Bias invalid")
    if decision.phase not in ALLOWED_PHASE:
        return _downgrade(decision, "Phase invalid")
    if decision.action not in ALLOWED_ACTION:
        return _downgrade(decision, "Action invalid")

    # Non-finite numbers must be caught before any comparison below: every check
    # against NaN is False, so a NaN stop or target slips through the long/short
    # pricing tests and the risk caps untouched and reaches the executor.
    for value, label in [
        (decision.entry_price, "Entry price"),
        (decision.stop_loss, "Stop loss"),
        (decision.take_profit, "Take profit"),
        (decision.risk_per_trade_pct, "Risk per trade"),
        (decision.max_position_size_pct, "Max position size"),
    ]:
        if value is not None and not math.isfinite(value):
            return _downgrade(decision, f"{label} not finite")

    if decision.entry_zone:
        if not all(math.isfinite(level) for level in decision.entry_zone):
            return _downgrade(decision, "Entry zone not finite")

    if decision.action in {"enter_long", "enter_short", "scale_in", "add_to_position", "flip_to_long", "flip_to_short"}:
        if decision.entry_price is None or decision.stop_loss is None:
            return _downgrade(decision, "Missing required entry/stop fields")
            
        is_long = decision.action in {"enter_long", "flip_to_long"} or (
            decision.action in {"scale_in", "add_to_position"} and decision.bias == "long"
        )
        is_short = decision.action in {"enter_short", "flip_to_short"} or (
            decision.action in {"scale_in", "add_to_position"} and decision.bias == "short"
        )

        if is_long:
            if decision.stop_loss >= decision.entry_price:
                return _downgrade(decision, f"Long pricing invalid: stop={decision.stop_loss} >= entry={decision.entry_price}")
            if decision.take_profit is not None and decision.take_profit <= decision.entry_price:
                return _downgrade(decision, f"Long pricing invalid: target={decision.take_profit} <= entry={decision.entry_price}")
                
        if is_short:
            if decision.stop_loss <= decision.entry_price:
                return _downgrade(decision, f"Short pricing invalid: stop={decision.stop_loss} <= entry={decision.entry_price}")
            if decision.take_profit is not None and decision.take_profit >= decision.entry_price:
                return _downgrade(decision, f"Short pricing invalid: target={decision.take_profit} >= entry={decision.entry_price}")

    caps = execution_capabilities or {}
    if decision.action in {"flip_to_long", "flip_to_short"}:
        flip_allowed = False
        # hasattr, not just a None check: a caller may hand us an AI-only settings
        # object with no `.runtime` section, and reaching through it would raise
        # AttributeError instead of returning a verdict. Same guard as max_sim_risk above.
        if settings is not None and hasattr(settings, "runtime"):
            flip_allowed = bool(getattr(settings.runtime, "flip_actions_enabled", False))
        if not flip_allowed:
            flip_allowed = bool(caps.get("flip_allowed"))
        if not flip_allowed:
            return stand_aside_decision(
                decision.symbol,
                decision.timeframe,
                f"Flip actions disabled; blocked {decision.action}; {decision.notes}",
            )

    if (caps.get("long_only") is True or caps.get("supports_short") is False) and decision.action in {
        "enter_short",
        "flip_to_short",
    }:
        return stand_aside_decision(
            decision.symbol,
            decision.timeframe,
            f"Venue long-only (supports_short=false); blocked {decision.action}; {decision.notes}",
        )

    if decision.risk_per_trade_pct is not None:
        if decision.risk_per_trade_pct > 1:
            logger.info("Normalizing risk_per_trade_pct from %.2f to fractional", decision.risk_per_trade_pct)
            decision.risk_per_trade_pct /= 100.0
        if decision.risk_per_trade_pct > max_sim_risk:
            logger.warning(
                "Risk per trade %.4f exceeds simulation cap %.4f", decision.risk_per_trade_pct, max_sim_risk
            )
            return _downgrade(decision, "Risk too spicy")

    if decision.entry_zone:
        low, high = decision.entry_zone
        if low <= 0 or high <= 0 or low >= high:
            return _downgrade(decision, "Entry zone nonsensical")

    for price_field, label in [
        (decision.entry_price, "entry"),
        (decision.stop_loss, "stop"),
        (decision.take_profit, "target"),
    ]:
        if price_field is not None and price_field <= 0:
            return _downgrade(decision, f"{label} invalid")

    if decision.max_position_size_pct is not None:
        if decision.max_position_size_pct > 1:
            logger.info(
                "Normalizing max_position_size_pct from %.2f to fractional", decision.max_position_size_pct
            )
            decision.max_position_size_pct /= 100.0

    return decision


def _downgrade(decision: AITradeDecision, reason: str) -> AITradeDecision:
    """Turns wild ideas into quiet sitting so you can breathe again."""
    return stand_aside_decision(decision.symbol, decision.timeframe, f"{reason}; {decision.notes}")
