import aiohttp
from aiohttp import web
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.add_routes([web.get('/ws', self.websocket_handler)])
        self.runner = None
        self.site = None
        self.clients = set()
        self.subscriptions: dict[aiohttp.web.WebSocketResponse, dict[str, str]] = {} # client -> {"symbol": "BTCUSD", "tf": "15m"}
        self.loop = None
        self._halted = False
        self._on_subscribe_cb = None # Optional callback for loop.py

    async def start(self):
        """Starts the WebSocket server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info(f"WebSocket Server started at ws://{self.host}:{self.port}/ws")

    async def stop(self):
        """Stops the WebSocket server."""
        for ws in list(self.clients):
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message='Server shutdown')
        if self.runner:
            await self.runner.cleanup()
        logger.info("WebSocket Server stopped.")

    async def websocket_handler(self, request):
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
                            if symbol:
                                self.subscriptions[ws] = {"symbol": symbol, "tf": tf or "15m"}
                                logger.info(f"[WS] Client subscribed to {symbol} ({tf})")
                                if self._on_subscribe_cb:
                                    self._on_subscribe_cb(symbol, tf or "15m")
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

    async def broadcast(self, message: dict):
        """Broadcasts a JSON message to all connected clients."""
        if not self.clients:
            return
        
        payload = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_str(payload)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                self.clients.discard(ws)

    def start_in_thread(self):
        """Starts the server in a separate daemon thread."""
        import threading
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, args=(self.loop,), daemon=True).start()
        asyncio.run_coroutine_threadsafe(self.start(), self.loop)

    def _run_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def stop_in_thread(self):
        """Stops the server from the main thread."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.stop(), self.loop)

    def broadcast_sync(self, message: dict):
        """Thread-safe broadcast from sync code."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

    def broadcast_candle_sync(self, symbol, timeframe, candle, provider=None):
        """Thread-safe candle broadcast with optional provider tagging."""
        msg = {
            "type": "candle",
            "symbol": symbol,
            "tf": timeframe,
            "data": candle,
            "provider": provider 
        }
        self.broadcast_sync(msg)

    def broadcast_log_sync(self, level, message):
        """Thread-safe log broadcast."""
        msg = {
            "type": "log",
            "level": level,
            "data": message
        }
        self.broadcast_sync(msg)

    def broadcast_state_sync(self, data: dict):
        """Thread-safe state update broadcast."""
        msg = {
            "type": "state",
            "data": data
        }
        self.broadcast_sync(msg)

    def broadcast_history_sync(self, symbol, timeframe, candles: list[dict]):
        """Thread-safe historical data broadcast."""
        msg = {
            "type": "history",
            "symbol": symbol,
            "tf": timeframe,
            "data": candles
        }
        self.broadcast_sync(msg)

    def broadcast_commentary_sync(self, commentary: str, timestamp: str, next_update_in: int = 300):
        """Thread-safe AI commentary broadcast for Electron UI."""
        msg = {
            "type": "ai_commentary",
            "content": commentary,
            "timestamp": timestamp,
            "next_update_in": next_update_in  # seconds until next update
        }
        self.broadcast_sync(msg)

    def set_on_subscribe_callback(self, cb):
        """Register a callback for when a client subscribes to a symbol."""
        self._on_subscribe_cb = cb

    def get_subscriptions(self) -> list[tuple[str, str]]:
        """Returns a list of (symbol, timeframe) currently subscribed to by clients."""
        return [(sub["symbol"], sub["tf"]) for sub in self.subscriptions.values()]

    def is_halted(self) -> bool:
        """Returns True if the bot should be paused."""
        return self._halted

