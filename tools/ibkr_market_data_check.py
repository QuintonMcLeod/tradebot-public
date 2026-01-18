from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, asdict


@dataclass
class CheckResult:
    connected: bool
    host: str
    port: int
    client_id: int
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    realtime_ticks: dict
    delayed_ticks: dict
    realtime_errors: list[dict]
    delayed_errors: list[dict]
    historical_realtime_bars: int
    historical_delayed_bars: int
    notes: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(description="Checks IBKR API market-data availability (realtime vs delayed).")
    parser.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("IBKR_PORT", "7497")))
    parser.add_argument("--client-id", type=int, default=0, help="0 = auto-pick to avoid collisions.")
    parser.add_argument("--symbol", default=os.getenv("IBKR_MD_SYMBOL", "SPY"))
    parser.add_argument("--sec-type", default="STK", choices=["STK", "CRYPTO", "CASH"])
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--timeout", type=float, default=4.0, help="Seconds to wait for ticks/bars.")
    parser.add_argument("--bars", type=int, default=120, help="Target number of 5m bars (approx).")
    args = parser.parse_args()

    try:
        from ib_insync import IB, Stock, Crypto, Forex  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: ib_insync not available in this environment: {exc}", file=sys.stderr)
        return 2

    client_id = args.client_id or (int(time.time()) % 10_000) + random.randint(100, 999)

    def mk_contract():
        if args.sec_type == "STK":
            return Stock(args.symbol, args.exchange, args.currency)
        if args.sec_type == "CRYPTO":
            return Crypto(args.symbol, args.exchange, args.currency)
        return Forex(args.symbol)

    ib = IB()
    notes: list[str] = []
    try:
        ib.connect(args.host, args.port, clientId=client_id, timeout=3.0)
    except Exception as exc:
        out = CheckResult(
            connected=False,
            host=args.host,
            port=args.port,
            client_id=client_id,
            symbol=args.symbol,
            sec_type=args.sec_type,
            exchange=args.exchange,
            currency=args.currency,
            realtime_ticks={},
            delayed_ticks={},
            realtime_errors=[{"code": "CONNECT", "msg": str(exc)}],
            delayed_errors=[],
            historical_realtime_bars=0,
            historical_delayed_bars=0,
            notes=["Unable to connect to TWS/IB Gateway. Ensure API port is enabled and matches --port."],
        )
        print(json.dumps(asdict(out), indent=2, sort_keys=True))
        return 1

    realtime_errors: list[dict] = []
    delayed_errors: list[dict] = []

    def on_error(req_id, error_code, error_string, contract):  # type: ignore[no-untyped-def]
        payload = {"reqId": req_id, "code": int(error_code), "msg": str(error_string)}
        # Market data permission errors typically show up here.
        if current_md_type == 1:
            realtime_errors.append(payload)
        else:
            delayed_errors.append(payload)

    ib.errorEvent += on_error

    current_md_type = 1

    def snap_ticks(market_data_type: int) -> dict:
        nonlocal current_md_type
        current_md_type = market_data_type
        ib.reqMarketDataType(market_data_type)
        contract = mk_contract()
        try:
            contract = ib.qualifyContracts(contract)[0]
        except Exception as exc:
            return {"ok": False, "error": f"qualifyContracts failed: {exc}"}
        ticker = ib.reqMktData(contract, "", snapshot=False, regulatorySnapshot=False)
        end = time.time() + args.timeout
        last = bid = ask = close = None
        while time.time() < end:
            ib.sleep(0.2)
            last = getattr(ticker, "last", None)
            bid = getattr(ticker, "bid", None)
            ask = getattr(ticker, "ask", None)
            close = getattr(ticker, "close", None)
            if any(v is not None and v == v and v != 0 for v in (last, bid, ask, close)):  # NaN-safe
                break

        try:
            ib.cancelMktData(contract)
        except Exception:
            pass

        def clean(v):
            if v is None:
                return None
            try:
                return None if v != v else v
            except Exception:
                return v

        return {
            "ok": True,
            "marketDataType": market_data_type,
            "last": clean(last),
            "bid": clean(bid),
            "ask": clean(ask),
            "close": clean(close),
        }

    def hist_bars(market_data_type: int) -> int:
        nonlocal current_md_type
        current_md_type = market_data_type
        ib.reqMarketDataType(market_data_type)
        contract = mk_contract()
        try:
            contract = ib.qualifyContracts(contract)[0]
        except Exception:
            return 0
        duration = "1 D" if args.bars <= 288 else "2 D"
        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
                keepUpToDate=False,
            )
            return int(len(bars or []))
        except Exception:
            return 0

    realtime_ticks = snap_ticks(1)
    realtime_hist = hist_bars(1)
    delayed_ticks = snap_ticks(3)
    delayed_hist = hist_bars(3)

    # Common permission errors:
    # - 10089: additional subscription required for API; delayed is available
    # - 354:  requested market data is not subscribed (varies by venue/product)
    realtime_blocked = any(e.get("code") in (354, 10089) for e in realtime_errors)
    if realtime_blocked:
        notes.append("Realtime streaming market data is not available (subscription required).")
    if delayed_hist > 0 or (delayed_ticks.get("last") is not None or delayed_ticks.get("close") is not None):
        notes.append("Delayed market data appears available via the API (marketDataType=3).")
    if not realtime_blocked and (
        realtime_hist > 0 or (realtime_ticks.get("last") is not None or realtime_ticks.get("close") is not None)
    ):
        notes.append("Realtime market data appears available via the API (marketDataType=1).")
    if not notes:
        notes.append("No ticks/bars received within timeout; could be permissions, symbol/contract mismatch, or pacing.")

    out = CheckResult(
        connected=True,
        host=args.host,
        port=args.port,
        client_id=client_id,
        symbol=args.symbol,
        sec_type=args.sec_type,
        exchange=args.exchange,
        currency=args.currency,
        realtime_ticks=realtime_ticks,
        delayed_ticks=delayed_ticks,
        realtime_errors=realtime_errors,
        delayed_errors=delayed_errors,
        historical_realtime_bars=realtime_hist,
        historical_delayed_bars=delayed_hist,
        notes=notes,
    )
    print(json.dumps(asdict(out), indent=2, sort_keys=True))
    try:
        ib.disconnect()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
