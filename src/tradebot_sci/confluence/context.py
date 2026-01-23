from __future__ import annotations

import logging
import time
import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from tradebot_sci.market.models import Candle, OrderBook, Ticker
from tradebot_sci.market.symbols import AssetClass, SYMBOL_METADATA

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceSnapshot:
    data: dict


def build_confluence(
    provider,
    symbol: str,
    candles: list[Candle],
    *,
    timezone: str = "America/New_York",
    include_external: bool = False,
) -> ConfluenceSnapshot:
    """Builds a minimal, auditable confluence bundle.

    This is intentionally optional and side-effect free:
    - Always: session context, volatility, (optional) spread/orderbook depth from provider.
    - Optional: external reference data (e.g. VIX) if include_external is enabled.
    """
    symbol_key = symbol.upper()
    meta = SYMBOL_METADATA.get(symbol_key)
    asset_class = meta.asset_class if meta else None

    now = candles[-1].timestamp if candles else datetime.now(ZoneInfo("UTC"))
    local = now.astimezone(ZoneInfo(timezone))
    session = _infer_session(asset_class, local)

    vol_20 = _volatility_20(candles[-21:])
    ticker = _safe_get_ticker(provider, symbol_key)
    spread_bps = _spread_bps(ticker) if ticker else None
    depth_usd = None
    book = _safe_get_order_book(provider, symbol_key)
    if book:
        depth_usd = _top_depth_usd(book, levels=10)

    data: dict = {
        "timestamp_local": local.isoformat(),
        "timezone": timezone,
        "asset_class": asset_class.value if asset_class is not None else "unknown",
        "session": session,
        "volatility_20": vol_20,
    }
    if spread_bps is not None:
        data["spread_bps"] = spread_bps
    if depth_usd is not None:
        data["orderbook_depth_usd_top10"] = depth_usd

    if include_external:
        vix = fetch_stooq_close("vix", timeout=3.0)
        if vix is not None:
            data["vix_close"] = vix

    confluence_score = _compute_confluence_score(data)
    data["confluence_score"] = confluence_score
    data["risk_cap_pct"] = _compute_risk_cap_pct(data, confluence_score)

    return ConfluenceSnapshot(data=data)


def _infer_session(asset_class: AssetClass | None, local_time: datetime) -> str:
    # Minimal session labeling (kept deterministic; no holiday calendar yet).
    weekday = local_time.weekday()  # Mon=0 .. Sun=6
    if asset_class == AssetClass.EQUITY:
        if weekday >= 5:
            return "US_CLOSED_WEEKEND"
        minutes = local_time.hour * 60 + local_time.minute
        if 9 * 60 + 30 <= minutes < 16 * 60:
            return "US_CASH"
        return "US_OFF_HOURS"
    if asset_class == AssetClass.CRYPTO:
        return "CRYPTO_24_7"
    return "UNKNOWN"


def _volatility_20(candles: list[Candle]) -> float | None:
    if len(candles) < 3:
        return None
    returns: list[float] = []
    for prev, curr in zip(candles, candles[1:]):
        if prev.close <= 0:
            continue
        returns.append((curr.close - prev.close) / prev.close)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return abs(var ** 0.5)


def _safe_get_ticker(provider, symbol: str) -> Ticker | None:
    getter = getattr(provider, "get_ticker", None)
    if not callable(getter):
        return None
    try:
        return getter(symbol)
    except Exception as e:
        logger.debug(f"Failed to get ticker for {symbol}: {e}")
        return None


def _safe_get_order_book(provider, symbol: str) -> OrderBook | None:
    getter = getattr(provider, "get_order_book", None)
    if not callable(getter):
        return None
    try:
        return getter(symbol)
    except Exception as e:
        logger.debug(f"Failed to get order book for {symbol}: {e}")
        return None


def _spread_bps(ticker: Ticker) -> float | None:
    if ticker.bid is None or ticker.ask is None:
        return None
    mid = (ticker.bid + ticker.ask) / 2.0
    if mid <= 0:
        return None
    return float(((ticker.ask - ticker.bid) / mid) * 10_000.0)


def _top_depth_usd(book: OrderBook, *, levels: int = 10) -> float:
    bids = book.bids[:levels]
    asks = book.asks[:levels]
    depth = sum(l.price * l.size for l in bids) + sum(l.price * l.size for l in asks)
    return float(depth)


