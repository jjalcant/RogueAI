import re
from pathlib import Path

from agent_loop import AgentLoop
from brain.context import get_recent_context_text
from brain.engineering_helper import build_codex_prompt
from brain.proactive_helper import dismiss_suggestion, explain_suggestions, get_suggestions
from execution_logger import ExecutionLogger
from improvement_observer import ImprovementObserver
from memory_manager import MemoryManager
from memory.memory_store import delete_note as delete_saved_note
from memory.memory_store import list_notes as list_saved_notes
from memory.memory_store import save_note as save_memory_note
from memory.memory_store import search_notes
from memory.move_history import find_move_by_name, get_last_batch, get_last_move, list_moves
from memory_store.notes import save_note
from planner import Planner
from result_contract import build_result, format_response_text, normalize_result
from status_reporter import StatusReporter
from task_manager import TaskManager
from tool_registry import build_default_registry
from tools.browser_tool import open_search, open_url
from tools.files_tool import (
    apply_download_organization,
    apply_home_workspace_organization,
    copy_path,
    create_folder,
    delete_path,
    list_path,
    move_path,
    open_path,
    preview_download_organization,
    preview_home_workspace_organization,
    scan_duplicates,
)
from tools.projects_tool import create_project, list_projects, open_projects_folder
from tools.storage_overview import storage_overview
from tools.system_health import system_health
from tools.system_info import system_info
from tools.system_tool import (
    is_application_alias,
    is_folder_alias,
    open_application,
    open_folder,
    run_shell_command,
)
from tasks.task_queue import archive_task, create_task, get_task, list_tasks, update_task_status


BASE = Path(__file__).resolve().parent.parent

FOLDER_REFERENCE_PRONOUNS = {"it", "this", "that", "them", "these", "those"}
FOLDER_INSPECTION_MARKERS = [
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
]
FOLDER_ORGANIZATION_MARKERS = [
    "organize ",
    "organize my ",
    "organise ",
    "organise my ",
    "clean up ",
    "clean up my ",
    "cleanup ",
    "cleanup my ",
    "sort ",
    "sort my ",
    "arrange ",
    "arrange my ",
]


def matches_any(text, patterns):
    return any(pattern in text for pattern in patterns)


def clean_project_name(name):
    name = name.strip().lower().replace(" ", "_")
    valid = []
    for ch in name:
        if ch.isalnum() or ch in ["_", "-"]:
            valid.append(ch)
    return "".join(valid)


def extract_project_name(text):
    lowered = text.lower()
    markers = ["llamado", "llamada", "named"]
    for marker in markers:
        if marker in lowered:
            idx = lowered.find(marker)
            name = text[idx + len(marker):].strip(" :,-")
            return clean_project_name(name)

    parts = text.strip().split()
    if len(parts) >= 4:
        return clean_project_name(parts[-1])

    return ""


def extract_note_text(text):
    cleaned = text
    removable_phrases = [
        "recuérdame",
        "recuerdame",
        "recuerda",
        "guardar nota",
        "guarda esto",
        "nota",
        "apunta",
        "anota",
    ]
    for phrase in removable_phrases:
        cleaned = cleaned.replace(phrase, "")
        cleaned = cleaned.replace(phrase.capitalize(), "")
    return cleaned.strip(" :,-")


def extract_memory_pair(text):
    lowered = text.lower()
    marker = "remember that "
    if marker not in lowered:
        return "", ""
    start = lowered.find(marker) + len(marker)
    remainder = text[start:].strip()
    if " is " in remainder.lower():
        idx = remainder.lower().find(" is ")
        return remainder[:idx].strip(), remainder[idx + 4:].strip()
    return "", ""


def extract_memory_query(text):
    lowered = text.lower()
    markers = [
        "what do you remember about ",
        "what do you remember ",
    ]
    for marker in markers:
        if marker in lowered:
            idx = lowered.find(marker)
            return text[idx + len(marker):].strip(" :,-\"'")
    return ""


def extract_note_key(text):
    lowered = text.lower()
    markers = [
        "forget note ",
        "delete note ",
        "remove note ",
    ]
    for marker in markers:
        if marker in lowered:
            idx = lowered.find(marker)
            return text[idx + len(marker):].strip(" :,-\"'")
    return ""


def extract_path_after_keyword(text, keywords):
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            idx = lowered.find(keyword)
            value = text[idx + len(keyword):].strip(" :,-\"'")
            if value:
                return value
    return ""


def remember_structured_response(app, payload):
    normalized = normalize_result(payload)
    try:
        setattr(app, "last_structured_response_payload", normalized)
    except Exception:
        pass
    return normalized


def format_tool_response(payload, app=None):
    normalized = normalize_result(payload)
    if app is not None:
        remember_structured_response(app, normalized)
        _remember_verified_folder_context(app, normalized)
    return format_response_text(normalized)


def extract_command_after_run(text):
    value = extract_path_after_keyword(
        text,
        ["run command ", "run ", "ejecuta comando ", "ejecuta "],
    )
    return value.strip()


