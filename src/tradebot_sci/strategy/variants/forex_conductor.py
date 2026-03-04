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
_ENTRY_COOLDOWN_BARS = 2  # 2 × 15min = 30 minutes

# ── Reversal signal: when set, allows immediate re-entry in opposite direction ──
_reversal_pending: dict[str, str] = {}  # symbol → "long" or "short" (direction to enter)


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

    def __init__(self):
        super().__init__("Forex Conductor")
        self._strategies = {
            "mean_reversion": MeanReversionStrategy(),
            "session_breakout": LondonBreakoutStrategy(),
            "trend_rider": TrendRiderStrategy(),
            "session_momentum": SessionMomentumStrategy(),
            "wind_down_truffle": WindDownTruffleStrategy(),
        }

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

        # ── SESSION FILTER: Block Asian dead zone ─────────────
        # 8 PM – 3 AM ET is the Asian session — low liquidity for
        # major forex pairs, poor for directional bets, high
        # spread cost. Block all entries (including SAR).
        if snapshot.candles:
            from zoneinfo import ZoneInfo
            _ts = snapshot.candles[-1].timestamp
            if _ts.tzinfo is None:
                _ts = _ts.replace(tzinfo=ZoneInfo("UTC"))
            et_hour = _ts.astimezone(ZoneInfo("America/New_York")).hour
            if et_hour >= 20 or et_hour < 3:
                return None  # Dead zone — no entries

        # ── Stop-and-Reverse: populate _reversal_pending ─────────
        # If enabled, scan trade_history for a recent stop exit on
        # this symbol.  If found, set _reversal_pending so the entry
        # logic immediately fires in the opposite direction (bypasses
        # cooldowns and blocks wrong-way signals).
        profile = gates.get("profile")
        sar_enabled = bool(getattr(profile, "stop_and_reverse_enabled", False)) if profile else False
        if sar_enabled and trade_history and snapshot.symbol not in _reversal_pending:
            for t in reversed(trade_history):  # newest first
                if t.get("symbol") != snapshot.symbol:
                    continue
                # SAR fires on ANY losing trade — no time window.
                # If the last trade on this symbol was a loss, flip direction.
                is_loss = (not t.get("is_win", True)) or (t.get("pnl_usd", 0) < 0)
                if not is_loss:
                    break  # last trade was a win — no reversal needed
                # Set reversal direction: opposite of the losing side
                old_side = (t.get("side") or "").lower()
                if old_side == "long":
                    _reversal_pending[snapshot.symbol] = "short"
                elif old_side == "short":
                    _reversal_pending[snapshot.symbol] = "long"
                if snapshot.symbol in _reversal_pending:
                    logger.info(
                        f"[CONDUCTOR] {snapshot.symbol}: LOSS DETECTED → "
                        f"reversal pending {_reversal_pending[snapshot.symbol]}"
                    )
                break  # only process most recent

        # ── Loss streak cooldown ─────────────────────────────────
        if _check_loss_cooldown(snapshot.symbol):
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by loss streak cooldown")
            return None

        # ── Entry cooldown (2h between entries per symbol) ───────
        # Bypass if a reversal is pending (we just got stopped,
        # market is moving the other way — ride it)
        has_reversal = snapshot.symbol in _reversal_pending
        if _entry_cooldown.get(snapshot.symbol, 0) > 0 and not has_reversal:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by entry cooldown ({_entry_cooldown.get(snapshot.symbol, 0)} bars remaining)")
            return None

        # ── Get regime from trend detection ──────────────────────
        regime = gates.get("market_regime", "unknown")

        # ── CHOPPY: Block all entries ────────────────────────────
        if regime in ("choppy", "unknown"):
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by regime={regime}")
            return None

        # ── Strength gate: don't enter weak signals ──────────────
        htf_strength = gates.get("htf_strength", 0)
        if regime == "trending" and htf_strength < 0.3:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by weak htf_strength={htf_strength:.2f} (need >=0.3)")
            return None  # Too weak to trust as trending

        # ── HTF/LTF alignment for directional regimes ────────────
        # Trending and transitional entries need both timeframes
        # pointing the same way. Ranging is exempt (counter-trend).
        if regime in ("trending", "transitional"):
            if not gates.get("htf_align", False):
                htf_dir = gates.get("htf_dir", "neutral")
                ltf_dir = gates.get("ltf_dir", "neutral")
                # Allow if one is neutral (not conflicting, just undecided)
                if htf_dir in ("long", "short") and ltf_dir in ("long", "short"):
                    logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by HTF/LTF misalignment (htf={htf_dir}, ltf={ltf_dir})")
                    return None  # Conflicting directions — skip

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

        is_sar_pending = sym in _reversal_pending
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
                # Prevent simultaneous entries on correlated pairs
                # (e.g., EURUSD + GBPUSD both short at the same time)
                # EXCEPTION: SAR reversal entries bypass this guard —
                # they are time-critical and blocking them negates the
                # entire stop-and-reverse recovery mechanism.
                is_sar_entry = snapshot.symbol in _reversal_pending
                if trade_history and not is_sar_entry:
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

                # ── REVERSAL DIRECTION CHECK ──────────────────────
                # If a reversal is pending, only allow entries in the
                # reversal direction. Reject entries the wrong way.
                rev_dir = _reversal_pending.pop(snapshot.symbol, None)
                if rev_dir:
                    signal_dir = (
                        "long" if signal.action == "enter_long" else "short"
                    )
                    if signal_dir != rev_dir:
                        logger.info(
                            f"[CONDUCTOR] {snapshot.symbol}: BLOCKED — "
                            f"reversal pending {rev_dir}, got {signal_dir}"
                        )
                        return None
                    signal.notes = (
                        f"[REVERSAL] {signal.notes}"
                    )

                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: "
                    f"Entry via {key} (regime={regime})"
                )
                # Hard 1% risk — override backtester performance boosts
                signal.risk_per_trade_pct = 0.01
                # Set entry cooldown for this symbol
                _entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS
                return signal

        # ── FORCED SAR ENTRY ──────────────────────────────────
        # If a reversal is pending but no sub-strategy fired,
        # force an entry in the SAR direction using ATR-based stop.
        rev_dir = _reversal_pending.pop(snapshot.symbol, None)
        if rev_dir:
            from tradebot_sci.strategy.icc_signals import calculate_atr
            atr = calculate_atr(snapshot.candles[-14:], period=14)
            if atr and atr > 0 and snapshot.candles:
                price = snapshot.candles[-1].close
                if rev_dir == "long":
                    sl = price - (atr * 1.5)
                    tp = price + (atr * 2.25)  # 1.5:1 R:R
                    action = "enter_long"
                else:
                    sl = price + (atr * 1.5)
                    tp = price - (atr * 2.25)
                    action = "enter_short"
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: FORCED SAR "
                    f"{rev_dir.upper()} (no strategy signal — forcing)"
                )
                _entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS
                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias=rev_dir,
                    phase="correction",
                    action=action,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    risk_per_trade_pct=0.01,
                    urgency="high",
                    structure_summary=(
                        f"[SAR] Forced reversal {rev_dir} "
                        f"(ATR={atr:.5f})"
                    ),
                    notes=(
                        f"[REVERSAL][Conductor:SAR] Forced "
                        f"{rev_dir} — no strategy signal"
                    ),
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
            current_stop = float(open_position.get("stop_price", 0) or 0)
            current_price = float(snapshot.candles[-1].close)

            if pos_dir in ("long", "short") and entry_price > 0 and current_stop > 0:
                initial_risk = abs(entry_price - current_stop)

                if initial_risk > 0:
                    # R-multiple: positive = winning, negative = losing
                    if pos_dir == "long":
                        pnl_dist = current_price - entry_price
                    else:
                        pnl_dist = entry_price - current_price
                    r_multiple = pnl_dist / initial_risk

                    # SAR reversals manage their own risk via SL/TP.
                    # Skip ALL milestone management (de-risk, pyramids,
                    # floors) so they can ride to their 1R target.
                    if open_position.get("strategy_name") == "reversal":
                        return None

                    # Track which milestones have already fired
                    sym = snapshot.symbol
                    milestones_key = f"{sym}_{pos_dir}_{entry_price:.5f}"
                    if not hasattr(self, '_milestones_fired'):
                        self._milestones_fired = {}
                    fired = self._milestones_fired.setdefault(milestones_key, set())

                    # ── LOWER-HIGH / HIGHER-LOW INVALIDATION ─────────
                    # If the trade's swing structure breaks (lower high
                    # for longs, higher low for shorts), exit 80%.
                    if "struct_inval_lh" not in fired:
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

                    # ── LOSING SIDE: Partial close at -0.6R ───────────
                    if r_multiple <= -0.6 and "de_risk" not in fired:
                        # Spread guard: only exit if loss > 2× spread cost
                        from tradebot_sci.utils.symbol_classifier import (
                            get_fee_for_symbol,
                        )
                        fee_pct = get_fee_for_symbol(sym)
                        spread_cost = entry_price * fee_pct * 2
                        if abs(pnl_dist) > spread_cost:
                            fired.add("de_risk")
                            from tradebot_sci.strategy.decisions import (
                                scale_out_decision,
                            )
                            logger.info(
                                f"[CONDUCTOR] DE-RISK {sym}: "
                                f"{r_multiple:.1f}R partial close"
                            )
                            return scale_out_decision(
                                sym, snapshot.timeframe,
                                reason=(
                                    f"Conductor: De-risk at {r_multiple:.1f}R "
                                    f"(partial close)"
                                ),
                            )

                    # ── WINNING SIDE: Unlimited Pyramiding ────────────
                    # 1R:   floor → BE  + pyramid 30% (hammer the win)
                    # 1.5R+: floor + pyramid 4% every 0.5R
                    # Plus: momentum acceleration, bounce re-pyramids,
                    #        dynamic ATR trailing
                    if r_multiple >= 1.0:
                        MAX_PYRAMIDS = 50
                        from tradebot_sci.strategy.icc_signals import calculate_atr
                        atr = calculate_atr(snapshot.candles[-14:], period=14)

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

                        # ── #4: DYNAMIC ATR TRAILING ──────────────────
                        # Tighten trailing stop as profit grows:
                        #   At 1R: trail = 1.5× ATR
                        #   At 2R: trail = 1.0× ATR
                        #   At 3R+: trail = 0.7× ATR
                        if atr and atr > 0 and r_multiple >= 1.0:
                            if r_multiple >= 3.0:
                                trail_mult = 0.7
                            elif r_multiple >= 2.0:
                                trail_mult = 1.0
                            else:
                                trail_mult = 1.5
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

                        # ── R-level milestones (floor + pyramid) ──────
                        level_idx = int((r_multiple - 1.0) / 0.5)
                        for i in range(level_idx, -1, -1):
                            threshold = 1.0 + (i * 0.5)
                            floor_r = max(0.0, threshold - 1.0)
                            m_key = f"pyr_{threshold:.1f}r"
                            pyr_risk = 0.30 if i == 0 else 0.04

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
                                )
                            break  # Only process highest level

        for key, strategy in self._strategies.items():
            signal = strategy.check_exit_signal(
                snapshot, open_position, gates,
                current_capital=current_capital,
                trade_history=trade_history,
            )
            if signal and signal.action in ("close_position",):
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
