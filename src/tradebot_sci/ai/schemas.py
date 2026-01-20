from __future__ import annotations

from typing import Literal, Optional, Tuple, TypedDict

from pydantic import BaseModel, Field

RoleLiteral = Literal["system", "user", "assistant"]


class ChatMessage(TypedDict):
    """Carries chat bits so the AI brain can pretend it's in a meeting."""

    role: RoleLiteral
    content: str


class ModelParams(BaseModel):
    """Specifies model knobs so you can dial the AI up to 11 without melting it."""

    model: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(gt=0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RawCompletionChoice(BaseModel):
    """Represents a single AI babble option before we slap it into shape."""

    index: Optional[int] = None
    message: dict
    finish_reason: Optional[str] = None


class RawCompletionResponse(BaseModel):
    """Wraps the raw LLM response so we can politely interrogate it later."""

    id: Optional[str] = None
    object: Optional[str] = None
    created: Optional[int] = None
    model: Optional[str] = None
    choices: list[RawCompletionChoice] = Field(default_factory=list)
    usage: Optional[dict] = None


class ParsedDecisionPayload(BaseModel):
    """Structured ICC trade idea—because JSON beats interpretive dance."""

    symbol: str
    timeframe: str  # execution timeframe like 1m/5m/15m
    bias: Literal["long", "short", "neutral"]
    phase: Literal["trend", "indication", "correction", "continuation", "chop"]
    action: Literal[
        "enter_long",
        "enter_short",
        "scale_in",
        "scale_out",
        "close_position",
        "hold",
        "stand_aside",
        "flip_to_long",
        "flip_to_short",
    ]
    entry_price: Optional[float] = None
    entry_zone: Optional[Tuple[float, float]] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # Accepts fractional percentages 0-1; higher values (e.g., 12) will be normalized in safety.
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_position_size_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    time_in_force_sec: Optional[int] = None
    urgency: Literal["low", "medium", "high"] = "medium"
    structure_summary: str
    invalidation_conditions: str
    management_instructions: str
    notes: str


def parse_decision_payload(raw_json: str) -> ParsedDecisionPayload:
    """Parses AI JSON so we can judge it without hurting its feelings."""
    return ParsedDecisionPayload.model_validate_json(raw_json)


class MarketContext(BaseModel):
    """Wraps market facts so the AI can act like it was watching the chart."""

    symbol: str
    timeframe: str
    trend_htf: str
    trend_ltf: str
    htf_align: Optional[bool] = None
    htf_timeframe: Optional[str] = None
    ltf_timeframe: Optional[str] = None
    execution_capabilities: Optional[dict] = None
    phase: Optional[str] = None
    recent_high: Optional[float] = None
    recent_low: Optional[float] = None
    liquidity_sweeps: Optional[list[str]] = None
    sweep_confirmed: Optional[bool] = None
    continuation_confirmed: Optional[bool] = None
    confluence: Optional[dict] = None
    recent_continuation_detection_rate: Optional[str] = None
    continuation_blocking_reason: Optional[str] = None
    htf_candles: Optional[list[dict]] = None
    ltf_candles: Optional[list[dict]] = None
    open_position: Optional[dict] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Exports context as dict so the AI gets the memo."""
        return self.model_dump(exclude_none=True)
