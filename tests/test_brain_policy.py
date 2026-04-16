import unittest

from brain.policy import RoguePolicy


class RoguePolicyTests(unittest.TestCase):
    def test_filter_tasks_blocks_dangerous_steps_and_keeps_safe_ones(self):
        policy = RoguePolicy()

        result = policy.filter_tasks(
            [
                {"id": 1, "task_name": "inspect_downloads", "tool_name": "list_path", "tool_input": {"path_name": "downloads"}},
                {"id": 2, "task_name": "move_files", "tool_name": "record_goal", "tool_input": {"goal": "move downloads"}},
                {"id": 3, "task_name": "delete_files", "tool_name": "delete_path", "tool_input": {"path_name": "downloads"}},
            ]
        )

        self.assertEqual(["inspect_downloads"], [task["task_name"] for task in result["approved"]])
        self.assertEqual(["move_files", "delete_files"], [task["task_name"] for task in result["blocked"]])
        self.assertIn("safety policy", result["blocked"][0]["policy_reason"].lower())

    def test_explicit_approval_can_override_a_dangerous_task_block(self):
        policy = RoguePolicy()

        allowed, reason = policy.is_task_allowed(
            {"task_name": "move_files", "tool_name": "move_path", "tool_input": {}},
            explicit_approval=True,
        )

        self.assertTrue(allowed)
        self.assertIn("explicit approval", reason.lower())


if __name__ == "__main__":
    unittest.main()
