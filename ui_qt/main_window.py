"""PySide6 desktop shell for RogueAI."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .agent_view import AgentView
from .backend import RogueBackendController
from .chat_view import ChatView
from .help_view import HelpView
from .operations_view import CommandCenterView, ExplainModeView, FrictionRadarView
from .settings_view import SettingsView
from .sidebar import Sidebar
from .theme import build_stylesheet


class UiEventBridge(QObject):
    message_received = Signal(object)
    navigation_requested = Signal(str)
    status_updated = Signal(str, str)
    state_refresh_requested = Signal()


class RogueMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rogue")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        self.bridge = UiEventBridge(self)
        self.bridge.message_received.connect(self._append_message)
        self.bridge.navigation_requested.connect(self.show_view)
        self.bridge.status_updated.connect(self._set_status)
        self.bridge.state_refresh_requested.connect(self.refresh_panels)

        self.backend = RogueBackendController(
            message_callback=self.bridge.message_received.emit,
            status_callback=self.bridge.status_updated.emit,
            navigation_callback=self.bridge.navigation_requested.emit,
            state_callback=self.bridge.state_refresh_requested.emit,
            clipboard_setter=self._set_clipboard_text,
        )
        self._command_dispatch_in_flight = False

        self._build_shell()
        self.apply_theme(self.backend.get_settings_payload().get("theme", "Dark"))
        self.help_view.set_model(self.backend.build_help_preview_model())
        self.chat_view.replace_messages(self.backend.message_history)
        self.refresh_panels()
        self.show_view("command_center")

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_panels)
        self.poll_timer.start(1500)

        self.backend_timer = QTimer(self)
        self.backend_timer.timeout.connect(self._refresh_backend_status)
        self.backend_timer.start(20000)

    def _build_shell(self):
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        self.header = QFrame(self)
        self.header.setObjectName("headerPanel")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(16)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Rogue", self.header)
        title.setObjectName("titleLabel")
        subtitle = QLabel("Local System Intelligence", self.header)
        subtitle.setObjectName("mutedLabel")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header_layout.addLayout(title_block, 1)

        status_block = QVBoxLayout()
        status_block.setSpacing(2)
        self.header_context = QLabel("-", self.header)
        self.header_context.setObjectName("mutedLabel")
        self.header_status = QLabel("Ready", self.header)
        self.header_status.setObjectName("sectionLabel")
        status_block.addWidget(self.header_context)
        status_block.addWidget(self.header_status)
        header_layout.addLayout(status_block)

        self.active_tasks_label = QLabel("Active tasks: 0", self.header)
        self.active_tasks_label.setObjectName("mutedLabel")
        header_layout.addWidget(self.active_tasks_label)
        root_layout.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(14)
        root_layout.addLayout(body, 1)

        self.sidebar = Sidebar(self)
        self.sidebar.navigate_requested.connect(self.show_view)
        self.sidebar.setFixedWidth(220)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget(self)
        body.addWidget(self.stack, 1)

        self.chat_view = ChatView(self.backend.quick_commands, parent=self)
        self.chat_view.command_submitted.connect(self._run_registered_command)
        self.chat_view.quick_command_requested.connect(self._run_quick_command)

        self.command_center_view = CommandCenterView(self)
        self.command_center_view.navigate_requested.connect(self.show_view)
        self.command_center_view.quick_command_requested.connect(self._run_quick_command)

        self.explain_view = ExplainModeView(self)
        self.explain_view.navigate_requested.connect(self.show_view)

        self.friction_view = FrictionRadarView(self)
        self.friction_view.navigate_requested.connect(self.show_view)

        self.agent_view = AgentView(self)
        self.agent_view.start_requested.connect(self.backend.start_agent_loop)
        self.agent_view.stop_requested.connect(self.backend.stop_agent_loop)
        self.agent_view.cycle_requested.connect(self.backend.run_agent_cycle)
        self.agent_view.mode_changed.connect(self._change_agent_mode)

        self.help_view = HelpView(self)

        self.settings_view = SettingsView(self)
        self.settings_view.theme_changed.connect(self._change_theme)
        self.settings_view.model_changed.connect(self._change_model)
        self.settings_view.save_requested.connect(self._save_settings)

        self._view_map = {
            "command_center": self.command_center_view,
            "chat": self.chat_view,
            "explain": self.explain_view,
            "friction": self.friction_view,
            "agent": self.agent_view,
            "help": self.help_view,
            "settings": self.settings_view,
        }
        for widget in self._view_map.values():
            self.stack.addWidget(widget)

    def _set_clipboard_text(self, text):
        QApplication.clipboard().setText(text)

    @Slot(object)
    def _append_message(self, payload):
        self.chat_view.append_message(payload)

    @Slot(str, str)
    def _set_status(self, message, level):
        self.header_status.setText(self._normalize_header_status(message, level))

    @staticmethod
    def _normalize_header_status(message, level):
        normalized_level = str(level or "").strip().lower()
        if normalized_level in {"ready", "info"}:
            return "READY"
        if normalized_level == "running":
            return "RUNNING"
        if normalized_level == "done":
            return "DONE"
        if normalized_level == "warning":
            return "WARNING"
        if normalized_level == "error":
            return "ERROR"

        prefix = str(message or "").split("|", 1)[0].strip().lower()
        if prefix in {"ready", "running", "done", "warning", "error"}:
            return prefix.upper()
        return "READY"

    def _refresh_backend_status(self):
        self.backend.refresh_backend_status()
        self.refresh_panels()

    def refresh_panels(self):
        settings_payload = self.backend.get_settings_payload()
        self.header_context.setText(self.backend.get_header_context())
        self.active_tasks_label.setText(f"Active tasks: {self.backend.refresh_task_indicator()}")
        self.command_center_view.update_payload(self.backend.get_command_center_payload())
        self.explain_view.update_payload(self.backend.get_explain_mode_payload())
        self.friction_view.update_payload(self.backend.get_friction_radar_payload())
        self.agent_view.update_payload(self.backend.get_agent_view_payload())
        self.settings_view.set_payload(settings_payload)
        self.help_view.set_model(self.backend.build_help_preview_model())
        self.apply_theme(settings_payload.get("theme", "Dark"))

    def apply_theme(self, theme_name):
        QApplication.instance().setStyleSheet(build_stylesheet(theme_name))
        self.chat_view.set_theme(theme_name)

    @Slot(str)
    def show_view(self, view_name):
        widget = self._view_map.get(view_name, self.chat_view)
        self.stack.setCurrentWidget(widget)
        self.sidebar.set_active(view_name if view_name in self._view_map else "chat")
        if widget is self.chat_view:
            self.chat_view.focus_input()

    def _confirm_command(self, title, message):
        return QMessageBox.question(self, title, message) == QMessageBox.Yes

    @Slot(str)
    def _run_registered_command(self, text):
        if self._command_dispatch_in_flight:
            self.backend.log_action(f"Ignored duplicate chat submission: {text}")
            return
        self._command_dispatch_in_flight = True
        QTimer.singleShot(0, lambda current=text: self._execute_registered_command(current))

    def _execute_registered_command(self, text):
        try:
            result = self.backend.execute_chat_input(
                text,
                confirm_callback=self._confirm_command,
                emit_user_message=False,
            )
            self.chat_view.finish_response_feedback(awaiting_async=result == "__ASYNC__")
            self.refresh_panels()
        finally:
            self._command_dispatch_in_flight = False

    @Slot(str)
    def _run_quick_command(self, text):
        if self._command_dispatch_in_flight:
            self.backend.log_action(f"Ignored duplicate quick command: {text}")
            return
        if not self.chat_view.submit_external_command(text, emit_signal=False):
            return
        self._command_dispatch_in_flight = True
        QTimer.singleShot(0, lambda current=text: self._execute_quick_command(current))

    def _execute_quick_command(self, text):
        try:
            result = self.backend.execute_chat_input(
                text,
                confirm_callback=self._confirm_command,
                emit_user_message=False,
            )
            self.chat_view.finish_response_feedback(awaiting_async=result == "__ASYNC__")
            self.refresh_panels()
        finally:
            self._command_dispatch_in_flight = False

    @Slot(str)
    def _change_agent_mode(self, value):
        self.backend.handle_agent_mode_change(value)
        self.refresh_panels()

    @Slot(str)
    def _change_theme(self, value):
        self.backend.set_theme(value)
        self.refresh_panels()

    @Slot(str)
    def _change_model(self, value):
        if value:
            self.backend.set_runtime_model(value)
            self.refresh_panels()

    @Slot(str, int)
    def _save_settings(self, app_name, max_memory_turns):
        self.backend.apply_basic_settings(app_name=app_name, max_memory_turns=max_memory_turns)
        self.refresh_panels()


def launch_qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    window = RogueMainWindow()
    window.show()
    return app.exec()
