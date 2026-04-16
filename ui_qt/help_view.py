"""Help page for the RogueAI Qt shell."""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QTextBrowser, QVBoxLayout


class HelpView(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pagePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = QTextBrowser(self)
        self.browser.setReadOnly(True)
        self.browser.setOpenExternalLinks(False)
        self.browser.setTextInteractionFlags(
            Qt.TextSelectableByMouse
            | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse
            | Qt.LinksAccessibleByKeyboard
        )
        layout.addWidget(self.browser)

    def set_model(self, model):
        sections_html = []
        for section in model.get("sections", []):
            lines = "".join(f"<li><code>{escape(line)}</code></li>" for line in section.get("lines", []))
            sections_html.append(f"<h3>{escape(section['title'])}</h3><ul>{lines}</ul>")

        note_blocks = []
        for key, label in (
            ("usage_notes", "Usage notes"),
            ("agent_modes", "Agent modes"),
            ("safety_notes", "Safety"),
        ):
            if model.get(key):
                items = "".join(f"<li>{escape(item)}</li>" for item in model[key])
                note_blocks.append(f"<h3>{label}</h3><ul>{items}</ul>")

        html = f"""
        <h1>{escape(model.get('title', 'Help'))}</h1>
        <p>{escape(model.get('subtitle', ''))}</p>
        {''.join(sections_html)}
        {''.join(note_blocks)}
        <p><strong>{escape(model.get('footer', ''))}</strong></p>
        """
        self.browser.setHtml(html)
