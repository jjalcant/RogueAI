import tempfile
import unittest
from pathlib import Path

from task_manager import TaskManager


class TaskManagerTests(unittest.TestCase):
    def make_step(self, title="step", tool_name="tool"):
        return {"id": 1, "title": title, "tool_name": tool_name, "tool_input": {}, "verification": {}, "max_retries": 0}

    def test_task_creation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            payload = manager.create_task("report status", [self.make_step()])

            self.assertTrue(payload["success"])
            self.assertEqual(1, payload["task"]["task_id"])
            self.assertTrue((Path(tempdir) / "tasks" / "task_00001.json").exists())

    def test_multiple_task_creation_increments_ids(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            first = manager.create_task("one", [self.make_step()])
            second = manager.create_task("two", [self.make_step()])

            self.assertEqual(1, first["task"]["task_id"])
            self.assertEqual(2, second["task"]["task_id"])

    def test_task_status_updates(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("report status", [self.make_step()])
            payload = manager.update_task_status(1, "in_progress")

            self.assertEqual("in_progress", payload["task"]["status"])

    def test_step_completion_and_failure_tracking(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task(
                "report status",
                [
                    {"id": 1, "title": "step one", "tool_name": "tool_one", "tool_input": {}, "verification": {}, "max_retries": 0},
                    {"id": 2, "title": "step two", "tool_name": "tool_two", "tool_input": {}, "verification": {}, "max_retries": 0},
                ],
            )

            complete = manager.mark_step_complete(1, 0, {"value": "ok"})
            failed = manager.mark_step_failed(1, 1, "verification failed")

            self.assertIn(0, complete["task"]["completed_steps"])
            self.assertEqual(1, failed["task"]["failed_steps"][0]["step_index"])

    def test_retry_count_tracking(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("report status", [self.make_step()])
            manager.increment_retry(1, 0)
            payload = manager.get_task(1)

            self.assertEqual(1, payload["task"]["retry_counts"]["0"])

    def test_task_resume_behavior(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task(
                "report status",
                [
                    {"id": 1, "title": "step one", "tool_name": "tool_one", "tool_input": {}, "verification": {}, "max_retries": 0},
                    {"id": 2, "title": "step two", "tool_name": "tool_two", "tool_input": {}, "verification": {}, "max_retries": 0},
                ],
            )
            manager.mark_step_complete(1, 0, {"value": "ok"})
            manager.mark_step_failed(1, 1, "temporary failure")
            payload = manager.resume_task(1)

            self.assertTrue(payload["success"])
            self.assertEqual(1, payload["task"]["current_step"])
            self.assertIn(payload["task"]["status"], {"resumed", "in_progress"})

    def test_task_memory_isolation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("report status", [self.make_step()])

            self.assertTrue((Path(tempdir) / "tasks" / "index.json").exists())
            self.assertFalse((Path(tempdir) / "session" / "index.json").exists())

    def test_list_tasks_returns_all_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("first goal", [self.make_step("first step")])
            manager.create_task("second goal", [self.make_step("second step")])

            payload = manager.list_tasks()

            self.assertEqual(2, len(payload["tasks"]))
            self.assertEqual("first goal", payload["tasks"][0]["goal"])
            self.assertEqual("second goal", payload["tasks"][1]["goal"])

    def test_list_active_tasks_filters_completed_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("active goal", [self.make_step("active step")])
            manager.create_task("done goal", [self.make_step("done step")])
            manager.update_task_status(2, "completed")

            payload = manager.list_active_tasks()

            self.assertEqual(1, len(payload["tasks"]))
            self.assertEqual("active goal", payload["tasks"][0]["goal"])

    def test_list_resumable_tasks_filters_completed_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("failed goal", [self.make_step("failed step")])
            manager.mark_step_failed(1, 0, "temporary issue")
            manager.create_task("done goal", [self.make_step("done step")])
            manager.mark_step_complete(2, 0, {"value": "ok"})
            manager.update_task_status(2, "completed")

            payload = manager.list_resumable_tasks()

            self.assertEqual(1, len(payload["tasks"]))
            self.assertEqual("failed goal", payload["tasks"][0]["goal"])

    def test_list_recent_tasks_returns_newest_first(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("older goal", [self.make_step("older step")])
            manager.create_task("newer goal", [self.make_step("newer step")])

            payload = manager.list_recent_tasks(limit=1)

            self.assertEqual(1, len(payload["tasks"]))
            self.assertEqual("newer goal", payload["tasks"][0]["goal"])

    def test_format_task_detail_includes_required_fields(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manager = TaskManager(Path(tempdir))
            manager.create_task("inspect system", [self.make_step("collect info", "get_system_info")])
            manager.increment_retry(1, 0)
            manager.set_verification_result(1, 0, True, "verified")
            manager.update_task_status(1, "completed", final_summary="Outcome: success")

            task = manager.get_task(1)["task"]
            detail = manager.format_task_detail(task)

            self.assertIn("Task 1", detail)
            self.assertIn("- Goal: inspect system", detail)
            self.assertIn("- Persisted status: completed", detail)
            self.assertIn("- Retry counts:", detail)
            self.assertIn("- Verification results:", detail)
            self.assertIn("Outcome: success", detail)


if __name__ == "__main__":
    unittest.main()
