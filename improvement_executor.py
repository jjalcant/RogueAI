"""Controlled execution of narrow, approved RogueAI improvement patches."""

from __future__ import annotations

import copy
import difflib
import json
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from improvement_guard import ImprovementGuard
from improvement_storage import ImprovementStorage


class ImprovementExecutor:
    SUPPORTED_OPERATIONS = {"replace_text", "append_text", "insert_after", "json_update"}

    def __init__(
        self,
        project_root: Path | str,
        memory_root: Path | str,
        guard: ImprovementGuard | None = None,
        approval_queue=None,
        execution_enabled: bool = True,
    ):
        self.project_root = Path(project_root).resolve()
        self.storage = ImprovementStorage(memory_root=memory_root)
        self.guard = guard or ImprovementGuard(self.project_root)
        self.approval_queue = approval_queue
        self.execution_enabled = bool(execution_enabled)

    def execute_proposal(self, proposal: dict, dry_run: bool = False):
        result = {
            "proposal_id": str(proposal.get("id") or ""),
            "status": "blocked",
            "files_touched": [],
            "backup_paths": [],
            "diff_summary": [],
            "validation_passed": False,
            "rollback_performed": False,
            "notes": [],
        }
        proposal = copy.deepcopy(proposal)

        if not self.execution_enabled:
            result["notes"].append("Improvement execution mode is disabled.")
            return self._record_result(result)

        if proposal.get("status") != "approved":
            result["notes"].append("Proposal must be approved before execution.")
            return self._record_result(result)

        safety = proposal.get("safety") or self.guard.evaluate_proposal_safety(proposal)
        if not safety.get("execution_allowed"):
            result["notes"].append("Proposal is not allowlisted for controlled execution.")
            result["notes"].extend(list(safety.get("reasons") or []))
            return self._record_result(result)

        patch_plan = proposal.get("patch_plan") or {}
        operations = patch_plan.get("operations") or []
        if not operations:
            result["notes"].append("Proposal does not contain structured patch operations.")
            return self._record_result(result)

        prepared = self._prepare_operations(proposal, operations, result)
        if not prepared:
            result["notes"].append("Patch plan produced no effective file changes.")
            return self._record_result(result)

        result["files_touched"] = [str(item["relative_path"]) for item in prepared]
        result["diff_summary"] = [item["diff"] for item in prepared]

        if dry_run:
            validation = self._validate_prepared_changes(prepared, proposal, dry_run=True)
            result["status"] = "dry_run"
            result["validation_passed"] = validation["passed"]
            result["notes"].extend(validation["notes"])
            return self._record_result(result)

        backups = self._create_backups(proposal.get("id") or "proposal", prepared)
        result["backup_paths"] = backups
        self._write_prepared_changes(prepared)

        validation = self._validate_prepared_changes(prepared, proposal, dry_run=False)
        result["validation_passed"] = validation["passed"]
        result["notes"].extend(validation["notes"])
        if validation["passed"]:
            result["status"] = "executed"
            if self.approval_queue is not None:
                self.approval_queue.mark_executed(result["proposal_id"])
            return self._record_result(result)

        self._rollback(prepared, backups)
        result["status"] = "rolled_back"
        result["rollback_performed"] = True
        if self.approval_queue is not None:
            self.approval_queue.mark_rolled_back(result["proposal_id"], "Rolled back after failed validation.")
        return self._record_result(result)

    def list_recent_results(self, limit: int = 5, status: str | None = None):
        _, results = self.storage.read_records(self.storage.patch_results_path, "results")
        ordered = list(reversed(results))
        if status:
            ordered = [item for item in ordered if item.get("status") == status]
        return ordered[:limit]

    def build_metrics_summary(self):
        _, results = self.storage.read_records(self.storage.patch_results_path, "results")
        summary = {
            "executed": 0,
            "rolled_back": 0,
            "blocked": 0,
            "dry_run": 0,
            "validation_failures": 0,
            "known_metric_deltas": [],
            "unknown_metrics": True,
        }
        for item in results:
            status = str(item.get("status") or "")
            if status in summary:
                summary[status] += 1
            if status == "rolled_back" and not item.get("validation_passed"):
                summary["validation_failures"] += 1
        return summary

    def _prepare_operations(self, proposal: dict, operations: list[dict], result: dict):
        prepared_by_path = {}
        proposal_files = {str(path) for path in proposal.get("files") or []}
        for operation in operations:
            op_type = str(operation.get("op") or operation.get("type") or "").strip().lower()
            if op_type not in self.SUPPORTED_OPERATIONS:
                result["notes"].append(f"Unsupported patch operation: {op_type or 'missing'}")
                return []

            relative_path = str(operation.get("path") or operation.get("file") or "").strip()
            if not relative_path:
                result["notes"].append("Patch operation is missing a target path.")
                return []
            if proposal_files and relative_path not in proposal_files:
                result["notes"].append(f"Patch operation targets {relative_path} outside the declared proposal scope.")
                return []

            absolute_path = self._resolve_project_path(relative_path)
            if not self._is_within_project(absolute_path):
                result["notes"].append(f"Patch operation targets a file outside the project: {relative_path}")
                return []

            current = prepared_by_path.get(
                relative_path,
                {
                    "relative_path": relative_path,
                    "absolute_path": absolute_path,
                    "original_exists": absolute_path.exists(),
                    "original_text": self._read_text(absolute_path),
                    "updated_text": self._read_text(absolute_path),
                },
            )
            try:
                next_text = self._apply_operation(current["updated_text"], operation, absolute_path)
            except ValueError as exc:
                result["notes"].append(str(exc))
                return []
            current["updated_text"] = next_text
            prepared_by_path[relative_path] = current

        prepared = []
        for item in prepared_by_path.values():
            if item["updated_text"] == item["original_text"]:
                continue
            item["diff"] = self._diff_summary(item["relative_path"], item["original_text"], item["updated_text"])
            prepared.append(item)
        return prepared

    def _apply_operation(self, current_text: str, operation: dict, absolute_path: Path):
        op_type = str(operation.get("op") or operation.get("type") or "").strip().lower()
        if op_type == "replace_text":
            old = str(operation.get("old") or "")
            new = str(operation.get("new") or "")
            if old not in current_text:
                raise ValueError(f"replace_text anchor not found in {absolute_path}")
            count = int(operation.get("count", 1) or 1)
            return current_text.replace(old, new, count)

        if op_type == "append_text":
            text = str(operation.get("text") or "")
            return current_text + text

        if op_type == "insert_after":
            anchor = str(operation.get("anchor") or "")
            text = str(operation.get("text") or "")
            if anchor not in current_text:
                raise ValueError(f"insert_after anchor not found in {absolute_path}")
            return current_text.replace(anchor, anchor + text, 1)

        if op_type == "json_update":
            payload = json.loads(current_text or "{}")
            if not isinstance(payload, dict):
                raise ValueError(f"json_update requires a JSON object in {absolute_path}")
            updates = operation.get("updates") or {}
            if not isinstance(updates, dict):
                raise ValueError(f"json_update requires a mapping of updates for {absolute_path}")
            payload.update(updates)
            return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        raise ValueError(f"Unsupported patch operation: {op_type}")

    def _create_backups(self, proposal_id: str, prepared: list[dict]):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = self.storage.backups_root / str(proposal_id) / timestamp
        paths = []
        for item in prepared:
            target = backup_root / str(item["relative_path"]).replace("/", "__").replace("\\", "__")
            target.parent.mkdir(parents=True, exist_ok=True)
            if item["absolute_path"].exists():
                shutil.copy2(item["absolute_path"], target)
            else:
                target.write_text("", encoding="utf-8")
            paths.append(str(target))
        return paths

    def _write_prepared_changes(self, prepared: list[dict]):
        for item in prepared:
            path = item["absolute_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item["updated_text"], encoding="utf-8")

    def _validate_prepared_changes(self, prepared: list[dict], proposal: dict, dry_run: bool):
        notes = []
        validation_plan = proposal.get("validation_plan") or (proposal.get("patch_plan") or {}).get("validation") or {}

        for item in prepared:
            if item["absolute_path"].suffix == ".py":
                try:
                    compile(item["updated_text"], str(item["absolute_path"]), "exec")
                except SyntaxError as exc:
                    return {"passed": False, "notes": [f"Syntax validation failed for {item['relative_path']}: {exc.msg}"]}

        if dry_run:
            notes.append("Dry-run skipped filesystem writes and external validation commands.")
            return {"passed": True, "notes": notes}

        python_files = [self._resolve_project_path(path) for path in validation_plan.get("python_files") or []]
        if python_files:
            try:
                for path in python_files:
                    if path.exists():
                        py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                return {"passed": False, "notes": [f"py_compile validation failed: {exc.msg}"]}

        for module_name in validation_plan.get("imports") or []:
            command = [sys.executable, "-c", f"import importlib; importlib.import_module({module_name!r})"]
            completed = subprocess.run(command, cwd=self.project_root, capture_output=True, text=True)
            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or "").strip()
                return {"passed": False, "notes": [f"Import validation failed for {module_name}: {error}"]}

        tests = validation_plan.get("tests") or []
        if tests:
            command = [sys.executable, "-m", "unittest", *tests]
            completed = subprocess.run(command, cwd=self.project_root, capture_output=True, text=True)
            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or "").strip()
                return {"passed": False, "notes": [f"Targeted tests failed: {error}"]}
            notes.append(f"Targeted validation passed: {' '.join(tests)}")
        else:
            notes.append("No targeted test module was defined for this patch.")

        return {"passed": True, "notes": notes}

    def _rollback(self, prepared: list[dict], backups: list[str]):
        for item, backup in zip(prepared, backups):
            if not item.get("original_exists"):
                if item["absolute_path"].exists():
                    item["absolute_path"].unlink()
                continue
            backup_path = Path(backup)
            if backup_path.exists():
                item["absolute_path"].write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")

    def _record_result(self, result: dict):
        state, results = self.storage.read_records(self.storage.patch_results_path, "results")
        payload = copy.deepcopy(result)
        payload["recorded_at"] = datetime.now().isoformat(timespec="seconds")
        results.append(payload)
        state["updated_at"] = payload["recorded_at"]
        state["results"] = results[-100:]
        self.storage.write_json(self.storage.patch_results_path, state)
        return payload

    def _diff_summary(self, relative_path: str, before: str, after: str):
        diff_lines = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=relative_path,
                tofile=relative_path,
                lineterm="",
            )
        )
        changed_preview = [line for line in diff_lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))][:6]
        return {
            "path": relative_path,
            "changed_lines": len(changed_preview),
            "preview": changed_preview,
        }

    def _read_text(self, path: Path):
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _resolve_project_path(self, relative_path: str):
        return (self.project_root / relative_path).resolve()

    def _is_within_project(self, path: Path):
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False
