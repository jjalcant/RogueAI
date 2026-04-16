"""Sequential agent executor for RogueAI."""

from __future__ import annotations

from pathlib import Path

from planner import Planner, plan_to_text


class AgentLoop:
    def __init__(
        self,
        tool_registry,
        memory_manager,
        execution_logger,
        status_reporter=None,
        task_manager=None,
        max_retries: int = 1,
        improvement_observer=None,
    ):
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.execution_logger = execution_logger
        self.status_reporter = status_reporter
        self.task_manager = task_manager
        self.max_retries = max_retries
        self.improvement_observer = improvement_observer

    def run(self, goal: str, tasks, task_id=None, start_step: int = 0):
        self.execution_logger.log("agent_run_started", goal=goal, task_count=len(tasks))
        self.memory_manager.append_session("user_goal", goal)
        if self.task_manager is not None and task_id is not None:
            self.task_manager.update_task_status(task_id, "in_progress")

        results = []
        success = True

        for step_index, task in enumerate(tasks):
            if step_index < start_step:
                continue

            attempt = 0
            task_result = None
            verification_reason = "Task was not verified."
            allowed_retries = max(self.max_retries, int(getattr(task, "max_retries", 0)))
            while attempt <= allowed_retries:
                attempt += 1
                if self.task_manager is not None and task_id is not None and attempt > 1:
                    self.task_manager.increment_retry(task_id, step_index)
                self.execution_logger.log(
                    "task_started",
                    task_id=task.id,
                    title=task.title,
                    tool_name=task.tool_name,
                    attempt=attempt,
                )
                task_result = self.tool_registry.invoke(task.tool_name, **task.tool_input)
                verified, verification_reason = self._verify(task, task_result)
                if self.task_manager is not None and task_id is not None:
                    self.task_manager.set_verification_result(task_id, step_index, verified, verification_reason)
                self.execution_logger.log(
                    "task_finished",
                    task_id=task.id,
                    tool_name=task.tool_name,
                    success=task_result.get("success"),
                    verified=verified,
                    verification_reason=verification_reason,
                    error=task_result.get("error"),
                )
                if not task_result.get("success"):
                    self._observe_friction(
                        area="task_execution",
                        trigger="execution_failure",
                        command=task.tool_name,
                        symptom=task_result.get("error") or "Tool reported failure.",
                        impact=5,
                        metadata={"task_id": task.id, "title": task.title, "attempt": attempt},
                    )
                elif not verified:
                    self._observe_friction(
                        area="agent_loop",
                        trigger="verification_failure",
                        command=task.tool_name,
                        symptom=verification_reason,
                        impact=4,
                        metadata={"task_id": task.id, "title": task.title, "attempt": attempt},
                    )
                if attempt < allowed_retries + 1 and not (task_result.get("success") and verified):
                    self._observe_friction(
                        area="agent_loop",
                        trigger="repeated_retry",
                        command=task.tool_name,
                        symptom=verification_reason or task_result.get("error") or "Task required retry.",
                        impact=3,
                        frequency_hint=attempt,
                        metadata={"task_id": task.id, "title": task.title, "attempt": attempt},
                    )
                if task_result.get("success") and verified:
                    break
            structured = {
                "task": task.to_dict(),
                "result": task_result,
                "verified": verified,
                "verification_reason": verification_reason,
                "attempts": attempt,
            }
            results.append(structured)
            if structured["verified"]:
                self.memory_manager.append_session("step_result", f"{task.title}: {verification_reason}")
                self._persist_result_memory(task, task_result)
                if self.task_manager is not None and task_id is not None:
                    self.task_manager.mark_step_complete(
                        task_id,
                        step_index,
                        {
                            "result": task_result,
                            "verification_result": {
                                "verified": True,
                                "reason": verification_reason,
                            },
                        },
                    )
            if not structured["verified"]:
                success = False
                if self.task_manager is not None and task_id is not None:
                    self.task_manager.mark_step_failed(task_id, step_index, verification_reason)
                break

        final_output = self._build_final_output(goal, tasks, results, success)
        self.memory_manager.append_session("agent_summary", final_output)
        self.execution_logger.log("agent_run_finished", goal=goal, success=success)

        if self.status_reporter is not None:
            self.status_reporter.add_validation(f"Agent workflow '{goal}' success={success}")
        if self.task_manager is not None and task_id is not None:
            self.task_manager.update_task_status(
                task_id,
                "completed" if success else "failed",
                final_summary=final_output,
            )

        return {
            "success": success,
            "goal": goal,
            "plan": [task.to_dict() for task in tasks],
            "results": results,
            "final_output": final_output,
            "task_id": task_id,
        }

    def _observe_friction(self, area: str, trigger: str, command: str, symptom: str, impact: int, metadata: dict | None = None, frequency_hint: int = 1):
        if self.improvement_observer is None:
            return
        try:
            self.improvement_observer.log_event(
                area=area,
                trigger=trigger,
                command=command,
                symptom=symptom or "unspecified task friction",
                impact=impact,
                frequency_hint=frequency_hint,
                raw_context={"command": command, "symptom": symptom, "metadata": metadata or {}},
                metadata=metadata or {},
            )
        except Exception:
            return

    def run_goal(self, goal: str, planner: Planner | None = None):
        planner = planner or Planner()
        tasks = planner.create_plan(goal)
        if not tasks:
            final_output = "No executable plan could be created."
            self.execution_logger.log("agent_run_finished", goal=goal, success=False, reason="empty_plan")
            if self.status_reporter is not None:
                self.status_reporter.add_validation(f"Agent workflow '{goal}' success=False")
            return {
                "success": False,
                "goal": goal,
                "plan": [],
                "results": [],
                "final_output": final_output,
            }
        task_id = None
        if self.task_manager is not None:
            task_payload = self.task_manager.create_task(goal, [task.to_dict() for task in tasks])
            task_id = task_payload["task"]["task_id"]
        return self.run(goal, tasks, task_id=task_id, start_step=0)

    def resume_task(self, task_id):
        if self.task_manager is None:
            return {
                "success": False,
                "goal": "",
                "plan": [],
                "results": [],
                "final_output": "Task resumption is not available without a task manager.",
            }

        payload = self.task_manager.resume_task(task_id)
        if not payload.get("success"):
            return {
                "success": False,
                "goal": "",
                "plan": [],
                "results": [],
                "final_output": payload.get("error", "Unable to resume task."),
            }

        task = payload["task"]
        tasks = [
            PlannerTaskAdapter.from_task_record(step)
            for step in task.get("steps", [])
        ]
        return self.run(
            goal=task["goal"],
            tasks=tasks,
            task_id=task["task_id"],
            start_step=task.get("current_step", 0),
        )

    def _verify(self, task, result: dict):
        if not isinstance(result, dict):
            return False, "Tool did not return a structured result."
        if not result.get("success"):
            return False, result.get("error") or "Tool reported failure."

        verification = getattr(task, "verification", None) or {"type": "non_empty_output"}
        verification_type = verification.get("type", "non_empty_output")
        output_text = self._result_text(result)
        output_text_lower = output_text.lower()

        if verification_type == "non_empty_output":
            if output_text:
                return True, "Task returned non-empty output."
            return False, "Task returned empty output."

        if verification_type == "result_contains_all":
            values = verification.get("values", [])
            missing = [value for value in values if value.lower() not in output_text_lower]
            if not missing:
                return True, "Result contained all required markers."
            return False, f"Result missing required markers: {', '.join(missing)}"

        if verification_type == "result_contains_any":
            values = verification.get("values", [])
            if any(value.lower() in output_text_lower for value in values):
                return True, "Result contained an expected marker."
            return False, "Result did not contain any expected marker."

        if verification_type == "preview_payload":
            confirmation_phrase = verification.get("confirmation_phrase")
            if "items" not in result or "summary" not in result:
                return False, "Preview payload did not include items and summary."
            if result.get("confirmation_phrase") != confirmation_phrase:
                return False, "Preview payload returned an unexpected confirmation phrase."
            if "no files were moved yet." in output_text_lower or "no loose files needed to be moved." in output_text_lower:
                return True, "Preview confirmed a non-destructive result."
            if isinstance(result.get("items"), list):
                return True, "Preview payload contained reviewable items."
            return False, "Preview payload did not contain reviewable items."

        if verification_type == "path_exists":
            candidate = verification.get("path") or result.get("path") or result.get("source")
            if candidate and Path(candidate).exists():
                return True, "Verified that the target path exists."
            return False, "Expected path does not exist."

        if verification_type == "workspace_summary_payload":
            report = result.get("report")
            required_sections = verification.get("required_sections", [])
            if not isinstance(report, dict):
                return False, "Workspace summary payload is missing report data."
            missing = [section for section in required_sections if section not in report]
            if missing:
                return False, f"Workspace summary missing sections: {', '.join(missing)}"
            if not report.get("safe_folder_aliases"):
                return False, "Workspace summary did not include safe folder aliases."
            system_result = report.get("system_info", {}).get("result", "")
            if "platform" not in str(system_result).lower():
                return False, "Workspace summary did not include system info content."
            return True, "Workspace summary payload contained the required sections."

        if verification_type == "project_inspection_payload":
            inspection = result.get("inspection")
            required_sections = verification.get("required_sections", [])
            if not isinstance(inspection, dict):
                return False, "Project inspection payload is missing inspection data."
            missing = [section for section in required_sections if section not in inspection]
            if missing:
                return False, f"Project inspection missing sections: {', '.join(missing)}"
            if not Path(inspection["path"]).exists():
                return False, "Project inspection path does not exist."
            if not isinstance(inspection.get("total_files"), int) or not isinstance(inspection.get("total_directories"), int):
                return False, "Project inspection counts were not numeric."
            if "total files" not in output_text_lower or "total directories" not in output_text_lower:
                return False, "Project inspection output did not include file and directory counts."
            return True, "Project inspection payload contained the required structure."

        if verification_type == "folder_summary_payload":
            summary = result.get("summary")
            required_sections = verification.get("required_sections", [])
            if not isinstance(summary, dict):
                return False, "Folder summary payload is missing summary data."
            missing = [section for section in required_sections if section not in summary]
            if missing:
                return False, f"Folder summary missing sections: {', '.join(missing)}"
            if not Path(summary["path"]).exists():
                return False, "Folder summary path does not exist."
            numeric_fields = ("total_files", "total_directories", "total_size_bytes")
            if any(not isinstance(summary.get(field), int) for field in numeric_fields):
                return False, "Folder summary numeric fields were invalid."
            for marker in ("total files", "total directories", "top file types", "largest files", "newest files"):
                if marker not in output_text_lower:
                    return False, f"Folder summary output missing marker: {marker}"
            return True, "Folder summary payload contained the required structure."

        if verification_type == "organization_preview_payload":
            preview = result.get("preview")
            required_sections = verification.get("required_sections", [])
            if not isinstance(preview, dict):
                return False, "Organization preview payload is missing preview data."
            missing = [section for section in required_sections if section not in preview]
            if missing:
                return False, f"Organization preview missing sections: {', '.join(missing)}"
            if not Path(preview["path"]).exists():
                return False, "Organization preview path does not exist."
            if not isinstance(preview.get("category_counts"), dict):
                return False, "Organization preview category counts were invalid."
            if not isinstance(preview.get("sample_filenames"), dict):
                return False, "Organization preview sample filenames were invalid."
            if preview.get("scope") not in {"top_level_only", "recursive"}:
                return False, "Organization preview scope was invalid."
            for marker in ("total files analyzed", "top categories", "sample filenames", "no files were modified"):
                if marker not in output_text_lower:
                    return False, f"Organization preview output missing marker: {marker}"
            if preview.get("included_subfolders") and "nested files analyzed" not in output_text_lower:
                return False, "Recursive organization preview did not report nested file counts."
            return True, "Organization preview payload contained the required structure."

        return False, f"Unknown verification type: {verification_type}"

    def _result_text(self, result: dict):
        return str(result.get("result") or result.get("stdout") or "")

    def _persist_result_memory(self, task, task_result):
        if task.tool_name == "inspect_project":
            inspection = task_result.get("inspection")
            if isinstance(inspection, dict):
                project_name = inspection.get("project_name") or task.tool_input.get("project_name", "unknown_project")
                self.memory_manager.save_project_inspection(project_name, inspection)
                self.memory_manager.save_project_fact(project_name, "languages", inspection.get("languages", []))
                self.memory_manager.save_project_fact(project_name, "config_files", inspection.get("config_files", []))
                self.memory_manager.save_project_fact(project_name, "readme_files", inspection.get("readme_files", []))

    def _build_final_output(self, goal, tasks, results, success):
        verified_count = sum(1 for item in results if item.get("verified"))
        lines = [
            f"Goal: {goal}",
            "Observed facts:",
            f"- Planned tasks: {len(tasks)}",
            f"- Verified completed tasks: {verified_count}",
            f"- Unverified or failed tasks: {max(len(results) - verified_count, 0)}",
            "",
            plan_to_text(goal, tasks),
            "",
            "Execution results:",
        ]
        for item in results:
            task = item["task"]
            result = item["result"]
            observed = result.get("observed") or []
            if observed:
                summary = observed[0]
            else:
                summary = result.get("result") or result.get("error") or "No current analysis result is available."
            lines.append(
                f"- Task {task['id']} ({task['tool_name']}): {summary} "
                f"[verified={item['verified']}; attempts={item['attempts']}; reason={item['verification_reason']}]"
            )
            if result.get("warnings"):
                for warning in result["warnings"]:
                    lines.append(f"  warning: {warning}")
            if result.get("errors") and not item["verified"]:
                for error in result["errors"]:
                    lines.append(f"  error: {error}")
        lines.append("")
        lines.append("Outcome:")
        if success:
            lines.append("- The workflow reached verified completion for every planned task.")
        else:
            lines.append("- The workflow did not reach verified completion.")
        return "\n".join(lines)


class PlannerTaskAdapter:
    def __init__(self, id, title, tool_name, tool_input, verification, max_retries=0):
        self.id = id
        self.title = title
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.verification = verification
        self.max_retries = max_retries

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "verification": self.verification,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_task_record(cls, step):
        return cls(
            id=step["id"],
            title=step["title"],
            tool_name=step["tool_name"],
            tool_input=step.get("tool_input", {}),
            verification=step.get("verification", {"type": "non_empty_output"}),
            max_retries=step.get("max_retries", 0),
        )
