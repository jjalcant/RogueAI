"""Persistent engineering task queue for Codex-ready requests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from result_contract import build_result, make_artifact


BASE = Path(__file__).resolve().parent.parent
TASKS_DIR = BASE / "tasks"
STORE_FILE = TASKS_DIR / "engineering_tasks.json"


def _structured_result(success, action, result="", error=None, observed=None, artifacts=None, warnings=None, errors=None, **extra):
    payload = build_result(
        success=success,
        action=action,
        result=result,
        error=error,
        observed=observed,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        **extra,
    )
    payload.update(extra)
    return payload


def _load_tasks():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        STORE_FILE.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_tasks(tasks):
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


def _next_id(tasks):
    if not tasks:
        return 1
    return max(int(task.get("id", 0)) for task in tasks) + 1


def create_task(title, task_type, prompt_text, status="pending"):
    action = "create_task"
    tasks = _load_tasks()
    task = {
        "id": _next_id(tasks),
        "title": title,
        "type": task_type,
        "prompt_text": prompt_text,
        "status": status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    tasks.append(task)
    _save_tasks(tasks)
    return _structured_result(
        True,
        action,
        result=f"Created task {task['id']}: {task['title']}",
        observed=[f"Persisted engineering task {task['id']} with status {task['status']}."],
        artifacts=[make_artifact("task_store", path=str(STORE_FILE), description="Engineering task store", exists=STORE_FILE.exists(), verified=True)],
        task=task,
    )


def list_tasks():
    action = "list_tasks"
    tasks = _load_tasks()
    if not tasks:
        return _structured_result(
            True,
            action,
            result="No Codex tasks saved.",
            observed=["Verified engineering task store contains 0 tasks."],
            artifacts=[make_artifact("task_store", path=str(STORE_FILE), description="Engineering task store", exists=STORE_FILE.exists(), verified=True)],
            tasks=[],
        )
    lines = [f"{task['id']}. [{task['status']}] {task['title']} ({task['type']})" for task in tasks[-20:]]
    return _structured_result(
        True,
        action,
        result="\n".join(lines),
        observed=[f"Loaded {len(tasks[-20:])} persisted engineering tasks."],
        artifacts=[make_artifact("task_store", path=str(STORE_FILE), description="Engineering task store", exists=STORE_FILE.exists(), verified=True)],
        tasks=tasks[-20:],
    )


def get_task(task_id):
    action = "get_task"
    tasks = _load_tasks()
    for task in tasks:
        if int(task.get("id", 0)) == int(task_id):
            lines = [
                f"Task {task['id']}: {task['title']}",
                f"Type: {task['type']}",
                f"Status: {task['status']}",
                f"Created: {task['created_at']}",
                "",
                task["prompt_text"],
            ]
            return _structured_result(True, action, result="\n".join(lines), task=task)
    return _structured_result(False, action, error=f"Task {task_id} not found.")


def update_task_status(task_id, status):
    action = "update_task_status"
    tasks = _load_tasks()
    for task in tasks:
        if int(task.get("id", 0)) == int(task_id):
            task["status"] = status
            _save_tasks(tasks)
            return _structured_result(
                True,
                action,
                result=f"Task {task_id} marked as {status}.",
                observed=[f"Persisted engineering task {task_id} status as {status}."],
                artifacts=[make_artifact("task_store", path=str(STORE_FILE), description="Engineering task store", exists=STORE_FILE.exists(), verified=True)],
                task=task,
            )
    return _structured_result(False, action, error=f"Task {task_id} not found.")


def archive_task(task_id):
    return update_task_status(task_id, "archived")
