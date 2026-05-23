from __future__ import annotations

import logging
import time
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.server.ws_server import WebSocketServer
from tradebot_sci.runtime.sabbath import SabbathContext
from tradebot_sci.runtime.scheduling import get_schedule_status
from tradebot_sci.runtime.health_monitor import HealthMonitor, health_monitor
from tradebot_sci.market.models import Candle

logger = logging.getLogger(__name__)

class RuntimeController:
    """Manages environmental interfaces (WS, logs) and high-level loop control."""
    
    def __init__(self, settings: Settings, profile_settings: TradingProfileSettings):
        self.settings = settings
        self.profile_settings = profile_settings
        self.profile_name = settings.app.profile_name
        self.ws_server: Optional[WebSocketServer] = None
        self.last_capital_sync_ts = 0.0
        self.replay_provider = None  # Set by loop.py during Sabbath replay
        self.health_monitor: HealthMonitor = health_monitor
        self._last_health_broadcast_ts = 0.0
        
    def start_ws_server(self, port: int = 8080):
        # Use port from settings if it's not the default or if we want to override
        effective_port = self.settings.runtime.ws_server_port or port
        self.ws_server = WebSocketServer(port=effective_port)
        self.ws_server.set_on_subscribe_callback(self._on_ws_subscribe)
        self.ws_server.start_in_thread()
        logger.info(f"[CONTROLLER] WebSocket server started on port {effective_port}")

    def _on_ws_subscribe(self, symbol: str, timeframe: str):
        """Callback when a new client subscribes to a symbol/timeframe."""
        logger.info(f"[WS] Subscription received for {symbol} ({timeframe})")
        # Immediate state sync would happen here via the runner/orchestrator
        # We'll expose a hook or method for the runner to push data

    def broadcast_state(self, executor: Any, force: bool = False, executor_real: Any = None):
        """Pushes account and bot state to UI via WebSocket."""
        if not self.ws_server:
            return
            
        now = time.time()
        execute_trades = getattr(self.settings.runtime, "execute_trades", True)
        is_paper = not execute_trades
        # If the active executor is not the real executor (e.g., during Sabbath simulation),
        # force UI into paper/simulation mode to reflect the virtual snapshot.
        if executor_real is not None and executor is not executor_real:
            is_paper = True

        # Paper/replay mode: 5s throttle for fast turbo updates; Live: 30s
        throttle = 5.0 if is_paper else 30.0
        if not force and (now - self.last_capital_sync_ts < throttle):
            return
            
        try:
            sabbath_active, _, _ = SabbathContext(self.profile_settings).evaluate(datetime.now(timezone.utc))

            # For GUI display, use actual tracked balance (not sizing-capped value).
            # When the system enters a simulated state (e.g. Sabbath), track the virtual snapshot.
            if not is_paper and executor_real is not None:
                display_source = executor_real
            else:
                display_source = executor

            if display_source and hasattr(display_source, 'get_display_cash'):
                cash = display_source.get_display_cash()
            else:
                cash = display_source.get_liquid_capital() if display_source else 0.0
            total_equity = display_source.get_total_balance_value() if display_source else 0.0
            
            # Get active holdings count from the active executor
            holdings_count = 0
            if executor and hasattr(executor, "list_open_position_symbols"):
                open_symbols = list(executor.list_open_position_symbols() or [])
                active_holds = [
                    s for s in open_symbols 
                    if not (executor.get_open_position_snapshot(s) or {}).get("is_dust", False)
                ]
                holdings_count = len(active_holds)

            # Refresh profile_name from settings each time to catch hot-reloads
            current_profile = getattr(self.settings.app, 'profile_name', self.profile_name)
            if current_profile != self.profile_name:
                logger.info(f"[CONTROLLER] Profile changed: {self.profile_name} -> {current_profile}")
                self.profile_name = current_profile

            # Multi-interval PnL Tracking
            pnl_stats = {}
            if display_source and hasattr(display_source, 'trade_results') and display_source.trade_results:
                store = display_source.trade_results
                for tf_code in ['24h', 'week', 'month', 'year', 'all']:
                    pnl_stats[tf_code] = store.get_stats_for_timeframe(tf_code).get('pnl_usd', 0.0)

            # Extract eval mode locally since paper isn't fully nested in settings
            is_eval = False
            try:
                import json
                from tradebot_sci.paths import CONFIG_FILE
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, "r") as f:
                        is_eval = str(json.load(f).get("paper", {}).get("eval_mode", "false")).lower() == "true"
            except Exception:
                pass

            # Evaluate scheduling status to pass active sessions to GUI
            _, _, active_sessions = get_schedule_status(self.profile_name, datetime.now(timezone.utc), self.settings)

            state_data = {
                "equity": total_equity,
                "capital": total_equity,
                "cash": cash,
                "holdings_count": holdings_count,
                "profile": self.profile_name,
                "profiles": {name: prof.model_dump() for name, prof in self.settings.profiles.items()},
                "symbols": getattr(self.profile_settings, "symbols", []),
                "is_sabbath": sabbath_active,
                "sabbath_mode": sabbath_active,
                "active_sessions": [s.id for s in active_sessions if getattr(s, 'id', None)],
                "is_eval": is_eval,
                "is_paper": is_paper,
                "halted": self.ws_server.is_halted(),
                "pnl_stats": pnl_stats,
                "time_format": getattr(self.settings.runtime, "time_format", "24h"),
            }
            # Include replay info if weekend replay is active
            if self.replay_provider and hasattr(self.replay_provider, 'get_replay_info'):
                state_data.update(self.replay_provider.get_replay_info())
                
            # Include eval metrics if Prop Firm Eval mode is active
            if is_eval and hasattr(self, 'eval_metrics') and self.eval_metrics:
                state_data["eval_metrics"] = self.eval_metrics
                
            logger.info(f"[PRODB-STATE] Broadcasting state: profile={self.profile_name} equity=${total_equity:.2f} cash=${cash:.2f} paper={is_paper}")
            self.ws_server.broadcast_state_sync(state_data)
            self.last_capital_sync_ts = now
        except Exception as e:
            logger.error(f"[CONTROLLER] State broadcast failed: {e}")

    def broadcast_holdings(self, executor: Any, executor_real: Any = None):
        """Send current paper/live holdings to GUI as a dedicated WS message.
        This is more reliable than relying on log-line parsing."""
        if not self.ws_server:
            return
        execute_trades = getattr(self.settings.runtime, "execute_trades", True)
        if execute_trades and executor_real is not None:
            holdings_source = executor_real
        else:
            holdings_source = executor

        if not holdings_source:
            return
        try:
            positions = []
            # Get current candle time from replay provider (or fall back to wall clock)
            sim_time = None
            mp = getattr(holdings_source, 'market_provider', None)
            if mp and hasattr(mp, 'sim_time'):
                sim_time = mp.sim_time
            if sim_time is None:
                sim_time = datetime.now(timezone.utc)

            if hasattr(holdings_source, 'list_open_position_symbols'):
                for sym in (holdings_source.list_open_position_symbols() or []):
                    snap = holdings_source.get_open_position_snapshot(sym)
                    if snap and not snap.get('is_dust', False):
                        # Compute candle-time-based age so GUI shows "15m" not "2 days"
                        entry_str = snap.get('entry_time', '')
                        if entry_str:
                            try:
                                from datetime import datetime as dt
                                entry_dt = dt.fromisoformat(entry_str.replace("Z", "+00:00"))
                                if entry_dt.tzinfo is None:
                                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                                st = sim_time if sim_time.tzinfo else sim_time.replace(tzinfo=timezone.utc)
                                snap['age_seconds'] = max(0, (st - entry_dt).total_seconds())
                            except Exception:
                                snap['age_seconds'] = 0
                        positions.append(snap)
            total_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)
            holdings_data = {
                "count": len(positions),
                "positions": positions,
                "reason": "heartbeat",
                "total_unrealized_pnl": total_pnl,
                "sim_time": sim_time.isoformat() if sim_time else None,
            }
            self.ws_server.broadcast_holdings_sync(holdings_data)
        except Exception as e:
            logger.error(f"[CONTROLLER] Holdings broadcast failed: {e}")

    def broadcast_candle(self, symbol: str, timeframe: str, candle: Candle):
        """Pushes a new candle to the UI."""
        if not self.ws_server:
            return
        c_data = {
            "time": int(candle.timestamp.timestamp()),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": getattr(candle, "volume", 0)
        }
        # Trace volume and timestamp
        self.ws_server.broadcast_candle_sync(symbol, timeframe, c_data)

    def is_halted(self) -> bool:
        return self.ws_server.is_halted() if self.ws_server else False

    # --- AI Commentary Integration ---
    _last_commentary_ts: float = 0.0
    _last_commentary_content: str = ""
    _commentary_call_count_today: int = 0
    _commentary_call_date: str = ""
    _commentary_fired_during_lockout: bool = False
    
    def _get_commentary_settings(self):
        """Get commentary settings from RuntimeSettings."""
        return self.settings.runtime
    
    def _should_trigger_commentary(self, force_signal: bool = False) -> bool:
        """Determine if commentary should be triggered based on policy."""
        rt = self._get_commentary_settings()
        
        # Master toggle
        if not rt.commentary_enabled:
            return False
        
        policy = rt.commentary_policy.lower()
        if policy == "disabled":
            return False

        # Suppress regular commentary when the Seasoned Trader Autopilot is active.
        # The Autopilot broadcasts its OWN insight commentary — regular commentary
        # would overwrite it in the UI panel.
        try:
            from tradebot_sci.paths import CONFIG_FILE
            if CONFIG_FILE.exists():
                import json as _json
                with open(CONFIG_FILE, "r") as f:
                    _raw = _json.load(f)
                _active = _raw.get("active_profile", "")
                _prof = _raw.get("profiles", {}).get(_active, {}) if _active else {}
                _is_enabled = _prof.get("ai_seasoned_trader_enabled") or _prof.get("ai", {}).get("ai_seasoned_trader_enabled")
                if str(_is_enabled).lower() == "true" or _is_enabled is True:
                    logger.debug("[COMMENTARY] Suppressed — Seasoned Trader Autopilot is active")
                    return False
        except Exception:
            pass  # If config read fails, allow commentary as fallback
        
        # Check daily limit
        today = datetime.now().strftime("%Y-%m-%d")
        if self._commentary_call_date != today:
            self._commentary_call_date = today
            self._commentary_call_count_today = 0
        
        if self._commentary_call_count_today >= rt.commentary_max_daily_calls:
            logger.debug(f"[COMMENTARY] Daily limit reached ({rt.commentary_max_daily_calls})")
            return False
        
        now = time.time()
        
        if policy == "on_signal":
            # Triggered by trade signals (force_signal flag from caller)
            return force_signal
        
        if policy == "interval":
            interval_seconds = rt.commentary_interval_minutes * 60
            if now - self._last_commentary_ts < interval_seconds:
                return False
            return True
        
        if policy == "schedule":
            # Check if current time matches a scheduled slot (within 1 minute)
            slots = [s.strip() for s in rt.commentary_daily_slots.split(",") if s.strip()]
            current_time = datetime.now().strftime("%H:%M")
            for slot in slots:
                if slot == current_time:
                    # Only trigger once per slot (check last update wasn't in same minute)
                    if now - self._last_commentary_ts > 60:
                        return True
            return False
        
        return False
    
    def broadcast_commentary(self, state_context: str, strategy_name: str = "supply_demand", recent_logs: list[str] | None = None, recent_errors: list[str] | None = None, force_signal: bool = False, session_locked: bool = False):
        """
        Generate and broadcast AI commentary to the Electron UI.
        
        Args:
            state_context: Current bot state summary for the AI
            strategy_name: The active strategy name (e.g. 'supply_demand', 'robocop')
            recent_logs: Recent log lines for context
            recent_errors: Recent error messages to highlight
            force_signal: If True, treat as an on_signal trigger
            session_locked: If True, session lockout is active (fire once, then stop)
        """
        if not self.ws_server:
            return
        
        # During Session Lockout: fire once for a summary, then stop repeating
        if session_locked:
            if self._commentary_fired_during_lockout:
                return  # Already spoke during this lockout — nothing new to say
        else:
            # Session is active again — reset the lockout flag
            self._commentary_fired_during_lockout = False
        
        if not self._should_trigger_commentary(force_signal):
            return
        
        try:
            from tradebot_sci.ai.commentary_prompts import build_commentary_messages, build_commentary_prompt_with_logs
            from tradebot_sci.ai.client import TradeSciAIClient
            from tradebot_sci.config.loader import load_settings
            
            # Immediately update the timestamp to prevent API spamming if this call throws an exception
            self._last_commentary_ts = time.time()
            
            # Build the rich prompt with log context
            prompt = build_commentary_prompt_with_logs(state_context, recent_logs, recent_errors)
            
            # Generate commentary
            settings = load_settings().ai
            client = TradeSciAIClient(settings)
            messages = build_commentary_messages(prompt, strategy_name=strategy_name)
            commentary = client.generate_text(messages)
            
            if commentary and commentary.strip():
                self._last_commentary_content = commentary.strip()
                self._commentary_call_count_today += 1
                
                timestamp = datetime.now().strftime("%I:%M %p")
                rt = self._get_commentary_settings()
                next_update = rt.commentary_interval_minutes * 60 if rt.commentary_policy == "interval" else 300
                
                self.ws_server.broadcast_commentary_sync(
                    self._last_commentary_content,
                    timestamp,
                    next_update
                )
                
                logger.info(f"[COMMENTARY] Generated update #{self._commentary_call_count_today} for today")
                
                # Mark that we've spoken during lockout — no need to repeat
                if session_locked:
                    self._commentary_fired_during_lockout = True
                    logger.info("[COMMENTARY] Session Lockout active — this will be the only update until session resumes.")
            
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "403" in err_msg:
                logger.error("[COMMENTARY] ⚠️ AI Provider rejected the request (Unauthorized). Please verify your API key in Settings.")
            elif "404" in err_msg:
                logger.error("[COMMENTARY] ⚠️ AI Provider rejected the request (Not Found). The selected model may not exist.")
            elif "429" in err_msg or "rate limit" in err_msg.lower():
                logger.error("[COMMENTARY] ⚠️ AI Provider rate limit exceeded. The bot will try again later.")
            else:
                logger.error(f"[SYSTEM] AI Commentary generation failed: {err_msg}")
    
    def get_last_commentary(self) -> tuple[str, float]:
        """Returns (last_commentary_content, last_update_timestamp)."""
        return self._last_commentary_content, self._last_commentary_ts

    # --- Health Monitor Integration ---
    def broadcast_health(self, force: bool = False) -> None:
        """Push health vitals to the GUI via WebSocket (30s throttle)."""
        if not self.ws_server:
            return
        now = time.time()
        if not force and (now - self._last_health_broadcast_ts < 30.0):
            return
        try:
            vitals = self.health_monitor.get_vitals()
            is_paper = not getattr(self.settings.runtime, "execute_trades", True)
            try:
                from tradebot_sci.runtime.sabbath import SabbathContext
                sabbath_active, _, _ = SabbathContext(self.profile_settings).evaluate(datetime.now(timezone.utc))
                if sabbath_active:
                    is_paper = True
            except Exception:
                pass
            vitals["is_paper"] = is_paper
            self.ws_server.broadcast_health_sync(vitals)
            self._last_health_broadcast_ts = now
        except Exception as e:
            logger.error(f"[CONTROLLER] Health broadcast failed: {e}")

    def add_health_event(self, label: str, level: str = "info") -> None:
        """Record an event in the health monitor timeline."""
        self.health_monitor.add_event(label, level)

    def broadcast_restriction(self, restriction_data: dict[str, Any]) -> None:
        """Push broker restriction notifications to the GUI via WebSocket."""
        if not self.ws_server:
            return
        try:
            self.ws_server.broadcast_restriction_sync(restriction_data)
        except Exception as e:
            logger.error(f"[CONTROLLER] Restriction broadcast failed: {e}")

