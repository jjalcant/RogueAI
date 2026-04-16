"""Normalize final operator-facing status from RogueAI execution evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass


SUCCESS_STATUSES = {"verified_success", "partial_success", "ready"}
FAILURE_MARKERS = ("failed", "error", "could not", "unknown command", "not available")
BLOCKED_MARKERS = ("blocked", "approval", "confirm", "cancelled", "proposal-only", "safe mode")


@dataclass
class VerificationResult:
    status: str
    reason: str
    ui_level: str
    message_kind: str
    mismatch_detected: bool = False
    evidence_count: int = 0
    verified_steps: int = 0
    total_steps: int = 0

    def to_dict(self):
        return asdict(self)


def verification_status_to_ui_level(status: str) -> str:
    mapping = {
        "verified_success": "done",
        "partial_success": "warning",
        "blocked": "warning",
        "failed": "error",
        "ready": "ready",
    }
    return mapping.get(str(status or "").strip().lower(), "info")


def verification_status_to_message_kind(status: str, default: str = "assistant") -> str:
    mapping = {
        "verified_success": "tool",
        "partial_success": "warning",
        "blocked": "warning",
        "failed": "warning",
        "ready": default,
    }
    return mapping.get(str(status or "").strip().lower(), default)


class VerificationPolicy:
    """Map raw execution details into a conservative operator status."""

    def normalize(self, response_text="", structured_payload=None, agent_payload=None, error=None) -> VerificationResult:
        if error is not None:
            return VerificationResult(
                status="failed",
                reason=f"Unhandled execution error: {error}",
                ui_level="error",
                message_kind="warning",
            )

        if isinstance(agent_payload, dict) and agent_payload.get("kind") == "agent_run":
            result = self._from_agent_run(agent_payload.get("payload", {}), response_text=response_text)
        elif isinstance(structured_payload, dict):
            result = self._from_structured_payload(structured_payload, response_text=response_text)
        else:
            result = self._from_text(response_text)

        if self._text_looks_failed(response_text) and result.status in SUCCESS_STATUSES:
            result.mismatch_detected = True
            result.reason = f"{result.reason} The user-facing text looked like a failure, but the verified payload indicated success."
        return result

    def _from_agent_run(self, payload, response_text=""):
        payload = payload if isinstance(payload, dict) else {}
        results = list(payload.get("results", []) or [])
        total_steps = max(len(payload.get("plan", []) or []), len(results))
        verified_steps = sum(1 for item in results if item.get("verified"))
        blocked = self._text_looks_blocked(payload.get("final_output") or response_text)

        if blocked:
            status = "blocked"
            reason = "Execution stopped in a blocked or approval-gated state."
        elif payload.get("success") and total_steps and verified_steps == total_steps:
            status = "verified_success"
            reason = "All planned steps completed and verified."
        elif verified_steps > 0:
            status = "partial_success"
            reason = "At least one step verified, but the full mission did not complete cleanly."
        elif payload.get("success"):
            status = "ready"
            reason = "The workflow returned without verifiable execution detail."
        else:
            status = "failed"
            reason = str(payload.get("final_output") or "The workflow did not verify successfully.")

        return VerificationResult(
            status=status,
            reason=reason,
            ui_level=verification_status_to_ui_level(status),
            message_kind=verification_status_to_message_kind(status),
            evidence_count=len(results),
            verified_steps=verified_steps,
            total_steps=total_steps,
        )

    def _from_structured_payload(self, payload, response_text=""):
        evidence_count = self._structured_evidence_count(payload)
        success = bool(payload.get("success"))
        blocked = self._text_looks_blocked(payload.get("error") or payload.get("result") or response_text)

        if blocked and not success:
            status = "blocked"
            reason = str(payload.get("error") or payload.get("result") or "Execution is blocked pending review or confirmation.")
        elif success and (evidence_count > 0 or str(payload.get("result") or "").strip()):
            status = "verified_success"
            reason = "Structured execution returned success with reviewable evidence."
        elif not success and evidence_count > 0:
            status = "partial_success"
            reason = "Structured execution returned mixed evidence despite a non-success status."
        elif success:
            status = "ready"
            reason = "The command succeeded, but there was little verification detail to display."
        else:
            status = "failed"
            reason = str(payload.get("error") or "The command did not return a verified success.")

        return VerificationResult(
            status=status,
            reason=reason,
            ui_level=verification_status_to_ui_level(status),
            message_kind=verification_status_to_message_kind(status),
            evidence_count=evidence_count,
        )

    def _from_text(self, response_text=""):
        text = str(response_text or "").strip()
        if not text:
            status = "ready"
            reason = "No result text was returned."
        elif self._text_looks_blocked(text):
            status = "blocked"
            reason = "The response indicates a blocked or confirmation-gated state."
        elif self._text_looks_failed(text):
            status = "failed"
            reason = "The response text indicates failure."
        else:
            status = "ready"
            reason = "The response is conversational or advisory."

        return VerificationResult(
            status=status,
            reason=reason,
            ui_level=verification_status_to_ui_level(status),
            message_kind=verification_status_to_message_kind(status, default="assistant"),
        )

    @staticmethod
    def _structured_evidence_count(payload):
        evidence = 0
        for key in ("summary", "preview", "inspection", "report"):
            if isinstance(payload.get(key), dict) and payload.get(key):
                evidence += 1
        evidence += len(payload.get("artifacts", []) or [])
        evidence += len(payload.get("observed", []) or [])
        return evidence

    @staticmethod
    def _text_looks_failed(text):
        lowered = str(text or "").strip().lower()
        return any(marker in lowered for marker in FAILURE_MARKERS)

    @staticmethod
    def _text_looks_blocked(text):
        lowered = str(text or "").strip().lower()
        return any(marker in lowered for marker in BLOCKED_MARKERS)
