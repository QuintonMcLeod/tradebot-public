from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

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
        else:
            # Fallback
            from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
            return RobotEvolutionStrategy()

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
        # 1. Gather Context
        snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        caps = execution_capabilities or {}
        
        # Build Confluence (Legacy block kept for strategy-v1 compatibility)
        confluence_data = build_confluence(
            self.market_provider,
            snapshot.symbol,
            snapshot.candles,
            include_external=os.getenv("CONFLUENCE_EXTERNAL", "false").lower() == "true",
        ).data

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
            "confluence": confluence_data,
            "score": score,
            "grade": grade
        }

        # 3. Request Decisions from Strategy
        # A. Check for EXIT if we have a position
        if open_position and abs(open_position.get("size", 0.0)) > 0:
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
