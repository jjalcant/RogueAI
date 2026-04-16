"""Sidebar navigation for the RogueAI Qt shell."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout


class Sidebar(QFrame):
    navigate_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarPanel")
        self._buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        for key, label in (
            ("command_center", "Command Center"),
            ("chat", "Chat"),
            ("explain", "Explain Mode"),
            ("friction", "Friction Radar"),
            ("agent", "Agent"),
            ("help", "Help"),
            ("settings", "Settings"),
        ):
            button = QPushButton(label, self)
            button.setObjectName("sidebarButton")
            button.clicked.connect(lambda _checked=False, current=key: self.navigate_requested.emit(current))
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addStretch(1)
        self.set_active("command_center")

    def set_active(self, view_name):
        for key, button in self._buttons.items():
            active = key == view_name
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)
