"""Chat workspace for the RogueAI Qt desktop shell."""

from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import get_palette


class AutoResizingTextBrowser(QTextBrowser):
    """Read-only transcript text that grows with its document height."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.document().contentsChanged.connect(self._sync_height)
        self._sync_height()

    def setPlainText(self, text):
        super().setPlainText(str(text or ""))
        self._sync_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_height)

    def _sync_height(self):
        document = self.document()
        available_width = max(0, self.viewport().width())
        if available_width:
            document.setTextWidth(available_width)
        height = int(document.size().height() + 6)
        self.setFixedHeight(max(24, height))


class MessageBubble(QFrame):
    """Single transcript card so only the newest message needs to update."""

    def __init__(self, payload, palette, parent=None):
        super().__init__(parent)
        self.setObjectName("messageCard")
        self._payload = {}
        self._palette = dict(palette)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.timestamp_label = QLabel(self)
        self.timestamp_label.setObjectName("metaLabel")
        layout.addWidget(self.timestamp_label)

        self.sender_label = QLabel(self)
        self.sender_label.setObjectName("senderLabel")
        layout.addWidget(self.sender_label)

        self.content = AutoResizingTextBrowser(self)
        self.content.setObjectName("contentBrowser")
        layout.addWidget(self.content)

        self.apply_payload(payload, palette)

    def apply_payload(self, payload, palette):
        self._payload = dict(payload or {})
        self._palette = dict(palette or {})
        self.timestamp_label.setText(str(self._payload.get("timestamp", "")))
        self.sender_label.setText(str(self._payload.get("sender", "Rogue")))
        self.content.setPlainText(self._payload.get("message", ""))
        self._apply_style()

    def set_message_text(self, text):
        self._payload["message"] = str(text or "")
        self.content.setPlainText(self._payload["message"])

    def payload(self):
        return dict(self._payload)

    def _apply_style(self):
        kind = str(self._payload.get("kind", "assistant"))
        palette = self._palette
        background = palette["assistant_bg"]
        border_color = palette["border"]
        border_style = "solid"
        text_color = palette["text"]
        font_style = "normal"

        if kind == "user":
            background = palette["user_bg"]
        elif kind == "warning":
            background = palette["panel_alt"]
            border_color = palette["danger"]
        elif kind == "diagnostics":
            background = palette["panel_alt"]
            border_color = palette["warning"]
        elif kind == "pending":
            border_style = "dashed"
            text_color = palette["text_muted"]
            font_style = "italic"

        self.setStyleSheet(
            f"""
            QFrame#messageCard {{
                background-color: {background};
                border: 1px {border_style} {border_color};
                border-radius: 12px;
            }}
            QLabel#metaLabel {{
                background: transparent;
                border: none;
                color: {palette['text_muted']};
                font-size: 11px;
                text-transform: uppercase;
            }}
            QLabel#senderLabel {{
                background: transparent;
                border: none;
                color: {palette['accent']};
                font-size: 14px;
                font-weight: 700;
            }}
            QTextBrowser#contentBrowser {{
                background: transparent;
                border: none;
                color: {text_color};
                font-family: "Consolas";
                font-size: 13px;
                font-style: {font_style};
                padding: 0px;
                margin: 0px;
            }}
            """
        )


class CommandInputEdit(QTextEdit):
    submit_requested = Signal()

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and not (event.modifiers() & Qt.ShiftModifier):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatView(QFrame):
    command_submitted = Signal(str)
    quick_command_requested = Signal(str)

    def __init__(self, quick_commands=None, theme_name="Dark", parent=None):
        super().__init__(parent)
        self.setObjectName("pagePanel")
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        self._quick_buttons = []
        self._messages = []
        self._message_widgets = []
        self._pending_response_index = None
        self._typing_queue = []
        self._active_typing_animation = None
        self._scroll_restore_token = 0
        self._typing_timer = QTimer(self)
        self._typing_timer.timeout.connect(self._advance_typing_animation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        intro = QFrame(self)
        intro.setObjectName("cardPanel")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(18, 16, 18, 16)
        intro_layout.setSpacing(6)

        section = QLabel("Chat", intro)
        section.setObjectName("sectionLabel")
        title = QLabel("Chat", intro)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Run Rogue commands and review verified system responses.",
            intro,
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        intro_layout.addWidget(section)
        intro_layout.addWidget(title)
        intro_layout.addWidget(subtitle)
        layout.addWidget(intro)

        transcript_panel = QFrame(self)
        transcript_panel.setObjectName("cardPanel")
        transcript_layout = QVBoxLayout(transcript_panel)
        transcript_layout.setContentsMargins(0, 0, 0, 0)
        transcript_layout.setSpacing(0)

        self.transcript_scroll = QScrollArea(transcript_panel)
        self.transcript_scroll.setWidgetResizable(True)
        self.transcript_scroll.setFrameShape(QFrame.NoFrame)
        self.transcript_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.transcript_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.transcript_scroll.setObjectName("transcriptScroll")
        transcript_layout.addWidget(self.transcript_scroll)

        self.transcript = QWidget(self.transcript_scroll)
        self.transcript.setObjectName("transcriptViewport")
        self._transcript_layout = QVBoxLayout(self.transcript)
        self._transcript_layout.setContentsMargins(14, 14, 14, 14)
        self._transcript_layout.setSpacing(10)
        self._transcript_layout.addStretch(1)
        self.transcript_scroll.setWidget(self.transcript)
        layout.addWidget(transcript_panel, 1)

        if quick_commands:
            quick_row = QWidget(self)
            quick_layout = QHBoxLayout(quick_row)
            quick_layout.setContentsMargins(0, 0, 0, 0)
            quick_layout.setSpacing(8)
            for label, command_text in quick_commands:
                button = QPushButton(label, quick_row)
                button.clicked.connect(lambda _checked=False, current=command_text: self.quick_command_requested.emit(current))
                quick_layout.addWidget(button)
                self._quick_buttons.append(button)
            quick_layout.addStretch(1)
            layout.addWidget(quick_row)

        composer = QFrame(self)
        composer.setObjectName("cardPanel")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(14, 14, 14, 14)
        composer_layout.setSpacing(10)

        composer_label = QLabel("Command input", composer)
        composer_label.setObjectName("sectionLabel")
        composer_layout.addWidget(composer_label)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.input_edit = CommandInputEdit(composer)
        self.input_edit.setAcceptRichText(False)
        self.input_edit.setPlaceholderText("Type a Rogue command and press Enter or Send.")
        self.input_edit.setMinimumHeight(88)
        self.input_edit.setMaximumHeight(120)
        self.input_edit.submit_requested.connect(self.submit_current_text)
        row.addWidget(self.input_edit, 1)

        self.send_button = QPushButton("Send", composer)
        self.send_button.setObjectName("accentButton")
        self.send_button.setMinimumWidth(108)
        self.send_button.clicked.connect(self.submit_current_text)
        row.addWidget(self.send_button)

        composer_layout.addLayout(row)
        layout.addWidget(composer)

        self.set_theme(theme_name)

    def set_theme(self, theme_name):
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        for widget in self._message_widgets:
            widget.apply_payload(widget.payload(), self._palette)

    def append_message(self, payload):
        normalized = self._normalize_payload(payload)
        if self._pending_response_index is not None and self._should_replace_pending_response(normalized):
            self._replace_pending_response(normalized)
            return
        self._insert_message(normalized)

    def replace_messages(self, items):
        self._typing_timer.stop()
        self._typing_queue = []
        self._active_typing_animation = None
        self._pending_response_index = None
        self._messages = []
        for widget in self._message_widgets:
            self._transcript_layout.removeWidget(widget)
            widget.deleteLater()
        self._message_widgets = []
        for payload in items:
            self._insert_message(self._normalize_payload(payload), preserve_scroll=False)
        self._scroll_to_bottom()

    def submit_current_text(self):
        text = self._extract_submission_text()
        if not self.submit_external_command(text):
            return False
        self.input_edit.clear()
        return True

    def submit_external_command(self, text, *, emit_signal=True):
        command_text = str(text or "").strip()
        if not command_text:
            return False
        self.append_message(
            {
                "sender": "You",
                "message": command_text,
                "kind": "user",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
        )
        self.begin_response_feedback(command_text)
        if emit_signal:
            self.command_submitted.emit(command_text)
        return True

    def focus_input(self):
        self.input_edit.setFocus(Qt.OtherFocusReason)

    def begin_response_feedback(self, command_text):
        self.finish_response_feedback()
        pending_payload = {
            "sender": "Rogue",
            "message": self._build_pending_status(command_text),
            "kind": "pending",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self._pending_response_index = self._insert_message(pending_payload)

    def finish_response_feedback(self, awaiting_async=False):
        if awaiting_async or self._pending_response_index is None:
            return
        if 0 <= self._pending_response_index < len(self._messages):
            self._remove_message_at(self._pending_response_index)
        self._pending_response_index = None

    def _normalize_payload(self, payload):
        item = dict(payload or {})
        item["sender"] = str(item.get("sender", "Rogue"))
        item["message"] = str(item.get("message", ""))
        item["kind"] = str(item.get("kind", "assistant"))
        item["timestamp"] = str(item.get("timestamp", ""))
        return item

    def _insert_message(self, payload, preserve_scroll=True):
        scroll_state = self._capture_scroll_state() if preserve_scroll else None
        bubble = MessageBubble(payload, self._palette, self.transcript)
        insert_at = self._transcript_layout.count() - 1
        self._transcript_layout.insertWidget(insert_at, bubble)
        self._messages.append(dict(payload))
        self._message_widgets.append(bubble)
        if scroll_state is not None:
            self._restore_scroll_state(scroll_state)
        return len(self._messages) - 1

    def _remove_message_at(self, index):
        if not (0 <= index < len(self._messages)):
            return
        scroll_state = self._capture_scroll_state()
        self._messages.pop(index)
        bubble = self._message_widgets.pop(index)
        self._transcript_layout.removeWidget(bubble)
        bubble.deleteLater()
        self._restore_scroll_state(scroll_state)

    def _capture_scroll_state(self):
        scrollbar = self.transcript_scroll.verticalScrollBar()
        threshold = max(48, scrollbar.pageStep() // 3)
        return {
            "near_top": scrollbar.value() <= max(0, threshold // 2),
            "near_bottom": scrollbar.value() >= scrollbar.maximum() - threshold,
            "value": scrollbar.value(),
        }

    def _restore_scroll_state(self, scroll_state):
        if scroll_state is None:
            return

        self._scroll_restore_token += 1
        token = self._scroll_restore_token

        def apply_scroll():
            if token != self._scroll_restore_token:
                return
            scrollbar = self.transcript_scroll.verticalScrollBar()
            if scroll_state.get("near_top"):
                scrollbar.setValue(0)
            elif scroll_state["near_bottom"]:
                self._force_scroll_to_bottom_after_layout(token=token)
            else:
                scrollbar.setValue(min(scroll_state["value"], scrollbar.maximum()))

        QTimer.singleShot(0, apply_scroll)

    def _scroll_to_bottom(self):
        self._force_scroll_to_bottom_after_layout()

    def _force_scroll_to_bottom_after_layout(self, token=None):
        def apply_scroll():
            if token is not None and token != self._scroll_restore_token:
                return
            scrollbar = self.transcript_scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            QTimer.singleShot(
                0,
                lambda: self._apply_bottom_scroll(token),
            )

        QTimer.singleShot(0, apply_scroll)

    def _apply_bottom_scroll(self, token=None):
        if token is not None and token != self._scroll_restore_token:
            return
        scrollbar = self.transcript_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _should_replace_pending_response(self, payload):
        if payload.get("kind") == "user":
            return False
        return payload.get("sender", "").strip().lower() == "rogue"

    def _replace_pending_response(self, payload):
        index = self._pending_response_index
        if index is None or not (0 <= index < len(self._message_widgets)):
            self._pending_response_index = None
            self._insert_message(payload)
            return

        scroll_state = self._capture_scroll_state()
        self._commit_all_typing_animations()
        bubble = self._message_widgets[index]
        animated_payload = dict(payload)
        animated_payload["message"] = ""
        self._messages[index] = dict(animated_payload)
        bubble.apply_payload(animated_payload, self._palette)
        self._pending_response_index = None

        full_message = payload.get("message", "")
        animation_limit = self._animation_limit(full_message)
        self._typing_queue.append(
            {
                "index": index,
                "full_message": full_message,
                "animation_limit": animation_limit,
                "position": 0,
            }
        )
        self._restore_scroll_state(scroll_state)
        if self._active_typing_animation is None:
            self._start_next_typing_animation()

    def _commit_all_typing_animations(self):
        self._typing_timer.stop()
        animations = []
        if self._active_typing_animation is not None:
            animations.append(self._active_typing_animation)
        animations.extend(self._typing_queue)
        self._typing_queue = []
        self._active_typing_animation = None
        for animation in animations:
            self._commit_animation_message(animation)

    def _commit_animation_message(self, animation):
        if not animation:
            return
        index = animation.get("index")
        if not isinstance(index, int) or not (0 <= index < len(self._message_widgets)):
            return
        full_message = str(animation.get("full_message", ""))
        self._message_widgets[index].set_message_text(full_message)
        self._messages[index]["message"] = full_message

    def _start_next_typing_animation(self):
        if not self._typing_queue:
            self._active_typing_animation = None
            self._typing_timer.stop()
            return
        self._active_typing_animation = self._typing_queue.pop(0)
        interval = self._typing_interval_ms(self._active_typing_animation["full_message"])
        self._typing_timer.start(interval)

    def _advance_typing_animation(self):
        animation = self._active_typing_animation
        if animation is None:
            self._typing_timer.stop()
            return

        index = animation["index"]
        if not (0 <= index < len(self._message_widgets)):
            self._active_typing_animation = None
            self._start_next_typing_animation()
            return

        full_message = animation["full_message"]
        animation_limit = animation["animation_limit"]
        scroll_state = self._capture_scroll_state()

        if animation["position"] >= animation_limit:
            self._message_widgets[index].set_message_text(full_message)
            self._messages[index]["message"] = full_message
            self._typing_timer.stop()
            self._active_typing_animation = None
            self._restore_scroll_state(scroll_state)
            self._start_next_typing_animation()
            return

        next_position = self._next_reveal_position(full_message, animation["position"], animation_limit)
        animation["position"] = next_position
        partial_message = full_message[:next_position]
        self._message_widgets[index].set_message_text(partial_message)
        self._messages[index]["message"] = partial_message
        self._restore_scroll_state(scroll_state)

        if next_position >= animation_limit:
            if animation_limit < len(full_message):
                scroll_state = self._capture_scroll_state()
                self._message_widgets[index].set_message_text(full_message)
                self._messages[index]["message"] = full_message
                self._restore_scroll_state(scroll_state)
            self._typing_timer.stop()
            self._active_typing_animation = None
            self._start_next_typing_animation()

    @staticmethod
    def _typing_interval_ms(message):
        length = len(str(message or ""))
        if length > 1200:
            return 10
        if length > 400:
            return 12
        return 16

    @staticmethod
    def _animation_limit(message):
        text = str(message or "")
        if len(text) <= 600 and text.count("\n") <= 16:
            return len(text)

        char_limit = 320
        line_limit = 8
        line_breaks = 0
        cutoff = len(text)
        for index, character in enumerate(text):
            if character == "\n":
                line_breaks += 1
                if line_breaks >= line_limit:
                    cutoff = index + 1
                    break
        return max(80, min(len(text), min(char_limit, cutoff)))

    @staticmethod
    def _next_reveal_position(message, current_position, animation_limit=None):
        text = str(message or "")
        limit = len(text) if animation_limit is None else min(len(text), animation_limit)
        if current_position >= limit:
            return limit

        remaining = limit - current_position
        if remaining <= 18:
            return limit

        if limit > 320:
            target = current_position + 56
        elif limit > 160:
            target = current_position + 36
        else:
            target = current_position + 22

        target = min(limit, target)
        newline_index = text.find("\n", current_position, target)
        if newline_index != -1 and newline_index > current_position:
            return newline_index + 1

        space_index = text.rfind(" ", current_position + 1, target)
        if space_index > current_position + 6:
            return space_index + 1
        return target

    @staticmethod
    def _build_pending_status(command_text):
        lowered = str(command_text or "").strip().lower()
        if not lowered:
            return "Thinking..."
        if "report" in lowered or "summary" in lowered:
            return "Generating report..."
        if "system status" in lowered or lowered == "status" or "agent status" in lowered:
            return "Checking system status..."
        if "desktop" in lowered and any(token in lowered for token in ("scan", "inspect", "analyze")):
            return "Analyzing desktop..."
        if "downloads" in lowered and any(token in lowered for token in ("scan", "inspect", "analyze")):
            return "Analyzing downloads..."
        if any(token in lowered for token in ("scan", "inspect", "analyze")):
            return "Analyzing..."
        if any(token in lowered for token in ("open", "organize", "cleanup", "move", "run")):
            return "Running command..."
        return "Thinking..."

    def _extract_submission_text(self):
        raw_text = self.input_edit.toPlainText()
        text = str(raw_text or "").strip()
        placeholder = str(self.input_edit.placeholderText() or "").strip()
        if not text:
            return ""
        if placeholder and text == placeholder:
            return ""
        return text
