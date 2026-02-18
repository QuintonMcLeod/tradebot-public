# Implementation Plan: Per-Asset-Class Strategy Selection

## Overview

This document outlines the implementation plan for enabling **per-asset-class strategy selection** in Tradebot SCI. Instead of a single `strategy_variant` for an entire profile, users can now assign different trading strategies to different asset classes (crypto, forex, stocks, ETFs, metals, futures).

---

## Current State

### Profile Configuration (Before)
```yaml
forex_intraday:
  strategy_variant: rubberband_reaper  # Single strategy for all symbols
  symbols:
    - EURUSD
    - BTCUSD
    - SPY
```

### Profile Configuration (After - Implemented in YAML)
```yaml
forex_intraday:
  strategy_variant: rubberband_reaper  # Default fallback
  strategies:
    crypto: rubberband_reaper
    forex: rubberband_reaper
    stocks: quantum
    etf: quantum
    metals: mean_reversion
    futures: volatility_breakout
  symbols:
    - EURUSD    # -> Uses forex strategy (rubberband_reaper)
    - BTCUSD    # -> Uses crypto strategy (rubberband_reaper)
    - SPY       # -> Uses etf strategy (quantum)
```

---

## Implementation Tasks

### Phase 1: Symbol Classification System

**File:** `src/tradebot_sci/utils/symbol_classifier.py` (NEW)

Create a utility to classify symbols into asset classes:

```python
from enum import Enum
from typing import Optional

class AssetClass(Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"
    ETF = "etf"
    METALS = "metals"
    FUTURES = "futures"
    UNKNOWN = "unknown"

# Known symbol patterns
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "LINK", "AVAX", "SHIB", "LTC", "DOT", "ATOM", "NEAR", "POL"}
FOREX_PAIRS = {"EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
METALS = {"XAU", "XAG", "XPT", "XPD", "GLD", "SLV", "GDX"}
ETF_SYMBOLS = {"SPY", "QQQ", "DIA", "IWM", "VTI", "XLK", "XLF", "XLE", "XLY", "XLP", "XLI", "XLU", "SMH", "XLB", "XOP", "XME", "ARKK", "ARKF", "SOXX", "USO", "UNG", "EWU", "EWG", "EWQ", "EWT", "EWJ", "EWS", "FXI"}
FUTURES_SYMBOLS = {"ES", "NQ", "MES", "MNQ", "M2K", "MGC", "CL", "GC", "SI", "HG", "NG"}

def classify_symbol(symbol: str) -> AssetClass:
    """
    Classify a trading symbol into its asset class.

    Args:
        symbol: The trading symbol (e.g., "BTCUSD", "EURUSD", "SPY")

    Returns:
        AssetClass enum value
    """
    symbol_upper = symbol.upper().replace("/", "").replace("-", "").replace(":", "")

    # Check for futures expiry format (e.g., "ETH/USD:USD-260130")
    if ":" in symbol and "-" in symbol.split(":")[-1]:
        # Extract base symbol
        base = symbol.split("/")[0].upper()
        if base in CRYPTO_SYMBOLS:
            return AssetClass.FUTURES  # Crypto futures
        return AssetClass.FUTURES

    # Check for crypto
    for crypto in CRYPTO_SYMBOLS:
        if symbol_upper.startswith(crypto) or crypto in symbol_upper:
            return AssetClass.CRYPTO

    # Check for forex pairs (6-char format: EURUSD, GBPJPY, etc.)
    if len(symbol_upper) == 6:
        base = symbol_upper[:3]
        quote = symbol_upper[3:]
        if base in FOREX_PAIRS and quote in FOREX_PAIRS:
            return AssetClass.FOREX

    # Check for metals
    for metal in METALS:
        if symbol_upper.startswith(metal) or metal in symbol_upper:
            return AssetClass.METALS

    # Check for ETFs
    if symbol_upper in ETF_SYMBOLS:
        return AssetClass.ETF

    # Check for futures
    if symbol_upper in FUTURES_SYMBOLS:
        return AssetClass.FUTURES

    # Default to stocks for single-ticker symbols
    if symbol_upper.isalpha() and 1 <= len(symbol_upper) <= 5:
        return AssetClass.STOCKS

    return AssetClass.UNKNOWN
```

---

### Phase 2: Settings Model Updates

**File:** `src/tradebot_sci/config/models.py`

#### 2.1 Add PerAssetStrategies Model

