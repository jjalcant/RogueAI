"""Qt-compatible backend controller that preserves RogueAI desktop behavior."""

from __future__ import annotations

import ast
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import brain.llm_bridge as llm_bridge
from app_config import StartupCheckError, run_startup_checks, write_json
from brain.agent_state import AgentState
from brain.auto_loop import RogueAutoLoop
from brain.llm_bridge import ask_llm as _ask_llm, get_ollama_status
from brain.proactive_helper import get_suggestions
from improvement_runtime import ImprovementRuntime
from memory.memory_store import list_notes as list_memory_notes
from operator_brain import OperatorBrain
from result_contract import format_response_text
from task_manager import TaskManager
from tasks.task_queue import get_task, list_tasks
from ui_command_registry import build_command_registry, normalize_command_name
from verification_policy import verification_status_to_message_kind

BASE = Path(__file__).resolve().parent.parent
MEMORY = BASE / "memory"
PROJECTS = BASE / "projects"
AGENTS = BASE / "agents"
AUTONOMY = BASE / "autonomy"
CONFIG = BASE / "config"
LOGS = BASE / "logs"

NOTES_FILE = MEMORY / "notes.md"
BRAIN_LOG = LOGS / "brain.log"
SETTINGS_FILE = CONFIG / "settings.json"
MODULES_FILE = CONFIG / "modules.json"

OFFICIAL_HELP_SECTIONS = [
    (
        "Navigation",
        [
            "help                Show this help screen",
            "back                Return to previous screen",
            "home                Return to command center",
            "esc                 Shortcut for back/home behavior",
        ],
    ),
    (
        "System",
        [
            "status              Show system summary",
            "system status       Show CPU, RAM, disk, tasks",
            "system health       Show verified CPU, RAM, and disk usage",
            "storage overview    Show verified disk usage and largest files",
            "agent status        Show agent state",
            "tasks               Show active tasks",
            "task history        Show previous tasks",
            "memory              Show memory status and recent remembered actions",
        ],
    ),
    (
        "Analysis",
        [
            "scan downloads      Analyze Downloads folder",
            "analyze downloads   Same as scan downloads",
            "scan desktop        Analyze Desktop folder",
            "analyze desktop     Same as scan desktop",
            "largest files       Show largest files in current analysis",
            "newest files        Show newest files in current analysis",
            "top file types      Show file type breakdown",
            "duplicates          Find duplicate candidates",
        ],
    ),
    (
        "Actions",
        [
            "open downloads      Open Downloads folder",
            "open desktop        Open Desktop folder",
            "open folder         Open selected folder",
            "organize downloads  Sort Downloads into categories",
            "smart cleanup       Clean obvious junk safely",
            "cleanup temp        Reserved cleanup command",
            "move files          Reserved explicit move workflow",
            "generate report     Create a report from current analysis",
        ],
    ),
]

COMMAND_DISPLAY_TITLES = {
    "system info": "System Information",
    "get system info": "System Information",
    "system health": "System Health",
    "scan desktop": "Desktop Scan",
    "inspect desktop": "Desktop Scan",
    "scan downloads": "Downloads Scan",
    "inspect downloads": "Downloads Scan",
    "storage overview": "Storage Overview",
    "workspace summary": "Workspace Summary",
    "system status": "System Status",
    "organize desktop": "Desktop Organization",
    "organize downloads": "Downloads Organization",
}

HANDLED = object()
ENVELOPE_WARNING_PREFIX = "__warning__::"


