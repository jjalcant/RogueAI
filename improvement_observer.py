"""Append-only friction event observer for the RogueAI self-improvement layer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from improvement_storage import ImprovementStorage


def _coerce_int(value, default=1, minimum=1, maximum=10):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))


def _stringify_context(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


class ImprovementObserver:
    def __init__(
        self,
        memory_root: Path | str,
        event_log_path: Path | str | None = None,
        candidates_path: Path | str | None = None,
        history_path: Path | str | None = None,
    ):
        self.storage = ImprovementStorage(
            memory_root=memory_root,
            event_log_path=event_log_path,
            candidates_path=candidates_path,
            history_path=history_path,
        )

    def log_event(self, event: dict | None = None, **overrides):
        normalized = self.normalize_event(event, **overrides)
        try:
            return self.storage.append_jsonl(self.storage.event_log_path, normalized)
        except Exception:
            return None

    def normalize_event(self, event: dict | None = None, **overrides):
        base = {}
        metadata = {}

        if isinstance(event, dict):
            base.update(event)
        elif event is not None:
            metadata["observer_error"] = "malformed_event_payload"
            metadata["original_payload_type"] = type(event).__name__
            base.update(
                {
                    "area": "improvement_observer",
                    "trigger": "malformed_event",
                    "symptom": "invalid event payload",
                    "raw_context": _stringify_context(event),
                }
            )

        base.update(overrides)

        original_metadata = base.get("metadata")
        if isinstance(original_metadata, dict):
            metadata.update(original_metadata)
        elif original_metadata is not None:
            metadata["metadata_value"] = _stringify_context(original_metadata)

        allowed_fields = {
            "timestamp",
            "area",
            "trigger",
            "command",
            "symptom",
            "impact",
            "frequency_hint",
            "raw_context",
            "metadata",
        }
        extra_fields = {key: value for key, value in base.items() if key not in allowed_fields}
        if extra_fields:
            metadata["extra_fields"] = extra_fields

        return {
            "timestamp": str(base.get("timestamp") or datetime.now().isoformat(timespec="seconds")),
            "area": str(base.get("area") or "general").strip() or "general",
            "trigger": str(base.get("trigger") or "unknown").strip() or "unknown",
            "command": str(base.get("command") or "").strip(),
            "symptom": str(base.get("symptom") or "unspecified friction").strip() or "unspecified friction",
            "impact": _coerce_int(base.get("impact"), default=1, minimum=1, maximum=10),
            "frequency_hint": _coerce_int(base.get("frequency_hint"), default=1, minimum=1, maximum=100),
            "raw_context": _stringify_context(base.get("raw_context")),
            "metadata": metadata,
        }

    def read_events(self):
        return list(self.storage.iter_jsonl(self.storage.event_log_path))

    def count_events(self):
        return sum(1 for _ in self.storage.iter_jsonl(self.storage.event_log_path))
