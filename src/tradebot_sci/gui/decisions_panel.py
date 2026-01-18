"""Recent decisions panel for the Tradebot GUI.

This module encapsulates the logic for parsing decision events and
rendering them with proper formatting.  The panel displays a
scrollable text area showing the most recent decisions along with
formatted explanations produced by the DecisionFormatter.

Moving this code into a separate module helps decouple the main
window from decision parsing and formatting logic, improving
maintainability and testability.
"""

from __future__ import annotations

from typing import Any

import json
import logging
import re

from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

from tradebot_sci.gui.shared import THEMES
from tradebot_sci.gui.decision_formatter import DecisionFormatter

__all__ = ["DecisionsPanel"]


class DecisionsPanel(QtWidgets.QWidget):
    """Recent decisions panel with formatted display.

    This widget owns a ``QPlainTextEdit`` used to display the latest
    decision events.  It accepts references to the shared UI state and
    settings so that it can read new decisions and apply the proper
    theme to its syntax highlighter.
    """

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(parent)
        self._state = state
        self._settings = settings
        # Text area for decisions
        self._widget = QtWidgets.QPlainTextEdit()
        self._widget.setReadOnly(True)
        self._widget.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        # Apply syntax highlighting using LogHighlighter from log_panel
        from tradebot_sci.gui.log_panel import LogHighlighter
        theme = THEMES.get(settings.theme_key, THEMES["dark"])
        self._highlighter = LogHighlighter(self._widget.document(), theme)
        # Layout to contain the text widget
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._widget)

    @property
    def widget(self) -> QtWidgets.QPlainTextEdit:
        """Return the underlying text edit used for decision display."""
        return self._widget

    @property
    def highlighter(self) -> Any:
        """Return the syntax highlighter used for decision coloring."""
        return self._highlighter

    def update_decisions(self) -> None:
        """Update the panel with the latest decision events.

        If there are no decision events yet, a waiting message is shown.
        Otherwise, the most recent events (up to 15) are parsed and
        formatted using :class:`DecisionFormatter` and displayed in the
        text area.
        """
        if not self._state.decision_events:
            self._widget.setPlainText("(waiting for first decision...)")
            return

        self._widget.clear()
        # Show last 15 decisions for readability
        num_to_display = 15
        recent = list(self._state.decision_events)[-num_to_display:]

        for dec in recent:
            try:
                # Parse decision event into dict
                decision_dict = self._parse_decision_event(dec)

                # Format using DecisionFormatter
                formatted = DecisionFormatter.format_decision(decision_dict)

                # Display with timestamp and symbol
                self._widget.appendPlainText(f"[{dec.ts}] {dec.symbol} ({dec.tf})")
                # Use <pre> to preserve whitespace when inserting HTML
                self._widget.appendHtml(
                    f"<pre style='font-family: monospace; margin-top: 0;'>{formatted}</pre>"
                )
                self._widget.appendPlainText("-" * 60 + "\n")
            except Exception as e:
                logging.error(f"Failed to format decision: {e}")
                self._widget.appendPlainText(f"[{dec.ts}] {dec.symbol} - Error formatting: {e}\n")
                self._widget.appendPlainText(f"Raw: {dec.rest}\n")
                self._widget.appendPlainText("-" * 60 + "\n")

    def _parse_decision_event(self, dec: Any) -> dict[str, Any]:
        """Convert a DecisionEvent to a dictionary for formatter consumption.

        The incoming event's ``rest`` field is a string containing key=value
        pairs and possibly JSON-encoded gate or code lists.  This method
        extracts those fields into a structured dictionary.  It also
        attempts to infer bias, phase and action when they are not
        explicitly provided.

        :param dec: The DecisionEvent instance to parse.
        :returns: A dictionary with keys expected by DecisionFormatter.
        """
        data: dict[str, Any] = {
            "symbol": dec.symbol,
            "timeframe": dec.tf,
            "raw_rest": dec.rest,
        }

        # Split dec.rest string (format: "bias=long phase=trend action=enter_long ...")
        parts = re.split(r"\s+(?=[a-zA-Z_]+=)", dec.rest)
        gates_str = ""
        codes_str = ""
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                if key == "gates":
                    gates_str = value
                elif key == "codes":
                    codes_str = value
                else:
                    data[key.strip()] = value.strip()
            else:
                if "reason" not in data:
                    data["reason"] = part.strip()

        # Parse gates string into a dictionary if available
        if gates_str:
            try:
                gates_dict = json.loads(gates_str.replace("'", '"'))
                data["gates"] = {k: v for k, v in gates_dict.items() if isinstance(k, str)}
            except json.JSONDecodeError:
                gate_dict: dict[str, bool] = {}
                for gate_match in re.finditer(r"([a-zA-Z_]+)=(True|False)", gates_str):
                    gate_dict[gate_match.group(1)] = gate_match.group(2) == "True"
                data["gates"] = gate_dict
        else:
            data["gates"] = {}

        # Parse decision reason codes
        if codes_str:
            try:
                codes_list = json.loads(codes_str.replace("'", '"'))
                data["decision_reason_codes"] = [c for c in codes_list if isinstance(c, str)]
            except json.JSONDecodeError:
                code_matches = re.findall(r"'([A-Z_]+)'", codes_str)
                data["decision_reason_codes"] = code_matches
        else:
            data["decision_reason_codes"] = []

        # Extract bias, phase, action from the rest string if not present
        if "bias" not in data:
            raw = data.get("raw_rest", "")
            if "long" in raw:
                data["bias"] = "long"
            elif "short" in raw:
                data["bias"] = "short"
            else:
                data["bias"] = "neutral"

        if "phase" not in data:
            raw = data.get("raw_rest", "")
            if "trend" in raw:
                data["phase"] = "trend"
            elif "correction" in raw:
                data["phase"] = "correction"
            elif "continuation" in raw:
                data["phase"] = "continuation"
            elif "chop" in raw:
                data["phase"] = "chop"
            else:
                data["phase"] = "unknown"

        if "action" not in data:
            raw = data.get("raw_rest", "")
            if "enter_long" in raw:
                data["action"] = "enter_long"
            elif "enter_short" in raw:
                data["action"] = "enter_short"
            elif "stand_aside" in raw:
                data["action"] = "stand_aside"
            elif "close_position" in raw:
                data["action"] = "close_position"
            elif "scale_in" in raw:
                data["action"] = "scale_in"
            elif "scale_out" in raw:
                data["action"] = "scale_out"
            elif "flip_to_long" in raw:
                data["action"] = "flip_to_long"
            elif "flip_to_short" in raw:
                data["action"] = "flip_to_short"
            elif "hold" in raw:
                data["action"] = "hold"
            else:
                data["action"] = "unknown"

        return data

    def set_theme(self, theme: Any) -> None:
        """Update the syntax highlighter with a new theme."""
        self._highlighter.set_theme(theme)