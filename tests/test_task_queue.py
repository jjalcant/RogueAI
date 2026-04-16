import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tasks import task_queue


class TaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.tasks_dir = self.base / "tasks"
        self.store_file = self.tasks_dir / "engineering_tasks.json"
        self.patches = [
            patch.object(task_queue, "TASKS_DIR", self.tasks_dir),
            patch.object(task_queue, "STORE_FILE", self.store_file),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tempdir.cleanup()

    def test_task_creation(self):
        result = task_queue.create_task("Feature task", "feature", "Prompt body")
        self.assertTrue(result["success"])
        self.assertEqual(1, result["task"]["id"])
        self.assertEqual("pending", result["task"]["status"])

    def test_task_listing(self):
        task_queue.create_task("Task one", "feature", "Prompt one")
        task_queue.create_task("Task two", "bugfix", "Prompt two")
        result = task_queue.list_tasks()
        self.assertTrue(result["success"])
        self.assertIn("Task one", result["result"])
        self.assertEqual(2, len(result["tasks"]))

    def test_task_retrieval_by_id(self):
        task_queue.create_task("Task one", "feature", "Prompt one")
        result = task_queue.get_task(1)
        self.assertTrue(result["success"])
        self.assertIn("Prompt one", result["result"])

    def test_task_status_update(self):
        task_queue.create_task("Task one", "feature", "Prompt one")
        result = task_queue.update_task_status(1, "approved")
        self.assertTrue(result["success"])
        self.assertEqual("approved", result["task"]["status"])


if __name__ == "__main__":
    unittest.main()
