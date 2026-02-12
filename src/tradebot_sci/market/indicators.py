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


def calculate_macd(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
    """
    Calculate MACD indicator.
    Returns (macd_line, signal_line, histogram).
    """
    if len(data) < slow + signal:
        return 0.0, 0.0, 0.0

    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(data, fast)
    slow_ema = calculate_ema(data, slow)
    macd_line = fast_ema - slow_ema

    # Build MACD line series for signal EMA
    macd_series = []
    alpha_fast = 2 / (fast + 1)
    alpha_slow = 2 / (slow + 1)

    ema_f = sum(data[:fast]) / fast
    ema_s = sum(data[:slow]) / slow

    for i in range(slow, len(data)):
        if i >= fast:
            ema_f = (data[i] * alpha_fast) + (ema_f * (1 - alpha_fast))
        ema_s = (data[i] * alpha_slow) + (ema_s * (1 - alpha_slow))
        macd_series.append(ema_f - ema_s)

    if len(macd_series) < signal:
        return macd_line, 0.0, macd_line

    # Signal line = EMA of MACD series
    sig_alpha = 2 / (signal + 1)
    sig_ema = sum(macd_series[:signal]) / signal
    for val in macd_series[signal:]:
        sig_ema = (val * sig_alpha) + (sig_ema * (1 - sig_alpha))

    histogram = macd_line - sig_ema
    return macd_line, sig_ema, histogram


def calculate_macd_series(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate full MACD series for crossover detection.
    Returns (macd_lines[], signal_lines[], histograms[]).
    """
    if len(data) < slow + signal:
        return [], [], []

    alpha_fast = 2 / (fast + 1)
    alpha_slow = 2 / (slow + 1)
    sig_alpha = 2 / (signal + 1)

    ema_f = sum(data[:fast]) / fast
    ema_s = sum(data[:slow]) / slow

    macd_series = []
    for i in range(slow, len(data)):
        if i >= fast:
            ema_f = (data[i] * alpha_fast) + (ema_f * (1 - alpha_fast))
        ema_s = (data[i] * alpha_slow) + (ema_s * (1 - alpha_slow))
        macd_series.append(ema_f - ema_s)

    if len(macd_series) < signal:
        return macd_series, [], []

    # Build signal series
    sig_ema = sum(macd_series[:signal]) / signal
    signal_series = [sig_ema]
    for val in macd_series[signal:]:
        sig_ema = (val * sig_alpha) + (sig_ema * (1 - sig_alpha))
        signal_series.append(sig_ema)

    # Align: trim macd_series to match signal_series length
    aligned_macd = macd_series[signal - 1:]
    histograms = [m - s for m, s in zip(aligned_macd, signal_series)]

    return aligned_macd, signal_series, histograms


def calculate_vwap(candles: List[Candle]) -> float:
    """
    Calculate Volume-Weighted Average Price from candle data.
    Uses typical price (H+L+C)/3 weighted by volume.
    """
    if not candles:
        return 0.0

    total_vp = 0.0
    total_volume = 0.0

    for c in candles:
        vol = getattr(c, 'volume', 0) or 0
        if vol <= 0:
            continue
        typical_price = (c.high + c.low + c.close) / 3.0
        total_vp += typical_price * vol
        total_volume += vol

    if total_volume == 0:
        # Fallback: simple average of closes
        closes = [c.close for c in candles]
        return sum(closes) / len(closes) if closes else 0.0

    return total_vp / total_volume
