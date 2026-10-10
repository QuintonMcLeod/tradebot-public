"""What an entry costs, priced once, where every strategy can see it.

The engine fetches the live bid/ask on every cycle and hands the difference to the
strategy as ``gates["current_spread"]``. Until 2026-10-10 nothing read that value, and
the guards that did exist tested three different numbers:

* ``forex_scrape_fade`` tested the per-pair AVERAGE spread from the measured table
  against its declared 1.9-pip ceiling, so an entry the guard admitted could still be
  quoted far above it, and the eleven pairs the table does not cover passed unchecked
  (facts 178 and 179).
* ``paper_broker`` compared an estimated round trip, taken from the measured table or
  else a 1-basis-point configuration fallback, against 30 percent of the intended risk.
* ``oanda_broker`` compared the ONE-WAY live spread against 30 percent of the stop
  distance, while its own comment calls that a round trip.

This module is the single answer to "what does this entry cost", in pips and as a share
of the risk unit, so every strategy is judged on the same number and by the same rule.
The preference order matters and is deliberate: the quote at the decision bar is what
the trade would actually pay, the measured table is a per-pair average and is only a
fallback for paths with no live quote, and when neither exists the cost is UNKNOWN.
Unknown is not cheap, and the caller decides whether to refuse it.

Nothing here reads the outcome of a trade, so the gate cannot select on the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# A pip is the fourth decimal on most pairs and the second on the yen crosses.
PIP_SIZE = 0.0001
PIP_SIZE_JPY = 0.01

LIVE_QUOTE = "live bid/ask"
MEASURED_TABLE = "measured table"


def pip_size(symbol: str) -> float:
    """Pip size in price terms for *symbol*."""
    return PIP_SIZE_JPY if "JPY" in (symbol or "").upper() else PIP_SIZE


def measured_toll_pips(symbol: str, reference_price: Optional[float]) -> Optional[float]:
    """The pair's average round trip in pips, from the measured table, or None.

    The table is one number per pair and covers 15 of the 26 forex symbols in the
    active profile, so None means "this pair has never been measured" and not "free".
    """
    if not reference_price or reference_price <= 0:
        return None
    try:
        from tradebot_sci.broker.paper_broker import _measured_spread_bps
    except Exception:
        return None
    try:
        bps = _measured_spread_bps(symbol)
    except Exception:
        return None
    if bps is None:
        return None
    try:
        return (float(bps) / 10000.0) * float(reference_price) / pip_size(symbol)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def live_toll_pips(gates: Any, symbol: str) -> Optional[float]:
    """The toll quoted for this cycle, in pips, from ``gates["current_spread"]``.

    The engine writes a PRICE difference there, so it is divided by the pip size. A
    non-positive reading is treated as no quote: a replay reports bid equal to ask
    because its data carries no spread field, which is the truth and not a free trade.
    """
    if not isinstance(gates, dict):
        return None
    live = gates.get("current_spread")
    try:
        if live:
            pips = float(live) / pip_size(symbol)
            if pips > 0:
                return pips
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return None


def entry_toll(symbol: str, gates: Any, reference_price: Optional[float]) -> tuple[Optional[float], Optional[str]]:
    """What this entry costs to get in, in pips, and where the number came from.

    Returns ``(pips, source)`` with both None when the cost cannot be priced.
    """
    live = live_toll_pips(gates, symbol)
    if live is not None:
        return live, LIVE_QUOTE
    measured = measured_toll_pips(symbol, reference_price)
    if measured is not None:
        return measured, MEASURED_TABLE
    return None, None


def risk_pips(entry_price: Any, stop_loss: Any, symbol: str) -> Optional[float]:
    """The risk unit, in pips, from the bracket the decision carries.

    None when either end is missing or the two are equal, which means the risk unit is
    not known at the decision and the cost cannot be expressed as a share of it.
    """
    try:
        entry = float(entry_price)
        stop = float(stop_loss)
    except (TypeError, ValueError):
        return None
    distance = abs(entry - stop)
    if distance <= 0:
        return None
    return distance / pip_size(symbol)


def cost_fraction(toll: Optional[float], risk: Optional[float]) -> Optional[float]:
    """The toll as a fraction of the risk unit, or None when either is unknown."""
    if toll is None or risk is None or risk <= 0:
        return None
    return float(toll) / float(risk)


@dataclass(frozen=True)
class CostVerdict:
    """The gate's answer, with the working kept so the journal can state it."""

    allowed: bool
    toll_pips: Optional[float]
    toll_source: Optional[str]
    risk_pips: Optional[float]
    fraction: Optional[float]
    ceiling: float
    reason: Optional[str] = None

    @property
    def over_ceiling(self) -> bool:
        return self.fraction is not None and self.fraction > self.ceiling

    def readout(self) -> str:
        """One line stating the toll, in pips and as a share of the risk unit."""
        if self.toll_pips is None:
            return (
                f"entry cost unknown: no live quote and no measured table entry, so the "
                f"{self.ceiling:.0%} ceiling cannot be checked"
            )
        share = f"{100.0 * self.fraction:.1f}% of R" if self.fraction is not None else "R unknown"
        risk = f"{self.risk_pips:.1f}p" if self.risk_pips is not None else "unknown"
        return (
            f"entry cost {self.toll_pips:.2f}p ({share}, risk unit {risk}) "
            f"from {self.toll_source}, ceiling {self.ceiling:.0%} of R"
        )


