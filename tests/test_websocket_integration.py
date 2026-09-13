"""WebSocket round-trip integration test + degradation contract.

Tests the real WebSocketServer from ws_server.py:
  - Server starts on a free port
  - Client connects and exchanges messages
  - Candle payloads are broadcast and received
  - Client disconnects gracefully
  - Server handles client drop without crashing
"""

import asyncio
import json
import os
import sys

import aiohttp
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.server.ws_server import WebSocketServer  # noqa: E402, I001


# ── Helpers ──────────────────────────────────────────────────────────

async def _find_free_port() -> int:
    """Find an available port for testing."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _start_server(port: int) -> WebSocketServer:
    """Start a WebSocketServer on the given port."""
    server = WebSocketServer(host="127.0.0.1", port=port)
    await server.start()
    return server


async def _connect_client(port: int) -> aiohttp.ClientWebSocketResponse:
    """Connect a WebSocket client to the server."""
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(f"ws://127.0.0.1:{port}/ws")
    return ws, session


# ═══════════════════════════════════════════════════════════════════
# Integration Test: WebSocket Round-Trip
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_websocket_ping_pong():
    """Server starts → client connects → ping/pong → values round-trip."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws, session = await _connect_client(port)
        try:
            # Send ping, expect pong
            await ws.send_str(json.dumps({"type": "ping"}))
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "pong", f"Expected pong, got {data}"
        finally:
            await ws.close()
            await session.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_websocket_subscribe_and_receive_candle():
    """Client subscribes → server broadcasts candle → client receives it."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws, session = await _connect_client(port)
        try:
            # Subscribe to BTCUSD
            await ws.send_str(json.dumps({
                "type": "subscribe",
                "symbol": "BTCUSD",
                "tf": "5m"
            }))

            # Give server time to register subscription
            await asyncio.sleep(0.1)

            # Verify subscription was registered
            subs = server.get_subscriptions()
            assert len(subs) == 1
            assert subs[0] == ("BTCUSD", "5m")

            # Broadcast a candle
            test_candle = {
                "open": 50000.0,
                "high": 50500.0,
                "low": 49800.0,
                "close": 50200.0,
                "volume": 12.5
            }
            await server.broadcast({
                "type": "candle",
                "symbol": "BTCUSD",
                "tf": "5m",
                "data": test_candle
            })

            # Client should receive the candle
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "candle"
            assert data["symbol"] == "BTCUSD"
            assert data["data"]["close"] == 50200.0
        finally:
            await ws.close()
            await session.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_websocket_state_update_broadcast():
    """Server broadcasts state update → client receives full payload."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws, session = await _connect_client(port)
        try:
            # Broadcast state
            state_data = {
                "capital": 10000.0,
                "positions": 2,
                "profile": "auto_schedule"
            }
            await server.broadcast({
                "type": "state",
                "data": state_data
            })

            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "state"
            assert data["data"]["capital"] == 10000.0
            assert data["data"]["positions"] == 2
        finally:
            await ws.close()
            await session.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_websocket_multi_client_broadcast():
    """Multiple clients all receive the same broadcast."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws1, session1 = await _connect_client(port)
        ws2, session2 = await _connect_client(port)
        try:
            await asyncio.sleep(0.1)
            assert len(server.clients) == 2

            await server.broadcast({"type": "log", "level": "INFO", "data": "test"})

            msg1 = await asyncio.wait_for(ws1.receive(), timeout=2.0)
            msg2 = await asyncio.wait_for(ws2.receive(), timeout=2.0)

            assert json.loads(msg1.data)["data"] == "test"
            assert json.loads(msg2.data)["data"] == "test"
        finally:
            await ws1.close()
            await ws2.close()
            await session1.close()
            await session2.close()
    finally:
        await server.stop()


# ═══════════════════════════════════════════════════════════════════
# Degradation: WebSocket Disconnects
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_websocket_client_disconnect_no_crash():
    """Client abruptly disconnects → server continues broadcasting to others."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws1, session1 = await _connect_client(port)
        ws2, session2 = await _connect_client(port)

        try:
            await asyncio.sleep(0.1)
            assert len(server.clients) == 2

            # Client1 abruptly disconnects
            await ws1.close()
            await asyncio.sleep(0.2)

            # Server should still broadcast to client2 without crashing
            await server.broadcast({"type": "log", "level": "INFO", "data": "after_disconnect"})

            msg = await asyncio.wait_for(ws2.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["data"] == "after_disconnect"
        finally:
            await ws2.close()
            await session1.close()
            await session2.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_websocket_broadcast_to_empty():
    """Broadcasting with no clients connected should not crash."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        assert len(server.clients) == 0
        # Should not raise
        await server.broadcast({"type": "log", "level": "INFO", "data": "echo"})
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_websocket_malformed_message():
    """Client sends non-JSON garbage → server handles without crashing."""
    port = await _find_free_port()
    server = await _start_server(port)

    try:
        ws, session = await _connect_client(port)
        try:
            # Send non-JSON garbage
            await ws.send_str("this is not json!!!")
            await asyncio.sleep(0.2)

            # Server should still be alive — send a valid ping and get pong
            await ws.send_str(json.dumps({"type": "ping"}))
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "pong", "Server should still respond after bad input"
        finally:
            await ws.close()
            await session.close()
    finally:
        await server.stop()
