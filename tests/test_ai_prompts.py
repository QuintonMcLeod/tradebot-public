from tradebot_sci.ai.prompts import build_decision_messages


def test_prompt_short_restriction_is_conditional_on_capabilities():
    messages = build_decision_messages(
        {
            "symbol": "GDX",
            "timeframe": "5m",
            "trend_htf": "short",
            "trend_ltf": "short",
            "phase": "continuation",
            "sweep_confirmed": True,
            "continuation_confirmed": True,
            "execution_capabilities": {
                "venue": "IBKR",
                "asset_class": "equity",
                "supports_short": True,
                "long_only": False,
            },
        }
    )
    joined = "\n".join(m["content"] for m in messages if "content" in m)
    assert "Interpret execution_capabilities literally" in joined
    assert "Only claim 'shorts are not permitted' when" in joined
