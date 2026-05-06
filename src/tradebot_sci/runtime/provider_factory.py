from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, List, Dict

from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider
from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
from tradebot_sci.broker.paxos_broker import PaxosExchangeBroker
from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
from tradebot_sci.market.paxos_provider import PaxosMarketDataProvider
from tradebot_sci.market.providers import (
    CCXTMarketDataProvider,
    IbkrMarketDataProvider,
    MarketDataProvider,
)
from tradebot_sci.market.symbols import is_crypto, SYMBOL_METADATA, AssetClass, FOREX_SYMBOLS

if TYPE_CHECKING:
    from tradebot_sci.market.models import Candle, MarketSnapshot, OrderBook, Ticker

logger = logging.getLogger(__name__)


def _get_asset_key(symbol: str) -> str:
    """Resolve asset class key for routing ('crypto', 'forex', 'equity')."""
    # 1. Check Metadata first (Specific override)
    meta = SYMBOL_METADATA.get(symbol)
    if meta:
        if meta.asset_class == AssetClass.CRYPTO: return "crypto"
        if meta.asset_class == AssetClass.FOREX: return "forex"
        if meta.asset_class == AssetClass.EQUITY: return "equity"
        if meta.asset_class == AssetClass.FUTURE: return "future"
        if meta.asset_class == AssetClass.METAL: return "metal"

    # 2. Heuristics
    if is_crypto(symbol): return "crypto"
    if symbol in FOREX_SYMBOLS: return "forex"
    
    # 3. Default Execution (Primary)
    return "equity"


class RoutedMarketDataProvider(MarketDataProvider):
    """Dispatches market data requests to specific providers based on asset class."""

    def __init__(self, providers: Dict[str, MarketDataProvider]):
        self.providers = providers
        # fallback is equity provider or first available
        self._fallback = providers.get("equity") or next(iter(providers.values()))

    def _get_provider(self, symbol: str) -> MarketDataProvider:
        key = _get_asset_key(symbol)
        return self.providers.get(key, self._fallback)

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        return self._get_provider(symbol).get_latest_candles(symbol, timeframe, limit)

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        return self._get_provider(symbol).get_latest_snapshot(symbol, timeframe)

    def get_ticker(self, symbol: str) -> Ticker | None:
        return self._get_provider(symbol).get_ticker(symbol)

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return self._get_provider(symbol).get_order_book(symbol, depth)

    def close(self) -> None:
        for p in self.providers.values():
            p.close()


