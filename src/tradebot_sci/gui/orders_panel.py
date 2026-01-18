"""Orders panel for displaying recent orders.

This module encapsulates the logic and user interface elements required
to display a list of the most recent orders within the Tradebot GUI.
It merges orders recorded in the GUI state (via the ``orders_by_id``
mapping) with live snapshots pulled from Interactive Brokers and
formats them into a table.  The panel does not handle positions
(``holdings``) which remain managed by the main window for the time
being.

The extracted panel helps reduce the size of the main application
module and isolates the responsibilities of rendering and updating the
orders table.  No business logic is changed during extraction; the
formatting and colour coding mirror the original implementation.

Usage example::

    from tradebot_sci.gui.orders_panel import OrdersPanel

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            # assume ``state`` and ``settings`` have been initialised
            self._orders_panel = OrdersPanel(self, state, settings)
            layout.addWidget(self._orders_panel)
            # when new data arrives:
            self._orders_panel.update_orders(
                state.orders_by_id,
                ibkr_orders,
                ibkr_fills,
                ibkr_status,
            )

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import time
import os

from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

from tradebot_sci.gui.shared import THEMES, _now_epoch

__all__ = ["OrdersPanel", "OrderEvent"]


@dataclass
class OrderEvent:
    """Represents a single order or fill event.

    This dataclass mirrors the original ``OrderEvent`` from the main
    application.  It is reproduced here to avoid a circular import on
    ``app.py`` while still preserving the exact fields and type hints
    used by the GUI logic.
    """

    ts: str
    symbol: str
    order_id: int
    action: Optional[str] = None
    qty: Optional[float] = None
    order_type: Optional[str] = None
    tif: Optional[str] = None
    status: Optional[str] = None
    filled: Optional[float] = None
    avg_fill_price: Optional[float] = None
    limit_price: Optional[float] = None
    updated_ts: float = 0.0


class OrdersPanel(QtWidgets.QWidget):
    """Widget for displaying recent orders.

    The panel maintains a ``QTableWidget`` which is updated whenever
    new order data is available.  It merges the persistent orders
    stored on the GUI state (``orders_by_id``) with live IBKR
    snapshots and displays up to 20 of the most recently updated
    orders.  Colour coding and text formatting match the original
    implementation in ``app.py``.
    """

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(parent)
        self._state = state
        self._settings = settings

        # Create the orders table.  We mirror the original column
        # configuration and enable sorting, alternating row colours and
        # selection behaviour.
        # [ANTIGRAVITY FIX] Check for Alternative/CCXT mode to determine columns
        provider = (os.getenv("EXCHANGE_PROVIDER") or getattr(settings.market, "exchange_provider", "") or "").strip().lower()
        broker_mode = (os.getenv("BROKER_MODE") or getattr(settings.market, "broker_mode", "") or "").strip().lower()
        self._is_alternative = (provider == "alternative" or broker_mode == "alternative")

        # Create the orders table.
        if self._is_alternative:
            # CCXT Columns: Simplified for Crypto
            self._columns = ["Time", "Symbol", "Side", "Amount", "Price", "Filled", "Status", "Type"]
            table = QtWidgets.QTableWidget(0, len(self._columns), self)
        else:
            # IBKR Columns: Standard
            self._columns = ["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]
            table = QtWidgets.QTableWidget(0, len(self._columns), self)

        table.setHorizontalHeaderLabels(self._columns)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # Allow users to resize columns
        header = table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setWordWrap(False)
        table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        # Stretch the Symbol column (Index 1)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self._table = table

        # Layout: embed only the table for now.  If desired, a header or
        # status label can be added here later.
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

    @property
    def widget(self) -> QtWidgets.QWidget:
        """Return the underlying widget for compatibility with older code."""
        return self

    def _ensure_id(self, seed: str, order_id: int) -> int:
        """Return a stable synthetic id if ``order_id`` is zero.

        This helper mirrors the logic used in the original implementation
        to generate deterministic identifiers for orders and fills
        lacking a numeric ``order_id``.  The hash is constrained to
        9 digits to avoid collisions with real IDs while remaining
        stable across invocations.
        """
        if order_id:
            return int(order_id)
        return -int(abs(hash(seed)) % 1_000_000_000 or 1)

    def update_orders(
        self,
        orders_by_id: Optional[Dict[int, OrderEvent]] = None,
        ibkr_orders: Optional[Iterable[Dict[str, Any]]] = None,
        ibkr_fills: Optional[Iterable[Dict[str, Any]]] = None,
        ibkr_status: Optional[str] = None,
    ) -> None:
        """Merge incoming order data and refresh the table display.

        Parameters
        ----------
        orders_by_id:
            A mapping of order id to ``OrderEvent`` representing
            previously seen orders.  May be ``None`` if no orders have
            been recorded yet.
        ibkr_orders:
            An iterable of dictionaries representing live order
            snapshots from Interactive Brokers.  Each dict should
            contain keys such as ``symbol``, ``ts``, ``order_id``,
            ``action``, ``qty``, ``order_type``, ``tif``, ``status``,
            ``filled``, ``avg_fill_price`` and ``limit_price``.
        ibkr_fills:
            An iterable of dictionaries representing recent order fills
            from Interactive Brokers.  The expected keys largely
            overlap with ``ibkr_orders`` but reflect fills rather than
            working orders.
        ibkr_status:
            A status string describing the last IBKR account snapshot.
        """
        merged: Dict[int, OrderEvent] = {}
        # Copy existing events from the state first.
        if orders_by_id:
            for oid, evt in orders_by_id.items():
                merged[oid] = OrderEvent(
                    ts=str(evt.ts),
                    symbol=str(evt.symbol),
                    order_id=int(evt.order_id),
                    action=evt.action,
                    qty=evt.qty,
                    order_type=evt.order_type,
                    tif=evt.tif,
                    status=evt.status,
                    filled=evt.filled,
                    avg_fill_price=evt.avg_fill_price,
                    limit_price=evt.limit_price,
                    updated_ts=float(evt.updated_ts),
                )

        now_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # Merge live working orders.
        if ibkr_orders:
            for d in ibkr_orders:
                try:
                    oid = int(d.get("order_id") or 0)
                except Exception:
                    oid = 0
                sym = str(d.get("symbol") or "?")
                ts = str(d.get("ts") or now_ts)
                oid = self._ensure_id(f"ord:{ts}:{sym}:{d.get('action')}:{d.get('qty')}", oid)
                evt = merged.get(oid) or OrderEvent(ts=ts, symbol=sym, order_id=oid)
                evt.ts = ts
                evt.symbol = sym
                evt.action = d.get("action") or evt.action
                if d.get("qty") is not None:
                    try:
                        evt.qty = float(d.get("qty"))
                    except Exception:
                        pass
                evt.order_type = d.get("order_type") or evt.order_type
                evt.tif = d.get("tif") or evt.tif
                evt.status = d.get("status") or evt.status
                if d.get("filled") is not None:
                    try:
                        evt.filled = float(d.get("filled"))
                    except Exception:
                        pass
                if d.get("avg_fill_price") is not None:
                    try:
                        evt.avg_fill_price = float(d.get("avg_fill_price"))
                    except Exception:
                        pass
                if d.get("limit_price") is not None:
                    try:
                        evt.limit_price = float(d.get("limit_price"))
                    except Exception:
                        pass
                evt.updated_ts = _now_epoch()
                merged[oid] = evt

        # Merge fills.  Fills override status to FILLED and update qty/price.
        if ibkr_fills:
            for f in ibkr_fills:
                try:
                    oid = int(f.get("order_id") or 0)
                except Exception:
                    oid = 0
                sym = str(f.get("symbol") or "?")
                ts = str(f.get("ts") or now_ts)
                oid = self._ensure_id(
                    f"fill:{ts}:{sym}:{f.get('action')}:{f.get('qty')}:{f.get('price')}",
                    oid,
                )
                evt = merged.get(oid) or OrderEvent(ts=ts, symbol=sym, order_id=oid)
                evt.ts = ts
                evt.symbol = sym
                evt.action = f.get("action") or evt.action
                if f.get("qty") is not None:
                    try:
                        evt.qty = float(f.get("qty"))
                    except Exception:
                        pass
                evt.order_type = evt.order_type or "FILL"
                evt.tif = evt.tif or "-"
                evt.status = "FILLED"
                if f.get("qty") is not None:
                    try:
                        evt.filled = float(f.get("qty"))
                    except Exception:
                        pass
                if f.get("price") is not None:
                    try:
                        evt.avg_fill_price = float(f.get("price"))
                    except Exception:
                        pass
                evt.updated_ts = _now_epoch()
                merged[oid] = evt

        # Drop stale entries so the panel doesn't keep ancient rejects forever.
        now_epoch = _now_epoch()
        cutoff = now_epoch - (24 * 60 * 60)

        def _is_recent(evt: OrderEvent) -> bool:
            if evt.updated_ts and evt.updated_ts > 0:
                return evt.updated_ts >= cutoff
            if evt.ts:
                try:
                    parsed = time.strptime(evt.ts[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return True
                return time.mktime(parsed) >= cutoff
            return True

        # Sort by most recent update time and take the top 20.
        events = [evt for evt in merged.values() if _is_recent(evt)]
        events.sort(key=lambda e: float(getattr(e, "updated_ts", 0.0)), reverse=True)
        top = events[:20]

        # Store current sorting state
        header = self._table.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        was_sorting = self._table.isSortingEnabled()
        if was_sorting:
            self._table.setSortingEnabled(False)

        # Clear any existing spans and items
        self._table.clearSpans()

        theme = THEMES.get(self._settings.theme_key, THEMES["dark"])
        if not top:
            self._table.setRowCount(1)
            hint = "No orders yet."
            if ibkr_status:
                hint += f" ({ibkr_status})"
            else:
                provider_label = getattr(self._settings, "market_provider_name", "IBKR")
                hint += f" (connect {provider_label} to see live orders/fills)"
            it = QtWidgets.QTableWidgetItem(hint)
            it.setForeground(QtGui.QColor(theme.muted))
            self._table.setSpan(0, 0, 1, self._table.columnCount())
            self._table.setItem(0, 0, it)
        else:
            self._table.setRowCount(len(top))
            for row, evt in enumerate(top):
                t = evt.ts[-8:] if len(evt.ts) >= 8 else evt.ts
                
                if self._is_alternative:
                    # CCXT Columns: ["Time", "Symbol", "Side", "Amount", "Price", "Filled", "Status", "Type"]
                    # 0: Time
                    self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(t))
                    # 1: Symbol
                    self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(evt.symbol))
                    # 2: Side
                    self._table.setItem(row, 2, QtWidgets.QTableWidgetItem(evt.action or "-"))
                    # 3: Amount (Qty) full precision
                    amt_str = f"{float(evt.qty):.8f}".rstrip("0").rstrip(".") if evt.qty is not None else "-"
                    i_amt = QtWidgets.QTableWidgetItem(amt_str)
                    i_amt.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    self._table.setItem(row, 3, i_amt)
                    # 4: Price (Avg)
                    prc_str = f"{float(evt.avg_fill_price):.4f}" if evt.avg_fill_price is not None else "-"
                    i_prc = QtWidgets.QTableWidgetItem(prc_str)
                    i_prc.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    self._table.setItem(row, 4, i_prc)
                    # 5: Filled
                    fill_str = f"{float(evt.filled):.8f}".rstrip("0").rstrip(".") if evt.filled is not None else "-"
                    i_fill = QtWidgets.QTableWidgetItem(fill_str)
                    i_fill.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    self._table.setItem(row, 5, i_fill)
                    # 6: Status
                    st_item = QtWidgets.QTableWidgetItem(evt.status or "-")
                    self._table.setItem(row, 6, st_item)
                    # 7: Type
                    self._table.setItem(row, 7, QtWidgets.QTableWidgetItem(evt.order_type or "-"))

                    # Status Color
                    status_u = (evt.status or "").upper()
                    if "FILLED" in status_u:
                        st_item.setForeground(QtGui.QColor(theme.good))
                    elif "CANCEL" in status_u or "INACTIVE" in status_u:
                        st_item.setForeground(QtGui.QColor(theme.bad))
                    elif "SUBMIT" in status_u:
                        st_item.setForeground(QtGui.QColor(theme.warn))
                    else:
                        st_item.setForeground(QtGui.QColor(theme.muted))

                else:
                    # IBKR Columns: ["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]
                    time_item = QtWidgets.QTableWidgetItem(t)
                    sym_item = QtWidgets.QTableWidgetItem(evt.symbol)
                    id_item = QtWidgets.QTableWidgetItem(str(evt.order_id))
                    id_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    side_item = QtWidgets.QTableWidgetItem(evt.action or "-")
                    qty_item = QtWidgets.QTableWidgetItem(
                        f"{float(evt.qty):.2f}" if evt.qty is not None else "-"
                    )
                    qty_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    type_item = QtWidgets.QTableWidgetItem(evt.order_type or "-")
                    tif_item = QtWidgets.QTableWidgetItem(evt.tif or "-")
                    status_item = QtWidgets.QTableWidgetItem(evt.status or "-")
                    filled_item = QtWidgets.QTableWidgetItem(
                        f"{float(evt.filled):.2f}" if evt.filled is not None else "-"
                    )
                    filled_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    avg_item = QtWidgets.QTableWidgetItem(
                        f"{float(evt.avg_fill_price):.2f}" if evt.avg_fill_price is not None else "-"
                    )
                    avg_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    
                    # Populate the row
                    self._table.setItem(row, 0, time_item)
                    self._table.setItem(row, 1, sym_item)
                    self._table.setItem(row, 2, id_item)
                    self._table.setItem(row, 3, side_item)
                    self._table.setItem(row, 4, qty_item)
                    self._table.setItem(row, 5, type_item)
                    self._table.setItem(row, 6, tif_item)
                    self._table.setItem(row, 7, status_item)
                    self._table.setItem(row, 8, filled_item)
                    self._table.setItem(row, 9, avg_item)
    
                    # Colour the status text according to outcome
                    status_u = (evt.status or "").upper()
                    if "FILLED" in status_u:
                        status_item.setForeground(QtGui.QColor(theme.good))
                    elif "CANCEL" in status_u or "INACTIVE" in status_u:
                        status_item.setForeground(QtGui.QColor(theme.bad))
                    elif "SUBMIT" in status_u:
                        status_item.setForeground(QtGui.QColor(theme.warn))
                    else:
                        status_item.setForeground(QtGui.QColor(theme.muted))

        # Restore sorting if it was enabled
        if was_sorting:
            self._table.setSortingEnabled(True)
            try:
                self._table.sortItems(int(sort_col), sort_order)
            except Exception:
                pass
