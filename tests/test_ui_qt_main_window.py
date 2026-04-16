import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui_qt.main_window import RogueMainWindow


class FakeBackendController:
    def __init__(
        self,
        *,
        message_callback=None,
        status_callback=None,
        navigation_callback=None,
        state_callback=None,
        clipboard_setter=None,
    ):
        self.message_callback = message_callback
        self.status_callback = status_callback
        self.navigation_callback = navigation_callback
        self.state_callback = state_callback
        self.clipboard_setter = clipboard_setter
        self.quick_commands = []
        self.message_history = []
        self.execute_chat_calls = []
        self.run_router_calls = []

    def get_settings_payload(self):
        return {
            "theme": "Dark",
            "installed_models": ["demo-model"],
            "model": "demo-model",
            "app_name": "Rogue Local",
            "max_memory_turns": 12,
            "backend_mode": "Hybrid",
            "backend_message": "Ready",
        }

    def build_help_preview_model(self):
        return {"title": "Rogue Help", "sections": [], "notes": [], "footer": ""}

    def get_command_center_payload(self):
        return {
            "metrics": {
                "system_status": {"value": "Stopped", "detail": "Mode: Manual | Active tasks: 0"},
                "backend_state": {"value": "Hybrid", "detail": "Model: demo-model"},
                "memory_tools": {"value": "Memory enabled", "detail": "Tools loaded"},
                "last_action": {"value": "No actions yet", "detail": "No activity has been recorded yet."},
            },
            "quick_actions": [{"label": "Scan Desktop", "command": "scan desktop"}],
            "suggested_actions": [{"label": "Run Diagnostics", "command": "diagnostics"}],
            "suggested_actions_text": "1. Run Diagnostics\nReason: Backend looks unavailable",
            "active_tasks_text": "No active tasks.",
            "recent_tasks_text": "No recent tasks yet.",
            "recent_events_text": "No recent events yet.",
        }

    def get_explain_mode_payload(self):
        return {
            "last_goal": "inspect desktop",
            "plan": "1. Inspect Desktop",
            "executed_steps": "1. Inspect Desktop\nStatus: verified",
            "result": "Desktop scan complete.",
            "warnings_failures": "No warnings or failures recorded.",
            "next_recommendation": "Open Chat for a follow-up command.",
        }

    def get_friction_radar_payload(self):
        return {
            "summary_text": "Events recorded: 0",
            "top_areas_text": "No friction areas recorded yet.",
            "top_candidates_text": "No improvement candidates yet.",
            "recent_proposals_text": "No recent proposals yet.",
            "approvals_text": "No approval state recorded yet.",
            "executions_text": "No executions or rollbacks recorded yet.",
            "confidence_text": "No confidence or risk data recorded yet.",
            "experiments_text": "No experiment summaries recorded yet.",
        }

    def get_header_context(self):
        return "Hybrid | demo-model | Dark"

    def refresh_task_indicator(self):
        return 0

    def get_agent_view_payload(self):
        return {
            "snapshot": {
                "running_status": "Stopped",
                "mode": "manual",
                "interval_seconds": 60,
                "last_cycle_time": "Not run yet",
                "next_cycle_time": "Not scheduled",
                "last_error": "None",
            },
            "task_summary": "No task data.",
            "plan_text": "No plan generated yet.",
            "workflow_text": "No workflow details yet.",
            "activity_text": "No recent activity yet.",
        }

    def refresh_backend_status(self):
        return {"reachable": True, "model": "demo-model"}

    def log_action(self, _message):
        return None

    def start_agent_loop(self):
        return None

    def stop_agent_loop(self):
        return None

    def run_agent_cycle(self):
        return None

    def handle_agent_mode_change(self, _value):
        return None

    def set_theme(self, _value):
        return None

    def set_runtime_model(self, _value):
        return None

    def apply_basic_settings(self, **_kwargs):
        return None

    def execute_chat_input(self, text, confirm_callback=None, emit_user_message=True):
        self.execute_chat_calls.append((text, emit_user_message))
        return True

    def run_router_command(self, text, show_user=True):
        self.run_router_calls.append((text, show_user))
        return True


class RogueMainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patcher = patch("ui_qt.main_window.RogueBackendController", FakeBackendController)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.window = RogueMainWindow()
        self.window.poll_timer.stop()
        self.window.backend_timer.stop()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_header_status_uses_stable_running_label_instead_of_command_text(self):
        self.window._set_status("Running | scan desktop", "running")

        self.assertEqual("RUNNING", self.window.header_status.text())
        self.assertNotIn("scan desktop", self.window.header_status.text().lower())

    def test_header_uses_product_subtitle_without_framework_text(self):
        header_text = "\n".join(label.text() for label in self.window.header.findChildren(type(self.window.header_status)))

        self.assertIn("Rogue", header_text)
        self.assertIn("Local System Intelligence", header_text)
        self.assertNotIn("PySide6", header_text)

    def test_window_lands_on_command_center_by_default(self):
        self.assertIs(self.window.stack.currentWidget(), self.window.command_center_view)
        self.assertIn("command_center", self.window.sidebar._buttons)

    def test_sidebar_exposes_command_center_explain_and_friction_navigation(self):
        labels = {key: button.text() for key, button in self.window.sidebar._buttons.items()}

        self.assertEqual("Command Center", labels["command_center"])
        self.assertEqual("Explain Mode", labels["explain"])
        self.assertEqual("Friction Radar", labels["friction"])

    def test_header_status_uses_stable_done_and_error_labels(self):
        self.window._set_status("Done | Response ready", "done")
        self.assertEqual("DONE", self.window.header_status.text())

        self.window._set_status("Error | Internal processing error", "error")
        self.assertEqual("ERROR", self.window.header_status.text())

    def test_registered_chat_submission_uses_dedicated_chat_execution_path(self):
        self.window._run_registered_command("run command dir")
        self.app.processEvents()

        self.assertEqual([("run command dir", False)], self.window.backend.execute_chat_calls)

    def test_duplicate_submission_is_ignored_while_dispatch_is_in_flight(self):
        self.window._run_registered_command("help")
        self.window._run_registered_command("help")
        self.app.processEvents()

        self.assertEqual([("help", False)], self.window.backend.execute_chat_calls)

    def test_quick_command_uses_same_chat_execution_path_and_pending_flow(self):
        def fake_execute(text, confirm_callback=None, emit_user_message=True):
            self.window.backend.execute_chat_calls.append((text, emit_user_message))
            self.window.backend.message_callback(
                {
                    "sender": "Rogue",
                    "message": "Desktop Scan Complete\n\nSummary\n- Files: 10",
                    "kind": "assistant",
                    "timestamp": "12:00:01",
                }
            )
            return True

        self.window.backend.execute_chat_input = fake_execute

        self.window._run_quick_command("scan desktop")
        self.app.processEvents()
        QTest.qWait(80)
        self.app.processEvents()

        self.assertEqual([("scan desktop", False)], self.window.backend.execute_chat_calls)
        self.assertEqual([], self.window.backend.run_router_calls)
        self.assertEqual(
            [("You", "scan desktop"), ("Rogue", "Desktop Scan Complete\n\nSummary\n- Files: 10")],
            [(payload["sender"], payload["message"]) for payload in self.window.chat_view._messages],
        )

    def test_typed_submission_shows_user_message_before_backend_reply_without_duplication(self):
        def fake_execute(text, confirm_callback=None, emit_user_message=True):
            self.window.backend.execute_chat_calls.append((text, emit_user_message))
            self.window.backend.message_callback(
                {
                    "sender": "Rogue",
                    "message": "Hello from Rogue.",
                    "kind": "assistant",
                    "timestamp": "12:00:00",
                }
            )
            return True

        self.window.backend.execute_chat_input = fake_execute
        self.window.chat_view.input_edit.setPlainText("hello")

        self.window.chat_view.submit_current_text()
        self.app.processEvents()
        QTest.qWait(80)
        self.app.processEvents()

        self.assertEqual([("hello", False)], self.window.backend.execute_chat_calls)
        self.assertEqual(
            [("You", "hello"), ("Rogue", "Hello from Rogue.")],
            [(payload["sender"], payload["message"]) for payload in self.window.chat_view._messages],
        )

    def test_help_and_settings_output_text_remain_selectable(self):
        help_flags = self.window.help_view.browser.textInteractionFlags()
        settings_flags = self.window.settings_view.backend_message_value.textInteractionFlags()

        self.assertTrue(help_flags & Qt.TextSelectableByMouse)
        self.assertTrue(help_flags & Qt.TextSelectableByKeyboard)
        self.assertTrue(settings_flags & Qt.TextSelectableByMouse)
        self.assertTrue(settings_flags & Qt.TextSelectableByKeyboard)


if __name__ == "__main__":
    unittest.main()
