"""Regression tests for the AI client / payload schema audit fixes.

Every test stubs the HTTP layer with an httpx MockTransport; nothing here touches
the network or a real provider.
"""

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from helpers import make_test_settings
from pydantic import ValidationError

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.schemas import ChatMessage, MarketContext, parse_decision_payload
from tradebot_sci.config.models import AISettings

MOCK_BASE_URL = "https://mock.example.com"


def _decision_payload(**overrides):
    """A schema-legal decision body, overridable per test."""
    payload = {
        "symbol": "BTC-USD",
        "timeframe": "5m",
        "bias": "long",
        "phase": "trend",
        "action": "enter_long",
        "entry_price": 100.0,
        "entry_zone": [99.0, 101.0],
        "stop_loss": 95.0,
        "take_profit": 112.0,
        "risk_per_trade_pct": 0.05,
        "max_position_size_pct": 0.2,
        "time_in_force_sec": 300,
        "urgency": "high",
        "structure_summary": "trend",
        "invalidation_conditions": "break",
        "management_instructions": "trail",
        "notes": "ok",
    }
    payload.update(overrides)
    return payload


def _openai_body(payload):
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _gemini_body(text, finish_reason="STOP"):
    candidate = {"finishReason": finish_reason}
    if text is not None:
        candidate["content"] = {"parts": [{"text": text}]}
    return {"candidates": [candidate]}


class _DummyContext:
    """Stands in for the market context handed to generate_decision."""

    def __init__(self, **extra):
        self._data = {
            "symbol": "BTC-USD",
            "timeframe": "5m",
            "trend_htf": "long",
            "trend_ltf": "long",
            "phase": "trend",
        }
        self._data.update(extra)
        for key, value in extra.items():
            setattr(self, key, value)
        self.symbol = self._data["symbol"]
        self.timeframe = self._data["timeframe"]

    def to_dict(self):
        return self._data


def _client(handler, *, provider="openai", api_key="test", root_settings=None):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url=MOCK_BASE_URL, transport=transport)
    settings = AISettings(
        provider=provider,
        base_url=MOCK_BASE_URL,
        api_key=api_key,
        # Keep provider-specific key fallbacks out of the environment's reach so the
        # "no key" cases below are deterministic.
        openai_key=None,
        gemini_key=None,
        claude_key=None,
        deepseek_key=None,
        openrouter_key=None,
        model_name="model",
        temperature=0.1,
        max_tokens=128,
        timeout_seconds=5,
    )
    return TradeSciAIClient(settings=settings, http_client=http, root_settings=root_settings)


def _test_root_settings(**overrides):
    """Full Settings object (carries .runtime) plus AI settings for the client."""
    ai = {
        "provider": "openai",
        "base_url": MOCK_BASE_URL,
        "api_key": "test",
        "model_name": "model",
        "temperature": 0.1,
        "max_tokens": 128,
        "timeout_seconds": 5,
    }
    return make_test_settings(ai=ai, **overrides)


# --- 1. Gemini key travels as a header, never in the URL ----------------------


def test_gemini_api_key_is_sent_as_header_not_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=_gemini_body("ok"))

    ai_client = _client(handler, provider="gemini", api_key="super-secret-key")

    assert ai_client.raw_chat([ChatMessage(role="user", content="hi")], expect_json=False) == "ok"
    assert seen["headers"].get("x-goog-api-key") == "super-secret-key"
    assert "super-secret-key" not in seen["url"]
    assert "key=" not in seen["url"]


# --- 4. Gemini generationConfig / finishReason ---------------------------------


