"""Custom detailed widgets for the Tradebot High-Fidelity GUI."""

from __future__ import annotations
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

ASSETS_DIR = Path(__file__).parent / "assets"

class GraphicalButton(QtWidgets.QPushButton):
    """Button represented entirely by an image (with hover scaling)."""
    
    def __init__(self, image_name: str, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setFlat(True)
        self.setStyleSheet("border: none; background: transparent;")
        path = ASSETS_DIR / f"{image_name}.png"
        self._pixmap = QtGui.QPixmap(str(path))
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._hover = False
        
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)
        
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if self._pixmap.isNull():
            return
            
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        
        rect = self.rect()
        if self._hover:
            # Slight zoom
            w = rect.width() * 0.95
            h = rect.height() * 0.95
            x = (rect.width() - w) / 2
            y = (rect.height() - h) / 2
            target = QtCore.QRectF(x, y, w, h)
        else:
            # Padding
            w = rect.width() * 0.8
            h = rect.height() * 0.8
            x = (rect.width() - w) / 2
            y = (rect.height() - h) / 2
            target = QtCore.QRectF(x, y, w, h)
            
        painter.drawPixmap(target.toRect(), self._pixmap)

class HudPanel(QtWidgets.QWidget):
    """Container that draws a HUD frame around its content."""
    
    def __init__(self, content: QtWidgets.QWidget, title: str = "", parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._content = content
        self._pixmap = QtGui.QPixmap(str(ASSETS_DIR / "hud_frame.png"))
        
        self._layout = QtWidgets.QVBoxLayout(self)
        # Margins to fit inside the frame graphic
        self._layout.setContentsMargins(20, 30, 20, 20)
        
        # Title
        if title:
            lbl = QtWidgets.QLabel(title)
            lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-family: 'Segoe UI'; font-size: 14px; background: transparent;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self._layout.addWidget(lbl)
            
        self._layout.addWidget(content)
        
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if self._pixmap.isNull():
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self._pixmap)

class CarouselPanel(QtWidgets.QWidget):
    """Container that swaps widgets using left/right graphical arrows."""
    
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._stack = QtWidgets.QStackedWidget()
        self._titles: list[str] = []
        
        # Arrows
        self._btn_prev = GraphicalButton("arrow_left", self)
        self._btn_prev.setFixedSize(60, 100)
        self._btn_prev.clicked.connect(self._prev)
        
        self._btn_next = GraphicalButton("arrow_right", self)
        self._btn_next.setFixedSize(60, 100)
        self._btn_next.clicked.connect(self._next)
        
        self._title_lbl = QtWidgets.QLabel("")
        self._title_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._title_lbl.setStyleSheet("color: #38bdf8; font-size: 18px; font-weight: bold; background: transparent; letter-spacing: 2px;")
        
        # Layout
        # Top: Title
        # Middle: < Content >
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        content_row = QtWidgets.QHBoxLayout()
        content_row.addWidget(self._btn_prev)
        
        # Wrap stack in HUD frame? If each panel has its own HUD, maybe not.
        # But user wants HUD for panes. The carousel IS a pane.
        # So we put the Stack inside the HUD frame, and the arrows OUTSIDE?
        # Or arrows floating on top?
        # Let's put arrows on sides of the content.
        
        # We need a container for the stack to apply sizing
        container = QtWidgets.QWidget()
        self._stack_layout = QtWidgets.QVBoxLayout(container)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)
        self._stack_layout.addWidget(self._stack)
        
        content_row.addWidget(container, 1)
        content_row.addWidget(self._btn_next)
        
        main_layout.addWidget(self._title_lbl)
        main_layout.addLayout(content_row)
        
    def add_tab(self, widget: QtWidgets.QWidget, title: str):
        self._stack.addWidget(widget)
        self._titles.append(title)
        if self._stack.count() == 1:
            self._update_title()
            
    def _prev(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
        else:
            self._stack.setCurrentIndex(self._stack.count() - 1)
        self._update_title()
            
    def _next(self):
        idx = self._stack.currentIndex()
        if idx < self._stack.count() - 1:
            self._stack.setCurrentIndex(idx + 1)
        else:
            self._stack.setCurrentIndex(0)
        self._update_title()
            
    def _update_title(self):
        idx = self._stack.currentIndex()
        if 0 <= idx < len(self._titles):
            self._title_lbl.setText(f"[ {self._titles[idx].upper()} ]")

class NeonDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate to draw glowing text for table cells."""
    
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        painter.save()
        
        # Draw background (transparent)
        # painter.fillRect(option.rect, option.palette.base()) # Skip for glass effect
        
        text = index.data(QtCore.Qt.DisplayRole)
        if text:
            # Setup neon pen
            color = option.palette.text().color()
            # If "BUY" or "SELL", override color
            txt_str = str(text).upper()
            if "BUY" in txt_str: color = QtGui.QColor("#4ade80") # green
            elif "SELL" in txt_str: color = QtGui.QColor("#f87171") # red
            elif "WAIT" in txt_str: color = QtGui.QColor("#fbbf24") # amber
            
            painter.setPen(color)
            font = option.font
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            
            # Simple glow: draw offset text with low opacity?
            # Or just draw sharp. Getting real blur is expensive.
            # Let's try drawing sharp text first.
            
            painter.drawText(option.rect, QtCore.Qt.AlignCenter, str(text))
            
        painter.restore()
