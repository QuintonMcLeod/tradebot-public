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
        self.loop = None
        self._halted = False

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
                        elif data.get('type') == 'command':
                            cmd = data.get('cmd')
                            if cmd == 'halt':
                                self._halted = True
                                logger.info("[WS] BOT HALT SIGNAL RECEIVED")
                            elif cmd == 'resume':
                                self._halted = False
                                logger.info("[WS] BOT RESUME SIGNAL RECEIVED")
                    except json.JSONDecodeError:
                        if msg.data == 'ping':
                            await ws.send_str(json.dumps({'type': 'pong'}))
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error('ws connection closed with exception %s', ws.exception())
        finally:
            self.clients.remove(ws)
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

    def broadcast_candle_sync(self, symbol, timeframe, candle):
        """Thread-safe candle broadcast."""
        msg = {
            "type": "candle",
            "symbol": symbol,
            "tf": timeframe,
            "data": candle
        }
        self.broadcast_sync(msg)

    def is_halted(self) -> bool:
        """Returns True if the bot should be paused."""
        return self._halted
