import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain import proactive_helper


class ProactiveHelperTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.memory_dir = self.base / "memory"
        self.logs_dir = self.base / "logs"
        self.state_file = self.memory_dir / "proactive_state.json"
        self.downloads = self.base / "Downloads"
        self.home = self.base / "Home"
        self.projects = self.base / "projects"
        self.downloads.mkdir(parents=True)
        self.home.mkdir(parents=True)
        self.projects.mkdir(parents=True)

        self.patches = [
            patch.object(proactive_helper, "MEMORY_DIR", self.memory_dir),
            patch.object(proactive_helper, "STATE_FILE", self.state_file),
            patch.object(proactive_helper, "LOGS_DIR", self.logs_dir),
            patch.object(proactive_helper, "LOG_FILE", self.logs_dir / "brain.log"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tempdir.cleanup()

    def test_downloads_clutter_suggestion(self):
        for index in range(5):
            (self.downloads / f"file{index}.txt").write_text("x", encoding="utf-8")

        payload = proactive_helper.get_suggestions(
            downloads_path=self.downloads,
            home_path=self.home,
            projects_path=self.projects,
            logs_path=self.logs_dir,
            backend_status={"reachable": True, "model_available": True, "message": "ok"},
        )

        ids = {item["id"] for item in payload["suggestions"]}
        self.assertIn("downloads_clutter", ids)

    def test_backend_unavailable_suggestion(self):
        payload = proactive_helper.get_suggestions(
            downloads_path=self.downloads,
            home_path=self.home,
            projects_path=self.projects,
            logs_path=self.logs_dir,
            backend_status={"reachable": False, "model_available": False, "message": "router-only mode"},
        )
        ids = {item["id"] for item in payload["suggestions"]}
        self.assertIn("backend_unavailable", ids)

    def test_workspace_clutter_suggestion(self):
        for index in range(4):
            (self.home / f"loose{index}.txt").write_text("x", encoding="utf-8")

        payload = proactive_helper.get_suggestions(
            downloads_path=self.downloads,
            home_path=self.home,
            projects_path=self.projects,
            logs_path=self.logs_dir,
            backend_status={"reachable": True, "model_available": True, "message": "ok"},
        )
        ids = {item["id"] for item in payload["suggestions"]}
        self.assertIn("home_workspace_clutter", ids)

    def test_suggestion_dismissal_hides_suggestion(self):
        for index in range(5):
            (self.downloads / f"file{index}.txt").write_text("x", encoding="utf-8")

        initial = proactive_helper.get_suggestions(
            downloads_path=self.downloads,
            home_path=self.home,
            projects_path=self.projects,
            logs_path=self.logs_dir,
            backend_status={"reachable": True, "model_available": True, "message": "ok"},
        )
        self.assertTrue(any(item["id"] == "downloads_clutter" for item in initial["suggestions"]))

        proactive_helper.dismiss_suggestion("downloads_clutter")

        updated = proactive_helper.get_suggestions(
            downloads_path=self.downloads,
            home_path=self.home,
            projects_path=self.projects,
            logs_path=self.logs_dir,
            backend_status={"reachable": True, "model_available": True, "message": "ok"},
        )
        self.assertFalse(any(item["id"] == "downloads_clutter" for item in updated["suggestions"]))


if __name__ == "__main__":
    unittest.main()
