# Changelog: Last 24 Hours

## 🚨 Critical Fixes (Latest)
- **Restored Configuration Model**: Fixed a critical severity `ImportError` by restoring the missing `TradingProfileSettings` class in `src/tradebot_sci/config/models.py`. This accidentally deleted class was preventing the bot from initializing any trading profile.
- **Provider Factory**: Resolved a `SyntaxError` caused by duplicate arguments in `src/tradebot_sci/runtime/provider_factory.py`, ensuring correct OANDA provider initialization.

## 🐛 Bug Fixes & UI Polishing
- **Decisions Panel Visibility**:
  - **Problem**: "Stand Aside" and low-score decisions were not being broadcast to the GUI, leaving the Decisions panel empty for skipped symbols.
  - **Solution**:
    - Updated `WSLoggingHandler` in `loop.py` to correctly whitelist and broadcast `[DECISION]` and `[STRUCTURE]` tags to the WebSocket client.
    - Modified `cycle.py` to explicitly log `[DECISION]` events with `action=HOLD` when a candidate fails the structure score threshold.
    - Updated `engine.py` to include `score` and `reason` in decision logs, matching the parser's expected format.
    - **Result**: The GUI now accurately displays "HOLD" decisions with their calculated scores, giving full transparency into why the bot is waiting.

## 🚀 New Features & Integration
### **Paxos (itBit) API Integration**
- **Native Broker Implementation**: Created `PaxosExchangeBroker` for direct trading and account management.
  - Implemented HMAC-SHA256 authentication.
  - Added support for Market Buy orders and Balance fetching.
- **Market Data Provider**: Created `PaxosMarketDataProvider` for real-time tickers and order books.
- **Factory Updates**: Integrated Paxos into `ProviderFactory` for seamless switching.
- **Settings UI**:
  - Added dedicated **"Paxos (Crypto)"** tab in settings.
  - Added fields for `API Key`, `API Secret`, and `Environment`.
  - Updated "Data Routing" in the UI to support selecting Paxos as a data source.

## 🛠 System Enhancements
- **Window Management**: Fixed issue where the Settings window would remain open after the main app closed.
- **Public Mirror Synchronization**:
  - Pushed latest `debug` branch to `gitlab.com/ultraedge/tradebot-public.git`.
  - Fore-tracked `src/tradebot_sci/gui.bak` for recovery purposes.
