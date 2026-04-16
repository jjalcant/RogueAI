"""Central tool registry for agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory.memory_store import list_notes as list_saved_notes
from result_contract import build_result, normalize_result
from tools.files_tool import list_path, preview_download_organization, preview_home_workspace_organization
from tools.inspection_tool import build_workspace_summary, inspect_project, preview_folder_organization, summarize_folder
from tools.projects_tool import list_projects, open_projects_folder
from tools.storage_overview import storage_overview
from tools.system_info import get_system_info, system_info
from tools.system_health import system_health
from tools.system_tool import open_folder


@dataclass
class RegisteredTool:
    name: str
    callback: object
    description: str = ""


class ToolRegistry:
    def __init__(self, improvement_observer=None):
        self._tools: dict[str, RegisteredTool] = {}
        self.improvement_observer = improvement_observer

    def register(self, name: str, callback, description: str = ""):
        self._tools[name] = RegisteredTool(name=name, callback=callback, description=description)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def invoke(self, tool_name: str, **kwargs) -> dict:
        if tool_name not in self._tools:
            payload = build_result(False, tool_name, error=f"Tool not registered: {tool_name}")
            self._observe_failure(
                area="command_execution",
                trigger="execution_failure",
                command=tool_name,
                symptom=payload["error"],
                metadata={"tool_name": tool_name, "reason": "tool_not_registered"},
            )
            return payload

        try:
            raw_result = self._tools[tool_name].callback(**kwargs)
        except Exception as exc:
            payload = build_result(False, tool_name, error=str(exc))
            self._observe_failure(
                area="command_execution",
                trigger="execution_failure",
                command=tool_name,
                symptom=payload["error"],
                metadata={"tool_name": tool_name, "kwargs": kwargs},
            )
            return payload

        return self._normalize_result(tool_name, raw_result)

    def _normalize_result(self, name: str, raw_result) -> dict:
        return normalize_result(raw_result, action=name)

    def _observe_failure(self, area: str, trigger: str, command: str, symptom: str, metadata: dict | None = None):
        if self.improvement_observer is None:
            return
        try:
            self.improvement_observer.log_event(
                area=area,
                trigger=trigger,
                command=command,
                symptom=symptom or "tool execution failure",
                impact=4,
                frequency_hint=1,
                raw_context={"command": command, "symptom": symptom},
                metadata=metadata or {},
            )
        except Exception:
            return


def build_default_registry(
    projects_path: Path | None = None,
    memory_dir: Path | None = None,
    workspace_root: Path | None = None,
    improvement_observer=None,
):
    projects_path = Path(projects_path) if projects_path is not None else Path.cwd() / "projects"
    workspace_root = Path(workspace_root) if workspace_root is not None else projects_path.parent
    memory_dir = Path(memory_dir) if memory_dir is not None else workspace_root / "memory"

    registry = ToolRegistry(improvement_observer=improvement_observer)
    registry.register("system_info", lambda: system_info(), "Read verified local system information.")
    registry.register("get_system_info", lambda: get_system_info(), "Read local system information.")
    registry.register("system_health", lambda: system_health(), "Read verified local CPU, memory, and disk health metrics.")
    registry.register("storage_overview", lambda: storage_overview(), "Read verified disk usage, large folders, and large files.")
    registry.register(
        "open_projects_folder",
        lambda: open_projects_folder(projects_path),
        "Open the Rogue projects folder.",
    )
    registry.register(
        "list_projects",
        lambda: list_projects(projects_path),
        "List projects in the Rogue projects folder.",
    )
    registry.register(
        "preview_download_organization",
        lambda path_name="downloads": preview_download_organization(path_name),
        "Preview Downloads organization without moving files.",
    )
    registry.register(
        "preview_home_workspace_organization",
        lambda path_name="home workspace": preview_home_workspace_organization(path_name),
        "Preview home workspace organization without moving files.",
    )
    registry.register(
        "list_path",
        lambda path_name="downloads": list_path(path_name),
        "List files in a safe local path or alias.",
    )
    registry.register(
        "open_folder",
        lambda path_name="downloads": open_folder(path_name),
        "Open a safe local folder alias.",
    )
    registry.register(
        "list_saved_notes",
        lambda: list_saved_notes(),
        "List persistent saved notes.",
    )
    registry.register(
        "record_goal",
        lambda goal="": {
            "success": True,
            "action": "record_goal",
            "result": f"Captured goal for follow-up: {goal}",
            "error": None,
            "observed": [f"Recorded unsupported goal text for follow-up: {goal}"],
            "goal": goal,
        },
        "Capture a goal when no direct executable tool exists yet.",
    )
    registry.register(
        "build_workspace_summary",
        lambda: build_workspace_summary(workspace_root=workspace_root, projects_path=projects_path, memory_dir=memory_dir),
        "Build a structured read-only workspace summary.",
    )
    registry.register(
        "inspect_project",
        lambda project_name="": inspect_project(project_name=project_name, workspace_root=workspace_root, projects_path=projects_path),
        "Inspect a project folder safely and report its structure.",
    )
    registry.register(
        "summarize_folder",
        lambda path_name="downloads": summarize_folder(path_name=path_name, workspace_root=workspace_root, projects_path=projects_path),
        "Summarize a safe folder with deterministic counts and file metadata.",
    )
    registry.register(
        "preview_folder_organization",
        lambda path_name="downloads", recursive=False, max_entries=5000: preview_folder_organization(
            path_name=path_name,
            workspace_root=workspace_root,
            projects_path=projects_path,
            recursive=recursive,
            max_entries=max_entries,
        ),
        "Preview a safe folder organization plan without modifying files.",
    )
    return registry