def extract_application_name(text):
    value = extract_path_after_keyword(
        text,
        ["open app ", "open application ", "abre app ", "abre aplicacion ", "abre aplicación ", "open ", "abre "],
    )
    return value.strip()


def extract_open_target(text):
    value = extract_path_after_keyword(text, ["open ", "abre "])
    return value.strip()


def extract_search_query(text):
    lowered = text.lower()
    markers = [
        "search youtube for ",
        "search for ",
        "look up ",
    ]
    for marker in markers:
        if marker in lowered:
            idx = lowered.find(marker)
            return text[idx + len(marker):].strip(" :,-\"'")
    return ""


def extract_two_paths(text, splitter_words):
    lowered = text.lower()
    for splitter in splitter_words:
        if splitter in lowered:
            parts = re.split(splitter, text, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                left = parts[0].strip(" :,-\"'")
                right = parts[1].strip(" :,-\"'")
                return left, right
    return "", ""


def extract_history_filename(text):
    lowered = text.lower()
    marker = "show where "
    suffix = " was moved"
    if marker in lowered and suffix in lowered:
        start = lowered.find(marker) + len(marker)
        end = lowered.rfind(suffix)
        if end > start:
            return text[start:end].strip(" :,-\"'")
    return ""


def extract_suggestion_target(text):
    lowered = text.lower().strip()
    marker = "dismiss suggestion "
    if marker in lowered:
        return lowered.split(marker, 1)[1].strip()
    return ""


def extract_task_id(text):
    match = re.search(r"\btask\s+(\d+)\b", text.lower())
    if match:
        return int(match.group(1))
    return None


def extract_agent_goal(text):
    prefixes = [
        "use agent to ",
        "run agent ",
        "agent ",
        "plan and execute ",
    ]
    lowered = text.lower().strip()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return text.strip()


def _normalize_folder_phrase_target(text):
    value = (text or "").strip(" .")
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"this folder", "current folder"}:
        return "workspace"
    if lowered.startswith("my "):
        value = value[3:].strip()
        lowered = value.lower()
    if lowered.endswith(" folder") and "\\" not in value and "/" not in value:
        value = value[:-7].strip()
    return value


def _extract_folder_request_target(text, markers):
    lowered = text.lower().strip()
    for marker in markers:
        if lowered.startswith(marker):
            return _normalize_folder_phrase_target(text[len(marker):])
    return ""


def is_natural_folder_inspection_request(text):
    return bool(_extract_folder_request_target(text, FOLDER_INSPECTION_MARKERS))


def is_natural_folder_organization_request(text):
    return bool(_extract_folder_request_target(text, FOLDER_ORGANIZATION_MARKERS))


def _extract_verified_folder_target_from_result(payload):
    if not isinstance(payload, dict) or not payload.get("success", False):
        return None

    for section_name in ("summary", "preview", "inspection"):
        section = payload.get(section_name)
        if isinstance(section, dict):
            path_value = section.get("path")
            if str(path_value or "").strip():
                return str(path_value).strip()

    return None


def _extract_verified_folder_target_from_agent_payload(payload):
    if not isinstance(payload, dict):
        return None

    if payload.get("kind") == "agent_run":
        workflow_payload = payload.get("payload", {})
        for item in reversed(workflow_payload.get("results", [])):
            target = _extract_verified_folder_target_from_result(item.get("result", {}))
            if target:
                return target
    else:
        target = _extract_verified_folder_target_from_result(payload)
        if target:
            return target

    return None


def _remember_verified_folder_context(app, payload):
    target = _extract_verified_folder_target_from_result(payload)
    if target:
        setattr(app, "verified_folder_target", target)


def _get_verified_folder_context(app):
    target = getattr(app, "verified_folder_target", None)
    if str(target or "").strip():
        return str(target).strip()

    target = _extract_verified_folder_target_from_result(getattr(app, "last_structured_response_payload", None))
    if target:
        return target

    return _extract_verified_folder_target_from_agent_payload(getattr(app, "last_agent_workflow_payload", None))


def _is_folder_reference_pronoun(target):
    return str(target or "").strip().lower() in FOLDER_REFERENCE_PRONOUNS


def _replace_folder_request_target(text, markers, resolved_target):
    original = str(text or "").strip()
    lowered = original.lower()
    for marker in markers:
        if lowered.startswith(marker):
            return f"{original[:len(marker)]}{resolved_target}"
    return original


def _build_missing_organize_target_response(reference_text):
    reference = str(reference_text or "").strip() or "that reference"
    return (
        "Organize Request Needs Target\n\n"
        "Summary\n"
        "- No verified folder target was available for this organize request.\n\n"
        "Details\n"
        f"- Rogue received the conversational reference '{reference}', but no prior verified folder context exists to reuse.\n\n"
        "Recommendation\n"
        "- Use 'organize desktop' or 'organize downloads', or scan a folder first."
    )


def _resolve_organization_request_text(app, text):
    target = _extract_folder_request_target(text, FOLDER_ORGANIZATION_MARKERS)
    if not _is_folder_reference_pronoun(target):
        return str(text or "").strip(), None

    resolved_target = _get_verified_folder_context(app)
    if not resolved_target:
        return None, _build_missing_organize_target_response(target)

    return _replace_folder_request_target(text, FOLDER_ORGANIZATION_MARKERS, resolved_target), None


def run_agent_workflow(app, goal):
    def remember_ui_payload(payload):
        try:
            app.last_agent_workflow_payload = payload
            target = _extract_verified_folder_target_from_agent_payload(payload)
            if target:
                setattr(app, "verified_folder_target", target)
        except Exception:
            pass

    planner = Planner()
    improvement_observer = getattr(app, "improvement_observer", None)
    if improvement_observer is None:
        improvement_observer = ImprovementObserver(getattr(app, "MEMORY", BASE / "memory"))
    registry = build_default_registry(
        getattr(app, "PROJECTS", BASE / "projects"),
        memory_dir=getattr(app, "MEMORY", BASE / "memory"),
        workspace_root=BASE,
        improvement_observer=improvement_observer,
    )
    memory_manager = MemoryManager(
        memory_root=getattr(app, "MEMORY", BASE / "memory"),
        session_memory=getattr(app, "conversation_memory", []),
    )
    task_manager = TaskManager(getattr(app, "MEMORY", BASE / "memory"))
    logger = ExecutionLogger(getattr(app, "LOGS", BASE / "logs") / "agent.log")
    status_reporter = StatusReporter(BASE / "STATUS.md")
    agent = AgentLoop(
        tool_registry=registry,
        memory_manager=memory_manager,
        execution_logger=logger,
        status_reporter=status_reporter,
        task_manager=task_manager,
        improvement_observer=improvement_observer,
    )
    lowered = goal.lower().strip()
    if lowered == "list tasks":
        tasks = task_manager.list_tasks().get("tasks", [])
        remember_ui_payload({"kind": "task_list", "title": "Agent Tasks", "tasks": tasks})
        return task_manager.format_task_list(tasks, title="Agent Tasks")
    if lowered == "list active tasks":
        tasks = task_manager.list_active_tasks().get("tasks", [])
        remember_ui_payload({"kind": "task_list", "title": "Active Agent Tasks", "tasks": tasks})
        return task_manager.format_task_list(tasks, title="Active Agent Tasks")
    if lowered == "list resumable tasks":
        tasks = task_manager.list_resumable_tasks().get("tasks", [])
        remember_ui_payload({"kind": "task_list", "title": "Resumable Agent Tasks", "tasks": tasks})
        return task_manager.format_task_list(tasks, title="Resumable Agent Tasks")
    if lowered == "recent tasks":
        tasks = task_manager.list_recent_tasks().get("tasks", [])
        remember_ui_payload({"kind": "task_list", "title": "Recent Agent Tasks", "tasks": tasks})
        return task_manager.format_task_list(tasks, title="Recent Agent Tasks")
    if lowered.startswith("show task "):
        try:
            task_id = int(goal.split()[-1])
        except ValueError:
            return "Task ID must be numeric."
        payload = task_manager.get_task(task_id)
        if not payload.get("success"):
            return payload.get("error", f"Task not found: {task_id}")
        remember_ui_payload({"kind": "task_detail", "task": payload["task"]})
        return task_manager.format_task_detail(payload["task"])
    if lowered.startswith("resume task "):
        task_id = int(goal.split()[-1])
        result = agent.resume_task(task_id)
        remember_ui_payload({"kind": "agent_run", "payload": result})
        return result["final_output"]
    result = agent.run_goal(goal, planner=planner)
    remember_ui_payload({"kind": "agent_run", "payload": result})
    return result["final_output"]


def infer_task_type(text):
    lowered = text.lower()
    if "bugfix" in lowered or "fix" in lowered:
        return "bugfix"
    if "refactor" in lowered:
        return "refactor"
    if "test" in lowered:
        return "tests"
    if "doc" in lowered:
        return "docs"
    if "hardening" in lowered or "harden" in lowered:
        return "hardening"
    return "feature"


def infer_task_goal(text):
    lowered = text.lower().strip()
    markers = [
        "create a codex task to ",
        "create a codex task for ",
        "create a bugfix task for ",
        "create a feature task for ",
        "create a refactor task for ",
        "create a tests task for ",
        "create a docs task for ",
        "create a hardening task for ",
    ]
    for marker in markers:
        if marker in lowered:
            start = lowered.find(marker) + len(marker)
            return text[start:].strip(" .")
    return text.strip(" .")


def infer_target_area(goal_text):
    goal = (goal_text or "").strip()
    if not goal:
        return "RogueAI"
    parts = goal.split()
    return " ".join(parts[:4])


def set_active_task_context(app, task):
    setattr(app, "active_task_context", task)


def get_active_task_context(app):
    return getattr(app, "active_task_context", None)


