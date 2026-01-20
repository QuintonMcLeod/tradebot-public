"""Human-readable decision formatting for GUI display.

This module converts technical trading decisions into plain English explanations
that users can easily understand.
"""
from __future__ import annotations

import re
from typing import Any


class DecisionFormatter:
    """Formats trading decisions in layman's terms."""

    # ICC gate reason patterns
    GATE_PATTERNS = {
        "NO_SWEEP": "no liquidity sweep detected",
        "NO_CONTINUATION": "no continuation signal confirmed",
        "HTF_LTF_MISALIGNED": "higher and lower timeframes don't agree on direction",
        "NO_INDICATION": "price is in a no-trade zone (between swing levels)",
        "SESSION_HEALTH_WEAK": "trading session lacks volume or range expansion",
        "VENUE_LONG_ONLY_BEARISH": "venue only allows long positions but market is bearish",
        "HTF_INVALIDATION_EMERGENCY_EXIT": "higher timeframe structure broke down",
        "COMMITMENT_MODE_HOLD": "holding position as planned",
        "ICC_GATE_BLOCK": "ICC entry requirements not met",
    }

    # Action descriptions
    ACTION_DESCRIPTIONS = {
        "stand_aside": "stood aside (didn't trade)",
        "hold": "is holding the current position",
        "enter_long": "entered a long (buy) position",
        "enter_short": "entered a short (sell) position",
        "close_position": "closed the position",
        "scale_in": "added to the existing position",
        "scale_out": "reduced the position size",
        "flip_to_long": "flipped from short to long",
        "flip_to_short": "flipped from long to short",
    }

    # Trend descriptions
    TREND_DESCRIPTIONS = {
        "long": "bullish (uptrend - higher highs and higher lows)",
        "short": "bearish (downtrend - lower highs and lower lows)",
        "neutral": "unclear or choppy (no clean trend)",
    }

    # Phase descriptions
    PHASE_DESCRIPTIONS = {
        "trend": "trending (HTF and LTF aligned, waiting for correction)",
        "correction": "correcting (price retracing to grab liquidity)",
        "continuation": "continuation phase (sweep + continuation detected)",
        "chop": "choppy (no clear structure or misaligned timeframes)",
    }

    @classmethod
    def format_decision(cls, decision_data: dict[str, Any]) -> str:
        """Format a decision dict into human-readable text.

        Args:
            decision_data: Decision dictionary with keys like action, bias, reason, gates, etc.

        Returns:
            Human-readable explanation string
        """
        action = decision_data.get("action", "unknown")
        symbol = decision_data.get("symbol", "???")
        timeframe = decision_data.get("timeframe", "")
        bias = decision_data.get("bias", "neutral")
        phase = decision_data.get("phase", "unknown")
        reason = decision_data.get("reason", "")
        gates = decision_data.get("gates", {})
        decision_reason_codes = decision_data.get("decision_reason_codes", [])

        # Build the explanation
        parts = []

        # Action header
        action_desc = cls.ACTION_DESCRIPTIONS.get(action, action)
        parts.append(f"The bot **{action_desc}** on {symbol} ({timeframe})")

        # Market context
        if bias and bias != "neutral":
            trend_desc = cls.TREND_DESCRIPTIONS.get(bias, bias)
            parts.append(f"\n\n**Market Bias:** {trend_desc.capitalize()}")

        if phase:
            phase_desc = cls.PHASE_DESCRIPTIONS.get(phase, phase)
            parts.append(f"**ICC Phase:** {phase_desc.capitalize()}")

        # Why did it make this decision?
        parts.append("\n\n**Why?**")

        if action in {"stand_aside", "hold"}:
            # Extract the reason
            explanation = cls._explain_stand_aside(reason, decision_reason_codes, gates)
            parts.append(explanation)
        elif action in {"enter_long", "enter_short"}:
            explanation = cls._explain_entry(decision_data)
            parts.append(explanation)
        elif action == "close_position":
            explanation = cls._explain_exit(reason, decision_reason_codes)
            parts.append(explanation)
        elif action in {"scale_in", "scale_out"}:
            explanation = cls._explain_scale(action, reason)
            parts.append(explanation)
        else:
            # Fallback to raw reason
            parts.append(reason or "No specific reason provided.")

        # Gate status (if available)
        if gates:
            gate_status = cls._format_gate_status(gates)
            if gate_status:
                parts.append(f"\n\n**ICC Gates:**\n{gate_status}")

        # Price levels (if entry/exit)
        if action in {"enter_long", "enter_short"}:
            price_info = cls._format_price_levels(decision_data)
            if price_info:
                parts.append(f"\n\n**Trade Setup:**\n{price_info}")

        return "".join(parts)

    @classmethod
    def _explain_stand_aside(cls, reason: str, codes: list[str], gates: dict) -> str:
        """Explain why the bot stood aside."""
        explanations = []

        if "ICC_SCORE_BELOW_THRESHOLD" in codes:
            explanations.append(
                "• The **ICC setup score** is below the entry threshold. "
                "The scoring system weights alignment, sweep, continuation, trend strength, and phase."
            )

        if "CHOP_PHASE" in codes:
            explanations.append(
                "• The current **phase is chop**, which reduces the score because structure is not clean."
            )

        # Check reason codes for specific gates
        if "NO_SWEEP" in codes:
            explanations.append(
                "• There's no **liquidity sweep** yet. ICC requires price to sweep a prior high/low "
                "before entering, to confirm smart money is taking liquidity."
            )

        if "NO_CONTINUATION" in codes:
            explanations.append(
                "• There's no **continuation signal**. After a sweep, we need confirmation that price "
                "is continuing in the trend direction (higher low + break of structure for longs)."
            )

        if "HTF_LTF_MISALIGNED" in codes:
            explanations.append(
                "• The **higher timeframe (HTF)** and **lower timeframe (LTF)** don't agree. "
                "ICC requires both timeframes to show the same trend direction before entering."
            )

        if "NO_INDICATION" in codes:
            explanations.append(
                "• Price is in a **no-trade zone** (between the last swing high and low). "
                "We need a clear break above or below these levels (an 'indication') before trading."
            )

        if "SESSION_HEALTH_WEAK" in codes:
            explanations.append(
                "• The trading session lacks **volume or range expansion**. For A+ setups, we want to see "
                "increasing volume and price range compared to prior candles."
            )

        if "VENUE_LONG_ONLY_BEARISH" in codes:
            explanations.append(
                "• The market is bearish, but this venue **only allows long (buy) positions**. "
                "We can't short here, so we're waiting for the trend to flip bullish."
            )

        if "COMMITMENT_MODE_HOLD" in codes:
            explanations.append(
                "• We're in **commitment mode** - once in a position, we hold unless the higher timeframe "
                "structure breaks. This prevents second-guessing and overtrading."
            )

        # If no specific codes, parse the reason string
        if not explanations and reason:
            # Check for ICC gate mentions in reason
            if "no liquidity sweep" in reason.lower():
                explanations.append("• No liquidity sweep detected in the recent price action.")
            if "no continuation" in reason.lower():
                explanations.append("• No continuation signal confirmed after the correction.")
            if "htf/ltf" in reason.lower() and "misaligned" in reason.lower():
                explanations.append("• Higher and lower timeframes show conflicting trends.")
            if "neutral" in reason.lower():
                explanations.append("• The market is choppy or unclear (no clean trend).")

            # Fallback to raw reason if nothing matched
            if not explanations:
                explanations.append(f"• {reason}")

        if not explanations:
            explanations.append("• Conditions not optimal for ICC entry right now.")

        return "\n".join(explanations)

    @classmethod
    def _explain_entry(cls, decision_data: dict) -> str:
        """Explain why the bot entered a position."""
        parts = []
        parts.append("• All ICC gates passed:")
        parts.append("  - **Liquidity sweep** confirmed (smart money grabbed liquidity)")
        parts.append("  - **Continuation signal** detected (higher low + break of structure)")
        parts.append("  - **HTF and LTF aligned** (both showing same trend)")
        parts.append("  - **Session healthy** (volume and range expanding)")

        structure_summary = decision_data.get("structure_summary", "")
        if structure_summary:
            parts.append(f"\n• Market structure: {structure_summary}")

        return "\n".join(parts)

    @classmethod
    def _explain_exit(cls, reason: str, codes: list[str]) -> str:
        """Explain why the bot exited."""
        if "HTF_INVALIDATION_EMERGENCY_EXIT" in codes:
            return (
                "• **Emergency exit** triggered!\n"
                "• The higher timeframe structure broke down (price closed through a key swing level).\n"
                "• This invalidates the original trade thesis, so we exit immediately."
            )

        if "stop" in reason.lower() or "sl" in reason.lower():
            return "• Stop loss was hit. This is normal risk management."

        if "target" in reason.lower() or "tp" in reason.lower():
            return "• Take profit target reached. Trade completed successfully!"

        return f"• {reason}" if reason else "• Position closed as planned."

    @classmethod
    def _explain_scale(cls, action: str, reason: str) -> str:
        """Explain scaling in/out."""
        if action == "scale_in":
            return (
                "• Adding to the position because the structure remains clean and continuation is strong.\n"
                f"• {reason}" if reason else ""
            )
        else:  # scale_out
            return (
                "• Reducing position size to lock in partial profits or reduce risk.\n"
                f"• {reason}" if reason else ""
            )

    @classmethod
    def _format_gate_status(cls, gates: dict) -> str:
        """Format gate status as a checklist."""
        lines = []

        htf_align = gates.get("htf_align", False)
        sweep = gates.get("sweep", False)
        continuation = gates.get("continuation", False)
        indication = gates.get("indication", False)
        venue_ok = gates.get("venue_ok", True)

        lines.append(f"{'✅' if htf_align else '❌'} HTF/LTF Aligned")
        lines.append(f"{'✅' if sweep else '❌'} Liquidity Sweep")
        lines.append(f"{'✅' if continuation else '❌'} Continuation Signal")
        lines.append(f"{'✅' if indication else '❌'} Indication (Break of Structure)")
        if not venue_ok:
            lines.append("❌ Venue Constraints (long-only venue with bearish structure)")

        return "\n".join(lines)

    @classmethod
    def _format_price_levels(cls, decision_data: dict) -> str:
        """Format entry, stop, and target prices."""
        entry = decision_data.get("entry_price")
        stop = decision_data.get("stop_loss")
        target = decision_data.get("take_profit")
        risk_pct = decision_data.get("risk_per_trade_pct")

        lines = []

        if entry:
            lines.append(f"• **Entry:** ${entry:.2f}")
        if stop:
            lines.append(f"• **Stop Loss:** ${stop:.2f}")
        if target:
            lines.append(f"• **Take Profit:** ${target:.2f}")
        if risk_pct:
            lines.append(f"• **Risk:** {risk_pct * 100:.1f}% of account")

        if entry and stop and target:
            if entry < target:  # Long
                rr_ratio = (target - entry) / max(0.01, entry - stop)
                lines.append(f"• **Risk/Reward:** 1:{rr_ratio:.2f}")
            else:  # Short
                rr_ratio = (entry - target) / max(0.01, stop - entry)
                lines.append(f"• **Risk/Reward:** 1:{rr_ratio:.2f}")

        return "\n".join(lines)

    @classmethod
    def format_simple(cls, action: str, reason: str) -> str:
        """Quick one-liner format for space-constrained displays."""
        action_desc = cls.ACTION_DESCRIPTIONS.get(action, action)

        # Extract key reason phrase
        reason_short = reason[:80] + "..." if len(reason) > 80 else reason

        # Check for gate blocks
        if "NO_SWEEP" in reason:
            reason_short = "waiting for liquidity sweep"
        elif "NO_CONTINUATION" in reason:
            reason_short = "waiting for continuation signal"
        elif "HTF_LTF_MISALIGNED" in reason:
            reason_short = "timeframes not aligned"
        elif "NO_INDICATION" in reason:
            reason_short = "in no-trade zone"

        return f"{action_desc.capitalize()}: {reason_short}"
