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
            # For the base variant, we keep the engine on Meta mode.
            # Initial setup detection will happen in decide()
            from tradebot_sci.strategy.variants.base import BaseStrategy
            return BaseStrategy("meta_sci")
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
        elif v in ("robocop", "supply_demand"):
            from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
            return SupplyDemandStrategy()
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
        
        sweep = detect_liquidity_sweep(snapshot.candles, trend_ltf)
        indication = detect_indication(snapshot.candles)
        correction = detect_correction(snapshot.candles, indication)
        continuation = detect_continuation(snapshot.candles, trend_ltf, sweep, indication, correction)
        
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
        # 0. ACCOUNT SAFETY GUARDS (Centralized)
        from tradebot_sci.strategy.safety_guard import SafetyGuard
        
        # [CONSOLIDATED] Run all pre-entry checks (Breaker, Lockout, Greed, Churn, Veto, Streak, Sentry)
        current_capital_val = current_capital if current_capital is not None else 0.0
        latest_snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        
        # [WEALTH SYNC] Pass latest stats to SafetyGuard
        if self.trade_results:
            stats = self.trade_results.get_stats()
            # If we have enough trades, update win rate for Kelly
            if stats.get('total_trades', 0) >= 5:
                 SafetyGuard.set_win_rate(stats.get('win_rate', 0.55))

        safety_decision = SafetyGuard.check_entry_safety(
            self.symbol, 
            timeframe, 
            current_capital_val,
            latest_snapshot
        )

        # [WEALTH MODE] Register current positions for House Money checks
        if open_position and isinstance(open_position, dict):
            SafetyGuard.set_current_positions([open_position]) 
            # In a real multi-symbol setup, we'd pass ALL positions from the cycle.
            # But for per-engine logic, we pass self.
        
        if safety_decision:
            logger.info(f"[SAFETY] Blocked {self.symbol}: {safety_decision.notes}")
            return safety_decision

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

        # [META-SCI] Auto-Strategy Ensemble Master
        if self._strategy.name == "meta_sci" and not open_position:
            logger.info(f" [META-SCI] Executing Ensemble Pulse for {self.symbol}...")
            
            # 1. Load sub-strategies
            strats_to_run = ["supply_demand", "robocop", "evolution", "london_breakout", "rubberband_reaper", "icc_core"]
            exclude = getattr(self.profile, 'meta_sci_exclude_list', [])
            consensus_needed = getattr(self.profile, 'meta_sci_min_consensus', 1)
            
            signals = []
            for s_name in strats_to_run:
                if s_name in exclude: continue
                # Dynamic load
                try:
                    s_inst = self._load_specific_variant(s_name)
                    sig = s_inst.check_entry_signal(snapshot, gates, open_position=None, current_capital=current_capital, trade_history=history)
                    if sig and sig.action in ("enter_long", "enter_short"):
                        sig.notes = (sig.notes or "") + f" | [META] Sourced via {s_name.upper()}"
                        # Attach the strategy name for dynamic adoption
                        sig.gates = sig.gates or {}
                        sig.gates["meta_source"] = s_name
                        signals.append(sig)
                except Exception as e:
                    logger.error(f"[META-SCI] Sub-strategy {s_name} failed: {e}")

            if signals:
                # Ranking logic: Winner is the highest score
                # Consensus logic: Directional agreement check
                long_sigs = [s for s in signals if s.bias == "long"]
                short_sigs = [s for s in signals if s.bias == "short"]
                
                winner = None
                if len(long_sigs) >= consensus_needed:
                    winner = max(long_sigs, key=lambda x: x.score or 0)
                elif len(short_sigs) >= consensus_needed:
                    winner = max(short_sigs, key=lambda x: x.score or 0)
                
                if winner:
                   logger.info(f" [META-SCI] Winner Selected: {winner.gates.get('meta_source').upper()} with score {winner.score or 'N/A'}")
                   decision = winner
                   # Proceed to safety augmentation below
                else:
                   from tradebot_sci.strategy.decisions import stand_aside_decision
                   return stand_aside_decision(snapshot.symbol, timeframe, f"Meta-SCI Consensus Not Met ({len(signals)} sigs vs {consensus_needed} needed)")
            else:
                from tradebot_sci.strategy.decisions import stand_aside_decision
                return stand_aside_decision(snapshot.symbol, timeframe, "Meta-SCI: No sub-strategy signals detected.")

        # [META-SCI] Dynamic Adoption for Exits
        if open_position and isinstance(open_position, dict) and self._strategy.name == "meta_sci":
            source = open_position.get("meta_source") or "supply_demand" # Default fallback
            self._strategy = self._load_specific_variant(source)
            logger.info(f" [META-SCI] Adopted {source.upper()} for exit management of {self.symbol}")

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

            # [WEALTH MODE] Augment with Performance Overrides (Sniper, Regime, etc.)
            decision = SafetyGuard.augment_entry_decision(
                decision, 
                score, 
                gates["htf_strength"], 
                snapshot,
                ai_client=self.ai_client
            )
            
            # [SMART POSITIONS] Financed Risk Check
            # Only allow new entries if we have enough open profit to cover the risk.
            if decision.action in ("enter_long", "enter_short"):
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
                    caps = execution_capabilities or {}
                    pnl = caps.get("total_unrealized_pnl", 0.0)
                    pos_count = caps.get("open_position_count", 0)

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
                        decision = stand_aside_decision(snapshot.symbol, timeframe, f"[SMART] Financing Required: PnL ${pnl:.2f} < Risk ${risk_amt:.2f}")
                        decision.score = score
                        decision.grade = grade
                        return decision

            # [SAFETY GUARD] Notify of Entry (for Churn Burner)
            if decision.action in ("enter_long", "enter_short", "scale_in"):
                 SafetyGuard.notify_entry()

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
