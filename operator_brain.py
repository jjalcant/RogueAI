"""Central orchestration layer for RogueAI operator coordination."""

from __future__ import annotations

from datetime import datetime

from brain.router import route_input, run_agent_workflow
from decision_policy import DecisionAction, DecisionPolicy
from operator_modes import OperatorMode, classify_operator_mode
from runtime_state import RuntimeStateBuilder
from verification_policy import VerificationPolicy


class OperatorBrain:
    """Coordinate existing Rogue subsystems without replacing them."""

    def __init__(
        self,
        app,
        *,
        runtime_state_builder=None,
        decision_policy=None,
        verification_policy=None,
        router_handler=None,
        agent_handler=None,
    ):
        self.app = app
        self.runtime_state_builder = runtime_state_builder or RuntimeStateBuilder()
        self.decision_policy = decision_policy or DecisionPolicy()
        self.verification_policy = verification_policy or VerificationPolicy()
        self.router_handler = router_handler or route_input
        self.agent_handler = agent_handler or run_agent_workflow

    def handle_request(self, text):
        request_text = str(text or "").strip()
        snapshot_before = self.runtime_state_builder.build(self.app)
        mode = classify_operator_mode(request_text, runtime_state=snapshot_before.to_dict())
        decision = self.decision_policy.decide(request_text, mode, runtime_state=snapshot_before.to_dict())

        response = ""
        error = None
        try:
            response = self._execute(decision, request_text, snapshot_before.to_dict())
        except Exception as exc:
            error = exc
            response = ""

        snapshot_after = self.runtime_state_builder.build(self.app)
        verification = self.verification_policy.normalize(
            response_text=response,
            structured_payload=getattr(self.app, "last_structured_response_payload", None),
            agent_payload=getattr(self.app, "last_agent_workflow_payload", None),
            error=error,
        )
        improvement_signal = self._route_improvement_signal(
            request_text=request_text,
            mode=mode,
            decision=decision.to_dict(),
            response=response,
            verification=verification.to_dict(),
            runtime_state=snapshot_after.to_dict(),
        )
        summary = self._build_operator_summary(
            request_text=request_text,
            mode=mode,
            decision=decision.to_dict(),
            response=response,
            verification=verification.to_dict(),
            runtime_state=snapshot_after.to_dict(),
            improvement_signal=improvement_signal,
        )
        self._store_summary(summary)

        if error is not None:
            raise error
        return response

    def get_operator_summary(self):
        existing = getattr(self.app, "last_operator_summary", None)
        runtime_state = self.runtime_state_builder.build(self.app).to_dict()
        if not isinstance(existing, dict):
            return self._build_idle_summary(runtime_state)

        summary = dict(existing)
        summary["runtime_state"] = runtime_state
        summary["runtime_health"] = runtime_state.get("runtime_health", {})
        summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
        return summary

    def _execute(self, decision, request_text, runtime_state):
        action = decision.action

        if action == DecisionAction.RESPOND_DIRECTLY.value:
            return self._build_operator_response(
                "Operator Ready",
                summary=["Rogue is ready."],
                details=["No tool or workflow execution was required for this request."],
                recommendations=[self._default_recommendation(runtime_state)],
            )

        if action == DecisionAction.SAFE_PROPOSAL_ONLY.value:
            return self._build_operator_response(
                "Safe Mode",
                summary=["Operator Brain stayed in proposal-only mode."],
                details=[
                    "The request touched self-modification or broad autonomous behavior.",
                    "No code changes or self-improvement execution paths were triggered.",
                ],
                recommendations=["Review Friction Radar or the approval queue before enabling any improvement execution."],
            )

        if action == DecisionAction.SHOW_DIAGNOSTICS.value:
            return self._build_operator_response(
                "Runtime Diagnostics",
                summary=[
                    f"Runtime health: {runtime_state.get('runtime_health', {}).get('label', 'unknown')}",
                    f"Backend mode: {runtime_state.get('backend', {}).get('mode', 'unknown')}",
                ],
                details=[
                    runtime_state.get("runtime_health", {}).get("summary", "No health summary available."),
                    f"Recent failures: {len(runtime_state.get('recent_failures', []))}",
                    f"Active tasks: {runtime_state.get('active_tasks', {}).get('active_count', 0)}",
                ],
                recommendations=[self._default_recommendation(runtime_state)],
            )

        if action == DecisionAction.SHOW_IMPROVEMENT_REVIEW.value:
            improvement = runtime_state.get("self_improvement_summary", {})
            top_candidate = improvement.get("top_candidate") if isinstance(improvement.get("top_candidate"), dict) else {}
            details = [
                f"Events recorded: {improvement.get('event_count', 0)}",
                f"Pending approvals: {runtime_state.get('approval_queue_summary', {}).get('pending_count', 0)}",
                f"Execution ready: {runtime_state.get('approval_queue_summary', {}).get('execution_ready_count', 0)}",
            ]
            if top_candidate:
                details.append(
                    "Top candidate: "
                    f"{top_candidate.get('area', 'general')} | {top_candidate.get('symptom', 'unspecified friction')}"
                )
            return self._build_operator_response(
                "Improvement Review",
                summary=["Existing self-improvement signals were surfaced without executing changes."],
                details=details,
                recommendations=["Review Friction Radar or pending approvals before taking any execution step."],
            )

        if action == DecisionAction.SHOW_EXPERIMENT_REVIEW.value:
            experiments = runtime_state.get("experiment_summary", {})
            return self._build_operator_response(
                "Experiment Review",
                summary=[f"Tracked experiments: {experiments.get('count', 0)}"],
                details=[
                    f"Latest experiment: {experiments.get('latest_experiment_id') or 'none'}",
                    f"Latest winner: {experiments.get('latest_winner') or 'none'}",
                ],
                recommendations=["Use Friction Radar to compare experiment outcomes with live improvement pressure."],
            )

        if action == DecisionAction.USE_AGENT_WORKFLOW.value:
            return self.agent_handler(self.app, decision.goal or request_text)

        return self.router_handler(self.app, request_text)

    def _build_operator_summary(self, *, request_text, mode, decision, response, verification, runtime_state, improvement_signal):
        mission = self._extract_mission_payload(decision, response)
        recommended_next_action = verification.get("reason") or self._default_recommendation(runtime_state)
        if improvement_signal.get("triggered"):
            recommended_next_action = "Review Friction Radar for repeated operator friction before retrying."

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "current_mode": mode.value,
            "current_mission": mission.get("goal") or request_text or "Idle",
            "runtime_health": runtime_state.get("runtime_health", {}),
            "verification": verification,
            "verification_status": verification.get("status", "ready"),
            "recommended_next_action": recommended_next_action,
            "mission": {
                "goal": mission.get("goal") or request_text,
                "chosen_mode": mode.value,
                "plan": mission.get("plan", []),
                "execution_path": decision.get("execution_path", ""),
                "verification_result": verification.get("status", "ready"),
                "recommendation": recommended_next_action,
                "improvement_signal": improvement_signal,
            },
            "runtime_state": runtime_state,
            "improvement_signal": improvement_signal,
            "operator_summary_line": (
                f"Mode: {mode.value} | "
                f"Mission: {mission.get('goal') or request_text or 'Idle'} | "
                f"Status: {verification.get('status', 'ready')}"
            ),
        }

    def _extract_mission_payload(self, decision, response):
        agent_payload = getattr(self.app, "last_agent_workflow_payload", None)
        if isinstance(agent_payload, dict) and agent_payload.get("kind") == "agent_run":
            payload = agent_payload.get("payload", {}) if isinstance(agent_payload.get("payload"), dict) else {}
            plan = [item.get("title") for item in payload.get("plan", []) if item.get("title")]
            return {"goal": payload.get("goal", ""), "plan": plan}

        return {
            "goal": decision.get("goal", ""),
            "plan": [decision.get("reason", "")] if decision.get("reason") else [],
            "response": str(response or ""),
        }

    def _route_improvement_signal(self, *, request_text, mode, decision, response, verification, runtime_state):
        observer = getattr(self.app, "improvement_observer", None)
        triggered = []
        if observer is None:
            return {"triggered": False, "signals": triggered}

        if verification.get("mismatch_detected"):
            observer.log_event(
                area="operator_brain",
                trigger="verification_mismatch",
                command=request_text,
                symptom=verification.get("reason", "verification mismatch"),
                impact=4,
                frequency_hint=1,
                raw_context=response,
                metadata={"mode": mode.value, "decision": decision.get("action"), "status": verification.get("status")},
            )
            triggered.append("verification_mismatch")

        recent_failures = len(runtime_state.get("recent_failures", []))
        if verification.get("status") in {"partial_success", "blocked", "failed"} and recent_failures >= 2:
            observer.log_event(
                area="operator_brain",
                trigger="repeated_friction",
                command=request_text,
                symptom=verification.get("reason", "repeated operator friction"),
                impact=4,
                frequency_hint=recent_failures,
                raw_context=response,
                metadata={"mode": mode.value, "decision": decision.get("action"), "status": verification.get("status")},
            )
            triggered.append("repeated_friction")

        return {"triggered": bool(triggered), "signals": triggered}

    def _store_summary(self, summary):
        setattr(self.app, "last_operator_summary", summary)
        setattr(self.app, "last_runtime_state_snapshot", summary.get("runtime_state"))
        setattr(self.app, "last_verification_result", summary.get("verification"))

    def _build_idle_summary(self, runtime_state):
        recommendation = self._default_recommendation(runtime_state)
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "current_mode": OperatorMode.CHAT.value,
            "current_mission": "Idle",
            "runtime_health": runtime_state.get("runtime_health", {}),
            "verification": {"status": "ready", "reason": "No request has been executed yet."},
            "verification_status": "ready",
            "recommended_next_action": recommendation,
            "mission": {
                "goal": "Idle",
                "chosen_mode": OperatorMode.CHAT.value,
                "plan": [],
                "execution_path": "idle",
                "verification_result": "ready",
                "recommendation": recommendation,
                "improvement_signal": {"triggered": False, "signals": []},
            },
            "runtime_state": runtime_state,
            "improvement_signal": {"triggered": False, "signals": []},
            "operator_summary_line": "Mode: chat | Mission: Idle | Status: ready",
        }

    @staticmethod
    def _default_recommendation(runtime_state):
        health = runtime_state.get("runtime_health", {})
        if health.get("label") == "degraded":
            return "Run diagnostics or a system-status workflow before starting a larger mission."
        if runtime_state.get("approval_queue_summary", {}).get("pending_count", 0):
            return "Review pending improvement approvals in Friction Radar."
        current_task = runtime_state.get("active_tasks", {}).get("current_task", {})
        if current_task.get("goal"):
            return f"Resume the active mission: {current_task['goal']}"
        return "Use Chat or Command Center to start the next verified task."

    @staticmethod
    def _build_operator_response(title, *, summary=None, details=None, recommendations=None):
        lines = [str(title).strip() or "Operator Response"]
        sections = [
            ("Summary", summary or []),
            ("Details", details or []),
            ("Recommendation", recommendations or []),
        ]
        for heading, values in sections:
            cleaned = [str(value).strip() for value in values if str(value).strip()]
            if not cleaned:
                continue
            lines.append("")
            lines.append(heading)
            for item in cleaned:
                lines.append(f"- {item}")
        return "\n".join(lines)
