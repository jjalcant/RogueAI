import unittest
from datetime import datetime

from brain.agent_state import AgentState


class AgentStateTests(unittest.TestCase):
    def test_apply_cycle_payload_formats_snapshot_fields(self):
        state = AgentState(mode="assist", interval_seconds=30, clock=lambda: datetime(2026, 4, 10, 15, 0, 0))
        payload = {
            "cycle_started_at": "2026-04-10T14:59:30",
            "success": True,
            "sensor_state": {
                "downloads": {
                    "exists": True,
                    "recursive": False,
                    "file_count": 4,
                    "total_size_human": "12.0 MB",
                    "recent_file_count": 2,
                }
            },
            "plan": [
                {"task_name": "inspect_downloads", "tool_name": "list_path"},
                {"task_name": "classify_files", "tool_name": "preview_folder_organization"},
            ],
            "approved_plan": [{"task_name": "inspect_downloads"}],
            "blocked_plan": [{"task_name": "move_files"}],
            "execution": {
                "final_output": "Assist mode: approved tasks were prepared but not executed.",
            },
        }

        state.apply_cycle_payload(payload, running=True)
        snapshot = state.snapshot()

        self.assertEqual("Running", snapshot["running_status"])
        self.assertEqual("2026-04-10 14:59:30", snapshot["last_cycle_time"])
        self.assertEqual("2026-04-10 15:00:30", snapshot["next_cycle_time"])
        self.assertIn("Downloads: 4 files, 12.0 MB, 2 recent files", snapshot["latest_observation_summary"])
        self.assertIn("1. inspect_downloads -> list_path", snapshot["latest_generated_plan"])
        self.assertEqual("- inspect_downloads", snapshot["approved_tasks"])
        self.assertEqual("- move_files", snapshot["blocked_tasks"])
        self.assertIn("prepared but not executed", snapshot["last_result"])


if __name__ == "__main__":
    unittest.main()
