from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, List

from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci.broker.mock_exchange_broker import MockExchangeBroker
from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider
from tradebot_sci.market.providers import (
    CCXTMarketDataProvider,
    IbkrMarketDataProvider,
    MarketDataProvider,
    MockMarketDataProvider,
)
from tradebot_sci.market.symbols import is_crypto

if TYPE_CHECKING:
    from tradebot_sci.market.models import Candle, MarketSnapshot, OrderBook, Ticker

logger = logging.getLogger(__name__)


class HybridMarketDataProvider(MarketDataProvider):
    """Dispatches market data requests to either IBKR or an Alternative provider based on symbol."""

    def __init__(self, primary: MarketDataProvider, alternative: MarketDataProvider):
        self.primary = primary
        self.alternative = alternative

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        if is_crypto(symbol):
            return self.alternative.get_latest_candles(symbol, timeframe, limit)
        return self.primary.get_latest_candles(symbol, timeframe, limit)

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        if is_crypto(symbol):
            return self.alternative.get_latest_snapshot(symbol, timeframe)
        return self.primary.get_latest_snapshot(symbol, timeframe)

    def get_ticker(self, symbol: str) -> Ticker | None:
        if is_crypto(symbol):
            return self.alternative.get_ticker(symbol)
        return self.primary.get_ticker(symbol)

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        if is_crypto(symbol):
            return self.alternative.get_order_book(symbol, depth)
        return self.primary.get_order_book(symbol, depth)

    def close(self) -> None:
        self.primary.close()
        self.alternative.close()


class HybridExchangeBroker(IExchangeBroker):
    """Dispatches broker commands to either IBKR or an Alternative broker (CCXT) based on symbol."""

    def __init__(self, primary: IExchangeBroker, alternative: IExchangeBroker):
        self.primary = primary
        self.alternative = alternative

    def place_order(self, symbol: str, *args, **kwargs) -> Any:
        if is_crypto(symbol):
            return self.alternative.place_order(symbol, *args, **kwargs)
        return self.primary.place_order(symbol, *args, **kwargs)

    def cancel_order(self, symbol: str, *args, **kwargs) -> Any:
        if is_crypto(symbol):
            return self.alternative.cancel_order(symbol, *args, **kwargs)
        return self.primary.cancel_order(symbol, *args, **kwargs)

    def get_positions(self, *args, **kwargs) -> Any:
        p_pos = self.primary.get_positions(*args, **kwargs)
        a_pos = self.alternative.get_positions(*args, **kwargs)
        return p_pos + a_pos

    def get_open_orders(self, *args, **kwargs) -> Any:
        return self.primary.get_open_orders(*args, **kwargs) + self.alternative.get_open_orders(*args, **kwargs)

    def get_recent_fills(self, *args, **kwargs) -> Any:
        return self.primary.get_recent_fills(*args, **kwargs) + self.alternative.get_recent_fills(*args, **kwargs)


def _selected_mode(settings: Settings, key: str, legacy_key: str = "EXCHANGE_PROVIDER") -> str:
    # Check specific env var first (e.g. MARKET_DATA_MODE)
    val = os.getenv(key.upper())
    if val:
        return val.strip().lower()
    
    # Check settings field
    # We dynamically getattr because settings might be an old object or updated one
    # But settings is pydantic, so:
    attr_val = getattr(settings.market, key.lower(), None)
    if attr_val and attr_val != "primary": # Assuming primary is default/empty
         return attr_val
         
    # Fallback to legacy Exchange Provider
    legacy = os.getenv(legacy_key)
    if legacy:
        return legacy.strip().lower()
    return settings.market.exchange_provider


