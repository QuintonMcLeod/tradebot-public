from __future__ import annotations
from typing import Optional, Tuple
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision

class BaseStrategy:
    """Interface for all bot strategy variants."""
    
    def __init__(self, name: str):
        self.name = name
        self.profile_risk_pct: float | None = None  # Set by Meta-SCI or engine
        self._profile = None  # Set by engine or conductor — strategies read config from here

    def get_risk_pct(self, fallback: float = 0.015) -> float:
        """Return the profile-configured risk, or a safe fallback."""
        return self.profile_risk_pct or fallback

    @staticmethod
    def grade_from_score_100(score: float) -> str:
        """Convert a 0-100 score to a letter grade (scaled for 80=100%)."""
        if score >= 76: return "A+"
        if score >= 72: return "A"
        if score >= 68: return "A-"
        if score >= 64: return "B+"
        if score >= 60: return "B"
        if score >= 56: return "B-"
        if score >= 52: return "C+"
        if score >= 48: return "C"
        if score >= 44: return "C-"
        if score >= 40: return "D"
        if score >= 32: return "F+"
        if score >= 24: return "F"
        return "F-"

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> Tuple[float, str, str]:
        """
        Score the current setup from this strategy's perspective.

        Returns:
            (score_0_to_100, grade, summary)
        """
        # Default: use the ICC structure score from gates (always available)
        icc_score = gates.get("score", 0.0)
        pct = round(icc_score * 100, 1)
        grade = self.grade_from_score_100(pct)
        return pct, grade, f"{self.name}: ICC {pct:.0f}%"

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for a new trade entry signal."""
        # BaseStrategy should strictly be used as a placeholder or abstract base.
        # If this is called directly, it means the Engine fell through the specific strategy logic.
        if self.name == "meta_sci":
            from tradebot_sci.strategy.decisions import stand_aside_decision
            return stand_aside_decision(snapshot.symbol, "N/A", "Meta-SCI Fall-through Safety Catch")
        raise NotImplementedError("BaseStrategy is abstract and should not be executed directly.")

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for an exit signal for an open position."""
        if self.name == "meta_sci":
             # Safe fallback: Hold position if we lost the managing strategy
             return None
        raise NotImplementedError("BaseStrategy is abstract and should not be executed directly.")

    def _get_asset_class(self, symbol: str) -> str:
        """Determine asset class from symbol format."""
        s = symbol.upper()
        if "/" in s: # Likely Crypto (BTC/USD) or Forex (EUR/USD)
            base, quote = s.split("/")
            if quote in ["USD", "USDT", "USDC"] and len(base) > 3: return "CRYPTO" # DOGE/USD
            if base in ["BTC", "ETH", "SOL", "XRP", "LTC", "BCH", "ZEC", "LINK", "UNI", "AAVE"]: return "CRYPTO"
            return "FOREX" # EUR/USD, GBP/JPY
        if len(s) == 3: return "STOCKS" # Old logic, weak
        return "STOCKS" # Default (SPY, TSLA)

    def calculate_fee_adjusted_break_even(self, entry_price: float, direction: str, symbol: str) -> float:
        """
        Calculate the price at which the trade is truly break-even after fees.
        Includes round-trip fee estimates (Entry + Exit).
        """
        asset_class = self._get_asset_class(symbol)
        
        # Total Round-Trip Buffer %
        if asset_class == "CRYPTO":
            buffer_pct = 0.0050 # 0.25% * 2 (Taker fees are high)
        elif asset_class == "FOREX":
            buffer_pct = 0.0004 # 0.02% * 2 (Spread + Comm)
        else:
            buffer_pct = 0.0020 # 0.10% * 2 (Stocks/ETF)
            
        buffer_amt = entry_price * buffer_pct
        
        if direction == "long":
            return entry_price + buffer_amt
        else:
            return entry_price - buffer_amt