def check_entry_cost(
    symbol: str,
    gates: Any,
    entry_price: Any,
    stop_loss: Any,
    ceiling: float = 0.30,
    refuse_unknown: bool = True,
    reference_price: Optional[float] = None,
) -> CostVerdict:
    """Judge one entry against the ceiling, on the quote it would actually pay.

    ``ceiling`` is the maximum toll as a fraction of the risk unit, so it travels with
    the stop: the same 1.5-pip spread is 15 percent of R behind a 10-pip stop and 5
    percent behind a 30-pip stop. A decision that carries no stop cannot be judged
    against a share of R at all, so it is allowed through and said to be unjudged; the
    bracket validation downstream owns a missing stop, not this gate.
    """
    toll, source = entry_toll(symbol, gates, reference_price if reference_price else entry_price)
    risk = risk_pips(entry_price, stop_loss, symbol)
    fraction = cost_fraction(toll, risk)

    if risk is None:
        return CostVerdict(
            allowed=True,
            toll_pips=toll,
            toll_source=source,
            risk_pips=None,
            fraction=None,
            ceiling=ceiling,
            reason="no stop on the decision, so the cost cannot be judged as a share of R",
        )

    if toll is None:
        if refuse_unknown:
            return CostVerdict(
                allowed=False,
                toll_pips=None,
                toll_source=None,
                risk_pips=risk,
                fraction=None,
                ceiling=ceiling,
                reason=(
                    f"entry cost unknown: {symbol} is absent from the measured spread "
                    f"table and no live quote is available, so the {ceiling:.0%} of R "
                    f"ceiling cannot be checked"
                ),
            )
        return CostVerdict(
            allowed=True,
            toll_pips=None,
            toll_source=None,
            risk_pips=risk,
            fraction=None,
            ceiling=ceiling,
            reason="entry cost unknown and the gate is configured to allow it",
        )

    if fraction is not None and fraction > ceiling:
        return CostVerdict(
            allowed=False,
            toll_pips=toll,
            toll_source=source,
            risk_pips=risk,
            fraction=fraction,
            ceiling=ceiling,
            reason=(
                f"entry cost {toll:.2f}p is {100.0 * fraction:.1f}% of the {risk:.1f}p "
                f"risk unit, above the {ceiling:.0%} ceiling (from {source})"
            ),
        )

    return CostVerdict(
        allowed=True,
        toll_pips=toll,
        toll_source=source,
        risk_pips=risk,
        fraction=fraction,
        ceiling=ceiling,
    )
