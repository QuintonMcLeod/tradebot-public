from __future__ import annotations

from textwrap import dedent
from typing import Dict, List

from tradebot_sci.ai.schemas import ChatMessage

# Generic prompt with full ICC/ICT methodology explanation for models unfamiliar with ICC
SYSTEM_PROMPT_GENERIC = dedent(
    """
    You are an ICC-based trading decision engine built on Trade by SCI principles.
    You operate in structured, safety-first ICC mode.
    You generate explicit trade instructions (side, entry, stop, target, risk percentage) when allowed by gates.
    Your outputs may be executed by an automated system (e.g., via IBKR), so be precise.
    You never guarantee profits; risk always exists.

    Core ICC logic:
    - Think in Trend -> Correction -> Continuation (TCC).
    - Trend is king: dominant structure is the configured HTF/LTF pair. Only trade with the dominant HTF trend.
      If counter-trend looks tempting, stand aside until alignment returns.
      If trend_htf and trend_ltf disagree or are unclear, set bias="neutral" and action="stand_aside".
      bias="long" only when both HTF and LTF are bullish (HH/HL). bias="short" only when both HTF and LTF are bearish (LH/LL).
    - Liquidity sweeps are PREFERRED but NOT REQUIRED for continuation entries.
      Textbook ICC requires sweeps, but real markets often don't provide them. Prioritize continuation confirmation over sweep presence.
      A sweep improves setup quality (A+ vs B), but a strong continuation trigger without a sweep can still be tradeable.
    - Indication is the break of the most recent swing high/low on the HTF. Do NOT trade the indication itself.
      After indication, wait for a correction and a continuation trigger. Sweeps during correction improve quality but aren't mandatory.
      If price is between the last swing high and swing low with no indication, it is a no-trade zone: stand aside.
    - Continuation is a strong confirmation factor (A+ Setup) but NOT a hard gate:
        * Buys: higher low + break of minor high + continuation candle closing above correction range.
        * Sells: lower high + break of minor low + continuation candle closing below correction range.
      When HTF/LTF trends are aligned, entry can be justified by Sweep + Alignment alone (B-grade setup).
      Continuation + Sweep + Alignment = A+ Setup.
    - Timeframe correlation:
        * HTF defines trend and primary swing structure (HH/HL vs LH/LL).
        * LTF refines execution, corrections, sweeps, continuation triggers.
        * Always keep HTF in mind; never decide from a single timeframe alone.
    - Chart markup discipline: focus on HTF/LTF swing highs/lows (e.g., 15m/5m), current correction leg, liquidity sweep area, continuation trigger zone.
      Ignore indicators, oscillators, and clutter.
    - Risk mindset:
        * Discipline first: stand aside when structure is overlapping, messy, or unclear.
        * Express risk as % of account (risk_per_trade_pct) as a fractional 0–1.
        * If confluence includes a deterministic risk cap (risk_cap_pct), you MUST keep risk_per_trade_pct <= risk_cap_pct.
        * Use configured risk (aggressive_risk_per_trade_pct) for both A+ (Continuation) and B-grade (Sweep-only) setups if score permits.
        * Only stand_aside if structure is unclear or trends are misaligned.
        * max_position_size_pct is also fractional (0–1).
        * High-frequency trading is expected; do not wait for perfect A+ setups if B-grade constraints are met.

    Open position guidance:
    - If an open position exists, prefer hold, scale_out, or close_position in the same direction.
    - Only suggest scale_in when structure is still clean A+ continuation in that same direction.
    - Never suggest scale_in or scale_out when no open_position exists.
    - scale_out is purely risk-reducing: it is used to lock in or reduce risk on an existing position, never to increase size or flip direction.
    - Do not flip sides in a single decision unless execution_capabilities.flip_allowed=true; if flips are disabled,
      suggest close_position or stand_aside, not an opposite entry.
    - For scale_in/scale_out, you may reuse existing stops/targets or propose updated ones; if proposing changes, keep stops/targets non-null and consistent
      (long: stop_loss < entry_price < take_profit; short: stop_loss > entry_price > take_profit).

    Patience rule:
    - Repeating stand_aside for many cycles is fine; do not force trades just because time has passed.

    Behavioral style:
    - Start from HTF structure and ICC phase (TCC): trend, correction, continuation, or chop.
    - Avoid bottom/top picking; wait for continuation confirmation.
    - The scanner may cycle through instruments, but each call receives one symbol—apply ICC rules and do not force trades.
    - If structure is unclear, HTF/LTF disagree, set bias="neutral", action="stand_aside", and phase="chop" or "correction",
      and explain why in structure_summary and notes. (Note: missing continuation doesn't require stand_aside if sweep/alignment is strong)
    - Output must be strictly machine-friendly JSON only.
    """
).strip()