class RoutedExchangeBroker(IExchangeBroker):
    """Dispatches broker commands to specific brokers based on asset class."""

    def __init__(self, brokers: Dict[str, IExchangeBroker]):
        self.brokers = brokers
        # Robust fallback: find first non-NoOp broker
        self._fallback = None
        for b in brokers.values():
            if not isinstance(b, NoOpExchangeBroker):
                self._fallback = b
                break
        if not self._fallback:
            self._fallback = next(iter(brokers.values()))

    def _get_broker(self, symbol: str) -> IExchangeBroker:
        key = _get_asset_key(symbol)
        broker = self.brokers.get(key)
        # If the requested asset class is NoOp, don't fall back to Oanda/IBKR!
        if broker and not isinstance(broker, NoOpExchangeBroker):
            return broker
        return broker or self._fallback

    @property
    def profile(self):
        """Returns the equity/primary broker's profile (master settings)."""
        return getattr(self._fallback, "profile", None)

    @property
    def position_hold_store(self):
        return getattr(self._fallback, "position_hold_store", None)

    def place_order(self, symbol: str, *args, **kwargs) -> Any:
        return self._get_broker(symbol).place_order(symbol, *args, **kwargs)

    def cancel_order(self, symbol: str, *args, **kwargs) -> Any:
        return self._get_broker(symbol).cancel_order(symbol, *args, **kwargs)

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        broker = self._get_broker(symbol)
        if hasattr(broker, "cancel_all_orders_for_symbol"):
            return broker.cancel_all_orders_for_symbol(symbol)

    def flatten_symbol(self, symbol: str) -> None:
        broker = self._get_broker(symbol)
        if hasattr(broker, "flatten_symbol"):
            return broker.flatten_symbol(symbol)

    def get_positions(self, *args, **kwargs) -> Any:
        # Aggregate positions from all brokers
        unique_brokers = set(self.brokers.values())
        all_pos = []
        for b in unique_brokers:
            p = b.get_positions(*args, **kwargs) or []
            all_pos.extend(p)
        return all_pos

    def get_open_orders(self, *args, **kwargs) -> Any:
        unique_brokers = set(self.brokers.values())
        all_orders = []
        for b in unique_brokers:
            o = b.get_open_orders(*args, **kwargs) or []
            all_orders.extend(o)
        return all_orders

    def get_recent_fills(self, *args, **kwargs) -> Any:
        # Deduplicate brokers and ignore NoOp
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        all_fills = []
        for b in unique_brokers:
            f = b.get_recent_fills(*args, **kwargs) or []
            all_fills.extend(f)
        return all_fills

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        return self._get_broker(symbol).get_open_position_snapshot(symbol)

    def list_open_position_symbols(self) -> List[str]:
        unique_brokers = set(self.brokers.values())
        all_syms = set()
        for b in unique_brokers:
            if hasattr(b, "list_open_position_symbols"):
                all_syms.update(b.list_open_position_symbols())
        return list(all_syms)

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Any:
        unique_brokers = set(self.brokers.values())
        all_res = []
        for b in unique_brokers:
            if hasattr(b, "evaluate_synthetic_stops"):
                provider_for_broker = market_provider # Pass routed provider
                all_res.extend(b.evaluate_synthetic_stops(provider_for_broker, timeframe))
        return all_res

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return self._get_broker(symbol)._fetch_symbol_state(symbol)

    def should_block_for_hold(self, symbol: str, decision: Any, open_position: dict | None) -> tuple[bool, str | None, float | None]:
        broker = self._get_broker(symbol)
        if hasattr(broker, "should_block_for_hold"):
            return broker.should_block_for_hold(symbol, decision, open_position)
        return False, None, None

    def modify_stop_loss(self, symbol: str, new_stop: float) -> bool:
        broker = self._get_broker(symbol)
        if hasattr(broker, "modify_stop_loss"):
            return broker.modify_stop_loss(symbol, new_stop)
        logger.warning(f"[ROUTED] modify_stop_loss not supported for {symbol} ({type(broker).__name__})")
        return False

    def execute_decision(self, decision: Any) -> Any:
        return self._get_broker(decision.symbol).execute_decision(decision)

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        return self._get_broker(symbol)._has_active_orders_or_position(symbol, state)

    def sync_profile(self, profile: TradingProfileSettings) -> None:
        """Propagate profile update to all underlying brokers (Hot-Reload)."""
        unique_brokers = set(self.brokers.values())
        for b in unique_brokers:
            if hasattr(b, "sync_profile"):
                b.sync_profile(profile)

    def refresh_account_summary(self) -> None:
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "refresh_account_summary"):
                b.refresh_account_summary()
        # Log aggregated total so UI stays in sync after individual refreshes
        self.get_total_balance_value()

    def summarize_pnl(self) -> None:
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "summarize_pnl"):
                b.summarize_pnl()

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        if symbol:
            return self._get_broker(symbol).get_liquid_capital(symbol)
            
        total = 0.0
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "get_liquid_capital"):
                b_cap = b.get_liquid_capital()
                logger.debug(f"[ROUTED] Broker {type(b).__name__} contributed ${b_cap:.2f}")
                total += b_cap
        
        # Log for internal awareness (not UI aggregate)
        logger.info(f"[CASH] Buying Power: ${total:.2f}")
        logger.debug("[ROUTED] Total Cash Breakdown completed: %.2f", total)
        return total

    def get_display_cash(self) -> float:
        """Return actual tracked cash balance for GUI display.

        Aggregates get_display_cash() from each sub-broker (falls back to
        get_liquid_capital for brokers without it). This ensures the GUI
        shows the real running balance, not the sizing-capped initial value.
        """
        total = 0.0
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "get_display_cash"):
                total += b.get_display_cash()
            elif hasattr(b, "get_liquid_capital"):
                total += b.get_liquid_capital()
        return total

    def get_total_balance_value(self) -> float:
        """Return aggregated Net Worth (Cash + Assets) across all brokers."""
        total = 0.0
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "get_total_balance_value"):
                val = b.get_total_balance_value()
                logger.debug(f"[ROUTED] Broker {type(b).__name__} equity: ${val:.2f}")
                total += val
            elif hasattr(b, "get_liquid_capital"):
                # Fallback to cash if equity method missing
                total += b.get_liquid_capital()
        
        # Authoritative Total Log for UI
        logger.info(f"[TOTAL] Liquidity available: ${total:.2f}")
        logger.debug("[ROUTED] Total Equity Breakdown completed: %.2f", total)
        return total

    def get_total_equity(self) -> float:
        """Aggregate total equity (cash + position value) across all sub-brokers."""
        total = 0.0
        unique_brokers = set(b for b in self.brokers.values() if not isinstance(b, NoOpExchangeBroker))
        for b in unique_brokers:
            if hasattr(b, "get_total_equity"):
                b_eq = b.get_total_equity()
                logger.debug(f"[ROUTED] Broker {type(b).__name__} equity: ${b_eq:.2f}")
                total += b_eq
            elif hasattr(b, "get_liquid_capital"):
                total += b.get_liquid_capital()
        logger.info(f"[EQUITY] Total Account Equity: ${total:.2f}")
        return total



