from __future__ import annotations
import logging
from typing import Optional, List, Dict
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

class MetaSCIStrategy(BaseStrategy):
    """
    True Adaptive Meta-Strategy (The "Clash" Engine).
    
    Logic:
    1. "Stickiness": If a specific strategy won the last trade for this symbol, 
       it is the "Champion". We check it first.
    2. "Challenge": If the Champion is silent or on a losing streak, 
       we run a full Tournament of all strategies.
    3. "Consensus": Winner of the tournament becomes the new temporary driver.
    """

    def __init__(self, profile_settings=None):
        super().__init__("meta_sci")
        self.profile = profile_settings or {}
        # Lazy loading registry to avoid circular imports on init if possible,
        # but we'll load them on first need or cache them.
        self.strategies: Dict[str, BaseStrategy] = {}
        self._initialized = False

    def _ensure_strategies_loaded(self):
        if self._initialized: return
        
        # Registry of all eligible contenders
        from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
        from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
        from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
        from tradebot_sci.strategy.variants.rubberband_reaper import RubberbandReaperStrategy
        from tradebot_sci.strategy.variants.breakout import VolatilityBreakoutStrategy
        from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy
        from tradebot_sci.strategy.variants.orb_breakout import ORBStrategy
        from tradebot_sci.strategy.variants.hyper_scalper import HyperScalperStrategy
        from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy
        from tradebot_sci.strategy.variants.robocop import RoboCopStrategy

        self.strategies = {
            "evolution": RobotEvolutionStrategy(),
            "supply_demand": SupplyDemandStrategy(),
            "london_breakout": LondonBreakoutStrategy(),
            "rubberband_reaper": RubberbandReaperStrategy(),
            "volatility_breakout": VolatilityBreakoutStrategy(),
            "icc_core": ICCCoreStrategy(),
            "orb_breakout": ORBStrategy(),
            "hyper_scalper": HyperScalperStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "robocop": RoboCopStrategy()
        }
        self._initialized = True

    def _get_champion(self, symbol: str, trade_history: List[dict]) -> Optional[str]:
        """
        Determine the current champion strategy for this symbol based on history.
        Returns the strategy name if it's on a winning streak or won the last trade.
        """
        if not trade_history:
            return None
            
        # Filter trades for this symbol
        my_trades = [t for t in trade_history if t.get('symbol') == symbol]
        if not my_trades:
            return None
            
        # Look at the last trade
        last_trade = my_trades[-1]
        source = last_trade.get('meta_source') or last_trade.get('strategy')
        pnl = last_trade.get('pnl_realized', 0)
        
        # Logic: If last trade was a WIN, stick to it.
        # If last trade was a LOSS but it had >1 win before that, maybe give it 1 more chance?
        # For now, strict: You lose, you defend your title in the tournament.
        if pnl > 0 and source in self.strategies:
            return source
            
        return None

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        self._ensure_strategies_loaded()
        
        # 1. Identify Champion
        champion_name = self._get_champion(snapshot.symbol, trade_history or [])
        champion_decision = None
        
        if champion_name:
            logger.info(f"[META-SCI] 👑 Defending Champion for {snapshot.symbol}: {champion_name.upper()}")
            strat = self.strategies[champion_name]
            champion_decision = strat.check_entry_signal(snapshot, gates, open_position, current_capital, trade_history)
            
            if champion_decision and champion_decision.action in ("enter_long", "enter_short", "scale_in"):
                # Champion defends title!
                champion_decision.notes = (champion_decision.notes or "") + f" | [META] 👑 Champion {champion_name.upper()} defends title"
                champion_decision.gates = champion_decision.gates or {}
                champion_decision.gates["meta_source"] = champion_name
                return champion_decision
            else:
                logger.info(f"[META-SCI] Champion {champion_name.upper()} is silent. Opening Tournament.")
        
        # 2. Tournament Mode (If no champion or champion silent)
        logger.info(f"[META-SCI] ⚔️ Starting Strategy Tournament for {snapshot.symbol}...")
        
        signals = []
        exclude_list = getattr(self.profile, 'meta_sci_exclude_list', [])
        
        for name, strat in self.strategies.items():
            if name == champion_name: continue # Already checked
            if name in exclude_list: continue
            
            try:
                # [ANTIGRAVITY FIX] Multi-Timeframe Routing
                # Route specific candle sets based on strategy preference.
                # RoboCop/Scalpers -> LTF (5m)
                # SupplyDemand/Swing -> HTF (15m)
                
                strat_snap = snapshot # Default
                
                # Check for cached dedicated snapshots or create them on fly
                if name in ("robocop", "hyper_scalper", "orb_breakout"):
                    # These WANT the fast timeframe (LTF)
                    # The main loop snapshot IS ltf_candles by default (since we set candle_tf=5m)
                    # So we use it as is.
                    pass
                    
                elif name in ("supply_demand", "mean_reversion"):
                    # These WANT the slow timeframe (HTF - 15m)
                    # We must verify we have HTF candles
                    if snapshot.htf_candles and len(snapshot.htf_candles) > 10:
                        # Construct a proxy snapshot for the definition of "candles"
                        # We keep trend_htf/ltf as is for context
                        strat_snap = MarketSnapshot(
                            symbol=snapshot.symbol,
                            timeframe=snapshot.htf_timeframe, # 15m
                            candles=snapshot.htf_candles,     # 15m data
                            trend_htf=snapshot.trend_htf,
                            trend_ltf=snapshot.trend_ltf,
                            htf_candles=snapshot.htf_candles,
                            ltf_candles=snapshot.ltf_candles,
                            htf_timeframe=snapshot.htf_timeframe,
                            ltf_timeframe=snapshot.ltf_timeframe,
                        )
                        # logger.debug(f"[META-TF] Routing HTF ({snapshot.htf_timeframe}) to {name}")

                # [ANTIGRAVITY FIX] Safe Dispatch using Introspection
                # Some strategies (RoboCop) take extra args, some (LondonBreakout) do not.
                # We inspect the signature to pass only what is accepted.
                import inspect
                sig_obj = inspect.signature(strat.check_entry_signal)
                params = sig_obj.parameters
                
                call_args = [strat_snap, gates] # First 2 are always required (after self)
                kwargs = {}
                
                # Check for optional positional/keyword parameters
                if "open_position" in params:
                    kwargs["open_position"] = open_position
                if "current_capital" in params:
                    kwargs["current_capital"] = current_capital
                if "trade_history" in params:
                    kwargs["trade_history"] = trade_history
                    
                # If the strategy accepts **kwargs, we can pass everything extra just in case
                has_varkw = any(p.kind == p.VAR_KEYWORD for p in params.values())
                if has_varkw:
                    kwargs["open_position"] = open_position
                    kwargs["current_capital"] = current_capital
                    kwargs["trade_history"] = trade_history
                
                # Execute logic
                sig = strat.check_entry_signal(*call_args, **kwargs)
                
                if sig and sig.action in ("enter_long", "enter_short", "scale_in"):
                    sig.gates = sig.gates or {}
                    sig.gates["meta_source"] = name
                    signals.append(sig)
                    logger.info(f"[META-DEBUG] {snapshot.symbol} {name.upper()}: WIN -> {sig.action} (Score: {sig.score})")
                else:
                    reason = sig.notes if sig else "No decision returned"
                    score = sig.score if sig else 0
                    logger.info(f"[META-DEBUG] {snapshot.symbol} {name.upper()}: REJECT -> {reason} (Score: {score})")
            except Exception as e:
                logger.error(f"[META-SCI] Strategy {name} crashed in tournament: {e}")

        if not signals:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Meta-SCI Tournament: No signals found.")

        # 3. Pick Winner
        # Logic: Highest Score -> Most Confluence
        winner = max(signals, key=lambda x: (x.score or 0) + (10 if x.grade == 'A' else 0))
        
        winner.notes = (winner.notes or "") + f" | [META] 🏆 Tournament Winner: {winner.gates['meta_source'].upper()}"
        logger.info(f"[META-SCI] Tournament Won by {winner.gates['meta_source'].upper()} (Score: {winner.score})")
        
        return winner

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        self._ensure_strategies_loaded()
        
        # Logic: Determine who opened this trade
        source = open_position.get("meta_source") or open_position.get("strategy_used")
        
        # Fallback handling
        if not source or source not in self.strategies:
            # If unknown source, ask Supply Demand (robust defaults)
            source = "supply_demand"
        
        logger.debug(f"[META-SCI] delegating exit to {source}")
        strat = self.strategies[source]
        
        # [ANTIGRAVITY FIX] Safe Dispatch for Exits (Mirroring Entry Logic)
        import inspect
        sig_obj = inspect.signature(strat.check_exit_signal)
        params = sig_obj.parameters
        
        call_args = [snapshot, open_position, gates]
        kwargs = {}
        
        if "current_capital" in params:
            kwargs["current_capital"] = current_capital
        if "trade_history" in params:
            kwargs["trade_history"] = trade_history
            
        has_varkw = any(p.kind == p.VAR_KEYWORD for p in params.values())
        if has_varkw:
            kwargs["current_capital"] = current_capital
            kwargs["trade_history"] = trade_history

        try:
            sig = strat.check_exit_signal(*call_args, **kwargs)
            if sig:
                logger.info(f"[META-DEBUG] {snapshot.symbol} {source.upper()} (EXIT): WIN -> {sig.action}")
                return sig
            else:
                logger.info(f"[META-DEBUG] {snapshot.symbol} {source.upper()} (EXIT): REJECT -> Hold")
                return None
        except Exception as e:
            logger.error(f"[META-SCI] Exit strategy {source} crashed: {e}")
            return None
