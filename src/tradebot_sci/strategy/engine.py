from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Any

from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import AITradeDecision
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
        
        # Load the Strategy Variant
        self._strategy = self._load_strategy_variant()
        
        # Propagate profile risk to the strategy
        risk_pct = getattr(self.profile, 'risk_per_trade_pct', None)
        if risk_pct and hasattr(self._strategy, 'profile_risk_pct'):
            self._strategy.profile_risk_pct = float(risk_pct)
        
        logger.info(f" [PHOENIX] === ENGINE LOADED === Symbol: {symbol} | Variant: {self._strategy.name.upper()} ")

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
        "supply_demand":        ("tradebot_sci.strategy.variants.supply_demand",         "SupplyDemandStrategy"),
        "meta_sci":             ("tradebot_sci.strategy.variants.meta_sci",             "MetaSCIStrategy"),
        "trend_rider":          ("tradebot_sci.strategy.variants.trend_rider",          "TrendRiderStrategy"),
        "session_momentum":     ("tradebot_sci.strategy.variants.session_momentum",     "SessionMomentumStrategy"),
        "bearish_engulfing":    ("tradebot_sci.strategy.variants.bearish_engulfing",    "BearishEngulfingStrategy"),
        "hyper_scalper":        ("tradebot_sci.strategy.variants.hyper_scalper",        "HyperScalperStrategy"),
        "orb_breakout":         ("tradebot_sci.strategy.variants.orb_breakout",         "ORBStrategy"),
        "quantum":              ("tradebot_sci.strategy.variants.quantum",              "QuantumStrategy"),
        "mean_reversion":       ("tradebot_sci.strategy.variants.mean_reversion",       "MeanReversionStrategy"),
        "crypto_rsi_macd":      ("tradebot_sci.strategy.variants.crypto_rsi_macd",      "CryptoRSIMACDStrategy"),
        "crypto_vwap_reversion":("tradebot_sci.strategy.variants.crypto_vwap_reversion","CryptoVWAPReversionStrategy"),
        "crypto_double_macd":   ("tradebot_sci.strategy.variants.crypto_double_macd",   "CryptoDoubleMACDStrategy"),
        "crypto_grid":          ("tradebot_sci.strategy.variants.crypto_grid",          "CryptoGridStrategy"),
        "aggregator":           ("tradebot_sci.strategy.variants.aggregator",           "AggregatorStrategy"),
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
        # MetaSCIStrategy requires profile_settings kwarg
        if variant == "meta_sci":
            return cls(profile_settings=self.profile)
        return cls()

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
        
        # Derive htf_align: True if HTF and LTF agree, or HTF is neutral with LTF directional
        htf_dir = str(snapshot.trend_htf.direction).lower()
        ltf_dir = str(snapshot.trend_ltf.direction).lower()
        htf_strength = round(float(snapshot.trend_htf.strength or 0.0), 3)
        ltf_strength = round(float(snapshot.trend_ltf.strength or 0.0), 3)

        # HTF alignment: either HTF agrees with LTF, or HTF is neutral but LTF has conviction
        htf_align = False
        if htf_dir in ("long",) and ltf_dir in ("long",):
            htf_align = True
        elif htf_dir in ("short",) and ltf_dir in ("short",):
            htf_align = True
        elif htf_dir == "neutral" and ltf_strength >= 0.3:
            # HTF neutral but LTF has structure — allow entry (vanilla ICC rule)
            htf_align = True

        # Compute ICC structure signals from candle data
        from tradebot_sci.strategy.icc_signals import (
            detect_liquidity_sweep, detect_indication,
            detect_correction, detect_continuation,
        )
        candles = snapshot.candles or []
        trend_dir = ltf_dir if ltf_dir in ("long", "short") else htf_dir

        # ── Trend Indicator Gates ─────────────────────────────────────────
        # Each enabled indicator acts as an independent entry filter.
        # Indicators are always computed (for GUI broadcast) but only gate
        # entries when their toggle is enabled in the Settings → Trends tab.
        from tradebot_sci.market.trend import (
            compute_adx, compute_rsi, compute_macd, compute_bollinger,
            compute_supertrend, compute_ema_ribbon,
        )

        # Compute ADX directly from candles (snapshot.trend_htf.adx can be stale/zero)
        htf_adx = round(compute_adx(candles), 1) if len(candles) >= 15 else 0.0
        adx_threshold = float(getattr(self.profile, 'adx_gate_threshold', 20))

        # Compute all indicators (always, for TREND-DATA broadcast)
        rsi_val = compute_rsi(candles) if len(candles) >= 15 else 50.0
        macd_data = compute_macd(candles) if len(candles) >= 35 else {"macd": 0, "signal": 0, "histogram": 0}
        boll_data = compute_bollinger(candles) if len(candles) >= 20 else {"upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "squeeze": False}
        st_data = compute_supertrend(candles) if len(candles) >= 11 else {"direction": "neutral", "value": 0}
        ema_data = compute_ema_ribbon(candles) if len(candles) >= 55 else {"ema8": 0, "ema21": 0, "ema55": 0, "aligned": False, "direction": "neutral"}

        # Broadcast for GUI Trends tab
        try:
            trend_payload = {
                "symbol": self.symbol,
                "adx": htf_adx,
                "rsi": rsi_val,
                "macd": macd_data,
                "bollinger": boll_data,
                "supertrend": st_data,
                "ema_ribbon": ema_data,
            }
            logger.info(f"[TREND-DATA] {json.dumps(trend_payload)}")
        except Exception:
            pass

        # ── Apply gates (only when enabled) ──────────────────────────────
        trend_vetoes = []  # Collect veto reasons

        # ADX: block if no trend strength
        adx_gate_passed = True
        if getattr(self.profile, 'trend_adx_enabled', True):
            adx_gate_passed = htf_adx >= adx_threshold
            if not adx_gate_passed and trend_dir in ("long", "short"):
                trend_vetoes.append(f"ADX={htf_adx:.1f}<{adx_threshold:.0f}")

        # RSI: block counter-momentum entries
        rsi_gate_passed = True
        if getattr(self.profile, 'trend_rsi_enabled', False):
            if trend_dir == "long" and rsi_val >= 80:
                rsi_gate_passed = False
                trend_vetoes.append(f"RSI={rsi_val:.0f} overbought")
            elif trend_dir == "short" and rsi_val <= 20:
                rsi_gate_passed = False
                trend_vetoes.append(f"RSI={rsi_val:.0f} oversold")

        # MACD: block if histogram disagrees with direction
        macd_gate_passed = True
        if getattr(self.profile, 'trend_macd_enabled', False):
            hist = macd_data.get("histogram", 0)
            if trend_dir == "long" and hist < 0:
                macd_gate_passed = False
                trend_vetoes.append(f"MACD histogram={hist:.5f} bearish")
            elif trend_dir == "short" and hist > 0:
                macd_gate_passed = False
                trend_vetoes.append(f"MACD histogram={hist:.5f} bullish")

        # Bollinger: block during squeeze (ambiguous market)
        boll_gate_passed = True
        if getattr(self.profile, 'trend_bollinger_enabled', False):
            if boll_data.get("squeeze", False):
                boll_gate_passed = False
                trend_vetoes.append(f"Bollinger SQUEEZE bw={boll_data.get('bandwidth', 0):.2f}")

        # Supertrend: block if direction disagrees
        st_gate_passed = True
        if getattr(self.profile, 'trend_supertrend_enabled', False):
            st_dir = st_data.get("direction", "neutral")
            if trend_dir in ("long", "short") and st_dir != trend_dir:
                st_gate_passed = False
                trend_vetoes.append(f"Supertrend={st_dir} vs {trend_dir}")

        # EMA Ribbon: block if tangled (no alignment)
        ema_gate_passed = True
        if getattr(self.profile, 'trend_ema_ribbon_enabled', False):
            if not ema_data.get("aligned", False):
                ema_gate_passed = False
                trend_vetoes.append(f"EMA Ribbon tangled")
            elif ema_data.get("direction") != trend_dir and trend_dir in ("long", "short"):
                ema_gate_passed = False
                trend_vetoes.append(f"EMA Ribbon={ema_data.get('direction')} vs {trend_dir}")

        # Log vetoes for monitoring (no hard block — strategies enforce direction)
        if trend_vetoes and trend_dir in ("long", "short"):
            logger.info(
                f"[TREND-GATE] {self.symbol} {trend_dir} entry has vetoes — "
                + " | ".join(trend_vetoes)
            )

        # ── ICC Signal Detection ─────────────────────────────────────────
        sweep_signal = None
        indication_signal = None
        correction_signal = None
        continuation_signal = None

        if len(candles) >= 40 and trend_dir in ("long", "short"):
            try:
                sweep_signal = detect_liquidity_sweep(candles, trend_dir)
                indication_signal = detect_indication(candles)
                if indication_signal:
                    correction_signal = detect_correction(candles, indication_signal)
                continuation_signal = detect_continuation(
                    candles, trend_dir,
                    sweep_signal,
                    indication_signal,
                    correction_signal,
                    require_indication=bool(indication_signal),
                    require_correction=bool(correction_signal),
                )
            except Exception as e:
                logger.debug(f"[ENGINE] ICC signal calc error for {self.symbol}: {e}")

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
            "htf_dir": htf_dir,  # Original trend direction for strategies to follow
            "ltf_dir": ltf_dir,
            "htf_strength": htf_strength,
            "ltf_strength": ltf_strength,
            "htf_adx": htf_adx,
            "adx_gate": adx_gate_passed,
            "rsi_gate": rsi_gate_passed,
            "macd_gate": macd_gate_passed,
            "boll_gate": boll_gate_passed,
            "st_gate": st_gate_passed,
            "ema_gate": ema_gate_passed,
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
        }

        # Per-strategy scoring (gives each strategy its own grade)
        strat_score, strat_grade, strat_summary = self._strategy.score_signal(snapshot, gates)
        strat_name = self._strategy.name
        # Store for cycle.py to read (can't attach to Pydantic decision objects)
        self.last_strat_name = strat_name
        self.last_strat_score = strat_score
        self.last_strat_grade = strat_grade

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
                # [CHURN GUARD] Block non-emergency strategy exits for young positions.
                # Prevents strategies from contradicting their own entry within 30-40s.
                entry_time = open_position.get("entry_time")
                position_age = None
                if entry_time:
                    if isinstance(entry_time, str):
                        try:
                            from datetime import datetime as dt
                            entry_time = dt.fromisoformat(entry_time.replace("Z", "+00:00"))
                        except (ValueError, TypeError, AttributeError):
                            logger.debug(f"[ENGINE] Churn Guard: failed to parse entry_time '{entry_time}'")
                    if isinstance(entry_time, datetime):
                        now = datetime.now(tz=entry_time.tzinfo) if entry_time.tzinfo else datetime.now(tz=ZoneInfo("UTC"))
                        position_age = (now - entry_time).total_seconds()

                is_emergency = getattr(exit_decision, 'emergency_exit', False)
                if position_age is not None and position_age < 120 and not is_emergency:
                    logger.debug(
                        f"[ENGINE] Churn Guard: {self.symbol} strategy exit blocked — "
                        f"position age {position_age:.0f}s < 120s minimum"
                    )
                else:
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

                logger.info(f"[PHOENIX] {self.symbol} PYRAMID signal: {pyramid_decision.summary()}")
                return pyramid_decision

            # [POSITION LOCK] If we have an open position and NO exit or pyramid was triggered,
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
        # Use the authoritative total equity from the broker layer.
        # This is cash + position value, consistent across all brokers.
        # Replaces the old ad-hoc calculation that caused capital semantics mismatch.
        total_equity = caps.get("total_equity", 0.0)
        if total_equity <= 0:
            # Fallback for legacy callers that don't pass total_equity
            total_equity = current_capital_val + caps.get("total_unrealized_pnl", 0.0)
        
        safety_decision = SafetyGuard.check_entry_safety(
            self.symbol, 
            timeframe, 
            total_equity,
            latest_snapshot,
            ai_client=self.ai_client,
            settings=self.settings or self.profile,
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


            # Counter-Trend Entry Block
            # Prevents going long when HTF is bearish, or short when HTF is bullish.
            htf_dir = gates.get("htf_dir", "neutral")
            if getattr(self.profile, "block_counter_trend_entries", True) and decision.action in ("enter_long", "enter_short", "scale_in"):
                # Determine effective direction for scale_in from existing position
                effective_action = decision.action
                if decision.action == "scale_in" and open_position:
                    pos_size = open_position.get("size", 0)
                    effective_action = "enter_long" if pos_size > 0 else "enter_short"
                
                is_counter_trend = (
                    (htf_dir == "short" and effective_action == "enter_long")
                    or (htf_dir == "long" and effective_action == "enter_short")
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
                    env_override = float(os.environ["SAFETY_FEE_RT_PCT"]) if "SAFETY_FEE_RT_PCT" in os.environ else None
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
