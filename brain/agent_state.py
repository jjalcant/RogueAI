"""Thread-safe shared state for the RogueAI autonomous loop."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta


class AgentState:
    """Store autonomous loop state in a UI-safe snapshot-friendly structure."""

    VALID_MODES = ("manual", "assist", "auto")

    def __init__(self, mode: str = "auto", interval_seconds: int = 60, clock=None):
        self.clock = clock or datetime.now
        self._lock = threading.RLock()
        self._state = {
            "running": False,
            "cycle_in_progress": False,
            "running_status": "Stopped",
            "mode": self._normalize_mode(mode),
            "interval_seconds": max(1, int(interval_seconds)),
            "last_cycle_time": "",
            "next_cycle_time": "",
            "latest_observation_summary": "No observation captured yet.",
            "latest_generated_plan": "No plan generated yet.",
            "approved_tasks": "None.",
            "blocked_tasks": "None.",
            "last_result": "Idle.",
            "last_error": "",
        }

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def get_mode(self) -> str:
        with self._lock:
            return self._state["mode"]

    def get_interval_seconds(self) -> int:
        with self._lock:
            return int(self._state["interval_seconds"])

    def set_mode(self, mode: str) -> str:
        normalized = self._normalize_mode(mode)
        with self._lock:
            self._state["mode"] = normalized
            if normalized == "manual" and not self._state["cycle_in_progress"]:
                self._state["next_cycle_time"] = ""
            self._update_running_status_locked()
        return normalized

    def set_interval_seconds(self, seconds: int) -> int:
        interval_seconds = max(1, int(seconds))
        with self._lock:
            self._state["interval_seconds"] = interval_seconds
            if self._state["running"] and not self._state["cycle_in_progress"]:
                self._state["next_cycle_time"] = self._format_dt(self._now() + timedelta(seconds=interval_seconds))
        return interval_seconds

    def mark_started(self):
        with self._lock:
            self._state["running"] = True
            self._state["next_cycle_time"] = self._format_dt(self._now())
            self._update_running_status_locked()

    def mark_stopped(self):
        with self._lock:
            self._state["running"] = False
            self._state["cycle_in_progress"] = False
            self._state["next_cycle_time"] = ""
            self._update_running_status_locked()

    def mark_cycle_started(self):
        with self._lock:
            self._state["cycle_in_progress"] = True
            self._update_running_status_locked()

    def apply_cycle_payload(self, payload: dict, running: bool = False):
        with self._lock:
            self._state["running"] = bool(running)
            self._state["cycle_in_progress"] = False
            self._state["last_cycle_time"] = self._format_timestamp(payload.get("cycle_started_at"))
            self._state["latest_observation_summary"] = self._build_observation_summary(payload.get("sensor_state", {}))
            self._state["latest_generated_plan"] = self._format_plan(payload.get("plan", []), empty="No plan generated.")
            self._state["approved_tasks"] = self._format_task_names(payload.get("approved_plan", []))
            self._state["blocked_tasks"] = self._format_task_names(payload.get("blocked_plan", []))
            self._state["last_result"] = self._build_result_summary(payload)
            self._state["last_error"] = str(payload.get("error") or "").strip()

            if self._state["running"]:
                next_time = self._now() + timedelta(seconds=self._state["interval_seconds"])
                self._state["next_cycle_time"] = self._format_dt(next_time)
            else:
                self._state["next_cycle_time"] = ""
            self._update_running_status_locked()

    def apply_cycle_error(self, error: str, cycle_started_at: str | None = None, running: bool = False):
        with self._lock:
            self._state["running"] = bool(running)
            self._state["cycle_in_progress"] = False
            if cycle_started_at:
                self._state["last_cycle_time"] = self._format_timestamp(cycle_started_at)
            self._state["last_result"] = f"Cycle failed: {error}"
            self._state["last_error"] = str(error).strip()
            if self._state["running"]:
                next_time = self._now() + timedelta(seconds=self._state["interval_seconds"])
                self._state["next_cycle_time"] = self._format_dt(next_time)
            else:
                self._state["next_cycle_time"] = ""
            self._update_running_status_locked()

    def _update_running_status_locked(self):
        if self._state["cycle_in_progress"] and self._state["running"]:
            self._state["running_status"] = "Running"
            return
        if self._state["cycle_in_progress"]:
            self._state["running_status"] = "Running one cycle"
            return
        if self._state["running"]:
            self._state["running_status"] = "Running"
            return
        self._state["running_status"] = "Stopped"

    def _build_observation_summary(self, sensor_state: dict) -> str:
        downloads = sensor_state.get("downloads", {})
        if not downloads:
            return "No observation captured."
        if not downloads.get("exists"):
            return f"Downloads folder not found at {downloads.get('path', 'unknown path')}."
        scope = "recursive" if downloads.get("recursive") else "top-level"
        return (
            f"Downloads: {downloads.get('file_count', 0)} files, "
            f"{downloads.get('total_size_human', '0 B')}, "
            f"{downloads.get('recent_file_count', 0)} recent files ({scope})."
        )

    def _build_result_summary(self, payload: dict) -> str:
        execution = payload.get("execution", {}) or {}
        final_output = str(execution.get("final_output") or "").strip()
        if final_output:
            return final_output
        if payload.get("success"):
            return "Cycle completed."
        return str(payload.get("error") or "Cycle failed.")

    def _format_plan(self, plan: list[dict], empty: str) -> str:
        if not plan:
            return empty
        lines = []
        for index, step in enumerate(plan, start=1):
            task_name = step.get("task_name") or step.get("title") or f"step_{index}"
            tool_name = step.get("tool_name", "tool")
            lines.append(f"{index}. {task_name} -> {tool_name}")
        return "\n".join(lines)

    def _format_task_names(self, tasks: list[dict]) -> str:
        if not tasks:
            return "None."
        return "\n".join(f"- {task.get('task_name') or task.get('title') or 'task'}" for task in tasks)

    def _format_timestamp(self, value) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            return self._format_dt(value)
        try:
            return self._format_dt(datetime.fromisoformat(str(value)))
        except ValueError:
            return str(value)

    def _format_dt(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in self.VALID_MODES:
            raise ValueError(f"Unsupported agent mode: {mode}")
        return normalized

    def _now(self) -> datetime:
        value = self.clock()
        if isinstance(value, datetime):
            return value
        raise TypeError("clock must return a datetime instance.")
