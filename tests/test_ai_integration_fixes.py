"""Regression tests for the AI-integration safety fixes.

Every test here pins a defect where unvalidated model text, a placeholder news
string, or malformed cache data could change live behaviour. The AI client and
the news feeds are always stubbed: no test in this file performs network I/O,
and none reads or writes the real config.json.
"""
from __future__ import annotations

import inspect
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from helpers import make_test_settings

from tradebot_sci.ai.architecture_reference import ARCHITECTURE_COURSE
from tradebot_sci.ai.news_scraper import RSSNewsScraper
from tradebot_sci.ai.rss_feed import NO_NEWS_PLACEHOLDER
from tradebot_sci.config.models import (
    AppSettings,
    PerformanceSettings,
    RiskSettings,
    RuntimeSettings,
    SafetySettings,
    Settings,
    TradingProfileSettings,
)
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.runtime import loop as loop_module
from tradebot_sci.strategy import safety_guard as safety_guard_module
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.safety_guard import AssetClass, SafetyGuard


# --------------------------------------------------------------------------
# Stubs and fixtures
# --------------------------------------------------------------------------

class StubAIClient:
    """Records every prompt and returns a canned reply (or raises it)."""

    def __init__(self, reply="SAFE"):
        self.reply = reply
        self.prompts: list[list[dict]] = []

    def generate_text(self, messages):
        self.prompts.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeHTTPResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture(autouse=True)
def clean_safety_state():
    """Reset SafetyGuard's shared state so tests cannot leak into each other."""
    SafetyGuard.reset_state()
    yield
    SafetyGuard.reset_state()


@pytest.fixture(autouse=True)
def no_real_config(monkeypatch):
    """Point config reads at a missing file so no test touches the real config."""
    from tradebot_sci import paths as paths_module

    monkeypatch.setattr(paths_module, "CONFIG_FILE", Path("/nonexistent/tradebot-test-config.json"))


def _snapshot(symbol="EURUSD", timeframe="5m", count=1, timestamp=None) -> MarketSnapshot:
    ts = timestamp or datetime.now(timezone.utc)
    candles = [
        Candle(timestamp=ts, open=1.1000, high=1.1000, low=1.1000, close=1.1000, volume=1.0)
        for _ in range(count)
    ]
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        ltf_candles=candles,
        trend_htf=TrendState(direction="long", strength=0.5),
        trend_ltf=TrendState(direction="long", strength=0.5),
    )


def _entry_decision(risk: float = 0.01) -> AITradeDecision:
    return AITradeDecision(
        symbol="EURUSD",
        timeframe="5m",
        bias="long",
        phase="continuation",
        action="enter_long",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        risk_per_trade_pct=risk,
        notes="",
    )


def _sentiment_mode(monkeypatch, reply, headlines="- Central bank holds rates"):
    """Activate only the 'sentiment' wealth mode with stubbed news and client."""
    monkeypatch.setattr(
        SafetyGuard, "get_active_wealth_modes", classmethod(lambda cls: ["sentiment"])
    )
    monkeypatch.setattr(safety_guard_module, "get_latest_news", lambda limit=5: headlines)
    return StubAIClient(reply)


def _shield_settings():
    """Settings with the sentiment shield on and every other entry guard off.

    The other guards are disabled explicitly so the outcome depends only on the
    shield, not on the wall-clock hour the suite happens to run at.
    """
    return make_test_settings(
        safety_sentiment_shield_enabled=True,
        safety_drawdown_breaker_enabled=False,
        safety_session_lockout_enabled=False,
        safety_rollover_deadzone_enabled=False,
        safety_opening_sentry_enabled=False,
        safety_greed_guard_enabled=False,
        safety_streak_breaker_enabled=False,
        safety_churn_burner_enabled=False,
        safety_leverage_sentry_enabled=False,
        safety_volatility_veto_enabled=False,
    )


def _run_shield(monkeypatch, reply, headlines):
    monkeypatch.setattr(safety_guard_module, "get_latest_news", lambda limit=5: headlines)
    client = StubAIClient(reply)
    decision = SafetyGuard.check_entry_safety(
        symbol="EURUSD",
        timeframe="5m",
        current_capital=10000.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=_shield_settings(),
    )
    return client, decision


# --------------------------------------------------------------------------
# Item 1 — the sentiment mode must not scale live risk from unvalidated text
# --------------------------------------------------------------------------

def test_unrecognised_sentiment_reply_leaves_risk_unchanged(monkeypatch):
    client = _sentiment_mode(monkeypatch, "UNCERTAIN")

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.01),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.01),
    )

    assert out.risk_per_trade_pct == pytest.approx(0.01)
    assert "Drag" not in (out.notes or "")


