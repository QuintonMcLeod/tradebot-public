"""Web-based Candles panel for the Tradebot GUI (High Fidelity).

This module replaces the native QtCharts implementation with a QWebEngineView
rendering TradingView Lightweight Charts (HTML/JS). This provides a "Pro"
look with sophisticated grids, smooth panning, and marker support.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets, QtWebEngineWidgets  # type: ignore

from tradebot_sci.gui.candles_panel import CandleFetcher
from tradebot_sci.gui.shared import THEMES, _pick_symbol, _now_epoch
from tradebot_sci.market.symbols import is_crypto

class WebChartPanel(QtWidgets.QWidget):
    """Panel for rendering candlestick charts using a WebEngine view."""

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(parent)
        self._state = state
        self._settings = settings
        self._current_symbol: str | None = None
        self._chart_locked_symbol: str | None = None
        self._market_data_enabled: bool = True
        self._js_ready = False
        self._fills_cache: list[dict] = []

        # -- UI Components --
        
        # 1. Header Controls (Styled to look integrated)
        self._title = QtWidgets.QLabel("CANDLES")
        self._title.setStyleSheet("font-weight: bold; color: #a1a1aa;")
        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #52525b; font-size: 10px;")

        self._tf_combo = QtWidgets.QComboBox()
        self._tf_combo.setMaximumWidth(80)
        self._tf_combo.setStyleSheet("background: #18181b; color: #e4e4e7; border: 1px solid #27272a;")
        candle_sizes = [("1m", "1 min"), ("5m", "5 mins"), ("15m", "15 mins"), 
                       ("1h", "1 hour"), ("4h", "4 hours"), ("1d", "1 day")]
        for label, val in candle_sizes:
            self._tf_combo.addItem(label, val)
            
        # Set initial TF
        current_tf = getattr(self._settings, "candle_tf", "5m")
        idx = self._tf_combo.findData(current_tf)
        if idx >= 0: self._tf_combo.setCurrentIndex(idx)
        self._tf_combo.currentIndexChanged.connect(self._on_tf_changed)

        self._symbol_combo = QtWidgets.QComboBox()
        self._symbol_combo.setEditable(False)
        self._symbol_combo.setMaximumWidth(100)
        self._symbol_combo.setStyleSheet("background: #18181b; color: #e4e4e7; border: 1px solid #27272a;")
        self._symbol_combo.currentIndexChanged.connect(self._on_symbol_selected)

        self._lock_checkbox = QtWidgets.QCheckBox("Lock")
        self._lock_checkbox.setStyleSheet("color: #a1a1aa;")
        self._lock_checkbox.stateChanged.connect(self._on_lock_toggled)

        # Header Layout
        hdr_widget = QtWidgets.QWidget()
        # Transparent header with slight tint
        hdr_widget.setStyleSheet("background-color: rgba(9, 9, 11, 0.5); border-bottom: 1px solid rgba(39, 39, 42, 0.5);")
        hdr_layout = QtWidgets.QHBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(8, 4, 8, 4)
        hdr_layout.addWidget(self._title)
        hdr_layout.addSpacing(10)
        hdr_layout.addWidget(self._symbol_combo)
        hdr_layout.addWidget(self._tf_combo)
        hdr_layout.addWidget(self._lock_checkbox)
        hdr_layout.addStretch(1)
        hdr_layout.addWidget(self._status)

        # 2. Web View
        self._view = QtWebEngineWidgets.QWebEngineView()
        self._view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        
        # [ANTIGRAVITY] Transparency
        self._view.page().setBackgroundColor(QtCore.Qt.transparent)
        self._view.setStyleSheet("background: transparent;")
        
        # Load local HTML
        html_path = Path(__file__).parent / "assets" / "chart.html"
        self._view.load(QtCore.QUrl.fromLocalFile(str(html_path.resolve())))
        self._view.loadFinished.connect(self._on_load_finished)

        # Main Layout
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        # We might not even need the header widget if we want pure overlay?
        # But controls are needed. Keep transparency.
        root_layout.addWidget(hdr_widget)
        root_layout.addWidget(self._view, 1)

        # 3. Data Fetcher
        self._fetcher = CandleFetcher(self._settings, self)
        self._fetcher.updated.connect(self._on_candles)
        
        self.populate_symbols()

    def _on_load_finished(self, ok: bool):
        if ok:
            self._js_ready = True
            # Initial sync if we have a symbol
            if self._current_symbol:
                self._update_watermark()

    def set_market_data_enabled(self, enabled: bool) -> None:
        self._market_data_enabled = bool(enabled)

    def set_theme(self, theme_key: str) -> None:
        # We could inject CSS into the webview here, but for now chart.html is hardcoded "Cyberpunk"
        pass
        
    def populate_symbols(self) -> None:
        # (Reuse logic from CandlesPanel - abbreviated for brevity but functional)
        try:
            prof = self._settings.get_active_profile()
            configured = (prof.symbols if prof and hasattr(prof, "symbols") else []) or []
        except:
            configured = []
            
        self._symbol_combo.blockSignals(True)
        self._symbol_combo.clear()
        syms = {str(s).strip().upper() for s in configured if s}
        if self._fetcher._provider_mode == "alternative":
             syms = {s for s in syms if is_crypto(s)}
             
        if syms:
            self._symbol_combo.addItems(sorted(syms))
            # Auto-select default
            default = str(getattr(self._settings.market, 'default_symbol', '')).upper()
            idx = self._symbol_combo.findText(default)
            if idx >= 0:
                self._symbol_combo.setCurrentIndex(idx)
                if not self._chart_locked_symbol:
                    self._chart_locked_symbol = default
                    self._lock_checkbox.setChecked(True)
        else:
            self._symbol_combo.addItem("No Symbols", "N/A")
        self._symbol_combo.blockSignals(False)

    def tick_candles(self) -> None:
        if not self._market_data_enabled: return
        
        # Resolve symbol logic (Locked > Active > Rotation)
        symbol = None
        mode = "manual"
        if self._chart_locked_symbol:
            symbol = self._chart_locked_symbol
            mode = "locked"
        elif self._state.active_symbol:
            symbol = str(self._state.active_symbol).upper()
            mode = "bot"
        else:
             # Rotation logic
             pass # Skip complex rotation for now to ensure stability
             
        if not symbol: return

        if symbol != self._current_symbol:
            self._current_symbol = symbol
            # Sync combo
            self._symbol_combo.blockSignals(True)
            idx = self._symbol_combo.findText(symbol)
            if idx >= 0: self._symbol_combo.setCurrentIndex(idx)
            self._symbol_combo.blockSignals(False)
            self._update_watermark()
            
        self._title.setText(f"CHART • {symbol} • {mode}")
        
        # Trigger Fetch
        QtCore.QTimer.singleShot(0, lambda: self._fetcher.fetch(symbol))

    def _on_candles(self, bars: list, age: int, status: str):
        self._status.setText(f"Data: {status} ({age}s ago)")
        if not self._js_ready: return
        
        # Convert bars to JSON for JS
        # JS expects: { time: unix_timestamp, open: float, high: float, low: float, close: float }
        # IBKR 'bars' are objects with .date (datetime or date)
        
        json_data = []
        for b in bars:
            # Handle both IBKR objects (attrs) and CCXT/Mock dicts
            ts = 0
            o = h = l = c = 0.0
            
            # 1. Timestamp
            if hasattr(b, "date"):
                d = b.date
                ts = d.timestamp() if hasattr(d, "timestamp") else 0
            elif isinstance(b, dict) and "date" in b:
                # CCXT often returns datetime objects or ISO strings or timestamps
                val = b["date"]
                if hasattr(val, "timestamp"):
                    ts = val.timestamp()
                elif isinstance(val, (int, float)):
                    ts = val
            elif isinstance(b, (list, tuple)) and len(b) > 0:
                # raw OHLCV list [ts, o, h, l, c, v]
                ts = b[0] / 1000.0 # CCXT uses ms
                
            # 2. OHLCW
            if hasattr(b, "open"):
                o = float(b.open)
                h = float(b.high)
                l = float(b.low)
                c = float(b.close)
            elif isinstance(b, dict):
                o = float(b.get("open", 0.0))
                h = float(b.get("high", 0.0))
                l = float(b.get("low", 0.0))
                c = float(b.get("close", 0.0))
            elif isinstance(b, (list, tuple)) and len(b) >= 5:
                o = float(b[1])
                h = float(b[2])
                l = float(b[3])
                c = float(b[4])

            json_data.append({
                "time": int(ts),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            })
            
        # Send to JS
        cmd = f"window.tradebot.updateData({json.dumps(json_data)});"
        self._view.page().runJavaScript(cmd)

    def update_fills(self, fills: list[dict]):
        """Receive recent fills to display checks on chart."""
        # This would convert fills to markers
        # Marker format: { time: ts, position: 'aboveBar'/'belowBar', color: 'red'/'green', shape: 'arrowDown'/'arrowUp', text: 'SELL' }
        pass # Todo: implement fill mapping match current symbol

    # -- Internal Slots --
    def _on_tf_changed(self, _):
        val = str(self._tf_combo.itemData(self._tf_combo.currentIndex()))
        if val != getattr(self._settings, "candle_tf", ""):
            self._settings.candle_tf = val
            # Reset fetcher
            setattr(self._fetcher, "_last_fetch_ts", None)
            self._update_watermark()
            self.tick_candles()

    def _on_symbol_selected(self, _):
        sym = self._symbol_combo.currentText()
        if sym and sym != "No Symbols":
            self._chart_locked_symbol = sym
            self._lock_checkbox.setChecked(True)
            self.tick_candles()

    def _on_lock_toggled(self, state):
        if state == QtCore.Qt.Checked:
            self._chart_locked_symbol = self._symbol_combo.currentText()
        else:
            self._chart_locked_symbol = None
            
    def _update_watermark(self):
        if not self._js_ready or not self._current_symbol: return
        tf = str(self._tf_combo.currentText())
        cmd = f"window.tradebot.setSymbolInfo('{self._current_symbol}', '{tf}');"
        self._view.page().runJavaScript(cmd)
