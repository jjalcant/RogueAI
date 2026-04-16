"""Convert ranked improvement candidates into small, execution-ready proposals."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from improvement_storage import ImprovementStorage


class ImprovementPlanner:
    AREA_FILE_HINTS = {
        "chat_rendering": ["rogue_app.py", "result_contract.py"],
        "chat_backend": ["rogue_app.py", "brain/router.py"],
        "backend_formatting": ["rogue_app.py", "result_contract.py"],
        "router": ["brain/router.py"],
        "command_execution": ["tool_registry.py"],
        "task_execution": ["agent_loop.py", "tool_registry.py"],
        "agent_loop": ["agent_loop.py", "task_manager.py"],
        "planner": ["planner.py"],
    }
    PATCH_CATEGORY_BY_AREA = {
        "chat_rendering": "text_update",
        "chat_backend": "normalization_fix",
        "backend_formatting": "normalization_fix",
        "router": "guard_clause",
        "command_execution": "guard_clause",
        "task_execution": "guard_clause",
        "agent_loop": "guard_clause",
        "planner": "wrapper_addition",
    }
    STRATEGY_BY_CATEGORY = {
        "normalization_fix": "replace_text",
        "wrapper_addition": "insert_after",
        "guard_clause": "insert_after",
        "text_update": "replace_text",
        "config_update": "json_update",
        "test_addition": "append_text",
    }
    STRATEGY_CONFIDENCE = {
        "normalization_fix": 13,
        "wrapper_addition": 11,
        "guard_clause": 14,
        "text_update": 12,
        "config_update": 9,
        "test_addition": 10,
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

    def build_proposals(self, candidates: list[dict], min_score: int = 20, limit: int = 5):
        proposals = []
        for candidate in candidates:
            if candidate.get("score", 0) < min_score:
                continue
            proposals.append(self._proposal_from_candidate(candidate))
            if len(proposals) >= limit:
                break

        history = self.storage.read_json(self.storage.history_path, default={"runs": [], "proposals": []})
        history["updated_at"] = datetime.now().isoformat(timespec="seconds")
        history["proposals"] = proposals
        history.setdefault("runs", []).append(
            {
                "timestamp": history["updated_at"],
                "candidate_ids": [item.get("id") for item in candidates[:limit]],
                "proposal_ids": [item.get("id") for item in proposals],
            }
        )
        history["runs"] = history["runs"][-25:]
        self.storage.write_json(self.storage.history_path, history)
        return proposals

    def _proposal_from_candidate(self, candidate: dict):
        area = str(candidate.get("area") or "general")
        area_label = area.replace("_", " ")
        symptom = str(candidate.get("symptom") or "unspecified friction")
        trigger = str(candidate.get("trigger") or "unknown")
        files = list(self.AREA_FILE_HINTS.get(area, [f"{area}.py" if "." not in area else area]))
        risk = self._risk_from_candidate(candidate, files)
        patch_category = self._patch_category_for_candidate(area, symptom, trigger)
        patch_strategy = self.STRATEGY_BY_CATEGORY.get(patch_category, "replace_text")
        validation_plan = self._validation_plan(files, patch_category)
        confidence = self._confidence_for_candidate(candidate, files, risk, patch_category, validation_plan)

        return {
            "id": candidate.get("id"),
            "title": self._title_for_candidate(area, symptom, trigger),
            "problem": f"Repeated friction in {area_label} is being observed as '{symptom}' via {trigger}.",
            "why": (
                f"This candidate was logged {candidate.get('frequency', 1)} times with impact {candidate.get('impact', 1)} "
                f"and ease {candidate.get('ease', 1)}, producing score {candidate.get('score', 0)}."
            ),
            "scope": f"Apply a small, local fix in {area_label} without changing the wider Rogue architecture.",
            "risk": risk,
            "files": files,
            "patch_category": patch_category,
            "patch_strategy": patch_strategy,
            "confidence": confidence,
            "acceptance_criteria": [
                f"The {area_label} flow handles '{symptom}' more deterministically.",
                "A focused regression test covers the observed failure or correction case.",
                "The change stays local and does not require framework or dependency changes.",
            ],
            "recommended_action": self._recommended_action(area, symptom, files),
            "validation_plan": validation_plan,
            "measurement_plan": self._measurement_plan(area, patch_category),
            "patch_plan": {
                "category": patch_category,
                "strategy": patch_strategy,
                "files": files,
                "operations": [],
                "validation": validation_plan,
                "notes": [
                    "Planner output is proposal-only until a narrow structured patch plan is attached.",
                    "Execution remains approval-gated and reversible.",
                ],
            },
            "status": "proposed",
        }

    def _title_for_candidate(self, area: str, symptom: str, trigger: str):
        symptom_lower = symptom.lower()
        if area == "chat_rendering" and "technical" in symptom_lower:
            return "Simplify chat output formatting"
        if area == "command_execution":
            return "Harden command execution failure handling"
        if area == "agent_loop" and trigger == "repeated_retry":
            return "Tighten repeated retry handling"
        prefix = area.replace("_", " ").title()
        return f"{prefix}: {symptom[:60].capitalize()}"

    def _recommended_action(self, area: str, symptom: str, files: list[str]):
        primary_file = files[0] if files else "the affected module"
        if area in {"chat_rendering", "backend_formatting", "chat_backend"}:
            return f"Add a small response-normalization or wording guard in {primary_file} to address '{symptom}'."
        if area == "command_execution":
            return f"Add a narrow validation or failure-normalization step in {primary_file} for '{symptom}'."
        if area == "agent_loop":
            return f"Adjust retry or verification handling in {primary_file} so '{symptom}' produces clearer outcomes."
        return f"Implement a local fix in {primary_file} for '{symptom}' before considering broader changes."

    def _risk_from_candidate(self, candidate: dict, files: list[str]):
        ease = int(candidate.get("ease", 1) or 1)
        if len(files) > 3 or ease <= 3:
            return "high"
        if ease <= 6:
            return "medium"
        return "low"

    def _patch_category_for_candidate(self, area: str, symptom: str, trigger: str):
        symptom_key = symptom.lower()
        if "config" in symptom_key:
            return "config_update"
        if "test" in symptom_key or trigger == "verification_failure":
            return "test_addition"
        if any(token in symptom_key for token in ("technical", "wording", "message", "summary", "format")):
            return "text_update"
        return self.PATCH_CATEGORY_BY_AREA.get(area, "normalization_fix")

    def _validation_plan(self, files: list[str], patch_category: str):
        python_files = [path for path in files if str(path).endswith(".py")]
        imports = [self._module_name_from_path(path) for path in python_files[:2]]
        tests = []
        if patch_category in {"guard_clause", "normalization_fix", "test_addition", "text_update"}:
            tests.append("tests.test_improvement_layer")
        return {
            "python_files": python_files,
            "imports": [name for name in imports if name],
            "tests": tests,
        }

    def _measurement_plan(self, area: str, patch_category: str):
        metrics = []
        if area in {"agent_loop", "task_execution"}:
            metrics.append("retry_reduction")
        if area in {"chat_rendering", "backend_formatting", "chat_backend"}:
            metrics.extend(["user_corrections", "fallback_responses"])
        if area == "command_execution":
            metrics.extend(["formatter_failures", "command_success_rate"])
        if patch_category == "test_addition":
            metrics.append("validation_coverage")
        deduped = []
        for metric in metrics:
            if metric not in deduped:
                deduped.append(metric)
        return {
            "metrics": deduped,
            "before": {},
            "after": {},
            "notes": ["Metrics remain unknown until explicit before/after evidence is recorded."],
        }

    def _confidence_for_candidate(
        self,
        candidate: dict,
        files: list[str],
        risk: str,
        patch_category: str,
        validation_plan: dict,
    ):
        frequency = int(candidate.get("frequency", 1) or 1)
        event_count = int(candidate.get("event_count", frequency) or frequency)
        factors = {
            "event_frequency": min(24, frequency * 4),
            "issue_consistency": min(14, event_count * 3),
            "scope_tightness": max(2, 14 - ((len(files) - 1) * 5)),
            "risk_level": {"low": 16, "medium": 4, "high": -12}.get(risk, 0),
            "file_count": max(1, 8 - ((len(files) - 1) * 3)),
            "patch_strategy_type": self.STRATEGY_CONFIDENCE.get(patch_category, 6),
            "validation_availability": 10 if (validation_plan.get("python_files") or validation_plan.get("tests")) else 2,
        }
        score = max(0, min(100, sum(factors.values())))
        if score >= 75:
            level = "high"
        elif score >= 50:
            level = "medium"
        else:
            level = "low"
        notes = [
            f"Confidence is {level} because the issue appears {frequency} times across {event_count} clustered events.",
            f"Planned scope is {len(files)} file(s) with {risk} estimated risk and {patch_category} strategy.",
        ]
        return {
            "score": score,
            "level": level,
            "factors": factors,
            "notes": notes,
        }

    def _module_name_from_path(self, path: str):
        text = str(path or "").strip().replace("\\", "/")
        if not text.endswith(".py"):
            return ""
        return text[:-3].replace("/", ".")