def format_active_task_followup(app):
    task = get_active_task_context(app)
    if not task:
        return None

    task_id = task.get("id", "?")
    title = task.get("title", "Untitled task")
    status = task.get("status", "pending")
    return (
        f"You are still reviewing Codex task {task_id}: {title}\n"
        f"Current status: {status}\n\n"
        "I can stay anchored to this task. Try one of these:\n"
        f"- show task {task_id}\n"
        f"- mark task {task_id} as approved\n"
        f"- mark task {task_id} as done\n"
        f"- archive task {task_id}\n"
        "- ask me to show the Codex-ready prompt again"
    )


def _suggestion_context(app):
    backend_status = getattr(app, "backend_status", {})
    return {
        "downloads_path": getattr(app, "downloads_path", None),
        "home_path": getattr(app, "home_path", None),
        "projects_path": getattr(app, "PROJECTS", None),
        "logs_path": getattr(app, "LOGS", None),
        "backend_status": backend_status,
    }


def get_current_suggestions(app):
    payload = get_suggestions(**_suggestion_context(app))
    suggestions = payload.get("suggestions", [])
    setattr(app, "last_suggestions", suggestions)
    return payload


def format_suggestion_list(payload):
    suggestions = payload.get("suggestions", [])
    if not suggestions:
        return "No active suggestions right now."

    lines = ["Suggested actions:"]
    for index, suggestion in enumerate(suggestions, start=1):
        lines.append(f"{index}. {suggestion['title']}")
        lines.append(f"   Reason: {suggestion['reason']}")
        lines.append(f"   Action: {suggestion['recommended_action']}")
        lines.append(f"   Command: {suggestion['suggested_command']}")
    return "\n".join(lines)


def is_explicit_confirmation(text, expected_type):
    confirmation_map = {
        "organize_downloads": {
            "confirm organize downloads",
            "confirm downloads organization",
        },
        "organize_home_workspace": {
            "confirm organize home workspace",
            "confirm home workspace organization",
            "confirma organizar workspace",
            "confirma organización",
            "si organiza workspace",
            "sí organiza workspace",
        },
    }
    return text in confirmation_map.get(expected_type, set())