def test_gemini_disables_thinking_budget():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_gemini_body("ok"))

    ai_client = _client(handler, provider="gemini")

    ai_client.raw_chat([ChatMessage(role="user", content="hi")], expect_json=False)
    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["thinkingConfig"]["thinkingBudget"] == 0
    assert generation_config["maxOutputTokens"] == 128


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY"])
def test_gemini_truncated_or_blocked_reply_is_discarded(finish_reason, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        # A truncated reply still carries a partial JSON body, which must not be
        # handed back as if the model had finished.
        return httpx.Response(
            200, json=_gemini_body('{"symbol": "BTC-USD", "timeframe"', finish_reason=finish_reason)
        )

    ai_client = _client(handler, provider="gemini")

    with caplog.at_level(logging.WARNING):
        content = ai_client.raw_chat([ChatMessage(role="user", content="hi")], expect_json=True)

    assert content == ""
    assert finish_reason in caplog.text


# --- 6. System prompt appears once --------------------------------------------


def test_gemini_system_prompt_is_not_flattened_into_the_prompt():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_gemini_body("ok"))

    ai_client = _client(handler, provider="gemini")
    messages = [
        ChatMessage(role="system", content="SYSTEM-RULES"),
        ChatMessage(role="user", content="hello"),
    ]

    ai_client.raw_chat(messages, expect_json=False)
    flattened = captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "SYSTEM-RULES" not in flattened
    assert "hello" in flattened
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"] == "SYSTEM-RULES"


# --- 3. Claude role alternation and single JSON instruction --------------------


def test_claude_merges_consecutive_user_roles_and_appends_one_json_instruction():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})

    ai_client = _client(handler, provider="claude")
    messages = [
        ChatMessage(role="system", content="SYSTEM-RULES"),
        ChatMessage(role="user", content="first"),
        ChatMessage(role="user", content="second"),
    ]

    assert ai_client.raw_chat(messages, expect_json=True) == "{}"
    claude_messages = captured["payload"]["messages"]
    assert [m["role"] for m in claude_messages] == ["user"]

    text = claude_messages[0]["content"][0]["text"]
    assert "first" in text and "second" in text
    assert text.count("Return a single JSON object only.") == 1
    assert text.rstrip().endswith("Return a single JSON object only.")


def test_claude_keeps_alternating_turns_and_tags_only_the_last_user_turn():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})

    ai_client = _client(handler, provider="claude")
    messages = [
        ChatMessage(role="system", content="SYSTEM-RULES"),
        ChatMessage(role="user", content="first"),
        ChatMessage(role="assistant", content="thinking"),
        ChatMessage(role="user", content="second"),
    ]

    ai_client.raw_chat(messages, expect_json=True)
    claude_messages = captured["payload"]["messages"]
    assert [m["role"] for m in claude_messages] == ["user", "assistant", "user"]
    assert "Return a single JSON object only." not in claude_messages[0]["content"][0]["text"]
    assert claude_messages[2]["content"][0]["text"].rstrip().endswith(
        "Return a single JSON object only."
    )


# --- 5. Missing API key raises instead of faking a response --------------------


@pytest.mark.parametrize("expect_json", [True, False])
def test_missing_api_key_raises_instead_of_returning_a_fake_response(expect_json):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        raise AssertionError("no HTTP request may be sent without an API key")

    ai_client = _client(handler, provider="openai", api_key=None)

    with pytest.raises(RuntimeError, match="openai"):
        ai_client.raw_chat([ChatMessage(role="user", content="hi")], expect_json=expect_json)


def test_custom_provider_without_api_key_still_calls_the_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    ai_client = _client(handler, provider="custom", api_key=None)

    assert ai_client.raw_chat([ChatMessage(role="user", content="hi")], expect_json=False) == "hello"


# --- 2. Percentage fields normalised into (0, 1] ------------------------------


@pytest.mark.parametrize(
    ("risk_pct", "size_pct", "expected_risk", "expected_size"),
    [
        (12, 25, 0.12, 0.25),
        (0.05, 0.2, 0.05, 0.2),
        (100, 100, 1.0, 1.0),
    ],
)
def test_percentage_fields_are_normalised_to_fractions(risk_pct, size_pct, expected_risk, expected_size):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_openai_body(
                _decision_payload(risk_per_trade_pct=risk_pct, max_position_size_pct=size_pct)
            ),
        )

    ai_client = _client(handler)
    decision = ai_client.generate_decision(_DummyContext())

    assert decision.action == "enter_long"
    assert decision.risk_per_trade_pct == pytest.approx(expected_risk)
    assert decision.max_position_size_pct == pytest.approx(expected_size)


