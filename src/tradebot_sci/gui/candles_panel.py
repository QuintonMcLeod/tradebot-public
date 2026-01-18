"""Candles panel for the Tradebot GUI.

This module encapsulates all of the logic required to display candlestick
charts within the Tradebot GUI.  It handles symbol selection, lock
behaviour, timeframe changes and integrates with a background fetcher
that retrieves bar data from Interactive Brokers via the ``ib_insync``
package.  Moving this code into a dedicated module helps keep the
``MainWindow`` class focused on high‑level orchestration rather than
widget construction and data retrieval.

The panel is composed of a header with a symbol combo box, lock
checkbox and timeframe selector, followed by a chart view displaying
recent OHLC data.  A small status label indicates when data was
last updated.  The panel exposes a few methods to allow the main
window to drive updates (``tick_candles``) and to react to theme
changes (``set_theme``).

Usage example::

    from tradebot_sci.gui.candles_panel import CandlesPanel

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            # Assume ``state`` and ``settings`` have been initialised
            self._candles_panel = CandlesPanel(self, state, settings)
            layout.addWidget(self._candles_panel)
            # Hook into your polling timer
            self._poll_timer.timeout.connect(self._candles_panel.tick_candles)

"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import os
import re
import time

from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
from PySide6.QtCharts import (  # type: ignore
    QChart,
    QChartView,
    QCandlestickSeries,
    QCandlestickSet,
    QValueAxis,
)

from ib_insync import IB  # type: ignore
from tradebot_sci.config.loader import load_settings, get_settings
from tradebot_sci.market.models import Candle
from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider
from tradebot_sci.market.providers import CCXTMarketDataProvider, MarketDataProvider
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.market.symbols import is_crypto
from tradebot_sci.gui.shared import THEMES, _pick_symbol, _now_epoch
from tradebot_sci.runtime.provider_factory import _selected_mode

__all__ = ["CandlesPanel"]


class CandleFetcher(QtCore.QObject):
    """Background worker for fetching candlestick data from IBKR.

    This object maintains a small cache of the last returned bars and
    throttles requests based on ``settings.refresh_seconds`` to avoid
    excessive network traffic.  When a new fetch completes it emits
    the ``updated`` signal with the bar list, the age of the data and
    a status string describing any errors.
    """

    #: Emitted when a fetch has completed.  The parameters are
    #: ``bars`` (an iterable of bar objects), ``updated_age`` (seconds since
    #: last update) and ``status`` (human friendly status).
    updated = QtCore.Signal(object, int, str)

    def __init__(self, settings: Any, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._last_fetch_ts: float | None = None
        self._last_status = ""
        self._cached: list[Any] = []
        self._busy = False
        self._ib: IB | None = None
        self._client_id = int(time.time() * 1000) % 2147483647  # Unique ID from timestamp

        # Cache provider detection
        self._provider_mode = self._detect_provider_mode()
        # Cache alternative provider instance
        self._alt_provider: MarketDataProvider | None = None
        if self._provider_mode in ("alternative", "hybrid", "coinbase_futures"):

             # [ANTIGRAVITY FIX] Use factory method or direct instantiation for CCXT if futures
             if self._provider_mode == "coinbase_futures":
                 try:
                     prof = settings.profiles.get(settings.app.profile_name)
                     broker = CCXTExchangeBroker(prof, default_type="future")
                     self._alt_provider = CCXTMarketDataProvider(broker.exchange, broker.symbol_map_data)
                 except Exception:
                     self._alt_provider = None
             else:
                 self._alt_provider = CoinbaseMarketDataProvider()

    def _detect_provider_mode(self) -> str:
        """Detect provider mode: primary, alternative, or hybrid (using market_data_mode)."""
        import logging
        log = logging.getLogger(__name__)
        try:
            from tradebot_sci.config.loader import get_settings
            # loaded = get_settings() # potentially cached
            # Force checking env var directly for debugging if needed, but settings should work
            # Check decoupled field first
            loaded = get_settings()
            mode = getattr(loaded.market, "market_data_mode", None)
            log.info(f"[CANDLES] Detected market_data_mode: {mode}")
            if mode and mode != "primary":
                 return str(mode).strip().lower()
            # Fallback to legacy
            prov = getattr(loaded.market, "exchange_provider", "primary")
            return str(prov).strip().lower()
        except Exception:
            return "primary"
            # Fallback to legacy
            prov = getattr(loaded.market, "exchange_provider", "primary")
            return str(prov).strip().lower()
        except Exception:
            return "primary"



    def is_using_alt_for(self, symbol: str) -> bool:
        if self._provider_mode == "alternative":
            return True
        if self._provider_mode == "coinbase_futures":
            return True
        if self._provider_mode == "hybrid":
            return is_crypto(symbol)
        return False

    def _pick_what_to_show(self, contract: Any) -> str:  # type: ignore[no-untyped-def]
        """Return the appropriate market data type based on the contract.

        Crypto contracts use aggregated trades, Forex uses midpoint and
        stocks use trades by default.
        """
        sec_type = str(getattr(contract, "secType", "") or "").upper()
        if sec_type == "CRYPTO":
            return "AGGTRADES"
        if sec_type == "CASH":
            return "MIDPOINT"
        return "TRADES"

    def _build_contract(self, symbol: str):  # type: ignore[no-untyped-def]
        """Construct an IBKR contract from a plain symbol string.

        The trading bot supports a mixture of crypto, FX and stock
        symbols.  This helper returns the appropriate contract type for
        the given symbol.  Contracts are returned from ``ib_insync``
        classes and will raise if the package is not installed.
        """
        from ib_insync import Crypto, Forex, Stock  # type: ignore

        sym = symbol.strip().upper()
        # Detect crypto pairs like BTCUSD, ETHUSD etc.  Only a handful
        # of base coins are supported via IBKR ZeroHash integration.
        if re.fullmatch(r"[A-Z]{3,10}USD", sym):
            base = sym[:-3]
            if base in {"BTC", "ETH", "SOL", "LTC", "BCH", "XRP", "ADA", "DOGE", "AVAX", "LINK"}:
                return Crypto(base, os.getenv("IBKR_CRYPTO_EXCHANGE", "ZEROHASH"), "USD")
        # Detect FX pairs (6 characters, both in known FX set)
        if re.fullmatch(r"[A-Z]{6}", sym):
            fx_ccy = {
                "USD",
                "EUR",
                "JPY",
                "GBP",
                "CHF",
                "CAD",
                "AUD",
                "NZD",
                "SEK",
                "NOK",
                "DKK",
                "HKD",
                "SGD",
                "CNH",
                "MXN",
                "ZAR",
                "TRY",
                "PLN",
                "CZK",
                "HUF",
                "ILS",
            }
            base, quote = sym[:3], sym[3:]
            if base in fx_ccy and quote in fx_ccy:
                return Forex(sym)
        # Default to stock contract
        return Stock(sym, "SMART", "USD")

    def _ensure_connection(self) -> tuple[IB, str]:
        """Ensure IBKR connection is established, return (ib, status).

        Reuses persistent connection if available and connected.
        Creates new connection if needed with unique client ID.
        Returns status string (empty if successful).
        """
        import logging
        logger = logging.getLogger(__name__)

        host = os.getenv("IBKR_HOST", "127.0.0.1")
        port = int(os.getenv("IBKR_PORT", "7497"))

        # Check if existing connection is still valid
        if self._ib is not None:
            try:
                if self._ib.isConnected():
                    return self._ib, ""
                else:
                    # Connection dropped, clear it
                    self._ib = None
            except Exception as e:
                logger.warning(f"CandleFetcher: Error checking connection: {e}")
                self._ib = None

        # [ANTIGRAVITY FIX] Strict guard: do not connect to IBKR in alternative mode
        if self._provider_mode == "alternative":
            return None, "IBKR disabled (alternative mode)"

        # Create new connection
        self._ib = IB()
        try:
            self._ib.connect(host, port, clientId=self._client_id, timeout=2.0)
            try:
                self._ib.reqMarketDataType(3)  # Delayed data
            except Exception:
                pass  # Not critical if this fails
            return self._ib, ""
        except Exception as exc:
            status = f"connection failed: {exc}"
            logger.error(f"CandleFetcher: {status}")
            self._ib = None
            return None, status  # type: ignore[return-value]

    def disconnect(self) -> None:
        """Clean up IBKR connection if active."""
        if self._ib is not None:
            try:
                if self._ib.isConnected():
                    self._ib.disconnect()

                # Force cleanup of ib_insync's event loop and threads
                import asyncio
                import time

                try:
                    # Get the event loop from ib_insync's client
                    loop = None
                    if hasattr(self._ib, 'client') and hasattr(self._ib.client, '_loop'):
                        loop = self._ib.client._loop
                    elif hasattr(self._ib, '_loop'):
                        loop = self._ib._loop

                    if loop and not loop.is_closed():
                        # Cancel all tasks on the loop
                        try:
                            pending = asyncio.all_tasks(loop)
                            for task in pending:
                                task.cancel()
                            # Give tasks time to cancel
                            time.sleep(0.1)
                        except RuntimeError:
                            # all_tasks might fail if loop is from another thread
                            pass

                        # Stop the loop if it's running
                        if loop.is_running():
                            loop.call_soon_threadsafe(loop.stop)
                            time.sleep(0.1)

                        # Close the loop
                        if not loop.is_closed():
                            loop.close()

                    # Wait for any background threads to finish (ib_insync uses a reader thread)
                    # Give it time to clean up
                    time.sleep(0.3)

                except Exception:
                    pass

            except Exception:
                pass
            finally:
                self._ib = None

    def fetch(self, symbol: str) -> None:
        """Fetch bar data for ``symbol`` and emit the result.

        Supports both IBKR (standard) and alternative providers based on configuration.
        """
        if self._busy:
            now = _now_epoch()
            updated_age = (
                0
                if self._last_fetch_ts is None
                else max(0, int(round(now - float(self._last_fetch_ts))))
            )
            self.updated.emit(self._cached, updated_age, self._last_status)
            return

        use_alt = self.is_using_alt_for(symbol)
        now = _now_epoch()
        # Throttling
        limit = 0.5 if use_alt else float(getattr(self._settings, "refresh_seconds", 5.0))

        if (
            self._last_fetch_ts is not None
            and now - float(self._last_fetch_ts) < limit
        ):
            updated_age = max(0, int(round(now - float(self._last_fetch_ts))))
            self.updated.emit(self._cached, updated_age, self._last_status)
            return

        if use_alt:
            self._fetch_alternative(symbol)
        else:
            self._fetch_ibkr(symbol)

    def _fetch_alternative(self, symbol: str) -> None:
        """Fetch candles via alternative provider (synchronous, fast)."""
        import logging
        logger = logging.getLogger(__name__)
        self._busy = True
        provider_name = getattr(self._settings, "market_provider_name", "Alternative")
        try:
            # Use cached provider instance
            provider = self._alt_provider
            if provider is None:
                # Fallback if somehow not initialized
                provider = CoinbaseMarketDataProvider()

            # Get settings
            tf = getattr(self._settings, "candle_tf", "5m")

            bars = provider.get_latest_candles(symbol, tf, limit=120)

            self._cached = bars
            self._last_fetch_ts = _now_epoch()
            self._last_status = f"{provider_name} API"
            self.updated.emit(bars, 0, self._last_status)

        except Exception as e:
            logger.error(f"[CANDLES] {provider_name} fetch failed: {e}")
            self._last_status = str(e)
            self.updated.emit(self._cached, 0, f"Error: {e}")
        finally:
            self._busy = False

    def _fetch_ibkr(self, symbol: str) -> None:
        """Fetch candles via IBKR (legacy/standard path)."""
        try:
            from ib_insync import IB  # type: ignore
        except Exception as exc:
            # ib_insync is optional; report missing module
            self._last_fetch_ts = _now_epoch()
            self._last_status = f"ib_insync missing: {exc}"
            self._cached = []
            self.updated.emit([], 0, self._last_status)
            return

        now = _now_epoch()
        # Throttle based on refresh_seconds
        if (
            self._last_fetch_ts is not None
            and now - float(self._last_fetch_ts) < float(getattr(self._settings, "refresh_seconds", 5.0))
        ):
            updated_age = max(0, int(round(now - float(self._last_fetch_ts))))
            self.updated.emit(self._cached, updated_age, self._last_status)
            return

        bars: list[Any] = []
        status = ""
        self._busy = True
        ib = None
        try:
            # Use persistent connection instead of creating new one each time
            ib, conn_status = self._ensure_connection()
            if conn_status:
                status = conn_status
                bars = []
            elif ib is not None:
                contract = self._build_contract(symbol)
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    status = "unqualified"
                else:
                    what = self._pick_what_to_show(qualified[0])
                    bars = (
                        ib.reqHistoricalData(
                            qualified[0],
                            endDateTime="",  # now
                            durationStr="3 D",
                            barSizeSetting=getattr(self._settings, "candle_tf", "15m"),
                            whatToShow=what,
                            useRTH=False,
                            formatDate=2,
                            keepUpToDate=False,
                        )
                        or []
                    )
                    if not bars:
                        status = "no bars"
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            status = str(exc)
            logger.error(f"CandleFetcher: Error fetching {symbol}: {exc}")
            # Connection might be broken, clear it to force reconnect next time
            self._ib = None
        finally:
            self._busy = False
            # NOTE: Connection stays open for reuse (cleaned up in disconnect())

        self._last_fetch_ts = _now_epoch()
        self._last_status = status
        self._cached = bars
        updated_age = 0
        self.updated.emit(bars, updated_age, status)


class CandlesPanel(QtWidgets.QWidget):
    """Panel for rendering candlestick charts with symbol selection.

    The panel presents a header with a symbol dropdown, lock checkbox and
    timeframe selector.  It uses a ``CandleFetcher`` to retrieve bar
    data asynchronously and updates the chart view when new data
    arrives.  A small status label displays the age of the last update.
    """

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(parent)
        self._state = state
        self._settings = settings
        self._current_symbol: str | None = None
        self._chart_locked_symbol: str | None = None
        self._market_data_enabled: bool = True

        # Title and status labels
        self._title = QtWidgets.QLabel("CANDLES")
        self._title.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._status = QtWidgets.QLabel("")
        self._status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        # Timeframe combo box
        self._tf_combo = QtWidgets.QComboBox()
        self._tf_combo.setMaximumWidth(140)
        candle_sizes: list[tuple[str, str]] = [
            ("1m", "1 min"),
            ("5m", "5 mins"),
            ("15m", "15 mins"),
            ("30m", "30 mins"),
            ("1h", "1 hour"),
            ("1d", "1 day"),
            ("1w", "1 week"),
            ("1M", "1 month"),
        ]
        for label, val in candle_sizes:
            self._tf_combo.addItem(label, val)
        # Set initial timeframe from settings
        for i in range(self._tf_combo.count()):
            if str(self._tf_combo.itemData(i) or "") == str(self._settings.candle_tf or ""):
                self._tf_combo.setCurrentIndex(i)
                break
        self._tf_combo.currentIndexChanged.connect(self._on_tf_changed)

        # Symbol selector and lock checkbox
        self._symbol_combo = QtWidgets.QComboBox()
        self._symbol_combo.setMaximumWidth(120)
        self._symbol_combo.setEditable(False)
        self._symbol_combo.currentIndexChanged.connect(self._on_symbol_selected)

        self._lock_checkbox = QtWidgets.QCheckBox("Lock")
        self._lock_checkbox.stateChanged.connect(self._on_lock_toggled)

        # Create chart objects
        self._series = QCandlestickSeries()
        # Set initial colours
        theme = THEMES.get(self._settings.theme_key, THEMES["dark"])
        self._series.setIncreasingColor(QtGui.QColor(theme.good))
        self._series.setDecreasingColor(QtGui.QColor(theme.bad))
        try:
            if hasattr(self._series, "setBodyOutlineVisible"):
                self._series.setBodyOutlineVisible(False)  # type: ignore[attr-defined]
            if hasattr(self._series, "setBodyWidth"):
                self._series.setBodyWidth(0.9)  # type: ignore[attr-defined]
            if hasattr(self._series, "setCapsWidth"):
                self._series.setCapsWidth(0.35)  # type: ignore[attr-defined]
        except Exception:
            pass

        self._chart = QChart()
        self._chart.legend().hide()
        self._chart.addSeries(self._series)

        self._axis_x = QValueAxis()
        self._axis_y = QValueAxis()
        self._axis_x.setGridLineVisible(False)
        self._axis_y.setGridLineVisible(True)
        self._axis_y.setMinorGridLineVisible(False)
        self._axis_y.setTickCount(6)

        self._chart.addAxis(self._axis_x, QtCore.Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, QtCore.Qt.AlignRight)
        self._series.attachAxis(self._axis_x)
        self._series.attachAxis(self._axis_y)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Layout header and chart
        hdr_layout = QtWidgets.QHBoxLayout()
        hdr_layout.addWidget(self._title)
        hdr_layout.addSpacing(8)
        hdr_layout.addWidget(QtWidgets.QLabel("Symbol"))
        hdr_layout.addWidget(self._symbol_combo)
        hdr_layout.addSpacing(8)
        hdr_layout.addWidget(self._lock_checkbox)
        hdr_layout.addSpacing(8)
        hdr_layout.addWidget(QtWidgets.QLabel("TF"))
        hdr_layout.addWidget(self._tf_combo)
        hdr_layout.addStretch(1)
        hdr_layout.addWidget(self._status)

        vlayout = QtWidgets.QVBoxLayout(self)
        vlayout.addLayout(hdr_layout)
        vlayout.addWidget(self._view, 1)

        # Create fetcher and connect signal
        self._fetcher = CandleFetcher(self._settings, self)
        self._fetcher.updated.connect(self._on_candles)

        # Populate available symbols once UI is constructed
        self.populate_symbols()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Clean up IBKR connection when panel is closed."""
        if hasattr(self, "_fetcher"):
            self._fetcher.disconnect()
        super().closeEvent(event)

    # --- Public API -----------------------------------------------------
    @property
    def widget(self) -> QtWidgets.QWidget:
        """Return the top‑level widget for the panel.

        In this implementation the panel itself is the widget, so this
        simply returns ``self``.  This property mirrors the interface
        used by the log and decisions panels for consistency.
        """
        return self

    def set_market_data_enabled(self, enabled: bool) -> None:
        """Enable or disable market data fetching.

        When disabled, calls to ``tick_candles`` will not trigger any
        data fetches and the status label will indicate that the chart
        is waiting for a start signal.
        """
        self._market_data_enabled = bool(enabled)

    def set_theme(self, theme_key: str) -> None:
        """Apply a new theme to the chart elements.

        This updates series colours, chart background and axis label
        colours based on the supplied theme key.  It should be called
        whenever the user changes themes from the main window.
        """
        theme = THEMES.get(theme_key, THEMES["dark"])
        self._series.setIncreasingColor(QtGui.QColor(theme.good))
        self._series.setDecreasingColor(QtGui.QColor(theme.bad))
        try:
            self._series.setPen(QtGui.QPen(QtGui.QColor(theme.muted), 1))
        except Exception:
            pass
        self._chart.setBackgroundBrush(QtGui.QColor(theme.base))
        self._chart.setPlotAreaBackgroundVisible(True)
        self._chart.setPlotAreaBackgroundBrush(QtGui.QBrush(QtGui.QColor(theme.base)))
        self._chart.setTitleBrush(QtGui.QBrush(QtGui.QColor(theme.text)))
        self._axis_x.setLabelsColor(QtGui.QColor(theme.muted))
        self._axis_y.setLabelsColor(QtGui.QColor(theme.muted))
        self._axis_y.setGridLineColor(QtGui.QColor(theme.border))

    def tick_candles(self) -> None:
        """Poll for new candle data if enabled and a symbol is selected."""
        if not self._market_data_enabled:
            return

        # Determine which symbol to fetch: locked symbol > active symbol > auto-pick
        symbol_to_fetch: str | None = None
        mode = "manual"
        if self._chart_locked_symbol:
            symbol_to_fetch = self._chart_locked_symbol
            mode = "locked"
        elif self._state.active_symbol:
            active_symbol = str(self._state.active_symbol).upper()
            symbol_to_fetch = active_symbol
            mode = "bot-selected"
            # Don't overwrite locked symbol - it may have been set by populate_symbols() auto-lock
        else:
            symbols_filter, _ = self._resolve_trading_symbols()
            picked_symbol, _ = _pick_symbol(
                self._state,
                rotate_seconds=self._settings.rotate_seconds,
                symbols_filter=symbols_filter,
            )
            symbol_to_fetch = picked_symbol

        # [ANTIGRAVITY FIX] Sanitize non-crypto symbols in alternative mode
        if self._fetcher._provider_mode == "alternative" and symbol_to_fetch and symbol_to_fetch != "N/A" and not is_crypto(symbol_to_fetch):
            # Try to pick a valid one from config
            symbols_filter, _ = self._resolve_trading_symbols()
            valid = [s for s in symbols_filter if is_crypto(s)]
            if valid:
                symbol_to_fetch = valid[0]
            else:
                symbol_to_fetch = None

        if not symbol_to_fetch or symbol_to_fetch == "N/A":
            self._status.setText("updated=never (no symbol selected/active)")
            mode = self._fetcher._provider_mode
            status_suffix = "delayed"
            if mode == "alternative": status_suffix = "live"
            elif mode == "hybrid": status_suffix = "hybrid"
            self._title.setText(f"CANDLES - N/A ({status_suffix})")
            self._series.clear()
            self._chart.setTitle("No symbol")
            return

        # Ensure combo reflects current symbol
        if self._symbol_combo.currentText() != symbol_to_fetch:
            self._symbol_combo.blockSignals(True)
            idx = self._symbol_combo.findText(symbol_to_fetch)
            if idx != -1:
                self._symbol_combo.setCurrentIndex(idx)
            else:
                self._symbol_combo.addItem(symbol_to_fetch)
                self._symbol_combo.setCurrentText(symbol_to_fetch)
            self._symbol_combo.blockSignals(False)

        self._current_symbol = symbol_to_fetch
        use_alt = self._fetcher.is_using_alt_for(symbol_to_fetch)
        status_suffix = "live" if use_alt else "delayed"
        self._title.setText(f"CANDLES - {symbol_to_fetch} ({status_suffix}) [{mode}]")
        # Kick off a fetch in the next event loop iteration
        QtCore.QTimer.singleShot(0, lambda: self._fetcher.fetch(symbol_to_fetch))

