"""Settings page for the RogueAI Qt shell."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class SettingsView(QFrame):
    theme_changed = Signal(str)
    model_changed = Signal(str)
    save_requested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pagePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QFrame(self)
        header.setObjectName("cardPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(6)
        section = QLabel("Settings", header)
        section.setObjectName("sectionLabel")
        title = QLabel("Appearance and runtime defaults", header)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Theme changes persist. Model selection updates the active runtime model without replacing the existing backend flow.",
            header,
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        header_layout.addWidget(section)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        form_card = QFrame(self)
        form_card.setObjectName("cardPanel")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(18, 18, 18, 18)
        form_layout.setSpacing(14)

        self.theme_combo = QComboBox(form_card)
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.currentTextChanged.connect(self.theme_changed.emit)

        self.model_combo = QComboBox(form_card)
        self.model_combo.currentTextChanged.connect(self.model_changed.emit)

        self.app_name_edit = QLineEdit(form_card)
        self.max_memory_spin = QSpinBox(form_card)
        self.max_memory_spin.setMinimum(1)
        self.max_memory_spin.setMaximum(200)

        self.backend_mode_value = QLabel("-", form_card)
        self.backend_mode_value.setObjectName("mutedLabel")
        self.backend_mode_value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.backend_message_value = QLabel("-", form_card)
        self.backend_message_value.setObjectName("mutedLabel")
        self.backend_message_value.setWordWrap(True)
        self.backend_message_value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        form_layout.addRow("Theme", self.theme_combo)
        form_layout.addRow("Model", self.model_combo)
        form_layout.addRow("App name", self.app_name_edit)
        form_layout.addRow("Max memory turns", self.max_memory_spin)
        form_layout.addRow("Backend mode", self.backend_mode_value)
        form_layout.addRow("Backend details", self.backend_message_value)
        layout.addWidget(form_card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_button = QPushButton("Save settings", self)
        save_button.setObjectName("accentButton")
        save_button.clicked.connect(self._emit_save_requested)
        actions.addWidget(save_button)
        layout.addLayout(actions)
        layout.addStretch(1)

    def set_payload(self, payload):
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(payload.get("theme", "Dark"))
        self.theme_combo.blockSignals(False)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(payload.get("installed_models", []))
        current_model = payload.get("model", "")
        if current_model:
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)

        self.app_name_edit.setText(payload.get("app_name", "Rogue Local"))
        self.max_memory_spin.setValue(int(payload.get("max_memory_turns", 12)))
        self.backend_mode_value.setText(payload.get("backend_mode", "-"))
        self.backend_message_value.setText(payload.get("backend_message", ""))

    def _emit_save_requested(self):
        self.save_requested.emit(self.app_name_edit.text(), int(self.max_memory_spin.value()))
