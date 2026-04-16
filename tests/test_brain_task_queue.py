import unittest

from brain.task_queue import TaskQueue


class BrainTaskQueueTests(unittest.TestCase):
    def test_queue_runs_tasks_sequentially_and_tracks_status(self):
        calls = []

        class Registry:
            def invoke(self, tool_name, **kwargs):
                calls.append((tool_name, kwargs))
                return {"success": True, "action": tool_name, "result": f"{tool_name}:{kwargs.get('value', '')}", "error": None}

        queue = TaskQueue()
        queue.queue_task("first_task", "first", {"value": "a"})
        queue.queue_task("second_task", "second", {"value": "b"})

        result = queue.run(Registry())

        self.assertTrue(result["success"])
        self.assertEqual([("first", {"value": "a"}), ("second", {"value": "b"})], calls)
        self.assertEqual(["completed", "completed"], [task["status"] for task in result["tasks"]])

    def test_queue_cancellation_marks_pending_task_cancelled(self):
        calls = []

        class Registry:
            def invoke(self, tool_name, **kwargs):
                calls.append(tool_name)
                return {"success": True, "action": tool_name, "result": tool_name, "error": None}

        queue = TaskQueue()
        first = queue.queue_task("first_task", "first", {})
        second = queue.queue_task("second_task", "second", {})
        cancel_result = queue.cancel(second["id"])
        run_result = queue.run(Registry())

        self.assertTrue(cancel_result["success"])
        self.assertEqual(["first"], calls)
        self.assertEqual("completed", queue.get_task(first["id"])["status"])
        self.assertEqual("cancelled", queue.get_task(second["id"])["status"])
        self.assertTrue(run_result["success"])

    def test_queue_stops_after_failure(self):
        calls = []

        class Registry:
            def invoke(self, tool_name, **kwargs):
                calls.append(tool_name)
                if tool_name == "first":
                    return {"success": False, "action": "first", "result": "", "error": "boom"}
                return {"success": True, "action": tool_name, "result": tool_name, "error": None}

        queue = TaskQueue()
        queue.queue_task("first_task", "first", {})
        queue.queue_task("second_task", "second", {})

        result = queue.run(Registry())

        self.assertFalse(result["success"])
        self.assertEqual(["first"], calls)
        self.assertEqual("failed", queue.get_task(1)["status"])
        self.assertEqual("pending", queue.get_task(2)["status"])


if __name__ == "__main__":
    unittest.main()
