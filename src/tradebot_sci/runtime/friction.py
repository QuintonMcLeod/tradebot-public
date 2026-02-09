from __future__ import annotations

import logging
from dataclasses import dataclass

from tradebot_sci.market.models import Ticker
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.runtime.rejection_journal import rejection_journal

logger = logging.getLogger(__name__)


@dataclass
class FrictionDecision:
    allow: bool
    reason: str
    spread_bps: float | None = None
    rr: float | None = None


def _spread_bps(ticker: Ticker) -> float | None:
    if ticker.bid is None or ticker.ask is None:
        return None
    mid = (ticker.bid + ticker.ask) / 2.0
    if mid <= 0:
        return None
    return ((ticker.ask - ticker.bid) / mid) * 10_000.0


def _risk_reward_ratio(decision: AITradeDecision) -> float | None:
    if decision.entry_price is None or decision.stop_loss is None or decision.take_profit is None:
        return None
    entry = float(decision.entry_price)
    stop = float(decision.stop_loss)
    tp = float(decision.take_profit)
    if decision.action == "enter_long":
        risk = entry - stop
        reward = tp - entry
    elif decision.action == "enter_short":
        risk = stop - entry
        reward = entry - tp
    else:
        return None
    if risk <= 0:
        return None
    return reward / risk


class FrictionModel:
    """Deterministic pre-trade gate to avoid dying by spread.

    This intentionally does not alter ICC entry logic; it only blocks trades
    when conditions make the expected edge non-viable.
    """

    def __init__(self, *, max_spread_bps: float = 25.0, min_rr: float = 1.2,
                 max_fee_to_reward_ratio: float = 0.25, default_fee_rate: float = 0.004) -> None:
        self.max_spread_bps = max_spread_bps
        self.min_rr = min_rr
        self.max_fee_to_reward_ratio = max_fee_to_reward_ratio
        self.default_fee_rate = default_fee_rate

    def evaluate(self, provider, decision: AITradeDecision) -> FrictionDecision:
        if decision.action not in {"enter_long", "enter_short", "scale_in"}:
            return FrictionDecision(allow=True, reason="not an entry action")

        rr = _risk_reward_ratio(decision)
        if rr is not None and rr < self.min_rr:
            rejection_journal.log(decision.symbol, decision.timeframe, "Friction: R:R", f"rr<{self.min_rr}")
            return FrictionDecision(allow=False, reason=f"rr<{self.min_rr}", rr=rr)

        ticker = self._safe_get_ticker(provider, decision.symbol)
        if ticker is None:
            return FrictionDecision(allow=True, reason="no ticker (skip friction gate)", rr=rr)

        spread = _spread_bps(ticker)
        if spread is None:
            return FrictionDecision(allow=True, reason="no spread (skip friction gate)", rr=rr)
        if spread > self.max_spread_bps:
            rejection_journal.log(decision.symbol, decision.timeframe, "Friction: Spread", f"spread_bps>{self.max_spread_bps}")
            return FrictionDecision(allow=False, reason=f"spread_bps>{self.max_spread_bps}", spread_bps=spread, rr=rr)

        # [ANTIGRAVITY] Fee-cost-to-reward gate: block trades where fees eat the edge
        if decision.entry_price and decision.take_profit:
            entry = float(decision.entry_price)
            tp = float(decision.take_profit)
            expected_reward = abs(tp - entry)
            if expected_reward > 0:
                round_trip_cost = entry * 2 * self.default_fee_rate  # Buy + Sell fees
                fee_ratio = round_trip_cost / expected_reward
                if fee_ratio > self.max_fee_to_reward_ratio:
                    logger.info(
                        f"[FRICTION] Fee-to-Reward BLOCK: {decision.symbol} "
                        f"fees=${round_trip_cost:.4f} / reward=${expected_reward:.4f} = {fee_ratio:.1%} > {self.max_fee_to_reward_ratio:.0%}"
                    )
                    rejection_journal.log(decision.symbol, decision.timeframe, "Friction: Fee Ratio", f"fee_ratio={fee_ratio:.2f}>{self.max_fee_to_reward_ratio}")
                    return FrictionDecision(
                        allow=False,
                        reason=f"fee_ratio={fee_ratio:.2f}>{self.max_fee_to_reward_ratio}",
                        spread_bps=spread, rr=rr,
                    )

        return FrictionDecision(allow=True, reason="ok", spread_bps=spread, rr=rr)

    @staticmethod
    def _safe_get_ticker(provider, symbol: str) -> Ticker | None:
        getter = getattr(provider, "get_ticker", None)
        if not callable(getter):
            return None
        try:
            return getter(symbol)
        except Exception as exc:
            logger.debug("ticker fetch failed for %s: %s", symbol, exc)
            return None

