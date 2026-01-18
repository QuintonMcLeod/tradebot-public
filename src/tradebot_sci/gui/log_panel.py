"""Log panel for displaying tradebot output.

This module provides a dedicated panel for rendering the live log output from
the trading bot.  It encapsulates the QTextEdit used to display log lines
along with the syntax highlighter that colors key log tokens.  By moving
this logic into its own module, the main GUI class remains focused on
orchestration and layout rather than widget configuration.

Usage example::

    from tradebot_sci.gui.log_panel import LogPanel

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            # Assume `settings` is available from the configuration loader
            self._log_panel = LogPanel(self, settings.log_file, settings)
            # Add the panel to your layout
            layout.addWidget(self._log_panel)
            # Access the underlying text widget via .widget if needed
            self._log_panel.widget.appendPlainText("hello")

"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

from tradebot_sci.gui.shared import THEMES, Theme

__all__ = ["LogPanel", "LogHighlighter", "choose_log_file"]


class LogHighlighter(QtGui.QSyntaxHighlighter):
    """Syntax highlighter for tradebot log output.

    Applies color formatting to log levels, timestamps, and key trading events
    based on the provided theme.
    """

    def __init__(self, doc: QtGui.QTextDocument, theme: Theme) -> None:
        super().__init__(doc)
        self._theme = theme
        self._rules: list[tuple[re.Pattern[str], QtGui.QTextCharFormat]] = []
        self._fullline_patterns: list[tuple[re.Pattern[str], QtGui.QTextCharFormat]] = []
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._rules = []
        self._fullline_patterns = []

        def fmt(color: str, bold: bool = False) -> QtGui.QTextCharFormat:
            f = QtGui.QTextCharFormat()
            f.setForeground(QtGui.QColor(color))
            if bold:
                f.setFontWeight(QtGui.QFont.Bold)
            return f

        # Full-line colors for errors, warnings, A+ lines
        full_green = fmt(theme.good)
        full_red = fmt(theme.bad)
        full_orange = fmt(theme.warn)

        # Tag colors - varied colors for different tags
        tag_holdings = fmt("#9b59b6", True)  # Purple
        tag_structure = fmt("#3498db", True)  # Blue
        tag_select = fmt("#2ecc71", True)  # Green
        tag_decision = fmt("#e74c3c", True)  # Red
        tag_exec = fmt("#f39c12", True)  # Orange
        tag_httpx = fmt("#9b59b6", True)  # Purple
        tag_coinbase = fmt("#3498db", True)  # Blue
        tag_ccxt = fmt("#2980b9", True)  # Deep Blue
        tag_other = fmt(theme.accent, True)  # Accent color
        good_partial = fmt(theme.good, True)
        warn_partial = fmt(theme.warn, True)

        # Full-line patterns (checked first)
        self._fullline_patterns.append((re.compile(r"A\+|A_PLUS"), full_green))  # A+ lines
        self._fullline_patterns.append((re.compile(r"\[ERROR\]|\[CRITICAL\]|ERROR:|Exception:|Traceback"), full_red))  # Error lines
        self._fullline_patterns.append((re.compile(r"\[WARN\]|\[WARNING\]"), full_orange))  # Warning lines

        # Partial patterns (for specific text within line)
        self._rules.append((re.compile(r"\[HOLDINGS\]"), tag_holdings))
        self._rules.append((re.compile(r"\[STRUCTURE\]"), tag_structure))
        self._rules.append((re.compile(r"\[SELECT\]"), tag_select))
        self._rules.append((re.compile(r"\[DECISION\]"), tag_decision))
        self._rules.append((re.compile(r"\[DECISION\]"), tag_decision))
        self._rules.append((re.compile(r"\[EXEC\]"), tag_exec))
        self._rules.append((re.compile(r"\[HTTPX\]"), tag_httpx))
        self._rules.append((re.compile(r"\[COINBASE\]"), tag_coinbase))
        self._rules.append((re.compile(r"\[CCXT\]"), tag_ccxt))
        self._rules.append((re.compile(r"\[(INFO|DEBUG|GATE|SWEEP|CONT)\]"), tag_other))
        self._rules.append((re.compile(r"\b(ENTER_LONG|BUY|LONG)\b"), good_partial))
        self._rules.append((re.compile(r"\b(STAND_ASIDE|NO_TRADE|BLOCK)\b"), warn_partial))
        self._rules.append((re.compile(r"\b(RESTART|EXECUTE_TRADES=true)\b"), warn_partial))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        # Check for full-line patterns first
        for rx, f in self._fullline_patterns:
            if rx.search(text):
                self.setFormat(0, len(text), f)
                return  # Don't apply other formatting

        # Apply partial patterns
        for rx, f in self._rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)


class LogPanel(QtWidgets.QWidget):
    """Panel for displaying log output from the trading bot.

    This widget wraps a ``QPlainTextEdit`` and applies syntax highlighting
    appropriate for tradebot logs.  It accepts the current theme at
    construction time via the provided settings object.  The panel exposes
    convenience methods for appending log lines and updating the theme.
    """

    def __init__(self, parent: QtWidgets.QWidget, log_file: Path, settings: Any) -> None:
        super().__init__(parent)
        self._settings = settings
        # Text area for log output
        self._widget = QtWidgets.QTextEdit()
        self._widget.setObjectName("logView")
        self._widget.setReadOnly(True)
        self._widget.setAcceptRichText(False)
        self._widget.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self._widget.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        # Limit the number of blocks to avoid unbounded growth
        self._widget.document().setMaximumBlockCount(2500)
        # Apply syntax highlighting
        theme = THEMES.get(settings.theme_key, THEMES["dark"])
        self._highlighter = LogHighlighter(self._widget.document(), theme)
        # Layout to house the text widget.  Use zero margins to align with
        # surrounding layouts in the main window.
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._widget)

    @property
    def widget(self) -> QtWidgets.QTextEdit:
        """Return the underlying text edit widget used for log display."""
        return self._widget

    @property
    def highlighter(self) -> Any:
        """Return the syntax highlighter used for log coloring."""
        return self._highlighter

    def clean_log_line(self, line: str) -> str:
        """Clean a log line by hiding date/time and module name.

        Removes:
        - Date/time prefix: "2025-12-26 00:42:36"
        - Module name: "tradebot_sci.runtime.loop"
        - Heartbeat holdings lines (noise)

        Returns the cleaned line ready for display, or None if line should be hidden.
        """
        # Hide heartbeat holdings spam - only show holdings when positions change
        if '[HOLDINGS]' in line and '"reason":"heartbeat"' in line:
            return None  # type: ignore[return-value]

        # Remove date/time prefix (YYYY-MM-DD HH:MM:SS)
        line = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*", "", line)

        # Fix httpx logs
        line = re.sub(r"httpx\s+-\s+", "- [HTTPX] ", line)

        # Remove module name "tradebot_sci.runtime.loop" and similar
        line = re.sub(r"tradebot_sci\.\w+\.\w+\s*", "", line)

        return line.strip()

    def append_line(self, line: str) -> None:
        """Append a single line of text to the log display after cleaning."""
        cleaned = self.clean_log_line(line)
        if cleaned is not None:
            self._append_wrapped_line(cleaned)

    def _append_wrapped_line(self, text: str) -> None:
        # Check if user is scrolling (not at bottom)
        vbar = self._widget.verticalScrollBar()
        at_bottom = vbar.value() >= (vbar.maximum() - 20)  # 20px tolerance

        indent_px = self._wrap_indent_pixels(text)
        block_format = QtGui.QTextBlockFormat()
        if indent_px > 0:
            block_format.setLeftMargin(indent_px)
            block_format.setTextIndent(-indent_px)

        cursor = self._widget.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if not self._widget.document().isEmpty():
            cursor.insertBlock(block_format)
        else:
            cursor.setBlockFormat(block_format)
        cursor.insertText(text)
        
        # Only scroll to bottom if we were already there
        if at_bottom:
            self._widget.setTextCursor(cursor)
            self._widget.ensureCursorVisible()

    def _wrap_indent_pixels(self, text: str) -> int:
        sep = " - "
        idx = text.find(sep)
        if idx < 0:
            return 0
        indent_cols = idx + len(sep)
        metrics = self._widget.fontMetrics()
        return metrics.horizontalAdvance(" ") * indent_cols

    def set_text(self, text: str) -> None:
        """Replace the entire contents of the log display with ``text``."""
        self._widget.setPlainText(text)

    def set_theme(self, theme: Any) -> None:
        """Update the syntax highlighter to use the provided theme."""
        self._highlighter.set_theme(theme)


def choose_log_file(parent: QtWidgets.QWidget, settings: Any) -> Path | None:
    """Open a file picker to select a new log file for display.

    :param parent: The parent widget used as the modality for the dialog.
    :param settings: The settings object containing the current log path.
    :returns: The selected path as a ``Path`` instance, or ``None`` if
        the user cancels the dialog.
    """
    path, _ = QtWidgets.QFileDialog.getOpenFileName(
        parent,
        "Select tradebot.log",
        str(settings.log_file),
        "Log files (*.log*);;All files (*)",
    )
    return Path(path) if path else None
