"""Safety evaluation for future proposal-driven self-improvement work."""

from __future__ import annotations

from pathlib import Path


class ImprovementGuard:
    ALLOWLISTED_EXECUTION_CATEGORIES = {
        "normalization_fix",
        "wrapper_addition",
        "guard_clause",
        "text_update",
        "config_update",
        "test_addition",
    }
    BLOCKED_EXECUTION_CATEGORIES = {
        "dependency_change",
        "framework_change",
        "large_refactor",
        "security_sensitive_change",
        "file_move",
        "command_generation",
        "unrestricted_code_synthesis",
        "ui_rewrite",
    }
    BLOCKED_FILE_MARKERS = (
        ".env",
        "secret",
        "token",
        "credential",
        "password",
        "id_rsa",
        ".pem",
        ".key",
        ".pfx",
    )
    BLOCKED_CHANGE_FILES = {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "poetry.lock",
        "pipfile",
        "pipfile.lock",
    }
    BROAD_CHANGE_MARKERS = (
        "rewrite",
        "rebuild",
        "massive refactor",
        "framework",
        "dependency",
        "migration",
        "overhaul",
        "self-edit the whole codebase",
        "autonomous unrestricted",
    )

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()

    def evaluate_proposal_safety(self, proposal: dict):
        reasons = []
        notes = ["Evaluation remains conservative. No proposal is executed automatically without approval."]
        blocked_files = []
        patch_plan = proposal.get("patch_plan") or {}
        files = proposal.get("files") or patch_plan.get("files") or []
        category = str(proposal.get("patch_category") or patch_plan.get("category") or "").strip().lower()
        operations = patch_plan.get("operations") or []
        allowed = True
        execution_allowed = False

        if not files:
            allowed = False
            reasons.append("Proposal did not define an explicit file scope.")

        if len(files) > 4:
            allowed = False
            reasons.append("Proposal touches too many files for a safe minimal fix.")

        for raw_file in files:
            normalized = str(raw_file or "").strip()
            if not normalized:
                continue
            resolved = self._resolve_candidate_path(normalized)
            if not self._is_within_project(resolved):
                allowed = False
                blocked_files.append(normalized)
                reasons.append("Proposal references files outside the approved RogueAI workspace.")
                continue

            lowered = normalized.lower()
            filename = Path(normalized).name.lower()
            if any(marker in lowered for marker in self.BLOCKED_FILE_MARKERS):
                allowed = False
                blocked_files.append(normalized)
                reasons.append("Proposal touches credentials or security-sensitive files.")
            if filename in self.BLOCKED_CHANGE_FILES:
                allowed = False
                blocked_files.append(normalized)
                reasons.append("Proposal changes dependency or framework definition files.")

        if category in self.BLOCKED_EXECUTION_CATEGORIES:
            allowed = False
            reasons.append("Proposal category is explicitly blocked from self-improvement execution.")
        elif category and category not in self.ALLOWLISTED_EXECUTION_CATEGORIES:
            notes.append("Proposal category is not allowlisted for automatic execution.")

        if len(operations) > 8:
            allowed = False
            reasons.append("Proposal defines too many patch operations for a narrow reversible change.")

        for operation in operations:
            target = str(operation.get("path") or operation.get("file") or "").strip()
            if not target:
                allowed = False
                reasons.append("Proposal patch plan contains an operation without a target path.")
                continue
            resolved = self._resolve_candidate_path(target)
            if not self._is_within_project(resolved):
                allowed = False
                blocked_files.append(target)
                reasons.append("Proposal patch operation references a file outside the approved RogueAI workspace.")

        proposal_text = " ".join(
            str(proposal.get(field, ""))
            for field in ("title", "problem", "scope", "recommended_action")
        ).lower()
        if any(marker in proposal_text for marker in self.BROAD_CHANGE_MARKERS):
            allowed = False
            reasons.append("Proposal describes a broad rewrite, dependency shift, or unrestricted self-modification.")

        plan_is_narrow = bool(operations) and len(files) <= 2
        execution_allowed = allowed and category in self.ALLOWLISTED_EXECUTION_CATEGORIES and plan_is_narrow
        if not operations:
            notes.append("Proposal does not yet include structured patch operations, so it remains proposal-only.")
        elif not execution_allowed:
            notes.append("Proposal may be reviewable, but it is not execution-ready under the current allowlist.")

        risk = self._risk_level(allowed, reasons, files, execution_allowed)
        if allowed:
            reasons.append("Proposal stays within a small, local file scope.")
        else:
            notes.append("Blocked proposals should be narrowed before any future executor considers them.")

        return {
            "allowed": allowed,
            "execution_allowed": execution_allowed,
            "category": category or "unspecified",
            "risk": risk,
            "reasons": reasons,
            "blocked_files": blocked_files,
            "notes": notes,
        }

    def _resolve_candidate_path(self, value: str):
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        return (self.project_root / path).resolve()

    def _is_within_project(self, path: Path):
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    def _risk_level(self, allowed: bool, reasons: list[str], files: list[str], execution_allowed: bool):
        if not allowed:
            return "high"
        if execution_allowed and len(files) <= 2:
            return "low"
        if len(files) > 2 or reasons:
            return "medium"
        return "low"
