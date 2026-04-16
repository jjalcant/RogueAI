import json
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE / "memory"
STORE_FILE = MEMORY_DIR / "file_move_history.json"
LOGS = BASE / "logs"
LOG_FILE = LOGS / "brain.log"


def _log_action(action, success, details):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] move_history action={action} success={success} details={details}\n")
    except Exception:
        pass


def _structured_result(success, action, result="", error=None, **extra):
    payload = {
        "success": success,
        "action": action,
        "result": result,
        "error": error,
    }
    payload.update(extra)
    return payload


def _load_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        STORE_FILE.write_text("[]", encoding="utf-8")
        return []

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_store(data):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_moves(entries):
    action = "record_moves"
    try:
        data = _load_store()
        data.extend(entries)
        _save_store(data)
        result = _structured_result(True, action, result=f"Recorded {len(entries)} moved files.", entries=entries)
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e), entries=[])
        _log_action(action, False, result["error"])
        return result


def get_last_move():
    action = "get_last_move"
    data = _load_store()
    if not data:
        return _structured_result(False, action, error="No file move history available.", entry=None)

    entry = data[-1]
    result = _structured_result(
        True,
        action,
        result=f"{entry['original_path']} -> {entry['destination_path']}",
        entry=entry,
    )
    _log_action(action, True, result["result"])
    return result


def get_last_batch(scope=None):
    action = "get_last_batch"
    data = _load_store()
    if scope:
        data = [entry for entry in data if entry.get("scope") == scope]
    if not data:
        return _structured_result(False, action, error="No matching file move batch found.", entries=[])

    batch_id = data[-1]["batch_id"]
    entries = [entry for entry in data if entry.get("batch_id") == batch_id]
    lines = [f"- {Path(entry['original_path']).name} -> {entry['destination_path']}" for entry in entries]
    result = _structured_result(True, action, result="\n".join(lines), entries=entries, batch_id=batch_id)
    _log_action(action, True, f"batch={batch_id} count={len(entries)}")
    return result


def find_move_by_name(filename):
    action = "find_move_by_name"
    needle = str(filename).strip().lower()
    data = _load_store()
    matches = [
        entry for entry in data
        if Path(entry.get("original_path", "")).name.lower() == needle
        or Path(entry.get("destination_path", "")).name.lower() == needle
    ]
    if not matches:
        return _structured_result(False, action, error=f"No moved file found for: {filename}", entries=[])

    lines = [f"- {entry['original_path']} -> {entry['destination_path']}" for entry in matches[-10:]]
    result = _structured_result(True, action, result="\n".join(lines), entries=matches[-10:])
    _log_action(action, True, f"matches={len(matches)} filename={filename}")
    return result


def list_moves(scope=None, limit=20):
    action = "list_moves"
    data = _load_store()
    if scope:
        data = [entry for entry in data if entry.get("scope") == scope]
    if not data:
        return _structured_result(False, action, error="No file moves recorded.", entries=[])

    entries = data[-limit:]
    lines = [
        f"- [{entry['timestamp']}] {Path(entry['original_path']).name} -> {entry['destination_path']}"
        for entry in entries
    ]
    result = _structured_result(True, action, result="\n".join(lines), entries=entries)
    _log_action(action, True, f"listed={len(entries)} scope={scope or 'all'}")
    return result


def make_history_entries(scope, batch_id, moved_items):
    timestamp = datetime.now().isoformat(timespec="seconds")
    entries = []
    for item in moved_items:
        entries.append(
            {
                "original_path": item["source"],
                "destination_path": item["target"],
                "category": item["category"],
                "timestamp": timestamp,
                "batch_id": batch_id,
                "scope": scope,
            }
        )
    return entries
