"""Bot Health Monitor — Self-diagnostic vitals system.

Tracks 8 vital signs of bot health and broadcasts them to the GUI
via WebSocket.  Each vital maps to a real failure mode that has caused
actual downtime in past sessions.

Vitals
------
1. Heartbeat       — loop cycle is alive
2. Indicator        — enabled indicators returning non-zero
3. Data Feed        — candle data arriving for watched symbols
4. Trade Pipeline   — candidates being evaluated
5. Broker Link      — broker authenticated and responding
6. Config Integrity — config parses cleanly
7. Risk Sizing      — position sizes match configured risk %
8. Strategy Signal  — engine producing non-HOLD signals
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Status enum ──────────────────────────────────────────
HEALTHY  = "healthy"
WARNING  = "warning"
CRITICAL = "critical"


@dataclass
class Vital:
    """A single health vital with triage state."""
    name: str
    icon: str                       # Material Symbols icon name
    status: str = HEALTHY
    message: str = ""               # Human-readable (for the user)
    detail: str = ""                # Technical detail (for the developer)
    last_checked: float = 0.0       # epoch seconds
    since: float = 0.0              # when this status began (epoch)

    def set(self, status: str, message: str, detail: str = "") -> None:
        now = time.time()
        if status != self.status:
            self.since = now
        self.status = status
        self.message = message
        self.detail = detail
        self.last_checked = now

    def to_dict(self) -> dict[str, Any]:
        now = time.time()
        return {
            "name": self.name,
            "icon": self.icon,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
            "last_checked": self.last_checked,
            "seconds_ago": round(now - self.last_checked, 1) if self.last_checked else None,
            "since": self.since,
            "status_duration": round(now - self.since, 1) if self.since else None,
        }


class HealthMonitor:
    """Singleton health monitor that tracks 8 vital signs."""

    _instance: Optional["HealthMonitor"] = None

    def __init__(self) -> None:
        self.vitals: dict[str, Vital] = {
            "heartbeat":  Vital("Heartbeat",           "monitor_heart"),
            "indicators": Vital("Indicator Integrity",  "air"),
            "data_feed":  Vital("Data Feed",            "sensors"),
            "pipeline":   Vital("Trade Pipeline",       "science"),
            "broker":     Vital("Broker Link",          "cable"),
            "config":     Vital("Config Integrity",     "genetics"),
            "risk":       Vital("Risk Sizing",          "balance"),
            "signal":     Vital("Strategy Signal",      "cell_tower"),
        }
        self._start_ts = time.time()
        self._events: list[dict[str, Any]] = []  # session timeline

        # Tracking state
        self._last_heartbeat_ts: float = 0.0
        self._indicator_zero_counts: dict[str, int] = {}
        self._data_feed_ts: dict[str, float] = {}
        self._candidate_count_window: list[int] = []  # rolling window
        self._hold_only_cycles: int = 0
        self._last_signal_ts: float = 0.0
        self._last_signal_detail: str = ""
        self._cycle_count: int = 0
        self._last_risk_detail: str = ""
        self._market_hours_active: bool = True

    @classmethod
    def get(cls) -> "HealthMonitor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (useful for testing)."""
        cls._instance = None

    # ──────────────────────────────────────────────────────
    # Event Timeline
    # ──────────────────────────────────────────────────────
    def add_event(self, label: str, level: str = "info") -> None:
        """Record a session timeline event."""
        self._events.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "label": label,
            "level": level,  # info, warn, error, trade
        })
        # Cap at 100 events
        if len(self._events) > 100:
            self._events = self._events[-100:]

    # ──────────────────────────────────────────────────────
    # Vital #1: Heartbeat
    # ──────────────────────────────────────────────────────
    def record_heartbeat(self, sabbath_active: bool = False) -> None:
        """Called at the top of each bot loop cycle."""
        self._last_heartbeat_ts = time.time()
        self._cycle_count += 1
        self._market_hours_active = not sabbath_active
        self._evaluate_heartbeat()

    @property
    def is_warming_up(self) -> bool:
        return self._cycle_count <= 10

    def _evaluate_heartbeat(self) -> None:
        v = self.vitals["heartbeat"]
        now = time.time()
        uptime = now - self._start_ts
        uptime_str = self._format_duration(uptime)

        if not self._market_hours_active:
            v.set(HEALTHY,
                  "Market is closed / Sabbath active — bot is resting normally.",
                  f"Last cycle: {now - self._last_heartbeat_ts if self._last_heartbeat_ts else 0:.0f}s ago | Uptime: {uptime_str} | Cycles: {self._cycle_count}")
            return

        if self._last_heartbeat_ts > 0:
            age = now - self._last_heartbeat_ts
        else:
            # If heartbeat hasn't been recorded yet but bot just booted, use uptime as age
            age = uptime if uptime < 120 else 9999

        if age < 60:
            v.set(HEALTHY,
                  "The bot's heart is beating normally.",
                  f"Last cycle: {age:.0f}s ago | Uptime: {uptime_str} | Cycles: {self._cycle_count}")
        elif age < 180:
            v.set(WARNING,
                  "The bot hasn't checked the market in over a minute — it might be slow.",
                  f"Last cycle: {age:.0f}s ago | Uptime: {uptime_str}")
        else:
            v.set(CRITICAL,
                  "The bot hasn't checked the market in over 3 minutes — it might be frozen!",
                  f"Last cycle: {age:.0f}s ago | Uptime: {uptime_str}")

    # ──────────────────────────────────────────────────────
    # Vital #2: Indicator Integrity
    # ──────────────────────────────────────────────────────
    def record_indicators(self, indicator_values: dict[str, float]) -> None:
        """Called after indicator computation each cycle.
        
        Args:
            indicator_values: e.g. {"macd": 0.0, "rsi": 55.2, "adx": 0.0, ...}
        """
        for name, val in indicator_values.items():
            if val == 0.0 or val is None:
                self._indicator_zero_counts[name] = self._indicator_zero_counts.get(name, 0) + 1
            else:
                self._indicator_zero_counts[name] = 0
        self._evaluate_indicators()

    def _evaluate_indicators(self) -> None:
        v = self.vitals["indicators"]
        if self.is_warming_up:
            v.set(HEALTHY,
                  "Strategy warm-up in progress — populating indicator buffers.",
                  f"Cycle {self._cycle_count}/10 warm-up")
            return

        zeroed = {k: c for k, c in self._indicator_zero_counts.items() if c >= 5}
        all_zero = all(c >= 5 for c in self._indicator_zero_counts.values()) if self._indicator_zero_counts else False

        if not zeroed:
            v.set(HEALTHY,
                  "All market sensors are reading data correctly.",
                  f"Tracking {len(self._indicator_zero_counts)} indicators — all non-zero")
        elif all_zero and len(self._indicator_zero_counts) >= 3:
            names = ", ".join(zeroed.keys())
            v.set(CRITICAL,
                  "ALL market sensors are blind — the bot cannot detect trends! This is an emergency.",
                  f"All indicators returning zero for {min(zeroed.values())}+ cycles: {names}")
            self.add_event(f"CRITICAL: All indicators zeroed ({names})", "error")
        elif len(zeroed) >= 2:
            names = ", ".join(f"{k}({c} cycles)" for k, c in zeroed.items())
            v.set(WARNING,
                  f"Some market sensors are returning zero — the bot may have reduced accuracy.",
                  f"Zeroed indicators: {names}")
        else:
            name, count = next(iter(zeroed.items()))
            v.set(WARNING,
                  f"The {name.upper()} indicator is returning zero — it may be misconfigured.",
                  f"{name} has returned 0 for {count} consecutive cycles")

    # ──────────────────────────────────────────────────────
    # Vital #3: Data Feed
    def set_active_symbols(self, symbols: list[str]) -> None:
        """Prune outdated symbols from trackers when profile changes."""
        old_keys = list(self._data_feed_ts.keys())
        for k in old_keys:
            if k not in symbols:
                del self._data_feed_ts[k]

    def record_data_feed(self, symbol: str, success: bool = True) -> None:
        """Called after each candle fetch attempt."""
        if success and symbol != "__all__":
            self._data_feed_ts[symbol] = time.time()
        self._evaluate_data_feed()

    def _evaluate_data_feed(self) -> None:
        v = self.vitals["data_feed"]

        if not self._market_hours_active:
            v.set(HEALTHY,
                  "Market is closed — no new pricing data expected.",
                  "Off-hours mode")
            return

        if not self._data_feed_ts:
            v.set(WARNING,
                  "No market data received yet — waiting for the first price update.",
                  "No symbols have reported data")
            return

        now = time.time()
        stale_600 = [s for s, ts in self._data_feed_ts.items() if now - ts > 600]
        stale_300 = [s for s, ts in self._data_feed_ts.items() if now - ts > 300]
        total = len(self._data_feed_ts)
        fresh = total - len(stale_300)

        if not stale_300:
            v.set(HEALTHY,
                  f"Live market data flowing for all {total} assets.",
                  f"All {total} symbols received fresh candles within 5 minutes")
        elif stale_600:
            v.set(CRITICAL,
                  f"Price data stale for {', '.join(stale_600)} — charts may be outdated!",
                  f"{len(stale_600)}/{total} symbols have no data for 10+ minutes")
        else:
            v.set(WARNING,
                  f"Price data delayed for {', '.join(stale_300)}.",
                  f"{len(stale_300)}/{total} symbols delayed >5min | {fresh}/{total} fresh")

    # ──────────────────────────────────────────────────────
    # Vital #4: Trade Pipeline
    # ──────────────────────────────────────────────────────
    def record_pipeline(self, candidates_evaluated: int) -> None:
        """Called after candidate evaluation each cycle."""
        self._candidate_count_window.append(candidates_evaluated)
        if len(self._candidate_count_window) > 100:
            self._candidate_count_window = self._candidate_count_window[-100:]
        self._evaluate_pipeline()

    def _evaluate_pipeline(self) -> None:
        v = self.vitals["pipeline"]
        window = self._candidate_count_window

        if not window:
            v.set(HEALTHY,
                  "The trade scanner is warming up...",
                  "No cycle data yet")
            return

        # Count cycles with at least 1 candidate in recent window
        recent = window[-60:] if len(window) >= 60 else window
        cycles_with_candidates = sum(1 for c in recent if c > 0)
        total_candidates = sum(recent)

        if not self._market_hours_active:
            v.set(HEALTHY,
                  "Market is closed — scanner is on standby.",
                  f"Off-hours mode | {self._cycle_count} total cycles completed")
            return

        if cycles_with_candidates > 0:
            v.set(HEALTHY,
                  f"The bot is actively scanning for opportunities ({total_candidates} candidates in last {len(recent)} cycles).",
                  f"{cycles_with_candidates}/{len(recent)} cycles found opportunities")
        elif len(window) >= 60:
            v.set(CRITICAL,
                  "The bot hasn't found anything to evaluate in a long time — the strategy engine might be stuck!",
                  f"0 candidates in last {len(recent)} cycles during market hours")
            self.add_event("CRITICAL: 0 candidates for 60+ cycles", "error")
        elif len(window) >= 20:
            v.set(WARNING,
                  "The bot hasn't found any trade candidates recently — this is unusual during market hours.",
                  f"0 candidates in last {len(window)} cycles")
        else:
            v.set(HEALTHY,
                  "The trade scanner is warming up...",
                  f"Only {len(window)} cycles completed — still building data")

    # ──────────────────────────────────────────────────────
    # Vital #5: Broker Link
    # ──────────────────────────────────────────────────────
    def record_broker(self, connected: bool, broker_name: str = "OANDA",
                      latency_ms: float | None = None,
                      error: str | None = None) -> None:
        """Called after each broker API interaction."""
        v = self.vitals["broker"]

        if connected and not error:
            lat_str = f" | Latency: {latency_ms:.0f}ms" if latency_ms else ""
            if latency_ms and latency_ms > 5000:
                v.set(WARNING,
                      f"Connected to {broker_name} but response is very slow ({latency_ms:.0f}ms).",
                      f"{broker_name} authenticated OK{lat_str} — high latency")
            else:
                v.set(HEALTHY,
                      f"Connected to {broker_name} — orders will execute normally.",
                      f"{broker_name} authenticated OK{lat_str}")
        elif error:
            v.set(CRITICAL,
                  f"Broker connection error — trades cannot be placed! Error: {error[:80]}",
                  f"{broker_name} error: {error}")
            self.add_event(f"Broker error: {error[:60]}", "error")
        else:
            v.set(CRITICAL,
                  f"{broker_name} is disconnected — trades cannot be placed!",
                  f"{broker_name} connection lost")

    # ──────────────────────────────────────────────────────
    # Vital #6: Config Integrity
    # ──────────────────────────────────────────────────────
    def record_config(self, valid: bool, profile_name: str = "",
                      errors: list[str] | None = None,
                      warnings: list[str] | None = None) -> None:
        """Called on config load/save."""
        v = self.vitals["config"]
        errs = errors or []
        warns = warnings or []

        if valid and not errs:
            detail = f"Profile: {profile_name}" if profile_name else "Config parsed OK"
            if warns:
                v.set(WARNING,
                      f"Settings loaded but with {len(warns)} warning(s).",
                      f"{detail} | Warnings: {'; '.join(warns[:3])}")
            else:
                v.set(HEALTHY,
                      "All settings are valid and applied correctly.",
                      detail)
        else:
            v.set(CRITICAL,
                  "Settings file has errors — the bot may not start correctly!",
                  f"Errors: {'; '.join(errs[:3])}")
            self.add_event(f"Config error: {errs[0] if errs else 'unknown'}", "error")

    # ──────────────────────────────────────────────────────
    # Vital #7: Risk Sizing
    # ──────────────────────────────────────────────────────
    def record_risk_sizing(self, configured_risk_pct: float,
                           actual_position_usd: float,
                           account_equity: float,
                           symbol: str = "",
                           leverage_capped: bool = False,
                           total_notional_sum: float = 0.0) -> None:
        """Called after position sizing calculation."""
        v = self.vitals["risk"]

        if self.is_warming_up:
            v.set(HEALTHY,
                  "Strategy warm-up in progress — establishing risk baselines.",
                  f"Cycle {self._cycle_count}/10 warm-up")
            return

        if account_equity <= 0:
            v.set(WARNING,
                  "Account equity is zero — risk calculation not possible.",
                  f"Equity: ${account_equity:.2f}")
            return

        expected_risk_usd = account_equity * (configured_risk_pct / 100.0)
        if expected_risk_usd <= 0:
            v.set(HEALTHY,
                  "No risk configured — trade sizing skipped.",
                  f"Risk %: {configured_risk_pct}%")
            return

        # Check if leverage_capped is True or if the broker's safety guards intentionally limited position size
        if leverage_capped:
            detail = (f"{symbol}: {configured_risk_pct}% of ${account_equity:.0f} = "
                      f"${expected_risk_usd:.2f} expected, ${actual_position_usd:.2f} actual "
                      f"[LEVERAGE CAPPED] (Total Notional: ${total_notional_sum:,.2f})")
            self._last_risk_detail = detail
            v.set(HEALTHY,
                  f"Trade size limited safely by leverage cap ({symbol} actual: ${actual_position_usd:.2f}).",
                  detail)
            return

        deviation = abs(actual_position_usd - expected_risk_usd) / expected_risk_usd

        # If we have total_notional_sum, perform aggregate exposure check
        if total_notional_sum > 0:
            agg_ratio = total_notional_sum / account_equity if account_equity > 0 else 0.0
            detail = (f"{symbol}: {configured_risk_pct}% of ${account_equity:.0f} = "
                      f"${expected_risk_usd:.2f} exp, ${actual_position_usd:.2f} act "
                      f"(dev: {deviation:.0%}) | Agg Exposure: ${total_notional_sum:,.2f} ({agg_ratio:.1f}x equity)")
            self._last_risk_detail = detail

            if deviation < 0.20:
                v.set(HEALTHY,
                      f"Trade sizes match your risk settings ({configured_risk_pct}% = ${expected_risk_usd:.0f}).",
                      detail)
            elif deviation < 0.80: # Relaxed threshold for aggregate/multi-position checks
                v.set(WARNING,
                      f"Position sizing deviation ({deviation:.0%}) within relaxed multi-position aggregate limits.",
                      detail)
            else:
                v.set(CRITICAL,
                      f"Trade sizes differ significantly from expected risk ({deviation:.0%} deviation).",
                      detail)
                self.add_event(f"Risk deviation: {deviation:.0%} on {symbol}", "warn")
        else:
            detail = (f"{symbol}: {configured_risk_pct}% of ${account_equity:.0f} = "
                      f"${expected_risk_usd:.2f} expected, ${actual_position_usd:.2f} actual "
                      f"(deviation: {deviation:.0%})")
            self._last_risk_detail = detail

            if deviation < 0.20:
                v.set(HEALTHY,
                      f"Trade sizes match your risk settings ({configured_risk_pct}% = ${expected_risk_usd:.0f}).",
                      detail)
            elif deviation < 0.50:
                v.set(WARNING,
                      "The bot is placing smaller trades than expected — minimum lot sizing may be rounding down.",
                      detail)
            else:
                v.set(CRITICAL,
                      "Trade sizes are very different from your expected risk. Risk configuration might be broken!",
                      detail)
                self.add_event(f"Risk deviation: {deviation:.0%} on {symbol}", "warn")

    # ──────────────────────────────────────────────────────
    # Vital #8: Strategy Signal
    # ──────────────────────────────────────────────────────
    def record_signal(self, signal: str, symbol: str = "") -> None:
        """Called after strategy engine produces a signal.
        
        Args:
            signal: "BUY", "SELL", "HOLD", etc.
        """
        signal_upper = signal.upper() if signal else "HOLD"
        if signal_upper in ("BUY", "SELL", "LONG", "SHORT"):
            self._hold_only_cycles = 0
            self._last_signal_ts = time.time()
            self._last_signal_detail = f"{signal_upper} {symbol}"
            self.add_event(f"Signal: {signal_upper} {symbol}", "trade")
        else:
            self._hold_only_cycles += 1
        self._evaluate_signal()

    def _evaluate_signal(self) -> None:
        v = self.vitals["signal"]

        if not self._market_hours_active:
            v.set(HEALTHY,
                  "Market is closed — no signals expected.",
                  "Off-hours / session lockout active")
            return

        if self._hold_only_cycles == 0 or self._last_signal_ts > 0:
            age = time.time() - self._last_signal_ts if self._last_signal_ts else 0
            if age < 60 and self._last_signal_detail:
                v.set(HEALTHY,
                      f"Latest signal: {self._last_signal_detail}.",
                      f"Signal {self._format_duration(age)} ago | HOLD streak: {self._hold_only_cycles} cycles")
            elif self._hold_only_cycles < 30:
                v.set(HEALTHY,
                      "The strategy is actively analyzing the market.",
                      f"Last signal: {self._last_signal_detail or 'none yet'} | HOLD streak: {self._hold_only_cycles} cycles")
            elif self._hold_only_cycles < 100:
                v.set(WARNING,
                      "The strategy has been saying HOLD for a while — no trade opportunities found.",
                      f"HOLD for {self._hold_only_cycles} consecutive cycles | Last signal: {self._last_signal_detail or 'none'}")
            else:
                v.set(CRITICAL,
                      "The strategy hasn't suggested a trade in a very long time — indicators may be misconfigured!",
                      f"HOLD for {self._hold_only_cycles} consecutive cycles | Last signal: {self._last_signal_detail or 'never'}")
                self.add_event(f"Strategy stuck: HOLD for {self._hold_only_cycles} cycles", "error")
        else:
            if self._cycle_count < 5:
                v.set(HEALTHY,
                      "Strategy engine is warming up...",
                      f"Only {self._cycle_count} cycles completed")
            else:
                v.set(HEALTHY,
                      "No signals yet — the strategy is analyzing initial data.",
                      f"Warming up ({self._cycle_count} cycles)")

    # ──────────────────────────────────────────────────────
    # Market Hours Awareness
    # ──────────────────────────────────────────────────────
    def set_market_hours(self, active: bool) -> None:
        """Tell the monitor whether market hours are active."""
        self._market_hours_active = active

    # ──────────────────────────────────────────────────────
    # Aggregation
    # ──────────────────────────────────────────────────────
    def get_vitals(self) -> dict[str, Any]:
        """Return all vitals as a dict for WebSocket broadcast."""
        # Re-evaluate time-sensitive vitals
        self._evaluate_heartbeat()

        vitals_list = [v.to_dict() for v in self.vitals.values()]

        # Overall status: worst of all vitals
        statuses = [v.status for v in self.vitals.values()]
        if CRITICAL in statuses:
            overall = CRITICAL
            overall_message = "CRITICAL — Immediate attention required!"
        elif WARNING in statuses:
            overall = WARNING
            overall_message = "Attention needed — some vitals are degraded."
        else:
            overall = HEALTHY
            overall_message = "All systems operational."

        return {
            "overall": overall,
            "overall_message": overall_message,
            "uptime": round(time.time() - self._start_ts, 1),
            "uptime_formatted": self._format_duration(time.time() - self._start_ts),
            "cycle_count": self._cycle_count,
            "vitals": {v["name"]: v for v in vitals_list},
            "events": self._events[-20:],  # Last 20 events for timeline
        }

    # ──────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        elif s < 3600:
            return f"{s // 60}m {s % 60}s"
        else:
            h = s // 3600
            m = (s % 3600) // 60
            return f"{h}h {m}m"


# Module-level singleton
health_monitor = HealthMonitor.get()
