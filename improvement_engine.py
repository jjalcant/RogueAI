"""Cluster friction events into ranked improvement candidates."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
from pathlib import Path

from improvement_storage import ImprovementStorage


class ImprovementEngine:
    EASE_BY_AREA = {
        "chat_rendering": 8,
        "chat_backend": 7,
        "backend_formatting": 7,
        "router": 6,
        "command_execution": 5,
        "task_execution": 5,
        "agent_loop": 4,
        "planner": 4,
        "architecture": 2,
    }

    EASE_BY_TRIGGER = {
        "user_correction": 1,
        "unhelpful_output": 1,
        "formatter_inconsistency": 1,
        "fallback_to_llm": 0,
        "execution_failure": -1,
        "verification_failure": -1,
        "repeated_retry": -1,
    }

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

    def build_candidates(self, limit: int | None = None):
        grouped = {}
        for event in self.storage.iter_jsonl(self.storage.event_log_path):
            key = self._cluster_key(event)
            bucket = grouped.setdefault(key, [])
            bucket.append(event)

        candidates = []
        for events in grouped.values():
            if not events:
                continue
            first = events[0]
            frequency = sum(max(1, int(item.get("frequency_hint", 1) or 1)) for item in events)
            event_count = len(events)
            impact = max(1, round(sum(int(item.get("impact", 1) or 1) for item in events) / event_count))
            ease = self.estimate_ease(first.get("area", ""), first.get("trigger", ""), first.get("symptom", ""))
            score = frequency * impact * ease
            candidates.append(
                {
                    "area": first.get("area", "general"),
                    "symptom": first.get("symptom", "unspecified friction"),
                    "trigger": first.get("trigger", "unknown"),
                    "frequency": frequency,
                    "event_count": event_count,
                    "impact": impact,
                    "ease": ease,
                    "score": score,
                    "examples": self._build_examples(events),
                    "status": "candidate",
                }
            )

        candidates.sort(key=lambda item: (-item["score"], -item["frequency"], -item["impact"], item["area"], item["symptom"]))
        for candidate in candidates:
            candidate["id"] = self._candidate_id(candidate)

        snapshot = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "event_count": sum(item["event_count"] for item in candidates),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        self.storage.write_json(self.storage.candidates_path, snapshot)
        if limit is None:
            return candidates
        return candidates[:limit]

    def build_dashboard_summary(self, limit: int = 5, candidates: list[dict] | None = None, recent_proposals: list[dict] | None = None):
        events = list(self.storage.iter_jsonl(self.storage.event_log_path))
        area_counts = Counter(str(event.get("area") or "general") for event in events)
        history = self.storage.read_json(self.storage.history_path, default={"proposals": []})
        proposals = recent_proposals if recent_proposals is not None else list(history.get("proposals", []))[-limit:]
        if candidates is None:
            candidates = self.build_candidates(limit=limit)
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "event_count": len(events),
            "top_candidates": candidates[:limit],
            "common_areas": [
                {"area": area, "count": count}
                for area, count in area_counts.most_common(limit)
            ],
            "recent_proposals": proposals[-limit:],
        }

    def estimate_ease(self, area: str, trigger: str, symptom: str):
        area_key = str(area or "").strip().lower()
        trigger_key = str(trigger or "").strip().lower()
        symptom_key = str(symptom or "").strip().lower()

        ease = self.EASE_BY_AREA.get(area_key, 5)
        ease += self.EASE_BY_TRIGGER.get(trigger_key, 0)

        if any(token in symptom_key for token in ("rewrite", "framework", "dependency", "migration", "architecture")):
            ease = min(ease, 2)
        if any(token in symptom_key for token in ("format", "wording", "message", "technical", "retry")):
            ease = max(ease, 7)
        return max(1, min(10, ease))

    def _cluster_key(self, event: dict):
        area = str(event.get("area") or "general").strip().lower()
        trigger = str(event.get("trigger") or "unknown").strip().lower()
        symptom = str(event.get("symptom") or "unspecified friction").strip().lower()
        return area, symptom, trigger

    def _build_examples(self, events: list[dict], limit: int = 3):
        examples = []
        for item in events[:limit]:
            examples.append(
                {
                    "timestamp": item.get("timestamp"),
                    "command": item.get("command", ""),
                    "symptom": item.get("symptom", ""),
                    "impact": item.get("impact", 1),
                    "trigger": item.get("trigger", ""),
                }
            )
        return examples

    def _candidate_id(self, candidate: dict):
        key = "|".join(
            [
                str(candidate.get("area") or "").strip().lower(),
                str(candidate.get("symptom") or "").strip().lower(),
                str(candidate.get("trigger") or "").strip().lower(),
            ]
        )
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        return f"imp_{digest}"