def detect_intent(text):
    if text.startswith(("use agent to ", "run agent ", "agent ", "plan and execute ")):
        return "agent_run"

    if matches_any(text, ["remember that "]):
        return "memory_save"

    if text in {"continue", "go on", "proceed", "next"}:
        return "task_followup_ambiguous"

    if matches_any(text, ["search youtube for "]):
        return "browser_search_youtube"

    if matches_any(text, ["search for ", "look up "]):
        return "browser_search"

    if matches_any(text, ["open youtube", "open google", "open github", "open wikipedia", "open this website"]):
        return "browser_open"

    if matches_any(text, ["copy task "]) and " prompt" in text:
        return "copy_task_prompt"

    if matches_any(text, ["copy the current task prompt", "copy current task prompt", "copy this codex prompt"]):
        return "copy_current_task_prompt"

    if matches_any(text, ["create a codex task to ", "create a codex task for ", "create a bugfix task for ", "create a feature task for ", "create a refactor task for ", "create a tests task for ", "create a docs task for ", "create a hardening task for "]):
        return "create_codex_task"

    if matches_any(text, ["list my codex tasks", "show my codex tasks", "list codex tasks"]):
        return "list_codex_tasks"

    if matches_any(text, ["show task "]):
        return "show_codex_task"

    if matches_any(text, ["mark task "]) and " as approved" in text:
        return "approve_codex_task"

    if matches_any(text, ["mark task "]) and " as done" in text:
        return "done_codex_task"

    if matches_any(text, ["archive task "]):
        return "archive_codex_task"

    if matches_any(text, ["what do you suggest", "show suggested actions", "show suggestions", "suggest something"]):
        return "show_suggestions"

    if matches_any(text, ["why are you suggesting this", "why do you suggest this", "explain suggestions"]):
        return "explain_suggestions"

    if matches_any(text, ["dismiss suggestion "]):
        return "dismiss_suggestion"

    if matches_any(text, ["what do you remember about ", "what do you remember "]):
        return "memory_get"

    if matches_any(text, ["list my saved notes", "list saved notes", "show my saved notes", "show saved notes"]):
        return "memory_list"

    if matches_any(text, ["forget note ", "delete note ", "remove note "]):
        return "memory_delete"

    if matches_any(text, ["where did you move my downloads", "what did you move from downloads"]):
        return "move_history_downloads"

    if matches_any(text, ["show my last file move"]):
        return "move_history_last"

    if matches_any(text, ["show my last organized files"]):
        return "move_history_last_batch"

    if matches_any(text, ["show where "]) and " was moved" in text:
        return "move_history_lookup"

    if matches_any(text, ["scan my downloads", "scan downloads", "preview my downloads", "show what files would be moved first"]):
        return "downloads_preview"

    if matches_any(text, ["organize my downloads", "organise my downloads", "organize downloads", "organise downloads"]):
        return "downloads_organize"

    if matches_any(
        text,
        [
            "scan my home workspace",
            "show what would be moved from my home workspace",
            "escanea mi workspace",
            "revisa mi workspace",
            "analiza mi carpeta de usuario",
            "mira mi workspace",
        ],
    ):
        return "home_workspace_preview"

    if matches_any(
        text,
        [
            "organize my home workspace",
            "organise my home workspace",
            "organiza mi workspace",
            "organiza mi espacio de trabajo",
            "organiza mi carpeta de usuario",
            "organiza mi usuario",
            "organiza mi home",
        ],
    ):
        return "home_workspace_organize"

    if matches_any(
        text,
        [
            "system health",
            "check system health",
            "health check",
            "system diagnostics",
        ],
    ):
        return "system_health"

    if matches_any(
        text,
        [
            "storage overview",
            "disk usage",
            "check disk",
            "disk analysis",
            "storage status",
        ],
    ):
        return "storage_overview"

    if is_natural_folder_organization_request(text):
        return "folder_organization_preview"

    if is_natural_folder_inspection_request(text):
        return "folder_inspection"

    if matches_any(
        text,
        [
            "show system info",
            "system info",
            "system specs",
            "pc info",
            "computer info",
            "informacion del sistema",
            "información del sistema",
            "muestra info del sistema",
        ],
    ):
        return "system_info"

    if matches_any(text, ["run command ", "run ", "ejecuta comando ", "ejecuta "]):
        return "run_command"

    if matches_any(text, ["open app ", "open application ", "abre app ", "abre aplicacion ", "abre aplicación "]):
        return "open_application"

    if matches_any(text, ["crea un proyecto", "crear proyecto", "nuevo proyecto", "haz un proyecto"]):
        return "project_create"

    if matches_any(text, ["que proyectos tengo", "qué proyectos tengo", "muestrame mis proyectos", "muéstrame mis proyectos", "ver proyectos", "mostrar proyectos", "mis proyectos", "lista de proyectos", "projects"]):
        return "project_list"

    if matches_any(text, ["recuerda", "recuérdame", "recuerdame", "guarda esto", "guardar nota", "nota", "apunta", "anota"]):
        return "note"

    if matches_any(text, ["estado", "status", "cual es mi estado", "cuál es mi estado", "como estas", "cómo estás", "system status"]):
        return "status"

    if matches_any(text, ["quiero pensar", "ayudame a pensar", "ayúdame a pensar", "piensa conmigo", "pensar", "think"]):
        return "think"

    if matches_any(text, ["haz un plan", "planea", "planifica", "plan", "organiza mis pasos"]):
        return "plan"

    if matches_any(text, ["abre proyectos", "abre la carpeta de proyectos", "open projects folder"]):
        return "open_projects_folder"

    if matches_any(text, ["abre notas", "abre mis notas", "open notes", "open notes file"]):
        return "open_notes"

    if matches_any(text, ["contexto reciente", "recent context", "muéstrame el contexto", "muestrame el contexto"]):
        return "context"

    if matches_any(text, ["abre ", "open "]):
        return "open_path"

    if matches_any(text, ["lista archivos de ", "lista ", "muestrame archivos de ", "muéstrame archivos de ", "list files in ", "list "]):
        return "list_path"

    if matches_any(text, ["crea carpeta ", "crear carpeta ", "make folder ", "create folder "]):
        return "create_folder"

    if matches_any(text, ["escanea duplicados en ", "buscar duplicados en ", "scan duplicates in "]):
        return "scan_duplicates"

    if matches_any(text, ["elimina ", "borrar ", "borra ", "delete "]):
        return "delete_path"

    if matches_any(text, ["mueve ", "move "]):
        return "move_path"

    if matches_any(text, ["copia ", "copy "]):
        return "copy_path"

    if matches_any(text, ["ayuda", "help", "que puedes hacer", "qué puedes hacer"]):
        return "help"

    return "unknown"


def handle_confirmation(app, text):
    if text in ["si", "sí", "yes"] or is_explicit_confirmation(text, app.pending_action["type"]):
        action = app.pending_action
        app.pending_action = None

        if action["type"] == "create_project":
            return format_tool_response(create_project(app.PROJECTS, action["name"]), app=app)

        if action["type"] == "delete_path":
            return format_tool_response(delete_path(action["path"]), app=app)

        if action["type"] == "organize_downloads":
            return format_tool_response(apply_download_organization(action["path"]), app=app)

        if action["type"] == "organize_home_workspace":
            return format_tool_response(apply_home_workspace_organization(action["path"]), app=app)

        return "Acción confirmada, pero no reconocida."

    if text in ["no", "cancelar", "cancel"]:
        app.pending_action = None
        return "Listo. Acción cancelada."

    return "Tengo una acción pendiente. Escribe SI para confirmar o usa la frase exacta de confirmación."


