from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Any

from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.icc_signals import (
    detect_liquidity_sweep,
    detect_indication,
    detect_correction,
    detect_continuation
)
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.broker.trade_result_store import TradeResultStore

logger = logging.getLogger(__name__)

class StrategyEngine:
    """
    Lean Strategy Orchestrator.
    Acts as the 'hands and eyes' for Strategy Variants.
    Zero internal filters. 100% Signal Fidelity.
    """

    # [SAFETY] Global Account Guardians (cleaned up — HWM now in SafetyGuard._state)

    def __init__(
        self,
        ai_client: TradeSciAIClient | None,
        market_provider: MarketDataProvider,
        profile: BaseProfile,
        symbol: str,
        trade_results: Optional[TradeResultStore] = None,
        settings: Optional[Any] = None,
    ):
        self.ai_client = ai_client
        self.market_provider = market_provider
        self.profile = profile
        self.symbol = symbol
        self.trade_results = trade_results
        self.settings = settings  # Root Settings object (has .safety, .risk, etc.)
        
        # Last strategy scoring (populated by decide(), read by cycle.py for logging)
        self.last_strat_name: str = "Unknown"
        self.last_strat_score: float = 0.0
        self.last_strat_grade: str = "N/A"
        self.last_gates: dict[str, Any] = {}
        
        # Determine which strategy this engine instance will run
        self._variant_key = self._resolve_variant_key()  # For SAR exclusion and masking
        
        # Engine Initialization Complete
        
        # Load the Strategy Variant using the purely isolated & masked profile
        self._strategy = self._load_strategy_variant()
        
        # Propagate profile risk to the strategy
        risk_pct = getattr(self.profile, 'risk_per_trade_pct', None)
        if risk_pct and hasattr(self._strategy, 'profile_risk_pct'):
            self._strategy.profile_risk_pct = float(risk_pct)
        
        logger.info(f" [ENGINE] === ENGINE LOADED === Symbol: {symbol} | Variant: {self._strategy.name.upper()} ")

    def sync_profile(self, profile: BaseProfile, settings: Optional[Any] = None) -> None:
        """Update internal profile and dynamically reload strategy variant (Hot-Reload)."""
        self.profile = profile
        if settings is not None:
            self.settings = settings
            
        self._variant_key = self._resolve_variant_key()
        self._strategy = self._load_strategy_variant()
        
        risk_pct = getattr(self.profile, 'risk_per_trade_pct', None)
        if risk_pct and hasattr(self._strategy, 'profile_risk_pct'):
            self._strategy.profile_risk_pct = float(risk_pct)
            
        logger.info(f"[ENGINE {self.symbol}] Hot-reloaded profile settings into {self._strategy.name.upper()}")

    # ── SAR (Stop-and-Reverse) — Engine-Level ────────────────────────
    # Aggregator is excluded (it has no own-position semantic).
    # ForexConductor previously had a duplicate SAR path; it now receives
    # sar_dir via gates["sar_dir"] and computes ATR-based SL/TP itself.
    _SAR_EXCLUDED = {"aggregator"}
    _sar_pending: dict[str, str] = {}  # symbol → reversal direction
    _cr_pending:  dict[str, str] = {}  # symbol → CR direction (back to original)
    _sar_cooldown_until: dict[str, object] = {}  # symbol → datetime; blocks spirals
    _sar_consec_losses:  dict[str, int] = {}     # symbol → consecutive SAR loss count
    _sar_last_processed: dict[str, str] = {}     # symbol → exit_time of last scanned trade (dedup)

    def _resolve_variant_key(self) -> str:
        """Get the registry key for the loaded strategy variant."""
        from tradebot_sci.config.models import UserConfig
        if hasattr(self.profile, "get_strategy_for_symbol"):
            return self.profile.get_strategy_for_symbol(self.symbol).lower()
        return getattr(UserConfig, "STRATEGY_VARIANT", "evolution").lower()

    @staticmethod
    def _timeframe_to_seconds(tf: str) -> int:
        """Convert timeframe string (e.g., '15m', '1h', '5m') to seconds."""
        tf = tf.strip().lower()
        try:
            if tf.endswith("m"):
                return int(tf[:-1]) * 60
            if tf.endswith("h"):
                return int(tf[:-1]) * 3600
            if tf.endswith("d"):
                return int(tf[:-1]) * 86400
        except ValueError:
            pass
        return 900  # Default: 15 minutes

    # ── Strategy Registry ────────────────────────────────────────────
    # Single registry: add new strategies here (keeps both load methods
    # in sync automatically).  Each entry maps a lowercase variant name
    # to a (module_path, class_name) tuple for lazy import.
    STRATEGY_REGISTRY: dict[str, tuple[str, str]] = {
        "evolution":            ("tradebot_sci.strategy.variants.evolution",            "RobotEvolutionStrategy"),
        "robocop":              ("tradebot_sci.strategy.variants.robocop",              "RoboCopStrategy"),
        "london_breakout":      ("tradebot_sci.strategy.variants.london_breakout",      "LondonBreakoutStrategy"),
        "rubberband_reaper":    ("tradebot_sci.strategy.variants.rubberband_reaper",    "RubberbandReaperStrategy"),
        "volatility_breakout":  ("tradebot_sci.strategy.variants.breakout",             "VolatilityBreakoutStrategy"),
        "icc_core":             ("tradebot_sci.strategy.variants.icc_core",             "ICCCoreStrategy"),
        "icc_core_standalone":  ("tradebot_sci.strategy.variants.icc_core_standalone",  "ICCCoreStandaloneStrategy"),
        "supply_demand":        ("tradebot_sci.strategy.variants.supply_demand",         "SupplyDemandStrategy"),
        "meta_sci":             ("tradebot_sci.strategy.variants.meta_sci",             "MetaSCIStrategy"),
        "trend_rider":          ("tradebot_sci.strategy.variants.trend_rider",          "TrendRiderStrategy"),
        "session_momentum":     ("tradebot_sci.strategy.variants.session_momentum",     "SessionMomentumStrategy"),
        "bearish_engulfing":    ("tradebot_sci.strategy.variants.bearish_engulfing",    "BearishEngulfingStrategy"),
        "hyper_scalper":        ("tradebot_sci.strategy.variants.hyper_scalper",        "HyperScalperStrategy"),
        "orb_breakout":         ("tradebot_sci.strategy.variants.orb_breakout",         "ORBStrategy"),
        "quantum":              ("tradebot_sci.strategy.variants.quantum",              "QuantumStrategy"),
        "yoyo":                 ("tradebot_sci.strategy.variants.yoyo",                "YoYoStrategy"),
        "mean_reversion":       ("tradebot_sci.strategy.variants.mean_reversion",       "MeanReversionStrategy"),
        "crypto_rsi_macd":      ("tradebot_sci.strategy.variants.crypto_rsi_macd",      "CryptoRSIMACDStrategy"),
        "crypto_vwap_reversion":("tradebot_sci.strategy.variants.crypto_vwap_reversion","CryptoVWAPReversionStrategy"),
        "crypto_double_macd":   ("tradebot_sci.strategy.variants.crypto_double_macd",   "CryptoDoubleMACDStrategy"),
        "crypto_grid":          ("tradebot_sci.strategy.variants.crypto_grid",          "CryptoGridStrategy"),
        "aggregator":           ("tradebot_sci.strategy.variants.aggregator",           "AggregatorStrategy"),
        "forex_conductor":      ("tradebot_sci.strategy.variants.forex_conductor",      "ForexConductorStrategy"),
        "forex_hybrid_reaper":  ("tradebot_sci.strategy.variants.forex_hybrid_reaper",  "ForexHybridReaperStrategy"),
        "qs_sma_filter":        ("tradebot_sci.strategy.variants.qs_sma_filter",        "QS_SMAFilterStrategy"),
        "qs_golden_cross":      ("tradebot_sci.strategy.variants.qs_golden_cross",      "QS_GoldenCrossStrategy"),
        "qs_rsi_mean_reversion":("tradebot_sci.strategy.variants.qs_rsi_mean_reversion","QS_RSIMeanReversionStrategy"),
        "qs_3_10_trend":        ("tradebot_sci.strategy.variants.qs_3_10_trend",        "QS_3_10_TrendStrategy"),
        "qs_tqqq_btal":         ("tradebot_sci.strategy.variants.qs_tqqq_btal",         "QS_TqqqBtalStrategy"),
        "qs_choppiness":        ("tradebot_sci.strategy.variants.qs_choppiness",        "QS_ChoppinessStrategy"),
        "qs_first_day_month":   ("tradebot_sci.strategy.variants.qs_first_day_month",   "QS_FirstDayOfMonthStrategy"),
        "silver_vwap":          ("tradebot_sci.strategy.variants.silver_vwap",          "SilverVwapStrategy"),
    }

    def _instantiate_variant(self, variant: str):
        """Lazily import and instantiate a strategy by registry key."""
        import importlib
        entry = self.STRATEGY_REGISTRY.get(variant)
        if not entry:
            return None
        module_path, class_name = entry
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        
        # Pass strategy base kwargs from the profile's dynamically loaded attributes
        kwargs = {}
        if hasattr(self.profile, "model_dump"):
            kwargs.update(self.profile.model_dump())
        elif hasattr(self.profile, "__dict__"):
            kwargs.update(self.profile.__dict__)

        # MetaSCIStrategy and ForexConductor require profile_settings kwarg
        if variant == "meta_sci":
            return cls(profile_settings=self.profile)
        if variant == "forex_conductor":
            kwargs["profile_settings"] = self.profile
            return cls(**kwargs)
            
        return cls(**kwargs)

    def _load_strategy_variant(self):
        """Factory method for loading strategy variants.
        
        ╔══════════════════════════════════════════════════════════════════╗
        ║  HOW TO ADD A NEW STRATEGY — FULL CHECKLIST                    ║
        ╠══════════════════════════════════════════════════════════════════╣
        ║                                                                ║
        ║  1. Create strategy class:                                     ║
        ║     src/tradebot_sci/strategy/variants/your_strategy.py        ║
        ║     - Extend BaseStrategy, implement evaluate() + get_signal() ║
        ║                                                                ║
        ║  2. Register in STRATEGY_REGISTRY (this file, engine.py):      ║
        ║     Add one line: "key": ("module.path", "ClassName"),         ║
        ║                                                                ║
        ║  3. Add to Meta-SCI ensemble (if applicable):                  ║
        ║     src/tradebot_sci/strategy/variants/meta_sci.py             ║
        ║     - Import class in _ensure_strategies_loaded()              ║
        ║     - Add to self.strategies dict                              ║
        ║     - Add to appropriate REGIME_GROUPS                         ║
        ║     - If crypto-only, add to self.CRYPTO_STRATEGIES set        ║
        ║     - Optionally add to self.STRATEGY_WEIGHTS                  ║
        ║                                                                ║
        ║  4. Add to UI — Profile Editor dropdown:                       ║
        ║     src/tradebot_sci/electron_gui/renderer.js                  ║
        ║     - Add to STRATEGY_OPTIONS array                            ║
        ║                                                                ║
        ║  5. Add to UI — System Tab dropdown (settings.js):             ║
        ║     src/tradebot_sci/electron_gui/settings.js                  ║
        ║     - Add to STRATEGY_VARIANT dropdown items                   ║
        ║                                                                ║
        ║  6. Add to UI — System Tab dropdown (settings_integrated.js):  ║
        ║     src/tradebot_sci/electron_gui/settings_integrated.js       ║
        ║     - Add to STRATEGY_VARIANT dropdown items in                ║
        ║       renderSystemTab()                                        ║
        ║                                                                ║
        ║  7. Add to UI — Strategy descriptions (STRATEGIES object):     ║
        ║     src/tradebot_sci/electron_gui/settings_integrated.js       ║
        ║     - Add to const STRATEGIES = { ... } near top of file       ║
        ║     - Include: name, shortDesc, description, style, risk,      ║
        ║       bestFor, stats                                           ║
        ║                                                                ║
        ║  8. Add to UI — Strategy Toolbox grid:                         ║
        ║     src/tradebot_sci/electron_gui/settings_integrated.js       ║
        ║     - Add to strategies array in renderStrategyToolbox()        ║
        ║     - Include: id, label, icon (Material Symbols), color       ║
        ║                                                                ║
        ╚══════════════════════════════════════════════════════════════════╝
        """
        from tradebot_sci.config.models import UserConfig
        
        if hasattr(self.profile, "get_strategy_for_symbol"):
            variant = self.profile.get_strategy_for_symbol(self.symbol).lower()
        else:
            variant = getattr(UserConfig, "STRATEGY_VARIANT", "evolution").lower()
        
        strategy = self._instantiate_variant(variant)
        if strategy:
            return strategy
        logger.warning(f"[ENGINE] Unknown strategy variant '{variant}', falling back to Evolution")
        return self._instantiate_variant("evolution")

    def _load_specific_variant(self, variant: str):
        """Dynamic helper for Meta-SCI ensemble loading."""
        return self._instantiate_variant(variant.lower())

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
        
        # Fallback: If LTF is neutral, use HTF as the baseline direction for signals.
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
        snapshot = snapshot or self.market_provider.get_latest_snapshot(self.symbol, timeframe)
        latest_snapshot = snapshot  # Unified: single fetch for both safety check and strategy logic

        if self.trade_results:
            stats = self.trade_results.get_stats()
            if stats.get('total_trades', 0) >= 5:
                 ac = classify_symbol(self.symbol)
                 SafetyGuard.set_win_rate(stats.get('win_rate', 0.55), asset_class=ac)

        # Register current position status for wealth mode / financed risk logic
        # This must happen before any decisions are made.
        SafetyGuard.update_position(self.symbol, open_position)

        caps = execution_capabilities or {}
        
        # 2. Build Gates (Metadata for Strategy)
        current_capital = current_capital if current_capital is not None else getattr(self.market_provider, "current_capital", None)
        history = [r.to_dict() for r in (self.trade_results.results if self.trade_results else [])]
        
        # Calculate grade for the current snapshot
        score, grade = self.score_icc_grade(snapshot)
        
        # ── Trend Detection (my sole authority on direction) ─────────────────
        # In Synthetic Mode, the provider forces trend states directly on my snapshot.
        # If the snapshot arrives with a synthetic override (e.g. strength > 0 and direction),
        # I bypass the lagging indicators in trend_consensus which would zero it out.
        is_synthetic_override = snapshot.trend_htf and snapshot.trend_htf.direction != "neutral" and snapshot.trend_htf.strength > 0.0

        candles = snapshot.candles or []
        if is_synthetic_override:
            # Use the forced synthetic trend directly, skipping lagging indicators
            htf_dir = snapshot.trend_htf.direction
            mtf_dir = snapshot.trend_htf.direction  # Synthetic: MTF follows HTF
            ltf_dir = snapshot.trend_ltf.direction
            exec_dir = snapshot.trend_ltf.direction
            htf_strength = snapshot.trend_htf.strength
            mtf_strength = snapshot.trend_htf.strength  # Synthetic: MTF follows HTF
            ltf_strength = snapshot.trend_ltf.strength
            exec_strength = snapshot.trend_ltf.strength
            htf_align = True # Synthetic overrides are strictly aligned
            htf_adx = 50.0 # Force high ADX for regime checks
            indicator_dir = snapshot.trend_htf.direction
            indicator_strength = snapshot.trend_htf.strength
            market_regime = "trending" if htf_strength > 0.5 else "transitional"
            
            consensus_rsi = 60.0 if htf_dir == "long" else 40.0
            consensus_macd = {"histogram": 0.001 if htf_dir == "long" else -0.001}
            consensus_supertrend = {"direction": htf_dir}
            consensus_ema_ribbon = {"aligned": True, "direction": htf_dir}
            consensus_bollinger = {"bandwidth": 0.02, "squeeze": False}
        else:
            from tradebot_sci.market.trend_consensus import detect_trend_direction
            consensus = detect_trend_direction(
                candles, self.profile,
                htf_candles=getattr(snapshot, 'htf_candles', None),
                mtf_candles=getattr(snapshot, 'mtf_candles', None),
                ltf_candles=getattr(snapshot, 'ltf_candles', None),
            )

            htf_dir = consensus.htf_dir
            mtf_dir = consensus.mtf_dir
            ltf_dir = consensus.ltf_dir
            exec_dir = consensus.exec_dir
            htf_strength = consensus.htf_strength
            mtf_strength = consensus.mtf_strength
            ltf_strength = consensus.ltf_strength
            exec_strength = consensus.exec_strength
            htf_adx = consensus.htf_adx
            htf_align = consensus.htf_align
            indicator_dir = consensus.indicator_dir
            indicator_strength = consensus.indicator_strength
            market_regime = consensus.market_regime
            
            consensus_rsi = consensus.rsi
            consensus_macd = consensus.macd
            consensus_supertrend = consensus.supertrend
            consensus_ema_ribbon = consensus.ema_ribbon
            consensus_bollinger = consensus.bollinger
            vote_sources = consensus.vote_sources

            # Update snapshot in-place so strategies reading snapshot.trend_htf directly
            # also receive the indicator-derived direction.
            from dataclasses import replace as dc_replace
            snapshot.trend_htf = dc_replace(
                snapshot.trend_htf, direction=htf_dir, strength=htf_strength
            )
            if hasattr(snapshot, "trend_mtf"):
                if snapshot.trend_mtf is not None:
                    snapshot.trend_mtf = dc_replace(
                        snapshot.trend_mtf, direction=mtf_dir, strength=mtf_strength
                    )
                else:
                    from tradebot_sci.market.models import TrendState
                    snapshot.trend_mtf = TrendState(direction=mtf_dir, strength=mtf_strength)
            snapshot.trend_ltf = dc_replace(
                snapshot.trend_ltf, direction=ltf_dir, strength=ltf_strength
            )
            
            if getattr(snapshot, 'trend_exec', None):
                snapshot.trend_exec = dc_replace(
                    snapshot.trend_exec, direction=exec_dir, strength=exec_strength
                )
            else:
                from tradebot_sci.market.models import TrendState
                snapshot.trend_exec = TrendState(direction=exec_dir, strength=exec_strength)

        trend_dir = ltf_dir if ltf_dir in ("long", "short") else htf_dir

        # Broadcast for GUI Trends tab
        try:
            trend_payload = {
                "symbol": self.symbol,
                "adx": htf_adx,
                "rsi": consensus_rsi,
                "macd": consensus_macd,
                "bollinger": consensus_bollinger,
                "supertrend": consensus_supertrend,
                "ema_ribbon": consensus_ema_ribbon,
            }
            logger.info(f"[TREND-DATA] {json.dumps(trend_payload)}")
            
            # Record Indicators for Nurse's Station
            from tradebot_sci.runtime.health_monitor import health_monitor
            ind_to_record = {}
            if getattr(self.profile, 'trend_rsi_enabled', False):
                ind_to_record["rsi"] = float(consensus_rsi) if consensus_rsi else 0.0
            if getattr(self.profile, 'trend_adx_enabled', True):
                ind_to_record["adx"] = float(htf_adx) if htf_adx else 0.0
            if getattr(self.profile, 'trend_macd_enabled', False):
                ind_to_record["macd"] = float(consensus_macd.get("histogram", 0.0)) if isinstance(consensus_macd, dict) else 1.0
            
            if ind_to_record:
                health_monitor.record_indicators(ind_to_record)
        except Exception:
            pass

        # Log consensus result
        if not is_synthetic_override and vote_sources:
            logger.info(
                f"[TREND-DETECT] {self.symbol} dir={htf_dir} "
                f"(consensus={indicator_dir}, strength={indicator_strength:.0%}) "
                f"| Votes: {', '.join(vote_sources)}"
            )

        # ── ICC Signal Detection ─────────────────────────────────────────
        sweep_signal = None
        indication_signal = None
        correction_signal = None
        continuation_signal = None

        if len(candles) >= 40:
            # When trend_dir is neutral, probe BOTH directions for structure signals.
            # ICC Core depends on sweep+correction or continuation — if these exist
            # in either direction, the strategy decides whether to trade.
            probe_dirs = [trend_dir] if trend_dir in ("long", "short") else ["long", "short"]
            for probe_dir in probe_dirs:
                try:
                    _sweep = detect_liquidity_sweep(candles, probe_dir)
                    _indication = detect_indication(candles)
                    _correction = None
                    if _indication:
                        _correction = detect_correction(candles, _indication)
                    _continuation = detect_continuation(
                        candles, probe_dir,
                        _sweep, _indication, _correction,
                        require_indication=bool(_indication),
                        require_correction=bool(_correction),
                    )
                    # Take the first direction that produces structure signals
                    has_structure = (_sweep and _correction) or _continuation
                    if has_structure or _sweep:
                        sweep_signal = _sweep
                        indication_signal = _indication
                        correction_signal = _correction
                        continuation_signal = _continuation
                        # If trend was neutral, adopt the direction from the structure
                        if trend_dir == "neutral" and has_structure:
                            trend_dir = probe_dir
                        break
                except Exception as e:
                    logger.debug(f"[ENGINE] ICC signal calc error for {self.symbol} ({probe_dir}): {e}")

        # Determine phase from signals
        phase = "range"
        if sweep_signal:
            phase = "indication" if not correction_signal else "correction"
        elif continuation_signal:
            phase = "continuation"
        elif htf_strength >= 0.4:
            phase = "trend"
        elif htf_strength < 0.15 and ltf_strength < 0.15:
            phase = "chop"

        gates = {
            "htf_dir": htf_dir,  # Enriched trend direction for strategies to follow
            "mtf_dir": mtf_dir,  # Required by exit router trend_invalidation (slow layer)
            "ltf_dir": ltf_dir,
            "exec_dir": exec_dir,
            "htf_strength": htf_strength,
            "ltf_strength": ltf_strength,
            "exec_strength": exec_strength,
            "htf_adx": htf_adx,
            # Indicator raw data (strategies can use if they want granular access)
            "indicator_dir": indicator_dir,
            "indicator_strength": indicator_strength,
            "rsi": consensus_rsi,
            "macd": consensus_macd,
            "supertrend": consensus_supertrend,
            "ema_ribbon": consensus_ema_ribbon,
            "bollinger": consensus_bollinger,
            "score": score,
            "grade": grade,
            "htf_align": htf_align,
            "phase": phase,
            "sweep": bool(sweep_signal),
            "sweep_dir": sweep_signal.direction if sweep_signal else None,
            "indication": bool(indication_signal),
            "correction": bool(correction_signal),
            "continuation": bool(continuation_signal),
            "continuation_dir": continuation_signal.direction if continuation_signal else None,
            "adx": htf_adx,
            "market_regime": market_regime,
            "is_synthetic_override": is_synthetic_override,
        }

        # Per-strategy scoring (gives each strategy its own grade)
        strat_score, strat_grade, strat_summary = self._strategy.score_signal(snapshot, gates)
        strat_name = self._strategy.name
        # Store for cycle.py to read (can't attach to Pydantic decision objects)
        self.last_strat_name = strat_name
        self.last_strat_score = strat_score
        self.last_strat_grade = strat_grade
        self.last_gates = gates

        # Pre-compute candle_now since both exit, entry, and SAR cooldown checks need it
        candle_now = None
        if snapshot.candles:
            candle_now = snapshot.candles[-1].timestamp
            if candle_now and candle_now.tzinfo is None:
                candle_now = candle_now.replace(tzinfo=ZoneInfo("UTC"))

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
            # ── Calculate position age (shared by hold guard + safety guard) ──
            # Use candle timestamps (market time) NOT wall-clock time.
            # This matches the backtester: position_age = current_candle_time - entry_time.
            # Wall-clock fails in replay (~8s per 5m candle) and gives wrong results.
            entry_time = open_position.get("entry_time")
            position_age = None
            if entry_time:
                if isinstance(entry_time, str):
                    try:
                        from datetime import datetime as dt
                        entry_time = dt.fromisoformat(entry_time.replace("Z", "+00:00"))
                    except (ValueError, TypeError, AttributeError):
                        logger.debug(f"[ENGINE] Hold Guard: failed to parse entry_time '{entry_time}'")
                if isinstance(entry_time, datetime):
                    # Use last candle timestamp as "now" — same as backtester.
                    # Falls back to current_bar_time, then wall-clock as last resort.
                    _now = candle_now or current_bar_time or (datetime.now(tz=entry_time.tzinfo) if entry_time.tzinfo else datetime.now(tz=ZoneInfo("UTC")))
                    if _now.tzinfo is None:
                        _now = _now.replace(tzinfo=ZoneInfo("UTC"))
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=ZoneInfo("UTC"))
                    position_age = (_now - entry_time).total_seconds()

            # ── HOLD GUARD ───────────────────────────────────────────────
            # Data-driven: 695 backtester trades show median=15m, avg=32m.
            # Hold for 15 minutes (3 candles on 5m) before allowing non-emergency exits.
            # This matches the backtester's natural bar-by-bar timing where trades
            # can't exit faster than one candle (5m).
            HOLD_GUARD_SECONDS = 900  # 15 minutes = median backtester trade duration
            position_is_young = (position_age is not None and position_age < HOLD_GUARD_SECONDS)

            if exit_decision:
                is_emergency = getattr(exit_decision, 'emergency_exit', False)
                if position_is_young and not is_emergency:
                    logger.info(
                        f"[HOLD GUARD] {self.symbol} strategy exit BLOCKED — "
                        f"age {position_age:.0f}s < {HOLD_GUARD_SECONDS}s "
                        f"(non-emergency exits blocked during hold). "
                        f"Reason: {getattr(exit_decision, 'notes', 'N/A')[:80]}"
                    )
                else:
                    if is_emergency and position_is_young:
                        logger.info(
                            f"[HOLD GUARD] {self.symbol} EMERGENCY EXIT allowed — "
                            f"age {position_age:.0f}s (bypassed hold guard)"
                        )
                    exit_decision.score = score
                    exit_decision.grade = grade

                    action_str = exit_decision.action.upper()
                    if action_str in ("SCALE_IN", "ADD_TO_POSITION"):
                        log_type = "PYRAMID"
                    elif action_str in ("HOLD", "STAND_ASIDE"):
                        log_type = "MANAGEMENT"
                    elif "EXIT" in action_str or "LIQUIDATE" in action_str:
                        log_type = "EXIT"
                    else:
                        log_type = "DECISION"
                        
                    logger.info(f"[ENGINE] {self.symbol} Strategy {log_type} triggered: {exit_decision.summary()}")
                    return exit_decision
            
            # [SAFETY GUARD] Augment with Safety Exits (ATR Armor, Trailing) if Strategy is silent
            # Use candle_now (same time reference as Hold Guard) so Day Enforcer
            # and other time-based checks use candle time, not wall-clock.
            _safety_sim_time = candle_now or current_bar_time
            safety_exit = SafetyGuard.augment_exit_decision(
                None, open_position, snapshot, sim_time=_safety_sim_time
            )
            
            # [WEALTH MODE] Check for "The Runner" partial exit
            if safety_exit or exit_decision:
                decision_to_check = exit_decision or safety_exit
                performance_exit = SafetyGuard.handle_runner_exit(decision_to_check, open_position)
                if performance_exit:
                    # Apply hold guard to runner exits too
                    if position_is_young:
                        logger.info(
                            f"[HOLD GUARD] {self.symbol} runner exit BLOCKED — "
                            f"age {position_age:.0f}s < {HOLD_GUARD_SECONDS}s"
                        )
                    else:
                        performance_exit.score = score
                        performance_exit.grade = grade

                        return performance_exit
            
            if safety_exit:
                # Apply hold guard to ALL safety exits — no exceptions
                if position_is_young:
                    logger.info(
                        f"[HOLD GUARD] {self.symbol} safety exit BLOCKED — "
                        f"age {position_age:.0f}s < {HOLD_GUARD_SECONDS}s "
                        f"(ALL exits blocked during hold). Reason: {getattr(safety_exit, 'notes', 'N/A')[:80]}"
                    )
                else:
                    safety_exit.score = score
                    safety_exit.grade = grade

                    return safety_exit

            # [PYRAMID CHECK] Before applying the position lock, give the strategy
            # a chance to emit a scale_in/add_to_position if it sees a new setup
            # in the SAME direction as the existing position. This allows pyramiding
            # while still protecting against flip-flopping.
            gates["profile"] = self.profile  # Pass profile for max_pyramid_entries access
            pyramid_decision = self._strategy.check_entry_signal(
                snapshot,
                gates,
                open_position=open_position,
                current_capital=current_capital,
                trade_history=history,
            )
            if pyramid_decision and pyramid_decision.action in ("scale_in", "add_to_position"):
                pyramid_decision.score = score
                pyramid_decision.grade = grade

                logger.info(f"[ENGINE] {self.symbol} PYRAMID signal: {pyramid_decision.summary()}")
                return pyramid_decision

            # [POSITION LOCK] If we have an open position and NO exit or pyramid was triggered,
            # HOLD. Do NOT fall through to entry checks. This prevents the Meta-SCI
            # tournament from flip-flopping between strategies (rubberband says long,
            # volatility says short, etc.) and bleeding capital via constant reversals.
            # The position lives or dies by its own SL/TP/exit logic.
            #
            # IMPORTANT: If the safety guard returned a hold decision with a trailing
            # stop_loss (Greedy Exit / Armor), preserve it so cycle.py can forward
            # the new stop to the broker via modify_stop_loss().
            if safety_exit and safety_exit.action == "hold" and safety_exit.stop_loss is not None:
                safety_exit.score = score
                safety_exit.grade = grade
                return safety_exit

            from tradebot_sci.strategy.decisions import stand_aside_decision
            hold = stand_aside_decision(self.symbol, timeframe, "[POSITION LOCK] Holding — position managed by SL/TP")
            hold.action = "hold"
            hold.score = score
            hold.grade = grade

            return hold

        # 4. ACCOUNT SAFETY GUARDS (My Centralized Entry Veto)
        # [CONSOLIDATED] I run all pre-entry checks (Breaker, Lockout, Greed, Churn, Veto, Streak, Sentry)
        # I run this AFTER my exit checks so that my TP/SL logic (SafetyGuard.augment_exit_decision)
        # takes priority over account-level blocks like Leverage Sentry.
        # I use the authoritative total equity from the broker layer.
        # This is cash + position value, consistent across all brokers.
        # Replaces the old ad-hoc calculation that caused capital semantics mismatch.
        total_equity = caps.get("total_equity", 0.0)
        if total_equity <= 0:
            # Fallback for legacy callers that don't pass total_equity
            total_equity = current_capital_val + caps.get("total_unrealized_pnl", 0.0)
            
        # [WAIT FOR BAR CLOSE GUARD]
        wait_for_close = getattr(self.profile, "wait_for_bar_close_enabled", False)
        if wait_for_close and snapshot.candles:
            _now = current_bar_time or datetime.now(timezone.utc)
            if _now.tzinfo is None:
                _now = _now.replace(tzinfo=timezone.utc)
            
            # The backtester uses _timeframe_to_seconds, but engine.py can just map it
            # Or use a simple mapping since timeframe is passed as a string like "5m"
            tf_seconds = 0
            tf = timeframe.lower()
            if tf.endswith("m"): tf_seconds = int(tf[:-1]) * 60
            elif tf.endswith("h"): tf_seconds = int(tf[:-1]) * 3600
            elif tf.endswith("d"): tf_seconds = int(tf[:-1]) * 86400
            
            if tf_seconds > 0:
                candle_start = snapshot.candles[-1].timestamp
                if candle_start.tzinfo is None:
                    candle_start = candle_start.replace(tzinfo=timezone.utc)
                
                # To account for slight API delays (getting the candle 1-2s late),
                # I add a small 5-second buffer grace period.
                candle_end = candle_start + timedelta(seconds=tf_seconds)
                
                # If my current time is strictly less than candle_end (minus 5s buffer),
                # the candle is still actively forming. Block entries.
                if _now < (candle_end - timedelta(seconds=5)):
                    from tradebot_sci.strategy.decisions import stand_aside_decision
                    wait_notes = f"Waiting for {timeframe} bar close. {candle_end.strftime('%H:%M:%S')} > {_now.strftime('%H:%M:%S')}"
                    logger.debug(f"[ENGINE] {self.symbol} {wait_notes}")
                    
                    wait_dec = stand_aside_decision(self.symbol, timeframe, wait_notes)
                    wait_dec.score = score
                    wait_dec.grade = grade
                    return wait_dec
        
        # (Conductor _reversal_pending pre-population removed — conductor now
        # reads gates["sar_dir"] set by engine SAR below.)
        open_symbols = caps.get("open_symbols", [])
        safety_decision = SafetyGuard.check_entry_safety(
            self.symbol, 
            timeframe, 
            total_equity,
            latest_snapshot,
            ai_client=self.ai_client,
            settings=self.settings or self.profile,
            trade_results=self.trade_results,
            open_symbols=open_symbols
        )
        if safety_decision:
            # SAR bypasses exit cooldown — reversals are time-critical.
            # Check whether engine SAR is pending for this symbol.
            is_exit_cooldown = "Exit Cooldown" in (safety_decision.notes or "")
            sar_pre = bool(getattr(self.profile, "stop_and_reverse_enabled", False))
            has_sar_pending = sar_pre and (self.symbol in self._sar_pending or self.symbol in self._cr_pending)
            if is_exit_cooldown and has_sar_pending:
                logger.info(f"[SAFETY] SAR bypass: skipping exit cooldown for {self.symbol}")
            else:
                from tradebot_sci.runtime.rejection_journal import rejection_journal
                rejection_journal.log(self.symbol, timeframe, "SafetyGuard", safety_decision.notes or "Entry blocked")
                logger.info(f"[SAFETY] Entry Blocked for {self.symbol}: {safety_decision.notes}")
                return safety_decision

        # ── ENGINE-LEVEL SAR + CR (Stop-and-Reverse / Counter-Reversal) ──
        # Detect recent stop exits and set reversal direction.
        # Excluded for tournament strategies that handle SAR internally.
        sar_dir = None  # Will be "long" or "short" if SAR should fire
        sar_enabled = bool(getattr(self.profile, "stop_and_reverse_enabled", False))
        cr_enabled  = bool(getattr(self.profile, "counter_reversal_enabled", False))
        max_consec  = int(getattr(self.profile, "max_consecutive_sar", 1))
        if sar_enabled and self._variant_key not in self._SAR_EXCLUDED:
            _nothing_pending = (
                self.symbol not in self._sar_pending and
                self.symbol not in self._cr_pending
            )
            if _nothing_pending:
                # Scan trade_history for the most recent trade on this symbol
                if history:
                    for t in reversed(history):  # newest first
                        if t.get("symbol") != self.symbol:
                            continue
                        # Dedup: skip if we already processed this exact trade
                        _exit_key = str(t.get("exit_time", ""))
                        if _exit_key and _exit_key == self._sar_last_processed.get(self.symbol):
                            break  # Same trade as last scan — nothing new

                        # ── STALENESS CHECK ──────────────────────────────
                        # SAR only makes sense for RECENT exits. On every bot restart
                        # _sar_last_processed is empty, so without this check my
                        # scanner re-processes weeks-old SAR losses and immediately
                        # triggers a cooldown that perma-blocks the symbol.
                        # I ignore trades older than 24 hours — by then the market has
                        # moved on and a reversal entry would be stale.
                        import datetime as _dt_sar
                        _exit_ts_str = t.get("exit_time") or t.get("closed_at") or ""
                        try:
                            if _exit_ts_str:
                                _exit_ts = _dt_sar.datetime.fromisoformat(str(_exit_ts_str).replace("Z", "+00:00"))
                                _sar_now = candle_now or _dt_sar.datetime.now(_dt_sar.timezone.utc)
                                if _sar_now.tzinfo is None:
                                    _sar_now = _sar_now.replace(tzinfo=_dt_sar.timezone.utc)
                                _age_hours = (_sar_now - _exit_ts).total_seconds() / 3600
                                if _age_hours > 24:
                                    # This trade is stale — mark as processed and skip
                                    self._sar_last_processed[self.symbol] = _exit_key
                                    break
                        except (ValueError, TypeError):
                            pass  # If we can't parse the time, proceed normally

                        is_loss = (not t.get("is_win", True)) or (t.get("pnl_usd", 0) < 0)
                        if not is_loss:
                            break  # last trade was a win — no reversal needed
                        old_side  = (t.get("side") or "").lower()
                        trade_stg = (t.get("strategy") or t.get("strategy_name") or "").lower()
                        is_sar_loss = "reversal" in trade_stg and "counter" not in trade_stg

                        if is_sar_loss and cr_enabled:
                            # ── COUNTER-REVERSAL: SAR itself failed ───────────
                            if old_side == "long":
                                self._cr_pending[self.symbol] = "long"
                            elif old_side == "short":
                                self._cr_pending[self.symbol] = "short"
                            if self.symbol in self._cr_pending:
                                logger.info(
                                    f"[ENGINE CR] {self.symbol}: SAR FAILED → "
                                    f"counter-reversal pending {self._cr_pending[self.symbol]}"
                                )
                        elif is_sar_loss:
                            # ── CONSECUTIVE SAR LOSS GUARD ───────────────────
                            # Increment incremental counter (no re-scan needed)
                            import datetime as _dt
                            _sim_time = candle_now or current_bar_time or _dt.datetime.now(_dt.timezone.utc)
                            if _sim_time.tzinfo is None:
                                _sim_time = _sim_time.replace(tzinfo=_dt.timezone.utc)

                            consec = self._sar_consec_losses.get(self.symbol, 0) + 1
                            self._sar_consec_losses[self.symbol] = consec
                            if consec >= max_consec:
                                cooldown_h = float(getattr(self.profile, "sar_cooldown_hours", 4.0))
                                self._sar_cooldown_until[self.symbol] = (
                                    _sim_time + _dt.timedelta(hours=cooldown_h)
                                )
                                logger.warning(
                                    f"[ENGINE SAR] {self.symbol}: {consec} consecutive SAR losses — "
                                    f"cooldown {cooldown_h}h (max_consecutive_sar={max_consec})"
                                )
                            else:
                                if old_side == "long":
                                    self._sar_pending[self.symbol] = "short"
                                elif old_side == "short":
                                    self._sar_pending[self.symbol] = "long"
                                if self.symbol in self._sar_pending:
                                    logger.info(
                                        f"[ENGINE SAR] {self.symbol}: LOSS DETECTED → "
                                        f"reversal pending {self._sar_pending[self.symbol]}"
                                    )
                        else:
                            # ── Standard SAR (non-SAR loss = first loss in streak) ──
                            # Reset consecutive counter since this isn't a SAR loss
                            self._sar_consec_losses[self.symbol] = 0
                            if old_side == "long":
                                self._sar_pending[self.symbol] = "short"
                            elif old_side == "short":
                                self._sar_pending[self.symbol] = "long"
                            if self.symbol in self._sar_pending:
                                logger.info(
                                    f"[ENGINE SAR] {self.symbol}: LOSS DETECTED → "
                                    f"reversal pending {self._sar_pending[self.symbol]}"
                                )
                        # Mark this trade as processed so it won't be re-scanned.
                        self._sar_last_processed[self.symbol] = _exit_key
                        break
                    else:
                        # Last trade was a win — reset consecutive SAR loss counter
                        self._sar_consec_losses[self.symbol] = 0

            # ── SAR COOLDOWN CHECK ──────────────────────────────────
            import datetime as _dt
            block_until = self._sar_cooldown_until.get(self.symbol)
            _sim_time = candle_now or current_bar_time or _dt.datetime.now(_dt.timezone.utc)
            if _sim_time.tzinfo is None:
                _sim_time = _sim_time.replace(tzinfo=_dt.timezone.utc)
                
            if block_until and _sim_time < block_until:
                rem = (block_until - _sim_time).total_seconds() / 60
                logger.info(
                    f"[ENGINE SAR] {self.symbol}: BLOCKED — spiral cooldown, "
                    f"{rem:.0f}m remaining"
                )
                self._sar_pending.pop(self.symbol, None)  # discard any stale pending
                sar_dir = None

            # Read and consume pending reversal (SAR takes priority; CR is secondary)
            sar_dir = self._sar_pending.pop(self.symbol, None)
            if sar_dir is None and cr_enabled:
                sar_dir = self._cr_pending.pop(self.symbol, None)
                if sar_dir:
                    logger.info(f"[ENGINE CR] {self.symbol}: firing counter-reversal {sar_dir}")

            # ── TREND-AWARE SAR GUARD ─────────────────────────────────────
            # Block SAR if it forces a trade against a strong HTF trend.
            if sar_dir:
                htf_dir = gates.get("htf_dir", "neutral")
                htf_strength = gates.get("htf_strength", 0.0)
                if htf_dir in ("long", "short") and htf_strength >= 0.5:
                    if sar_dir != htf_dir:
                        logger.warning(
                            f"[ENGINE SAR] {self.symbol}: CANCELED — SAR direction {sar_dir.upper()} "
                            f"opposes strong HTF trend ({htf_dir.upper()}, strength={htf_strength:.0%})"
                        )
                        sar_dir = None

        # B. Check for ENTRY / SCALE_IN
        # Pass sar_dir via gates so conductor can compute ATR-based SL/TP
        # for the forced reversal entry rather than relying on None SL/TP.
        gates["profile"] = self.profile
        gates["sar_dir"] = sar_dir  # None if no SAR pending
        decision = self._strategy.check_entry_signal(
            snapshot,
            gates,
            open_position=open_position,
            current_capital=current_capital,
            trade_history=history
        )

        # ── SAR Direction Enforcement / Forced Entry ─────────────────
        if sar_dir:
            if decision and decision.action in ("enter_long", "enter_short"):
                # Strategy returned a signal — enforce SAR direction
                signal_dir = "long" if decision.action == "enter_long" else "short"
                if signal_dir != sar_dir:
                    logger.info(
                        f"[ENGINE SAR] {self.symbol}: Strategy signal {signal_dir} "
                        f"rejected — SAR requires {sar_dir}"
                    )
                    decision = None  # Will fall through to forced entry below
                else:
                    # Strategy agrees with SAR direction — tag it
                    decision.notes = f"[SAR] {decision.notes or ''}"
                    logger.info(
                        f"[ENGINE SAR] {self.symbol}: Strategy agrees with "
                        f"SAR direction ({sar_dir}) — entry confirmed"
                    )

            if decision is None or decision.action in ("stand_aside", "hold"):
                # Strategy (e.g. conductor) didn't produce a valid entry.
                # Fall back to engine-level forced SAR, calculating ATR for SL.
                _explicit_sar_risk = float(getattr(self.profile, "reversal_risk_per_trade", 0) or 0)
                if _explicit_sar_risk > 0:
                    rev_risk = _explicit_sar_risk
                else:
                    _scale_out = float(getattr(self.profile, "scale_out_fraction", 0.95))
                    _base_risk = float(getattr(self.profile, "risk_per_trade_pct", 0.01))
                    rev_risk = (1.0 - _scale_out) * _base_risk
                    if rev_risk <= 0:
                        rev_risk = 0.01

                rev_action = "enter_long" if sar_dir == "long" else "enter_short"
                
                # Calculate SL/TP using ATR
                price = snapshot.candles[-1].close if snapshot.candles else 0.0
                sl = None
                tp = None
                if price > 0 and snapshot.candles and len(snapshot.candles) >= 15:
                    try:
                        from tradebot_sci.strategy.icc_signals import calculate_atr
                        atr = calculate_atr(snapshot.candles[-30:], period=14)
                        if atr and atr > 0:
                            is_jpy = "JPY" in self.symbol.upper()
                            min_sl_dist = 15 * (0.01 if is_jpy else 0.0001)
                            stop_dist = max(atr * 1.5, min_sl_dist)
                            tp_r = float(getattr(self.profile, "reversal_tp_r", 1.0))
                            tp_dist = stop_dist * tp_r
                            
                            if sar_dir == "long":
                                sl = price - stop_dist
                                tp = price + tp_dist
                            else:
                                sl = price + stop_dist
                                tp = price - tp_dist
                    except Exception as e:
                        logger.warning(f"[ENGINE SAR] failed to calculate ATR for SL/TP: {e}")

                if sl is None:
                    # Fallback if ATR fails (1% / 2%) so safety checking doesn't crash
                    sl = price * 0.99 if sar_dir == "long" else price * 1.01
                    tp = price * 1.02 if sar_dir == "long" else price * 0.98

                logger.info(
                    f"[ENGINE SAR] {self.symbol}: Forcing {rev_action} "
                    f"(risk={rev_risk*100:.1f}%, sl={sl:.5f}, tp={tp:.5f}) — strategy produced no SAR entry"
                )
                decision = AITradeDecision(
                    symbol=self.symbol,
                    timeframe=timeframe,
                    bias=sar_dir,
                    phase="correction",
                    action=rev_action,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    risk_per_trade_pct=rev_risk,
                    urgency="high",
                    structure_summary=f"[SAR] Stop-and-Reverse: forced {sar_dir} after stop exit",
                    notes=f"[SAR] Automatic reversal entry ({self._strategy.name})",
                )
                decision.score = score
                decision.grade = grade
            elif decision.stop_loss is not None:
                # Strategy produced its own ATR-based SL/TP (e.g. Conductor).
                # Keep it — just tag it as a SAR entry.
                logger.info(
                    f"[ENGINE SAR] {self.symbol}: Using strategy ATR SL/TP for SAR "
                    f"({sar_dir}, sl={decision.stop_loss:.5f})"
                )

        if decision:
            decision.score = strat_score
            decision.grade = strat_grade

            # [META-SCI] Propagate the winning sub-strategy name (e.g. "bullish_trending")
            # so the GUI shows the actual strategy instead of the conglomerate "meta_sci".
            meta_src = (getattr(decision, 'gates', None) or {}).get('meta_source')
            if meta_src:
                self.last_strat_name = meta_src


            # Counter-Trend Entry Block
            # Prevents going long when HTF is bearish, or short when HTF is bullish.
            # SAR reversals bypass this — the whole point is to trade against the prior direction.
            # Counter-trend strategies are also exempt, as they hunt pullbacks and sweeps autonomously.
            htf_dir = gates.get("htf_dir", "neutral")
            ltf_dir = gates.get("ltf_dir", "neutral")
            exec_dir = gates.get("exec_dir", "neutral")
            
            is_sar_reversal = "[REVERSAL]" in (decision.notes or "")
            
            # Explicitly whitelist known counter-trend / mean-reverting algorithms
            counter_tags = (
                "mean_reversion", "londonsweep", "london_sweep", "goldenpocket", "golden_pocket", 
                "newyorkdrive", "new_york_drive", "counter", "reversal", "rubberband", "choppiness", "supply_demand", "yoyo"
            )
            is_counter_trend_strat = any(tag.lower() in (decision.strategy_name or "").lower() for tag in counter_tags)
            
            if getattr(self.profile, "block_counter_trend_entries", True) and decision.action in ("enter_long", "enter_short", "scale_in") and not is_sar_reversal and not is_counter_trend_strat:
                # Determine effective direction for scale_in from existing position
                effective_action = decision.action
                if decision.action == "scale_in" and open_position:
                    pos_size = open_position.get("size", 0)
                    effective_action = "enter_long" if pos_size > 0 else "enter_short"
                
                # Check Triple-Timeframe Alignment: All three timeframes MUST explicitly agree with the entry direction
                req_dir = "long" if effective_action == "enter_long" else "short"
                triple_aligned = (htf_dir == req_dir and ltf_dir == req_dir and exec_dir == req_dir)
                
                if not triple_aligned:
                    reason = f"Triple-Timeframe Blocked: {effective_action} violates alignment (HTF={htf_dir}, LTF={ltf_dir}, EXEC={exec_dir})"
                    logger.info(f"[TREND_GUARD] {self.symbol} {reason}")
                    from tradebot_sci.strategy.decisions import stand_aside_decision
                    from tradebot_sci.runtime.rejection_journal import rejection_journal
                    rejection_journal.log(self.symbol, timeframe, "TrendGuard", reason)
                    blocked = stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)
                    blocked.score = score
                    blocked.grade = grade

                    return blocked

            # ── CHOP-PHASE ENTRY REJECTION ────────────────────────────
            # If both HTF and LTF trend strengths are weak (< 0.15), OR
            # if ADX is too low (< 20.0), the market lacks conviction/volatility.
            # Entries during chop get stopped at ~40% rate. Block them.
            # SAR entries bypass this (they're reactive, not structural).
            is_sar_entry = decision.notes and "[SAR]" in decision.notes
            if not is_sar_entry and decision.action in ("enter_long", "enter_short"):
                htf_str = gates.get("htf_strength", 0.0)
                ltf_str = gates.get("ltf_strength", 0.0)
                htf_adx = gates.get("htf_adx", 0.0)
                
                is_conflicted = htf_str < 0.15 and ltf_str < 0.15
                
                if is_conflicted:
                    reason = f"Chop Filter: Trend Str Conflicts Str={htf_str:.2f}/{ltf_str:.2f}"
                    logger.info(f"[CHOP_GUARD] {self.symbol} {reason}")
                    from tradebot_sci.strategy.decisions import stand_aside_decision
                    from tradebot_sci.runtime.rejection_journal import rejection_journal
                    rejection_journal.log(self.symbol, timeframe, "ChopGuard", reason)
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
                settings=self.settings or self.profile
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
                    # Use Global Aggregation across all Brokers (Forex + Crypto)
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

            # Note: Churn Burner notification moved to cycle.py (after confirmed execution)
            # Previously here, it counted every entry SIGNAL as a trade, causing false churn blocks.

            # [FEE SHIELD] Capital Bleed Prevention (moved from safety_guard.py where it was dead code)
            # Validates that the trade has enough reward to cover broker fees before execution.
            safety = getattr(self.settings or self.profile, 'safety', None)
            if safety and getattr(safety, 'safety_fee_shield_enabled', False):
                entry = float(decision.entry_price or 0.0)
                tp = float(decision.take_profit or 0.0)
                if entry > 0 and tp > 0:
                    potential_reward_pct = abs(tp - entry) / entry
                    from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
                    import os
                    safety_pct = getattr(safety, 'safety_fee_rt_pct', None)
                    if safety_pct is not None:
                        env_override = float(safety_pct) / 100.0
                    else:
                        env_override = float(os.environ["SAFETY_FEE_RT_PCT"]) / 100.0 if "SAFETY_FEE_RT_PCT" in os.environ else None
                    est_fee_rt = get_fee_for_symbol(self.symbol, override=env_override)
                    min_edge_pct = est_fee_rt * 1.5
                    if potential_reward_pct < min_edge_pct:
                        logger.warning(f"[FEE SHIELD] {self.symbol} Reward {potential_reward_pct:.2%} < Min Edge {min_edge_pct:.2%} (Fees)")
                        from tradebot_sci.strategy.decisions import stand_aside_decision
                        from tradebot_sci.runtime.rejection_journal import rejection_journal
                        rejection_journal.log(self.symbol, timeframe, "Fee Shield", f"Reward {potential_reward_pct:.2%} < Fees {min_edge_pct:.2%}")
                        blocked = stand_aside_decision(snapshot.symbol, timeframe, f"Fee Shield: Reward {potential_reward_pct:.2%} < Fees")
                        blocked.score = score
                        blocked.grade = grade
                        return blocked

            logger.info(f"[ENGINE] {self.symbol} Strategy {decision.action.upper()} triggered: {decision.summary()}")
            # 4. Final Safety Patch (Margin/Venue Only)
            return validate_decision(decision, execution_capabilities=caps)

        # 5. Default: Stand Aside
        # Generate dynamic reason based on market context
        adx = gates.get("htf_adx", 0.0)
        phase = gates.get("phase", "range")

        if adx > 0 and adx < 20:
            reason = "Volume is dead. Price is just wandering sideways."
        elif phase == "chop":
            reason = "Market is too choppy and unpredictable to risk capital."
        elif phase == "range" and strat_score < 40:
            reason = "Price is trapped in a tight range. Waiting for a breakout."
        elif strat_score >= 75:
            reason = "High-grade setup detected. Stalking an optimal sniper entry."
        elif strat_score >= 65:
            reason = "Setup is developing nicely; waiting for final confirmation trigger."
        elif strat_score >= 55:
            reason = "Strong structure present, waiting for a safe pullback to complete."
        elif strat_score >= 45:
            reason = "Mixed signals across timeframes. Waiting for clear alignment."
        elif strat_score >= 30:
            reason = "Mediocre setup. Missing the momentum needed for a safe entry."
        elif strat_score >= 20:
            reason = "Trend is present, but current price action is unconvincing."
        else:
            reason = "No viable setups. Market conditions are completely poor."

        from tradebot_sci.strategy.decisions import stand_aside_decision
        decision = stand_aside_decision(snapshot.symbol, timeframe, reason)
        decision.score = strat_score / 100.0  # Normalize to 0-1 (cycle.py × 100 for display)
        decision.grade = strat_grade

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