def test_sentiment_boost_cannot_exceed_operator_risk(monkeypatch):
    # A trailing period must still be recognised as the BULLISH token, so this
    # exercises the cap and not the unrecognised-reply path.
    client = _sentiment_mode(monkeypatch, "BULLISH.")

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.01),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.01),
    )

    # 1.5x would be 1.5%; the operator set 1%, so 1% is the ceiling and risk must
    # not move at all.
    assert out.risk_per_trade_pct == pytest.approx(0.01)
    # The note must not describe a boost that did not happen. Wording it as
    # "capped @ 1.00%" reads as though risk was raised to that cap, when the value
    # was already there and never changed.
    notes = (out.notes or "").lower()
    assert "declined" in notes
    assert "capped" not in notes


def test_sentiment_boost_still_applies_below_the_operator_cap(monkeypatch):
    client = _sentiment_mode(monkeypatch, "BULLISH")

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.01),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.05),
    )

    assert out.risk_per_trade_pct == pytest.approx(0.015)
    assert "AI Sentiment Boost" in (out.notes or "")


def test_sentiment_boost_does_not_cut_dynamically_sized_risk(monkeypatch):
    # With dynamic risk sizing the base is 1.5% (score 70 → 2%, −0.5% for a weak
    # HTF), which is above the operator's static 1%. The AI boost must not become
    # a hidden risk cut down to the static percentage.
    client = _sentiment_mode(monkeypatch, "BULLISH")

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.015),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.01, risk_dynamic_auto=True),
    )

    assert out.risk_per_trade_pct == pytest.approx(0.015)


def test_contradicting_sentiment_reply_still_dampens(monkeypatch):
    client = _sentiment_mode(monkeypatch, "BEARISH")

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.01),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.01),
    )

    assert out.risk_per_trade_pct == pytest.approx(0.005)
    assert "AI Sentiment Drag" in (out.notes or "")


def test_sentiment_error_leaves_risk_unchanged(monkeypatch):
    client = _sentiment_mode(monkeypatch, RuntimeError("backend down"))

    out = SafetyGuard.augment_entry_decision(
        _entry_decision(risk=0.01),
        score=70.0,
        htf_strength=0.0,
        snapshot=_snapshot(),
        ai_client=client,
        settings=make_test_settings(risk_per_trade_pct=0.01),
    )

    assert out.risk_per_trade_pct == pytest.approx(0.01)


# --------------------------------------------------------------------------
# Item 2 — the news shield: no placeholder verdicts, no substring vetoes
# --------------------------------------------------------------------------

def test_no_news_skips_shield_instead_of_asking_the_model(monkeypatch):
    client, decision = _run_shield(monkeypatch, "DANGEROUS", NO_NEWS_PLACEHOLDER)

    assert client.prompts == []
    assert decision is None


def test_blank_news_context_also_skips_the_shield(monkeypatch):
    client, decision = _run_shield(monkeypatch, "DANGEROUS", "   ")

    assert client.prompts == []
    assert decision is None


def test_negated_dangerous_reply_does_not_veto(monkeypatch):
    client, decision = _run_shield(
        monkeypatch, "NOT DANGEROUS", "- Headline: central bank holds rates"
    )

    assert len(client.prompts) == 1
    assert decision is None


def test_exact_dangerous_reply_still_vetoes(monkeypatch):
    client, decision = _run_shield(
        monkeypatch, "DANGEROUS.", "- Headline: peg breaks, exchange halted"
    )

    assert len(client.prompts) == 1
    assert decision is not None
    assert decision.action == "stand_aside"
    assert "AI Sentiment Shield" in (decision.notes or "")


def test_shield_request_error_abstains_without_caching_safe(monkeypatch):
    client, decision = _run_shield(
        monkeypatch, RuntimeError("request failed"), "- Headline: rates unchanged"
    )

    assert len(client.prompts) == 1
    assert decision is None
    cached = SafetyGuard._state.sentiment_cache[AssetClass.FOREX][AssetClass.FOREX][1]
    assert cached != "SAFE"


# --------------------------------------------------------------------------
# Item 6 — <content> must be used even when the Element has no children
# --------------------------------------------------------------------------

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Rates unchanged</title>
    <content>Full content body from the feed</content>
    <summary>Short summary text</summary>
  </entry>