# --- 8. Non-finite numbers are rejected at parse time -------------------------


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_non_finite_prices_are_rejected_by_the_payload_schema(token):
    raw = json.dumps(_decision_payload()).replace('"entry_price": 100.0', f'"entry_price": {token}')

    with pytest.raises(ValidationError):
        parse_decision_payload(raw)


def test_nan_price_never_reaches_a_decision():
    raw = json.dumps(_decision_payload()).replace('"entry_price": 100.0', '"entry_price": NaN')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})

    ai_client = _client(handler)
    decision = ai_client.generate_decision(_DummyContext())

    assert decision.action == "stand_aside"


# --- 9. time_in_force_sec is bounded ------------------------------------------


def test_time_in_force_is_bounded():
    assert parse_decision_payload(json.dumps(_decision_payload())).time_in_force_sec == 300

    for bad in (0, -30, 10**9):
        with pytest.raises(ValidationError):
            parse_decision_payload(json.dumps(_decision_payload(time_in_force_sec=bad)))


# --- 10. MarketContext keeps the caller's fields ------------------------------


def test_market_context_keeps_timestamp_price_signals_and_metadata():
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    # Same keyword shape StrategyEngine.build_market_context uses.
    context = MarketContext(
        symbol="BTC-USD",
        timeframe="5m",
        timestamp=stamp,
        price=100.5,
        trend_htf="long",
        trend_ltf="long",
        signals={"rsi": 55.0},
        metadata={"strategy": "icc_core"},
    )

    data = context.to_dict()
    assert data["timestamp"] == stamp
    assert data["price"] == 100.5
    assert data["signals"] == {"rsi": 55.0}
    assert data["metadata"] == {"strategy": "icc_core"}


def test_continuation_detection_rate_is_numeric():
    context = MarketContext(
        symbol="BTC-USD",
        timeframe="5m",
        trend_htf="long",
        trend_ltf="long",
        recent_continuation_detection_rate=0.62,
    )

    assert context.recent_continuation_detection_rate == pytest.approx(0.62)
    assert context.to_dict()["recent_continuation_detection_rate"] == pytest.approx(0.62)


# --- 7. validate_decision receives the settings object ------------------------


def test_simulation_risk_cap_from_settings_blocks_the_decision():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_body(_decision_payload(risk_per_trade_pct=0.05)))

    root_settings = _test_root_settings(simulation_risk_cap=0.01)
    ai_client = _client(handler, root_settings=root_settings)

    decision = ai_client.generate_decision(_DummyContext())

    assert decision.action == "stand_aside"


def test_flip_actions_enabled_from_settings_is_honoured():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_openai_body(_decision_payload(action="flip_to_long", bias="long"))
        )

    root_settings = _test_root_settings(flip_actions_enabled=True)
    ai_client = _client(handler, root_settings=root_settings)

    decision = ai_client.generate_decision(_DummyContext())

    assert decision.action == "flip_to_long"


def test_settings_can_be_passed_per_call():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_openai_body(_decision_payload(action="flip_to_long", bias="long"))
        )

    ai_client = _client(handler)
    settings = _test_root_settings(flip_actions_enabled=True)

    decision = ai_client.generate_decision(_DummyContext(), settings=settings)

    assert decision.action == "flip_to_long"


def test_runtime_guard_uses_the_clients_own_settings_when_no_root_object_is_given():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_body(_decision_payload(risk_per_trade_pct=0.05)))

    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url=MOCK_BASE_URL, transport=transport)
    # Settings object that carries both the AI fields and a runtime section.
    settings = SimpleNamespace(
        provider="openai",
        base_url=MOCK_BASE_URL,
        api_key="test",
        model_name="model",
        temperature=0.1,
        max_tokens=128,
        timeout_seconds=5,
        runtime=SimpleNamespace(simulation_risk_cap=0.01, flip_actions_enabled=False),
    )

    ai_client = TradeSciAIClient(settings=settings, http_client=http)

    assert ai_client.generate_decision(_DummyContext()).action == "stand_aside"
