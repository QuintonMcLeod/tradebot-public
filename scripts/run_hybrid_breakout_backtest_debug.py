import json
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src')

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings, SafetySettings
from tradebot_sci.market.models import Candle, MarketSnapshot
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.simulation.utils import resample_candles

# Check data range
data = json.load(open('/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/data/forex_backtest/EURUSD_5m.json'))
first_ts = datetime.fromisoformat(data[0]['timestamp'].replace('Z', '+00:00'))
last_ts = datetime.fromisoformat(data[-1]['timestamp'].replace('Z', '+00:00'))
print('Data:', len(data), 'candles')
print('Range:', first_ts.date(), '->', last_ts.date())
print('Days:', (last_ts - first_ts).days)

# Create profile with forex_hybrid_reaper_breakout strategy
profile = TradingProfileSettings(
    strategy_variant="forex_hybrid_reaper_breakout",
        breakout_distance_pct=0.01,
    candle_timeframe="5m",
    market_poll_interval_seconds=300,
    ai_decision_interval_seconds=300,
    htf_timeframe="15m",
    ltf_timeframe="5m",
    trend_window=30,
    trend_min_swings=3,
    trend_strength_floor=0.1,
    risk_per_trade_pct=0.01,
    max_pyramid_entries=1,
)

settings = Settings(
    app=AppSettings(profile_name="backtest"),
    logging=LoggingSettings(),
    ai=AISettings(provider="openai"),
    market=MarketSettings(symbols=["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]),
    profiles={"backtest": profile},
    safety=SafetySettings(block_counter_trend_entries=False),
)

print('Strategy variant:', profile.strategy_variant)

# Run backtest over full data range
bt = Backtester(ib=None, settings=settings, ai_client=None)

class LocalProvider:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        # Cache for loaded candle data: key = (symbol, timeframe) -> list[Candle]
        self._candle_cache = {}
        # Cache for snapshots: key = (symbol, timeframe) -> MarketSnapshot
        self._snapshot_cache = {}
        # Required by backtester
        self._cache = {}

    def _load_candles(self, symbol, timeframe):
        """Load and cache all candles for a symbol/timeframe."""
        key = (symbol, timeframe)
        if key in self._candle_cache:
            return self._candle_cache[key]
        
        file_symbol = symbol.replace("/", "")
        path = os.path.join(self.data_dir, f"{file_symbol}_{timeframe}.json")
        if not os.path.exists(path):
            self._candle_cache[key] = []
            return []
        
        with open(path) as f:
            raw = json.load(f)
        candles = []
        for item in raw:
            ts = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            candles.append(Candle(
                timestamp=ts, open=float(item['open']), high=float(item['high']),
                low=float(item['low']), close=float(item['close']),
                volume=float(item.get('volume', 0))
            ))
        self._candle_cache[key] = candles
        return candles

    def fetch_historical_candles(self, symbol, timeframe, start_date, end_date, **kwargs):
        candles = self._load_candles(symbol, timeframe)
        return [c for c in candles if start_date <= c.timestamp <= end_date]

    def get_latest_candles(self, symbol, timeframe, count):
        candles = self._load_candles(symbol, timeframe)
        return candles[-count:] if count < len(candles) else candles

    def get_latest_snapshot(self, symbol, timeframe):
        """Return cached snapshot; invalidate cache if data changes (it doesn't in backtest)."""
        key = (symbol, timeframe)
        if key in self._snapshot_cache:
            return self._snapshot_cache[key]
        
        candles = self.get_latest_candles(symbol, timeframe, 300)
        if not candles:
            self._snapshot_cache[key] = None
            return None
        
        htf_candles = resample_candles(candles, 900) if timeframe == "1m" else candles
        trend_htf = infer_trend_from_swings(
            htf_candles[-20:] if len(htf_candles) > 20 else htf_candles,
            swing_lookback=3, min_swings=2, strength_floor=0.1
        )
        snapshot = MarketSnapshot(
            symbol=symbol, timeframe=timeframe, candles=candles,
            trend_htf=trend_htf, trend_ltf=trend_htf,
        )
        self._snapshot_cache[key] = snapshot
        return snapshot

bt.market_provider = LocalProvider('/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/data/forex_backtest')
bt._is_market_hours_utc = lambda ts: True

warmup_days = 3
backtest_start = first_ts + timedelta(days=warmup_days)
backtest_end = last_ts

print(f'\nBacktest: {backtest_start.date()} -> {backtest_end.date()}')

# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
results = bt.run_backtest(
    initial_capital=1000.0,
    start_date=backtest_start,
    end_date=backtest_end,
    symbols=["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"],
    warmup_days=warmup_days
)

print(f'\n=== RESULTS ===')
print(f'Total Trades: {len(results.trades)}')
print(f'Final Capital: ${results.final_capital:.2f}')
print(f'Total PnL: ${results.total_pnl:.2f} ({results.total_return_pct:.2f}%)')
print(f'Win Rate: {results.win_rate:.1f}%')
print(f'Max Drawdown: {results.max_drawdown_pct:.2f}%')

if results.trades:
    wins = sum(1 for t in results.trades if getattr(t, 'realized_pnl', 0) > 0)
    losses = len(results.trades) - wins
    print(f'Wins: {wins}, Losses: {losses}')
    total_wins = sum(getattr(t, 'realized_pnl', 0) for t in results.trades if getattr(t, 'realized_pnl', 0) > 0)
    total_losses = sum(getattr(t, 'realized_pnl', 0) for t in results.trades if getattr(t, 'realized_pnl', 0) < 0)
    print(f'Total Wins: ${total_wins:.2f}, Total Losses: ${total_losses:.2f}')
    print(f'\nLast 5 trades:')
    for t in results.trades[-5:]:
        pnl = getattr(t, 'realized_pnl', 0)
        exit_p = getattr(t, 'exit_price', None)
        print(f"  {t.symbol} {t.direction} @ {t.entry_price:.5f} -> {exit_p:.5f if exit_p else 'open'}, PnL: ${pnl:.2f}")
