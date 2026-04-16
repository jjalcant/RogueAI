"""Agent monitoring and control page for the RogueAI Qt shell."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)


class AgentView(QFrame):
    start_requested = Signal()
    stop_requested = Signal()
    cycle_requested = Signal()
    mode_changed = Signal(str)

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

        section = QLabel("Agent", header)
        section.setObjectName("sectionLabel")
        title = QLabel("Loop state and execution controls", header)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "The autonomous loop stays backend-compatible while Qt keeps the layout readable during resize.",
            header,
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        header_layout.addWidget(section)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        controls = QFrame(self)
        controls.setObjectName("cardPanel")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 16, 16, 16)
        controls_layout.setSpacing(12)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("Start Agent", controls)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button = QPushButton("Stop Agent", controls)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.run_cycle_button = QPushButton("Run One Cycle", controls)
        self.run_cycle_button.setObjectName("accentButton")
        self.run_cycle_button.clicked.connect(self.cycle_requested.emit)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.stop_button)
        action_row.addWidget(self.run_cycle_button)
        action_row.addStretch(1)

        self.mode_combo = QComboBox(controls)
        self.mode_combo.addItems(["Manual", "Assist", "Auto"])
        self.mode_combo.currentTextChanged.connect(self.mode_changed.emit)
        action_row.addWidget(QLabel("Mode", controls))
        action_row.addWidget(self.mode_combo)
        controls_layout.addLayout(action_row)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.metric_labels = {}
        metric_fields = [
            ("running_status", "Running status"),
            ("mode", "Current mode"),
            ("interval_seconds", "Interval (seconds)"),
            ("last_cycle_time", "Last cycle"),
            ("next_cycle_time", "Next cycle"),
            ("last_error", "Last error"),
        ]
        for index, (key, title_text) in enumerate(metric_fields):
            card = QFrame(controls)
            card.setObjectName("cardPanel")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(6)
            title = QLabel(title_text, card)
            title.setObjectName("sectionLabel")
            value = QLabel("-", card)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            metrics.addWidget(card, index // 3, index % 3)
            self.metric_labels[key] = value
        controls_layout.addLayout(metrics)
        layout.addWidget(controls)

        body = QGridLayout()
        body.setHorizontalSpacing(12)
        body.setVerticalSpacing(12)

        self.task_summary = self._build_text_group("Task summary")
        self.plan_preview = self._build_text_group("Plan preview")
        self.workflow_details = self._build_text_group("Workflow details")
        self.activity_preview = self._build_text_group("Recent activity")

        body.addWidget(self.task_summary["group"], 0, 0)
        body.addWidget(self.plan_preview["group"], 0, 1)
        body.addWidget(self.workflow_details["group"], 1, 0, 1, 2)
        body.addWidget(self.activity_preview["group"], 2, 0, 1, 2)

        layout.addLayout(body, 1)

    def _build_text_group(self, title_text):
        group = QGroupBox(title_text, self)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 16, 12, 12)
        editor = QPlainTextEdit(group)
        editor.setReadOnly(True)
        editor.setMinimumHeight(180)
        group_layout.addWidget(editor)
        return {"group": group, "editor": editor}

    def update_payload(self, payload):
        snapshot = payload.get("snapshot", {})
        self.metric_labels["running_status"].setText(snapshot.get("running_status", "Stopped"))
        self.metric_labels["mode"].setText(str(snapshot.get("mode", "manual")).title())
        self.metric_labels["interval_seconds"].setText(str(snapshot.get("interval_seconds", 60)))
        self.metric_labels["last_cycle_time"].setText(snapshot.get("last_cycle_time", "Not run yet") or "Not run yet")
        self.metric_labels["next_cycle_time"].setText(snapshot.get("next_cycle_time", "Not scheduled") or "Not scheduled")
        self.metric_labels["last_error"].setText(snapshot.get("last_error", "None") or "None")
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(str(snapshot.get("mode", "manual")).title())
        self.mode_combo.blockSignals(False)
        self.task_summary["editor"].setPlainText(payload.get("task_summary", "No task data."))
        self.plan_preview["editor"].setPlainText(payload.get("plan_text", "No plan generated yet."))
        self.workflow_details["editor"].setPlainText(payload.get("workflow_text", "No workflow details yet."))
        self.activity_preview["editor"].setPlainText(payload.get("activity_text", "No recent activity yet."))
