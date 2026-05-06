import logging
import json
import time
from typing import Iterable

import zmq

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult, ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci import paths as _paths

logger = logging.getLogger(__name__)

class MT5ZMQBroker(IExchangeBroker):
    """
    ZeroMQ bridge broker for MetaTrader 5.
    Connects to an MQL5 Expert Advisor running a ZMQ REP socket on port 5555.
    """

    def __init__(self, profile_settings, req_port: int = 5555, trade_results=None):
        self.profile = profile_settings
        self.req_port = req_port
        self.trade_results = trade_results
        
        # Initialize ZMQ Context and Socket
        self.context = zmq.Context()
        self.req_socket = self.context.socket(zmq.REQ)
        self.req_socket.connect(f"tcp://localhost:{self.req_port}")
        
        # Socket settings
        self.req_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
        self.req_socket.setsockopt(zmq.SNDTIMEO, 5000)
        self.req_socket.setsockopt(zmq.LINGER, 0)
        
        self._initial_balance = 0.0
        self._total_equity = 0.0
        
        logger.info(f"[MT5-ZMQ] Connecting to MetaTrader 5 ZMQ Bridge on port {self.req_port}")
        self.refresh_account_summary()

    def _send_request(self, payload: dict) -> dict:
        """Sends a JSON request to MT5 and awaits the JSON response."""
        try:
            message = json.dumps(payload).encode('utf-8')
            self.req_socket.send(message)
            response = self.req_socket.recv()
            if not response:
                return {"status": "error", "message": "Empty response from MT5"}
            return json.loads(response.decode('utf-8'))
        except zmq.error.Again:
            logger.error(f"[MT5-ZMQ] Timeout waiting for MT5 ZMQ server on port {self.req_port}")
            # Reset socket on timeout
            self.req_socket.close()
            self.req_socket = self.context.socket(zmq.REQ)
            self.req_socket.connect(f"tcp://localhost:{self.req_port}")
            self.req_socket.setsockopt(zmq.RCVTIMEO, 5000)
            self.req_socket.setsockopt(zmq.SNDTIMEO, 5000)
            self.req_socket.setsockopt(zmq.LINGER, 0)
            return {"status": "error", "message": "Timeout"}
        except Exception as e:
            logger.error(f"[MT5-ZMQ] Exception in ZMQ request: {e}")
            return {"status": "error", "message": str(e)}

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        payload = {"action": "CANCEL_ALL", "symbol": symbol}
        logger.debug(f"[MT5-ZMQ] Canceling all orders for {symbol}")
        self._send_request(payload)

    def flatten_symbol(self, symbol: str) -> None:
        payload = {"action": "FLATTEN", "symbol": symbol}
        logger.info(f"[MT5-ZMQ] Flattening {symbol}")
        resp = self._send_request(payload)
        if resp.get("status") != "success":
            logger.error(f"[MT5-ZMQ] Flatten failed: {resp.get('message')}")

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        payload = {"action": "GET_POSITION", "symbol": symbol}
        resp = self._send_request(payload)
        
        if resp.get("status") == "success" and "position" in resp:
            pos = resp["position"]
            snapshot = {
                "symbol": pos.get("symbol", symbol),
                "side": "long" if pos.get("type", 0) == 0 else "short",
                "size": pos.get("volume", 0.0),
                "qty": abs(pos.get("volume", 0.0)),
                "entry_price": pos.get("price_open", 0.0),
                "current_price": pos.get("price_current", 0.0),
                "unrealized_pnl": pos.get("profit", 0.0),
                "stop_loss": pos.get("sl", 0.0),
                "take_profit": pos.get("tp", 0.0),
                "ticket": pos.get("ticket", 0)
            }
            
            # Extract timestamp if EA provides it
            pos_time = pos.get("time") or pos.get("time_msc") or pos.get("time_update")
            if pos_time:
                import datetime
                if pos_time > 1e11: # likely milliseconds
                    pos_time = pos_time / 1000.0
                try:
                    dt = datetime.datetime.fromtimestamp(pos_time, tz=datetime.timezone.utc)
                    snapshot["opened_at"] = dt.isoformat()
                    snapshot["entry_time"] = dt.isoformat()
                except Exception:
                    pass
                    
            # Extract strategy comment if EA provides it
            comment = pos.get("comment", "")
            if comment:
                snapshot["strategy"] = comment
                
            return snapshot
        return None

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        symbol = decision.symbol
        action = decision.action
        
        # Simple sizing calculation for bridging
        # In a real environment, you might calculate lot sizes based on MT5 symbol properties
        risk_pct = getattr(decision, "risk_per_trade_pct", None) or getattr(self.profile, "risk_per_trade_pct", 0.01)
        sizing_capital = self._initial_balance if self._initial_balance > 0 else 50000.0
        risk_usd = sizing_capital * risk_pct
        
        # Just sending the risk instructions to MT5 to handle lot sizing natively
        payload = {
            "action": "EXECUTE",
            "symbol": symbol,
            "type": "BUY" if action == "enter_long" else "SELL" if action == "enter_short" else action.upper(),
            "sl": getattr(decision, "stop_loss", 0.0),
            "tp": getattr(decision, "take_profit", 0.0),
            "risk_usd": risk_usd,
            "strategy": getattr(decision, "strategy_name", "manual") or "manual"
        }
        
        logger.info(f"[MT5-ZMQ] Sending {action} for {symbol} to MT5. SL:{payload['sl']} TP:{payload['tp']}")
        resp = self._send_request(payload)
        
        if resp.get("status") == "success":
            logger.info(f"[MT5-ZMQ] Execution successful: Ticket {resp.get('ticket')}")
            return (
                ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"MT5 Ticket {resp.get('ticket')}"),
                ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"MT5 Ticket {resp.get('ticket')}")
            )
        else:
            logger.error(f"[MT5-ZMQ] Execution blocked by MT5 Error: {resp.get('message')}")
            return (
                ExecutionResult(ExecutionStatus.ERROR, symbol, f"MT5 Error: {resp.get('message')}"),
                ExecutionOutcome(ExecutionOutcomeType.ERROR, symbol, f"MT5 Error: {resp.get('message')}")
            )

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        # Implementation depends on hold guards. Can be skipped or basic check.
        return False, None, None

    @property
    def position_hold_store(self):
        return None

    def list_open_position_symbols(self) -> list[str]:
        # The DUMMY MT5 ZMQ Bridge currently lacks a GET_POSITIONS command.
        # Natively, we ask the MT5 Terminal to return all open position symbol strings.
        # Since it's a DUMMY, it will return an empty array.
        payload = {"action": "GET_ALL_POSITIONS"}
        resp = self._send_request(payload)
        open_syms = []
        if resp.get("status") == "success" and "positions" in resp:
            open_syms = [p.get("symbol") for p in resp["positions"] if "symbol" in p]
        return open_syms

    def refresh_account_summary(self) -> None:
        payload = {"action": "GET_ACCOUNT"}
        resp = self._send_request(payload)
        
        if resp.get("status") == "success" and "account" in resp:
            acc = resp["account"]
            self._initial_balance = acc.get("balance", self._initial_balance)
            self._total_equity = acc.get("equity", self._total_equity)
            self._margin_free = acc.get("margin_free", self._initial_balance)
            logger.info(f"[MT5-ZMQ] Account Update: Balance ${self._initial_balance:.2f} | Equity ${self._total_equity:.2f} | Free Margin ${self._margin_free:.2f}")

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        return []

    def summarize_pnl(self) -> None:
        if not self.trade_results:
            return
            
        payload = {"action": "GET_HISTORY", "days": 30}
        resp = self._send_request(payload)
        
        if resp.get("status") == "success" and "deals" in resp:
            deals = resp["deals"]
            if not deals:
                return
                
            from tradebot_sci.broker.trade_result_store import TradeResult
            from datetime import datetime, timezone
            
            # Extract existing tickets or timestamps to prevent duplicates
            # MT5 deals don't directly map to bot tickets easily, so we use timestamp + symbol + profit as fingerprint
            existing_fingerprints = set()
            for r in self.trade_results.get_recent_results(limit=500):
                # Using a rough timestamp (seconds) and pnl for uniqueness
                try:
                    dt = datetime.fromisoformat(r.closed_at.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                    fingerprint = f"{r.symbol}_{ts}_{r.pnl_usd:.2f}"
                    existing_fingerprints.add(fingerprint)
                except:
                    pass
            
            for deal in deals:
                sym = deal.get("symbol")
                if not sym: continue
                profit = float(deal.get("profit", 0.0))
                vol = float(deal.get("volume", 0.0))
                time_sec = int(deal.get("time", 0))
                comment = deal.get("comment", "")
                
                # Create fingerprint
                fingerprint = f"{sym}_{time_sec}_{profit:.2f}"
                # Allow +/- 5 seconds for timestamp mismatch
                found = False
                for offset in range(-5, 6):
                    if f"{sym}_{time_sec + offset}_{profit:.2f}" in existing_fingerprints:
                        found = True
                        break
                
                if found:
                    continue
                
                # New deal found! Synthesize a TradeResult
                dt = datetime.fromtimestamp(time_sec, tz=timezone.utc)
                cap = self.get_liquid_capital()
                
                # Approximate percent if capital > 0
                pct = (profit / cap * 100.0) if cap > 0 else 0.0
                
                tr = TradeResult(
                    symbol=sym,
                    closed_at=dt.isoformat(),
                    pnl_pct=pct,
                    pnl_usd=profit,
                    is_win=(profit > 0),
                    tier="MT5_MANUAL",
                    capital_at_close=cap,
                    strategy=comment if comment else "manual",
                    exit_reason="MT5 Native Close"
                )
                self.trade_results.add_result(tr)
                logger.info(f"[MT5-ZMQ] Synced closed deal for {sym}: PnL ${profit:.2f}")

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return getattr(self, '_margin_free', self._initial_balance)
        
    def get_display_cash(self) -> float:
        return getattr(self, '_margin_free', self._initial_balance)

    def get_total_balance_value(self) -> float:
        return self._total_equity

    def get_total_equity(self) -> float:
        return self._total_equity

    def sync_profile(self, profile) -> None:
        self.profile = profile
        logger.info("[MT5-ZMQ] Profile synchronized.")

    def _fetch_symbol_state(self, symbol: str) -> dict:
        pos = self.get_open_position_snapshot(symbol)
        return {"position": pos} if pos else {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        pos = self.get_open_position_snapshot(symbol)
        return pos is not None

from tradebot_sci.market.providers import MarketDataProvider
from tradebot_sci.market.models import Candle, MarketSnapshot, OrderBook, Ticker
from typing import List

class MT5ZMQMarketProvider(MarketDataProvider):
    """
    Market Data Provider bridging to MT5 via ZeroMQ.
    Fetches raw OHLCV tick data from MetaTrader 5 over ZMQ.
    """
    def __init__(self, req_port: int = 5555):
        self.req_port = req_port
        logger.info("[MT5-ZMQ] MT5 Market Data Provider initialized on port %s", req_port)

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        import zmq
        import json
        from datetime import datetime, timezone
        
        logger.debug(f"[MT5-ZMQ] Requesting {limit} {timeframe} candles for {symbol} via ZMQ...")
        
        context = zmq.Context()
        req_socket = context.socket(zmq.REQ)
        req_socket.connect(f"tcp://localhost:{self.req_port}")
        req_socket.setsockopt(zmq.RCVTIMEO, 5000)
        req_socket.setsockopt(zmq.SNDTIMEO, 5000)
        req_socket.setsockopt(zmq.LINGER, 0)
        
        try:
            payload = {"action": "GET_CANDLES", "symbol": symbol, "timeframe": timeframe, "limit": limit}
            req_socket.send(json.dumps(payload).encode('utf-8'))
            response = req_socket.recv()
            data = json.loads(response.decode('utf-8'))
            
            if data.get("status") == "success" and "candles" in data:
                candles = []
                for c in data["candles"]:
                    ts = datetime.fromtimestamp(c.get("time", 0), tz=timezone.utc)
                    candles.append(Candle(
                        timestamp=ts,
                        open=float(c.get("open", 0.0)),
                        high=float(c.get("high", 0.0)),
                        low=float(c.get("low", 0.0)),
                        close=float(c.get("close", 0.0)),
                        volume=float(c.get("real_volume", c.get("tick_volume", 0.0)))
                    ))
                return candles
            else:
                logger.warning(f"[MT5-ZMQ] EA did not return candles: {data.get('message', 'Unknown error')}")
                
        except zmq.error.Again:
            logger.error(f"[MT5-ZMQ] Timeout fetching candles for {symbol}")
        except Exception as e:
            logger.error(f"[MT5-ZMQ] Error fetching candles: {e}")
        finally:
            req_socket.close()
            
        return []

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        # Resolve HTF timeframe from config
        from tradebot_sci.config.loader import load_config_json
        config = load_config_json()
        active_prof = config.get("active_profile", "primary")
        prof_data = config.get("profiles", {}).get(active_prof, {})
        htf_setting = prof_data.get("htf_timeframe") or config.get("global", {}).get("htf_timeframe") or "4h"

        ltf_candles = self.get_latest_candles(symbol, timeframe, limit=200)
        htf_candles = self.get_latest_candles(symbol, htf_setting, limit=200)

        # Neutral defaults — engine.py's Trend Detection sets direction
        from tradebot_sci.market.models import TrendState
        _neutral = TrendState(direction="neutral", strength=0.0)
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=ltf_candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=htf_setting,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return None

    def close(self) -> None:
        pass
