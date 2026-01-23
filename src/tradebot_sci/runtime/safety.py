from __future__ import annotations

import logging
from typing import Optional

from tradebot_sci.config.models import Settings
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision

logger = logging.getLogger(__name__)

ALLOWED_BIAS = {"long", "short", "neutral"}
ALLOWED_PHASE = {"trend", "correction", "continuation", "chop"}
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
    max_sim_risk = 0.25  # Increased to 25% for small account hyper-growth
    try:
        if settings and hasattr(settings, "app"):
            max_sim_risk = max_sim_risk  # placeholder for future configurable cap
    except Exception as e:
        logger.debug(f"Failed to get max_sim_risk from settings: {e}")
        pass

    if decision.bias not in ALLOWED_BIAS:
        return _downgrade(decision, "Bias invalid")
    if decision.phase not in ALLOWED_PHASE:
        return _downgrade(decision, "Phase invalid")
    if decision.action not in ALLOWED_ACTION:
        return _downgrade(decision, "Action invalid")

    if decision.action in {"enter_long", "enter_short", "scale_in", "add_to_position", "flip_to_long", "flip_to_short"}:
        if decision.entry_price is None or decision.stop_loss is None or decision.take_profit is None:
            return _downgrade(decision, "Missing required entry/stop/target fields")
            
        is_long = decision.action in {"enter_long", "flip_to_long"} or (
            decision.action in {"scale_in", "add_to_position"} and decision.bias == "long"
        )
        is_short = decision.action in {"enter_short", "flip_to_short"} or (
            decision.action in {"scale_in", "add_to_position"} and decision.bias == "short"
        )

        if is_long and not (decision.stop_loss < decision.entry_price < decision.take_profit):
            msg = f"Long pricing invalid: stop={decision.stop_loss} < entry={decision.entry_price} < target={decision.take_profit}"
            return _downgrade(decision, msg)
        if is_short and not (decision.stop_loss > decision.entry_price > decision.take_profit):
            msg = f"Short pricing invalid: stop={decision.stop_loss} > entry={decision.entry_price} > target={decision.take_profit}"
            return _downgrade(decision, msg)

    caps = execution_capabilities or {}
    if decision.action in {"flip_to_long", "flip_to_short"}:
        flip_allowed = False
        if settings is not None:
            try:
                profile = settings.get_active_profile()
                flip_allowed = bool(getattr(profile, "flip_actions_enabled", False))
            except Exception:
                flip_allowed = False
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
