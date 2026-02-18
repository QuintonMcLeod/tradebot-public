from enum import Enum
from typing import Optional

class AssetClass(Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"
    ETF = "etf"
    METALS = "metals"
    FUTURES = "futures"
    UNKNOWN = "unknown"

# Known symbol patterns
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "LINK", "AVAX", "SHIB", "LTC", "DOT", "ATOM", "NEAR", "POL"}
FOREX_PAIRS = {"EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
METALS = {"XAU", "XAG", "XPT", "XPD", "GLD", "SLV", "GDX"}
ETF_SYMBOLS = {"SPY", "QQQ", "DIA", "IWM", "VTI", "XLK", "XLF", "XLE", "XLY", "XLP", "XLI", "XLU", "SMH", "XLB", "XOP", "XME", "ARKK", "ARKF", "SOXX", "USO", "UNG", "EWU", "EWG", "EWQ", "EWT", "EWJ", "EWS", "FXI"}
FUTURES_SYMBOLS = {"ES", "NQ", "MES", "MNQ", "M2K", "MGC", "CL", "GC", "SI", "HG", "NG"}

def classify_symbol(symbol: str) -> AssetClass:
    """
    Classify a trading symbol into its asset class.

    Args:
        symbol: The trading symbol (e.g., "BTCUSD", "EURUSD", "SPY")

    Returns:
        AssetClass enum value
    """
    if not symbol:
        return AssetClass.UNKNOWN

    symbol_upper = symbol.upper().replace("/", "").replace("-", "").replace(":", "")

    # Check for futures expiry format (e.g., "ETH/USD:USD-260130")
    if ":" in symbol and "-" in symbol.split(":")[-1]:
        # Extract base symbol
        base = symbol.split("/")[0].upper()
        if base in CRYPTO_SYMBOLS:
            return AssetClass.FUTURES  # Crypto futures
        return AssetClass.FUTURES

    # Check for crypto
    for crypto in CRYPTO_SYMBOLS:
        if symbol_upper.startswith(crypto) or crypto in symbol_upper:
            return AssetClass.CRYPTO

    # Check for forex pairs (6-char format: EURUSD, GBPJPY, etc.)
    if len(symbol_upper) == 6:
        base = symbol_upper[:3]
        quote = symbol_upper[3:]
        if base in FOREX_PAIRS and quote in FOREX_PAIRS:
            return AssetClass.FOREX

    # Check for metals
    for metal in METALS:
        if symbol_upper.startswith(metal) or metal in symbol_upper:
            return AssetClass.METALS

    # Check for ETFs
    if symbol_upper in ETF_SYMBOLS:
        return AssetClass.ETF

    # Check for futures
    if symbol_upper in FUTURES_SYMBOLS:
        return AssetClass.FUTURES

    # Default to stocks for single-ticker symbols (1-5 chars)
    if symbol_upper.isalpha() and 1 <= len(symbol_upper) <= 5:
        return AssetClass.STOCKS

    return AssetClass.UNKNOWN


# ── Per-broker round-trip fee defaults (decimal, e.g. 0.008 = 0.8%) ──
BROKER_FEE_DEFAULTS: dict[AssetClass, float] = {
    AssetClass.CRYPTO:  0.008,    # Gemini / CCXT: ~0.4% per leg × 2
    AssetClass.FOREX:   0.0004,   # OANDA spread cost ~0.02% per leg × 2
    AssetClass.STOCKS:  0.002,    # IBKR commission-based, ~0.1% per leg × 2
    AssetClass.ETF:     0.002,    # Same as stocks
    AssetClass.METALS:  0.001,    # Tight spread metals via OANDA / IBKR
    AssetClass.FUTURES: 0.001,    # IBKR futures, low per-contract cost
    AssetClass.UNKNOWN: 0.004,    # Conservative fallback
}


def get_fee_for_symbol(symbol: str, override: float | None = None) -> float:
    """Return the estimated round-trip fee for *symbol*.

    If *override* is given and non-zero it takes precedence (allows the
    ``SAFETY_FEE_RT_PCT`` env-var to act as a global override).
    """
    if override:
        return override
    asset_class = classify_symbol(symbol)
    return BROKER_FEE_DEFAULTS.get(asset_class, 0.004)

