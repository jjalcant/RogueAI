"""Minimal sequential execution queue for RogueAgent tasks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QueuedTask:
    id: int
    task_name: str
    tool_name: str
    tool_input: dict = field(default_factory=dict)
    status: str = "pending"
    result: dict | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_name": self.task_name,
            "tool_name": self.tool_name,
            "tool_input": dict(self.tool_input),
            "status": self.status,
            "result": dict(self.result) if isinstance(self.result, dict) else self.result,
            "cancel_requested": self.cancel_requested,
        }


class TaskQueue:
    """Queue agent steps and execute them one at a time."""

    def __init__(self):
        self._tasks: list[QueuedTask] = []
        self._next_id = 1

    def queue_task(self, task_name: str, tool_name: str, tool_input: dict | None = None) -> dict:
        task = QueuedTask(
            id=self._next_id,
            task_name=task_name,
            tool_name=tool_name,
            tool_input=dict(tool_input or {}),
        )
        self._next_id += 1
        self._tasks.append(task)
        return task.to_dict()

    def queue_plan(self, plan) -> list[dict]:
        queued = []
        for step in plan or []:
            payload = self._normalize_step(step)
            queued.append(
                self.queue_task(
                    task_name=payload["task_name"],
                    tool_name=payload["tool_name"],
                    tool_input=payload.get("tool_input", {}),
                )
            )
        return queued

    def run(self, command_registry) -> dict:
        results = []
        success = True

        for task in self._tasks:
            if task.status in {"completed", "failed", "cancelled"}:
                continue

            if task.cancel_requested or task.status == "cancelled":
                task.status = "cancelled"
                task.result = {
                    "success": False,
                    "action": task.tool_name,
                    "result": "",
                    "error": "Task cancelled.",
                }
                results.append({"task": task.to_dict(), "result": task.result})
                continue

            task.status = "running"
            result = command_registry.invoke(task.tool_name, **task.tool_input)
            task.result = result

            if task.cancel_requested:
                task.status = "cancelled"
                if isinstance(task.result, dict):
                    task.result = dict(task.result)
                    task.result["success"] = False
                    task.result["error"] = task.result.get("error") or "Task cancelled."
            elif result.get("success"):
                task.status = "completed"
            else:
                task.status = "failed"
                success = False

            results.append({"task": task.to_dict(), "result": task.result})

            if task.status == "failed":
                break

        return {
            "success": success and all(task.status != "failed" for task in self._tasks),
            "tasks": self.list_tasks(),
            "results": results,
        }

    def cancel(self, task_id: int) -> dict:
        task = self._find_task(task_id)
        if task is None:
            return {
                "success": False,
                "task_id": task_id,
                "result": "",
                "error": f"Task {task_id} not found.",
            }

        if task.status in {"completed", "failed", "cancelled"}:
            return {
                "success": False,
                "task_id": task_id,
                "result": "",
                "error": f"Task {task_id} is already {task.status}.",
            }

        task.cancel_requested = True
        if task.status == "pending":
            task.status = "cancelled"
            task.result = {
                "success": False,
                "action": task.tool_name,
                "result": "",
                "error": "Task cancelled.",
            }

        return {
            "success": True,
            "task_id": task_id,
            "result": f"Task {task_id} cancellation requested.",
            "error": None,
            "task": task.to_dict(),
        }

    def get_task(self, task_id: int) -> dict | None:
        task = self._find_task(task_id)
        return None if task is None else task.to_dict()

    def list_tasks(self) -> list[dict]:
        return [task.to_dict() for task in self._tasks]

    def _find_task(self, task_id: int) -> QueuedTask | None:
        for task in self._tasks:
            if task.id == int(task_id):
                return task
        return None

    def _normalize_step(self, step) -> dict:
        if hasattr(step, "tool_name") and hasattr(step, "tool_input"):
            return {
                "task_name": getattr(step, "task_name", getattr(step, "title", "task")),
                "tool_name": step.tool_name,
                "tool_input": dict(getattr(step, "tool_input", {}) or {}),
            }

        payload = dict(step)
        return {
            "task_name": str(payload.get("task_name") or payload.get("title") or "task"),
            "tool_name": str(payload["tool_name"]),
            "tool_input": dict(payload.get("tool_input", {}) or {}),
        }