```python
from typing import Dict, Optional
from pydantic import BaseModel

class PerAssetStrategies(BaseModel):
    """Per-asset-class strategy configuration."""
    crypto: str = "rubberband_reaper"
    forex: str = "rubberband_reaper"
    stocks: str = "quantum"
    etf: str = "quantum"
    metals: str = "mean_reversion"
    futures: str = "volatility_breakout"

class Settings(BaseSettings):
    # ... existing fields ...

    # Legacy single strategy (fallback)
    strategy_variant: str = "rubberband_reaper"

    # NEW: Per-asset-class strategies
    strategies: Optional[PerAssetStrategies] = None

    def get_strategy_for_symbol(self, symbol: str) -> str:
        """
        Get the appropriate strategy for a given symbol.

        Args:
            symbol: The trading symbol

        Returns:
            Strategy variant name
        """
        if self.strategies is None:
            return self.strategy_variant

        from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass

        asset_class = classify_symbol(symbol)

        strategy_map = {
            AssetClass.CRYPTO: self.strategies.crypto,
            AssetClass.FOREX: self.strategies.forex,
            AssetClass.STOCKS: self.strategies.stocks,
            AssetClass.ETF: self.strategies.etf,
            AssetClass.METALS: self.strategies.metals,
            AssetClass.FUTURES: self.strategies.futures,
        }

        return strategy_map.get(asset_class, self.strategy_variant)
```

---

### Phase 3: Strategy Factory Updates

**File:** `src/tradebot_sci/strategies/factory.py` (or similar)

Update the strategy instantiation to use per-symbol strategy selection:

```python
from tradebot_sci.config.models import Settings
from tradebot_sci.utils.symbol_classifier import classify_symbol

def get_strategy_for_symbol(settings: Settings, symbol: str):
    """
    Get the appropriate strategy instance for a symbol.

    Args:
        settings: Application settings
        symbol: The trading symbol

    Returns:
        Strategy instance configured for the symbol
    """
    strategy_name = settings.get_strategy_for_symbol(symbol)

    # Import strategy classes
    from tradebot_sci.strategies import (
        RubberbandReaperStrategy,
        RoboCopStrategy,
        EvolutionStrategy,
        QuantumStrategy,
        MeanReversionStrategy,
        HyperScalperStrategy,
        LondonBreakoutStrategy,
        VolatilityBreakoutStrategy,
        AggregatorStrategy,
    )

    STRATEGY_MAP = {
        "rubberband_reaper": RubberbandReaperStrategy,
        "robocop": RoboCopStrategy,
        "evolution": EvolutionStrategy,
        "quantum": QuantumStrategy,
        "mean_reversion": MeanReversionStrategy,
        "hyper_scalper": HyperScalperStrategy,
        "london_breakout": LondonBreakoutStrategy,
        "volatility_breakout": VolatilityBreakoutStrategy,
        "aggregator": AggregatorStrategy,
    }

    strategy_class = STRATEGY_MAP.get(strategy_name)
    if strategy_class is None:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    return strategy_class(settings, symbol)
```

---

### Phase 4: Runtime Loop Updates

**File:** `src/tradebot_sci/runtime/loop.py`

Update the main trading loop to use per-symbol strategies:

```python
# BEFORE (single strategy for all symbols):
strategy = get_strategy(settings)
for symbol in symbols:
    signal = strategy.analyze(symbol, data)

# AFTER (per-symbol strategy selection):
for symbol in symbols:
    strategy = get_strategy_for_symbol(settings, symbol)
    signal = strategy.analyze(symbol, data)
```

#### Key Changes:
1. Move strategy instantiation inside the symbol loop
2. Cache strategy instances per symbol to avoid recreation
3. Log which strategy is being used for each symbol

```python
class TradingLoop:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._strategy_cache: Dict[str, BaseStrategy] = {}

    def get_strategy(self, symbol: str) -> BaseStrategy:
        """Get or create cached strategy for symbol."""
        if symbol not in self._strategy_cache:
            self._strategy_cache[symbol] = get_strategy_for_symbol(
                self.settings, symbol
            )
            logger.info(
                f"Using strategy '{self.settings.get_strategy_for_symbol(symbol)}' "
                f"for {symbol} ({classify_symbol(symbol).value})"
            )
        return self._strategy_cache[symbol]

    def run_cycle(self, symbols: List[str]):
        for symbol in symbols:
            strategy = self.get_strategy(symbol)
            # ... rest of trading logic
```

---

### Phase 5: GUI Integration

**File:** `src/tradebot_sci/electron_gui/settings.js`

The GUI already has the Asset Strategies tab implemented with:
- `ASSET_CLASSES` constant defining 6 asset classes
- `STRATEGIES` constant with all 9 strategies
- Per-asset dropdown selectors with live description updates
- Environment keys: `STRATEGY_CRYPTO`, `STRATEGY_FOREX`, etc.

#### 5.1 Update Main Process IPC

