from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.confluence.context import build_confluence
from tradebot_sci.broker.trade_result_store import TradeResultStore

logger = logging.getLogger(__name__)

class StrategyEngine:
    """
    Lean Strategy Orchestrator.
    Acts as the 'hands and eyes' for Strategy Variants.
    Zero internal filters. 100% Signal Fidelity.
    """

    # [SAFETY] Global Account Guardians
    MAX_CAPITAL_SEEN = 0.0
    PAUSE_UNTIL = None

    def __init__(
        self,
        ai_client: TradeSciAIClient | None,
        market_provider: MarketDataProvider,
        profile: BaseProfile,
        symbol: str,
        trade_results: Optional[TradeResultStore] = None,
    ):
        self.ai_client = ai_client
        self.market_provider = market_provider
        self.profile = profile
        self.symbol = symbol
        self.trade_results = trade_results
        
        # Load the Strategy Variant
        self._strategy = self._load_strategy_variant()
        logger.info(f" [PHOENIX] === ENGINE LOADED === Symbol: {symbol} | Variant: {self._strategy.name.upper()} ")

    def _load_strategy_variant(self):
        """Factory method for loading strategy variants."""
        # Note: We maintain compatibility with the legacy loading logic
        from tradebot_sci.config.models import UserConfig
        
        if hasattr(self.profile, "get_strategy_for_symbol"):
            variant = self.profile.get_strategy_for_symbol(self.symbol).lower()
        else:
            variant = getattr(UserConfig, "STRATEGY_VARIANT", "evolution").lower()
        
        # Standard variant mapping
        if variant == "evolution":
            from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
            return RobotEvolutionStrategy()
        elif variant == "robocop":
            # [RENT GOAL] Standardized to Supply/Demand for maximum aggression
            from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
            return SupplyDemandStrategy()
        elif variant == "london_breakout":
            from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
            return LondonBreakoutStrategy()
        elif variant == "rubberband_reaper":
            from tradebot_sci.strategy.variants.rubberband_reaper import RubberbandReaperStrategy
            return RubberbandReaperStrategy()
        elif variant == "volatility_breakout":
            from tradebot_sci.strategy.variants.breakout import VolatilityBreakoutStrategy
            return VolatilityBreakoutStrategy()
        elif variant == "icc_core":
            from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy
            return ICCCoreStrategy()
        elif variant == "supply_demand":
            from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
            return SupplyDemandStrategy()
        elif variant == "meta_sci":
            # [ANTIGRAVITY] Updated to use the true Adaptive Meta-SCI Strategy
            from tradebot_sci.strategy.variants.meta_sci import MetaSCIStrategy
            return MetaSCIStrategy(profile_settings=self.profile)
        else:
            # Fallback
            from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
            return RobotEvolutionStrategy()

    def _load_specific_variant(self, variant: str):
        """Dynamic helper for Meta-SCI ensemble loading."""
        v = variant.lower()
        if v == "evolution":
            from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
            return RobotEvolutionStrategy()
        elif v == "supply_demand":
            from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
            return SupplyDemandStrategy()
        elif v == "robocop":
            from tradebot_sci.strategy.variants.robocop import RoboCopStrategy
            return RoboCopStrategy()
        elif v == "london_breakout":
            from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
            return LondonBreakoutStrategy()
        elif v == "rubberband_reaper":
            from tradebot_sci.strategy.variants.rubberband_reaper import RubberbandReaperStrategy
            return RubberbandReaperStrategy()
        elif v == "volatility_breakout":
            from tradebot_sci.strategy.variants.breakout import VolatilityBreakoutStrategy
            return VolatilityBreakoutStrategy()
        elif v == "icc_core":
            from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy
            return ICCCoreStrategy()
        elif v == "orb_breakout":
            from tradebot_sci.strategy.variants.orb_breakout import ORBStrategy
            return ORBStrategy()
        return None

    def score_icc_grade(self, snapshot: MarketSnapshot) -> tuple[float, str]:
        """Provides a score and grade for the current market state."""
        from tradebot_sci.strategy.scoring import ActionScorer
        from tradebot_sci.strategy.icc_signals import (
            detect_liquidity_sweep,
            detect_continuation,
            detect_indication,
            detect_correction,
        )
        
        # 1. Gather Structure Signals
        trend_htf = snapshot.trend_htf.direction
        trend_ltf = snapshot.trend_ltf.direction
        
        # [ANTIGRAVITY] Fallback: If LTF is neutral, use HTF as the baseline direction for signals.
        # This prevents "barriers" during local chop if the macro trend is strong.
        signal_dir = trend_ltf if trend_ltf != "neutral" else trend_htf
        
        sweep = detect_liquidity_sweep(snapshot.candles, signal_dir)
        indication = detect_indication(snapshot.candles)
        correction = detect_correction(snapshot.candles, indication)
        continuation = detect_continuation(snapshot.candles, signal_dir, sweep, indication, correction)
        
        # 2. Delegate to Scorer
        # Note: session_ok is True for this real-time check
        score, grade = ActionScorer.score_icc_grade(
            snapshot, 
            sweep=bool(sweep), 
            continuation=bool(continuation), 
            indication=bool(indication), 
            correction=bool(correction), 
            session_ok=True
        )
        return score, grade

    def decide(
        self,
        timeframe: str,
        open_position: dict | None = None,
        snapshot: MarketSnapshot | None = None,
        execution_capabilities: dict | None = None,
        current_bar_time: datetime | None = None,
        current_capital: float | None = None,
    ) -> AITradeDecision:
        """
        The Main Entry Point.
        Ask the strategy for a decision and return it with minimal validation.
        """
        # 0. WEALTH SYNC & POSITION REGISTRATION (Always Run)
        from tradebot_sci.strategy.safety_guard import SafetyGuard
        from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
        
        current_capital_val = current_capital if current_capital is not None else 0.0
        latest_snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        
        if self.trade_results:
            stats = self.trade_results.get_stats()
            if stats.get('total_trades', 0) >= 5:
                 ac = classify_symbol(self.symbol)
                 SafetyGuard.set_win_rate(stats.get('win_rate', 0.55), asset_class=ac)

        # Register current position status for wealth mode / financed risk logic
        # This must happen before any decisions are made.
        SafetyGuard.update_position(self.symbol, open_position)

        # 1. Gather Context
        snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        caps = execution_capabilities or {}
        
        # 2. Build Gates (Metadata for Strategy)
        current_capital = current_capital if current_capital is not None else getattr(self.market_provider, "current_capital", None)
        history = [r.to_dict() for r in (self.trade_results.results if self.trade_results else [])]
        
        # Calculate grade for the current snapshot
        score, grade = self.score_icc_grade(snapshot)
        
        gates = {
            "htf_dir": snapshot.trend_htf.direction,
            "ltf_dir": snapshot.trend_ltf.direction,
            "htf_strength": round(float(snapshot.trend_htf.strength or 0.0), 3),
            "ltf_strength": round(float(snapshot.trend_ltf.strength or 0.0), 3),
            "score": score,
            "grade": grade
        }

        # [META-SCI] Auto-Strategy handled by MetaSCIStrategy class transparently below.
        
        # 3. Request Decisions from Strategy (Standard Path or Adopted Meta Path)
        # A. Check for EXIT if we have a position
        if open_position and isinstance(open_position, dict) and abs(open_position.get("size", 0.0)) > 0:
            exit_decision = self._strategy.check_exit_signal(
                snapshot, 
                open_position, 
                gates, 
                current_capital=current_capital, 
                trade_history=history
            )
            if exit_decision:
                exit_decision.score = score
                exit_decision.grade = grade
                logger.info(f"[PHOENIX] {self.symbol} Strategy EXIT triggered: {exit_decision.summary()}")
                return exit_decision
            
            # [SAFETY GUARD] Augment with Safety Exits (ATR Armor, Trailing) if Strategy is silent
            safety_exit = SafetyGuard.augment_exit_decision(None, open_position, snapshot)
            
            # [WEALTH MODE] Check for "The Runner" partial exit
            if safety_exit or exit_decision:
                decision_to_check = exit_decision or safety_exit
                performance_exit = SafetyGuard.handle_runner_exit(decision_to_check, open_position)
                if performance_exit:
                    performance_exit.score = score
                    performance_exit.grade = grade
                    return performance_exit
            
            if safety_exit:
                 safety_exit.score = score
                 safety_exit.grade = grade
                 return safety_exit

            # [POSITION LOCK] If we have an open position and NO exit was triggered above,
            # HOLD. Do NOT fall through to entry checks. This prevents the Meta-SCI
            # tournament from flip-flopping between strategies (rubberband says long,
            # volatility says short, etc.) and bleeding capital via constant reversals.
            # The position lives or dies by its own SL/TP/exit logic.
            from tradebot_sci.strategy.decisions import stand_aside_decision
            hold = stand_aside_decision(self.symbol, timeframe, "[POSITION LOCK] Holding — position managed by SL/TP")
            hold.action = "hold"
            hold.score = score
            hold.grade = grade
            return hold

        # 4. ACCOUNT SAFETY GUARDS (Centralized Entry Veto)
        # [CONSOLIDATED] Run all pre-entry checks (Breaker, Lockout, Greed, Churn, Veto, Streak, Sentry)
        # We run this AFTER exit checks so that TP/SL logic (SafetyGuard.augment_exit_decision)
        # takes priority over account-level blocks like Leverage Sentry.
        # [ANTIGRAVITY FIX] Use Total Equity (Cash + Unrealized PnL) for Leverage calculation.
        # Otherwise, if we are fully invested with $0 cash, leverage spikes to infinity.
        total_equity = current_capital_val + caps.get("total_unrealized_pnl", 0.0)
        
        safety_decision = SafetyGuard.check_entry_safety(
            self.symbol, 
            timeframe, 
            total_equity,
            latest_snapshot,
            ai_client=self.ai_client,
            settings=self.profile,
            trade_results=self.trade_results
        )
        if safety_decision:
            from tradebot_sci.runtime.rejection_journal import rejection_journal
            rejection_journal.log(self.symbol, timeframe, "SafetyGuard", safety_decision.notes or "Entry blocked")
            logger.info(f"[SAFETY] Entry Blocked for {self.symbol}: {safety_decision.notes}")
            return safety_decision

        # B. Check for ENTRY / SCALE_IN
        decision = self._strategy.check_entry_signal(
            snapshot, 
            gates, 
            open_position=open_position, 
            current_capital=current_capital, 
            trade_history=history
        )

        if decision:
            decision.score = score
            decision.grade = grade

            # [ANTIGRAVITY] Counter-Trend Entry Block
            # Prevents going long when HTF is bearish, or short when HTF is bullish.
            htf_dir = gates.get("htf_dir", "neutral")
            if getattr(self.profile, "block_counter_trend_entries", True) and decision.action in ("enter_long", "enter_short", "scale_in"):
                # Determine effective direction for scale_in from existing position
                effective_action = decision.action
                if decision.action == "scale_in" and open_position:
                    pos_size = open_position.get("size", 0)
                    effective_action = "enter_long" if pos_size > 0 else "enter_short"
                
                is_counter_trend = (
                    (htf_dir == "bearish" and effective_action == "enter_long")
                    or (htf_dir == "bullish" and effective_action == "enter_short")
                )
                if is_counter_trend:
                    reason = f"Counter-Trend Blocked: {decision.action} vs HTF={htf_dir}"
                    logger.info(f"[TREND_GUARD] {self.symbol} {reason}")
                    from tradebot_sci.strategy.decisions import stand_aside_decision
                    from tradebot_sci.runtime.rejection_journal import rejection_journal
                    rejection_journal.log(self.symbol, timeframe, "TrendGuard", reason)
                    blocked = stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)
                    blocked.score = score
                    blocked.grade = grade
                    return blocked

            # [WEALTH MODE] Augment with Performance Overrides (Sniper, Regime, etc.)
            decision = SafetyGuard.augment_entry_decision(
                decision, 
                score, 
                gates["htf_strength"], 
                snapshot,
                ai_client=self.ai_client,
                settings=self.profile
            )
            
            # [SMART POSITIONS] Financed Risk Check
            # Only allow new entries if we have enough open profit to cover the risk.
            if decision.action in ("enter_long", "enter_short", "scale_in"):
                # [FRIDAY FADE DAMPER] Global Forex Protection
                from tradebot_sci.config.models import UserConfig
                if UserConfig.FRIDAY_FADE_ENABLED:
                    est_now = datetime.now(ZoneInfo("America/New_York"))
                    if est_now.weekday() == 4 and est_now.hour >= 12:
                        if classify_symbol(self.symbol) == AssetClass.FOREX:
                            old_risk = decision.risk_per_trade_pct
                            decision.risk_per_trade_pct = 0.0025
                            decision.notes = (decision.notes or "") + " | [DAMPER] Friday Fade Active (Risk capped at 0.25%)"
                            logger.info(f"[DAMPER] Capping {self.symbol} risk from {old_risk} to 0.0025 due to Friday afternoon liquidity.")

                if UserConfig.SMART_POSITIONS_ENABLED:
                    # [ANTIGRAVITY FIX] Use Global Aggregation across all Brokers (Forex + Crypto)
                    pnl, pos_count = SafetyGuard.get_financed_risk_stats()

                    # If we have no positions open, we allow the first trade to start the cycle
                    if pos_count == 0:
                        return decision
                    
                    # Calculate Risk
                    risk_amt = 0.0
                    if decision.risk_per_trade_dollars:
                        risk_amt = decision.risk_per_trade_dollars
                    elif decision.risk_per_trade_pct and current_capital:
                         risk_amt = current_capital * decision.risk_per_trade_pct
                    
                    # Default fallback if risk not explicit (estimate 1% of capital)
                    if risk_amt == 0.0 and current_capital:
                        risk_amt = current_capital * 0.01

                    if pnl < risk_amt:
                        logger.info(f"[SMART_POSITIONS] Blocked {decision.action} on {self.symbol}. Global PnL (${pnl:.2f}) < New Risk (${risk_amt:.2f})")
                        from tradebot_sci.strategy.decisions import stand_aside_decision
                        from tradebot_sci.runtime.rejection_journal import rejection_journal
                        rejection_journal.log(self.symbol, timeframe, "Smart Positions", f"Financing Required: PnL ${pnl:.2f} < Risk ${risk_amt:.2f}")
                        decision = stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"[SMART] Financing Required: PnL ${pnl:.2f} < Risk ${risk_amt:.2f}")
                        decision.score = score
                        decision.grade = grade
                        return decision

            # [SAFETY GUARD] Notify of Entry (for Churn Burner)
            if decision.action in ("enter_long", "enter_short", "scale_in"):
                 SafetyGuard.notify_entry(self.symbol)

            logger.info(f"[PHOENIX] {self.symbol} Strategy {decision.action.upper()} triggered: {decision.summary()}")
            # 4. Final Safety Patch (Margin/Venue Only)
            return validate_decision(decision, execution_capabilities=caps)

        # 5. Default: Stand Aside
        from tradebot_sci.strategy.decisions import stand_aside_decision
        decision = stand_aside_decision(snapshot.symbol, timeframe, "No strategy signal detected.")
        decision.score = score
        decision.grade = grade
        return decision

    def build_market_context(self, snapshot: MarketSnapshot, **kwargs):
        """Legacy helper for AI compatibility."""
        from tradebot_sci.ai.schemas import MarketContext
        return MarketContext(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            timestamp=snapshot.candles[-1].timestamp if snapshot.candles else None,
            price=snapshot.candles[-1].close if snapshot.candles else 0.0,
            trend_htf=snapshot.trend_htf.direction,
            trend_ltf=snapshot.trend_ltf.direction,
            signals={},
            metadata=kwargs
        )