class NoOpMarketDataProvider(MarketDataProvider):
    """Placeholder provider for deactivated assets."""
    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        return [] # Return empty to skip processing
    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        return None
    def get_ticker(self, symbol: str) -> Ticker | None:
        return None
    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return None
    def close(self) -> None:
        pass


class NoOpExchangeBroker(IExchangeBroker):
    """Placeholder broker for deactivated assets."""
    @property
    def profile(self): return None
    @property
    def position_hold_store(self): return None
    def place_order(self, *args, **kwargs) -> Any:
        logger.warning("[NO-OP] Order placement blocked (Asset Class Disabled).")
        return None
    def cancel_order(self, *args, **kwargs) -> Any: return None
    def cancel_all_orders_for_symbol(self, *args, **kwargs) -> None: pass
    def flatten_symbol(self, *args, **kwargs) -> None: pass
    def get_positions(self, *args, **kwargs) -> Any: return []
    def get_open_orders(self, *args, **kwargs) -> Any: return []
    def get_recent_fills(self, *args, **kwargs) -> Any: return []
    def get_open_position_snapshot(self, *args, **kwargs) -> Any: return None
    def list_open_position_symbols(self) -> List[str]: return []
    def evaluate_synthetic_stops(self, *args, **kwargs) -> Any: return []
    def _fetch_symbol_state(self, *args, **kwargs) -> dict: return {}
    def should_block_for_hold(self, *args, **kwargs) -> Any: return False, None, None
    def execute_decision(self, *args, **kwargs) -> Any: return None
    def _has_active_orders_or_position(self, *args, **kwargs) -> bool: return False
    def refresh_account_summary(self) -> None: pass
    def summarize_pnl(self) -> None: pass
    def get_liquid_capital(self) -> float: return 0.0
    def get_total_equity(self) -> float: return 0.0


def _get_effective_setting(key: str, settings: Settings, profile_settings: TradingProfileSettings | None) -> str:
    """Resolves a setting key looking at Profile Overrides -> Env -> Global Settings."""
    # 1. Profile Override
    if profile_settings and profile_settings.runtime_overrides:
        val = profile_settings.runtime_overrides.get(key)
        if val:
            return str(val).lower()
    
    # 2. Environment Variable
    env_val = os.getenv(key.upper())
    if env_val:
        return env_val.lower()
        
    # 3. Global Settings Object
    # Check market_data_mode, broker_mode etc.
    if hasattr(settings.market, key):
        return str(getattr(settings.market, key)).lower()
        
    return ""

