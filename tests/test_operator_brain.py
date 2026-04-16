import tempfile
import unittest
from pathlib import Path

from decision_policy import DecisionAction, DecisionPolicy
from operator_brain import OperatorBrain
from operator_modes import OperatorMode, classify_operator_mode
from runtime_state import RuntimeStateBuilder
from verification_policy import VerificationPolicy


class FakeObserver:
    def __init__(self):
        self.events = []

    def log_event(self, **payload):
        self.events.append(payload)
        return payload


class DummyApp:
    def __init__(self, base):
        self.MEMORY = Path(base) / "memory"
        self.PROJECTS = Path(base) / "projects"
        self.LOGS = Path(base) / "logs"
        self.MEMORY.mkdir(parents=True, exist_ok=True)
        self.PROJECTS.mkdir(parents=True, exist_ok=True)
        self.LOGS.mkdir(parents=True, exist_ok=True)
        self.backend_status = {
            "reachable": True,
            "model_available": True,
            "message": "backend ok",
            "model": "llama3:latest",
        }
        self.modules = {"memory": True, "tools": True, "autonomy": True}
        self.conversation_memory = [{"role": "user", "content": "scan desktop"}]
        self.activity_history = []
        self.last_structured_response_payload = None
        self.last_agent_workflow_payload = None
        self.last_operator_summary = None
        self.improvement_observer = FakeObserver()
        self.improvement_summary = {
            "event_count": 3,
            "top_candidates": [{"area": "operator_brain", "symptom": "verification mismatch"}],
            "pending_approvals": [{"id": "imp_1"}],
            "execution_ready_proposals": [],
            "blocked_proposals": [],
            "experiment_summaries": [{"id": "exp_1", "winner": {"variant": "A"}}],
        }
        self.task_snapshot = {
            "all_tasks": [],
            "active_tasks": [
                {
                    "task_id": 7,
                    "goal": "Inspect Desktop",
                    "status": "in_progress",
                    "current_step": 1,
                    "steps": [{"title": "Inspect Desktop"}, {"title": "Summarize results"}],
                    "failed_steps": [],
                }
            ],
            "resumable_tasks": [],
            "recent_tasks": [],
        }

    def count_items(self, folder):
        return len(list(Path(folder).iterdir()))

    def get_agent_task_snapshot(self):
        return self.task_snapshot

    def get_improvement_dashboard_summary(self, limit=5):
        return self.improvement_summary


class OperatorModeTests(unittest.TestCase):
    def test_mode_selection_covers_expected_modes(self):
        cases = {
            "hello": OperatorMode.CHAT,
            "open downloads": OperatorMode.DIRECT_COMMAND,
            "scan desktop": OperatorMode.AGENT_TASK,
            "system diagnostics": OperatorMode.DIAGNOSTIC,
            "show improvements": OperatorMode.IMPROVEMENT_REVIEW,
            "review experiments": OperatorMode.EXPERIMENT_REVIEW,
            "improve yourself": OperatorMode.SAFE_MODE,
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, classify_operator_mode(text))


class RuntimeStateBuilderTests(unittest.TestCase):
    def test_runtime_state_assembles_operator_snapshot(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = DummyApp(tempdir)
            app.activity_history = [
                {"summary": "Failed agent run", "command": "scan desktop", "tool": "agent", "timestamp": "12:00:00", "success": False}
            ]
            snapshot = RuntimeStateBuilder().build(app)

            self.assertEqual("ollama-backed", snapshot.backend["mode"])
            self.assertTrue(snapshot.tools["tools_enabled"])
            self.assertEqual(1, snapshot.active_tasks["active_count"])
            self.assertEqual(1, snapshot.approval_queue_summary["pending_count"])
            self.assertEqual("healthy", snapshot.runtime_health["label"])
            self.assertEqual("Failed agent run", snapshot.recent_failures[0]["summary"])


class DecisionPolicyTests(unittest.TestCase):
    def test_decision_policy_routes_agent_and_safe_mode_conservatively(self):
        policy = DecisionPolicy()

        agent_decision = policy.decide("scan desktop", OperatorMode.AGENT_TASK)
        safe_decision = policy.decide("improve yourself", OperatorMode.SAFE_MODE)

        self.assertEqual(DecisionAction.USE_AGENT_WORKFLOW.value, agent_decision.action)
        self.assertEqual("scan desktop", agent_decision.goal)
        self.assertEqual(DecisionAction.SAFE_PROPOSAL_ONLY.value, safe_decision.action)


class VerificationPolicyTests(unittest.TestCase):
    def test_verification_normalizes_success_even_when_text_looks_failed(self):
        payload = {"success": True, "action": "open_folder", "result": "Opened folder", "summary": {"path": "C:\\Temp"}}

        result = VerificationPolicy().normalize(
            response_text="Command failed, but folder is open.",
            structured_payload=payload,
        )

        self.assertEqual("verified_success", result.status)
        self.assertTrue(result.mismatch_detected)


class OperatorBrainImprovementRoutingTests(unittest.TestCase):
    def test_operator_brain_routes_repeated_friction_into_improvement_observer(self):
        with tempfile.TemporaryDirectory() as tempdir:
            app = DummyApp(tempdir)
            app.activity_history = [
                {"summary": "Failure one", "command": "scan desktop", "tool": "router", "timestamp": "12:00:00", "success": False},
                {"summary": "Failure two", "command": "scan desktop", "tool": "router", "timestamp": "12:01:00", "success": False},
            ]

            def failing_router(app_instance, text):
                app_instance.last_structured_response_payload = {
                    "success": False,
                    "action": "open_folder",
                    "result": "",
                    "error": "Command failed.",
                }
                return "Command failed."

            brain = OperatorBrain(app, router_handler=failing_router)
            brain.handle_request("open downloads")

            self.assertEqual("failed", app.last_operator_summary["verification_status"])
            self.assertIn("repeated_friction", app.last_operator_summary["improvement_signal"]["signals"])
            self.assertEqual("repeated_friction", app.improvement_observer.events[-1]["trigger"])


if __name__ == "__main__":
    unittest.main()
