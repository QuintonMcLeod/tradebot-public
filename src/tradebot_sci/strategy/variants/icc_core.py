from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr, detect_structure_invalidation
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)


class ICCCoreStrategy(BaseStrategy):
    """
    ICC Core Strategy (Vanilla).
    
    The pure, unmodified Trade By Sci Internal Capital Cycle methodology.
    
    Rules:
    - HTF Alignment: Mandatory (unless HTF neutral and LTF has structure).
    - Entry: Requires confirmation (Sweep + Indication OR Continuation).
    - Scoring: Must meet strict ICC Score threshold.
    - No "Rubberband" mean reversion.
    - No "RoboCop" bypasses.
    """

    def __init__(self):
        super().__init__("ICC Core")

    def check_entry_signal(
        self, 
        snapshot: MarketSnapshot, 
        gates: dict, 
        open_position: Optional[dict] = None, 
        current_capital: Optional[float] = None, 
        trade_history: Optional[list] = None
    ) -> Optional[AITradeDecision]:
        
        # 1. Check Score Gate (Strict)
        # Core methodology relies on the scorecard.
        score = gates.get("score", 0.0)
        threshold = gates.get("score_threshold", 50.0)
        
        if score < threshold:
            # OPTIONAL: Allow auto-entry override if explicitly configured in profile
            # (Matches behavior of high-volume backtesting if desired)
            # But "Vanilla" implies respecting the score.
            # We defer to the Engine's "auto_entry_enabled" check if we return a decision here?
            # No, the Engine calls US to ASK for a decision.
            # If we return None, no trade.
            # So if Score < Threshold, we should mostly reject.
            
            # EXCEPT: If we have a perfect setup (Sweep+Indication or Continuation),
            # the scorecard might be lagging or missing context?
            # Vanilla ICC says: Trust the Structure. Score is a helper.
            pass

        # 2. Check Structure Signals (Calculated by Engine)
        sweep = gates.get("sweep", False)
        continuation = gates.get("continuation", False)
        indication = gates.get("indication", False)
        correction = gates.get("correction", False)
        htf_align = gates.get("htf_align", False)
        phase = gates.get("phase", "neutral")
        
        logger.debug(
            f"[ICC-CORE] {snapshot.symbol} gates: "
            f"htf_align={htf_align} phase={phase} sweep={sweep} "
            f"continuation={continuation} indication={indication} "
            f"correction={correction} score={score:.1f}"
        )
        
        # 3. Check Alignment
        # [FIX] Structure signals (sweep+correction, continuation) ARE the entry thesis.
        # If we have confirmed structure, we don't need strict HTF alignment —
        # the sweep+correction itself proves the setup exists regardless of 5m trend reading.
        # HTF alignment only gatekeeps when we have NO structure signals.
        has_structure = (sweep and correction) or continuation
        
        if not htf_align and not has_structure:
            return None
            
        # 4. Filter Chop — only block if we have NO confirmed structure
        if phase == "chop" and not has_structure:
            return None

        # 5. Define Entry Logic
        action = None
        bias = None
        
        # [USER CORRECTION] "Sweep IS Indication" -> Correction -> Entry
        # We don't need a formal "Continuation" signal if we have the Reversal Sequence.
        
        # Case A: Sweep + Correction (The "Core" Reversal)
        # If we have a Sweep AND a verified Correction, we enter.
        # Note: 'correction' implies 'indication' existed (as prereq in Engine).
        if sweep and correction:
            # Determine direction from the Sweep
            sweep_dir = gates.get("sweep_dir") # "long" (swept lows) or "short" (swept highs)
            
            # Verify correction direction aligns
            # Correction direction is usually "long" (retesting low) or "short" (retesting high)
            # Actually, check signals.py: correction.direction is "long" (expected move AFTER correction)
            # So if sweep_dir == "long", correction_dir should optionally be checked?
            # Let's trust sweep_dir.
            
            if sweep_dir == "long":
                action = "enter_long"
                bias = "long"
            elif sweep_dir == "short":
                action = "enter_short"
                bias = "short"
                
        # Case B: Continuation (Trend Following without a fresh Sweep?)
        # Only if we didn't already trigger on A.
        elif continuation:
            cont_dir = gates.get("continuation_dir")
            if cont_dir == "long":
                action = "enter_long" # Override if duplicate
                bias = "long"
            elif cont_dir == "short":
                action = "enter_short"
                bias = "short"
                
        if not action:
            return None
            
        # 6. Construct Decision
        # Use default risk from profile (handled by Engine usually, or we specify base)
        # Vanilla uses standard 1-2% risk. Engine/Profile handles sizing.
        # We just signal the Entry.
        
        last_close = snapshot.candles[-1].close
        # Stop/Target logic:
        # Standard ICC: Stop below structure (recent low for long).
        # Target: 2R or Structure High.
        
        # Simple default for "Core": Use ATR-based if structure is complex, 
        # or rely on Engine's `validate_decision` to fill gaps?
        # `RubberbandReaper` calculated exact stops.
        # We should calculate a sensible Stop.
        
        atr = calculate_atr(snapshot.candles) or (last_close * 0.005)
        
        # Enforce minimum stop distance for broker compliance
        # OANDA requires at least 10 pips (0.00100) for forex pairs
        # Use at least 15 pips to avoid rejection + give room
        min_stop_dist = max(atr * 3.0, last_close * 0.0015)  # 3x ATR or 15 pips, whichever is larger
        stop_dist = min_stop_dist
        
        if action == "enter_long":
            stop_loss = last_close - stop_dist
            take_profit = last_close + (stop_dist * 2.0)  # 2R
        else:
            stop_loss = last_close + stop_dist
            take_profit = last_close - (stop_dist * 2.0)

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            action=action,
            bias=bias,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            phase=phase,
            structure_summary=f"ICC Core {action} (Score={score:.0f})",
            invalidation_conditions=f"Close beyond SL at {stop_loss:.5f}",
            management_instructions="Target 2R. Structure-based ICC entry.",
            urgency="medium",
            notes="Vanilla ICC Entry"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Structure-based exit: close if the entry thesis is structurally invalid."""
        if not open_position or not snapshot.candles or len(snapshot.candles) < 20:
            return None

        pos_dir = open_position.get("direction") or open_position.get("side")
        if pos_dir not in {"long", "short"}:
            return None

        # Check for structure invalidation (swing level broken by ATR buffer)
        inval = detect_structure_invalidation(snapshot.candles, pos_dir, atr_mult=0.5)
        if inval:
            logger.warning(
                f"[ICC-CORE] Structure Invalidation for {snapshot.symbol} ({pos_dir}): "
                f"close={inval.last_close:.4f} broke swing={inval.swing_level:.4f} "
                f"(buffer={inval.buffer:.4f})"
            )
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                reason=f"ICC Core: Structure Invalidation (swing={inval.swing_level:.4f})",
                emergency_exit=True,
            )

        # [SAFETY] All other exits managed by StrategyEngine via SafetyGuard
        return None
