from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, List

from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider
from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
from tradebot_sci.market.providers import (
    CCXTMarketDataProvider,
    IbkrMarketDataProvider,
    MarketDataProvider,
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
        # [ANTIGRAVITY FIX] Only route CRYPTO to alternative provider (Coinbase/CCXT)
        # Forex, commodities, and equities stay on IBKR (primary)
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

    @property
    def profile(self):
        """Returns the primary broker's profile (master settings)."""
        return getattr(self.primary, "profile", None)

    @property
    def position_hold_store(self):
        """Direct access to primary hold store (used by loop)."""
        return getattr(self.primary, "position_hold_store", None)

    def place_order(self, symbol: str, *args, **kwargs) -> Any:
        if is_crypto(symbol):
            return self.alternative.place_order(symbol, *args, **kwargs)
        return self.primary.place_order(symbol, *args, **kwargs)

    def cancel_order(self, symbol: str, *args, **kwargs) -> Any:
        if is_crypto(symbol):
            return self.alternative.cancel_order(symbol, *args, **kwargs)
        return self.primary.cancel_order(symbol, *args, **kwargs)

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        if is_crypto(symbol):
            if hasattr(self.alternative, "cancel_all_orders_for_symbol"):
                return self.alternative.cancel_all_orders_for_symbol(symbol)
            return None
        if hasattr(self.primary, "cancel_all_orders_for_symbol"):
            return self.primary.cancel_all_orders_for_symbol(symbol)

    def flatten_symbol(self, symbol: str) -> None:
        if is_crypto(symbol):
            if hasattr(self.alternative, "flatten_symbol"):
                return self.alternative.flatten_symbol(symbol)
            return None
        if hasattr(self.primary, "flatten_symbol"):
            return self.primary.flatten_symbol(symbol)

    def get_positions(self, *args, **kwargs) -> Any:
        p_pos = self.primary.get_positions(*args, **kwargs) or []
        a_pos = self.alternative.get_positions(*args, **kwargs) or []
        return list(p_pos) + list(a_pos)

    def get_open_orders(self, *args, **kwargs) -> Any:
        p_orders = self.primary.get_open_orders(*args, **kwargs) or []
        a_orders = self.alternative.get_open_orders(*args, **kwargs) or []
        return list(p_orders) + list(a_orders)

    def get_recent_fills(self, *args, **kwargs) -> Any:
        p_fills = self.primary.get_recent_fills(*args, **kwargs) or []
        a_fills = self.alternative.get_recent_fills(*args, **kwargs) or []
        return list(p_fills) + list(a_fills)

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        if is_crypto(symbol):
            res = self.alternative.get_open_position_snapshot(symbol)
            if res is None and hasattr(self.primary, "get_open_position_snapshot"):
                # Fallback to primary if alternative has no record but we know it might be there (e.g. Zerohash)
                res = self.primary.get_open_position_snapshot(symbol)
            return res
        return self.primary.get_open_position_snapshot(symbol)

    def list_open_position_symbols(self) -> List[str]:
        p_syms = self.primary.list_open_position_symbols() if hasattr(self.primary, "list_open_position_symbols") else []
        a_syms = self.alternative.list_open_position_symbols() if hasattr(self.alternative, "list_open_position_symbols") else []
        logger.debug(f"[HYBRID] list_open_position_symbols: primary={p_syms} alternative={a_syms}")
        return list(set(p_syms) | set(a_syms))

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Any:
        p_res = self.primary.evaluate_synthetic_stops(market_provider, timeframe) if hasattr(self.primary, "evaluate_synthetic_stops") else []
        a_res = self.alternative.evaluate_synthetic_stops(market_provider, timeframe) if hasattr(self.alternative, "evaluate_synthetic_stops") else []
        return list(p_res) + list(a_res)

    def _fetch_symbol_state(self, symbol: str) -> dict:
        if is_crypto(symbol):
            return self.alternative._fetch_symbol_state(symbol)
        return self.primary._fetch_symbol_state(symbol)

    def should_block_for_hold(self, symbol: str, decision: AITradeDecision, open_position: dict | None) -> tuple[bool, str | None, float | None]:
        if is_crypto(symbol):
            if hasattr(self.alternative, "should_block_for_hold"):
                return self.alternative.should_block_for_hold(symbol, decision, open_position)
            return False, None, None
        if hasattr(self.primary, "should_block_for_hold"):
            return self.primary.should_block_for_hold(symbol, decision, open_position)
        return False, None, None

    def execute_decision(self, decision: AITradeDecision) -> Any:
        symbol = decision.symbol
        if is_crypto(symbol):
            return self.alternative.execute_decision(decision)
        return self.primary.execute_decision(decision)

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        if is_crypto(symbol):
            return self.alternative._has_active_orders_or_position(symbol, state)
        return self.primary._has_active_orders_or_position(symbol, state)

    def refresh_account_summary(self) -> None:
        if hasattr(self.primary, "refresh_account_summary"):
            self.primary.refresh_account_summary()
        if hasattr(self.alternative, "refresh_account_summary"):
            self.alternative.refresh_account_summary()

    def summarize_pnl(self) -> None:
        if hasattr(self.primary, "summarize_pnl"):
            self.primary.summarize_pnl()
        if hasattr(self.alternative, "summarize_pnl"):
            self.alternative.summarize_pnl()

    def get_liquid_capital(self) -> float:
        """Returns the total liquid capital across all brokers."""
        primary_cap = self.primary.get_liquid_capital() if hasattr(self.primary, "get_liquid_capital") else 0.0
        alternative_cap = self.alternative.get_liquid_capital() if hasattr(self.alternative, "get_liquid_capital") else 0.0
        
        # [ANTIGRAVITY FIX] Sum broker capitals.
        # This addresses the "separated capital" requirement where the user may have funds
        # split between IBKR (Forex/Futures) and CCXT (Coinbase/Crypto).
        total = primary_cap + alternative_cap
        
        logger.debug("[HYBRID] Capital breakdown: primary=$%.2f alternative=$%.2f total=$%.2f", primary_cap, alternative_cap, total)
        return total


def _selected_mode(settings: Settings, key: str, legacy_key: str = "EXCHANGE_PROVIDER") -> str:
    # [ANTIGRAVITY FIX] Prioritize new mode env vars (BROKER_MODE/MARKET_DATA_MODE)
    # over legacy EXCHANGE_PROVIDER to avoid configuration conflicts.
    val = os.getenv(key.upper())
    if val:
        return val.strip().lower()
    
    # Fallback to legacy Exchange Provider
    legacy = os.getenv(legacy_key)
    if legacy:
        return legacy.strip().lower()

    # Check settings field
    attr_val = getattr(settings.market, key.lower(), None)
    if attr_val and attr_val != "primary": 
         return attr_val
         
    return settings.market.exchange_provider


def build_market_provider(
    settings: Settings,
    profile_settings: TradingProfileSettings | None = None,
    *,
    shared_ib: object | None,
) -> MarketDataProvider:
    mode = _selected_mode(settings, "market_data_mode")
    if mode == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        return OandaMarketDataProvider(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            environment=settings.oanda.environment
        )

    if mode == "mock":
        raise ValueError("Mock mode is disabled. Please use 'primary', 'alternative', or 'hybrid'.")

    primary_mode = os.getenv("PRIMARY_PROVIDER", "ibkr").lower()
    primary_provider = None
    if primary_mode == "ibkr" and shared_ib is not None:
        primary_provider = IbkrMarketDataProvider(shared_ib)
    elif primary_mode == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        primary_provider = OandaMarketDataProvider(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            environment=settings.oanda.environment
        )
    
    alt = os.getenv("ALTERNATIVE_MARKET_DATA") or settings.market.alternative_market_data
    alt = alt.strip().lower()
    if alt == "mock":
        raise ValueError("Mock market data is disabled. Use 'ccxt' or 'coinbase'.")

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
            logger.error("[CCXT-FUTURES] No profile_settings provided. Mock fallback disabled.")
            raise ValueError("Authenticated session required for Coinbase Futures.")
        else:
            logger.info("[CCXT-FUTURES] Mode active: Ensuring CCXT market provider.")
            temp_broker = CCXTExchangeBroker(profile_settings, default_type="future")
            alt_provider = CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
    elif alt == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        alt_provider = OandaMarketDataProvider(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            environment=settings.oanda.environment
        )
    else:
        # Final safety check: if we're here, we don't have a valid alternative
        if mode in ("alternative", "hybrid"):
            raise ValueError(f"Unknown or disabled alternative market data provider: {alt}")
        alt_provider = None

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
                 raise ValueError("Authenticated session required for Coinbase Futures.")
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
    if mode == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        return OandaExchangeBroker(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            profile_settings=profile_settings,
            environment=settings.oanda.environment,
            read_only=settings.oanda.read_only
        )

    if mode == "mock":
        raise ValueError("Mock broker is disabled. Please use 'primary', 'alternative', or 'hybrid'.")

    primary_mode = os.getenv("PRIMARY_BROKER", "ibkr").lower()
    primary_broker = None
    if mode in ("primary", "hybrid", ""):  # default fallback is primary
        if primary_mode == "ibkr":
            primary_broker = IbkrExecutor(
                settings.broker,
                settings.runtime,
                profile_settings,
                ib_client=shared_ib,
                allowed_symbols=allowed_symbols,
                position_hold_store_path=settings.runtime.position_hold_store_path,
            )
        elif primary_mode == "oanda":
            if not settings.oanda:
                from tradebot_sci.config.broker import load_oanda_broker_options
                settings.oanda = load_oanda_broker_options()
            primary_broker = OandaExchangeBroker(
                account_id=settings.oanda.account_id,
                api_key=settings.oanda.api_key,
                profile_settings=profile_settings,
                environment=settings.oanda.environment,
                read_only=settings.oanda.read_only
            )
    
    alt = os.getenv("ALTERNATIVE_BROKER") or settings.market.alternative_broker
    alt = alt.strip().lower()
    if alt == "mock":
        if mode in ("alternative", "hybrid"):
            raise ValueError("Mock broker is disabled. Use 'ccxt' for crypto.")
        alt_broker = None # Should not be used in primary mode
    elif alt == "ccxt":
        alt_broker = CCXTExchangeBroker(
            profile_settings,
            position_hold_store_path=settings.runtime.position_hold_store_path
        )
    elif alt == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        alt_broker = OandaExchangeBroker(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            profile_settings=profile_settings,
            environment=settings.oanda.environment,
            read_only=settings.oanda.read_only
        )
    else:
        if mode in ("alternative", "hybrid"):
             raise ValueError(f"Unknown or disabled alternative broker: {alt}")
        alt_broker = None

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
        if not alt_broker:
            raise ValueError("Hybrid mode requires a valid alternative broker (ccxt).")
        return HybridExchangeBroker(primary_broker, alt_broker)
        
    return primary_broker
