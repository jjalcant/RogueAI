"""Structured execution logging for the Rogue agent loop."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class ExecutionLogger:
    def __init__(self, log_file: Path):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **details):
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "details": details,
        }
        with open(self.log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload
