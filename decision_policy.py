"""Conservative execution-path selection for RogueAI operator requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from operator_modes import OperatorMode, normalize_operator_text


class DecisionAction(str, Enum):
    RESPOND_DIRECTLY = "respond_directly"
    USE_ROUTER = "use_router"
    USE_AGENT_WORKFLOW = "use_agent_workflow"
    SHOW_DIAGNOSTICS = "show_diagnostics"
    SHOW_IMPROVEMENT_REVIEW = "show_improvement_review"
    SHOW_EXPERIMENT_REVIEW = "show_experiment_review"
    SAFE_PROPOSAL_ONLY = "safe_proposal_only"


ROUTER_DIAGNOSTIC_COMMANDS = ("system health", "storage overview")
AGENT_DIAGNOSTIC_COMMANDS = ("report system status", "agent status")
GREETING_MARKERS = {"hi", "hello", "hey", "hola"}


@dataclass
class Decision:
    action: str
    mode: str
    execution_path: str
    reason: str
    goal: str = ""

    def to_dict(self):
        return asdict(self)


def _extract_agent_goal(text: str) -> str:
    raw_text = str(text or "").strip()
    lowered = raw_text.lower()
    for prefix in ("use agent to ", "run agent ", "agent ", "plan and execute "):
        if lowered.startswith(prefix):
            return raw_text[len(prefix):].strip()
    return raw_text


class DecisionPolicy:
    """Pick the smallest safe execution path for a classified request."""

    def decide(self, text, mode: OperatorMode, runtime_state=None) -> Decision:
        normalized = normalize_operator_text(text)

        if normalized in GREETING_MARKERS:
            return Decision(
                action=DecisionAction.RESPOND_DIRECTLY.value,
                mode=mode.value,
                execution_path="operator_response",
                reason="Greeting detected; no tool or workflow execution required.",
            )

        if mode == OperatorMode.SAFE_MODE:
            return Decision(
                action=DecisionAction.SAFE_PROPOSAL_ONLY.value,
                mode=mode.value,
                execution_path="safe_mode_guard",
                reason="Unsafe autonomy or self-modification language detected.",
                goal=str(text or "").strip(),
            )

        if mode == OperatorMode.IMPROVEMENT_REVIEW:
            return Decision(
                action=DecisionAction.SHOW_IMPROVEMENT_REVIEW.value,
                mode=mode.value,
                execution_path="improvement_runtime_summary",
                reason="The request asks for current improvement pressure or proposals.",
            )

        if mode == OperatorMode.EXPERIMENT_REVIEW:
            return Decision(
                action=DecisionAction.SHOW_EXPERIMENT_REVIEW.value,
                mode=mode.value,
                execution_path="experiment_summary",
                reason="The request asks for the current experiment state.",
            )

        if mode == OperatorMode.DIAGNOSTIC:
            if any(marker in normalized for marker in ROUTER_DIAGNOSTIC_COMMANDS):
                return Decision(
                    action=DecisionAction.USE_ROUTER.value,
                    mode=mode.value,
                    execution_path="router -> direct tool path",
                    reason="The request maps to an existing verified diagnostic tool.",
                    goal=str(text or "").strip(),
                )

            if any(marker in normalized for marker in AGENT_DIAGNOSTIC_COMMANDS):
                return Decision(
                    action=DecisionAction.USE_AGENT_WORKFLOW.value,
                    mode=mode.value,
                    execution_path="planner -> agent_loop",
                    reason="The request needs a multi-step diagnostic workflow.",
                    goal="report system status",
                )

            return Decision(
                action=DecisionAction.SHOW_DIAGNOSTICS.value,
                mode=mode.value,
                execution_path="runtime_state_snapshot",
                reason="A lightweight runtime diagnostic summary is sufficient.",
            )

        if mode == OperatorMode.AGENT_TASK:
            goal = _extract_agent_goal(text)
            return Decision(
                action=DecisionAction.USE_AGENT_WORKFLOW.value,
                mode=mode.value,
                execution_path="planner -> task_manager -> agent_loop",
                reason="The request looks like a larger multi-step goal.",
                goal=goal,
            )

        if mode == OperatorMode.DIRECT_COMMAND:
            return Decision(
                action=DecisionAction.USE_ROUTER.value,
                mode=mode.value,
                execution_path="router -> direct command path",
                reason="The request looks like an explicit command with an existing route.",
                goal=str(text or "").strip(),
            )

        return Decision(
            action=DecisionAction.USE_ROUTER.value,
            mode=mode.value,
            execution_path="router",
            reason="Default to the existing router for conservative handling.",
            goal=str(text or "").strip(),
        )
