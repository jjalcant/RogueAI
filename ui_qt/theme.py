"""Qt theme helpers for the RogueAI command-center shell."""

PALETTES = {
    "Dark": {
        "background": "#0b0f10",
        "panel": "#12181b",
        "panel_alt": "#162024",
        "panel_soft": "#101618",
        "border": "#1f2a2e",
        "text": "#d7e3dc",
        "text_muted": "#8fa39a",
        "accent": "#39ff88",
        "accent_soft": "#173426",
        "accent_hover": "#1f4732",
        "warning": "#f4c15d",
        "danger": "#ff7a7a",
        "user_bg": "#13261d",
        "assistant_bg": "#141d21",
    },
    "Light": {
        "background": "#f3f7f5",
        "panel": "#ffffff",
        "panel_alt": "#f4f8f6",
        "panel_soft": "#eef4f1",
        "border": "#cfded7",
        "text": "#182521",
        "text_muted": "#5d746b",
        "accent": "#157347",
        "accent_soft": "#dff4e8",
        "accent_hover": "#cdebdc",
        "warning": "#9a6700",
        "danger": "#b42318",
        "user_bg": "#e8f7ee",
        "assistant_bg": "#f6fbf8",
    },
}


def normalize_theme_name(theme_name):
    return "Dark" if str(theme_name or "").strip().lower() == "dark" else "Light"


def get_palette(theme_name):
    return PALETTES[normalize_theme_name(theme_name)]


def build_stylesheet(theme_name):
    palette = get_palette(theme_name)
    return f"""
    QWidget {{
        background: {palette['background']};
        color: {palette['text']};
        font-family: "Segoe UI";
        font-size: 13px;
    }}
    QMainWindow {{
        background: {palette['background']};
    }}
    QFrame#shellPanel, QFrame#sidebarPanel, QFrame#headerPanel, QFrame#cardPanel {{
        background: {palette['panel']};
        border: 1px solid {palette['border']};
        border-radius: 14px;
    }}
    QFrame#pagePanel {{
        background: {palette['background']};
        border: none;
    }}
    QLabel#titleLabel {{
        font-size: 20px;
        font-weight: 700;
        color: {palette['text']};
    }}
    QLabel#mutedLabel {{
        color: {palette['text_muted']};
    }}
    QLabel#sectionLabel {{
        color: {palette['accent']};
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}
    QPushButton {{
        background: {palette['panel_alt']};
        color: {palette['text']};
        border: 1px solid {palette['border']};
        border-radius: 10px;
        padding: 8px 12px;
    }}
    QPushButton:hover {{
        background: {palette['accent_soft']};
        border-color: {palette['accent']};
    }}
    QPushButton:pressed {{
        background: {palette['accent_hover']};
    }}
    QPushButton#accentButton {{
        background: {palette['accent']};
        color: #09110d;
        border-color: {palette['accent']};
        font-weight: 700;
    }}
    QPushButton#sidebarButton {{
        text-align: left;
        padding: 12px 14px;
        border-radius: 12px;
        background: transparent;
    }}
    QPushButton#sidebarButton[active="true"] {{
        background: {palette['accent_soft']};
        color: {palette['accent']};
        border-color: {palette['accent']};
        font-weight: 700;
    }}
    QTextEdit, QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QSpinBox {{
        background: {palette['panel']};
        color: {palette['text']};
        border: 1px solid {palette['border']};
        border-radius: 12px;
        padding: 8px;
        selection-background-color: {palette['accent']};
        selection-color: #09110d;
    }}
    QTextBrowser {{
        background: {palette['panel_soft']};
    }}
    QScrollBar:vertical {{
        background: {palette['panel_soft']};
        width: 12px;
        margin: 4px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background: {palette['border']};
        min-height: 24px;
        border-radius: 6px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QGroupBox {{
        border: 1px solid {palette['border']};
        border-radius: 12px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        color: {palette['accent']};
    }}
    """
