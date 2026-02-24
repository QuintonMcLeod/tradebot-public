"""Diagnostic: dump trade details for losing forex strategies."""
import sys, os, unittest.mock, logging
sys.path.insert(0, 'src'); sys.path.insert(0, '.')
sys.modules['ib_insync'] = unittest.mock.MagicMock()
os.environ['TRADING_CONFIRMATION'] = 'YES'
logging.disable(logging.CRITICAL)
from datetime import datetime, timedelta, timezone
from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings
from tradebot_sci.simulation.backtester import Backtester
from tools.utils.local_provider import LocalJSONProvider

end = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
start = end - timedelta(days=14)

saved = os.dup(1)
dn = os.open(os.devnull, os.O_WRONLY)

strats = ['quantum','meta_sci','trend_rider','robocop','supply_demand','icc_core','bearish_engulfing','volatility_breakout']
results = {}
for strat in strats:
    os.dup2(dn, 1)
    p = TradingProfileSettings(
        strategy_variant=strat, candle_timeframe='15m', htf_timeframe='1h', ltf_timeframe='5m',
        trend_window=12, ltf_trend_window=8, min_hold_hours=1.0, block_counter_trend_entries=True,
        trend_strength_floor=0.20, trend_adx_enabled=True, trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True, trend_macd_enabled=True,
    )
    s = Settings(app=AppSettings(profile_name='T'), logging=LoggingSettings(),
        ai=AISettings(provider='openai'), market=MarketSettings(symbols=['EURUSD','GBPUSD']), profiles={'T': p})
    bt = Backtester(ib=None, settings=s, ai_client=None)
    bt.market_provider = LocalJSONProvider('data/audit')
    bt._is_market_hours_utc = lambda ts: True
    r = bt.run_backtest(initial_capital=2000, start_date=start, end_date=end, wind_down_days=0)
    results[strat] = r

os.dup2(saved, 1)
os.close(dn)

# Write results to stderr to avoid interference
out = open('/tmp/forex_diag.txt', 'w')

for strat, r in results.items():
    wins = [t for t in r.trades if t.pnl > 0]
    wr = len(wins)/len(r.trades)*100 if r.trades else 0
    out.write(f'\n===== {strat.upper()} ({len(r.trades)} trades, WR={wr:.0f}%) =====\n')
    for t in r.trades[:6]:
        hm = (t.exit_time - t.entry_time).total_seconds()/60
        mp = abs(t.exit_price - t.entry_price)*10000
        out.write(f'  {t.symbol} {t.direction:5s} hold={hm:5.0f}m e={t.entry_price:.5f} x={t.exit_price:.5f} mv={mp:5.1f}p pnl=${t.pnl:+8.2f} {t.exit_reason}\n')
    if len(r.trades) > 6: out.write(f'  ... ({len(r.trades)-6} more)\n')
    reasons = {}
    for t in r.trades: reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    out.write(f'  Exits: {reasons}\n')
    ht = [(t.exit_time - t.entry_time).total_seconds()/60 for t in r.trades]
    ah = sum(ht)/len(ht) if ht else 0
    ap = sum(abs(t.exit_price - t.entry_price)*10000 for t in r.trades)/len(r.trades) if r.trades else 0
    out.write(f'  AvgHold: {ah:.0f}min | AvgMove: {ap:.1f}p\n')

out.close()
print("Done - results in /tmp/forex_diag.txt")
