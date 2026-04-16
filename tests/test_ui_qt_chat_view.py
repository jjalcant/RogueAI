import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from ui_qt.chat_view import ChatView


class ChatViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = ChatView()
        self.view.show()
        self.app.processEvents()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def test_submit_current_text_inserts_pending_feedback_immediately(self):
        submitted = []
        self.view.command_submitted.connect(submitted.append)
        self.view.input_edit.setPlainText("scan desktop")

        self.view.submit_current_text()

        self.assertEqual(["scan desktop"], submitted)
        self.assertEqual("", self.view.input_edit.toPlainText())
        self.assertEqual("user", self.view._messages[0]["kind"])
        self.assertEqual("scan desktop", self.view._messages[0]["message"])
        self.assertEqual("pending", self.view._messages[-1]["kind"])
        self.assertEqual("Analyzing desktop...", self.view._messages[-1]["message"])

    def test_intro_copy_uses_chat_wording_without_operator_console_label(self):
        label_text = [label.text() for label in self.view.findChildren(QLabel)]

        self.assertIn("Chat", label_text)
        self.assertIn("Run Rogue commands and review verified system responses.", label_text)
        self.assertNotIn("Operator console", label_text)

    def test_submit_current_text_ignores_blank_and_placeholder_only_content(self):
        submitted = []
        self.view.command_submitted.connect(submitted.append)

        self.view.input_edit.setPlainText("   \n  ")
        self.assertFalse(self.view.submit_current_text())

        self.view.input_edit.setPlainText(self.view.input_edit.placeholderText())
        self.assertFalse(self.view.submit_current_text())

        self.assertEqual([], submitted)
        self.assertEqual([], self.view._messages)

    def test_append_message_replaces_pending_feedback_with_progressive_verified_text(self):
        final_text = "System status\n- CPU: OK\n- RAM: OK\n- Disk: OK"
        self.view.append_message(
            {
                "sender": "You",
                "message": "status",
                "kind": "user",
                "timestamp": "11:59:59",
            }
        )
        first_widget = self.view._message_widgets[0]
        self.view.begin_response_feedback("system status")

        self.view.append_message(
            {
                "sender": "Rogue",
                "message": final_text,
                "kind": "assistant",
                "timestamp": "12:00:00",
            }
        )

        self.assertEqual(2, len(self.view._messages))
        self.assertEqual(first_widget, self.view._message_widgets[0])
        self.assertEqual("status", self.view._message_widgets[0].content.toPlainText())
        self.assertEqual("", self.view._message_widgets[-1].content.toPlainText())

        QTest.qWait(50)
        self.app.processEvents()
        partial = self.view._message_widgets[-1].content.toPlainText()
        self.assertTrue(partial)
        self.assertNotEqual(final_text, partial)
        self.assertTrue(final_text.startswith(partial))

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and self.view._active_typing_animation is not None:
            QTest.qWait(20)
            self.app.processEvents()

        self.assertIsNone(self.view._active_typing_animation)
        self.assertEqual(final_text, self.view._message_widgets[-1].content.toPlainText())
        self.assertNotIn("Checking system status...", self.view._message_widgets[-1].content.toPlainText())
        self.assertEqual("status", self.view._message_widgets[0].content.toPlainText())

    def test_finish_response_feedback_removes_stale_pending_placeholder(self):
        self.view.begin_response_feedback("help")

        self.view.finish_response_feedback()

        self.assertEqual([], self.view._messages)

    def test_large_outputs_animate_intro_then_commit_full_text_quickly(self):
        final_text = "\n".join(f"line {index:02d} | detail block for validation" for index in range(40))
        self.view.begin_response_feedback("generate report")

        self.view.append_message(
            {
                "sender": "Rogue",
                "message": final_text,
                "kind": "assistant",
                "timestamp": "12:01:00",
            }
        )

        QTest.qWait(250)
        self.app.processEvents()

        self.assertIsNone(self.view._active_typing_animation)
        self.assertEqual(final_text, self.view._message_widgets[-1].content.toPlainText())

    def test_animation_does_not_force_scroll_when_user_is_reading_older_messages(self):
        self.view.resize(900, 420)
        for index in range(18):
            self.view.append_message(
                {
                    "sender": "Rogue",
                    "message": f"earlier message {index}\n" * 3,
                    "kind": "assistant",
                    "timestamp": "12:02:00",
                }
            )
        QTest.qWait(50)
        self.app.processEvents()

        scrollbar = self.view.transcript_scroll.verticalScrollBar()
        scrollbar.setValue(0)
        self.app.processEvents()

        self.view.begin_response_feedback("system status")
        self.view.append_message(
            {
                "sender": "Rogue",
                "message": "System status\n- CPU OK\n- RAM OK\n- Disk OK\n- Tasks idle",
                "kind": "assistant",
                "timestamp": "12:03:00",
            }
        )

        QTest.qWait(80)
        self.app.processEvents()

        self.assertLess(scrollbar.value(), scrollbar.maximum())

    def test_animation_keeps_top_edge_pinned_when_user_is_at_start(self):
        self.view.resize(900, 420)
        for index in range(18):
            self.view.append_message(
                {
                    "sender": "Rogue",
                    "message": f"existing message {index}\n" * 3,
                    "kind": "assistant",
                    "timestamp": "12:03:30",
                }
            )
        QTest.qWait(50)
        self.app.processEvents()

        scrollbar = self.view.transcript_scroll.verticalScrollBar()
        scrollbar.setValue(0)
        self.app.processEvents()

        self.view.begin_response_feedback("system status")
        self.view.append_message(
            {
                "sender": "Rogue",
                "message": "System status\n- CPU OK\n- RAM OK\n- Disk OK\n- Tasks idle",
                "kind": "assistant",
                "timestamp": "12:04:00",
            }
        )

        QTest.qWait(80)
        self.app.processEvents()

        self.assertEqual(0, scrollbar.value())

    def test_append_message_keeps_scrollbar_at_true_bottom_when_user_is_already_at_bottom(self):
        self.view.resize(900, 420)
        for index in range(18):
            self.view.append_message(
                {
                    "sender": "Rogue",
                    "message": f"bottom anchor message {index}\n" * 3,
                    "kind": "assistant",
                    "timestamp": "12:04:20",
                }
            )

        QTest.qWait(80)
        self.app.processEvents()

        scrollbar = self.view.transcript_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()

        self.view.append_message(
            {
                "sender": "Rogue",
                "message": "Newest reply should stay pinned to the bottom of the transcript.",
                "kind": "assistant",
                "timestamp": "12:04:21",
            }
        )

        QTest.qWait(80)
        self.app.processEvents()

        self.assertEqual(scrollbar.maximum(), scrollbar.value())

    def test_newest_rogue_message_takes_over_animation_and_commits_older_reply(self):
        first_text = "First verified Rogue reply with enough content to animate gradually."
        second_text = "Second verified Rogue reply should be the only active animation."

        self.view.begin_response_feedback("scan desktop")
        self.view.append_message(
            {
                "sender": "Rogue",
                "message": first_text,
                "kind": "assistant",
                "timestamp": "12:04:00",
            }
        )

        QTest.qWait(30)
        self.app.processEvents()
        first_partial = self.view._message_widgets[-1].content.toPlainText()
        self.assertTrue(first_partial)
        self.assertNotEqual(first_text, first_partial)

        self.view.begin_response_feedback("inspect downloads")
        self.view.append_message(
            {
                "sender": "Rogue",
                "message": second_text,
                "kind": "assistant",
                "timestamp": "12:04:01",
            }
        )

        self.assertEqual(first_text, self.view._message_widgets[0].content.toPlainText())
        self.assertEqual("", self.view._message_widgets[-1].content.toPlainText())

        QTest.qWait(50)
        self.app.processEvents()

        second_partial = self.view._message_widgets[-1].content.toPlainText()
        self.assertTrue(second_partial)
        self.assertNotEqual(second_text, second_partial)
        self.assertTrue(second_text.startswith(second_partial))


if __name__ == "__main__":
    unittest.main()
