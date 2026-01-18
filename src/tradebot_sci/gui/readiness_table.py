"""Symbol readiness table for the Tradebot GUI.

This module defines a subclass of :class:`QTableWidget` that renders
structure/readiness information for each tracked symbol.  The table
displays the readiness score, selection score, gate, sweep and
continuation ages along with a truncated reason.  Colors are applied
based on the active symbol and readiness level, using the current
theme from :mod:`tradebot_sci.gui.shared`.

Extracting this code from the main window class allows the main
application to focus on orchestration while the table encapsulates
its own rendering logic.
"""

from __future__ import annotations

from typing import Any

import time

from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

from tradebot_sci.gui.shared import THEMES, _now_epoch, filter_auto_schedule_symbols

__all__ = ["ReadinessTable"]


class ReadinessTable(QtWidgets.QTableWidget):
    """Table widget showing symbol readiness and structure metrics."""

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(0, 11, parent)
        self._state = state
        self._settings = settings

        # Configure columns and headers
        self.setHorizontalHeaderLabels([
            "Symbol",
            "Active",
            "Ready",
            "Score",
            "ICC",
            "Watch",
            "Gate",
            "Sweep",
            "Cont",
            "Age",
            "Reason",
        ])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for i in range(10):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(10, QtWidgets.QHeaderView.Stretch)

    def update_table(self) -> None:
        """Refresh the table rows based on the current state."""
        items = list((self._state.structure_by_symbol or {}).items())
        if items:
            allowed_universe: set[str] | None = None
            try:
                from tradebot_sci.config.loader import load_settings, get_settings  # type: ignore
                from tradebot_sci.runtime.universe import resolve_symbol_universe  # type: ignore

                settings_obj = get_settings()
                profile_settings = settings_obj.get_active_profile()
                profile_name = settings_obj.app.profile_name
                allowed_universe = set(
                    s.upper() for s in resolve_symbol_universe(settings_obj, profile_settings, profile_name)
                )
            except Exception:
                allowed_universe = None

            if allowed_universe:
                items = [(sym, info) for sym, info in items if sym.upper() in allowed_universe]

            allowed = set(filter_auto_schedule_symbols([sym for sym, _ in items]))
            if allowed:
                items = [(sym, info) for sym, info in items if sym in allowed]
            else:
                items = []
        # Sort by readiness then selection score descending
        items.sort(key=lambda kv: (kv[1].readiness, kv[1].selection_score), reverse=True)
        now = _now_epoch()
        sort_col = self.horizontalHeader().sortIndicatorSection()
        sort_order = self.horizontalHeader().sortIndicatorOrder()
        was_sorting = self.isSortingEnabled()
        if was_sorting:
            self.setSortingEnabled(False)

        self.setRowCount(len(items))
        theme = THEMES.get(self._settings.theme_key, THEMES["dark"])
        active_sym = (self._state.active_symbol or "").strip().upper()
        for r, (sym, info) in enumerate(items):
            def mk(text: str, *, align_right: bool = False) -> QtWidgets.QTableWidgetItem:
                it = QtWidgets.QTableWidgetItem(text)
                # Disable editing
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                if align_right:
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                return it

            reason = info.reason or ""
            reason_short = reason
            if len(reason_short) > 72:
                reason_short = reason_short[:69].rstrip() + "…"

            it_sym = mk(sym)
            it_active = mk("●" if sym == active_sym else "")
            # Convert readiness to Yes/Almost/No
            try:
                r_val = float(info.readiness)
                if r_val >= 1.0:
                    ready_text = "Yes"
                elif r_val >= 0.5:
                    ready_text = "Almost"
                else:
                    ready_text = "No"
            except (ValueError, TypeError):
                ready_text = "-"
            it_ready = mk(ready_text, align_right=False)
            it_score = mk(f"{info.selection_score:.3f}", align_right=True)
            it_icc = mk(info.icc_grade or "-")
            it_watch = mk(info.watch_grade or "-")
            it_gate = mk(info.last_gate or "")
            it_sweep = mk(info.since_sweep or "", align_right=True)
            it_cont = mk(info.since_cont or "", align_right=True)
            age_s = "" if not info.seen_ts else f"{int(max(0.0, now - float(info.seen_ts)))}s"
            it_age = mk(age_s, align_right=True)
            it_reason = mk(reason_short)

            # Compose tooltip combining reason and additional metrics
            tooltip = info.reason or ""
            if info.last_gate or info.since_sweep or info.since_cont:
                extra: list[str] = []
                if info.last_gate:
                    extra.append(f"last_gate={info.last_gate}")
                if info.since_sweep:
                    extra.append(f"since_sweep={info.since_sweep}")
                if info.since_cont:
                    extra.append(f"since_cont={info.since_cont}")
                tooltip = (tooltip + "\n" if tooltip else "") + " · ".join(extra)
            for it in (
                it_sym,
                it_active,
                it_ready,
                it_score,
                it_icc,
                it_watch,
                it_gate,
                it_sweep,
                it_cont,
                it_age,
                it_reason,
            ):
                it.setToolTip(tooltip)

            # Assign items to the table
            self.setItem(r, 0, it_sym)
            self.setItem(r, 1, it_active)
            self.setItem(r, 2, it_ready)
            self.setItem(r, 3, it_score)
            self.setItem(r, 4, it_icc)
            self.setItem(r, 5, it_watch)
            self.setItem(r, 6, it_gate)
            self.setItem(r, 7, it_sweep)
            self.setItem(r, 8, it_cont)
            self.setItem(r, 9, it_age)
            self.setItem(r, 10, it_reason)

            # Apply row colours based on active symbol and readiness
            if sym == active_sym:
                bg = QtGui.QColor(theme.header)
                bg.setAlpha(140)
                for it in (
                    it_sym,
                    it_active,
                    it_ready,
                    it_score,
                    it_icc,
                    it_watch,
                    it_gate,
                    it_sweep,
                    it_cont,
                    it_age,
                    it_reason,
                ):
                    it.setBackground(bg)
            # Colour readiness values (Yes=green, Almost=yellow, No/other=muted)
            if ready_text == "Yes":
                it_ready.setForeground(QtGui.QColor(theme.good))
            elif ready_text == "Almost":
                it_ready.setForeground(QtGui.QColor(theme.warn))
            else:
                it_ready.setForeground(QtGui.QColor(theme.muted))

            # Colour ICC grade: A+/A=green, B=yellow, C/D=orange, F=red
            if info.icc_grade:
                grade = info.icc_grade.upper()
                if grade.startswith("A"):
                    it_icc.setForeground(QtGui.QColor(theme.good))
                elif grade.startswith("B"):
                    it_icc.setForeground(QtGui.QColor("#f1c40f"))  # Yellow
                elif grade.startswith("C") or grade.startswith("D"):
                    it_icc.setForeground(QtGui.QColor(theme.warn))  # Orange
                elif grade.startswith("F"):
                    it_icc.setForeground(QtGui.QColor(theme.bad))  # Red

            # Colour Watch grade: A+/A=green, B=yellow, C/D=orange, F=red
            if info.watch_grade:
                grade = info.watch_grade.upper()
                if grade.startswith("A"):
                    it_watch.setForeground(QtGui.QColor(theme.good))
                elif grade.startswith("B"):
                    it_watch.setForeground(QtGui.QColor("#f1c40f"))  # Yellow
                elif grade.startswith("C") or grade.startswith("D"):
                    it_watch.setForeground(QtGui.QColor(theme.warn))  # Orange
                elif grade.startswith("F"):
                    it_watch.setForeground(QtGui.QColor(theme.bad))  # Red

        if was_sorting:
            self.setSortingEnabled(True)
            try:
                self.sortItems(int(sort_col), sort_order)
            except Exception:
                pass

    def set_theme(self, theme_key: str) -> None:
        """Apply theme colours to the table.

        This method refreshes the readiness values' colours based on the
        supplied theme.  Call this whenever the application theme
        changes.
        """
        theme = THEMES.get(theme_key, THEMES["dark"])
        # Update existing rows with new colours
        row_count = self.rowCount()
        active_sym = (self._state.active_symbol or "").strip().upper()
        for r in range(row_count):
            it_ready = self.item(r, 2)
            it_sym = self.item(r, 0)
            if not it_ready or not it_sym:
                continue
            sym = it_sym.text().strip().upper()
            ready_text = it_ready.text().strip()
            # Colour readiness values (Yes=green, Almost=yellow, No/other=muted)
            if ready_text == "Yes":
                it_ready.setForeground(QtGui.QColor(theme.good))
            elif ready_text == "Almost":
                it_ready.setForeground(QtGui.QColor(theme.warn))
            else:
                it_ready.setForeground(QtGui.QColor(theme.muted))
            if sym == active_sym:
                bg = QtGui.QColor(theme.header)
                bg.setAlpha(140)
                for c in range(self.columnCount()):
                    it = self.item(r, c)
                    if it:
                        it.setBackground(bg)
            else:
                for c in range(self.columnCount()):
                    it = self.item(r, c)
                    if it:
                        it.setBackground(QtGui.QBrush())
