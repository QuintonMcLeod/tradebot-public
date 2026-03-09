#!/usr/bin/env python3
"""
MinovskyEngine — the core trading engine, built on the Backtester foundation.

This is NOT a reimplementation — it directly uses the Backtester's run_backtest()
method, which already handles:
  • Multi-position (max_concurrent_positions)
  • OHLC SL/TP simulation
  • Tiered Guillotine (partial-close cascade)
  • SAR (Stop-and-Reverse) with chain guards
  • Counter-Reversal (CR)
  • Position sizing with risk caps
  • Consecutive-loss cooldown
  • Session management (EOD flatten, hold guards)
  • Compound Flywheel
  • Trailing stops
  • Pyramid entries
  • Dust guards

The class is called MinovskyEngine — named after the Gundam Minovsky Particle
Reactor. Just as the Minovsky Reactor is the power source that ALL mobile suit
systems connect to, this engine is the foundation that ALL trading systems
(SAR, CR, Guillotine, ICC, Safety Guards) plug into.
"""

import importlib.util
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src/ is on path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from tradebot_sci.config.models import (
    AISettings,
    AppSettings,
    LoggingSettings,
    MarketSettings,
    Settings,
)
from tradebot_sci.simulation.backtester import BacktestResult, Backtester
from tools.utils.local_provider import LocalJSONProvider

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Cartridge Loader
# ──────────────────────────────────────────────────────────────────────────────

def load_cartridge(cartridge_name: str) -> dict:
    """Load a cartridge config from tools/cartridges/<name>.py."""
    cart_dir = _ROOT / "tools" / "cartridges"
    cart_file = cart_dir / f"{cartridge_name}.py"
    if not cart_file.exists():
        raise FileNotFoundError(
            f"Cartridge '{cartridge_name}' not found at {cart_file}"
        )

    spec = importlib.util.spec_from_file_location(cartridge_name, str(cart_file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if not hasattr(mod, "get_config"):
        raise ValueError(
            f"Cartridge '{cartridge_name}' missing get_config() function"
        )

    config = mod.get_config()

    # Run apply_overrides if present
    if hasattr(mod, "apply_overrides"):
        mod.apply_overrides()

    return config


# ──────────────────────────────────────────────────────────────────────────────
# MinovskyEngine
# ──────────────────────────────────────────────────────────────────────────────

class MinovskyEngine:
    """
    Trading engine built on the Backtester foundation.

    Usage:
        engine = MinovskyEngine.from_cartridge("conductor_14d_all")
        result = engine.run()
        print(f"PnL: ${result.total_pnl:.2f}")
        print(f"Trades: {len(result.trades)}")
    """

    def __init__(
        self,
        settings: Settings,
        initial_capital: float = 5500.0,
        symbols: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_dir: Optional[str] = None,
        htf_data_paths: Optional[Dict[str, str]] = None,
        force_market_open: bool = False,
        wind_down_days: int = 0,
        runtime_config: Optional[dict] = None,
    ):
        self.settings = settings
        self.initial_capital = initial_capital
        self.symbols = symbols or settings.market.symbols
        self.start_date = start_date
        self.end_date = end_date
        self.data_dir = data_dir
        self.htf_data_paths = htf_data_paths
        self.force_market_open = force_market_open
        self.wind_down_days = wind_down_days

        # Create the Backtester — the real simulation engine
        self._backtester = Backtester(
            ib=None, settings=settings, ai_client=None
        )

        # Inject local data provider if data_dir specified
        if data_dir:
            self._backtester.market_provider = LocalJSONProvider(
                data_dir, settings=settings
            )

        # Force 24/7 trading if requested
        if force_market_open:
            self._backtester._is_market_hours_utc = lambda ts: True

    # ── Factory: create from cartridge ────────────────────────────────────

    @classmethod
    def from_cartridge(
        cls,
        cartridge_name: str,
        symbol_override: Optional[List[str]] = None,
        strategy_override: Optional[str] = None,
    ) -> "MinovskyEngine":
        """Create engine from a cartridge config (same pattern as mega_backtester)."""
        config = load_cartridge(cartridge_name)

        profile_settings = config["profile_settings"]
        symbols = config["symbols"]
        start_date = config["start_date"]
        end_date = config["end_date"]
        initial_capital = config.get("initial_capital", 5500.0)
        data_dir_name = config.get("data_dir_name", "forex_backtest")
        force_market_open = config.get("force_market_open", False)
        htf_data_paths = config.get("htf_data_paths")
        wind_down_days = config.get("wind_down_days", 0)

        # Override strategy if requested
        if strategy_override:
            profile_settings.strategy_variant = strategy_override

        # Override symbols if requested
        if symbol_override:
            symbols = symbol_override

        # Build synthetic Settings — exact same pattern as mega_backtester
        profile_name = "EngineProfile"
        settings_kwargs = dict(
            app=AppSettings(profile_name=profile_name),
            logging=LoggingSettings(),
            ai=AISettings(provider="openai"),
            market=MarketSettings(symbols=symbols),
            profiles={profile_name: profile_settings},
        )

        # Inject runtime settings if cartridge provides them
        if "runtime_settings" in config:
            from tradebot_sci.config.models import RuntimeSettings
            settings_kwargs["runtime"] = RuntimeSettings(**config["runtime_settings"])

        settings = Settings(**settings_kwargs)

        # Re-inject the profile to ensure it's the active one
        from tradebot_sci.config.models import TradingProfileSettings
        try:
            actual_profile = TradingProfileSettings(**profile_settings)
        except TypeError:
            actual_profile = profile_settings

        profile_key = "engine_profile"
        settings.profiles[profile_key] = actual_profile
        settings.app.profile_name = profile_key

        # Resolve data directory
        data_dir = str(_ROOT / "data" / data_dir_name)

        # Auto-detect HTF data files if not provided
        if htf_data_paths is None and os.path.isdir(data_dir):
            htf_tf = getattr(profile_settings, "htf_timeframe", "4h")
            detected = {}
            for sym in symbols:
                htf_path = os.path.join(data_dir, f"{sym}_{htf_tf}.json")
                if os.path.exists(htf_path):
                    detected[sym] = htf_path
            if detected:
                htf_data_paths = detected
                logger.info(f"[ENGINE] Auto-detected {len(detected)} HTF ({htf_tf}) data files")

        return cls(
            settings=settings,
            initial_capital=initial_capital,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            data_dir=data_dir,
            htf_data_paths=htf_data_paths,
            force_market_open=force_market_open,
            wind_down_days=wind_down_days,
        )

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self) -> BacktestResult:
        """Run the simulation and return results."""
        if not self.start_date or not self.end_date:
            raise ValueError("start_date and end_date are required")

        logger.info(
            f"[ENGINE] Starting simulation: ${self.initial_capital:.2f} capital, "
            f"{self.start_date.date()} to {self.end_date.date()}, "
            f"symbols={self.symbols}"
        )

        result = self._backtester.run_backtest(
            initial_capital=self.initial_capital,
            start_date=self.start_date,
            end_date=self.end_date,
            symbols=self.symbols,
            wind_down_days=self.wind_down_days,
            htf_data_paths=self.htf_data_paths,
        )

        return result
