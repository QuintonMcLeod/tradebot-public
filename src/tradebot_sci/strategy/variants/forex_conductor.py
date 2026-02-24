"""
Forex Conductor — Session Scheduler with Overlap Zones

Each forex session has a PRIMARY strategy.  During overlap periods
(Asian↔London, London↔US), both strategies evaluate in parallel
and the highest-scoring signal wins.

Session Schedule (UTC):
    00:00–07:00  Asian only         → icc_core (structure trades, any session)
    07:00–09:00  London open        → london_breakout ⇆ volatility_breakout
    09:00–13:00  London only        → london_breakout
    13:00–16:00  London + US Open   → orb_breakout ⇆ volatility_breakout
    16:00–21:00  US Open only       → orb_breakout
    21:00–24:00  Off-peak           → icc_core

Design philosophy: ONE primary strategy per slot to avoid position-lock
cannibalization.  During overlaps, the overlap strategy can only fire
if the primary is silent (no signal).  This ensures the primary's
high-WR trades are NEVER blocked by a competing entry.
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)


# ── Session Windows (UTC) ──────────────────────────────────────────────
_SESSION_WINDOWS = [
    (0,  9,  "icc_core"),               # Asian + early London (structure trades)
    (7,  16, "london_breakout"),         # London (extended to overlap both)
    (7,  9,  "volatility_breakout"),     # London open breakouts (high vol)
    (13, 16, "volatility_breakout"),     # London/US overlap breakouts (highest vol)
    (13, 21, "orb_breakout"),            # US Open (extended to overlap London)
]

# Primary strategy per hour — this strategy ALWAYS evaluates first
# and is never blocked by overlap competitors
_PRIMARY_MAP = {
    # Asian — icc_core (structure trades work in thin liquidity)
    0: "icc_core", 1: "icc_core", 2: "icc_core",
    3: "icc_core", 4: "icc_core", 5: "icc_core",
    6: "icc_core",
    # London open — VB can catch explosive moves, London Breakout primary
    7: "london_breakout", 8: "london_breakout",
    # London sole
    9: "london_breakout", 10: "london_breakout", 11: "london_breakout",
    12: "london_breakout",
    # London/US overlap — highest volume, VB can fire alongside ORB
    13: "orb_breakout", 14: "orb_breakout", 15: "orb_breakout",
    # US sole
    16: "orb_breakout", 17: "orb_breakout", 18: "orb_breakout",
    19: "orb_breakout", 20: "orb_breakout",
    # Off-peak — icc_core
    21: "icc_core", 22: "icc_core", 23: "icc_core",
}

_OFFPEAK_CANDIDATES = ("icc_core", "hyper_scalper")


class ForexConductorStrategy(BaseStrategy):
    """
    Session-based scheduler:  primary-first, overlap-if-silent.

    The primary strategy for each time slot evaluates first.
    If it's silent (no actionable signal), overlap strategies
    and the off-peak all-rounder get a chance.

    With multi_position=True, each sub-strategy can hold its own
    independent position on the same symbol simultaneously.
    """

    multi_position = True  # Each sub-strategy manages its own position

    def __init__(self, profile_settings=None):
        super().__init__("forex_conductor")
        self.profile = profile_settings or {}
        self._strategies: Dict[str, BaseStrategy] = {}
        self._initialized = False

    # ── Lazy Sub-Strategy Loading ──────────────────────────────────────

    def _ensure_loaded(self):
        if self._initialized:
            return

        from tradebot_sci.strategy.variants.breakout import VolatilityBreakoutStrategy
        from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
        from tradebot_sci.strategy.variants.orb_breakout import ORBStrategy
        from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy
        from tradebot_sci.strategy.variants.hyper_scalper import HyperScalperStrategy

        self._strategies = {
            "volatility_breakout": VolatilityBreakoutStrategy(),
            "london_breakout": LondonBreakoutStrategy(),
            "orb_breakout": ORBStrategy(),
            "icc_core": ICCCoreStrategy(),
            "hyper_scalper": HyperScalperStrategy(),
        }

        risk_pct = getattr(self.profile, "risk_per_trade_pct", None)
        if risk_pct:
            for strat in self._strategies.values():
                strat.profile_risk_pct = float(risk_pct)

        self._initialized = True

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "profile_risk_pct" and hasattr(self, "_strategies"):
            for strat in self._strategies.values():
                strat.profile_risk_pct = value

    # ── Session Logic ──────────────────────────────────────────────────

    def _get_utc_hour(self, snapshot: MarketSnapshot) -> int:
        candles = snapshot.candles
        if candles:
            ts = candles[-1].timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc).hour
        return datetime.now(timezone.utc).hour

    def _get_ordered_strategies(self, snapshot: MarketSnapshot, trade_history: Optional[list]) -> List[str]:
        """
        Return strategies in priority order: primary FIRST, then overlap,
        then off-peak.  The caller tries them in order and takes the first
        actionable signal.
        """
        utc_hour = self._get_utc_hour(snapshot)
        primary = _PRIMARY_MAP.get(utc_hour)

        # Collect all active session strategies
        active_session = []
        for start, end, name in _SESSION_WINDOWS:
            if start <= utc_hour < end:
                active_session.append(name)

        # Build priority list: primary first, then others, then off-peak
        ordered: List[str] = []

        if primary:
            ordered.append(primary)
            for name in active_session:
                if name != primary and name not in ordered:
                    ordered.append(name)
        else:
            # Off-peak hours, no primary
            pass

        # Off-peak strategy is always available as fallback
        offpeak = self._pick_offpeak(trade_history)
        if offpeak not in ordered:
            ordered.append(offpeak)

        return ordered

    def _pick_offpeak(self, trade_history: Optional[list]) -> str:
        if not trade_history:
            return "icc_core"

        win_rates: Dict[str, float] = {}
        for candidate in _OFFPEAK_CANDIDATES:
            trades = [
                t for t in trade_history
                if (t.get("strategy") or t.get("meta_source") or t.get("strategy_used", "")) == candidate
            ]
            if not trades:
                continue
            wins = sum(1 for t in trades if (t.get("pnl_usd", 0) or t.get("pnl_realized", 0)) > 0)
            win_rates[candidate] = wins / len(trades)

        if not win_rates:
            return "icc_core"
        return max(win_rates, key=win_rates.get)

    # ── Safe Dispatch Helpers ──────────────────────────────────────────

    def _safe_dispatch_entry(
        self, strat: BaseStrategy, snapshot: MarketSnapshot, gates: dict,
        open_position, current_capital, trade_history,
    ) -> Optional[AITradeDecision]:
        sig_obj = inspect.signature(strat.check_entry_signal)
        params = sig_obj.parameters

        kwargs = {}
        if "open_position" in params:
            kwargs["open_position"] = open_position
        if "current_capital" in params:
            kwargs["current_capital"] = current_capital
        if "trade_history" in params:
            kwargs["trade_history"] = trade_history

        has_varkw = any(p.kind == p.VAR_KEYWORD for p in params.values())
        if has_varkw:
            kwargs["open_position"] = open_position
            kwargs["current_capital"] = current_capital
            kwargs["trade_history"] = trade_history

        return strat.check_entry_signal(snapshot, gates, **kwargs)

    def _safe_dispatch_exit(
        self, strat: BaseStrategy, snapshot: MarketSnapshot,
        open_position: dict, gates: dict, current_capital, trade_history,
    ) -> Optional[AITradeDecision]:
        sig_obj = inspect.signature(strat.check_exit_signal)
        params = sig_obj.parameters

        kwargs = {}
        if "current_capital" in params:
            kwargs["current_capital"] = current_capital
        if "trade_history" in params:
            kwargs["trade_history"] = trade_history

        has_varkw = any(p.kind == p.VAR_KEYWORD for p in params.values())
        if has_varkw:
            kwargs["current_capital"] = current_capital
            kwargs["trade_history"] = trade_history

        return strat.check_exit_signal(snapshot, open_position, gates, **kwargs)

    # ── Scoring ────────────────────────────────────────────────────────

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        self._ensure_loaded()
        ordered = self._get_ordered_strategies(snapshot, None)

        for name in ordered:
            strat = self._strategies.get(name)
            if not strat:
                continue
            try:
                s, g, summary = strat.score_signal(snapshot, gates)
                if s > 0:
                    return s, g, f"Conductor [{name}] {summary}"
            except Exception:
                pass
        return 0.0, "F", "Conductor: no signal"

    # ── Entry ──────────────────────────────────────────────────────────

    def check_entry_signal(
        self, snapshot: MarketSnapshot, gates: dict,
        open_position: Optional[dict] = None,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        self._ensure_loaded()

        ordered = self._get_ordered_strategies(snapshot, trade_history)

        # ── Minimum quality bar ─────────────────────────────────────────
        # Use the engine's ICC grade scoring (0.0-1.0 scale), which
        # properly evaluates HTF/LTF alignment, structure (sweep,
        # continuation), and session health.  Sub-strategy score_signal
        # is inflated (always returns 95-100).
        from tradebot_sci.strategy.engine import StrategyEngine
        MIN_ENTRY_SCORE = 0.85   # A- grade or above (0.0-1.0 scale)

        # Try strategies in priority order: primary → overlap → off-peak
        # Take the FIRST actionable signal that passes the quality bar
        for name in ordered:
            strat = self._strategies.get(name)
            if not strat:
                continue

            try:
                # Route the correct sub-position to this sub-strategy
                # so it can see its own position for pyramid decisions
                sub_pos = open_position
                if open_position and '_sub_positions' in open_position:
                    sub_pos = open_position['_sub_positions'].get(name)

                decision = self._safe_dispatch_entry(
                    strat, snapshot, gates,
                    sub_pos, current_capital, trade_history,
                )
            except Exception as e:
                logger.error(f"[CONDUCTOR] 💥 {name.upper()} crashed: {e}")
                continue

            if decision and decision.action in ("enter_long", "enter_short", "scale_in"):
                # ── Quality gate: ICC grade scoring ─────────────────────
                icc_score = decision.score if decision.score is not None else 0.0
                icc_grade = decision.grade or "F"

                # If the strategy didn't set score/grade, compute via engine
                if icc_score == 0.0:
                    try:
                        tmp_engine = StrategyEngine(
                            ai_client=None,
                            market_provider=None,
                            profile=self.profile,
                            symbol=snapshot.symbol,
                        )
                        icc_score, icc_grade = tmp_engine.score_icc_grade(snapshot)
                    except Exception:
                        icc_score, icc_grade = 0.0, "F"

                if icc_score < MIN_ENTRY_SCORE:
                    logger.info(
                        f"[CONDUCTOR] {snapshot.symbol} REJECTED {name.upper()} "
                        f"({decision.action}): ICC grade={icc_grade} score={icc_score:.2f} < {MIN_ENTRY_SCORE}"
                    )
                    continue  # Try next strategy

                # ── HTF alignment gate ──────────────────────────────────
                htf_dir = snapshot.trend_htf.direction
                trade_dir = "long" if decision.action == "enter_long" else "short"
                if htf_dir != trade_dir and htf_dir != "neutral":
                    logger.info(
                        f"[CONDUCTOR] {snapshot.symbol} REJECTED {name.upper()} "
                        f"({decision.action}): HTF={htf_dir} vs trade={trade_dir}"
                    )
                    continue

                # ── Passed all gates — accept the signal ────────────────
                decision.gates = decision.gates or {}
                decision.gates["meta_source"] = name
                decision.score = icc_score
                decision.grade = icc_grade

                is_primary = name == ordered[0]
                tag = "PRIMARY" if is_primary else "OVERLAP"
                decision.notes = (decision.notes or "") + (
                    f" | [CONDUCTOR] [{tag}] 🎼 {name.upper()} [GRADE={icc_grade}]"
                )

                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol} [{tag}] "
                    f"→ {name.upper()} ({decision.action}) GRADE={icc_grade} score={icc_score:.2f}"
                )
                return decision

        return stand_aside_decision(
            snapshot.symbol, snapshot.timeframe,
            f"Conductor: all {len(ordered)} strategies below quality bar ({', '.join(ordered)})"
        )

    # ── Exit ───────────────────────────────────────────────────────────

    def check_exit_signal(
        self, snapshot: MarketSnapshot, open_position: dict, gates: dict,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        """Sub-strategy exit only fires when the trade is LOSING.
        This cuts losers short (Structure Invalidation, etc.) while
        letting winners run — profit management is handled by
        SafetyGuard (Greedy Exit trailing, ATR Armor breakeven).
        """
        # Only delegate exit to sub-strategy when position is underwater
        pnl = float(open_position.get("unrealized_pnl") or 0.0)
        if pnl >= 0:
            return None  # In profit — let SafetyGuard manage

        self._ensure_loaded()

        source = (
            open_position.get("meta_source")
            or open_position.get("strategy_used")
        )
        if not source or source not in self._strategies:
            source = "icc_core"

        strat = self._strategies.get(source)
        if not strat:
            return None

        try:
            return self._safe_dispatch_exit(
                strat, snapshot, open_position, gates,
                current_capital, trade_history,
            )
        except Exception as e:
            logger.error(f"[CONDUCTOR] Exit crash in {source}: {e}")
            return None
