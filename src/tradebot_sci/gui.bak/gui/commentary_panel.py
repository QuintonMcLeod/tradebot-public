"""AI commentary panel for the Tradebot GUI.

This module provides a thin wrapper around a ``QTextBrowser`` used to
display AI commentary within the dashboard.  Extracting the widget
creation into its own module helps keep the main window focused on
orchestration while allowing the commentary area to be themed and
managed independently.  The logic for generating and updating
commentary remains in the main window since it depends on a variety
of timers, environment variables and internal state.

Usage example::

    from tradebot_sci.gui.commentary_panel import CommentaryPanel

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self._commentary_panel = CommentaryPanel(self, state, settings)
            layout.addWidget(self._commentary_panel)

            # Access the underlying text widget via ``widget`` to set
            # commentary content from elsewhere in the application.
            self._commentary = self._commentary_panel.widget

"""

from __future__ import annotations

from typing import Any
from PySide6 import QtWidgets, QtCore  # type: ignore

__all__ = ["CommentaryPanel"]


class CommentaryPanel(QtWidgets.QWidget):
    """Widget encapsulating a markdown-rendered area for AI commentary."""

    def __init__(self, parent: QtWidgets.QWidget, state: Any, settings: Any) -> None:
        super().__init__(parent)
        # Create the text widget.  The main window will update this
        # directly via the ``widget`` property.
        self._text = QtWidgets.QTextBrowser(self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self._text.setOpenExternalLinks(True)
        self._text.setMarkdown("AI COMMENTARY\n\n(waiting...)")

        # Use a simple layout with zero margins so the text widget fills
        # the available space.  Additional controls (e.g. copy buttons)
        # could be added here later if desired.
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text)

    @property
    def widget(self) -> QtWidgets.QTextBrowser:
        """Return the underlying text widget for direct access."""
        return self._text
