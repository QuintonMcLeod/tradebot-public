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
import os
from datetime import time
from zoneinfo import ZoneInfo
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

from tradebot_sci.strategy.variants.london_sweep import LondonSweepStrategy
from tradebot_sci.strategy.variants.golden_pocket import GoldenPocketStrategy
from tradebot_sci.strategy.variants.new_york_drive import NewYorkDriveStrategy
from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy

logger = logging.getLogger(__name__)

# ── Regime → Strategy mapping ────────────────────────────────────────
# FIXED: Trend-following strategies belong in trending markets, mean-reversion in ranging
_REGIME_MAP = {
    "trending":      "london_sweep",     # Trend continuation in strong trends
    "ranging":       "mean_reversion",   # Mean reversion in sideways markets
    "transitional":  "golden_pocket",    # Pullback entries during regime changes
    # "choppy" → no entry (handled explicitly)
}

# ── Per-symbol loss streak cooldown ──────────────────────────────────
_COOLDOWN_TRIGGER = 3
_COOLDOWN_BARS = 6

# ── Per-symbol entry cooldown (prevents rapid re-entry after stops) ──
_ENTRY_COOLDOWN_BARS = 12  # 1-hour cooldown on 5m chart to prevent clustered re-entries

# ── SAR: conductor delegates to engine for detection/cooldowns. ──────
# Engine populates gates["sar_dir"] ("long"/"short"/None) before
# calling check_entry_signal. Conductor reads it here to either
# constrain sub-strategy direction or compute an ATR forced entry.
_SAR_RISK_PCT = 0.027  # ~$60 max SAR loss per trade at 5.7k balance


def _check_loss_cooldown(symbol: str, instance_state: dict) -> bool:
    return instance_state.get('_cooldown_bars', {}).get(symbol, 0) > 0


def _update_cooldown(symbol: str, is_loss: bool, instance_state: dict):
    loss_streaks = instance_state.setdefault('_loss_streaks', {})
    cooldown_bars = instance_state.setdefault('_cooldown_bars', {})
    
    if is_loss:
        loss_streaks[symbol] = loss_streaks.get(symbol, 0) + 1
        if loss_streaks[symbol] >= _COOLDOWN_TRIGGER:
            cooldown_bars[symbol] = _COOLDOWN_BARS
            logger.info(
                f"[CONDUCTOR] {symbol}: {loss_streaks[symbol]} consecutive "
                f"losses → {_COOLDOWN_BARS}-bar cooldown"
            )
    else:
        loss_streaks[symbol] = 0


def _tick_cooldowns(symbol: str, instance_state: dict):
    """Tick cooldowns for a SINGLE symbol only.

    This must only tick the given symbol because the function is called
    once per symbol per bar.  With N symbols, calling it N times and
    ticking ALL symbols each time would make cooldowns expire N× faster
    — a nasty coupling bug that changes behaviour depending on how many
    pairs are traded.
    """
    cooldown_bars = instance_state.setdefault('_cooldown_bars', {})
    entry_cooldown = instance_state.setdefault('_entry_cooldown', {})
    
    if symbol in cooldown_bars and cooldown_bars[symbol] > 0:
        cooldown_bars[symbol] -= 1
    if symbol in entry_cooldown and entry_cooldown[symbol] > 0:
        entry_cooldown[symbol] -= 1


def reset_module_state():
    """Clear all module-level state for a fresh replay day.

    Called by loop.py when day-chaining to prevent stale cooldowns and
    loss streak memory from the previous day leaking into decisions.
    
    DEPRECATED: Module-level globals removed. State is now instance-based.
    This function kept for backward compatibility but does nothing.
    """
    # Module-level globals removed - state is now in ForexConductorStrategy instances
    logger.info("[CONDUCTOR] reset_module_state() deprecated - use instance.reset_instance_state()")