# --- Internal helpers ---------------------------------------------
    def _on_tf_changed(self, _idx: int) -> None:
        """Callback for timeframe combo box changes."""
        val = str(self._tf_combo.currentData() or "").strip()
        if not val:
            return
        if val == getattr(self._settings, "candle_tf", None):
            return
        self._settings.candle_tf = val
        # Persist timeframe selection via QSettings if available on settings
        try:
            qsettings = getattr(self._settings, "_qsettings", None)
            if qsettings:
                qsettings.setValue("candles/tf", self._settings.candle_tf)
        except Exception:
            pass
        # Reset fetcher state so next tick pulls fresh data
        try:
            setattr(self._fetcher, "_last_fetch_ts", None)
        except Exception:
            pass
        self.tick_candles()

    def populate_symbols(self) -> None:
        """Populate the symbol combo box from configuration."""
        try:
            configured_symbols = None
            prof = self._settings.get_active_profile()
            # [ANTIGRAVITY FIX] Explicitly check for presence, allow empty list if that's what's intended 
            # (though here we usually want to fall back if symbols isn't defined at all in the profile)
            if prof is not None and hasattr(prof, "symbols"):
                configured_symbols = prof.symbols
            
            if configured_symbols is None:
                market = getattr(self._settings, "market", None)
                if market is not None:
                    configured_symbols = getattr(market, "symbols", None)
        except Exception:
            configured_symbols = []

        # [ANTIGRAVITY FIX] Ensure signals are blocked and try/finally is correctly structured
        self._symbol_combo.blockSignals(True)
        try:
            self._symbol_combo.clear()
            syms = {str(s).strip().upper() for s in configured_symbols if s}

            # Filter symbols if in alternative (crypto-only) mode
            if self._fetcher._provider_mode == "alternative":
                syms = {s for s in syms if is_crypto(s)}
            
            if syms:
                self._symbol_combo.addItems(sorted(syms))
                # Set initial symbol to default_symbol from config if available
                try:
                    default_sym = getattr(self._settings.market, 'default_symbol', None)
                    if default_sym:
                        default_sym = str(default_sym).strip().upper()
                        idx = self._symbol_combo.findText(default_sym)
                        if idx >= 0:
                            self._symbol_combo.setCurrentIndex(idx)
                            # Auto-lock to default symbol on first load
                            if not self._chart_locked_symbol:
                                self._chart_locked_symbol = default_sym
                                self._lock_checkbox.setChecked(True)
                except Exception:
                    pass
            else:
                self._symbol_combo.addItem("No Symbols Configured", "N/A")
        finally:
            self._symbol_combo.blockSignals(False)


    def _on_symbol_selected(self) -> None:
        """Handle changes in the symbol combo selection."""
        selected_symbol = self._symbol_combo.currentText()
        
        # [ANTIGRAVITY FIX] If user overrides symbol, auto-lock to it
        if selected_symbol and selected_symbol != "No Symbols Configured":
            self._chart_locked_symbol = selected_symbol
            if not self._lock_checkbox.isChecked():
                self._lock_checkbox.setChecked(True)
        
        self.tick_candles()

    def _on_lock_toggled(self, state: int) -> None:
        """Handle toggling of the lock checkbox."""
        if state == QtCore.Qt.Checked:
            selected_symbol = self._symbol_combo.currentText()
            self._chart_locked_symbol = (
                None if selected_symbol == "No Symbols Configured" else selected_symbol
            )
            parent = self.parentWidget()
            if parent is not None:
                try:
                    parent.statusBar().showMessage(
                        f"Chart locked to: {self._chart_locked_symbol or 'N/A'}"
                    )
                except Exception:
                    pass
        else:
            self._chart_locked_symbol = None
            parent = self.parentWidget()
            if parent is not None:
                try:
                    parent.statusBar().showMessage("Chart unlocked. Auto-selecting active symbol.")
                except Exception:
                    pass
        self.tick_candles()

    def _resolve_trading_symbols(self) -> tuple[list[str], list[str]]:
        """Return the list of configured trading symbols and a short list of names.

        This helper mirrors the ``_resolve_trading_symbols`` method in
        the original ``MainWindow``.  It reads the ``state.structure_by_symbol``
        to determine which symbols are currently available for trading and
        sorts them based on the highest readiness scores.  A fallback list
        containing all configured symbols is returned if no structure data
        is present.
        """
        # Use structure if available
        out_syms: list[str] = []
        out_names: list[str] = []
        try:
            struct = self._state.structure_by_symbol or {}
            if struct:
                items = list(struct.items())
                # Sort by readiness then selection score
                items.sort(key=lambda kv: (kv[1].readiness, kv[1].selection_score), reverse=True)
                for sym, _info in items:
                    out_syms.append(str(sym).upper())
                out_names = list(out_syms)
            else:
                # Fallback to all configured symbols
                cfg_syms = None
                market = getattr(self._settings, "market", None)
                if market is not None:
                    cfg_syms = getattr(market, "symbols", None)
                if not cfg_syms:
                    cfg_syms = get_settings().market.symbols
                out_syms = [str(s).upper() for s in cfg_syms or []]
                out_names = list(out_syms)
        except Exception:
            pass
        return out_syms, out_names

    def _on_candles(self, bars: object, updated_age: int, status: str) -> None:
        """Slot invoked when the fetcher emits a new set of bar data."""
        # Update status label
        # Show "Live" for alternative providers (no countdown needed), show age for IBKR
        if self._fetcher._provider_mode == "alternative":
            status_txt = "Live"
        else:
            status_txt = f"Updated {updated_age}s ago"
        if status:
            status_txt += f" · {status}"
        self._status.setText(status_txt)

        bar_list = list(bars or [])
        if not bar_list:
            self._series.clear()
            self._chart.setTitle("No bars")
            return

        def _bar_epoch(b: Any) -> float:
            d = getattr(b, "date", None)
            if d is None:
                return 0.0
            try:
                if isinstance(d, (int, float)):
                    return float(d)
                ts = getattr(d, "timestamp", None)
                if callable(ts):
                    return float(ts())
                if isinstance(d, str):
                    s = d.strip()
                    if s.isdigit():
                        return float(int(s))
                    # IBKR commonly: "YYYYMMDD  HH:MM:SS"
                    m = re.match(r"^(\d{8})\s+(\d{2}:\d{2}:\d{2})$", s)
                    if m:
                        from datetime import datetime as _dt

                        dt = _dt.strptime(m.group(1) + " " + m.group(2), "%Y%m%d %H:%M:%S")
                        return float(dt.timestamp())
                    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})$", s)
                    if m:
                        from datetime import datetime as _dt

                        dt = _dt.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")
                        return float(dt.timestamp())
            except Exception:
                return 0.0
            return 0.0

        ordered = sorted(bar_list, key=_bar_epoch)

        self._series.clear()
        x = 0.0
        highs: list[float] = []
        lows: list[float] = []
        n = max(10, int(getattr(self._settings, "candle_bars", 120) or 120))
        for b in ordered[-n:]:
            o = float(getattr(b, "open", 0.0) or 0.0)
            h = float(getattr(b, "high", 0.0) or 0.0)
            l = float(getattr(b, "low", 0.0) or 0.0)
            c = float(getattr(b, "close", 0.0) or 0.0)
            cs = QCandlestickSet(o, h, l, c, x)
            self._series.append(cs)
            highs.append(h)
            lows.append(l)
            x += 1.0

        lo = min(lows)
        hi = max(highs)
        if hi <= lo:
            hi = lo + 1e-6
        self._axis_x.setRange(max(0.0, x - float(n)), x)
        pad = (hi - lo) * 0.05
        self._axis_y.setRange(lo - pad, hi + pad)
        tf_label = str(self._settings.candle_tf or "").strip() or "?"
        self._chart.setTitle(f"CANDLE CHART ({tf_label})")
