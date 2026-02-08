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

    def broadcast_state(self, executor: Any, force: bool = False):
        """Pushes account and bot state to UI via WebSocket."""
        if not self.ws_server:
            return
            
        now = time.time()
        if not force and (now - self.last_capital_sync_ts < 30.0):
            return
            
        try:
            # [ANTIGRAVITY FIX] Distinguish between Liquid Cash and Total Equity
            cash = executor.get_liquid_capital() if executor else 0.0
            total_equity = executor.get_total_balance_value() if executor else 0.0
            
            # Get active holdings count
            holdings_count = 0
            if executor and hasattr(executor, "list_open_position_symbols"):
                open_symbols = list(executor.list_open_position_symbols() or [])
                active_holds = [
                    s for s in open_symbols 
                    if not (executor.get_open_position_snapshot(s) or {}).get("is_dust", False)
                ]
                holdings_count = len(active_holds)

            sabbath_active, _, _ = SabbathContext(self.profile_settings).evaluate(datetime.now(timezone.utc))

            # [ANTIGRAVITY FIX] Refresh profile_name from settings each time to catch hot-reloads
            current_profile = getattr(self.settings.app, 'profile_name', self.profile_name)
            if current_profile != self.profile_name:
                logger.info(f"[CONTROLLER] Profile changed: {self.profile_name} -> {current_profile}")
                self.profile_name = current_profile

            # [ANTIGRAVITY] Multi-interval PnL Tracking
            pnl_stats = {}
            if executor and hasattr(executor, "trade_results"):
                store = executor.trade_results
                for tf_code in ['24h', 'week', 'month', 'year', 'all']:
                    pnl_stats[tf_code] = store.get_stats_for_timeframe(tf_code).get('pnl_usd', 0.0)

            state_data = {
                "equity": total_equity,
                "capital": total_equity,
                "cash": cash,
                "holdings_count": holdings_count,
                "profile": self.profile_name,
                "symbols": getattr(self.profile_settings, "symbols", []),
                "is_sabbath": sabbath_active,
                "halted": self.ws_server.is_halted(),
                "pnl_stats": pnl_stats,
                "time_format": getattr(self.settings.runtime, "time_format", "24h")
            }
            logger.info(f"[PRODB-STATE] Broadcasting state: profile={self.profile_name} equity=${total_equity:.2f} cash=${cash:.2f}")
            self.ws_server.broadcast_state_sync(state_data)
            self.last_capital_sync_ts = now
        except Exception as e:
            logger.error(f"[CONTROLLER] State broadcast failed: {e}")

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
        # [ANTIGRAVITY DEBUG] Trace volume and timestamp
        self.ws_server.broadcast_candle_sync(symbol, timeframe, c_data)

    def is_halted(self) -> bool:
        return self.ws_server.is_halted() if self.ws_server else False

    # --- AI Commentary Integration ---
    _last_commentary_ts: float = 0.0
    _last_commentary_content: str = ""
    _commentary_call_count_today: int = 0
    _commentary_call_date: str = ""
    
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
    
    def broadcast_commentary(self, state_context: str, strategy_name: str = "supply_demand", recent_logs: list[str] | None = None, recent_errors: list[str] | None = None, force_signal: bool = False):
        """
        Generate and broadcast AI commentary to the Electron UI.
        
        Args:
            state_context: Current bot state summary for the AI
            strategy_name: The active strategy name (e.g. 'supply_demand', 'robocop')
            recent_logs: Recent log lines for context
            recent_errors: Recent error messages to highlight
            force_signal: If True, treat as an on_signal trigger
        """
        if not self.ws_server:
            return
        
        if not self._should_trigger_commentary(force_signal):
            return
        
        try:
            from tradebot_sci.ai.commentary_prompts import build_commentary_messages, build_commentary_prompt_with_logs
            from tradebot_sci.ai.client import TradeSciAIClient
            from tradebot_sci.config.loader import load_settings
            
            # Build the rich prompt with log context
            prompt = build_commentary_prompt_with_logs(state_context, recent_logs, recent_errors)
            
            # Generate commentary
            settings = load_settings().ai
            client = TradeSciAIClient(settings)
            messages = build_commentary_messages(prompt, strategy_name=strategy_name)
            commentary = client.generate_text(messages)
            
            if commentary and commentary.strip():
                self._last_commentary_content = commentary.strip()
                self._last_commentary_ts = time.time()
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
            
        except Exception as e:
            logger.error(f"[COMMENTARY] Generation failed: {e}")
    
    def get_last_commentary(self) -> tuple[str, float]:
        """Returns (last_commentary_content, last_update_timestamp)."""
        return self._last_commentary_content, self._last_commentary_ts

