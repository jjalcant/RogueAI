"""Optional CLI support for RogueAI."""

from pathlib import Path
import json
from datetime import datetime
import sys
import subprocess

from agent_loop import AgentLoop
from app_config import ConfigError, load_or_create_modules, load_or_create_settings
from brain.llm_bridge import get_ollama_status
from brain.proactive_helper import get_suggestions
from execution_logger import ExecutionLogger
from improvement_observer import ImprovementObserver
from memory_manager import MemoryManager
from memory import memory_store
from memory import move_history
from planner import Planner
from status_reporter import StatusReporter
from task_manager import TaskManager
from tasks import task_queue
from tool_registry import build_default_registry
from tools.files_tool import preview_download_organization, preview_home_workspace_organization
from tools import system_tool

BASE = Path(__file__).resolve().parent

MEMORY = BASE / "memory"
PROJECTS = BASE / "projects"
AGENTS = BASE / "agents"
AUTONOMY = BASE / "autonomy"
CONFIG = BASE / "config"
CODE = BASE / "Code"
SETTINGS_FILE = CONFIG / "settings.json"
MODULES_FILE = CONFIG / "modules.json"

def load_json(path):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def log_action(action):
    logs_dir = BASE / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "brain.log"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {action}\n")

def count_items(folder):
    if folder.exists() and folder.is_dir():
        return len(list(folder.iterdir()))
    return 0


def folder_status_lines():
    folders = {
        "memory": MEMORY,
        "projects": PROJECTS,
        "agents": AGENTS,
        "autonomy": AUTONOMY,
        "config": CONFIG,
        "logs": BASE / "logs",
    }
    lines = []
    for name, folder in folders.items():
        state = "OK" if folder.exists() else "MISSING"
        lines.append(f" - {name}: {state} ({folder})")
    return lines


def show_diagnostics():
    print("\n=== ROGUE DIAGNOSTICS ===")
    print("Desktop app entrypoint: python rogue_app.py")
    print("CLI support: brain.py")

    try:
        settings = load_or_create_settings(SETTINGS_FILE)
        modules = load_or_create_modules(MODULES_FILE)
        print("\nConfig:")
        print(" - settings.json: OK")
        print(" - modules.json: OK")
        print(f" - app_name: {settings.get('app_name')}")
        print(f" - max_memory_turns: {settings.get('max_memory_turns')}")
        enabled_modules = [name for name, enabled in modules.items() if enabled]
        print(f" - enabled modules: {', '.join(enabled_modules)}")
    except ConfigError as e:
        print("\nConfig:")
        print(f" - ERROR: {e}")

    print("\nFolders:")
    for line in folder_status_lines():
        print(line)

    ollama = get_ollama_status()
    print("\nBackend:")
    print(f" - reachable: {'YES' if ollama['reachable'] else 'NO'}")
    print(f" - model configured: {ollama['model']}")
    print(f" - model available: {'YES' if ollama['model_available'] else 'NO'}")
    print(f" - details: {ollama['message']}")

    print("\nSystem tools:")
    print(f" - System tools loaded: {bool(system_tool)}")
    print(" - Command execution available: True")
    print(" - Browser control available: True")

    print("\nFeatures:")
    print(f" - Memory enabled: {bool(memory_store)}")
    print(f" - File organization available: {callable(preview_download_organization)}")
    print(f" - File move history enabled: {bool(move_history)}")
    print(f" - Home workspace organization available: {callable(preview_home_workspace_organization)}")
    print(" - Downloads organization mode: local organized subfolders")
    suggestions = get_suggestions(
        downloads_path=Path.home() / "Downloads",
        home_path=Path.home(),
        projects_path=PROJECTS,
        logs_path=BASE / "logs",
        backend_status=ollama,
    )
    print(f" - Proactive assistant enabled: True")
    print(f" - Current suggestion count: {len(suggestions.get('suggestions', []))}")
    tasks = task_queue.list_tasks()
    print(f" - Engineering task queue enabled: True")
    print(f" - Current engineering task count: {len(tasks.get('tasks', []))}")
    print(" - Clipboard handoff available: True")

    active_mode = "Ollama-backed mode" if ollama["reachable"] and ollama["model_available"] else "Router-only mode"
    print("\nActive mode:")
    print(f" - {active_mode}")
    log_action(f"Diagnostics checked: {active_mode} | Ollama reachable={ollama['reachable']}")

