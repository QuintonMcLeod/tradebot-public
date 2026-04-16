from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Literal


class AssetClass(Enum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FOREX = "forex"
    FUTURE = "future"
    METAL = "metal"


class MarketType(Enum):
    US_EQUITY = "US_EQUITY"
    EU_EQUITY = "EU_EQUITY"
    APAC_EQUITY = "APAC_EQUITY"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    FUTURE = "FUTURE"
    COMMODITY = "COMMODITY"


MARKET_HOURS: Dict[MarketType, dict[str, str]] = {
    MarketType.US_EQUITY: {
        "timezone": "America/New_York",
        "open": "09:30",
        "close": "16:00",
    },
    MarketType.EU_EQUITY: {
        "timezone": "Europe/London",
        "open": "08:00",
        "close": "16:30",
    },
    MarketType.APAC_EQUITY: {
        "timezone": "Asia/Tokyo",
        "open": "09:00",
        "close": "15:00",
    },
    MarketType.FOREX: {"timezone": "UTC", "open": "22:00", "close": "22:00"},
    # Data-driven crypto hours: Open 12PM–6AM EST, Closed 6AM–12PM EST
    # The "Morning Kill Zone" (6AM–12PM EST) lost -$2,000+ across all strategies in 30-day backtest
    MarketType.CRYPTO: {"timezone": "America/New_York", "open": "12:00", "close": "06:00"},
    MarketType.FUTURE: {"timezone": "UTC", "open": "00:00", "close": "00:00"},
    MarketType.COMMODITY: {"timezone": "UTC", "open": "23:00", "close": "22:00"},
}


SYMBOL_MARKET_TYPE: Dict[str, MarketType] = {
    "SPY": MarketType.US_EQUITY,
    "QQQ": MarketType.US_EQUITY,
    "DIA": MarketType.US_EQUITY,
    "IWM": MarketType.US_EQUITY,
    "VTI": MarketType.US_EQUITY,
    "XLK": MarketType.US_EQUITY,
    "XLF": MarketType.US_EQUITY,
    "XLE": MarketType.US_EQUITY,
    "XLY": MarketType.US_EQUITY,
    "XLP": MarketType.US_EQUITY,
    "XLI": MarketType.US_EQUITY,
    "XLU": MarketType.US_EQUITY,
    "SMH": MarketType.US_EQUITY,
    "XLB": MarketType.US_EQUITY,
    "XOP": MarketType.US_EQUITY,
    "XME": MarketType.US_EQUITY,
    "ARKK": MarketType.US_EQUITY,
    "ARKF": MarketType.US_EQUITY,
    "SOXX": MarketType.US_EQUITY,
    "GLD": MarketType.US_EQUITY,
    "SLV": MarketType.US_EQUITY,
    "GDX": MarketType.US_EQUITY,
    "USO": MarketType.US_EQUITY,
    "UNG": MarketType.FOREX,
    "EWU": MarketType.US_EQUITY,
    "EWG": MarketType.US_EQUITY,
    "EWQ": MarketType.US_EQUITY,
    "EWT": MarketType.APAC_EQUITY,
    "EWJ": MarketType.APAC_EQUITY,
    "EWS": MarketType.APAC_EQUITY,
    "FXI": MarketType.APAC_EQUITY,
    "BTCUSD": MarketType.CRYPTO,
    "ETHUSD": MarketType.CRYPTO,
    "BTCUSD": MarketType.CRYPTO,
    "ETHUSD": MarketType.CRYPTO,
    "SOLUSD": MarketType.CRYPTO,
    "ADAUSDT": MarketType.CRYPTO,
    "LINKUSDT": MarketType.CRYPTO,
    "POLUSD": MarketType.CRYPTO,
    "AVAXUSDT": MarketType.CRYPTO,
    "DOTUSDT": MarketType.CRYPTO,
    "ATOMUSDT": MarketType.CRYPTO,
    "DOGEUSD": MarketType.CRYPTO,
    "XRPUSD": MarketType.CRYPTO,
    "ADAUSD": MarketType.CRYPTO,
    "LINKUSD": MarketType.CRYPTO,
    "AVAXUSD": MarketType.CRYPTO,
    "SHIBUSD": MarketType.CRYPTO,
    "NEARUSD": MarketType.CRYPTO,
    "DOTUSD": MarketType.CRYPTO,
    "ATOMUSD": MarketType.CRYPTO,
    "EURUSD": MarketType.FOREX,
    "GBPUSD": MarketType.FOREX,
    "USDJPY": MarketType.FOREX,
    "AUDUSD": MarketType.FOREX,
    "NZDUSD": MarketType.FOREX,
    "USDCAD": MarketType.FOREX,
    "USDCHF": MarketType.FOREX,
    "GBPJPY": MarketType.FOREX,
    "EURJPY": MarketType.FOREX,
    "AUDJPY": MarketType.FOREX,
    "XAUUSD": MarketType.FOREX,
    "XAGUSD": MarketType.FOREX,
    "XPTUSD": MarketType.FOREX,  # Platinum
    "XPDUSD": MarketType.FOREX,  # Palladium
    "MES": MarketType.FUTURE,
    "MNQ": MarketType.FUTURE,
    "M2K": MarketType.FUTURE,
    "MGC": MarketType.FUTURE,
    "CL": MarketType.FUTURE,
    "ETP-20DEC30-CDE": MarketType.CRYPTO,
    "BIP-20DEC30-CDE": MarketType.CRYPTO,
    "CDEOIL": MarketType.CRYPTO,
    "CDEGLD": MarketType.CRYPTO,
    "CDESIL": MarketType.CRYPTO,
    "CDENGS": MarketType.CRYPTO,
    "CDENGS": MarketType.CRYPTO,
    "B50": MarketType.CRYPTO,
    "BCHUSD": MarketType.CRYPTO,
    "ZECUSD": MarketType.CRYPTO,
}


CRYPTO_SYMBOLS = {
    "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD",
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT", "DOGEUSDT",
    "XRPUSDT", "ADAUSDT", "LINKUSDT", "POLUSD", "AVAXUSDT", "SHIBUSDT", "NEARUSDT", "DOTUSDT", "ATOMUSDT",
    "DOGEUSD", "XRPUSD", "ADAUSD", "LINKUSD", "AVAXUSD", "SHIBUSD", "NEARUSD", "DOTUSD", "ATOMUSD",
    "ETP-20DEC30-CDE", "BIP-20DEC30-CDE",
    # New Volatile Adds
    "DASH/USDC:USDC", "ORDI/USDC:USDC",
    "INJ/USDC:USDC", "AR/USDC:USDC", "ZEN/USDC:USDC", "ETC/USDC:USDC",
    "HYPEUSD", "PEPEUSD", "WIFUSD", "GUSDUSD", "USDPUSD",
    "BCHUSD", "ZECUSD",
}
FOREX_SYMBOLS = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "GBPJPY",
    "EURJPY",
    "AUDJPY",
    "XAUUSD",
    "XAGUSD",
    "XPTUSD",
    "XPDUSD",
    "UNG",
}

