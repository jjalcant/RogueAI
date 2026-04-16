import unittest
from unittest.mock import patch

from result_contract import build_result, format_response_text
from ui_qt.backend import HANDLED, RogueBackendController


class QtBackendControllerTests(unittest.TestCase):
    def build_controller(self):
        messages = []
        statuses = []
        navigations = []
        controller = RogueBackendController(
            message_callback=messages.append,
            status_callback=lambda message, level: statuses.append((message, level)),
            navigation_callback=navigations.append,
        )
        return controller, messages, statuses, navigations

    def test_help_preview_model_contains_expected_sections(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        model = controller.build_help_preview_model()

        self.assertEqual("Rogue Help", model["title"])
        self.assertEqual(
            ["Navigation", "System", "Analysis", "Actions"],
            [section["title"] for section in model["sections"]],
        )

    def test_command_center_payload_surfaces_last_action_and_suggestions(self):
        controller, _messages, _statuses, _navigations = self.build_controller()
        controller.activity_history = [
            {
                "timestamp": "12:00:00",
                "kind": "command",
                "summary": "Executed scan desktop",
                "command": "scan desktop",
                "tool": "command_registry",
                "success": True,
            }
        ]
        active_task = {
            "task_id": 7,
            "goal": "Inspect Desktop",
            "status": "in_progress",
            "created_at": "2026-04-15T11:00:00",
            "updated_at": "2026-04-15T11:05:00",
            "current_step": 1,
            "steps": [{"title": "Inspect Desktop"}, {"title": "Summarize results"}],
            "completed_steps": [0],
            "failed_steps": [],
            "retry_counts": {},
            "verification_results": {},
            "final_summary": "",
        }
        with patch.object(
            controller,
            "get_agent_task_snapshot",
            return_value={
                "all_tasks": [active_task],
                "active_tasks": [active_task],
                "resumable_tasks": [],
                "recent_tasks": [active_task],
                "completed_tasks": [],
            },
        ):
            with patch.object(
                controller,
                "get_suggestion_payload",
                return_value={
                    "suggestions": [
                        {
                            "title": "Run Diagnostics",
                            "reason": "Backend looks unavailable",
                            "recommended_action": "Run Diagnostics",
                            "suggested_command": "diagnostics",
                        }
                    ]
                },
            ):
                payload = controller.get_command_center_payload()

        self.assertEqual("Executed scan desktop", payload["metrics"]["last_action"]["value"])
        self.assertEqual("Run Diagnostics", payload["suggested_actions"][0]["label"])
        self.assertIn("Backend looks unavailable", payload["suggested_actions_text"])
        self.assertIn("Task 7 [in_progress]", payload["active_tasks_text"])

    def test_command_center_payload_surfaces_operator_summary_fields(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        with patch.object(
            controller,
            "get_operator_summary",
            return_value={
                "current_mode": "agent_task",
                "current_mission": "Inspect Desktop",
                "runtime_health": {"label": "healthy"},
                "verification_status": "verified_success",
                "recommended_next_action": "Review the completed mission in Explain Mode.",
                "operator_summary_line": "Mode: agent_task | Mission: Inspect Desktop | Status: verified_success",
                "verification": {"status": "verified_success"},
            },
        ):
            payload = controller.get_command_center_payload()

        self.assertEqual("agent_task", payload["current_mode"])
        self.assertEqual("Inspect Desktop", payload["current_mission"])
        self.assertEqual("verified_success", payload["verification_status"])
        self.assertIn("Runtime health: healthy", payload["operator_summary_text"])
        self.assertIn("Inspect Desktop", payload["metrics"]["last_action"]["value"])

    def test_explain_mode_payload_uses_latest_agent_run(self):
        controller, _messages, _statuses, _navigations = self.build_controller()
        controller.conversation_memory = [{"role": "user", "content": "inspect desktop"}]
        controller.last_agent_workflow_payload = {
            "kind": "agent_run",
            "payload": {
                "success": True,
                "goal": "Inspect Desktop",
                "plan": [
                    {"title": "Inspect Desktop", "tool_name": "inspect_folder"},
                    {"title": "Summarize results", "tool_name": "generate_report"},
                ],
                "results": [
                    {
                        "task": {"title": "Inspect Desktop", "tool_name": "inspect_folder"},
                        "result": {"result": "Verified 10 files.", "warnings": []},
                        "verified": True,
                        "verification_reason": "Summary verified.",
                        "attempts": 1,
                    }
                ],
                "final_output": "Inspection completed successfully.",
                "suggestions": ["Open Friction Radar if this repeats."],
            },
        }

        with patch.object(
            controller,
            "get_operator_summary",
            return_value={
                "current_mode": "agent_task",
                "current_mission": "Inspect Desktop",
                "runtime_health": {"label": "healthy"},
                "verification_status": "verified_success",
                "recommended_next_action": "Review Friction Radar only if this repeats.",
                "verification": {"status": "verified_success"},
            },
        ):
            payload = controller.get_explain_mode_payload()

        self.assertEqual("Inspect Desktop", payload["last_goal"])
        self.assertIn("Inspect Desktop", payload["plan"])
        self.assertIn("Status: verified", payload["executed_steps"])
        self.assertEqual("Inspection completed successfully.", payload["result"])
        self.assertEqual("Review Friction Radar only if this repeats.", payload["next_recommendation"])
        self.assertEqual("agent_task", payload["operator_mode"])
        self.assertEqual("verified_success", payload["verification_status"])

    def test_friction_radar_payload_formats_real_summary_sections(self):
        controller, _messages, _statuses, _navigations = self.build_controller()
        summary = {
            "event_count": 3,
            "execution_enabled": True,
            "common_areas": [{"area": "chat_backend", "count": 2}],
            "top_candidates": [
                {
                    "id": "imp_1234",
                    "area": "chat_backend",
                    "symptom": "response too technical",
                    "score": 48,
                    "frequency": 3,
                    "impact": 2,
                    "ease": 8,
                }
            ],
            "recent_proposals": [
                {
                    "id": "imp_1234",
                    "title": "Simplify chat output formatting",
                    "status": "ready_for_review",
                    "risk": "low",
                    "recommended_action": "Add a wording guard.",
                    "confidence": {"score": 82, "level": "high"},
                    "safety": {"execution_allowed": True},
                }
            ],
            "pending_approvals": [{"title": "Simplify chat output formatting", "status": "ready_for_review"}],
            "execution_ready_proposals": [],
            "blocked_proposals": [],
            "recent_executions": [{"proposal_id": "imp_1234", "status": "executed", "validation_passed": True}],
            "recent_rollbacks": [],
            "confidence_scores": [{"proposal_id": "imp_1234", "score": 82, "level": "high", "status": "ready_for_review"}],
            "experiment_summaries": [],
            "improvement_stats": {"executed": 1, "rolled_back": 0, "blocked": 0},
        }
        with patch.object(controller, "get_improvement_dashboard_summary", return_value=summary):
            payload = controller.get_friction_radar_payload()

        self.assertIn("Events recorded: 3", payload["summary_text"])
        self.assertIn("chat_backend", payload["top_areas_text"])
        self.assertIn("response too technical", payload["top_candidates_text"])
        self.assertIn("ready_for_review", payload["recent_proposals_text"])
        self.assertIn("Pending approvals: 1", payload["approvals_text"])
        self.assertIn("imp_1234 | executed", payload["executions_text"])

    def test_execute_command_reports_unknown_command_cleanly(self):
        controller, messages, statuses, _navigations = self.build_controller()

        result = controller.execute_command("totally unknown")

        self.assertFalse(result)
        self.assertEqual(
            "Command Not Available\n\nSummary\n- Unknown command. Type help to see available commands.\n\nRecommendation\n- Open Help to review the supported desktop commands.",
            messages[-1]["message"],
        )
        self.assertEqual("error", statuses[-1][1])

    def test_execute_chat_input_records_user_and_runs_exact_command_response(self):
        controller, messages, _statuses, _navigations = self.build_controller()

        def fake_execute_command(_text, confirm_callback=None):
            controller.add_message("Rogue", "Exact command executed.")
            return True

        with patch.object(controller, "get_command_definition", return_value=object()):
            with patch.object(controller, "execute_command", side_effect=fake_execute_command):
                result = controller.execute_chat_input("status")

        self.assertTrue(result)
        self.assertEqual(
            [("You", "status"), ("Rogue", "Exact command executed.")],
            [(payload["sender"], payload["message"]) for payload in messages[-2:]],
        )

    def test_execute_chat_input_records_user_for_greeting_fallback(self):
        controller, messages, statuses, _navigations = self.build_controller()

        with patch.object(controller, "process_input", return_value="Router handled the request."):
            result = controller.execute_chat_input("hola")

        self.assertEqual("Router handled the request.", result)
        self.assertEqual(("You", "hola"), (messages[-2]["sender"], messages[-2]["message"]))
        self.assertEqual(
            "Command Result\n\nSummary\n- Router handled the request.\n\nRecommendation\n- Continue with the next command when ready.",
            messages[-1]["message"],
        )
        self.assertNotIn("Unknown command", messages[-1]["message"])
        self.assertEqual("done", statuses[-1][1])

    def test_execute_chat_input_records_user_for_unknown_non_empty_fallback(self):
        controller, messages, statuses, _navigations = self.build_controller()

        with patch.object(controller, "process_input", return_value="I did not recognize that command, but I can help."):
            result = controller.execute_chat_input("something odd")

        self.assertEqual("I did not recognize that command, but I can help.", result)
        self.assertEqual(("You", "something odd"), (messages[-2]["sender"], messages[-2]["message"]))
        self.assertEqual(
            "Command Result\n\nSummary\n- I did not recognize that command, but I can help.\n\nRecommendation\n- Continue with the next command when ready.",
            messages[-1]["message"],
        )
        self.assertEqual("done", statuses[-1][1])

    def test_execute_chat_input_registry_router_command_keeps_single_user_message(self):
        controller, messages, _statuses, _navigations = self.build_controller()

        with patch.object(controller, "process_input", return_value="Verified desktop summary is ready."):
            result = controller.execute_chat_input("scan desktop")

        self.assertTrue(result)
        self.assertEqual(1, len([payload for payload in messages if payload["sender"] == "You"]))
        self.assertEqual(
            [
                ("You", "scan desktop"),
                ("Rogue", "Command Result\n\nSummary\n- Verified desktop summary is ready.\n\nRecommendation\n- Continue with the next command when ready."),
            ],
            [(payload["sender"], payload["message"]) for payload in messages[-2:]],
        )

    def test_execute_chat_input_ignores_blank_text_without_recording_messages(self):
        controller, messages, statuses, _navigations = self.build_controller()

        result = controller.execute_chat_input("   \n  ")

        self.assertFalse(result)
        self.assertEqual([], messages)
        self.assertEqual("ready", statuses[-1][1])

    def test_run_router_command_unstructured_warning_uses_warning_status(self):
        controller, _messages, statuses, _navigations = self.build_controller()

        with patch.object(controller, "process_input", return_value="Warning: action skipped."):
            controller.run_router_command("skip action", show_user=False)

        self.assertEqual("warning", statuses[-1][1])

    def test_run_router_command_structured_failure_uses_error_status(self):
        controller, _messages, statuses, _navigations = self.build_controller()
        failure_payload = build_result(
            False,
            "scan_duplicates",
            result="",
            errors=["Folder not found."],
            observed=["I cannot confirm that yet."],
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = failure_payload
            return format_response_text(failure_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("scan duplicates in missing", show_user=False)

        self.assertEqual("error", statuses[-1][1])

    def test_run_router_command_formats_structured_summary_for_chat_and_keeps_workflow_details_for_agent(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "inspect_desktop",
            result="ignored raw structured text",
            observed=["Verified Desktop summary is available."],
            summary={
                "path": str(controller.home_path / "Desktop"),
                "total_files": 9595,
                "total_directories": 405,
                "total_size_human": "8.5 GB",
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("scan desktop", show_user=False)

        self.assertEqual(
            "Desktop Scan Complete\n\nSummary\n- Files: 9,595\n- Folders: 405\n- Total size: 8.5 GB",
            messages[-1]["message"],
        )
        self.assertIn("Action: inspect_desktop", controller.get_agent_view_payload()["workflow_text"])

    def test_run_router_command_uses_mapped_display_title_for_known_raw_command(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "scan downloads",
            observed=["Verified downloads summary is available."],
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("scan downloads", show_user=False)

        self.assertEqual(
            "Downloads Scan\n\nSummary\n- Verified downloads summary is available.",
            messages[-1]["message"],
        )

    def test_run_router_command_formats_structured_failure_as_single_clear_chat_message(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        failure_payload = build_result(
            False,
            "scan_duplicates",
            result="",
            errors=["Folder not found."],
            observed=["I cannot confirm that yet."],
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = failure_payload
            return format_response_text(failure_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("scan duplicates in missing", show_user=False)

        self.assertEqual("Scan Duplicates Failed\n\nSummary\n- Folder not found.", messages[-1]["message"])

    def test_run_router_command_failure_uses_normalized_known_command_title(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        failure_payload = build_result(
            False,
            "organize desktop",
            errors=["No verified folder target was available."],
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = failure_payload
            return format_response_text(failure_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("organize desktop", show_user=False)

        self.assertEqual(
            "Desktop Organization Failed\n\nSummary\n- No verified folder target was available.",
            messages[-1]["message"],
        )

    def test_run_router_command_failure_uses_safe_fallback_title_for_unknown_raw_phrase(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        failure_payload = build_result(
            False,
            "organize it",
            errors=["No verified folder target was available."],
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = failure_payload
            return format_response_text(failure_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("organize it", show_user=False)

        self.assertEqual(
            "Command Result Failed\n\nSummary\n- No verified folder target was available.",
            messages[-1]["message"],
        )

    def test_run_router_command_formats_system_info_using_verified_fields_only(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "system_info",
            result="ignored raw text",
            info={
                "Operating System": "Windows 11",
                "CPU": "AMD Ryzen Test CPU",
                "RAM": "32.0 GB",
                "GPU": ["NVIDIA Test GPU"],
                "Disk summary": "C:\\ | 200.0 GB used of 500.0 GB",
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("system info", show_user=False)

        self.assertEqual(
            "System Information\n\nSummary\n- Operating System: Windows 11\n- CPU: AMD Ryzen Test CPU\n- RAM: 32.0 GB\n\nDetails\n- GPU: NVIDIA Test GPU\n- Disk summary: C:\\ | 200.0 GB used of 500.0 GB",
            messages[-1]["message"],
        )
        self.assertNotIn("Observed facts", messages[-1]["message"])
        self.assertNotIn("[Insert", messages[-1]["message"])

    def test_run_router_command_system_info_falls_back_when_required_fields_are_missing(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "system_info",
            result="ignored raw text",
            info={
                "Operating System": "[Insert Operating System]",
                "CPU": "[Insert Processor type]",
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("system info", show_user=False)

        self.assertEqual(
            "Command Result\n\nSummary\n- System information command not available yet.\n- Available commands:\n- - system status\n- - scan desktop\n- - workspace summary\n\nRecommendation\n- Continue with the next command when ready.",
            messages[-1]["message"],
        )
        self.assertNotIn("[Insert", messages[-1]["message"])

    def test_run_router_command_formats_system_health_with_warning_and_recommendations(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "system_health",
            result="ignored raw text",
            warnings=["Disk usage is high"],
            inferences=["Storage pressure detected on the system drive"],
            suggestions=["Run System Info", "Run Scan Downloads"],
            health={
                "cpu_usage_percent": 18,
                "memory_usage_percent": 42,
                "disk_usage_percent": 91,
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("system health", show_user=False)

        self.assertEqual(
            "System Health\n\nSummary\n- CPU usage: 18%\n- Memory usage: 42%\n- Disk usage: 91%\n\nDetails\n- Storage pressure detected on the system drive\n\nWarning\n- Disk usage is high\n\nRecommendation\n- Run System Info\n- Run Scan Downloads",
            messages[-1]["message"],
        )

    def test_run_router_command_omits_missing_system_health_fields_without_placeholders(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "system_health",
            result="ignored raw text",
            inferences=["No critical performance issues detected"],
            health={
                "cpu_usage_percent": None,
                "memory_usage_percent": 42,
                "disk_usage_percent": 72,
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("system health", show_user=False)

        self.assertEqual(
            "System Health\n\nSummary\n- Memory usage: 42%\n- Disk usage: 72%\n\nDetails\n- No critical performance issues detected",
            messages[-1]["message"],
        )
        self.assertNotIn("CPU usage", messages[-1]["message"])
        self.assertNotIn("[Insert", messages[-1]["message"])

    def test_run_router_command_formats_storage_overview_using_normalized_sections(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "storage_overview",
            result="ignored raw text",
            suggestions=["Run Scan Downloads", "Review the largest files listed above"],
            storage={
                "drive_usage_percent": 72,
                "drive_free_human": "120.0 GB",
                "drive_total_human": "500.0 GB",
                "large_file_threshold_human": "100.0 MB",
                "largest_folders": [
                    {"name": "Downloads", "size_human": "80.0 GB"},
                    {"name": "Desktop", "size_human": "12.0 GB"},
                ],
                "large_files": [
                    {"name": "video.mkv", "size_human": "4.0 GB"},
                    {"name": "archive.zip", "size_human": "900.0 MB"},
                ],
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("storage overview", show_user=False)

        self.assertEqual(
            "Storage Overview\n\nSummary\n- Drive usage: 72%\n- Free space: 120.0 GB\n- Total disk size: 500.0 GB\n\nDetails\n- Largest folders: Downloads (80.0 GB), Desktop (12.0 GB)\n- Large files above 100.0 MB: video.mkv (4.0 GB), archive.zip (900.0 MB)\n\nRecommendation\n- Run Scan Downloads\n- Review the largest files listed above",
            messages[-1]["message"],
        )

    def test_run_router_command_omits_missing_storage_overview_fields_without_placeholders(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        structured_payload = build_result(
            True,
            "storage_overview",
            result="ignored raw text",
            storage={
                "drive_usage_percent": None,
                "drive_free_human": "120.0 GB",
                "drive_total_human": "",
                "largest_folders": [],
                "large_files": [],
            },
        )

        def fake_process_input(_text):
            controller.last_structured_response_payload = structured_payload
            return format_response_text(structured_payload)

        with patch.object(controller, "process_input", side_effect=fake_process_input):
            controller.run_router_command("storage overview", show_user=False)

        self.assertEqual(
            "Storage Overview\n\nSummary\n- Free space: 120.0 GB",
            messages[-1]["message"],
        )
        self.assertNotIn("Drive usage", messages[-1]["message"])
        self.assertNotIn("[Insert", messages[-1]["message"])

    def test_build_chat_response_text_hides_raw_agent_only_sections_from_chat(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        response = controller.build_chat_response_text("Action: inspect_desktop\nObserved facts:\n- verified")

        self.assertEqual("Response ready.", response)

    def test_build_chat_response_text_wraps_plain_text_in_operator_format(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        response = controller.build_chat_response_text("Router handled the request.\nVerified result is ready.")

        self.assertEqual(
            "Command Result\n\nSummary\n- Router handled the request.\n\nDetails\n- Verified result is ready.\n\nRecommendation\n- Continue with the next command when ready.",
            response,
        )

    def test_build_chat_response_text_infers_agent_result_success_from_verified_result(self):
        controller, _messages, _statuses, _navigations = self.build_controller()
        controller.last_agent_workflow_payload = {
            "kind": "agent_run",
            "payload": {
                "goal": "scan desktop",
                "success": False,
                "plan": [{"id": 1}],
                "results": [
                    {
                        "verified": True,
                        "result": {
                            "success": True,
                            "summary": {
                                "total_files": 12,
                                "total_directories": 3,
                                "total_size_human": "1.2 GB",
                            },
                        },
                    }
                ],
            },
        }

        response = controller.build_chat_response_text("ignored")

        self.assertEqual(
            "Desktop Scan Complete\n\nSummary\n- Files: 12\n- Folders: 3\n- Total size: 1.2 GB",
            response,
        )

    def test_show_folder_summary_section_uses_operator_response_format(self):
        controller, messages, _statuses, _navigations = self.build_controller()
        controller.last_agent_workflow_payload = {
            "kind": "agent_run",
            "payload": {
                "results": [
                    {
                        "result": {
                            "summary": {
                                "largest_files": [
                                    {"name": "video.mkv", "size_bytes": 4096},
                                    {"name": "archive.zip", "size_bytes": 1024},
                                ]
                            }
                        }
                    }
                ]
            },
        }

        result = controller.show_folder_summary_section("largest_files", "Largest Files")

        self.assertIs(HANDLED, result)
        self.assertEqual(
            "Largest Files\n\nSummary\n- Showing 2 verified items from the latest folder summary.\n\nDetails\n- video.mkv: 4096 bytes\n- archive.zip: 1024 bytes",
            messages[-1]["message"],
        )

    def test_execute_command_handler_exception_does_not_leak_raw_exception_text(self):
        controller, messages, statuses, _navigations = self.build_controller()
        definition = type("Definition", (), {"name": "scan desktop", "requires_confirmation": False})()

        with patch.object(controller, "get_command_definition", return_value=definition):
            with patch.object(controller, "log_action"):
                result = controller.execute_command("scan desktop")

        self.assertFalse(result)
        self.assertEqual(
            "Desktop Scan Failed\n\nSummary\n- The command could not be completed.\n\nDetails\n- A local desktop command handler raised an unexpected error.\n\nRecommendation\n- Retry the command once. If it keeps failing, review the Agent or diagnostics surfaces.",
            messages[-1]["message"],
        )
        self.assertEqual("error", statuses[-1][1])

    def test_run_router_command_internal_exception_uses_operator_failure_response(self):
        controller, messages, statuses, _navigations = self.build_controller()

        with patch.object(controller, "process_input", side_effect=RuntimeError("boom")):
            result = controller.run_router_command("organize desktop", show_user=False)

        self.assertEqual("The command could not be completed.", result)
        self.assertEqual(
            "Desktop Organization Failed\n\nSummary\n- The command could not be completed.\n\nDetails\n- The router raised an unexpected internal error while processing this request.\n\nRecommendation\n- Retry the command once. If it keeps failing, review the Agent or diagnostics surfaces.",
            messages[-1]["message"],
        )
        self.assertEqual("error", statuses[-1][1])

    def test_execute_command_help_navigates_without_rewriting_registry(self):
        controller, _messages, _statuses, navigations = self.build_controller()

        result = controller.execute_command("help")

        self.assertTrue(result)
        self.assertEqual(["help"], navigations)

    def test_theme_updates_settings_payload(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        controller.set_theme("dark")

        self.assertEqual("Dark", controller.get_settings_payload()["theme"])

    def test_quick_commands_use_title_case_labels(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        self.assertEqual(
            [
                "Scan Desktop",
                "Inspect Downloads",
                "Workspace Summary",
                "System Status",
                "Tasks",
                "Organize Desktop",
            ],
            [label for label, _command in controller.quick_commands],
        )

    @patch("ui_qt.backend.get_task")
    def test_copy_current_task_prompt_uses_clipboard_callback(self, mock_get_task):
        copied = []
        controller = RogueBackendController(clipboard_setter=copied.append)
        controller.active_task_context = {"id": 4, "prompt_text": "fix the bug"}

        payload = controller.copy_current_task_prompt()

        self.assertTrue(payload["success"])
        self.assertEqual(["fix the bug"], copied)
        self.assertIn("Copied current task 4 prompt", payload["result"])

    def test_build_command_envelope_respects_success_flag_when_present(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "system status",
            {"success": True, "result": "Verified system status is ready."},
        )

        self.assertTrue(envelope["ok"])
        self.assertEqual("System Status", envelope["title"])
        self.assertEqual("Verified system status is ready.", envelope["summary"])

    def test_build_command_envelope_error_flag_forces_failure(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "scan desktop",
            {"error": "Desktop path is unavailable."},
        )

        self.assertFalse(envelope["ok"])
        self.assertEqual("Desktop Scan Failed", envelope["title"])
        self.assertEqual("Desktop path is unavailable.", envelope["summary"])

    def test_build_command_envelope_zero_planned_and_verified_tasks_do_not_imply_success(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "scan downloads",
            {"result": "Verified downloads summary is ready."},
            planned_tasks=0,
            verified_tasks=0,
            default_ok=False,
        )

        self.assertFalse(envelope["ok"])
        self.assertEqual("Downloads Scan Failed", envelope["title"])

    def test_build_command_envelope_verified_result_still_implies_success(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "scan downloads",
            {"result": "Verified downloads summary is ready."},
            planned_tasks=0,
            verified_tasks=1,
            default_ok=False,
        )

        self.assertTrue(envelope["ok"])
        self.assertEqual("Downloads Scan", envelope["title"])

    def test_build_command_envelope_matching_planned_and_verified_tasks_infer_success(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "workspace summary",
            {"result": "Workspace summary is ready."},
            planned_tasks=3,
            verified_tasks=3,
            default_ok=False,
        )

        self.assertTrue(envelope["ok"])
        self.assertEqual("Workspace Summary", envelope["title"])

    def test_build_chat_response_text_wraps_plain_string_result_safely(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        response = controller.build_chat_response_text("Router handled the request.\nVerified result is ready.")

        self.assertEqual(
            "Command Result\n\nSummary\n- Router handled the request.\n\nDetails\n- Verified result is ready.\n\nRecommendation\n- Continue with the next command when ready.",
            response,
        )

    def test_build_command_envelope_failure_title_uses_normalized_operator_title(self):
        controller, _messages, _statuses, _navigations = self.build_controller()

        envelope = controller.build_command_envelope(
            "organize desktop",
            {"error": "No verified folder target was available."},
        )

        self.assertFalse(envelope["ok"])
        self.assertEqual("Desktop Organization Failed", envelope["title"])


if __name__ == "__main__":
    unittest.main()
