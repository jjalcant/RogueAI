import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain.router import format_tool_response, route_input, run_agent_workflow


class DummyApp:
    def __init__(self, base):
        self.PROJECTS = Path(base) / "projects"
        self.MEMORY = Path(base) / "memory"
        self.AGENTS = Path(base) / "agents"
        self.AUTONOMY = Path(base) / "autonomy"
        self.CONFIG = Path(base) / "config"
        self.LOGS = Path(base) / "logs"
        for folder in [
            self.PROJECTS,
            self.MEMORY,
            self.AGENTS,
            self.AUTONOMY,
            self.CONFIG,
            self.LOGS,
        ]:
            folder.mkdir(parents=True, exist_ok=True)
        self.pending_action = None
        self.conversation_memory = []
        self.async_requests = []
        self.backend_status = {"reachable": True, "model_available": True, "message": "ok", "model": "llama3:latest"}
        self.last_suggestions = []
        self.active_task_context = None
        self.last_browser_target = None
        self.last_structured_response_payload = None
        self.last_agent_workflow_payload = None
        self.verified_folder_target = None

    def count_items(self, folder):
        return len(list(Path(folder).iterdir()))

    def open_notes_file(self):
        return "opened notes"

    def start_async_fallback(self, text):
        self.async_requests.append(text)

    def copy_task_prompt(self, task_id):
        return {"success": True, "action": "copy_task_prompt", "result": f"Copied prompt for task {task_id} to clipboard.", "error": None}

    def copy_current_task_prompt(self):
        return {"success": True, "action": "copy_current_task_prompt", "result": "Copied current task 3 prompt to clipboard.", "error": None}


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = DummyApp(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_project_create_requires_confirmation(self):
        response = route_input(self.app, "crea un proyecto llamado demo")
        self.assertIn("Escribe SI para confirmar", response)
        self.assertEqual(self.app.pending_action["type"], "create_project")
        self.assertEqual(self.app.pending_action["name"], "demo")

    def test_project_create_confirmation_creates_folder(self):
        route_input(self.app, "crea un proyecto llamado demo")
        response = route_input(self.app, "si")
        self.assertIn("Action: create_project", response)
        self.assertIn("Verified project folder exists after create request", response)
        self.assertTrue((self.app.PROJECTS / "demo").exists())

    def test_note_saves_into_memory_notes(self):
        response = route_input(self.app, "recuerdame comprar leche")
        self.assertIn("Ya guard", response)
        notes_file = self.app.MEMORY / "notes.md"
        self.assertTrue(notes_file.exists())
        self.assertIn("comprar leche", notes_file.read_text(encoding="utf-8"))

    def test_unknown_routes_to_async_fallback(self):
        response = route_input(self.app, "haz algo que no entiendas")
        self.assertEqual("__ASYNC__", response)
        self.assertEqual(["haz algo que no entiendas"], self.app.async_requests)

    def test_system_info_route_returns_structured_summary(self):
        with patch(
            "brain.router.system_info",
            return_value={"success": True, "action": "system_info", "result": "verified", "error": None, "observed": ["CPU: Verified"]},
        ):
            response = route_input(self.app, "show system info")
        self.assertIn("system_info", response)

    def test_system_info_alias_routes_to_system_info_tool(self):
        with patch(
            "brain.router.system_info",
            return_value={"success": True, "action": "system_info", "result": "verified", "error": None, "observed": ["CPU: Verified"]},
        ):
            response = route_input(self.app, "pc info")
        self.assertIn("system_info", response)

    def test_system_health_route_executes_new_tool(self):
        with patch(
            "brain.router.system_health",
            return_value={
                "success": True,
                "action": "system_health",
                "result": "verified",
                "error": None,
                "observed": ["CPU usage: 18%", "Memory usage: 42%", "Disk usage: 72%"],
            },
        ):
            response = route_input(self.app, "system health")
        self.assertIn("system_health", response)

    def test_system_health_aliases_route_to_system_health_tool(self):
        aliases = ["check system health", "health check", "system diagnostics"]
        for alias in aliases:
            with self.subTest(alias=alias):
                with patch(
                    "brain.router.system_health",
                    return_value={
                        "success": True,
                        "action": "system_health",
                        "result": "verified",
                        "error": None,
                        "observed": ["CPU usage: 18%", "Memory usage: 42%", "Disk usage: 72%"],
                    },
                ) as tool_call:
                    response = route_input(self.app, alias)
                self.assertIn("system_health", response)
                tool_call.assert_called_once()

    def test_storage_overview_route_executes_new_tool(self):
        with patch(
            "brain.router.storage_overview",
            return_value={
                "success": True,
                "action": "storage_overview",
                "result": "verified",
                "error": None,
                "observed": ["Drive usage: 72%", "Free space: 120 GB"],
            },
        ):
            response = route_input(self.app, "storage overview")
        self.assertIn("storage_overview", response)

    def test_storage_overview_aliases_route_to_storage_overview_tool(self):
        aliases = ["disk usage", "check disk", "disk analysis", "storage status"]
        for alias in aliases:
            with self.subTest(alias=alias):
                with patch(
                    "brain.router.storage_overview",
                    return_value={
                        "success": True,
                        "action": "storage_overview",
                        "result": "verified",
                        "error": None,
                        "observed": ["Drive usage: 72%", "Free space: 120 GB"],
                    },
                ) as tool_call:
                    response = route_input(self.app, alias)
                self.assertIn("storage_overview", response)
                tool_call.assert_called_once()

    def test_open_downloads_folder_alias_routes_to_system_tool(self):
        with patch("brain.router.open_folder", return_value={"success": True, "action": "open_folder", "result": "Opened folder", "error": None}):
            response = route_input(self.app, "open downloads folder")
        self.assertIn("open_folder", response)

    def test_open_notepad_alias_routes_to_system_tool(self):
        with patch("brain.router.open_application", return_value={"success": True, "action": "open_application", "result": "Application launched", "error": None}):
            response = route_input(self.app, "open notepad")
        self.assertIn("open_application", response)

    def test_open_url_command_mapping(self):
        with patch("brain.router.open_url", return_value={"success": True, "action": "open_url", "result": "Opened URL: https://www.youtube.com", "error": None, "url": "https://www.youtube.com"}):
            response = route_input(self.app, "open youtube")
        self.assertIn("open_url", response)

    def test_search_query_mapping(self):
        with patch("brain.router.open_search", return_value={"success": True, "action": "open_search", "result": "Opened google search for: python tkinter docs", "error": None, "url": "https://www.google.com/search?q=python+tkinter+docs"}):
            response = route_input(self.app, "search for python tkinter docs")
        self.assertIn("open_search", response)

    def test_browser_malformed_input_fails_cleanly(self):
        with patch("brain.router.open_url", return_value={"success": False, "action": "open_url", "result": "", "error": "Malformed or unsupported URL: ???"}):
            response = route_input(self.app, "open this website")
        self.assertIn("which website", response.lower())

    def test_agent_command_routes_to_agent_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="agent workflow ok"):
            response = route_input(self.app, "agent report system status")
        self.assertEqual("agent workflow ok", response)

    def test_agent_list_tasks_routes_to_agent_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="Agent Tasks\n- Task 1: [completed] status") as run_agent:
            response = route_input(self.app, "agent list tasks")
        self.assertIn("Agent Tasks", response)
        run_agent.assert_called_once()

    def test_agent_show_task_routes_to_agent_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="Task 1\n- Goal: workspace summary") as run_agent:
            response = route_input(self.app, "agent show task 1")
        self.assertIn("Task 1", response)
        run_agent.assert_called_once()

    def test_run_agent_workflow_stores_last_payload_for_ui_preview(self):
        with patch("brain.router.build_default_registry"), \
             patch("brain.router.MemoryManager"), \
             patch("brain.router.ExecutionLogger"), \
             patch("brain.router.StatusReporter"), \
             patch("brain.router.TaskManager"), \
             patch("brain.router.AgentLoop") as agent_cls:
            agent_cls.return_value.run_goal.return_value = {
                "success": True,
                "goal": "scan desktop",
                "results": [],
                "final_output": "done",
            }

            response = run_agent_workflow(self.app, "scan desktop")

        self.assertEqual("done", response)
        self.assertEqual("agent_run", self.app.last_agent_workflow_payload["kind"])
        self.assertEqual("scan desktop", self.app.last_agent_workflow_payload["payload"]["goal"])

    def test_scan_desktop_routes_to_agent_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="Folder summary: desktop") as run_agent:
            response = route_input(self.app, "scan desktop")
        self.assertIn("Folder summary", response)
        run_agent.assert_called_once()

    def test_organize_it_without_verified_context_returns_clean_target_guidance(self):
        with patch("brain.router.run_agent_workflow") as run_agent:
            response = route_input(self.app, "organize it")

        self.assertIn("Organize Request Needs Target", response)
        self.assertIn("No verified folder target was available", response)
        self.assertIn("conversational reference 'it'", response)
        self.assertIn("organize desktop", response)
        self.assertNotIn("Safe folder not found or unavailable: it", response)
        run_agent.assert_not_called()

    def test_organize_it_reuses_verified_folder_context(self):
        self.app.verified_folder_target = r"C:\Users\Test\Desktop"

        with patch(
            "brain.router.run_agent_workflow",
            return_value="Organization preview: desktop\n- No files were modified.",
        ) as run_agent:
            response = route_input(self.app, "organize it")

        self.assertIn("Organization preview", response)
        run_agent.assert_called_once_with(self.app, r"organize C:\Users\Test\Desktop")

    def test_organize_my_desktop_routes_to_agent_preview_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="Organization preview: desktop\n- No files were modified.") as run_agent:
            response = route_input(self.app, "organize my desktop")
        self.assertIn("Organization preview", response)
        self.assertIn("No files were modified", response)
        run_agent.assert_called_once()

    def test_clean_up_my_desktop_routes_to_agent_preview_workflow(self):
        with patch("brain.router.run_agent_workflow", return_value="Organization preview: desktop\n- Included subfolders: True\n- No files were modified.") as run_agent:
            response = route_input(self.app, "clean up my desktop")
        self.assertIn("Included subfolders: True", response)
        self.assertIn("No files were modified", response)
        run_agent.assert_called_once()

    def test_organize_downloads_returns_preview_only(self):
        with patch("brain.router.run_agent_workflow", return_value="Organization preview: downloads\n- Top categories:\n  Documents: 1\n- No files were modified.") as run_agent:
            response = route_input(self.app, "organize my downloads")
        self.assertIn("Organization preview", response)
        self.assertIn("No files were modified", response)
        self.assertIsNone(self.app.pending_action)
        run_agent.assert_called_once()

    def test_explicit_downloads_confirmation_runs_apply(self):
        self.app.pending_action = {"type": "organize_downloads", "path": "downloads"}
        with patch("brain.router.apply_download_organization", return_value={"success": True, "action": "apply_download_organization", "result": "Moved 1 files", "error": None}):
            response = route_input(self.app, "confirm organize downloads")
        self.assertIn("apply_download_organization", response)
        self.assertIsNone(self.app.pending_action)

    def test_old_confirmation_remains_compatible_for_downloads(self):
        self.app.pending_action = {"type": "organize_downloads", "path": "downloads"}
        with patch("brain.router.apply_download_organization", return_value={"success": True, "action": "apply_download_organization", "result": "Moved 1 files", "error": None}):
            response = route_input(self.app, "si")
        self.assertIn("apply_download_organization", response)

    def test_home_workspace_preview_route(self):
        preview_payload = {
            "success": True,
            "action": "preview_home_workspace_organization",
            "result": "Preview ready",
            "error": None,
            "items": [{"source": "a", "target_folder": "b", "category": "Notes"}],
            "summary": {"Notes": 1},
            "confirmation_phrase": "confirm organize home workspace",
            "skipped_protected": ["Desktop"],
        }
        with patch("brain.router.preview_home_workspace_organization", return_value=preview_payload):
            response = route_input(self.app, "scan my home workspace")
        self.assertIn("preview_home_workspace_organization", response)

    def test_home_workspace_preview_route_supports_spanish_natural_phrase(self):
        preview_payload = {
            "success": True,
            "action": "preview_home_workspace_organization",
            "result": "Preview ready",
            "error": None,
            "items": [{"source": "a", "target_folder": "b", "category": "Notes"}],
            "summary": {"Notes": 1},
            "confirmation_phrase": "confirm organize home workspace",
            "skipped_protected": ["Desktop"],
        }
        with patch("brain.router.preview_home_workspace_organization", return_value=preview_payload):
            response = route_input(self.app, "revisa mi workspace")
        self.assertIn("preview_home_workspace_organization", response)

    def test_home_workspace_organize_returns_preview_only(self):
        preview_payload = {
            "success": True,
            "action": "preview_home_workspace_organization",
            "result": "Preview ready",
            "error": None,
            "items": [{"source": "a", "target_folder": "b", "category": "Notes"}],
            "summary": {"Notes": 1},
            "confirmation_phrase": "confirm organize home workspace",
            "skipped_protected": ["Desktop"],
        }
        with patch("brain.router.preview_home_workspace_organization", return_value=preview_payload):
            response = route_input(self.app, "organize my home workspace")
        self.assertIn("Preview only", response)
        self.assertIn("No files were modified", response)
        self.assertIsNone(self.app.pending_action)

    def test_home_workspace_organize_route_supports_spanish_natural_phrase(self):
        preview_payload = {
            "success": True,
            "action": "preview_home_workspace_organization",
            "result": "Preview ready",
            "error": None,
            "items": [{"source": "a", "target_folder": "b", "category": "Notes"}],
            "summary": {"Notes": 1},
            "confirmation_phrase": "confirm organize home workspace",
            "skipped_protected": ["Desktop"],
        }
        with patch("brain.router.preview_home_workspace_organization", return_value=preview_payload):
            response = route_input(self.app, "organiza mi espacio de trabajo")
        self.assertIn("Preview only", response)
        self.assertIn("No files were modified", response)
        self.assertIsNone(self.app.pending_action)

    def test_explicit_home_workspace_confirmation_runs_apply(self):
        self.app.pending_action = {"type": "organize_home_workspace", "path": "home workspace"}
        with patch("brain.router.apply_home_workspace_organization", return_value={"success": True, "action": "apply_home_workspace_organization", "result": "Moved 2 files", "error": None}):
            response = route_input(self.app, "confirm organize home workspace")
        self.assertIn("apply_home_workspace_organization", response)
        self.assertIsNone(self.app.pending_action)

    def test_spanish_explicit_home_workspace_confirmation_runs_apply(self):
        self.app.pending_action = {"type": "organize_home_workspace", "path": "home workspace"}
        with patch("brain.router.apply_home_workspace_organization", return_value={"success": True, "action": "apply_home_workspace_organization", "result": "Moved 2 files", "error": None}):
            response = route_input(self.app, "confirma organizar workspace")
        self.assertIn("apply_home_workspace_organization", response)
        self.assertIsNone(self.app.pending_action)

    def test_move_history_lookup_route(self):
        with patch("brain.router.find_move_by_name", return_value={"success": True, "action": "find_move_by_name", "result": "report.txt -> target", "error": None, "entries": []}):
            response = route_input(self.app, "show where report.txt was moved")
        self.assertIn("find_move_by_name", response)

    def test_show_suggested_actions_route(self):
        payload = {
            "success": True,
            "action": "get_suggestions",
            "result": "Found 2 active suggestions.",
            "error": None,
            "suggestions": [
                {
                    "id": "downloads_clutter",
                    "title": "Downloads look cluttered",
                    "reason": "Loose files detected.",
                    "recommended_action": "Preview Downloads organization",
                    "confirmation_required": False,
                    "suggested_command": "scan my downloads",
                }
            ],
        }
        with patch("brain.router.get_suggestions", return_value=payload):
            response = route_input(self.app, "show suggested actions")
        self.assertIn("Suggested actions:", response)
        self.assertIn("Downloads look cluttered", response)

    def test_explain_suggestions_route(self):
        payload = {
            "success": True,
            "action": "explain_suggestions",
            "result": "1. Backend looks unavailable\n   Reason: Router-only mode",
            "error": None,
            "suggestions": [
                {
                    "id": "backend_unavailable",
                    "title": "Backend looks unavailable",
                    "reason": "Router-only mode",
                    "recommended_action": "Run Diagnostics",
                    "confirmation_required": False,
                    "suggested_command": "diagnostics",
                }
            ],
        }
        with patch("brain.router.explain_suggestions", return_value=payload):
            response = route_input(self.app, "why are you suggesting this")
        self.assertIn("Backend looks unavailable", response)

    def test_dismiss_suggestion_by_index_route(self):
        self.app.last_suggestions = [
            {
                "id": "downloads_clutter",
                "title": "Downloads look cluttered",
                "reason": "Loose files detected.",
                "recommended_action": "Preview Downloads organization",
                "confirmation_required": False,
                "suggested_command": "scan my downloads",
            }
        ]
        updated_payload = {
            "success": True,
            "action": "get_suggestions",
            "result": "Found 0 active suggestions.",
            "error": None,
            "suggestions": [],
        }
        with patch("brain.router.dismiss_suggestion", return_value={"success": True, "action": "dismiss_suggestion", "result": "Dismissed suggestion: downloads_clutter", "error": None}), \
             patch("brain.router.get_suggestions", return_value=updated_payload):
            response = route_input(self.app, "dismiss suggestion 1")
        self.assertIn("Dismissed suggestion: downloads_clutter", response)

    def test_create_codex_task_route(self):
        prompt_payload = {
            "success": True,
            "action": "build_codex_prompt",
            "result": "Prompt body",
            "error": None,
            "title": "Codex feature request",
            "prompt_text": "Prompt body",
            "task_type": "feature",
        }
        created_payload = {
            "success": True,
            "action": "create_task",
            "result": "Created task 1: Feature task",
            "error": None,
            "task": {"id": 1, "title": "Feature task", "status": "pending"},
        }
        with patch("brain.router.build_codex_prompt", return_value=prompt_payload), \
             patch("brain.router.create_task", return_value=created_payload):
            response = route_input(self.app, "create a Codex task to add browser control")
        self.assertIn("Action: create_task", response)
        self.assertIn("Created task 1", response)
        self.assertIn("show task 1", response)

    def test_list_codex_tasks_route(self):
        with patch("brain.router.list_tasks", return_value={"success": True, "action": "list_tasks", "result": "1. [pending] Task one (feature)", "error": None, "tasks": []}):
            response = route_input(self.app, "list my Codex tasks")
        self.assertIn("Action: list_tasks", response)
        self.assertIn("Task one", response)

    def test_show_codex_task_route(self):
        with patch("brain.router.get_task", return_value={"success": True, "action": "get_task", "result": "Task 3: Router bugfix", "error": None, "task": {"id": 3}}):
            response = route_input(self.app, "show task 3")
        self.assertIn("get_task", response)

    def test_mark_codex_task_approved_route(self):
        with patch("brain.router.update_task_status", return_value={"success": True, "action": "update_task_status", "result": "Task 3 marked as approved.", "error": None, "task": {"id": 3, "status": "approved"}}):
            response = route_input(self.app, "mark task 3 as approved")
        self.assertIn("approved", response)

    def test_archive_codex_task_route(self):
        with patch("brain.router.archive_task", return_value={"success": True, "action": "update_task_status", "result": "Task 3 marked as archived.", "error": None, "task": {"id": 3, "status": "archived"}}):
            response = route_input(self.app, "archive task 3")
        self.assertIn("archived", response)

    def test_format_tool_response_reports_missing_evidence_instead_of_guessing(self):
        response = format_tool_response(
            {"success": True, "action": "create_report", "result": "", "error": None},
            app=self.app,
        )
        self.assertIn("Action: create_report", response)
        self.assertIn("That action returned no concrete evidence.", response)

    def test_format_tool_response_preserves_unverified_command_warning(self):
        response = format_tool_response(
            {
                "success": True,
                "action": "open_folder",
                "result": "Open request sent for folder: C:\\demo",
                "observed": ["Verified folder exists: C:\\demo"],
                "warnings": ["I cannot confirm that the File Explorer window is visible."],
            },
            app=self.app,
        )
        self.assertIn("Observed facts", response)
        self.assertIn("Warnings", response)
        self.assertIn("I cannot confirm", response)

    def test_copy_task_prompt_route(self):
        response = route_input(self.app, "copy task 3 prompt")
        self.assertIn("copy_task_prompt", response)
        self.assertIn("task 3", response)

    def test_copy_current_task_prompt_route(self):
        self.app.active_task_context = {"id": 3, "title": "Router bugfix", "status": "approved", "prompt_text": "Prompt text"}
        response = route_input(self.app, "copy the current task prompt")
        self.assertIn("copy_current_task_prompt", response)

    def test_ambiguous_followup_stays_anchored_after_task_creation(self):
        prompt_payload = {
            "success": True,
            "action": "build_codex_prompt",
            "result": "Prompt body",
            "error": None,
            "title": "Codex feature request",
            "prompt_text": "Prompt body",
            "task_type": "feature",
        }
        created_payload = {
            "success": True,
            "action": "create_task",
            "result": "Created task 1: Feature task",
            "error": None,
            "task": {"id": 1, "title": "Feature task", "status": "pending"},
        }
        with patch("brain.router.build_codex_prompt", return_value=prompt_payload), \
             patch("brain.router.create_task", return_value=created_payload):
            route_input(self.app, "create a Codex task to add browser control")

        response = route_input(self.app, "continue")
        self.assertIn("Codex task 1", response)
        self.assertIn("show task 1", response)
        self.assertEqual([], self.app.async_requests)

    def test_ambiguous_followup_stays_anchored_after_show_task(self):
        payload = {
            "success": True,
            "action": "get_task",
            "result": "Task 3: Router bugfix",
            "error": None,
            "task": {"id": 3, "title": "Router bugfix", "status": "approved"},
        }
        with patch("brain.router.get_task", return_value=payload):
            route_input(self.app, "show task 3")

        response = route_input(self.app, "next")
        self.assertIn("Codex task 3", response)
        self.assertIn("mark task 3 as done", response)


if __name__ == "__main__":
    unittest.main()
