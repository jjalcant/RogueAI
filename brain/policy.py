"""Minimal safety policy for autonomous RogueAI task execution."""

from __future__ import annotations


class RoguePolicy:
    """Approve only clearly safe autonomous tasks by default."""

    SAFE_TOOL_NAMES = {
        "build_workspace_summary",
        "get_system_info",
        "inspect_project",
        "list_path",
        "list_projects",
        "list_saved_notes",
        "preview_download_organization",
        "preview_folder_organization",
        "preview_home_workspace_organization",
        "record_goal",
        "summarize_folder",
    }

    BLOCKED_TASK_TOKENS = {
        "apply_download_organization",
        "apply_home_workspace_organization",
        "create_folder",
        "delete",
        "delete_files",
        "delete_path",
        "kill",
        "kill_process",
        "move",
        "move_files",
        "move_path",
        "open_application",
        "open_folder",
        "open_path",
        "run_shell_command",
    }

    def is_task_allowed(self, task, explicit_approval: bool = False) -> tuple[bool, str]:
        normalized = self._normalize_task(task)
        tool_name = normalized["tool_name"]
        task_name = normalized["task_name"]
        searchable = f"{task_name} {tool_name}".lower()

        for token in self.BLOCKED_TASK_TOKENS:
            if token in searchable:
                if explicit_approval:
                    return True, f"Explicit approval bypassed policy block for: {token}"
                return False, f"Blocked by autonomous safety policy: {token}"

        if tool_name in self.SAFE_TOOL_NAMES:
            return True, f"Auto-approved safe tool: {tool_name}"

        if explicit_approval:
            return True, f"Explicit approval allowed tool: {tool_name}"

        return False, f"Tool is not approved for autonomous execution: {tool_name}"

    def filter_tasks(self, tasks, explicit_approval: bool = False) -> dict:
        approved = []
        blocked = []

        for task in tasks or []:
            normalized = self._normalize_task(task)
            allowed, reason = self.is_task_allowed(normalized, explicit_approval=explicit_approval)
            candidate = dict(normalized)
            candidate["policy_reason"] = reason
            if allowed:
                approved.append(candidate)
            else:
                blocked.append(candidate)

        return {
            "approved": approved,
            "blocked": blocked,
        }

    def _normalize_task(self, task) -> dict:
        if hasattr(task, "to_dict"):
            task = task.to_dict()

        payload = dict(task)
        return {
            "id": int(payload.get("id", 0)),
            "task_name": str(payload.get("task_name") or payload.get("title") or "task"),
            "tool_name": str(payload.get("tool_name") or ""),
            "tool_input": dict(payload.get("tool_input", {}) or {}),
        }
