"""Reusable runtime-state snapshotting for RogueAI operator surfaces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from task_manager import TaskManager


@dataclass
class RuntimeStateSnapshot:
    generated_at: str
    backend: dict
    tools: dict
    memory: dict
    active_tasks: dict
    recent_failures: list[dict]
    last_action: dict
    self_improvement_summary: dict
    approval_queue_summary: dict
    experiment_summary: dict
    runtime_health: dict

    def to_dict(self):
        return asdict(self)


class RuntimeStateBuilder:
    """Collect the local runtime state without changing execution behavior."""

    def build(self, app) -> RuntimeStateSnapshot:
        backend_status = getattr(app, "backend_status", {}) if isinstance(getattr(app, "backend_status", {}), dict) else {}
        modules = getattr(app, "modules", {}) if isinstance(getattr(app, "modules", {}), dict) else {}
        task_snapshot = self._get_task_snapshot(app)
        improvement_summary = self._get_improvement_summary(app)
        activity_history = list(getattr(app, "activity_history", []) or [])

        backend = {
            "reachable": bool(backend_status.get("reachable")),
            "model_available": bool(backend_status.get("model_available")),
            "model": str(backend_status.get("model") or "unavailable"),
            "message": str(backend_status.get("message") or "No backend details available."),
            "mode": "ollama-backed" if backend_status.get("reachable") and backend_status.get("model_available") else "router-only",
        }

        tools = {
            "tools_enabled": bool(modules.get("tools") or modules.get("autonomy")),
            "memory_enabled": bool(modules.get("memory", True)),
            "autonomy_enabled": bool(modules.get("autonomy")),
            "clipboard_available": True,
        }

        memory = {
            "session_turns": len(getattr(app, "conversation_memory", []) or []),
            "memory_root": str(getattr(app, "MEMORY", "")),
            "memory_items": self._count_items(app, getattr(app, "MEMORY", None)),
            "projects_tracked": self._count_items(app, getattr(app, "PROJECTS", None)),
        }

        recent_failures = self._collect_recent_failures(activity_history, task_snapshot)
        approval_queue_summary = {
            "pending_count": len(improvement_summary.get("pending_approvals", []) or []),
            "execution_ready_count": len(improvement_summary.get("execution_ready_proposals", []) or []),
            "blocked_count": len(improvement_summary.get("blocked_proposals", []) or []),
        }
        experiments = list(improvement_summary.get("experiment_summaries", []) or [])
        experiment_summary = {
            "count": len(experiments),
            "latest_experiment_id": experiments[0].get("id") if experiments else "",
            "latest_winner": (experiments[0].get("winner") or {}).get("variant") if experiments else "",
        }
        self_improvement_summary = {
            "event_count": int(improvement_summary.get("event_count", 0) or 0),
            "top_candidate": (improvement_summary.get("top_candidates", []) or [{}])[0],
            "pending_approvals": approval_queue_summary["pending_count"],
            "execution_ready": approval_queue_summary["execution_ready_count"],
        }

        active_tasks = {
            "active_count": len(task_snapshot.get("active_tasks", []) or []),
            "resumable_count": len(task_snapshot.get("resumable_tasks", []) or []),
            "recent_count": len(task_snapshot.get("recent_tasks", []) or []),
            "current_task": self._summarize_task((task_snapshot.get("active_tasks", []) or [None])[0]),
        }

        runtime_health = self._build_runtime_health(backend, recent_failures, approval_queue_summary)

        return RuntimeStateSnapshot(
            generated_at=datetime.now().isoformat(timespec="seconds"),
            backend=backend,
            tools=tools,
            memory=memory,
            active_tasks=active_tasks,
            recent_failures=recent_failures,
            last_action=self._extract_last_action(activity_history),
            self_improvement_summary=self_improvement_summary,
            approval_queue_summary=approval_queue_summary,
            experiment_summary=experiment_summary,
            runtime_health=runtime_health,
        )

    def _get_task_snapshot(self, app):
        if hasattr(app, "get_agent_task_snapshot"):
            try:
                snapshot = app.get_agent_task_snapshot()
                if isinstance(snapshot, dict):
                    return snapshot
            except Exception:
                pass

        memory_root = getattr(app, "MEMORY", None)
        if memory_root:
            try:
                manager = TaskManager(Path(memory_root))
                all_tasks = manager.list_tasks().get("tasks", [])
                return {
                    "all_tasks": all_tasks,
                    "active_tasks": manager.list_active_tasks().get("tasks", []),
                    "resumable_tasks": manager.list_resumable_tasks().get("tasks", []),
                    "recent_tasks": manager.list_recent_tasks(limit=6).get("tasks", []),
                }
            except Exception:
                pass
        return {"all_tasks": [], "active_tasks": [], "resumable_tasks": [], "recent_tasks": []}

    def _get_improvement_summary(self, app):
        if hasattr(app, "get_improvement_dashboard_summary"):
            try:
                summary = app.get_improvement_dashboard_summary(limit=5)
                if isinstance(summary, dict):
                    return summary
            except Exception:
                pass
        return {}

    def _count_items(self, app, folder):
        if folder is None:
            return 0
        if hasattr(app, "count_items"):
            try:
                return int(app.count_items(folder))
            except Exception:
                pass
        path = Path(folder)
        if not path.exists() or not path.is_dir():
            return 0
        return len(list(path.iterdir()))

    @staticmethod
    def _extract_last_action(activity_history):
        if not activity_history:
            return {"summary": "No actions yet", "timestamp": "", "command": "", "tool": ""}
        latest = dict(activity_history[-1])
        return {
            "summary": str(latest.get("summary") or "No actions yet"),
            "timestamp": str(latest.get("timestamp") or ""),
            "command": str(latest.get("command") or ""),
            "tool": str(latest.get("tool") or ""),
            "success": latest.get("success"),
        }

    def _collect_recent_failures(self, activity_history, task_snapshot):
        failures = []
        for item in activity_history[-10:]:
            if item.get("success") is False:
                failures.append(
                    {
                        "source": "activity",
                        "summary": str(item.get("summary") or "Failure recorded."),
                        "command": str(item.get("command") or ""),
                        "tool": str(item.get("tool") or ""),
                        "timestamp": str(item.get("timestamp") or ""),
                    }
                )

        for task in (task_snapshot.get("recent_tasks", []) or [])[:5]:
            for failure in task.get("failed_steps", []) or []:
                failures.append(
                    {
                        "source": "task",
                        "summary": str(failure.get("reason") or "Task step failed."),
                        "command": str(task.get("goal") or ""),
                        "tool": "agent_task",
                        "timestamp": str(failure.get("timestamp") or ""),
                    }
                )

        return failures[-6:]

    @staticmethod
    def _summarize_task(task):
        if not isinstance(task, dict):
            return {}
        steps = task.get("steps") or []
        current_step = int(task.get("current_step", 0) or 0)
        current_step_title = ""
        if 0 <= current_step < len(steps):
            current_step_title = str(steps[current_step].get("title") or "")
        return {
            "task_id": task.get("task_id"),
            "goal": task.get("goal", ""),
            "status": task.get("status", "unknown"),
            "current_step": current_step,
            "current_step_title": current_step_title,
        }

    @staticmethod
    def _build_runtime_health(backend, recent_failures, approvals):
        issues = []
        if not backend.get("reachable"):
            issues.append("backend_unreachable")
        elif not backend.get("model_available"):
            issues.append("model_unavailable")
        if len(recent_failures) >= 2:
            issues.append("recent_failures")
        if approvals.get("blocked_count", 0) > 0:
            issues.append("blocked_improvements")

        if not issues:
            label = "healthy"
            summary = "Backend, task state, and approvals look stable."
        elif "backend_unreachable" in issues or "recent_failures" in issues:
            label = "degraded"
            summary = "The runtime needs attention before taking on larger goals."
        else:
            label = "attention"
            summary = "The runtime is usable, but there are operator follow-ups to review."

        return {"label": label, "summary": summary, "issues": issues}
