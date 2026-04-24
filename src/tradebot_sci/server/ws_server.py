"""WebSocket server for real-time GUI communication.

Provides a WebSocket endpoint at /ws that the Electron GUI connects to.
Supports broadcasting candle data, state updates, log messages, and
AI commentary to all connected clients.
"""

from __future__ import annotations

from typing import Any, Callable

import aiohttp
from aiohttp import web
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class WebSocketServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 8080) -> None:
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.add_routes([web.get('/ws', self.websocket_handler)])
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.clients: set[web.WebSocketResponse] = set()
        self.subscriptions: dict[web.WebSocketResponse, dict[str, str]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._halted = False
        self._on_subscribe_cb: Callable[[str, str, int | None], Any] | None = None
        self._on_tick_cb: Callable[[str, str], Any] | None = None
        self._on_flatten_cb: Callable[[str], Any] | None = None

    async def start(self) -> None:
        """Starts the WebSocket server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info(f"WebSocket Server started at ws://{self.host}:{self.port}/ws")

    async def stop(self) -> None:
        """Stops the WebSocket server."""
        for ws in list(self.clients):
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message=b'Server shutdown')
        if self.runner:
            await self.runner.cleanup()
        logger.info("WebSocket Server stopped.")

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)
        logger.info("New WebSocket client connected.")

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'ping':
                            await ws.send_str(json.dumps({'type': 'pong'}))
                        elif data.get('type') == 'subscribe':
                            symbol = data.get('symbol')
                            tf = data.get('tf')
                            since = data.get('since')  # epoch seconds, optional
                            if symbol:
                                self.subscriptions[ws] = {"symbol": symbol, "tf": tf or "15m"}
                                logger.info(f"[WS] Client subscribed to {symbol} ({tf}){f' since={since}' if since else ''}")
                                if self._on_subscribe_cb:
                                    # Run in thread pool — callback makes blocking HTTP calls
                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(
                                        None, self._on_subscribe_cb, symbol, tf or "15m", since
                                    )
                        elif data.get('type') == 'tick':
                            symbol = data.get('symbol')
                            tf = (data.get('tf') or '15m').lower()
                            if symbol and self._on_tick_cb:
                                # Run in thread pool — callback makes blocking HTTP calls
                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(
                                    None, self._on_tick_cb, symbol, tf
                                )
                        elif data.get('type') == 'flatten_symbol':
                            symbol = data.get('symbol')
                            if symbol and self._on_flatten_cb:
                                logger.info(f"[WS] Manual Cash-Out request received for {symbol}")
                                try:
                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(
                                        None, self._on_flatten_cb, symbol
                                    )
                                    # Broadcast success to ALL clients
                                    ack = json.dumps({
                                        'type': 'flatten_ack',
                                        'symbol': symbol,
                                        'status': 'ok'
                                    })
                                    for client in list(self.clients):
                                        try:
                                            await client.send_str(ack)
                                        except Exception:
                                            pass
                                except Exception as e:
                                    logger.error(f"[WS] Flatten failed for {symbol}: {e}")
                                    # Broadcast error to ALL clients
                                    ack = json.dumps({
                                        'type': 'flatten_ack',
                                        'symbol': symbol,
                                        'status': 'error',
                                        'reason': str(e)
                                    })
                                    for client in list(self.clients):
                                        try:
                                            await client.send_str(ack)
                                        except Exception:
                                            pass
                            elif symbol:
                                logger.warning(f"[WS] Flatten request for {symbol} but no callback registered")
                                await ws.send_str(json.dumps({
                                    'type': 'flatten_ack',
                                    'symbol': symbol,
                                    'status': 'error',
                                    'reason': 'No executor available'
                                }))
                        elif data.get('type') == 'log':
                            # Bridge frontend logs to backend for easier debugging
                            lvl = data.get('level', 'INFO').upper()
                            log_data = data.get('data', '')
                            getattr(logger, lvl.lower(), logger.info)(f"[FRONTEND] {log_data}")
                    except json.JSONDecodeError:
                        if msg.data == 'ping':
                            await ws.send_str(json.dumps({'type': 'pong'}))
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error('ws connection closed with exception %s', ws.exception())
        finally:
            self.clients.remove(ws)
            if ws in self.subscriptions:
                del self.subscriptions[ws]
            logger.info("WebSocket client disconnected.")
        
        return ws

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcasts a JSON message to all connected clients."""
        if not self.clients:
            return
        
        try:
            payload = json.dumps(message)
        except Exception as e:
            logger.error(f"[WS-BROADCAST] JSON Serialization Error for message type '{message.get('type')}': {e}")
            logger.error(f"[WS-BROADCAST] Offending payload type: {type(message)}")
            return

        for ws in list(self.clients):
            if ws.closed:
                self.clients.discard(ws)
                continue
            try:
                await ws.send_str(payload)
            except (aiohttp.ClientConnectionResetError, RuntimeError) as e:
                # Suppress noisy 'closing transport' errors during disconnects
                if "closing transport" in str(e).lower() or "closed" in str(e).lower():
                    logger.debug(f"WebSocket client disconnected during broadcast: {e}")
                else:
                    logger.warning(f"Failed to send to WebSocket client: {e}")
                self.clients.discard(ws)
            except Exception as e:
                logger.error(f"Unexpected WebSocket broadcast error: {e}")
                self.clients.discard(ws)

    def start_in_thread(self) -> None:
        """Starts the server in a separate daemon thread."""
        import threading
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, args=(self.loop,), daemon=True).start()
        asyncio.run_coroutine_threadsafe(self.start(), self.loop)

    def _run_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def stop_in_thread(self) -> None:
        """Stops the server from the main thread."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.stop(), self.loop)

    def broadcast_sync(self, message: dict[str, Any]) -> None:
        """Thread-safe broadcast from sync code."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

    def broadcast_candle_sync(
        self, symbol: str, timeframe: str, candle: dict[str, Any], provider: str | None = None
    ) -> None:
        """Thread-safe candle broadcast with optional provider tagging."""
        msg: dict[str, Any] = {
            "type": "candle",
            "symbol": symbol,
            "tf": timeframe,
            "data": candle,
            "provider": provider 
        }
        self.broadcast_sync(msg)

    def broadcast_log_sync(self, level: str, message: str) -> None:
        """Thread-safe log broadcast."""
        msg: dict[str, Any] = {
            "type": "log",
            "level": level,
            "data": message
        }
        self.broadcast_sync(msg)

    def broadcast_state_sync(self, data: dict[str, Any]) -> None:
        """Thread-safe state update broadcast."""
        msg: dict[str, Any] = {
            "type": "state",
            "data": data
        }
        self.broadcast_sync(msg)

    def broadcast_history_sync(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> None:
        """Thread-safe historical data broadcast."""
        msg: dict[str, Any] = {
            "type": "history",
            "symbol": symbol,
            "tf": timeframe,
            "data": candles
        }
        self.broadcast_sync(msg)

    def broadcast_commentary_sync(self, commentary: str, timestamp: str, next_update_in: int = 300) -> None:
        """Thread-safe AI commentary broadcast for Electron UI."""
        msg: dict[str, Any] = {
            "type": "ai_commentary",
            "content": commentary,
            "timestamp": timestamp,
            "next_update_in": next_update_in  # seconds until next update
        }
        self.broadcast_sync(msg)

    def broadcast_holdings_sync(self, holdings_data: dict[str, Any]) -> None:
        """Thread-safe holdings broadcast — dedicated message so the GUI
        doesn't need to rely on log-line parsing to populate the Holdings panel."""
        msg: dict[str, Any] = {
            "type": "holdings",
            "data": holdings_data
        }
        self.broadcast_sync(msg)

    def broadcast_health_sync(self, health_data: dict[str, Any]) -> None:
        """Thread-safe health vitals broadcast for the Vitals dashboard."""
        msg: dict[str, Any] = {
            "type": "health",
            "data": health_data
        }
        self.broadcast_sync(msg)

    def set_on_subscribe_callback(self, cb: Callable[[str, str, int | None], Any]) -> None:
        """Register a callback for when a client subscribes to a symbol."""
        self._on_subscribe_cb = cb

    def set_on_tick_callback(self, cb: Callable[[str, str], Any]) -> None:
        """Register a callback for lightweight candle tick refresh."""
        self._on_tick_cb = cb

    def set_on_flatten_callback(self, cb: Callable[[str], Any]) -> None:
        """Register a callback for manual position cash-out from the GUI."""
        self._on_flatten_cb = cb

    def get_subscriptions(self) -> list[tuple[str, str]]:
        """Returns a list of (symbol, timeframe) currently subscribed to by clients."""
        return [(sub["symbol"], sub["tf"]) for sub in self.subscriptions.values()]

    def is_halted(self) -> bool:
        """Returns True if the bot should be paused."""
        return self._halted