</feed>
"""


def test_atom_content_is_used_when_it_has_text_but_no_children(monkeypatch, tmp_path):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=None: FakeHTTPResponse(ATOM_FEED.encode())
    )
    scraper = RSSNewsScraper(cache_dir=str(tmp_path))

    items = scraper.fetch_feed("https://example.invalid/atom")

    assert len(items) == 1
    assert "Full content body from the feed" in items[0]
    assert "Short summary text" not in items[0]


# --------------------------------------------------------------------------
# Item 7 — a cache file with the wrong shape must not crash the caller
# --------------------------------------------------------------------------

def test_list_shaped_cache_falls_back_to_empty_cache(monkeypatch, tmp_path):
    (tmp_path / "rss_cache.json").write_text(json.dumps([{"title": "not a cache"}]))

    scraper = RSSNewsScraper(cache_dir=str(tmp_path))

    assert scraper._cache == {}
    monkeypatch.setattr(scraper, "fetch_feed", lambda url: [])
    assert "No recent" in scraper.get_latest_news_context()


def test_scalar_shaped_cache_falls_back_to_empty_cache(tmp_path):
    (tmp_path / "rss_cache.json").write_text(json.dumps("junk"))

    scraper = RSSNewsScraper(cache_dir=str(tmp_path))

    assert scraper._cache == {}


def test_valid_cache_dict_is_still_used(monkeypatch, tmp_path):
    (tmp_path / "rss_cache.json").write_text(
        json.dumps({"last_fetch": time.time(), "context": "- cached headline"})
    )
    scraper = RSSNewsScraper(cache_dir=str(tmp_path))
    monkeypatch.setattr(
        scraper, "fetch_feed", lambda url: pytest.fail("a valid cache must not re-fetch")
    )

    assert scraper.get_latest_news_context() == "- cached headline"


# --------------------------------------------------------------------------
# Item 5 — every setting the architecture course names must exist
# --------------------------------------------------------------------------

def _mapped_setting_keys() -> set[str]:
    """The keys adjust_settings accepts, built exactly as the AI builds them."""
    keys: set[str] = set()
    for model in (
        Settings,
        TradingProfileSettings,
        AppSettings,
        RuntimeSettings,
        PerformanceSettings,
        SafetySettings,
        RiskSettings,
    ):
        keys.update(name.upper() for name in model.model_fields)
    return keys


def _course_listed_settings() -> set[str]:
    """Setting-looking names from the course's SAFE / NEVER MODIFY lists."""
    names: set[str] = set()
    in_list = False
    for line in ARCHITECTURE_COURSE.splitlines():
        stripped = line.strip()
        if stripped.startswith(("✅", "⛔")):
            in_list = True
            continue
        if not in_list:
            continue
        if not stripped.startswith("- "):
            if stripped:
                in_list = False  # prose after the list ends it
            continue
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
            # Settings always carry an underscore; a trailing one is a prefix such
            # as the "trend_" family rather than a name.
            if "_" in token and not token.endswith("_"):
                names.add(token)
    return names


def test_architecture_course_only_names_real_settings():
    listed = _course_listed_settings()
    assert listed, "the course setting lists were not parsed"

    mapped = _mapped_setting_keys()
    unknown = sorted(name for name in listed if name.upper() not in mapped)

    assert unknown == [], f"the course teaches settings that do not exist: {unknown}"


# --------------------------------------------------------------------------
# Items 3, 4 and 8 — ordering and key spellings inside run_bot's hot-reload
# block. They are closures of a very large function, so the assertions pin the
# source order the fixes depend on rather than executing a live trading loop.
# --------------------------------------------------------------------------

def _run_bot_code() -> str:
    """run_bot's source with comment-only lines removed.

    Comments may name the calls these tests order against, so they are stripped
    to keep the assertions about executable lines only.
    """
    source = inspect.getsource(loop_module.run_bot)
    lines = [line for line in source.splitlines() if not line.strip().startswith("#")]
    return "\n".join(lines)


def _hot_reload_block() -> str:
    marker = "[HOT-RELOAD] Detected configuration change"
    source = _run_bot_code()
    assert marker in source, "hot-reload block not found in run_bot"
    return source.split(marker, 1)[1]


def test_execute_trades_is_refreshed_before_the_autopilot_check():
    block = _hot_reload_block()

    refresh = block.index("execute_trades = settings.runtime.execute_trades")
    daemon_check = block.index("_maybe_start_seasoned_daemon()")

    assert refresh < daemon_check, (
        "the Live Trading toggle must be re-read before _maybe_start_seasoned_daemon(), "
        "otherwise the daemon guard tests the previous cycle's value"
    )


def test_autopilot_reads_the_lowercase_gui_keys_first():
    source = _run_bot_code()

    for key in ("ai_monetary_path", "ai_personality", "ai_autopilot_interval_mins"):
        lower_prof = source.index(f'_prof.get("{key}"')
        lower_ai = source.index(f'_ai.get("{key}"')
        upper_ai = source.index(f'_ai.get("{key.upper()}"')
        assert lower_prof < lower_ai < upper_ai, f"{key} must prefer the GUI spelling"


def test_autopilot_keeps_the_uppercase_spellings_as_fallback():
    source = _run_bot_code()

    for key in ("AI_MONETARY_PATH", "AI_PERSONALITY", "AI_AUTOPILOT_INTERVAL_MINS"):
        assert f'_ai.get("{key}"' in source


def test_config_mtime_advances_only_after_a_successful_reload():
    block = _hot_reload_block()

    reload_call = block.index("settings = reload_settings()")
    mtime_commit = block.index("last_config_mtime = current_mtime")

    assert reload_call < mtime_commit, (
        "advancing last_config_mtime before reload_settings() succeeds means a "
        "malformed config is never retried and the old settings keep trading"
    )
