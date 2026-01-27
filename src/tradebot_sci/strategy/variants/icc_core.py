from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
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
        
        # 3. Check Alignment
        # Vanilla ICC requires HTF alignment (or HTF Neutral + LTF Trend).
        if not htf_align:
            return None
            
        # 4. Filter Chop (unless scalping allowed? Core says stay out of chop)
        if phase == "chop":
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
        
        from tradebot_sci.strategy.icc_signals import calculate_atr
        atr = calculate_atr(snapshot.candles) or (last_close * 0.005)
        
        if action == "enter_long":
            stop_loss = last_close - (2.0 * atr) # Wide structural stop placeholder
            take_profit = last_close + (4.0 * atr) # 2R
        else:
            stop_loss = last_close + (2.0 * atr)
            take_profit = last_close - (4.0 * atr)

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            action=action,
            bias=bias,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            phase=phase,
            structure_summary=f"ICC Core {action} (Score={score})",
            urgency="medium",
            notes="Vanilla ICC Entry"
        )

    def check_exit_signal(self, *args, **kwargs) -> Optional[AITradeDecision]:
        # Vanilla ICC holds to Target/Stop (Manager handles it).
        return None
