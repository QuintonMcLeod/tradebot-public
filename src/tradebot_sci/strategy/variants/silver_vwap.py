from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime, time
import pytz

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_vwap, calculate_ema

logger = logging.getLogger(__name__)

class SilverVwapStrategy(BaseStrategy):
    """
    Apex Silver-VWAP Strategy — Designed for CME Futures (NQ / ES).
    
    Trades the 09:50 AM to 11:10 AM EST "Silver Bullet" window.
    Uses the 15M Opening Range and Anchored VWAP as trend filters.
    Executes on VWAP pullbacks within the direction of the trend.
    """
    ASSET_TAG = "futures"

    def __init__(self, **kwargs):
        super().__init__("silver_vwap")
        self.stop_loss_points = float(kwargs.get('silver_vwap_sl_points', 20.0))
        self.take_profit_points = float(kwargs.get('silver_vwap_tp_points', 40.0))
        self.max_vwap_dist_pct = float(kwargs.get('silver_vwap_max_dist_pct', 0.0015))
        self.max_daily_losses = int(kwargs.get('silver_vwap_max_losses', 2))
        
        # Time constraints (EST) for Opening Range calculation ONLY
        self.est_tz = pytz.timezone('US/Eastern')
        
        # Opening Range calculation
        or_start_env = str(kwargs.get('silver_vwap_or_start', '09:30')).split(':')
        or_end_env = str(kwargs.get('silver_vwap_or_end', '09:50')).split(':')
        self.or_start = time(int(or_start_env[0]), int(or_start_env[1]))
        self.or_end = time(int(or_end_env[0]), int(or_end_env[1]))
        
        # Guard states
        self.consecutive_losses = 0
        self.halt_trading = False
        self.last_trade_date = None

    def _calculate_opening_range(self, snapshot: MarketSnapshot) -> tuple[float, float]:
        """Calculates the High and Low of the Opening Range (09:30 - 09:50 EST)."""
        or_high = 0.0
        or_low = float('inf')
        
        # Since we might be given 1m candles, iterate backwards to find the current session's OR
        now_est = datetime.now(self.est_tz)
        today_date = now_est.date()
        
        for idx in range(len(snapshot.candles)-1, -1, -1):
            c = snapshot.candles[idx]
            if not c.timestamp:
                continue
                
            try:
                # Naive str to datetime (assuming snapshot candles have isoformat)
                # Ensure we handle different timestamp formats safely
                if isinstance(c.timestamp, str):
                    c_dt = datetime.fromisoformat(c.timestamp.replace("Z", "+00:00"))
                elif isinstance(c.timestamp, datetime):
                    c_dt = c.timestamp
                else:
                    c_dt = datetime.fromtimestamp(c.timestamp, tz=pytz.UTC)
                
                c_est = c_dt.astimezone(self.est_tz)
                
                # Check if it's from today
                if c_est.date() < today_date:
                    break
                    
                # Check if it falls in the OR window
                if self.or_start <= c_est.time() < self.or_end:
                    or_high = max(or_high, float(c.high))
                    or_low = min(or_low, float(c.low))
            except Exception as e:
                logger.debug(f"[SilverVWAP] Candle parse error: {e}")
                
        return or_high, or_low if or_high > 0 else (0.0, 0.0)

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> tuple[float, str, str]:
        score = 0.0
        details = []
        
        # 1. ICC Core HTF Trend Alignment
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        if htf_dir in ("long", "short"):
            score += 30
            details.append(f"HTF={htf_dir}")
            
        # 2. VWAP Alignment
        candles = snapshot.candles
        if len(candles) > 0:
            last_close = float(candles[-1].close)
            vwap = calculate_vwap(candles)
            if (htf_dir == "long" and last_close > vwap) or (htf_dir == "short" and last_close < vwap):
                score += 30
                details.append("VWAP Alignment")
                
            # 3. Pullback Proximity
            vwap_dist = abs(last_close - vwap)
            if vwap_dist < last_close * self.max_vwap_dist_pct:
                score += 40
                details.append("Pullback Ready")
                
        grade = self.grade_from_score_100(score)
        summary = f"Silver-VWAP: {score:.0f}% — {', '.join(details)}"
        return score, grade, summary

    def check_entry_signal(
        self, 
        snapshot: MarketSnapshot, 
        gates: dict,
        open_position: Optional[dict] = None, 
        current_capital: Optional[float] = None, 
        trade_history: Optional[list] = None,
        **kwargs
    ) -> Optional[AITradeDecision]:
        
        # 1. Reset daily limits on a new day
        now_est = datetime.now(self.est_tz)
        current_date = now_est.date()
        if self.last_trade_date != current_date:
            self.last_trade_date = current_date
            self.consecutive_losses = 0
            self.halt_trading = False
            
        if self.halt_trading:
            logger.info(f"[SilverVWAP] Trading halted for {snapshot.symbol} due to daily loss limits.")
            return None
            
        candles = snapshot.candles
        if len(candles) < 30:
            return None
            
        closes = [c.close for c in candles]
        last_close = float(closes[-1])
        
        # 3. Trend Alignment (VWAP + OR)
        vwap = calculate_vwap(candles)
        ema9 = calculate_ema(closes, 9)
        
        or_high, or_low = self._calculate_opening_range(snapshot)
        if or_high == 0.0:
            # Cannot determine trend without Opening Range
            return None
            
        # Trend filters
        bullish_trend = last_close > vwap and last_close > or_high
        bearish_trend = last_close < vwap and last_close < or_low
        
        if not (bullish_trend or bearish_trend):
            return None
            
        # 4. Entry Trigger (Pullback to VWAP / EMA)
        # We want price to have pulled back closely to the VWAP, but EMA9 showing momentum
        vwap_dist = abs(last_close - vwap)
        
        # Require price to be relatively close to VWAP to avoid buying the top
        max_dist_allowed = last_close * self.max_vwap_dist_pct
        
        if vwap_dist > max_dist_allowed:
            return None
            
        # NQ/ES point conversions
        # Assuming ES price is around 5000, NQ is around 20000
        is_nq = last_close > 10000
        point_multiplier = float(kwargs.get('silver_vwap_nq_mult', 1.0)) if is_nq else float(kwargs.get('silver_vwap_es_mult', 0.25))
        
        sl_points = self.stop_loss_points * point_multiplier
        tp_points = self.take_profit_points * point_multiplier

        score, grade, _ = self.score_signal(snapshot, gates)
        
        if bullish_trend and last_close > ema9:
            stop_loss = last_close - sl_points
            take_profit = last_close + tp_points
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Silver-VWAP Long (Price > ORH, Pullback near VWAP={vwap:.2f})",
                invalidation_conditions="Close below VWAP",
                management_instructions="Trailing stop after 1R",
                urgency="high",
                notes="Apex Silver VWAP Breakout",
                score=score, grade=grade
            )
            
        if bearish_trend and last_close < ema9:
            stop_loss = last_close + sl_points
            take_profit = last_close - tp_points
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Silver-VWAP Short (Price < ORL, Pullback near VWAP={vwap:.2f})",
                invalidation_conditions="Close above VWAP",
                management_instructions="Trailing stop after 1R",
                urgency="high",
                notes="Apex Silver VWAP Breakdown",
                score=score, grade=grade
            )
            
        return None

    def check_exit_signal(
        self, 
        snapshot: MarketSnapshot, 
        open_position: dict,
        gates: dict, 
        current_capital: Optional[float] = None, 
        trade_history: Optional[list] = None,
        **kwargs
    ) -> Optional[AITradeDecision]:
        
        # We entrust Time-Based exits / End-of-Day liquidations to the global scheduler
        # inside the bot ecosystem, rather than hardcoding flatten rules here.
        return None

    def register_trade_result(self, pnl: float):
        """Callback to record PnL and enforce the strict consecutive loss halt rule."""
        if pnl < 0:
            self.consecutive_losses += 1
            logger.info(f"[SilverVWAP] Trade loss registered. Consecutive losses: {self.consecutive_losses}/{self.max_daily_losses}")
            if self.consecutive_losses >= self.max_daily_losses:
                self.halt_trading = True
                logger.warning(f"[SilverVWAP] DAILY LOSS LIMIT REACHED. Halting algo for the day.")
        else:
            # Reset on a win
            self.consecutive_losses = 0