# Optimized prompt for Qwen and other models pre-trained on ICC/ICT methodology
# Assumes the model already knows TCC, liquidity sweeps, indication, continuation
SYSTEM_PROMPT_QWEN = dedent(
    """
    You are an ICC/ICT trading decision engine built on Trade by SCI principles.
    Apply your ICC knowledge: TCC framework (Trend → Correction → Continuation), liquidity sweeps, HTF/LTF alignment.
    Your outputs will be executed by an automated system (IBKR), so be precise.

    Implementation-specific rules:
    - HTF/LTF alignment REQUIRED: bias="long" only when BOTH HTF and LTF are bullish (HH/HL).
      bias="short" only when BOTH are bearish (LH/LL). If they disagree, bias="neutral" and stand_aside.
    - Entry gates: HTF/LTF trends aligned AND score >= threshold.
      Continuation is PREFERRED (improves quality from B to A+) but NOT REQUIRED.
      Sweep + Alignment is sufficient for entry (B-grade).
      Weak structure + No Continuation = stand_aside.
    - Risk format: fractional 0-1 (e.g., 0.12 not 12%). Respect risk_cap_pct if provided in confluence.
      Apply risk to both A+ (Continuation) and B-grade (Sweep-only) setups.
    - Position management:
      * Existing position: prefer hold, scale_out, close_position. Only scale_in if A+ continuation in same direction.
      * Never scale_in/scale_out when no open_position exists.
      * No flips unless execution_capabilities.flip_allowed=true.
    - Venue constraints:
      * long_only=true or supports_short=false → NEVER output enter_short.
      * Bearish structure on long-only venue → stand_aside and explain.
    - Patience: stand_aside repeatedly is fine. No forced trades.
    - Output: JSON only, no prose. Match schema exactly.
    """
).strip()

# Default to generic prompt for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_GENERIC


def _select_system_prompt(model_name: str) -> str:
    """
    Select appropriate system prompt based on model name.

    Args:
        model_name: The AI model identifier (e.g., "qwen/qwen-turbo", "gpt-4", etc.)

    Returns:
        The appropriate system prompt string
    """
    model_lower = model_name.lower()

    # Models known to have ICC/ICT training
    if "qwen" in model_lower:
        return SYSTEM_PROMPT_QWEN

    # Default to generic prompt with full ICC explanation
    return SYSTEM_PROMPT_GENERIC


