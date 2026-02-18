from __future__ import annotations

import logging
from functools import lru_cache

try:
    from ib_insync import Crypto, Forex, Stock, Commodity, CFD  # type: ignore
except ImportError:  # pragma: no cover
    Crypto = None  # type: ignore[assignment]
    Forex = None  # type: ignore[assignment]
    Stock = None  # type: ignore[assignment]
    Commodity = None
    CFD = None

from tradebot_sci.config.models import CryptoRoutingSettings
from tradebot_sci.market.symbols import AssetClass, SymbolMetadata, SYMBOL_METADATA

logger = logging.getLogger(__name__)


class ContractResolutionError(Exception):
    """Raised when IBKR cannot resolve the requested contract."""


_crypto_exchange_default = "PAXOS"
_crypto_exchange_overrides: dict[str, str] = {}


def configure_crypto_routing(settings: CryptoRoutingSettings) -> None:
    """Applies settings that control which exchange each crypto order routes through."""
    global _crypto_exchange_default, _crypto_exchange_overrides
    _crypto_exchange_default = settings.default_exchange.upper()
    _crypto_exchange_overrides = {
        symbol.upper(): exchange.upper() for symbol, exchange in settings.overrides.items()
    }
    build_contract.cache_clear()


def _stock_contract(metadata: SymbolMetadata):
    if Stock is None:
        raise ContractResolutionError(metadata.symbol)
    return Stock(metadata.contract_symbol, metadata.exchange, metadata.currency)


def _crypto_contract(metadata: SymbolMetadata):
    if Crypto is None:
        raise ContractResolutionError(metadata.symbol)
    exchange = _crypto_exchange_overrides.get(metadata.symbol, _crypto_exchange_default)
    return Crypto(symbol=metadata.contract_symbol, exchange=exchange, currency=metadata.currency)


def _forex_contract(metadata: SymbolMetadata):
    if Forex is None:
        raise ContractResolutionError(metadata.symbol)
    
    symbol = metadata.contract_symbol
    
    # Metals contract routing
    if symbol == "XAUUSD": return Commodity(symbol, "SMART", "USD", primaryExchange="IBCMDTY", conId=69067924)
    if symbol == "XAGUSD": return Commodity(symbol, "SMART", "USD", primaryExchange="IBCMDTY", conId=77124483)
    if symbol == "XPTUSD": return Commodity(symbol, "SMART", "USD", primaryExchange="IBCMDTY", conId=78363317)
    if symbol == "XPDUSD":
        # Final attempt: SMART usually works if primary is right.
        return Commodity(symbol, "SMART", "USD", primaryExchange="IBCMDTY")

    # Standard Forex pairs
    # ib_insync Forex constructor expects the full pair string (e.g. "EURUSD")
    return Forex(symbol)


@lru_cache(maxsize=256)
def build_contract(symbol: str):
    key = symbol.upper()
    metadata = SYMBOL_METADATA.get(key)
    if not metadata:
        raise ContractResolutionError(symbol)
    if metadata.asset_class == AssetClass.FUTURE:
        raise ContractResolutionError(symbol)
    if metadata.asset_class == AssetClass.CRYPTO:
        contract = _crypto_contract(metadata)
    elif metadata.asset_class == AssetClass.FOREX:
        contract = _forex_contract(metadata)
    else:
        contract = _stock_contract(metadata)
    logger.debug("Built contract for %s (%s)", symbol, metadata.asset_class.value)
    return contract
