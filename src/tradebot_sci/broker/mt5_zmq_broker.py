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

    def __init__(self, profile_settings, req_port: int = 5555):
        self.profile = profile_settings
        self.req_port = req_port
        
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
            return {
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
            "risk_usd": risk_usd
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

    def refresh_account_summary(self) -> None:
        payload = {"action": "GET_ACCOUNT"}
        resp = self._send_request(payload)
        
        if resp.get("status") == "success" and "account" in resp:
            acc = resp["account"]
            self._initial_balance = acc.get("balance", self._initial_balance)
            self._total_equity = acc.get("equity", self._total_equity)
            logger.info(f"[MT5-ZMQ] Account Update: Balance ${self._initial_balance:.2f} | Equity ${self._total_equity:.2f}")

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        return []

    def summarize_pnl(self) -> None:
        pass

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return self._initial_balance
        
    def get_display_cash(self) -> float:
        return self._initial_balance

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
        # Implement ZeroMQ CopyRates fetch request here
        logger.debug(f"[MT5-ZMQ] Requesting {limit} {timeframe} candles for {symbol} via ZMQ...")
        return []

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, timeframe=timeframe, candles=[])

    def get_ticker(self, symbol: str) -> Ticker | None:
        return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return None

    def close(self) -> None:
        pass
