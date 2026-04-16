import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from brain.agent import RogueAgent
from brain.agent_state import AgentState
from brain.auto_loop import RogueAutoLoop
from brain.policy import RoguePolicy
from brain.sensor import RogueSensor
from memory_manager import MemoryManager
from tool_registry import ToolRegistry


class RogueAutoLoopTests(unittest.TestCase):
    def test_run_cycle_executes_only_policy_approved_tasks_and_logs_to_memory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            downloads = base / "Downloads"
            downloads.mkdir()
            (downloads / "invoice.pdf").write_text("content", encoding="utf-8")

            registry = ToolRegistry()
            registry.register(
                "list_path",
                lambda path_name="downloads": {
                    "success": True,
                    "action": "list_path",
                    "result": f"listed:{path_name}",
                    "error": None,
                },
            )
            registry.register(
                "preview_folder_organization",
                lambda path_name="downloads", recursive=False: {
                    "success": True,
                    "action": "preview_folder_organization",
                    "result": f"preview:{path_name}:{recursive}",
                    "error": None,
                },
            )
            registry.register(
                "record_goal",
                lambda goal="": {
                    "success": True,
                    "action": "record_goal",
                    "result": goal,
                    "error": None,
                },
            )

            now = datetime(2026, 4, 10, 13, 0, 0)
            memory_manager = MemoryManager(base / "memory")
            loop = RogueAutoLoop(
                cycle_seconds=1,
                agent=RogueAgent(command_registry=registry),
                policy=RoguePolicy(),
                sensor=RogueSensor(downloads_path=downloads, clock=lambda: now),
                memory_manager=memory_manager,
                clock=lambda: now,
            )

            result = loop.run_cycle()

            self.assertTrue(result["success"])
            self.assertEqual("organize downloads", result["goal"])
            self.assertEqual(["inspect_downloads", "classify_files"], [task["task_name"] for task in result["approved_plan"]])
            self.assertEqual(["move_files"], [task["task_name"] for task in result["blocked_plan"]])
            self.assertEqual(2, len(result["execution"]["results"]))

            recent_entry = memory_manager.get_recent_session(1)[0]
            self.assertEqual("auto_loop", recent_entry["namespace"])
            self.assertIn("organize downloads", recent_entry["content"])

    def test_start_and_stop_manage_the_background_thread(self):
        with tempfile.TemporaryDirectory() as tempdir:
            loop = RogueAutoLoop(
                cycle_seconds=1,
                agent=RogueAgent(command_registry=ToolRegistry()),
                sensor=RogueSensor(downloads_path=Path(tempdir), clock=lambda: datetime(2026, 4, 10, 14, 0, 0)),
                memory_manager=MemoryManager(Path(tempdir) / "memory"),
                clock=lambda: datetime(2026, 4, 10, 14, 0, 0),
            )

            calls = []

            def single_cycle():
                calls.append("cycle")
                loop.stop_event.set()
                return {"success": True}

            loop.run_cycle = single_cycle

            self.assertTrue(loop.start())
            loop._thread.join(timeout=2)
            self.assertEqual(1, len(calls))
            self.assertTrue(loop.stop())
            self.assertIsNone(loop._thread)

            self.assertTrue(loop.start())
            loop._thread.join(timeout=2)
            self.assertEqual(2, len(calls))
            self.assertTrue(loop.stop())

    def test_manual_mode_collects_state_without_executing_approved_tasks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            downloads = base / "Downloads"
            downloads.mkdir()
            (downloads / "invoice.pdf").write_text("content", encoding="utf-8")

            calls = []
            registry = ToolRegistry()
            registry.register(
                "list_path",
                lambda path_name="downloads": calls.append(("list_path", path_name)) or {
                    "success": True,
                    "action": "list_path",
                    "result": path_name,
                    "error": None,
                },
            )
            registry.register(
                "preview_folder_organization",
                lambda path_name="downloads", recursive=False: calls.append(("preview_folder_organization", path_name, recursive)) or {
                    "success": True,
                    "action": "preview_folder_organization",
                    "result": path_name,
                    "error": None,
                },
            )
            registry.register(
                "record_goal",
                lambda goal="": calls.append(("record_goal", goal)) or {
                    "success": True,
                    "action": "record_goal",
                    "result": goal,
                    "error": None,
                },
            )

            now = datetime(2026, 4, 10, 15, 30, 0)
            state = AgentState(mode="manual", interval_seconds=45, clock=lambda: now)
            loop = RogueAutoLoop(
                cycle_seconds=45,
                agent=RogueAgent(command_registry=registry),
                policy=RoguePolicy(),
                sensor=RogueSensor(downloads_path=downloads, clock=lambda: now),
                memory_manager=MemoryManager(base / "memory"),
                agent_state=state,
                clock=lambda: now,
            )

            result = loop.run_cycle()
            snapshot = state.snapshot()

            self.assertTrue(result["success"])
            self.assertEqual([], calls)
            self.assertEqual(2, len(result["approved_plan"]))
            self.assertIn("without executing tasks", result["execution"]["final_output"])
            self.assertEqual("Stopped", snapshot["running_status"])
            self.assertEqual("2026-04-10 15:30:00", snapshot["last_cycle_time"])
            self.assertEqual("", snapshot["next_cycle_time"])
            self.assertIn("inspect_downloads", snapshot["approved_tasks"])


if __name__ == "__main__":
    unittest.main()
