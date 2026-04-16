"""Schema-separated memory manager for RogueAI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class MemoryManager:
    def __init__(self, memory_root: Path, session_memory: list | None = None):
        self.memory_root = Path(memory_root)
        self.memory_root.mkdir(parents=True, exist_ok=True)

        self.session_dir = self.memory_root / "session"
        self.tasks_dir = self.memory_root / "tasks"
        self.projects_dir = self.memory_root / "projects"
        self.preferences_dir = self.memory_root / "preferences"

        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_dir.mkdir(parents=True, exist_ok=True)

        self.session_file = self.session_dir / "current_session.json"
        self.preferences_file = self.preferences_dir / "agent_preferences.json"

        self._ensure_session_store()
        self._ensure_preference_store()

        self.session_memory = self._load_session_entries()
        for item in session_memory or []:
            normalized = self._normalize_session_item(item)
            if normalized:
                self.session_memory.append(normalized)
        if session_memory:
            self._save_session_entries(self.session_memory)

    def append_session(self, role: str, content: str, namespace: str = "execution"):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "role": role,
            "content": content,
            "namespace": namespace,
        }
        self.session_memory.append(entry)
        self._save_session_entries(self.session_memory)
        return entry

    def get_recent_session(self, limit: int = 6):
        return self.session_memory[-limit:]

    def clear_session(self):
        self.session_memory = []
        self._save_session_entries([])

    def save_project_fact(self, project_name: str, key: str, value):
        payload = self._load_project_payload(project_name)
        payload.setdefault("facts", {})[str(key).strip()] = value
        payload["updated_at"] = self._timestamp()
        self._save_project_payload(project_name, payload)
        return payload["facts"][str(key).strip()]

    def save_project_inspection(self, project_name: str, inspection: dict):
        payload = self._load_project_payload(project_name)
        payload["inspection"] = inspection
        payload["updated_at"] = self._timestamp()
        self._save_project_payload(project_name, payload)
        return payload["inspection"]

    def get_project_memory(self, project_name: str):
        return self._load_project_payload(project_name)

    def list_project_memories(self):
        payloads = []
        for path in sorted(self.projects_dir.glob("*.json"), key=lambda item: item.name.lower()):
            try:
                payloads.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return payloads

    def set_preference(self, key: str, value):
        payload = self._load_preferences()
        payload[str(key).strip()] = value
        self._save_preferences(payload)
        return payload[str(key).strip()]

    def get_preference(self, key: str, default=None):
        return self._load_preferences().get(str(key).strip(), default)

    def get_preferences(self):
        return self._load_preferences()

    def _ensure_session_store(self):
        if not self.session_file.exists():
            self.session_file.write_text(json.dumps({"entries": []}, indent=2), encoding="utf-8")

    def _ensure_preference_store(self):
        if self.preferences_file.exists():
            return

        from tools.system_tool import FOLDER_ALIASES

        payload = {
            "safe_folder_aliases": sorted(FOLDER_ALIASES.keys()),
            "behavior_flags": {
                "agent_read_only": True,
                "allow_destructive_actions": False,
            },
            "defaults": {},
        }
        self._save_preferences(payload)

    def _load_session_entries(self):
        try:
            payload = json.loads(self.session_file.read_text(encoding="utf-8"))
            entries = payload.get("entries", [])
            return entries if isinstance(entries, list) else []
        except Exception:
            return []

    def _save_session_entries(self, entries: list):
        payload = {
            "updated_at": self._timestamp(),
            "entries": entries,
        }
        self.session_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_preferences(self):
        try:
            return json.loads(self.preferences_file.read_text(encoding="utf-8"))
        except Exception:
            return {"safe_folder_aliases": [], "behavior_flags": {"agent_read_only": True, "allow_destructive_actions": False}, "defaults": {}}

    def _save_preferences(self, payload: dict):
        self.preferences_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _project_file(self, project_name: str):
        return self.projects_dir / f"{self._slugify(project_name)}.json"

    def _load_project_payload(self, project_name: str):
        path = self._project_file(project_name)
        if not path.exists():
            return {
                "project_name": project_name,
                "updated_at": self._timestamp(),
                "facts": {},
                "inspection": {},
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "project_name": project_name,
                "updated_at": self._timestamp(),
                "facts": {},
                "inspection": {},
            }

    def _save_project_payload(self, project_name: str, payload: dict):
        path = self._project_file(project_name)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _normalize_session_item(self, item):
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if role is None or content is None:
            return None
        return {
            "timestamp": item.get("timestamp", self._timestamp()),
            "role": role,
            "content": content,
            "namespace": item.get("namespace", "conversation"),
        }

    def _slugify(self, value: str):
        normalized = str(value).strip().lower().replace(" ", "_")
        filtered = [ch for ch in normalized if ch.isalnum() or ch in {"_", "-"}]
        return "".join(filtered) or "default"

    def _timestamp(self):
        return datetime.now().isoformat(timespec="seconds")