def _create_single_broker(name: str, settings: Settings, profile_settings, shared_ib, allowed_symbols, trade_results=None):
    """Helper to instantiate a broker by name."""
    name = name.lower().strip()
    
    if name == "disabled" or name == "none":
        return NoOpExchangeBroker()

    # ── Credential gate: skip brokers that lack required API keys ──
    # Note: OANDA account_id comes from config.json, only require API key in env.
    _BROKER_CREDS = {
        "gemini":   lambda: os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_SECRET"),
        "ccxt":     lambda: os.getenv("CCXT_API_KEY"),
        "coinbase": lambda: os.getenv("CCXT_API_KEY"),
        "ibkr":     lambda: shared_ib is not None,
        "oanda":    lambda: os.getenv("OANDA_API_KEY"),
        "paxos":    lambda: os.getenv("PAXOS_API_KEY") or (settings.paxos and settings.paxos.api_key),
        "itbit":    lambda: os.getenv("PAXOS_API_KEY") or (settings.paxos and settings.paxos.api_key),
        "kraken":   lambda: os.getenv("KRAKEN_API_KEY"),
        "apex":  lambda: os.getenv("PROP_APEX_APP_ID") or (profile_settings and getattr(profile_settings, "prop_apex_app_id", "")),
        "tradovate":lambda: os.getenv("PROP_APEX_APP_ID") or (profile_settings and getattr(profile_settings, "prop_apex_app_id", "")),
    }
    cred_check = _BROKER_CREDS.get(name)
    if cred_check and not cred_check():
        logger.info(f"[ROUTED-EXEC] Skipping '{name}' broker (no credentials configured)")
        return NoOpExchangeBroker()

    if name == "alternative":
        # Resolve what 'alternative' actually means here
        alt_name = _get_effective_setting("alternative_broker", settings, profile_settings)
        if alt_name and alt_name != "alternative":
            return _create_single_broker(alt_name, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        name = "ccxt" # Default alternative for broker is CCXT

    if name == "primary":
        prime = settings.market.primary_broker
        if prime and prime not in ("primary", "hybrid"):
            return _create_single_broker(prime, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        name = "ibkr" # Final fallback

    if name == "ibkr":
        return IbkrExecutor(
            settings.broker,
            settings.runtime,
            profile_settings,
            ib_client=shared_ib,
            allowed_symbols=allowed_symbols,
            position_hold_store_path=settings.runtime.position_hold_store_path,
        )
    elif name == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        broker = OandaExchangeBroker(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,
            profile_settings=profile_settings,
            environment=settings.oanda.environment,
            read_only=not settings.runtime.execute_trades,
            trade_results=trade_results,
            position_hold_store_path=settings.runtime.position_hold_store_path
        )
        # Wire live spread data into the global fee system (Skip in Replay mode to avoid offline/weekend API spread blowouts)
        if os.getenv("IS_REPLAY") != "1":
            try:
                from tradebot_sci.utils.symbol_classifier import set_live_spread_provider
                set_live_spread_provider(broker.get_live_spread_as_pct)
                logger.info("[SPREAD] Live spread provider registered (OANDA Pricing API)")
            except Exception as e:
                logger.warning(f"[SPREAD] Failed to register live spread provider: {e}")
        else:
            logger.info("[SPREAD] Replay Mode: Live spread injection bypassed (using historical/static defaults)")
        return broker
    elif name == "paxos" or name == "itbit":
        if not settings.paxos:
            from tradebot_sci.config.broker import load_paxos_broker_options
            settings.paxos = load_paxos_broker_options()
        return PaxosExchangeBroker(
            api_key=settings.paxos.api_key,
            api_secret=settings.paxos.api_secret,
            profile_settings=profile_settings,
            environment=settings.paxos.environment
        )
    elif name == "ccxt" or name == "coinbase":
         return CCXTExchangeBroker(
            profile_settings,
            position_hold_store_path=settings.runtime.position_hold_store_path,
            trade_results=trade_results
        )
    elif name == "gemini":
        # Gemini specific CCXT initialization
        api_key = os.getenv("GEMINI_API_KEY")
        api_secret = os.getenv("GEMINI_API_SECRET")
        sandbox = os.getenv("GEMINI_SANDBOX", "false").lower() == "true"
        
        # We can reuse CCXTExchangeBroker by overriding CCXT_EXCHANGE env locally for this instance
        # or passing it in. Let's ensure the environment reflects the choice.
        os.environ["CCXT_EXCHANGE"] = "gemini"
        if api_key: os.environ["CCXT_API_KEY"] = api_key
        if api_secret: os.environ["CCXT_SECRET"] = api_secret
        os.environ["CCXT_SANDBOX"] = "true" if sandbox else "false"

        return CCXTExchangeBroker(
            profile_settings,
            position_hold_store_path=settings.runtime.position_hold_store_path,
            trade_results=trade_results
        )
    elif name == "kraken":
        # Kraken specific CCXT initialization
        api_key = os.getenv("KRAKEN_API_KEY")
        api_secret = os.getenv("KRAKEN_API_SECRET")
        sandbox = os.getenv("KRAKEN_ENVIRONMENT", "production").lower() == "sandbox"
        
        os.environ["CCXT_EXCHANGE"] = "kraken"
        if api_key: os.environ["CCXT_API_KEY"] = api_key
        if api_secret: os.environ["CCXT_SECRET"] = api_secret
        os.environ["CCXT_SANDBOX"] = "true" if sandbox else "false"

        return CCXTExchangeBroker(
            profile_settings,
            position_hold_store_path=settings.runtime.position_hold_store_path,
            trade_results=trade_results
        )
    elif name in ("tradovate", "apex"):
        from tradebot_sci.broker.tradovate_broker import TradovateBroker
        return TradovateBroker(
            username=getattr(profile_settings, "prop_apex_user", ""),
            password=getattr(profile_settings, "prop_apex_pass", ""),
            app_id=getattr(profile_settings, "prop_apex_app_id", ""),
            profile_settings=profile_settings,
            environment="demo", # Apex Evaluation always executes on Demo endpoint
            read_only=not settings.runtime.execute_trades
        )
    elif name in ("mt5", "ftmo"):
        from tradebot_sci.broker.mt5_zmq_broker import MT5ZMQBroker
        return MT5ZMQBroker(profile_settings, trade_results=trade_results)
    # Fallback to Mock?
    return NoOpExchangeBroker()

def _create_single_provider(name: str, settings: Settings, profile_settings, shared_ib):
    """Helper to instantiate a market provider by name."""
    name = name.lower().strip()
    
    if name == "disabled" or name == "none":
        return NoOpMarketDataProvider()

    # ── Credential gate: skip providers that lack required API keys ──
    # Note: OANDA account_id comes from config.json, only require API key in env.
    _PROVIDER_CREDS = {
        "gemini":   lambda: os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_SECRET"),
        "ccxt":     lambda: os.getenv("CCXT_API_KEY"),
        "coinbase": lambda: os.getenv("CCXT_API_KEY"),
        "ibkr":     lambda: shared_ib is not None,
        "oanda":    lambda: os.getenv("OANDA_API_KEY"),
        "paxos":    lambda: os.getenv("PAXOS_API_KEY") or (settings.paxos and settings.paxos.api_key),
        "itbit":    lambda: os.getenv("PAXOS_API_KEY") or (settings.paxos and settings.paxos.api_key),
        # kraken = public API, no keys needed for market data
    }
    cred_check = _PROVIDER_CREDS.get(name)
    if cred_check and not cred_check():
        logger.info(f"[ROUTED-DATA] Skipping '{name}' market provider (no credentials configured)")
        return NoOpMarketDataProvider()

    if name == "alternative":
        alt_name = _get_effective_setting("alternative_market_data", settings, profile_settings)
        if alt_name and alt_name != "alternative":
            return _create_single_provider(alt_name, settings, profile_settings, shared_ib)
        name = "coinbase" # Default alternative for market data

    if name == "primary":
        prime = settings.market.primary_market_provider
        if prime and prime not in ("primary", "hybrid"):
            return _create_single_provider(prime, settings, profile_settings, shared_ib)
        name = "kraken" # Changed from ibkr to kraken per user request to avoid F- grades

    if name == "ibkr":
        return IbkrMarketDataProvider(shared_ib)
    elif name == "oanda":
        if not settings.oanda:
            from tradebot_sci.config.broker import load_oanda_broker_options
            settings.oanda = load_oanda_broker_options()
        return OandaMarketDataProvider(
            account_id=settings.oanda.account_id,
            api_key=settings.oanda.api_key,

            environment=settings.oanda.environment
        )
    elif name == "paxos" or name == "itbit":
        if not settings.paxos:
            from tradebot_sci.config.broker import load_paxos_broker_options
            settings.paxos = load_paxos_broker_options()
        return PaxosMarketDataProvider(environment=settings.paxos.environment)
    elif name == "ccxt" or name == "coinbase":
        if profile_settings:
            temp_broker = CCXTExchangeBroker(profile_settings)
            return CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
        return CoinbaseMarketDataProvider()
    elif name == "gemini":
        # Gemini specific CCXT initialization
        os.environ["CCXT_EXCHANGE"] = "gemini"
        temp_broker = CCXTExchangeBroker(profile_settings)
        return CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
    elif name == "kraken":
        # Kraken specific CCXT initialization (public API, no keys needed)
        os.environ["CCXT_EXCHANGE"] = "kraken"
        temp_broker = CCXTExchangeBroker(profile_settings)
        return CCXTMarketDataProvider(temp_broker.exchange, temp_broker.symbol_map_data)
    elif name in ("mt5", "ftmo"):
        from tradebot_sci.broker.mt5_zmq_broker import MT5ZMQMarketProvider
        logger.info(f"[ROUTED-DATA] MT5 Market Data Provider engaged via ZMQ (Mode: {name}).")
        return MT5ZMQMarketProvider()
    return NoOpMarketDataProvider()


def build_market_provider(
    settings: Settings,
    profile_settings: TradingProfileSettings | None = None,
    *,
    shared_ib: object | None,
    allowed_symbols: set[str] | None = None,
) -> MarketDataProvider:
    """Builds a market data provider with per-asset routing support."""
    
    # FTMO / Prop Firm Force Override
    use_ftmo = getattr(settings.risk, "prop_ftmo_enabled", False) or (profile_settings and getattr(profile_settings, "prop_ftmo_enabled", False))
    use_apex = getattr(settings.risk, "prop_apex_enabled", False) or (profile_settings and getattr(profile_settings, "prop_apex_enabled", False))

    # ── OANDA-only short-circuit ──
    # If OANDA credentials exist but no CCXT/Gemini keys, skip ALL config-driven
    # routing (which may reference gemini/ccxt) and return OANDA+Kraken directly.
    _has_oanda = bool(os.getenv("OANDA_API_KEY"))
    _has_ccxt = bool(os.getenv("CCXT_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("CCXT_SECRET") or os.getenv("GEMINI_API_SECRET"))
    if _has_oanda and not _has_ccxt and not use_ftmo and not use_apex:
        logger.info("[ROUTED-DATA] OANDA-only detected (no CCXT/Gemini keys) → Forex=OANDA, Crypto=Kraken (public)")
        p_forex = _create_single_provider("oanda", settings, profile_settings, shared_ib)
        p_crypto = _create_single_provider("kraken", settings, profile_settings, shared_ib)
        return RoutedMarketDataProvider({
            "crypto": p_crypto,
            "forex": p_forex,
            "equity": NoOpMarketDataProvider(),
        })

    # Check for Granular Overrides first
    crypto_md_mode = os.getenv("BROKER_CRYPTO", "").lower()
    forex_md_mode = os.getenv("BROKER_FOREX", "").lower() 
    if forex_md_mode in ("kraken", "ccxt", "binance"):
        logger.info(f"[PROVIDER_FACTORY] Overriding unsafe Forex data feed '{forex_md_mode}' to 'ibkr' to prevent rate limit lockouts.")
        forex_md_mode = "ibkr"
    
    # Force default routing if no explicit override is provided but keys exist
    if not forex_md_mode:
        forex_md_mode = "oanda" if _has_oanda else "ibkr"

    equity_md_mode = os.getenv("BROKER_EQUITIES", "").lower() # Or Default
    future_md_mode = os.getenv("BROKER_FUTURES", "").lower()
    metal_md_mode = os.getenv("BROKER_METALS", "").lower()

    # Logic: If ANY granular override is present, use Routed Mode.
    is_routed = bool(crypto_md_mode or forex_md_mode or equity_md_mode or future_md_mode or metal_md_mode)
    
    if is_routed:
        # Default defaults
        if not crypto_md_mode: crypto_md_mode = "ccxt" if _has_ccxt else "kraken"
        if not forex_md_mode: forex_md_mode = "oanda" if _has_oanda else "ibkr"
        if not equity_md_mode: equity_md_mode = "ibkr" # Default equity
        if not future_md_mode: future_md_mode = "ibkr"
        if not metal_md_mode: metal_md_mode = "ibkr"
        
        providers = {}
        cache = {} # Deduplication cache

        def get_p(mode, asset_class=None):
            if mode in cache: return cache[mode]
            
            # Optimization: Skip if no symbols for this asset class
            if allowed_symbols and asset_class:
                 has_class = any(_get_asset_key(s) == asset_class for s in allowed_symbols)
                 if not has_class:
                     logger.debug(f"[ROUTED-DATA] Skipping {asset_class} provider ({mode}) - no symbols assigned.")
                     from tradebot_sci.market.providers import NoOpMarketDataProvider
                     cache[mode] = NoOpMarketDataProvider()
                     return cache[mode]

            p = _create_single_provider(mode, settings, profile_settings, shared_ib)
            if p: cache[mode] = p
            return p

        p_crypto = get_p(crypto_md_mode, "crypto")
        p_forex = get_p(forex_md_mode, "forex")
        p_equity = get_p(equity_md_mode, "equity")
        p_future = get_p(future_md_mode, "future")
        p_metal = get_p(metal_md_mode, "metal")
        
        if p_crypto: providers["crypto"] = p_crypto
        if p_forex: providers["forex"] = p_forex
        if p_equity: providers["equity"] = p_equity
        if p_future: providers["future"] = p_future
        if p_metal: providers["metal"] = p_metal
        
        logger.info(f"[ROUTED-DATA] 5-Lane Active: Crypto={crypto_md_mode} Forex={forex_md_mode} Equity={equity_md_mode} Future={future_md_mode} Metal={metal_md_mode}")
        return RoutedMarketDataProvider(providers)
    
    # --- LEGACY / GLOBAL MODE FALLBACK ---
    # Keeps original logic for backward compatibility if no overrides set
    mode = _get_effective_setting("market_data_mode", settings, profile_settings)
    if not mode:
        mode = _get_effective_setting("exchange_provider", settings, profile_settings) or "primary"
    # Auto-detect OANDA-only: if OANDA credentials exist but no CCXT/Gemini keys,
    # build a routed provider: OANDA for forex, Kraken (public, no keys) for crypto.
    _has_oanda = bool(os.getenv("OANDA_API_KEY"))
    _has_ccxt = bool(os.getenv("CCXT_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if _has_oanda and mode in ("primary", "alternative") and not _has_ccxt:
        logger.info("[ROUTED-DATA] OANDA-only detected → Forex=OANDA, Crypto=Kraken (public)")
        p_forex = _create_single_provider("oanda", settings, profile_settings, shared_ib)
        p_crypto = _create_single_provider("kraken", settings, profile_settings, shared_ib)
        return RoutedMarketDataProvider({
            "crypto": p_crypto,
            "forex": p_forex,
            "equity": NoOpMarketDataProvider(),
        })
    
    if mode == "hybrid":
        p_forex = _create_single_provider(settings.market.primary_forex, settings, profile_settings, shared_ib)
        p_crypto = _create_single_provider(settings.market.primary_crypto, settings, profile_settings, shared_ib)
        p_equity = _create_single_provider(settings.market.primary_equities, settings, profile_settings, shared_ib)
        p_future = _create_single_provider(settings.market.primary_futures, settings, profile_settings, shared_ib)
        p_metal = _create_single_provider(settings.market.primary_metals, settings, profile_settings, shared_ib)
        
        return RoutedMarketDataProvider({
            "crypto": p_crypto,
            "forex": p_forex,
            "equity": p_equity,
            "future": p_future,
            "metal": p_metal
        })

    p = _create_single_provider(mode, settings, profile_settings, shared_ib)
    
    # Final safety check: if we are in crypto_only but ended up with Oanda/IBKR
    if p and allowed_symbols:
        has_crypto = any(_get_asset_key(s) == "crypto" for s in allowed_symbols)
        has_others = any(_get_asset_key(s) != "crypto" for s in allowed_symbols)
        if has_crypto and not has_others:
            # Strictly crypto only, make sure we aren't using Oanda for everything
            if "oanda" in str(p).lower() or "ibkr" in str(p).lower():
                logger.debug("[ROUTED-DATA] Overriding global %s to NoOp (crypto_only detected)", p)
                return NoOpMarketDataProvider()

    return p or NoOpMarketDataProvider()


def build_exchange_broker(
    settings: Settings,
    profile_settings: TradingProfileSettings,
    *,
    shared_ib: object | None,
    allowed_symbols: set[str] | None,
    trade_results = None,
) -> IExchangeBroker:
    """Builds an exchange broker with per-asset routing support."""
    
    # FTMO / Prop Firm Force Override
    use_ftmo = getattr(settings.risk, "prop_ftmo_enabled", False) or (profile_settings and getattr(profile_settings, "prop_ftmo_enabled", False))
    use_apex = getattr(settings.risk, "prop_apex_enabled", False) or (profile_settings and getattr(profile_settings, "prop_apex_enabled", False))

    # ── OANDA-only short-circuit ──
    # If OANDA credentials exist but no CCXT/Gemini keys, skip ALL config-driven
    # routing (which may reference gemini/ccxt) and return OANDA+NoOp directly.
    _has_oanda = bool(os.getenv("OANDA_API_KEY"))
    _has_ccxt = bool(os.getenv("CCXT_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("CCXT_SECRET") or os.getenv("GEMINI_API_SECRET"))
    if _has_oanda and not _has_ccxt and not use_ftmo and not use_apex:
        logger.info("[ROUTED-EXEC] OANDA-only detected (no CCXT/Gemini keys) → Forex=OANDA, Crypto/Equity=NoOp")
        b_forex = _create_single_broker("oanda", settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        return RoutedExchangeBroker({
            "crypto": NoOpExchangeBroker(),
            "forex": b_forex,
            "equity": NoOpExchangeBroker(),
        })

    crypto_mode = os.getenv("BROKER_CRYPTO", "").lower()
    forex_mode = os.getenv("BROKER_FOREX", "").lower()
    equity_mode = os.getenv("BROKER_EQUITIES", "").lower()
    future_mode = os.getenv("BROKER_FUTURES", "").lower()
    metal_mode = os.getenv("BROKER_METALS", "").lower()

    if use_ftmo:
        forex_mode = "mt5"
        equity_mode = "mt5"
        future_mode = "mt5"
        metal_mode = "mt5"
        
    if use_apex:
        equity_mode = "tradovate"
        future_mode = "tradovate"

    is_routed = bool(crypto_mode or forex_mode or equity_mode or future_mode or metal_mode)
    
    if is_routed:
        if not crypto_mode: crypto_mode = "ccxt"
        if not forex_mode: forex_mode = "oanda" if _has_oanda else "ibkr"
        if not equity_mode: equity_mode = "ibkr"
        if not future_mode: future_mode = "ibkr"
        if not metal_mode: metal_mode = "ibkr"
        
        brokers = {}
        cache = {}

        def get_b(mode, asset_class=None):
            if mode in cache: return cache[mode]
            
            # Don't skip broker instantiation based on allowed_symbols
            # We need them for get_liquid_capital even if no symbols match this cycle.
            b = _create_single_broker(mode, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
            if b: cache[mode] = b
            return b

        b_crypto = get_b(crypto_mode, "crypto")
        b_forex = get_b(forex_mode, "forex")
        b_equity = get_b(equity_mode, "equity")
        b_future = get_b(future_mode, "future")
        b_metal = get_b(metal_mode, "metal")
        
        if b_crypto: brokers["crypto"] = b_crypto
        if b_forex: brokers["forex"] = b_forex
        if b_equity: brokers["equity"] = b_equity
        if b_future: brokers["future"] = b_future
        if b_metal: brokers["metal"] = b_metal
        
        logger.info(f"[ROUTED-EXEC] 5-Lane Active: Crypto={crypto_mode} Forex={forex_mode} Equity={equity_mode} Future={future_mode} Metal={metal_mode}")
        return RoutedExchangeBroker(brokers)

    # --- LEGACY / GLOBAL MODE FALLBACK ---
    mode = _get_effective_setting("broker_mode", settings, profile_settings)
    if not mode:
        mode = _get_effective_setting("exchange_provider", settings, profile_settings) or "primary"
    # Auto-detect OANDA-only: if OANDA credentials exist but no CCXT/Gemini keys,
    # build a routed broker: OANDA for forex, NoOp for crypto/equity.
    _has_oanda = bool(os.getenv("OANDA_API_KEY"))
    _has_ccxt = bool(os.getenv("CCXT_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if _has_oanda and mode in ("primary", "alternative") and not _has_ccxt:
        logger.info("[ROUTED-EXEC] OANDA-only detected → Forex=OANDA, Crypto/Equity=NoOp")
        b_forex = _create_single_broker("oanda", settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        return RoutedExchangeBroker({
            "crypto": NoOpExchangeBroker(),
            "forex": b_forex,
            "equity": NoOpExchangeBroker(),
        })
    
    if mode == "hybrid":
        b_forex = _create_single_broker(settings.market.primary_forex, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        b_crypto = _create_single_broker(settings.market.primary_crypto, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        b_equity = _create_single_broker(settings.market.primary_equities, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        b_future = _create_single_broker(settings.market.primary_futures, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        b_metal = _create_single_broker(settings.market.primary_metals, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)
        
        return RoutedExchangeBroker({
            "crypto": b_crypto,
            "forex": b_forex,
            "equity": b_equity,
            "future": b_future,
            "metal": b_metal
        })

    p = _create_single_broker(mode, settings, profile_settings, shared_ib, allowed_symbols, trade_results=trade_results)

    # Final safety check: if we are in crypto_only but ended up with Oanda/IBKR
    if p and allowed_symbols:
        has_crypto = any(_get_asset_key(s) == "crypto" for s in allowed_symbols)
        has_others = any(_get_asset_key(s) != "crypto" for s in allowed_symbols)
        if has_crypto and not has_others:
            # Strictly crypto only, make sure we aren't using Oanda/IBKR for everything
            if "oanda" in str(p).lower() or "ibkr" in str(p).lower():
                logger.debug("[ROUTED-EXEC] Overriding global broker %s to NoOp (crypto_only detected)", p)
                return NoOpExchangeBroker()

    return p or NoOpExchangeBroker()
