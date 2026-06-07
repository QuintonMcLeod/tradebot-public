"""
Dynamic Symbol Scoring — Per-symbol score threshold adjustment.

If a symbol is bleeding (3+ consecutive losses or win rate < 30%),
raise its entry score requirement so only higher-quality setups qualify.
If a symbol is printing wins (win rate > 70%), lower the threshold
to catch more of the good wave.

This is defence-in-depth against runaway bleeding on specific pairs
while still allowing profitable pairs to trade freely.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache recent trade lookups for 30 seconds so we don't re-read JSON
# dozens of times per cycle.
_TRADE_CACHE: Dict[str, Tuple[List[dict], float]] = {}
_CACHE_TTL = 30.0


def _load_recent_trades(max_age_hours: int = 72) -> List[dict]:
    """Load recent closed trades from the appropriate results file."""
    # Determine which file to read based on paper vs live mode.
    # Paper mode writes to paper_trade_results.json; live writes to trade_results.json
    # We read whichever has the most recent activity.
    candidates = []
    base = Path.home() / ".config" / "tradebot-sci-gui" / "local" / "data"
    for fname in ("paper_trade_results.json", "trade_results.json"):
        p = base / fname
        if p.exists():
            try:
                mtime = p.stat().st_mtime
                candidates.append((mtime, p))
            except Exception:
                pass

    if not candidates:
        return []

    # Prefer the most recently written file
    candidates.sort(reverse=True)
    path = candidates[0][1]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("trades", [])
    except Exception as e:
        logger.debug(f"[DynamicScoring] Failed to load trades from {path}: {e}")
        return []


def _get_symbol_stats(symbol: str, lookback: int) -> Tuple[int, int, int, float]:
    """Return (total_trades, wins, losses, win_rate) for symbol's recent history."""
    cache_key = "all_trades"
    now = datetime.now(timezone.utc).timestamp()
    cached = _TRADE_CACHE.get(cache_key)
    if cached and (now - cached[1]) < _CACHE_TTL:
        all_trades = cached[0]
    else:
        all_trades = _load_recent_trades()
        _TRADE_CACHE[cache_key] = (all_trades, now)

    # Filter to this symbol, newest first
    symbol_trades = [
        t for t in all_trades
        if t.get("symbol", "").upper().replace("_", "") == symbol.upper().replace("_", "")
        and t.get("closed_at")
    ]
    symbol_trades.sort(
        key=lambda t: t.get("closed_at", ""),
        reverse=True,
    )

    recent = symbol_trades[:lookback]
    if not recent:
        return 0, 0, 0, 0.0

    wins = sum(1 for t in recent if t.get("is_win", False))
    losses = len(recent) - wins
    win_rate = wins / len(recent)
    return len(recent), wins, losses, win_rate


def _consecutive_losses(symbol: str, lookback: int) -> int:
    """Count the most recent consecutive losses for a symbol."""
    cache_key = "all_trades"
    now = datetime.now(timezone.utc).timestamp()
    cached = _TRADE_CACHE.get(cache_key)
    if cached and (now - cached[1]) < _CACHE_TTL:
        all_trades = cached[0]
    else:
        all_trades = _load_recent_trades()
        _TRADE_CACHE[cache_key] = (all_trades, now)

    symbol_trades = [
        t for t in all_trades
        if t.get("symbol", "").upper().replace("_", "") == symbol.upper().replace("_", "")
        and t.get("closed_at")
    ]
    symbol_trades.sort(key=lambda t: t.get("closed_at", ""), reverse=True)

    streak = 0
    for t in symbol_trades[:lookback]:
        if not t.get("is_win", False):
            streak += 1
        else:
            break
    return streak


def get_adjusted_threshold(
    symbol: str,
    base_threshold: float,
    profile_settings = None,
) -> float:
    """Return the dynamically adjusted score threshold for a symbol.

    Parameters
    ----------
    symbol : str
        The trading symbol (e.g. "EURUSD").
    base_threshold : float
        The strategy's raw score requirement (e.g. 60.0).
    profile_settings :
        Optional profile / settings object. If None, reads from global
        get_settings() automatically.

    Returns
    -------
    float
        The adjusted threshold, clamped to [min_threshold, max_threshold].
    """
    # If no profile_settings provided, read from global settings
    if profile_settings is None:
        try:
            from tradebot_sci.config.loader import get_settings
            profile_settings = get_settings().performance
        except Exception:
            return base_threshold

    if not getattr(profile_settings, "dynamic_symbol_scoring_enabled", False):
        return base_threshold

    lookback = int(getattr(profile_settings, "dynamic_score_lookback", 10))
    loss_streak_trigger = int(getattr(profile_settings, "dynamic_score_loss_streak", 3))
    min_winrate = float(getattr(profile_settings, "dynamic_score_min_winrate", 0.30))
    boost_winrate = float(getattr(profile_settings, "dynamic_score_boost_winrate", 0.70))
    penalty = float(getattr(profile_settings, "dynamic_score_penalty", 15.0))
    reward = float(getattr(profile_settings, "dynamic_score_reward", 10.0))
    max_thresh = float(getattr(profile_settings, "dynamic_score_max_threshold", 85.0))
    min_thresh = float(getattr(profile_settings, "dynamic_score_min_threshold", 45.0))

    total, wins, losses, win_rate = _get_symbol_stats(symbol, lookback)
    streak = _consecutive_losses(symbol, lookback)

    adjustment = 0.0

    # Underperformance triggers
    if streak >= loss_streak_trigger:
        adjustment += penalty
        logger.info(
            f"[DynamicScoring] {symbol}: loss streak {streak} >= {loss_streak_trigger}, "
            f"raising threshold by +{penalty:.0f} points"
        )
    elif total > 0 and win_rate < min_winrate:
        adjustment += penalty * 0.5
        logger.info(
            f"[DynamicScoring] {symbol}: win rate {win_rate:.0%} < {min_winrate:.0%}, "
            f"raising threshold by +{penalty * 0.5:.0f} points"
        )

    # Outperformance reward
    if total > 0 and win_rate >= boost_winrate:
        adjustment -= reward
        logger.info(
            f"[DynamicScoring] {symbol}: win rate {win_rate:.0%} >= {boost_winrate:.0%}, "
            f"lowering threshold by -{reward:.0f} points"
        )

    adjusted = base_threshold + adjustment
    adjusted = max(min_thresh, min(max_thresh, adjusted))

    if adjustment != 0.0:
        logger.info(
            f"[DynamicScoring] {symbol}: base={base_threshold:.0f} adjustment={adjustment:+.0f} "
            f"final={adjusted:.0f} (recent: {wins}W/{losses}L over {total})",
            extra={"symbol": symbol, "base_threshold": base_threshold,
                   "adjusted_threshold": adjusted, "adjustment": adjustment,
                   "wins": wins, "losses": losses, "lookback": total}
        )

    return adjusted
