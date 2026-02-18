# AI Handoff Prompt: Rubberband Reaper "Friday Fade" Validation

## Context
You are working on a Python-based trading bot (`tradebot-sci`). The current strategy is **Rubberband Reaper**, a mean-reversion system that fades Bollinger Band extremes when RSI confirms exhaustion.

## The Feature: Friday Fade Risk Damper
We successfully implemented a safety feature called the **Friday Fade Risk Damper**.
- **Logic**: If the time is **Friday** and **>= 12:00 PM EST**, the bot overrides the user's risk setting and caps it at **0.25%** (almost zero).
- **Goal**: Prevent "weekend drift" and liquidity dry-ups from erasing weekly profits.
- **Location**: `src/tradebot_sci/strategy/variants/rubberband_reaper.py` in `check_entry_signal`.

## The Discrepancy (Current Barrier)
The user ran this bot LIVE on a Friday and made profit. However, our simulated backtest (`scripts/run_friday_backtest.py`) using **15-minute candles** downloaded from Kraken/Coinbase shows **0 trades** for that same day.

We believe this is a **Data Granularity Issue**. The live bot likely traded on 1-minute or tick-level volatility spikes that are "smoothed out" and invisible in the 15-minute close data used by the backtester.

## Your Task
We need to prove that the bot *would* have traded profitably in the morning (Active Risk) and then safely clamped down in the afternoon (Friday Fade).

### 1. High-Resolution Backtest
- Modify `scripts/run_friday_backtest.py` or `tools/download_forex_data.py`.
- **Fetch 1-minute (1m) data** instead of 15m for the target tokens (EURUSD, GBPUSD, USDJPY, AUDUSD).
- The strategy profile (`FullProfile` in the script) is currently set to `candle_timeframe="15m"`. You may need to create a **"ScalpProfile"** variant that uses `1m` candles to capture the noise.

### 2. Verify the "Morning Profit"
- Run the simulation on the 1m data for the **Morning Session (8 AM - 12 PM EST)**.
- Confirm that trades trigger and generate profit (matching the user's experience).

### 3. Verify the "Afternoon Safety"
- Run the simulation for the **Afternoon Session (12 PM - 5 PM EST)**.
- Confirm that if any signals occur, the `[FRIDAY FADE]` log appears and Risk is clamped to 0.25%.

## Important Files
- `src/tradebot_sci/strategy/variants/rubberband_reaper.py`: The strategy logic.
- `scripts/run_friday_backtest.py`: The current backtest runner (uses `ccxt` data).
- `tools/download_forex_data.py`: The script to fetch historical JSON data.

## Goal
Produce a backtest log that shows:
1.  **Trades executing > 0.25% risk** before 12 PM.
2.  **Trades executing (or capped) at 0.25% risk** after 12 PM.