def build_market_provider(
    settings: Settings,
    profile_settings: TradingProfileSettings | None = None,
    *,
    shared_ib: object | None,
) -> MarketDataProvider:
    mode = _selected_mode(settings, "market_data_mode")
    
    primary_provider = None
    if shared_ib is not None:
        primary_provider = IbkrMarketDataProvider(shared_ib)
    
    alt = os.getenv("ALTERNATIVE_MARKET_DATA") or settings.market.alternative_market_data
    alt = alt.strip().lower()
    
    if alt == "ccxt" or (alt == "coinbase" and os.getenv("ALTERNATIVE_BROKER") == "ccxt"):
        if not profile_settings:
            # Fallback to creating a minimal CCXT if no profile (rare)
            # But better to just use CoinbaseMarketDataProvider legacy if we really have no keys
            logger.warning("[CCXT-DATA] Requested but no profile_settings provided. Falling back to legacy Coinbase API.")
            alt_provider = CoinbaseMarketDataProvider()
        else:
            logger.info("[CCXT-DATA] Initializing authenticated market provider (Coinbase V3).")
            # We can create a temporary broker just to get the exchange handle
            temp_broker = CCXTExchangeBroker(profile_settings, default_type="future" if alt == "coinbase_futures" else None)
            alt_provider = CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
    elif alt == "coinbase":
        alt_provider = CoinbaseMarketDataProvider()
    elif alt == "coinbase_futures":
        if not profile_settings:
            logger.warning("[CCXT-FUTURES] No profile_settings provided. Falling back to mock.")
            alt_provider = MockMarketDataProvider()
        else:
            logger.info("[CCXT-FUTURES] Mode active: Ensuring CCXT market provider.")
            temp_broker = CCXTExchangeBroker(profile_settings, default_type="future")
            alt_provider = CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
    else:
        alt_provider = MockMarketDataProvider()

    if mode == "primary":
        if primary_provider is None:
            raise RuntimeError("market_data_mode=primary requires an IB client (shared_ib)")
        return primary_provider
    if mode == "alternative":
        return alt_provider
    if mode == "coinbase_futures":
        # Force CCXT-based provider for futures mode
        if alt == "coinbase_futures":
            return alt_provider
        else:
            # Re-build alt_provider specifically as CCXT if it wasn't already
            if not profile_settings:
                 return alt_provider
            logger.info("[CCXT-FUTURES] Mode active: Ensuring CCXT market provider.")
            temp_broker = CCXTExchangeBroker(profile_settings, default_type="future")
            return CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
            
    if mode == "hybrid":
        if primary_provider is None:
             logger.warning("[HYBRID] IBKR provider not available (no shared_ib). Falling back to Alternative only.")
             return alt_provider
        return HybridMarketDataProvider(primary_provider, alt_provider)
        
    # Default to primary if unknown
    if primary_provider is None:
         raise RuntimeError(f"Unknown market data mode '{mode}' and no IB client available.")
    return primary_provider


def build_exchange_broker(
    settings: Settings,
    profile_settings: TradingProfileSettings,
    *,
    shared_ib: object | None,
    allowed_symbols: set[str] | None,
) -> IExchangeBroker:
    mode = _selected_mode(settings, "broker_mode")
    
    primary_broker = None
    if mode in ("primary", "hybrid", ""):  # default fallback is primary
        primary_broker = IbkrExecutor(
            settings.broker,
            settings.runtime,
            profile_settings,
            ib_client=shared_ib,
            allowed_symbols=allowed_symbols,
            position_hold_store_path=settings.runtime.position_hold_store_path,
        )
    
    alt = os.getenv("ALTERNATIVE_BROKER") or settings.market.alternative_broker
    alt = alt.strip().lower()
    if alt == "ccxt":
        alt_broker = CCXTExchangeBroker(
            profile_settings,
            position_hold_store_path=settings.runtime.position_hold_store_path
        )
    else:
        alt_broker = MockExchangeBroker(settings.broker, settings.runtime, profile_settings, allowed_symbols=allowed_symbols)

    if mode == "primary":
        return primary_broker
    if mode == "alternative":
        return alt_broker
    if mode == "coinbase_futures":
        # Force CCXT broker
        if (alt == "ccxt" or alt == "coinbase_futures") and hasattr(alt_broker, "default_type") and alt_broker.default_type == "future":
             return alt_broker
        else:
            logger.info("[CCXT-FUTURES] Mode active: Ensuring CCXT exchange broker in futures mode.")
            return CCXTExchangeBroker(
                profile_settings,
                position_hold_store_path=settings.runtime.position_hold_store_path,
                default_type="future"
            )
    if mode == "hybrid":
        return HybridExchangeBroker(primary_broker, alt_broker)
        
    return primary_broker
