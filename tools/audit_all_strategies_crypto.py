"""Full strategy audit for CRYPTO — run all strategy variants on BTC+ETH+SOL 14-day backtest."""
import sys, os, unittest.mock, logging, io

sys.path.insert(0, 'src')
sys.path.insert(0, '.')
sys.modules['ib_insync'] = unittest.mock.MagicMock()
os.environ['TRADING_CONFIRMATION'] = 'YES'
logging.disable(logging.CRITICAL)
_real_stdout = sys.stdout
sys.stdout = io.StringIO()

from datetime import datetime, timedelta, timezone
from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings
from tradebot_sci.simulation.backtester import Backtester
from tools.utils.local_provider import LocalJSONProvider

end = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
start = end - timedelta(days=14)

CRYPTO = ['BTCUSD', 'ETHUSD', 'SOLUSD']
STRATS = [
    'quantum', 'london_breakout', 'rubberband_reaper', 'volatility_breakout',
    'trend_rider', 'session_momentum', 'hyper_scalper', 'orb_breakout',
    'mean_reversion',
    'supply_demand', 'evolution', 'robocop', 'icc_core', 'meta_sci',
    'crypto_rsi_macd', 'crypto_vwap_reversion', 'crypto_double_macd', 'crypto_grid',
]

rows = []
for strat in STRATS:
    try:
        p = TradingProfileSettings(
            strategy_variant=strat, candle_timeframe='15m', htf_timeframe='1h', ltf_timeframe='5m',
            trend_window=12, ltf_trend_window=8, min_hold_hours=1.0, block_counter_trend_entries=True,
            trend_strength_floor=0.20, trend_adx_enabled=True, trend_ema_ribbon_enabled=True,
            trend_supertrend_enabled=True, trend_macd_enabled=True,
        )
        s = Settings(app=AppSettings(profile_name='T'), logging=LoggingSettings(),
            ai=AISettings(provider='openai'), market=MarketSettings(symbols=CRYPTO), profiles={'T': p})
        bt = Backtester(ib=None, settings=s, ai_client=None)
        bt.market_provider = LocalJSONProvider('data/audit')
        bt._is_market_hours_utc = lambda ts: True
        r = bt.run_backtest(initial_capital=2000, start_date=start, end_date=end, wind_down_days=0)
        
        t = r.trades; n = len(t)
        pnl = r.total_pnl
        w = [x for x in t if x.pnl > 0]; l = [x for x in t if x.pnl <= 0]
        wr = len(w)/n*100 if n else 0
        aw = sum(x.pnl for x in w)/len(w) if w else 0
        al = sum(abs(x.pnl) for x in l)/len(l) if l else 0
        dd = r.max_drawdown_pct if hasattr(r, 'max_drawdown_pct') else 0
        rows.append((strat, n, wr, pnl, aw, al, dd, None))
    except Exception as e:
        rows.append((strat, 0, 0, 0, 0, 0, 0, str(e)[:50]))

sys.stdout = _real_stdout
rows.sort(key=lambda x: x[3], reverse=True)

print(f"\n{'#':>2}  {'Strategy':<22} {'Trades':>6} {'Win%':>5} {'Net PnL ($)':>14} {'AvgWin':>10} {'AvgLoss':>10} {'MaxDD':>6}")
print("=" * 85)
for i, (strat, n, wr, pnl, aw, al, dd, err) in enumerate(rows, 1):
    if err:
        print(f"{i:>2}  💥 {strat:<20} ERROR: {err}")
    elif n == 0:
        print(f"{i:>2}  ⬜ {strat:<20}      0    --             --         --         --     --")
    else:
        icon = '✅' if pnl > 0 else '❌'
        print(f"{i:>2}  {icon} {strat:<20} {n:>4} {wr:>4.0f}% ${pnl:>13.2f} ${aw:>9.2f} ${al:>9.2f} {dd:>5.1f}%")
