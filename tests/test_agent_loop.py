import tempfile
import unittest
from pathlib import Path

from agent_loop import AgentLoop
from execution_logger import ExecutionLogger
from memory_manager import MemoryManager
from planner import PlannedTask, Planner
from status_reporter import StatusReporter
from task_manager import TaskManager
from tool_registry import ToolRegistry


class AgentLoopTests(unittest.TestCase):
    def test_agent_loop_executes_plan(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry = ToolRegistry()
            registry.register(
                "get_system_info",
                lambda: {
                    "success": True,
                    "action": "get_system_info",
                    "result": "{'platform': 'Windows', 'python_version': '3.11.7', 'cwd': 'C:\\\\RogueAI'}",
                    "error": None,
                },
            )
            memory_manager = MemoryManager(Path(tempdir) / "memory")
            logger = ExecutionLogger(Path(tempdir) / "logs" / "agent.log")
            reporter = StatusReporter(Path(tempdir) / "STATUS.md")
            loop = AgentLoop(registry, memory_manager, logger, reporter)

            result = loop.run(
                "report system status",
                [
                    PlannedTask(
                        id=1,
                        title="Collect current system information",
                        tool_name="get_system_info",
                        tool_input={},
                        verification={"type": "result_contains_all", "values": ["platform", "python_version", "cwd"]},
                        max_retries=0,
                    )
                ],
            )

            self.assertTrue(result["success"])
            self.assertIn("Outcome:", result["final_output"])
            self.assertIn("verified completion", result["final_output"])
            self.assertTrue((Path(tempdir) / "logs" / "agent.log").exists())

    def test_agent_loop_retries_until_verification_passes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            attempts = {"count": 0}
            registry = ToolRegistry()

            def flaky_status():
                attempts["count"] += 1
                if attempts["count"] == 1:
                    return {"success": True, "action": "get_system_info", "result": "partial", "error": None}
                return {
                    "success": True,
                    "action": "get_system_info",
                    "result": "{'platform': 'Windows', 'python_version': '3.11.7', 'cwd': 'C:\\\\RogueAI'}",
                    "error": None,
                }

            registry.register("get_system_info", flaky_status)
            memory_manager = MemoryManager(Path(tempdir) / "memory")
            logger = ExecutionLogger(Path(tempdir) / "logs" / "agent.log")
            reporter = StatusReporter(Path(tempdir) / "STATUS.md")
            loop = AgentLoop(registry, memory_manager, logger, reporter)

            result = loop.run(
                "report system status",
                [
                    Planner().create_plan("report system status")[0],
                ],
            )

            self.assertTrue(result["success"])
            self.assertEqual(2, attempts["count"])
            self.assertEqual(2, result["results"][0]["attempts"])
            self.assertTrue(result["results"][0]["verified"])

    def test_workspace_summary_verification_logic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry = ToolRegistry()
            registry.register(
                "build_workspace_summary",
                lambda: {
                    "success": True,
                    "action": "build_workspace_summary",
                    "result": "Workspace summary:\n- Platform: {'platform': 'Windows'}\n- Safe folder aliases available: downloads",
                    "error": None,
                    "report": {
                        "system_info": {"result": "{'platform': 'Windows'}"},
                        "safe_folder_aliases": {"downloads": "C:\\Downloads"},
                        "recent_agent_memory": [],
                        "known_projects": [],
                        "folder_summaries": {},
                    },
                },
            )
            loop = AgentLoop(
                registry,
                MemoryManager(Path(tempdir) / "memory"),
                ExecutionLogger(Path(tempdir) / "logs" / "agent.log"),
                StatusReporter(Path(tempdir) / "STATUS.md"),
            )
            result = loop.run(
                "workspace summary",
                [
                    PlannedTask(
                        id=1,
                        title="Build workspace summary",
                        tool_name="build_workspace_summary",
                        tool_input={},
                        verification={
                            "type": "workspace_summary_payload",
                            "required_sections": ["system_info", "safe_folder_aliases", "recent_agent_memory", "known_projects", "folder_summaries"],
                        },
                        max_retries=0,
                    )
                ],
            )
        self.assertTrue(result["success"])

    def test_agent_loop_persists_task_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            registry = ToolRegistry()
            registry.register(
                "get_system_info",
                lambda: {
                    "success": True,
                    "action": "get_system_info",
                    "result": "{'platform': 'Windows', 'python_version': '3.11.7', 'cwd': 'C:\\\\RogueAI'}",
                    "error": None,
                },
            )
            registry.register(
                "list_projects",
                lambda: {"success": True, "action": "list_projects", "result": "Ahora mismo no tienes proyectos creados.", "error": None},
            )
            registry.register(
                "list_saved_notes",
                lambda: {"success": True, "action": "list_saved_notes", "result": "No saved notes yet.", "error": None},
            )
            memory_manager = MemoryManager(base / "memory")
            task_manager = TaskManager(base / "memory")
            loop = AgentLoop(
                registry,
                memory_manager,
                ExecutionLogger(base / "logs" / "agent.log"),
                StatusReporter(base / "STATUS.md"),
                task_manager=task_manager,
            )

            result = loop.run_goal("report system status", planner=Planner())

            self.assertTrue(result["success"])
            self.assertIsNotNone(result["task_id"])
            persisted = task_manager.get_task(result["task_id"])
            self.assertTrue(persisted["success"])
            self.assertEqual("completed", persisted["task"]["status"])
            self.assertTrue(persisted["task"]["completed_steps"])

    def test_agent_loop_can_resume_task(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            registry = ToolRegistry()
            registry.register(
                "list_projects",
                lambda: {"success": True, "action": "list_projects", "result": "Ahora mismo no tienes proyectos creados.", "error": None},
            )
            memory_manager = MemoryManager(base / "memory")
            task_manager = TaskManager(base / "memory")
            task_payload = task_manager.create_task(
                "list projects",
                [
                    {
                        "id": 1,
                        "title": "List current projects",
                        "tool_name": "list_projects",
                        "tool_input": {},
                        "verification": {"type": "result_contains_any", "values": ["Tienes ", "Ahora mismo no tienes proyectos"]},
                        "max_retries": 0,
                    }
                ],
            )
            task_manager.mark_step_failed(task_payload["task"]["task_id"], 0, "temporary failure")
            loop = AgentLoop(
                registry,
                memory_manager,
                ExecutionLogger(base / "logs" / "agent.log"),
                StatusReporter(base / "STATUS.md"),
                task_manager=task_manager,
            )

            result = loop.resume_task(task_payload["task"]["task_id"])

            self.assertTrue(result["success"])
            persisted = task_manager.get_task(task_payload["task"]["task_id"])
            self.assertEqual("completed", persisted["task"]["status"])
            self.assertIn(0, persisted["task"]["completed_steps"])

    def test_folder_summary_verification_logic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            folder = Path(tempdir)
            registry = ToolRegistry()
            registry.register(
                "summarize_folder",
                lambda: {
                    "success": True,
                    "action": "summarize_folder",
                    "result": "Folder summary:\n- Total files: 1\n- Total directories: 0\n- Top file types:\n- Largest files:\n- Newest files:",
                    "error": None,
                    "summary": {
                        "path": str(folder),
                        "total_files": 1,
                        "total_directories": 0,
                        "total_size_bytes": 10,
                        "top_file_types": [],
                        "largest_files": [],
                        "newest_files": [],
                    },
                },
            )
            loop = AgentLoop(
                registry,
                MemoryManager(folder / "memory"),
                ExecutionLogger(folder / "logs" / "agent.log"),
                StatusReporter(folder / "STATUS.md"),
            )
            result = loop.run(
                "summarize folder tmp",
                [
                    PlannedTask(
                        id=1,
                        title="Summarize folder tmp",
                        tool_name="summarize_folder",
                        tool_input={},
                        verification={
                            "type": "folder_summary_payload",
                            "required_sections": ["total_files", "total_directories", "top_file_types", "largest_files", "newest_files"],
                        },
                        max_retries=0,
                    )
                ],
            )
        self.assertTrue(result["success"])

    def test_organization_preview_verification_logic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            folder = Path(tempdir)
            registry = ToolRegistry()
            registry.register(
                "preview_folder_organization",
                lambda: {
                    "success": True,
                    "action": "preview_folder_organization",
                    "result": (
                        "Organization preview: tmp\n"
                        "- Preview scope: recursive\n"
                        "- Included subfolders: True\n"
                        "- Total files analyzed: 2\n"
                        "- Nested files analyzed: 1\n"
                        "- Folder entries seen: 1\n"
                        "- Top categories:\n"
                        "  Documents: 1\n"
                        "- Sample filenames:\n"
                        "  Documents: note.txt\n"
                        "- Category counts:\n"
                        "  Documents: 1\n"
                        "- No files were modified."
                    ),
                    "error": None,
                    "preview": {
                        "path": str(folder),
                        "scope": "recursive",
                        "included_subfolders": True,
                        "total_files_analyzed": 2,
                        "nested_files_analyzed": 1,
                        "top_categories": [{"category": "Documents", "count": 1}],
                        "sample_filenames": {"Documents": ["note.txt"]},
                        "category_counts": {"Documents": 1},
                    },
                },
            )
            loop = AgentLoop(
                registry,
                MemoryManager(folder / "memory"),
                ExecutionLogger(folder / "logs" / "agent.log"),
                StatusReporter(folder / "STATUS.md"),
            )
            result = loop.run(
                "organize desktop",
                [
                    PlannedTask(
                        id=1,
                        title="Preview folder organization for desktop",
                        tool_name="preview_folder_organization",
                        tool_input={},
                        verification={
                            "type": "organization_preview_payload",
                            "required_sections": ["path", "scope", "included_subfolders", "total_files_analyzed", "nested_files_analyzed", "top_categories", "sample_filenames"],
                        },
                        max_retries=0,
                    )
                ],
            )
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
