from __future__ import annotations

import logging
import statistics
import os
from collections import OrderedDict
from datetime import datetime, timezone, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Tuple

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.schemas import MarketContext
from tradebot_sci.market.models import Candle, MarketSnapshot
from tradebot_sci.market.trend import swing_progress
from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.market.trend_enums import TrendDirection
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import (
    AITradeDecision,
    close_position_decision,
    hold_decision,
    scale_out_decision,
    stand_aside_decision,
)
from tradebot_sci.confluence.context import build_confluence
from tradebot_sci.strategy.icc_signals import (
    detect_correction,
    detect_continuation,
    detect_indication,
    detect_liquidity_sweep,
    detect_no_trade_zone,
    detect_structure_invalidation,
    last_structure_range,
    next_structure_target,
)
from tradebot_sci.market.symbols import SYMBOL_METADATA, AssetClass, is_crypto
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.strategy.constants import (
    HTF_TREND_WEIGHT,
    LTF_TREND_WEIGHT,
    VOLATILITY_WEIGHT,
    GRADE_A_PLUS_THRESHOLD,
    GRADE_A_THRESHOLD,
    GRADE_A_MINUS_THRESHOLD,
    GRADE_B_PLUS_THRESHOLD,
    GRADE_B_THRESHOLD,
    GRADE_B_MINUS_THRESHOLD,
    GRADE_C_PLUS_THRESHOLD,
    GRADE_C_THRESHOLD,
    GRADE_C_MINUS_THRESHOLD,
    GRADE_D_THRESHOLD,
    GRADE_F_PLUS_THRESHOLD,
    GRADE_F_THRESHOLD,
    DEFAULT_SESSION_RANGE_MULTIPLIER,
    DEFAULT_SESSION_VOLUME_MULTIPLIER,
    DEFAULT_SESSION_OVERLAP_START_HOUR,
    DEFAULT_SESSION_OVERLAP_END_HOUR,
)

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Orchestrates AI calls so humans can sip coffee instead of panic."""

    def __init__(
        self,
        ai_client: TradeSciAIClient | None,
        market_provider: MarketDataProvider,
        profile: BaseProfile,
        symbol: str,
    ) -> None:
        """Stashes the collaborators so decisions can flow like caffeine."""
        self.ai_client = ai_client
        self.market_provider = market_provider
        self.profile = profile
        self.symbol = symbol
        self._last_auto_entry_time: dict[str, datetime] = {}
        self._last_scale_out_time: dict[str, datetime] = {}
        # AI decision cache with LRU eviction (max 100 entries)
        self._ai_decision_cache: OrderedDict[str, tuple[float, str, str, datetime, AITradeDecision]] = OrderedDict()
        self._ai_decision_cache_max_size = 100

    def build_market_context(
        self,
        snapshot: MarketSnapshot,
        open_position: dict | None = None,
        execution_capabilities: dict | None = None,
        confluence: dict | None = None,
    ) -> MarketContext:
        """Summarizes market state into a neat package for the AI brain."""
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        htf_candles = snapshot.htf_candles or snapshot.candles
        recent_candles = ltf_candles[-20:]
        recent_high = max(c.high for c in recent_candles) if recent_candles else None
        recent_low = min(c.low for c in recent_candles) if recent_candles else None
        sweep = self._detect_sweep(snapshot)
        indication = self._detect_indication(snapshot)
        correction = self._detect_correction(snapshot, indication)
        continuation = self._detect_continuation(snapshot, sweep, indication, correction)
        continuation = self._detect_continuation(snapshot, sweep, indication, correction)
        # Pass all signals to _determine_phase for strict state machine
        phase = self._determine_phase(snapshot, sweep=sweep, continuation=continuation, indication=indication, correction=correction)
        liquidity_sweeps = [sweep.describe()] if sweep else []
        confluence = confluence or build_confluence(
            self.market_provider,
            snapshot.symbol,
            snapshot.candles,
            include_external=os.getenv("CONFLUENCE_EXTERNAL", "false").lower() == "true",
        ).data
        return MarketContext(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            trend_htf=snapshot.trend_htf.direction,
            trend_ltf=snapshot.trend_ltf.direction,
            htf_align=(
                snapshot.trend_ltf.direction != "neutral"
                and (snapshot.trend_htf.direction == "neutral" or snapshot.trend_htf.direction == snapshot.trend_ltf.direction)
            ),
            htf_timeframe=snapshot.htf_timeframe,
            ltf_timeframe=snapshot.ltf_timeframe,
            execution_capabilities=execution_capabilities,
            recent_high=recent_high,
            recent_low=recent_low,
            phase=phase,
            liquidity_sweeps=liquidity_sweeps,
            sweep_confirmed=bool(sweep),
            continuation_confirmed=bool(continuation),
            recent_continuation_detection_rate="0%" if phase == "chop" else None,
            continuation_blocking_reason="choppy markets (HTF=neutral, no HL/LH structure)" if phase == "chop" else None,
            confluence=confluence,
            htf_candles=[{"o": c.open, "h": c.high, "l": c.low, "c": c.close} for c in htf_candles[-5:]],
            ltf_candles=[{"o": c.open, "h": c.high, "l": c.low, "c": c.close} for c in ltf_candles[-5:]],
            open_position=open_position,
            notes=self._build_notes(
                snapshot,
                phase=phase,
                sweep=sweep,
                continuation=continuation,
                indication=indication,
            ),
        )

    def decide(
        self,
        timeframe: str,
        open_position: dict | None = None,
        snapshot: MarketSnapshot | None = None,
        execution_capabilities: dict | None = None,
        current_bar_time: datetime | None = None,
    ) -> AITradeDecision:
        """Fetches data, pokes the AI, and returns a validated idea."""
        snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        caps = execution_capabilities or {}

        confluence = build_confluence(
            self.market_provider,
            snapshot.symbol,
            snapshot.candles,
            include_external=os.getenv("CONFLUENCE_EXTERNAL", "false").lower() == "true",
        ).data

        # Allow neutral HTF if LTF shows clear direction (realistic trend development)
        # Block only if HTF directly opposes LTF
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction
        htf_align = (
            ltf_dir != "neutral"  # LTF must be trending
            and (htf_dir == "neutral" or htf_dir == ltf_dir)  # HTF can be neutral or aligned with LTF
        )

        # Detect ICC signals BEFORE venue gate check
        # This ensures we can see fresh signals and invalidate cache properly
        sweep = self._detect_sweep(snapshot)
        indication = self._detect_indication(snapshot)
        correction = self._detect_correction(snapshot, indication)
        continuation = self._detect_continuation(snapshot, sweep, indication, correction)

        # Check venue gates (long-only venues with bearish structure)
        venue_decision = self._check_venue_gates(snapshot, caps, open_position, htf_align)
        if venue_decision is not None:
            # Update gates with actual signal state before returning
            return venue_decision.copy(update={
                "gates": {
                    "htf_align": htf_align,
                    "sweep": bool(sweep),
                    "continuation": bool(continuation),
                    "indication": bool(indication),
                    "venue_ok": False,
                }
            })

        # DEBUG: Log trend alignment and ICC signal detection
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[STRATEGY] {snapshot.symbol} HTF={htf_dir} LTF={ltf_dir} align={htf_align} "
            f"sweep={sweep is not None} continuation={continuation is not None}"
        )
        # Pass all signals to _determine_phase for strict state machine
        phase = self._determine_phase(snapshot, sweep=sweep, continuation=continuation, indication=indication, correction=correction)
        _, stack_label = self._confluence_stack_score(snapshot, sweep, continuation)
        session_ok, session_reason = self._session_health(snapshot)
        supports_short = not (caps.get("long_only") is True or caps.get("supports_short") is False)
        venue_ok = True if snapshot.trend_htf.direction != "short" else supports_short

        gates = {
            "htf_align": htf_align,
            "sweep": bool(sweep),
            "continuation": bool(continuation),
            "indication": bool(indication),
            "venue_ok": venue_ok,
        }
        gates.update(
            {
                "htf_dir": htf_dir,
                "ltf_dir": ltf_dir,
                "htf_strength": round(float(snapshot.trend_htf.strength or 0.0), 3),
                "ltf_strength": round(float(snapshot.trend_ltf.strength or 0.0), 3),
                "phase": phase,
                "stack_label": stack_label,
                "session_ok": session_ok,
                "continuation_dir": continuation.direction if continuation else None,
                "sweep_dir": sweep.direction if sweep else None,
            }
        )
        score, score_breakdown, score_threshold = self._score_icc_entry(
            snapshot=snapshot,
            sweep=sweep,
            continuation=continuation,
            indication=indication,
            phase=phase,
            htf_align=htf_align,
        )
        gates.update(
            {
                "score": round(score, 2),
                "score_threshold": round(score_threshold, 2),
                "score_breakdown": score_breakdown,
            }
        )

        # Check invalidation for open positions
        invalidation_decision = self._check_invalidation_gate(snapshot, open_position, gates)
        if invalidation_decision is not None:
            return invalidation_decision

        # Check if we can pyramid/scale into existing position (BEFORE commitment mode)
        if open_position and abs(open_position.get("size", 0.0)) > 0:
            pyramid_decision = self._check_pyramid_entry(
                snapshot=snapshot,
                open_position=open_position,
                sweep=sweep,
                continuation=continuation,
                phase=phase,
                htf_align=htf_align,
                gates=gates,
            )
            if pyramid_decision is not None:
                return pyramid_decision

        # Check commitment mode (AFTER pyramid check, so we can add to position)
        commitment_decision = self._check_commitment_mode(snapshot, open_position, phase, gates)
        if commitment_decision is not None:
            return commitment_decision

        # Check ICC gates for new entries
        if not open_position:
            # No-trade zone check (skip if we have sweep+continuation)
            no_trade_decision = self._check_no_trade_zone(snapshot, indication, sweep, continuation, phase, gates)
            if no_trade_decision is not None:
                return no_trade_decision

            # Session health gate for A+ setups
            session_decision = self._check_session_health_gate(
                snapshot, sweep, continuation, stack_label, session_ok, session_reason, phase, gates
            )
            if session_decision is not None:
                return session_decision

            # ICC scoring gate (points-based)
            # If score passes threshold, proceed with auto-entry
            # If score fails but AI is available, skip score gate and let AI decide
            # If score fails and no AI, block entry
            score_gate_decision = self._check_icc_entry_score(
                snapshot,
                sweep,
                continuation,
                indication,
                htf_align,
                phase,
                score,
                score_breakdown,
                score_threshold,
                gates,
            )
            if score_gate_decision is not None:
                # Score failed - check if AI can override
                if self.ai_client is not None:
                     # OPIMIZATION: Don't ask AI if the setup is fundamentally weak (HTF strength)
                     # This prevents 1000s of API calls during chop
                    min_htf_strength = getattr(self.profile, "icc_auto_entry_min_htf_strength", 0.0)
                    htf_strength = float(snapshot.trend_htf.strength or 0.0)
                    
                    # DEBUG LOG
                    logger.info(f"[DEBUG] HTF Gate Check: strength={htf_strength}, min={min_htf_strength}, score={score}")

                    if htf_strength < min_htf_strength:
                        logger.info(
                            "[STRATEGY] Skipping AI override: HTF strength %.2f < %.2f (Hard Gate)",
                            htf_strength, min_htf_strength
                        )
                        return score_gate_decision
                    
                    if score < 10.0:
                         logger.info(f"[STRATEGY] Skipping AI override: Score {score} is too low (Garbage)")
                         return score_gate_decision

                    # AI available - skip score gate, let AI decide later
                    logger.info(
                        "[SCORING] Score %s/%s failed, deferring to AI decision",
                        score,
                        score_threshold,
                    )
                else:
                    # No AI - enforce score gate
                    return score_gate_decision

            auto_entry_enabled = bool(getattr(self.profile, "icc_auto_entry_enabled", False))
            if continuation is not None:
                bar_time = current_bar_time
                if bar_time is None and snapshot.candles:
                    bar_time = getattr(snapshot.candles[-1], "timestamp", None) or getattr(
                        snapshot.candles[-1], "time", None
                    )
                if bar_time is None:
                    logger.warning("[AUTO-ENTRY] No timestamp available")
                else:
                    if bar_time.tzinfo is None:
                        bar_time = bar_time.replace(tzinfo=timezone.utc)
                    eastern_time = bar_time.astimezone(ZoneInfo("America/New_York"))
                    logger.info(
                        "[AUTO-ENTRY] Continuation detected: time=%s, direction=%s, sweep=%s, htf_strength=%.2f",
                        eastern_time.strftime("%Y-%m-%d %H:%M %Z"),
                        getattr(continuation, "direction", "unknown"),
                        sweep is not None,
                        snapshot.trend_htf.strength,
                    )
            allow_auto_entry = True
            auto_entry_time = current_bar_time
            if auto_entry_time is None and snapshot.candles:
                auto_entry_time = snapshot.candles[-1].timestamp
            if auto_entry_time is None:
                allow_auto_entry = False
                logger.warning("[AUTO-ENTRY] No timestamp available for market hours gate")
            elif phase == "chop":
                # [ANTIGRAVITY FIX] Removed hard block. Use as filter/context only.
                # allow_auto_entry remains True (inherited).
                logger.info("[AUTO-ENTRY] CHOP PHASE: proceeding with caution (structure override)")
            else:
                if auto_entry_time.tzinfo is None:
                    auto_entry_time = auto_entry_time.replace(tzinfo=timezone.utc)
                if auto_entry_enabled and snapshot.symbol in {"SPY", "QQQ", "IWM"}:
                    eastern_time = auto_entry_time.astimezone(ZoneInfo("America/New_York"))
                    market_open = dt_time(9, 30)
                    market_close = dt_time(16, 0)
                    current_time = eastern_time.time()
                    if not (market_open <= current_time < market_close):
                        allow_auto_entry = False
                        logger.info(
                            "[AUTO-ENTRY] BLOCKED by market hours: %s",
                            eastern_time.strftime("%Y-%m-%d %H:%M %Z"),
                        )
                        logger.info(
                            "[STRATEGY] %s Auto-entry blocked: Outside market hours "
                            "(current: %s, requires 09:30-16:00 EST)",
                            snapshot.symbol,
                            eastern_time.strftime("%H:%M %Z"),
                        )
            if auto_entry_enabled and allow_auto_entry:
                # Cooldown check REMOVED for market entries per user request.
                # Logic passed to AI will handle its own throttling if needed.
                pass
            require_sweep = bool(getattr(self.profile, "icc_auto_entry_require_sweep", True))
            sweep_confirmed = bool(sweep)
            continuation_confirmed = continuation is not None
            two_signal_override = bool(getattr(self.profile, "icc_two_signal_override_enabled", False))
            two_signal_ready = two_signal_override and sweep is not None and (continuation is not None or indication)
            auto_entry_enabled = auto_entry_enabled or two_signal_ready
            sweep_ok = (not require_sweep) or sweep_confirmed
            # [REVERTED] Keep requiring continuation - it's the breakout confirmation
            # Aggressive mode (sweep+indication) was entering too early and blowing accounts
            continuation_ok = continuation is not None

            if auto_entry_enabled and allow_auto_entry and sweep_ok and continuation_ok:
                # Require minimum HTF trend strength for auto entries
                # [ANTIGRAVITY FIX] Removed HTF filter (default 0.0) to allow aggressive chopping
                min_htf_strength = getattr(self.profile, "icc_auto_entry_min_htf_strength", 0.0)
                htf_strength = snapshot.trend_htf.strength

                if htf_strength < min_htf_strength:
                    logger.info(
                        "[AUTO-ENTRY] BLOCKED by HTF strength: %.2f < %.2f",
                        htf_strength,
                        min_htf_strength,
                    )
                    logger.info(
                        f"[STRATEGY] {snapshot.symbol} Auto-entry blocked: HTF strength {htf_strength:.2f} "
                        f"< minimum {min_htf_strength:.2f}"
                    )
                else:
                    auto_decision = self._build_auto_entry_decision(
                        snapshot,
                        continuation=continuation,
                        sweep=sweep,
                        indication=indication,
                        phase=phase,
                        stack_label=stack_label,
                    )
                    if auto_decision is not None:
                        auto_decision = self._apply_icc_post_checks(
                            auto_decision,
                            snapshot=snapshot,
                            open_position=open_position,
                            phase=phase,
                            sweep_confirmed=sweep_confirmed,
                            continuation_confirmed=continuation_confirmed,
                            session_health_ok=session_ok,
                            stack_label=stack_label,
                            confluence=confluence,
                        )
                        auto_decision = auto_decision.copy(update={"gates": gates})
                        self._last_auto_entry_time[snapshot.symbol] = auto_entry_time
                        return validate_decision(auto_decision, execution_capabilities=execution_capabilities)
        context = self.build_market_context(
            snapshot,
            open_position=open_position,
            execution_capabilities=execution_capabilities,
            confluence=confluence,
        )
        if self.ai_client is None:
            decision = stand_aside_decision(
                snapshot.symbol,
                timeframe,
                "AI disabled for deterministic backtest",
            )
            decision = decision.copy(update={"gates": gates})
            return decision

        # OPTIMIZATION: Final check to preventing expensive AI calls on weak setups
        # If auto-entry was blocked by HTF strength, AI should typically not override it in backtest
        min_htf_strength = getattr(self.profile, "icc_auto_entry_min_htf_strength", 0.0)
        htf_strength = float(snapshot.trend_htf.strength or 0.0)
        
        # Only block if we have a hard gate configured (min > 0)
        if min_htf_strength > 0 and htf_strength < min_htf_strength:
             logger.info(f"[STRATEGY] Optimization: Blocking AI call for {self.symbol} (HTF {htf_strength:.2f} < {min_htf_strength:.2f})")
             decision = stand_aside_decision(
                 snapshot.symbol, 
                 timeframe, 
                 f"AI Blocked: HTF Strength {htf_strength:.2f} < {min_htf_strength:.2f}"
             )
             decision = decision.copy(update={"gates": gates})
             return decision

        # Hybrid cache: 15-min TTL + HTF/LTF trend state tracking + fresh continuation check
        cache_score = round(score, 2)
        cache_key = snapshot.symbol
        cached = self._ai_decision_cache.get(cache_key)
        now = datetime.now(timezone.utc)
        cache_ttl_minutes = 15

        # Check cache validity: score + trends match AND within TTL AND no fresh continuation
        cache_valid = False
        if cached is not None:
            cached_score, cached_htf, cached_ltf, cached_time, cached_decision = cached
            elapsed_minutes = (now - cached_time).total_seconds() / 60.0

            htf_trend = snapshot.trend_htf.direction
            ltf_trend = snapshot.trend_ltf.direction

            score_match = cached_score == cache_score
            trend_match = (cached_htf == htf_trend and cached_ltf == ltf_trend)
            within_ttl = elapsed_minutes < cache_ttl_minutes

            # CRITICAL: Invalidate cache if continuation/sweep JUST triggered (fresh signal)
            # When continuation fires, structure fundamentally changes even if score stays similar
            # Calculate bars_ago from signal index
            fresh_continuation = False
            fresh_sweep = False
            if continuation is not None and hasattr(continuation, 'index'):
                bars_ago_cont = len(snapshot.candles) - 1 - continuation.index
                fresh_continuation = bars_ago_cont <= 1
            if sweep is not None and hasattr(sweep, 'index'):
                bars_ago_sweep = len(snapshot.candles) - 1 - sweep.index
                fresh_sweep = bars_ago_sweep <= 1

            fresh_signal = fresh_continuation or fresh_sweep

            if fresh_signal:
                logger.info(
                    f"[CACHE] {snapshot.symbol} invalidating cache due to fresh signal: "
                    f"continuation={fresh_continuation} sweep={fresh_sweep}"
                )

            cache_valid = score_match and trend_match and within_ttl and not fresh_signal

        if cache_valid:
            decision = cached_decision.copy(deep=True)
            # Move to end (mark as recently used)
            self._ai_decision_cache.move_to_end(cache_key)
        else:
            decision = self.ai_client.generate_decision(context)
            htf_trend = snapshot.trend_htf.direction
            ltf_trend = snapshot.trend_ltf.direction
            self._ai_decision_cache[cache_key] = (cache_score, htf_trend, ltf_trend, now, decision)
            # LRU eviction: remove oldest entry if cache exceeds max size
            if len(self._ai_decision_cache) > self._ai_decision_cache_max_size:
                self._ai_decision_cache.popitem(last=False)  # Remove oldest (FIFO)
        decision = self._apply_icc_post_checks(
            decision,
            snapshot=snapshot,
            open_position=open_position,
            phase=phase,
            sweep_confirmed=bool(sweep),
            continuation_confirmed=bool(continuation),
            session_health_ok=session_ok,
            stack_label=stack_label,
            confluence=confluence,
        )
        
        # Bug Fix: Check structural invalidation BEFORE returning an entry decision
        # This prevents entering a trade that is already technically invalid on HTF
        if decision.action in {"enter_long", "enter_short"}:
             entry_invalidation = self._check_entry_invalidation(decision, snapshot, gates)
             if entry_invalidation:
                 return entry_invalidation

        decision = decision.copy(update={"gates": gates})
        decision = validate_decision(decision, execution_capabilities=execution_capabilities)
        return decision

    def _check_entry_invalidation(
        self,
        decision: AITradeDecision,
        snapshot: MarketSnapshot,
        gates: dict,
    ) -> AITradeDecision | None:
        """Checks if a proposed entry is already structurally invalid."""
        if decision.action not in {"enter_long", "enter_short"}:
            return None
            
        direction = "long" if decision.action == "enter_long" else "short"
        htf_candles = snapshot.htf_candles or snapshot.candles
        
        # Check structural invalidation
        invalidation = detect_structure_invalidation(
            htf_candles,
            direction,
            swing_lookback=2
        )
        
        if invalidation:
            reason = invalidation.describe()
            logger.warning(
                f"[ENTRY BLOCKED] Structure invalidation detected for {decision.symbol} {direction}: {reason}"
            )
            return stand_aside_decision(
                decision.symbol,
                decision.timeframe,
                f"Entry blocked: Structure invalidated ({reason})"
            ).copy(update={"gates": gates})
            
        return None

    def _build_auto_entry_decision(
        self,
        snapshot: MarketSnapshot,
        *,
        continuation,
        sweep,
        indication,
        phase: str,
        stack_label: str,
    ) -> AITradeDecision | None:
        entry_price = snapshot.candles[-1].close if snapshot.candles else None
        if entry_price is None:
            return None

        # Direction comes from continuation (required) or sweep as fallback
        direction = getattr(continuation, "direction", None) if continuation else getattr(sweep, "direction", None)
        if direction not in {"long", "short"}:
            return None

        htf_candles = snapshot.htf_candles or snapshot.candles
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        stop_loss = None
        # Prefer HTF structure for stop placement (ICC guidance).
        structure_levels = last_structure_range(htf_candles, swing_lookback=2)
        if structure_levels:
            last_high, last_low = structure_levels
            stop_loss = last_low if direction == "long" else last_high
        # Fall back to LTF structure if HTF structure isn't available.
        if stop_loss is None:
            structure_levels = last_structure_range(ltf_candles, swing_lookback=1)
            if structure_levels:
                last_high, last_low = structure_levels
                stop_loss = last_low if direction == "long" else last_high
        if stop_loss is None:
            stop_loss = float(getattr(sweep, "swept_price", 0.0)) if sweep is not None else None
        if stop_loss is None and ltf_candles:
            last_candle = ltf_candles[-1]
            if direction == "long":
                stop_loss = min(float(last_candle.low), entry_price * 0.995)
            else:
                stop_loss = max(float(last_candle.high), entry_price * 1.005)

        # Validate entry_price and stop_loss before arithmetic
        if entry_price is None or entry_price <= 0:
            return None
        if stop_loss is None or stop_loss <= 0:
            return None

        entry_price = float(entry_price)
        stop_loss = float(stop_loss)
        if direction == "long" and stop_loss >= entry_price:
            stop_loss = min(entry_price * 0.995, stop_loss)
        if direction == "short" and stop_loss <= entry_price:
            stop_loss = max(entry_price * 1.005, stop_loss)

        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return None

        target_risk_multiplier = 2.5
        target = next_structure_target(htf_candles, direction, entry_price=entry_price, swing_lookback=1)
        if target is None:
            target = (
                entry_price + (risk * target_risk_multiplier)
                if direction == "long"
                else entry_price - (risk * target_risk_multiplier)
            )
        else:
            target = float(target)

        if direction == "long" and target <= entry_price:
            target = entry_price + (risk * target_risk_multiplier)
        if direction == "short" and target >= entry_price:
            target = entry_price - (risk * target_risk_multiplier)

        min_reward = risk * target_risk_multiplier
        if direction == "long" and (target - entry_price) < min_reward:
            target = entry_price + min_reward
        if direction == "short" and (entry_price - target) < min_reward:
            target = entry_price - min_reward

        action = "enter_long" if direction == "long" else "enter_short"
        if continuation:
            trigger_label = "sweep+continuation (Phase 3)"
        else:
            # Should be unreachable with auto-entry logic, but handled for manual overrides
            trigger_label = "manual/override"
        notes = f"Auto ICC entry: {trigger_label}; stack={stack_label}"
        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=direction,
            phase=phase if phase != "chop" else "continuation",
            action=action,
            entry_price=entry_price,
            entry_zone=None,
            stop_loss=stop_loss,
            take_profit=target,
            risk_per_trade_pct=None,
            max_position_size_pct=None,
            time_in_force_sec=None,
            urgency="medium",
            structure_summary=notes,
            invalidation_conditions="Stop below/above correction low/high.",
            management_instructions="Manage per ICC continuation rules.",
            notes=notes,
        )

    def score_structure(self, snapshot: MarketSnapshot) -> tuple[float, str]:
        """Scores ICC structure cleanliness for symbol selection."""
        # Allow neutral HTF if LTF shows clear direction
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction
        if ltf_dir == "neutral":
            return 0.0, "LTF neutral"
        if htf_dir not in {"neutral", ltf_dir}:  # Block if HTF opposes LTF
            return 0.0, "HTF/LTF misaligned"
        base = snapshot.trend_htf.strength * HTF_TREND_WEIGHT + snapshot.trend_ltf.strength * LTF_TREND_WEIGHT
        vol_score = self._calc_volatility_percentile(snapshot.candles, window=20, history=120)
        score = base + VOLATILITY_WEIGHT * vol_score
        reason = f"trend aligned, vol_pct={vol_score:.2f}"
        return min(score, 1.2), reason

    def score_icc_readiness(self, snapshot: MarketSnapshot) -> tuple[float, str]:
        """Scores ICC readiness (sweep + continuation) for explainable logging."""
        # Allow neutral HTF if LTF shows clear direction
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction
        if ltf_dir == "neutral":
            return 0.0, "LTF neutral"
        if htf_dir not in {"neutral", ltf_dir}:  # Block if HTF opposes LTF
            return 0.0, "HTF/LTF misaligned"
        sweep = self._detect_sweep(snapshot)
        indication = self._detect_indication(snapshot)
        correction = self._detect_correction(snapshot, indication)
        continuation = self._detect_continuation(snapshot, sweep, indication, correction)
        session_ok, session_reason = self._session_health(snapshot)
        stack_score, stack_label = self._confluence_stack_score(snapshot, sweep, continuation)
        if sweep and continuation:
            if not session_ok:
                return 0.7, f"sweep+continuation; session weak ({session_reason}); stack={stack_label}"
            return 1.0, f"sweep+continuation confirmed; stack={stack_label}"
        if sweep and not continuation:
            # If we rely on the Point System, a confirmed Sweep is a valid "Ready" state (Yellow/Green).
            # The actual entry trigger is the Score.
            return 0.9, f"sweep confirmed; READY (Points System); stack={stack_label}"
        return 0.1, f"awaiting sweep; stack={stack_label}"

    def score_icc_grade(self, snapshot: MarketSnapshot) -> tuple[float, str]:
        """Scores ICC setup quality on a smooth 0-1 scale and returns a letter grade."""
        htf_strength = float(snapshot.trend_htf.strength or 0.0)
        ltf_strength = float(snapshot.trend_ltf.strength or 0.0)
        htf_candles = snapshot.htf_candles or snapshot.candles
        ltf_candles = snapshot.ltf_candles or snapshot.candles

        if snapshot.trend_htf.direction == "neutral":
            htf_strength = max(
                htf_strength,
                swing_progress(htf_candles, swing_lookback=2, min_swings=3),
            )
        if snapshot.trend_ltf.direction == "neutral":
            ltf_strength = max(
                ltf_strength,
                swing_progress(ltf_candles, swing_lookback=2, min_swings=3),
            )

        align = (
            snapshot.trend_htf.direction != "neutral"
            and snapshot.trend_ltf.direction != "neutral"
            and snapshot.trend_htf.direction == snapshot.trend_ltf.direction
        )
        sweep = self._detect_sweep(snapshot)
        indication = self._detect_indication(snapshot)
        correction = self._detect_correction(snapshot, indication)
        continuation = self._detect_continuation(snapshot, sweep, indication, correction)
        session_ok, _ = self._session_health(snapshot)

        score = 0.0
        score += 0.35 * htf_strength
        score += 0.25 * ltf_strength
        if align:
            score += 0.15
        if sweep:
            score += 0.1
        if continuation:
            score += 0.12
        if indication:
            score += 0.08
        if session_ok:
            score += 0.05
        if not align:
            score *= 0.7
        score = min(1.0, max(0.0, score))
        return score, self._grade_from_score(score)

    def score_icc_watch(self, snapshot: MarketSnapshot) -> tuple[float, str, bool]:
        """Scores pre-flip watch state when HTF/LTF are not yet aligned."""
        aligned = (
            snapshot.trend_htf.direction != "neutral"
            and snapshot.trend_ltf.direction != "neutral"
            and snapshot.trend_htf.direction == snapshot.trend_ltf.direction
        )
        if aligned:
            return 0.0, "F-", False

        ltf_candles = snapshot.ltf_candles or snapshot.candles
        ltf_strength = float(snapshot.trend_ltf.strength or 0.0)
        if snapshot.trend_ltf.direction == "neutral":
            ltf_strength = max(ltf_strength, swing_progress(ltf_candles, swing_lookback=2, min_swings=3))

        sweep = self._detect_sweep(snapshot)
        indication = self._detect_indication(snapshot)
        compression = 1.0 - self._calc_volatility_percentile(snapshot.candles, window=20, history=120)
        signal = 1.0 if sweep else 0.6 if indication else 0.2

        score = 0.4 * ltf_strength + 0.3 * compression + 0.3 * signal
        score = min(0.7, max(0.0, score))
        flip_watch = score >= 0.35
        return score, self._grade_from_score(score), flip_watch

    @staticmethod
    def _grade_from_score(score: float) -> str:
        if score >= GRADE_A_PLUS_THRESHOLD:
            return "A+"
        if score >= GRADE_A_THRESHOLD:
            return "A"
        if score >= GRADE_A_MINUS_THRESHOLD:
            return "A-"
        if score >= GRADE_B_PLUS_THRESHOLD:
            return "B+"
        if score >= GRADE_B_THRESHOLD:
            return "B"
        if score >= GRADE_B_MINUS_THRESHOLD:
            return "B-"
        if score >= GRADE_C_PLUS_THRESHOLD:
            return "C+"
        if score >= GRADE_C_THRESHOLD:
            return "C"
        if score >= GRADE_C_MINUS_THRESHOLD:
            return "C-"
        if score >= GRADE_D_THRESHOLD:
            return "D"
        if score >= GRADE_F_PLUS_THRESHOLD:
            return "F+"
        if score >= GRADE_F_THRESHOLD:
            return "F"
        return "F-"

    def icc_gate_telemetry(self, snapshot: MarketSnapshot) -> dict:
        """Returns helpful gate timing telemetry for logs (best-effort)."""
        # Allow neutral HTF if LTF shows clear direction (realistic trend development)
        # Block only if HTF directly opposes LTF
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction
        htf_align = (
            ltf_dir != "neutral"  # LTF must be trending
            and (htf_dir == "neutral" or htf_dir == ltf_dir)  # HTF can be neutral or aligned with LTF
        )
        sweep = self._detect_sweep(snapshot) if htf_align else None
        indication = self._detect_indication(snapshot)
        correction = self._detect_correction(snapshot, indication) if htf_align else None
        continuation = self._detect_continuation(snapshot, sweep, indication, correction) if htf_align else None

        def since(index: int | None) -> float | None:
            if index is None:
                return None
            if index < 0 or index >= len(snapshot.candles):
                return None
            try:
                now_ts = snapshot.candles[-1].timestamp
                then_ts = snapshot.candles[index].timestamp
                return float((now_ts - then_ts).total_seconds())
            except Exception as e:
                logger.error(f"Failed to calculate time delta for index {index}: {e}")
                return None

        sweep_idx = getattr(sweep, "index", None) if sweep else None
        cont_idx = getattr(continuation, "index", None) if continuation else None
        time_since_sweep_s = since(sweep_idx)
        time_since_continuation_s = since(cont_idx)

        if not htf_align:
            last_gate = None
        elif not sweep:
            last_gate = "htf_align"
        elif sweep and not continuation:
            last_gate = "sweep"
        else:
            last_gate = "continuation"

        return {
            "htf_align": htf_align,
            "sweep": bool(sweep),
            "continuation": bool(continuation),
            "last_gate_to_true": last_gate,
            "time_since_sweep_s": time_since_sweep_s,
            "time_since_continuation_s": time_since_continuation_s,
        }

    def _calc_volatility(self, candles: List[Candle]) -> float:
        returns = []
        for prev, curr in zip(candles, candles[1:]):
            if prev.close <= 0:
                continue
            returns.append((curr.close - prev.close) / prev.close)
        if not returns:
            return 0.0
        if len(returns) < 2:
            return abs(returns[0])
        return abs(statistics.stdev(returns))

    def _calc_volatility_percentile(self, candles: List[Candle], *, window: int, history: int) -> float:
        if len(candles) < max(window + 1, history):
            return 0.5
        recent = candles[-window:]
        recent_vol = self._calc_volatility(recent)
        vols: list[float] = []
        start = max(0, len(candles) - history)
        slice_candles = candles[start:]
        for i in range(window, len(slice_candles)):
            sub = slice_candles[i - window : i]
            vols.append(self._calc_volatility(sub))
        if not vols:
            return 0.5
        below = sum(1 for v in vols if v <= recent_vol)
        return min(1.0, max(0.0, below / float(len(vols))))

    def _determine_phase(
        self,
        snapshot: MarketSnapshot,
        *,
        sweep: object | None = None,
        continuation: object | None = None,
        indication: object | None = None,
        correction: object | None = None,
    ) -> str:
        """Infers ICC phase from strict state machine logic.
        
        States:
        1. RANGE (No Trade Zone): Price is inside HTF swing high/low.
        2. INDICATION: Price broke NTZ. Waiting for pullback.
        3. CORRECTION: Price pulling back.
        4. CONTINUATION: Entry trigger.
        """
        # 1. Check No Trade Zone
        # Use HTF candles for NTZ as per strict rules (Day 7)
        htf_candles = snapshot.htf_candles or snapshot.candles
        ntz = detect_no_trade_zone(htf_candles, swing_lookback=2)
        
        if ntz and not ntz.is_broken:
            # We are inside the range. STRICT NO TRADE.
            return "range" # New phase "range" maps to "chop" or "stand_aside" logic
            
        # 2. If NTZ is broken, we have an implicit Indication (or explicit one passed in)
        # If we have a valid Continuation signal, we are in execution phase
        if continuation:
            return "continuation"
            
        # 3. If we have a Correction signal, we are monitoring for entry
        if correction:
            return "correction"
            
        # 4. If we have Indication but no Correction yet, we are waiting
        if indication or (ntz and ntz.is_broken):
            return "indication"
            
        # Fallback
        return "chop"

    def _detect_sweep(self, snapshot: MarketSnapshot):
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction

        # HTF can be neutral, long, or short
        if htf_dir not in {"long", "short", "neutral"}:
            return None

        trend_dir = ltf_dir if ltf_dir in {"long", "short"} else (
            htf_dir if htf_dir in {"long", "short"} else None
        )
        if trend_dir is None:
            return None
        # Block only when HTF explicitly opposes a trending LTF
        if ltf_dir in {"long", "short"} and htf_dir in {"long", "short"} and htf_dir != ltf_dir:
            return None

        ltf_candles = snapshot.ltf_candles or snapshot.candles
        return detect_liquidity_sweep(ltf_candles, trend_dir, swing_lookback=1)

    def _detect_continuation(self, snapshot: MarketSnapshot, sweep, indication, correction=None):
        """Wrapper for detect_continuation."""
        # [FIX] Use HTF candles to match indication/correction timeframe
        # All ICC signals should use the same timeframe for consistency
        htf_candles = snapshot.htf_candles or snapshot.candles
        htf_dir = snapshot.trend_htf.direction
        
        if htf_dir not in {"long", "short"}:
            # If HTF is neutral, use LTF direction
            htf_dir = snapshot.trend_ltf.direction
            if htf_dir not in {"long", "short"}:
                return None

        require_sweep = bool(getattr(self.profile, "icc_auto_entry_require_sweep", True))
        # [ANTIGRAVITY FIX] Configurable confirmation bars for trade frequency tuning
        # Default to 1 for more trades (human traders use 1-bar confirmation)
        confirmation_bars = int(getattr(self.profile, "icc_confirmation_bars", 1))
        max_bars_after_sweep = int(getattr(self.profile, "icc_max_bars_after_sweep", 30))

        return detect_continuation(
            htf_candles,
            htf_dir,
            sweep,
            indication,
            correction=correction,
            # [ANTIGRAVITY FIX] Relaxed for higher trade frequency
            require_sweep=False,
            require_indication=False,
            require_correction=False,
            max_bars_after_sweep=max_bars_after_sweep,
            swing_lookback=1,
            confirmation_bars=confirmation_bars,
        )

    def _detect_indication(self, snapshot: MarketSnapshot):
        htf_candles = snapshot.htf_candles or snapshot.candles
        return detect_indication(htf_candles, swing_lookback=1)

    def _detect_correction(self, snapshot: MarketSnapshot, indication):
        """Wrapper for detect_correction."""
        from tradebot_sci.strategy.icc_signals import detect_correction
        if indication is None:
            return None
        # [FIX] Use HTF candles to match indication timeframe
        # Indication is detected on HTF, so correction should also check HTF
        htf_candles = snapshot.htf_candles or snapshot.candles
        return detect_correction(htf_candles, indication, swing_lookback=1)

    def _build_notes(
        self,
        snapshot: MarketSnapshot,
        *,
        phase: str,
        sweep,
        continuation,
        indication,
    ) -> str:
        stack_score, stack_label = self._confluence_stack_score(snapshot, sweep, continuation)
        parts = [
            f"phase={phase}",
            f"htf={snapshot.trend_htf.direction}",
            f"ltf={snapshot.trend_ltf.direction}",
            f"stack={stack_label}({stack_score:.2f})",
        ]
        if indication:
            parts.append(indication.describe())
        if sweep:
            parts.append(sweep.describe())
        if continuation:
            parts.append(continuation.describe())
        return "; ".join(parts)

    def _apply_icc_post_checks(
        self,
        decision: AITradeDecision,
        *,
        snapshot: MarketSnapshot,
        open_position: dict | None,
        phase: str,
        sweep_confirmed: bool,
        continuation_confirmed: bool,
        session_health_ok: bool,
        stack_label: str,
        confluence: dict | None = None,
    ) -> AITradeDecision:
        confluence = confluence or {}
        risk_cap = confluence.get("risk_cap_pct")
        if not isinstance(risk_cap, (int, float)):
            risk_cap = 0.05

        if decision.action in {"enter_long", "enter_short"}:
            # Removed hard gate for sweep+continuation - scoring system handles this
            # (sweep = 25 points, continuation = 25 points in scoring)
            if stack_label == "A+" and not session_health_ok:
                return stand_aside_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    "ICC gate: A+ session health weak (wait for expansion/volume).",
                )
            if risk_cap <= 0:
                return stand_aside_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    "Confluence gate: risk_cap_pct=0 (market closed / unsafe conditions).",
                )
            entry_ref = decision.entry_price or (snapshot.candles[-1].close if snapshot.candles else None)
            target = None
            if entry_ref is not None:
                htf_candles = snapshot.htf_candles or snapshot.candles
                target = next_structure_target(
                    htf_candles,
                    "long" if decision.action == "enter_long" else "short",
                    entry_price=float(entry_ref),
                    swing_lookback=1,
                )
            if target is not None:
                decision = decision.copy(
                    update={
                        "take_profit": float(target),
                        "notes": f"{decision.notes} | TP aligned to HTF swing target={target:.4f}",
                    }
                )
            if decision.risk_per_trade_pct is None:
                decision = decision.copy(update={"risk_per_trade_pct": float(min(0.05, risk_cap))})
            elif isinstance(decision.risk_per_trade_pct, (int, float)) and decision.risk_per_trade_pct > risk_cap:
                decision = decision.copy(
                    update={
                        "risk_per_trade_pct": float(risk_cap),
                        "notes": f"{decision.notes} | risk capped by confluence (cap={risk_cap:.2f})",
                    }
                )
        if decision.action == "scale_in":
            if not open_position:
                return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "ICC gate: no scale_in without position.")
            if not continuation_confirmed:
                return stand_aside_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    "ICC gate: scale_in requires continuation confirmation.",
                )
        if open_position and decision.action in {"close_position", "reduce_position"} and not decision.emergency_exit:
            htf_candles = snapshot.htf_candles or snapshot.candles
            inv = detect_structure_invalidation(
                htf_candles,
                str(open_position.get("direction", "")).lower(),
                swing_lookback=1,
            )
            if inv is None:
                return hold_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    bias=str(open_position.get("direction", "neutral")).lower(),
                    phase=phase,
                    reason="ICC hold: exit blocked until HTF invalidation confirms.",
                )
        return decision.copy(update={"phase": phase})

    def _check_venue_gates(
        self,
        snapshot: MarketSnapshot,
        caps: dict,
        open_position: dict | None,
        htf_align: bool,
    ) -> AITradeDecision | None:
        """Check venue-specific constraints (long-only venues with bearish structure).

        Returns a stand_aside decision if venue constraints block the trade, None otherwise.
        """
        if not open_position and (caps.get("long_only") is True or caps.get("supports_short") is False):
            if snapshot.trend_htf.direction == "short":
                decision = stand_aside_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    "Venue long-only (supports_short=false); bearish structure; wait for long reset/continuation.",
                )
                return decision.copy(
                    update={
                        "gates": {"htf_align": htf_align, "sweep": False, "continuation": False, "venue_ok": False},
                        "decision_reason_codes": ["VENUE_LONG_ONLY_BEARISH"],
                    }
                )
        return None

    def _check_icc_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
    ) -> AITradeDecision | None:
        """Evaluates ICC structure for exit signals (Indication -> Correction -> Continuation).
        
        Per ICC_EXIT_STRATEGY_GUIDE.md:
        - Exit = Opposite ICC sequence or hard invalidation.
        - Sequence: Indication (Watch) -> Correction (Armed) -> Continuation (Confirmed).
        - Noise Immunity: Logic relies on detect_continuation which requires candle CLOSE beyond structure.
        """
        pos_dir = str(open_position.get("direction", "")).lower()
        if pos_dir not in {"long", "short"}:
            return None

        # [ANTIGRAVITY DEBUG]
        # logger.info(f"[ICC-EXIT-DEBUG] Checking exit for {snapshot.symbol} {pos_dir}")

        # Exit Direction is opposite of Position
        exit_dir = "short" if pos_dir == "long" else "long"
        
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        
        # Detect Reverse Signals (Opposite ICC)
        indication = detect_indication(ltf_candles, swing_lookback=1)
        # Filter for exit direction
        if indication and indication.direction != exit_dir:
            indication = None
        correction = detect_correction(ltf_candles, indication, swing_lookback=1)
        sweep = detect_liquidity_sweep(ltf_candles, exit_dir, swing_lookback=1)

        # Enforce ICC exit sequencing: Indication -> Correction -> Continuation
        continuation = None
        if indication and correction:
            continuation = detect_continuation(
                ltf_candles,
                exit_dir,
                sweep=sweep,
                indication=indication,
                correction=correction,
                require_sweep=False,
                require_indication=True,
                require_correction=True,
                swing_lookback=2,
                confirmation_bars=2,
            )
        
        # Determine Exit State
        exit_state = "IN_TRADE"
        if continuation:
            exit_state = "EXIT_CONFIRMED" # Continuation against us
        elif correction:
            exit_state = "EXIT_ARMED" # Correction/Sweep against us
        elif indication:
            exit_state = "EXIT_WATCH" # Indication against us
            
        if exit_state != "IN_TRADE":
             logger.info(f"[ICC-EXIT] {snapshot.symbol} State={exit_state} (pos={pos_dir}, exit_check={exit_dir})")

        # HOLD RULE: If HTF align matches POSITION, suppress exit unless Continuation is confirmed
        # (i.e. Ignore Indication/Correction noise if HTF supports the trade)
        htf_dir = snapshot.trend_htf.direction
        htf_supports_pos = (htf_dir == TrendDirection.LONG and pos_dir == "long") or \
                           (htf_dir == TrendDirection.SHORT and pos_dir == "short")
                           
        if exit_state == "EXIT_CONFIRMED":
             # CONFIRMED: We exit regardless of HTF (Structure Broken)
             decision = close_position_decision(
                 snapshot.symbol, 
                 snapshot.timeframe,
                 f"ICC Exit: Opposite Continuation confirmed ({exit_dir}).",
                 emergency_exit=True # Treat as structural break
             )
             return decision.copy(update={"gates": gates, "decision_reason_codes": ["ICC_EXIT_CONTINUATION"]})
             
        elif exit_state == "EXIT_ARMED":
             if htf_supports_pos:
                 logger.info(f"[ICC-EXIT] Holding through Correction (HTF aligned). State={exit_state}")
                 return None # HOLD
             else:
                 # If HTF is against us (or neutral), and we have Correction... do we exit?
                 # Guide says: "Exit = Opposite ICC sequence". Usually sequence ends at Continuation.
                 # "Correction (Exit Armed)... waiting confirmation."
                 # So we WAIT for continuation.
                 logger.info(f"[ICC-EXIT] Armed for exit, awaiting confirmation. State={exit_state}")
                 return None

        elif exit_state == "EXIT_WATCH":
             logger.info(f"[ICC-EXIT] Watching structure (Indication). State={exit_state}")
             return None
             
        return None

    def _check_invalidation_gate(
        self,
        snapshot: MarketSnapshot,
        open_position: dict | None,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check HTF structure invalidation for open positions.

        Returns an emergency exit decision if HTF structure is broken, None otherwise.
        """
        if not open_position or abs(open_position.get("size", 0.0)) <= 0:
            return None
        
        # [ANTIGRAVITY DEBUG] Log what we are checking
        logger.info(f"[INVALIDATION-CHECK] {snapshot.symbol} checking pos: {open_position}")

        # [ANTIGRAVITY FIX] ICC Exit Strategy (Structure Driven)
        # Replaces Timer/Sticky exits with Indication -> Correction -> Continuation sequence.
        icc_patience_decision = self._check_icc_exit_signal(snapshot, open_position, gates)
        
        # If the ICC Signal returns a decision (EXIT_CONFIRMED), return it.
        # If it returns None (HOLD), we check other hard limits below.
        if icc_patience_decision:
             return icc_patience_decision

        position_direction = str(open_position.get("direction", "")).lower()
        htf_trend = snapshot.trend_htf
        ltf_trend = snapshot.trend_ltf

        # Optional partial exit: continuation extension + favorable sweep
        if position_direction in {"long", "short"}:
            ltf_candles = snapshot.ltf_candles or snapshot.candles
            ind_favor = detect_indication(ltf_candles, swing_lookback=1)
            if ind_favor and ind_favor.direction != position_direction:
                ind_favor = None
            corr_favor = detect_correction(ltf_candles, ind_favor, swing_lookback=1)
            sweep_favor = detect_liquidity_sweep(ltf_candles, position_direction, swing_lookback=1)

            continuation_favor = None
            if ind_favor and corr_favor and sweep_favor:
                continuation_favor = detect_continuation(
                    ltf_candles,
                    position_direction,
                    sweep=sweep_favor,
                    indication=ind_favor,
                    correction=corr_favor,
                    require_sweep=True,
                    require_indication=True,
                    require_correction=True,
                    swing_lookback=2,
                    confirmation_bars=2,
                )

            if continuation_favor and sweep_favor:
                now = datetime.now(timezone.utc)
                last_scale = self._last_scale_out_time.get(snapshot.symbol)
                if last_scale is None or (now - last_scale) >= timedelta(minutes=30):
                    self._last_scale_out_time[snapshot.symbol] = now
                    decision = scale_out_decision(
                        snapshot.symbol,
                        snapshot.timeframe,
                        "ICC scale-out: continuation extension + favorable sweep.",
                    )
                    return decision.copy(update={"gates": gates, "decision_reason_codes": ["ICC_SCALE_OUT"]})

        # NEW: HTF flip exit - exit if HTF trend flips to opposite direction
        if position_direction == "long" and htf_trend.direction == TrendDirection.SHORT:
            decision = close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "HTF invalidation: HTF flipped SHORT while holding LONG",
                emergency_exit=True,
            )
            logger.warning(
                f"[EXIT] HTF flip detected: position=LONG, HTF={htf_trend.direction}, exiting immediately"
            )
            return decision.copy(update={"gates": gates, "decision_reason_codes": ["HTF_FLIP_EXIT_LONG_TO_SHORT"]})

        elif position_direction == "short" and htf_trend.direction == TrendDirection.LONG:
            decision = close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "HTF invalidation: HTF flipped LONG while holding SHORT",
                emergency_exit=True,
            )
            logger.warning(
                f"[EXIT] HTF flip detected: position=SHORT, HTF={htf_trend.direction}, exiting immediately"
            )
            return decision.copy(update={"gates": gates, "decision_reason_codes": ["HTF_FLIP_EXIT_SHORT_TO_LONG"]})

        # NEW: HTF neutral too long - track neutral bars in position metadata
        # [ANTIGRAVITY FIX] Disabled per user request (premature exits).
        # We want to hold until Stop Loss or Take Profit/Swing invalidation.
        # htf_neutral_exit_bars = int(getattr(self.profile, "htf_neutral_exit_bars", 48))
        # if htf_trend.direction == TrendDirection.NEUTRAL and htf_neutral_exit_bars > 0:
        #     neutral_bars = open_position.get("htf_neutral_bars", 0) + 1
        #     # Note: neutral_bars counter should be incremented by the backtester/runtime
        #     # We'll use the metadata if available, otherwise assume 1
        #     if neutral_bars > htf_neutral_exit_bars:
        #         decision = close_position_decision(
        #             snapshot.symbol,
        #             snapshot.timeframe,
        #             f"HTF neutral for {neutral_bars} bars (> {htf_neutral_exit_bars} bars / 4 hours), exiting position",
        #             emergency_exit=False,
        #         )
        #         logger.info(
        #             f"[EXIT] HTF neutral timeout: {neutral_bars} bars > {htf_neutral_exit_bars} bars, exiting"
        #         )
        #         return decision.copy(update={"gates": gates, "decision_reason_codes": ["HTF_NEUTRAL_TIMEOUT"]})

        # [ANTIGRAVITY FEATURE] Take Profit Check
        take_profit = float(open_position.get("take_profit", 0.0) or 0.0)
        current_price = getattr(snapshot.candles[-1], "close", 0.0) if snapshot.candles else 0.0
        
        if take_profit > 0 and current_price > 0:
            if position_direction == "long" and current_price >= take_profit:
                decision = close_position_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    f"Take Profit hit: Price {current_price:.2f} >= Target {take_profit:.2f}",
                    emergency_exit=False,
                )
                logger.info(f"[EXIT] Take Profit hit for {snapshot.symbol}: {current_price:.2f} >= {take_profit:.2f}")
                return decision.copy(update={"gates": gates, "decision_reason_codes": ["TAKE_PROFIT_HIT"]})
            elif position_direction == "short" and current_price <= take_profit:
                decision = close_position_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    f"Take Profit hit: Price {current_price:.2f} <= Target {take_profit:.2f}",
                    emergency_exit=False,
                )
                logger.info(f"[EXIT] Take Profit hit for {snapshot.symbol}: {current_price:.2f} <= {take_profit:.2f}")
                return decision.copy(update={"gates": gates, "decision_reason_codes": ["TAKE_PROFIT_HIT"]})

        # Original structure invalidation check
        htf_candles = snapshot.htf_candles or snapshot.candles
        inv = detect_structure_invalidation(htf_candles, position_direction)
        if inv is not None:
            decision = close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                f"ICC invalidation: {inv.describe()}",
                emergency_exit=True,
            )
            logger.warning(f"[EXIT] Structure invalidation: {inv.describe()}")
            return decision.copy(update={"gates": gates, "decision_reason_codes": ["HTF_INVALIDATION_EMERGENCY_EXIT"]})

        return None

    def _check_commitment_mode(
        self,
        snapshot: MarketSnapshot,
        open_position: dict | None,
        phase: str,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check commitment mode - hold position unless invalidation triggers.

        Returns a hold decision if commitment mode is active, None otherwise.

        NOTE: Pyramiding is checked BEFORE this method, so if we reach here,
        we've already decided not to pyramid and should just hold.
        """
        if open_position and abs(open_position.get("size", 0.0)) > 0:
            if os.getenv("COMMITMENT_MODE", "true").lower() == "true":
                side = str(open_position.get("direction", "neutral")).lower()
                bias = "long" if side == "long" else "short" if side == "short" else "neutral"
                decision = hold_decision(
                    snapshot.symbol,
                    snapshot.timeframe,
                    bias=bias,
                    phase=phase,
                    reason="Commitment mode: holding position; rely on existing protection unless HTF invalidation triggers.",
                )
                return decision.copy(update={"gates": gates, "decision_reason_codes": ["COMMITMENT_MODE_HOLD"]})
        return None

    def _check_pyramid_entry(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        sweep,
        continuation,
        phase: str,
        htf_align: bool,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check if we can add to an existing position (pyramiding).

        Returns an add_to_position decision if conditions are met, None otherwise.
        """
        position_direction = str(open_position.get("direction", "")).lower()
        if position_direction not in {"long", "short"}:
            return None

        # [ANTIGRAVITY FIX] Safely cast entry_price to float, handling None explicitly
        entry_price = float(open_position.get("entry_price") or 0.0)
        current_price = snapshot.candles[-1].close if snapshot.candles else 0.0

        if entry_price <= 0 or current_price <= 0:
            return None

        # Check if position is profitable
        if position_direction == "long":
            is_profitable = current_price > entry_price
            htf_trend_direction = TrendDirection.LONG
            ltf_trend_direction = TrendDirection.LONG
        else:  # short
            is_profitable = current_price < entry_price
            htf_trend_direction = TrendDirection.SHORT
            ltf_trend_direction = TrendDirection.SHORT

        if not is_profitable:
            logger.debug(
                f"[PYRAMID] Position not profitable: entry={entry_price:.4f}, current={current_price:.4f}, "
                f"direction={position_direction}"
            )
            return None

        # Check HTF/LTF alignment in same direction as position
        htf_dir = snapshot.trend_htf.direction
        ltf_dir = snapshot.trend_ltf.direction

        direction_matches = (
            (position_direction == "long" and htf_dir in {TrendDirection.LONG, TrendDirection.NEUTRAL} and ltf_dir == TrendDirection.LONG)
            or (position_direction == "short" and htf_dir in {TrendDirection.SHORT, TrendDirection.NEUTRAL} and ltf_dir == TrendDirection.SHORT)
        )

        # [ANTIGRAVITY FIX] Removed trend alignment check for aggressive pyramiding
        # if not direction_matches:
        #    logger.debug(
        #        f"[PYRAMID] Trend mismatch: position={position_direction}, HTF={htf_dir}, LTF={ltf_dir}"
        #    )
        #    return None
        pass

        # [ANTIGRAVITY "FEET WET" PYRAMIDING - PROFIT ONLY]
        # Logic: If profitable, add to position aggressively (User Request)
        
        can_pyramid = True
        pyramid_reason = "Aggressive Scale-In: Position is Profitable"
        
        # Ensure we have decent profit (e.g. > 0.2%) to avoid adding on noise
        # User asked for "profitable", but let's be sane:
        min_profit_buffer = 1.002 if position_direction == "long" else 0.998
        
        if position_direction == "long":
            if current_price < entry_price * 1.002:
                 can_pyramid = False
                 pyramid_reason = "Profit too small (< 0.2%)"
        else:
            if current_price > entry_price * 0.998:
                 can_pyramid = False
                 pyramid_reason = "Profit too small (< 0.2%)"

        if not can_pyramid:
             # logger.debug(f"[PYRAMID] Skipping: {pyramid_reason}")
             return None

        # [SAFETY CHECK] Max Pyramid Entries
        max_pyramid_entries = int(getattr(self.profile, "max_pyramid_entries", 3))
        current_pyramid_count = int(open_position.get("pyramid_count", 0))

        if current_pyramid_count >= max_pyramid_entries:
            # logger.debug(f"[PYRAMID] Max count reached: {current_pyramid_count}/{max_pyramid_entries}")
            return None

        # Build Decision
        # [HYBRID FLIP] Dynamic Risk Sizing
        # Load (Add #1): 30% Risk to build the position
        # Scale (Add #2+): 10% Risk to compound
        risk_load = float(getattr(self.profile, "pyramid_risk_load", 0.30))
        risk_scale = float(getattr(self.profile, "pyramid_risk_scale", 0.10))
        
        current_count = int(open_position.get("pyramid_count", 0))
        risk_pct = risk_load if current_count == 0 else risk_scale
        
        # Stop Loss for the Add?
        # [ANTIGRAVITY RULE] Pyramid Breakeven
        # If this is a pyramid entry (add > 0), the aggregate stop cannot be worse than avg price.
        # We must protect the "house money".
        avg_price = float(open_position.get("avg_price", current_price))
        # [ANTIGRAVITY FIX] Get initial entry price (approximated if not tracked, but we should track it)
        #Ideally engine tracks initial_entry_price. For now, avg_price is close enough if count=0, 
        # but if count>0 we need the floor.
        # Fallback: We'll use the current logic but add the buffer to the "Soft BE" concept.
        
        # NOTE: Live engine might not have 'initial_entry_price' stored in open_position dict yet.
        # We will assume Avg Price of the PREVIOUS state was the entry? No.
        # We will use a calculated floor based on current pricing.
        
        if position_direction == "long":
             # Stop is structure low, OR Breakeven, whichever is higher (safer)
             structure_stop = current_price * 0.995 
             
             # [USER REQUEST] "Compensate" with 6% risk tolerance on Load.
             # Soft BE with Breathing Room (0.05% buffer below Avg Price) for first add.
             # Since we don't track initial_entry perfectly here without DB schema change,
             # we use Avg Price - Buffer.
             
             buffer = avg_price * 0.0005 # 0.05%
             floored_stop = avg_price - buffer if int(open_position.get("pyramid_count", 0)) == 0 else avg_price
             
             stop_loss = max(structure_stop, floored_stop)
        else:
             # Stop is structure high, OR Breakeven, whichever is lower (safer)
             structure_stop = current_price * 1.005
             
             buffer = avg_price * 0.0005
             ceiled_stop = avg_price + buffer if int(open_position.get("pyramid_count", 0)) == 0 else avg_price
             
             stop_loss = min(structure_stop, ceiled_stop)
             
        take_profit = None 
        
        logger.info(f"[PYRAMID] Triggering Profit-Only Scale-In: {pyramid_reason}. Adding {risk_pct*100}% Risk.")
        
        decision = AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=position_direction,
            phase=phase,
            action="add_to_position",
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=None,
            risk_per_trade_pct=risk_pct,
            urgency="medium",
            structure_summary=pyramid_reason,
            management_instructions="Manage aggregate position stops.",
            notes=f"Pyramid Entry: {pyramid_reason}",
            invalidation_conditions=f"Stop Loss set to {stop_loss}"
        )
        return decision.copy(update={"gates": gates})

        # Use pyramid-specific threshold (higher than initial entry)
        pyramid_threshold = float(getattr(self.profile, "pyramid_score_threshold", 70.0))
        pyramid_min_threshold = float(getattr(self.profile, "pyramid_min_score_threshold", pyramid_threshold))

        if pyramid_score < pyramid_threshold:
            if continuation is None or pyramid_score < pyramid_min_threshold:
                logger.info(
                    f"[PYRAMID] Score below threshold: {pyramid_score:.1f}/{pyramid_threshold:.1f}, "
                    f"breakdown={breakdown}"
                )
                return None
            logger.info(
                f"[PYRAMID] Using min threshold: {pyramid_score:.1f}/{pyramid_min_threshold:.1f} "
                f"(below {pyramid_threshold:.1f}); breakdown={breakdown}"
            )

        # Calculate stop and target for pyramid entry
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        structure_levels = last_structure_range(ltf_candles, swing_lookback=1)
        stop_price = None
        if structure_levels:
            last_high, last_low = structure_levels
            stop_price = last_low if position_direction == "long" else last_high

        if stop_price is None:
            stop_price = float(getattr(sweep, "swept_price", 0.0)) if sweep is not None else None

        if stop_price is None and ltf_candles:
            last_candle = ltf_candles[-1]
            if position_direction == "long":
                stop_price = min(float(last_candle.low), current_price * 0.995)
            else:
                stop_price = max(float(last_candle.high), current_price * 1.005)

        # Calculate target
        htf_candles = snapshot.htf_candles or snapshot.candles
        target_price = next_structure_target(
            htf_candles,
            position_direction,
            entry_price=current_price,
            swing_lookback=1,
        )

        if target_price is None:
            risk = abs(current_price - stop_price) if stop_price else current_price * 0.01
            target_price = (
                current_price + (risk * 2.5)
                if position_direction == "long"
                else current_price - (risk * 2.5)
            )

        # Validate stop_price and target_price before using them
        if stop_price is None or stop_price <= 0:
            logger.warning(
                f"[PYRAMID] Invalid stop_price={stop_price} for {position_direction}, cannot pyramid"
            )
            return None
        if target_price is None or target_price <= 0:
            logger.warning(
                f"[PYRAMID] Invalid target_price={target_price} for {position_direction}, cannot pyramid"
            )
            return None

        logger.info(
            f"[PYRAMID] Entry #{current_pyramid_count + 1}: score={pyramid_score:.1f}/{pyramid_threshold:.1f}, "
            f"sweep={sweep is not None}, continuation={continuation is not None}, "
            f"entry={current_price:.4f}, stop={stop_price:.4f}, target={target_price:.4f}"
        )

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=position_direction,
            phase=phase,
            action="add_to_position",
            entry_price=current_price,
            entry_zone=None,
            stop_loss=stop_price,
            take_profit=target_price,
            risk_per_trade_pct=None,
            max_position_size_pct=None,
            time_in_force_sec=None,
            urgency="medium",
            structure_summary=f"Pyramid entry #{current_pyramid_count + 1}: score={pyramid_score:.1f}, sweep={sweep is not None}, continuation={continuation is not None}",
            invalidation_conditions="Stop below/above correction low/high.",
            management_instructions="Manage per ICC continuation rules.",
            notes=f"Pyramid entry #{current_pyramid_count + 1}: score={pyramid_score:.1f}, sweep={sweep is not None}, continuation={continuation is not None}",
            gates=gates,
        )

    def _check_no_trade_zone(
        self,
        snapshot: MarketSnapshot,
        indication,
        sweep,
        continuation,
        phase: str,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check if price is in ICC no-trade zone (between swing high/low with no indication).

        Returns a stand_aside decision if in no-trade zone, None otherwise.

        IMPORTANT: Skip this check if we have sweep+continuation, as that indicates
        a valid breakout from the consolidation zone.
        """
        # Allow trade if we have sweep AND continuation (valid breakout from consolidation)
        if sweep is not None and continuation is not None:
            return None

        require_sweep = bool(getattr(self.profile, "icc_auto_entry_require_sweep", True))
        if not require_sweep and continuation is not None:
            return None

        trend_htf = snapshot.trend_htf
        if trend_htf and trend_htf.strength >= 0.5:
            return None

        trend_ltf = snapshot.trend_ltf
        if trend_ltf and trend_ltf.direction in ("long", "short") and trend_ltf.strength >= 0.4:
            return None

        htf_candles = snapshot.htf_candles or snapshot.candles
        struct_range = last_structure_range(htf_candles, swing_lookback=1)
        if indication is None and struct_range:
            last_high, last_low = struct_range
            if htf_candles:
                last_close = htf_candles[-1].close
                if last_low < last_close < last_high:
                    reason = "ICC no-trade zone: between swing high/low; waiting for indication."
                    decision = stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)
                    codes = ["ICC_GATE_BLOCK", "NO_INDICATION"]
                    return decision.copy(update={"phase": phase, "gates": gates, "decision_reason_codes": codes})
        return None

    def _check_session_health_gate(
        self,
        snapshot: MarketSnapshot,
        sweep,
        continuation,
        stack_label: str,
        session_ok: bool,
        session_reason: str,
        phase: str,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check session health for A+ setups.

        Returns a stand_aside decision if A+ setup lacks session health, None otherwise.
        """
        if sweep and continuation and stack_label == "A+" and not session_ok:
            decision = stand_aside_decision(
                snapshot.symbol,
                snapshot.timeframe,
                f"ICC gate: A+ session health weak ({session_reason}).",
            )
            codes = ["ICC_GATE_BLOCK", "SESSION_HEALTH_WEAK"]
            return decision.copy(update={"phase": phase, "gates": gates, "decision_reason_codes": codes})
        return None

    def _score_icc_entry(
        self,
        *,
        snapshot: MarketSnapshot,
        sweep,
        continuation,
        indication=None,
        phase: str,
        htf_align: bool,
    ) -> tuple[float, dict[str, float], float]:
        score_threshold = float(getattr(self.profile, "icc_entry_score_threshold", 60.0))
        align_points = float(getattr(self.profile, "icc_score_htf_ltf_align_points", 30.0))
        sweep_points = float(getattr(self.profile, "icc_score_sweep_points", 25.0))
        continuation_points = float(getattr(self.profile, "icc_score_continuation_points", 25.0))
        indication_points = float(getattr(self.profile, "icc_score_indication_points", 0.0))
        strong_htf_points = float(getattr(self.profile, "icc_score_strong_htf_points", 15.0))
        phase_points = float(getattr(self.profile, "icc_score_phase_points", 5.0))
        strong_htf_threshold = float(
            getattr(self.profile, "icc_score_htf_strength_threshold", 0.7)
        )

        if indication is None and indication_points > 0.0:
            indication = self._detect_indication(snapshot)

        strong_htf = float(snapshot.trend_htf.strength or 0.0) >= strong_htf_threshold
        good_phase = phase != "chop"
        breakdown = {
            "htf_ltf_align": align_points if htf_align else 0.0,
            "liquidity_sweep": sweep_points if sweep is not None else 0.0,
            "continuation": continuation_points if continuation is not None else 0.0,
            "strong_htf_trend": strong_htf_points if strong_htf else 0.0,
            "good_phase": phase_points if good_phase else 0.0,
        }
        if indication_points > 0.0:
            breakdown["indication"] = indication_points if indication else 0.0
        score = sum(breakdown.values())

        # [ANTIGRAVITY ATTACHMENT] Tiebreaker Nudge
        # If score is very close (e.g. 55/60) and we have strong HTF backing, tip the scale.
        if score >= (score_threshold - 5.0) and score < score_threshold:
            if breakdown.get("strong_htf_trend", 0.0) > 0:
                 score += 5.0
                 breakdown["tiebreaker_nudge"] = 5.0
        
        return score, breakdown, score_threshold

    def _check_icc_entry_score(
        self,
        snapshot: MarketSnapshot,
        sweep,
        continuation,
        indication,
        htf_align: bool,
        phase: str,
        score: float,
        score_breakdown: dict[str, float],
        score_threshold: float,
        gates: dict,
    ) -> AITradeDecision | None:
        """Check points-based ICC score for new entries."""
        two_signal_override = bool(getattr(self.profile, "icc_two_signal_override_enabled", False))
        if two_signal_override and sweep is not None and (continuation is not None or indication):
            return None

        if score >= score_threshold:
            return None

        missing = [name.replace("_", " ") for name, points in score_breakdown.items() if points <= 0]
        missing_str = ", ".join(missing) if missing else "insufficient confluence"
        reason = f"ICC score {score:.1f}/{score_threshold:.1f} below threshold; missing: {missing_str}."
        decision = stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)
        codes: list[str] = ["ICC_SCORE_BELOW_THRESHOLD"]
        if not htf_align:
            codes.append("HTF_LTF_MISALIGNED")
        if sweep is None:
            codes.append("NO_SWEEP")
        if continuation is None:
            codes.append("NO_CONTINUATION")
        indication_points = float(getattr(self.profile, "icc_score_indication_points", 0.0))
        if indication_points > 0.0 and not indication:
            codes.append("NO_INDICATION")
        if phase == "chop":
            codes.append("CHOP_PHASE")
        return decision.copy(update={"phase": phase, "gates": gates, "decision_reason_codes": codes})

    def _asset_class(self, symbol: str) -> AssetClass | None:
        meta = SYMBOL_METADATA.get(symbol.upper())
        if meta:
            return meta.asset_class
        if is_crypto(symbol):
            return AssetClass.CRYPTO
        return None

    def _session_health(self, snapshot: MarketSnapshot) -> Tuple[bool, str]:
        candles = snapshot.ltf_candles or snapshot.candles
        if not getattr(self.profile, "session_gate_enabled", True):
            return True, "session gate disabled"
        min_candles = int(getattr(self.profile, "session_gate_min_candles", 30))
        if not candles or len(candles) < min_candles:
            return True, "insufficient candles for session gate"
        recent = candles[-5:]
        prior = candles[-25:-5]
        avg_range_recent = statistics.mean(max(0.0, c.high - c.low) for c in recent)
        avg_range_prior = statistics.mean(max(0.0, c.high - c.low) for c in prior)
        avg_vol_recent = statistics.mean(max(0.0, c.volume) for c in recent)
        avg_vol_prior = statistics.mean(max(0.0, c.volume) for c in prior)
        range_mult = float(getattr(self.profile, "session_range_multiplier", DEFAULT_SESSION_RANGE_MULTIPLIER))
        vol_mult = float(getattr(self.profile, "session_volume_multiplier", DEFAULT_SESSION_VOLUME_MULTIPLIER))
        range_ok = avg_range_prior > 0 and avg_range_recent >= avg_range_prior * range_mult
        vol_ok = avg_vol_prior > 0 and avg_vol_recent >= avg_vol_prior * vol_mult
        if not (range_ok and vol_ok):
            return False, "range/volume below expansion threshold"
        asset = self._asset_class(snapshot.symbol)
        if asset in {AssetClass.FOREX, AssetClass.CRYPTO}:
            last_ts = candles[-1].timestamp
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            tz_name = getattr(self.profile, "session_overlap_timezone", "UTC") or "UTC"
            try:
                local_ts = last_ts.astimezone(ZoneInfo(tz_name))
            except Exception:
                local_ts = last_ts
                tz_name = "UTC"
            start_hour = int(getattr(self.profile, "session_overlap_start_hour", DEFAULT_SESSION_OVERLAP_START_HOUR))
            end_hour = int(getattr(self.profile, "session_overlap_end_hour", DEFAULT_SESSION_OVERLAP_END_HOUR))
            hour = local_ts.hour
            if not (start_hour <= hour < end_hour):
                return False, f"outside session bias window ({tz_name} {start_hour:02d}-{end_hour:02d})"
        return True, "session healthy"

    def _confluence_stack_score(self, snapshot: MarketSnapshot, sweep, continuation) -> Tuple[float, str]:
        trend_score = (snapshot.trend_htf.strength + snapshot.trend_ltf.strength) / 2
        sweep_score = 0.0
        if sweep is not None and getattr(sweep, "level", None):
            level = float(sweep.level)
            swept = float(getattr(sweep, "swept_price", level))
            sweep_score = min(1.0, abs(swept - level) / max(1e-9, level) * 5)
        bos_score = 0.0
        last_close = snapshot.candles[-1].close if snapshot.candles else None
        if continuation is not None and last_close is not None:
            trigger = float(getattr(continuation, "trigger_level", last_close))
            bos_score = min(1.0, abs(last_close - trigger) / max(1e-9, trigger) * 5)
        score = 0.5 * trend_score + 0.25 * sweep_score + 0.25 * bos_score
        if score >= 0.85:
            label = "A+"
        elif score >= 0.7:
            label = "A"
        else:
            label = "B"
        return min(1.0, score), label
