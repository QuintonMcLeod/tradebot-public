"""Regression tests for the Seasoned Trader autopilot.

Every test here isolates the daemon from the real environment: config paths,
data directories and the profiles YAML are redirected into tmp_path, and no
test performs a network call or reads credentials.
"""
import json
import threading
import time

import pytest

from tradebot_sci.ai import seasoned_trader as st
from tradebot_sci.ai.seasoned_trader import SeasonedTraderDaemon
from tradebot_sci.config.loader import _REAL_PROFILE_KEYS
from tradebot_sci.runtime.controller import RuntimeController


# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeMemory:
    def __init__(self):
        self.notes = []
        self.actions = []

    def add_note(self, content):
        self.notes.append(content)

    def record_action(self, action_type, details):
        self.actions.append((action_type, details))

    def get_contextual_memory(self):
        return ""

    def save(self):
        pass


class FakeAI:
    """Minimal stand-in for the cognitive backend."""

    def __init__(self, response="{}", error=None):
        self._response = response
        self._error = error
        self.raw_chat_calls = 0

    def raw_chat(self, messages, expect_json=False):
        self.raw_chat_calls += 1
        if self._error is not None:
            raise self._error
        return self._response

    def generate_text(self, messages):
        return "briefing"


class FakeNews:
    def get_latest_news_context(self):
        return ""


class FakeController:
    def __init__(self):
        self.halt_reasons = []
        self.resume_calls = 0
        self._halted = False
        self.replay_provider = None
        self.ws_server = None

    def halt(self, reason=""):
        self.halt_reasons.append(reason)
        self._halted = True
        return True

    def resume(self):
        self.resume_calls += 1
        self._halted = False
        return True

    def is_halted(self):
        return self._halted


