
import csv
import io
import os
import json
import logging
from datetime import datetime, timezone
from typing import List

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.simulation.utils import resample_candles
from tools.utils.downloader import ensure_data_exists

logger = logging.getLogger(__name__)

# ── Timeframe helpers ─────────────────────────────────────────────────
_TF_SECONDS = {
    "1m": 60, "2m": 120, "3m": 180, "5m": 300, "10m": 600,
    "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
    "4h": 14400, "8h": 28800, "1d": 86400,
}

def _tf_to_seconds(tf: str) -> int:
    return _TF_SECONDS.get(tf, 300)


class LocalJSONProvider:
    """Reads candles from JSON or CSV files and serves them to the backtester.

    Snapshot construction mirrors the LIVE bot's cycle.py:fetch_snapshot()
    to ensure backtester ↔ live parity.
    """
    def __init__(self, data_dir, settings=None):
        self.data_dir = data_dir
        self.settings = settings
        self._cache = {}

    # ── File Loading ──────────────────────────────────────────────────
    def _load_candles_from_file(self, path: str) -> List[Candle]:
        """Load candles from a JSON or CSV file."""
        if path.endswith(".csv"):
            return self._load_csv(path)
        return self._load_json(path)

    def _load_json(self, path: str) -> List[Candle]:
        try:
            with open(path, "r") as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to read {path}: {e}")
            return []

        candles = []
        for item in raw_data:
            ts = datetime.fromisoformat(item["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            candles.append(Candle(
                timestamp=ts,
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
            ))
        return candles

    def _load_csv(self, path: str) -> List[Candle]:
        candles = []
        try:
            with open(path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts_str = row["timestamp"]
                    # Handle OANDA-style timestamps with +00:00 or Z
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    candles.append(Candle(
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0)),
                    ))
        except Exception as e:
            print(f"[ERROR] Failed to read CSV {path}: {e}")
        return candles

    def fetch_historical_candles(self, symbol, timeframe, start_date, end_date, file_path=None):
        # Map symbol "EUR/USD" -> "EURUSD"
        file_symbol = symbol.replace("/", "")

        # Try multiple file formats: JSON first, then CSV
        for ext in (".json", ".csv"):
            file_name = f"{file_symbol}_{timeframe}{ext}"
            path = os.path.join(self.data_dir, file_name)
            if path in self._cache:
                # Already loaded
                filtered = [c for c in self._cache[path] if start_date <= c.timestamp <= end_date]
                return filtered
            if os.path.exists(path):
                candles = self._load_candles_from_file(path)
                self._cache[path] = candles
                print(f"[INFO] Loaded {len(candles)} candles from {file_name}")
                filtered = [c for c in candles if start_date <= c.timestamp <= end_date]
                return filtered

        # Neither format found — try auto-download
        json_name = f"{file_symbol}_{timeframe}.json"
        json_path = os.path.join(self.data_dir, json_name)
        print(f"[PROVIDER] Data missing for {symbol}. Attempting auto-download...")
        success = ensure_data_exists(symbol, timeframe, start_date, end_date, self.data_dir)
        if not success:
            print(f"[WARN] Data file not found and download failed: {json_path}")
            return []
        # Retry after download
        if os.path.exists(json_path):
            candles = self._load_json(json_path)
            self._cache[json_path] = candles
            filtered = [c for c in candles if start_date <= c.timestamp <= end_date]
            return filtered
        return []

    def get_latest_candles(self, symbol, timeframe, limit):
         # The backtester populates _cache["{symbol}:{timeframe}_current"] each bar.
         cache_key = f"{symbol}:{timeframe}_current"
         return self._cache.get(cache_key, [])[-limit:]

    def get_latest_snapshot(self, symbol, timeframe):
        """Build a MarketSnapshot that MATCHES the live bot's cycle.py:fetch_snapshot().

        Key rules for parity:
        1. Use the profile's htf_timeframe / ltf_timeframe (NOT hardcoded)
        2. Set trends to NEUTRAL — let trend_consensus.py handle detection
        3. Populate htf_timeframe and ltf_timeframe fields in the snapshot
        """
        # ── Determine timeframes from profile (same as live bot) ──────
        profile = None
        if self.settings:
            try:
                profile = self.settings.get_active_profile()
            except Exception:
                pass

        htf_timeframe = getattr(profile, "htf_timeframe", None) or "4h"
        ltf_timeframe = getattr(profile, "ltf_timeframe", None) or timeframe
        max_candles = 200

        # ── Fetch candles (same approach as live bot's fetch_snapshot) ─
        ltf_candles = self.get_latest_candles(symbol, ltf_timeframe, limit=max_candles)

        # HTF: Check if native HTF candles exist in cache (populated by
        # backtester from htf_data_paths or from file), otherwise resample
        htf_cache_key = f"{symbol}:{htf_timeframe}_current"
        native_htf = self._cache.get(htf_cache_key)
        if native_htf and len(native_htf) >= 20:
            htf_candles = native_htf
        else:
            # Resample from base candles to the CORRECT HTF
            base_candles = self.get_latest_candles(symbol, timeframe, limit=500)
            htf_seconds = _tf_to_seconds(htf_timeframe)
            base_seconds = _tf_to_seconds(timeframe)
            if htf_seconds != base_seconds and base_candles:
                htf_candles = resample_candles(base_candles, htf_seconds)
            else:
                htf_candles = base_candles

        # ── NEUTRAL trend — engine.py's trend_consensus handles this ──
        _neutral = TrendState(direction="neutral", strength=0.0)

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=ltf_candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=htf_timeframe,
            ltf_timeframe=ltf_timeframe,
        )