FUTURES_SYMBOLS = {"MES", "MNQ", "M2K", "MGC", "CL"}
FUTURES_CONTRACT_SPECS: Dict[str, dict[str, Any]] = {
    # Coinbase Nano Futures (V3)
    "ETP-20DEC30-CDE": {"multiplier": 0.1, "unit": "ETH", "name": "Nano Ether"},
    "BIP-20DEC30-CDE": {"multiplier": 0.01, "unit": "BTC", "name": "Nano Bitcoin"},
}


SUPPORTED_SYMBOLS = [
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "VTI",
    "XLK",
    "XLF",
    "XLE",
    "XLY",
    "XLP",
    "XLI",
    "XLU",
    "SMH",
    "XLB",
    "XOP",
    "XME",
    "ARKK",
    "ARKF",
    "SOXX",
    "GLD",
    "SLV",
    "GDX",
    "USO",
    "UNG",
    "EWU",
    "EWG",
    "EWQ",
    "EWT",
    "EWJ",
    "EWS",
    "FXI",
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LTCUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "POLUSD",
    "AVAXUSDT",
    "SHIBUSDT",
    "NEARUSDT",
    "DOTUSDT",
    "ATOMUSDT",
    "DOGEUSD",
    "XRPUSD",
    "ADAUSD",
    "LINKUSD",
    "AVAXUSD",
    "SHIBUSD",
    "NEARUSD",
    "DOTUSD",
    "ATOMUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "GBPJPY",
    "EURJPY",
    "AUDJPY",
    "XAUUSD",
    "XAGUSD",
    "XPTUSD",
    "XPDUSD",
    "MES",
    "MNQ",
    "M2K",
    "MGC",
    "CL",
    "ETP-20DEC30-CDE",
    "BIP-20DEC30-CDE",
    # Affordable Futures (<$250 notional)
    "SHIB/USD:USD-301220", 
    "AVAX/USD:USD-301220",
    "DOT/USD:USD-301220",
    # High Volatility Gems (<$20 Margin)
    "DASH/USDC:USDC",
    "ORDI/USDC:USDC",
    # New Volatile Adds
    "INJ/USDC:USDC",
    "AR/USDC:USDC",
    "ZEN/USDC:USDC",
    "ETC/USDC:USDC",
    "HYPEUSD",
    "PEPEUSD",
    "WIFUSD",
    "GUSDUSD",
    "GUSDUSD",
    "USDPUSD",
    "BCHUSD",
    "ZECUSD",
]