**File:** `src/tradebot_sci/electron_gui/main.js`

Add handler to read/write per-asset strategies to the YAML profiles:

```javascript
ipcMain.handle('read-profile-strategies', async (event, profileName) => {
    const yaml = require('js-yaml');
    if (!fs.existsSync(PROFILES_PATH)) return null;
    const content = fs.readFileSync(PROFILES_PATH, 'utf8');
    const profiles = yaml.load(content);
    return profiles?.profiles?.[profileName]?.strategies || null;
});

ipcMain.handle('save-profile-strategies', async (event, profileName, strategies) => {
    const yaml = require('js-yaml');
    const content = fs.readFileSync(PROFILES_PATH, 'utf8');
    const profiles = yaml.load(content);

    if (!profiles.profiles[profileName]) {
        profiles.profiles[profileName] = {};
    }
    profiles.profiles[profileName].strategies = strategies;

    fs.writeFileSync(PROFILES_PATH, yaml.dump(profiles, { lineWidth: -1 }));
    return { success: true };
});
```

---

### Phase 6: Logging & Observability

Add clear logging to track which strategy is used for each trade:

```python
# In entry signal generation
logger.info(
    f"[{symbol}] Strategy: {strategy_name} | "
    f"Asset Class: {asset_class.value} | "
    f"Signal: {signal.direction}"
)

# In trade execution
logger.info(
    f"ENTRY [{symbol}] Using {strategy_name} strategy | "
    f"Side: {side} | Size: {size} | Entry: {entry_price}"
)
```

---

## Migration Notes

### Backward Compatibility

The implementation maintains full backward compatibility:

1. **If `strategies` is not defined:** Falls back to `strategy_variant`
2. **If asset class is unknown:** Falls back to `strategy_variant`
3. **Existing profiles work unchanged:** Only adds new functionality

### Environment Variable Override

For quick testing, support env var overrides:

```bash
# Override all strategies to use robocop
STRATEGY_VARIANT=robocop

# Or override specific asset classes
STRATEGY_CRYPTO=robocop
STRATEGY_FOREX=quantum
```

---

## Testing Checklist

- [ ] Symbol classifier correctly identifies all asset classes
- [ ] Settings model loads `strategies` from YAML
- [ ] `get_strategy_for_symbol()` returns correct strategy
- [ ] Strategy cache prevents duplicate instantiation
- [ ] GUI saves per-asset strategies correctly
- [ ] Logs show which strategy is used for each symbol
- [ ] Backward compatibility with profiles lacking `strategies`
- [ ] Environment variable overrides work

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `utils/symbol_classifier.py` | CREATE | Symbol to asset class mapping |
| `config/models.py` | MODIFY | Add `PerAssetStrategies`, `get_strategy_for_symbol()` |
| `strategies/factory.py` | MODIFY | Update to use per-symbol strategy selection |
| `runtime/loop.py` | MODIFY | Cache strategies per symbol, use new factory |
| `electron_gui/main.js` | MODIFY | Add IPC handlers for profile strategies |
| `electron_gui/settings.js` | DONE | Already implemented Asset Strategies tab |
| `config/settings_profiles.yaml` | DONE | Added `strategies` block to all profiles |

---

## Available Strategies

| Key | Name | Best For |
|-----|------|----------|
| `rubberband_reaper` | Rubberband Reaper | Ranging markets, volatile assets |
| `robocop` | RoboCop | Trending markets, high volatility |
| `evolution` | Robot Evolution | Sideways markets, consolidation |
| `quantum` | Quantum | Strong trending forex pairs |
| `mean_reversion` | Mean Reversion | Ranging crypto and forex |
| `hyper_scalper` | HyperScalper | Liquid forex, fast markets |
| `london_breakout` | London Breakout | GBP pairs, European session |
| `volatility_breakout` | Volatility Breakout | Any market showing compression |
| `aggregator` | Singularity Aggregator | Maximizing capital efficiency |

---

## Timeline Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: Symbol Classifier | ~2 hours |
| Phase 2: Settings Model | ~1 hour |
| Phase 3: Strategy Factory | ~1 hour |
| Phase 4: Runtime Loop | ~2 hours |
| Phase 5: GUI Integration | DONE |
| Phase 6: Logging | ~30 min |
| Testing | ~2 hours |
| **Total** | **~8-9 hours** |

---

## Notes for AI Implementers

1. **Start with Phase 1** - The symbol classifier is the foundation
2. **Test incrementally** - Each phase should be testable independently
3. **Preserve existing behavior** - Always fall back to `strategy_variant`
4. **Cache strategies** - Don't recreate strategy objects every cycle
5. **Log clearly** - Users should see which strategy is being used
