"""Approval-aware proposal lifecycle management for RogueAI improvements."""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

from improvement_guard import ImprovementGuard
from improvement_storage import ImprovementStorage


class ImprovementApprovalQueue:
    REVIEW_THRESHOLD = 70
    BLOCK_THRESHOLD = 30
    EXECUTION_READY_THRESHOLD = 80
    TERMINAL_STATUSES = {"executed", "rolled_back"}
    MANUAL_STATUSES = {"approved", "blocked"}

    def __init__(self, memory_root: Path | str, project_root: Path | str, guard: ImprovementGuard | None = None):
        self.storage = ImprovementStorage(memory_root=memory_root)
        self.guard = guard or ImprovementGuard(project_root)

    def stage_proposals(self, proposals: list[dict]):
        proposals_state, stored_proposals = self.storage.read_records(self.storage.proposals_path, "proposals")
        approvals_state, stored_queue = self.storage.read_records(self.storage.approvals_path, "queue")
        proposal_map = {str(item.get("id")): copy.deepcopy(item) for item in stored_proposals if item.get("id")}
        queue_map = {str(item.get("proposal_id")): copy.deepcopy(item) for item in stored_queue if item.get("proposal_id")}

        staged = []
        now = self._timestamp()
        for proposal in proposals:
            proposal_id = str(proposal.get("id") or "").strip()
            if not proposal_id:
                continue

            merged = proposal_map.get(proposal_id, {})
            merged.update(copy.deepcopy(proposal))
            safety = self.guard.evaluate_proposal_safety(merged)
            confidence = self._normalize_confidence(merged.get("confidence"))
            suggested_status, reason = self._suggested_status(merged, safety, confidence)

            queue_entry = queue_map.get(proposal_id, {"proposal_id": proposal_id, "history": []})
            previous_status = str(queue_entry.get("status") or "").strip().lower()
            final_status = self._resolved_status(previous_status, suggested_status, safety)

            merged["safety"] = safety
            merged["confidence"] = confidence
            merged["status"] = final_status
            merged["approval_required"] = final_status not in self.TERMINAL_STATUSES
            merged["execution_ready"] = self._is_execution_ready(merged, safety, final_status)
            merged["updated_at"] = now

            queue_entry["status"] = final_status
            queue_entry["updated_at"] = now
            queue_entry["reason"] = reason
            queue_entry["execution_ready"] = merged["execution_ready"]
            queue_entry["history"] = self._append_history(
                queue_entry.get("history", []),
                final_status,
                reason,
                timestamp=now,
            )

            proposal_map[proposal_id] = merged
            queue_map[proposal_id] = queue_entry
            staged.append(merged)

        proposals_state["updated_at"] = now
        proposals_state["proposals"] = self._sorted_proposals(list(proposal_map.values()))
        approvals_state["updated_at"] = now
        approvals_state["queue"] = self._sorted_queue(list(queue_map.values()))
        self.storage.write_json(self.storage.proposals_path, proposals_state)
        self.storage.write_json(self.storage.approvals_path, approvals_state)
        return [copy.deepcopy(item) for item in staged]

    def mark_proposal_ready_for_review(self, proposal_id: str):
        return self._update_status(proposal_id, "ready_for_review", "Queued for operator review.")

    def approve_proposal(self, proposal_id: str):
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return None
        if proposal.get("status") == "blocked":
            return None
        return self._update_status(proposal_id, "approved", "Approved for controlled execution.")

    def block_proposal(self, proposal_id: str, reason: str):
        return self._update_status(proposal_id, "blocked", reason or "Blocked by operator.")

    def mark_executed(self, proposal_id: str, note: str = "Execution completed."):
        return self._update_status(proposal_id, "executed", note)

    def mark_rolled_back(self, proposal_id: str, note: str = "Rolled back after validation failure."):
        return self._update_status(proposal_id, "rolled_back", note)

    def list_pending_approvals(self, limit: int | None = None):
        proposals = self._read_proposals()
        pending = [item for item in proposals if item.get("status") == "ready_for_review"]
        if limit is None:
            return pending
        return pending[:limit]

    def list_execution_ready(self, limit: int | None = None):
        proposals = self._read_proposals()
        ready = [item for item in proposals if item.get("execution_ready")]
        if limit is None:
            return ready
        return ready[:limit]

    def list_blocked(self, limit: int | None = None):
        proposals = self._read_proposals()
        blocked = [item for item in proposals if item.get("status") == "blocked"]
        if limit is None:
            return blocked
        return blocked[:limit]

    def get_proposal(self, proposal_id: str):
        for proposal in self._read_proposals():
            if proposal.get("id") == proposal_id:
                return proposal
        return None

    def _update_status(self, proposal_id: str, new_status: str, reason: str):
        proposals_state, proposals = self.storage.read_records(self.storage.proposals_path, "proposals")
        approvals_state, queue = self.storage.read_records(self.storage.approvals_path, "queue")
        proposal_map = {str(item.get("id")): item for item in proposals if item.get("id")}
        queue_map = {str(item.get("proposal_id")): item for item in queue if item.get("proposal_id")}

        proposal = proposal_map.get(proposal_id)
        if proposal is None:
            return None

        safety = proposal.get("safety") or self.guard.evaluate_proposal_safety(proposal)
        if new_status == "ready_for_review" and not safety.get("allowed"):
            new_status = "blocked"
        if new_status == "approved" and proposal.get("status") == "blocked":
            return None

        now = self._timestamp()
        proposal["status"] = new_status
        proposal["safety"] = safety
        proposal["approval_required"] = new_status not in self.TERMINAL_STATUSES
        proposal["execution_ready"] = self._is_execution_ready(proposal, safety, new_status)
        proposal["updated_at"] = now

        entry = queue_map.get(proposal_id, {"proposal_id": proposal_id, "history": []})
        entry["status"] = new_status
        entry["updated_at"] = now
        entry["reason"] = reason
        entry["execution_ready"] = proposal["execution_ready"]
        entry["history"] = self._append_history(entry.get("history", []), new_status, reason, timestamp=now)

        proposal_map[proposal_id] = proposal
        queue_map[proposal_id] = entry
        proposals_state["updated_at"] = now
        proposals_state["proposals"] = self._sorted_proposals(list(proposal_map.values()))
        approvals_state["updated_at"] = now
        approvals_state["queue"] = self._sorted_queue(list(queue_map.values()))
        self.storage.write_json(self.storage.proposals_path, proposals_state)
        self.storage.write_json(self.storage.approvals_path, approvals_state)
        return copy.deepcopy(proposal)

    def _read_proposals(self):
        _, proposals = self.storage.read_records(self.storage.proposals_path, "proposals")
        return self._sorted_proposals([copy.deepcopy(item) for item in proposals])

    def _suggested_status(self, proposal: dict, safety: dict, confidence: dict):
        score = int(confidence.get("score", 0) or 0)
        if not safety.get("allowed"):
            return "blocked", "Guard blocked the proposal scope."
        if score < self.BLOCK_THRESHOLD:
            return "blocked", "Confidence is too low for review."
        if score >= self.REVIEW_THRESHOLD:
            return "ready_for_review", "Confidence and scope justify operator review."
        return "proposed", "Proposal remains observational until evidence improves."

    def _resolved_status(self, previous_status: str, suggested_status: str, safety: dict):
        if not safety.get("allowed"):
            return "blocked"
        if previous_status in self.TERMINAL_STATUSES:
            return previous_status
        if previous_status in self.MANUAL_STATUSES and previous_status != "blocked":
            return previous_status
        return suggested_status

    def _is_execution_ready(self, proposal: dict, safety: dict, status: str):
        score = int((proposal.get("confidence") or {}).get("score", 0) or 0)
        return bool(
            safety.get("execution_allowed")
            and score >= self.EXECUTION_READY_THRESHOLD
            and status in {"ready_for_review", "approved", "executed"}
        )

    def _normalize_confidence(self, payload):
        if not isinstance(payload, dict):
            return {"score": 0, "level": "low", "factors": {}, "notes": ["Confidence data unavailable."]}
        score = int(payload.get("score", 0) or 0)
        if score >= 75:
            level = "high"
        elif score >= 50:
            level = "medium"
        else:
            level = "low"
        return {
            "score": max(0, min(100, score)),
            "level": str(payload.get("level") or level),
            "factors": payload.get("factors") if isinstance(payload.get("factors"), dict) else {},
            "notes": list(payload.get("notes") or []),
        }

    def _append_history(self, history: list[dict], status: str, reason: str, timestamp: str):
        if history and history[-1].get("status") == status and history[-1].get("reason") == reason:
            return history
        updated = list(history)
        updated.append({"timestamp": timestamp, "status": status, "reason": reason})
        return updated[-25:]

    def _sorted_proposals(self, proposals: list[dict]):
        order = {
            "approved": 0,
            "ready_for_review": 1,
            "proposed": 2,
            "executed": 3,
            "rolled_back": 4,
            "blocked": 5,
        }
        return sorted(
            proposals,
            key=lambda item: (
                order.get(str(item.get("status") or ""), 9),
                -int((item.get("confidence") or {}).get("score", 0) or 0),
                str(item.get("id") or ""),
            ),
        )

    def _sorted_queue(self, queue: list[dict]):
        return sorted(queue, key=lambda item: (str(item.get("status") or ""), str(item.get("proposal_id") or "")))

    def _timestamp(self):
        return datetime.now().isoformat(timespec="seconds")