CRYPTO_BASE_SYMBOLS = {
    "BTCUSD": "BTC", "ETHUSD": "ETH", "SOLUSD": "SOL",
    "BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL", "LTCUSDT": "LTC", "DOGEUSDT": "DOGE",
    "XRPUSDT": "XRP", "ADAUSDT": "ADA", "LINKUSDT": "LINK", "POLUSD": "POL", "AVAXUSDT": "AVAX",
    "SHIBUSDT": "SHIB", "NEARUSDT": "NEAR", "DOTUSDT": "DOT", "ATOMUSDT": "ATOM",
    "DOGEUSD": "DOGE", "ADAUSD": "ADA", "XRPUSD": "XRP", "LINKUSD": "LINK",
    "AVAXUSD": "AVAX", "SHIBUSD": "SHIB", "NEARUSD": "NEAR", "DOTUSD": "DOT",
    "ATOMUSD": "ATOM",
    "ETP-20DEC30-CDE": "ETH", "BIP-20DEC30-CDE": "BTC",
    "BIP": "BTC", "ETP": "ETH",
    "CDENGS/USD:USD-260127": "FANG+",
    "SHIB/USD:USD-301220": "SHIB",
    "AVAX/USD:USD-301220": "AVAX",
    "DOT/USD:USD-301220": "DOT",
    "DASH/USDC:USDC": "DASH",
    "ORDI/USDC:USDC": "ORDI",
    "INJ/USDC:USDC": "INJ",
    "AR/USDC:USDC": "AR",
    "ZEN/USDC:USDC": "ZEN",
    "ETC/USDC:USDC": "ETC",
    "HYPEUSD": "HYPE",
    "PEPEUSD": "PEPE",
    "WIFUSD": "WIF",
    "GUSDUSD": "GUSD",
    "GUSDUSD": "GUSD",
    "USDPUSD": "USDP",
    "BCHUSD": "BCH",
    "ZECUSD": "ZEC",
}
DISABLED_SYMBOLS = {
    # "BIP-20DEC30-CDE", "ETP-20DEC30-CDE", # Re-enabled for management
    "SOL/USD:USD-301220", "XRP/USD:USD-301220", "DOGE/USD:USD-301220", # Whale Traps (>$700)
    "LINK/USD:USD-301220", "BCH/USD:USD-301220", # Also too expensive
    "LTC/USD:USD-301220", # Unaffordable (~$98 margin vs $86 balance)
    "SHIB/USD:USD-301220", # [USER REQUEST] Too expensive / Blacklisted
}


