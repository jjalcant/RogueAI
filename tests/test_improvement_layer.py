import json
import tempfile
import unittest
from pathlib import Path

from improvement_approval import ImprovementApprovalQueue
from agent_loop import AgentLoop
from execution_logger import ExecutionLogger
from improvement_engine import ImprovementEngine
from improvement_executor import ImprovementExecutor
from improvement_experiments import ImprovementExperiments
from improvement_guard import ImprovementGuard
from improvement_observer import ImprovementObserver
from improvement_planner import ImprovementPlanner
from memory_manager import MemoryManager
from planner import PlannedTask
from tool_registry import ToolRegistry


class ImprovementObserverTests(unittest.TestCase):
    def test_event_logging_creates_jsonl_and_normalizes_partial_input(self):
        with tempfile.TemporaryDirectory() as tempdir:
            observer = ImprovementObserver(Path(tempdir) / "memory")
            payload = observer.log_event(
                {
                    "area": "chat_rendering",
                    "trigger": "user_correction",
                    "symptom": "response too technical",
                    "impact": "3",
                    "metadata": "raw value",
                }
            )

            self.assertEqual("chat_rendering", payload["area"])
            self.assertEqual(3, payload["impact"])
            self.assertEqual("raw value", payload["metadata"]["metadata_value"])
            self.assertTrue((Path(tempdir) / "memory" / "improvement_log.jsonl").exists())

    def test_malformed_event_payload_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tempdir:
            observer = ImprovementObserver(Path(tempdir) / "memory")
            payload = observer.log_event(["bad", "payload"])

            self.assertEqual("malformed_event", payload["trigger"])
            self.assertEqual("invalid event payload", payload["symptom"])
            self.assertEqual(1, observer.count_events())


