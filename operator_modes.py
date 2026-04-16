"""High-level operator modes for RogueAI request orchestration."""

from __future__ import annotations

from enum import Enum


class OperatorMode(str, Enum):
    CHAT = "chat"
    DIRECT_COMMAND = "direct_command"
    AGENT_TASK = "agent_task"
    DIAGNOSTIC = "diagnostic"
    IMPROVEMENT_REVIEW = "improvement_review"
    EXPERIMENT_REVIEW = "experiment_review"
    SAFE_MODE = "safe_mode"


SAFE_MODE_MARKERS = (
    "improve yourself",
    "self modify",
    "self-modify",
    "rewrite yourself",
    "rewrite the architecture",
    "autonomously improve",
    "run self improvement",
    "execute improvement proposals",
    "modify your own code",
)

IMPROVEMENT_REVIEW_MARKERS = (
    "improvement review",
    "review improvements",
    "show improvements",
    "friction radar",
    "pending approvals",
    "improvement proposals",
)

EXPERIMENT_REVIEW_MARKERS = (
    "experiment review",
    "review experiments",
    "show experiments",
    "experiment summary",
    "ab test",
    "a/b test",
)

DIAGNOSTIC_MARKERS = (
    "diagnostic",
    "diagnostics",
    "system status",
    "agent status",
    "report system status",
    "health check",
    "system health",
    "storage overview",
)

AGENT_PREFIXES = (
    "use agent to ",
    "run agent ",
    "agent ",
    "plan and execute ",
)

AGENT_MARKERS = (
    "scan ",
    "inspect ",
    "summarize folder ",
    "workspace summary",
    "organize ",
    "organise ",
    "report system status",
)

DIRECT_COMMAND_PREFIXES = (
    "open ",
    "run ",
    "list ",
    "show ",
    "create ",
    "make ",
    "delete ",
    "remove ",
    "move ",
    "copy ",
    "search ",
)


def normalize_operator_text(text) -> str:
    return " ".join(str(text or "").strip().lower().split())


def classify_operator_mode(text, runtime_state=None) -> OperatorMode:
    """Classify the request into a conservative operator mode."""

    normalized = normalize_operator_text(text)
    if not normalized:
        return OperatorMode.CHAT

    if any(marker in normalized for marker in SAFE_MODE_MARKERS):
        return OperatorMode.SAFE_MODE

    if any(marker in normalized for marker in IMPROVEMENT_REVIEW_MARKERS):
        return OperatorMode.IMPROVEMENT_REVIEW

    if any(marker in normalized for marker in EXPERIMENT_REVIEW_MARKERS):
        return OperatorMode.EXPERIMENT_REVIEW

    if normalized.startswith(AGENT_PREFIXES) or any(marker in normalized for marker in AGENT_MARKERS):
        return OperatorMode.AGENT_TASK

    if any(marker in normalized for marker in DIAGNOSTIC_MARKERS):
        return OperatorMode.DIAGNOSTIC

    if normalized.startswith(DIRECT_COMMAND_PREFIXES):
        return OperatorMode.DIRECT_COMMAND

    return OperatorMode.CHAT
