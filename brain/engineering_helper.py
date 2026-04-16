"""Lightweight engineering helper for Codex-ready task prompts."""

from __future__ import annotations


DEFAULT_CONSTRAINTS = [
    "minimal invasive changes",
    "no architecture rewrite",
    "preserve current behavior",
]


def _structured_result(success, action, result="", error=None, **extra):
    payload = {
        "success": success,
        "action": action,
        "result": result,
        "error": error,
    }
    payload.update(extra)
    return payload


def _normalize_task_type(task_type):
    value = (task_type or "feature").strip().lower()
    allowed = {"bugfix", "feature", "refactor", "tests", "documentation", "docs", "hardening"}
    if value not in allowed:
        return "feature"
    if value == "documentation":
        return "docs"
    return value


def build_codex_prompt(task_type, target_area, user_goal, constraints=None):
    task_type = _normalize_task_type(task_type)
    constraints = list(constraints or [])
    merged_constraints = DEFAULT_CONSTRAINTS + [item for item in constraints if item not in DEFAULT_CONSTRAINTS]
    if task_type in {"bugfix", "tests", "hardening"} and "add tests where relevant" not in merged_constraints:
        merged_constraints.append("add tests where relevant")

    title = f"Codex {task_type} request for {target_area or 'the project'}"
    prompt_lines = [
        "You are extending RogueAI, a stable local desktop AI agent.",
        "",
        f"Task type: {task_type}",
        f"Target area: {target_area or 'general project area'}",
        f"Goal: {user_goal}",
        "",
        "Constraints:",
    ]
    prompt_lines.extend([f"- {item}" for item in merged_constraints])
    prompt_lines.extend(
        [
            "",
            "Requirements:",
            "- keep it review-first and human-approved",
            "- do not introduce autonomous self-modification",
            "- return a concise implementation summary, verification results, and remaining risks",
        ]
    )
    prompt_text = "\n".join(prompt_lines)
    return _structured_result(True, "build_codex_prompt", result=prompt_text, title=title, prompt_text=prompt_text, task_type=task_type)


def summarize_project_issue(issue_text):
    cleaned = (issue_text or "").strip()
    if not cleaned:
        return _structured_result(False, "summarize_project_issue", error="No issue text provided.")
    summary = cleaned.splitlines()[0][:240]
    return _structured_result(True, "summarize_project_issue", result=summary, summary=summary)


def suggest_next_engineering_step(context):
    cleaned = (context or "").strip().lower()
    if "router" in cleaned:
        suggestion = "Prepare a focused bugfix or hardening task for the router and add a router regression test."
    elif "ui" in cleaned or "desktop" in cleaned:
        suggestion = "Prepare a small UI hardening task with one clear workflow improvement and verification steps."
    else:
        suggestion = "Prepare a narrowly scoped Codex feature or hardening task with tests and explicit constraints."
    return _structured_result(True, "suggest_next_engineering_step", result=suggestion, suggestion=suggestion)


def format_change_request(title, objective, files=None, risks=None):
    files = files or []
    risks = risks or []
    lines = [
        f"Title: {title}",
        f"Objective: {objective}",
    ]
    if files:
        lines.append("Files:")
        lines.extend([f"- {item}" for item in files])
    if risks:
        lines.append("Risks:")
        lines.extend([f"- {item}" for item in risks])
    result = "\n".join(lines)
    return _structured_result(True, "format_change_request", result=result, change_request=result)
