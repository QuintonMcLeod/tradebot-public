"""
Forex Conductor — Regime-Based Strategy Router

Routes to the correct strategy based on market_regime from trend detection:
- trending    → EMA Trend Rider (pullback entries in established trends)
- ranging     → Mean Reversion (bounce off Bollinger Bands)
- transitional → Session Breakout (Asian box breakout at London open)
- choppy      → BLOCK all entries (no edge in choppy markets)

Session Momentum fires at session opens regardless of regime.
"""

from __future__ import annotations
import logging
from datetime import time
from zoneinfo import ZoneInfo
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy
from tradebot_sci.strategy.variants.trend_rider import TrendRiderStrategy
from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
from tradebot_sci.strategy.variants.session_momentum import SessionMomentumStrategy
from tradebot_sci.strategy.variants.wind_down_truffle import WindDownTruffleStrategy

logger = logging.getLogger(__name__)

# ── Regime → Strategy mapping ────────────────────────────────────────
_REGIME_MAP = {
    "trending":      "trend_rider",
    "ranging":       "mean_reversion",
    "transitional":  "session_breakout",
    # "choppy" → no entry (handled explicitly)
}

# ── Per-symbol loss streak cooldown ──────────────────────────────────
_loss_streaks: dict[str, int] = {}
_cooldown_bars: dict[str, int] = {}
_COOLDOWN_TRIGGER = 3
_COOLDOWN_BARS = 6

# ── Per-symbol entry cooldown (prevents rapid re-entry after stops) ──
_entry_cooldown: dict[str, int] = {}
_ENTRY_COOLDOWN_BARS = 0  # Disabled — other guardrails handle spacing

# ── SAR: conductor delegates to engine for detection/cooldowns. ──────
# Engine populates gates["sar_dir"] ("long"/"short"/None) before
# calling check_entry_signal. Conductor reads it here to either
# constrain sub-strategy direction or compute an ATR forced entry.
_SAR_RISK_PCT = 0.027  # ~$60 max SAR loss per trade at 5.7k balance


def _check_loss_cooldown(symbol: str) -> bool:
    return _cooldown_bars.get(symbol, 0) > 0


def _update_cooldown(symbol: str, is_loss: bool):
    if is_loss:
        _loss_streaks[symbol] = _loss_streaks.get(symbol, 0) + 1
        if _loss_streaks[symbol] >= _COOLDOWN_TRIGGER:
            _cooldown_bars[symbol] = _COOLDOWN_BARS
            logger.info(
                f"[CONDUCTOR] {symbol}: {_loss_streaks[symbol]} consecutive "
                f"losses → {_COOLDOWN_BARS}-bar cooldown"
            )
    else:
        _loss_streaks[symbol] = 0


def _tick_cooldowns(symbol: str):
    """Tick cooldowns for a SINGLE symbol only.

    This must only tick the given symbol because the function is called
    once per symbol per bar.  With N symbols, calling it N times and
    ticking ALL symbols each time would make cooldowns expire N× faster
    — a nasty coupling bug that changes behaviour depending on how many
    pairs are traded.
    """
    if symbol in _cooldown_bars and _cooldown_bars[symbol] > 0:
        _cooldown_bars[symbol] -= 1
    if symbol in _entry_cooldown and _entry_cooldown[symbol] > 0:
        _entry_cooldown[symbol] -= 1


