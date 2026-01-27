
from __future__ import annotations
import logging
import os
import re
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_bollinger_bands, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class RubberbandReaperStrategy(BaseStrategy):
    """
    Rubberband Reaper: CONFIG 20 (The Staircase Ratchet).
    - Strict Thresholds (Config 13 Quality).
    - Staircase Floor (User Milestones + 2x Cushion).
    - 20% Profit Scaling (The Hammer).
    """
    
    # Class-level persistence for account-wide High Water Mark
    MAX_CAPITAL_SEEN = 100.0
    
    def __init__(self, bb_period=20, bb_std=2.5, rsi_period=7, rsi_overbought=75, rsi_oversold=25, base_risk_pct=0.05):
        import os
        print(f"DEBUG: Loaded RubberbandReaper from {__file__}")
        super().__init__("Rubberband Reaper")
        
        # CONFIG 20: THE STAIRCASE RATCHET
        self.SEED_CAPITAL = 100.0
        self.bb_period = 20
        self.bb_std = 2.5             # Strict (Quality)
        self.rsi_period = 7
        self.rsi_overbought = 75      # Strict
        self.rsi_oversold = 25        # Strict
        
        print(f"DEBUG REAPER: Config 20 (Staircase Ratchet) Loaded. BB={self.bb_std}, RSI={self.rsi_oversold}/{self.rsi_overbought}")

    def _get_staircase_floor(self, hwm: float) -> float:
        """Calculate the safety floor based on staircase milestones with 2x-2.5x cushion."""
        # User Milestones: 100, 200, 500, 1000, 2000
        # Format: (Trigger Capital, Locked Floor)
        # We only lock in a floor when we have enough "Wiggle Room" (approx 2x-2.5x the floor)
        staircase = [
            (5000.0, 2000.0),
            (2500.0, 1000.0),
            (1250.0, 500.0),
            (500.0,  200.0),
            (0.0,    100.0), # Initial Floor
        ]
        
        for trigger, floor in staircase:
            if hwm >= trigger:
                return floor
        return 100.0

    def _detect_recovery_surge(self, trade_history: Optional[list]) -> bool:
        """Determines if 'losses have stopped' and we can surge out of Sensor Mode."""
        if not trade_history or len(trade_history) < 3:
            return False
        
        # Condition: Last 3 trades must be wins
        recent = trade_history[-3:]
        return all(t.get("is_win", False) for t in recent)

    def _get_dynamic_risk(self, capital: float, trade_history: Optional[list] = None) -> float:
        # Update Global High Water Mark
        if capital > RubberbandReaperStrategy.MAX_CAPITAL_SEEN:
            RubberbandReaperStrategy.MAX_CAPITAL_SEEN = capital
            
        # 1. THE STAIRCASE (Safety Floor)
        floor = self._get_staircase_floor(RubberbandReaperStrategy.MAX_CAPITAL_SEEN)
        cushion = capital - floor
        
        # 3. SAFETY MODE (At or below floor)
        # If we drawdown to the floor, we enter "Sensor Mode" (0.1% risk) to protect principal.
        if cushion <= 0:
            # Check for RECOVERY SURGE: If we have 3 wins, surge to 1% to get back to the floor.
            if self._detect_recovery_surge(trade_history):
                return 0.01
            return 0.001 
            
        # 4. THE HAMMER (Cushion-Aware Scaling)
        # We assume 5 symbols are trading. We risk 20% of the CUSHION total.
        # Risk per symbol = (Cushion * 0.20) / 5
        risk_dollars = (cushion * 0.20) / 5.0
        
        # Add a tiny "Scout" base risk (0.25% of capital)
        risk_dollars += (capital * 0.0025)
        
        risk_pct = risk_dollars / capital
        return min(risk_pct, 0.25) # Hard Cap per trade at 25%

    def _apply_ocean_floor(self, capital: float) -> float:
        """Snaps capital to the nearest floor for accounts under $100 (Underwater Mode)."""
        if capital >= 100.0:
            return capital
        
        # Floors: $1, $2, $5, $10, $25, $50, $100
        floors = [1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0]
        snap_to = 1.0
        for f in floors:
            if capital >= f:
                snap_to = f
            else:
                break
        
        logger.info(f"[RISK] Underwater Mode: Snapping ${capital:.2f} to floor ${snap_to:.2f}")
        return snap_to

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        
        # --- RISK GOVERNANCE ---
        # 1. Reconstruct Capital (Prioritize Real Broker Balance)
        effective_capital = current_capital or 0.0
        
        # [ANTIGRAVITY FIX] Detect and Ignore corrupt backtest data
        # If real balance is > $1, it takes 100% priority.
        if effective_capital > 1.0:
            logger.info(f"[RISK] Using Real-Time Broker Capital: ${effective_capital:.2f}")
        else:
            reconstructed_capital = 100.0
            if os.path.exists("backtest_pnl.txt"):
                try:
                    with open("backtest_pnl.txt", "r") as f:
                        content = f.read()
                        pnl_matches = re.findall(r"PnL:\s*\$([-+]?\d*\.?\d+)", content)
                        # Filter out extreme outliers (e.g. > $1k loss on $100 seed)
                        parsed_pnl = sum(float(p) for p in pnl_matches)
                        if parsed_pnl < -150.0:
                            logger.warning(f"[RISK] Ignoring extreme PnL in backtest_pnl.txt (${parsed_pnl:.2f}). Possibly corrupt.")
                        else:
                            reconstructed_capital += parsed_pnl
                except Exception:
                    pass
            effective_capital = max(reconstructed_capital, 1.0)
            logger.info(f"[RISK] Using Reconstructed Capital: ${effective_capital:.2f}")
        
        # 2. OCEAN FLOOR / UNDERWATER MODE
        # If below $100, snap to the nearest floor to stabilize risk.
        if effective_capital < 100.0:
            effective_capital = self._apply_ocean_floor(effective_capital)
        
        # 3. DYNAMIC UNIT CAP (Small Account Protection)
        # For accounts < $250, we cap exposure at 2,000 units (~$2k) to prevent liquidation.
        # For larger accounts, we use a tiered approach up to 50k units.
        if effective_capital < 250.0:
            hard_unit_cap = 2000.0
        elif effective_capital < 1000.0:
            hard_unit_cap = 10000.0
        else:
            hard_unit_cap = 50000.0
            
        # We calculate the LimitPct based on a proxy base of effective_capital * 100.0 (leverage)
        unit_cap_base = effective_capital * 100.0
        limit_pct = hard_unit_cap / unit_cap_base if unit_cap_base > 0 else 0.0025
        
        trade_risk_pct = self._get_dynamic_risk(effective_capital, trade_history=trade_history)
        
        # Apply Unit Cap to the final risk %
        final_risk_pct = min(trade_risk_pct, limit_pct)
        
        if final_risk_pct < trade_risk_pct:
            logger.info(f"[UnitCap] Capping risk from {trade_risk_pct:.5f} to {final_risk_pct:.5f} (hard_cap={hard_unit_cap}, cap={effective_capital:.2f})")

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period:
            return None
            
        lower, mid, upper = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # 1. THE HAMMER (Scale-In / Pyramid)
        if open_position:
            if open_position.get("pyramid_count", 1) > 1:
                return None
            pos_dir = open_position.get("direction")
            is_long_hammer = pos_dir == "long" and last_close > lower
            is_short_hammer = pos_dir == "short" and last_close < upper

            if is_long_hammer or is_short_hammer:
                 target = upper if pos_dir == "long" else lower
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias=pos_dir, phase="continuation", action="scale_in",
                    entry_price=last_close, stop_loss=open_position.get("stop_price"), take_profit=target,
                    risk_per_trade_pct=final_risk_pct,
                    structure_summary=f"STAIRCASE HAMMER ({final_risk_pct*100:.2f}%)",
                    urgency="high",
                    notes=f"Staircase Floor logic active. Risk={final_risk_pct*100:.2f}%",
                    invalidation_conditions="Price breaks structure.",
                    management_instructions="Aggressive TP."
                )
            return None

        # 2. THE SCOUT (Initial Entry)
        if last_close < lower and rsi < self.rsi_oversold:
            stop_loss = last_close - (atr * 1.5)
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=upper,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Strict Quality Entry. Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close below stop loss.",
                management_instructions="Standard management."
            )

        if last_close > upper and rsi > self.rsi_overbought:
            stop_loss = last_close + (atr * 1.5)
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=lower,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Strict Quality Entry. Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close above stop loss.",
                management_instructions="Standard management."
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        return None
