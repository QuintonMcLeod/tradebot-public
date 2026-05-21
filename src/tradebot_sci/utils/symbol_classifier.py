from enum import Enum
from typing import Optional, Callable, Any

class AssetClass(Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"
    ETF = "etf"
    METALS = "metals"
    FUTURES = "futures"
    UNKNOWN = "unknown"

# Known symbol patterns
CRYPTO_SYMBOLS = {
    "BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "LINK", "AVAX", "SHIB", "LTC",
    "DOT", "ATOM", "NEAR", "POL", "BCH", "ZEC", "AAVE", "COMP", "MATIC",
    "UNI", "SUSHI", "MKR", "SNX", "YFI", "CRV", "BAL", "FIL", "MANA",
    "SAND", "AXS", "ENJ", "BAT", "GRT", "LRC", "ALGO", "FTM", "ONE",
    "HBAR", "ICP", "THETA", "VET", "EOS", "XLM", "TRX", "XTZ", "DASH",
    "ETC", "PEPE", "WIF", "BONK", "RENDER", "FET", "TAO", "INJ", "TIA",
    "SUI", "SEI", "APT", "ARB", "OP", "ONDO", "PENDLE", "RUNE", "STX",
}
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

    symbol_upper = symbol.upper().replace("/", "").replace("-", "").replace(":", "").replace("_", "")

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
# These MUST reflect REAL costs or Fee Shield can't block unprofitable trades!
# Round-trip = entry spread/commission + exit spread/commission
BROKER_FEE_DEFAULTS: dict[AssetClass, float] = {
    AssetClass.CRYPTO:  0.005,    # Gemini: ~0.25% taker per leg × 2 = 0.50%
    AssetClass.FOREX:   0.00015,  # OANDA spread-only: EUR/USD ~1.4p, GBP/USD ~2.0p
    AssetClass.STOCKS:  0.001,    # IBKR commission-based, ~0.05% per leg × 2
    AssetClass.ETF:     0.001,    # Same as stocks
    AssetClass.METALS:  0.0005,   # Metals spreads wider than forex (XAUUSD ~3 pips)
    AssetClass.FUTURES: 0.0003,   # IBKR futures, low per-contract cost
    AssetClass.UNKNOWN: 0.002,    # Conservative fallback
}

# ── Live spread provider callback ──
# When set, get_fee_for_symbol() will call this function first to get
# real-time spread data from the broker.  If it returns None, we fall
# back to the static BROKER_FEE_DEFAULTS.
_live_spread_provider: "Callable[[str], float | None] | None" = None


def set_live_spread_provider(provider: "Callable[[str], float | None]") -> None:
    """Register a callback that returns live round-trip spread cost as a decimal
    fraction for a given symbol, or None to signal a fallback to static defaults."""
    global _live_spread_provider
    _live_spread_provider = provider


def get_fee_for_symbol(symbol: str, override: float | None = None) -> float:
    """Return the estimated round-trip fee for *symbol*.

    Priority:
      1. *override* (if given and non-zero) — ``SAFETY_FEE_RT_PCT`` env-var
      2. Live spread provider (if registered and returns a value)
      3. Static ``BROKER_FEE_DEFAULTS``
    """
    if override:
        return override
    # Try live spread from the broker
    if _live_spread_provider is not None:
        live = _live_spread_provider(symbol)
        if live is not None:
            return live
    asset_class = classify_symbol(symbol)
    return BROKER_FEE_DEFAULTS.get(asset_class, 0.004)


def convert_quote_to_usd(amount: float, symbol: str, current_price: float, market_provider: Optional[Any] = None) -> float:
    """Converts a quote currency amount to USD for a given symbol."""
    if amount == 0.0:
        return 0.0

    sym_clean = symbol.upper().replace("_", "").replace("-", "").replace("/", "")
    
    # 1. Quote is already USD, no conversion needed.
    if sym_clean.endswith("USD"):
        return amount
        
    # 2. Base is USD, quote is something else (USDJPY, USDCAD, USDCHF, etc.)
    # The price of the pair is USD/Quote.
    # To convert Quote amount to USD, we divide by USD/Quote rate (which is current_price).
    if sym_clean.startswith("USD") and current_price > 0:
        return amount / current_price
        
    # 3. Cross currency pairs (e.g. AUDJPY, GBPJPY, EURGBP)
    if len(sym_clean) == 6:
        quote = sym_clean[3:]
        conversion_pair = f"USD_{quote}"
        
        if market_provider:
            # Try to get the latest price of USD_quote from the market provider
            try:
                ticker = market_provider.get_ticker(conversion_pair)
                if ticker and ticker.last and ticker.last > 0:
                    return amount / ticker.last
            except Exception:
                pass
                
            try:
                snapshot = market_provider.get_latest_snapshot(conversion_pair, "5m")
                if snapshot and snapshot.candles:
                    rate = snapshot.candles[-1].close
                    if rate > 0:
                        return amount / rate
            except Exception:
                pass

        # Static fallback if market provider fails or is missing
        static_rates = {
            "JPY": 150.0,
            "CAD": 1.35,
            "CHF": 0.90,
            "EUR": 0.92,
            "GBP": 0.80,
            "AUD": 1.50
        }
        if quote in static_rates:
            return amount / static_rates[quote]

    return amount


