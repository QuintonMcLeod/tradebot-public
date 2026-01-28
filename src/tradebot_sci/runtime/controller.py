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
        self.ws_server = WebSocketServer(port=port)
        self.ws_server.set_on_subscribe_callback(self._on_ws_subscribe)
        self.ws_server.start_in_thread()
        logger.info(f"[CONTROLLER] WebSocket server started on port {port}")

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
            cap = executor.get_liquid_capital() if executor else 0.0
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

            state_data = {
                "equity": cap,
                "capital": cap,
                "holdings_count": holdings_count,
                "profile": self.profile_name,
                "symbols": getattr(self.profile_settings, "symbols", []),
                "is_sabbath": sabbath_active,
                "halted": self.ws_server.is_halted()
            }
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
            "close": candle.close
        }
        self.ws_server.broadcast_candle_sync(symbol, timeframe, c_data)

    def is_halted(self) -> bool:
        return self.ws_server.is_halted() if self.ws_server else False

    # --- AI Commentary Integration ---
    _last_commentary_ts: float = 0.0
    _last_commentary_content: str = ""
    _commentary_min_interval: int = 300  # 5 minutes between updates
    
    def broadcast_commentary(self, state_context: str, strategy_name: str = "supply_demand", recent_logs: list[str] | None = None, recent_errors: list[str] | None = None):
        """
        Generate and broadcast AI commentary to the Electron UI.
        
        Args:
            state_context: Current bot state summary for the AI
            strategy_name: The active strategy name (e.g. 'supply_demand', 'robocop')
            recent_logs: Recent log lines for context
            recent_errors: Recent error messages to highlight
        """
        if not self.ws_server:
            return
        
        now = time.time()
        if now - self._last_commentary_ts < self._commentary_min_interval:
            return  # Too soon for another update
        
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
                self._last_commentary_ts = now
                
                timestamp = datetime.now().strftime("%I:%M %p")
                next_update = self._commentary_min_interval
                
                self.ws_server.broadcast_commentary_sync(
                    self._last_commentary_content,
                    timestamp,
                    next_update
                )
            
        except Exception as e:
            logger.error(f"[COMMENTARY] Generation failed: {e}")
    
    def get_last_commentary(self) -> tuple[str, float]:
        """Returns (last_commentary_content, last_update_timestamp)."""
        return self._last_commentary_content, self._last_commentary_ts
```