def _decision(**overrides):
    payload = {
        "analysis": "test analysis",
        "proposed_interval_mins": 30,
        "trigger_kill_switch": False,
        "adjust_settings": {},
        "bypass_strategy_routing": "",
        "memory_note_for_next_cycle": "",
        "profile_actions": [],
        "schedule_actions": [],
        "change_explanation": "",
        "insight_commentary": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Redirect the daemon's config.json into tmp_path."""
    path = tmp_path / "config.json"
    monkeypatch.setattr(st, "CONFIG_FILE", path)
    return path


@pytest.fixture
def profiles_paths(tmp_path, monkeypatch):
    """Keep profile mirroring away from the real home config directory."""
    yaml_path = tmp_path / "settings_profiles.yaml"
    monkeypatch.setattr(st, "PROFILES_YAML", yaml_path)
    monkeypatch.setattr(st, "_LEGACY_PROFILES", tmp_path / "legacy_profiles.yaml")
    return yaml_path


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Redirect every data path the daemon reads into tmp_path."""
    import tradebot_sci.paths as paths

    directory = tmp_path / "data"
    directory.mkdir(exist_ok=True)
    monkeypatch.setattr(st, "DATA_DIR", directory)
    monkeypatch.setattr(paths, "DATA_DIR", directory)
    monkeypatch.setattr(paths, "USER_DATA_DIR", tmp_path / "userdata")
    return directory


@pytest.fixture
def broadcasts():
    """Collects everything the daemon would push to the commentary feed."""
    collected = []

    def _record(text, *args, **kwargs):
        collected.append(text)

    return collected


@pytest.fixture
def make_daemon(monkeypatch, broadcasts):
    """Build a daemon with no threads, no network and no real files."""
    monkeypatch.setattr(st, "RSSNewsScraper", FakeNews)
    monkeypatch.setattr(st, "SentinelMemory", FakeMemory)

    def _factory(ai_client=None, controller=None, interval_mins=30, stub_state=True):
        daemon = SeasonedTraderDaemon(
            ai_client=ai_client or FakeAI(_decision()),
            config_payload={"AI_AUTOPILOT_INTERVAL_MINS": interval_mins},
            controller=controller,
        )
        daemon.memory = FakeMemory()
        daemon.news_scraper = FakeNews()
        if stub_state:
            daemon._build_system_state_payload = lambda: "STATE"
            daemon._get_sabbath_status = lambda config=None: {"enabled": False, "active": False}
        daemon._broadcast_change_commentary = broadcasts.append
        return daemon

    return _factory


def _actions(daemon, action_type):
    return [details for kind, details in daemon.memory.actions if kind == action_type]


# ── Item 1: config destruction and unvalidated writes ───────────────────────


def test_unparsable_config_is_not_overwritten(make_daemon, config_file):
    """A transient parse failure must abort the mutation, not replace the file."""
    garbage = "{ this is not valid json"
    config_file.write_text(garbage)

    result = make_daemon()._apply_settings_adjustments({"RISK_PER_TRADE_PCT": 0.02})

    assert config_file.read_text() == garbage
    assert result["applied"] == {}
    assert result["rejected"], "the refused adjustment must be reported"


def test_non_object_config_is_not_overwritten(make_daemon, config_file):
    config_file.write_text(json.dumps(["not", "an", "object"]))

    result = make_daemon()._apply_settings_adjustments({"RISK_PER_TRADE_PCT": 0.02})

    assert json.loads(config_file.read_text()) == ["not", "an", "object"]
    assert result["applied"] == {}


def test_write_config_is_atomic_on_serialisation_failure(make_daemon, config_file):
    """A non-serialisable value must leave the previous file intact."""
    original = {"ai": {"api_key": "SECRET"}, "risk": {"risk_per_trade_pct": 0.01}}
    config_file.write_text(json.dumps(original))
    daemon = make_daemon()

    written = daemon._write_config({"ai": {"api_key": "SECRET"}, "bad": object()})

    assert written is False
    assert json.loads(config_file.read_text()) == original
    assert not list(config_file.parent.glob("*.tmp")), "no temporary file may be left behind"


def test_write_profiles_is_atomic_on_serialisation_failure(make_daemon, profiles_paths):
    profiles_paths.write_text("profiles:\n  keep:\n    strategy_variant: meta_sci\n")
    original = profiles_paths.read_text()
    daemon = make_daemon()

    # A lock cannot be represented in YAML, so the dump fails mid-write.
    written = daemon._write_profiles({"bad": threading.Lock()})

    assert written is False
    assert profiles_paths.read_text() == original
    assert not list(profiles_paths.parent.glob("*.tmp"))


def test_read_config_for_write_distinguishes_missing_from_broken(make_daemon, config_file):
    daemon = make_daemon()
    # Missing file: creating one is correct.
    assert daemon._read_config_for_write() == {}

    config_file.write_text("{ broken")
    assert daemon._read_config_for_write() is None
    # Read-only consumers still degrade to an empty dict.
    assert daemon._read_config() == {}


# ── Item 2: settings allowlist, bounds and honest reporting ─────────────────


@pytest.mark.parametrize(
    "key",
    [
        "NUCLEAR_OVERRIDES_ENABLED",
        "MAX_RISK_CAP_OVERRIDE",
        "EXECUTE_TRADES",
        "SABBATH_ENABLED",
        "SAFETY_FEE_SHIELD_ENABLED",
        "SAFETY_DRAWDOWN_MAX_PCT",
        "SESSION_GATE_ENABLED",
        "SMART_POSITIONS_ENABLED",
    ],
)
def test_safety_critical_keys_are_refused(make_daemon, config_file, key):
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))
    daemon = make_daemon()

    result = daemon._apply_settings_adjustments({key: True})

    assert result["applied"] == {}
    assert [r["key"] for r in result["rejected"]] == [key]
    written = json.loads(config_file.read_text())
    assert written == {"risk": {"risk_per_trade_pct": 0.01}}


def test_lowercase_key_still_maps(make_daemon, config_file):
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))

    result = make_daemon()._apply_settings_adjustments({"risk_per_trade_pct": "0.02"})

    assert result["applied"] == {"RISK_PER_TRADE_PCT": 0.02}
    assert json.loads(config_file.read_text())["risk"]["risk_per_trade_pct"] == 0.02


def test_unknown_key_is_rejected_and_reported(make_daemon, config_file):
    config_file.write_text(json.dumps({}))

    result = make_daemon()._apply_settings_adjustments({"NOT_A_REAL_SETTING": 1})

    assert result["applied"] == {}
    assert result["rejected"][0]["key"] == "NOT_A_REAL_SETTING"


def test_out_of_bounds_value_rejects_the_whole_set(make_daemon, config_file):
    """One invalid value must not leave a half-applied adjustment behind."""
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))

    result = make_daemon()._apply_settings_adjustments(
        {"risk_per_trade_pct": 0.02, "MAX_EXPOSURE_PCT": 200}
    )

    assert result["applied"] == {}
    assert {r["key"] for r in result["rejected"]} == {"RISK_PER_TRADE_PCT", "MAX_EXPOSURE_PCT"}
    assert json.loads(config_file.read_text()) == {"risk": {"risk_per_trade_pct": 0.01}}


def test_applied_outcome_records_only_written_keys(make_daemon, config_file, broadcasts):
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))
    daemon = make_daemon(ai_client=FakeAI(_decision(
        adjust_settings={"risk_per_trade_pct": 0.02, "NUCLEAR_OVERRIDES_ENABLED": True},
        change_explanation="I raised the risk cap and enabled nuclear mode.",
    )))

    daemon._evaluate_and_adjust()

    text = "\n".join(broadcasts)
    assert "Applied settings: RISK_PER_TRADE_PCT=0.02" not in text
    assert "NUCLEAR_OVERRIDES_ENABLED" in text
    assert "not applied as written" in text
    assert _actions(daemon, "SETTINGS_UPDATE") == []


def test_successful_adjustment_is_broadcast_and_recorded(make_daemon, config_file, broadcasts):
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))
    daemon = make_daemon(ai_client=FakeAI(_decision(
        adjust_settings={"risk_per_trade_pct": 0.02},
        change_explanation="Tightening risk.",
    )))

    daemon._evaluate_and_adjust()

    text = "\n".join(broadcasts)
    assert "Applied settings: RISK_PER_TRADE_PCT=0.02" in text
    assert _actions(daemon, "SETTINGS_UPDATE") == [{"RISK_PER_TRADE_PCT": 0.02}]
    assert json.loads(config_file.read_text())["risk"]["risk_per_trade_pct"] == 0.02


# ── Item 3: profiles that the loader would refuse ───────────────────────────


def test_create_profile_drops_keys_the_loader_rejects(make_daemon, config_file, profiles_paths):
    config_file.write_text(json.dumps({"profiles": {}}))

    daemon = make_daemon()
    created = daemon._create_profile("new_profile", {
        "symbols": ["EUR_USD"],
        "session_gate_enabled": True,
        "crypto_only": True,
        "winner_giveback_pct": 0.3,
        "not_a_real_key": 1,
    })

    assert created is True
    profile = json.loads(config_file.read_text())["profiles"]["new_profile"]
    assert "session_gate_enabled" not in profile
    assert "crypto_only" not in profile
    assert "winner_giveback_pct" not in profile
    assert "not_a_real_key" not in profile
    # The loader raises a fatal error on any key outside its whitelist.
    assert set(profile) <= _REAL_PROFILE_KEYS


def test_create_profile_defaults_are_all_whitelisted(make_daemon, config_file, profiles_paths):
    config_file.write_text(json.dumps({"profiles": {}}))

    make_daemon()._create_profile("plain", {})

    profile = json.loads(config_file.read_text())["profiles"]["plain"]
    assert set(profile) <= _REAL_PROFILE_KEYS


def test_modify_profile_drops_keys_the_loader_rejects(make_daemon, config_file, profiles_paths):
    config_file.write_text(json.dumps({"profiles": {"base": {"strategy_variant": "meta_sci"}}}))

    daemon = make_daemon()
    assert daemon._modify_profile("base", {"symbols": ["GBP_USD"], "session_gate_enabled": False}) is True

    profile = json.loads(config_file.read_text())["profiles"]["base"]
    assert profile["symbols"] == ["GBP_USD"]
    assert "session_gate_enabled" not in profile


def test_profile_reference_advertises_only_whitelisted_keys():
    for key in st.SENTINEL_PROFILE_REFERENCE:
        root = key.split(".", 1)[0]
        assert root in _REAL_PROFILE_KEYS, f"{key} is not a valid profile key"


def test_undecodable_config_aborts_profile_writes(make_daemon, config_file, profiles_paths):
    config_file.write_text("{ broken")
    daemon = make_daemon()

    assert daemon._create_profile("new_profile", {"symbols": []}) is False
    assert config_file.read_text() == "{ broken"


# ── Item 4: the synthetic pre-flight gate ───────────────────────────────────


def test_preflight_rejects_safety_critical_key(make_daemon):
    assert make_daemon()._execute_synthetic_preflight({"NUCLEAR_OVERRIDES_ENABLED": True}) is False


def test_preflight_rejects_unsafe_risk_combination(make_daemon):
    """0.9 validates against the field bounds but exceeds the exposure cap."""
    daemon = make_daemon()

    assert daemon._execute_synthetic_preflight({"RISK_PER_TRADE_PCT": 0.9}) is False
    assert daemon._execute_synthetic_preflight({"MAX_EXPOSURE_PCT": 200}) is False
    assert daemon._execute_synthetic_preflight({"RISK_PER_TRADE_PCT": 0.02}) is True


def test_preflight_does_not_sleep_or_write(make_daemon, config_file, monkeypatch):
    config_file.write_text(json.dumps({"risk": {"risk_per_trade_pct": 0.01}}))
    sleeps = []
    monkeypatch.setattr(st.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert make_daemon()._execute_synthetic_preflight({"RISK_PER_TRADE_PCT": 0.02}) is True

    assert sleeps == []
    assert json.loads(config_file.read_text()) == {"risk": {"risk_per_trade_pct": 0.01}}


# ── Item 5: the kill switch must actually halt ──────────────────────────────


def test_kill_switch_calls_controller_halt(make_daemon, broadcasts):
    controller = FakeController()
    daemon = make_daemon(
        ai_client=FakeAI(_decision(trigger_kill_switch=True, analysis="flash crash")),
        controller=controller,
    )

    daemon._evaluate_and_adjust()

    assert controller.is_halted() is True
    assert controller.halt_reasons, "the controller halt must be invoked"
    assert "KILL SWITCH ACTIVATED" in "\n".join(broadcasts)
    assert _actions(daemon, "KILL_SWITCH")


def test_kill_switch_without_halt_mechanism_reports_that_trading_continues(make_daemon, broadcasts):
    daemon = make_daemon(
        ai_client=FakeAI(_decision(trigger_kill_switch=True, analysis="flash crash")),
        controller=None,
    )

    daemon._evaluate_and_adjust()

    text = "\n".join(broadcasts)
    assert "TRADING IS STILL RUNNING" in text.upper()
    assert "KILL SWITCH ACTIVATED" not in text
    assert _actions(daemon, "KILL_SWITCH_FAILED")


def test_ws_server_set_halted_drives_is_halted():
    from tradebot_sci.server.ws_server import WebSocketServer

    server = WebSocketServer()

    assert server.is_halted() is False
    assert server.set_halted(True, "test") is True
    assert server.is_halted() is True
    assert server.set_halted(False, "test") is False
    assert server.is_halted() is False


def test_controller_halt_and_resume_delegate_to_ws_server():
    controller = RuntimeController.__new__(RuntimeController)
    controller.ws_server = None
    assert controller.halt("no server") is False
    assert controller.resume() is False

    from tradebot_sci.server.ws_server import WebSocketServer

    controller.ws_server = WebSocketServer()
    assert controller.halt("prop firm failed") is True
    assert controller.is_halted() is True
    assert controller.resume() is True
    assert controller.is_halted() is False


# ── Item 6: Sabbath status from the safety section ──────────────────────────


def test_sabbath_status_reads_the_safety_section(make_daemon):
    daemon = make_daemon()

    status = SeasonedTraderDaemon._get_sabbath_status(
        daemon,
        {"safety": {"sabbath_enabled": True, "sabbath_timezone": "America/New_York",
                    "sabbath_astronomical": False}},
    )

    assert status["enabled"] is True


def test_sabbath_status_safety_section_wins_over_legacy_keys(make_daemon):
    daemon = make_daemon()

    status = SeasonedTraderDaemon._get_sabbath_status(
        daemon,
        {
            "safety": {"sabbath_enabled": False},
            "schedule": {"sabbath_enabled": True},
            "global": {"sabbath_enabled": True},
        },
    )

    assert status["enabled"] is False


def test_sabbath_status_falls_back_when_safety_section_is_absent(make_daemon):
    daemon = make_daemon()

    status = SeasonedTraderDaemon._get_sabbath_status(
        daemon, {"global": {"sabbath_enabled": True}}
    )

    assert status["enabled"] is True


# ── Item 7: 24h performance from the real ledger schema ─────────────────────


def _ledger_with_trades(tmp_path):
    from datetime import datetime, timedelta

    now = datetime.now()
    recent = (now - timedelta(hours=2)).isoformat()
    stale = (now - timedelta(hours=72)).isoformat()
    return {
        "version": 2,
        "current_day": {"trade_log": [
            {"symbol": "EUR_USD", "pnl": 25.0, "closed_at": recent},
            {"symbol": "GBP_USD", "pnl": -10.0, "closed_at": recent},
        ]},
        "days": [
            {"trade_log": [
                {"symbol": "USD_JPY", "pnl": 5.0, "closed_at": recent},
                {"symbol": "AUD_USD", "pnl": 900.0, "closed_at": stale},
            ]},
        ],
    }


def test_24h_performance_reads_the_real_ledger_schema(make_daemon, tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(_ledger_with_trades(tmp_path)))

    wins, losses, pnl = make_daemon()._summarise_24h_performance(ledger)

    assert (wins, losses) == (2, 1)
    assert pnl == pytest.approx(20.0)


def test_24h_performance_tolerates_missing_and_malformed_ledgers(make_daemon, tmp_path):
    daemon = make_daemon()

    assert daemon._summarise_24h_performance(tmp_path / "absent.json") == (0, 0, 0.0)

    broken = tmp_path / "broken.json"
    broken.write_text("{ not json")
    assert daemon._summarise_24h_performance(broken) == (0, 0, 0.0)

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"current_day": {}, "days": []}))
    assert daemon._summarise_24h_performance(empty) == (0, 0, 0.0)


def test_ledger_entries_accept_legacy_shapes(make_daemon):
    daemon = make_daemon()

    assert daemon._ledger_trade_entries([{"pnl": 1}]) == [{"pnl": 1}]
    assert daemon._ledger_trade_entries({"trades": [{"pnl": 2}]}) == [{"pnl": 2}]
    assert daemon._ledger_trade_entries("nonsense") == []


# ── Item 8: open positions follow the trading mode ──────────────────────────


def test_open_positions_follow_the_trading_mode(make_daemon, data_dir):
    (data_dir / "paper_state.json").write_text(
        json.dumps({"positions": {"PAPER_ONE": {"entry_price": 1.0}}})
    )
    (data_dir / "state.json").write_text(
        json.dumps({"positions": {"LIVE_ONE": {"entry_price": 2.0}}})
    )
    daemon = make_daemon()

    live = daemon._read_open_positions(True)
    paper = daemon._read_open_positions(False)

    assert [p["symbol"] for p in live] == ["LIVE_ONE"]
    assert [p["symbol"] for p in paper] == ["PAPER_ONE"]


def test_open_positions_prefer_the_controller_snapshot(make_daemon, data_dir):
    class _Executor:
        def list_open_position_symbols(self):
            return ["CTRL_ONE"]

        def get_open_position_snapshot(self, symbol):
            return {"entry_price": 3.0}

    controller = FakeController()
    controller.executor_real = _Executor()
    (data_dir / "state.json").write_text(
        json.dumps({"positions": {"LIVE_ONE": {"entry_price": 2.0}}})
    )

    positions = make_daemon(controller=controller)._read_open_positions(True)

    assert [p["symbol"] for p in positions] == ["CTRL_ONE"]


# ── Items 9 and 10: prop tier, brokers and the OANDA environment ────────────


@pytest.fixture
def payload_daemon(make_daemon, config_file, data_dir, monkeypatch):
    """A daemon whose state payload can be built without I/O or network."""
    def _factory(config):
        config_file.write_text(json.dumps(config))
        daemon = make_daemon(stub_state=False)
        daemon._build_market_data_payload = lambda *a, **k: ""
        daemon._build_analytics_payload = lambda: ""
        daemon._get_sabbath_status = lambda cfg=None: {"enabled": False, "active": False}
        return daemon

    return _factory


def test_prop_firm_tier_is_read_from_the_risk_section(payload_daemon):
    daemon = payload_daemon({
        "global": {"execute_trades": False},
        "risk": {"prop_challenge_tier_usd": 50000.0, "prop_challenge_max_loss_pct": 0.06},
    })

    payload = daemon._build_system_state_payload()

    assert "PROP FIRM EVALUATION" in payload
    assert "Tier: $50,000.00" in payload


def test_exchange_list_reads_the_brokers_section(payload_daemon):
    daemon = payload_daemon({
        "global": {"execute_trades": False},
        "brokers": {"oanda": {"account_id": "101-004-1234567-001", "environment": "live"}},
    })

    payload = daemon._build_system_state_payload()

    assert "Connected Exchanges: OANDA (Forex/Metals/Indices)\n" in payload + "\n"
    assert "assumed default" not in payload


def test_24h_performance_appears_in_the_state_payload(payload_daemon, data_dir):
    (data_dir / "paper_ledger.json").write_text(json.dumps(_ledger_with_trades(data_dir)))
    daemon = payload_daemon({"global": {"execute_trades": False}})

    payload = daemon._build_system_state_payload()

    assert "24h Performance: 2 Wins / 1 Losses | Net PnL: $20.00" in payload


def test_oanda_environment_comes_from_the_brokers_section(make_daemon, config_file, monkeypatch):
    """A live account whose ID lacks the 001- prefix must not get a practice provider."""
    from tradebot_sci.market import oanda_provider

    created = {}

    class FakeProvider:
        def __init__(self, account_id, api_key, environment):
            created["environment"] = environment

    monkeypatch.setattr(oanda_provider, "OandaMarketDataProvider", FakeProvider)
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "999-999-9999999-999")
    monkeypatch.setenv("OANDA_API_KEY", "fake-key")
    config = {
        "runtime": {"execute_trades": True},
        "brokers": {"oanda": {"account_id": "999-999-9999999-999", "environment": "live"}},
    }

    provider = make_daemon()._get_market_provider(config)

    assert provider is not None
    assert created["environment"] == "live"


# ── Items 12, 13, 14: error classification and value coercion ───────────────


@pytest.mark.parametrize(
    "error, expected",
    [
        (json.JSONDecodeError("Expecting value", "", 0), "PARSE ERROR"),
        (RuntimeError("401 Unauthorized: invalid api key"), "AUTH ERROR"),
        (RuntimeError("HTTPSConnectionPool: connection timed out"), "NETWORK ERROR"),
        (RuntimeError("429 Too Many Requests: rate limit exceeded"), "RATE LIMITED"),
        (KeyError("unexpected"), "INTERNAL ERROR"),
    ],
)
def test_error_classification(error, expected):
    headline, _detail = SeasonedTraderDaemon._classify_evaluation_error(error)
    assert expected in headline


def test_internal_error_is_not_reported_as_a_credential_problem(make_daemon, broadcasts):
    daemon = make_daemon(ai_client=FakeAI(error=KeyError("internal state missing")))

    daemon._evaluate_and_adjust()

    text = "\n".join(broadcasts)
    assert "INTERNAL ERROR" in text
    assert "API Keys" not in text


def test_malformed_response_is_reported_as_a_parse_error(make_daemon, broadcasts):
    daemon = make_daemon(ai_client=FakeAI(response="this is not json at all"))

    daemon._evaluate_and_adjust()

    assert "PARSE ERROR" in "\n".join(broadcasts)


def test_payload_failure_is_caught_and_reported(make_daemon, broadcasts):
    daemon = make_daemon(stub_state=False)

    def _boom():
        raise RuntimeError("ledger exploded")

    daemon._build_system_state_payload = _boom
    daemon._evaluate_and_adjust()

    assert "INTERNAL ERROR" in "\n".join(broadcasts)


def test_boolean_interval_is_rejected(make_daemon):
    daemon = make_daemon(ai_client=FakeAI(_decision(proposed_interval_mins=True)))

    daemon._evaluate_and_adjust()

    assert daemon.interval_mins == 30


def test_numeric_interval_is_accepted(make_daemon):
    daemon = make_daemon(ai_client=FakeAI(_decision(proposed_interval_mins=45)))

    daemon._evaluate_and_adjust()

    assert daemon.interval_mins == 45


def test_string_schedule_index_is_coerced(make_daemon, config_file, broadcasts):
    sessions = [
        {"profile_name": "a", "start_time": "09:00", "end_time": "17:00"},
        {"profile_name": "b", "start_time": "09:00", "end_time": "17:00"},
    ]
    config_file.write_text(json.dumps({"schedule": {"sessions": sessions}}))
    daemon = make_daemon(ai_client=FakeAI(_decision(
        schedule_actions=[{"action": "delete_session", "index": "1"}],
    )))

    daemon._evaluate_and_adjust()

    remaining = json.loads(config_file.read_text())["schedule"]["sessions"]
    assert [s["profile_name"] for s in remaining] == ["a"]


def test_bad_schedule_index_does_not_abort_later_actions(make_daemon, config_file):
    config_file.write_text(json.dumps({"schedule": {"sessions": [
        {"profile_name": "a", "start_time": "09:00", "end_time": "17:00"},
    ]}}))
    daemon = make_daemon(ai_client=FakeAI(_decision(
        schedule_actions=[
            {"action": "delete_session", "index": "not-a-number"},
            {"action": "create_session", "profile_name": "late", "start_time": "01:00"},
        ],
    )))

    daemon._evaluate_and_adjust()

    names = [s["profile_name"] for s in json.loads(config_file.read_text())["schedule"]["sessions"]]
    assert names == ["a", "late"]


# ── Item 11: daemon lifetime ────────────────────────────────────────────────


def test_stop_is_safe_when_never_started(make_daemon):
    daemon = make_daemon()
    daemon.stop()
    daemon.stop(timeout=0.01)
    assert daemon.running is False


def test_stop_joins_the_running_thread(make_daemon):
    daemon = make_daemon()
    finished = threading.Event()

    def _worker():
        while daemon.running:
            time.sleep(0.01)
        finished.set()

    daemon.running = True
    thread = threading.Thread(target=_worker, daemon=True)
    daemon._thread = thread
    thread.start()

    daemon.stop(timeout=5.0)

    assert finished.is_set()
    assert not thread.is_alive()
    assert daemon._thread is None


def test_loop_survives_a_failing_cycle(make_daemon, monkeypatch, caplog):
    daemon = make_daemon()
    daemon.ws_server = type("_WS", (), {"clients": {1}})()
    daemon._broadcast_initial_briefing = lambda: None

    calls = []

    def _boom():
        calls.append(1)
        raise RuntimeError("cycle exploded")

    daemon._evaluate_and_adjust = _boom

    sleeps = []

    def _fake_sleep(_seconds):
        sleeps.append(_seconds)
        if len(sleeps) >= 2:
            daemon.running = False

    monkeypatch.setattr(st.time, "sleep", _fake_sleep)

    daemon.loop()

    assert calls, "the cycle must have been attempted"
    assert daemon.running is False
    assert "Evaluation cycle failed" in caplog.text


def test_thread_main_restarts_the_loop_after_a_crash(make_daemon, monkeypatch, caplog):
    daemon = make_daemon()
    attempts = []

    def _flaky_loop():
        attempts.append(1)
        if len(attempts) >= 3:
            daemon.running = False
            return
        raise RuntimeError("loop exploded")

    daemon.loop = _flaky_loop
    daemon.running = True
    monkeypatch.setattr(st.time, "sleep", lambda _seconds: None)

    daemon._thread_main()

    assert len(attempts) == 3
    assert "loop crashed" in caplog.text
