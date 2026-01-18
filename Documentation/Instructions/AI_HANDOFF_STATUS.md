# AI Handoff Status (Tradebot SCI)

## Purpose
This handoff summarizes recent bot changes, why they were made, and the current monitoring focus so another AI can continue work without re-reading all logs.

## Current Goal
Align the bot with ICC rules so sweeps are a primary trigger and the bot can enter on sweep + indication (two signals) without being blocked by strict continuation gating, while still respecting risk and single-position focus.

## What Changed (and Why)
- Added ICC two-signal override: sweep + indication (or sweep + continuation) can bypass the score gate, to avoid missing ICC entries when continuation has not printed yet.
- Added optional indication points to ICC scoring so near-miss scores can pass when indication is present.
- Ensured auto-entry can proceed when the two-signal override is enabled, even if icc_auto_entry_enabled is false, so the override actually fires.
- Removed invalid Coinbase futures symbol B50-20DEC30-CDE from the coinbase_futures profile list (this symbol was causing CCXT symbol errors).
- Lowered/disabled HTF strength hard gate for coinbase_futures to avoid blocking entries in real-time chop.
- Adjusted score weights for sweep/continuation (sweep is now the primary entry cue per ICC intent).
- GUI fix: futures symbol dropdown now prefers profile symbols and falls back to market symbols, so Coinbase futures symbols show correctly.
- Backtester: disabled HTF neutral exit bar to avoid forced early closes after entry.
- Restarted bot after changes.
- Added CCXT open-order discovery filtering to prevent ghost symbols (e.g., B50-20DEC30-CDE) from being auto-mapped unless they are in the active profile and a known exchange market.
- Added CCXT ticker fallback to 1m OHLCV close when fetch_ticker fails (fixes commodity/derivative symbols that lack standard ticker data).
- Adjusted liquid capital lookup to check futures/derivatives balances so the capital guard reads the correct account.

## Files Touched (Recent)
- src/tradebot_sci/strategy/engine.py
  - Added two-signal override in score gate.
  - Added indication scoring support.
  - Forced auto-entry when two-signal override is active.
  - Auto-entry notes show sweep+indication when that is the trigger.
- src/tradebot_sci/config/models.py
  - New settings: icc_score_indication_points, icc_two_signal_override_enabled.
- config/settings_profiles.yaml
  - coinbase_futures: sweep points = 30, continuation points = 25, indication points = 10, two-signal override enabled.
  - coinbase_futures: min notional set to 2.50.
  - removed B50-20DEC30-CDE from symbols list.
- src/tradebot_sci/gui/candles_panel.py
  - Dropdown fix for Coinbase futures symbols.
- src/tradebot_sci/simulation/backtester.py
  - Disabled HTF neutral exit bar.
- src/tradebot_sci/broker/ccxt_broker.py
  - Filtered open-order symbol discovery to allowed profile symbols and known markets.
  - Futures/derivatives balance fallback for liquid capital.
- src/tradebot_sci/market/providers.py
  - Added OHLCV fallback for tickers when CCXT fetch_ticker fails.
- .env
  - Profile settings updated (htf timeframe, aggressive risk).

## Current Behavior Observed
- Bot is running and scanning but still standing aside frequently due to LTF neutral/chop phases.
- There are still CCXT warnings for non-crypto symbols (CDEOIL/CDEGLD/CDESIL) due to ticker fetch list index errors.
- A legacy symbol (B50-20DEC30-CDE) still appears in CCXT protection checks, suggesting a cached or legacy list outside the profile.

## What to Monitor Next
- Look for sweep + indication situations in logs and confirm the bot now enters (or at least does not stand aside for lack of continuation).
- Confirm no additional blockers remain in the entry path for coinbase_futures.
- Track if the B50-20DEC30-CDE warning persists; if so, locate and remove it from any remaining symbol list or cached state.

## Recent Bot Control
- Restart command used: ./scripts/tradebot.sh --restart
- Latest restart: 2026-01-13 03:32 AM ET
