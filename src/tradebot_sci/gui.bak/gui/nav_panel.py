from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

if TYPE_CHECKING:
    from tradebot_sci.gui.app import MainWindow

class NavPanel(QtWidgets.QWidget):
    """
    Left Sidebar Navigation Panel.
    Features:
    - Top Section: Navigation Buttons (Dashboard, Settings)
    - Bottom Section: Panic Button ("STOP ALL TRADES")
    """

    def __init__(self, parent: MainWindow) -> None:
        super().__init__(parent)
        self._main_window = parent
        self.init_ui()

    def init_ui(self) -> None:
        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(15)

        # --- Top Section: Navigation ---
        
        # Dashboard Button (Active View)
        self.btn_dashboard = QtWidgets.QPushButton("Dashboard")
        self.btn_dashboard.setCheckable(True)
        self.btn_dashboard.setChecked(True)  # Default active
        self.btn_dashboard.setMinimumHeight(50)
        self.btn_dashboard.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_dashboard.clicked.connect(self._on_dashboard_clicked)
        layout.addWidget(self.btn_dashboard)

        # Settings Button
        self.btn_settings = QtWidgets.QPushButton("Settings")
        self.btn_settings.setMinimumHeight(40)
        self.btn_settings.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self._main_window.open_settings)
        layout.addWidget(self.btn_settings)

        # Spacer to push everything else down
        layout.addStretch()

        # --- Bottom Section: Danger Zone ---
        
        # Panic Button
        # Panic Button
        from tradebot_sci.gui.custom_widgets import GraphicalButton
        self.btn_panic = GraphicalButton("panic_button", self)
        self.btn_panic.setFixedSize(128, 128)  # Adjust based on image aspect
        self.btn_panic.clicked.connect(self._on_panic_clicked)
        
        # Center the panic button and add Top margin to push it into the bottom square
        panic_container = QtWidgets.QWidget()
        panic_layout = QtWidgets.QHBoxLayout(panic_container)
        panic_layout.setContentsMargins(0, 40, 0, 0) # Top padding
        panic_layout.addWidget(self.btn_panic)
        layout.addWidget(panic_container)
    
    def _on_dashboard_clicked(self) -> None:
        # Ensure it stays checked if it's the only view for now
        self.btn_dashboard.setChecked(True)

    def _on_panic_clicked(self) -> None:
        # Confirm before panicking
        reply = QtWidgets.QMessageBox.question(
            self,
            "STOP ALL TRADES",
            "EMERGENCY PROTOCOL:\n\nThis will instantly STOP the bot and attempt to CLOSE ALL POSITIONS.\n\nAre you sure?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self._main_window.trigger_panic_mode()
