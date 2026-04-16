import json
import io
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app_config import (
    ConfigError,
    StartupCheckError,
    load_or_create_modules,
    load_or_create_settings,
    run_startup_checks,
)
from brain.agent_state import AgentState
from brain.llm_bridge import get_ollama_status
from brain.router import handle_confirmation
from rogue_app import DEFAULT_WINDOW_GEOMETRY, MIN_WINDOW_SIZE, RogueApp
from task_manager import TaskManager

_BRAIN_CLI_SPEC = importlib.util.spec_from_file_location("brain_cli_module", Path(__file__).resolve().parent.parent / "brain.py")
brain_cli = importlib.util.module_from_spec(_BRAIN_CLI_SPEC)
_BRAIN_CLI_SPEC.loader.exec_module(brain_cli)


class DummyRoot:
    def __init__(self):
        self.geometry_value = ""

    def title(self, *_args, **_kwargs):
        pass

    def geometry(self, value=None):
        if value is None:
            return self.geometry_value
        self.geometry_value = value

    def minsize(self, *_args, **_kwargs):
        pass

    def after(self, _delay, callback):
        callback()


class FakeLabel:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class FakeWidgetTree:
    def __init__(self, *children):
        self.children = list(children)

    def winfo_children(self):
        return list(self.children)


class FakeCanvas:
    def __init__(self, bbox_value=(0, 0, 640, 1200)):
        self.bbox_value = bbox_value
        self.scroll_calls = []
        self.config = {}
        self.item_config = {}

    def yview_scroll(self, direction, units):
        self.scroll_calls.append((direction, units))

    def bbox(self, _target):
        return self.bbox_value

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def itemconfigure(self, item, **kwargs):
        self.item_config[item] = kwargs


class FakeTextWidget:
    def __init__(self, width=900):
        self.width = width
        self.config_state = {}
        self.tag_configs = {}
        self.insert_calls = []
        self.delete_calls = []
        self.see_calls = []

    def winfo_width(self):
        return self.width

    def tag_configure(self, tag_name, **kwargs):
        self.tag_configs[tag_name] = kwargs

    def config(self, **kwargs):
        self.config_state.update(kwargs)

    configure = config

    def insert(self, index, text, tag_name):
        self.insert_calls.append((index, text, tag_name))

    def delete(self, start, end):
        self.delete_calls.append((start, end))

    def see(self, index):
        self.see_calls.append(index)


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeFont:
    def __init__(self, size):
        self.size = size

    def cget(self, key):
        if key == "size":
            return self.size
        raise KeyError(key)


class StartupConfigTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.memory = self.base / "memory"
        self.projects = self.base / "projects"
        self.agents = self.base / "agents"
        self.autonomy = self.base / "autonomy"
        self.config = self.base / "config"
        self.logs = self.base / "logs"
        self.settings = self.config / "settings.json"
        self.modules = self.config / "modules.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_startup_checks_create_missing_folders_and_configs(self):
        report = run_startup_checks(
            required_folders=[
                self.memory,
                self.projects,
                self.agents,
                self.autonomy,
                self.config,
                self.logs,
            ],
            settings_path=self.settings,
            modules_path=self.modules,
        )
        self.assertTrue(self.settings.exists())
        self.assertTrue(self.modules.exists())
        self.assertEqual("Rogue Local", report["settings"]["app_name"])
        self.assertEqual("Light", report["settings"]["theme"])
        self.assertTrue(report["modules"]["memory"])

    def test_load_settings_rejects_malformed_values(self):
        self.config.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            json.dumps({"app_name": "Rogue Local", "max_memory_turns": "twelve"}),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigError):
            load_or_create_settings(self.settings)

    def test_load_settings_accepts_legacy_file_shape(self):
        self.config.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            json.dumps({"assistant_name": "Rogue Brain v2", "mode": "zaza"}),
            encoding="utf-8",
        )
        data = load_or_create_settings(self.settings)
        self.assertEqual("Rogue Brain v2", data["app_name"])
        self.assertEqual(12, data["max_memory_turns"])
        self.assertEqual("Light", data["theme"])

    def test_load_modules_rejects_missing_keys(self):
        self.config.mkdir(parents=True, exist_ok=True)
        self.modules.write_text(json.dumps({"memory": True}), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_or_create_modules(self.modules)

    def test_run_startup_checks_raises_clear_error_for_invalid_config(self):
        self.config.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{invalid", encoding="utf-8")
        with self.assertRaises(StartupCheckError):
            run_startup_checks(
                required_folders=[self.config],
                settings_path=self.settings,
                modules_path=self.modules,
            )


class RogueAppBehaviorTests(unittest.TestCase):
    def test_home_layout_window_defaults_match_stabilized_targets(self):
        self.assertEqual("1360x860", DEFAULT_WINDOW_GEOMETRY)
        self.assertEqual((1024, 680), MIN_WINDOW_SIZE)

    def test_select_ui_font_family_prefers_segoe_ui_then_fallbacks(self):
        self.assertEqual("Segoe UI", RogueApp.select_ui_font_family(["Arial", "Inter", "Segoe UI"]))
        self.assertEqual("Segoe UI", RogueApp.select_ui_font_family(["Calibri", "Segoe UI"]))
        self.assertEqual("TkDefaultFont", RogueApp.select_ui_font_family(["Calibri"]))

    def test_handle_home_mousewheel_scrolls_canvas(self):
        app = object.__new__(RogueApp)
        app.home_canvas = FakeCanvas()

        up_result = RogueApp.handle_home_mousewheel(app, type("Event", (), {"delta": 120})())
        down_result = RogueApp.handle_home_mousewheel(app, type("Event", (), {"delta": -120})())

        self.assertEqual("break", up_result)
        self.assertEqual("break", down_result)
        self.assertEqual([(-1, "units"), (1, "units")], app.home_canvas.scroll_calls)

    def test_on_home_canvas_configure_updates_width_and_scroll_region(self):
        app = object.__new__(RogueApp)
        app.home_canvas = FakeCanvas(bbox_value=(0, 0, 720, 1800))
        app.home_canvas_window = "home-window"

        RogueApp.on_home_canvas_configure(app, type("Event", (), {"width": 900})())

        self.assertEqual({"width": 900}, app.home_canvas.item_config["home-window"])
        self.assertEqual((0, 0, 720, 1800), app.home_canvas.config["scrollregion"])

    def test_refresh_home_scroll_bindings_skips_nested_preview_and_chat_targets(self):
        chat_child = FakeWidgetTree()
        preview_body_child = FakeWidgetTree()
        preview_canvas_child = FakeWidgetTree()
        normal_leaf = FakeWidgetTree()
        normal_branch = FakeWidgetTree(normal_leaf)
        chat_widget = FakeWidgetTree(chat_child)
        preview_canvas = FakeWidgetTree(preview_canvas_child)
        preview_body = FakeWidgetTree(preview_body_child)
        home_root = FakeWidgetTree(normal_branch, chat_widget, preview_canvas, preview_body)

        app = object.__new__(RogueApp)
        app.home_body_frame = home_root
        app.chat_box = chat_widget
        app.preview_canvas = preview_canvas
        app.preview_body_frame = preview_body
        bound = []
        app.bind_home_mousewheel = lambda widget: bound.append(widget)

        RogueApp.refresh_home_scroll_bindings(app)

        self.assertIn(home_root, bound)
        self.assertIn(normal_branch, bound)
        self.assertIn(normal_leaf, bound)
        self.assertNotIn(chat_widget, bound)
        self.assertNotIn(chat_child, bound)
        self.assertNotIn(preview_canvas, bound)
        self.assertNotIn(preview_canvas_child, bound)
        self.assertNotIn(preview_body, bound)
        self.assertNotIn(preview_body_child, bound)

    def test_ask_llm_safe_returns_readable_message_when_backend_raises(self):
        app = object.__new__(RogueApp)
        with patch("rogue_app._ask_llm", side_effect=RuntimeError("ollama down")):
            response = RogueApp.ask_llm_safe(app, "hola", [])
        self.assertIn("No pude consultar el backend LLM", response)
        self.assertIn("ollama down", response)

    def test_pending_confirmation_cancel_clears_action(self):
        app = type("PendingApp", (), {"pending_action": {"type": "delete_path", "path": "x"}})()
        response = handle_confirmation(app, "no")
        self.assertIn("cancelada", response)
        self.assertIsNone(app.pending_action)

    def test_run_startup_checks_method_wraps_config_failures(self):
        app = object.__new__(RogueApp)
        app.MEMORY = Path("memory")
        app.PROJECTS = Path("projects")
        app.AGENTS = Path("agents")
        app.AUTONOMY = Path("autonomy")
        app.CONFIG = Path("config")
        app.LOGS = Path("logs")
        with patch("rogue_app.run_startup_checks", side_effect=StartupCheckError("bad config")):
            with self.assertRaises(RuntimeError) as ctx:
                RogueApp.run_startup_checks(app)
        self.assertIn("Startup self-check failed", str(ctx.exception))

    def test_init_uses_startup_checks_before_ui(self):
        fake_report = {
            "created_folders": [],
            "settings": {"app_name": "Rogue Local", "max_memory_turns": 12, "theme": "Light"},
            "modules": {
                "memory": True,
                "projects": True,
                "agents": True,
                "tools": True,
                "autonomy": True,
            },
        }
        root = DummyRoot()
        fake_var = lambda *args, **kwargs: type("FakeVar", (), {"set": lambda self, value: None, "get": lambda self: kwargs.get("value", "")})()
        with patch.object(RogueApp, "run_startup_checks", return_value=fake_report), \
             patch("rogue_app.tk.StringVar", side_effect=fake_var), \
             patch("rogue_app.get_ollama_status", return_value={"message": "Ollama unavailable. Rogue will continue in router-only mode.", "reachable": False, "model_available": False, "model": "llama3:latest"}), \
             patch.object(RogueApp, "build_ui", return_value=None), \
             patch.object(RogueApp, "log_action", return_value=None), \
             patch.object(RogueApp, "add_message", return_value=None):
            app = RogueApp(root)
        self.assertEqual(12, app.settings["max_memory_turns"])
        self.assertTrue(app.modules["tools"])

    def test_normalize_theme_name_defaults_unknown_values_to_light(self):
        self.assertEqual("Dark", RogueApp.normalize_theme_name("dark"))
        self.assertEqual("Light", RogueApp.normalize_theme_name("unknown"))
        self.assertEqual("Light", RogueApp.normalize_theme_name(None))

    def test_refresh_settings_view_updates_theme_font_and_runtime_values(self):
        class FakeAgentState:
            def get_mode(self):
                return "assist"

        app = object.__new__(RogueApp)
        app.current_theme_name = "Dark"
        app.settings = {"theme": "Dark", "app_name": "Rogue Local", "max_memory_turns": 8}
        app.settings_theme_var = FakeVar()
        app.settings_value_vars = {
            "theme": FakeVar(),
            "font_size": FakeVar(),
            "default_mode": FakeVar(),
            "model_name": FakeVar(),
            "app_name": FakeVar(),
            "memory_turns": FakeVar(),
        }
        app.ui_fonts = {"body": FakeFont(12)}
        app.agent_state = FakeAgentState()
        app.backend_status = {"model": "llama3:latest"}
        app.get_agent_state = lambda: app.agent_state

        RogueApp.refresh_settings_view(app)

        self.assertEqual("Dark", app.settings_value_vars["theme"].get())
        self.assertEqual("Dark", app.settings_theme_var.get())
        self.assertEqual("12 pt", app.settings_value_vars["font_size"].get())
        self.assertEqual("Assist", app.settings_value_vars["default_mode"].get())
        self.assertEqual("llama3:latest", app.settings_value_vars["model_name"].get())
        self.assertEqual("Rogue Local", app.settings_value_vars["app_name"].get())
        self.assertEqual("8", app.settings_value_vars["memory_turns"].get())

    def test_save_settings_persists_selected_theme(self):
        with tempfile.TemporaryDirectory() as tempdir:
            settings_path = Path(tempdir) / "config" / "settings.json"
            app = object.__new__(RogueApp)
            app.settings = {"app_name": "Rogue Local", "max_memory_turns": 12, "theme": "Dark"}
            app.current_theme_name = "Dark"

            with patch("rogue_app.SETTINGS_FILE", settings_path):
                saved = RogueApp.save_settings(app)

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual("Dark", saved["theme"])
            self.assertEqual("Dark", payload["theme"])

    def test_resolve_brand_asset_path_prefers_configured_relative_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            asset = base / "Images" / "rogue_logo.gif"
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(b"GIF89a")

            app = object.__new__(RogueApp)
            app.settings = {"brand_asset": "Images/rogue_logo.gif"}

            with patch("rogue_app.BASE", base):
                resolved = RogueApp.resolve_brand_asset_path(app)

        self.assertEqual(asset, resolved)

    def test_should_animate_status_stays_limited_to_selected_messages(self):
        self.assertTrue(RogueApp.should_animate_status("Initializing Rogue...", level="info"))
        self.assertTrue(RogueApp.should_animate_status("System ready", level="done"))
        self.assertTrue(RogueApp.should_animate_status("Running | Agent loop started in Assist mode.", level="running"))
        self.assertFalse(RogueApp.should_animate_status("Done | Command executed: help", level="done"))
        self.assertFalse(RogueApp.should_animate_status("Error | Backend offline", level="error"))

    def test_set_status_feedback_updates_directly_when_after_is_unavailable(self):
        app = object.__new__(RogueApp)
        app.status_var = FakeVar()
        app.status_label = FakeLabel()

        RogueApp.set_status_feedback(app, "System ready", level="done", animate=True)

        self.assertEqual("System ready", app.status_var.get())
        self.assertEqual("#1f8a57", app.status_label.config["fg"])

    def test_classify_message_distinguishes_confirmation_and_tool_output(self):
        app = object.__new__(RogueApp)
        self.assertEqual("confirm", RogueApp.classify_message(app, "Rogue", "Preview only.\nConfirm with: confirm organize downloads"))
        self.assertEqual("tool", RogueApp.classify_message(app, "Rogue", "apply_download_organization: Moved 2 files"))
        self.assertEqual("warning", RogueApp.classify_message(app, "Rogue", "No pude abrir el log"))

    def test_summarize_action_from_text_returns_useful_labels(self):
        app = object.__new__(RogueApp)
        self.assertEqual("Organized downloads", RogueApp.summarize_action_from_text(app, "apply_download_organization: done"))
        self.assertEqual("Reviewed file move history", RogueApp.summarize_action_from_text(app, "find_move_by_name: report.pdf"))

    def test_build_diagnostics_text_includes_engineering_and_suggestions(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = object.__new__(RogueApp)
            app.modules = {"memory": True, "tools": True}
            app.backend_status = {"reachable": True, "model_available": True, "model": "llama3:latest", "message": "Ollama reachable"}
            app.PROJECTS = Path(tempdir)
            app.MEMORY = Path(tempdir) / "memory"
            app.LOGS = Path(tempdir) / "logs"
            app.agent_task_manager = TaskManager(app.MEMORY)
            app.count_items = lambda _folder: 0
            app.get_backend_mode_label = lambda: "Ollama-backed"
            app.get_suggestion_payload = lambda: {"suggestions": [{"id": "downloads_clutter"}]}

            text = RogueApp.build_diagnostics_text(app)
            self.assertIn("Current suggestion count: 1", text)
            self.assertIn("Engineering task queue enabled: True", text)
            self.assertIn("Agent task visibility enabled: True", text)

    def test_record_activity_stores_richer_metadata(self):
        app = object.__new__(RogueApp)
        app.activity_history = []
        app.set_last_action = lambda *_args, **_kwargs: None
        app.refresh_suggestions = lambda: None
        app.refresh_tasks_panel = lambda: None
        app.activity_list = type("ListBoxStub", (), {"delete": lambda *args, **kwargs: None, "insert": lambda *args, **kwargs: None})()

        RogueApp.record_activity(app, "tool", "Opened logs", command="open logs", tool="logs", success=True)

        self.assertEqual(1, len(app.activity_history))
        self.assertEqual("open logs", app.activity_history[0]["command"])
        self.assertEqual("logs", app.activity_history[0]["tool"])
        self.assertTrue(app.activity_history[0]["success"])

    def test_copy_current_task_prompt_uses_active_task_context(self):
        app = object.__new__(RogueApp)
        app.active_task_context = {"id": 3, "prompt_text": "Prompt text"}
        app.copy_text_to_clipboard = lambda text, label="": {"success": True, "action": "copy_to_clipboard", "result": "ok", "error": None}
        app.record_activity = lambda *_args, **_kwargs: None

        result = RogueApp.copy_current_task_prompt(app)
        self.assertTrue(result["success"])
        self.assertIn("task 3", result["result"])

    def test_copy_task_prompt_fails_gracefully_when_clipboard_unavailable(self):
        app = object.__new__(RogueApp)
        app.record_activity = lambda *_args, **_kwargs: None
        app.copy_text_to_clipboard = lambda text, label="": {"success": False, "action": "copy_to_clipboard", "result": "", "error": "Clipboard unavailable: test"}

        with patch("rogue_app.get_task", return_value={"success": True, "action": "get_task", "result": "Task 3", "error": None, "task": {"id": 3, "prompt_text": "Prompt text"}}):
            result = RogueApp.copy_task_prompt(app, 3)

        self.assertFalse(result["success"])
        self.assertIn("Clipboard unavailable", result["error"])

    def test_build_agent_task_status_summary_reports_counts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            manager = TaskManager(memory_root)
            manager.create_task("active goal", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])
            manager.create_task("done goal", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])
            manager.update_task_status(2, "completed")

            app = object.__new__(RogueApp)
            app.MEMORY = memory_root
            app.agent_task_manager = manager

            summary = RogueApp.build_agent_task_status_summary(app)

            self.assertIn("Total tasks: 2", summary)
            self.assertIn("Active tasks: 1", summary)
            self.assertIn("Completed tasks: 1", summary)

    def test_refresh_agent_control_panel_reads_shared_state_snapshot(self):
        class FakeVar:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        now = datetime(2026, 4, 10, 16, 0, 0)
        state = AgentState(mode="assist", interval_seconds=20, clock=lambda: now)
        state.apply_cycle_payload(
            {
                "cycle_started_at": "2026-04-10T15:59:45",
                "success": True,
                "sensor_state": {
                    "downloads": {
                        "exists": True,
                        "recursive": False,
                        "file_count": 3,
                        "total_size_human": "5.0 MB",
                        "recent_file_count": 1,
                    }
                },
                "plan": [{"task_name": "inspect_downloads", "tool_name": "list_path"}],
                "approved_plan": [{"task_name": "inspect_downloads"}],
                "blocked_plan": [{"task_name": "move_files"}],
                "execution": {"final_output": "Assist mode: approved tasks were prepared but not executed."},
            },
            running=True,
        )

        app = object.__new__(RogueApp)
        app.agent_state = state
        app.root = object()
        app.agent_running_var = FakeVar()
        app.agent_mode_selector_var = FakeVar()
        app.agent_mode_display_var = FakeVar()
        app.agent_interval_var = FakeVar()
        app.agent_last_cycle_var = FakeVar()
        app.agent_next_cycle_var = FakeVar()
        app.agent_observation_var = FakeVar()
        app.agent_plan_var = FakeVar()
        app.agent_approved_var = FakeVar()
        app.agent_blocked_var = FakeVar()
        app.agent_result_var = FakeVar()
        app.agent_error_var = FakeVar()
        app.agent_status_badge = FakeLabel()
        app.agent_running_value_label = FakeLabel()

        RogueApp.refresh_agent_control_panel(app)

        self.assertEqual("Running", app.agent_running_var.get())
        self.assertEqual("Assist", app.agent_mode_selector_var.get())
        self.assertEqual("20", app.agent_interval_var.get())
        self.assertEqual("2026-04-10 15:59:45", app.agent_last_cycle_var.get())
        self.assertEqual("2026-04-10 16:00:20", app.agent_next_cycle_var.get())
        self.assertIn("Downloads: 3 files, 5.0 MB, 1 recent files", app.agent_observation_var.get())
        self.assertIn("Inspect downloads", app.agent_plan_var.get())
        self.assertIn("Tool: List folder contents", app.agent_plan_var.get())
        self.assertIn("move_files", app.agent_blocked_var.get())
        self.assertEqual("Running", app.agent_status_badge.config["text"])

    def test_refresh_agent_control_panel_marks_error_status_red(self):
        class FakeVar:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        state = AgentState(mode="manual", interval_seconds=60, clock=lambda: datetime(2026, 4, 10, 16, 0, 0))
        state.apply_cycle_error("Loop failure", cycle_started_at="2026-04-10T15:59:45", running=False)

        app = object.__new__(RogueApp)
        app.agent_state = state
        app.root = object()
        app.agent_running_var = FakeVar()
        app.agent_mode_selector_var = FakeVar()
        app.agent_mode_display_var = FakeVar()
        app.agent_interval_var = FakeVar()
        app.agent_last_cycle_var = FakeVar()
        app.agent_next_cycle_var = FakeVar()
        app.agent_observation_var = FakeVar()
        app.agent_plan_var = FakeVar()
        app.agent_approved_var = FakeVar()
        app.agent_blocked_var = FakeVar()
        app.agent_result_var = FakeVar()
        app.agent_error_var = FakeVar()
        app.agent_status_badge = FakeLabel()
        app.agent_running_value_label = FakeLabel()

        RogueApp.refresh_agent_control_panel(app)

        self.assertEqual("Error", app.agent_status_badge.config["text"])
        self.assertEqual("#b42318", app.agent_status_badge.config["fg"])

    def test_save_and_restore_window_state_use_ui_state_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = object.__new__(RogueApp)
            app.root = DummyRoot()
            app.root.geometry("1400x900+150+90")
            app.ui_state_path = Path(tempdir) / "config" / "ui_state.json"
            app.window_state_save_job = None

            RogueApp.save_window_state(app)

            saved = json.loads(app.ui_state_path.read_text(encoding="utf-8"))
            self.assertEqual("1400x900+150+90", saved["geometry"])

            restored_app = object.__new__(RogueApp)
            restored_app.root = DummyRoot()
            restored_app.ui_state_path = app.ui_state_path

            RogueApp.restore_window_state(restored_app)

            self.assertEqual("1400x900+150+90", restored_app.root.geometry())

    def test_show_agent_task_details_adds_formatted_message(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            manager = TaskManager(memory_root)
            manager.create_task("inspect workspace", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])

            app = object.__new__(RogueApp)
            app.MEMORY = memory_root
            app.agent_task_manager = manager
            messages = []
            app.add_message = lambda sender, message, kind=None: messages.append((sender, message, kind))
            app.record_activity = lambda *_args, **_kwargs: None

            RogueApp.show_agent_task_details(app, 1)

            self.assertEqual(1, len(messages))
            self.assertEqual("tool", messages[0][2])
            self.assertIn("Task 1", messages[0][1])
            self.assertIn("inspect workspace", messages[0][1])

    def test_add_message_preserves_transcript_insert_and_scroll_behavior(self):
        app = object.__new__(RogueApp)
        app.chat_box = FakeTextWidget()
        app.sanitize_chat_message = lambda message: message
        app.classify_message = RogueApp.classify_message.__get__(app, RogueApp)

        RogueApp.add_message(app, "Rogue", "All systems nominal.", kind="assistant")

        self.assertEqual("disabled", str(app.chat_box.config_state["state"]).lower())
        self.assertEqual(
            [
                ("end", "Rogue\n", "header_assistant"),
                ("end", "All systems nominal.\n\n", "body_assistant"),
            ],
            [(str(index).lower(), text, tag) for index, text, tag in app.chat_box.insert_calls],
        )
        self.assertEqual(["end"], [str(index).lower() for index in app.chat_box.see_calls])

    def test_build_preview_from_agent_result_formats_folder_summary(self):
        app = object.__new__(RogueApp)

        model = RogueApp.build_preview_from_agent_result(
            app,
            {
                "goal": "scan desktop",
                "results": [
                    {
                        "result": {
                            "summary": {
                                "path": "C:/Users/test/Desktop",
                                "total_files": 22,
                                "total_directories": 5,
                                "total_size_human": "12.0 MB",
                                "top_file_types": [
                                    {"extension": ".png", "count": 8},
                                    {"extension": ".pdf", "count": 4},
                                ],
                                "largest_files": [{"name": "archive.zip", "size_bytes": 1024, "path": "C:/Users/test/Desktop/archive.zip"}],
                                "newest_files": [{"name": "notes.txt", "modified": "2026-04-08T18:10:00", "path": "C:/Users/test/Desktop/notes.txt"}],
                            }
                        }
                    }
                ],
            },
        )

        self.assertEqual("Desktop analysis", model["title"])
        self.assertIn(("Files", 22), model["rows"])
        self.assertEqual("Top File Types", model["sections"][0]["title"])
        self.assertEqual("Largest Files", model["sections"][1]["title"])
        self.assertEqual("Newest Files", model["sections"][2]["title"])
        self.assertEqual(".png: 8", model["sections"][0]["entries"][0]["text"])
        self.assertEqual("C:/Users/test/Desktop/archive.zip", model["sections"][1]["entries"][0]["path"])
        self.assertEqual("C:/Users/test/Desktop/notes.txt", model["sections"][2]["entries"][0]["path"])
        self.assertIn("No files were modified.", model["footer"])

    def test_build_system_status_preview_parses_structured_rows(self):
        app = object.__new__(RogueApp)

        model = RogueApp.build_system_status_preview(
            app,
            {
                "results": [
                    {
                        "result": {
                            "action": "get_system_info",
                            "result": "{'platform': 'Windows', 'python_version': '3.12.1', 'cwd': 'C:/RogueAI'}",
                        }
                    },
                    {
                        "result": {
                            "action": "list_projects",
                            "result": "Tienes 1 proyectos.\n- RogueAI",
                        }
                    },
                    {
                        "result": {
                            "action": "list_saved_notes",
                            "result": "- remember test cases",
                        }
                    },
                ]
            },
        )

        self.assertEqual("System status", model["title"])
        self.assertIn(("Platform", "Windows"), model["rows"])
        self.assertEqual("RogueAI", model["sections"][0]["lines"][0])

    def test_build_preview_model_uses_task_list_payload(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            manager = TaskManager(memory_root)
            manager.create_task(
                "scan desktop",
                [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}],
            )

            app = object.__new__(RogueApp)
            app.MEMORY = memory_root
            app.agent_task_manager = manager
            app.last_agent_workflow_payload = {
                "kind": "task_list",
                "title": "Agent Tasks",
                "tasks": manager.list_tasks().get("tasks", []),
            }

            model = RogueApp.build_preview_model(app, "agent list tasks", "Agent Tasks")

            self.assertEqual("Agent Tasks", model["title"])
            self.assertIn(("Count", 1), model["rows"])
            self.assertIn("Task 1 [planned] - scan desktop", model["sections"][0]["lines"][0])


class DiagnosticsTests(unittest.TestCase):
    def test_get_ollama_status_returns_degraded_message_on_connection_error(self):
        with patch("brain.llm_bridge.requests.get", side_effect=RuntimeError("connection refused")):
            status = get_ollama_status()
        self.assertFalse(status["reachable"])
        self.assertIn("router-only mode", status["message"])

    def test_show_diagnostics_reports_router_only_mode(self):
        fake_settings = {"app_name": "Rogue Local", "max_memory_turns": 12}
        fake_modules = {
            "memory": True,
            "projects": True,
            "agents": True,
            "tools": True,
            "autonomy": True,
        }
        fake_ollama = {
            "reachable": False,
            "model": "llama3:latest",
            "model_available": False,
            "message": "Ollama unavailable. Rogue will continue in router-only mode.",
        }
        stream = io.StringIO()
        with patch.object(brain_cli, "load_or_create_settings", return_value=fake_settings), \
             patch.object(brain_cli, "load_or_create_modules", return_value=fake_modules), \
             patch.object(brain_cli, "get_ollama_status", return_value=fake_ollama), \
             patch.object(brain_cli, "log_action", return_value=None), \
             redirect_stdout(stream):
            brain_cli.show_diagnostics()
        output = stream.getvalue()
        self.assertIn("ROGUE DIAGNOSTICS", output)
        self.assertIn("Router-only mode", output)
        self.assertIn("reachable: NO", output)
        self.assertIn("System tools loaded: True", output)
        self.assertIn("Command execution available: True", output)
        self.assertIn("Browser control available: True", output)
        self.assertIn("Memory enabled: True", output)
        self.assertIn("File organization available: True", output)
        self.assertIn("File move history enabled: True", output)
        self.assertIn("Home workspace organization available: True", output)
        self.assertIn("Downloads organization mode: local organized subfolders", output)
        self.assertIn("Proactive assistant enabled: True", output)
        self.assertIn("Current suggestion count:", output)
        self.assertIn("Engineering task queue enabled: True", output)
        self.assertIn("Current engineering task count:", output)
        self.assertIn("Clipboard handoff available: True", output)

    def test_show_diagnostics_panel_adds_diagnostics_message(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = object.__new__(RogueApp)
            app.modules = {"memory": True, "tools": True}
            app.backend_status = {"reachable": False, "model_available": False, "model": "llama3:latest", "message": "Router-only mode"}
            app.PROJECTS = Path(tempdir)
            app.MEMORY = Path(tempdir) / "memory"
            app.LOGS = Path(tempdir) / "logs"
            app.agent_task_manager = TaskManager(app.MEMORY)
            app.record_activity = lambda *_args, **_kwargs: None
            app.log_action = lambda *_args, **_kwargs: None
            app.count_items = lambda _folder: 0
            app.refresh_status_bar = lambda: None
            app.get_suggestion_payload = lambda: {"suggestions": [{"id": "backend_unavailable"}]}
            messages = []
            app.add_message = lambda sender, message, kind=None: messages.append((sender, message, kind))

            RogueApp.show_diagnostics_panel(app)

            self.assertEqual(1, len(messages))
            self.assertEqual("diagnostics", messages[0][2])
            self.assertIn("ROGUE DESKTOP DIAGNOSTICS", messages[0][1])
            self.assertIn("Browser control available: True", messages[0][1])
            self.assertIn("Current suggestion count: 1", messages[0][1])
            self.assertIn("Engineering task queue enabled: True", messages[0][1])
            self.assertIn("Agent task visibility enabled: True", messages[0][1])
            self.assertIn("Clipboard handoff available: True", messages[0][1])


class AgentCliTaskVisibilityTests(unittest.TestCase):
    def test_agent_mode_lists_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir) / "memory")
            manager.create_task("inspect system", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])
            stream = io.StringIO()

            with patch.object(brain_cli, "build_agent_runtime", return_value=(object(), manager, object())), \
                 patch.object(brain_cli, "log_action", return_value=None), \
                 patch.object(brain_cli.sys, "argv", ["brain.py", "agent", "list", "tasks"]), \
                 redirect_stdout(stream):
                brain_cli.agent_mode()

            output = stream.getvalue()
            self.assertIn("Agent Tasks", output)
            self.assertIn("inspect system", output)

    def test_agent_mode_shows_task_details(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir) / "memory")
            manager.create_task("workspace summary", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])
            stream = io.StringIO()

            with patch.object(brain_cli, "build_agent_runtime", return_value=(object(), manager, object())), \
                 patch.object(brain_cli, "log_action", return_value=None), \
                 patch.object(brain_cli.sys, "argv", ["brain.py", "agent", "show", "task", "1"]), \
                 redirect_stdout(stream):
                brain_cli.agent_mode()

            output = stream.getvalue()
            self.assertIn("Task 1", output)
            self.assertIn("workspace summary", output)

    def test_handle_agent_task_visibility_lists_resumable_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir) / "memory")
            manager.create_task("resumable goal", [{"id": 1, "title": "step", "tool_name": "tool", "tool_input": {}, "verification": {}, "max_retries": 0}])
            manager.mark_step_failed(1, 0, "temporary issue")

            result = brain_cli.handle_agent_task_visibility("list resumable tasks", manager)

            self.assertTrue(result["success"])
            self.assertIn("Resumable Agent Tasks", result["final_output"])
            self.assertIn("resumable goal", result["final_output"])


if __name__ == "__main__":
    unittest.main()
