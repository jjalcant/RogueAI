"""Minimal A/B tracking for low-risk RogueAI improvement experiments."""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

from improvement_storage import ImprovementStorage


class ImprovementExperiments:
    def __init__(self, memory_root: Path | str):
        self.storage = ImprovementStorage(memory_root=memory_root)

    def register_experiment(
        self,
        experiment_id: str,
        variant_a: dict,
        variant_b: dict,
        metric_directions: dict | None = None,
        auto_ship: bool = False,
    ):
        state, experiments = self.storage.read_records(self.storage.experiments_path, "experiments")
        experiment_map = {str(item.get("id")): item for item in experiments if item.get("id")}
        now = self._timestamp()
        payload = experiment_map.get(experiment_id, self._default_experiment(experiment_id))
        payload.update(
            {
                "id": experiment_id,
                "updated_at": now,
                "auto_ship": bool(auto_ship),
                "metric_directions": metric_directions if isinstance(metric_directions, dict) else {},
                "variants": {
                    "A": self._normalize_variant(variant_a, existing=payload.get("variants", {}).get("A")),
                    "B": self._normalize_variant(variant_b, existing=payload.get("variants", {}).get("B")),
                },
            }
        )
        experiment_map[experiment_id] = payload
        state["updated_at"] = now
        state["experiments"] = self._sorted_experiments(list(experiment_map.values()))
        self.storage.write_json(self.storage.experiments_path, state)
        return copy.deepcopy(payload)

    def record_usage(self, experiment_id: str, variant: str, metrics: dict | None = None):
        state, experiments = self.storage.read_records(self.storage.experiments_path, "experiments")
        experiment_map = {str(item.get("id")): item for item in experiments if item.get("id")}
        payload = experiment_map.get(experiment_id)
        if payload is None:
            return None

        variant_key = str(variant).upper()
        if variant_key not in {"A", "B"}:
            return None

        variant_payload = payload.setdefault("variants", {}).setdefault(variant_key, self._normalize_variant({}))
        variant_payload["usage_count"] = int(variant_payload.get("usage_count", 0) or 0) + 1
        for metric_name, metric_value in (metrics or {}).items():
            if not isinstance(metric_value, (int, float)):
                continue
            metric_payload = variant_payload.setdefault("metrics", {}).setdefault(metric_name, {"total": 0.0, "count": 0, "average": 0.0})
            metric_payload["total"] = float(metric_payload.get("total", 0.0) or 0.0) + float(metric_value)
            metric_payload["count"] = int(metric_payload.get("count", 0) or 0) + 1
            metric_payload["average"] = round(metric_payload["total"] / metric_payload["count"], 4)

        payload["updated_at"] = self._timestamp()
        experiment_map[experiment_id] = payload
        state["updated_at"] = payload["updated_at"]
        state["experiments"] = self._sorted_experiments(list(experiment_map.values()))
        self.storage.write_json(self.storage.experiments_path, state)
        return copy.deepcopy(payload)

    def select_winner(self, experiment_id: str, primary_metric: str | None = None, min_samples: int = 1):
        experiment = self.get_experiment(experiment_id)
        if experiment is None:
            return None

        metric_name = primary_metric or self._first_metric_name(experiment)
        if not metric_name:
            return None

        direction = str((experiment.get("metric_directions") or {}).get(metric_name, "higher_is_better"))
        variant_a = experiment.get("variants", {}).get("A", {})
        variant_b = experiment.get("variants", {}).get("B", {})
        metric_a = (variant_a.get("metrics") or {}).get(metric_name, {})
        metric_b = (variant_b.get("metrics") or {}).get(metric_name, {})

        if int(metric_a.get("count", 0) or 0) < min_samples or int(metric_b.get("count", 0) or 0) < min_samples:
            return None

        average_a = float(metric_a.get("average", 0.0) or 0.0)
        average_b = float(metric_b.get("average", 0.0) or 0.0)
        if average_a == average_b:
            winner = None
        elif direction == "lower_is_better":
            winner = "A" if average_a < average_b else "B"
        else:
            winner = "A" if average_a > average_b else "B"

        state, experiments = self.storage.read_records(self.storage.experiments_path, "experiments")
        experiment_map = {str(item.get("id")): item for item in experiments if item.get("id")}
        stored = experiment_map.get(experiment_id)
        if stored is None:
            return None
        stored["winner"] = {
            "variant": winner,
            "metric": metric_name,
            "direction": direction,
            "evaluated_at": self._timestamp(),
        }
        stored["updated_at"] = stored["winner"]["evaluated_at"]
        experiment_map[experiment_id] = stored
        state["updated_at"] = stored["updated_at"]
        state["experiments"] = self._sorted_experiments(list(experiment_map.values()))
        self.storage.write_json(self.storage.experiments_path, state)
        return copy.deepcopy(stored["winner"])

    def summarize_experiments(self, limit: int = 5):
        _, experiments = self.storage.read_records(self.storage.experiments_path, "experiments")
        summaries = []
        for experiment in self._sorted_experiments(experiments)[:limit]:
            summaries.append(
                {
                    "id": experiment.get("id"),
                    "updated_at": experiment.get("updated_at"),
                    "winner": experiment.get("winner"),
                    "auto_ship": bool(experiment.get("auto_ship")),
                    "variants": {
                        key: {
                            "label": value.get("label"),
                            "usage_count": value.get("usage_count", 0),
                            "metrics": value.get("metrics", {}),
                        }
                        for key, value in (experiment.get("variants") or {}).items()
                    },
                }
            )
        return summaries

    def get_experiment(self, experiment_id: str):
        _, experiments = self.storage.read_records(self.storage.experiments_path, "experiments")
        for experiment in experiments:
            if experiment.get("id") == experiment_id:
                return copy.deepcopy(experiment)
        return None

    def _normalize_variant(self, payload: dict, existing: dict | None = None):
        current = copy.deepcopy(existing) if isinstance(existing, dict) else {}
        current.update(payload if isinstance(payload, dict) else {})
        current["label"] = str(current.get("label") or "variant")
        current["description"] = str(current.get("description") or "")
        current["usage_count"] = int(current.get("usage_count", 0) or 0)
        metrics = current.get("metrics") if isinstance(current.get("metrics"), dict) else {}
        normalized_metrics = {}
        for name, value in metrics.items():
            if not isinstance(value, dict):
                continue
            total = float(value.get("total", 0.0) or 0.0)
            count = int(value.get("count", 0) or 0)
            average = round(total / count, 4) if count else 0.0
            normalized_metrics[name] = {"total": total, "count": count, "average": average}
        current["metrics"] = normalized_metrics
        return current

    def _default_experiment(self, experiment_id: str):
        return {
            "id": experiment_id,
            "created_at": self._timestamp(),
            "updated_at": self._timestamp(),
            "auto_ship": False,
            "metric_directions": {},
            "winner": None,
            "variants": {
                "A": self._normalize_variant({}),
                "B": self._normalize_variant({}),
            },
        }

    def _first_metric_name(self, experiment: dict):
        for variant in ("A", "B"):
            metrics = (experiment.get("variants", {}).get(variant, {}) or {}).get("metrics") or {}
            for name in metrics:
                return name
        return ""

    def _sorted_experiments(self, experiments: list[dict]):
        return sorted(experiments, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def _timestamp(self):
        return datetime.now().isoformat(timespec="seconds")