def route_input(app, text):
    lowered = text.lower().strip()

    if app.pending_action:
        return handle_confirmation(app, lowered)

    intent = detect_intent(lowered)

    if intent == "project_list":
        return format_tool_response(list_projects(app.PROJECTS), app=app)

    if intent == "project_create":
        project_name = extract_project_name(text)
        if not project_name:
            return "Dime el nombre del proyecto que quieres crear."
        app.pending_action = {"type": "create_project", "name": project_name}
        return f'Voy a crear el proyecto "{project_name}" en tu carpeta projects.\nEscribe SI para confirmar.'

    if intent == "note":
        note_text = extract_note_text(text)
        if not note_text:
            return "Dime qué quieres guardar."
        return save_note(app.MEMORY, note_text)

    if intent == "memory_save":
        key, value = extract_memory_pair(text)
        if not key or not value:
            return "Usa este formato:\nremember that KEY is VALUE"
        return format_tool_response(save_memory_note(key, value), app=app)

    if intent == "memory_get":
        query = extract_memory_query(text)
        if not query:
            return "Dime qué recuerdo quieres consultar."
        return format_tool_response(search_notes(query), app=app)

    if intent == "memory_list":
        return format_tool_response(list_saved_notes(), app=app)

    if intent == "memory_delete":
        note_key = extract_note_key(text)
        if not note_key:
            return "Dime qué nota quieres olvidar."
        return format_tool_response(delete_saved_note(note_key), app=app)

    if intent == "task_followup_ambiguous":
        anchored = format_active_task_followup(app)
        if anchored:
            return anchored

    if intent == "create_codex_task":
        task_type = infer_task_type(text)
        user_goal = infer_task_goal(text)
        if not user_goal:
            return "Dime qué tarea de Codex quieres crear."
        target_area = infer_target_area(user_goal)
        prompt_payload = build_codex_prompt(task_type, target_area, user_goal)
        title = f"{task_type.title()} task: {user_goal[:60]}"
        task_payload = create_task(title, prompt_payload["task_type"], prompt_payload["prompt_text"])
        set_active_task_context(app, task_payload["task"])
        task_payload.setdefault("suggestions", [])
        task_payload["suggestions"].append(f"Use `show task {task_payload['task']['id']}` to review the prompt.")
        return format_tool_response(task_payload, app=app)

    if intent == "list_codex_tasks":
        return format_tool_response(list_tasks(), app=app)

    if intent == "show_codex_task":
        task_id = extract_task_id(text)
        if not task_id:
            return "Dime qué task quieres ver."
        payload = get_task(task_id)
        if payload.get("success") and payload.get("task"):
            set_active_task_context(app, payload["task"])
        return format_tool_response(payload, app=app)

    if intent == "approve_codex_task":
        task_id = extract_task_id(text)
        if not task_id:
            return "Dime qué task quieres aprobar."
        payload = update_task_status(task_id, "approved")
        if payload.get("success") and payload.get("task"):
            set_active_task_context(app, payload["task"])
        return format_tool_response(payload, app=app)

    if intent == "done_codex_task":
        task_id = extract_task_id(text)
        if not task_id:
            return "Dime qué task quieres marcar como done."
        payload = update_task_status(task_id, "done")
        if payload.get("success") and payload.get("task"):
            set_active_task_context(app, payload["task"])
        return format_tool_response(payload, app=app)

    if intent == "archive_codex_task":
        task_id = extract_task_id(text)
        if not task_id:
            return "Dime qué task quieres archivar."
        payload = archive_task(task_id)
        if payload.get("success") and payload.get("task"):
            set_active_task_context(app, payload["task"])
        return format_tool_response(payload, app=app)

    if intent == "copy_task_prompt":
        task_id = extract_task_id(text)
        if not task_id:
            return "Dime qué task prompt quieres copiar."
        if not hasattr(app, "copy_task_prompt"):
            return "Clipboard handoff is not available in this context."
        return format_tool_response(app.copy_task_prompt(task_id), app=app)

    if intent == "copy_current_task_prompt":
        if not hasattr(app, "copy_current_task_prompt"):
            return "Clipboard handoff is not available in this context."
        return format_tool_response(app.copy_current_task_prompt(), app=app)

    if intent == "show_suggestions":
        return format_suggestion_list(get_current_suggestions(app))

    if intent == "explain_suggestions":
        payload = explain_suggestions(**_suggestion_context(app))
        setattr(app, "last_suggestions", payload.get("suggestions", []))
        return payload["result"]

    if intent == "dismiss_suggestion":
        target = extract_suggestion_target(text)
        if not target:
            return "Dime qué sugerencia quieres descartar."
        suggestions = getattr(app, "last_suggestions", None) or get_current_suggestions(app).get("suggestions", [])
        suggestion_id = target
        if target.isdigit():
            index = int(target) - 1
            if index < 0 or index >= len(suggestions):
                return f"No encontré la sugerencia {target}."
            suggestion_id = suggestions[index]["id"]
        result = dismiss_suggestion(suggestion_id)
        updated = get_current_suggestions(app)
        return f"{result['result']}\n{format_suggestion_list(updated)}"

    if intent == "move_history_downloads":
        return format_tool_response(list_moves(scope="downloads"), app=app)

    if intent == "move_history_last":
        return format_tool_response(get_last_move(), app=app)

    if intent == "move_history_last_batch":
        return format_tool_response(get_last_batch(), app=app)

    if intent == "move_history_lookup":
        filename = extract_history_filename(text)
        if not filename:
            return "Dime qué archivo quieres buscar en el historial."
        return format_tool_response(find_move_by_name(filename), app=app)

    if intent == "status":
        return (
            "Estado actual de Rogue:\n"
            f"- memoria: {app.count_items(app.MEMORY)} items\n"
            f"- proyectos: {app.count_items(app.PROJECTS)} items\n"
            f"- agentes: {app.count_items(app.AGENTS)} items\n"
            f"- autonomía: {app.count_items(app.AUTONOMY)} items\n"
            "- planner: habilitado\n"
            "- agent loop: habilitado\n"
            "- files tool: conectada\n"
            "- borrar: con confirmación\n"
            "- mover/copiar/crear/abrir: habilitado"
        )

    if intent == "think":
        return (
            "Vamos a pensar.\n\n"
            "Respóndeme esto:\n"
            "1. qué quieres resolver\n"
            "2. qué te está frenando\n"
            "3. cuál es el siguiente paso más pequeño"
        )

    if intent == "plan":
        return (
            "Vamos a planearlo.\n\n"
            "Dime:\n"
            "1. el proyecto\n"
            "2. el resultado que quieres\n"
            "3. lo que ya tienes hecho\n\n"
            "Si quieres ejecución estructurada, usa:\n"
            "- agent report system status\n"
            "- agent open projects folder"
        )

    if intent == "agent_run":
        goal = extract_agent_goal(text)
        if not goal:
            return "Tell me the goal you want the agent to plan and execute."
        return run_agent_workflow(app, goal)

    if intent == "open_projects_folder":
        return format_tool_response(open_projects_folder(app.PROJECTS), app=app)

    if intent == "open_notes":
        return app.open_notes_file()

    if intent == "context":
        return get_recent_context_text(app.conversation_memory)

    if intent == "open_path":
        target_value = extract_open_target(text)
        if not target_value:
            return "Dime qué ruta, carpeta o aplicación quieres abrir."

        if is_folder_alias(target_value):
            return format_tool_response(open_folder(target_value), app=app)

        if is_application_alias(target_value):
            return format_tool_response(open_application(target_value), app=app)

    if intent == "browser_open":
        target_value = extract_open_target(text)
        if target_value == "this website":
            target_value = getattr(app, "last_browser_target", None)
            if not target_value:
                return "Tell me which website you want to open."
        payload = open_url(target_value)
        if payload.get("success"):
            setattr(app, "last_browser_target", payload.get("url"))
        return format_tool_response(payload, app=app)

    if intent == "browser_search":
        query = extract_search_query(text)
        if not query:
            return "Tell me what you want to search for."
        payload = open_search(query, engine="google")
        if payload.get("success"):
            setattr(app, "last_browser_target", payload.get("url"))
        return format_tool_response(payload, app=app)

    if intent == "browser_search_youtube":
        query = extract_search_query(text)
        if not query:
            return "Tell me what you want to search for on YouTube."
        payload = open_search(query, engine="youtube")
        if payload.get("success"):
            setattr(app, "last_browser_target", payload.get("url"))
        return format_tool_response(payload, app=app)

    if intent == "system_info":
        return format_tool_response(system_info(), app=app)

    if intent == "system_health":
        return format_tool_response(system_health(), app=app)

    if intent == "storage_overview":
        return format_tool_response(storage_overview(), app=app)

    if intent == "downloads_preview":
        return format_tool_response(preview_download_organization("downloads"), app=app)

    if intent == "downloads_organize":
        return run_agent_workflow(app, text)

    if intent == "home_workspace_preview":
        return format_tool_response(preview_home_workspace_organization("home workspace"), app=app)

    if intent == "home_workspace_organize":
        preview = preview_home_workspace_organization("home workspace")
        if not preview["success"]:
            return format_tool_response(preview, app=app)
        return (
            f"{format_tool_response(preview, app=app)}\n\n"
            "Preview only. No files were modified."
        )

    if intent == "folder_organization_preview":
        resolved_text, missing_target_response = _resolve_organization_request_text(app, text)
        if missing_target_response:
            return missing_target_response
        return run_agent_workflow(app, resolved_text)

    if intent == "folder_inspection":
        return run_agent_workflow(app, text)

    if intent == "run_command":
        command_value = extract_command_after_run(text)
        if not command_value:
            return "Dime qué comando local quieres ejecutar."
        return format_tool_response(run_shell_command(command_value), app=app)

    if intent == "open_application":
        app_value = extract_application_name(text)
        if not app_value:
            return "Dime qué aplicación quieres abrir."
        return format_tool_response(open_application(app_value), app=app)

    if intent == "list_path":
        path_value = extract_path_after_keyword(
            text,
            ["lista archivos de ", "lista ", "muestrame archivos de ", "muéstrame archivos de ", "list files in ", "list "],
        )
        if not path_value:
            return "Dime qué ruta quieres listar."
        return format_tool_response(list_path(path_value), app=app)

    if intent == "create_folder":
        path_value = extract_path_after_keyword(text, ["crea carpeta ", "crear carpeta ", "make folder ", "create folder "])
        if not path_value:
            return "Dime qué carpeta quieres crear."
        return format_tool_response(create_folder(path_value), app=app)

    if intent == "scan_duplicates":
        path_value = extract_path_after_keyword(text, ["escanea duplicados en ", "buscar duplicados en ", "scan duplicates in "])
        if not path_value:
            return "Dime qué carpeta quieres escanear."
        return format_tool_response(scan_duplicates(path_value), app=app)

    if intent == "delete_path":
        path_value = extract_path_after_keyword(text, ["elimina ", "borrar ", "borra ", "delete "])
        if not path_value:
            return "Dime qué ruta quieres eliminar."
        app.pending_action = {"type": "delete_path", "path": path_value}
        return f'Voy a eliminar esta ruta:\n{path_value}\n\nEscribe SI para confirmar.'

    if intent == "move_path":
        src, dst = extract_two_paths(extract_path_after_keyword(text, ["mueve ", "move "]), [r"\sa\s", r"\sto\s"])
        if not src or not dst:
            return "Usa este formato:\nmueve ORIGEN a DESTINO"
        return format_tool_response(move_path(src, dst), app=app)

    if intent == "copy_path":
        src, dst = extract_two_paths(extract_path_after_keyword(text, ["copia ", "copy "]), [r"\sa\s", r"\sto\s"])
        if not src or not dst:
            return "Usa este formato:\ncopia ORIGEN a DESTINO"
        return format_tool_response(copy_path(src, dst), app=app)

    if intent == "help":
        return (
            "Ahora mismo puedo ayudarte con:\n"
            "- ver proyectos\n"
            "- crear proyectos\n"
            "- guardar notas\n"
            "- guardar memoria persistente\n"
            "- consultar memoria persistente\n"
            "- listar notas guardadas\n"
            "- olvidar notas guardadas\n"
            "- ver sugerencias proactivas\n"
            "- descartar sugerencias\n"
            "- crear tareas de Codex\n"
            "- listar tareas de Codex\n"
            "- actualizar estado de tareas de Codex\n"
            "- revisar historial de movimientos\n"
            "- ver estado\n"
            "- pensar\n"
            "- planear\n"
            "- ejecutar flujos agentic con planner + agent loop\n"
            "- abrir la carpeta de proyectos\n"
            "- abrir notas\n"
            "- mostrar contexto reciente\n"
            "- abrir cualquier ruta\n"
            "- abrir sitios web explícitos\n"
            "- buscar en la web o en YouTube\n"
            "- abrir carpetas del sistema\n"
            "- abrir aplicaciones locales\n"
            "- ejecutar comandos locales seguros\n"
            "- previsualizar organización de downloads\n"
            "- previsualizar organización de carpetas sin modificar archivos\n"
            "- previsualizar home workspace\n"
            "- inspeccionar carpetas con lenguaje natural\n"
            "- revisar salud del sistema\n"
            "- revisar almacenamiento\n"
            "- mostrar información del sistema\n"
            "- listar cualquier carpeta\n"
            "- crear carpetas\n"
            "- copiar rutas\n"
            "- mover rutas\n"
            "- escanear duplicados en cualquier carpeta\n"
            "- eliminar rutas con confirmación\n\n"
            "Ejemplos:\n"
            "- open downloads folder\n"
            "- open google\n"
            "- open youtube\n"
            "- search for python tkinter docs\n"
            "- search youtube for doberman training\n"
            "- look up local llm setup\n"
            "- open notepad\n"
            "- remember that my main project is RogueAI\n"
            "- what do you remember about project\n"
            "- list my saved notes\n"
            "- forget note main project\n"
            "- scan my downloads\n"
            "- show suggested actions\n"
            "- why are you suggesting this\n"
            "- dismiss suggestion 1\n"
            "- create a Codex task to add browser control\n"
            "- list my Codex tasks\n"
            "- show task 3\n"
            "- mark task 3 as approved\n"
            "- mark task 3 as done\n"
            "- archive task 3\n"
            "- organize my downloads\n"
            "- where did you move my downloads\n"
            "- show my last file move\n"
            "- show where report.pdf was moved\n"
            "- scan my home workspace\n"
            "- organize my home workspace\n"
            "- system health\n"
            "- storage overview\n"
            "- scan desktop\n"
            "- inspect desktop\n"
            "- organize desktop\n"
            "- organize documents\n"
            "- agent report system status\n"
            "- agent open projects folder\n"
        )

    app.start_async_fallback(text)
    return "__ASYNC__"
