"""Shared self-improvement runtime wiring for RogueAI desktop surfaces."""

from __future__ import annotations

import os
from pathlib import Path

from improvement_approval import ImprovementApprovalQueue
from improvement_engine import ImprovementEngine
from improvement_executor import ImprovementExecutor
from improvement_experiments import ImprovementExperiments
from improvement_guard import ImprovementGuard
from improvement_observer import ImprovementObserver
from improvement_planner import ImprovementPlanner


def is_improvement_execution_enabled(settings=None):
    raw_value = os.getenv("ROGUE_ENABLE_IMPROVEMENT_EXECUTION")
    if raw_value is None and isinstance(settings, dict):
        raw_value = settings.get("improvement_execution_enabled", True)
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() not in {"0", "false", "off", "no"}


class ImprovementRuntime:
    """Instantiate and summarize the existing RogueAI improvement stack."""

    def __init__(self, project_root: Path | str, memory_root: Path | str, settings=None):
        self.project_root = Path(project_root).resolve()
        self.memory_root = Path(memory_root).resolve()
        self.settings = settings if isinstance(settings, dict) else {}

        self.observer = ImprovementObserver(self.memory_root)
        self.engine = ImprovementEngine(self.memory_root)
        self.planner = ImprovementPlanner(self.memory_root)
        self.guard = ImprovementGuard(self.project_root)
        self.approval = ImprovementApprovalQueue(self.memory_root, self.project_root, guard=self.guard)
        self.execution_enabled = is_improvement_execution_enabled(self.settings)
        self.executor = ImprovementExecutor(
            self.project_root,
            self.memory_root,
            guard=self.guard,
            approval_queue=self.approval,
            execution_enabled=self.execution_enabled,
        )
        self.experiments = ImprovementExperiments(self.memory_root)

    def build_dashboard_summary(self, limit=5):
        candidates = self.engine.build_candidates(limit=limit)
        proposals = self.planner.build_proposals(candidates, limit=limit)
        staged_proposals = self.approval.stage_proposals(proposals)
        summary = self.engine.build_dashboard_summary(
            limit=limit,
            candidates=candidates,
            recent_proposals=staged_proposals,
        )
        summary["pending_approvals"] = self.approval.list_pending_approvals(limit=limit)
        summary["execution_ready_proposals"] = self.approval.list_execution_ready(limit=limit)
        summary["blocked_proposals"] = self.approval.list_blocked(limit=limit)
        summary["recent_executions"] = self.executor.list_recent_results(limit=limit, status="executed")
        summary["recent_rollbacks"] = self.executor.list_recent_results(limit=limit, status="rolled_back")
        summary["confidence_scores"] = [
            {
                "proposal_id": item.get("id"),
                "score": (item.get("confidence") or {}).get("score"),
                "level": (item.get("confidence") or {}).get("level"),
                "status": item.get("status"),
            }
            for item in staged_proposals[:limit]
        ]
        summary["experiment_summaries"] = self.experiments.summarize_experiments(limit=limit)
        summary["improvement_stats"] = self.executor.build_metrics_summary()
        summary["execution_enabled"] = self.execution_enabled
        return summary
