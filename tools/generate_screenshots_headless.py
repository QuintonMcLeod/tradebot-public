#!/usr/bin/env python3
import sys
import os
import time
import math
import random
from pathlib import Path
from datetime import datetime, timedelta

# Force offscreen before importing PySide6
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# Set smoke test mode to avoid connecting to IBKR/AI
os.environ["TRADEBOT_GUI_SMOKE"] = "1"
os.environ["TRADEBOT_GUI_SMOKE_BOT"] = "1"

# Add src to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PySide6 import QtWidgets, QtCore, QtGui

# Mock Bar object for chart
class MockBar:
    def __init__(self, date, open_, high, low, close):
        self.date = date
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = 1000
        self.barCount = 10
        self.average = (high + low) / 2

def generate_trend_bars(count=60):
    bars = []
    price = 1.0850
    now = datetime.now()
    # Create a nice "Hybrid Flip" structure: consolidation -> sweep -> expansion
    for i in range(count):
        t = now - timedelta(minutes=(count - i) * 15)
        
        # Inject some structure
        if i < 20: # Chop
            move = random.uniform(-0.0005, 0.0005)
        elif i < 25: # Sweep low
            move = -0.0010 - random.uniform(0, 0.0005)
        elif i < 30: # Reclaim
            move = 0.0015 + random.uniform(0, 0.0005)
        else: # Trend
            move = 0.0002 + random.uniform(-0.0001, 0.0004)
            
        open_ = price
        close = price + move
        high = max(open_, close) + random.uniform(0, 0.0003)
        low = min(open_, close) - random.uniform(0, 0.0003)
        
        bars.append(MockBar(t, open_, high, low, close))
        price = close
    return bars

def capture_dashboard():
    print("Capturing Dashboard...")
    from tradebot_sci.gui import app as gui_app
    from tradebot_sci.gui.candles_panel import CandleFetcher
    
    # 1. Patch CandleFetcher to return fake data
    original_fetch = CandleFetcher.fetch
    
    def mocked_fetch(self, symbol):
        print(f"Mock Data: Fetching for {symbol}...")
        # Emit fake bars
        bars = generate_trend_bars()
        # The updated signal signature: (bars, age, status)
        self.updated.emit(bars, 0, "Connected (SIMDATA)")
        
    CandleFetcher.fetch = mocked_fetch
    
    # 2. Monkeypatch exec to capture and exit
    original_exec = QtWidgets.QApplication.exec
    
    def mocked_exec(self):
        print("Mocked exec called. Waiting for widgets...")
        
        # Initial simulation loop to let things appear
        for _ in range(10):
            self.processEvents()
            time.sleep(0.1)
            
        widgets = self.topLevelWidgets()
        target_window = None
        for w in widgets:
            if isinstance(w, QtWidgets.QMainWindow):
                target_window = w
                break
        
        if target_window:
            print("Found MainWindow. Configuring...")
            target_window.resize(1600, 1000) # Slightly larger for crispness
            
            # Inject State/Logs
            if hasattr(target_window, "_state"):
                from tradebot_sci.gui.app import _ingest_line
                st = target_window._state
                
                # Setup active symbol
                st.active_symbol = "EURUSD"
                
                # Inject logs to populate panels
                logs = [
                    "[INFO] System initialized. Profile: forex_intraday (Risk: 1%)",
                    "[INFO] Market checks passed. Payout limit: $100.00",
                    "[STRUC] symbol=EURUSD fields=(selection_score=0.95 readiness=1.0 icc_grade=A+ last_gate=SWEEP)",
                    "[DECISION] symbol=EURUSD tf=15m rest={'action': 'ENTER_LONG', 'score': 85.5, 'score_threshold': 70.0}",
                    "ib_insync: placeOrder: id=101 action=BUY qty=25000 sym=EURUSD tif=GTC",
                    "[EXEC] OPEN_LONG: EURUSD 25k @ 1.0865 (Risk: $25.00)",
                    "[INFO] Monitoring position: EURUSD (Unrealized PnL: +$12.50)",
                    "ib_insync: orderStatus: id=101 status=Filled fill=25000 avg=1.0865",
                    "[STRUC] symbol=GBPUSD fields=(selection_score=0.4 readiness=0.2 icc_grade=C last_gate=WAIT)",
                ]
                
                for line in logs:
                    _ingest_line(st, line)
                    # Also append to log widget directly if accessible via public API logic
                    # But _ingest_line only updates state. log panel listens to file.
                    # We can manually append to the log widget for the screenshot
                    if hasattr(target_window, "_log_panel"):
                        target_window._log_panel.append_line(line)
            
            # Trigger Candle Fetch manually
            if hasattr(target_window, "_candles_panel"):
                print("Triggering candle tick...")
                target_window._candles_panel._symbol_combo.setCurrentText("EURUSD")
                target_window._candles_panel.tick_candles()
            
            # Render Loop
            print("Rendering...")
            for i in range(20):
                self.processEvents()
                time.sleep(0.2)
            
            # Capture
            out_path = REPO_ROOT / "docs/images/dashboard_main.png"
            target_window.grab().save(str(out_path))
            print(f"Saved Dashboard to {out_path} ({out_path.stat().st_size} bytes)")
                
        return 0
        
    # Apply patch
    QtWidgets.QApplication.exec = mocked_exec
    
    # Run app
    try:
        gui_app.run_app(repo_root=REPO_ROOT)
    except Exception as e:
        print(f"Error running app: {e}")

def capture_settings():
    print("Capturing Settings...")
    from tradebot_sci.gui import settings_dialog
    
    # Monkeypatch QDialog.exec
    original_exec = QtWidgets.QDialog.exec
    
    def mocked_dialog_exec(self):
        print("Mocked Dialog exec called.")
        self.resize(1180, 820)
        
        # Extended Render Loop
        for i in range(10):
            QtWidgets.QApplication.instance().processEvents()
            time.sleep(0.2)
        
        out_path = REPO_ROOT / "docs/images/settings_window.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.grab().save(str(out_path))
        print(f"Saved Settings to {out_path} ({out_path.stat().st_size} bytes)")
        return 1
        
    QtWidgets.QDialog.exec = mocked_dialog_exec
    
    try:
        settings_dialog.run_settings_only(repo_root=REPO_ROOT)
    except Exception as e:
        print(f"Error running settings: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["dashboard", "settings"], required=True)
    args = parser.parse_args()
    
    if args.target == "dashboard":
        capture_dashboard()
    elif args.target == "settings":
        capture_settings()
