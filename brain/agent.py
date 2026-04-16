"""Minimal registry-backed agent adapter for RogueAI."""

from __future__ import annotations

from dataclasses import dataclass

from planner import Planner
from brain.task_queue import TaskQueue
from tool_registry import build_default_registry


@dataclass
class AgentStep:
    id: int
    task_name: str
    tool_name: str
    tool_input: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_name": self.task_name,
            "tool_name": self.tool_name,
            "tool_input": dict(self.tool_input),
        }


class RogueAgent:
    """Plan and execute simple goals with the existing command registry."""

    def __init__(self, command_registry=None, planner: Planner | None = None, task_queue: TaskQueue | None = None):
        self.command_registry = command_registry or build_default_registry()
        self.planner = planner or Planner()
        self.task_queue = task_queue or TaskQueue()

    def plan(self, goal: str) -> list[dict]:
        normalized_goal = (goal or "").strip()
        if not normalized_goal:
            return []

        custom_steps = self._build_simple_plan(normalized_goal)
        if custom_steps:
            return [step.to_dict() for step in custom_steps]

        planned_tasks = self.planner.create_plan(normalized_goal)
        return [
            AgentStep(
                id=task.id,
                task_name=task.title,
                tool_name=task.tool_name,
                tool_input=task.tool_input,
            ).to_dict()
            for task in planned_tasks
        ]

    def execute(self, plan) -> dict:
        steps = [self._normalize_step(step, index) for index, step in enumerate(plan or [], start=1)]
        self.task_queue = TaskQueue()
        self.task_queue.queue_plan(steps)
        queue_result = self.task_queue.run(self.command_registry)
        results = [
            {
                "step": {
                    "id": item["task"]["id"],
                    "task_name": item["task"]["task_name"],
                    "tool_name": item["task"]["tool_name"],
                    "tool_input": item["task"]["tool_input"],
                    "status": item["task"]["status"],
                },
                "result": item["result"],
            }
            for item in queue_result["results"]
        ]
        success = queue_result["success"]

        return {
            "success": success,
            "plan": [step.to_dict() for step in steps],
            "results": results,
            "queue": self.task_queue.list_tasks(),
            "final_output": self._build_final_output(steps, results, success),
        }

    def cancel_task(self, task_id: int) -> dict:
        return self.task_queue.cancel(task_id)

    def _build_simple_plan(self, goal: str) -> list[AgentStep]:
        lowered_goal = goal.lower()
        if "organize downloads" not in lowered_goal:
            return []

        return [
            AgentStep(
                id=1,
                task_name="inspect_downloads",
                tool_name=self._pick_tool("list_path", "summarize_folder"),
                tool_input={"path_name": "downloads"},
            ),
            AgentStep(
                id=2,
                task_name="classify_files",
                tool_name=self._pick_tool("preview_folder_organization", "preview_download_organization", "summarize_folder"),
                tool_input=self._build_classification_input(),
            ),
            AgentStep(
                id=3,
                task_name="move_files",
                # Keep the step visible in the plan while preserving the current
                # non-destructive architecture unless a dedicated move tool exists.
                tool_name=self._pick_tool("move_files", "record_goal"),
                tool_input=self._build_move_input(),
            ),
        ]

    def _build_classification_input(self) -> dict:
        if self._pick_tool("preview_folder_organization", default="") == "preview_folder_organization":
            return {"path_name": "downloads", "recursive": False}
        return {"path_name": "downloads"}

    def _build_move_input(self) -> dict:
        if self._pick_tool("move_files", default="") == "move_files":
            return {"path_name": "downloads"}
        return {"goal": "move_files downloads"}

    def _normalize_step(self, step, index: int) -> AgentStep:
        if isinstance(step, AgentStep):
            return step

        if hasattr(step, "tool_name") and hasattr(step, "tool_input"):
            return AgentStep(
                id=getattr(step, "id", index),
                task_name=getattr(step, "title", getattr(step, "task_name", f"step_{index}")),
                tool_name=step.tool_name,
                tool_input=dict(getattr(step, "tool_input", {}) or {}),
            )

        payload = dict(step)
        return AgentStep(
            id=int(payload.get("id", index)),
            task_name=str(payload.get("task_name") or payload.get("title") or f"step_{index}"),
            tool_name=str(payload["tool_name"]),
            tool_input=dict(payload.get("tool_input", {}) or {}),
        )

    def _pick_tool(self, *candidates: str, default: str | None = None) -> str:
        available_tools = set()
        if hasattr(self.command_registry, "list_tools"):
            try:
                available_tools = set(self.command_registry.list_tools())
            except Exception:
                available_tools = set()

        for candidate in candidates:
            if not available_tools or candidate in available_tools:
                return candidate

        if default is not None:
            return default

        return candidates[0]

    def _build_final_output(self, steps: list[AgentStep], results: list[dict], success: bool) -> str:
        if not steps:
            return "No plan was provided."

        lines = ["RogueAgent execution:", f"Outcome: {'success' if success else 'failure'}"]
        for item in results:
            step = item["step"]
            result = item["result"]
            summary = result.get("result") or result.get("error") or ""
            status = step.get("status")
            status_label = f" [{status}]" if status else ""
            lines.append(f"{step['id']}. {step['task_name']} -> {step['tool_name']}{status_label}: {summary}")
        return "\n".join(lines)
