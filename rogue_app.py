"""Desktop app entrypoint for RogueAI."""

import ast
import json
import os
import subprocess
import threading
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont, messagebox, scrolledtext

from app_config import StartupCheckError, run_startup_checks
from brain.agent_state import AgentState
from brain.auto_loop import RogueAutoLoop
from brain.llm_bridge import ask_llm as _ask_llm, get_ollama_status
from brain.proactive_helper import dismiss_suggestion, get_suggestions
from improvement_runtime import ImprovementRuntime, is_improvement_execution_enabled
from memory.memory_store import list_notes as list_memory_notes
from memory.move_history import list_moves as list_file_moves
from operator_brain import OperatorBrain
from task_manager import TaskManager
from tasks.task_queue import get_task, list_tasks
from ui_command_registry import build_command_registry, normalize_command_name
from verification_policy import verification_status_to_message_kind

BASE = Path(__file__).resolve().parent
MEMORY = BASE / "memory"
PROJECTS = BASE / "projects"
AGENTS = BASE / "agents"
AUTONOMY = BASE / "autonomy"
CONFIG = BASE / "config"
LOGS = BASE / "logs"

NOTES_FILE = MEMORY / "notes.md"
BRAIN_LOG = LOGS / "brain.log"
SETTINGS_FILE = CONFIG / "settings.json"
MODULES_FILE = CONFIG / "modules.json"
UI_STATE_FILE = CONFIG / "ui_state.json"
DEFAULT_WINDOW_GEOMETRY = "1360x860"
MIN_WINDOW_SIZE = (1024, 680)
UI_FONT_STACK = ("Segoe UI", "Inter", "Roboto", "Arial")
BRANDING_ASSET_CANDIDATES = (
    "Images/branding/rogue_logo.gif",
    "Images/branding/rogue_logo.png",
    "Images/rogue_logo.gif",
    "Images/rogue_logo.png",
    "Images/logo.gif",
    "Images/logo.png",
)
OFFICIAL_HELP_SECTIONS = [
    (
        "Navigation",
        [
            "help                Show this help screen",
            "back                Return to previous screen",
            "home                Return to dashboard",
            "esc                 Shortcut for back/home behavior",
        ],
    ),
    (
        "System",
        [
            "status              Show system summary",
            "system status       Show CPU, RAM, disk, tasks",
            "agent status        Show agent state",
            "tasks               Show active tasks",
            "task history        Show previous tasks",
            "memory              Show memory status and recent remembered actions",
        ],
    ),
    (
        "Analysis",
        [
            "scan downloads      Analyze Downloads folder",
            "analyze downloads   Same as scan downloads",
            "scan desktop        Analyze Desktop folder",
            "analyze desktop     Same as scan desktop",
            "largest files       Show largest files in current analysis",
            "newest files        Show newest files in current analysis",
            "top file types      Show file type breakdown",
            "duplicates          Find duplicate candidates",
        ],
    ),
    (
        "Actions",
        [
            "open downloads      Open Downloads folder",
            "open desktop        Open Desktop folder",
            "open folder         Open selected folder",
            "organize downloads  Sort Downloads into categories",
            "smart cleanup       Clean obvious junk safely",
            "cleanup temp        Remove temporary files",
            "move files          Move selected files",
            "generate report     Create a report from current analysis",
        ],
    ),
]
THEME_PALETTES = {
    "Light": {
        "app_bg": "#f5f5f5",
        "surface": "#ffffff",
        "surface_alt": "#fafafa",
        "surface_subtle": "#f0f0f0",
        "surface_muted": "#f7f7f7",
        "border": "#dddddd",
        "border_strong": "#cfcfcf",
        "text": "#222222",
        "text_muted": "#555555",
        "accent": "#1f8a57",
        "accent_soft": "#e8f7ef",
        "accent_hover": "#d9f1e4",
        "success": "#1f8a57",
        "success_soft": "#e8f7ef",
        "warning": "#a56a00",
        "warning_soft": "#fff4d6",
        "danger": "#b42318",
        "danger_soft": "#fdeceb",
        "chat_bg": "#ffffff",
        "assistant_bg": "#fafafa",
        "user_bg": "#eef7f2",
        "shadow_line": "#e8e8e8",
        "select_bg": "#d9f1e4",
        "select_fg": "#222222",
    },
    "Dark": {
        "app_bg": "#0b0f10",
        "surface": "#12181b",
        "surface_alt": "#162024",
        "surface_subtle": "#182327",
        "surface_muted": "#101618",
        "border": "#1f2a2e",
        "border_strong": "#2a383d",
        "text": "#d7e3dc",
        "text_muted": "#8fa39a",
        "accent": "#39ff88",
        "accent_soft": "#173426",
        "accent_hover": "#1f4732",
        "success": "#39ff88",
        "success_soft": "#163326",
        "warning": "#f4c15d",
        "warning_soft": "#3a2c08",
        "danger": "#ff7a7a",
        "danger_soft": "#36181b",
        "chat_bg": "#0f1518",
        "assistant_bg": "#141d21",
        "user_bg": "#13261d",
        "shadow_line": "#182126",
        "select_bg": "#244537",
        "select_fg": "#d7e3dc",
    },
}
UI_THEME = dict(THEME_PALETTES["Light"])


class RogueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rogue")
        self.root.geometry(DEFAULT_WINDOW_GEOMETRY)
        self.root.minsize(*MIN_WINDOW_SIZE)

        self.MEMORY = MEMORY
        self.PROJECTS = PROJECTS
        self.AGENTS = AGENTS
        self.AUTONOMY = AUTONOMY
        self.CONFIG = CONFIG
        self.LOGS = LOGS

        self.pending_action = None
        self.conversation_memory = []
        self.activity_history = []
        self.active_sidebar_view = "quick_actions"
        self.last_suggestions = []
        self.active_task_context = None
        self.active_agent_task_context = None
        self.agent_task_view_mode = "recent"
        self.last_agent_workflow_payload = None
        self.last_structured_response_payload = None
        self.last_operator_summary = None
        self.last_runtime_state_snapshot = None
        self.last_verification_result = None
        self.dashboard_preview_model = None
        self.current_view_name = "dashboard"
        self.current_view_state = None
        self.view_history = []
        self.command_registry = None
        self.command_context_menu = None
        self.preview_text_context_menu = None
        self.preview_text_menu_target = None
        self.task_window = None
        self.is_busy = False
        self.command_history = []
        self.command_history_index = None
        self.command_history_draft = ""
        self.window_state_save_job = None
        self.ui_state_path = UI_STATE_FILE
        self.agent_status_badge = None
        self.agent_running_value_label = None
        self.sidebar_collapsed = False
        self.active_primary_view = "chat"
        self.view_frames = {}
        self.nav_buttons = {}
        self.sidebar_width_expanded = 220
        self.sidebar_width_collapsed = 72
        self.button_variants = {}
        self.current_theme_name = "Light"
        self.status_animation_job = None
        self.status_animation_token = 0
        self.brand_animation_job = None
        self.brand_media_frames = []
        self.brand_media_index = 0
        self.brand_asset_path = None

        self.restore_window_state()

        self.startup_report = self.run_startup_checks()
        self.settings = self.startup_report["settings"]
        self.modules = self.startup_report["modules"]
        self.current_theme_name = self.normalize_theme_name(self.settings.get("theme", "Light"))
        self.apply_theme_palette(self.current_theme_name)
        self.backend_status = get_ollama_status()
        self.agent_task_manager = TaskManager(self.MEMORY)
        self.agent_state = AgentState(mode="manual", interval_seconds=60)
        self.auto_loop = None
        self.improvement_runtime = ImprovementRuntime(BASE, self.MEMORY, settings=self.settings)
        self.improvement_observer = self.improvement_runtime.observer
        self.improvement_engine = self.improvement_runtime.engine
        self.improvement_planner = self.improvement_runtime.planner
        self.improvement_guard = self.improvement_runtime.guard
        self.improvement_approval = self.improvement_runtime.approval
        self.improvement_execution_enabled = self.improvement_runtime.execution_enabled
        self.improvement_executor = self.improvement_runtime.executor
        self.improvement_experiments = self.improvement_runtime.experiments
        self.operator_brain = OperatorBrain(self)

        self.status_var = tk.StringVar(master=self.root, value="")
        self.backend_mode_var = tk.StringVar(master=self.root)
        self.model_var = tk.StringVar(master=self.root)
        self.memory_var = tk.StringVar(master=self.root)
        self.tools_var = tk.StringVar(master=self.root)
        self.last_action_var = tk.StringVar(master=self.root, value="UI initialized")
        self.confirmation_var = tk.StringVar(master=self.root, value="No pending confirmation.")
        self.header_context_var = tk.StringVar(master=self.root)
        self.runtime_status_var = tk.StringVar(master=self.root, value="CPU -- | RAM -- | Active tasks 0")
        self.task_indicator_var = tk.StringVar(master=self.root, value="Active tasks: 0")
        self.preview_title_var = tk.StringVar(master=self.root, value="Result preview")
        self.preview_subtitle_var = tk.StringVar(master=self.root, value="Structured agent results appear here.")
        self.agent_running_var = tk.StringVar(master=self.root, value="Stopped")
        self.agent_mode_selector_var = tk.StringVar(master=self.root, value="Manual")
        self.agent_mode_display_var = tk.StringVar(master=self.root, value="Manual")
        self.agent_interval_var = tk.StringVar(master=self.root, value="60")
        self.agent_last_cycle_var = tk.StringVar(master=self.root, value="Not run yet")
        self.agent_next_cycle_var = tk.StringVar(master=self.root, value="Not scheduled")
        self.agent_observation_var = tk.StringVar(master=self.root, value="No observation captured yet.")
        self.agent_plan_var = tk.StringVar(master=self.root, value="No plan generated yet.")
        self.agent_approved_var = tk.StringVar(master=self.root, value="None.")
        self.agent_blocked_var = tk.StringVar(master=self.root, value="None.")
        self.agent_result_var = tk.StringVar(master=self.root, value="Idle.")
        self.agent_error_var = tk.StringVar(master=self.root, value="None.")
        self.settings_theme_var = tk.StringVar(master=self.root, value=self.current_theme_name)

        self.quick_commands = [
            ("scan desktop", "scan desktop"),
            ("inspect downloads", "inspect downloads"),
            ("workspace summary", "workspace summary"),
            ("system status", "agent report system status"),
            ("tasks", "agent list tasks"),
            ("organize desktop", "organize desktop"),
        ]

        self.build_ui()
        self.refresh_status_bar()
        self.log_action(f"Rogue started from: {__file__}")

        startup_lines = []
        if self.startup_report["created_folders"]:
            created = ", ".join(folder.name for folder in self.startup_report["created_folders"])
            startup_lines.append(f"Startup check: created folders -> {created}.")
        else:
            startup_lines.append("Startup check: required folders OK.")

        startup_lines.append(
            f"Config OK. app_name={self.settings['app_name']}, max_memory_turns={self.settings['max_memory_turns']}."
        )
        startup_lines.append(f"Backend: {self.backend_status['message']}")
        self.log_action(f"Startup diagnostics: {' | '.join(startup_lines)}")

        self.add_message(
            "Rogue",
            "Rogue online.\n\n"
            "Primary desktop entrypoint: rogue_app.py\n\n"
            + "\n".join(startup_lines) + "\n\n"
            "Quick commands:\n"
            "- scan desktop\n"
            "- inspect downloads\n"
            "- workspace summary\n"
            "- agent report system status\n"
            "- organize desktop",
            kind="diagnostics",
        )
        self.start_startup_sequence()
        self.record_activity("startup", "Desktop app initialized", tool="ui", success=True)

    def run_startup_checks(self):
        try:
            return run_startup_checks(
                required_folders=[
                    self.MEMORY,
                    self.PROJECTS,
                    self.AGENTS,
                    self.AUTONOMY,
                    self.CONFIG,
                    self.LOGS,
                ],
                settings_path=SETTINGS_FILE,
                modules_path=MODULES_FILE,
            )
        except StartupCheckError as e:
            raise RuntimeError(
                "Startup self-check failed.\n"
                f"{e}\n"
                "Fix the config files and start the desktop app again."
            ) from e

    @staticmethod
    def normalize_theme_name(theme_name):
        resolved = str(theme_name or "").strip().title()
        return resolved if resolved in THEME_PALETTES else "Light"

    def apply_theme_palette(self, theme_name):
        resolved = self.normalize_theme_name(theme_name)
        UI_THEME.clear()
        UI_THEME.update(THEME_PALETTES[resolved])
        self.current_theme_name = resolved
        return resolved

    def save_settings(self):
        settings_payload = dict(getattr(self, "settings", {}) or {})
        settings_payload["theme"] = self.normalize_theme_name(settings_payload.get("theme", self.current_theme_name))
        self.settings = settings_payload
        self.save_json(SETTINGS_FILE, settings_payload)
        return settings_payload

    def resolve_brand_asset_path(self):
        configured = None
        if isinstance(getattr(self, "settings", None), dict):
            configured = self.settings.get("brand_asset")

        raw_candidates = []
        for value in (configured, os.environ.get("ROGUE_BRAND_ASSET")):
            if isinstance(value, str) and value.strip():
                raw_candidates.append(value.strip())
        raw_candidates.extend(BRANDING_ASSET_CANDIDATES)

        for raw_path in raw_candidates:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = BASE / candidate
            if candidate.exists() and candidate.is_file():
                self.brand_asset_path = candidate
                return candidate

        self.brand_asset_path = None
        return None

    @staticmethod
    def scale_brand_image(image, max_size=30):
        width = max(1, int(image.width()))
        height = max(1, int(image.height()))
        scale = max(1, (max(width, height) + max_size - 1) // max_size)
        return image.subsample(scale, scale) if scale > 1 else image

    def load_brand_media(self):
        self.brand_media_frames = []
        self.brand_media_index = 0
        asset_path = self.resolve_brand_asset_path()
        if asset_path is None:
            return False

        try:
            if asset_path.suffix.lower() == ".gif":
                frame_index = 0
                while True:
                    try:
                        frame = tk.PhotoImage(file=str(asset_path), format=f"gif -index {frame_index}")
                    except tk.TclError:
                        break
                    self.brand_media_frames.append(self.scale_brand_image(frame))
                    frame_index += 1
            else:
                self.brand_media_frames.append(self.scale_brand_image(tk.PhotoImage(file=str(asset_path))))
        except tk.TclError:
            self.brand_media_frames = []
            self.brand_asset_path = None

        return bool(self.brand_media_frames)

    def cancel_brand_animation(self):
        job = getattr(self, "brand_animation_job", None)
        if job is not None and hasattr(getattr(self, "root", None), "after_cancel"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.brand_animation_job = None

    def play_brand_animation_frame(self):
        if not getattr(self, "brand_media_frames", None) or not hasattr(self, "brand_media_label"):
            return

        frame = self.brand_media_frames[self.brand_media_index]
        self.brand_media_label.configure(image=frame, text="")

        if len(self.brand_media_frames) <= 1 or not hasattr(getattr(self, "root", None), "after"):
            self.brand_animation_job = None
            return

        self.brand_media_index = (self.brand_media_index + 1) % len(self.brand_media_frames)
        self.brand_animation_job = self.root.after(140, self.play_brand_animation_frame)

    def render_fallback_brand_icon(self):
        if not hasattr(self, "brand_icon_canvas"):
            return

        self.brand_icon_canvas.delete("all")
        accent = UI_THEME["accent"]
        border = UI_THEME["border_strong"]
        center_fill = UI_THEME["accent_soft"]
        self.brand_icon_canvas.create_oval(4, 4, 28, 28, outline=border, width=1)
        self.brand_icon_canvas.create_arc(6, 6, 26, 26, start=28, extent=294, style=tk.ARC, outline=accent, width=2)
        self.brand_icon_canvas.create_line(16, 9, 16, 23, fill=accent, width=2)
        self.brand_icon_canvas.create_line(9, 16, 23, 16, fill=accent, width=2)
        self.brand_icon_canvas.create_oval(12, 12, 20, 20, fill=center_fill, outline=accent, width=1)

    def refresh_branding_visuals(self):
        if not hasattr(self, "brand_media_label") or not hasattr(self, "brand_icon_canvas"):
            return

        self.cancel_brand_animation()
        if self.load_brand_media():
            self.brand_icon_canvas.grid_remove()
            self.brand_media_label.grid(row=0, column=0, sticky="nsew")
            self.play_brand_animation_frame()
            return

        self.brand_media_label.grid_remove()
        self.brand_icon_canvas.grid(row=0, column=0, sticky="nsew")
        self.render_fallback_brand_icon()

    def start_startup_sequence(self):
        self.set_status_feedback("Initializing Rogue...", level="info", animate=True)
        if hasattr(getattr(self, "root", None), "after"):
            self.root.after(900, lambda: self.set_status_feedback("System ready", level="done", animate=True))
        else:
            self.set_status_feedback("System ready", level="done")

    def apply_text_widget_theme(self, widget, editable=False):
        if widget is None:
            return
        config = {
            "bg": UI_THEME["surface_alt"] if editable else UI_THEME["chat_bg"],
            "fg": UI_THEME["text"],
            "insertbackground": UI_THEME["accent"],
            "selectbackground": UI_THEME["select_bg"],
            "selectforeground": UI_THEME["select_fg"],
            "highlightbackground": UI_THEME["border_strong"],
            "highlightcolor": UI_THEME["accent"],
            "exportselection": False,
        }
        if not editable:
            config["cursor"] = "xterm"
        try:
            widget.configure(**config)
        except Exception:
            pass

    def configure_output_text_widget(self, widget):
        if widget is None:
            return widget
        self.apply_text_widget_theme(widget, editable=False)
        widget.bind("<Button-1>", self.handle_output_text_focus)
        widget.bind("<Control-c>", self.handle_output_copy)
        widget.bind("<Control-C>", self.handle_output_copy)
        widget.bind("<Control-a>", self.handle_output_select_all)
        widget.bind("<Control-A>", self.handle_output_select_all)
        widget.bind("<Button-3>", self.show_preview_text_context_menu)
        return widget

    def configure_menu_theme(self, menu):
        if menu is None:
            return
        try:
            menu.configure(
                bg=UI_THEME["surface"],
                fg=UI_THEME["text"],
                activebackground=UI_THEME["accent_soft"],
                activeforeground=UI_THEME["text"],
                bd=1,
                relief=tk.FLAT,
            )
        except Exception:
            return

    def recolor_widget_tree(self, root_widget, previous_theme_name):
        if root_widget is None:
            return
        previous_theme = THEME_PALETTES[self.normalize_theme_name(previous_theme_name)]
        replacements = {
            str(old_value).lower(): UI_THEME[key]
            for key, old_value in previous_theme.items()
            if key in UI_THEME
        }
        option_names = (
            "bg",
            "fg",
            "activebackground",
            "activeforeground",
            "highlightbackground",
            "highlightcolor",
            "insertbackground",
            "selectbackground",
            "selectforeground",
            "disabledforeground",
            "buttonbackground",
            "troughcolor",
        )
        stack = [root_widget]
        while stack:
            widget = stack.pop()
            try:
                children = list(widget.winfo_children())
            except Exception:
                children = []
            stack.extend(children)
            updates = {}
            try:
                keys = set(widget.keys())
            except Exception:
                keys = set()
            for option_name in option_names:
                if option_name not in keys:
                    continue
                try:
                    current_value = widget.cget(option_name)
                except Exception:
                    continue
                replacement = replacements.get(str(current_value).strip().lower())
                if replacement and replacement != current_value:
                    updates[option_name] = replacement
            if isinstance(widget, tk.Canvas) and "bg" not in updates:
                updates["bg"] = UI_THEME["surface_alt"] if widget is getattr(self, "preview_canvas", None) else UI_THEME["app_bg"]
            if isinstance(widget, tk.Scrollbar):
                updates.setdefault("bg", UI_THEME["surface"])
                updates.setdefault("activebackground", UI_THEME["accent_soft"])
                updates.setdefault("troughcolor", UI_THEME["surface_muted"])
                updates.setdefault("highlightbackground", UI_THEME["border"])
            if isinstance(widget, tk.Radiobutton):
                updates.setdefault("selectcolor", UI_THEME["accent_soft"])
                updates.setdefault("activebackground", UI_THEME["surface_alt"])
                updates.setdefault("activeforeground", UI_THEME["text"])
            if updates:
                try:
                    widget.configure(**updates)
                except Exception:
                    pass

    def refresh_theme_widgets(self, previous_theme_name):
        if not hasattr(self, "root"):
            return
        try:
            self.root.configure(bg=UI_THEME["app_bg"])
        except Exception:
            pass
        self.recolor_widget_tree(self.root, previous_theme_name)
        for button, variant in list(self.button_variants.items()):
            try:
                if button.winfo_exists():
                    self.apply_button_variant(button, variant)
                else:
                    self.button_variants.pop(button, None)
            except Exception:
                self.button_variants.pop(button, None)
        self.configure_menu_theme(self.command_context_menu)
        self.configure_menu_theme(self.preview_text_context_menu)
        if hasattr(self, "agent_mode_menu"):
            try:
                self.agent_mode_menu.configure(
                    bg=UI_THEME["surface_alt"],
                    fg=UI_THEME["text"],
                    activebackground=UI_THEME["accent_soft"],
                    activeforeground=UI_THEME["text"],
                    highlightbackground=UI_THEME["border"],
                )
                self.configure_menu_theme(self.agent_mode_menu["menu"])
            except Exception:
                pass
        if hasattr(self, "command_entry"):
            self.apply_text_widget_theme(self.command_entry, editable=True)
        if hasattr(self, "chat_box"):
            self.apply_text_widget_theme(self.chat_box, editable=False)
            self.configure_chat_tags()
        self.refresh_branding_visuals()
        self.set_sidebar_active(getattr(self, "active_primary_view", "chat"))
        self.refresh_settings_view()
        self.refresh_agent_control_panel()
        self.refresh_runtime_status_line()
        self.update_confirmation_ui()

    def set_theme(self, theme_name, persist=True, announce=True):
        resolved = self.normalize_theme_name(theme_name)
        previous_theme = getattr(self, "current_theme_name", "Light")
        self.apply_theme_palette(resolved)
        if hasattr(self, "settings_theme_var"):
            self.settings_theme_var.set(resolved)
        if hasattr(self, "settings"):
            self.settings["theme"] = resolved
            if persist:
                self.save_settings()
        if hasattr(self, "main_frame") and previous_theme != resolved:
            self.refresh_theme_widgets(previous_theme)
        if announce and hasattr(self, "set_status_feedback"):
            self.set_status_feedback(f"Done | Theme set to {resolved}", level="done")
        return resolved

    def handle_theme_change(self):
        selected_theme = self.normalize_theme_name(self.settings_theme_var.get())
        self.set_theme(selected_theme)

    @staticmethod
    def select_ui_font_family(available_families):
        normalized = {str(name).lower(): str(name) for name in available_families}
        for candidate in UI_FONT_STACK:
            if candidate.lower() in normalized:
                return normalized[candidate.lower()]
        return "TkDefaultFont"

    def build_typography(self):
        available_families = tkfont.families(self.root)
        self.ui_font_family = self.select_ui_font_family(available_families)
        self.ui_font_stack_label = ", ".join(UI_FONT_STACK) + ", sans-serif"
        self.ui_fonts = {
            "header_lg": tkfont.Font(root=self.root, family=self.ui_font_family, size=16, weight="bold"),
            "header_md": tkfont.Font(root=self.root, family=self.ui_font_family, size=14, weight="bold"),
            "header_sm": tkfont.Font(root=self.root, family=self.ui_font_family, size=14, weight="bold"),
            "body": tkfont.Font(root=self.root, family=self.ui_font_family, size=12),
            "body_sm": tkfont.Font(root=self.root, family=self.ui_font_family, size=11),
            "body_bold": tkfont.Font(root=self.root, family=self.ui_font_family, size=12, weight="bold"),
            "button": tkfont.Font(root=self.root, family=self.ui_font_family, size=12),
            "status": tkfont.Font(root=self.root, family=self.ui_font_family, size=11),
            "chat": tkfont.Font(root=self.root, family=self.ui_font_family, size=12),
            "chat_header": tkfont.Font(root=self.root, family=self.ui_font_family, size=12, weight="bold"),
            "label_caps": tkfont.Font(root=self.root, family=self.ui_font_family, size=10, weight="bold"),
        }
        self.root.option_add("*Font", self.ui_fonts["body"])

    def build_ui(self):
        self.root.configure(bg=UI_THEME["app_bg"])
        self.build_typography()

        self.main_frame = tk.Frame(self.root, bg=UI_THEME["app_bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        self.build_top_bar()
        self.build_app_shell()
        self.render_preview_placeholder()
        self.populate_help_view()
        self.refresh_settings_view()
        self.refresh_runtime_status_line()
        self.refresh_agent_control_panel()
        if hasattr(self.root, "tk") and hasattr(self.root, "after"):
            self.root.after(20000, lambda: self.refresh_runtime_status_line(schedule=True))
            self.root.after(1500, lambda: self.refresh_agent_control_panel(schedule=True))
        if hasattr(self.root, "bind"):
            self.root.bind("<Escape>", self.handle_escape_key)
            try:
                self.root.bind("<Configure>", self.handle_root_configure, add="+")
            except TypeError:
                self.root.bind("<Configure>", self.handle_root_configure)
        if hasattr(self.root, "protocol"):
            self.root.protocol("WM_DELETE_WINDOW", self.handle_app_close)

        if hasattr(self, "command_entry"):
            self.command_entry.focus_set()

    def build_branding_area(self, parent):
        title_block = tk.Frame(parent, bg=UI_THEME["surface"])
        title_block.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))
        title_block.grid_columnconfigure(1, weight=1)

        self.brand_media_frame = tk.Frame(
            title_block,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            width=34,
            height=34,
        )
        self.brand_media_frame.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 12))
        self.brand_media_frame.grid_propagate(False)
        self.brand_media_frame.grid_rowconfigure(0, weight=1)
        self.brand_media_frame.grid_columnconfigure(0, weight=1)

        self.brand_media_label = tk.Label(
            self.brand_media_frame,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightthickness=0,
        )
        self.brand_icon_canvas = tk.Canvas(
            self.brand_media_frame,
            width=32,
            height=32,
            bg=UI_THEME["surface_alt"],
            highlightthickness=0,
            bd=0,
        )

        tk.Label(
            title_block,
            text="ROGUE AI",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            title_block,
            text="Rogue",
            font=self.ui_fonts["header_lg"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            title_block,
            text="LOCAL",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["accent_soft"],
            padx=8,
            pady=2,
        ).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(2, 0))
        tk.Label(
            title_block,
            textvariable=self.header_context_var,
            font=self.ui_fonts["status"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
        ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(3, 0))

        self.refresh_branding_visuals()
        return title_block

    def build_top_bar(self):
        self.status_frame = tk.Frame(
            self.main_frame,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.status_frame.grid_columnconfigure(1, weight=1)

        self.build_branding_area(self.status_frame)

        action_frame = tk.Frame(self.status_frame, bg=UI_THEME["surface"])
        action_frame.grid(row=0, column=1, sticky="e", padx=16, pady=(14, 6))
        self.run_task_button = tk.Button(
            action_frame,
            text="Run Task",
            command=self.open_task_list_window,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.run_task_button.grid(row=0, column=0, padx=(0, 8))
        self.apply_button_variant(self.run_task_button, "neutral")

        self.clear_chat_button = tk.Button(
            action_frame,
            text="Clear Chat",
            command=self.clear_chat,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.clear_chat_button.grid(row=0, column=1, padx=(0, 8))
        self.apply_button_variant(self.clear_chat_button, "accent")

        self.task_indicator_button = tk.Button(
            action_frame,
            textvariable=self.task_indicator_var,
            command=self.open_task_list_window,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.task_indicator_button.grid(row=0, column=2, sticky="e")
        self.apply_button_variant(self.task_indicator_button, "accent")

        self.runtime_status_label = tk.Label(
            self.status_frame,
            textvariable=self.runtime_status_var,
            font=self.ui_fonts["status"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
            anchor="w",
            padx=16,
            pady=10,
        )
        self.runtime_status_label.grid(row=1, column=0, columnspan=2, sticky="ew")

    def build_app_shell(self):
        self.shell_frame = tk.Frame(self.main_frame, bg=UI_THEME["app_bg"])
        self.shell_frame.grid(row=1, column=0, sticky="nsew")
        self.shell_frame.grid_columnconfigure(1, weight=1)
        self.shell_frame.grid_rowconfigure(0, weight=1)

        self.home_scroll_frame = self.shell_frame
        self.home_body_frame = self.shell_frame

        self.build_sidebar(self.shell_frame)
        self.build_view_stack(self.shell_frame)
        self.switch_main_view("chat")

    def build_sidebar(self, parent):
        self.sidebar_frame = tk.Frame(
            parent,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            width=self.sidebar_width_expanded,
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        sidebar_header = tk.Frame(self.sidebar_frame, bg=UI_THEME["surface"])
        sidebar_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        sidebar_header.grid_columnconfigure(0, weight=1)

        self.sidebar_title_label = tk.Label(
            sidebar_header,
            text="Navigate",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        )
        self.sidebar_title_label.grid(row=0, column=0, sticky="w")

        self.sidebar_toggle_button = tk.Button(
            sidebar_header,
            text="Collapse",
            command=self.toggle_sidebar,
            font=self.ui_fonts["body_sm"],
            padx=8,
            pady=4,
        )
        self.sidebar_toggle_button.grid(row=0, column=1, sticky="e")
        self.apply_button_variant(self.sidebar_toggle_button, "accent")

        self.sidebar_subtitle_label = tk.Label(
            self.sidebar_frame,
            text="Chat is the default workspace. Agent, Help, and Settings stay separate.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
            justify="left",
            wraplength=180,
            padx=12,
        )
        self.sidebar_subtitle_label.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self.sidebar_items = [
            ("chat", "Chat", self.show_home),
            ("agent", "Agent", self.show_agent_view),
            ("help", "Help", self.show_help),
            ("settings", "Settings", self.show_settings_view),
        ]
        self.nav_buttons = {}
        for row_index, (view_name, label, handler) in enumerate(self.sidebar_items, start=2):
            button = tk.Button(
                self.sidebar_frame,
                text=label,
                command=handler,
                font=self.ui_fonts["button"],
                anchor="w",
                padx=14,
                pady=10,
            )
            button.grid(row=row_index, column=0, sticky="ew", padx=10, pady=(0, 8))
            self.apply_button_variant(button, "neutral")
            self.nav_buttons[view_name] = button

        tk.Frame(self.sidebar_frame, bg=UI_THEME["surface"]).grid(row=10, column=0, sticky="nsew")

    def build_view_stack(self, parent):
        self.view_stack_frame = tk.Frame(parent, bg=UI_THEME["app_bg"])
        self.view_stack_frame.grid(row=0, column=1, sticky="nsew")
        self.view_stack_frame.grid_rowconfigure(0, weight=1)
        self.view_stack_frame.grid_columnconfigure(0, weight=1)

        self.chat_view = tk.Frame(self.view_stack_frame, bg=UI_THEME["app_bg"])
        self.chat_view.grid(row=0, column=0, sticky="nsew")
        self.chat_view.grid_rowconfigure(0, weight=1)
        self.chat_view.grid_columnconfigure(0, weight=1)
        self.view_frames["chat"] = self.chat_view

        self.agent_view = tk.Frame(self.view_stack_frame, bg=UI_THEME["app_bg"])
        self.agent_view.grid(row=0, column=0, sticky="nsew")
        self.agent_view.grid_rowconfigure(0, weight=1)
        self.agent_view.grid_columnconfigure(0, weight=1)
        self.view_frames["agent"] = self.agent_view

        self.help_view = tk.Frame(self.view_stack_frame, bg=UI_THEME["app_bg"])
        self.help_view.grid(row=0, column=0, sticky="nsew")
        self.help_view.grid_rowconfigure(0, weight=1)
        self.help_view.grid_columnconfigure(0, weight=1)
        self.view_frames["help"] = self.help_view

        self.settings_view = tk.Frame(self.view_stack_frame, bg=UI_THEME["app_bg"])
        self.settings_view.grid(row=0, column=0, sticky="nsew")
        self.settings_view.grid_rowconfigure(0, weight=1)
        self.settings_view.grid_columnconfigure(0, weight=1)
        self.view_frames["settings"] = self.settings_view

        self.build_chat_view(self.chat_view)
        self.build_agent_view(self.agent_view)
        self.build_help_view(self.help_view)
        self.build_settings_view(self.settings_view)

    def build_chat_view(self, parent):
        container = tk.Frame(
            parent,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_rowconfigure(2, weight=1)
        container.grid_columnconfigure(0, weight=1)

        header = tk.Frame(container, bg=UI_THEME["surface"])
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="CHAT",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Work with Rogue in a chat-first workspace",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text="Use the composer below to run the same router-backed commands while keeping agent diagnostics in their own view.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
            justify="left",
            wraplength=920,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        quick_row = tk.Frame(container, bg=UI_THEME["surface"])
        quick_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        for index, (label, command_text) in enumerate(self.quick_commands):
            button = tk.Button(
                quick_row,
                text=label,
                command=lambda current=command_text: self.run_router_command(current, show_user=True),
                font=self.ui_fonts["body_sm"],
                padx=10,
                pady=6,
            )
            button.grid(row=0, column=index, padx=(0, 8), pady=0, sticky="w")
            self.apply_button_variant(button, "neutral")

        self.chat_panel = tk.Frame(container, bg=UI_THEME["surface"])
        self.chat_panel.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.chat_panel.grid_rowconfigure(2, weight=1)
        self.chat_panel.grid_columnconfigure(0, weight=1)

        self.confirmation_panel = tk.Frame(
            self.chat_panel,
            bg=UI_THEME["warning_soft"],
            bd=0,
            highlightbackground=UI_THEME["warning"],
            highlightthickness=1,
        )
        self.confirmation_panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.confirmation_panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            self.confirmation_panel,
            text="Confirmation Required",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["warning"],
            bg=UI_THEME["warning_soft"],
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self.confirmation_label = tk.Label(
            self.confirmation_panel,
            textvariable=self.confirmation_var,
            font=self.ui_fonts["body"],
            fg=UI_THEME["warning"],
            bg=UI_THEME["warning_soft"],
            justify="left",
            wraplength=820,
        )
        self.confirmation_label.grid(row=1, column=0, sticky="ew", padx=10)

        self.confirmation_buttons = tk.Frame(self.confirmation_panel, bg=UI_THEME["warning_soft"])
        self.confirmation_buttons.grid(row=2, column=0, sticky="w", padx=10, pady=(8, 10))

        self.confirm_downloads_button = tk.Button(
            self.confirmation_buttons,
            text="Confirm organize downloads",
            command=lambda: self.handle_ui_confirmation("downloads"),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.confirm_downloads_button, "warning")
        self.confirm_home_button = tk.Button(
            self.confirmation_buttons,
            text="Confirm organize home workspace",
            command=lambda: self.handle_ui_confirmation("home_workspace"),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.confirm_home_button, "warning")
        self.cancel_button = tk.Button(
            self.confirmation_buttons,
            text="Cancel",
            command=lambda: self.run_router_command("cancel", show_user=False),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.cancel_button, "neutral")

        self.chat_box = scrolledtext.ScrolledText(
            self.chat_panel,
            wrap=tk.WORD,
            font=self.ui_fonts["chat"],
            state=tk.DISABLED,
            bg=UI_THEME["chat_bg"],
            fg=UI_THEME["text"],
            padx=14,
            pady=14,
            bd=0,
            exportselection=False,
            cursor="xterm",
        )
        self.chat_box.grid(row=2, column=0, sticky="nsew")
        self.configure_chat_tags()
        self.configure_output_text_widget(self.chat_box)

        self.preview_panel = tk.Frame(
            self.chat_panel,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.preview_panel.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.preview_panel.grid_columnconfigure(0, weight=1)
        self.preview_panel.grid_rowconfigure(1, weight=1)

        preview_header = tk.Frame(self.preview_panel, bg=UI_THEME["surface_alt"])
        preview_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        preview_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            preview_header,
            text="ROGUE RESPONSE",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            preview_header,
            textvariable=self.preview_title_var,
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            preview_header,
            textvariable=self.preview_subtitle_var,
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        self.preview_scroll_frame = tk.Frame(self.preview_panel, bg=UI_THEME["surface_alt"])
        self.preview_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(12, 12))
        self.preview_scroll_frame.grid_columnconfigure(0, weight=1)
        self.preview_scroll_frame.grid_rowconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            self.preview_scroll_frame,
            bg=UI_THEME["surface_alt"],
            highlightthickness=0,
            bd=0,
            height=240,
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_scrollbar = tk.Scrollbar(
            self.preview_scroll_frame,
            orient=tk.VERTICAL,
            command=self.preview_canvas.yview,
        )
        self.preview_scrollbar.grid(row=0, column=1, sticky="ns")
        self.preview_canvas.configure(yscrollcommand=self.preview_scrollbar.set)

        self.preview_body_frame = tk.Frame(self.preview_canvas, bg=UI_THEME["surface_alt"])
        self.preview_body_frame.grid_columnconfigure(0, weight=1)
        self.preview_canvas_window = self.preview_canvas.create_window((0, 0), window=self.preview_body_frame, anchor="nw")
        self.preview_body_frame.bind("<Configure>", self.on_preview_body_configure)
        self.preview_canvas.bind("<Configure>", self.on_preview_canvas_configure)
        self.bind_preview_mousewheel(self.preview_canvas)
        self.bind_preview_mousewheel(self.preview_body_frame)

        composer = tk.Frame(
            container,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        composer.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        composer.grid_columnconfigure(1, weight=1)

        tk.Label(
            composer,
            text="Message Rogue",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.command_entry = tk.Text(
            composer,
            font=self.ui_fonts["chat"],
            bd=1,
            relief=tk.SOLID,
            bg=UI_THEME["surface_alt"],
            fg=UI_THEME["text"],
            insertbackground=UI_THEME["accent"],
            highlightthickness=1,
            highlightbackground=UI_THEME["border_strong"],
            highlightcolor=UI_THEME["accent"],
            wrap=tk.WORD,
            height=3,
            padx=8,
            pady=8,
            undo=True,
            exportselection=False,
        )
        self.command_entry.grid(row=0, column=1, sticky="ew")
        self.command_entry.bind("<Return>", self.handle_command_enter)
        self.configure_command_entry_bindings()
        self.apply_text_widget_theme(self.command_entry, editable=True)

        self.execute_button = tk.Button(
            composer,
            text="Send",
            command=self.execute_command,
            font=self.ui_fonts["button"],
            padx=14,
            pady=8,
        )
        self.execute_button.grid(row=0, column=2, padx=(12, 0))
        self.apply_button_variant(self.execute_button, "primary")

        self.status_label = tk.Label(
            composer,
            textvariable=self.status_var,
            anchor="w",
            bg=UI_THEME["surface"],
            fg=UI_THEME["text_muted"],
            font=self.ui_fonts["status"],
        )
        self.status_label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self.update_confirmation_ui()

    def build_agent_view(self, parent):
        outer, _canvas, body = self.create_scrollable_view(parent, bg=UI_THEME["app_bg"])
        outer.grid(row=0, column=0, sticky="nsew")
        self.agent_view_body = body

        header = tk.Frame(body, bg=UI_THEME["app_bg"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="AGENT",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["app_bg"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Agent control panel",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["app_bg"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text="Autonomous loop controls, state, observation summaries, plans, and last execution details stay here instead of crowding Chat.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["app_bg"],
            justify="left",
            wraplength=920,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.build_agent_control_panel(parent=body)

    def build_help_view(self, parent):
        outer, _canvas, body = self.create_scrollable_view(parent, bg=UI_THEME["app_bg"])
        outer.grid(row=0, column=0, sticky="nsew")
        self.help_view_body = body

    def build_settings_view(self, parent):
        container = tk.Frame(
            parent,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        self.settings_card = container

        header = tk.Frame(container, bg=UI_THEME["surface"])
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="SETTINGS",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Desktop preferences",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text="This is a light-weight settings view for visible current values and future desktop preferences.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
            justify="left",
            wraplength=920,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.settings_values_frame = tk.Frame(container, bg=UI_THEME["surface"])
        self.settings_values_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.settings_values_frame.grid_columnconfigure(0, weight=1)
        self.settings_value_vars = {
            "theme": tk.StringVar(master=self.root, value=self.current_theme_name),
            "font_size": tk.StringVar(master=self.root, value="12"),
            "default_mode": tk.StringVar(master=self.root, value="Manual"),
            "model_name": tk.StringVar(master=self.root, value="unknown"),
            "app_name": tk.StringVar(master=self.root, value=self.settings.get("app_name", "Rogue Local")),
            "memory_turns": tk.StringVar(master=self.root, value=str(self.settings.get("max_memory_turns", 12))),
        }

        appearance_card = tk.Frame(
            self.settings_values_frame,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=12,
            pady=12,
        )
        appearance_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        appearance_card.grid_columnconfigure(0, weight=1)
        tk.Label(
            appearance_card,
            text="APPEARANCE",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            appearance_card,
            text="Theme",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        theme_controls = tk.Frame(appearance_card, bg=UI_THEME["surface_alt"])
        theme_controls.grid(row=2, column=0, sticky="w", pady=(8, 0))
        for column, theme_name in enumerate(("Light", "Dark")):
            radio = tk.Radiobutton(
                theme_controls,
                text=theme_name,
                value=theme_name,
                variable=self.settings_theme_var,
                command=self.handle_theme_change,
                indicatoron=False,
                padx=14,
                pady=6,
                font=self.ui_fonts["button"],
                bg=UI_THEME["surface_muted"],
                fg=UI_THEME["text"],
                selectcolor=UI_THEME["accent_soft"],
                activebackground=UI_THEME["accent_soft"],
                activeforeground=UI_THEME["text"],
                highlightthickness=1,
                highlightbackground=UI_THEME["border"],
                relief=tk.FLAT,
                bd=0,
            )
            radio.grid(row=0, column=column, padx=(0, 8), sticky="w")

        tk.Label(
            appearance_card,
            text="Font Size",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=3, column=0, sticky="w", pady=(14, 0))
        tk.Label(
            appearance_card,
            textvariable=self.settings_value_vars["font_size"],
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=4, column=0, sticky="w", pady=(6, 0))
        tk.Label(
            appearance_card,
            text="Font scaling remains fixed for stability in the current desktop build.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface_alt"],
            justify="left",
            wraplength=860,
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))

        settings_rows = [
            ("Theme", self.settings_value_vars["theme"], "Current desktop appearance mode saved in config/settings.json."),
            ("Default Mode", self.settings_value_vars["default_mode"], "Current autonomous mode shown for quick visibility."),
            ("Model Name", self.settings_value_vars["model_name"], "Active configured model when available."),
            ("App Name", self.settings_value_vars["app_name"], "Configured desktop application name from settings."),
            ("Memory Turns", self.settings_value_vars["memory_turns"], "Configured short-term conversation memory window."),
        ]
        for index, (title, variable, note) in enumerate(settings_rows, start=1):
            card = tk.Frame(
                self.settings_values_frame,
                bg=UI_THEME["surface_alt"],
                bd=0,
                highlightbackground=UI_THEME["border"],
                highlightthickness=1,
                padx=12,
                pady=12,
            )
            card.grid(row=index, column=0, sticky="ew", pady=(0, 10))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(
                card,
                text=title,
                font=self.ui_fonts["label_caps"],
                fg=UI_THEME["accent"],
                bg=UI_THEME["surface_alt"],
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                card,
                textvariable=variable,
                font=self.ui_fonts["header_sm"],
                fg=UI_THEME["text"],
                bg=UI_THEME["surface_alt"],
            ).grid(row=1, column=0, sticky="w", pady=(4, 2))
            tk.Label(
                card,
                text=note,
                font=self.ui_fonts["body_sm"],
                fg=UI_THEME["text_muted"],
                bg=UI_THEME["surface_alt"],
                justify="left",
                wraplength=860,
            ).grid(row=2, column=0, sticky="w")

    def create_scrollable_view(self, parent, bg=None):
        resolved_bg = bg or UI_THEME["app_bg"]
        outer = tk.Frame(parent, bg=resolved_bg)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=resolved_bg, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        body = tk.Frame(canvas, bg=resolved_bg)
        body.grid_columnconfigure(0, weight=1)
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")

        body.bind("<Configure>", lambda _event, target=canvas: target.configure(scrollregion=target.bbox("all")))
        canvas.bind(
            "<Configure>",
            lambda event, target=canvas, window_id=canvas_window: (
                target.itemconfigure(window_id, width=event.width),
                target.configure(scrollregion=target.bbox("all")),
            ),
        )

        def _bind_mousewheel(widget):
            if widget is None:
                return
            widget.bind(
                "<MouseWheel>",
                lambda event, target=canvas: (target.yview_scroll(-1 if event.delta > 0 else 1, "units"), "break")[1],
            )
            widget.bind("<Button-4>", lambda _event, target=canvas: (target.yview_scroll(-1, "units"), "break")[1])
            widget.bind("<Button-5>", lambda _event, target=canvas: (target.yview_scroll(1, "units"), "break")[1])

        _bind_mousewheel(canvas)
        _bind_mousewheel(body)
        return outer, canvas, body

    def populate_help_view(self, model=None):
        if not hasattr(self, "help_view_body"):
            return
        model = model or self.build_help_preview_model()
        for child in self.help_view_body.winfo_children():
            child.destroy()

        header = tk.Frame(self.help_view_body, bg=UI_THEME["app_bg"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="HELP",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["app_bg"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text=model.get("title", "Rogue Help"),
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["app_bg"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text=model.get("subtitle", "Desktop usage guidance"),
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["app_bg"],
            justify="left",
            wraplength=920,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.create_help_card(
            1,
            "Quick Start",
            model.get(
                "usage_notes",
                [
                    "Open Chat to ask Rogue for folder inspection, summaries, and safe task routing.",
                    "Use Agent when you want to start, stop, or inspect the autonomous loop in more detail.",
                    "Use Help for command reference and safety guidance without mixing that content into the chat transcript.",
                ],
            ),
        )
        self.create_help_card(
            2,
            "Agent Modes",
            model.get(
                "agent_modes",
                [
                    "Manual: observe and plan only. Use Run One Cycle for a single pass.",
                    "Assist: observe and prepare approved tasks without executing them.",
                    "Auto: observe, approve safe tasks, and execute them in the background loop.",
                ],
            ),
        )
        self.create_help_card(
            3,
            "Safety Notes",
            model.get(
                "safety_notes",
                [
                    "Commands that can change files remain confirmation-gated before execution.",
                    "Preview-style organization commands stay non-destructive until you explicitly confirm them.",
                    "The desktop app keeps router, planner, task, memory, and loop behavior deterministic unless you deliberately change modes or approve actions.",
                ],
            ),
        )

        for offset, section in enumerate(model.get("sections", []), start=4):
            self.create_help_card(offset, section.get("title", "Section"), section.get("lines", []))

    def create_help_card(self, row, title, lines):
        card = tk.Frame(
            self.help_view_body,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        tk.Label(
            card,
            text=title,
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        for index, line in enumerate(lines, start=1):
            tk.Label(
                card,
                text=f"- {line}",
                font=self.ui_fonts["body"],
                fg=UI_THEME["text"],
                bg=UI_THEME["surface"],
                justify="left",
                wraplength=900,
            ).grid(row=index, column=0, sticky="w", pady=(6 if index == 1 else 4, 0))

    def refresh_settings_view(self):
        if not hasattr(self, "settings_value_vars"):
            return
        current_theme = self.normalize_theme_name(self.settings.get("theme", self.current_theme_name)) if hasattr(self, "settings") else self.current_theme_name
        self.settings_value_vars["theme"].set(current_theme)
        if hasattr(self, "settings_theme_var"):
            self.settings_theme_var.set(current_theme)
        body_size = self.ui_fonts["body"].cget("size") if hasattr(self, "ui_fonts") else 12
        self.settings_value_vars["font_size"].set(f"{body_size} pt")
        default_mode = self.get_agent_state().get_mode().title() if hasattr(self, "get_agent_state") else "Manual"
        self.settings_value_vars["default_mode"].set(default_mode)
        model_name = self.backend_status.get("model", "unknown") if hasattr(self, "backend_status") else "unknown"
        self.settings_value_vars["model_name"].set(str(model_name))
        if "app_name" in self.settings_value_vars:
            self.settings_value_vars["app_name"].set(str(self.settings.get("app_name", "Rogue Local")))
        if "memory_turns" in self.settings_value_vars:
            self.settings_value_vars["memory_turns"].set(str(self.settings.get("max_memory_turns", 12)))

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        width = self.sidebar_width_collapsed if self.sidebar_collapsed else self.sidebar_width_expanded
        if hasattr(self, "sidebar_frame"):
            self.sidebar_frame.configure(width=width)
        if hasattr(self, "sidebar_toggle_button"):
            self.sidebar_toggle_button.configure(text="Expand" if self.sidebar_collapsed else "Collapse")
        if hasattr(self, "sidebar_title_label"):
            self.sidebar_title_label.configure(text="Views" if self.sidebar_collapsed else "Navigate")
        if hasattr(self, "sidebar_subtitle_label"):
            if self.sidebar_collapsed:
                self.sidebar_subtitle_label.grid_remove()
            else:
                self.sidebar_subtitle_label.grid()
        for view_name, label, _handler in getattr(self, "sidebar_items", []):
            button = self.nav_buttons.get(view_name)
            if button is not None:
                button.configure(text=label[0] if self.sidebar_collapsed else label, anchor="center" if self.sidebar_collapsed else "w")

    def set_sidebar_active(self, view_name):
        for name, button in getattr(self, "nav_buttons", {}).items():
            if name == view_name:
                button.config(bg=UI_THEME["accent_soft"], fg=UI_THEME["accent"])
            else:
                button.config(bg=UI_THEME["surface_muted"], fg=UI_THEME["text"])

    def switch_main_view(self, view_name):
        frame = getattr(self, "view_frames", {}).get(view_name)
        if frame is None:
            return None
        self.active_primary_view = view_name
        frame.tkraise()
        self.set_sidebar_active(view_name)
        if view_name == "chat" and hasattr(self, "command_entry"):
            self.command_entry.focus_set()
        if view_name == "help":
            self.populate_help_view()
        elif view_name == "settings":
            self.refresh_settings_view()
        return view_name

    def apply_button_hover(self, button, hover_bg=None, hover_fg=None):
        if button is None:
            return
        normal_bg = button.cget("bg")
        normal_fg = button.cget("fg")
        resolved_hover_bg = hover_bg or button.cget("activebackground") or normal_bg
        resolved_hover_fg = hover_fg or button.cget("activeforeground") or normal_fg
        button.configure(cursor="hand2")
        button.bind("<Enter>", lambda _event, widget=button, bg=resolved_hover_bg, fg=resolved_hover_fg: widget.configure(bg=bg, fg=fg))
        button.bind("<Leave>", lambda _event, widget=button, bg=normal_bg, fg=normal_fg: widget.configure(bg=bg, fg=fg))

    def apply_button_variant(self, button, variant="neutral"):
        self.button_variants[button] = variant
        palettes = {
            "primary": {
                "bg": UI_THEME["accent"],
                "fg": UI_THEME["app_bg"] if self.current_theme_name == "Dark" else "white",
                "activebackground": UI_THEME["accent_hover"],
                "activeforeground": UI_THEME["text"] if self.current_theme_name == "Dark" else "white",
            },
            "accent": {
                "bg": UI_THEME["accent_soft"],
                "fg": UI_THEME["accent"],
                "activebackground": UI_THEME["accent_hover"],
                "activeforeground": UI_THEME["accent"],
            },
            "neutral": {
                "bg": UI_THEME["surface_muted"],
                "fg": UI_THEME["text"],
                "activebackground": UI_THEME["surface_subtle"],
                "activeforeground": UI_THEME["text"],
            },
            "success": {
                "bg": UI_THEME["success_soft"],
                "fg": UI_THEME["success"],
                "activebackground": UI_THEME["accent_hover"],
                "activeforeground": UI_THEME["success"],
            },
            "warning": {
                "bg": UI_THEME["warning"],
                "fg": UI_THEME["app_bg"] if self.current_theme_name == "Dark" else "white",
                "activebackground": UI_THEME["warning_soft"],
                "activeforeground": UI_THEME["warning"],
            },
        }
        palette = palettes.get(variant, palettes["neutral"])
        button.configure(
            bg=palette["bg"],
            fg=palette["fg"],
            activebackground=palette["activebackground"],
            activeforeground=palette["activeforeground"],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
        )
        self.apply_button_hover(button)

    def configure_command_entry_bindings(self):
        if not hasattr(self, "command_entry"):
            return
        bindings = {
            "<Control-c>": self.handle_command_copy,
            "<Control-C>": self.handle_command_copy,
            "<Control-v>": self.handle_command_paste,
            "<Control-V>": self.handle_command_paste,
            "<Control-x>": self.handle_command_cut,
            "<Control-X>": self.handle_command_cut,
            "<Control-a>": self.handle_command_select_all,
            "<Control-A>": self.handle_command_select_all,
            "<Shift-Return>": self.handle_command_shift_enter,
            "<Up>": self.handle_command_history_up,
            "<Down>": self.handle_command_history_down,
            "<Button-3>": self.show_command_context_menu,
        }
        for sequence, callback in bindings.items():
            self.command_entry.bind(sequence, callback)

    def get_command_text(self):
        if not hasattr(self, "command_entry"):
            return ""
        try:
            return self.command_entry.get("1.0", "end-1c")
        except TypeError:
            return self.command_entry.get()
        except Exception:
            return ""

    def set_command_text(self, value):
        if not hasattr(self, "command_entry"):
            return
        self.clear_command_text()
        text = str(value or "")
        if not text:
            return
        try:
            self.command_entry.insert("1.0", text)
            self.command_entry.mark_set(tk.INSERT, tk.END)
            self.command_entry.see(tk.INSERT)
        except TypeError:
            self.command_entry.insert(0, text)
            self.command_entry.icursor(tk.END)

    def clear_command_text(self):
        if not hasattr(self, "command_entry"):
            return
        try:
            self.command_entry.delete("1.0", tk.END)
        except TypeError:
            self.command_entry.delete(0, tk.END)

    def add_command_history_entry(self, command_text):
        normalized = str(command_text or "").strip()
        if not normalized:
            return
        if not hasattr(self, "command_history"):
            self.command_history = []
        if not hasattr(self, "command_history_index"):
            self.command_history_index = None
        if not hasattr(self, "command_history_draft"):
            self.command_history_draft = ""
        if not self.command_history or self.command_history[-1] != normalized:
            self.command_history.append(normalized)
        self.command_history = self.command_history[-50:]
        self.command_history_index = None
        self.command_history_draft = ""

    def should_navigate_command_history(self, direction):
        if not hasattr(self, "command_entry") or not hasattr(self.command_entry, "index"):
            return True
        current_text = self.get_command_text()
        if "\n" not in current_text:
            return True
        try:
            current_line = int(str(self.command_entry.index(tk.INSERT)).split(".")[0])
            total_lines = int(str(self.command_entry.index("end-1c")).split(".")[0])
        except Exception:
            return False
        if direction < 0:
            return current_line <= 1
        return current_line >= total_lines

    def navigate_command_history(self, direction):
        if not self.command_history:
            return "break"
        if not self.should_navigate_command_history(direction):
            return None

        current_text = self.get_command_text().strip()
        if self.command_history_index is None:
            if direction > 0:
                return None
            self.command_history_draft = current_text
            self.command_history_index = len(self.command_history) - 1
        else:
            self.command_history_index += direction
            if self.command_history_index < 0:
                self.command_history_index = 0
            if self.command_history_index >= len(self.command_history):
                self.command_history_index = None
                self.set_command_text(self.command_history_draft)
                return "break"

        self.set_command_text(self.command_history[self.command_history_index])
        return "break"

    def handle_command_shift_enter(self, event=None):
        if hasattr(self, "command_entry"):
            self.command_entry.insert(tk.INSERT, "\n")
        return "break"

    def handle_command_history_up(self, event=None):
        return self.navigate_command_history(-1)

    def handle_command_history_down(self, event=None):
        return self.navigate_command_history(1)

    def handle_command_copy(self, event=None):
        if hasattr(self, "command_entry"):
            self.command_entry.event_generate("<<Copy>>")
        self.set_status_feedback("Copied command text.", level="done")
        return "break"

    def handle_command_paste(self, event=None):
        if hasattr(self, "command_entry"):
            self.command_entry.event_generate("<<Paste>>")
        self.set_status_feedback("Pasted into command bar.", level="done")
        return "break"

    def handle_command_cut(self, event=None):
        if hasattr(self, "command_entry"):
            self.command_entry.event_generate("<<Cut>>")
        self.set_status_feedback("Cut command text.", level="done")
        return "break"

    def handle_command_select_all(self, event=None):
        if hasattr(self, "command_entry"):
            try:
                self.command_entry.tag_add(tk.SEL, "1.0", tk.END)
                self.command_entry.mark_set(tk.INSERT, "1.0")
                self.command_entry.see(tk.INSERT)
            except Exception:
                self.command_entry.selection_range(0, tk.END)
                self.command_entry.icursor(tk.END)
        return "break"

    def handle_command_clear(self):
        self.clear_command_text()
        self.command_history_index = None
        self.command_history_draft = ""
        if hasattr(self, "command_entry"):
            self.command_entry.focus_set()
        self.set_status_feedback("Done | Cleared command bar", level="done")

    def show_command_context_menu(self, event):
        if self.command_context_menu is None:
            self.command_context_menu = tk.Menu(self.root, tearoff=0)
            self.command_context_menu.add_command(label="Copy", command=self.handle_command_copy)
            self.command_context_menu.add_command(label="Paste", command=self.handle_command_paste)
            self.command_context_menu.add_command(label="Cut", command=self.handle_command_cut)
            self.command_context_menu.add_command(label="Select All", command=self.handle_command_select_all)
            self.command_context_menu.add_command(label="Clear", command=self.handle_command_clear)
            self.configure_menu_theme(self.command_context_menu)
        self.command_entry.focus_set()
        self.command_context_menu.tk_popup(event.x_root, event.y_root)
        self.command_context_menu.grab_release()
        return "break"

    def on_preview_body_configure(self, _event=None):
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def on_preview_canvas_configure(self, event):
        if hasattr(self, "preview_canvas_window"):
            self.preview_canvas.itemconfigure(self.preview_canvas_window, width=event.width)

    def bind_preview_mousewheel(self, widget):
        if widget is None:
            return
        widget.bind("<MouseWheel>", self.handle_preview_mousewheel)
        widget.bind("<Button-4>", self.handle_preview_mousewheel)
        widget.bind("<Button-5>", self.handle_preview_mousewheel)

    def handle_preview_mousewheel(self, event):
        if not hasattr(self, "preview_canvas"):
            return None
        if getattr(event, "delta", 0):
            direction = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            direction = -1
        else:
            direction = 1
        self.preview_canvas.yview_scroll(direction, "units")
        return "break"

    def apply_status_level(self, level="ready"):
        palette = {
            "ready": UI_THEME["text_muted"],
            "running": UI_THEME["accent"],
            "done": UI_THEME["success"],
            "error": UI_THEME["danger"],
            "info": UI_THEME["text"],
        }
        if hasattr(self, "status_label"):
            self.status_label.configure(fg=palette.get(level, palette["ready"]))

    @staticmethod
    def should_animate_status(message, level="ready"):
        if level == "error":
            return False
        normalized = str(message or "").strip().lower()
        return (
            normalized.startswith("initializing rogue")
            or normalized.startswith("system ready")
            or normalized.startswith("running | agent loop started")
            or normalized.startswith("running | agent cycle started")
        )

    def cancel_status_animation(self):
        job = getattr(self, "status_animation_job", None)
        if job is not None and hasattr(getattr(self, "root", None), "after_cancel"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.status_animation_job = None
        self.status_animation_token = getattr(self, "status_animation_token", 0) + 1

    def animate_status_text(self, message, level="ready", interval_ms=22):
        if not hasattr(self, "status_var"):
            return
        if not hasattr(getattr(self, "root", None), "after"):
            self.status_var.set(str(message or ""))
            self.apply_status_level(level)
            return

        final_text = str(message or "")
        self.cancel_status_animation()
        token = self.status_animation_token
        self.apply_status_level(level)

        if not final_text:
            self.status_var.set("")
            return

        def step(index=1):
            if getattr(self, "status_animation_token", None) != token:
                return
            self.status_var.set(final_text[:index])
            if index < len(final_text):
                self.status_animation_job = self.root.after(interval_ms, lambda: step(index + 1))
            else:
                self.status_animation_job = None

        step(1)

    def set_status_feedback(self, message, level="ready", animate=None):
        self.apply_status_level(level)
        if animate is None:
            animate = self.should_animate_status(message, level)

        if animate:
            self.animate_status_text(message, level=level)
            return

        self.cancel_status_animation()
        if hasattr(self, "status_var"):
            self.status_var.set(message)
        self.apply_status_level(level)

    def handle_app_close(self):
        self.cancel_status_animation()
        self.cancel_brand_animation()
        loop = getattr(self, "auto_loop", None)
        if loop is not None:
            try:
                loop.stop(wait=False)
            except Exception:
                pass
        self.save_window_state()
        if hasattr(self.root, "destroy"):
            self.root.destroy()

    def get_ui_state_path(self):
        return Path(getattr(self, "ui_state_path", UI_STATE_FILE))

    def restore_window_state(self):
        path = self.get_ui_state_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        geometry = str(data.get("geometry") or "").strip()
        if not geometry:
            return
        try:
            self.root.geometry(geometry)
        except Exception:
            return

    def save_window_state(self):
        self.window_state_save_job = None
        try:
            geometry = self.root.geometry()
        except Exception:
            geometry = ""
        geometry = str(geometry or "").strip()
        if not geometry:
            return
        self.save_json(
            self.get_ui_state_path(),
            {
                "geometry": geometry,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def handle_root_configure(self, event=None):
        widget = getattr(event, "widget", self.root)
        if widget is not self.root:
            return
        if hasattr(self.root, "after_cancel") and self.window_state_save_job is not None:
            try:
                self.root.after_cancel(self.window_state_save_job)
            except Exception:
                pass
        if hasattr(self.root, "after"):
            self.window_state_save_job = self.root.after(250, self.save_window_state)

    def build_status_bar(self):
        self.status_frame = tk.Frame(
            self.main_frame,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.status_frame.grid_columnconfigure(1, weight=1)

        nav_frame = tk.Frame(self.status_frame, bg=UI_THEME["surface"])
        nav_frame.grid(row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 4))
        self.back_button = tk.Button(
            nav_frame,
            text="Back",
            command=self.go_back,
            font=self.ui_fonts["button"],
            padx=10,
            pady=6,
        )
        self.back_button.grid(row=0, column=0, padx=(0, 8))
        self.back_button.grid_remove()
        self.apply_button_variant(self.back_button, "accent")

        self.home_button = tk.Button(
            nav_frame,
            text="Home",
            command=self.show_home,
            font=self.ui_fonts["button"],
            padx=10,
            pady=6,
        )
        self.home_button.grid(row=0, column=1, padx=(0, 8))
        self.apply_button_variant(self.home_button, "neutral")

        self.help_button = tk.Button(
            nav_frame,
            text="Help",
            command=self.show_help,
            font=self.ui_fonts["button"],
            padx=10,
            pady=6,
        )
        self.help_button.grid(row=0, column=2)
        self.apply_button_variant(self.help_button, "accent")

        title_block = tk.Frame(self.status_frame, bg=UI_THEME["surface"])
        title_block.grid(row=0, column=1, sticky="w", padx=8, pady=(12, 4))
        tk.Label(
            title_block,
            text="DESKTOP ASSISTANT",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="Rogue",
            font=self.ui_fonts["header_lg"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            title_block,
            textvariable=self.header_context_var,
            font=self.ui_fonts["status"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        action_frame = tk.Frame(self.status_frame, bg=UI_THEME["surface"])
        action_frame.grid(row=0, column=2, sticky="e", padx=16, pady=(12, 4))
        self.run_task_button = tk.Button(
            action_frame,
            text="Run Task",
            command=self.open_task_list_window,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.run_task_button.grid(row=0, column=0, padx=(0, 8))
        self.apply_button_variant(self.run_task_button, "neutral")

        self.clear_chat_button = tk.Button(
            action_frame,
            text="Clear Chat",
            command=self.clear_chat,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.clear_chat_button.grid(row=0, column=1, padx=(0, 8))
        self.apply_button_variant(self.clear_chat_button, "accent")

        self.task_indicator_button = tk.Button(
            action_frame,
            textvariable=self.task_indicator_var,
            command=self.open_task_list_window,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.task_indicator_button.grid(row=0, column=2, sticky="e")
        self.apply_button_variant(self.task_indicator_button, "accent")

        self.command_bar_frame = tk.Frame(self.status_frame, bg=UI_THEME["surface"])
        self.command_bar_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 12))
        self.command_bar_frame.grid_columnconfigure(0, weight=1)

        composer = tk.Frame(
            self.command_bar_frame,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(1, weight=1)

        tk.Label(
            composer,
            text="COMMAND BAR",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(
            composer,
            text="Ask Rogue to inspect, navigate, or run a safe assistant command.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface_alt"],
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 10))

        tk.Label(
            composer,
            text="Ask Rogue",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
            padx=0,
            pady=0,
        ).grid(row=2, column=0, sticky="w", padx=(0, 12))

        self.command_entry = tk.Text(
            composer,
            font=self.ui_fonts["chat"],
            bd=1,
            relief=tk.SOLID,
            bg=UI_THEME["surface"],
            fg=UI_THEME["text"],
            insertbackground=UI_THEME["accent"],
            highlightthickness=1,
            highlightbackground=UI_THEME["border_strong"],
            highlightcolor=UI_THEME["accent"],
            wrap=tk.WORD,
            height=3,
            padx=8,
            pady=8,
            undo=True,
        )
        self.command_entry.grid(row=2, column=1, sticky="ew")
        self.command_entry.bind("<Return>", self.handle_command_enter)
        self.configure_command_entry_bindings()

        self.execute_button = tk.Button(
            composer,
            text="Send",
            command=self.execute_command,
            font=self.ui_fonts["button"],
            padx=14,
            pady=8,
        )
        self.execute_button.grid(row=2, column=2, padx=(12, 0))
        self.apply_button_variant(self.execute_button, "primary")

        self.runtime_status_label = tk.Label(
            self.status_frame,
            textvariable=self.runtime_status_var,
            font=self.ui_fonts["status"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
            anchor="w",
            padx=16,
            pady=10,
        )
        self.runtime_status_label.grid(row=2, column=0, columnspan=3, sticky="ew")

    def build_home_scroll_area(self):
        self.home_scroll_frame = tk.Frame(self.main_frame, bg=UI_THEME["app_bg"])
        self.home_scroll_frame.grid(row=1, column=0, sticky="nsew")
        self.home_scroll_frame.grid_rowconfigure(0, weight=1)
        self.home_scroll_frame.grid_columnconfigure(0, weight=1)

        self.home_canvas = tk.Canvas(
            self.home_scroll_frame,
            bg=UI_THEME["app_bg"],
            highlightthickness=0,
            bd=0,
        )
        self.home_canvas.grid(row=0, column=0, sticky="nsew")

        self.home_scrollbar = tk.Scrollbar(
            self.home_scroll_frame,
            orient=tk.VERTICAL,
            command=self.home_canvas.yview,
        )
        self.home_scrollbar.grid(row=0, column=1, sticky="ns")
        self.home_canvas.configure(yscrollcommand=self.home_scrollbar.set)

        self.home_body_frame = tk.Frame(self.home_canvas, bg=UI_THEME["app_bg"])
        self.home_body_frame.grid_columnconfigure(0, weight=1)
        self.home_canvas_window = self.home_canvas.create_window((0, 0), window=self.home_body_frame, anchor="nw")
        self.home_body_frame.bind("<Configure>", self.on_home_body_configure)
        self.home_canvas.bind("<Configure>", self.on_home_canvas_configure)
        self.bind_home_mousewheel(self.home_canvas)
        self.bind_home_mousewheel(self.home_body_frame)

    def on_home_body_configure(self, _event=None):
        if hasattr(self, "home_canvas"):
            self.home_canvas.configure(scrollregion=self.home_canvas.bbox("all"))

    def on_home_canvas_configure(self, event):
        if hasattr(self, "home_canvas_window"):
            self.home_canvas.itemconfigure(self.home_canvas_window, width=event.width)
        self.on_home_body_configure()

    def bind_home_mousewheel(self, widget):
        if widget is None:
            return
        widget.bind("<MouseWheel>", self.handle_home_mousewheel)
        widget.bind("<Button-4>", self.handle_home_mousewheel)
        widget.bind("<Button-5>", self.handle_home_mousewheel)

    def handle_home_mousewheel(self, event):
        if not hasattr(self, "home_canvas"):
            return None
        if getattr(event, "delta", 0):
            direction = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            direction = -1
        else:
            direction = 1
        self.home_canvas.yview_scroll(direction, "units")
        return "break"

    def refresh_home_scroll_bindings(self):
        if not hasattr(self, "home_body_frame"):
            return

        excluded = {
            getattr(self, "chat_box", None),
            getattr(self, "preview_canvas", None),
            getattr(self, "preview_body_frame", None),
        }

        def _bind_tree(widget):
            if widget in excluded or widget is None:
                return
            self.bind_home_mousewheel(widget)
            if hasattr(widget, "winfo_children"):
                for child in widget.winfo_children():
                    _bind_tree(child)

        _bind_tree(self.home_body_frame)

    def build_content_area(self):
        self.content_frame = tk.Frame(self.home_body_frame, bg=UI_THEME["app_bg"])
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=0)
        self.content_frame.grid_columnconfigure(1, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.quick_panel = tk.Frame(
            self.content_frame,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            width=220,
        )
        self.quick_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        self.quick_panel.grid_propagate(False)
        self.quick_panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            self.quick_panel,
            text="Quick prompts",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
            padx=12,
            pady=14,
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            self.quick_panel,
            text="Use these as instant prompts for the same assistant commands you can type below.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface_alt"],
            justify="left",
            wraplength=180,
            padx=12,
        ).grid(row=1, column=0, sticky="ew")

        for index, (label, command_text) in enumerate(self.quick_commands, start=2):
            button = tk.Button(
                self.quick_panel,
                text=label,
                command=lambda current=command_text: self.run_router_command(current, show_user=True),
                font=self.ui_fonts["button"],
                anchor="w",
                padx=12,
                pady=8,
            )
            button.grid(row=index, column=0, sticky="ew", padx=10, pady=(0, 8))
            self.apply_button_variant(button, "neutral")

        self.chat_panel = tk.Frame(
            self.content_frame,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.chat_panel.grid(row=0, column=1, sticky="nsew")
        self.chat_panel.grid_rowconfigure(2, weight=1)
        self.chat_panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            self.chat_panel,
            text="Conversation",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
            padx=12,
            pady=12,
        ).grid(row=0, column=0, sticky="ew")

        self.confirmation_panel = tk.Frame(
            self.chat_panel,
            bg=UI_THEME["warning_soft"],
            bd=0,
            highlightbackground=UI_THEME["warning"],
            highlightthickness=1,
        )
        self.confirmation_panel.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 14))
        self.confirmation_panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            self.confirmation_panel,
            text="Confirmation Required",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["warning"],
            bg=UI_THEME["warning_soft"],
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self.confirmation_label = tk.Label(
            self.confirmation_panel,
            textvariable=self.confirmation_var,
            font=self.ui_fonts["body"],
            fg=UI_THEME["warning"],
            bg=UI_THEME["warning_soft"],
            justify="left",
            wraplength=640,
        )
        self.confirmation_label.grid(row=1, column=0, sticky="ew", padx=10)

        self.confirmation_buttons = tk.Frame(self.confirmation_panel, bg=UI_THEME["warning_soft"])
        self.confirmation_buttons.grid(row=2, column=0, sticky="w", padx=10, pady=(8, 10))

        self.confirm_downloads_button = tk.Button(
            self.confirmation_buttons,
            text="Confirm organize downloads",
            command=lambda: self.handle_ui_confirmation("downloads"),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.confirm_downloads_button, "warning")
        self.confirm_home_button = tk.Button(
            self.confirmation_buttons,
            text="Confirm organize home workspace",
            command=lambda: self.handle_ui_confirmation("home_workspace"),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.confirm_home_button, "warning")
        self.cancel_button = tk.Button(
            self.confirmation_buttons,
            text="Cancel",
            command=lambda: self.run_router_command("cancel", show_user=False),
            font=self.ui_fonts["button"],
            padx=10,
        )
        self.apply_button_variant(self.cancel_button, "neutral")

        self.chat_box = scrolledtext.ScrolledText(
            self.chat_panel,
            wrap=tk.WORD,
            font=self.ui_fonts["chat"],
            state=tk.DISABLED,
            bg=UI_THEME["chat_bg"],
            fg=UI_THEME["text"],
            padx=14,
            pady=14,
            bd=0,
            exportselection=False,
            cursor="xterm",
        )
        self.chat_box.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.configure_chat_tags()
        self.configure_output_text_widget(self.chat_box)

        self.update_confirmation_ui()

    def build_agent_control_panel(self, parent=None):
        host = parent or self.home_body_frame
        self.agent_control_panel = tk.Frame(
            host,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.agent_control_panel.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.agent_control_panel.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.agent_control_panel, bg=UI_THEME["surface"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="AGENT CONTROL",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Autonomous loop visibility and controls",
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            text="Loop state stays visible here while background work remains off the Tkinter thread.",
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        self.agent_status_badge = tk.Label(
            header,
            text="Stopped",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface_muted"],
            padx=12,
            pady=4,
        )
        self.agent_status_badge.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        controls = tk.Frame(self.agent_control_panel, bg=UI_THEME["surface"])
        controls.grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 8))
        controls.grid_columnconfigure(0, weight=1)

        action_row = tk.Frame(controls, bg=UI_THEME["surface"])
        action_row.grid(row=0, column=0, sticky="w")

        self.start_agent_button = tk.Button(
            action_row,
            text="Start Agent",
            command=self.start_agent_loop,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.start_agent_button.grid(row=0, column=0, padx=(0, 8))
        self.apply_button_variant(self.start_agent_button, "success")

        self.stop_agent_button = tk.Button(
            action_row,
            text="Stop Agent",
            command=self.stop_agent_loop,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.stop_agent_button.grid(row=0, column=1, padx=(0, 8))
        self.apply_button_variant(self.stop_agent_button, "warning")

        self.run_cycle_button = tk.Button(
            action_row,
            text="Run One Cycle",
            command=self.run_agent_cycle,
            font=self.ui_fonts["button"],
            padx=12,
            pady=6,
        )
        self.run_cycle_button.grid(row=0, column=2)
        self.apply_button_variant(self.run_cycle_button, "accent")

        mode_row = tk.Frame(controls, bg=UI_THEME["surface"])
        mode_row.grid(row=0, column=1, sticky="e")
        tk.Label(
            mode_row,
            text="Mode",
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))

        self.agent_mode_menu = tk.OptionMenu(
            mode_row,
            self.agent_mode_selector_var,
            "Manual",
            "Assist",
            "Auto",
            command=self.handle_agent_mode_change,
        )
        self.agent_mode_menu.grid(row=0, column=1, sticky="w")
        self.agent_mode_menu.configure(
            bg=UI_THEME["surface_alt"],
            fg=UI_THEME["text"],
            activebackground=UI_THEME["accent_soft"],
            activeforeground=UI_THEME["text"],
            highlightthickness=1,
            highlightbackground=UI_THEME["border"],
            bd=0,
            relief=tk.FLAT,
        )

        summary_strip = tk.Frame(self.agent_control_panel, bg=UI_THEME["surface"])
        summary_strip.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        summary_strip.grid_columnconfigure(0, weight=1)
        summary_strip.grid_columnconfigure(1, weight=1)
        summary_strip.grid_columnconfigure(2, weight=1)

        self.agent_running_value_label = self.build_agent_inline_field(summary_strip, "Running Status", self.agent_running_var, 0, 0)
        self.build_agent_inline_field(summary_strip, "Current Mode", self.agent_mode_display_var, 0, 1)
        self.build_agent_inline_field(summary_strip, "Interval (seconds)", self.agent_interval_var, 0, 2)
        self.build_agent_inline_field(summary_strip, "Last Cycle Time", self.agent_last_cycle_var, 1, 0)
        self.build_agent_inline_field(summary_strip, "Next Cycle Time", self.agent_next_cycle_var, 1, 1, columnspan=2)

        body = tk.Frame(self.agent_control_panel, bg=UI_THEME["surface"])
        body.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self.build_agent_value_card(body, "Latest Observation Summary", self.agent_observation_var, 0, 0)
        self.build_agent_value_card(body, "Latest Generated Plan", self.agent_plan_var, 0, 1)
        self.build_agent_value_card(body, "Approved Tasks", self.agent_approved_var, 1, 0)
        self.build_agent_value_card(body, "Blocked Tasks", self.agent_blocked_var, 1, 1)
        self.build_agent_value_card(body, "Last Result", self.agent_result_var, 2, 0)
        self.build_agent_value_card(body, "Last Error", self.agent_error_var, 2, 1)

    def build_agent_inline_field(self, parent, title, variable, row, column, columnspan=1):
        card = tk.Frame(
            parent,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=8,
            pady=6,
        )
        right_pad = 8 if column + columnspan - 1 < 2 else 0
        card.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=(0, right_pad), pady=(0, 6))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text=title,
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface_alt"],
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        value_label = tk.Label(
            card,
            textvariable=variable,
            font=self.ui_fonts["body_bold"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
            anchor="w",
            justify="left",
            wraplength=420 if columnspan > 1 else 220,
        )
        value_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        return value_label

    def build_agent_value_card(self, parent, title, variable, row, column, columnspan=1):
        card = tk.Frame(
            parent,
            bg=UI_THEME["surface_alt"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=8,
            pady=7,
        )
        card.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", pady=(0, 6), padx=(0, 8 if column == 0 and columnspan == 1 else 0))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text=title,
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface_alt"],
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        value_label = tk.Label(
            card,
            textvariable=variable,
            font=self.ui_fonts["body"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface_alt"],
            anchor="w",
            justify="left",
            wraplength=360,
        )
        value_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        return value_label

    def build_input_area(self):
        self.preview_panel = tk.Frame(
            self.home_body_frame,
            bg=UI_THEME["surface"],
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
        )
        self.preview_panel.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        self.preview_panel.grid_columnconfigure(0, weight=1)
        self.preview_panel.grid_rowconfigure(1, weight=1)

        preview_header = tk.Frame(self.preview_panel, bg=UI_THEME["surface"])
        preview_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        preview_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            preview_header,
            text="ROGUE RESPONSE",
            font=self.ui_fonts["label_caps"],
            fg=UI_THEME["accent"],
            bg=UI_THEME["surface"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            preview_header,
            textvariable=self.preview_title_var,
            font=self.ui_fonts["header_sm"],
            fg=UI_THEME["text"],
            bg=UI_THEME["surface"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            preview_header,
            textvariable=self.preview_subtitle_var,
            font=self.ui_fonts["body_sm"],
            fg=UI_THEME["text_muted"],
            bg=UI_THEME["surface"],
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        self.preview_scroll_frame = tk.Frame(self.preview_panel, bg=UI_THEME["surface"])
        self.preview_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(12, 12))
        self.preview_scroll_frame.grid_columnconfigure(0, weight=1)
        self.preview_scroll_frame.grid_rowconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            self.preview_scroll_frame,
            bg=UI_THEME["surface"],
            highlightthickness=0,
            bd=0,
            height=360,
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_scrollbar = tk.Scrollbar(
            self.preview_scroll_frame,
            orient=tk.VERTICAL,
            command=self.preview_canvas.yview,
        )
        self.preview_scrollbar.grid(row=0, column=1, sticky="ns")
        self.preview_canvas.configure(yscrollcommand=self.preview_scrollbar.set)

        self.preview_body_frame = tk.Frame(self.preview_canvas, bg=UI_THEME["surface"])
        self.preview_body_frame.grid_columnconfigure(0, weight=1)
        self.preview_canvas_window = self.preview_canvas.create_window((0, 0), window=self.preview_body_frame, anchor="nw")
        self.preview_body_frame.bind("<Configure>", self.on_preview_body_configure)
        self.preview_canvas.bind("<Configure>", self.on_preview_canvas_configure)
        self.bind_preview_mousewheel(self.preview_canvas)
        self.bind_preview_mousewheel(self.preview_body_frame)

        self.bottom_frame = tk.Frame(self.home_body_frame, bg=UI_THEME["app_bg"])
        self.bottom_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(
            self.bottom_frame,
            textvariable=self.status_var,
            anchor="w",
            bg=UI_THEME["app_bg"],
            fg=UI_THEME["text_muted"],
            font=self.ui_fonts["status"],
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

    def configure_chat_tags(self):
        common_margins = {"lmargin1": 14, "lmargin2": 14, "rmargin": 14}
        self.chat_box.tag_configure("header_user", foreground=UI_THEME["accent"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)
        self.chat_box.tag_configure("header_assistant", foreground=UI_THEME["text"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)
        self.chat_box.tag_configure("header_warning", foreground=UI_THEME["warning"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)
        self.chat_box.tag_configure("header_tool", foreground=UI_THEME["success"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)
        self.chat_box.tag_configure("header_confirm", foreground=UI_THEME["warning"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)
        self.chat_box.tag_configure("header_diagnostics", foreground=UI_THEME["accent"], font=self.ui_fonts["chat_header"], spacing1=10, **common_margins)

        self.chat_box.tag_configure("body_user", foreground=UI_THEME["text"], background=UI_THEME["user_bg"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)
        self.chat_box.tag_configure("body_assistant", foreground=UI_THEME["text"], background=UI_THEME["assistant_bg"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)
        self.chat_box.tag_configure("body_tool", foreground=UI_THEME["success"], background=UI_THEME["success_soft"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)
        self.chat_box.tag_configure("body_warning", foreground=UI_THEME["warning"], background=UI_THEME["warning_soft"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)
        self.chat_box.tag_configure("body_confirm", foreground=UI_THEME["warning"], background=UI_THEME["warning_soft"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)
        self.chat_box.tag_configure("body_diagnostics", foreground=UI_THEME["text"], background=UI_THEME["surface_subtle"], font=self.ui_fonts["chat"], spacing1=4, spacing3=14, **common_margins)

    def refresh_status_bar(self):
        backend_mode = self.get_backend_mode_label()
        self.backend_mode_var.set(backend_mode)
        self.model_var.set(self.backend_status.get("model", "unknown"))
        self.memory_var.set("Enabled" if self.modules.get("memory") else "Disabled")
        tools_loaded = self.modules.get("tools") or self.modules.get("autonomy")
        self.tools_var.set("Loaded" if tools_loaded else "Unavailable")
        self.header_context_var.set(
            f"{backend_mode} | {self.model_var.get()} | memory {self.memory_var.get().lower()} | tools {self.tools_var.get().lower()}"
        )
        self.refresh_task_indicator()
        self.refresh_settings_view()

    def refresh_task_indicator(self):
        try:
            active_tasks = len(self.get_agent_task_snapshot().get("active_tasks", []))
        except Exception:
            active_tasks = 0
        if hasattr(self, "task_indicator_var"):
            self.task_indicator_var.set(f"Active tasks: {active_tasks}")
        return active_tasks

    def get_agent_state(self):
        if not hasattr(self, "agent_state") or self.agent_state is None:
            self.agent_state = AgentState(mode="manual", interval_seconds=60)
        return self.agent_state

    def get_auto_loop(self):
        if getattr(self, "auto_loop", None) is None:
            state = self.get_agent_state()
            self.auto_loop = RogueAutoLoop(
                cycle_seconds=state.get_interval_seconds(),
                agent_state=state,
            )
        return self.auto_loop

    @staticmethod
    def normalize_agent_panel_text(value, empty_text):
        text = str(value or "").strip()
        return text if text else empty_text

    @staticmethod
    def humanize_internal_identifier(value):
        lookup = {
            "inspect_downloads": "Inspect downloads",
            "inspect_desktop": "Inspect desktop",
            "inspect_workspace": "Inspect workspace",
            "workspace_summary": "Workspace summary",
            "list_path": "List folder contents",
            "preview_folder_organization": "Preview folder organization",
            "apply_download_organization": "Organize downloads",
            "apply_home_workspace_organization": "Organize home workspace",
            "move_files": "Move files",
            "delete_files": "Delete files",
            "kill_process": "Stop process",
            "get_system_info": "Get system info",
        }
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in lookup:
            return lookup[lowered]
        if "_" in text and " " not in text:
            text = text.replace("_", " ")
        return text[:1].upper() + text[1:] if text else ""

    def refresh_agent_control_panel(self, schedule=False):
        snapshot = self.get_agent_state().snapshot()
        running_status = self.normalize_agent_panel_text(snapshot.get("running_status"), "Stopped")
        last_error = self.normalize_agent_panel_text(snapshot.get("last_error"), "")
        self.agent_running_var.set(running_status)
        mode_label = self.normalize_agent_panel_text(snapshot.get("mode"), "manual").title()
        self.agent_mode_selector_var.set(mode_label)
        self.agent_mode_display_var.set(mode_label)
        self.agent_interval_var.set(str(snapshot.get("interval_seconds", 60)))
        self.agent_last_cycle_var.set(self.normalize_agent_panel_text(snapshot.get("last_cycle_time"), "Not run yet"))
        self.agent_next_cycle_var.set(self.normalize_agent_panel_text(snapshot.get("next_cycle_time"), "Not scheduled"))
        self.agent_observation_var.set(
            self.normalize_agent_panel_text(snapshot.get("latest_observation_summary"), "No observation captured yet.")
        )
        self.agent_plan_var.set(
            self.format_agent_plan_text(
                self.normalize_agent_panel_text(snapshot.get("latest_generated_plan"), "No plan generated yet.")
            )
        )
        self.agent_approved_var.set(self.normalize_agent_panel_text(snapshot.get("approved_tasks"), "None."))
        self.agent_blocked_var.set(self.normalize_agent_panel_text(snapshot.get("blocked_tasks"), "None."))
        self.agent_result_var.set(self.normalize_agent_panel_text(snapshot.get("last_result"), "Idle."))
        self.agent_error_var.set(last_error or "None.")
        self.update_agent_status_indicator(running_status, last_error)
        if schedule and hasattr(self.root, "after") and hasattr(self.root, "tk"):
            self.root.after(1500, lambda: self.refresh_agent_control_panel(schedule=True))

    def format_agent_plan_text(self, plan_text):
        text = str(plan_text or "").strip()
        if not text:
            return "No plan generated yet."
        lines = []
        source_lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(source_lines):
            task_text, separator, tool_text = line.partition("->")
            prefix = ""
            stripped_task = task_text.strip()
            if ". " in stripped_task:
                maybe_prefix, _, maybe_task = stripped_task.partition(". ")
                if maybe_prefix.isdigit() and maybe_task:
                    prefix = f"{maybe_prefix}. "
                    stripped_task = maybe_task.strip()
            if separator:
                lines.append(f"{prefix}{self.humanize_internal_identifier(stripped_task)}")
                lines.append(f"    Tool: {self.humanize_internal_identifier(tool_text.strip())}")
            else:
                if prefix:
                    lines.append(f"{prefix}{self.humanize_internal_identifier(stripped_task)}")
                else:
                    lines.append(self.humanize_internal_identifier(line))
            if index < len(source_lines) - 1:
                lines.append("")
        return "\n".join(lines)

    def update_agent_status_indicator(self, running_status, last_error=""):
        status_text = str(running_status or "").strip()
        error_text = str(last_error or "").strip()
        if error_text and not status_text.lower().startswith("running"):
            label_text = "Error"
            bg = UI_THEME["danger_soft"]
            fg = UI_THEME["danger"]
        elif status_text.lower().startswith("running"):
            label_text = "Running"
            bg = UI_THEME["success_soft"]
            fg = UI_THEME["success"]
        else:
            label_text = "Stopped"
            bg = UI_THEME["surface_muted"]
            fg = UI_THEME["text_muted"]

        if self.agent_status_badge is not None:
            self.agent_status_badge.configure(text=label_text, bg=bg, fg=fg)
        if self.agent_running_value_label is not None:
            self.agent_running_value_label.configure(fg=fg)

    def handle_agent_mode_change(self, selected_mode=None):
        mode_text = str(selected_mode or self.agent_mode_selector_var.get()).strip().lower()
        state = self.get_agent_state()
        state.set_mode(mode_text)
        if mode_text == "manual":
            loop = getattr(self, "auto_loop", None)
            if loop is not None and loop.is_running():
                loop.stop(wait=False)
                self.add_message("Rogue", "Agent mode set to Manual. Background loop stopping after the current cycle.", kind="tool")
            self.set_status_feedback("Ready | Agent mode set to Manual", level="ready")
        elif mode_text == "assist":
            self.set_status_feedback("Ready | Agent mode set to Assist", level="ready")
        else:
            self.set_status_feedback("Ready | Agent mode set to Auto", level="ready")
        self.refresh_agent_control_panel()

    def start_agent_loop(self):
        state = self.get_agent_state()
        if state.get_mode() == "manual":
            message = "Manual mode does not run continuously. Use Run One Cycle or switch to Assist/Auto."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            self.refresh_agent_control_panel()
            return False

        loop = self.get_auto_loop()
        if not loop.start():
            message = "Agent loop is already running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            self.refresh_agent_control_panel()
            return False

        message = f"Agent loop started in {state.get_mode().title()} mode."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Running | {message}", level="running")
        self.refresh_agent_control_panel()
        return True

    def stop_agent_loop(self):
        loop = getattr(self, "auto_loop", None)
        if loop is None or not loop.stop(wait=False):
            self.get_agent_state().mark_stopped()
            message = "Agent loop is not running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            self.refresh_agent_control_panel()
            return False

        message = "Agent loop stop requested."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Ready | {message}", level="ready")
        self.refresh_agent_control_panel()
        return True

    def run_agent_cycle(self):
        loop = self.get_auto_loop()
        if not loop.run_cycle_async():
            message = "Agent cycle is already running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            self.refresh_agent_control_panel()
            return False

        message = f"Agent cycle started in {self.get_agent_state().get_mode().title()} mode."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Running | {message}", level="running")
        self.refresh_agent_control_panel()
        return True

    def collect_runtime_metrics(self):
        active_tasks = self.refresh_task_indicator()
        cpu_value = "--"
        ram_value = "--"
        try:
            command = (
                "$cpu = (Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue; "
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "[pscustomobject]@{cpu=[math]::Round($cpu,0); "
                "used_ram_gb=[math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB),1); "
                "total_ram_gb=[math]::Round(($os.TotalVisibleMemorySize / 1MB),1)} | ConvertTo-Json -Compress"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                payload = json.loads(completed.stdout.strip())
                cpu_value = f"{int(payload.get('cpu', 0))}%"
                ram_value = f"{payload.get('used_ram_gb', '--')}/{payload.get('total_ram_gb', '--')} GB"
        except Exception:
            pass
        return {"cpu": cpu_value, "ram": ram_value, "active_tasks": active_tasks}

    def refresh_runtime_status_line(self, schedule=False):
        metrics = self.collect_runtime_metrics()
        self.runtime_status_var.set(
            f"CPU {metrics['cpu']} | RAM {metrics['ram']} | Active tasks {metrics['active_tasks']}"
        )
        if schedule:
            self.root.after(20000, lambda: self.refresh_runtime_status_line(schedule=True))

    def get_command_registry(self):
        if self.command_registry is None:
            self.command_registry = build_command_registry(self)
        return self.command_registry

    def get_command_definition(self, command_text):
        normalized = normalize_command_name(command_text)
        if not normalized:
            return None
        for definition in self.get_command_registry():
            names = (definition.name,) + tuple(definition.aliases)
            if normalized in {normalize_command_name(value) for value in names}:
                return definition
        return None

    def handle_command_enter(self, event):
        if event is not None and getattr(event, "state", 0) & 0x1:
            return self.handle_command_shift_enter(event)
        return self.execute_command()

    def handle_escape_key(self, event=None):
        return self.go_back(event=event)

    def execute_command(self, command_text=None):
        raw_value = command_text
        if raw_value is None and hasattr(self, "command_entry"):
            raw_value = self.get_command_text()
        raw_value = str(raw_value or "").strip()
        if not raw_value:
            self.set_status_feedback("Ready | Enter a command to execute.", level="ready")
            return "break"
        self.add_command_history_entry(raw_value)

        definition = self.get_command_definition(raw_value)
        if not definition:
            message = "Unknown command. Type help to see available commands."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Error | {message}", level="error")
            return "break"

        if definition.requires_confirmation and not self.confirm_command_execution(definition):
            message = f"Cancelled command: {definition.name}"
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return "break"

        if hasattr(self, "command_entry"):
            self.clear_command_text()

        self.set_status_feedback(f"Running | {definition.name}", level="running")
        try:
            result = definition.handler(raw_value)
        except Exception as exc:
            message = f"Command failed: {definition.name} ({exc})"
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Error | {message}", level="error")
            self.observe_friction(
                area="command_execution",
                trigger="execution_failure",
                command=raw_value,
                symptom=f"command failed: {definition.name}",
                impact=4,
                raw_context=message,
                metadata={"tool": "command_registry", "command_name": definition.name},
            )
            self.record_activity("warning", f"Command failed: {definition.name}", command=raw_value, tool="command_registry", success=False)
            return "break"

        self.set_status_feedback(f"Done | Command executed: {definition.name}", level="done")
        self.record_activity("command", f"Executed {definition.name}", command=raw_value, tool="command_registry", success=True)
        if hasattr(self, "command_entry"):
            self.command_entry.focus_set()
        return result

    def confirm_command_execution(self, definition):
        message = definition.confirmation_message or f"Run command: {definition.name}?"
        try:
            return bool(messagebox.askyesno("Confirm Command", message, parent=self.root))
        except TypeError:
            return bool(messagebox.askyesno("Confirm Command", message))

    def run_registered_router_command(self, command_text):
        return self.run_router_command(command_text, show_user=True)

    def show_dashboard_preview(self, model=None):
        if model:
            self.dashboard_preview_model = model
        self.current_view_name = "dashboard"
        self.current_view_state = None
        self.view_history = []
        self.switch_main_view("chat")
        if self.dashboard_preview_model:
            self.render_preview_model(self.dashboard_preview_model)
        else:
            self.render_preview_placeholder()
        self.update_navigation_controls()
        self.set_status_feedback("Ready | Dashboard ready", level="ready")
        return "dashboard"

    def show_secondary_view(self, view_name, model):
        if self.current_view_name == view_name and self.current_view_state:
            self.current_view_state = {"name": view_name, "model": model}
            if view_name == "help":
                self.populate_help_view(model)
                self.switch_main_view("help")
            else:
                self.switch_main_view("chat")
                self.render_preview_model(model)
            self.update_navigation_controls()
            self.set_status_feedback(f"Ready | Viewing {model.get('title', view_name)}", level="info")
            return view_name
        if self.current_view_name != "dashboard" and self.current_view_state:
            self.view_history.append(self.current_view_state)
        self.current_view_name = view_name
        self.current_view_state = {"name": view_name, "model": model}
        if view_name == "help":
            self.populate_help_view(model)
            self.switch_main_view("help")
        elif view_name == "agent":
            self.switch_main_view("agent")
        elif view_name == "settings":
            self.switch_main_view("settings")
        else:
            self.switch_main_view("chat")
            self.render_preview_model(model)
        self.update_navigation_controls()
        self.set_status_feedback(f"Ready | Viewing {model.get('title', view_name)}", level="info")
        return view_name

    def show_home(self):
        return self.show_dashboard_preview()

    def show_agent_view(self):
        self.current_view_name = "agent"
        self.current_view_state = None
        self.switch_main_view("agent")
        self.update_navigation_controls()
        self.set_status_feedback("Ready | Agent view", level="info")
        return "agent"

    def show_settings_view(self):
        self.current_view_name = "settings"
        self.current_view_state = None
        self.switch_main_view("settings")
        self.update_navigation_controls()
        self.set_status_feedback("Ready | Settings view", level="info")
        return "settings"

    def go_back(self, event=None):
        if self.view_history:
            state = self.view_history.pop()
            self.current_view_name = state["name"]
            self.current_view_state = state
            if state["name"] == "help":
                self.populate_help_view(state["model"])
                self.switch_main_view("help")
            else:
                self.switch_main_view("chat")
                self.render_preview_model(state["model"])
            self.update_navigation_controls()
            self.set_status_feedback(f"Ready | Viewing {state['model'].get('title', state['name'])}", level="info")
        else:
            self.show_home()
        return "break" if event is not None else "dashboard"

    def update_navigation_controls(self):
        if not hasattr(self, "nav_buttons"):
            return
        if self.current_view_name == "help":
            self.set_sidebar_active("help")
        elif self.current_view_name == "agent":
            self.set_sidebar_active("agent")
        elif self.current_view_name == "settings":
            self.set_sidebar_active("settings")
        else:
            self.set_sidebar_active("chat")

    def build_help_preview_model(self):
        sections = [
            {"title": title, "lines": lines}
            for title, lines in OFFICIAL_HELP_SECTIONS
        ]
        return {
            "title": "Rogue Help",
            "subtitle": "Official command reference and desktop usage guidance.",
            "rows": [
                ("Navigation", "help, back, home, esc"),
                ("System", "status, system status, agent status, tasks, task history, memory"),
                ("Analysis", "scan downloads, scan desktop, largest files, newest files, top file types, duplicates"),
                ("Actions", "open downloads, open desktop, open folder, organize downloads, smart cleanup, cleanup temp, move files, generate report"),
            ],
            "sections": sections,
            "usage_notes": [
                "Chat is the main workspace for commands and conversation.",
                "Agent is the technical control panel for loop state, plans, and cycle execution.",
                "Settings currently shows visible defaults and placeholders for future preferences.",
            ],
            "agent_modes": [
                "Manual: run observation and planning only when you ask for a cycle.",
                "Assist: prepare approved work without executing it automatically.",
                "Auto: continuously run approved work in the background loop.",
            ],
            "safety_notes": [
                "Potentially destructive commands require explicit confirmation before execution.",
                "Preview-style organization flows remain non-destructive until you confirm them.",
                "Use Help or Chat for guidance; use Agent when you want detailed loop visibility.",
            ],
            "footer": "Safety: Destructive actions require confirmation before execution.\nType help anytime to see this list again.",
        }

    def show_help(self):
        return self.show_secondary_view("help", self.build_help_preview_model())

    def show_status_overview(self):
        model = {
            "title": "System status",
            "subtitle": "Desktop runtime overview",
            "rows": [
                ("Backend", self.get_backend_mode_label()),
                ("Model", self.backend_status.get("model", "unknown")),
                ("Memory", self.memory_var.get() if hasattr(self, "memory_var") else "unknown"),
                ("Tools", self.tools_var.get() if hasattr(self, "tools_var") else "unknown"),
                ("Active tasks", self.refresh_task_indicator()),
            ],
            "sections": [
                {
                    "title": "Workspace",
                    "lines": [
                        f"Projects items: {self.count_items(self.PROJECTS)}",
                        f"Memory items: {self.count_items(self.MEMORY)}",
                        f"Logs folder items: {self.count_items(self.LOGS)}",
                    ],
                }
            ],
        }
        return self.show_secondary_view("status", model)

    def show_tasks_overview(self):
        snapshot = self.get_agent_task_snapshot()
        model = self.build_task_list_preview(snapshot.get("recent_tasks", []), "Agent Tasks")
        model["subtitle"] = "Recent task visibility from persistent agent task state."
        return self.show_secondary_view("tasks", model)

    def show_task_history(self):
        recent_activity = [
            f"{item['timestamp']} | {item['summary']}"
            for item in reversed(self.activity_history[-8:])
        ] or ["No desktop activity recorded yet."]
        recent_tasks = []
        for task in self.get_agent_task_snapshot().get("recent_tasks", [])[:6]:
            summary = self.get_agent_task_manager().summarize_task(task)
            recent_tasks.append(
                f"Task {summary['task_id']} [{summary['status']}] - {summary['goal']}"
            )
        model = {
            "title": "Task history",
            "subtitle": "Recent agent tasks and desktop command activity.",
            "rows": [
                ("Recent tasks", len(self.get_agent_task_snapshot().get("recent_tasks", []))),
                ("Session actions", len(self.activity_history)),
            ],
            "sections": [
                {"title": "Recent Tasks", "lines": recent_tasks or ["No tasks recorded yet."]},
                {"title": "Desktop Activity", "lines": recent_activity},
            ],
        }
        return self.show_secondary_view("task_history", model)

    def show_memory_overview(self):
        payload = list_memory_notes()
        note_lines = []
        if payload.get("notes"):
            note_lines = [f"{key}: {value}" for key, value in sorted(payload["notes"].items())]
        else:
            note_lines = [payload.get("result") or payload.get("error", "No notes available.")]
        model = {
            "title": "Memory",
            "subtitle": "Persistent memory notes from the current store.",
            "rows": [("Saved notes", len(payload.get("notes", {})))],
            "sections": [{"title": "Notes", "lines": note_lines}],
        }
        return self.show_secondary_view("memory", model)

    def show_stub_message(self, message, title="Command"):
        model = {
            "title": title,
            "subtitle": "Registered in the desktop command registry.",
            "rows": [("Status", "Stubbed")],
            "sections": [{"title": "Details", "lines": [message]}],
        }
        return self.show_secondary_view(normalize_command_name(title), model)

    def get_latest_folder_summary(self):
        payload = getattr(self, "last_agent_workflow_payload", None)
        if not isinstance(payload, dict) or payload.get("kind") != "agent_run":
            return None, ""
        agent_payload = payload.get("payload", {})
        for item in reversed(agent_payload.get("results", [])):
            summary = item.get("result", {}).get("summary")
            if summary:
                return summary, agent_payload.get("goal", "")
        return None, agent_payload.get("goal", "")

    def show_folder_summary_section(self, summary_key, section_title):
        summary, goal = self.get_latest_folder_summary()
        if not summary:
            self.run_router_command("inspect downloads", show_user=False)
            summary, goal = self.get_latest_folder_summary()
        if not summary:
            return self.show_stub_message(
                "No folder summary is available yet. Run scan downloads or scan desktop first.",
                title=section_title,
            )

        formatter_map = {
            "top_file_types": lambda entry: {"text": f"{entry['extension']}: {entry['count']}"},
            "largest_files": lambda entry: {"text": f"{entry['name']}: {entry['size_bytes']} bytes", "path": entry.get("path")},
            "newest_files": lambda entry: {"text": f"{entry['name']}: {entry['modified']}", "path": entry.get("path")},
        }
        entries = [
            formatter_map[summary_key](entry)
            for entry in summary.get(summary_key, [])[:8]
        ] or [{"text": "No entries available."}]
        model = {
            "title": section_title,
            "subtitle": Path(summary.get("path", "")).name or (goal or "Folder summary"),
            "rows": [
                ("Files", summary.get("total_files", 0)),
                ("Directories", summary.get("total_directories", 0)),
                ("Size", summary.get("total_size_human", "0 B")),
            ],
            "sections": [{"title": section_title, "entries": entries}],
            "footer": "Back returns to the dashboard summary.",
        }
        return self.show_secondary_view(normalize_command_name(section_title), model)

    def clear_preview_panel(self):
        if not hasattr(self, "preview_body_frame"):
            return
        for child in self.preview_body_frame.winfo_children():
            child.destroy()

    def create_preview_card(self, parent, title=None, subtitle=None, row=0, pady=(0, 12), bg=None):
        bg = bg or UI_THEME["surface_alt"]
        card = tk.Frame(
            parent,
            bg=bg,
            bd=0,
            highlightbackground=UI_THEME["border"],
            highlightthickness=1,
            padx=0,
            pady=0,
        )
        card.grid(row=row, column=0, sticky="ew", pady=pady)
        card.grid_columnconfigure(0, weight=1)
        self.bind_preview_mousewheel(card)

        body_start_row = 0
        if title:
            title_label = tk.Label(
                card,
                text=title,
                font=self.ui_fonts["header_md"],
                fg=UI_THEME["text"],
                bg=bg,
                anchor="w",
                justify="left",
                padx=16,
                pady=16,
            )
            title_label.grid(row=0, column=0, sticky="ew")
            self.bind_preview_mousewheel(title_label)
            body_start_row = 1

        if subtitle:
            subtitle_label = tk.Label(
                card,
                text=subtitle,
                font=self.ui_fonts["body_sm"],
                fg=UI_THEME["text_muted"],
                bg=bg,
                anchor="w",
                justify="left",
                wraplength=760,
                padx=16,
                pady=0,
            )
            subtitle_label.grid(row=body_start_row, column=0, sticky="ew")
            self.bind_preview_mousewheel(subtitle_label)
            body_start_row += 1

        body = tk.Frame(card, bg=bg)
        body.grid(row=body_start_row, column=0, sticky="ew", padx=16, pady=(12 if subtitle else 0, 16))
        body.grid_columnconfigure(0, weight=1)
        self.bind_preview_mousewheel(body)
        return card, body

    def render_preview_rows(self, parent, rows, bg=None):
        bg = bg or UI_THEME["surface_alt"]
        for index, (label, value) in enumerate(rows):
            row = tk.Frame(parent, bg=bg)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            row.grid_columnconfigure(1, weight=1)
            self.bind_preview_mousewheel(row)
            label_widget = tk.Label(
                row,
                text=str(label),
                font=self.ui_fonts["body_bold"],
                fg=UI_THEME["text_muted"],
                bg=bg,
                anchor="w",
                justify="left",
                width=18,
            )
            label_widget.grid(row=0, column=0, sticky="w")
            self.bind_preview_mousewheel(label_widget)
            value_widget = tk.Label(
                row,
                text=str(value),
                font=self.ui_fonts["body"],
                fg=UI_THEME["text"],
                bg=bg,
                anchor="w",
                justify="left",
                wraplength=600,
            )
            value_widget.grid(row=0, column=1, sticky="ew")
            self.bind_preview_mousewheel(value_widget)
            copy_button = tk.Button(
                row,
                text="Copy",
                command=lambda current_label=label, current_value=value: self.copy_result_line(f"{current_label}: {current_value}"),
                font=self.ui_fonts["body_sm"],
                relief=tk.FLAT,
                padx=8,
                pady=3,
            )
            copy_button.grid(row=0, column=2, padx=(10, 0))
            self.apply_button_variant(copy_button, "accent")
            self.bind_preview_mousewheel(copy_button)

    def create_selectable_text_block(self, parent, text, bg=None, height=None, row=0):
        bg = bg or UI_THEME["surface_alt"]
        line_count = max(1, str(text).count("\n") + 1)
        widget = tk.Text(
            parent,
            wrap=tk.WORD,
            font=self.ui_fonts["body"],
            bg=bg,
            fg=UI_THEME["text"],
            bd=0,
            relief=tk.FLAT,
            height=height or min(max(line_count, 2), 14),
            padx=0,
            pady=0,
            undo=False,
            highlightthickness=0,
        )
        widget.grid(row=row, column=0, sticky="ew")
        widget.insert("1.0", text)
        widget.config(state=tk.DISABLED)
        self.configure_output_text_widget(widget)
        self.bind_preview_mousewheel(widget)
        return widget

    def handle_output_text_focus(self, event=None):
        widget = getattr(event, "widget", None)
        if widget is None:
            return None
        self.preview_text_menu_target = widget
        try:
            widget.focus_set()
        except Exception:
            pass
        return None

    def handle_output_copy(self, event=None):
        if event is not None:
            self.preview_text_menu_target = event.widget
        self.copy_preview_text_selection()
        return "break"

    def handle_output_select_all(self, event=None):
        if event is not None:
            self.preview_text_menu_target = event.widget
        self.select_all_preview_text()
        return "break"

    def show_preview_text_context_menu(self, event):
        widget = event.widget
        self.preview_text_menu_target = widget
        if self.preview_text_context_menu is None:
            self.preview_text_context_menu = tk.Menu(self.root, tearoff=0)
        else:
            self.preview_text_context_menu.delete(0, tk.END)
        self.preview_text_context_menu.add_command(label="Copy", command=self.copy_preview_text_selection)
        self.preview_text_context_menu.add_command(label="Select All", command=self.select_all_preview_text)
        if widget is getattr(self, "chat_box", None):
            self.preview_text_context_menu.add_separator()
            self.preview_text_context_menu.add_command(label="Clear Chat", command=self.clear_preview_text)
        self.configure_menu_theme(self.preview_text_context_menu)
        widget.focus_set()
        try:
            widget.mark_set("insert", widget.index(f"@{event.x},{event.y}"))
        except Exception:
            pass
        self.preview_text_context_menu.tk_popup(event.x_root, event.y_root)
        self.preview_text_context_menu.grab_release()
        return "break"

    def copy_preview_text_selection(self):
        widget = self.preview_text_menu_target
        if widget is None:
            return
        try:
            selected = widget.selection_get()
        except Exception:
            selected = ""
        if selected:
            self.copy_result_line(selected)

    def select_all_preview_text(self):
        widget = self.preview_text_menu_target
        if widget is None:
            return
        try:
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
        except Exception:
            return

    def clear_preview_text(self):
        widget = self.preview_text_menu_target
        if widget is None:
            return
        if widget is getattr(self, "chat_box", None):
            self.clear_chat()

    def render_preview_entries(self, parent, entries, bg=None):
        bg = bg or UI_THEME["surface_alt"]
        for index, entry in enumerate(entries):
            row = tk.Frame(parent, bg=bg)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 10))
            row.grid_columnconfigure(0, weight=1)
            self.bind_preview_mousewheel(row)
            text = entry.get("text", "")
            text_label = tk.Label(
                row,
                text=text,
                font=self.ui_fonts["body"],
                fg=UI_THEME["text"],
                bg=bg,
                justify="left",
                anchor="w",
                wraplength=540,
            )
            text_label.grid(row=0, column=0, sticky="ew")
            self.bind_preview_mousewheel(text_label)
            button_row = tk.Frame(row, bg=bg)
            button_row.grid(row=0, column=1, sticky="e", padx=(12, 0))
            self.bind_preview_mousewheel(button_row)

            buttons = []
            if entry.get("path"):
                buttons.extend(
                    [
                        ("Open", lambda current=entry["path"]: self.open_result_path(current), "#eff6ff", "#1d4ed8"),
                        ("Open Folder", lambda current=entry["path"]: self.open_result_folder(current), UI_THEME["surface_muted"], UI_THEME["text"]),
                        ("Copy Path", lambda current=entry["path"]: self.copy_result_path(current), UI_THEME["success_soft"], UI_THEME["success"]),
                    ]
                )
            buttons.append(("Copy Line", lambda current=text: self.copy_result_line(current), UI_THEME["surface_muted"], UI_THEME["text"]))

            for button_index, (label, callback, bg_color, fg_color) in enumerate(buttons):
                button = tk.Button(
                    button_row,
                    text=label,
                    command=callback,
                    font=self.ui_fonts["body_sm"],
                    bg=bg_color,
                    fg=fg_color,
                    relief=tk.FLAT,
                    padx=8,
                    pady=3,
                )
                button.grid(row=0, column=button_index, padx=(0, 6))
                if fg_color == UI_THEME["success"]:
                    self.apply_button_variant(button, "success")
                elif fg_color == UI_THEME["accent"]:
                    self.apply_button_variant(button, "accent")
                else:
                    self.apply_button_variant(button, "neutral")
                self.bind_preview_mousewheel(button)

    def render_preview_placeholder(self, message="Structured agent results appear here."):
        if not hasattr(self, "preview_body_frame") or not hasattr(self, "preview_title_var"):
            return
        self.preview_title_var.set("Result preview")
        self.preview_subtitle_var.set(message)
        self.clear_preview_panel()
        _, body = self.create_preview_card(
            self.preview_body_frame,
            title="Rogue is listening",
            subtitle="Run a folder summary, organization preview, workspace summary, or system-status command.",
            row=0,
            pady=(0, 0),
            bg=UI_THEME["surface_alt"],
        )
        self.create_selectable_text_block(
            body,
            "Agent sections will appear here as lightweight cards.\n\nUse help, scan downloads, scan desktop, or generate report to populate this area.",
            bg=UI_THEME["surface_alt"],
            row=0,
        )
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.yview_moveto(0)

    def render_preview_model(self, model):
        if not model or not hasattr(self, "preview_body_frame") or not hasattr(self, "preview_title_var"):
            return

        self.preview_title_var.set(model.get("title", "Result preview"))
        self.preview_subtitle_var.set(model.get("subtitle", ""))
        self.clear_preview_panel()

        row_index = 0
        rows = model.get("rows", [])
        if rows:
            _, summary_body = self.create_preview_card(
                self.preview_body_frame,
                title=model.get("title", "Result preview"),
                subtitle=model.get("subtitle", ""),
                row=row_index,
                pady=(0, 14),
            )
            self.render_preview_rows(summary_body, rows)
            row_index += 1

        for section in model.get("sections", []):
            _, section_body = self.create_preview_card(
                self.preview_body_frame,
                title=section.get("title", ""),
                subtitle=section.get("subtitle", ""),
                row=row_index,
                pady=(0, 14),
            )
            if section.get("entries"):
                self.render_preview_entries(section_body, section.get("entries", []), bg="#fbfcfe")
            else:
                section_text = "\n".join(section.get("lines", []))
                self.create_selectable_text_block(section_body, section_text, bg="#fbfcfe", row=0)
            row_index += 1

        footer = model.get("footer")
        if footer:
            _, footer_body = self.create_preview_card(
                self.preview_body_frame,
                title="Status",
                row=row_index,
                pady=(0, 0),
                bg=UI_THEME["success_soft"],
            )
            self.create_selectable_text_block(footer_body, footer, bg=UI_THEME["success_soft"], row=0)
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.yview_moveto(0)

    def build_preview_model(self, command_text, response_text):
        payload = getattr(self, "last_agent_workflow_payload", None)
        if not isinstance(payload, dict):
            structured = getattr(self, "last_structured_response_payload", None)
            if isinstance(structured, dict):
                return self.build_preview_from_structured_result(structured)
            return None

        payload_kind = payload.get("kind")
        if payload_kind == "agent_run":
            return self.build_preview_from_agent_result(payload.get("payload", {}))
        if payload_kind == "task_list":
            return self.build_task_list_preview(payload.get("tasks", []), payload.get("title", "Agent Tasks"))
        if payload_kind == "task_detail":
            task = payload.get("task")
            if task:
                return self.build_task_detail_preview(task)
        return None

    def build_preview_from_structured_result(self, payload):
        if not isinstance(payload, dict):
            return None

        action = payload.get("action", "result")
        rows = [
            ("Action", action),
            ("Success", "Yes" if payload.get("success") else "No"),
            ("Observed", len(payload.get("observed", []))),
            ("Warnings", len(payload.get("warnings", []))),
            ("Errors", len(payload.get("errors", []))),
        ]

        sections = []
        if payload.get("observed"):
            sections.append({"title": "Observed Facts", "lines": payload.get("observed", [])})
        if payload.get("artifacts"):
            artifact_entries = []
            for artifact in payload.get("artifacts", []):
                text = artifact.get("description") or artifact.get("path") or artifact.get("kind", "artifact")
                path_value = artifact.get("path")
                if artifact.get("verified") and artifact.get("exists") is True:
                    text = f"{text} | verified exists"
                elif artifact.get("verified") and artifact.get("exists") is False:
                    text = f"{text} | verified missing"
                artifact_entries.append({"text": text, "path": path_value if artifact.get("exists") else None})
            sections.append({"title": "Artifacts", "entries": artifact_entries})
        if payload.get("inferences"):
            sections.append({"title": "Inferences", "lines": payload.get("inferences", [])})
        if payload.get("suggestions"):
            sections.append({"title": "Suggestions", "lines": payload.get("suggestions", [])})
        if payload.get("warnings"):
            sections.append({"title": "Warnings", "lines": payload.get("warnings", [])})
        if payload.get("errors"):
            sections.append({"title": "Errors", "lines": payload.get("errors", [])})

        if not sections:
            sections.append({"title": "Observed Facts", "lines": ["No current analysis result is available."]})

        return {
            "title": action.replace("_", " ").title(),
            "subtitle": "Structured command result",
            "rows": rows,
            "sections": sections,
        }

    def build_preview_from_agent_result(self, payload):
        if not isinstance(payload, dict):
            return None

        goal = payload.get("goal", "").strip() or "Agent result"
        for item in reversed(payload.get("results", [])):
            result = item.get("result", {})
            if result.get("preview"):
                preview = result["preview"]
                rows = [
                    ("Scope", "recursive" if preview.get("included_subfolders") else "top-level only"),
                    ("Files analyzed", preview.get("total_files_analyzed", 0)),
                    ("Folders seen", preview.get("folder_entries_seen", 0)),
                ]
                sections = [
                    {
                        "title": "Top Categories",
                        "lines": [
                            f"{entry['category']}: {entry['count']}"
                            for entry in preview.get("top_categories", [])[:5]
                        ]
                        or ["No categories found."],
                    },
                    {
                        "title": "Sample Filenames",
                        "lines": [
                            f"{category}: {', '.join(names)}"
                            for category, names in preview.get("sample_filenames", {}).items()
                        ][:5]
                        or ["No sample filenames available."],
                    },
                ]
                return {
                    "title": self._friendly_preview_title(goal, fallback="Organization preview"),
                    "subtitle": Path(preview.get("path", "")).name or preview.get("path", ""),
                    "rows": rows,
                    "sections": sections,
                    "footer": "No files were modified.",
                }
            if result.get("summary"):
                summary = result["summary"]
                sections = [
                    {
                        "title": "Top File Types",
                        "entries": [
                            {"text": f"{entry['extension']}: {entry['count']}"}
                            for entry in summary.get("top_file_types", [])[:5]
                        ]
                        or [{"text": "No files found."}],
                    },
                    {
                        "title": "Largest Files",
                        "entries": [
                            {
                                "text": f"{entry['name']}: {entry['size_bytes']} bytes",
                                "path": entry.get("path"),
                            }
                            for entry in summary.get("largest_files", [])[:5]
                        ]
                        or [{"text": "No files found."}],
                    },
                    {
                        "title": "Newest Files",
                        "entries": [
                            {
                                "text": f"{entry['name']}: {entry['modified']}",
                                "path": entry.get("path"),
                            }
                            for entry in summary.get("newest_files", [])[:5]
                        ]
                        or [{"text": "No files found."}],
                    },
                ]
                return {
                    "title": self._friendly_preview_title(goal, fallback="Folder summary"),
                    "subtitle": Path(summary.get("path", "")).name or summary.get("path", ""),
                    "rows": [
                        ("Files", summary.get("total_files", 0)),
                        ("Directories", summary.get("total_directories", 0)),
                        ("Size", summary.get("total_size_human", "0 B")),
                    ],
                    "sections": sections,
                    "footer": "No files were modified.",
                }
            if result.get("report"):
                report = result["report"]
                system_info = self.parse_system_info_result(report.get("system_info", {}).get("result", ""))
                folder_summaries = report.get("folder_summaries", {})
                return {
                    "title": self._friendly_preview_title(goal, fallback="Workspace summary"),
                    "subtitle": "Workspace overview",
                    "rows": [
                        ("Platform", system_info.get("platform", "unknown")),
                        ("Projects", len(report.get("known_projects", []))),
                        ("Memory entries", len(report.get("recent_agent_memory", []))),
                        ("Downloads files", folder_summaries.get("downloads", {}).get("total_files", 0)),
                        ("Workspace files", folder_summaries.get("workspace", {}).get("total_files", 0)),
                    ],
                    "sections": [
                        {
                            "title": "Safe Aliases",
                            "lines": [", ".join(report.get("safe_folder_aliases", [])[:8]) or "None"],
                        },
                        {
                            "title": "Known Projects",
                            "lines": report.get("known_projects", [])[:8] or ["No projects found."],
                        }
                    ],
                }
            if result.get("inspection"):
                inspection = result["inspection"]
                return {
                    "title": self._friendly_preview_title(goal, fallback="Project inspection"),
                    "subtitle": inspection.get("project_name", ""),
                    "rows": [
                        ("Files", inspection.get("total_files", 0)),
                        ("Directories", inspection.get("total_directories", 0)),
                        ("README", ", ".join(inspection.get("readme_files", [])) or "None"),
                    ],
                    "sections": [
                        {
                            "title": "Top-level Entries",
                            "lines": inspection.get("top_level_entries", [])[:6] or ["No entries found."],
                        },
                        {
                            "title": "Languages",
                            "lines": [
                                f"{entry['language']}: {entry['count']}"
                                for entry in inspection.get("languages", [])[:6]
                            ]
                            or ["No languages detected."],
                        },
                        {
                            "title": "Largest Files",
                            "entries": [
                                {
                                    "text": f"{entry['name']}: {entry['size_bytes']} bytes",
                                    "path": entry.get("path"),
                                }
                                for entry in inspection.get("largest_files", [])[:5]
                            ]
                            or [{"text": "No files found."}],
                        },
                        {
                            "title": "Newest Files",
                            "entries": [
                                {
                                    "text": f"{entry['name']}: {entry['modified']}",
                                    "path": entry.get("path"),
                                }
                                for entry in inspection.get("newest_files", [])[:5]
                            ]
                            or [{"text": "No files found."}],
                        },
                    ],
                }

        if "system status" in goal.lower() or "diagnostics" in goal.lower() or "health" in goal.lower():
            return self.build_system_status_preview(payload)
        return None

    def build_system_status_preview(self, payload):
        rows = []
        project_lines = []
        note_lines = []
        for item in payload.get("results", []):
            result = item.get("result", {})
            action = result.get("action")
            if action == "get_system_info":
                system_info = self.parse_system_info_result(result.get("result", ""))
                rows.extend(
                    [
                        ("Platform", system_info.get("platform", "unknown")),
                        ("Python", system_info.get("python_version", "unknown")),
                        ("Workspace", system_info.get("cwd", "unknown")),
                    ]
                )
            elif action == "list_projects":
                project_lines = self.extract_bulleted_lines(result.get("result", ""))
            elif action == "list_saved_notes":
                note_lines = self.extract_bulleted_lines(result.get("result", ""))

        if not rows:
            return None
        return {
            "title": "System status",
            "subtitle": "Current Rogue environment",
            "rows": rows,
            "sections": [
                {"title": "Projects", "lines": project_lines[:5] or ["No projects listed."]},
                {"title": "Saved Notes", "lines": note_lines[:5] or ["No saved notes listed."]},
            ],
        }

    def build_task_list_preview(self, tasks, title):
        task_lines = []
        for task in tasks[:5]:
            summary = self.get_agent_task_manager().summarize_task(task)
            task_lines.append(f"Task {summary['task_id']} [{summary['status']}] - {summary['goal']}")
        return {
            "title": title,
            "subtitle": "Simple task list",
            "rows": [("Count", len(tasks))],
            "sections": [{"title": "Tasks", "lines": task_lines or ["No tasks found."]}],
        }

    def build_task_detail_preview(self, task):
        summary = self.get_agent_task_manager().summarize_task(task)
        return {
            "title": f"Task {summary['task_id']}",
            "subtitle": summary.get("goal", ""),
            "rows": [
                ("Status", summary.get("status", "unknown")),
                ("Step", f"{summary.get('current_step', 0)}/{summary.get('total_steps', 0)}"),
                ("Updated", summary.get("updated_at", "")),
            ],
            "sections": [
                {
                    "title": "Current step",
                    "lines": [summary.get("current_step_title") or "None"],
                }
            ],
        }

    def parse_system_info_result(self, result_text):
        if not result_text:
            return {}
        try:
            parsed = ast.literal_eval(str(result_text))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def extract_bulleted_lines(self, text):
        lines = []
        for raw_line in str(text).splitlines():
            cleaned = raw_line.strip()
            if cleaned.startswith("- "):
                lines.append(cleaned[2:])
        return lines

    def _friendly_preview_title(self, goal, fallback="Result preview"):
        lowered = str(goal).lower()
        if "desktop" in lowered and any(token in lowered for token in ["scan", "inspect", "organize", "summarize"]):
            return "Desktop analysis"
        if "downloads" in lowered and any(token in lowered for token in ["scan", "inspect", "organize", "summarize"]):
            return "Downloads analysis"
        return str(goal).strip().capitalize() or fallback

    def open_task_list_window(self):
        if self.task_window is None or not self.task_window.winfo_exists():
            self.task_window = tk.Toplevel(self.root)
            self.task_window.title("Agent tasks")
            self.task_window.geometry("520x360")
            self.task_window.configure(bg="#ffffff")
        self.render_task_list_window()
        self.task_window.lift()

    def render_task_list_window(self):
        if self.task_window is None or not self.task_window.winfo_exists():
            return

        for child in self.task_window.winfo_children():
            child.destroy()

        snapshot = self.get_agent_task_snapshot()
        tasks = snapshot.get("recent_tasks", [])

        tk.Label(
            self.task_window,
            text=self.task_indicator_var.get(),
            font=self.ui_fonts["header_sm"],
            fg="#0f172a",
            bg="#ffffff",
            padx=12,
            pady=12,
        ).grid(row=0, column=0, sticky="w")

        if not tasks:
            tk.Label(
                self.task_window,
                text="No agent tasks yet.",
                font=self.ui_fonts["body"],
                fg="#64748b",
                bg="#ffffff",
                padx=12,
                pady=8,
            ).grid(row=1, column=0, sticky="w")
            return

        body = tk.Frame(self.task_window, bg="#ffffff")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)

        manager = self.get_agent_task_manager()
        for index, task in enumerate(tasks[:8]):
            summary = manager.summarize_task(task)
            card = tk.Frame(body, bg="#f8fafc", bd=1, relief=tk.SOLID)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(
                card,
                text=f"Task {summary['task_id']} [{summary['status']}]",
                font=self.ui_fonts["body_bold"],
                fg="#1d4ed8",
                bg="#f8fafc",
                padx=10,
                pady=8,
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                card,
                text=summary["goal"],
                font=self.ui_fonts["body"],
                fg="#0f172a",
                bg="#f8fafc",
                justify="left",
                wraplength=380,
                padx=10,
            ).grid(row=1, column=0, sticky="ew", pady=(0, 8))
            tk.Button(
                card,
                text="Show",
                command=lambda task_id=summary["task_id"]: self.show_agent_task_details(task_id),
                bg="#eff6ff",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=10,
                pady=4,
            ).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))

    def get_suggestion_payload(self):
        payload = get_suggestions(
            downloads_path=Path.home() / "Downloads",
            home_path=Path.home(),
            projects_path=self.PROJECTS,
            logs_path=self.LOGS,
            backend_status=self.backend_status,
        )
        self.last_suggestions = payload.get("suggestions", [])
        return payload

    def refresh_suggestions(self):
        if not hasattr(self, "suggestions_frame"):
            return

        for child in self.suggestions_frame.winfo_children():
            child.destroy()

        payload = self.get_suggestion_payload()
        suggestions = payload.get("suggestions", [])
        if not suggestions:
            tk.Label(
                self.suggestions_frame,
                text="No active suggestions right now.",
                bg="#ffffff",
                fg="#475569",
                justify="left",
                anchor="w",
                padx=10,
                pady=8,
            ).grid(row=0, column=0, sticky="ew")
            return

        for index, suggestion in enumerate(suggestions[:3]):
            card = tk.Frame(self.suggestions_frame, bg="#ffffff", bd=1, relief=tk.SOLID, padx=8, pady=8)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=suggestion["title"], font=self.ui_fonts["body_bold"], bg="#ffffff", fg="#18212f").grid(row=0, column=0, sticky="w")
            tk.Label(
                card,
                text=suggestion["reason"],
                font=self.ui_fonts["body_sm"],
                bg="#ffffff",
                fg="#475569",
                justify="left",
                wraplength=220,
            ).grid(row=1, column=0, sticky="ew", pady=(4, 6))
            button_row = tk.Frame(card, bg="#ffffff")
            button_row.grid(row=2, column=0, sticky="w")
            tk.Button(
                button_row,
                text=suggestion["recommended_action"],
                command=lambda cmd=suggestion["suggested_command"]: self.handle_suggested_command(cmd),
                bg="#dbeafe",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=0, padx=(0, 6))
            tk.Button(
                button_row,
                text="Later",
                command=lambda sid=suggestion["id"]: self.dismiss_suggestion_ui(sid),
                bg="#e5e7eb",
                fg="#18212f",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=1)

    def get_agent_task_manager(self):
        if not hasattr(self, "agent_task_manager") or self.agent_task_manager is None:
            self.agent_task_manager = TaskManager(self.MEMORY)
        return self.agent_task_manager

    def get_agent_task_snapshot(self):
        manager = self.get_agent_task_manager()
        all_tasks = manager.list_tasks().get("tasks", [])
        active_tasks = manager.list_active_tasks().get("tasks", [])
        resumable_tasks = manager.list_resumable_tasks().get("tasks", [])
        recent_tasks = manager.list_recent_tasks(limit=6).get("tasks", [])
        completed_tasks = [task for task in all_tasks if task.get("status") == "completed"]
        return {
            "all_tasks": all_tasks,
            "active_tasks": active_tasks,
            "resumable_tasks": resumable_tasks,
            "recent_tasks": recent_tasks,
            "completed_tasks": completed_tasks,
        }

    def build_agent_task_status_summary(self):
        snapshot = self.get_agent_task_snapshot()
        return "\n".join(
            [
                "Agent task status summary",
                f"- Total tasks: {len(snapshot['all_tasks'])}",
                f"- Active tasks: {len(snapshot['active_tasks'])}",
                f"- Resumable tasks: {len(snapshot['resumable_tasks'])}",
                f"- Completed tasks: {len(snapshot['completed_tasks'])}",
            ]
        )

    def set_agent_task_view_mode(self, mode):
        self.agent_task_view_mode = mode
        self.render_agent_tasks_view()

    def show_agent_task_details(self, task_id):
        manager = self.get_agent_task_manager()
        payload = manager.get_task(task_id)
        if payload.get("success") and payload.get("task"):
            self.active_agent_task_context = payload["task"]
        message = payload.get("error", f"Task not found: {task_id}")
        if payload.get("success"):
            message = manager.format_task_detail(payload["task"])
        kind = "tool" if payload.get("success") else "warning"
        self.add_message("Rogue", message, kind=kind)
        if payload.get("success") and payload.get("task") and hasattr(self, "current_view_name"):
            self.show_secondary_view("agent_task_detail", self.build_task_detail_preview(payload["task"]))
        self.record_activity(
            "task",
            f"Viewed agent task {task_id}",
            command=f"agent show task {task_id}",
            tool="agent_task_manager",
            success=payload.get("success"),
        )

    def refresh_tasks_panel(self):
        if not hasattr(self, "tasks_frame"):
            return

        for child in self.tasks_frame.winfo_children():
            child.destroy()

        payload = list_tasks()
        tasks = payload.get("tasks", [])
        controls = tk.Frame(self.tasks_frame, bg="#eef2f7")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tk.Button(
            controls,
            text="Refresh Tasks",
            command=self.refresh_tasks_panel,
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=0, padx=(0, 6))
        tk.Button(
            controls,
            text="List Tasks",
            command=lambda: self.run_router_command("list my Codex tasks", show_user=False),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=1)

        if not tasks:
            tk.Label(
                self.tasks_frame,
                text="No Codex tasks yet.",
                bg="#ffffff",
                fg="#475569",
                justify="left",
                anchor="w",
                padx=10,
                pady=8,
            ).grid(row=1, column=0, sticky="ew")
            return

        for index, task in enumerate(reversed(tasks[-3:]), start=1):
            card = tk.Frame(self.tasks_frame, bg="#ffffff", bd=1, relief=tk.SOLID, padx=8, pady=8)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=f"#{task['id']} [{task['status']}]", font=self.ui_fonts["body_bold"], bg="#ffffff", fg="#1d4ed8").grid(row=0, column=0, sticky="w")
            tk.Label(card, text=task["title"], font=self.ui_fonts["body"], bg="#ffffff", fg="#18212f", wraplength=220, justify="left").grid(row=1, column=0, sticky="ew", pady=(4, 6))
            tk.Button(
                card,
                text="View",
                command=lambda task_id=task["id"]: self.show_task_details(task_id),
                bg="#dbeafe",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=2, column=0, sticky="w")

    def clear_sidebar_body(self):
        for child in self.sidebar_body_frame.winfo_children():
            child.destroy()

    def set_nav_active(self, view_name):
        for name, button in self.nav_buttons.items():
            if name == view_name:
                button.config(bg="#dbeafe", fg="#1d4ed8")
            else:
                button.config(bg="#ffffff", fg="#18212f")

    def show_sidebar_view(self, view_name):
        self.active_sidebar_view = view_name
        self.set_nav_active(view_name)
        renderers = {
            "quick_actions": self.render_quick_actions_view,
            "suggestions": self.render_suggestions_view,
            "memory": self.render_memory_view,
            "move_history": self.render_move_history_view,
            "agent_tasks": self.render_agent_tasks_view,
            "tasks": self.render_tasks_view,
            "diagnostics": self.render_diagnostics_view,
        }
        renderer = renderers.get(view_name, self.render_quick_actions_view)
        renderer()

    def _render_sidebar_text_block(self, text, height=16):
        widget = scrolledtext.ScrolledText(
            self.sidebar_body_frame,
            wrap=tk.WORD,
            font=self.ui_fonts["body"],
            bg="#f8fafc",
            fg="#1f2937",
            bd=0,
            relief=tk.FLAT,
            height=height,
            padx=10,
            pady=10,
        )
        widget.grid(row=0, column=0, sticky="nsew")
        widget.insert("1.0", text)
        widget.config(state=tk.DISABLED)
        self.configure_output_text_widget(widget)
        return widget

    def render_quick_actions_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Quick Actions")
        self.sidebar_subtitle_var.set("Common router-backed actions, grouped for faster navigation.")
        actions = [
            ("Scan Downloads", lambda: self.run_router_command("scan my downloads")),
            ("Organize Downloads", lambda: self.run_router_command("organize my downloads")),
            ("Scan Home Workspace", lambda: self.run_router_command("scan my home workspace")),
            ("Agent System Status", lambda: self.run_router_command("agent report system status")),
            ("Recent Agent Tasks", lambda: self.show_sidebar_view("agent_tasks")),
            ("List Agent Tasks", lambda: self.run_router_command("agent list tasks")),
            ("Open Google", lambda: self.run_router_command("open google")),
            ("Search Tkinter Docs", lambda: self.run_router_command("search for python tkinter docs")),
            ("Show Memory Notes", lambda: self.run_router_command("list my saved notes")),
            ("List Codex Tasks", lambda: self.run_router_command("list my Codex tasks")),
            ("Diagnostics", self.show_diagnostics_panel),
            ("Open Logs", self.open_logs_file),
        ]
        for index, (label, callback) in enumerate(actions):
            tk.Button(
                self.sidebar_body_frame,
                text=label,
                command=callback,
                bg="#eff6ff" if index < 3 else "#ffffff",
                fg="#1d4ed8" if index < 3 else "#18212f",
                relief=tk.FLAT,
                anchor="w",
                padx=12,
                pady=9,
            ).grid(row=index, column=0, sticky="ew", pady=(0, 8))

    def render_suggestions_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Suggested Actions")
        self.sidebar_subtitle_var.set("Review-first recommendations based on local state checks.")
        suggestions = self.get_suggestion_payload().get("suggestions", [])
        if not suggestions:
            self._render_sidebar_text_block("No active suggestions right now.", height=8)
            return
        for index, suggestion in enumerate(suggestions[:5]):
            card = tk.Frame(self.sidebar_body_frame, bg="#ffffff", bd=1, relief=tk.SOLID, padx=8, pady=8)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=suggestion["title"], font=self.ui_fonts["body_bold"], bg="#ffffff", fg="#18212f").grid(row=0, column=0, sticky="w")
            tk.Label(card, text=suggestion["reason"], font=self.ui_fonts["body_sm"], bg="#ffffff", fg="#64748b", wraplength=280, justify="left").grid(row=1, column=0, sticky="ew", pady=(4, 6))
            row = tk.Frame(card, bg="#ffffff")
            row.grid(row=2, column=0, sticky="w")
            tk.Button(
                row,
                text=suggestion["recommended_action"],
                command=lambda cmd=suggestion["suggested_command"]: self.handle_suggested_command(cmd),
                bg="#dbeafe",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=0, padx=(0, 6))
            tk.Button(
                row,
                text="Later",
                command=lambda sid=suggestion["id"]: self.dismiss_suggestion_ui(sid),
                bg="#e5e7eb",
                fg="#18212f",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=1)

    def render_memory_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Saved Memory Notes")
        self.sidebar_subtitle_var.set("Persistent notes loaded from the current local memory store.")
        payload = list_memory_notes()
        text = payload.get("result") if payload.get("success") else payload.get("error", "Could not load notes.")
        self._render_sidebar_text_block(text, height=14)

    def render_move_history_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Recent File Move History")
        self.sidebar_subtitle_var.set("Recent organized file moves from the persistent move history store.")
        payload = list_file_moves(limit=15)
        text = payload.get("result") if payload.get("success") else payload.get("error", "No file move history available.")
        self._render_sidebar_text_block(text, height=14)

    def render_agent_tasks_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Agent Tasks")
        self.sidebar_subtitle_var.set("Read-only visibility into recent, active, and resumable agent workflow tasks.")
        snapshot = self.get_agent_task_snapshot()
        mode_map = {
            "recent": ("Recent Agent Tasks", snapshot["recent_tasks"]),
            "active": ("Active Agent Tasks", snapshot["active_tasks"]),
            "resumable": ("Resumable Agent Tasks", snapshot["resumable_tasks"]),
        }
        current_title, tasks = mode_map.get(self.agent_task_view_mode, mode_map["recent"])

        controls = tk.Frame(self.sidebar_body_frame, bg="#ffffff")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Button(
            controls,
            text="Refresh",
            command=self.render_agent_tasks_view,
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=0, padx=(0, 6))
        tk.Button(
            controls,
            text="Recent",
            command=lambda: self.set_agent_task_view_mode("recent"),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=1, padx=(0, 6))
        tk.Button(
            controls,
            text="Active",
            command=lambda: self.set_agent_task_view_mode("active"),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=2, padx=(0, 6))
        tk.Button(
            controls,
            text="Resumable",
            command=lambda: self.set_agent_task_view_mode("resumable"),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=3, padx=(0, 6))
        tk.Button(
            controls,
            text="List in Chat",
            command=lambda: self.run_router_command(f"agent {self.agent_task_view_mode} tasks", show_user=False),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=4)

        summary = tk.Label(
            self.sidebar_body_frame,
            text=self.build_agent_task_status_summary(),
            font=self.ui_fonts["body_sm"],
            bg="#f8fafc",
            fg="#475569",
            justify="left",
            anchor="w",
            padx=10,
            pady=10,
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        if not tasks:
            tk.Label(
                self.sidebar_body_frame,
                text=f"{current_title}\n- None found.",
                font=self.ui_fonts["body"],
                bg="#ffffff",
                fg="#475569",
                justify="left",
                anchor="w",
                padx=10,
                pady=10,
            ).grid(row=2, column=0, sticky="ew")
            return

        manager = self.get_agent_task_manager()
        for index, task in enumerate(tasks[:6], start=2):
            summary_payload = manager.summarize_task(task)
            card = tk.Frame(self.sidebar_body_frame, bg="#f8fafc", bd=1, relief=tk.SOLID, padx=8, pady=8)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(
                card,
                text=f"Task {summary_payload['task_id']}  [{summary_payload['status']}]",
                font=self.ui_fonts["body_bold"],
                bg="#f8fafc",
                fg="#1d4ed8",
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                card,
                text=summary_payload["goal"],
                font=self.ui_fonts["body"],
                bg="#f8fafc",
                fg="#18212f",
                wraplength=280,
                justify="left",
            ).grid(row=1, column=0, sticky="ew", pady=(4, 6))
            tk.Label(
                card,
                text=(
                    f"Step {summary_payload['current_step']}/{summary_payload['total_steps']} | "
                    f"Updated {summary_payload['updated_at']}"
                ),
                font=self.ui_fonts["body_sm"],
                bg="#f8fafc",
                fg="#64748b",
            ).grid(row=2, column=0, sticky="w", pady=(0, 6))
            actions = tk.Frame(card, bg="#f8fafc")
            actions.grid(row=3, column=0, sticky="w")
            tk.Button(
                actions,
                text="View details",
                command=lambda task_id=summary_payload["task_id"]: self.show_agent_task_details(task_id),
                bg="#dbeafe",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=0, padx=(0, 6))
            tk.Button(
                actions,
                text="Show in Chat",
                command=lambda task_id=summary_payload["task_id"]: self.run_router_command(f"agent show task {task_id}", show_user=False),
                bg="#f3f4f6",
                fg="#18212f",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=1)

    def render_tasks_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Codex Tasks")
        self.sidebar_subtitle_var.set("Recent engineering requests with status and quick task inspection.")
        payload = list_tasks()
        tasks = payload.get("tasks", [])
        controls = tk.Frame(self.sidebar_body_frame, bg="#ffffff")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Button(
            controls,
            text="Refresh",
            command=self.render_tasks_view,
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=0, padx=(0, 6))
        tk.Button(
            controls,
            text="List in Chat",
            command=lambda: self.run_router_command("list my Codex tasks", show_user=False),
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=1)
        if not tasks:
            self._render_sidebar_text_block("No Codex tasks yet.", height=8)
            return
        for index, task in enumerate(reversed(tasks[-6:]), start=1):
            card = tk.Frame(self.sidebar_body_frame, bg="#f8fafc", bd=1, relief=tk.SOLID, padx=8, pady=8)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=f"#{task['id']}  [{task['status']}]", font=self.ui_fonts["body_bold"], bg="#f8fafc", fg="#1d4ed8").grid(row=0, column=0, sticky="w")
            tk.Label(card, text=task["title"], font=self.ui_fonts["body"], bg="#f8fafc", fg="#18212f", wraplength=280, justify="left").grid(row=1, column=0, sticky="ew", pady=(4, 6))
            tk.Label(card, text=f"{task['type']} | {task['created_at']}", font=self.ui_fonts["body_sm"], bg="#f8fafc", fg="#64748b").grid(row=2, column=0, sticky="w", pady=(0, 6))
            actions = tk.Frame(card, bg="#f8fafc")
            actions.grid(row=3, column=0, sticky="w")
            tk.Button(
                actions,
                text="View details",
                command=lambda task_id=task["id"]: self.show_task_details(task_id),
                bg="#dbeafe",
                fg="#1d4ed8",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=0, sticky="w", padx=(0, 6))
            tk.Button(
                actions,
                text="Copy Prompt",
                command=lambda task_id=task["id"]: self.handle_copy_result(self.copy_task_prompt(task_id)),
                bg="#dcfce7",
                fg="#166534",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=1, sticky="w", padx=(0, 6))
            tk.Button(
                actions,
                text="Copy Summary",
                command=lambda task_id=task["id"]: self.handle_copy_result(self.copy_task_summary(task_id)),
                bg="#f3f4f6",
                fg="#18212f",
                relief=tk.FLAT,
                padx=8,
            ).grid(row=0, column=2, sticky="w")

    def build_diagnostics_text(self):
        suggestion_payload = self.get_suggestion_payload()
        agent_snapshot = self.get_agent_task_snapshot()
        return "\n".join(
            [
                "ROGUE DESKTOP DIAGNOSTICS",
                f"Backend mode: {self.get_backend_mode_label()}",
                f"Configured model: {self.backend_status.get('model', 'unknown')}",
                f"Memory enabled: {bool(self.modules.get('memory'))}",
                f"Tools loaded: {bool(self.modules.get('tools'))}",
                "Browser control available: True",
                "Proactive assistant enabled: True",
                f"Current suggestion count: {len(suggestion_payload.get('suggestions', []))}",
                "Engineering task queue enabled: True",
                f"Current engineering task count: {len(list_tasks().get('tasks', []))}",
                "Agent task visibility enabled: True",
                f"Current agent task count: {len(agent_snapshot.get('all_tasks', []))}",
                f"Current agent active count: {len(agent_snapshot.get('active_tasks', []))}",
                f"Current agent resumable count: {len(agent_snapshot.get('resumable_tasks', []))}",
                "Clipboard handoff available: True",
                f"Projects folder items: {self.count_items(self.PROJECTS)}",
                f"Memory folder items: {self.count_items(self.MEMORY)}",
                f"Logs file: {BRAIN_LOG}",
                f"Backend details: {self.backend_status.get('message', 'n/a')}",
            ]
        )

    def render_diagnostics_view(self):
        self.clear_sidebar_body()
        self.sidebar_title_var.set("Logs / Diagnostics")
        self.sidebar_subtitle_var.set("Current desktop diagnostics and quick access to runtime logs.")
        controls = tk.Frame(self.sidebar_body_frame, bg="#ffffff")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Button(
            controls,
            text="Refresh Diagnostics",
            command=self.render_diagnostics_view,
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=0, padx=(0, 6))
        tk.Button(
            controls,
            text="Open Logs",
            command=self.open_logs_file,
            bg="#ffffff",
            fg="#18212f",
            relief=tk.FLAT,
            padx=8,
        ).grid(row=0, column=1)
        widget = scrolledtext.ScrolledText(
            self.sidebar_body_frame,
            wrap=tk.WORD,
            font=self.ui_fonts["body"],
            bg="#f8fafc",
            fg="#1f2937",
            bd=0,
            relief=tk.FLAT,
            height=14,
            padx=10,
            pady=10,
        )
        widget.grid(row=1, column=0, sticky="nsew")
        widget.insert("1.0", self.build_diagnostics_text())
        widget.config(state=tk.DISABLED)
        self.configure_output_text_widget(widget)

    def get_backend_mode_label(self):
        if self.backend_status.get("reachable") and self.backend_status.get("model_available"):
            return "Ollama-backed"
        return "Router-only"

    def set_last_action(self, summary):
        self.last_action_var.set(summary[:80])

    def classify_message(self, sender, message):
        lowered = str(message).lower()
        if sender.lower() in {"tú", "tu", "you"}:
            return "user"
        if "confirm with:" in lowered or "confirmation required" in lowered or "preview only" in lowered:
            return "confirm"
        if "diagnostics" in lowered or "startup check" in lowered or "backend:" in lowered:
            return "diagnostics"
        if "error" in lowered or "no pude" in lowered or "failed" in lowered or "warning" in lowered:
            return "warning"
        if any(token in lowered for token in ["open_", "apply_", "preview_", "get_system_info", "list_moves", "find_move_by_name"]):
            return "tool"
        return "assistant"

    def summarize_action_from_text(self, message):
        lowered = str(message).lower()
        if "preview_download_organization" in lowered:
            return "Previewed downloads organization"
        if "apply_download_organization" in lowered:
            return "Organized downloads"
        if "preview_home_workspace_organization" in lowered:
            return "Previewed home workspace"
        if "apply_home_workspace_organization" in lowered:
            return "Organized home workspace"
        if "open_folder" in lowered:
            return "Opened folder"
        if "open_application" in lowered:
            return "Opened application"
        if "record_moves" in lowered or "list_moves" in lowered or "find_move_by_name" in lowered:
            return "Reviewed file move history"
        if "diagnostics" in lowered:
            return "Viewed diagnostics"
        if "saved" in lowered or "guard" in lowered:
            return "Saved memory note"
        return str(message).splitlines()[0][:80]

    def detect_user_correction_signal(self, text):
        lowered = str(text or "").strip().lower()
        signal_map = {
            "too technical": "response too technical",
            "be simpler": "response too technical",
            "simpler": "response too technical",
            "that is wrong": "incorrect response",
            "that's wrong": "incorrect response",
            "not what i asked": "response missed user intent",
            "you missed": "response missed user intent",
            "retry": "user requested retry",
            "try again": "user requested retry",
        }
        for marker, symptom in signal_map.items():
            if marker in lowered:
                return symptom
        return ""

    def observe_friction(self, area, trigger, symptom, command="", impact=1, frequency_hint=1, raw_context="", metadata=None):
        observer = getattr(self, "improvement_observer", None)
        if observer is None:
            return None
        try:
            return observer.log_event(
                area=area,
                trigger=trigger,
                command=command,
                symptom=symptom,
                impact=impact,
                frequency_hint=frequency_hint,
                raw_context=raw_context,
                metadata=metadata or {},
            )
        except Exception:
            return None

    def get_improvement_dashboard_summary(self, limit=5):
        return self.improvement_runtime.build_dashboard_summary(limit=limit)

    def _is_improvement_execution_enabled(self):
        return is_improvement_execution_enabled(self.settings)

    def update_confirmation_ui(self):
        action_type = self.pending_action["type"] if self.pending_action else None

        if action_type == "organize_downloads":
            self.confirmation_var.set(
                "Preview ready for downloads organization.\n"
                "No files moved yet.\n"
                "Use the button below or type: confirm organize downloads"
            )
            self.confirm_downloads_button.grid(row=0, column=0, padx=(0, 8))
            self.confirm_home_button.grid_remove()
            self.cancel_button.grid(row=0, column=2)
            self.confirmation_panel.grid()
            return

        if action_type == "organize_home_workspace":
            self.confirmation_var.set(
                "Preview ready for home workspace organization.\n"
                "No files moved yet.\n"
                "Use the button below or type: confirm organize home workspace"
            )
            self.confirm_home_button.grid(row=0, column=1, padx=(0, 8))
            self.confirm_downloads_button.grid_remove()
            self.cancel_button.grid(row=0, column=2)
            self.confirmation_panel.grid()
            return

        if action_type == "delete_path":
            self.confirmation_var.set("A delete action is waiting for confirmation. No changes made yet.")
            self.confirm_downloads_button.grid_remove()
            self.confirm_home_button.grid_remove()
            self.cancel_button.grid(row=0, column=2)
            self.confirmation_panel.grid()
            return

        self.confirmation_var.set("No pending confirmation.")
        self.confirm_downloads_button.grid_remove()
        self.confirm_home_button.grid_remove()
        self.cancel_button.grid_remove()
        self.confirmation_panel.grid_remove()

    def record_activity(self, kind, summary, command=None, tool=None, success=None):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "kind": kind,
            "summary": summary,
            "command": command,
            "tool": tool,
            "success": success,
        }
        self.activity_history.append(entry)
        self.activity_history = self.activity_history[-12:]
        if hasattr(self, "activity_list"):
            self.activity_list.delete(0, tk.END)
            for item in reversed(self.activity_history):
                status = "OK" if item["success"] is True else "ERR" if item["success"] is False else "..."
                command_text = f" | {item['command']}" if item.get("command") else ""
                tool_text = f" [{item['tool']}]" if item.get("tool") else ""
                line = f"{item['timestamp']} {status} {item['kind']}{tool_text} | {item['summary']}{command_text}"
                self.activity_list.insert(tk.END, line[:120])
        self.set_last_action(summary)
        self.refresh_task_indicator()
        if getattr(self, "task_window", None) is not None and self.task_window.winfo_exists():
            self.render_task_list_window()

    def clear_chat(self):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.delete("1.0", tk.END)
        self.chat_box.config(state=tk.DISABLED)
        self.add_message("Rogue", "Chat cleared.", kind="assistant")
        self.record_activity("ui", "Cleared chat")
        self.set_status_feedback("Done | Chat cleared", level="done")

    def sanitize_chat_message(self, message):
        text = str(message or "")
        if not text:
            return ""
        replacements = {
            "inspect_downloads": "Inspect downloads",
            "inspect_desktop": "Inspect desktop",
            "inspect_workspace": "Inspect workspace",
            "workspace_summary": "Workspace summary",
            "list_path": "List folder contents",
            "preview_folder_organization": "Preview folder organization",
            "apply_download_organization": "Organize downloads",
            "apply_home_workspace_organization": "Organize home workspace",
            "move_files": "Move files",
            "delete_files": "Delete files",
            "kill_process": "Stop process",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def save_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_message(self, sender, message, kind=None):
        if str(sender).lower() == "rogue":
            message = self.sanitize_chat_message(message)
        if kind is None:
            kind = self.classify_message(sender, message)

        header_tag = {
            "user": "header_user",
            "assistant": "header_assistant",
            "warning": "header_warning",
            "tool": "header_tool",
            "confirm": "header_confirm",
            "diagnostics": "header_diagnostics",
        }.get(kind, "header_assistant")
        body_tag = {
            "user": "body_user",
            "assistant": "body_assistant",
            "warning": "body_warning",
            "tool": "body_tool",
            "confirm": "body_confirm",
            "diagnostics": "body_diagnostics",
        }.get(kind, "body_assistant")

        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, f"{sender}\n", header_tag)
        self.chat_box.insert(tk.END, f"{message}\n\n", body_tag)
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.see(tk.END)

    def handle_enter(self, event):
        return self.execute_command()

    def send_message(self):
        return self.execute_command()

    def run_router_command(self, text, show_user=True):
        if show_user:
            self.add_message("Tú", text, kind="user")
        self.remember_turn("user", text)
        self.last_agent_workflow_payload = None
        self.last_structured_response_payload = None
        self.set_status_feedback(f"Running | {text}", level="running")
        correction_signal = self.detect_user_correction_signal(text)
        if correction_signal:
            self.observe_friction(
                area="chat_rendering",
                trigger="user_correction",
                command=text,
                symptom=correction_signal,
                impact=3,
                raw_context=text,
                metadata={"source": "user_input"},
            )

        try:
            response = self.process_input(text)
            self.update_confirmation_ui()

            if response == "__ASYNC__":
                self.observe_friction(
                    area="router",
                    trigger="fallback_to_llm",
                    command=text,
                    symptom="request required async fallback",
                    impact=2,
                    raw_context=text,
                    metadata={"path": "async_fallback"},
                )
                self.record_activity("llm", "Async fallback started", command=text, tool="llm", success=True)
                self.set_status_feedback("Running | Waiting for model response", level="running")
                return response

            message_kind = self.classify_message("Rogue", response)
            operator_summary = self.get_operator_summary()
            verification = operator_summary.get("verification", {})
            message_kind = verification.get("message_kind") or verification_status_to_message_kind(
                verification.get("status"),
                default=message_kind,
            )
            activity_summary = operator_summary.get("operator_summary_line") or self.summarize_action_from_text(response)
            if message_kind == "warning":
                self.observe_friction(
                    area="chat_backend",
                    trigger="unhelpful_output",
                    command=text,
                    symptom=self.summarize_action_from_text(response),
                    impact=3,
                    raw_context=response,
                    metadata={"source": "router_response"},
                )
            self.remember_turn("assistant", response)
            self.add_message("Rogue", response, kind=message_kind)
            preview_model = self.build_preview_model(text, response)
            if preview_model:
                self.show_dashboard_preview(preview_model)
            self.record_activity(
                message_kind,
                activity_summary,
                command=text,
                tool=message_kind,
                success=verification.get("status") not in {"blocked", "failed"},
            )
            status_level = verification.get("ui_level") or ("error" if message_kind == "warning" else "done")
            status_reason = verification.get("reason") or activity_summary
            if status_level == "error":
                self.set_status_feedback(f"Error | {status_reason}", level="error")
            elif status_level == "warning":
                self.set_status_feedback(f"Warning | {status_reason}", level="warning")
            elif status_level == "done":
                self.set_status_feedback(f"Done | {activity_summary}", level="done")
            else:
                self.set_status_feedback(f"Ready | {status_reason}", level=status_level)
            if hasattr(self, "command_entry"):
                self.command_entry.focus_set()
            return response

        except Exception as e:
            error_msg = f"Error interno procesando tu mensaje: {e}"
            self.log_action(error_msg)
            self.add_message("Rogue", error_msg, kind="warning")
            self.observe_friction(
                area="chat_backend",
                trigger="execution_failure",
                command=text,
                symptom="internal processing error",
                impact=5,
                raw_context=error_msg,
                metadata={"tool": "router"},
            )
            self.record_activity("warning", "Internal processing error", command=text, tool="router", success=False)
            self.set_status_feedback(f"Error | {error_msg}", level="error")
            return error_msg

    def handle_suggested_command(self, command):
        if command == "diagnostics":
            self.show_diagnostics_panel()
            return
        if command == "open logs":
            self.open_logs_file()
            return
        self.run_router_command(command, show_user=False)

    def dismiss_suggestion_ui(self, suggestion_id):
        dismiss_suggestion(suggestion_id)
        self.add_message("Rogue", f"Suggestion dismissed: {suggestion_id}", kind="tool")
        self.record_activity("suggestion", f"Dismissed {suggestion_id}", tool="proactive_helper", success=True)

    def handle_copy_result(self, payload):
        kind = "tool" if payload.get("success") else "warning"
        self.add_message("Rogue", payload.get("result") or payload.get("error"), kind=kind)
        if payload.get("success"):
            self.set_status_feedback(f"Done | {payload.get('result')}", level="done")
        else:
            self.set_status_feedback(f"Error | {payload.get('error')}", level="error")

    def show_task_details(self, task_id):
        payload = get_task(task_id)
        if payload.get("success") and payload.get("task"):
            self.active_task_context = payload["task"]
        kind = "tool" if payload.get("success") else "warning"
        self.add_message("Rogue", payload.get("result") or payload.get("error"), kind=kind)
        self.record_activity("task", f"Viewed task {task_id}", command=f"show task {task_id}", tool="task_queue", success=payload.get("success"))

    def copy_text_to_clipboard(self, text, label="clipboard text"):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text))
            self.root.update()
            self.set_status_feedback(f"Done | Copied {label}", level="done")
            return {
                "success": True,
                "action": "copy_to_clipboard",
                "result": f"Copied {label} to clipboard.",
                "error": None,
            }
        except Exception as e:
            self.set_status_feedback(f"Error | Clipboard unavailable: {e}", level="error")
            return {
                "success": False,
                "action": "copy_to_clipboard",
                "result": "",
                "error": f"Clipboard unavailable: {e}",
            }

    def open_result_path(self, path_value):
        try:
            target = Path(path_value)
            os.startfile(str(target))
            self.record_activity("tool", f"Open request sent for {target.name}", command=str(target), tool="result_actions", success=True)
            self.set_status_feedback(f"Done | Open request sent for {target.name}", level="done")
        except Exception as exc:
            self.record_activity("warning", "Result open failed", command=str(path_value), tool="result_actions", success=False)
            self.set_status_feedback(f"Error | Could not open path: {exc}", level="error")

    def open_result_folder(self, path_value):
        try:
            target = Path(path_value)
            folder = target if target.is_dir() else target.parent
            os.startfile(str(folder))
            self.record_activity("tool", f"Open request sent for folder {folder}", command=str(folder), tool="result_actions", success=True)
            self.set_status_feedback(f"Done | Open request sent for folder {folder}", level="done")
        except Exception as exc:
            self.record_activity("warning", "Result folder open failed", command=str(path_value), tool="result_actions", success=False)
            self.set_status_feedback(f"Error | Could not open folder: {exc}", level="error")

    def copy_result_path(self, path_value):
        self.copy_text_to_clipboard(path_value, label="file path")

    def copy_result_line(self, line_text):
        self.copy_text_to_clipboard(line_text, label="result line")

    def copy_task_prompt(self, task_id):
        payload = get_task(task_id)
        if not payload.get("success") or not payload.get("task"):
            return {
                "success": False,
                "action": "copy_task_prompt",
                "result": "",
                "error": payload.get("error", f"Task {task_id} not found."),
            }
        task = payload["task"]
        self.active_task_context = task
        clipboard_result = self.copy_text_to_clipboard(task.get("prompt_text", ""), label=f"task {task_id} prompt")
        if clipboard_result["success"]:
            self.record_activity("task", f"Copied prompt for task {task_id}", command=f"copy task {task_id} prompt", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_task_prompt",
                "result": f"Copied prompt for task {task_id} to clipboard.",
                "error": None,
                "task": task,
            }
        self.record_activity("warning", f"Clipboard failed for task {task_id}", command=f"copy task {task_id} prompt", tool="clipboard", success=False)
        return {
            "success": False,
            "action": "copy_task_prompt",
            "result": "",
            "error": clipboard_result["error"],
            "task": task,
        }

    def copy_current_task_prompt(self):
        task = self.active_task_context
        if not task:
            return {
                "success": False,
                "action": "copy_current_task_prompt",
                "result": "",
                "error": "No active task is currently selected.",
            }
        result = self.copy_text_to_clipboard(task.get("prompt_text", ""), label=f"task {task.get('id', '?')} prompt")
        if result["success"]:
            self.record_activity("task", f"Copied current task {task.get('id', '?')} prompt", command="copy current task prompt", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_current_task_prompt",
                "result": f"Copied current task {task.get('id', '?')} prompt to clipboard.",
                "error": None,
                "task": task,
            }
        self.record_activity("warning", "Clipboard failed for current task prompt", command="copy current task prompt", tool="clipboard", success=False)
        return {
            "success": False,
            "action": "copy_current_task_prompt",
            "result": "",
            "error": result["error"],
            "task": task,
        }

    def copy_task_summary(self, task_id):
        payload = get_task(task_id)
        if not payload.get("success") or not payload.get("task"):
            return {
                "success": False,
                "action": "copy_task_summary",
                "result": "",
                "error": payload.get("error", f"Task {task_id} not found."),
            }
        task = payload["task"]
        summary = f"Task {task['id']}: {task['title']}\nType: {task['type']}\nStatus: {task['status']}\nCreated: {task['created_at']}"
        result = self.copy_text_to_clipboard(summary, label=f"task {task_id} summary")
        if result["success"]:
            self.record_activity("task", f"Copied summary for task {task_id}", command=f"copy task {task_id} summary", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_task_summary",
                "result": f"Copied summary for task {task_id} to clipboard.",
                "error": None,
                "task": task,
            }
        return {
            "success": False,
            "action": "copy_task_summary",
            "result": "",
            "error": result["error"],
            "task": task,
        }

    def handle_ui_confirmation(self, target):
        if target == "downloads":
            self.run_router_command("confirm organize downloads", show_user=False)
        elif target == "home_workspace":
            self.run_router_command("confirm organize home workspace", show_user=False)

    def remember_turn(self, role, content):
        self.conversation_memory.append({"role": role, "content": content})
        max_turns = int(self.settings.get("max_memory_turns", 12))
        self.conversation_memory = self.conversation_memory[-max_turns:]

    def process_input(self, text):
        return self.get_operator_brain().handle_request(text)

    def get_operator_brain(self):
        if getattr(self, "operator_brain", None) is None:
            self.operator_brain = OperatorBrain(self)
        return self.operator_brain

    def get_operator_summary(self):
        return self.get_operator_brain().get_operator_summary()

    def ask_llm_safe(self, prompt, recent_context):
        try:
            response = _ask_llm(prompt, recent_context)
            if not isinstance(response, str):
                return str(response)
            cleaned = response.strip()
            if "router-only mode" in cleaned.lower():
                self.log_action(f"LLM degraded mode used for prompt: {prompt[:80]}")
            return cleaned if cleaned else "No recibí una respuesta válida del modelo."
        except Exception as e:
            self.log_action(f"LLM backend error: {e}")
            return f"No pude consultar el backend LLM: {e}"

    def open_notes_file(self):
        try:
            self.MEMORY.mkdir(parents=True, exist_ok=True)
            if not NOTES_FILE.exists():
                NOTES_FILE.write_text("", encoding="utf-8")
            os.startfile(str(NOTES_FILE))
            self.log_action("Notes file opened")
            self.record_activity("tool", "Opened notes file", tool="memory", success=True)
            self.set_status_feedback("Done | Opened notes", level="done")
            return "Listo. Ya abrí tu archivo de notas."
        except Exception as e:
            self.set_status_feedback(f"Error | No pude abrir tus notas: {e}", level="error")
            return f"No pude abrir tus notas: {e}"

    def open_logs_file(self):
        try:
            self.LOGS.mkdir(parents=True, exist_ok=True)
            if not BRAIN_LOG.exists():
                BRAIN_LOG.write_text("", encoding="utf-8")
            os.startfile(str(BRAIN_LOG))
            self.log_action("Log file opened")
            self.record_activity("tool", "Opened logs", tool="logs", success=True)
            self.add_message("Rogue", f"Log file opened:\n{BRAIN_LOG}", kind="tool")
            self.set_status_feedback("Done | Opened logs", level="done")
        except Exception as e:
            self.add_message("Rogue", f"No pude abrir el log: {e}", kind="warning")
            self.set_status_feedback(f"Error | No pude abrir el log: {e}", level="error")

    def show_diagnostics_panel(self):
        self.backend_status = get_ollama_status()
        self.refresh_status_bar()
        message = self.build_diagnostics_text()
        self.log_action("Desktop diagnostics viewed")
        self.add_message("Rogue", message, kind="diagnostics")
        self.record_activity("diagnostics", "Viewed desktop diagnostics", tool="diagnostics", success=True)
        self.set_status_feedback("Done | Diagnostics refreshed", level="done")

    def start_async_fallback(self, text):
        self.set_busy(True, "Thinking...")
        worker = threading.Thread(
            target=self._background_fallback,
            args=(text,),
            daemon=True
        )
        worker.start()

    def _background_fallback(self, text):
        recent = self.get_recent_context_list()
        response = self.ask_llm_safe(text, recent)
        self.root.after(0, lambda: self.finish_async_response(response))

    def finish_async_response(self, response):
        self.remember_turn("assistant", response)
        message_kind = self.classify_message("Rogue", response)
        if message_kind == "warning":
            self.observe_friction(
                area="chat_backend",
                trigger="unhelpful_output",
                symptom=self.summarize_action_from_text(response),
                impact=3,
                raw_context=response,
                metadata={"source": "llm_response"},
            )
        self.add_message("Rogue", response, kind=message_kind)
        self.record_activity(message_kind, self.summarize_action_from_text(response), tool="llm", success=message_kind != "warning")
        self.set_busy(False, "Done | Response ready")

    def get_recent_context_list(self):
        if not self.conversation_memory:
            return []

        lines = []
        for item in self.conversation_memory[-6:]:
            role = "User" if item["role"] == "user" else "Assistant"
            lines.append(f"{role}: {item['content']}")
        return lines

    def get_recent_context_text(self):
        if not self.conversation_memory:
            return "sin contexto reciente"

        last_items = self.conversation_memory[-4:]
        lines = []
        for item in last_items:
            role = "Tú" if item["role"] == "user" else "Rogue"
            lines.append(f"- {role}: {item['content'][:120]}")
        return "\n".join(lines)

    def count_items(self, folder):
        if folder.exists() and folder.is_dir():
            return len(list(folder.iterdir()))
        return 0

    def set_busy(self, busy, status_text=None):
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        if hasattr(self, "clear_chat_button"):
            self.clear_chat_button.config(state=state)
        if hasattr(self, "command_entry"):
            self.command_entry.config(state=state)
        if hasattr(self, "execute_button"):
            self.execute_button.config(state=state)

        if status_text:
            self.set_status_feedback(status_text, level="running" if busy else "done")
        else:
            self.set_status_feedback("Running | Thinking..." if busy else "Ready", level="running" if busy else "ready")

        if not busy and hasattr(self, "command_entry"):
            self.command_entry.focus_set()

    def log_action(self, action):
        try:
            self.LOGS.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(BRAIN_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{now}] {action}\n")
        except Exception:
            pass


def _launch_legacy_tk_app():
    root = tk.Tk()
    app = RogueApp(root)
    root.mainloop()
    return app


def _import_qt_launcher():
    from ui_qt.main_window import launch_qt_app

    return launch_qt_app


def _is_pyside6_missing(exc):
    module_name = str(getattr(exc, "name", "") or "").strip()
    return module_name == "PySide6" or module_name.startswith("PySide6.")


def _report_pyside6_unavailable(exc):
    print(f"PySide6 import failed: {exc.__class__.__name__}: {exc}")
    print("PySide6 is unavailable. Falling back to the legacy Tkinter desktop.")


def launch_desktop_app(prefer_qt=True):
    ui_mode = os.environ.get("ROGUE_UI", "").strip().lower()
    if ui_mode in {"tk", "tkinter", "legacy"}:
        return _launch_legacy_tk_app()

    if prefer_qt:
        try:
            launch_qt_app = _import_qt_launcher()
        except ModuleNotFoundError as exc:
            if not _is_pyside6_missing(exc):
                raise
            _report_pyside6_unavailable(exc)
        else:
            try:
                return launch_qt_app()
            except Exception as exc:
                print(f"PySide6 startup failed: {exc.__class__.__name__}: {exc}")
                raise

    return _launch_legacy_tk_app()


if __name__ == "__main__":
    try:
        launch_desktop_app(prefer_qt=True)
    except Exception as e:
        print(f"Rogue desktop startup failed: {e}")
        traceback.print_exc()
        raise
