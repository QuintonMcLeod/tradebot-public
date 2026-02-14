from __future__ import annotations

from typing import Iterable

from tradebot_sci.market.symbols import AssetClass, SYMBOL_METADATA


def get_market_symbols(settings) -> list[str]:
    symbols = getattr(settings.market, "symbols", None) or []
    if symbols:
        return list(symbols)
    default_symbol = getattr(settings.market, "default_symbol", None)
    return [default_symbol] if default_symbol else []


def filter_crypto_symbols(symbols: Iterable[str]) -> list[str]:
    allowed: list[str] = []
    for symbol in symbols:
        metadata = SYMBOL_METADATA.get(str(symbol).upper())
        if metadata and metadata.asset_class == AssetClass.CRYPTO:
            allowed.append(str(symbol))
    return allowed


def resolve_symbol_universe(settings, profile_settings, profile_name: str) -> list[str]:
    import logging
    logger = logging.getLogger(__name__)
    
    if getattr(profile_settings, "symbols", None):
        symbols = list(profile_settings.symbols)
        logger.info(f"[UNIVERSE-DEBUG] Profile {profile_name} raw symbols (count={len(symbols)}): {symbols}")
    else:
        logger.info(f"[UNIVERSE-DEBUG] Profile {profile_name} has no symbols, checking market settings.")
        symbols = get_market_symbols(settings)

    if getattr(profile_settings, "crypto_only", False):
        logger.info(f"[UNIVERSE-DEBUG] Profile {profile_name} is crypto_only. Filtering...")
        before = len(symbols)
        symbols = filter_crypto_symbols(symbols)
        logger.info(f"[UNIVERSE-DEBUG] Filtered crypto symbols: {before} -> {len(symbols)}. Result: {symbols}")

    # Filter out disabled symbols (e.g. BTC/ETH due to insufficient funds)
    final_symbols = []
    for s in symbols:
        meta = SYMBOL_METADATA.get(str(s).upper())
        if meta and not meta.enabled:
            logger.info(f"[UNIVERSE-DEBUG] Dropping disabled symbol: {s}")
            continue
        final_symbols.append(s)
    symbols = final_symbols

    if symbols:
        return symbols

    default_symbol = getattr(settings.market, "default_symbol", None)
    logger.warning(f"[UNIVERSE-DEBUG] No symbols resolved! Falling back to default: {default_symbol}")
    return [default_symbol] if default_symbol else []


def instrument_classes_for_symbols(symbols: Iterable[str]) -> list[str]:
    asset_classes: set[str] = set()
    for symbol in symbols:
        metadata = SYMBOL_METADATA.get(str(symbol).upper())
        asset_classes.add(metadata.asset_class.value if metadata else "unknown")
    return sorted(asset_classes)
