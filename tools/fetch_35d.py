import os, json, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

env_path = Path("/home/qchan/.config/tradebot-sci/.env.secrets")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

import oandapyV20
import oandapyV20.endpoints.instruments as instruments

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SYMBOLS = ["EUR_USD", "GBP_USD"]

def chunked_download(client, symbol, gran, start_date, end_date):
    all_data = []
    chunk_start = start_date
    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=7), end_date)
        params = {"from": chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"), "granularity": gran, "price": "M"}
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            client.request(r)
            for c in r.response.get("candles", []):
                if c.get("complete"):
                    ts = c["time"].split(".")[0].replace("Z", "+00:00")
                    if not ts.endswith("+00:00"): ts += "+00:00"
                    all_data.append({"timestamp": ts, "open": float(c["mid"]["o"]), "high": float(c["mid"]["h"]), "low": float(c["mid"]["l"]), "close": float(c["mid"]["c"]), "volume": float(c["volume"])})
        except Exception as e:
            print(f"Error {symbol} {gran}: {e}")
        chunk_start = chunk_end
        time.sleep(0.2)
    return all_data

client = oandapyV20.API(access_token=os.environ["OANDA_API_KEY"], environment="live")
end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=35)

for sym in SYMBOLS:
    for gran, label in [("M5", "5m"), ("M15", "15m"), ("H1", "1h"), ("H4", "4h")]:
        data = chunked_download(client, sym, gran, start_date, end_date)
        if data:
            with open(DATA_DIR / f"{sym.replace('_', '')}_{label}.json", "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved {sym} {label}: {len(data)}")
