import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_manager import MemoryManager
from tools.inspection_tool import build_workspace_summary, inspect_project, preview_folder_organization, resolve_safe_folder, summarize_folder


class InspectionToolTests(unittest.TestCase):
    def test_workspace_summary_generation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()
            (projects / "demo").mkdir()
            memory_dir = base / "memory"
            memory = MemoryManager(memory_dir)
            memory.append_session("assistant", "workspace summary cached")
            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)

            with patch("tools.inspection_tool.get_system_info", return_value={"success": True, "action": "get_system_info", "result": "{'platform': 'Windows'}", "error": None}):
                result = build_workspace_summary(workspace_root=base, projects_path=projects, memory_dir=memory_dir)

        self.assertTrue(result["success"])
        self.assertIn("safe_folder_aliases", result["report"])
        self.assertIn("folder_summaries", result["report"])
        self.assertEqual(1, len(result["report"]["recent_agent_memory"]))
        self.assertIn("Known projects", result["result"])

    def test_project_inspection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            project = projects / "demo"
            project.mkdir(parents=True)
            (project / "README.md").write_text("demo", encoding="utf-8")
            (project / "app.py").write_text("print('hi')", encoding="utf-8")
            (project / "requirements.txt").write_text("requests", encoding="utf-8")

            result = inspect_project("demo", workspace_root=base, projects_path=projects)

        self.assertTrue(result["success"])
        self.assertEqual("demo", result["inspection"]["project_name"])
        self.assertGreaterEqual(result["inspection"]["total_files"], 3)
        self.assertIn("README.md", result["inspection"]["readme_files"])

    def test_folder_summary(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()
            target = base / "folder"
            target.mkdir()
            (target / "a.txt").write_text("a", encoding="utf-8")
            (target / "b.py").write_text("print('hi')", encoding="utf-8")

            result = summarize_folder(str(target), workspace_root=base, projects_path=projects)

        self.assertTrue(result["success"])
        self.assertEqual(2, result["summary"]["total_files"])
        self.assertIn("top_file_types", result["summary"])
        self.assertIn("largest_files", result["summary"])

    def test_preview_folder_organization(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()
            target = base / "desktop"
            target.mkdir()
            (target / "todo.txt").write_text("note", encoding="utf-8")
            (target / "photo.jpg").write_text("image", encoding="utf-8")

            result = preview_folder_organization(str(target), workspace_root=base, projects_path=projects)

        self.assertTrue(result["success"])
        self.assertEqual("top_level_only", result["preview"]["scope"])
        self.assertFalse(result["preview"]["included_subfolders"])
        self.assertEqual(2, result["preview"]["total_files_analyzed"])
        self.assertIn("Documents", result["preview"]["category_counts"])
        self.assertIn("Images", result["preview"]["category_counts"])
        self.assertIn("Total files analyzed", result["result"])
        self.assertIn("Top categories", result["result"])
        self.assertIn("Sample filenames", result["result"])
        self.assertIn("No files were modified.", result["result"])

    def test_preview_folder_organization_recursive_counts_nested_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()
            target = base / "downloads"
            nested = target / "nested"
            nested.mkdir(parents=True)
            (target / "todo.txt").write_text("note", encoding="utf-8")
            (nested / "song.mp3").write_text("audio", encoding="utf-8")
            (nested / "photo.png").write_text("image", encoding="utf-8")

            result = preview_folder_organization(str(target), workspace_root=base, projects_path=projects, recursive=True)

        self.assertTrue(result["success"])
        self.assertEqual("recursive", result["preview"]["scope"])
        self.assertTrue(result["preview"]["included_subfolders"])
        self.assertEqual(3, result["preview"]["total_files_analyzed"])
        self.assertEqual(2, result["preview"]["nested_files_analyzed"])
        self.assertIn("Nested files analyzed", result["result"])
        self.assertIn("Included subfolders: True", result["result"])

    def test_preview_folder_organization_category_detection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()
            target = base / "workspace"
            nested = target / "folder"
            nested.mkdir(parents=True)
            (target / "photo.jpg").write_text("image", encoding="utf-8")
            (target / "report.pdf").write_text("doc", encoding="utf-8")
            (target / "track.mp3").write_text("audio", encoding="utf-8")
            (target / "clip.mp4").write_text("video", encoding="utf-8")
            (target / "archive.zip").write_text("zip", encoding="utf-8")
            (target / "main.py").write_text("print('hi')", encoding="utf-8")
            (target / "installer.exe").write_text("exe", encoding="utf-8")
            (target / "shortcut.lnk").write_text("link", encoding="utf-8")
            (target / "misc.bin").write_text("bin", encoding="utf-8")

            result = preview_folder_organization(str(target), workspace_root=base, projects_path=projects, recursive=True)

        self.assertTrue(result["success"])
        counts = result["preview"]["category_counts"]
        self.assertIn("Images", counts)
        self.assertIn("Documents", counts)
        self.assertIn("Audio", counts)
        self.assertIn("Video", counts)
        self.assertIn("Archives", counts)
        self.assertIn("Code", counts)
        self.assertIn("Installers", counts)
        self.assertIn("Shortcuts", counts)
        self.assertIn("Folders", counts)
        self.assertIn("Other", counts)

    def test_alias_resolution_supports_desktop_downloads_and_documents(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()

            desktop = resolve_safe_folder("desktop", workspace_root=base, projects_path=projects)
            downloads = resolve_safe_folder("downloads", workspace_root=base, projects_path=projects)
            documents = resolve_safe_folder("documents", workspace_root=base, projects_path=projects)

        self.assertIsNotNone(desktop)
        self.assertEqual("desktop", desktop.name.lower())
        self.assertIsNotNone(downloads)
        self.assertEqual("downloads", downloads.name.lower())
        self.assertIsNotNone(documents)
        self.assertEqual("documents", documents.name.lower())

    def test_preview_folder_organization_returns_clear_failure_for_missing_target(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            projects = base / "projects"
            projects.mkdir()

            result = preview_folder_organization("missing_safe_alias", workspace_root=base, projects_path=projects)

        self.assertFalse(result["success"])
        self.assertIn("Safe folder not found or unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