def show_status():
    try:
        settings = load_or_create_settings(SETTINGS_FILE)
        modules = load_or_create_modules(MODULES_FILE)
    except ConfigError as e:
        print("\n=== ROGUE CLI STATUS ===")
        print("brain.py is optional CLI support.")
        print(f"Config error: {e}")
        log_action(f"CLI config error: {e}")
        return

    print("\n=== ROGUE BRAIN V2 (Optional CLI Support) ===")
    print("Assistant:", settings.get("assistant_name", settings.get("app_name", "Unknown")))
    print("Mode:", settings.get("mode", "normal"))

    print("\nModules:")
    for name, enabled in modules.items():
        state = "ON" if enabled else "OFF"
        print(f" - {name}: {state}")

    print("\nFolders:")
    print(" - memory items:", count_items(MEMORY))
    print(" - project folders/items:", count_items(PROJECTS))
    print(" - agents items:", count_items(AGENTS))
    print(" - autonomy items:", count_items(AUTONOMY))

    ollama = get_ollama_status()
    print("\nBackend:")
    print(f" - reachable: {'YES' if ollama['reachable'] else 'NO'}")
    print(f" - mode: {'Ollama-backed' if ollama['reachable'] and ollama['model_available'] else 'Router-only'}")

    log_action("Brain status checked")

def plan_mode():
    print("\n=== PLAN MODE ===")
    print("Use Rogue to break goals into smaller actions.")
    print("Suggested flow:")
    print(" 1. Identify one active project")
    print(" 2. Define the next smallest action")
    print(" 3. Execute before switching context")
    log_action("Plan mode opened")

def clean_mode():
    print("\n=== CLEAN MODE ===")
    cleaner = CODE / "desktop_cleaner.py"

    if cleaner.exists():
        print("Desktop cleaner found.")
        print("Run it manually with:")
        print(" python Code/desktop_cleaner.py")
        log_action("Clean mode opened")
    else:
        print("Desktop cleaner not found.")
        log_action("Clean mode failed: cleaner missing")

def think_mode():
    print("\n=== THINK MODE ===")
    print("Use this format:")
    print(" rogue note [idea/task/thought]")
    print("")
    print("Suggested mental workflow:")
    print(" 1. What am I trying to solve?")
    print(" 2. What is the bottleneck?")
    print(" 3. What is the next smallest move?")
    log_action("Think mode opened")

def project_mode():
    print("\n=== PROJECT MODE ===")

    if not PROJECTS.exists():
        print("Projects folder not found.")
        log_action("Project mode failed: folder missing")
        return

    items = [item for item in PROJECTS.iterdir()]

    if not items:
        print("No projects found.")
        log_action("Project mode opened: no projects")
        return

    print("Projects found:")
    for item in items:
        label = "[DIR]" if item.is_dir() else "[FILE]"
        print(f" {label} {item.name}")

    log_action("Project mode opened")

def new_project_mode():
    args = sys.argv[2:]

    if not args:
        print("No project name provided.")
        return

    project_name = "_".join(args).strip()
    project_path = PROJECTS / project_name

    if project_path.exists():
        print(f"Project already exists: {project_name}")
        log_action(f"New project skipped: {project_name} already exists")
        return

    project_path.mkdir(parents=True, exist_ok=True)

    print(f"Project created: {project_name}")
    print(f"Location: {project_path}")
    log_action(f"New project created: {project_name}")