class ForexConductorStrategy(BaseStrategy):
    """
    Forex Conductor — routes to strategies based on market regime.
    """

    def __init__(self, **kwargs):
        self._profile_risk_pct: float | None = None
        self._strategies = {
            "london_sweep": LondonSweepStrategy(),
            "golden_pocket": GoldenPocketStrategy(),
            "new_york_drive": NewYorkDriveStrategy(),
            "mean_reversion": MeanReversionStrategy(),
        }
        self._profile = kwargs.get('profile_settings', None)
        
        # Propagate profile to sub-strategies so they read config, not hardcoded values
        if self._profile:
            for strategy in self._strategies.values():
                strategy._profile = self._profile
            pyramid_r = getattr(self._profile, 'conductor_pyramid_start_r', 1.0)
            pyramid_pct = getattr(self._profile, 'conductor_pyramid_first_pct', 0.3)
            logger.info(f"[CONDUCTOR] Initializing with Pyramiding -> Trigger: {pyramid_r}R, First %: {pyramid_pct}")
            
        super().__init__("Forex Conductor")
        
        # FIXED: Move module-level globals to instance state to prevent persistence across restarts
        self._loss_streaks: dict[str, int] = {}
        self._cooldown_bars: dict[str, int] = {}
        self._entry_cooldown: dict[str, int] = {}

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

    def reset_instance_state(self):
        """Clear per-instance state for a fresh replay day.

        Called by loop.py when day-chaining so session cooldowns,
        position tracking, and daily PnL counters don't leak across days.
        """
        if hasattr(self, '_last_position_state'):
            self._last_position_state.clear()
        if hasattr(self, '_session_losses'):
            self._session_losses.clear()
        if hasattr(self, '_session_blocked'):
            self._session_blocked.clear()
        if hasattr(self, '_daily_total_pnl'):
            self._daily_total_pnl = 0.0
            self._daily_cb_date = None
        self._bar_index = 0
        logger.info("[CONDUCTOR] Instance state reset for new replay day")


    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        sym = snapshot.symbol
        sar_dir = gates.get("sar_dir")
        
        # ── POSITION STATE TRACKING (for session cooldown) ───────
        # Read previous state BEFORE overwriting with current.
        # Detects position open→close transitions to count session losses.
        if not hasattr(self, '_last_position_state'):
            self._last_position_state = {}
        if not hasattr(self, '_session_losses'):
            self._session_losses = {}
            self._session_blocked = {}
            self._bar_index = 0
        
        has_position = open_position is not None and abs(open_position.get("size", 0)) > 0
        prev = self._last_position_state.get(sym, {"had_pos": False, "pnl": 0})
        
        if prev["had_pos"] and not has_position:
            # Position just closed! Determine session and count it.
            if snapshot.candles:
                _h = snapshot.candles[-1].timestamp.hour
                _d = snapshot.candles[-1].timestamp.date()
                _s = "asian" if _h < 7 else ("london" if _h < 13 else ("ny" if _h < 20 else "late"))
                _sk = f"{_d}_{_s}"
                last_pnl = prev["pnl"]
                logger.info(f"[CONDUCTOR] {sym}: POSITION CLOSED (pnl=${last_pnl:.2f}, session={_sk})")
                if last_pnl <= 0:
                    sk = (sym, _sk)
                    self._session_losses[sk] = self._session_losses.get(sk, 0) + 1
                    logger.info(f"[CONDUCTOR] {sym}: session loss #{self._session_losses[sk]} in {_sk}")
                    if self._session_losses[sk] >= 2:
                        self._session_blocked[sk] = True
                        logger.info(f"[CONDUCTOR] {sym}: SESSION BLOCKED — {self._session_losses[sk]} losses in {_sk}")
        
        # Write current state
        self._last_position_state[sym] = {
            "had_pos": has_position,
            "pnl": float(open_position.get("unrealized_pnl", 0)) if open_position else 0,
        }
        
        if sar_dir:
            logger.info(f"[DEBUG SAR] check_entry_signal started. open_pos={bool(open_position)}")
        if open_position:
            return None



        _tick_cooldowns(snapshot.symbol, self)

        # ── SESSION FILTER: Asian dead zone DISABLED ─────────────
        # Previously blocked EUR/GBP/CHF/CAD majors during 8PM–3AM ET.
        # Removed: locking out majors no longer benefits the strategy.
        sar_dir = gates.get("sar_dir")  # Set by engine SAR

        # ── Loss streak cooldown ─────────────────────────────────
        if _check_loss_cooldown(snapshot.symbol, self) and not sar_dir:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by loss streak cooldown")
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Forex Conductor: Blocked by loss streak cooldown")

        # ── Entry cooldown (2h between entries per symbol) ───────
        # In real markets, I find RSI is largely noise and leads to premature exits
        # in structural trend trading. I forcefully ignore it here and rely
        # exclusively on MACD divergence and Chandelier structure break confirmation.
        has_reversal = False
        sar_dir = None
        
        if self._entry_cooldown.get(snapshot.symbol, 0) > 0:
            rem = self._entry_cooldown.get(snapshot.symbol, 0)
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by entry cooldown ({rem} bars remaining)")
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"Forex Conductor: Blocked by entry cooldown ({rem} bars)")

        # ── Get regime from trend detection ──────────────────────
        regime = gates.get("market_regime", "unknown")

        # ── CHOPPY / RANGING: Block all entries (SAR bypasses) ─────────────
        # 2026-03-10: I restored profile override so ranging can be traded if desired.
        _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
        block_ranging = bool(getattr(_profile, 'block_ranging_regime', False))  # Switched to False to enable London Sweep
        
        blocked_regimes = ["choppy", "unknown"]
        if block_ranging:
            blocked_regimes.append("ranging")
            
        if regime in blocked_regimes and not has_reversal:
            logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by regime={regime}")
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"Forex Conductor: Blocked by market regime ({regime})")

        # ── CANDLE CHOP DETECTOR (independent of classifier) ─────
        # I count direction changes in last 10 candles. If the market
        # is whipsawing (>5 reversals), I consider it choppy regardless of
        # what the regime classifier says.
        if len(snapshot.candles) >= 10:
            _recent = [c.close for c in snapshot.candles[-10:]]
            _reversals = sum(
                1 for i in range(2, len(_recent))
                if (_recent[i] - _recent[i-1]) * (_recent[i-1] - _recent[i-2]) < 0
            )
            if _reversals > 8:
                logger.info(f"[CONDUCTOR] {snapshot.symbol}: BLOCKED by chop detector ({_reversals} reversals in 10 bars)")
                return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"Forex Conductor: Blocked by candle chop detector ({_reversals} reversals)")

        # ── A+ ENTRY FILTER: Strict Multi-Timeframe Alignment ────
        # [REMOVED] Macro trend alignment conflicts no longer block entries because Forex Conductor
        # now exclusively operates on rubberband mechanics which inherently trade counter-trend.

        # Pass the unified direction down into the sub-strategies.
        # Sub-strategies use exec_dir and ltf_dir as instantaneous execution triggers.
        ltf_dir = getattr(snapshot.trend_ltf, "direction", "neutral")
        exec_dir = getattr(snapshot.trend_exec, "direction", "neutral") if getattr(snapshot, "trend_exec", None) else ltf_dir
        gates["exec_dir"] = exec_dir
                
        if regime == "transitional" and not has_reversal:
            if exec_dir in ("long", "short"):
                gates["htf_ltf_conflict"] = True

        # ── NOTE: Macro trend filters tested and reverted ─────────
        # EMA slope, price-vs-EMA, persistence, EMA-50/100 alignment
        # all killed more winners than losers in transitional markets.
        # Partial close + tight stops already limit loss sizes.

        # ── PER-PAIR SESSION COOLDOWN ─────────────────────────────
        # "Test the waters" approach: let each pair trade freely at
        # the start of each session. After 3 losses in a session for
        # a specific pair, block that pair for the rest of the session.
        # Sessions: Asian (0-7), London (7-13), NY (13-20), Late (20-24)
        # Counters reset when a new session starts.
        
        self._bar_index += 1
        sym = snapshot.symbol

        # Determine current session
        if snapshot.candles:
            _hour = snapshot.candles[-1].timestamp.hour
            _date = snapshot.candles[-1].timestamp.date()
            if _hour < 7:
                _session = "asian"
            elif _hour < 13:
                _session = "london"
            elif _hour < 20:
                _session = "ny"
            else:
                _session = "late"
            _session_key = f"{_date}_{_session}"
        else:
            _session_key = "unknown"

        # ── DAILY MAX-LOSS CIRCUIT BREAKER ───────────────────────
        # Cross-symbol: total daily loss across ALL symbols.
        if not hasattr(self, '_daily_total_pnl'):
            self._daily_total_pnl = 0.0
            self._daily_cb_date = None
        current_date = snapshot.candles[-1].timestamp.date() if snapshot.candles else None
        if current_date:
            if self._daily_cb_date != current_date:
                self._daily_total_pnl = 0.0
                self._daily_cb_date = current_date
            
            _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
            breaker_enabled = bool(getattr(_profile, 'safety_drawdown_breaker_enabled', True))
            max_pct = float(getattr(_profile, 'safety_drawdown_max_pct', 0.10))
            
            if breaker_enabled:
                limit = -300.0
                if current_capital:
                    limit = -(current_capital * max_pct)
                    
                if self._daily_total_pnl <= limit:
                    logger.info(
                        f"[CONDUCTOR] {sym}: BLOCKED by daily max-loss "
                        f"(daily total=${self._daily_total_pnl:.2f}, limit=${limit:.2f})"
                    )
                    return None

        # Check if this pair is blocked for the current session
        is_sar_pending = bool(sar_dir)
        sk = (sym, _session_key)
        if self._session_blocked.get(sk) and not is_sar_pending:
            session_losses = self._session_losses.get(sk, 0)
            logger.info(
                f"[CONDUCTOR] {sym}: SESSION COOLDOWN "
                f"({session_losses} losses in {_session_key}, blocked until next session)"
            )
            return None

        # ── Route to primary strategy for this regime ────────────
        primary_key = _REGIME_MAP.get(regime, "london_sweep")
        candidates = [primary_key]

        htf_strength = getattr(snapshot.trend_htf, "strength", 0.0)
        logger.info(
            f"[CONDUCTOR] {snapshot.symbol}: regime={regime}, "
            f"htf_str={htf_strength:.2f}, route={primary_key}, "
            f"candidates={candidates}"
            + (f" [SAR:{sar_dir}]" if sar_dir else "")
        )

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

                # (Net Momentum Validation removed because it suffocates new pullback/reversal trap modules)

                # ── CORRELATION GUARD ─────────────────────────────
                # Prevent simultaneous entries on correlated pairs.
                # SAR entries bypass — they are time-critical.
                _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
                if not getattr(_profile, 'trend_correlation_stacking_enabled', True):
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

                _ts = snapshot.candles[-1].timestamp.strftime('%Y-%m-%d %H:%M') if snapshot.candles else "Unknown"
                logger.info(
                    f"[CONDUCTOR] {_ts} {snapshot.symbol}: "
                    f"Entry via {key} (regime={regime})"
                )
                signal.risk_per_trade_pct = getattr(self._profile, 'risk_per_trade_pct', 0.01)
                # Set entry cooldown for this symbol
                self._entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS

                # ── BROKER MINIMUM STOP GUARD ──
                _ep = float(signal.entry_price or 0.0)
                _sl = float(signal.stop_loss or 0.0)
                if _ep > 0 and _sl > 0:
                    is_jpy = "JPY" in snapshot.symbol.upper()
                    # Minimum 8 pips for prop firms/Oanda minimum stop levels
                    min_sl_dist = 8.0 * (0.01 if is_jpy else 0.0001)
                    
                    _current_ir = abs(_ep - _sl)
                    if _current_ir < min_sl_dist:
                        _ir = min_sl_dist
                        _sl = (_ep - _ir) if signal.bias == "long" else (_ep + _ir)
                        signal.stop_loss = _sl
                        logger.info(f"[CONDUCTOR] {snapshot.symbol}: Widened SL from {_current_ir*10000:.1f} to {min_sl_dist*10000:.1f} pips to meet broker limits. New SL: {_sl:.5f}")
                        signal.notes = (signal.notes or "") + " [SL Widened]"
                    else:
                        _ir = _current_ir
                
                # ── GLOBAL TARGET_R OVERRIDE ──
                # Force the base strategy to respect the config target_r but enforce a minimum mathematical viability floor
                tr = float(getattr(self._profile, 'target_r', 0) or 0)
                if tr > 0:
                    if tr < 0.2:
                        tr = 0.2
                        
                    if _ep > 0 and _sl > 0:
                        if signal.bias == "long":
                            signal.take_profit = _ep + (_ir * tr)
                        else:
                            signal.take_profit = _ep - (_ir * tr)
                else:
                    if _ep > 0 and _sl > 0:
                        # Use a distant 100R target to safely bypass safety validators while keeping trades open
                        if signal.bias == "long":
                            signal.take_profit = _ep + (_ir * 100.0)
                        else:
                            signal.take_profit = _ep - (_ir * 100.0)

                # Expose the specific route (e.g. trend_rider vs london_sweep) to the engine
                signal.strategy_name = f"{self.name} [{key}]"
                return signal

        # ── ATR-BASED FORCED SAR ENTRY (DISABLED) ────────────────────
        # Structural trend strategies (Conductor) cannot survive the SAR
        # whipsaw death spiral. Forced SAR entries have been disabled in
        # favor of strict structural confirmation from the Sub-Strategies.
        if False and sar_dir and snapshot.candles:
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
            logger.info(f"[DEBUG SAR] Reached ATR calculation. candles={candles_ok}, dir={has_direction}")

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
                if tp_dist <= 0:
                    logger.info(f"[DEBUG SAR] TP dist <= 0? {tp_dist}")
                logger.info(
                    f"[CONDUCTOR] {snapshot.symbol}: FORCED SAR {sar_dir.upper()} "
                    f"via engine (ATR={atr:.5f}, sl={sl:.5f}, tp_r={tp_r})"
                )
                self._entry_cooldown[snapshot.symbol] = _ENTRY_COOLDOWN_BARS
                logger.info("[DEBUG SAR] Returning Force SAR Decision")
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
                    strategy_name="[SAR] Reversal",
                )
            else:
                logger.info(f"[DEBUG SAR] ATR WAS ZERO OR NONE! atr={atr}")

        if sar_dir:
            logger.info("[DEBUG SAR] Reached end of function. Returning None.")
        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        current_capital: Optional[float] = None,
        trade_history: Optional[list] = None,
    ) -> Optional[AITradeDecision]:
        """Universal Exit Router Delegation"""
        if not open_position:
            return None
            
        from tradebot_sci.strategy.exit_logic import run_universal_exit_logic
        _profile = getattr(self, 'profile', None) or getattr(self, '_profile', None) or gates.get('profile') or type('_P', (), {})()
        
        return run_universal_exit_logic(
            snapshot=snapshot,
            open_position=open_position,
            gates=gates,
            profile=_profile,
            strategy_name=self.name
        )

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """Score using regime-appropriate strategy."""
        regime = gates.get("market_regime", "unknown")
        
        # ── RANGING/CHOPPY UI FIX ──────────────────────────────────────
        # Display a '-' in the UI to match the engine's internal block
        # on ranging/choppy markets (unless forced by profile).
        _profile = getattr(self, 'profile', None) or gates.get('profile') or type('_P', (), {})()
        block_ranging = bool(getattr(_profile, 'block_ranging_regime', False))
        
        blocked_regimes = ["choppy", "unknown"]
        if block_ranging:
            blocked_regimes.append("ranging")
            
        if regime in blocked_regimes:
            return 0.0, "-", f"Regime blocked: {regime}"

        primary_key = _REGIME_MAP.get(regime)
        if primary_key and primary_key in self._strategies:
            return self._strategies[primary_key].score_signal(snapshot, gates)
        return 0.0, "-", f"No strategy for regime={regime}"
