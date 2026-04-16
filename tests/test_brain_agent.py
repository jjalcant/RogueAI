import unittest

from brain.agent import RogueAgent
from brain.task_queue import TaskQueue
from planner import Planner
from tool_registry import ToolRegistry


class RogueAgentTests(unittest.TestCase):
    def test_plan_generates_simple_download_steps(self):
        registry = ToolRegistry()
        registry.register("list_path", lambda path_name="downloads": {"success": True, "action": "list_path", "result": path_name, "error": None})
        registry.register(
            "preview_folder_organization",
            lambda path_name="downloads", recursive=False: {
                "success": True,
                "action": "preview_folder_organization",
                "result": f"{path_name}:{recursive}",
                "error": None,
            },
        )
        registry.register("record_goal", lambda goal="": {"success": True, "action": "record_goal", "result": goal, "error": None})

        plan = RogueAgent(command_registry=registry).plan("organize downloads")

        self.assertEqual(["inspect_downloads", "classify_files", "move_files"], [step["task_name"] for step in plan])
        self.assertEqual(["list_path", "preview_folder_organization", "record_goal"], [step["tool_name"] for step in plan])

    def test_execute_runs_steps_in_sequence(self):
        calls = []
        registry = ToolRegistry()

        def first(value=""):
            calls.append(("first", value))
            return {"success": True, "action": "first", "result": f"first:{value}", "error": None}

        def second(value=""):
            calls.append(("second", value))
            return {"success": True, "action": "second", "result": f"second:{value}", "error": None}

        registry.register("first", first)
        registry.register("second", second)

        agent = RogueAgent(command_registry=registry)
        result = agent.execute(
            [
                {"id": 1, "task_name": "step_one", "tool_name": "first", "tool_input": {"value": "a"}},
                {"id": 2, "task_name": "step_two", "tool_name": "second", "tool_input": {"value": "b"}},
            ]
        )

        self.assertTrue(result["success"])
        self.assertEqual([("first", "a"), ("second", "b")], calls)
        self.assertEqual(2, len(result["results"]))
        self.assertEqual(["completed", "completed"], [task["status"] for task in result["queue"]])

    def test_execute_accepts_existing_planner_tasks(self):
        registry = ToolRegistry()
        registry.register(
            "get_system_info",
            lambda: {"success": True, "action": "get_system_info", "result": "platform: test\npython_version: 3.11\ncwd: C:/RogueAI", "error": None},
        )
        registry.register(
            "list_projects",
            lambda: {"success": True, "action": "list_projects", "result": "Tienes 0 proyectos.", "error": None},
        )
        registry.register(
            "list_saved_notes",
            lambda: {"success": True, "action": "list_saved_notes", "result": "No saved notes yet.", "error": None},
        )

        agent = RogueAgent(command_registry=registry, planner=Planner())
        result = agent.execute(Planner().create_plan("report system status"))

        self.assertTrue(result["success"])
        self.assertEqual(3, len(result["results"]))

    def test_cancel_task_delegates_to_queue(self):
        registry = ToolRegistry()
        registry.register("first", lambda: {"success": True, "action": "first", "result": "ok", "error": None})

        queue = TaskQueue()
        agent = RogueAgent(command_registry=registry, task_queue=queue)
        agent.execute([{"task_name": "first_task", "tool_name": "first", "tool_input": {}}])

        cancel_result = agent.cancel_task(1)

        self.assertFalse(cancel_result["success"])
        self.assertIn("already completed", cancel_result["error"])


if __name__ == "__main__":
    unittest.main()