def _compute_confluence_score(data: dict) -> float:
    """Returns a simple 0..1 confluence score based on available context.

    This is intentionally conservative: missing fields do not increase the score.
    """
    points = 0.0
    total = 0.0

    session = data.get("session")
    session_score = {
        "US_CASH": 1.0,
        "US_OFF_HOURS": 0.6,
        "US_CLOSED_WEEKEND": 0.0,
        "CRYPTO_24_7": 0.8,
        "UNKNOWN": 0.5,
    }.get(session, 0.5)
    points += session_score
    total += 1.0

    spread_bps = data.get("spread_bps")
    if isinstance(spread_bps, (int, float)):
        total += 1.0
        if spread_bps <= 20:
            points += 1.0
        elif spread_bps <= 50:
            points += 0.6
        elif spread_bps <= 100:
            points += 0.2
        else:
            points += 0.0

    depth_usd = data.get("orderbook_depth_usd_top10")
    if isinstance(depth_usd, (int, float)):
        total += 1.0
        # Generic thresholds; asset-specific tuning can come later.
        if depth_usd >= 1_000_000:
            points += 1.0
        elif depth_usd >= 250_000:
            points += 0.7
        elif depth_usd >= 50_000:
            points += 0.4
        else:
            points += 0.0

    vol_20 = data.get("volatility_20")
    if isinstance(vol_20, (int, float)):
        total += 1.0
        # Sweet-spot heuristic: avoid dead/ultra-spiky.
        if 0.002 <= vol_20 <= 0.02:
            points += 1.0
        elif 0.001 <= vol_20 <= 0.05:
            points += 0.5
        else:
            points += 0.0

    vix = data.get("vix_close")
    if isinstance(vix, (int, float)):
        total += 1.0
        # Lower VIX -> cleaner conditions (heuristic).
        if vix <= 20:
            points += 1.0
        elif vix <= 30:
            points += 0.6
        elif vix <= 40:
            points += 0.3
        else:
            points += 0.0

    if total <= 0:
        return 0.0
    return float(max(0.0, min(1.0, points / total)))


def _compute_risk_cap_pct(data: dict, confluence_score: float) -> float:
    """Returns a deterministic risk cap (fractional 0..1)."""
    # Relaxed caps for hyper-growth: low=5%, medium=10%, high=15%, ultra=25%.
    if confluence_score >= 0.8:
        cap = 0.25
    elif confluence_score >= 0.65:
        cap = 0.15
    elif confluence_score >= 0.5:
        cap = 0.10
    else:
        cap = 0.05

    spread_bps = data.get("spread_bps")
    if isinstance(spread_bps, (int, float)) and spread_bps > 100:
        cap = min(cap, 0.02)

    asset_class = data.get("asset_class")
    friction_fail_safe = os.getenv("FRICTION_FAIL_SAFE", "true").lower() == "true"
    friction_risk_cap = float(os.getenv("FRICTION_RISK_CAP", "0.05"))
    if friction_fail_safe and asset_class == "crypto" and not isinstance(spread_bps, (int, float)):
        cap = min(cap, friction_risk_cap)

    vix_present = isinstance(data.get("vix_close"), (int, float))
    vix_fail_safe = os.getenv("VIX_FAIL_SAFE", "true").lower() == "true"
    vix_risk_cap = float(os.getenv("VIX_RISK_CAP", "0.05"))
    if asset_class == "equity" and vix_fail_safe and not vix_present:
        cap = min(cap, vix_risk_cap)

    # Session hard limits (equities outside hours should generally be lower risk).
    session = data.get("session")
    if session == "US_CLOSED_WEEKEND":
        cap = min(cap, 0.0)
    if session == "US_OFF_HOURS":
        cap = min(cap, 0.05)

    return float(max(0.0, min(0.30, cap)))


_STOOQ_CACHE: dict[str, tuple[float, float]] = {}


def fetch_stooq_close(symbol: str, *, timeout: float = 3.0, cache_ttl_seconds: int = 300) -> float | None:
    """Fetches last close from Stooq (free CSV endpoint) with a small cache.

    Returns None on any failure (network, parse, empty result).
    """
    sym = symbol.strip().lower()
    now = time.time()
    cached = _STOOQ_CACHE.get(sym)
    if cached and now - cached[0] < cache_ttl_seconds:
        return cached[1]
    url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        header = lines[0].split(",")
        row = lines[1].split(",")
        if len(row) != len(header):
            return None
        mapping = dict(zip(header, row))
        close_str = mapping.get("Close")
        if not close_str or close_str in {"-", "N/A"}:
            return None
        close = float(close_str)
        _STOOQ_CACHE[sym] = (now, close)
        return close
    except Exception as e:
        logger.debug(f"Failed to fetch Stooq data for {sym}: {e}")
        return None
