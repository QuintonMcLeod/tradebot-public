from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from helpers import make_test_profile
from tradebot_sci.strategy.decisions import close_position_decision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.profiles import build_profile
from tradebot_sci.market.models import MarketSnapshot, TrendState, Candle
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.broker.position_hold_store import PositionHoldRecord, PositionHoldStore


class FakeAIClient(TradeSciAIClient):
    def __init__(self):
        pass

    def generate_decision(self, context):
        return None


class MockPositionHoldStore:
    def __init__(self):
        self.records = {}
        self.save_called = 0
        self.upsert_called = 0

    def get(self, symbol):
        return self.records.get(symbol.upper())

    def upsert(self, symbol, opened_at, stop_loss=None, entry_price=None, take_profit=None, size=None, strategy=None):
        self.upsert_called += 1
        rec = PositionHoldRecord(
            symbol=symbol.upper(),
            opened_at=opened_at.isoformat() if hasattr(opened_at, 'isoformat') else opened_at,
            stop_loss=stop_loss,
            entry_price=entry_price,
            take_profit=take_profit,
            size=size,
            strategy=strategy,
            mfe_usd=0.0,
            mae_usd=0.0
        )
        self.records[symbol.upper()] = rec
        self.save()

    def save(self):
        self.save_called += 1

    def record_exit_with_result(self, symbol, is_win, strategy=None):
        pass

    def remove(self, symbol):
        self.records.pop(symbol.upper(), None)


def _make_profile(**overrides):
    return make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        **overrides,
    )


def test_engine_mfe_mae_bootstrapping_and_save(monkeypatch):
    """Verify that the engine bootstraps a missing position hold record and immediately saves to disk."""
    now = datetime.now(timezone.utc)
    def_candles = [Candle(timestamp=now - timedelta(minutes=5), open=100.0, high=105.0, low=95.0, close=102.0, volume=1000)]

    class FixedProvider:
        def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
            return MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                candles=def_candles,
                trend_htf=TrendState(direction="long", strength=1.0),
                trend_ltf=TrendState(direction="long", strength=1.0),
            )

    class MockBroker:
        def __init__(self):
            self.position_hold_store = MockPositionHoldStore()

    broker = MockBroker()
    provider = FixedProvider()
    profile = build_profile("intraday")
    
    # Isolate engine from running exits
    import tradebot_sci.strategy.exit_logic as exit_logic_module
    monkeypatch.setattr(exit_logic_module, "run_universal_exit_logic", lambda *args, **kwargs: None)

    engine = StrategyEngine(
        ai_client=FakeAIClient(),
        market_provider=provider,
        profile=profile,
        symbol="SPY",
        broker=broker
    )

    open_pos = {
        "symbol": "SPY",
        "side": "long",
        "entry_price": 100.0,
        "entry_time": (now - timedelta(minutes=10)).isoformat(),
        "size": 10.0,
    }

    # Verify no record exists initially
    assert broker.position_hold_store.get("SPY") is None

    # Run decide - it should bootstrap the record
    snapshot = provider.get_latest_snapshot("SPY", profile.candle_timeframe)
    engine.decide(timeframe=profile.candle_timeframe, open_position=open_pos, snapshot=snapshot)

    # Verify record was bootstrapped
    hold_rec = broker.position_hold_store.get("SPY")
    assert hold_rec is not None
    assert hold_rec.entry_price == 100.0
    assert hold_rec.size == 10.0
    assert broker.position_hold_store.upsert_called == 1
    
    # Verify save was called (once in upsert, and once for the subsequent MFE/MAE update)
    assert broker.position_hold_store.save_called == 2

    # Check MFE/MAE value calculation:
    # entry_price = 100.0, size = 10.0, current_price = 102.0
    # floating_gross_raw = (102.0 - 100.0) * 10 = 20.0
    # So mfe_usd should be 20.0, mae_usd should be 0.0
    assert hold_rec.mfe_usd == 20.0
    assert hold_rec.mae_usd == 0.0


