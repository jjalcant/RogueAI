import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tool_registry import ToolRegistry, build_default_registry


class ToolRegistryTests(unittest.TestCase):
    def test_manual_registry_invocation(self):
        registry = ToolRegistry()
        registry.register("hello", lambda name="world": {"success": True, "action": "hello", "result": f"hi {name}", "error": None})
        result = registry.invoke("hello", name="rogue")
        self.assertTrue(result["success"])
        self.assertEqual("hi rogue", result["result"])

    def test_default_registry_can_list_projects(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects"
            projects.mkdir(parents=True, exist_ok=True)
            (projects / "demo").mkdir()
            registry = build_default_registry(projects)
            result = registry.invoke("list_projects")
        self.assertTrue(result["success"])
        self.assertIn("demo", result["result"])

    def test_default_registry_wraps_open_projects_folder(self):
        with tempfile.TemporaryDirectory() as tempdir:
            projects = Path(tempdir) / "projects"
            projects.mkdir(parents=True, exist_ok=True)
            with patch("tool_registry.open_projects_folder", return_value="Listo. Ya abrí tu carpeta de proyectos."):
                registry = build_default_registry(projects)
                result = registry.invoke("open_projects_folder")
        self.assertTrue(result["success"])

    def test_default_registry_wraps_list_path(self):
        with patch("tool_registry.list_path", return_value="Contenido de:\nDownloads"):
            registry = build_default_registry(Path.cwd() / "projects")
            result = registry.invoke("list_path", path_name="downloads")
        self.assertTrue(result["success"])
        self.assertIn("Contenido de", result["result"])

    def test_default_registry_exposes_workspace_summary_tool(self):
        registry = build_default_registry(Path.cwd() / "projects")
        self.assertIn("build_workspace_summary", registry.list_tools())
        self.assertIn("inspect_project", registry.list_tools())
        self.assertIn("summarize_folder", registry.list_tools())
        self.assertIn("preview_folder_organization", registry.list_tools())
        self.assertIn("system_info", registry.list_tools())
        self.assertIn("get_system_info", registry.list_tools())
        self.assertIn("system_health", registry.list_tools())
        self.assertIn("storage_overview", registry.list_tools())

    def test_registry_normalizes_empty_success_result_without_inventing_output(self):
        registry = ToolRegistry()
        registry.register("empty_success", lambda: {"success": True, "action": "empty_success", "result": "", "error": None})

        result = registry.invoke("empty_success")

        self.assertTrue(result["success"])
        self.assertEqual([], result["observed"])
        self.assertEqual([], result["errors"])


if __name__ == "__main__":
    unittest.main()
