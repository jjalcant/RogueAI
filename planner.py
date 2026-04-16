"""Goal planner for RogueAI's lightweight agent workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PlannedTask:
    id: int
    title: str
    tool_name: str
    tool_input: dict
    verification: dict
    max_retries: int = 0

    def to_dict(self):
        return asdict(self)


class Planner:
    """Translate a user goal into an ordered list of executable tasks."""

    def create_plan(self, goal: str) -> list[PlannedTask]:
        normalized = (goal or "").strip()
        lowered = normalized.lower()
        tasks: list[PlannedTask] = []

        if not normalized:
            return tasks

        if "workspace summary" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="Build a structured workspace summary report",
                    tool_name="build_workspace_summary",
                    tool_input={},
                    verification={
                        "type": "workspace_summary_payload",
                        "required_sections": ["system_info", "safe_folder_aliases", "recent_agent_memory", "known_projects", "folder_summaries"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        if lowered.startswith("inspect project "):
            project_name = normalized[len("inspect project "):].strip()
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"Inspect project {project_name}",
                    tool_name="inspect_project",
                    tool_input={"project_name": project_name},
                    verification={
                        "type": "project_inspection_payload",
                        "required_sections": ["project_name", "path", "total_files", "total_directories", "top_level_entries"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        inspection_target = self._extract_inspection_target(normalized, lowered)
        if inspection_target:
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"Summarize folder {inspection_target}",
                    tool_name="summarize_folder",
                    tool_input={"path_name": inspection_target},
                    verification={
                        "type": "folder_summary_payload",
                        "required_sections": ["total_files", "total_directories", "top_file_types", "largest_files", "newest_files"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        organization_request = self._extract_organization_request(normalized, lowered)
        if organization_request:
            organization_target = organization_request["path_name"]
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"Preview folder organization for {organization_target}",
                    tool_name="preview_folder_organization",
                    tool_input=organization_request,
                    verification={
                        "type": "organization_preview_payload",
                        "required_sections": ["path", "scope", "included_subfolders", "total_files_analyzed", "nested_files_analyzed", "top_categories", "sample_filenames"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        if lowered.startswith("summarize folder "):
            folder_name = normalized[len("summarize folder "):].strip()
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"Summarize folder {folder_name}",
                    tool_name="summarize_folder",
                    tool_input={"path_name": folder_name},
                    verification={
                        "type": "folder_summary_payload",
                        "required_sections": ["total_files", "total_directories", "top_file_types", "largest_files", "newest_files"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        if "system status" in lowered or "diagnostics" in lowered or "health" in lowered:
            tasks.extend(
                [
                    PlannedTask(
                        id=1,
                        title="Collect current system information",
                        tool_name="get_system_info",
                        tool_input={},
                        verification={"type": "result_contains_all", "values": ["platform", "python_version", "cwd"]},
                        max_retries=1,
                    ),
                    PlannedTask(
                        id=2,
                        title="List current projects for workspace status",
                        tool_name="list_projects",
                        tool_input={},
                        verification={"type": "result_contains_any", "values": ["Tienes ", "Ahora mismo no tienes proyectos"]},
                        max_retries=1,
                    ),
                    PlannedTask(
                        id=3,
                        title="List persistent saved notes for memory status",
                        tool_name="list_saved_notes",
                        tool_input={},
                        verification={"type": "result_contains_any", "values": ["No saved notes yet.", "- "]},
                        max_retries=1,
                    ),
                ]
            )
            return tasks

        if "open project folder" in lowered or "open projects folder" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="Open the projects folder",
                    tool_name="open_projects_folder",
                    tool_input={},
                    verification={"type": "result_contains_any", "values": ["abr", "Opened", "projects"]},
                    max_retries=1,
                )
            )
            return tasks

        folder_alias = self._infer_folder_target(lowered)
        if folder_alias and ("open " in lowered or lowered.startswith("show ")) and "folder" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"Open the {folder_alias} folder",
                    tool_name="open_folder",
                    tool_input={"path_name": folder_alias},
                    verification={"type": "result_contains_any", "values": ["Opened folder", "abr", folder_alias.split()[0]]},
                    max_retries=1,
                )
            )
            return tasks

        if "list projects" in lowered or "show projects" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="List current projects",
                    tool_name="list_projects",
                    tool_input={},
                    verification={"type": "result_contains_any", "values": ["Tienes ", "Ahora mismo no tienes proyectos"]},
                    max_retries=1,
                )
            )
            return tasks

        if "memory status" in lowered or "show memory notes" in lowered or "list saved notes" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="List saved persistent notes",
                    tool_name="list_saved_notes",
                    tool_input={},
                    verification={"type": "result_contains_any", "values": ["No saved notes yet.", "- "]},
                    max_retries=1,
                )
            )
            return tasks

        if "scan downloads" in lowered or "preview downloads" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="Preview the Downloads organization plan",
                    tool_name="preview_download_organization",
                    tool_input={"path_name": "downloads"},
                    verification={"type": "preview_payload", "confirmation_phrase": "confirm organize downloads"},
                    max_retries=1,
                )
            )
            return tasks

        if "organize downloads" in lowered or "downloads status" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="Preview folder organization for downloads",
                    tool_name="preview_folder_organization",
                    tool_input={"path_name": "downloads", "recursive": False},
                    verification={
                        "type": "organization_preview_payload",
                        "required_sections": ["path", "scope", "included_subfolders", "total_files_analyzed", "nested_files_analyzed", "top_categories", "sample_filenames"],
                    },
                    max_retries=1,
                )
            )
            return tasks

        if "scan home workspace" in lowered or "preview home workspace" in lowered or "home workspace status" in lowered or "workspace status" in lowered:
            tasks.append(
                PlannedTask(
                    id=1,
                    title="Preview the home workspace organization plan",
                    tool_name="preview_home_workspace_organization",
                    tool_input={"path_name": "home workspace"},
                    verification={"type": "preview_payload", "confirmation_phrase": "confirm organize home workspace"},
                    max_retries=1,
                )
            )
            return tasks

        if folder_alias and ("list files in " in lowered or "show files in " in lowered or "list " in lowered):
            tasks.append(
                PlannedTask(
                    id=1,
                    title=f"List files in {folder_alias}",
                    tool_name="list_path",
                    tool_input={"path_name": folder_alias},
                    verification={"type": "result_contains_any", "values": ["Contenido de", "La carpeta está vacía"]},
                    max_retries=1,
                )
            )
            return tasks

        tasks.append(
            PlannedTask(
                id=1,
                title="Capture the current Rogue projects context",
                tool_name="list_projects",
                tool_input={},
                verification={"type": "result_contains_any", "values": ["Tienes ", "Ahora mismo no tienes proyectos"]},
                max_retries=1,
            )
        )
        tasks.append(
            PlannedTask(
                id=2,
                title=f"Record the unsupported goal for follow-up: {normalized}",
                tool_name="record_goal",
                tool_input={"goal": normalized},
                verification={"type": "result_contains_any", "values": ["Captured goal for follow-up"]},
            )
        )
        return tasks

    def _infer_folder_target(self, lowered_goal: str) -> str | None:
        folder_aliases = {
            "projects": "projects",
            "project folder": "projects",
            "downloads": "downloads",
            "downloads folder": "downloads",
            "documents": "documents",
            "documents folder": "documents",
            "desktop": "desktop",
            "desktop folder": "desktop",
            "pictures": "pictures",
            "pictures folder": "pictures",
            "music": "music",
            "music folder": "music",
            "videos": "videos",
            "videos folder": "videos",
            "workspace": "workspace",
            "workspace folder": "workspace",
            "this folder": "workspace",
            "current folder": "workspace",
            "home workspace": "home workspace",
        }
        for marker, alias in folder_aliases.items():
            if marker in lowered_goal:
                return alias
        return None

    def _extract_inspection_target(self, normalized_goal: str, lowered_goal: str) -> str | None:
        if lowered_goal.startswith("summarize folder "):
            return None

        list_target = self._extract_target_after_markers(
            normalized_goal,
            lowered_goal,
            [
                "list files in ",
                "show files in ",
                "list files under ",
            ],
        )
        if list_target:
            return None

        return self._extract_target_after_markers(
            normalized_goal,
            lowered_goal,
            [
                "scan ",
                "scan my ",
                "inspect ",
                "inspect my ",
                "summarize ",
                "summarise ",
                "check ",
                "check my ",
                "what is on ",
                "what is in ",
                "what's on ",
                "what's in ",
            ],
        )

    def _extract_organization_request(self, normalized_goal: str, lowered_goal: str) -> dict | None:
        marker_groups = [
            ("top_level", ["organize ", "organize my ", "organise ", "organise my "]),
            ("recursive", ["clean up ", "clean up my ", "cleanup ", "cleanup my ", "sort ", "sort my ", "arrange ", "arrange my "]),
        ]
        for mode, markers in marker_groups:
            target = self._extract_target_after_markers(normalized_goal, lowered_goal, markers)
            if target:
                return {
                    "path_name": target,
                    "recursive": mode == "recursive" or self._goal_requests_recursive(lowered_goal),
                }
        return None

    def _extract_target_after_markers(self, normalized_goal: str, lowered_goal: str, markers: list[str]) -> str | None:
        for marker in markers:
            if lowered_goal.startswith(marker):
                target = normalized_goal[len(marker):].strip(" .")
                return self._normalize_folder_target(target)
        return None

    def _goal_requests_recursive(self, lowered_goal: str) -> bool:
        return any(marker in lowered_goal for marker in [" recursive", " recursively", " including subfolders", " with subfolders"])

    def _normalize_folder_target(self, target: str) -> str | None:
        cleaned = (target or "").strip()
        if not cleaned:
            return None

        lowered = cleaned.lower()
        if lowered in {"this", "this folder", "current folder"}:
            return "workspace"
        if lowered.startswith("my "):
            cleaned = cleaned[3:].strip()
            lowered = cleaned.lower()
        if lowered.endswith(" folder") and "\\" not in cleaned and "/" not in cleaned:
            cleaned = cleaned[:-7].strip()
            lowered = cleaned.lower()

        alias = self._infer_folder_target(lowered)
        return alias or cleaned


def plan_to_text(goal: str, tasks: list[PlannedTask]) -> str:
    lines = [f"Goal: {goal}", "Planned tasks:"]
    for task in tasks:
        lines.append(f"{task.id}. {task.title} -> {task.tool_name}")
    return "\n".join(lines)
