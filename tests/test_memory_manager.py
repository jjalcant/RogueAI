import tempfile
import unittest
from pathlib import Path

from memory_manager import MemoryManager


class MemoryManagerTests(unittest.TestCase):
    def test_session_memory_isolation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = MemoryManager(Path(tempdir))
            manager.append_session("user", "hello")

            self.assertEqual(1, len(manager.get_recent_session()))
            self.assertTrue((Path(tempdir) / "session" / "current_session.json").exists())
            self.assertFalse((Path(tempdir) / "tasks" / "current_session.json").exists())

    def test_project_memory_isolation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = MemoryManager(Path(tempdir))
            manager.save_project_fact("RogueAI", "language", "Python")
            manager.save_project_inspection("RogueAI", {"project_name": "RogueAI", "total_files": 10})

            payload = manager.get_project_memory("RogueAI")
            self.assertEqual("Python", payload["facts"]["language"])
            self.assertEqual("RogueAI", payload["inspection"]["project_name"])
            self.assertTrue((Path(tempdir) / "projects" / "rogueai.json").exists())

    def test_preference_memory_isolation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = MemoryManager(Path(tempdir))
            manager.set_preference("default_project", "RogueAI")

            self.assertEqual("RogueAI", manager.get_preference("default_project"))
            self.assertTrue((Path(tempdir) / "preferences" / "agent_preferences.json").exists())

    def test_clear_session_resets_only_session_memory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = MemoryManager(Path(tempdir))
            manager.append_session("user", "hello")
            manager.save_project_fact("RogueAI", "language", "Python")

            manager.clear_session()

            self.assertEqual([], manager.get_recent_session())
            self.assertEqual("Python", manager.get_project_memory("RogueAI")["facts"]["language"])


if __name__ == "__main__":
    unittest.main()