def help_mode():
    print("\n=== ROGUE COMMANDS ===")
    print("brain.py is optional CLI support.")
    print("Desktop app entrypoint: python rogue_app.py")
    print("python brain.py status")
    print("python brain.py plan")
    print("python brain.py clean")
    print("python brain.py think")
    print("python brain.py project")
    print("python brain.py newproject [name]")
    print("python brain.py note \"your text here\"")
    print("python brain.py diagnostics")
    print("python brain.py agent [goal]")
    print("python brain.py help")
    log_action("Help shown")


def build_agent_runtime():
    planner = Planner()
    improvement_observer = ImprovementObserver(MEMORY)
    registry = build_default_registry(PROJECTS, memory_dir=MEMORY, workspace_root=BASE, improvement_observer=improvement_observer)
    memory_manager = MemoryManager(MEMORY)
    task_manager = TaskManager(MEMORY)
    logger = ExecutionLogger(BASE / "logs" / "agent.log")
    status_reporter = StatusReporter(BASE / "STATUS.md")
    agent = AgentLoop(
        tool_registry=registry,
        memory_manager=memory_manager,
        execution_logger=logger,
        status_reporter=status_reporter,
        task_manager=task_manager,
        improvement_observer=improvement_observer,
    )
    return planner, task_manager, agent


def handle_agent_task_visibility(goal, task_manager):
    lowered = goal.lower().strip()

    if lowered == "list tasks":
        payload = task_manager.list_tasks()
        return {
            "success": True,
            "final_output": task_manager.format_task_list(payload.get("tasks", []), title="Agent Tasks"),
        }

    if lowered == "list active tasks":
        payload = task_manager.list_active_tasks()
        return {
            "success": True,
            "final_output": task_manager.format_task_list(payload.get("tasks", []), title="Active Agent Tasks"),
        }

    if lowered == "list resumable tasks":
        payload = task_manager.list_resumable_tasks()
        return {
            "success": True,
            "final_output": task_manager.format_task_list(payload.get("tasks", []), title="Resumable Agent Tasks"),
        }

    if lowered == "recent tasks":
        payload = task_manager.list_recent_tasks()
        return {
            "success": True,
            "final_output": task_manager.format_task_list(payload.get("tasks", []), title="Recent Agent Tasks"),
        }

    if lowered.startswith("show task "):
        try:
            task_id = int(goal.split()[-1])
        except ValueError:
            return {"success": False, "final_output": "Task ID must be numeric."}
        payload = task_manager.get_task(task_id)
        if not payload.get("success"):
            return {"success": False, "final_output": payload.get("error", f"Task not found: {task_id}")}
        return {
            "success": True,
            "final_output": task_manager.format_task_detail(payload["task"]),
        }

    return None


def agent_mode():
    goal = " ".join(sys.argv[2:]).strip() or "report system status"
    planner, task_manager, agent = build_agent_runtime()

    visibility_result = handle_agent_task_visibility(goal, task_manager)
    if visibility_result is not None:
        result = visibility_result
    elif goal.lower().startswith("resume task "):
        task_id = int(goal.split()[-1])
        result = agent.resume_task(task_id)
    else:
        result = agent.run_goal(goal, planner=planner)
    print(result["final_output"])
    if result.get("task_id") is not None:
        print(f"Task ID: {result['task_id']}")
    log_action(f"Agent mode executed: {goal} success={result['success']}")

def main():
    if len(sys.argv) == 1:
        show_status()
        return

    command = sys.argv[1].lower()

    if command == "status":
        show_status()
    elif command == "plan":
        plan_mode()
    elif command == "clean":
        clean_mode()
    elif command == "think":
        think_mode()
    elif command == "project":
        project_mode()
    elif command == "newproject":
        new_project_mode()
    elif command == "note":
        args = sys.argv[2:]
        subprocess.run(["python", "Code/memory_engine.py"] + args)
    elif command == "diagnostics":
        show_diagnostics()
    elif command == "agent":
        agent_mode()
    else:
        help_mode()

if __name__ == "__main__":
    main()
