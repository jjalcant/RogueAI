"""Shared evidence-backed result helpers for RogueAI."""

from __future__ import annotations

from pathlib import Path


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def make_artifact(kind, path=None, description=None, exists=None, verified=None, **extra):
    artifact = {"kind": str(kind)}
    if path is not None:
        artifact["path"] = str(path)
    if description:
        artifact["description"] = str(description)
    if exists is not None:
        artifact["exists"] = bool(exists)
    if verified is not None:
        artifact["verified"] = bool(verified)
    artifact.update(extra)
    return artifact


def _normalize_artifacts(artifacts):
    normalized = []
    for item in artifacts or []:
        if isinstance(item, dict):
            artifact = dict(item)
            if "path" in artifact and artifact["path"] is not None:
                artifact["path"] = str(artifact["path"])
            normalized.append(artifact)
            continue
        if item is None:
            continue
        normalized.append({"kind": "artifact", "description": str(item)})
    return normalized


def build_result(
    success,
    action,
    result="",
    error=None,
    observed=None,
    artifacts=None,
    warnings=None,
    errors=None,
    inferences=None,
    suggestions=None,
    **extra,
):
    error_list = _as_list(errors)
    if error:
        error_list.extend(_as_list(error))
    payload = {
        "success": bool(success),
        "action": str(action),
        "result": str(result or ""),
        "error": error_list[0] if error_list else None,
        "observed": _as_list(observed),
        "artifacts": _normalize_artifacts(artifacts),
        "warnings": _as_list(warnings),
        "errors": error_list,
        "inferences": _as_list(inferences),
        "suggestions": _as_list(suggestions),
    }
    payload.update(extra)
    return payload


def normalize_result(payload, action="tool"):
    if isinstance(payload, dict):
        raw = dict(payload)
        normalized = build_result(
            success=raw.get("success", raw.get("ok", raw.get("error") in (None, ""))),
            action=raw.get("action", action),
            result=raw.get("result", raw.get("message", "")),
            error=raw.get("error"),
            observed=raw.get("observed"),
            artifacts=raw.get("artifacts"),
            warnings=raw.get("warnings"),
            errors=raw.get("errors"),
            inferences=raw.get("inferences"),
            suggestions=raw.get("suggestions"),
        )

        if not normalized["observed"] and normalized["result"]:
            normalized["observed"] = _as_list(normalized["result"])

        if "path" in raw and raw.get("path"):
            candidate = Path(raw["path"])
            normalized["artifacts"].append(
                make_artifact(
                    "path",
                    path=str(candidate),
                    description=raw.get("path_description", "Referenced path"),
                    exists=candidate.exists(),
                    verified=True,
                )
            )

        for moved in raw.get("moved", []) or []:
            target = moved.get("target")
            if not target:
                continue
            candidate = Path(target)
            normalized["artifacts"].append(
                make_artifact(
                    moved.get("category", "moved_item"),
                    path=str(candidate),
                    description=f"Moved target for {Path(moved.get('source', target)).name}",
                    exists=candidate.exists(),
                    verified=True,
                )
            )

        normalized.update(raw)
        normalized["success"] = bool(normalized["success"])
        normalized["action"] = str(normalized["action"])
        normalized["observed"] = _as_list(normalized.get("observed"))
        normalized["warnings"] = _as_list(normalized.get("warnings"))
        normalized["errors"] = _as_list(normalized.get("errors"))
        if normalized.get("error") and normalized["error"] not in normalized["errors"]:
            normalized["errors"].append(str(normalized["error"]))
        normalized["artifacts"] = _normalize_artifacts(normalized.get("artifacts"))
        normalized["inferences"] = _as_list(normalized.get("inferences"))
        normalized["suggestions"] = _as_list(normalized.get("suggestions"))
        normalized["error"] = normalized["errors"][0] if normalized["errors"] else None
        return normalized

    if payload is None:
        return build_result(
            False,
            action,
            observed=["I cannot confirm that yet."],
            errors=["No current analysis result is available."],
        )

    return build_result(True, action, result=str(payload), observed=[str(payload)])


def artifact_to_text(artifact):
    kind = artifact.get("kind", "artifact")
    path_value = artifact.get("path")
    description = artifact.get("description")
    exists = artifact.get("exists")
    verified = artifact.get("verified")

    parts = []
    if description:
        parts.append(str(description))
    elif path_value:
        parts.append(str(path_value))
    else:
        parts.append(kind)

    if path_value and description and description != path_value:
        parts.append(f"path={path_value}")

    if verified and exists is True:
        parts.append("verified exists")
    elif verified and exists is False:
        parts.append("verified missing")
    elif verified:
        parts.append("verified")

    return " | ".join(parts)


def format_response_text(payload):
    normalized = normalize_result(payload)
    lines = [f"Action: {normalized['action']}"]

    sections = [
        ("Observed facts", normalized.get("observed", [])),
        ("Artifacts", [artifact_to_text(item) for item in normalized.get("artifacts", [])]),
        ("Inferences", normalized.get("inferences", [])),
        ("Suggestions", normalized.get("suggestions", [])),
        ("Warnings", normalized.get("warnings", [])),
        ("Errors", normalized.get("errors", [])),
    ]

    rendered_any = False
    for title, values in sections:
        values = [str(value) for value in values if str(value).strip()]
        if not values:
            continue
        rendered_any = True
        lines.append(f"{title}:")
        for value in values:
            lines.append(f"- {value}")

    if not rendered_any:
        lines.append("Observed facts:")
        if normalized.get("success"):
            lines.append("- That action returned no concrete evidence.")
        else:
            lines.append("- I cannot confirm that yet.")

    return "\n".join(lines)
