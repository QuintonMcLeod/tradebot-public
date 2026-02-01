from __future__ import annotations
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision

class BaseStrategy:
    """Interface for all bot strategy variants."""
    
    def __init__(self, name: str):
        self.name = name

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for a new trade entry signal."""
        raise NotImplementedError

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for an exit signal for an open position."""
        raise NotImplementedError

    def get_asset_class(self, symbol: str) -> str:
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
        asset_class = self.get_asset_class(symbol)
        
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