@dataclass
class SymbolMetadata:
    symbol: str
    contract_symbol: str
    asset_class: AssetClass
    market_type: MarketType
    exchange: str
    currency: str
    enabled: bool


SYMBOL_METADATA: Dict[str, SymbolMetadata] = {}
for sym in SUPPORTED_SYMBOLS:
    if sym in CRYPTO_SYMBOLS:
        asset_class = AssetClass.CRYPTO
    elif sym in FOREX_SYMBOLS:
        asset_class = AssetClass.FOREX
    elif sym in FUTURES_SYMBOLS:
        asset_class = AssetClass.FUTURE
    else:
        asset_class = AssetClass.EQUITY
    if asset_class == AssetClass.CRYPTO:
        exchange = "PAXOS"
    elif asset_class == AssetClass.FOREX:
        exchange = "IDEALPRO"
    elif asset_class == AssetClass.FUTURE:
        exchange = "GLOBEX"
    else:
        exchange = "SMART"
    contract_symbol = CRYPTO_BASE_SYMBOLS.get(sym, sym)
    enabled = sym not in DISABLED_SYMBOLS
    
    # Infer MarketType from AssetClass if not explicit
    market_type = SYMBOL_MARKET_TYPE.get(sym)
    if not market_type:
        if asset_class == AssetClass.CRYPTO:
            market_type = MarketType.CRYPTO
        elif asset_class == AssetClass.FOREX:
            market_type = MarketType.FOREX
        elif asset_class == AssetClass.FUTURE:
            market_type = MarketType.FUTURE
        else:
            market_type = MarketType.US_EQUITY
            
    SYMBOL_METADATA[sym] = SymbolMetadata(
        symbol=sym,
        contract_symbol=contract_symbol,
        asset_class=asset_class,
        market_type=market_type,
        exchange=exchange,
        currency="USD",
        enabled=enabled,
    )

def is_coinbase_derivative(symbol: str) -> bool:
    """Return True if the symbol is a Coinbase Derivatives (CDE) product."""
    sym = symbol.upper().strip()
    return sym.startswith("CDE") or sym.endswith("-CDE") or ":USD-" in sym

def is_crypto(symbol: str) -> bool:
    """Return True if the symbol is classified as crypto."""
    sym = symbol.upper().strip()
    if sym in CRYPTO_SYMBOLS:
        return True
    
    # Treat Coinbase Derivatives (BIP, ETP) as 'crypto' for CCXT routing
    # They are Coinbase Nano Futures and should use CCXT provider
    if is_coinbase_derivative(sym):
        return True

    # Heuristic: ends with common crypto quotes
    for quote in ["USD", "USDT", "USDC", "EUR", "GBP"]:
        if sym.endswith(quote) and len(sym) > len(quote):
            # Check if it's NOT in futures or forex (which might also end in USD/GBP)
            if sym in FUTURES_SYMBOLS or sym in FOREX_SYMBOLS:
                return False
            # Check if it's a known non-crypto like XPTUSD/XPDUSD (sometimes in universals)
            if sym in {"XPTUSD", "XPDUSD", "XAUUSD", "XAGUSD"}:
                return False
            # Check if it's a known equity/ETF like GLD (ends in USD-ish but is Equity)
            meta = SYMBOL_METADATA.get(sym)
            if meta and meta.asset_class != AssetClass.CRYPTO:
                return False
            return True
    return False


# Explicit Metal Registration
for meta_sym in ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]:
    SYMBOL_METADATA[meta_sym] = SymbolMetadata(
        symbol=meta_sym,
        contract_symbol=meta_sym,
        asset_class=AssetClass.METAL,
        market_type=MarketType.COMMODITY,
        exchange="SMART",
        currency="USD",
        enabled=True,
    )
