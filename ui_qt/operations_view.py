"""Operational overview pages for the RogueAI Qt desktop shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _SelectableTextGroup(QGroupBox):
    def __init__(self, title, *, min_height=120, parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setMinimumHeight(min_height)
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.editor)

    def set_text(self, value):
        self.editor.setPlainText(str(value or ""))


class _MetricCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("sectionLabel")
        self.value_label = QLabel("-", self)
        self.value_label.setObjectName("titleLabel")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.detail_label = QLabel("", self)
        self.detail_label.setObjectName("mutedLabel")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_payload(self, value, detail=""):
        self.value_label.setText(str(value or "-"))
        self.detail_label.setText(str(detail or ""))


class _BaseScrollPage(QFrame):
    navigate_requested = Signal(str)
    quick_command_requested = Signal(str)

    def __init__(self, section_label, title_text, subtitle_text, *, parent=None):
        super().__init__(parent)
        self.setObjectName("pagePanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QFrame(self)
        header.setObjectName("cardPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(4)

        section = QLabel(section_label, header)
        section.setObjectName("sectionLabel")
        title = QLabel(title_text, header)
        title.setObjectName("titleLabel")
        subtitle = QLabel(subtitle_text, header)
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        title_block.addWidget(section)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        title_row.addLayout(title_block, 1)

        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        title_row.addLayout(self.header_actions)
        header_layout.addLayout(title_row)
        root.addWidget(header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root.addWidget(self.scroll, 1)

        self.body = QWidget(self.scroll)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.scroll.setWidget(self.body)

    def add_nav_button(self, label, target):
        button = QPushButton(label, self)
        button.clicked.connect(lambda _checked=False, current=target: self.navigate_requested.emit(current))
        self.header_actions.addWidget(button)
        return button

    def add_quick_button(self, label, command):
        button = QPushButton(label, self)
        button.clicked.connect(lambda _checked=False, current=command: self.quick_command_requested.emit(current))
        return button


class CommandCenterView(_BaseScrollPage):
    def __init__(self, parent=None):
        super().__init__(
            "Command Center",
            "Operational overview",
            "Live desktop state, quick actions, suggestions, tasks, and recent activity stay here so Chat is no longer the only home screen.",
            parent=parent,
        )
        self.add_nav_button("Open Chat", "chat")
        self.add_nav_button("Explain Mode", "explain")
        self.add_nav_button("Friction Radar", "friction")

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.metric_cards = {
            "system_status": _MetricCard("System status", self.body),
            "backend_state": _MetricCard("Backend / model", self.body),
            "memory_tools": _MetricCard("Memory / tools", self.body),
            "last_action": _MetricCard("Last action", self.body),
        }
        for index, key in enumerate(("system_status", "backend_state", "memory_tools", "last_action")):
            metrics.addWidget(self.metric_cards[key], index // 2, index % 2)
        self.body_layout.addLayout(metrics)

        actions_card = QFrame(self.body)
        actions_card.setObjectName("cardPanel")
        actions_layout = QGridLayout(actions_card)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setHorizontalSpacing(12)
        actions_layout.setVerticalSpacing(12)

        self.quick_actions_group = QGroupBox("Quick actions", actions_card)
        quick_layout = QVBoxLayout(self.quick_actions_group)
        quick_layout.setContentsMargins(12, 16, 12, 12)
        self.quick_actions_row = QHBoxLayout()
        self.quick_actions_row.setSpacing(8)
        quick_layout.addLayout(self.quick_actions_row)
        quick_layout.addStretch(1)

        self.suggested_actions_group = _SelectableTextGroup("Suggested actions", min_height=160, parent=actions_card)
        self.suggested_actions_buttons = QWidget(actions_card)
        buttons_layout = QVBoxLayout(self.suggested_actions_buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        self.suggested_actions_row = buttons_layout
        self.suggested_actions_group.layout().insertWidget(0, self.suggested_actions_buttons)

        actions_layout.addWidget(self.quick_actions_group, 0, 0)
        actions_layout.addWidget(self.suggested_actions_group, 0, 1)
        self.body_layout.addWidget(actions_card)

        tasks_grid = QGridLayout()
        tasks_grid.setHorizontalSpacing(12)
        tasks_grid.setVerticalSpacing(12)
        self.active_tasks_group = _SelectableTextGroup("Active tasks", min_height=180, parent=self.body)
        self.recent_tasks_group = _SelectableTextGroup("Recent tasks", min_height=180, parent=self.body)
        tasks_grid.addWidget(self.active_tasks_group, 0, 0)
        tasks_grid.addWidget(self.recent_tasks_group, 0, 1)
        self.body_layout.addLayout(tasks_grid)

        self.recent_events_group = _SelectableTextGroup("Recent events", min_height=220, parent=self.body)
        self.body_layout.addWidget(self.recent_events_group)
        self.body_layout.addStretch(1)

        self._quick_buttons = []
        self._suggestion_buttons = []

    def update_payload(self, payload):
        payload = payload or {}
        for key, card in self.metric_cards.items():
            metric = payload.get("metrics", {}).get(key, {})
            card.set_payload(metric.get("value", "-"), metric.get("detail", ""))

        self._replace_button_row(self.quick_actions_row, self._quick_buttons, payload.get("quick_actions", []))
        self._replace_button_column(self.suggested_actions_row, self._suggestion_buttons, payload.get("suggested_actions", []))
        self.suggested_actions_group.set_text(payload.get("suggested_actions_text", "No suggested actions right now."))
        self.active_tasks_group.set_text(payload.get("active_tasks_text", "No active tasks."))
        self.recent_tasks_group.set_text(payload.get("recent_tasks_text", "No recent tasks yet."))
        self.recent_events_group.set_text(payload.get("recent_events_text", "No recent events yet."))

    def _replace_button_row(self, layout, existing, actions):
        self._clear_layout(layout, existing)
        for item in actions:
            button = self.add_quick_button(item.get("label", "Action"), item.get("command", ""))
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            layout.addWidget(button)
            existing.append(button)
        layout.addStretch(1)

    def _replace_button_column(self, layout, existing, actions):
        self._clear_layout(layout, existing)
        if not actions:
            return
        for item in actions:
            button = self.add_quick_button(item.get("label", "Action"), item.get("command", ""))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(button)
            existing.append(button)

    @staticmethod
    def _clear_layout(layout, existing):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        existing.clear()


class ExplainModeView(_BaseScrollPage):
    def __init__(self, parent=None):
        super().__init__(
            "Explain Mode",
            "Why Rogue did what it did",
            "Use this view to inspect the latest goal, plan, executed steps, result, warnings, and next recommendation without digging through the transcript.",
            parent=parent,
        )
        self.add_nav_button("Back to Command Center", "command_center")
        self.add_nav_button("Open Chat", "chat")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.last_goal_group = _SelectableTextGroup("Last goal", min_height=90, parent=self.body)
        self.plan_group = _SelectableTextGroup("Plan", min_height=180, parent=self.body)
        self.executed_steps_group = _SelectableTextGroup("Executed steps", min_height=220, parent=self.body)
        self.result_group = _SelectableTextGroup("Result", min_height=200, parent=self.body)
        self.warnings_group = _SelectableTextGroup("Warnings / failures", min_height=160, parent=self.body)
        self.next_group = _SelectableTextGroup("Next recommendation", min_height=120, parent=self.body)

        grid.addWidget(self.last_goal_group, 0, 0)
        grid.addWidget(self.next_group, 0, 1)
        grid.addWidget(self.plan_group, 1, 0, 1, 2)
        grid.addWidget(self.executed_steps_group, 2, 0, 1, 2)
        grid.addWidget(self.result_group, 3, 0)
        grid.addWidget(self.warnings_group, 3, 1)
        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

    def update_payload(self, payload):
        payload = payload or {}
        self.last_goal_group.set_text(payload.get("last_goal", "No goal recorded yet."))
        self.plan_group.set_text(payload.get("plan", "No plan recorded yet."))
        self.executed_steps_group.set_text(payload.get("executed_steps", "No execution steps recorded yet."))
        self.result_group.set_text(payload.get("result", "No result recorded yet."))
        self.warnings_group.set_text(payload.get("warnings_failures", "No warnings or failures recorded."))
        self.next_group.set_text(payload.get("next_recommendation", "No next recommendation recorded yet."))


class FrictionRadarView(_BaseScrollPage):
    def __init__(self, parent=None):
        super().__init__(
            "Friction Radar",
            "Improvement pressure and approvals",
            "This surface reuses the real self-improvement backend so operators can inspect clustered friction, proposals, approvals, executions, rollbacks, and experiments.",
            parent=parent,
        )
        self.add_nav_button("Back to Command Center", "command_center")
        self.add_nav_button("Explain Mode", "explain")

        self.summary_group = _SelectableTextGroup("Summary", min_height=110, parent=self.body)
        self.top_areas_group = _SelectableTextGroup("Top friction areas", min_height=160, parent=self.body)
        self.top_candidates_group = _SelectableTextGroup("Top improvement candidates", min_height=220, parent=self.body)
        self.recent_proposals_group = _SelectableTextGroup("Recent proposals", min_height=220, parent=self.body)
        self.approvals_group = _SelectableTextGroup("Approval status", min_height=180, parent=self.body)
        self.executions_group = _SelectableTextGroup("Executions / rollbacks", min_height=200, parent=self.body)
        self.confidence_group = _SelectableTextGroup("Confidence / risk", min_height=180, parent=self.body)
        self.experiments_group = _SelectableTextGroup("Experiments", min_height=180, parent=self.body)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(12)
        top_grid.setVerticalSpacing(12)
        top_grid.addWidget(self.summary_group, 0, 0, 1, 2)
        top_grid.addWidget(self.top_areas_group, 1, 0)
        top_grid.addWidget(self.confidence_group, 1, 1)
        top_grid.addWidget(self.top_candidates_group, 2, 0, 1, 2)
        top_grid.addWidget(self.recent_proposals_group, 3, 0)
        top_grid.addWidget(self.approvals_group, 3, 1)
        top_grid.addWidget(self.executions_group, 4, 0)
        top_grid.addWidget(self.experiments_group, 4, 1)
        self.body_layout.addLayout(top_grid)
        self.body_layout.addStretch(1)

    def update_payload(self, payload):
        payload = payload or {}
        self.summary_group.set_text(payload.get("summary_text", "No friction data recorded yet."))
        self.top_areas_group.set_text(payload.get("top_areas_text", "No friction areas recorded yet."))
        self.top_candidates_group.set_text(payload.get("top_candidates_text", "No improvement candidates yet."))
        self.recent_proposals_group.set_text(payload.get("recent_proposals_text", "No recent proposals yet."))
        self.approvals_group.set_text(payload.get("approvals_text", "No approval state recorded yet."))
        self.executions_group.set_text(payload.get("executions_text", "No executions or rollbacks recorded yet."))
        self.confidence_group.set_text(payload.get("confidence_text", "No confidence or risk data recorded yet."))
        self.experiments_group.set_text(payload.get("experiments_text", "No experiment summaries recorded yet."))
