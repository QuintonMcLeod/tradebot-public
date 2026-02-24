"""
Full Strategy Audit — Threaded (1 strategy per thread)
Usage: python tools/audit_all_strategies.py [forex|crypto|both]

Each of the 19 strategies runs in its own thread with the full 14-day window.
Threading is limited to 2× CPU cores.
"""
import sys, os, unittest.mock, logging, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

sys.path.insert(0, 'src')
sys.path.insert(0, '.')
sys.modules['ib_insync'] = unittest.mock.MagicMock()
os.environ['TRADING_CONFIRMATION'] = 'YES'
logging.disable(logging.CRITICAL)

from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings
from tradebot_sci.simulation.backtester import Backtester
from tools.utils.local_provider import LocalJSONProvider

# ── Configuration ──────────────────────────────────────────
FOREX_SYMBOLS = ['EURUSD', 'GBPUSD']
CRYPTO_SYMBOLS = ['BTCUSD', 'ETHUSD', 'SOLUSD']

ALL_STRATS = [
    'quantum', 'london_breakout', 'rubberband_reaper', 'volatility_breakout',
    'trend_rider', 'session_momentum', 'hyper_scalper', 'orb_breakout',
    'mean_reversion', 'supply_demand', 'evolution', 'robocop', 'icc_core',
    'meta_sci', 'forex_conductor', 'crypto_rsi_macd', 'crypto_vwap_reversion', 'crypto_double_macd',
    'crypto_grid', 'bearish_engulfing',
]

DAYS = 14
INITIAL_CAPITAL = 2000.0
MAX_THREADS = os.cpu_count() or 8

_lock = threading.Lock()
_completed = [0]


def run_strategy(strat: str, symbols: list, start: datetime, end: datetime) -> dict:
    """Run a full 14-day backtest for one strategy. Thread-safe."""
    try:
        p = TradingProfileSettings(
            strategy_variant=strat, candle_timeframe='15m', htf_timeframe='1h', ltf_timeframe='5m',
            trend_window=12, ltf_trend_window=8, min_hold_hours=1.0, block_counter_trend_entries=True,
            trend_strength_floor=0.20, trend_adx_enabled=True, trend_ema_ribbon_enabled=True,
            trend_supertrend_enabled=True, trend_macd_enabled=True,
        )
        s = Settings(
            app=AppSettings(profile_name='A'), logging=LoggingSettings(),
            ai=AISettings(provider='openai'), market=MarketSettings(symbols=symbols),
            profiles={'A': p},
        )
        bt = Backtester(ib=None, settings=s, ai_client=None)
        bt.market_provider = LocalJSONProvider('data/audit')
        bt._is_market_hours_utc = lambda ts: True
        r = bt.run_backtest(initial_capital=INITIAL_CAPITAL, start_date=start, end_date=end, wind_down_days=0)
        with _lock:
            _completed[0] += 1
        return {
            'strat': strat, 'trades': r.trades, 'pnl': r.total_pnl,
            'max_dd': r.max_drawdown_pct, 'error': None
        }
    except Exception as e:
        with _lock:
            _completed[0] += 1
        return {'strat': strat, 'trades': [], 'pnl': 0, 'max_dd': 0, 'error': str(e)[:80]}


def audit_market(market_name: str, symbols: list):
    """Run all strategies using thread pool."""
    end = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=DAYS)
    task_count = len(ALL_STRATS)
    _completed[0] = 0

    sys.stderr.write(f"\n{'='*85}\n")
    sys.stderr.write(f"  {market_name.upper()} AUDIT — {task_count} strategies, {DAYS} days, {MAX_THREADS} threads\n")
    sys.stderr.write(f"  Symbols: {', '.join(symbols)} | Capital: ${INITIAL_CAPITAL:.0f}\n")
    sys.stderr.write(f"{'='*85}\n\n")
    sys.stderr.flush()

    # Redirect stdout to /dev/null for threads (fd-level, thread-safe)
    saved_fd = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)

    results = []
    with ThreadPoolExecutor(max_workers=min(MAX_THREADS, task_count)) as pool:
        futures = {pool.submit(run_strategy, strat, symbols, start, end): strat for strat in ALL_STRATS}
        for f in as_completed(futures):
            results.append(f.result())
            with _lock:
                pct = _completed[0] / task_count * 100
                sys.stderr.write(f'\r  Progress: {_completed[0]}/{task_count} ({pct:.0f}%)')
                sys.stderr.flush()

    # Restore stdout
    os.dup2(saved_fd, 1)
    os.close(saved_fd)
    os.close(devnull)

    sys.stderr.write('\n\n')
    sys.stderr.flush()

    # Build sorted table
    rows = []
    for data in results:
        t = data['trades']
        n = len(t)
        pnl = data['pnl']
        w = [x for x in t if x.pnl > 0]
        l = [x for x in t if x.pnl <= 0]
        wr = len(w) / n * 100 if n else 0
        aw = sum(x.pnl for x in w) / len(w) if w else 0
        al = sum(abs(x.pnl) for x in l) / len(l) if l else 0
        dd = data['max_dd']
        rows.append((data['strat'], n, wr, pnl, aw, al, dd, data['error']))

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


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'
    if len(sys.argv) > 2:
        INITIAL_CAPITAL = float(sys.argv[2])
    import time
    t0 = time.time()
    if mode in ('forex', 'both'):
        audit_market('Forex', FOREX_SYMBOLS)
    if mode in ('crypto', 'both'):
        audit_market('Crypto', CRYPTO_SYMBOLS)
    elapsed = time.time() - t0
    print(f"\n⏱️  Total time: {elapsed:.1f}s")
