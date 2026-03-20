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
    
    ╔══════════════════════════════════════════════════════════════════╗
    ║  HOW TO ADD A NEW STRATEGY TO META-SCI                         ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║                                                                ║
    ║  1. Import the strategy class in _ensure_strategies_loaded()   ║
    ║  2. Add to self.strategies dict with a key name                ║
    ║  3. Add to self.REGIME_GROUPS — pick the right regime(s):      ║
    ║     - bearish_trending / bullish_trending (directional forex)  ║
    ║     - ranging (sideways forex/stocks)                          ║
    ║     - session_open (London/NY session strategies)              ║
    ║     - crypto_trending / crypto_ranging (crypto-specific)       ║
    ║  4. If crypto-only, add to self.CRYPTO_STRATEGIES set          ║
    ║  5. Optionally add to self.STRATEGY_WEIGHTS for tournament     ║
    ║     bonus (higher number = more weight in scoring)             ║
    ║                                                                ║
    ║  ALSO UPDATE THESE OTHER FILES (full checklist in engine.py):  ║
    ║  - src/tradebot_sci/strategy/engine.py (_load_strategy_variant)║
    ║  - src/tradebot_sci/electron_gui/renderer.js (STRATEGY_OPTIONS)║
    ║  - src/tradebot_sci/electron_gui/settings.js (dropdown)        ║
    ║  - src/tradebot_sci/electron_gui/settings_integrated.js        ║
    ║    (STRATEGIES object + System Tab dropdown + Toolbox grid)     ║
    ║                                                                ║
    ╚══════════════════════════════════════════════════════════════════╝
    """

    def __init__(self, profile_settings=None):
        super().__init__("meta_sci")
        self.profile = profile_settings or {}
        # Lazy loading registry to avoid circular imports on init if possible,
        # but we'll load them on first need or cache them.
        self.strategies: Dict[str, BaseStrategy] = {}
        self._initialized = False
        # [JUDGE] Track consecutive losses per strategy per symbol
        # Key: (symbol, strategy_name) -> int (consecutive loss count)
        self._loss_streaks: Dict[str, int] = {}

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """
        Meta-SCI Tournament Scoring: runs each eligible sub-strategy's
        score_signal() and reports the best one.

        Returns:
            (best_score, best_grade, summary_string)
        """
        self._ensure_strategies_loaded()
        regime = self._detect_regime(snapshot, gates)
        eligible_names = set(self.REGIME_GROUPS.get(regime, []))
        exclude_list = getattr(self.profile, 'meta_sci_exclude_list', [])

        best_score = 0.0
        best_grade = "F-"
        best_name = "none"
        results = []

        for name, strat in self.strategies.items():
            if name in exclude_list:
                continue
            if name not in eligible_names:
                continue
            try:
                s_score, s_grade, s_summary = strat.score_signal(snapshot, gates)
                weights = self._get_weights(snapshot.symbol)
                weight_bonus = weights.get(name, 0)
                effective = s_score + weight_bonus
                results.append((name, s_score, s_grade, effective))
                logger.info(
                    f"[META-DEBUG] {snapshot.symbol} {name.upper()}: "
                    f"score={s_score:.1f} grade={s_grade} "
                    f"(+{weight_bonus} weight = {effective:.1f})"
                )
                if effective > best_score:
                    best_score = s_score  # Report raw score, not weighted
                    best_grade = s_grade
                    best_name = name
            except Exception as e:
                logger.warning(f"[META-SCI] ⚠️ STRATEGY CRASH in score_signal: {name.upper()} → {e}", exc_info=True)

        if not results:
            # Fallback to ICC score
            icc_score = gates.get("score", 0.0)
            pct = round(icc_score * 100, 1)
            grade = self.grade_from_score_100(pct)
            return pct, grade, f"Meta-SCI: No eligible strategies (ICC {pct:.0f}%)"

        # Build compact summary showing top contenders
        top3 = sorted(results, key=lambda r: r[3], reverse=True)[:3]
        breakdown = " | ".join(f"{n}:{s:.0f}({g})" for n, s, g, _ in top3)
        summary = f"Meta-SCI [{regime}] Best={best_name}:{best_score:.0f} | {breakdown}"
        return best_score, best_grade, summary

    def _ensure_strategies_loaded(self):
        if self._initialized: return
        
        # Registry of all eligible contenders
        from tradebot_sci.strategy.variants.supply_demand import SupplyDemandStrategy
        from tradebot_sci.strategy.variants.london_breakout import LondonBreakoutStrategy
        from tradebot_sci.strategy.variants.rubberband_reaper import RubberbandReaperStrategy
        from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy
        from tradebot_sci.strategy.variants.orb_breakout import ORBStrategy
        from tradebot_sci.strategy.variants.hyper_scalper import HyperScalperStrategy
        from tradebot_sci.strategy.variants.robocop import RoboCopStrategy
        from tradebot_sci.strategy.variants.trend_rider import TrendRiderStrategy
        from tradebot_sci.strategy.variants.session_momentum import SessionMomentumStrategy
        from tradebot_sci.strategy.variants.bearish_engulfing import BearishEngulfingStrategy
        from tradebot_sci.strategy.variants.quantum import QuantumStrategy
        from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy
        # [PHASE 7] Previously missing — these are proven forex winners
        from tradebot_sci.strategy.variants.breakout import VolatilityBreakoutStrategy
        from tradebot_sci.strategy.variants.evolution import RobotEvolutionStrategy
        from tradebot_sci.strategy.variants.forex_conductor import ForexConductorStrategy
        # [CRYPTO SUITE] Crypto-specific strategies
        from tradebot_sci.strategy.variants.crypto_rsi_macd import CryptoRSIMACDStrategy
        from tradebot_sci.strategy.variants.crypto_vwap_reversion import CryptoVWAPReversionStrategy
        from tradebot_sci.strategy.variants.crypto_double_macd import CryptoDoubleMACDStrategy
        from tradebot_sci.strategy.variants.crypto_grid import CryptoGridStrategy

        self.strategies = {
            # --- Trending Market ---
            "supply_demand": SupplyDemandStrategy(),
            "robocop": RoboCopStrategy(),
            "hyper_scalper": HyperScalperStrategy(),
            "trend_rider": TrendRiderStrategy(),
            "quantum": QuantumStrategy(),
            "volatility_breakout": VolatilityBreakoutStrategy(),  # [PHASE 7] Was missing!
            "forex_conductor": ForexConductorStrategy(profile_settings=getattr(self, 'profile', None)),
            # --- Ranging / Reversal Market ---
            "rubberband_reaper": RubberbandReaperStrategy(),
            "icc_core": ICCCoreStrategy(),
            "bearish_engulfing": BearishEngulfingStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "evolution": RobotEvolutionStrategy(),                     # [PHASE 7] Was missing!
            # --- Session Open ---
            "london_breakout": LondonBreakoutStrategy(),
            "orb_breakout": ORBStrategy(),
            "session_momentum": SessionMomentumStrategy(),
            # --- Crypto-Specific ---
            "crypto_rsi_macd": CryptoRSIMACDStrategy(),
            "crypto_vwap_reversion": CryptoVWAPReversionStrategy(),
            "crypto_double_macd": CryptoDoubleMACDStrategy(),
            "crypto_grid": CryptoGridStrategy(),
        }

        # [CRYPTO SUITE] Strategies restricted to crypto symbols only
        self.CRYPTO_STRATEGIES = {
            "crypto_rsi_macd", "crypto_vwap_reversion",
            "crypto_double_macd", "crypto_grid",
            "hyper_scalper",  # EMA scalper — designed for crypto volatility, not forex
        }

        # Propagate profile risk to all strategies
        risk_pct = getattr(self.profile, "risk_per_trade_pct", None)
        if risk_pct:
            for strat in self.strategies.values():
                strat.profile_risk_pct = float(risk_pct)

        # [PHASE 7] Regime groupings — curated by 14-day solo battle-hardening.
        # Only strategies that are individually profitable or near-profitable
        # are included in forex regime groups. Losers drag the ensemble down.
        # REMOVED from forex: supply_demand (-$16K), bearish_engulfing (-$5K),
        #   robocop (-$4K), quantum (-$3K), evolution (-$3K),
        #   volatility_breakout (0 trades), trend_rider (0 trades)
        self.REGIME_GROUPS = {
            "bearish_trending": [
                "icc_core",             # ✅ +$1,237 solo (ATR*2.0, 2.0R, profit guard)
                "mean_reversion",       # Near-break (R:R 0.82, best of losers)
                "forex_conductor",
            ],
            "bullish_trending": [
                "icc_core",             # ✅ +$1,237 solo
                "mean_reversion",
                "forex_conductor",
            ],
            "ranging": [
                "icc_core",             # ✅ Works in all regimes
                "mean_reversion",       # Mean reversion natural in ranging
                "forex_conductor",
            ],
            "session_open": [
                "london_breakout",      # Session-specific (London open)
                "orb_breakout",         # ✅ +$1,718 solo (Opening Range Breakout)
                "session_momentum",     # Session-specific
                "forex_conductor",
            ],
            "crypto_trending": [
                "supply_demand", "robocop", "hyper_scalper", "trend_rider", "quantum",
                "rubberband_reaper", "icc_core", "bearish_engulfing", "mean_reversion",
                "crypto_rsi_macd", "crypto_vwap_reversion", "crypto_double_macd", "crypto_grid",
            ],
            "crypto_ranging": [
                "supply_demand", "robocop", "hyper_scalper", "quantum",
                "rubberband_reaper", "icc_core", "bearish_engulfing", "mean_reversion",
                "crypto_rsi_macd", "crypto_vwap_reversion", "crypto_double_macd", "crypto_grid",
            ],
        }

        # [PHASE 7] Asset-aware tournament weights based on 14-day battle-hardening
        # FOREX weights: only boost PROVEN profitable strategies
        self.FOREX_WEIGHTS = {
            "icc_core": 20,              # ✅ +$1,237 solo — top forex strategy
            "orb_breakout": 20,          # ✅ +$1,718 solo — session breakout king
            "london_breakout": 10,       # Session-only, -$116 in Meta-SCI context
            "mean_reversion": 8,         # Best remaining R:R (0.82)
            "session_momentum": 5,       # Low volume, session-specific
            "forex_conductor": 20,       # Strong router
        }
        # CRYPTO weights: keep old weights (legacy, for when crypto is re-enabled)
        self.CRYPTO_WEIGHTS = {
            "bearish_engulfing": 15,
            "supply_demand": 5,
            "quantum": 5,
            "mean_reversion": 10,
        }
        # Default fallback
        self.STRATEGY_WEIGHTS = self.FOREX_WEIGHTS

        self._initialized = True

    def _get_weights(self, symbol: str) -> dict:
        """Return asset-class-aware tournament weights for the given symbol."""
        from tradebot_sci.market.symbols import is_crypto
        if is_crypto(symbol):
            return self.CRYPTO_WEIGHTS
        return self.FOREX_WEIGHTS

    # ══════════════════════════════════════════════════════════════════
    #  THE JUDGE — Asset-Aware Tournament Scoring
    # ══════════════════════════════════════════════════════════════════
    #
    #  The Judge guarantees proven winners always dominate tournaments:
    #
    #  1. PROVEN WINNER boost: 10× score if strategy is a known winner
    #     for this asset class (from backtested audit data).
    #
    #  2. SESSION WINDOW boost: 10× score if strategy is in its optimal
    #     session window (e.g., London open for london_breakout).
    #
    #  3. These STACK: a proven winner in session = 100× score.
    #
    #  4. LOSS STREAK penalty: consecutive losses halve the boost each
    #     time. 2 losses = 25% boost. 3+ losses = boost revoked.
    #
    # ══════════════════════════════════════════════════════════════════

    # Proven winners per asset class — from 14-day audited backtests
    FOREX_PROVEN_WINNERS = {
        "icc_core",             # ✅ +$1,237 solo (battle-hardened)
        "orb_breakout",         # ✅ +$1,718 solo (battle-hardened)
        "london_breakout",      # Session-specific, near-profitable in ensemble
        "forex_conductor",      # Router-based ensemble
    }

    CRYPTO_PROVEN_WINNERS = set()  # None profitable yet

    # Session windows: when each strategy is allowed to compete
    # Format: {strategy_name: [(start_utc_hour, end_utc_hour), ...]}
    # Strategies NOT listed here and NOT in ALL_AROUND_HITTERS cannot fire.
    SESSION_WINDOWS = {
        "london_breakout": [(8, 12)],          # London session: 08:00-12:00 UTC
        "orb_breakout": [(13, 16)],             # US open: ~09:00-11:00 ET = 13:00-16:00 UTC
        "volatility_breakout": [(0, 8)],        # Asian session: 00:00-08:00 UTC
    }

    # All-around hitters: can fire ANY time of day
    ALL_AROUND_HITTERS = {
        "icc_core",        # ICT methodology works in any session
        "mean_reversion",  # Mean reversion works in any session (best R:R 0.82)
        "forex_conductor", # Conductor handles sessions internally
    }

    def _is_in_session_window(self, strategy_name: str, snapshot) -> bool:
        """Check if the strategy is currently in its optimal session window."""
        # All-around hitters are ALWAYS in session
        if strategy_name in self.ALL_AROUND_HITTERS:
            return True

        windows = self.SESSION_WINDOWS.get(strategy_name)
        if not windows:
            return False

        if not snapshot.candles:
            return False

        from zoneinfo import ZoneInfo
        ts = snapshot.candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("UTC"))
        utc_hour = ts.astimezone(ZoneInfo("UTC")).hour

        for start_h, end_h in windows:
            if start_h <= utc_hour < end_h:
                return True
        return False

    def _is_proven_winner(self, strategy_name: str, symbol: str) -> bool:
        """Check if this strategy is a proven winner for the symbol's asset class."""
        from tradebot_sci.market.symbols import is_crypto
        if is_crypto(symbol):
            return strategy_name in self.CRYPTO_PROVEN_WINNERS
        return strategy_name in self.FOREX_PROVEN_WINNERS

    def _get_loss_streak(self, symbol: str, strategy_name: str) -> int:
        """Get the current consecutive loss count for a strategy on a symbol."""
        key = f"{symbol}:{strategy_name}"
        return self._loss_streaks.get(key, 0)

    def _record_trade_result(self, symbol: str, strategy_name: str, is_win: bool):
        """Update loss streak tracker after a trade completes."""
        key = f"{symbol}:{strategy_name}"
        if is_win:
            self._loss_streaks[key] = 0  # Reset on win
        else:
            self._loss_streaks[key] = self._loss_streaks.get(key, 0) + 1

    def _judge_boost(self, strategy_name: str, symbol: str, snapshot) -> float:
        """
        The Judge: calculate the tournament score multiplier.

        Returns a multiplier (1.0 = no boost, 10.0 = proven winner,
        100.0 = proven winner + in session, etc.)

        Loss streaks reduce the boost:
          0 losses: full boost
          1 loss: 50% boost
          2 losses: 25% boost
          3+ losses: boost revoked (1.0 multiplier)
        """
        multiplier = 1.0

        is_winner = self._is_proven_winner(strategy_name, symbol)
        in_session = self._is_in_session_window(strategy_name, snapshot)

        if is_winner:
            multiplier *= 10.0
        if in_session:
            multiplier *= 10.0

        # Apply loss streak penalty
        if multiplier > 1.0:
            losses = self._get_loss_streak(symbol, strategy_name)
            if losses >= 3:
                multiplier = 1.0  # Boost fully revoked
            elif losses == 2:
                multiplier *= 0.25  # 75% reduction
            elif losses == 1:
                multiplier *= 0.50  # 50% reduction

        return multiplier

    def _detect_regime(self, snapshot: MarketSnapshot, gates: dict) -> str:
        """
        Detect current market regime.
        For crypto symbols: 'crypto_trending' or 'crypto_ranging'
        For others: 'trending', 'ranging', or 'session_open'
        Uses HTF trend strength and session time.
        """
        from tradebot_sci.market.symbols import is_crypto

        # [CRYPTO SUITE] Crypto symbols get crypto-specific regimes
        if is_crypto(snapshot.symbol):
            htf_strength = float(gates.get("htf_strength", 0))
            if htf_strength >= 0.4:
                return "crypto_trending"
            return "crypto_ranging"

        # Check session open windows first (highest priority)
        if snapshot.candles:
            from zoneinfo import ZoneInfo
            ts = snapshot.candles[-1].timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ZoneInfo("UTC"))
            utc_time = ts.astimezone(ZoneInfo("UTC"))
            et_time = ts.astimezone(ZoneInfo("America/New_York"))

            # London open: 08:00-08:30 UTC
            from datetime import time as dt_time
            if dt_time(8, 0) <= utc_time.time() < dt_time(8, 30):
                return "session_open"
            # NY open: 09:30-10:00 ET
            if dt_time(9, 30) <= et_time.time() < dt_time(10, 0):
                return "session_open"

        # HTF trend strength + direction determines regime
        htf_strength = float(gates.get("htf_strength", 0))
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        if htf_strength >= 0.4:
            if htf_dir == "short":
                return "bearish_trending"
            elif htf_dir == "long":
                return "bullish_trending"

        return "ranging"

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

        # ── [JUDGE] Derive loss streaks from trade history ──────────────
        # Scan recent Meta-SCI trades to track consecutive losses per
        # sub-strategy. This powers the Judge's loss streak penalty.
        if trade_history:
            # Group recent trades by (symbol, meta_source)
            for t in reversed(trade_history[-50:]):  # Last 50 trades max
                sym = t.get('symbol', '')
                source = t.get('meta_source') or t.get('strategy_used', '')
                if not source or source not in self.strategies:
                    continue
                pnl = t.get('pnl_realized', 0)
                key = f"{sym}:{source}"
                if key not in self._loss_streaks:
                    # First time seeing this combo — count backward
                    streak = 0
                    for t2 in reversed(trade_history):
                        s2 = t2.get('meta_source') or t2.get('strategy_used', '')
                        if t2.get('symbol') == sym and s2 == source:
                            if t2.get('pnl_realized', 0) <= 0:
                                streak += 1
                            else:
                                break  # Win found, stop counting
                    self._loss_streaks[key] = streak        # ── Trend Direction Reference ─────────────────────────────────────
        # Strategies use gates["htf_dir"] to orient their trade direction.
        # htf_dir = str(gates.get("htf_dir", "neutral")).lower()

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
        # [AUDIT] Detect market regime to filter competing strategies
        regime = self._detect_regime(snapshot, gates)
        eligible_names = set(self.REGIME_GROUPS.get(regime, []))
        logger.info(f"[META-SCI] ⚔️ Starting {regime.upper()} Tournament for {snapshot.symbol} ({len(eligible_names)} strategies eligible)...")
        
        signals = []
        rejects = []  # Track reject scores for summary
        crashes = []  # Track crashed strategies
        exclude_list = getattr(self.profile, 'meta_sci_exclude_list', [])
        
        for name, strat in self.strategies.items():
            if name == champion_name: continue # Already checked
            if name in exclude_list: continue
            if name not in eligible_names: continue  # [AUDIT] Regime filter
            # [JUDGE] Gatekeeper: on forex, only proven winners may compete,
            # AND only during their assigned session window.
            if not self._is_proven_winner(name, snapshot.symbol):
                continue
            if not self._is_in_session_window(name, snapshot):
                continue  # Not this strategy's time to shine
            
            try:
                # Multi-Timeframe Routing
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

                # Safe Dispatch using Introspection
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
                    score = float(sig.score or 0) if sig else 0
                    grade = (sig.grade or "F") if sig else "F"
                    reason = sig.notes if sig else "No decision"
                    rejects.append((name, score, grade, reason))
                    logger.info(f"[META-DEBUG] {snapshot.symbol} {name.upper()}: REJECT -> {reason} (Score: {score})")
            except Exception as e:
                crashes.append(name)
                logger.critical(f"[META-SCI] 💥 STRATEGY CRASH: {name.upper()} crashed in tournament → {e}", exc_info=True)

        if not signals:
            # Build a rich summary mirroring the winning format
            champ_part = f"👑 {champion_name.upper()} silent → " if champion_name else ""
            crash_part = f" | 💥 {len(crashes)} CRASHED: {','.join(c.upper() for c in crashes)}" if crashes else ""
            # Sort rejects by score descending, show top contenders with scores
            top_rejects = sorted(rejects, key=lambda r: r[1], reverse=True)[:4]
            breakdown = " | ".join(f"{n}:{s:.0f}({g})" for n, s, g, _ in top_rejects)
            reason = f"Meta-SCI [{regime}] {champ_part}{len(rejects)} rejected{crash_part} | {breakdown}"
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)

        # 3. Pick Winner — THE JUDGE decides
        #    Score = (base_score + grade_bonus) × judge_boost
        #    Judge boost = 10× proven winner × 10× session window
        #    Loss streaks reduce the boost (see _judge_boost)
        def _tournament_score(sig):
            name = sig.gates.get("meta_source", "")
            
            # Rule-based strategies (icc_core, etc.) don't emit scores; if they fire, 
            # it's 100% conviction. Conductor supplies a 0-100 scale.
            base = float(sig.score) if getattr(sig, "score", None) is not None else 100.0
            grade_bonus = 10.0 if getattr(sig, "grade", "") == 'A' else 0.0
            
            # Add strategy's inherent weight as a tie-breaker / edge
            weights = self._get_weights(snapshot.symbol)
            inherent_weight = float(weights.get(name, 5.0))
            
            raw = base + grade_bonus + inherent_weight
            
            boost = self._judge_boost(name, snapshot.symbol, snapshot)
            final = raw * boost
            if boost > 1.0:
                losses = self._get_loss_streak(snapshot.symbol, name)
                logger.info(
                    f"[JUDGE] {snapshot.symbol} {name.upper()}: "
                    f"base={base:.0f} wt={inherent_weight:.0f} raw={raw:.0f} × boost={boost:.0f}× = {final:.0f} "
                    f"(losses={losses})"
                )
            return final
        
        winner = max(signals, key=_tournament_score)
        
        winner_name = winner.gates['meta_source']
        winner_boost = self._judge_boost(winner_name, snapshot.symbol, snapshot)
        winner.notes = (winner.notes or "") + (
            f" | [META] 🏆 Tournament Winner: {winner_name.upper()}"
            f" (Judge: {winner_boost:.0f}×)"
        )
        logger.info(f"[META-SCI] Tournament Won by {winner_name.upper()} (Score: {winner.score}, Judge: {winner_boost:.0f}×)")
        
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
        
        # Safe Dispatch for Exits (Mirroring Entry Logic)
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
