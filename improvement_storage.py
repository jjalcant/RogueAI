"""Shared storage helpers for the RogueAI self-improvement layer."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import Lock


class ImprovementStorage:
    def __init__(
        self,
        memory_root: Path | str,
        event_log_path: Path | str | None = None,
        candidates_path: Path | str | None = None,
        history_path: Path | str | None = None,
        proposals_path: Path | str | None = None,
        approvals_path: Path | str | None = None,
        patch_results_path: Path | str | None = None,
        experiments_path: Path | str | None = None,
        backups_root: Path | str | None = None,
    ):
        self.memory_root = Path(memory_root)
        self.event_log_path = Path(event_log_path) if event_log_path is not None else self.memory_root / "improvement_log.jsonl"
        self.candidates_path = Path(candidates_path) if candidates_path is not None else self.memory_root / "improvement_candidates.json"
        self.history_path = Path(history_path) if history_path is not None else self.memory_root / "improvement_history.json"
        self.proposals_path = Path(proposals_path) if proposals_path is not None else self.memory_root / "improvement_proposals.json"
        self.approvals_path = Path(approvals_path) if approvals_path is not None else self.memory_root / "improvement_approvals.json"
        self.patch_results_path = Path(patch_results_path) if patch_results_path is not None else self.memory_root / "improvement_patch_results.json"
        self.experiments_path = Path(experiments_path) if experiments_path is not None else self.memory_root / "improvement_experiments.json"
        self.backups_root = Path(backups_root) if backups_root is not None else self.memory_root / "improvement_backups"
        self._lock = Lock()
        self.ensure_paths()

    def ensure_paths(self):
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.candidates_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.proposals_path.parent.mkdir(parents=True, exist_ok=True)
        self.approvals_path.parent.mkdir(parents=True, exist_ok=True)
        self.patch_results_path.parent.mkdir(parents=True, exist_ok=True)
        self.experiments_path.parent.mkdir(parents=True, exist_ok=True)
        self.backups_root.mkdir(parents=True, exist_ok=True)

    def append_jsonl(self, path: Path | str, payload: dict):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return payload

    def iter_jsonl(self, path: Path | str):
        target = Path(path)
        if not target.exists():
            return
        try:
            with open(target, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        yield payload
        except OSError:
            return

    def read_json(self, path: Path | str, default):
        target = Path(path)
        if not target.exists():
            return copy.deepcopy(default)
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return copy.deepcopy(default)

    def write_json(self, path: Path | str, payload):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(target.suffix + ".tmp")
        with self._lock:
            temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temp_path.replace(target)
        return payload

    def read_records(self, path: Path | str, key: str):
        payload = self.read_json(path, default={key: []})
        records = payload.get(key)
        if not isinstance(records, list):
            records = []
        return payload, records
