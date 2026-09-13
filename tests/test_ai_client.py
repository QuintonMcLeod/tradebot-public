import httpx

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.schemas import ChatMessage
from tradebot_sci.config.models import AISettings


def test_raw_chat_and_decision_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "{\"symbol\": \"BTC-USD\", \"timeframe\": \"5m\", \"bias\": \"long\", \"phase\": \"trend\", \"action\": \"enter_long\", \"entry_price\": 100, \"entry_zone\": [99, 101], \"stop_loss\": 95, \"take_profit\": 110, \"risk_per_trade_pct\": 0.05, \"max_position_size_pct\": 0.2, \"time_in_force_sec\": 300, \"urgency\": \"high\", \"structure_summary\": \"trend\", \"invalidation_conditions\": \"break\", \"management_instructions\": \"trail\", \"notes\": \"ok\"}"
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://mock.example.com", transport=transport)
    settings = AISettings(
        base_url="https://mock.example.com",
        api_key="test",
        model_name="model",
        temperature=0.1,
        max_tokens=128,
        timeout_seconds=5,
    )
    ai_client = TradeSciAIClient(settings=settings, http_client=client)

    messages = [ChatMessage(role="user", content="hello")]
    completion = ai_client.raw_chat(messages, expect_json=False)
    assert isinstance(completion, str) or hasattr(completion, 'choices')

    class DummyContext:
        def to_dict(self):
            return {
                "symbol": "BTC-USD",
                "timeframe": "5m",
                "trend_htf": "long",
                "trend_ltf": "long",
                "phase": "trend",
            }

    decision = ai_client.generate_decision(DummyContext())
    assert decision.bias == "long"
    assert decision.action == "enter_long"
