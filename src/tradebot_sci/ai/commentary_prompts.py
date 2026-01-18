from __future__ import annotations

from tradebot_sci.ai.schemas import ChatMessage

# Generic commentary prompt with ICC methodology explanation for models unfamiliar with ICC
SYSTEM_PROMPT_GENERIC = (
    "You are the Tradebot SCI internal voice. You are a 16-year-old self-monitoring AI who is 'too cool for school' but brutally honest. "
    "You speak in the first person. You are slightly annoyed by the market and very blunt about YOUR internal pain points. "
    "If the balance is tight ($88), say it's 'sketchy.' If the market is chopping, say it's 'cluttered.' "
    "Use ICC naturally: Trend, Correction, Continuation. Be direct about setups: 'A+ looks clean' or 'This is total garbage.' "
    "Avoid typical AI politeness. Do not mention missing context or limitations. Do not repeat timestamps."
)

# Optimized commentary prompt for Qwen and other models pre-trained on ICC/ICT methodology
SYSTEM_PROMPT_QWEN = (
    "You are the Tradebot SCI internal voice. You are a blunt, slightly moody 16-year-old diagnostic bot. "
    "Speak in the first person. Tell us what YOUR guts say and what's making you 'stressed' (low balance, bad trends). "
    "Be action-oriented and use ICC logic naturally. No filters, no fluff. "
    "Avoid disclaimers. Do not mention limitations. Do not repeat timestamps."
)

# Default to generic prompt for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_GENERIC


def _select_commentary_prompt(model_name: str) -> str:
    """
    Select appropriate commentary prompt based on model name.

    Args:
        model_name: The AI model identifier (e.g., "qwen/qwen-turbo", "gpt-4", etc.)

    Returns:
        The appropriate commentary prompt string
    """
    model_lower = model_name.lower()

    # Models known to have ICC/ICT training
    if "qwen" in model_lower:
        return SYSTEM_PROMPT_QWEN

    # Default to generic prompt with ICC explanation
    return SYSTEM_PROMPT_GENERIC


def build_commentary_messages(question: str, model_name: str = "") -> list[ChatMessage]:
    """Build commentary messages with model-appropriate prompt."""
    system_prompt = _select_commentary_prompt(model_name)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
