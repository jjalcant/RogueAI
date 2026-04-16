"""Lightweight proactive suggestion helpers for RogueAI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE / "memory"
STATE_FILE = MEMORY_DIR / "proactive_state.json"
LOGS_DIR = BASE / "logs"
LOG_FILE = LOGS_DIR / "brain.log"


def _structured_result(success, action, result="", error=None, **extra):
    payload = {
        "success": success,
        "action": action,
        "result": result,
        "error": error,
    }
    payload.update(extra)
    return payload


def _log_action(action, details):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] proactive_helper action={action} details={details}\n")
    except Exception:
        pass


def _load_state():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = {"dismissed_ids": []}
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"dismissed_ids": []}
        dismissed_ids = data.get("dismissed_ids", [])
        if not isinstance(dismissed_ids, list):
            dismissed_ids = []
        return {"dismissed_ids": dismissed_ids}
    except Exception:
        return {"dismissed_ids": []}


def _save_state(state):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _count_loose_files(folder):
    if not folder.exists() or not folder.is_dir():
        return 0
    return sum(1 for item in folder.iterdir() if item.is_file())


def _recent_log_has_error(logs_path):
    log_file = Path(logs_path) / "brain.log"
    if not log_file.exists():
        return False
    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-80:]
        joined = "\n".join(lines).lower()
        return any(token in joined for token in [" error", "failed", "traceback", "startup self-check failed", "backend error"])
    except Exception:
        return False


def _build_suggestion(suggestion_id, title, reason, recommended_action, suggested_command, confirmation_required=False):
    return {
        "id": suggestion_id,
        "title": title,
        "reason": reason,
        "recommended_action": recommended_action,
        "confirmation_required": confirmation_required,
        "suggested_command": suggested_command,
    }


def collect_suggestions(downloads_path=None, home_path=None, projects_path=None, logs_path=None, backend_status=None):
    downloads = Path(downloads_path) if downloads_path else Path.home() / "Downloads"
    home = Path(home_path) if home_path else Path.home()
    projects = Path(projects_path) if projects_path else BASE / "projects"
    logs = Path(logs_path) if logs_path else BASE / "logs"
    backend_status = backend_status or {}

    suggestions = []

    downloads_count = _count_loose_files(downloads)
    if downloads_count >= 5:
        suggestions.append(
            _build_suggestion(
                "downloads_clutter",
                "Downloads look cluttered",
                f"I found {downloads_count} loose files in Downloads that may be easier to review in a preview-first organization pass.",
                "Preview Downloads organization",
                "scan my downloads",
                confirmation_required=False,
            )
        )

    home_count = _count_loose_files(home)
    if home_count >= 4:
        suggestions.append(
            _build_suggestion(
                "home_workspace_clutter",
                "Home workspace may need review",
                f"I found {home_count} loose files in your home workspace. A preview can show what would move without changing anything.",
                "Preview Home Workspace organization",
                "scan my home workspace",
                confirmation_required=False,
            )
        )

    if not backend_status.get("reachable") or not backend_status.get("model_available"):
        suggestions.append(
            _build_suggestion(
                "backend_unavailable",
                "Backend looks unavailable",
                backend_status.get("message", "The model backend is not fully available, so Rogue may stay in router-only mode."),
                "Run Diagnostics",
                "diagnostics",
                confirmation_required=False,
            )
        )

    if _recent_log_has_error(logs):
        suggestions.append(
            _build_suggestion(
                "recent_log_errors",
                "Recent logs may need attention",
                "I found recent error-like entries in logs/brain.log. Reviewing logs can help explain degraded behavior.",
                "Open Logs",
                "open logs",
                confirmation_required=False,
            )
        )

    projects_count = 0
    if projects.exists() and projects.is_dir():
        try:
            projects_count = len(list(projects.iterdir()))
        except Exception:
            projects_count = 0
    if projects_count == 0:
        suggestions.append(
            _build_suggestion(
                "low_project_context",
                "Project context looks thin",
                "I do not see any project folders yet. A project note can make future suggestions and organization more relevant.",
                "Create project note",
                "remember that my main project is RogueAI",
                confirmation_required=False,
            )
        )

    return suggestions


def get_suggestions(downloads_path=None, home_path=None, projects_path=None, logs_path=None, backend_status=None):
    action = "get_suggestions"
    state = _load_state()
    dismissed_ids = set(state.get("dismissed_ids", []))
    suggestions = [
        item for item in collect_suggestions(
            downloads_path=downloads_path,
            home_path=home_path,
            projects_path=projects_path,
            logs_path=logs_path,
            backend_status=backend_status,
        )
        if item["id"] not in dismissed_ids
    ]
    result_text = f"Found {len(suggestions)} active suggestions."
    _log_action(action, result_text)
    return _structured_result(True, action, result=result_text, suggestions=suggestions)


def explain_suggestions(downloads_path=None, home_path=None, projects_path=None, logs_path=None, backend_status=None):
    action = "explain_suggestions"
    payload = get_suggestions(
        downloads_path=downloads_path,
        home_path=home_path,
        projects_path=projects_path,
        logs_path=logs_path,
        backend_status=backend_status,
    )
    suggestions = payload.get("suggestions", [])
    if not suggestions:
        return _structured_result(True, action, result="No active suggestions right now.", suggestions=[])

    lines = []
    for index, suggestion in enumerate(suggestions, start=1):
        lines.append(f"{index}. {suggestion['title']}")
        lines.append(f"   Reason: {suggestion['reason']}")
        lines.append(f"   Suggested command: {suggestion['suggested_command']}")
    return _structured_result(True, action, result="\n".join(lines), suggestions=suggestions)


def dismiss_suggestion(suggestion_id):
    action = "dismiss_suggestion"
    state = _load_state()
    dismissed_ids = state.get("dismissed_ids", [])
    if suggestion_id not in dismissed_ids:
        dismissed_ids.append(suggestion_id)
        state["dismissed_ids"] = dismissed_ids
        _save_state(state)
    _log_action(action, f"dismissed={suggestion_id}")
    return _structured_result(True, action, result=f"Dismissed suggestion: {suggestion_id}", suggestion_id=suggestion_id)

