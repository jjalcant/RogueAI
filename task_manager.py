"""Persistent task-state manager for RogueAI agent workflows."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class TaskManager:
    def __init__(self, memory_root: Path):
        self.memory_root = Path(memory_root)
        self.tasks_dir = self.memory_root / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.tasks_dir / "index.json"
        self.lock_file = self.tasks_dir / ".task_manager.lock"
        self._ensure_index()

    def create_task(self, goal, planned_steps):
        with self._locked():
            index = self._load_index()
            task_id = index["next_task_id"]
            index["next_task_id"] += 1
            self._save_index(index)

            step_records = []
            for idx, step in enumerate(planned_steps):
                step_payload = dict(step)
                step_payload.update(
                    {
                        "step_index": idx,
                        "status": "pending",
                        "result": None,
                        "failure_reason": None,
                        "verification_result": None,
                        "retry_count": 0,
                    }
                )
                step_records.append(step_payload)

            task = {
                "task_id": task_id,
                "goal": goal,
                "status": "planned",
                "created_at": self._timestamp(),
                "updated_at": self._timestamp(),
                "steps": step_records,
                "current_step": 0,
                "completed_steps": [],
                "failed_steps": [],
                "retry_counts": {str(idx): 0 for idx in range(len(step_records))},
                "verification_results": {},
                "final_summary": "",
            }
            self._save_task(task)
        return {"success": True, "task": task}

    def get_task(self, task_id):
        task = self._load_task(task_id)
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}
        return {"success": True, "task": task}

    def update_task_status(self, task_id, status, final_summary=None):
        with self._locked():
            task = self._require_task(task_id)
            if isinstance(task, dict) and task.get("error"):
                return task
            task["status"] = status
            task["updated_at"] = self._timestamp()
            if final_summary is not None:
                task["final_summary"] = final_summary
            self._save_task(task)
        return {"success": True, "task": task}

    def mark_step_complete(self, task_id, step_index, result):
        with self._locked():
            task = self._require_task(task_id)
            if isinstance(task, dict) and task.get("error"):
                return task

            step = task["steps"][step_index]
            step["status"] = "completed"
            step["result"] = result
            step["failure_reason"] = None
            step["verification_result"] = result.get("verification_result") if isinstance(result, dict) else None
            if step_index not in task["completed_steps"]:
                task["completed_steps"].append(step_index)
            task["failed_steps"] = [item for item in task["failed_steps"] if item.get("step_index") != step_index]
            task["current_step"] = self._next_incomplete_step(task)
            task["updated_at"] = self._timestamp()
            self._save_task(task)
        return {"success": True, "task": task}

    def mark_step_failed(self, task_id, step_index, reason):
        with self._locked():
            task = self._require_task(task_id)
            if isinstance(task, dict) and task.get("error"):
                return task

            step = task["steps"][step_index]
            step["status"] = "failed"
            step["failure_reason"] = reason
            failure = {
                "step_index": step_index,
                "reason": reason,
                "timestamp": self._timestamp(),
            }
            task["failed_steps"] = [item for item in task["failed_steps"] if item.get("step_index") != step_index]
            task["failed_steps"].append(failure)
            task["current_step"] = step_index
            task["updated_at"] = self._timestamp()
            self._save_task(task)
        return {"success": True, "task": task}

    def increment_retry(self, task_id, step_index):
        with self._locked():
            task = self._require_task(task_id)
            if isinstance(task, dict) and task.get("error"):
                return task

            step = task["steps"][step_index]
            step["retry_count"] += 1
            task["retry_counts"][str(step_index)] = step["retry_count"]
            task["updated_at"] = self._timestamp()
            self._save_task(task)
        return {"success": True, "task": task}

    def list_active_tasks(self):
        return self.list_tasks(statuses={"planned", "in_progress", "resumed"})

    def list_tasks(self, statuses=None, limit=None, newest_first=False):
        tasks = self._load_all_tasks()
        if statuses is not None:
            allowed = {str(status).lower() for status in statuses}
            tasks = [task for task in tasks if str(task.get("status", "")).lower() in allowed]
        tasks.sort(
            key=lambda task: (
                self._timestamp_sort_key(task.get("updated_at")),
                int(task.get("task_id", 0)),
            ),
            reverse=newest_first,
        )
        if limit is not None:
            tasks = tasks[: int(limit)]
        return {"success": True, "tasks": tasks}

    def list_resumable_tasks(self):
        tasks = []
        for task in self._load_all_tasks():
            if self._is_resumable(task):
                tasks.append(task)
        tasks.sort(
            key=lambda task: (
                self._timestamp_sort_key(task.get("updated_at")),
                int(task.get("task_id", 0)),
            ),
            reverse=True,
        )
        return {"success": True, "tasks": tasks}

    def list_recent_tasks(self, limit=10):
        return self.list_tasks(limit=limit, newest_first=True)

    def summarize_task(self, task):
        current_step_index = int(task.get("current_step", 0))
        total_steps = len(task.get("steps", []))
        current_step_title = None
        if 0 <= current_step_index < total_steps:
            current_step_title = task["steps"][current_step_index].get("title")
        return {
            "task_id": task.get("task_id"),
            "goal": task.get("goal", ""),
            "status": task.get("status", "unknown"),
            "created_at": task.get("created_at", ""),
            "updated_at": task.get("updated_at", ""),
            "current_step": current_step_index,
            "current_step_title": current_step_title,
            "total_steps": total_steps,
            "completed_steps": list(task.get("completed_steps", [])),
            "failed_steps": list(task.get("failed_steps", [])),
            "retry_counts": dict(task.get("retry_counts", {})),
            "verification_results": dict(task.get("verification_results", {})),
            "final_summary": task.get("final_summary", ""),
            "is_resumable": self._is_resumable(task),
        }

    def format_task_list(self, tasks, title="Agent Tasks"):
        if not tasks:
            return f"{title}\nObserved facts:\n- No persisted agent tasks matched this view."

        lines = [title]
        for task in tasks:
            summary = self.summarize_task(task)
            lines.append(
                f"- Task {summary['task_id']}: [{summary['status']}] "
                f"step {summary['current_step']}/{summary['total_steps']} | {summary['goal']}"
            )
        return "\n".join(lines)

    def format_task_detail(self, task):
        summary = self.summarize_task(task)
        lines = [
            f"Task {summary['task_id']}",
            "Observed facts:",
            f"- Goal: {summary['goal']}",
            f"- Persisted status: {summary['status']}",
            f"- Created: {summary['created_at']}",
            f"- Updated: {summary['updated_at']}",
            f"- Current step: {summary['current_step']} of {summary['total_steps']}",
            f"- Current step title: {summary['current_step_title'] or 'none'}",
            f"- Completed steps: {summary['completed_steps'] or []}",
            f"- Failed steps: {summary['failed_steps'] or []}",
            f"- Retry counts: {summary['retry_counts'] or {}}",
            f"- Verification results: {summary['verification_results'] or {}}",
        ]
        if summary["final_summary"]:
            lines.append("- Final summary from persisted execution state:")
            lines.append(summary["final_summary"])
        return "\n".join(lines)

    def resume_task(self, task_id):
        with self._locked():
            payload = self.get_task(task_id)
            if not payload.get("success"):
                return payload

            task = payload["task"]
            if task.get("status") == "completed":
                return {"success": False, "error": f"Task {task_id} is already completed."}

            next_step = self._next_incomplete_step(task)
            task["current_step"] = next_step
            task["status"] = "resumed" if task.get("failed_steps") else "in_progress"
            task["updated_at"] = self._timestamp()
            self._save_task(task)
        return {"success": True, "task": task}

    def set_verification_result(self, task_id, step_index, verified, reason):
        with self._locked():
            task = self._require_task(task_id)
            if isinstance(task, dict) and task.get("error"):
                return task

            task["verification_results"][str(step_index)] = {
                "verified": verified,
                "reason": reason,
                "timestamp": self._timestamp(),
            }
            task["steps"][step_index]["verification_result"] = task["verification_results"][str(step_index)]
            task["updated_at"] = self._timestamp()
            self._save_task(task)
        return {"success": True, "task": task}

    def _ensure_index(self):
        if not self.index_file.exists():
            self._save_index({"next_task_id": 1})

    def _load_index(self):
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"next_task_id": 1}

    def _save_index(self, payload):
        self.index_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _task_file(self, task_id):
        return self.tasks_dir / f"task_{int(task_id):05d}.json"

    def _load_task(self, task_id):
        path = self._task_file(task_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_task(self, task):
        path = self._task_file(task["task_id"])
        path.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")

    def _require_task(self, task_id):
        task = self._load_task(task_id)
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}
        return task

    def _load_all_tasks(self):
        tasks = []
        for path in sorted(self.tasks_dir.glob("task_*.json"), key=lambda item: item.name.lower()):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(task, dict) and task.get("task_id") is not None:
                tasks.append(task)
        return tasks

    def _next_incomplete_step(self, task):
        for idx, step in enumerate(task.get("steps", [])):
            if step.get("status") != "completed":
                return idx
        return len(task.get("steps", []))

    def _is_resumable(self, task):
        total_steps = len(task.get("steps", []))
        current_step = int(task.get("current_step", 0))
        status = str(task.get("status", "")).lower()
        if status in {"completed", "cancelled"}:
            return False
        if current_step >= total_steps and total_steps > 0:
            return False
        return True

    def _timestamp(self):
        return datetime.now().isoformat(timespec="seconds")

    def _timestamp_sort_key(self, value):
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return str(value)

    @contextmanager
    def _locked(self, timeout_seconds: float = 5.0):
        deadline = time.time() + timeout_seconds
        while True:
            try:
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError("Timed out waiting for the task manager lock.")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                os.remove(self.lock_file)
            except FileNotFoundError:
                pass