def test_oanda_failsafe_seeding_loss(monkeypatch):
    """Verify that OandaBroker seeds MAE when a losing trade finishes but MFE/MAE are 0.0."""
    pytest.importorskip("oandapyV20")
    from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
    from oandapyV20.endpoints import positions

    # Mock oanda client request handling
    class MockClient:
        def request(self, req):
            if isinstance(req, positions.PositionDetails):
                req.response = {
                    "position": {
                        "unrealizedPL": "-50.0",
                        "long": {"units": "100", "averagePrice": "1.1000"},
                        "short": {"units": "0", "averagePrice": "0"}
                    }
                }
            elif isinstance(req, positions.PositionClose):
                req.response = {
                    "longOrderFillTransaction": {
                        "pl": "-50.0",
                        "financing": "0.0",
                        "dividendAdjustment": "0.0"
                    }
                }

    mock_trade_results = MagicMock()
    mock_store = MockPositionHoldStore()
    
    # Add a hold record with both MFE and MAE set to 0.0
    mock_store.upsert("EURUSD", datetime.now(timezone.utc), entry_price=1.1000, size=100.0)
    
    with patch.object(OandaExchangeBroker, "_discover_and_validate_account", return_value=None):
        broker = OandaExchangeBroker(
            account_id="001-001-FAKE-001",
            api_key="fake_key",
            profile_settings=_make_profile(read_only=False),
            environment="practice",
            read_only=False,
            trade_results=mock_trade_results,
        )
    
    broker.client = MockClient()
    broker.position_hold_store = mock_store
    broker._tracked_positions["EURUSD"] = {"entry_time": datetime.now(timezone.utc).isoformat()}
    
    # Call flatten_symbol which triggers TradeResult addition
    broker.flatten_symbol("EURUSD")
    
    # Verify that add_result was called with seeded mae_usd=-50.0 and mfe_usd=0.0
    mock_trade_results.add_result.assert_called_once()
    trade_result = mock_trade_results.add_result.call_args[0][0]
    assert trade_result.pnl_usd == -50.0
    assert trade_result.mae_usd == -50.0
    assert trade_result.mfe_usd == 0.0


def test_oanda_failsafe_seeding_win(monkeypatch):
    """Verify that OandaBroker seeds MFE when a winning trade finishes but MFE/MAE are 0.0."""
    pytest.importorskip("oandapyV20")
    from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
    from oandapyV20.endpoints import positions

    # Mock oanda client request handling
    class MockClient:
        def request(self, req):
            if isinstance(req, positions.PositionDetails):
                req.response = {
                    "position": {
                        "unrealizedPL": "50.0",
                        "long": {"units": "100", "averagePrice": "1.1000"},
                        "short": {"units": "0", "averagePrice": "0"}
                    }
                }
            elif isinstance(req, positions.PositionClose):
                req.response = {
                    "longOrderFillTransaction": {
                        "pl": "50.0",
                        "financing": "0.0",
                        "dividendAdjustment": "0.0"
                    }
                }

    mock_trade_results = MagicMock()
    mock_store = MockPositionHoldStore()
    
    # Add a hold record with both MFE and MAE set to 0.0
    mock_store.upsert("EURUSD", datetime.now(timezone.utc), entry_price=1.1000, size=100.0)
    
    with patch.object(OandaExchangeBroker, "_discover_and_validate_account", return_value=None):
        broker = OandaExchangeBroker(
            account_id="001-001-FAKE-001",
            api_key="fake_key",
            profile_settings=_make_profile(read_only=False),
            environment="practice",
            read_only=False,
            trade_results=mock_trade_results,
        )
    
    broker.client = MockClient()
    broker.position_hold_store = mock_store
    broker._tracked_positions["EURUSD"] = {"entry_time": datetime.now(timezone.utc).isoformat()}
    
    # Call flatten_symbol which triggers TradeResult addition
    broker.flatten_symbol("EURUSD")
    
    # Verify that add_result was called with seeded mfe_usd=50.0 and mae_usd=0.0
    mock_trade_results.add_result.assert_called_once()
    trade_result = mock_trade_results.add_result.call_args[0][0]
    assert trade_result.pnl_usd == 50.0
    assert trade_result.mae_usd == 0.0
    assert trade_result.mfe_usd == 50.0