class ForexConductorStrategy(BaseStrategy):
    """
    Forex Conductor — routes to strategies based on market regime.
    """

    def __init__(self, **kwargs):
        # Build _strategies BEFORE super().__init__() because BaseStrategy's
        # __init__ sets self.profile_risk_pct = None which triggers our
        # property setter, which iterates self._strategies.
        self._profile_risk_pct: float | None = None
        self._strategies = {
            "mean_reversion": MeanReversionStrategy(),
            "session_breakout": LondonBreakoutStrategy(),
            "trend_rider": TrendRiderStrategy(),
            "session_momentum": SessionMomentumStrategy(),
            "wind_down_truffle": WindDownTruffleStrategy(),
        }
        self.quick_ranging_tp_enabled = kwargs.get('quick_ranging_tp_enabled', False)
        self._profile = kwargs.get('profile_settings', None)
        super().__init__("Forex Conductor")

    # ── Risk propagation ────────────────────────────────────────────────
    # The parent BaseStrategy stores risk in profile_risk_pct.  When the
    # engine injects the live profile's risk (e.g. 4.5%), we must cascade
    # it to every child strategy — otherwise they all fall back to 1%.
    @property
    def profile_risk_pct(self):
        return self._profile_risk_pct

    @profile_risk_pct.setter
    def profile_risk_pct(self, value):
        self._profile_risk_pct = value
        for strat in getattr(self, '_strategies', {}).values():
            strat.profile_risk_pct = value


    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        if open_position:
            return None



        _tick_cooldowns(snapshot.symbol)

        # ── SESSION FILTER: Block Asian dead zone for non-Asian pairs ─
        # 8 PM – 3 AM ET is the Asian/Tokyo session.
        # JPY crosses and AUD/NZD have decent Tokyo liquidity,
        # so only block EUR/GBP/CHF/CAD majors and commodities.
        _ASIAN_FRIENDLY = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY",
                           "AUDUSD", "NZDUSD"}
        if snapshot.candles:
            if not gates.get("is_synthetic_override", False):
                from zoneinfo import ZoneInfo
                _ts = snapshot.candles[-1].timestamp
                if _ts.tzinfo is None:
                    _ts = _ts.replace(tzinfo=ZoneInfo("UTC"))
                et_hour = _ts.astimezone(ZoneInfo("America/New_York")).hour
                if et_hour >= 20 or et_hour < 3:
                    if snapshot.symbol not in _ASIAN_FRIENDLY:
                        return None  # Dead zone — skip non-Asian pairs

        # ── Loss streak cooldown ─────────────────────────────────
        sar_dir = gates.get("sar_dir")  # Set by engine SAR
        if _check_loss_cooldown(snapshot.symbol) and not sar_dir:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by loss streak cooldown")
            return None

        # ── Entry cooldown (2h between entries per symbol) ───────
        # Bypass if engine SAR is pending (time-critical reversal)
        has_reversal = bool(sar_dir)
        if _entry_cooldown.get(snapshot.symbol, 0) > 0 and not has_reversal:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by entry cooldown ({_entry_cooldown.get(snapshot.symbol, 0)} bars remaining)")
            return None

        # ── Get regime from trend detection ──────────────────────
        regime = gates.get("market_regime", "unknown")

        # ── CHOPPY / RANGING: Block all entries (SAR bypasses) ─────────────
        # 2026-03-10: Restored profile override so ranging can be traded if desired.
        _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
        block_ranging = bool(getattr(_profile, 'block_ranging_regime', True))
        
        blocked_regimes = ["choppy", "unknown"]
        if block_ranging:
            blocked_regimes.append("ranging")
            
        if regime in blocked_regimes and not has_reversal:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by regime={regime}")
            return None

        # ── Strength gate: don't enter weak signals ──────────────
        htf_strength = gates.get("htf_strength", 0)
        # Only gate strength for trending regime — ranging is counter-trend so
        # a neutral/conflicted HTF is actually the ideal entry condition.
        if regime == "trending" and htf_strength < 0.10 and not has_reversal:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by weak htf_strength={htf_strength:.2f} (need >=0.10)")
            return None  # Too weak to trust as trending


        # ── HTF/LTF alignment for directional regimes ────────────
        # Trending and transitional entries need both timeframes
        # pointing the same way. Ranging is exempt (counter-trend).
        if regime in ("trending", "transitional"):
            if not gates.get("htf_align", False):
                htf_dir = gates.get("htf_dir", "neutral")
                ltf_dir = gates.get("ltf_dir", "neutral")
                # Soft conflict: set flag for sub-strategies to penalize, but don't hard-block.
                # A conflicted multi-TF picture is often ideal for mean-reversion entries.
                if htf_dir in ("long", "short") and ltf_dir in ("long", "short") and htf_dir != ltf_dir:
                    if not has_reversal:
                        logger.info(f"[CONDUCTOR] {snapshot.symbol}: HTF/LTF conflict (htf={htf_dir}, ltf={ltf_dir}) — soft flag")
                    gates["htf_ltf_conflict"] = True

        # ── NOTE: Macro trend filters tested and reverted ─────────
        # EMA slope, price-vs-EMA, persistence, EMA-50/100 alignment
        # all killed more winners than losers in transitional markets.
        # Partial close + tight stops already limit loss sizes.

        # ── CONSECUTIVE-LOSS COOLDOWN ─────────────────────────────
        # After 2 consecutive losses on a symbol, sit out for 4 bars
        # (~1 hour on 15m) to avoid churn on choppy pairs.
        # SAR entries bypass this — they're time-critical.
        if not hasattr(self, '_loss_streak'):
            self._loss_streak = {}  # symbol → consecutive loss count
            self._cooldown_until = {}  # symbol → bar index to resume
            self._bar_index = 0

        self._bar_index += 1
        sym = snapshot.symbol

        # Update loss streak from trade history
        if trade_history:
            # Find last closed trade for this symbol
            closed = [t for t in trade_history
                      if t.get("symbol") == sym and t.get("exit_time")]
            if closed:
                last = closed[-1]
                last_pnl = last.get("pnl", 0)
                last_key = f"{sym}_{last.get('exit_time')}"
                if not hasattr(self, '_last_seen_exit'):
                    self._last_seen_exit = {}
                if last_key != self._last_seen_exit.get(sym):
                    self._last_seen_exit[sym] = last_key
                    if last_pnl <= 0:
                        self._loss_streak[sym] = self._loss_streak.get(sym, 0) + 1
                    else:
                        self._loss_streak[sym] = 0
                        self._cooldown_until.pop(sym, None)

        streak = self._loss_streak.get(sym, 0)
        cooldown_bar = self._cooldown_until.get(sym, 0)

        if streak >= 2 and cooldown_bar == 0:
            # Start cooldown: 4 bars (~1 hour)
            self._cooldown_until[sym] = self._bar_index + 4
            cooldown_bar = self._cooldown_until[sym]

        is_sar_pending = bool(sar_dir)
        if cooldown_bar > self._bar_index and not is_sar_pending:
            bars_left = cooldown_bar - self._bar_index
            logger.info(
                f"[CONDUCTOR] {sym}: COOLDOWN ({streak} consecutive losses, "
                f"{bars_left} bars remaining)"
            )
            return None

        # ── Route to primary strategy for this regime ────────────
        primary_key = _REGIME_MAP.get(regime)
        candidates = []

        if primary_key and primary_key in self._strategies:
            candidates.append(primary_key)

        # ── Transitional fallback: also try mean_reversion ────────
        # Session Breakout only fires on actual Asian Box breakouts,
        # which are rare. If the breakout hasn't happened, Mean Reversion
        # can catch BB bounce opportunities during transitional periods.
        if regime == "transitional" and "mean_reversion" in self._strategies:
            candidates.append("mean_reversion")

        logger.info(
            f"[CONDUCTOR] {snapshot.symbol}: regime={regime}, "
            f"htf_str={htf_strength:.2f}, route={primary_key}, "
            f"candidates={candidates + ['session_momentum']}"
            + (f" [SAR:{sar_dir}]" if sar_dir else "")
        )

        # Session Momentum is always a candidate (self-gates by time)
        candidates.append("session_momentum")

        # Wind Down Truffle is always a candidate (self-gates to Friday PM)
        candidates.append("wind_down_truffle")

        # ── Try each candidate ───────────────────────────────────
        for key in candidates:
            strategy = self._strategies[key]
            signal = strategy.check_entry_signal(
                snapshot, gates,
                open_position=open_position,
                current_capital=current_capital,
                trade_history=trade_history,
            )
            if signal and signal.action not in ("stand_aside", "hold"):
                # ── CORRELATION GUARD ─────────────────────────────
                # Prevent simultaneous entries on correlated pairs.
                # SAR entries bypass — they are time-critical.
                if trade_history and not has_reversal:
                    from datetime import timedelta
                    now = snapshot.candles[-1].timestamp if snapshot.candles else None
                    if now:
                        recent_cutoff = now - timedelta(minutes=30)
                        recent_entries = [
                            t for t in trade_history
                            if t.get("symbol") != snapshot.symbol
                            and t.get("entry_time")
                            and str(t["entry_time"]) > str(recent_cutoff)
                            and not t.get("exit_time")  # Still open
                        ]
                        if recent_entries:
                            logger.info(
                                f"[CONDUCTOR] {snapshot.symbol}: BLOCKED — "
                                f"correlation guard ({len(recent_entries)} "
                                f"other forex positions opened < 30min ago)"
                            )
                            return None

                signal.notes = (
                    f"[Conductor:{key}|{regime}] {signal.notes or ''}"
                )
                signal.structure_summary = (
                    f"[{key}|{regime}] {signal.structure_summary or ''}"
                )

                # ── SAR DIRECTION CHECK ──────────────────────────
                # If engine SAR is pending, only allow entries in that
                # direction. Reject wrong-way signals and fall through
                # to the ATR forced-entry below.
                if sar_dir:
                    signal_dir = (
                        "long" if signal.action == "enter_long" else "short"
                    )
                    if signal_dir != sar_dir:
                        logger.info(
                            f"[CONDUCTOR] {snapshot.symbol}: BLOCKED — "
                            f"SAR requires {sar_dir}, got {signal_dir}"
                        )
                        break  # Fall through to ATR forced SAR entry
                    signal.notes = f"[REVERSAL] {signal.notes}"

                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: "
                    f"Entry via {key} (regime={regime})"
                )
                # Hard 1% risk — override backtester performance boosts
                signal.risk_per_trade_pct = 0.01
                # Set entry cooldown for this symbol
                _entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS
                signal.strategy_name = self.name
                return signal

        # ── ATR-BASED FORCED SAR ENTRY ────────────────────────────────
        # Engine detected a SAR condition and passed sar_dir via gates.
        # No sub-strategy fired in that direction — compute ATR SL/TP
        # and return a forced reversal entry so we get proper risk sizing
        # (engine fallback has no SL/TP and defaults to zero-risk sizing).
        if sar_dir and snapshot.candles:
            # Guard: need at least 30 candles for indicators
            htf_adx = gates.get("htf_adx") or 0
            htf_dir_sar = gates.get("htf_dir", "neutral")
            ltf_dir_sar = gates.get("ltf_dir", "neutral")
            candles_ok  = len(snapshot.candles) >= 30
            has_direction = (htf_dir_sar != "neutral") or (ltf_dir_sar != "neutral")
            if not candles_ok or not has_direction:
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: SAR DEFERRED — "
                    f"cold-start or no directional data "
                    f"(htf={htf_dir_sar}/{htf_adx:.0f} ltf={ltf_dir_sar}, "
                    f"cands={len(snapshot.candles)})"
                )
                return None  # Engine will retry next tick (sar_dir stays in _sar_pending)

            from tradebot_sci.strategy.icc_signals import calculate_atr
            atr = calculate_atr(snapshot.candles[-50:], period=14)
            if atr and atr > 0:
                price = snapshot.candles[-1].close
                is_jpy = "JPY" in snapshot.symbol.upper()
                min_sl_dist = 15 * (0.01 if is_jpy else 0.0001)
                stop_dist = max(atr * 1.5, min_sl_dist)

                # TP = reversal_tp_r × risk (RTFM: 1R, NOT 2R)
                _profile = gates.get("profile")
                tp_r = float(getattr(_profile, "reversal_tp_r", 1.0)) if _profile else 1.0
                tp_dist = stop_dist * tp_r

                # Cost-aware TP: add spread buffer so net PnL ≈ true 1R after fees
                cost_aware = bool(getattr(_profile, "reversal_cost_aware_tp", True)) if _profile else True
                if cost_aware:
                    from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                    fee_pct = get_fee_for_symbol(snapshot.symbol)
                    tp_dist += price * fee_pct * 2  # round-trip spread

                if sar_dir == "long":
                    sl = price - stop_dist
                    tp = price + tp_dist
                    action = "enter_long"
                else:
                    sl = price + stop_dist
                    tp = price - tp_dist
                    action = "enter_short"
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: FORCED SAR {sar_dir.upper()} "
                    f"via engine (ATR={atr:.5f}, sl={sl:.5f}, tp_r={tp_r})"
                )
                _entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS
                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias=sar_dir,
                    phase="correction",
                    action=action,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    risk_per_trade_pct=_SAR_RISK_PCT,
                    urgency="high",
                    structure_summary=(
                        f"[SAR] Forced reversal {sar_dir} (ATR={atr:.5f})"
                    ),
                    notes=(
                        f"[REVERSAL][Conductor:SAR] Forced {sar_dir} — no strategy signal"
                    ),
                    strategy_name="reversal",
                )

        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        """Rising floor + early reversal exit + sub-strategy exits."""
        if not open_position:
            return None

        # ── FRIDAY 5PM CLOSE ─────────────────────────────────────────
        # Close any position at 5PM ET Friday (forex weekly close).
        # Wind Down Truffle trades specifically need this, but it's
        # a good safety for any position approaching the weekly close.
        if snapshot.candles:
            ts = snapshot.candles[-1].timestamp
            if ts.tzinfo is None:
                from zoneinfo import ZoneInfo as _ZI
                ts = ts.replace(tzinfo=_ZI("UTC"))
            et = ts.astimezone(ZoneInfo("America/New_York"))
            if et.weekday() == 4 and (et.hour >= 17 or (et.hour == 16 and et.minute >= 45)):
                from tradebot_sci.strategy.decisions import close_position_decision
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: Friday 5PM close — "
                    f"closing before weekly shutdown"
                )
                return close_position_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason="Conductor: Friday 5PM Close"
                )

        # ── R-MILESTONE MANAGEMENT ─────────────────────────────────
        # Two-sided position management based on R-multiple:
        #   LOSING:  -0.3R → partial close 50% (only if loss > spread)
        #   WINNING: +1R   → floor BE + pyramid 50%
        #            +1.5R → floor 0.5R + pyramid 25%
        #            +2R   → floor 1R
        if snapshot.candles and len(snapshot.candles) >= 5:
            pos_dir = open_position.get("direction") or open_position.get("side")
            entry_price = float(open_position.get("entry_price", 0))
            current_stop = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0) or 0)
            current_price = float(snapshot.candles[-1].close)

            if pos_dir in ("long", "short") and entry_price > 0 and current_stop > 0:
                initial_risk = abs(entry_price - current_stop)

            elif pos_dir in ("long", "short") and entry_price > 0 and current_stop == 0:
                # ── FALLBACK: No SL in snapshot ─────────────────────────────
                # Oanda sometimes returns no stopLossOrder (e.g., when SL was
                # placed via a separate order that isn't linked to the trade,
                # or when the trade details API call failed).
                # Estimate initial_risk from unrealized_pnl + position size.
                unrealized = float(open_position.get("unrealized_pnl", 0) or 0)
                pos_size = abs(float(open_position.get("size", 0) or 0))
                if unrealized != 0 and pos_size > 0 and entry_price > 0:
                    # pip_value ≈ unrealized / (size * pnl_dist_in_price)
                    pnl_dist_now = abs(current_price - entry_price)
                    if pnl_dist_now > 0:
                        pip_value = abs(unrealized) / (pos_size * pnl_dist_now)
                        # Assume default 1.5× ATR risk; ATR ≈ 0.0010 for major pairs
                        atr_guess = float(snapshot.candles[-1].close) * 0.0007 if snapshot.candles else 0.001
                        initial_risk = atr_guess
                        logger.warning(
                            f"[CONDUCTOR] {snapshot.symbol}: stop_loss missing — "
                            f"using estimated initial_risk={initial_risk:.5f} (ATR fallback). "
                            f"CHECK: hold_store SL backfill may have failed."
                        )
                    else:
                        initial_risk = 0.0
                else:
                    initial_risk = 0.0
            else:
                initial_risk = 0.0

            if initial_risk > 0:
                # R-multiple: positive = winning, negative = losing
                if pos_dir == "long":
                    pnl_dist = current_price - entry_price
                else:
                    pnl_dist = entry_price - current_price
                r_multiple = pnl_dist / initial_risk


                # SAR reversals: skip pyramids + de-risk milestones,
                # but KEEP ATR trailing active so they benefit from
                # regime-aware trailing stops (especially on ranging days).
                is_sar = open_position.get("strategy_name") == "reversal"

                # Track which milestones have already fired
                sym = snapshot.symbol
                milestones_key = f"{sym}_{pos_dir}_{entry_price:.5f}"
                if not hasattr(self, '_milestones_fired'):
                    self._milestones_fired = {}
                fired = self._milestones_fired.setdefault(milestones_key, set())

                # ── LOWER-HIGH / HIGHER-LOW INVALIDATION ─────────
                # 2026-03-10: Restored profile override so users can enable if desired.
                _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
                use_struct_inval = bool(getattr(_profile, 'structure_invalidation_enabled', False))
                
                if use_struct_inval and not is_sar and "struct_inval_lh" not in fired:
                    from tradebot_sci.market.swing_analysis import swing_points
                    trade_candles = snapshot.candles[-40:]
                    if len(trade_candles) >= 10:
                        sh_idx, sl_idx = swing_points(trade_candles, lookback=2)

                        if pos_dir == "long" and len(sh_idx) >= 2:
                            last_sh = float(trade_candles[sh_idx[-1]].high)
                            prev_sh = float(trade_candles[sh_idx[-2]].high)
                            if last_sh < prev_sh and current_price < last_sh:
                                fired.add("struct_inval_lh")
                                from tradebot_sci.strategy.decisions import (
                                    scale_out_decision,
                                )
                                logger.info(
                                    f"[CONDUCTOR] STRUCT INVAL {sym}: "
                                    f"Lower High ({prev_sh:.5f} → "
                                    f"{last_sh:.5f}), closing 80%%"
                                )
                                return scale_out_decision(
                                    sym, snapshot.timeframe,
                                    reason=(
                                        f"Conductor: Lower-High "
                                        f"Invalidation ({prev_sh:.5f}"
                                        f" → {last_sh:.5f})"
                                    ),
                                )

                        elif pos_dir == "short" and len(sl_idx) >= 2:
                            last_sl = float(trade_candles[sl_idx[-1]].low)
                            prev_sl = float(trade_candles[sl_idx[-2]].low)
                            if last_sl > prev_sl and current_price > last_sl:
                                fired.add("struct_inval_lh")
                                from tradebot_sci.strategy.decisions import (
                                    scale_out_decision,
                                )
                                logger.info(
                                    f"[CONDUCTOR] STRUCT INVAL {sym}: "
                                    f"Higher Low ({prev_sl:.5f} → "
                                    f"{last_sl:.5f}), closing 80%%"
                                )
                                return scale_out_decision(
                                    sym, snapshot.timeframe,
                                    reason=(
                                        f"Conductor: Higher-Low "
                                        f"Invalidation ({prev_sl:.5f}"
                                        f" → {last_sl:.5f})"
                                    ),
                                )

                # ── LOSING SIDE: TIERED GUILLOTINE ───────────────
                # DISABLED FOR PARITY (2026-03-08):
                # In the backtester (backtester.py L892-951), the Guillotine
                # fires ONLY on the candle where the stop is actually hit,
                # cascading T1→T2→final as intra-candle simulation. It does
                # NOT fire mid-trade on every decision cycle.
                #
                # This standalone version was cutting 80% of the position at
                # just -0.15R (a tiny 15-minute pullback), killing trades
                # before they had any chance to recover. This caused a 100%
                # loss rate in paper trading while the backtester showed wins
                # because it let trades breathe until the actual stop was hit.
                #
                # The Guillotine cascade still happens via paper_broker's
                # stop_loss/take_profit checking once price hits the stop.
                # Re-enabled (2026-03-09): OANDA does not do tiered stops. We must do it mid-trade.
                # 2026-03-10: Exposed to profile settings so users can re-enable the Guillotine if desired.
                if not is_sar:
                    _profile = getattr(self, 'profile', None) \
                        or gates.get('profile') \
                        or type('_P', (), {})()
                    
                    # Read from profile, default to 0.0 (disabled)
                    t1_r = float(getattr(_profile, 'tier1_r_threshold', 0.0))
                    t2_r = float(getattr(_profile, 'tier2_r_threshold', 0.0))
                    t1_cut = float(getattr(_profile, 'tier1_cut_fraction', 0.8))
                    t2_cut = float(getattr(_profile, 'tier2_cut_fraction', 0.8))

                    # ── Tier 1 ────────────────────────────────────────
                    if t1_r < 0 and r_multiple <= t1_r and "guillotine_t1" not in fired:
                        from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                        fee_pct = get_fee_for_symbol(sym)
                        spread_cost = entry_price * fee_pct * 2
                        if abs(pnl_dist) > spread_cost:
                            fired.add("guillotine_t1")
                            from tradebot_sci.strategy.decisions import scale_out_decision
                            logger.info(
                                f"[GUILLOTINE-T1] {sym}: "
                                f"{r_multiple:.2f}R → cutting {t1_cut*100:.0f}%"
                            )
                            dec = scale_out_decision(
                                sym, snapshot.timeframe,
                                reason=(
                                    f"Conductor: Guillotine T1 at {r_multiple:.2f}R "
                                    f"(cut {t1_cut*100:.0f}%)|scale_frac={t1_cut:.2f}|"
                                ),
                            )
                            return dec

                    # ── Tier 2 (original de_risk) ──────────────────────
                    if t2_r < 0 and r_multiple <= t2_r and "de_risk" not in fired:
                        from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                        fee_pct = get_fee_for_symbol(sym)
                        spread_cost = entry_price * fee_pct * 2
                        if abs(pnl_dist) > spread_cost:
                            fired.add("de_risk")
                            from tradebot_sci.strategy.decisions import scale_out_decision
                            logger.info(
                                f"[GUILLOTINE-T2] {sym}: "
                                f"{r_multiple:.2f}R → cutting {t2_cut*100:.0f}% of remainder"
                            )
                            return scale_out_decision(
                                sym, snapshot.timeframe,
                                reason=(
                                    f"Conductor: Guillotine T2 at {r_multiple:.2f}R "
                                    f"(cut {t2_cut*100:.0f}% of remaining)"
                                    f"|scale_frac={t2_cut:.2f}|"
                                ),
                            )


                # ── SWAP AVOIDANCE (Wednesday 3× charge) ──────────────
                # OANDA charges 3× overnight swap on Wednesday 5PM ET.
                # Close marginal trades before the cutoff to save money.
                if (
                    self._profile
                    and getattr(self._profile, 'swap_avoidance_enabled', False)
                    and 0 <= r_multiple < 0.5
                    and not is_sar
                ):
                    import pytz
                    from datetime import datetime
                    tz_name = getattr(self._profile, 'swap_avoidance_timezone', 'America/New_York')
                    try:
                        tz = pytz.timezone(tz_name)
                    except Exception:
                        tz = pytz.timezone('America/New_York')
                    now_local = datetime.now(tz)
                    # Wednesday = 2, check if within 30 min of 5PM cutoff
                    if now_local.weekday() == 2 and now_local.hour >= 16 and now_local.hour < 17:
                        logger.info(
                            f"[CONDUCTOR] SWAP AVOIDANCE {sym}: "
                            f"{r_multiple:.2f}R (marginal) — closing before "
                            f"Wednesday 5PM ET to dodge 3× swap charge"
                        )
                        return AITradeDecision(
                            symbol=sym,
                            timeframe=snapshot.timeframe,
                            bias=pos_dir,
                            phase="management",
                            action="close_position",
                            strategy_name=self.name,
                            notes=(
                                f"[MANAGEMENT] Swap avoidance: "
                                f"{r_multiple:.2f}R — Wed 3× swap dodge"
                            ),
                        )

                # ── EARLY ATR TRAILING (0.5R+) ─────────────────────
                # Move broker SL to lock in profit once 0.5R is reached.
                # REGIME-AWARE: Ranging markets use TIGHT trails to
                # capture oscillation peaks. Trending uses wide trails
                # to let winners run.
                from tradebot_sci.strategy.icc_signals import calculate_atr
                atr = calculate_atr(snapshot.candles[-14:], period=14)
                regime = gates.get("market_regime", "unknown")
                is_ranging = regime in ("ranging", "choppy")

                # ── RANGING DAY QUICK TP (0.7R+) ─────────────────
                # On consolidation days, DON'T try to let winners run.
                # Take profit at oscillation peaks and re-enter on dips.
                # This captures the up/down/up/down pattern the user wants.
                if is_ranging and r_multiple >= 0.7 and not is_sar and self.quick_ranging_tp_enabled:
                    pnl_approx = r_multiple * initial_risk * (
                        abs(open_position.get("size", 0))
                        / (entry_price if entry_price else 1)
                    )
                    logger.info(
                        f"[CONDUCTOR] RANGING TP {sym}: "
                        f"{r_multiple:.2f}R (~${pnl_approx:.0f}) — "
                        f"taking profit at oscillation peak "
                        f"(regime={regime})"
                    )
                    return AITradeDecision(
                        symbol=sym,
                        timeframe=snapshot.timeframe,
                        bias=pos_dir,
                        phase="management",
                        action="close_position",
                        strategy_name=self.name,
                        notes=(
                            f"[MANAGEMENT] Ranging TP: "
                            f"{r_multiple:.2f}R — oscillation peak"
                        ),
                    )

                # ── WINNING SIDE: R-MILESTONE PYRAMIDS (1R+) ──────
                # Check milestones BEFORE ATR trail so pyramids fire.
                # 1R:   floor → BE  + pyramid 30% (hammer the win)
                # 1.5R+: floor + pyramid 4% every 0.5R
                # Plus: momentum acceleration, bounce re-pyramids
                # SAR trades skip pyramiding — they ride to TP.
                if not is_sar and r_multiple >= 1.0:
                    MAX_PYRAMIDS = getattr(self._profile, 'conductor_pyramid_max_count', 50) if self._profile else 50

                    # ── #2: MOMENTUM ACCELERATION ─────────────────
                    # If a single candle moves ≥ 0.3R in our direction,
                    # that's a displacement — pyramid immediately.
                    if (
                        atr and atr > 0
                        and len(snapshot.candles) >= 2
                        and "momentum_accel" not in fired
                    ):
                        candle = snapshot.candles[-1]
                        candle_move = (
                            (candle.close - candle.open)
                            if pos_dir == "long"
                            else (candle.open - candle.close)
                        )
                        if candle_move >= initial_risk * 0.3:
                            pyr_count = sum(
                                1 for k in fired if k.startswith("pyr_")
                            )
                            if pyr_count < MAX_PYRAMIDS:
                                fired.add("momentum_accel")
                                logger.info(
                                    f"[CONDUCTOR] MOMENTUM {sym}: "
                                    f"candle move {candle_move/initial_risk:.1f}R "
                                    f"→ immediate pyramid 4%"
                                )
                                return AITradeDecision(
                                    symbol=sym,
                                    timeframe=snapshot.timeframe,
                                    bias=pos_dir, phase="management",
                                    action="scale_in",
                                    risk_per_trade_pct=0.04,
                                    strategy_name=self.name,
                                    notes=(
                                        f"[MANAGEMENT] Momentum accel: "
                                        f"candle={candle_move/initial_risk:.1f}R"
                                    ),
                                )

                    # ── #3: RE-PYRAMID ON PULLBACK BOUNCES ────────
                    # Track peak R-level. If we pulled back ≥ 0.5R
                    # and then re-broke the level, reset that milestone
                    # so a new pyramid can fire.
                    peak_key = f"peak_{milestones_key}"
                    if not hasattr(self, '_peak_r'):
                        self._peak_r = {}
                    prev_peak = self._peak_r.get(peak_key, 0.0)
                    if r_multiple > prev_peak:
                        self._peak_r[peak_key] = r_multiple
                    elif prev_peak - r_multiple >= 0.5:
                        # Pulled back ≥ 0.5R — mark trough
                        trough_key = f"trough_{milestones_key}"
                        if not hasattr(self, '_trough_r'):
                            self._trough_r = {}
                        self._trough_r[trough_key] = r_multiple

                    trough_key = f"trough_{milestones_key}"
                    trough_r = getattr(self, '_trough_r', {}).get(trough_key)
                    if trough_r is not None and r_multiple > trough_r + 0.5:
                        # Bounced back up past trough + 0.5R — refresh
                        # the milestone at this level
                        bounce_level = 1.0 + (int((r_multiple - 1.0) / 0.5) * 0.5)
                        bounce_key = f"pyr_{bounce_level:.1f}r"
                        if bounce_key in fired:
                            fired.discard(bounce_key)
                            # Clear trough so we don't re-fire
                            self._trough_r.pop(trough_key, None)
                            logger.info(
                                f"[CONDUCTOR] BOUNCE RE-PYRAMID {sym}: "
                                f"pullback to {trough_r:.1f}R → "
                                f"re-broke {bounce_level:.1f}R, "
                                f"reset milestone"
                            )

                    # ── R-level milestones (floor + pyramid) ──────
                    level_idx = int((r_multiple - 1.0) / 0.5)
                    for i in range(level_idx, -1, -1):
                        threshold = 1.0 + (i * 0.5)
                        floor_r = max(0.0, threshold - 1.0)
                        m_key = f"pyr_{threshold:.1f}r"
                        _pyr_first = getattr(self._profile, 'conductor_pyramid_first_pct', 0.30) if self._profile else 0.30
                        _pyr_sub = getattr(self._profile, 'conductor_pyramid_subsequent_pct', 0.04) if self._profile else 0.04
                        pyr_risk = _pyr_first if i == 0 else _pyr_sub

                        # Floor move
                        if pos_dir == "long":
                            floor_price = entry_price + (initial_risk * floor_r)
                            need_floor = current_stop < floor_price
                        else:
                            floor_price = entry_price - (initial_risk * floor_r)
                            need_floor = current_stop > floor_price

                        # Pyramid (if not already fired and under cap)
                        pyr_count = sum(
                            1 for k in fired if k.startswith("pyr_")
                        )
                        need_pyramid = (
                            m_key not in fired
                            and pyr_count < MAX_PYRAMIDS
                        )

                        if need_floor or need_pyramid:
                            if need_pyramid:
                                fired.add(m_key)

                            action = "scale_in" if need_pyramid else "hold"
                            notes_parts = []
                            if need_floor:
                                notes_parts.append(f"floor→{floor_r:.1f}R")
                            if need_pyramid:
                                notes_parts.append(
                                    f"pyramid {int(pyr_risk*100)}%"
                                )

                            logger.info(
                                f"[CONDUCTOR] MILESTONE {sym}: "
                                f"{r_multiple:.1f}R → "
                                f"{', '.join(notes_parts)}"
                            )
                            return AITradeDecision(
                                symbol=sym,
                                timeframe=snapshot.timeframe,
                                bias=pos_dir,
                                phase="management",
                                action=action,
                                stop_loss=floor_price if need_floor else None,
                                risk_per_trade_pct=pyr_risk,
                                notes=(
                                    f"[MANAGEMENT] {r_multiple:.1f}R: "
                                    f"{', '.join(notes_parts)}"
                                ),
                                strategy_name=self.name,
                            )
                        break  # Only process highest level

                # ── ATR TRAILING FALLBACK (0.5R – 1.0R) ───────────
                # Only fires if no pyramid milestone was triggered above.
                # This handles the gap between breakeven and 1R.
                if atr and atr > 0 and r_multiple >= 0.5:
                    if is_ranging:
                        # RANGING: tight trails — capture oscillation peaks
                        if r_multiple >= 3.0:
                            trail_mult = 0.3
                        elif r_multiple >= 2.0:
                            trail_mult = 0.5
                        elif r_multiple >= 1.0:
                            trail_mult = 0.7
                        else:
                            trail_mult = 1.0  # 0.5-1.0R: lock near BE
                    else:
                        # TRENDING: wide trails — let winners run
                        if r_multiple >= 3.0:
                            trail_mult = 0.7
                        elif r_multiple >= 2.0:
                            trail_mult = 1.0
                        elif r_multiple >= 1.0:
                            trail_mult = 1.5
                        else:
                            trail_mult = 2.0  # 0.5-1.0R: wide trail
                    trail_dist = atr * trail_mult

                    if pos_dir == "long":
                        atr_trail = current_price - trail_dist
                        if atr_trail > current_stop:
                            logger.info(
                                f"[CONDUCTOR] ATR TRAIL {sym}: "
                                f"{r_multiple:.1f}R, "
                                f"{trail_mult}× ATR → "
                                f"stop ${atr_trail:.5f}"
                            )
                            return AITradeDecision(
                                symbol=sym,
                                timeframe=snapshot.timeframe,
                                bias=pos_dir, phase="management",
                                action="hold",
                                stop_loss=atr_trail,
                                notes=(
                                    f"[MANAGEMENT] ATR trail: "
                                    f"{trail_mult}× ATR at "
                                    f"{r_multiple:.1f}R"
                                ),
                            )
                    else:
                        atr_trail = current_price + trail_dist
                        if atr_trail < current_stop:
                            logger.info(
                                f"[CONDUCTOR] ATR TRAIL {sym}: "
                                f"{r_multiple:.1f}R, "
                                f"{trail_mult}× ATR → "
                                f"stop ${atr_trail:.5f}"
                            )
                            return AITradeDecision(
                                symbol=sym,
                                timeframe=snapshot.timeframe,
                                bias=pos_dir, phase="management",
                                action="hold",
                                stop_loss=atr_trail,
                                notes=(
                                    f"[MANAGEMENT] ATR trail: "
                                    f"{trail_mult}× ATR at "
                                    f"{r_multiple:.1f}R"
                                ),
                            )

        # ── SUB-STRATEGY EXIT LOOP ──────────────────────────────────
        # Compute R-multiple for profit guard (may not exist from above
        # if candles < 5 or missing stop/entry data)
        _exit_r = None
        if snapshot.candles:
            _dir = open_position.get("direction") or open_position.get("side")
            _ep = float(open_position.get("entry_price", 0))
            _sl = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0) or 0)
            _cp = float(snapshot.candles[-1].close)
            if _dir and _ep > 0 and _sl > 0:
                _ir = abs(_ep - _sl)
                if _ir > 0:
                    _pd = (_cp - _ep) if _dir == "long" else (_ep - _cp)
                    _exit_r = _pd / _ir

        for key, strategy in self._strategies.items():
            signal = strategy.check_exit_signal(
                snapshot, open_position, gates,
                current_capital=current_capital,
                trade_history=trade_history,
            )
            if signal and signal.action in ("close_position",):
                # PROFIT GUARD: Don't let sub-strategies kill profitable trades.
                # If trade is above +0.3R, let SL/TP and ATR trailing handle
                # the exit — those produce $326 avg wins vs $76 avg from EMA exits.
                if _exit_r is not None and _exit_r >= 0.3:
                    logger.info(
                        f"[CONDUCTOR] {snapshot.symbol}: PROFIT GUARD — "
                        f"suppressed {key} exit at {_exit_r:.1f}R "
                        f"(letting SL/TP handle)"
                    )
                    continue  # skip this exit, check next strategy
                signal.notes = f"[Conductor:{key}] {signal.notes or ''}"
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: "
                    f"Exit via {key}: {signal.notes}"
                )
                return signal
            if signal and signal.action == "hold" and signal.stop_loss:
                return signal

        return None

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """Score using regime-appropriate strategy."""
        regime = gates.get("market_regime", "unknown")
        primary_key = _REGIME_MAP.get(regime)
        if primary_key and primary_key in self._strategies:
            return self._strategies[primary_key].score_signal(snapshot, gates)
        return 0.0, "F-", f"No strategy for regime={regime}"
