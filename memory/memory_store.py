import json
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE / "memory"
STORE_FILE = MEMORY_DIR / "saved_notes.json"
RECENT_STORE_FILE = MEMORY_DIR / "recent_memory.json"
LOGS = BASE / "logs"
LOG_FILE = LOGS / "brain.log"
MAX_RECENT_ITEMS = 50


def _log_action(action, success, details):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] memory_store action={action} success={success} details={details}\n")
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


def _normalize_key(key):
    normalized = str(key).strip().lower()
    for prefix in ("my ", "the "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
    return normalized


def _load_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        STORE_FILE.write_text("{}", encoding="utf-8")
        return {}

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_store(data):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _default_recent_store():
    return {"actions": [], "commands": []}


def _load_recent_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not RECENT_STORE_FILE.exists():
        RECENT_STORE_FILE.write_text(json.dumps(_default_recent_store(), indent=2), encoding="utf-8")
        return _default_recent_store()

    try:
        with open(RECENT_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_recent_store()
        actions = data.get("actions", [])
        commands = data.get("commands", [])
        return {
            "actions": actions if isinstance(actions, list) else [],
            "commands": commands if isinstance(commands, list) else [],
        }
    except Exception:
        return _default_recent_store()


def _save_recent_store(data):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECENT_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _append_recent_entry(bucket, value):
    data = _load_recent_store()
    entries = list(data.get(bucket, []))
    entry = {
        "text": str(value).strip(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    entries.append(entry)
    data[bucket] = entries[-MAX_RECENT_ITEMS:]
    _save_recent_store(data)
    return entry, data


def _format_recent_entries(entries):
    if not entries:
        return ""
    return "\n".join(f"- [{item['timestamp']}] {item['text']}" for item in entries)


def save_note(key, value):
    action = "save_note"
    try:
        normalized_key = _normalize_key(key)
        if not normalized_key or not str(value).strip():
            result = _structured_result(False, action, error="Both note key and value are required.")
            _log_action(action, False, result["error"])
            return result

        data = _load_store()
        data[normalized_key] = str(value).strip()
        _save_store(data)
        result = _structured_result(True, action, result=f"Saved note '{normalized_key}': {data[normalized_key]}", notes=data)
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def get_note(key):
    action = "get_note"
    try:
        normalized_key = _normalize_key(key)
        data = _load_store()
        if normalized_key in data:
            result = _structured_result(True, action, result=f"{normalized_key}: {data[normalized_key]}", key=normalized_key, value=data[normalized_key])
            _log_action(action, True, result["result"])
            return result

        result = _structured_result(False, action, error=f"Note not found: {normalized_key}")
        _log_action(action, False, result["error"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def list_notes():
    action = "list_notes"
    try:
        data = _load_store()
        if not data:
            result = _structured_result(True, action, result="No saved notes yet.", notes={})
            _log_action(action, True, result["result"])
            return result

        lines = [f"- {key}: {value}" for key, value in sorted(data.items())]
        result = _structured_result(True, action, result="\n".join(lines), notes=data)
        _log_action(action, True, f"listed={len(data)}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def delete_note(key):
    action = "delete_note"
    try:
        normalized_key = _normalize_key(key)
        data = _load_store()
        if normalized_key not in data:
            result = _structured_result(False, action, error=f"Note not found: {normalized_key}")
            _log_action(action, False, result["error"])
            return result

        removed_value = data.pop(normalized_key)
        _save_store(data)
        result = _structured_result(True, action, result=f"Deleted note '{normalized_key}': {removed_value}", notes=data)
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def search_notes(query):
    action = "search_notes"
    try:
        normalized_query = _normalize_key(query)
        data = _load_store()
        matches = {
            key: value
            for key, value in data.items()
            if normalized_query in key or normalized_query in value.lower()
        }
        if not matches:
            result = _structured_result(False, action, error=f"No saved notes matched: {normalized_query}", notes={})
            _log_action(action, False, result["error"])
            return result

        lines = [f"- {key}: {value}" for key, value in sorted(matches.items())]
        result = _structured_result(True, action, result="\n".join(lines), notes=matches)
        _log_action(action, True, f"matches={len(matches)} query={normalized_query}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def log(action_text):
    action = "log"
    try:
        text = str(action_text).strip()
        if not text:
            result = _structured_result(False, action, error="Action text is required.")
            _log_action(action, False, result["error"])
            return result

        entry, data = _append_recent_entry("actions", text)
        result = _structured_result(
            True,
            action,
            result=f"Logged action: {entry['text']}",
            entry=entry,
            actions=data["actions"],
        )
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def log_command(command_text):
    action = "log_command"
    try:
        text = str(command_text).strip()
        if not text:
            result = _structured_result(False, action, error="Command text is required.")
            _log_action(action, False, result["error"])
            return result

        entry, data = _append_recent_entry("commands", text)
        result = _structured_result(
            True,
            action,
            result=f"Logged command: {entry['text']}",
            entry=entry,
            commands=data["commands"],
        )
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def get_recent_actions(limit=10):
    action = "get_recent_actions"
    try:
        data = _load_recent_store()
        count = max(0, int(limit))
        actions = data["actions"][-count:] if count else []
        result_text = _format_recent_entries(actions) if actions else "No recent actions."
        result = _structured_result(True, action, result=result_text, actions=actions)
        _log_action(action, True, f"count={len(actions)}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def get_recent_commands(limit=10):
    action = "get_recent_commands"
    try:
        data = _load_recent_store()
        count = max(0, int(limit))
        commands = data["commands"][-count:] if count else []
        result_text = _format_recent_entries(commands) if commands else "No recent commands."
        result = _structured_result(True, action, result=result_text, commands=commands)
        _log_action(action, True, f"count={len(commands)}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result
