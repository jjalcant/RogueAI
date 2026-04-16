import unittest
from unittest.mock import patch

from rogue_app import RogueApp
from ui_command_registry import CommandDefinition, build_command_registry


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeEntry:
    def __init__(self, value=""):
        self.value = value
        self.deleted = False
        self.focused = False

    def get(self):
        return self.value

    def delete(self, *_args, **_kwargs):
        self.value = ""
        self.deleted = True

    def insert(self, _index, value):
        self.value = str(value)

    def index(self, spec):
        if spec == "end-1c":
            return f"{max(1, self.value.count(chr(10)) + 1)}.0"
        return "1.0"

    def mark_set(self, *_args, **_kwargs):
        return None

    def see(self, *_args, **_kwargs):
        return None

    def selection_range(self, *_args, **_kwargs):
        return None

    def icursor(self, *_args, **_kwargs):
        return None

    def tag_add(self, *_args, **_kwargs):
        return None

    def focus_set(self):
        self.focused = True


class DesktopCommandRegistryTests(unittest.TestCase):
    def test_registry_contains_expected_commands_and_aliases(self):
        app = object.__new__(RogueApp)

        registry = build_command_registry(app)
        names = {item.name: item for item in registry}

        self.assertIn("help", names)
        self.assertIn("status", names)
        self.assertIn("agent status", names)
        self.assertIn("open folder", names)
        self.assertIn("organize downloads", names)
        self.assertIn("generate report", names)
        self.assertIn("system status", names["status"].aliases)
        self.assertIn("esc", names["back"].aliases)

    def test_help_preview_groups_commands_by_category(self):
        app = object.__new__(RogueApp)
        app.command_registry = None

        model = RogueApp.build_help_preview_model(app)

        self.assertEqual("Rogue Help", model["title"])
        self.assertEqual(
            ["Navigation", "System", "Analysis", "Actions"],
            [section["title"] for section in model["sections"]],
        )
        self.assertEqual("help                Show this help screen", model["sections"][0]["lines"][0])
        self.assertEqual("generate report     Create a report from current analysis", model["sections"][3]["lines"][-1])
        self.assertIn("Type help anytime to see this list again.", model["footer"])

    def test_show_help_switches_to_dedicated_help_view(self):
        app = object.__new__(RogueApp)
        app.current_view_name = "dashboard"
        app.current_view_state = None
        app.view_history = []
        app.command_registry = None
        captured = {}
        app.populate_help_view = lambda model=None: captured.setdefault("model", model)
        app.switch_main_view = lambda name: captured.setdefault("view", name)
        app.update_navigation_controls = lambda: captured.setdefault("nav", True)
        app.set_status_feedback = lambda message, level="info": captured.setdefault("status", (message, level))

        result = RogueApp.show_help(app)

        self.assertEqual("help", result)
        self.assertEqual("help", captured["view"])
        self.assertEqual("Rogue Help", app.current_view_state["model"]["title"])

    def test_show_settings_view_marks_settings_as_active_view(self):
        app = object.__new__(RogueApp)
        app.current_view_name = "dashboard"
        app.current_view_state = None
        captured = {}
        app.switch_main_view = lambda name: captured.setdefault("view", name)
        app.update_navigation_controls = lambda: captured.setdefault("nav", True)
        app.set_status_feedback = lambda message, level="info": captured.setdefault("status", (message, level))

        result = RogueApp.show_settings_view(app)

        self.assertEqual("settings", result)
        self.assertEqual("settings", app.current_view_name)
        self.assertEqual("settings", captured["view"])

    def test_build_preview_model_uses_structured_router_payload(self):
        app = object.__new__(RogueApp)
        app.last_agent_workflow_payload = None
        app.last_structured_response_payload = {
            "success": True,
            "action": "create_folder",
            "observed": ["Verified folder exists after create request: C:\\demo"],
            "artifacts": [{"description": "Requested folder", "path": "C:\\demo", "verified": True, "exists": True}],
            "warnings": [],
            "errors": [],
        }

        model = RogueApp.build_preview_model(app, "create folder demo", "ignored")

        self.assertEqual("Create Folder", model["title"])
        self.assertEqual("Observed Facts", model["sections"][0]["title"])
        self.assertEqual("Artifacts", model["sections"][1]["title"])

    def test_go_back_without_history_returns_dashboard_safely(self):
        app = object.__new__(RogueApp)
        app.dashboard_preview_model = None
        app.current_view_name = "help"
        app.current_view_state = {"name": "help", "model": {"title": "Help"}}
        app.view_history = []
        app.status_var = FakeVar()
        app.render_preview_placeholder = lambda: setattr(app, "placeholder_rendered", True)
        app.render_preview_model = lambda _model: setattr(app, "model_rendered", True)
        app.update_navigation_controls = lambda: setattr(app, "nav_updated", True)

        result = RogueApp.go_back(app)

        self.assertEqual("dashboard", result)
        self.assertEqual("dashboard", app.current_view_name)
        self.assertTrue(getattr(app, "placeholder_rendered", False))

    def test_execute_command_returns_clean_message_for_unknown_command(self):
        messages = []
        app = object.__new__(RogueApp)
        app.command_registry = []
        app.command_entry = FakeEntry("totally unknown")
        app.status_var = FakeVar()
        app.add_message = lambda sender, message, kind=None: messages.append((sender, message, kind))

        result = RogueApp.execute_command(app)

        self.assertEqual("break", result)
        self.assertEqual("Unknown command. Type help to see available commands.", messages[0][1])
        self.assertEqual("Error | Unknown command. Type help to see available commands.", app.status_var.get())

    def test_execute_command_uses_confirmation_for_risky_command(self):
        handled = []
        messages = []
        app = object.__new__(RogueApp)
        app.command_registry = [
            CommandDefinition(
                name="cleanup temp",
                aliases=(),
                description="stub",
                example="cleanup temp",
                handler=lambda _command: handled.append("ran"),
                category="Actions",
                requires_confirmation=True,
                confirmation_message="Confirm cleanup temp?",
                implemented=False,
            )
        ]
        app.command_entry = FakeEntry("cleanup temp")
        app.status_var = FakeVar()
        app.add_message = lambda sender, message, kind=None: messages.append((sender, message, kind))
        app.record_activity = lambda *args, **kwargs: None
        app.root = None

        with patch("rogue_app.messagebox.askyesno", return_value=False):
            result = RogueApp.execute_command(app)

        self.assertEqual("break", result)
        self.assertEqual([], handled)
        self.assertIn("Cancelled command", messages[0][1])

    def test_execute_command_routes_to_registered_handler(self):
        handled = []
        app = object.__new__(RogueApp)
        app.command_registry = [
            CommandDefinition(
                name="help",
                aliases=(),
                description="help",
                example="help",
                handler=lambda _command: handled.append("help"),
                category="Navigation",
            )
        ]
        app.command_entry = FakeEntry("help")
        app.status_var = FakeVar()
        app.add_message = lambda *args, **kwargs: None
        app.record_activity = lambda *args, **kwargs: None

        RogueApp.execute_command(app)

        self.assertEqual(["help"], handled)
        self.assertTrue(app.command_entry.deleted)

    def test_command_history_navigation_uses_recent_commands(self):
        app = object.__new__(RogueApp)
        app.command_entry = FakeEntry()
        app.command_history = ["scan desktop", "inspect downloads"]
        app.command_history_index = None
        app.command_history_draft = ""
        app.set_status_feedback = lambda *_args, **_kwargs: None

        result = RogueApp.handle_command_history_up(app)

        self.assertEqual("break", result)
        self.assertEqual("inspect downloads", app.command_entry.get())

        result = RogueApp.handle_command_history_up(app)

        self.assertEqual("break", result)
        self.assertEqual("scan desktop", app.command_entry.get())

        result = RogueApp.handle_command_history_down(app)

        self.assertEqual("break", result)
        self.assertEqual("inspect downloads", app.command_entry.get())


if __name__ == "__main__":
    unittest.main()