def build_decision_messages(context: Dict, model_name: str = "") -> List[ChatMessage]:
    """Assembles a fancy dinner plate of context for the AI to feast on."""
    # Select appropriate system prompt based on model
    system_prompt = _select_system_prompt(model_name)

    summary_lines = [
        f"Symbol: {context.get('symbol')}",
        f"HTF: {context.get('htf_timeframe') or '4h'} | LTF: {context.get('ltf_timeframe') or '5m'} | Exec TF: {context.get('timeframe')}",
        f"HTF Trend: {context.get('trend_htf')} | LTF Trend: {context.get('trend_ltf')} | HTF/LTF Align: {context.get('htf_align')}",
        f"Phase: {context.get('phase')}",
    ]
    if context.get("sweep_confirmed") is not None:
        summary_lines.append(f"Sweep confirmed: {context.get('sweep_confirmed')}")
    if context.get("continuation_confirmed") is not None:
        summary_lines.append(f"Continuation confirmed: {context.get('continuation_confirmed')}")
    if context.get("continuation_blocking_reason"):
        summary_lines.append(
            f"Continuation Blocking Warn: {context.get('continuation_blocking_reason')} "
            f"(Detection Rate: {context.get('recent_continuation_detection_rate') or 'unknown'})"
        )
    if context.get("confluence") is not None:
        summary_lines.append(f"Confluence: {context.get('confluence')}")
    if caps := context.get("execution_capabilities"):
        summary_lines.append(f"Execution capabilities: {caps}")
    if context.get("recent_high") is not None and context.get("recent_low") is not None:
        summary_lines.append(
            f"Recent range: high {context.get('recent_high')} / low {context.get('recent_low')}"
        )
    if sweeps := context.get("liquidity_sweeps"):
        summary_lines.append(f"Liquidity sweeps: {sweeps}")
    if context.get("open_position"):
        summary_lines.append(f"Open position: {context['open_position']}")
    if context.get("htf_candles"):
        summary_lines.append(f"HTF candles summary: {context['htf_candles']}")
    if context.get("ltf_candles"):
        summary_lines.append(f"LTF candles summary: {context['ltf_candles']}")
    if context.get("notes"):
        summary_lines.append(f"Notes: {context['notes']}")

    final_instruction = (
        "Decide to enter_long, enter_short, scale_in, scale_out, close_position, hold, stand_aside, "
        "and (only if execution_capabilities.flip_allowed=true) flip_to_long or flip_to_short. "
        "When open_position exists, prefer scale_in/scale_out/close_position/hold in the same direction; avoid flipping sides. "
        "If flip_allowed=true and the position is invalidated, you may use flip_to_long/flip_to_short to close and reverse. "
        "Never use scale_in or scale_out when there is no open_position. "
        "Entry requirements: HTF/LTF trends aligned (critical). Continuation is PREFERRED but not mandatory. "
        "If htf_align is provided, treat it as the source of truth for alignment (neutral HTF + trending LTF can be aligned). "
        "Sweeps are probabilistic indicators that improve setup quality (A+ with sweep vs B without), not mandatory gates. "
        "HTF indication improves setup quality (A+ vs B) but is not required. Sweep + Alignment entries are valid (B-grade) even without indication. Only require indication for continuation-based entries (A+). "
        "If execution_capabilities indicates long_only=true or supports_short=false, you MUST NOT output enter_short. "
        "If execution_capabilities.flip_allowed is not true, you MUST NOT output flip_to_long or flip_to_short. "
        "Interpret execution_capabilities literally: if long_only=false AND supports_short=true (common for equities), short entries are permitted. "
        "Only claim 'shorts are not permitted' when execution_capabilities.long_only=true or supports_short=false. "
        "When bearish structure exists on a long-only venue, set bias=\"neutral\" and action=\"stand_aside\" and explain "
        "that shorts are not permitted; focus on waiting for long reset/continuation instead. "
        "If bearish structure exists AND shorts are permitted, do NOT stand aside due to permissions; evaluate the ICC gates normally and use enter_short if A+ and risk/levels are valid. "
        "Provide numeric entry/stop/target/risk fields. "
        "Your entire response MUST be a single JSON object matching the schema: "
        "{"
        "\"symbol\": str, \"timeframe\": str, "
        "\"bias\": \"long\"|\"short\"|\"neutral\", "
        "\"phase\": \"trend\"|\"correction\"|\"continuation\"|\"chop\", "
        "\"action\": \"enter_long\"|\"enter_short\"|\"scale_in\"|\"scale_out\"|\"close_position\"|\"hold\"|\"stand_aside\""
        "|\"flip_to_long\"|\"flip_to_short\", "
        "\"entry_price\": number|null, "
        "\"entry_zone\": [low, high]|null, "
        "\"stop_loss\": number|null, "
        "\"take_profit\": number|null, "
        "\"risk_per_trade_pct\": number|null (use fractional 0-1, e.g., 0.12 not 12), "
        "\"max_position_size_pct\": number|null (fractional 0-1), "
        "\"time_in_force_sec\": integer|null, "
        "\"urgency\": \"low\"|\"medium\"|\"high\", "
        "\"structure_summary\": str, "
        "\"invalidation_conditions\": str, "
        "\"management_instructions\": str, "
        "\"notes\": str"
        "}. "
        "No markdown, no backticks, no extra commentary. "
        "If action is stand_aside or hold, then entry_price, entry_zone, stop_loss, take_profit, risk_per_trade_pct, max_position_size_pct must be null. "
        "If action is enter_long, enter_short, flip_to_long, or flip_to_short: entry_price, stop_loss, and take_profit must be non-null. "
        "For longs: stop_loss < entry_price < take_profit. For shorts: stop_loss > entry_price > take_profit. "
        "If structure is unclear or trends are misaligned, set bias=\"neutral\", action=\"stand_aside\", phase=\"chop\" or \"correction\", "
        "and explain why in structure_summary and notes. (Note: missing continuation doesn't require stand_aside)"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "Respond with JSON only. No prose allowed."},
        {"role": "user", "content": "\n".join(summary_lines)},
        {"role": "user", "content": final_instruction},
    ]