@patch("tradebot_sci.broker.ccxt_broker.ccxt")
def test_ccxt_failsafe_seeding_win(mock_ccxt, monkeypatch):
    """Verify that CCXTExchangeBroker seeds MFE when a winning trade finishes but MFE/MAE are 0.0."""
    from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
    
    mock_exchange = MagicMock()
    mock_exchange.load_markets.return_value = {}
    mock_exchange.markets = {}
    mock_exchange.id = "gemini"
    mock_ccxt.gemini.return_value = mock_exchange

    mock_trade_results = MagicMock()
    mock_store = MockPositionHoldStore()
    
    # Add a hold record with both MFE and MAE set to 0.0
    mock_store.upsert("BTCUSD", datetime.now(timezone.utc), entry_price=50000.0, size=1.0)

    profile = _make_profile()
    with patch.dict("os.environ", {
        "CCXT_EXCHANGE": "gemini",
        "CCXT_API_KEY": "test_key",
        "CCXT_API_SECRET": "test_secret",
    }):
        broker = CCXTExchangeBroker(profile)
    
    broker.trade_results = mock_trade_results
    broker.position_hold_store = mock_store
    
    # Mock CCXT specific methods
    monkeypatch.setattr(broker, "_is_crypto", lambda sym: True)
    monkeypatch.setattr(broker, "_map_symbol", lambda sym: "BTC/USD")
    monkeypatch.setattr(broker, "cancel_all_orders_for_symbol", lambda sym: None)
    monkeypatch.setattr(broker, "_ccxt_create_order", lambda *args, **kwargs: None)
    
    # mock get_open_position_snapshot to return a long position where current_price > entry_price
    # entry_price = 50000.0, current_price = 55000.0, size = 1.0
    # pnl = (55000 - 50000) * 1.0 = 5000.0
    # fee estimated = 50000 * 1.0 * 0.008 = 400.0
    # net pnl_val = 4600.0 > 0 (win)
    monkeypatch.setattr(broker, "get_open_position_snapshot", lambda sym: {
        "symbol": "BTCUSD",
        "size": 1.0,
        "entry_price": 50000.0,
        "current_price": 55000.0,
    })
    
    broker.flatten_symbol("BTCUSD")
    
    # Verify that add_result was called with seeded mfe_usd = 4600.0 and mae_usd = 0.0
    mock_trade_results.add_result.assert_called_once()
    trade_result = mock_trade_results.add_result.call_args[0][0]
    assert trade_result.pnl_usd == 4600.0
    assert trade_result.mae_usd == 0.0
    assert trade_result.mfe_usd == 4600.0


def test_oanda_failsafe_seeding_bounding(monkeypatch):
    """Verify that OandaBroker bounds existing non-zero MFE/MAE excursions with the final PnL on exit."""
    pytest.importorskip("oandapyV20")
    from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
    from oandapyV20.endpoints import positions

    # Mock client
    class MockClient:
        def request(self, req):
            if isinstance(req, positions.PositionDetails):
                req.response = {
                    "position": {
                        "unrealizedPL": "50.0",
                        "long": {"units": "100", "averagePrice": "1.1000"},
                        "short": {"units": "0", "averagePrice": "0"}
                    }
                }
            elif isinstance(req, positions.PositionClose):
                req.response = {
                    "longOrderFillTransaction": {
                        "pl": "50.0",
                        "financing": "0.0",
                        "dividendAdjustment": "0.0"
                    }
                }

    mock_trade_results = MagicMock()
    mock_store = MockPositionHoldStore()
    
    # Set MFE to a value lower than final PnL (20.0 < 50.0)
    mock_store.upsert("EURUSD", datetime.now(timezone.utc), entry_price=1.1000, size=100.0)
    rec = mock_store.get("EURUSD")
    rec.mfe_usd = 20.0
    rec.mae_usd = -10.0
    
    with patch.object(OandaExchangeBroker, "_discover_and_validate_account", return_value=None):
        broker = OandaExchangeBroker(
            account_id="001-001-FAKE-001",
            api_key="fake_key",
            profile_settings=_make_profile(read_only=False),
            environment="practice",
            read_only=False,
            trade_results=mock_trade_results,
        )
    
    broker.client = MockClient()
    broker.position_hold_store = mock_store
    broker._tracked_positions["EURUSD"] = {"entry_time": datetime.now(timezone.utc).isoformat()}
    
    # Call flatten_symbol
    broker.flatten_symbol("EURUSD")
    
    # Verify MFE bounded to final PnL 50.0, and MAE remains -10.0
    mock_trade_results.add_result.assert_called_once()
    trade_result = mock_trade_results.add_result.call_args[0][0]
    assert trade_result.pnl_usd == 50.0
    assert trade_result.mfe_usd == 50.0
    assert trade_result.mae_usd == -10.0