class RogueBackendController:
    """Preserve the desktop command and router behavior for the Qt shell."""

    def __init__(
        self,
        *,
        message_callback: Callable[[dict], None] | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        navigation_callback: Callable[[str], None] | None = None,
        state_callback: Callable[[], None] | None = None,
        clipboard_setter: Callable[[str], None] | None = None,
    ):
        self.MEMORY = MEMORY
        self.PROJECTS = PROJECTS
        self.AGENTS = AGENTS
        self.AUTONOMY = AUTONOMY
        self.CONFIG = CONFIG
        self.LOGS = LOGS

        self._message_callback = message_callback
        self._status_callback = status_callback
        self._navigation_callback = navigation_callback
        self._state_callback = state_callback
        self._clipboard_setter = clipboard_setter

        self.pending_action = None
        self.conversation_memory = []
        self.message_history = []
        self.activity_history = []
        self.last_suggestions = []
        self.last_agent_workflow_payload = None
        self.last_structured_response_payload = None
        self.last_operator_summary = None
        self.last_runtime_state_snapshot = None
        self.last_verification_result = None
        self.active_task_context = None
        self.active_agent_task_context = None
        self.agent_task_view_mode = "recent"
        self.command_registry = None
        self.current_view_name = "command_center"
        self.last_browser_target = None
        self.downloads_path = Path.home() / "Downloads"
        self.home_path = Path.home()
        self.quick_commands = [
            ("Scan Desktop", "scan desktop"),
            ("Inspect Downloads", "inspect downloads"),
            ("Workspace Summary", "workspace summary"),
            ("System Status", "agent report system status"),
            ("Tasks", "agent list tasks"),
            ("Organize Desktop", "organize desktop"),
        ]
        self._last_status_signature = None

        self.startup_report = self.run_startup_checks()
        self.settings = self.startup_report["settings"]
        self.modules = self.startup_report["modules"]
        self.backend_status = get_ollama_status()
        self.agent_task_manager = TaskManager(self.MEMORY)
        self.agent_state = AgentState(mode="manual", interval_seconds=60)
        self.improvement_runtime = ImprovementRuntime(BASE, self.MEMORY, settings=self.settings)
        self.improvement_observer = self.improvement_runtime.observer
        self.improvement_engine = self.improvement_runtime.engine
        self.improvement_planner = self.improvement_runtime.planner
        self.improvement_guard = self.improvement_runtime.guard
        self.improvement_approval = self.improvement_runtime.approval
        self.improvement_execution_enabled = self.improvement_runtime.execution_enabled
        self.improvement_executor = self.improvement_runtime.executor
        self.improvement_experiments = self.improvement_runtime.experiments
        self.operator_brain = OperatorBrain(self)
        self.auto_loop = None
        self.log_action("Qt controller initialized")

    def run_startup_checks(self):
        required_folders = [
            self.MEMORY,
            self.PROJECTS,
            self.AGENTS,
            self.AUTONOMY,
            self.CONFIG,
            self.LOGS,
        ]
        try:
            return run_startup_checks(required_folders, SETTINGS_FILE, MODULES_FILE)
        except StartupCheckError:
            raise

    @staticmethod
    def normalize_theme_name(theme_name):
        lowered = str(theme_name or "").strip().lower()
        if lowered == "dark":
            return "Dark"
        return "Light"

    def log_action(self, action):
        try:
            self.LOGS.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(BRAIN_LOG, "a", encoding="utf-8") as handle:
                handle.write(f"[{now}] {action}\n")
        except Exception:
            pass

    def _emit_state(self):
        if self._state_callback is not None:
            self._state_callback()

    def set_status_feedback(self, message, level="info"):
        signature = (str(level), str(message))
        if signature != self._last_status_signature:
            self.log_action(f"UI status -> {str(level).upper()}: {message}")
            self._last_status_signature = signature
        if self._status_callback is not None:
            self._status_callback(str(message), str(level))

    def navigate(self, view_name):
        self.current_view_name = view_name
        if self._navigation_callback is not None:
            self._navigation_callback(view_name)
        self._emit_state()

    def get_command_registry(self):
        if self.command_registry is None:
            self.command_registry = build_command_registry(self)
        return self.command_registry

    def get_command_definition(self, command_text):
        normalized = normalize_command_name(command_text)
        if not normalized:
            return None
        for definition in self.get_command_registry():
            names = (definition.name,) + tuple(definition.aliases)
            if normalized in {normalize_command_name(value) for value in names}:
                return definition
        return None

    def confirm_command_execution(self, definition, confirm_callback=None):
        if confirm_callback is None:
            return True
        message = definition.confirmation_message or f"Run command: {definition.name}?"
        return bool(confirm_callback("Confirm Command", message))

    def execute_command(self, command_text=None, confirm_callback=None):
        raw_value = str(command_text or "").strip()
        if not raw_value:
            self.set_status_feedback("Ready | Enter a command to execute.", level="ready")
            return False

        definition = self.get_command_definition(raw_value)
        if not definition:
            message = "Unknown command. Type help to see available commands."
            self._emit_operator_message(
                "Command Not Available",
                summary=[message],
                recommendations=["Open Help to review the supported desktop commands."],
                kind="warning",
            )
            self.set_status_feedback(f"Error | {message}", level="error")
            return False

        if definition.requires_confirmation and not self.confirm_command_execution(definition, confirm_callback):
            message = f"Cancelled command: {definition.name}"
            self._emit_operator_message(
                self._normalized_command_display_title(definition.name, fallback="Command"),
                summary=[message],
                recommendations=["Run the command again if you still want to continue."],
                kind="warning",
            )
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return False

        self.set_status_feedback(f"Running | {definition.name}", level="running")
        try:
            result = definition.handler(raw_value)
        except Exception as exc:
            self.log_action(f"Registry command failure [{definition.name}]: {exc}")
            self._emit_operator_message(
                self._compose_result_title(self._normalized_command_display_title(definition.name, fallback="Command"), False),
                summary=["The command could not be completed."],
                details=["A local desktop command handler raised an unexpected error."],
                recommendations=["Retry the command once. If it keeps failing, review the Agent or diagnostics surfaces."],
                kind="warning",
            )
            self.record_activity(
                "warning",
                f"Command failed: {definition.name}",
                command=raw_value,
                tool="command_registry",
                success=False,
            )
            self.set_status_feedback("Error | The command could not be completed.", level="error")
            return False

        self.record_activity(
            "command",
            f"Executed {definition.name}",
            command=raw_value,
            tool="command_registry",
            success=True,
        )
        self.set_status_feedback(f"Done | Command executed: {definition.name}", level="done")
        if isinstance(result, str) and result not in {"break", "__ASYNC__"}:
            self.add_message("Rogue", self.build_chat_response_text(result))
        return result is not False

    def execute_chat_input(self, command_text=None, confirm_callback=None, emit_user_message=True):
        raw_value = str(command_text or "").strip()
        if not raw_value:
            self.set_status_feedback("Ready | Enter a command to execute.", level="ready")
            return False

        self.add_message("You", raw_value, kind="user", emit=emit_user_message)
        self.remember_turn("user", raw_value)
        definition = self.get_command_definition(raw_value)
        if definition is not None:
            self.log_action(f"Chat submit routed to registry: {raw_value}")
            return self.execute_command(raw_value, confirm_callback=confirm_callback)

        self.log_action(f"Chat submit routed to router fallback: {raw_value}")
        return self.run_router_command(raw_value, show_user=False, remember_user=False)

    def classify_message(self, sender, message):
        lowered = str(message).lower()
        if str(sender).lower() in {"tú", "tu", "you"}:
            return "user"
        if "confirm with:" in lowered or "confirmation required" in lowered or "preview only" in lowered:
            return "confirm"
        if "diagnostics" in lowered or "startup check" in lowered or "backend:" in lowered:
            return "diagnostics"
        if "error" in lowered or "no pude" in lowered or "failed" in lowered or "warning" in lowered:
            return "warning"
        if any(token in lowered for token in ["open_", "apply_", "preview_", "get_system_info", "list_moves", "find_move_by_name"]):
            return "tool"
        return "assistant"

    def sanitize_chat_message(self, message):
        text = str(message or "")
        replacements = {
            "inspect_downloads": "Inspect downloads",
            "inspect_desktop": "Inspect desktop",
            "inspect_workspace": "Inspect workspace",
            "workspace_summary": "Workspace summary",
            "list_path": "List folder contents",
            "preview_folder_organization": "Preview folder organization",
            "apply_download_organization": "Organize downloads",
            "apply_home_workspace_organization": "Organize home workspace",
            "move_files": "Move files",
            "delete_files": "Delete files",
            "kill_process": "Stop process",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def add_message(self, sender, message, kind=None, emit=True):
        if str(sender).lower() == "rogue":
            message = self.sanitize_chat_message(message)
        if kind is None:
            kind = self.classify_message(sender, message)
        payload = {
            "sender": sender,
            "message": str(message),
            "kind": kind,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self.message_history.append(payload)
        self.message_history = self.message_history[-200:]
        if emit and self._message_callback is not None:
            self._message_callback(payload)
        self._emit_state()

    def clear_chat(self):
        self.message_history = []
        self.add_message("Rogue", "Chat cleared.", kind="assistant")
        self.record_activity("ui", "Cleared chat")
        self.set_status_feedback("Done | Chat cleared", level="done")

    def record_activity(self, kind, summary, command=None, tool=None, success=None):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "kind": kind,
            "summary": summary,
            "command": command,
            "tool": tool,
            "success": success,
        }
        self.activity_history.append(entry)
        self.activity_history = self.activity_history[-50:]
        self._emit_state()

    def remember_turn(self, role, content):
        self.conversation_memory.append({"role": role, "content": content})
        max_turns = int(self.settings.get("max_memory_turns", 12))
        self.conversation_memory = self.conversation_memory[-max_turns:]

    def process_input(self, text):
        return self.get_operator_brain().handle_request(text)

    def get_operator_brain(self):
        if getattr(self, "operator_brain", None) is None:
            self.operator_brain = OperatorBrain(self)
        return self.operator_brain

    def get_operator_summary(self):
        return self.get_operator_brain().get_operator_summary()

    def get_recent_context_list(self):
        lines = []
        for item in self.conversation_memory[-6:]:
            role = "User" if item["role"] == "user" else "Assistant"
            lines.append(f"{role}: {item['content']}")
        return lines

    def ask_llm_safe(self, prompt, recent_context):
        try:
            response = _ask_llm(prompt, recent_context)
            if not isinstance(response, str):
                return str(response)
            cleaned = response.strip()
            if "router-only mode" in cleaned.lower():
                self.log_action(f"LLM degraded mode used for prompt: {prompt[:80]}")
            return cleaned if cleaned else "No recibi una respuesta valida del modelo."
        except Exception as exc:
            self.log_action(f"LLM backend error: {exc}")
            return f"No pude consultar el backend LLM: {exc}"

    def start_async_fallback(self, text):
        worker = threading.Thread(target=self._background_fallback, args=(text,), daemon=True)
        worker.start()

    def _background_fallback(self, text):
        recent = self.get_recent_context_list()
        response = self.ask_llm_safe(text, recent)
        self.finish_async_response(response)

    def finish_async_response(self, response):
        self.remember_turn("assistant", response)
        chat_response = self.build_chat_response_text(response)
        message_kind = self.classify_message("Rogue", chat_response)
        self.add_message("Rogue", chat_response, kind=message_kind)
        self.record_activity(
            message_kind,
            self.summarize_action_from_text(chat_response),
            tool="llm",
            success=message_kind != "warning",
        )
        self.set_status_feedback("Done | Response ready", level="done")

    def summarize_action_from_text(self, message):
        lowered = str(message).lower()
        if "preview_download_organization" in lowered:
            return "Previewed downloads organization"
        if "apply_download_organization" in lowered:
            return "Organized downloads"
        if "preview_home_workspace_organization" in lowered:
            return "Previewed home workspace"
        if "apply_home_workspace_organization" in lowered:
            return "Organized home workspace"
        if "open_folder" in lowered:
            return "Opened folder"
        if "open_application" in lowered:
            return "Opened application"
        if "record_moves" in lowered or "list_moves" in lowered or "find_move_by_name" in lowered:
            return "Reviewed file move history"
        if "diagnostics" in lowered:
            return "Viewed diagnostics"
        if "saved" in lowered or "guard" in lowered:
            return "Saved memory note"
        return str(message).splitlines()[0][:80]

    def run_router_command(self, text, show_user=True, remember_user=True):
        if show_user:
            self.add_message("You", text, kind="user")
        if remember_user:
            self.remember_turn("user", text)
        self.last_agent_workflow_payload = None
        self.last_structured_response_payload = None
        self.set_status_feedback(f"Running | {text}", level="running")

        try:
            response = self.process_input(text)
            if response == "__ASYNC__":
                self.record_activity("llm", "Async fallback started", command=text, tool="llm", success=True)
                self.set_status_feedback("Running | Waiting for model response", level="running")
                return response

            chat_response = self.build_chat_response_text(response)
            operator_summary = self.get_operator_summary()
            verification = operator_summary.get("verification", {})
            default_kind = self.classify_message("Rogue", chat_response)
            message_kind = verification.get("message_kind") or verification_status_to_message_kind(
                verification.get("status"),
                default=default_kind,
            )
            activity_summary = operator_summary.get("operator_summary_line") or self.summarize_action_from_text(chat_response)
            self.remember_turn("assistant", response)
            self.add_message("Rogue", chat_response, kind=message_kind)
            self.record_activity(
                message_kind,
                activity_summary,
                command=text,
                tool=message_kind,
                success=verification.get("status") not in {"blocked", "failed"},
            )
            status_level = verification.get("ui_level") or self._status_level_for_router_response(message_kind)
            status_prefix = {
                "error": "Error",
                "warning": "Warning",
                "running": "Running",
                "ready": "Ready",
                "info": "Ready",
            }.get(status_level, "Done")
            self.set_status_feedback(
                f"{status_prefix} | {verification.get('reason') or activity_summary}",
                level=status_level,
            )
            return response
        except Exception as exc:
            self.log_action(f"Router command failure [{text}]: {exc}")
            self._emit_operator_message(
                self._compose_result_title(self._normalized_command_display_title(text, fallback="Command Result"), False),
                summary=["The command could not be completed."],
                details=["The router raised an unexpected internal error while processing this request."],
                recommendations=["Retry the command once. If it keeps failing, review the Agent or diagnostics surfaces."],
                kind="warning",
            )
            self.record_activity("warning", "Internal processing error", command=text, tool="router", success=False)
            self.set_status_feedback("Error | The command could not be completed.", level="error")
            return "The command could not be completed."

    def _status_level_for_router_response(self, message_kind):
        payload = self.last_structured_response_payload
        if isinstance(payload, dict):
            if payload.get("success") is False or payload.get("errors"):
                return "error"
            if payload.get("warnings"):
                return "warning"
        if message_kind == "warning":
            return "warning"
        return "done"

    def run_registered_router_command(self, command_text):
        self.run_router_command(command_text, show_user=False, remember_user=False)
        return HANDLED

    def show_help(self):
        self.navigate("help")
        self.set_status_feedback("Ready | Help view", level="info")
        return HANDLED

    def show_home(self):
        self.navigate("command_center")
        self.set_status_feedback("Ready | Command Center", level="info")
        return HANDLED

    def show_agent_view(self):
        self.navigate("agent")
        self.set_status_feedback("Ready | Agent view", level="info")
        return HANDLED

    def show_chat_view(self):
        self.navigate("chat")
        self.set_status_feedback("Ready | Chat view", level="info")
        return HANDLED

    def show_command_center(self):
        self.navigate("command_center")
        self.set_status_feedback("Ready | Command Center", level="info")
        return HANDLED

    def show_explain_mode(self):
        self.navigate("explain")
        self.set_status_feedback("Ready | Explain Mode", level="info")
        return HANDLED

    def show_friction_radar(self):
        self.navigate("friction")
        self.set_status_feedback("Ready | Friction Radar", level="info")
        return HANDLED

    def show_settings_view(self):
        self.navigate("settings")
        self.set_status_feedback("Ready | Settings view", level="info")
        return HANDLED

    def go_back(self, _event=None):
        return self.show_home()

    def show_status_overview(self):
        self._emit_operator_message(
            "System Status",
            summary=[
                f"Backend: {self.get_backend_mode_label()}",
                f"Model: {self.backend_status.get('model', 'unknown')}",
                f"Active tasks: {self.refresh_task_indicator()}",
            ],
            details=[
                f"Memory: {'Enabled' if self.modules.get('memory') else 'Disabled'}",
                f"Tools: {'Loaded' if self.modules.get('tools') or self.modules.get('autonomy') else 'Unavailable'}",
                f"Projects items: {self.count_items(self.PROJECTS)}",
                f"Memory items: {self.count_items(self.MEMORY)}",
                f"Logs items: {self.count_items(self.LOGS)}",
            ],
        )
        return HANDLED

    def show_tasks_overview(self):
        snapshot = self.get_agent_task_snapshot()
        tasks = snapshot.get("recent_tasks", [])
        details = []
        if not tasks:
            details.append("No agent tasks recorded yet.")
        else:
            for task in tasks:
                summary = self.get_agent_task_manager().summarize_task(task)
                details.append(
                    f"Task {summary['task_id']} [{summary['status']}] "
                    f"{summary['goal']} ({summary['current_step']}/{summary['total_steps']})"
                )
        self._emit_operator_message(
            "Agent Tasks",
            summary=[f"Recent tasks: {len(tasks)}"],
            details=details,
        )
        return HANDLED

    def show_task_history(self):
        details = []
        recent_activity = list(reversed(self.activity_history[-8:]))
        if recent_activity:
            for item in recent_activity:
                command_text = f" | {item['command']}" if item.get("command") else ""
                details.append(f"{item['timestamp']} {item['summary']}{command_text}")
        else:
            details.append("No desktop activity recorded yet.")
        self._emit_operator_message(
            "Task History",
            summary=[f"Recent activity entries: {len(recent_activity)}"],
            details=details,
        )
        return HANDLED

    def show_memory_overview(self):
        payload = list_memory_notes()
        notes = payload.get("notes", {})
        if notes:
            summary = [f"Saved notes: {len(notes)}"]
            details = [f"{key}: {value}" for key, value in sorted(notes.items())]
        else:
            summary = ["Saved notes: 0"]
            details = [payload.get("result") or payload.get("error", "No notes available.")]
        self._emit_operator_message(
            "Memory",
            summary=summary,
            details=details,
        )
        return HANDLED

    def show_stub_message(self, message, title="Command"):
        self._emit_operator_message(
            title,
            summary=[str(message)],
            recommendations=["Use Help to review the supported desktop commands."],
            kind="warning",
        )
        return HANDLED

    def get_latest_folder_summary(self):
        payload = getattr(self, "last_agent_workflow_payload", None)
        if not isinstance(payload, dict) or payload.get("kind") != "agent_run":
            return None
        agent_payload = payload.get("payload", {})
        for item in reversed(agent_payload.get("results", [])):
            summary = item.get("result", {}).get("summary")
            if summary:
                return summary
        return None

    def show_folder_summary_section(self, summary_key, section_title):
        summary = self.get_latest_folder_summary()
        if not summary:
            self.run_router_command("inspect downloads", show_user=False)
            summary = self.get_latest_folder_summary()
        if not summary:
            return self.show_stub_message(
                "No folder summary is available yet. Run scan downloads or scan desktop first.",
                title=section_title,
            )

        formatter_map = {
            "top_file_types": lambda entry: f"{entry['extension']}: {entry['count']}",
            "largest_files": lambda entry: f"{entry['name']}: {entry['size_bytes']} bytes",
            "newest_files": lambda entry: f"{entry['name']}: {entry['modified']}",
        }
        formatter = formatter_map.get(summary_key)
        values = summary.get(summary_key, [])
        if not values or formatter is None:
            self._emit_operator_message(
                section_title,
                summary=["No verified items are available for this section yet."],
                recommendations=["Run scan downloads or scan desktop to refresh the verified folder summary."],
            )
        else:
            self._emit_operator_message(
                section_title,
                summary=[f"Showing {min(len(values), 10)} verified items from the latest folder summary."],
                details=[formatter(entry) for entry in values[:10]],
            )
        return HANDLED

    def count_items(self, folder):
        if folder.exists() and folder.is_dir():
            return len(list(folder.iterdir()))
        return 0

    def open_notes_file(self):
        try:
            self.MEMORY.mkdir(parents=True, exist_ok=True)
            if not NOTES_FILE.exists():
                NOTES_FILE.write_text("", encoding="utf-8")
            os.startfile(str(NOTES_FILE))
            self.log_action("Notes file opened")
            self.record_activity("tool", "Opened notes file", tool="memory", success=True)
            self.set_status_feedback("Done | Opened notes", level="done")
            self._emit_operator_message(
                "Notes",
                summary=["Notes file opened."],
                details=[str(NOTES_FILE)],
            )
        except Exception as exc:
            self.log_action(f"Open notes failure: {exc}")
            self.set_status_feedback(f"Error | No pude abrir tus notas: {exc}", level="error")
            self._emit_operator_message(
                "Notes Failed",
                summary=["The notes file could not be opened."],
                details=["The local file-open request failed."],
                recommendations=["Retry once. If it keeps failing, review the file path and desktop diagnostics."],
                kind="warning",
            )
        return HANDLED

    def open_logs_file(self):
        try:
            self.LOGS.mkdir(parents=True, exist_ok=True)
            if not BRAIN_LOG.exists():
                BRAIN_LOG.write_text("", encoding="utf-8")
            os.startfile(str(BRAIN_LOG))
            self.log_action("Log file opened")
            self.record_activity("tool", "Opened logs", tool="logs", success=True)
            self.set_status_feedback("Done | Opened logs", level="done")
            self._emit_operator_message(
                "Logs",
                summary=["Log file opened."],
                details=[str(BRAIN_LOG)],
            )
        except Exception as exc:
            self.log_action(f"Open logs failure: {exc}")
            self._emit_operator_message(
                "Logs Failed",
                summary=["The log file could not be opened."],
                details=["The local file-open request failed."],
                recommendations=["Retry once. If it keeps failing, review the file path and desktop diagnostics."],
                kind="warning",
            )
            self.set_status_feedback(f"Error | No pude abrir el log: {exc}", level="error")
        return HANDLED

    def show_diagnostics_panel(self):
        self.backend_status = get_ollama_status()
        diagnostics_lines = [line for line in self.build_diagnostics_text().splitlines() if line.strip()]
        self._emit_operator_message(
            "Diagnostics",
            summary=diagnostics_lines[:3],
            details=diagnostics_lines[3:],
            kind="diagnostics",
        )
        self.record_activity("diagnostics", "Viewed desktop diagnostics", tool="diagnostics", success=True)
        self.set_status_feedback("Done | Diagnostics refreshed", level="done")
        return HANDLED

    def copy_text_to_clipboard(self, text, label="clipboard text"):
        if self._clipboard_setter is None:
            return {
                "success": False,
                "action": "copy_to_clipboard",
                "result": "",
                "error": "Clipboard unavailable in this context.",
            }
        try:
            self._clipboard_setter(str(text))
            self.set_status_feedback(f"Done | Copied {label}", level="done")
            return {
                "success": True,
                "action": "copy_to_clipboard",
                "result": f"Copied {label} to clipboard.",
                "error": None,
            }
        except Exception as exc:
            self.set_status_feedback(f"Error | Clipboard unavailable: {exc}", level="error")
            return {
                "success": False,
                "action": "copy_to_clipboard",
                "result": "",
                "error": f"Clipboard unavailable: {exc}",
            }

    def copy_task_prompt(self, task_id):
        payload = get_task(task_id)
        if not payload.get("success") or not payload.get("task"):
            return {
                "success": False,
                "action": "copy_task_prompt",
                "result": "",
                "error": payload.get("error", f"Task {task_id} not found."),
            }
        task = payload["task"]
        self.active_task_context = task
        clipboard_result = self.copy_text_to_clipboard(task.get("prompt_text", ""), label=f"task {task_id} prompt")
        if clipboard_result["success"]:
            self.record_activity("task", f"Copied prompt for task {task_id}", command=f"copy task {task_id} prompt", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_task_prompt",
                "result": f"Copied prompt for task {task_id} to clipboard.",
                "error": None,
                "task": task,
            }
        operator_mission = operator_summary.get("current_mission")
        if not operator_mission or operator_mission == "Idle":
            operator_mission = last_action_value

        return {
            "success": False,
            "action": "copy_task_prompt",
            "result": "",
            "error": clipboard_result["error"],
            "task": task,
        }

    def copy_current_task_prompt(self):
        task = self.active_task_context
        if not task:
            return {
                "success": False,
                "action": "copy_current_task_prompt",
                "result": "",
                "error": "No active task is currently selected.",
            }
        result = self.copy_text_to_clipboard(task.get("prompt_text", ""), label=f"task {task.get('id', '?')} prompt")
        if result["success"]:
            self.record_activity("task", f"Copied current task {task.get('id', '?')} prompt", command="copy current task prompt", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_current_task_prompt",
                "result": f"Copied current task {task.get('id', '?')} prompt to clipboard.",
                "error": None,
                "task": task,
            }
        return {
            "success": False,
            "action": "copy_current_task_prompt",
            "result": "",
            "error": result["error"],
            "task": task,
        }

    def copy_task_summary(self, task_id):
        payload = get_task(task_id)
        if not payload.get("success") or not payload.get("task"):
            return {
                "success": False,
                "action": "copy_task_summary",
                "result": "",
                "error": payload.get("error", f"Task {task_id} not found."),
            }
        task = payload["task"]
        summary = f"Task {task['id']}: {task['title']}\nType: {task['type']}\nStatus: {task['status']}\nCreated: {task['created_at']}"
        result = self.copy_text_to_clipboard(summary, label=f"task {task_id} summary")
        if result["success"]:
            self.record_activity("task", f"Copied summary for task {task_id}", command=f"copy task {task_id} summary", tool="clipboard", success=True)
            return {
                "success": True,
                "action": "copy_task_summary",
                "result": f"Copied summary for task {task_id} to clipboard.",
                "error": None,
                "task": task,
            }
        return {
            "success": False,
            "action": "copy_task_summary",
            "result": "",
            "error": result["error"],
            "task": task,
        }

    def get_agent_state(self):
        if self.agent_state is None:
            self.agent_state = AgentState(mode="manual", interval_seconds=60)
        return self.agent_state

    def get_auto_loop(self):
        if self.auto_loop is None:
            state = self.get_agent_state()
            self.auto_loop = RogueAutoLoop(
                cycle_seconds=state.get_interval_seconds(),
                agent_state=state,
            )
        return self.auto_loop

    @staticmethod
    def humanize_internal_identifier(value):
        lookup = {
            "inspect_downloads": "Inspect downloads",
            "inspect_desktop": "Inspect desktop",
            "inspect_workspace": "Inspect workspace",
            "workspace_summary": "Workspace summary",
            "system_info": "System info",
            "list_path": "List folder contents",
            "preview_folder_organization": "Preview folder organization",
            "apply_download_organization": "Organize downloads",
            "apply_home_workspace_organization": "Organize home workspace",
            "move_files": "Move files",
            "delete_files": "Delete files",
            "kill_process": "Stop process",
            "get_system_info": "Get system info",
        }
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in lookup:
            return lookup[lowered]
        if "_" in text and " " not in text:
            text = text.replace("_", " ")
        return text[:1].upper() + text[1:] if text else ""

    def format_agent_plan_text(self, text):
        source_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not source_lines:
            return "No plan generated yet."
        lines = []
        for index, line in enumerate(source_lines):
            task_text, separator, tool_text = line.partition("->")
            prefix = ""
            stripped_task = task_text.strip()
            if ". " in stripped_task:
                maybe_prefix, _, maybe_task = stripped_task.partition(". ")
                if maybe_prefix.isdigit() and maybe_task:
                    prefix = f"{maybe_prefix}. "
                    stripped_task = maybe_task.strip()
            if separator:
                lines.append(f"{prefix}{self.humanize_internal_identifier(stripped_task)}")
                lines.append(f"    Tool: {self.humanize_internal_identifier(tool_text.strip())}")
            else:
                lines.append(f"{prefix}{self.humanize_internal_identifier(stripped_task) or stripped_task}")
            if index < len(source_lines) - 1:
                lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_count(value):
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    @staticmethod
    def _format_percent(value):
        if value in (None, ""):
            return ""
        try:
            return f"{int(round(float(value)))}%"
        except Exception:
            return ""

    def _parse_system_info_result(self, result_text):
        if not result_text:
            return {}
        try:
            parsed = ast.literal_eval(str(result_text))
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def _normalize_verified_value(value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(parts)
        text = str(value).strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in {"unknown", "n/a", "none", "null"}:
            return ""
        if text.startswith("[Insert ") and text.endswith("]"):
            return ""
        return text

    def _clean_section_items(self, values):
        cleaned = []
        for value in values or []:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            if "[insert " in text.lower():
                continue
            normalized = self._normalize_verified_value(text)
            if normalized:
                cleaned.append(normalized)
        return cleaned

    def _build_operator_response(self, title, *, summary=None, details=None, warnings=None, recommendations=None):
        lines = [self._normalize_verified_value(title) or "Response"]
        for heading, values in [
            ("Summary", summary),
            ("Details", details),
            ("Warning", warnings),
            ("Recommendation", recommendations),
        ]:
            items = self._clean_section_items(values)
            if not items:
                continue
            lines.append("")
            lines.append(heading)
            for item in items:
                lines.append(f"- {item}")
        return "\n".join(lines)

    def _emit_operator_message(self, title, *, summary=None, details=None, warnings=None, recommendations=None, kind=None):
        message = self._build_operator_response(
            title,
            summary=summary,
            details=details,
            warnings=warnings,
            recommendations=recommendations,
        )
        self.add_message("Rogue", message, kind=kind or self.classify_message("Rogue", message))
        return message

    def normalize_command_title(self, command_text, fallback="Command Result"):
        return self._normalized_command_display_title(command_text, fallback=fallback)

    def infer_result_success(self, result, *, planned_tasks=None, verified_tasks=None, default=True):
        def _safe_count(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        if isinstance(result, dict):
            if "success" in result:
                return bool(result.get("success"))
            if result.get("error"):
                return False
        verified_total = _safe_count(verified_tasks)
        planned_total = _safe_count(planned_tasks)
        if verified_total is not None and verified_total > 0:
            return True
        if (
            planned_total is not None
            and verified_total is not None
            and planned_total > 0
            and planned_total == verified_total
        ):
            return True
        return bool(default)

    def _normalize_envelope_text(self, value):
        if isinstance(value, (list, tuple)):
            return "\n".join(self._clean_section_items(value))
        return self._normalize_verified_value(value)

    def _coerce_envelope_details(self, values):
        if isinstance(values, str):
            values = values.splitlines()
        return self._clean_section_items(values or [])

    @staticmethod
    def _default_envelope_recommendation(ok):
        if ok:
            return "Continue with the next command when ready."
        return "Retry the command once. If it keeps failing, review the Agent or diagnostics surfaces."

    def _derive_command_envelope_sections(self, result, ok):
        if isinstance(result, dict):
            summary_lines = []
            details = []

            if not ok:
                errors = self._coerce_envelope_details(result.get("errors"))
                if not errors and result.get("error"):
                    errors = self._coerce_envelope_details([result.get("error")])
                warnings = self._coerce_envelope_details(result.get("warnings"))
                summary_lines = errors[:1] or warnings[:1] or ["The command could not be completed."]
                details.extend(errors[1:])
                details.extend(self._coerce_envelope_details(result.get("inferences")))
                if not details and result.get("result"):
                    details.extend(self._coerce_envelope_details([result.get("result")]))
                details.extend(f"{ENVELOPE_WARNING_PREFIX}{item}" for item in warnings)
                return "\n".join(summary_lines), details

            observed = self._coerce_envelope_details(result.get("observed"))
            string_summary = self._normalize_envelope_text(result.get("summary"))
            string_result = self._normalize_verified_value(result.get("result"))
            if observed:
                summary_lines = observed[:1]
                details.extend(observed[1:])
            elif string_summary and not isinstance(result.get("summary"), dict):
                summary_lines = [string_summary]
            elif string_result:
                summary_lines = [string_result]
            elif result.get("artifacts"):
                summary_lines = [f"Verified artifacts: {self._format_count(len(result.get('artifacts', [])))}"]
            else:
                summary_lines = ["Response ready."]

            details.extend(self._coerce_envelope_details(result.get("inferences")))
            if not details and result.get("artifacts"):
                details.append(f"Artifacts: {self._format_count(len(result.get('artifacts', [])))}")
            warnings = self._coerce_envelope_details(result.get("warnings"))
            details.extend(f"{ENVELOPE_WARNING_PREFIX}{item}" for item in warnings)
            return "\n".join(summary_lines), details

        if isinstance(result, str):
            lines = [line.strip() for line in result.splitlines() if line.strip()]
            if lines:
                return lines[0], lines[1:]
        if ok:
            return "Response ready.", []
        return "The command could not be completed.", []

    def build_command_envelope(
        self,
        command_text,
        result,
        *,
        title=None,
        summary=None,
        details=None,
        warnings=None,
        recommendation=None,
        ok=None,
        planned_tasks=None,
        verified_tasks=None,
        default_ok=True,
        success_label="",
        default_recommendation=True,
    ):
        inferred_ok = bool(ok) if ok is not None else self.infer_result_success(
            result,
            planned_tasks=planned_tasks,
            verified_tasks=verified_tasks,
            default=default_ok,
        )
        base_title = self._normalize_verified_value(title) or self.normalize_command_title(command_text, fallback="Command Result")
        normalized_summary = self._normalize_envelope_text(summary)
        normalized_details = self._coerce_envelope_details(details)
        normalized_warnings = self._coerce_envelope_details(warnings)
        normalized_details.extend(f"{ENVELOPE_WARNING_PREFIX}{item}" for item in normalized_warnings)
        normalized_recommendation = self._normalize_envelope_text(recommendation)

        if not normalized_summary or not normalized_details:
            derived_summary, derived_details = self._derive_command_envelope_sections(result, inferred_ok)
            if not normalized_summary:
                normalized_summary = derived_summary
            if not normalized_details:
                normalized_details = derived_details

        if not normalized_recommendation and isinstance(result, dict):
            normalized_recommendation = self._normalize_envelope_text(
                result.get("recommendations") or result.get("suggestions")
            )
        if not normalized_recommendation and default_recommendation:
            normalized_recommendation = self._default_envelope_recommendation(inferred_ok)

        return {
            "ok": inferred_ok,
            "title": self._compose_result_title(base_title, inferred_ok, success_label=success_label),
            "summary": normalized_summary or ("Response ready." if inferred_ok else "The command could not be completed."),
            "details": normalized_details,
            "recommendation": normalized_recommendation,
            "raw": result,
        }

    def _render_command_envelope(self, envelope):
        if not isinstance(envelope, dict):
            return "Response ready."
        detail_lines = []
        warning_lines = []
        for item in self._coerce_envelope_details(envelope.get("details")):
            if item.startswith(ENVELOPE_WARNING_PREFIX):
                warning_lines.append(item[len(ENVELOPE_WARNING_PREFIX) :].strip())
            else:
                detail_lines.append(item)
        return self._build_operator_response(
            envelope.get("title", "Command Result"),
            summary=self._coerce_envelope_details(envelope.get("summary")),
            details=detail_lines,
            warnings=warning_lines,
            recommendations=self._coerce_envelope_details(envelope.get("recommendation")),
        )

    def _build_command_envelope_from_operator_response(self, text, *, raw=None):
        normalized = str(text or "").strip()
        if not normalized:
            return None
        if not self._looks_like_operator_response(normalized):
            return None

        lines = normalized.splitlines()
        title = self._normalize_verified_value(lines[0]) or "Command Result"
        sections = {"Summary": [], "Details": [], "Warning": [], "Recommendation": []}
        current_section = None
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in sections:
                current_section = stripped
                continue
            item = stripped[2:] if stripped.startswith("- ") else stripped
            if current_section in sections and item:
                sections[current_section].append(item)

        details = list(sections["Details"])
        details.extend(f"{ENVELOPE_WARNING_PREFIX}{item}" for item in sections["Warning"])
        ok = self.infer_result_success(
            raw if isinstance(raw, dict) else None,
            default=not title.endswith(" Failed"),
        )
        return {
            "ok": ok,
            "title": title,
            "summary": "\n".join(sections["Summary"]) or ("Response ready." if ok else "The command could not be completed."),
            "details": details,
            "recommendation": "\n".join(sections["Recommendation"]),
            "raw": raw if raw is not None else text,
        }

    def _compose_result_title(self, base_title, success=True, success_label="Complete"):
        label = self._normalize_verified_value(base_title) or "Result"
        if not success:
            return f"{label} Failed"
        return f"{label} {success_label}".strip()

    def _system_info_guidance_message(self):
        return (
            "System information command not available yet.\n\n"
            "Available commands:\n"
            "- system status\n"
            "- scan desktop\n"
            "- workspace summary"
        )

    def _extract_system_info_payload(self, payload):
        info = payload.get("info")
        if isinstance(info, dict):
            return info
        return self._parse_system_info_result(payload.get("result", ""))

    def _build_system_info_chat_response(self, payload):
        info = self._extract_system_info_payload(payload)
        if not isinstance(info, dict):
            return self._system_info_guidance_message()

        operating_system = self._normalize_verified_value(info.get("Operating System") or info.get("platform"))
        cpu = self._normalize_verified_value(info.get("CPU") or info.get("processor"))
        ram = self._normalize_verified_value(info.get("RAM"))
        disk_summary = self._normalize_verified_value(info.get("Disk summary"))
        gpu = self._normalize_verified_value(info.get("GPU"))

        summary = []
        if operating_system:
            summary.append(f"Operating System: {operating_system}")
        if cpu:
            summary.append(f"CPU: {cpu}")
        if ram:
            summary.append(f"RAM: {ram}")

        details = []
        if gpu:
            details.append(f"GPU: {gpu}")
        if disk_summary:
            details.append(f"Disk summary: {disk_summary}")

        if not summary and not details:
            return self._system_info_guidance_message()

        return self.build_command_envelope(
            payload.get("action") or "system info",
            payload,
            title="System Information",
            summary=summary,
            details=details,
            ok=payload.get("success", True),
            default_recommendation=False,
        )

    def _extract_system_health_payload(self, payload):
        health = payload.get("health")
        if isinstance(health, dict):
            return health
        return self._parse_system_info_result(payload.get("result", ""))

    def _build_system_health_chat_response(self, payload):
        health = self._extract_system_health_payload(payload)
        if not isinstance(health, dict):
            return None

        summary = []
        cpu_usage = self._format_percent(health.get("cpu_usage_percent"))
        memory_usage = self._format_percent(health.get("memory_usage_percent"))
        disk_usage = self._format_percent(health.get("disk_usage_percent"))

        if cpu_usage:
            summary.append(f"CPU usage: {cpu_usage}")
        if memory_usage:
            summary.append(f"Memory usage: {memory_usage}")
        if disk_usage:
            summary.append(f"Disk usage: {disk_usage}")

        details = self._clean_section_items(payload.get("details") or payload.get("inferences") or [])
        warnings = self._clean_section_items(payload.get("warnings") or [])
        recommendations = self._clean_section_items(payload.get("recommendations") or payload.get("suggestions") or [])

        if not summary and not details and not warnings:
            return None

        return self.build_command_envelope(
            payload.get("action") or "system health",
            payload,
            title="System Health",
            summary=summary,
            details=details,
            warnings=warnings,
            recommendation=recommendations,
            ok=payload.get("success", True),
            default_recommendation=False,
        )

    def _extract_storage_overview_payload(self, payload):
        storage = payload.get("storage")
        if isinstance(storage, dict):
            return storage
        return self._parse_system_info_result(payload.get("result", ""))

    def _build_storage_overview_chat_response(self, payload):
        storage = self._extract_storage_overview_payload(payload)
        if not isinstance(storage, dict):
            return None

        summary = []
        drive_usage = self._format_percent(storage.get("drive_usage_percent"))
        free_space = self._normalize_verified_value(storage.get("drive_free_human"))
        total_space = self._normalize_verified_value(storage.get("drive_total_human"))

        if drive_usage:
            summary.append(f"Drive usage: {drive_usage}")
        if free_space:
            summary.append(f"Free space: {free_space}")
        if total_space:
            summary.append(f"Total disk size: {total_space}")

        details = []
        largest_folders = storage.get("largest_folders") or []
        if largest_folders:
            folder_names = ", ".join(
                f"{item.get('name')} ({item.get('size_human')})"
                for item in largest_folders[:3]
                if self._normalize_verified_value(item.get("name")) and self._normalize_verified_value(item.get("size_human"))
            )
            if folder_names:
                details.append(f"Largest folders: {folder_names}")

        large_files = storage.get("large_files") or []
        threshold = self._normalize_verified_value(storage.get("large_file_threshold_human"))
        if large_files:
            file_names = ", ".join(
                f"{item.get('name')} ({item.get('size_human')})"
                for item in large_files[:3]
                if self._normalize_verified_value(item.get("name")) and self._normalize_verified_value(item.get("size_human"))
            )
            if file_names:
                if threshold:
                    details.append(f"Large files above {threshold}: {file_names}")
                else:
                    details.append(f"Large files: {file_names}")

        if storage.get("scan_truncated"):
            details.append(
                f"Scan reached the verification limit after {self._format_count(storage.get('scanned_file_count', 0))} files"
            )
        warnings = self._clean_section_items(payload.get("warnings") or [])
        recommendations = self._clean_section_items(payload.get("recommendations") or payload.get("suggestions") or [])

        if not summary and not details and not warnings:
            return None

        return self.build_command_envelope(
            payload.get("action") or "storage overview",
            payload,
            title="Storage Overview",
            summary=summary,
            details=details,
            warnings=warnings,
            recommendation=recommendations,
            ok=payload.get("success", True),
            default_recommendation=False,
        )

    @staticmethod
    def _contains_agent_only_sections(text):
        lowered = str(text or "").lower()
        blocked_headers = [
            "goal:",
            "observed facts:",
            "execution results:",
            "action:",
        ]
        return any(header in lowered for header in blocked_headers)

    def _friendly_preview_title(self, goal, fallback="Result"):
        return self._normalized_command_display_title(goal, fallback=fallback)

    def _normalized_command_display_title(self, value, fallback="Command Result"):
        raw_value = str(value or "").strip()
        normalized = " ".join(raw_value.lower().replace("_", " ").split())
        if not normalized:
            return fallback

        mapped = COMMAND_DISPLAY_TITLES.get(normalized)
        if mapped:
            return mapped

        if "_" in raw_value and " " not in raw_value:
            label = self.humanize_internal_identifier(raw_value)
            return " ".join(part.capitalize() for part in str(label or fallback).split())

        normalized_fallback = " ".join(str(fallback or "").strip().lower().replace("_", " ").split())
        if normalized_fallback and normalized_fallback != normalized:
            return str(fallback)

        return "Command Result"

    def build_chat_response_text(self, response):
        agent_payload = getattr(self, "last_agent_workflow_payload", None)
        if isinstance(agent_payload, dict):
            envelope = self._build_chat_response_from_agent_payload(agent_payload)
            if isinstance(envelope, dict):
                return self._render_command_envelope(envelope)
            if envelope:
                parsed = self._build_command_envelope_from_operator_response(envelope, raw=agent_payload)
                if parsed is not None:
                    return self._render_command_envelope(parsed)
                return self._render_command_envelope(self.build_command_envelope("Command Result", agent_payload, summary=envelope))

        structured_payload = getattr(self, "last_structured_response_payload", None)
        if isinstance(structured_payload, dict):
            envelope = self._build_chat_response_from_structured_result(structured_payload)
            if isinstance(envelope, dict):
                return self._render_command_envelope(envelope)
            if envelope:
                parsed = self._build_command_envelope_from_operator_response(envelope, raw=structured_payload)
                if parsed is not None:
                    return self._render_command_envelope(parsed)
                return self._render_command_envelope(
                    self.build_command_envelope("Command Result", structured_payload, summary=envelope)
                )

        fallback_text = str(response or "")
        if self._contains_agent_only_sections(fallback_text):
            return "Response ready."
        parsed = self._build_command_envelope_from_operator_response(fallback_text, raw=response)
        if parsed is not None:
            return self._render_command_envelope(parsed)
        return self._build_plain_text_operator_response(fallback_text)

    @staticmethod
    def _looks_like_operator_response(text):
        normalized = str(text or "").strip()
        if not normalized:
            return False
        return any(section in normalized for section in ("\nSummary\n", "\nDetails\n", "\nWarning\n", "\nRecommendation\n"))

    def _build_plain_text_operator_response(self, text):
        envelope = self.build_command_envelope(
            "Command Result",
            text,
            default_ok=not any(
                token in str(text or "").lower()
                for token in ("failed", "error", "unknown command", "not available", "cancelled", "could not")
            ),
        )
        return self._render_command_envelope(envelope)

    def _build_chat_response_from_agent_payload(self, payload):
        payload_kind = payload.get("kind")
        if payload_kind == "agent_run":
            return self._build_chat_response_from_agent_run(payload.get("payload", {}))
        if payload_kind == "task_list":
            tasks = payload.get("tasks", [])
            return self.build_command_envelope(
                payload.get("title", "Agent Tasks"),
                payload,
                title=payload.get("title", "Agent Tasks"),
                summary=[f"Count: {self._format_count(len(tasks))}"],
                ok=True,
                default_recommendation=False,
            )
        if payload_kind == "task_detail":
            task = payload.get("task") or {}
            task_id = task.get("task_id") or task.get("id") or "?"
            summary = []
            task_name = self._normalize_verified_value(task.get("goal") or task.get("title"))
            status = self._normalize_verified_value(task.get("status"))
            if task_name:
                summary.append(f"Task: {task_name}")
            if status:
                summary.append(f"Status: {status}")
            return self.build_command_envelope(
                f"Task {task_id}",
                payload,
                title=f"Task {task_id}",
                summary=summary,
                ok=True,
                default_recommendation=False,
            )
        return None

    def _build_chat_response_from_agent_run(self, payload):
        if not isinstance(payload, dict):
            return None

        goal = payload.get("goal", "")
        title = self._friendly_preview_title(goal, fallback="Agent workflow")
        results = payload.get("results", [])
        planned_count = len(payload.get("plan", []))
        verified_count = sum(1 for item in results if item.get("verified"))

        for item in reversed(results):
            result = item.get("result", {})
            inferred_success = self.infer_result_success(
                result,
                planned_tasks=planned_count,
                verified_tasks=verified_count,
                default=payload.get("success", True),
            )
            summary = result.get("summary")
            if isinstance(summary, dict):
                summary_items = []
                if summary.get("total_files") is not None:
                    summary_items.append(f"Files: {self._format_count(summary.get('total_files'))}")
                if summary.get("total_directories") is not None:
                    summary_items.append(f"Folders: {self._format_count(summary.get('total_directories'))}")
                total_size = self._normalize_verified_value(summary.get("total_size_human"))
                if total_size:
                    summary_items.append(f"Total size: {total_size}")
                return self.build_command_envelope(
                    goal or title,
                    result,
                    title=title,
                    summary=summary_items,
                    details=result.get("inferences"),
                    warnings=result.get("warnings"),
                    recommendation=result.get("suggestions"),
                    ok=inferred_success,
                    success_label="Complete",
                    default_recommendation=False,
                )

            preview = result.get("preview")
            if isinstance(preview, dict):
                summary_items = []
                if preview.get("total_files_analyzed") is not None:
                    summary_items.append(f"Files analyzed: {self._format_count(preview.get('total_files_analyzed'))}")
                if preview.get("folder_entries_seen") is not None:
                    summary_items.append(f"Folders seen: {self._format_count(preview.get('folder_entries_seen'))}")
                if "included_subfolders" in preview:
                    scope = "recursive" if preview.get("included_subfolders") else "top-level only"
                    summary_items.append(f"Scope: {scope}")
                return self.build_command_envelope(
                    goal or title,
                    result,
                    title=title,
                    summary=summary_items,
                    details=result.get("inferences"),
                    warnings=result.get("warnings"),
                    recommendation=result.get("suggestions"),
                    ok=inferred_success,
                    success_label="Preview Ready",
                    default_recommendation=False,
                )

            inspection = result.get("inspection")
            if isinstance(inspection, dict):
                project_name = inspection.get("project_name") or Path(inspection.get("path", "")).name or "Project"
                summary_items = []
                if inspection.get("total_files") is not None:
                    summary_items.append(f"Files: {self._format_count(inspection.get('total_files'))}")
                if inspection.get("total_directories") is not None:
                    summary_items.append(f"Folders: {self._format_count(inspection.get('total_directories'))}")
                if inspection.get("readme_files") is not None:
                    summary_items.append(f"README files: {self._format_count(len(inspection.get('readme_files', [])))}")
                return self.build_command_envelope(
                    goal or project_name,
                    result,
                    title=f"{project_name} Inspection",
                    summary=summary_items,
                    details=result.get("inferences"),
                    warnings=result.get("warnings"),
                    recommendation=result.get("suggestions"),
                    ok=inferred_success,
                    default_recommendation=False,
                )

            report = result.get("report")
            if isinstance(report, dict):
                system_info = self._parse_system_info_result(report.get("system_info", {}).get("result", ""))
                folder_summaries = report.get("folder_summaries", {})
                summary_items = [
                    f"Projects: {self._format_count(len(report.get('known_projects', [])))}",
                    f"Memory entries: {self._format_count(len(report.get('recent_agent_memory', [])))}",
                    f"Workspace files: {self._format_count(folder_summaries.get('workspace', {}).get('total_files', 0))}",
                ]
                details = []
                platform_name = self._normalize_verified_value(
                    system_info.get("Operating System") or system_info.get("platform")
                )
                if platform_name:
                    details.append(f"Platform: {platform_name}")
                return self.build_command_envelope(
                    goal or title,
                    result,
                    title=title,
                    summary=summary_items,
                    details=details,
                    recommendation=payload.get("suggestions"),
                    ok=inferred_success,
                    success_label="Complete",
                    default_recommendation=False,
                )

        summary_items = [
            f"Planned tasks: {self._format_count(len(payload.get('plan', [])))}",
            f"Verified tasks: {self._format_count(verified_count)}",
        ]
        details = []
        failure_detail = self._extract_agent_failure_detail(payload)
        if failure_detail:
            details.append(f"Reason: {failure_detail}")
        return self.build_command_envelope(
            goal or title,
            payload,
            title=title,
            summary=summary_items,
            details=details,
            recommendation=payload.get("suggestions"),
            ok=self.infer_result_success(
                None,
                planned_tasks=planned_count,
                verified_tasks=verified_count,
                default=payload.get("success", True),
            ),
            success_label="Complete",
            default_recommendation=False,
        )

    def _extract_agent_failure_detail(self, payload):
        for item in reversed(payload.get("results", [])):
            result = item.get("result", {})
            if result.get("errors"):
                return str(result["errors"][0])
            if result.get("error"):
                return str(result["error"])
            if item.get("verified") is False and item.get("verification_reason"):
                return str(item["verification_reason"])
        return ""

    def _build_chat_response_from_structured_result(self, payload):
        if not isinstance(payload, dict):
            return None

        if payload.get("action") == "system_health":
            return self._build_system_health_chat_response(payload)

        if payload.get("action") == "storage_overview":
            return self._build_storage_overview_chat_response(payload)

        if payload.get("action") in {"system_info", "get_system_info"}:
            return self._build_system_info_chat_response(payload)

        summary = payload.get("summary")
        if isinstance(summary, dict):
            title = self._friendly_preview_title(payload.get("action"), fallback="Scan")
            summary_items = []
            if summary.get("total_files") is not None:
                summary_items.append(f"Files: {self._format_count(summary.get('total_files'))}")
            if summary.get("total_directories") is not None:
                summary_items.append(f"Folders: {self._format_count(summary.get('total_directories'))}")
            total_size = self._normalize_verified_value(summary.get("total_size_human"))
            if total_size:
                summary_items.append(f"Total size: {total_size}")
            return self.build_command_envelope(
                payload.get("action") or title,
                payload,
                title=title,
                summary=summary_items,
                details=payload.get("inferences"),
                warnings=payload.get("warnings"),
                recommendation=payload.get("suggestions"),
                ok=self.infer_result_success(payload, default=payload.get("success", True)),
                success_label="Complete",
                default_recommendation=False,
            )

        preview = payload.get("preview")
        if isinstance(preview, dict):
            title = self._friendly_preview_title(payload.get("action"), fallback="Preview")
            summary_items = []
            if preview.get("total_files_analyzed") is not None:
                summary_items.append(f"Files analyzed: {self._format_count(preview.get('total_files_analyzed'))}")
            if preview.get("folder_entries_seen") is not None:
                summary_items.append(f"Folders seen: {self._format_count(preview.get('folder_entries_seen'))}")
            if "included_subfolders" in preview:
                scope = "recursive" if preview.get("included_subfolders") else "top-level only"
                summary_items.append(f"Scope: {scope}")
            return self.build_command_envelope(
                payload.get("action") or title,
                payload,
                title=title,
                summary=summary_items,
                details=payload.get("inferences"),
                warnings=payload.get("warnings"),
                recommendation=payload.get("suggestions"),
                ok=self.infer_result_success(payload, default=payload.get("success", True)),
                success_label="Preview Ready",
                default_recommendation=False,
            )

        inspection = payload.get("inspection")
        if isinstance(inspection, dict):
            project_name = inspection.get("project_name") or Path(inspection.get("path", "")).name or "Project"
            summary_items = []
            if inspection.get("total_files") is not None:
                summary_items.append(f"Files: {self._format_count(inspection.get('total_files'))}")
            if inspection.get("total_directories") is not None:
                summary_items.append(f"Folders: {self._format_count(inspection.get('total_directories'))}")
            if inspection.get("readme_files") is not None:
                summary_items.append(f"README files: {self._format_count(len(inspection.get('readme_files', [])))}")
            return self.build_command_envelope(
                payload.get("action") or project_name,
                payload,
                title=f"{project_name} Inspection",
                summary=summary_items,
                details=payload.get("inferences"),
                warnings=payload.get("warnings"),
                recommendation=payload.get("suggestions"),
                ok=self.infer_result_success(payload, default=payload.get("success", True)),
                default_recommendation=False,
            )

        report = payload.get("report")
        if isinstance(report, dict):
            system_info = self._parse_system_info_result(report.get("system_info", {}).get("result", ""))
            folder_summaries = report.get("folder_summaries", {})
            summary_items = [
                f"Projects: {self._format_count(len(report.get('known_projects', [])))}",
                f"Memory entries: {self._format_count(len(report.get('recent_agent_memory', [])))}",
                f"Workspace files: {self._format_count(folder_summaries.get('workspace', {}).get('total_files', 0))}",
            ]
            details = []
            platform_name = self._normalize_verified_value(
                system_info.get("Operating System") or system_info.get("platform")
            )
            if platform_name:
                details.append(f"Platform: {platform_name}")
            return self.build_command_envelope(
                payload.get("action") or "workspace summary",
                payload,
                title="Workspace Summary",
                summary=summary_items,
                details=details,
                warnings=payload.get("warnings"),
                recommendation=payload.get("suggestions"),
                ok=self.infer_result_success(payload, default=payload.get("success", True)),
                default_recommendation=False,
            )

        action_label = self._friendly_preview_title(
            payload.get("action"),
            fallback=self.humanize_internal_identifier(payload.get("action", "result")),
        )
        if payload.get("success") is False or payload.get("errors"):
            detail = payload.get("errors", []) or ([payload.get("error")] if payload.get("error") else [])
            summary_items = detail[:1]
            if not summary_items and payload.get("warnings"):
                summary_items = payload.get("warnings", [])[:1]
            return self.build_command_envelope(
                payload.get("action") or action_label,
                payload,
                title=action_label,
                summary=summary_items,
                warnings=payload.get("warnings"),
                recommendation=payload.get("suggestions"),
                ok=False,
                default_recommendation=False,
            )

        observed = [str(item) for item in payload.get("observed", []) if str(item).strip()]
        summary_items = observed[:3]
        if not summary_items and payload.get("artifacts"):
            summary_items = [f"Verified artifacts: {self._format_count(len(payload.get('artifacts', [])))}"]
        elif not summary_items and payload.get("result"):
            summary_items = [str(payload.get("result")).strip()]

        details = payload.get("inferences")
        if not details and payload.get("artifacts"):
            details = [f"Artifacts: {self._format_count(len(payload.get('artifacts', [])))}"]

        return self.build_command_envelope(
            payload.get("action") or action_label,
            payload,
            title=action_label,
            summary=summary_items,
            details=details,
            warnings=payload.get("warnings"),
            recommendation=payload.get("suggestions"),
            ok=self.infer_result_success(payload, default=payload.get("success", True)),
            default_recommendation=False,
        )

    def build_agent_workflow_text(self):
        payload = getattr(self, "last_agent_workflow_payload", None)
        if isinstance(payload, dict):
            payload_kind = payload.get("kind")
            if payload_kind == "agent_run":
                agent_payload = payload.get("payload", {})
                return str(agent_payload.get("final_output") or "No workflow details yet.")
            if payload_kind == "task_list":
                return self.get_agent_task_manager().format_task_list(
                    payload.get("tasks", []),
                    title=payload.get("title", "Agent Tasks"),
                )
            if payload_kind == "task_detail" and payload.get("task"):
                return self.get_agent_task_manager().format_task_detail(payload["task"])

        structured = getattr(self, "last_structured_response_payload", None)
        if isinstance(structured, dict):
            return format_response_text(structured)

        return "No workflow details yet."

    def handle_agent_mode_change(self, selected_mode=None):
        mode_text = str(selected_mode or self.get_agent_state().get_mode()).strip().lower()
        state = self.get_agent_state()
        state.set_mode(mode_text)
        if mode_text == "manual":
            loop = getattr(self, "auto_loop", None)
            if loop is not None and loop.is_running():
                loop.stop(wait=False)
                self.add_message("Rogue", "Agent mode set to Manual. Background loop stopping after the current cycle.", kind="tool")
            self.set_status_feedback("Ready | Agent mode set to Manual", level="ready")
        elif mode_text == "assist":
            self.set_status_feedback("Ready | Agent mode set to Assist", level="ready")
        else:
            self.set_status_feedback("Ready | Agent mode set to Auto", level="ready")
        self._emit_state()

    def start_agent_loop(self):
        state = self.get_agent_state()
        if state.get_mode() == "manual":
            message = "Manual mode does not run continuously. Use Run One Cycle or switch to Assist/Auto."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return False

        loop = self.get_auto_loop()
        if not loop.start():
            message = "Agent loop is already running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return False

        message = f"Agent loop started in {state.get_mode().title()} mode."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Running | {message}", level="running")
        return True

    def stop_agent_loop(self):
        loop = getattr(self, "auto_loop", None)
        if loop is None or not loop.stop(wait=False):
            self.get_agent_state().mark_stopped()
            message = "Agent loop is not running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return False

        message = "Agent loop stop requested."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Ready | {message}", level="ready")
        return True

    def run_agent_cycle(self):
        loop = self.get_auto_loop()
        if not loop.run_cycle_async():
            message = "Agent cycle is already running."
            self.add_message("Rogue", message, kind="warning")
            self.set_status_feedback(f"Ready | {message}", level="ready")
            return False

        message = f"Agent cycle started in {self.get_agent_state().get_mode().title()} mode."
        self.add_message("Rogue", message, kind="tool")
        self.set_status_feedback(f"Running | {message}", level="running")
        return True

    def get_agent_task_manager(self):
        return self.agent_task_manager

    def get_agent_task_snapshot(self):
        manager = self.get_agent_task_manager()
        all_tasks = manager.list_tasks().get("tasks", [])
        active_tasks = manager.list_active_tasks().get("tasks", [])
        resumable_tasks = manager.list_resumable_tasks().get("tasks", [])
        recent_tasks = manager.list_recent_tasks(limit=6).get("tasks", [])
        completed_tasks = [task for task in all_tasks if task.get("status") == "completed"]
        return {
            "all_tasks": all_tasks,
            "active_tasks": active_tasks,
            "resumable_tasks": resumable_tasks,
            "recent_tasks": recent_tasks,
            "completed_tasks": completed_tasks,
        }

    def refresh_task_indicator(self):
        try:
            return len(self.get_agent_task_snapshot().get("active_tasks", []))
        except Exception:
            return 0

    def build_agent_task_status_summary(self):
        snapshot = self.get_agent_task_snapshot()
        return "\n".join(
            [
                "Agent task status summary",
                f"- Total tasks: {len(snapshot['all_tasks'])}",
                f"- Active tasks: {len(snapshot['active_tasks'])}",
                f"- Resumable tasks: {len(snapshot['resumable_tasks'])}",
                f"- Completed tasks: {len(snapshot['completed_tasks'])}",
            ]
        )

    def get_suggestion_payload(self):
        payload = get_suggestions(
            downloads_path=self.downloads_path,
            home_path=self.home_path,
            projects_path=self.PROJECTS,
            logs_path=self.LOGS,
            backend_status=self.backend_status,
        )
        self.last_suggestions = payload.get("suggestions", [])
        return payload

    def get_backend_mode_label(self):
        if self.backend_status.get("reachable") and self.backend_status.get("model_available"):
            return "Ollama-backed"
        return "Router-only"

    def build_diagnostics_text(self):
        suggestion_payload = self.get_suggestion_payload()
        agent_snapshot = self.get_agent_task_snapshot()
        return "\n".join(
            [
                "ROGUE DESKTOP DIAGNOSTICS",
                f"Backend mode: {self.get_backend_mode_label()}",
                f"Configured model: {self.backend_status.get('model', 'unknown')}",
                f"Memory enabled: {bool(self.modules.get('memory'))}",
                f"Tools loaded: {bool(self.modules.get('tools'))}",
                "Browser control available: True",
                "Proactive assistant enabled: True",
                f"Current suggestion count: {len(suggestion_payload.get('suggestions', []))}",
                "Engineering task queue enabled: True",
                f"Current engineering task count: {len(list_tasks().get('tasks', []))}",
                "Agent task visibility enabled: True",
                f"Current agent task count: {len(agent_snapshot.get('all_tasks', []))}",
                f"Current agent active count: {len(agent_snapshot.get('active_tasks', []))}",
                f"Current agent resumable count: {len(agent_snapshot.get('resumable_tasks', []))}",
                "Clipboard handoff available: True",
                f"Projects folder items: {self.count_items(self.PROJECTS)}",
                f"Memory folder items: {self.count_items(self.MEMORY)}",
                f"Logs file: {BRAIN_LOG}",
                f"Backend details: {self.backend_status.get('message', 'n/a')}",
            ]
        )

    def get_improvement_dashboard_summary(self, limit=5):
        return self.improvement_runtime.build_dashboard_summary(limit=limit)

    def get_command_center_payload(self):
        snapshot = self.get_agent_state().snapshot()
        settings_payload = self.get_settings_payload()
        task_snapshot = self.get_agent_task_snapshot()
        suggestion_payload = self.get_suggestion_payload()
        operator_summary = self.get_operator_summary()
        latest_activity = self.activity_history[-1] if self.activity_history else None
        memory_enabled = bool(self.modules.get("memory"))
        tools_loaded = bool(self.modules.get("tools") or self.modules.get("autonomy"))

        last_action_value = latest_activity["summary"] if latest_activity else "No actions yet"
        last_action_detail = ""
        if latest_activity:
            parts = [latest_activity.get("timestamp", "")]
            if latest_activity.get("command"):
                parts.append(str(latest_activity["command"]))
            if latest_activity.get("tool"):
                parts.append(str(latest_activity["tool"]))
            last_action_detail = " | ".join(part for part in parts if part)
        operator_mission = operator_summary.get("current_mission")
        if not operator_mission or operator_mission == "Idle":
            operator_mission = last_action_value

        return {
            "metrics": {
                "system_status": {
                    "value": snapshot.get("running_status", "Stopped"),
                    "detail": (
                        f"Mode: {str(snapshot.get('mode', 'manual')).title()} | "
                        f"Operator: {operator_summary.get('current_mode', 'chat')} | "
                        f"Verification: {operator_summary.get('verification_status', 'ready')} | "
                        f"Active tasks: {len(task_snapshot.get('active_tasks', []))} | "
                        f"Last cycle: {snapshot.get('last_cycle_time', 'Not run yet') or 'Not run yet'}"
                    ),
                },
                "backend_state": {
                    "value": settings_payload.get("backend_mode", "Unknown"),
                    "detail": (
                        f"Model: {settings_payload.get('model') or 'unavailable'} | "
                        f"{settings_payload.get('backend_message') or 'No backend detail available.'} | "
                        f"Runtime health: {operator_summary.get('runtime_health', {}).get('label', 'unknown')}"
                    ),
                },
                "memory_tools": {
                    "value": f"Memory {'enabled' if memory_enabled else 'disabled'}",
                    "detail": (
                        f"Tools {'loaded' if tools_loaded else 'unavailable'} | "
                        f"Conversation turns: {len(self.conversation_memory)} | "
                        f"Projects tracked: {self.count_items(self.PROJECTS)}"
                    ),
                },
                "last_action": {
                    "value": operator_mission,
                    "detail": operator_summary.get("operator_summary_line") or last_action_detail or "No activity has been recorded yet.",
                },
            },
            "quick_actions": [
                {"label": label, "command": command_text}
                for label, command_text in self.quick_commands
            ],
            "suggested_actions": [
                {"label": item.get("title", "Suggested action"), "command": item.get("suggested_command", "")}
                for item in suggestion_payload.get("suggestions", [])
                if item.get("suggested_command")
            ],
            "suggested_actions_text": self._format_suggestions_text(suggestion_payload.get("suggestions", [])),
            "active_tasks_text": self._format_task_records(task_snapshot.get("active_tasks", []), empty_message="No active tasks."),
            "recent_tasks_text": self._format_task_records(task_snapshot.get("recent_tasks", []), empty_message="No recent tasks yet."),
            "recent_events_text": self._format_activity_text(limit=10),
            "current_mode": operator_summary.get("current_mode", "chat"),
            "current_mission": operator_summary.get("current_mission", "Idle"),
            "runtime_health": operator_summary.get("runtime_health", {}),
            "verification_status": operator_summary.get("verification_status", "ready"),
            "recommended_next_action": operator_summary.get("recommended_next_action", ""),
            "operator_summary_text": "\n".join(
                [
                    f"Mode: {operator_summary.get('current_mode', 'chat')}",
                    f"Mission: {operator_summary.get('current_mission', 'Idle')}",
                    f"Runtime health: {operator_summary.get('runtime_health', {}).get('label', 'unknown')}",
                    f"Verification: {operator_summary.get('verification_status', 'ready')}",
                    f"Recommended next action: {operator_summary.get('recommended_next_action', '')}",
                ]
            ),
        }

    def get_explain_mode_payload(self):
        agent_payload = getattr(self, "last_agent_workflow_payload", None)
        structured_payload = getattr(self, "last_structured_response_payload", None)
        operator_summary = self.get_operator_summary()
        snapshot = self.get_agent_state().snapshot()
        fallback_goal = operator_summary.get("current_mission") or self._get_last_user_goal()
        fallback_plan = self.format_agent_plan_text(snapshot.get("latest_generated_plan"))

        if isinstance(agent_payload, dict):
            payload_kind = agent_payload.get("kind")
            if payload_kind == "agent_run":
                run_payload = agent_payload.get("payload", {}) if isinstance(agent_payload.get("payload"), dict) else {}
                return {
                    "last_goal": run_payload.get("goal") or fallback_goal or "No goal recorded yet.",
                    "plan": self._format_plan_entries(run_payload.get("plan"), fallback=fallback_plan),
                    "executed_steps": self._format_executed_steps(run_payload.get("results", [])),
                    "result": str(run_payload.get("final_output") or "No result recorded yet."),
                    "warnings_failures": (
                        f"{self._format_agent_warning_text(run_payload)}\n\n"
                        f"Verification: {operator_summary.get('verification_status', 'ready')}"
                    ),
                    "next_recommendation": operator_summary.get("recommended_next_action")
                    or self._extract_next_recommendation(run_payload, fallback="No next recommendation recorded yet."),
                    "operator_mode": operator_summary.get("current_mode", "chat"),
                    "verification_status": operator_summary.get("verification_status", "ready"),
                    "runtime_health": operator_summary.get("runtime_health", {}),
                }
            if payload_kind == "task_detail" and agent_payload.get("task"):
                task = agent_payload["task"]
                summary = self.get_agent_task_manager().summarize_task(task)
                warnings = []
                if summary.get("failed_steps"):
                    warnings.append(f"Failed steps: {summary['failed_steps']}")
                if summary.get("retry_counts"):
                    warnings.append(f"Retry counts: {summary['retry_counts']}")
                next_recommendation = "No next recommendation recorded yet."
                if summary.get("is_resumable"):
                    next_recommendation = f"Task {summary['task_id']} can be resumed from the next incomplete step."
                return {
                    "last_goal": summary.get("goal") or fallback_goal or "No goal recorded yet.",
                    "plan": self._format_plan_entries(task.get("steps", []), fallback=fallback_plan),
                    "executed_steps": self.get_agent_task_manager().format_task_detail(task),
                    "result": summary.get("final_summary") or "No result recorded yet.",
                    "warnings_failures": "\n".join(warnings) if warnings else "No warnings or failures recorded.",
                    "next_recommendation": operator_summary.get("recommended_next_action") or next_recommendation,
                    "operator_mode": operator_summary.get("current_mode", "chat"),
                    "verification_status": operator_summary.get("verification_status", "ready"),
                    "runtime_health": operator_summary.get("runtime_health", {}),
                }
            if payload_kind == "task_list":
                return {
                    "last_goal": fallback_goal or "Task list view",
                    "plan": fallback_plan,
                    "executed_steps": "No execution steps recorded for the current task list view.",
                    "result": self.get_agent_task_manager().format_task_list(
                        agent_payload.get("tasks", []),
                        title=agent_payload.get("title", "Agent Tasks"),
                    ),
                    "warnings_failures": "No warnings or failures recorded.",
                    "next_recommendation": operator_summary.get("recommended_next_action")
                    or "Open a task detail from Chat or Agent when you need a step-by-step explanation.",
                    "operator_mode": operator_summary.get("current_mode", "chat"),
                    "verification_status": operator_summary.get("verification_status", "ready"),
                    "runtime_health": operator_summary.get("runtime_health", {}),
                }

        if isinstance(structured_payload, dict):
            return {
                "last_goal": fallback_goal or self.humanize_internal_identifier(structured_payload.get("action", "Command result")),
                "plan": fallback_plan,
                "executed_steps": "No step-by-step execution payload was recorded for this response.",
                "result": self.build_chat_response_text(structured_payload.get("result") or format_response_text(structured_payload)),
                "warnings_failures": (
                    f"{self._format_structured_warning_text(structured_payload)}\n\n"
                    f"Verification: {operator_summary.get('verification_status', 'ready')}"
                ),
                "next_recommendation": operator_summary.get("recommended_next_action")
                or self._extract_next_recommendation(structured_payload, fallback="No next recommendation recorded yet."),
                "operator_mode": operator_summary.get("current_mode", "chat"),
                "verification_status": operator_summary.get("verification_status", "ready"),
                "runtime_health": operator_summary.get("runtime_health", {}),
            }

        return {
            "last_goal": fallback_goal or "No goal recorded yet.",
            "plan": fallback_plan,
            "executed_steps": "No execution steps recorded yet.",
            "result": "No result recorded yet.",
            "warnings_failures": f"No warnings or failures recorded.\n\nVerification: {operator_summary.get('verification_status', 'ready')}",
            "next_recommendation": operator_summary.get("recommended_next_action", "No next recommendation recorded yet."),
            "operator_mode": operator_summary.get("current_mode", "chat"),
            "verification_status": operator_summary.get("verification_status", "ready"),
            "runtime_health": operator_summary.get("runtime_health", {}),
        }

    def get_friction_radar_payload(self):
        summary = self.get_improvement_dashboard_summary(limit=6)
        stats = summary.get("improvement_stats", {})
        return {
            "summary_text": "\n".join(
                [
                    f"Events recorded: {summary.get('event_count', 0)}",
                    f"Execution enabled: {'Yes' if summary.get('execution_enabled') else 'No'}",
                    f"Pending approvals: {len(summary.get('pending_approvals', []))}",
                    f"Execution ready: {len(summary.get('execution_ready_proposals', []))}",
                    f"Executed: {stats.get('executed', 0)} | Rolled back: {stats.get('rolled_back', 0)} | Blocked: {stats.get('blocked', 0)}",
                ]
            ),
            "top_areas_text": self._format_area_counts(summary.get("common_areas", []), empty_message="No friction areas recorded yet."),
            "top_candidates_text": self._format_candidates(summary.get("top_candidates", [])),
            "recent_proposals_text": self._format_proposals(summary.get("recent_proposals", [])),
            "approvals_text": self._format_approval_text(summary),
            "executions_text": self._format_execution_history(summary),
            "confidence_text": self._format_confidence_text(summary),
            "experiments_text": self._format_experiment_text(summary.get("experiment_summaries", [])),
        }

    def _get_last_user_goal(self):
        for item in reversed(self.conversation_memory):
            if item.get("role") == "user":
                text = str(item.get("content") or "").strip()
                if text:
                    return text
        return ""

    def _format_task_records(self, tasks, empty_message="No tasks recorded yet.", limit=6):
        if not tasks:
            return empty_message
        lines = []
        manager = self.get_agent_task_manager()
        for task in tasks[:limit]:
            summary = manager.summarize_task(task)
            lines.append(f"Task {summary['task_id']} [{summary['status']}]")
            lines.append(f"Goal: {summary['goal'] or 'No goal recorded'}")
            lines.append(
                f"Current: step {summary['current_step']}/{summary['total_steps']} | "
                f"{summary['current_step_title'] or 'Waiting for next step'}"
            )
            if summary.get("final_summary"):
                lines.append(f"Result: {str(summary['final_summary']).splitlines()[0]}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_activity_text(self, limit=10):
        if not self.activity_history:
            return "No recent events yet."
        lines = []
        for item in reversed(self.activity_history[-limit:]):
            status = "OK" if item.get("success") is True else "ERR" if item.get("success") is False else "..."
            command_text = f" | {item['command']}" if item.get("command") else ""
            tool_text = f" | {item['tool']}" if item.get("tool") else ""
            lines.append(f"{item.get('timestamp', '--:--:--')} {status} {item.get('summary', '')}{command_text}{tool_text}")
        return "\n".join(lines)

    def _format_suggestions_text(self, suggestions):
        if not suggestions:
            return "No suggested actions right now."
        lines = []
        for index, item in enumerate(suggestions, start=1):
            lines.append(f"{index}. {item.get('title', 'Suggested action')}")
            reason = str(item.get("reason") or "").strip()
            if reason:
                lines.append(f"Reason: {reason}")
            command_text = str(item.get("suggested_command") or "").strip()
            if command_text:
                lines.append(f"Command: {command_text}")
            action_text = str(item.get("recommended_action") or "").strip()
            if action_text:
                lines.append(f"Action: {action_text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_plan_entries(self, plan, fallback="No plan recorded yet."):
        if isinstance(plan, list) and plan:
            lines = []
            for index, item in enumerate(plan, start=1):
                if isinstance(item, dict):
                    title = item.get("title") or item.get("action") or item.get("tool_name") or f"Step {index}"
                    lines.append(f"{index}. {title}")
                    tool_name = item.get("tool_name")
                    if tool_name:
                        lines.append(f"   Tool: {self.humanize_internal_identifier(tool_name)}")
                else:
                    lines.append(f"{index}. {item}")
            return "\n".join(lines)
        text = str(plan or "").strip()
        if text:
            return self.format_agent_plan_text(text)
        return fallback

    def _format_executed_steps(self, results):
        if not results:
            return "No execution steps recorded yet."
        lines = []
        for index, item in enumerate(results, start=1):
            task = item.get("task", {}) if isinstance(item.get("task"), dict) else {}
            result = item.get("result", {}) if isinstance(item.get("result"), dict) else {}
            title = task.get("title") or task.get("id") or f"Step {index}"
            status = "verified" if item.get("verified") else "failed"
            lines.append(f"{index}. {title}")
            lines.append(f"Status: {status} | Attempts: {item.get('attempts', 1)}")
            if task.get("tool_name"):
                lines.append(f"Tool: {self.humanize_internal_identifier(task['tool_name'])}")
            evidence = self._first_non_empty(
                result.get("result"),
                *(result.get("observed") or []),
                result.get("error"),
                item.get("verification_reason"),
            )
            if evidence:
                lines.append(f"Evidence: {evidence}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_agent_warning_text(self, payload):
        warnings = []
        for item in payload.get("results", []) or []:
            result = item.get("result", {}) if isinstance(item.get("result"), dict) else {}
            task = item.get("task", {}) if isinstance(item.get("task"), dict) else {}
            task_title = task.get("title") or task.get("tool_name") or "Step"
            for warning in result.get("warnings", []) or []:
                warnings.append(f"{task_title}: {warning}")
            for error in result.get("errors", []) or []:
                warnings.append(f"{task_title}: {error}")
            if not item.get("verified"):
                warnings.append(f"{task_title}: {item.get('verification_reason') or 'Verification failed.'}")
        if not warnings and payload.get("success") is False:
            warnings.append(self._extract_agent_failure_detail(payload) or "The last workflow did not complete successfully.")
        return "\n".join(warnings) if warnings else "No warnings or failures recorded."

    def _format_structured_warning_text(self, payload):
        lines = list(payload.get("warnings", []) or [])
        lines.extend(payload.get("errors", []) or [])
        if not lines and payload.get("success") is False and payload.get("error"):
            lines.append(str(payload.get("error")))
        return "\n".join(str(item) for item in lines if str(item).strip()) or "No warnings or failures recorded."

    def _extract_next_recommendation(self, payload, fallback="No next recommendation recorded yet."):
        suggestions = payload.get("suggestions") if isinstance(payload, dict) else None
        if isinstance(suggestions, list) and suggestions:
            return "\n".join(str(item) for item in suggestions if str(item).strip()) or fallback
        return fallback

    def _format_area_counts(self, areas, empty_message="No data recorded yet."):
        if not areas:
            return empty_message
        return "\n".join(f"- {item.get('area', 'general')}: {item.get('count', 0)}" for item in areas)

    def _format_candidates(self, candidates):
        if not candidates:
            return "No improvement candidates yet."
        lines = []
        for index, item in enumerate(candidates, start=1):
            lines.append(
                f"{index}. [{item.get('id', 'candidate')}] {item.get('area', 'general')} | "
                f"{item.get('symptom', 'unspecified friction')}"
            )
            lines.append(
                f"Score: {item.get('score', 0)} | Frequency: {item.get('frequency', 0)} | "
                f"Impact: {item.get('impact', 0)} | Ease: {item.get('ease', 0)}"
            )
            lines.append("")
        return "\n".join(lines).strip()

    def _format_proposals(self, proposals):
        if not proposals:
            return "No recent proposals yet."
        lines = []
        for index, item in enumerate(proposals, start=1):
            confidence = item.get("confidence", {}) if isinstance(item.get("confidence"), dict) else {}
            lines.append(f"{index}. {item.get('title', item.get('id', 'Proposal'))}")
            lines.append(
                f"Status: {item.get('status', 'proposed')} | Risk: {item.get('risk', 'unknown')} | "
                f"Confidence: {confidence.get('score', 0)} ({confidence.get('level', 'low')})"
            )
            if item.get("recommended_action"):
                lines.append(f"Action: {item['recommended_action']}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_approval_text(self, summary):
        lines = [
            f"Pending approvals: {len(summary.get('pending_approvals', []))}",
            f"Execution ready: {len(summary.get('execution_ready_proposals', []))}",
            f"Blocked proposals: {len(summary.get('blocked_proposals', []))}",
            "",
            "Pending queue:",
        ]
        pending = summary.get("pending_approvals", [])
        if pending:
            for item in pending:
                lines.append(f"- {item.get('title', item.get('id', 'Proposal'))} | {item.get('status', 'ready_for_review')}")
        else:
            lines.append("- No proposals are waiting for review.")

        lines.append("")
        lines.append("Execution-ready:")
        ready = summary.get("execution_ready_proposals", [])
        if ready:
            for item in ready:
                lines.append(f"- {item.get('title', item.get('id', 'Proposal'))}")
        else:
            lines.append("- No proposals are execution-ready.")
        return "\n".join(lines)

    def _format_execution_history(self, summary):
        lines = ["Recent executions:"]
        executed = summary.get("recent_executions", [])
        if executed:
            for item in executed:
                lines.append(
                    f"- {item.get('proposal_id', 'proposal')} | {item.get('status', 'executed')} | "
                    f"validation={'passed' if item.get('validation_passed') else 'failed'}"
                )
        else:
            lines.append("- No executed improvements yet.")
        lines.append("")
        lines.append("Recent rollbacks:")
        rollbacks = summary.get("recent_rollbacks", [])
        if rollbacks:
            for item in rollbacks:
                lines.append(
                    f"- {item.get('proposal_id', 'proposal')} | rollback={'yes' if item.get('rollback_performed') else 'no'} | "
                    f"notes={'; '.join(item.get('notes', [])[:2]) or 'n/a'}"
                )
        else:
            lines.append("- No rollback history yet.")
        return "\n".join(lines)

    def _format_confidence_text(self, summary):
        proposals = summary.get("recent_proposals", [])
        if not proposals and not summary.get("confidence_scores"):
            return "No confidence or risk data recorded yet."
        lines = []
        for item in proposals:
            confidence = item.get("confidence", {}) if isinstance(item.get("confidence"), dict) else {}
            safety = item.get("safety", {}) if isinstance(item.get("safety"), dict) else {}
            lines.append(
                f"{item.get('id', 'proposal')}: confidence {confidence.get('score', 0)} ({confidence.get('level', 'low')}) | "
                f"risk {item.get('risk', 'unknown')} | execution allowed {bool(safety.get('execution_allowed'))}"
            )
        for item in summary.get("confidence_scores", []):
            proposal_id = item.get("proposal_id")
            if proposal_id and not any(line.startswith(f"{proposal_id}:") for line in lines):
                lines.append(
                    f"{proposal_id}: confidence {item.get('score', 0)} ({item.get('level', 'low')}) | status {item.get('status', 'unknown')}"
                )
        return "\n".join(lines)

    def _format_experiment_text(self, experiments):
        if not experiments:
            return "No experiment summaries recorded yet."
        lines = []
        for item in experiments:
            winner = item.get("winner") or {}
            lines.append(f"{item.get('id', 'experiment')}")
            lines.append(
                f"Winner: {winner.get('variant') or 'none'} | "
                f"Metric: {winner.get('metric') or 'n/a'} | Auto ship: {bool(item.get('auto_ship'))}"
            )
            variant_lines = []
            for key, value in (item.get("variants") or {}).items():
                variant_lines.append(f"{key}={value.get('usage_count', 0)} uses")
            if variant_lines:
                lines.append("Usage: " + " | ".join(variant_lines))
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _first_non_empty(*values):
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def build_help_preview_model(self):
        sections = [{"title": title, "lines": lines} for title, lines in OFFICIAL_HELP_SECTIONS]
        return {
            "title": "Rogue Help",
            "subtitle": "Official command reference and desktop usage guidance.",
            "rows": [
                ("Navigation", "help, back, home, esc"),
                ("System", "status, system status, system health, storage overview, agent status, tasks"),
                ("Analysis", "scan downloads, scan desktop, largest files, newest files, top file types, duplicates"),
                ("Actions", "open downloads, open desktop, open folder, organize downloads, smart cleanup, cleanup temp, move files, generate report"),
            ],
            "sections": sections,
            "usage_notes": [
                "Command Center is the default landing view for live state, suggestions, and task visibility.",
                "Chat stays available for command execution and conversation.",
                "Explain Mode shows the latest goal, plan, and result in one place.",
                "Friction Radar surfaces real improvement observations, proposals, approvals, and execution history.",
                "Agent is the technical control panel for loop state, plans, and cycle execution.",
                "Settings shows active appearance and backend defaults.",
            ],
            "agent_modes": [
                "Manual: run observation and planning only when you ask for a cycle.",
                "Assist: prepare approved work without executing it automatically.",
                "Auto: continuously run approved work in the background loop.",
            ],
            "safety_notes": [
                "Potentially destructive commands require explicit confirmation before execution.",
                "Preview-style organization flows remain non-destructive until you confirm them.",
                "Use Command Center for operational overview, Explain Mode for reasoning traces, and Friction Radar for improvement pressure.",
            ],
            "footer": "Safety: Destructive actions require confirmation before execution.\nType help anytime to see this list again.",
        }

    def refresh_backend_status(self):
        self.backend_status = get_ollama_status()
        self._emit_state()
        return self.backend_status

    def save_settings(self):
        write_json(SETTINGS_FILE, self.settings)

    def set_theme(self, theme_name):
        normalized = self.normalize_theme_name(theme_name)
        self.settings["theme"] = normalized
        self.save_settings()
        self.set_status_feedback(f"Done | Theme set to {normalized}", level="done")
        self._emit_state()
        return normalized

    def set_runtime_model(self, model_name):
        selected = str(model_name or "").strip()
        if not selected:
            return False
        llm_bridge.MODEL = selected
        self.backend_status = get_ollama_status()
        self.log_action(f"Runtime model changed to {selected}")
        self.set_status_feedback(f"Done | Model set to {selected}", level="done")
        self._emit_state()
        return True

    def apply_basic_settings(self, *, app_name=None, max_memory_turns=None):
        if app_name is not None:
            self.settings["app_name"] = str(app_name).strip() or self.settings.get("app_name", "Rogue Local")
        if max_memory_turns is not None:
            self.settings["max_memory_turns"] = max(1, int(max_memory_turns))
        self.save_settings()
        self.set_status_feedback("Done | Settings saved", level="done")
        self._emit_state()

    def get_header_context(self):
        return (
            f"{self.get_backend_mode_label()} | {self.backend_status.get('model', 'unknown')} | "
            f"memory {'enabled' if self.modules.get('memory') else 'disabled'} | "
            f"tools {'loaded' if self.modules.get('tools') or self.modules.get('autonomy') else 'unavailable'}"
        )

    def get_settings_payload(self):
        installed = list(self.backend_status.get("installed_models", []))
        current_model = self.backend_status.get("model", "")
        if current_model and current_model not in installed:
            installed.insert(0, current_model)
        return {
            "theme": self.normalize_theme_name(self.settings.get("theme", "Light")),
            "app_name": self.settings.get("app_name", "Rogue Local"),
            "max_memory_turns": int(self.settings.get("max_memory_turns", 12)),
            "model": current_model,
            "installed_models": installed if installed else ([current_model] if current_model else []),
            "backend_mode": self.get_backend_mode_label(),
            "backend_message": self.backend_status.get("message", ""),
        }

    def get_agent_view_payload(self):
        snapshot = self.get_agent_state().snapshot()
        recent_activity = []
        for item in reversed(self.activity_history[-10:]):
            status = "OK" if item["success"] is True else "ERR" if item["success"] is False else "..."
            command_text = f" | {item['command']}" if item.get("command") else ""
            recent_activity.append(f"{item['timestamp']} {status} {item['summary']}{command_text}")
        return {
            "snapshot": snapshot,
            "plan_text": self.format_agent_plan_text(snapshot.get("latest_generated_plan")),
            "activity_text": "\n".join(recent_activity) if recent_activity else "No recent activity yet.",
            "task_summary": self.build_agent_task_status_summary(),
            "workflow_text": self.build_agent_workflow_text(),
        }
