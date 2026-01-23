from __future__ import annotations
import statistics
from typing import List, Tuple
from tradebot_sci.market.models import Candle

def calculate_sma(data: List[float], period: int) -> float:
    if len(data) < period:
        return 0.0
    return sum(data[-period:]) / period

def calculate_ema(data: List[float], period: int) -> float:
    """Standard Exponential Moving Average."""
    if not data:
        return 0.0
    if len(data) < period:
        return sum(data) / len(data)
    
    alpha = 2 / (period + 1)
    ema = sum(data[:period]) / period # Start with SMA
    for price in data[period:]:
        ema = (price * alpha) + (ema * (1 - alpha))
    return ema

def calculate_bollinger_bands(data: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
    """Returns (Lower, Middle, Upper) bands."""
    if len(data) < period:
        return 0.0, 0.0, 0.0
    
    window = data[-period:]
    middle = sum(window) / period
    stdev = statistics.stdev(window)
    
    lower = middle - (std_dev * stdev)
    upper = middle + (std_dev * stdev)
    
    return lower, middle, upper

def calculate_rsi(data: List[float], period: int = 14) -> float:
    if len(data) < period + 1:
        return 50.0
        
    gains = []
    losses = []
    
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
            
    # Wilder's Smoothing
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
        
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