class ImprovementPipelineTests(unittest.TestCase):
    def test_engine_clusters_scores_and_summarizes_candidates(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            observer = ImprovementObserver(memory_root)
            observer.log_event(
                area="chat_rendering",
                trigger="user_correction",
                command="scan desktop",
                symptom="response too technical",
                impact=4,
                frequency_hint=1,
                raw_context="User asked for a simpler answer.",
            )
            observer.log_event(
                area="chat_rendering",
                trigger="user_correction",
                command="scan desktop",
                symptom="response too technical",
                impact=4,
                frequency_hint=2,
                raw_context="Still too technical.",
            )
            observer.log_event(
                area="agent_loop",
                trigger="repeated_retry",
                command="system_info",
                symptom="task required retry",
                impact=3,
                frequency_hint=1,
                raw_context="verification failed",
            )

            engine = ImprovementEngine(memory_root)
            candidates = engine.build_candidates()

            self.assertEqual("chat_rendering", candidates[0]["area"])
            self.assertEqual("response too technical", candidates[0]["symptom"])
            self.assertEqual(3, candidates[0]["frequency"])
            self.assertGreater(candidates[0]["score"], candidates[1]["score"])

            summary = engine.build_dashboard_summary(limit=2, candidates=candidates[:2])
            self.assertEqual(3, summary["event_count"])
            self.assertEqual("chat_rendering", summary["common_areas"][0]["area"])

    def test_planner_generates_structured_proposals_and_updates_history(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            planner = ImprovementPlanner(memory_root)
            proposals = planner.build_proposals(
                [
                    {
                        "id": "imp_001",
                        "area": "chat_rendering",
                        "symptom": "response too technical",
                        "trigger": "user_correction",
                        "frequency": 5,
                        "impact": 4,
                        "ease": 8,
                        "score": 160,
                        "examples": [],
                        "status": "candidate",
                    }
                ],
                min_score=1,
            )

            self.assertEqual(1, len(proposals))
            self.assertEqual("imp_001", proposals[0]["id"])
            self.assertEqual("proposed", proposals[0]["status"])
            self.assertIn("rogue_app.py", proposals[0]["files"])
            self.assertIn("patch_category", proposals[0])
            self.assertIn("confidence", proposals[0])
            self.assertIn("validation_plan", proposals[0])
            self.assertGreater(proposals[0]["confidence"]["score"], 0)

            history_path = Path(tempdir) / "memory" / "improvement_history.json"
            history = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual("imp_001", history["proposals"][0]["id"])

    def test_guard_blocks_sensitive_or_broad_changes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            guard = ImprovementGuard(tempdir)
            allowed = guard.evaluate_proposal_safety(
                {
                    "title": "Simplify chat output formatting",
                    "problem": "Repeated wording issue",
                    "scope": "Small local fix in chat rendering",
                    "recommended_action": "Add a small response-normalization step.",
                    "files": ["rogue_app.py"],
                }
            )
            blocked = guard.evaluate_proposal_safety(
                {
                    "title": "Rewrite architecture and dependencies",
                    "problem": "Broad change",
                    "scope": "Rewrite framework integration everywhere",
                    "recommended_action": "Rewrite the architecture and update dependencies.",
                    "files": ["requirements.txt", "..\\secrets.env"],
                }
            )

            self.assertTrue(allowed["allowed"])
            self.assertFalse(blocked["allowed"])
            self.assertIn("requirements.txt", blocked["blocked_files"])


class ImprovementApprovalExecutorTests(unittest.TestCase):
    def test_approval_state_transitions_and_confidence_gating(self):
        with tempfile.TemporaryDirectory() as tempdir:
            memory_root = Path(tempdir) / "memory"
            project_root = Path(tempdir)
            approval = ImprovementApprovalQueue(memory_root, project_root)

            ready = approval.stage_proposals(
                [
                    {
                        "id": "imp_ready",
                        "title": "Tighten formatter wording",
                        "problem": "Repeated formatting friction",
                        "scope": "Small local change",
                        "recommended_action": "Replace one message.",
                        "files": ["sample.py"],
                        "patch_category": "text_update",
                        "patch_strategy": "replace_text",
                        "patch_plan": {
                            "category": "text_update",
                            "strategy": "replace_text",
                            "files": ["sample.py"],
                            "operations": [],
                        },
                        "confidence": {"score": 84, "level": "high", "factors": {}, "notes": []},
                    },
                    {
                        "id": "imp_blocked",
                        "title": "Broad architecture change",
                        "problem": "Vague architectural issue",
                        "scope": "Large cross-cutting rewrite",
                        "recommended_action": "Rewrite architecture",
                        "files": ["architecture.py"],
                        "patch_category": "framework_change",
                        "patch_strategy": "replace_text",
                        "patch_plan": {
                            "category": "framework_change",
                            "strategy": "replace_text",
                            "files": ["architecture.py"],
                            "operations": [],
                        },
                        "confidence": {"score": 18, "level": "low", "factors": {}, "notes": []},
                    },
                ]
            )

            by_id = {item["id"]: item for item in ready}
            self.assertEqual("ready_for_review", by_id["imp_ready"]["status"])
            self.assertEqual("blocked", by_id["imp_blocked"]["status"])
            self.assertEqual(1, len(approval.list_pending_approvals()))

            approved = approval.approve_proposal("imp_ready")
            self.assertEqual("approved", approved["status"])
            self.assertIsNone(approval.approve_proposal("imp_blocked"))

    def test_executor_dry_run_returns_diff_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            sample = base / "sample.py"
            sample.write_text("value = 1\n", encoding="utf-8")
            approval = ImprovementApprovalQueue(base / "memory", base)
            executor = ImprovementExecutor(base, base / "memory", approval_queue=approval)

            proposal = {
                "id": "imp_dry",
                "status": "approved",
                "files": ["sample.py"],
                "patch_category": "text_update",
                "patch_plan": {
                    "category": "text_update",
                    "strategy": "replace_text",
                    "files": ["sample.py"],
                    "operations": [
                        {"op": "replace_text", "path": "sample.py", "old": "value = 1", "new": "value = 2"}
                    ],
                },
                "validation_plan": {"python_files": ["sample.py"], "imports": [], "tests": []},
            }

            result = executor.execute_proposal(proposal, dry_run=True)

            self.assertEqual("dry_run", result["status"])
            self.assertEqual("value = 1\n", sample.read_text(encoding="utf-8"))
            self.assertEqual([], result["backup_paths"])
            self.assertEqual(["sample.py"], result["files_touched"])
            self.assertTrue(result["validation_passed"])

    def test_executor_creates_backup_and_executes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            sample = base / "sample.py"
            sample.write_text("value = 1\n", encoding="utf-8")
            approval = ImprovementApprovalQueue(base / "memory", base)
            executor = ImprovementExecutor(base, base / "memory", approval_queue=approval)

            staged = approval.stage_proposals(
                [
                    {
                        "id": "imp_exec",
                        "title": "Update sample value",
                        "problem": "Repeated wording issue",
                        "scope": "Small local change",
                        "recommended_action": "Replace one literal.",
                        "files": ["sample.py"],
                        "patch_category": "text_update",
                        "patch_strategy": "replace_text",
                        "patch_plan": {
                            "category": "text_update",
                            "strategy": "replace_text",
                            "files": ["sample.py"],
                            "operations": [
                                {"op": "replace_text", "path": "sample.py", "old": "value = 1", "new": "value = 2"}
                            ],
                        },
                        "validation_plan": {"python_files": ["sample.py"], "imports": [], "tests": []},
                        "confidence": {"score": 92, "level": "high", "factors": {}, "notes": []},
                    }
                ]
            )[0]
            approved = approval.approve_proposal(staged["id"])

            result = executor.execute_proposal(approved)

            self.assertEqual("executed", result["status"])
            self.assertTrue(result["validation_passed"])
            self.assertTrue(result["backup_paths"])
            self.assertEqual("value = 2\n", sample.read_text(encoding="utf-8"))
            self.assertEqual("executed", approval.get_proposal("imp_exec")["status"])

    def test_executor_rolls_back_on_validation_failure(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            sample = base / "sample.py"
            original = "value = 1\n"
            sample.write_text(original, encoding="utf-8")
            approval = ImprovementApprovalQueue(base / "memory", base)
            executor = ImprovementExecutor(base, base / "memory", approval_queue=approval)

            staged = approval.stage_proposals(
                [
                    {
                        "id": "imp_rollback",
                        "title": "Introduce a broken patch",
                        "problem": "Test rollback path",
                        "scope": "Small local change",
                        "recommended_action": "Replace one literal with invalid syntax.",
                        "files": ["sample.py"],
                        "patch_category": "text_update",
                        "patch_strategy": "replace_text",
                        "patch_plan": {
                            "category": "text_update",
                            "strategy": "replace_text",
                            "files": ["sample.py"],
                            "operations": [
                                {"op": "replace_text", "path": "sample.py", "old": "value = 1", "new": "value = "}
                            ],
                        },
                        "validation_plan": {"python_files": ["sample.py"], "imports": [], "tests": []},
                        "confidence": {"score": 92, "level": "high", "factors": {}, "notes": []},
                    }
                ]
            )[0]
            approved = approval.approve_proposal(staged["id"])

            result = executor.execute_proposal(approved)

            self.assertEqual("rolled_back", result["status"])
            self.assertFalse(result["validation_passed"])
            self.assertTrue(result["rollback_performed"])
            self.assertEqual(original, sample.read_text(encoding="utf-8"))
            self.assertEqual("rolled_back", approval.get_proposal("imp_rollback")["status"])

    def test_executor_blocks_unsafe_proposal_and_noop_patch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            sample = base / "sample.py"
            sample.write_text("value = 1\n", encoding="utf-8")
            executor = ImprovementExecutor(base, base / "memory")

            unsafe = executor.execute_proposal(
                {
                    "id": "imp_unsafe",
                    "status": "approved",
                    "files": ["requirements.txt"],
                    "patch_category": "dependency_change",
                    "patch_plan": {
                        "category": "dependency_change",
                        "strategy": "replace_text",
                        "files": ["requirements.txt"],
                        "operations": [
                            {"op": "replace_text", "path": "requirements.txt", "old": "", "new": "PySide6==6.8.0"}
                        ],
                    },
                }
            )
            noop = executor.execute_proposal(
                {
                    "id": "imp_noop",
                    "status": "approved",
                    "files": ["sample.py"],
                    "patch_category": "text_update",
                    "patch_plan": {
                        "category": "text_update",
                        "strategy": "replace_text",
                        "files": ["sample.py"],
                        "operations": [
                            {"op": "replace_text", "path": "sample.py", "old": "value = 1", "new": "value = 1"}
                        ],
                    },
                    "validation_plan": {"python_files": ["sample.py"], "imports": [], "tests": []},
                }
            )

            self.assertEqual("blocked", unsafe["status"])
            self.assertEqual("blocked", noop["status"])
            self.assertIn("no effective file changes", " ".join(noop["notes"]).lower())

    def test_experiment_winner_selection_logic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            experiments = ImprovementExperiments(Path(tempdir) / "memory")
            experiments.register_experiment(
                "exp_formatter",
                {"label": "Formatter A", "description": "Current phrasing"},
                {"label": "Formatter B", "description": "Tighter phrasing"},
                metric_directions={"command_success_rate": "higher_is_better"},
            )
            experiments.record_usage("exp_formatter", "A", {"command_success_rate": 0.92})
            experiments.record_usage("exp_formatter", "A", {"command_success_rate": 0.88})
            experiments.record_usage("exp_formatter", "B", {"command_success_rate": 0.75})
            experiments.record_usage("exp_formatter", "B", {"command_success_rate": 0.70})

            winner = experiments.select_winner("exp_formatter", primary_metric="command_success_rate", min_samples=2)
            summary = experiments.summarize_experiments(limit=1)[0]

            self.assertEqual("A", winner["variant"])
            self.assertEqual("A", summary["winner"]["variant"])


class ImprovementIntegrationTests(unittest.TestCase):
    def test_tool_registry_logs_execution_failures_to_observer(self):
        with tempfile.TemporaryDirectory() as tempdir:
            observer = ImprovementObserver(Path(tempdir) / "memory")
            registry = ToolRegistry(improvement_observer=observer)

            payload = registry.invoke("missing_tool")

            self.assertFalse(payload["success"])
            events = observer.read_events()
            self.assertEqual(1, len(events))
            self.assertEqual("command_execution", events[0]["area"])
            self.assertEqual("execution_failure", events[0]["trigger"])

    def test_agent_loop_logs_retry_and_verification_friction(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            attempts = {"count": 0}
            registry = ToolRegistry()

            def flaky_tool():
                attempts["count"] += 1
                if attempts["count"] == 1:
                    return {"success": True, "action": "get_system_info", "result": "partial", "error": None}
                return {
                    "success": True,
                    "action": "get_system_info",
                    "result": "{'platform': 'Windows', 'python_version': '3.11.7', 'cwd': 'C:\\\\RogueAI'}",
                    "error": None,
                }

            registry.register("get_system_info", flaky_tool)
            observer = ImprovementObserver(base / "memory")
            loop = AgentLoop(
                registry,
                MemoryManager(base / "memory"),
                ExecutionLogger(base / "logs" / "agent.log"),
                improvement_observer=observer,
            )

            result = loop.run(
                "report system status",
                [
                    PlannedTask(
                        id=1,
                        title="Collect current system information",
                        tool_name="get_system_info",
                        tool_input={},
                        verification={"type": "result_contains_all", "values": ["platform", "python_version", "cwd"]},
                        max_retries=1,
                    )
                ],
            )

            self.assertTrue(result["success"])
            triggers = [item["trigger"] for item in observer.read_events()]
            self.assertIn("verification_failure", triggers)
            self.assertIn("repeated_retry", triggers)


if __name__ == "__main__":
    unittest.main()
