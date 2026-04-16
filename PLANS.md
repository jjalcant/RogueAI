# RogueAI Implementation Plan

## Phase 38. Operator Brain v1 orchestration layer

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Add a central orchestration layer above the existing router, planner, agent loop, tools, memory, and self-improvement systems
- Do not rewrite the planner, agent loop, tool registry, UI frameworks, or self-improvement stack
- Limit this pass to additive, reversible coordination modules plus light backend integration:
- new modules:
- `operator_brain.py`
- `runtime_state.py`
- `operator_modes.py`
- `decision_policy.py`
- `verification_policy.py`
- optional helper module only if it reduces duplication cleanly:
- `mission_control.py`
- existing files to extend only where needed:
- `rogue_app.py`
- `ui_qt/backend.py`
- focused tests only

### Audit

- The supported launcher path is already stable:
- `start_rogue.bat`
- `rogue_app.py`
- `brain.py`
- The project already contains the required execution subsystems:
- router in `brain/router.py`
- planner in `planner.py`
- agent execution in `agent_loop.py`
- persistent task state in `task_manager.py`
- memory handling in `memory_manager.py` plus `memory/`
- self-improvement wiring in `improvement_runtime.py`
- The Qt backend already exposes operator-style payload surfaces for:
- `Command Center`
- `Explain Mode`
- `Friction Radar`
- The safest integration point is a thin coordinator that:
- snapshots runtime state before action
- classifies the request into a conservative operating mode
- chooses an existing execution path
- normalizes verification before UI status is shown
- routes repeated friction into the existing improvement observer
- publishes one structured operator summary for UI/backend consumption

### Minimal Fix Scope

- Create explicit operating-mode definitions for:
- `chat`
- `direct_command`
- `agent_task`
- `diagnostic`
- `improvement_review`
- `experiment_review`
- `safe_mode`
- Add a reusable runtime-state snapshot that reports:
- backend/model availability
- tools availability
- memory status
- active and resumable tasks
- recent failures
- last action
- self-improvement summary
- approval queue summary
- experiment summary
- Add a simple inspectable decision policy that chooses between:
- direct response
- router/direct command handling
- planner + agent loop
- diagnostics/status path
- improvement review
- safe/proposal-only behavior
- Add a verification policy that normalizes final operator-facing result status into:
- `verified_success`
- `partial_success`
- `blocked`
- `failed`
- `ready`
- Add mission summary assembly for operator-facing UI consumption:
- goal
- chosen mode
- execution path
- verification result
- recommendation
- improvement signal
- Integrate the new summary into existing backend/UI payload builders without redesigning views

### Validation

- Run focused `unittest` coverage for:
- mode selection
- runtime-state assembly
- decision routing
- verification normalization
- improvement routing triggers
- backend summary exposure
- Run `python -m py_compile` on new modules and touched backend files
- Run focused end-to-end request handling through the supported runtime code path where practical
- Record remaining risks and any deferred integration edges in `STATUS.md`

### Completion Status

- [x] Operator modes added
- [x] Runtime state snapshot added
- [x] Decision policy added
- [x] Verification policy added
- [x] Operator Brain integrated into backend request handling
- [x] Operator summary exposed to existing UI payloads
- [x] Focused tests added and passing
- [x] Remaining risks documented

## Phase 37. Qt Command Center exposure for self-improvement surfaces

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Fix the visible desktop UI only; do not rebuild or duplicate the existing self-improvement backend
- Make the current Qt shell expose the already-implemented improvement stack through:
- `Command Center`
- `Explain Mode`
- `Friction Radar`
- Keep Chat available, but no longer as the only dominant landing experience
- Limit the implementation surface to:
- `rogue_app.py`
- `ui_qt/main_window.py`
- `ui_qt/backend.py`
- `ui_qt/sidebar.py`
- new focused Qt view/helper modules only where needed
- focused lightweight Qt/backend tests

### Audit

- The supported launcher still enters through `rogue_app.py`, but the visible desktop shell is the Qt path when `PySide6` is available
- The Qt shell currently starts on `chat` and only exposes `Chat`, `Agent`, `Help`, and `Settings`
- The self-improvement backend already exists and is integrated in the Tk entrypoint path:
- `improvement_observer.py`
- `improvement_engine.py`
- `improvement_planner.py`
- `improvement_guard.py`
- `improvement_approval.py`
- `improvement_executor.py`
- `improvement_experiments.py`
- `rogue_app.py` already contains a real improvement dashboard summary builder
- The Qt backend controller currently owns the live state we need for UI exposure:
- backend/model status
- task snapshots
- activity history
- latest router payloads
- latest agent workflow payloads
- suggestions
- The safest fix is to reuse the existing improvement modules and existing controller state, then add small read-only UI surfaces for those summaries

### Minimal Fix Scope

- Extract or reuse the existing improvement summary assembly so the Qt shell and desktop entrypoint share the same summary source instead of duplicating logic
- Add a default `Command Center` view to the Qt shell that shows:
- system status
- backend/model state
- tools/memory state
- last action
- quick actions
- suggested actions
- active/recent tasks
- recent events
- Add visible navigation items for:
- `Explain Mode`
- `Friction Radar`
- Add an `Explain Mode` surface backed by existing agent/router payloads for:
- last goal
- plan
- executed steps
- result
- warnings/failures
- next recommendation
- Add a `Friction Radar` surface backed by the real improvement summary for:
- top friction areas
- top improvement candidates
- recent proposals
- approval status
- recent executions / rollbacks
- confidence / risk
- experiment summaries when available
- Provide clean empty states when no real data exists
- Preserve copy/select behavior, scrolling, and the current router/tool execution paths

### Validation

- Run `python -m py_compile` on touched desktop UI/backend files and focused tests
- Run focused `unittest` coverage for the new summary mapping helpers and Qt navigation/default-view behavior
- Run an offscreen Qt smoke launch through the supported entrypoint modules
- Record any remaining UI/runtime limits in `STATUS.md`

### Completion Status

- [x] Shared improvement summary source reused by the desktop/UI layers
- [x] Qt shell lands on `Command Center` instead of `Chat`
- [x] Visible navigation added for `Explain Mode` and `Friction Radar`
- [x] Real improvement data shown with clean empty states
- [x] Focused tests added and passing
- [x] Offscreen Qt smoke launch completed
- [x] Remaining risks documented

## Phase 36. Self-improvement layer v2.5 controlled execution

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Extend the existing self-improvement v1 backend instead of creating a parallel app or rewrite
- Limit this pass to conservative, auditable additions around the current observer -> engine -> planner -> guard flow:
- new modules:
- `improvement_approval.py`
- `improvement_executor.py`
- `improvement_experiments.py`
- existing modules to extend only where needed:
- `improvement_planner.py`
- `improvement_guard.py`
- `improvement_storage.py`
- `rogue_app.py`
- `tests/test_improvement_layer.py`
- Preserve the router, agent loop, tool registry, supported launcher path, and desktop UI architecture

### Audit

- v1 already provides append-only friction observation, candidate ranking, proposal generation, advisory safety evaluation, and dashboard summary generation
- The clean extension seam is the proposal lifecycle itself:
- `ImprovementPlanner` can enrich proposals with confidence, patch category, and validation hints
- `ImprovementGuard` can remain the single conservative gate for execution allowlisting and scope limits
- `rogue_app.py` already exposes one backend-first improvement summary method that can expand without a UI rewrite
- The current storage layer is small, local, JSON-based, and already tolerant of malformed data, which matches the new approval, patch-result, and experiment persistence needs
- The safest execution model is not autonomous synthesis; it is an explicit executor that only applies structured, approved, allowlisted patch plans with backup, diff, validation, and rollback

### Minimal Fix Scope

- Extend proposal generation to include:
- `patch_category`
- `patch_strategy`
- compact `validation_plan`
- proposal confidence score and factor breakdown
- Add a local approval queue that supports:
- `proposed`
- `ready_for_review`
- `approved`
- `blocked`
- `executed`
- `rolled_back`
- Keep approval storage backend-local and UI-ready without implementing a full new UI surface
- Add a controlled executor that:
- requires approved proposal state
- requires guard approval
- supports dry-run mode
- creates backups before writes
- generates a compact diff summary
- runs lightweight targeted validation
- rolls back automatically on validation failure
- records all outcomes to patch-result history
- Keep execution limited to small structured operations for allowlisted categories only:
- `normalization_fix`
- `wrapper_addition`
- `guard_clause`
- `text_update`
- `config_update`
- `test_addition`
- Block execution for dependency changes, framework shifts, broad refactors, secret/security-sensitive edits, broad UI rewrites, file moves, arbitrary command generation, and unrestricted synthesis
- Add a minimal experiment manager for backend-first A/B tracking of small variants, usage counts, simple metrics, and winner selection without auto-shipping winners
- Expand the existing improvement dashboard summary with:
- pending approvals
- execution-ready proposals
- recent executions
- recent rollbacks
- blocked proposals
- confidence scores
- experiment summaries
- simple known improvement outcome metrics

### Validation

- Run `python -m py_compile` on the touched improvement modules, `rogue_app.py`, and focused tests
- Run focused unittest coverage for the improvement layer and nearby runtime seams
- Exercise at least one end-to-end approved improvement execution path in tests, including rollback-on-failure behavior
- Record any residual limitations or unsupported execution categories in `STATUS.md`

### Completion Status

- [x] Added approval-aware proposal lifecycle storage and helper methods
- [x] Added confidence scoring and readiness gating to improvement proposals
- [x] Added the controlled executor with dry-run, backup, diff, validation, and rollback
- [x] Added the minimal experiment manager and dashboard summaries
- [x] Preserved the supported runtime path and existing architecture
- [x] Added focused executor/approval/experiment regression coverage
- [x] Completed compile and targeted unittest validation
- [x] Documented remaining risks and how to disable execution mode

## Phase 35. Self-improvement layer v1 foundation

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit this pass to a small additive backend self-improvement pipeline and a few high-value hooks:
- new modules:
- `improvement_observer.py`
- `improvement_engine.py`
- `improvement_planner.py`
- `improvement_guard.py`
- optional shared support only if needed for clean separation
- focused integrations in:
- `tool_registry.py`
- `agent_loop.py`
- `brain/router.py`
- `rogue_app.py`
- focused tests in `tests/`
- Preserve the existing router, planner, agent loop, desktop UI, and tool architecture

### Audit

- The current codebase records execution and activity history, but it does not yet convert repeated friction into an inspectable improvement backlog
- The smallest stable insertion points are already present:
- `ToolRegistry.invoke()` for concrete tool execution failures
- `AgentLoop.run()` for retries, verification failures, and failed task execution
- `rogue_app.py` for explicit user-correction signals, async fallback routing, and warning-class chat outcomes
- The safest storage location is the existing `memory/` tree, using append-only JSONL for raw events plus small JSON snapshots for candidates/history
- A safe v1 should prepare structured proposals and future execution hooks without performing broad autonomous editing

### Minimal Fix Scope

- Add a lightweight observer that normalizes and appends friction events to `memory/improvement_log.jsonl`
- Add a simple engine that groups repeated events by stable keys, estimates `ease`, computes `score = frequency * impact * ease`, and writes candidate snapshots to `memory/improvement_candidates.json`
- Add a planner that converts high-value candidates into small, concrete, execution-ready proposals and records them in `memory/improvement_history.json`
- Add a guard that evaluates proposal safety and blocks:
- out-of-scope file writes
- credentials/security file touching
- broad dependency or framework changes
- large refactors
- auto-execution without explicit safety approval
- Expose one clean improvement-summary method suitable for later UI use without requiring a UI rewrite now
- Keep integration intentionally limited to high-value backend seams instead of adding logging calls throughout the codebase
- Add focused tests for event logging, malformed input tolerance, clustering/scoring, proposal generation, and safety decisions

### Validation

- Run `python -m py_compile` on the new modules plus touched integration files and focused tests
- Run focused `unittest` modules for:
- improvement layer
- agent loop
- tool registry
- router
- launcher/runtime path smoke where practical
- Exercise at least one end-to-end workflow through the supported backend path without changing the launcher contract

### Completion Status

- [x] Added the self-improvement v1 observer, engine, planner, and guard modules
- [x] Integrated the layer only at the identified high-value seams
- [x] Kept all raw friction storage append-only and inspectable under `memory/`
- [x] Added focused regression coverage without broad test bloat
- [x] Validated compile, tests, and one end-to-end workflow path
- [x] Documented remaining limits and future v2 patch-executor hooks

## Phase 34. Qt backend command-envelope normalization

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit this pass to the backend Chat response boundary and focused regression coverage:
- `ui_qt/backend.py`
- `tests/test_ui_qt_backend.py`
- Preserve the existing PySide6, router, planner, and tool architecture

### Audit

- The Qt backend still allows raw command result shape drift to reach Chat:
- plain strings
- partial dicts
- structured task payloads
- implicit failures inferred from inconsistent fields
- This causes false `... Failed` titles, unstable summaries, and formatter inconsistency at the final desktop render seam
- The safest insertion point is the existing `build_chat_response_text()` path in `ui_qt/backend.py`, because it is already the last backend step before Chat rendering

### Minimal Fix Scope

- Add a small internal command-envelope helper in `ui_qt/backend.py` that normalizes raw command results into one backend shape:
- `ok`
- `title`
- `summary`
- `details`
- `recommendation`
- `raw`
- Reuse the existing command-title normalization mapping instead of introducing a new naming system
- Respect explicit success/error fields first, then infer success from verified/planned task counts where available
- Keep agent/debug raw payloads intact for non-Chat surfaces, but require Chat rendering to use the normalized envelope only
- Add focused tests for:
- explicit success flag
- explicit error flag
- verified-task success inference
- planned/verified equality success inference
- safe wrapping of plain strings
- normalized failure titles

### Validation

- Run `python -m py_compile ui_qt\\backend.py tests\\test_ui_qt_backend.py`
- Run `python -m unittest tests.test_ui_qt_backend`

### Completion Status

- [x] Added a small internal command-envelope normalization layer in `ui_qt/backend.py`
- [x] Routed the backend Chat formatting boundary through the normalized envelope
- [x] Preserved agent/debug raw payloads through the envelope `raw` field
- [x] Added the six focused backend normalization regression tests
- [x] Focused compile and unittest validation passed

## Phase 33. Qt backend command-result success inference hardening

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit this pass to the Qt backend command-result labeling seam and one focused regression test
- Preserve the existing formatter and operator response structure

### Audit

- `ui_qt/backend.py` currently labels some agent-run responses from the top-level payload success flag even when the concrete command result shows success
- This can surface `... Failed` titles for successful command details, which is misleading in the Qt chat surface
- The safest insertion point is a small success inference helper used only when composing backend result titles

### Minimal Fix Scope

- Add a small backend helper that infers success from the concrete result first, then safe task-count signals, before falling back to the broader payload flag
- Apply that helper to the agent-run chat response path without rewriting the formatter
- Add a unit test that reproduces a false-failure title and proves the corrected success label

### Validation

- Run `python -m py_compile` on the touched backend and test modules
- Run the focused Qt backend unit test module

### Completion Status

- [x] Added a small Qt backend success inference helper without rewriting the formatter
- [x] Applied the helper only to agent-run result title composition
- [x] Added a focused regression test for successful results previously labeled as failed
- [x] Validation passed for the touched backend and test module

## Phase 32. Strict stabilization self-review containment

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit this pass to a strict self-review of the already-touched Qt response seam and focused tests
- Preserve the current PySide6, router, registry, and backend architecture

### Audit

- Exact registry commands can still re-enter `run_router_command(..., show_user=True)` through `run_registered_router_command()`, which risks duplicating the visible user message after the shared chat submission path already inserted it
- `show_folder_summary_section()` still writes raw list text directly into Chat instead of using the operator response formatter, which is a remaining formatter bypass on the main Chat surface
- Existing typewriter and scroll behavior already have focused coverage and do not currently show a nearby smaller or safer containment change

### Minimal Fix Scope

- Keep registry-backed router commands on the already-established chat submission path by suppressing redundant user-message reinsertion inside `run_registered_router_command()`
- Convert folder-summary section chat output to the existing operator response format without changing the surrounding navigation or summary lookup flow
- Add focused tests for:
- registry-backed command execution without duplicate user insertion
- folder-summary section formatting without raw list-text leakage

### Validation

- Run `python -m py_compile` on touched backend and test modules
- Run focused Qt/backend test subsets covering the reviewed seams

## Phase 31. Qt stabilization and operator-response hardening

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit the pass to the active Qt render/response path and one bounded filesystem safety seam:
- `ui_qt/backend.py`
- `ui_qt/main_window.py`
- `tools/files_tool.py`
- focused tests in `tests/`
- Preserve the existing PySide6 shell, router, planner, agent, and tool architecture

### Audit

- The main typed-chat path is stable, but quick action buttons still use a different execution path than typed commands and therefore miss the same pending/typewriter flow
- Several desktop command handlers in `ui_qt/backend.py` still add raw tool/diagnostic strings directly into Chat, bypassing the operator formatter
- Registry and router exception handling can still expose raw exception text in Chat instead of operator-style failure responses
- Plain-text fallback responses can still reach Chat without Rogue response sections when no structured payload is present
- The active duplicate-scan implementation in `tools/files_tool.py` still performs an unbounded recursive file collection before hashing, which can become slow and unpredictable on large folders

### Minimal Fix Scope

- Unify quick action execution with the typed-chat submission path so both produce the same user bubble, pending state, and normalized final Chat response
- Add a small backend helper for operator-grade Chat messages and use it on the existing direct-to-chat desktop command handlers instead of raw message injection
- Normalize local command and exception failures into operator-style Chat responses without exposing raw trace-like text in the main Chat surface
- Wrap plain-text fallback responses in Rogue response sections only when they are not already operator-formatted
- Add a bounded duplicate-scan helper that stops after a safe file limit and reports truncation deterministically instead of scanning indefinitely

### Validation

- Run `python -m py_compile` on touched backend, window, files-tool, and test modules
- Run focused tests for:
- backend operator-response normalization
- quick-action path consistency
- bounded duplicate scanning
- Record validation results and remaining risk in `STATUS.md`

### Completion Status

- [x] Quick action buttons now use the same chat submission flow as typed commands
- [x] Direct desktop command handlers no longer inject raw status/task/memory/stub strings into Chat
- [x] Registry and router internal failures now return operator-style Chat failures instead of raw exception text
- [x] Plain-text fallback responses are wrapped into Rogue response sections when no structured payload exists
- [x] Duplicate scanning is bounded and reports truncation deterministically

## Phase 30. Pronoun-safe organize routing and chat title cleanup

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit the change set to the active router and PySide6 chat presentation seam:
- `brain/router.py`
- `ui_qt/backend.py`
- `ui_qt/chat_view.py`
- focused router/backend/chat tests
- Preserve the existing PySide6 architecture, router flow, planner/agent execution path, and response contract

### Audit

- Natural-language organization requests currently pass conversational targets such as `it` through to the existing folder workflow, which lets downstream logic treat the pronoun as a literal target
- The active Qt chat intro card in `ui_qt/chat_view.py` still shows `Operator console`, which is product-hostile wording for the main operator response surface
- The Qt backend title helper in `ui_qt/backend.py` still derives some chat titles too directly from raw command phrasing, which can surface awkward titles such as `Organize It Failed`
- The smallest safe insertion points are:
- router-side target normalization before agent dispatch
- the chat intro copy in `ui_qt/chat_view.py`
- the backend display-title helper used by structured and agent chat summaries

### Minimal Fix Scope

- Add a small router helper that treats conversational pronouns such as `it`, `this`, `that`, `them`, `these`, and `those` as references, not literal folder targets
- Reuse stored verified folder context only when a prior successful verified folder result exposed a concrete path
- If no verified folder context exists, return a deterministic operator-facing organize-target guidance response without guessing a folder
- Replace the visible `Operator console` wording with a clean operator-facing chat title/subtitle in `ui_qt/chat_view.py`
- Add a small normalized command-display title map in `ui_qt/backend.py` for the requested command phrases and use it for success/failure chat titles
- Keep unknown raw command phrasing on a safe fallback title instead of mirroring awkward user wording

### Validation

- Run `python -m py_compile` on the touched router, backend, chat-view, and test modules
- Run focused unit tests for:
- pronoun-safe organize routing
- backend title normalization
- chat intro copy
- Record validation results and any remaining risk in `STATUS.md`

### Completion Status

- [x] Pronoun-based organize requests no longer fall through as literal folder targets
- [x] Verified folder context is reused only when a prior successful verified folder result exposed a concrete target
- [x] Missing organize target now fails with a clean operator-facing response
- [x] Chat intro copy no longer shows `Operator console`
- [x] Known backend command titles normalize to operator-facing display names
- [x] Unknown raw command phrasing now falls back safely instead of echoing awkward titles

## Current Architecture

- Official launcher: `start_rogue.bat`
- Desktop entrypoint: `rogue_app.py`
- Optional CLI support: `brain.py`
- Intent routing: `brain/router.py`
- Agent planning: `planner.py`
- Agent task state: `task_manager.py`
- Agent execution: `agent_loop.py`
- Agent tool registry: `tool_registry.py`
- Agent memory abstraction: `memory_manager.py`
- Agent execution logging: `execution_logger.py`
- Agent status updates: `status_reporter.py`
- LLM fallback bridge: `brain/llm_bridge.py`
- Memory persistence: `memory/memory_store.py`
- Move history: `memory/move_history.py`
- Engineering task queue: `tasks/task_queue.py`
- Tools: `tools/files_tool.py`, `tools/system_tool.py`, `tools/browser_tool.py`, `tools/projects_tool.py`
- Startup validation: `app_config.py`
- Existing tests cover router, tools, startup/config, memory, move history, task queue, planner, tool registry, execution logging, status reporting, and agent loop

## Phase 29. PySide6 UI hardening and real system info command

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit the change set to the active Qt shell, router aliases, and tool registration
- Preserve the existing PySide6 layout, backend routing, planner, tool registry, verification flow, and agent/Chat view separation

### Audit

- The header in `ui_qt/main_window.py` still exposes framework text (`PySide6 operator console`) instead of the product-facing subtitle
- The Qt backend chat summarizer in `ui_qt/backend.py` can fall back to generic structured output text instead of enforcing verified-field-only rendering for system data
- The existing system info implementation lives in `tools/system_tool.py` as `get_system_info`, but it currently returns only a small platform snapshot and is not standardized as a dedicated `system_info` tool entry
- `brain/router.py` already recognizes `system info`, but it does not include the requested aliases (`pc info`, `computer info`, `system specs`) and still routes through the legacy import path
- `ui_qt/chat_view.py` preserves scroll position intelligently, but append/update timing can still leave the transcript slightly above the true bottom after layout updates
- Quick command labels are still lower-case command phrases in the Qt backend payload instead of normalized title-case UI labels

### Minimal Fix Scope

- Update the header subtitle to `Local System Intelligence` and remove framework names from the UI surface
- Harden Chat summaries so system data is rendered only from verified payload fields
- If required verified system fields are missing, return a deterministic guidance message instead of placeholders or guessed values
- Add `tools/system_info.py` for richer verified machine data using standard-library collection with optional local enhancement where available
- Register both `system_info` and legacy-compatible `get_system_info` tool names in `tool_registry.py`
- Extend router aliases for `pc info`, `computer info`, `system specs`, and `system info`
- Force transcript scrolling to the real bottom after layout updates when the user is already at the bottom
- Normalize quick command button labels to title case without changing their routed command text
- Keep Agent-only workflow layers out of Chat summaries

### Validation

- Run `python -m py_compile` on every modified module
- Run focused Qt, router, tool-registry, and system-info tests
- Exercise the `system info` command path and confirm it returns real machine fields
- Record remaining risk, if any, in `STATUS.md`

### Completion Status

- [x] Header subtitle updated with no framework name in the UI
- [x] Chat system-info rendering limited to verified payload fields
- [x] Placeholder system data blocked with deterministic fallback guidance
- [x] Dedicated `tools/system_info.py` added and registered
- [x] Router aliases added for `pc info`, `computer info`, `system specs`, and `system info`
- [x] Bottom scroll anchoring hardened after layout updates
- [x] Quick-command labels normalized to title case
- [x] Focused compile and unit-test validation completed

## Phase 28. PySide6 transcript ordering fix

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit the change to the existing Qt chat submit path in:
- `ui_qt/chat_view.py`
- `ui_qt/main_window.py`
- `ui_qt/backend.py`
- focused Qt tests
- Preserve current PySide6 layout, styling, selectable transcript widgets, backend routing, and fallback behavior

### Audit

- Active typed chat submissions currently create a transient Rogue pending row in `ui_qt/chat_view.py` before backend dispatch
- The typed-submit backend path in `ui_qt/backend.py` does not currently record or emit the user message for exact-command execution, and explicitly suppresses the user message on router fallback via `show_user=False`
- That split allows conversational fallback inputs such as greetings to render a Rogue reply without the corresponding user text appearing first in the transcript
- Quick-command buttons already use `run_router_command(..., show_user=True)` and are not the primary defect path

### Minimal Fix Scope

- Append every non-empty typed user submission to the visible transcript before pending feedback or backend routing
- Record the same typed submission in backend message history without duplicating the visible Qt transcript row
- Keep blank and whitespace-only suppression unchanged
- Preserve exact-command execution, natural-language routing, greeting handling, and unknown-input fallback behavior
- Add regression tests for:
- exact command transcript ordering
- greeting transcript ordering
- unknown non-empty transcript ordering
- blank-input no-op behavior

### Validation

- Run targeted Qt/backend unit tests covering the submit path
- Run `python -m py_compile` on touched Qt modules and tests
- Record any residual risk in `STATUS.md`

## Phase 27. PySide6 stability and bug-fix pass

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Limit the pass to stabilization of the active Qt shell under `ui_qt/`
- Preserve backend routing, tool execution, agent logic, and anti-hallucination safeguards
- Do not redesign the app and do not add feature work

### Audit

- Active PySide6 launcher path is `start_rogue.bat` -> `rogue_app.py` -> `ui_qt.main_window.launch_qt_app()`
- Current Qt chat flow is split across:
- `ui_qt/main_window.py`
- `ui_qt/chat_view.py`
- `ui_qt/backend.py`
- Typed chat submissions currently go through registry-only execution, while quick commands use router execution directly
- That split is a likely source of false `Unknown command` chat replies for router-valid commands typed into the main chat input
- Current status handling still derives global banner state from per-command feedback, and router warnings can be escalated into `ERROR` too aggressively
- Transcript rendering already moved to per-message widgets, but scroll anchoring and submission guarding still need edge-case hardening
- Chat/help/agent output panes are already close to copy/select capable, so the safest path is focused fixes plus regression tests rather than UI replacement

### Minimal Fix Scope

- Add a dedicated Qt chat submission path that:
- ignores blank and placeholder-only text
- prevents duplicate same-turn submission
- prefers registered desktop commands when present
- falls back to router execution for valid non-registry chat commands
- Tighten chat transcript behavior in `ui_qt/chat_view.py`:
- keep a single clear transcript/output surface
- stabilize top/bottom scroll anchoring during pending-state swaps and animation updates
- prevent misplaced response animation or stale pending rows
- Harden status/banner correctness:
- keep the top-right banner limited to stable app states
- only surface `ERROR` for verified failures
- keep transcript content and internal detail text out of the global banner
- Verify copy/select usability across Chat, Help, Agent, and Settings views without altering the layout architecture
- Add lightweight UI-state logging only where it helps diagnose incorrect command-routing or status transitions

### Stability Checklist

- [x] PySide6 app launches through `start_rogue.bat` / `rogue_app.py`
- [x] Blank or placeholder input is ignored
- [x] Duplicate same-turn submit is blocked
- [x] Registry commands still work
- [x] Router-valid typed commands no longer trigger false `Unknown command`
- [x] Chat transcript uses one clear response surface
- [x] Pending/animated response stays in the chat transcript only
- [x] Scroll remains stable at top and bottom edges during updates
- [x] Header status reflects real app state without raw transcript/log text
- [x] Chat/help/output text remains selectable and copyable
- [x] Chat, Agent, Help, and Settings remain navigable and stable

### Validation

- Run targeted Qt unit tests before and after the fix pass to confirm the current baseline and the repaired behavior
- Run `python -m py_compile` over touched Qt modules and tests
- Run a non-interactive offscreen Qt smoke launch through the supported entrypoint where feasible
- Record remaining risks, if any, in `STATUS.md`

## Phase 25. PySide6 chat response feedback

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Scope the change to the active PySide6 chat surface only:
- `ui_qt/chat_view.py`
- `ui_qt/main_window.py`
- focused Qt tests
- Preserve backend behavior in `ui_qt/backend.py`:
- no command routing changes
- no tool execution changes
- no fabricated response text
- Add immediate lightweight transcript feedback when a chat command is submitted so the UI feels responsive before the verified backend text arrives
- Use short, deterministic pending labels derived from the submitted command where safe, such as:
- `Thinking...`
- `Analyzing desktop...`
- `Checking system status...`
- `Generating report...`
- Replace the pending state only when real backend text exists, then render that verified text progressively in subtle chunks
- Keep the transcript stable and selectable by retaining the final rendered text in the existing chat surface after animation completes
- Ensure commands that navigate views or otherwise do not emit a chat reply do not leave stale pending placeholders behind
- Add focused validation for:
- pending-state insertion
- progressive reveal completing to the exact backend text
- placeholder cleanup for no-reply command paths
- offscreen Qt smoke execution staying stable

## Phase 26. PySide6 chat animation stability

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Preserve backend/controller behavior and the current operator-console styling while fixing the UI-only animation defect
- Replace the current full-transcript `QTextBrowser` repaint loop with per-message transcript rendering so only the newest Rogue response block updates during typing
- Keep the temporary thinking state, but stop rebuilding or clearing older chat messages while the newest response animates
- Stabilize scroll behavior:
- autoscroll only when the user is already near the bottom
- do not force-scroll when the user is reading earlier transcript content
- avoid the bottom-edge jump caused by repeated full transcript resets
- Keep the typewriter effect lightweight and professional:
- reveal in chunks or line-aware segments
- animate only verified backend text
- clamp animation for very large outputs so long technical reports remain usable
- Add focused Qt validation for:
- newest-message-only animation
- no stale pending state
- large output fast-path behavior
- transcript stability under offscreen Qt smoke execution

## Phase 24. PySide6 launcher interpreter repair

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Audit the desktop startup path for interpreter drift between the active shell Python and the repo-local `.venv`
- Fix the launcher at the smallest safe surface so Rogue does not force a `.venv` interpreter that cannot import the Qt launcher when the active interpreter can
- Preserve the existing backend split:
- prefer PySide6 when the selected interpreter can import the Qt shell
- keep Tkinter as the legacy fallback only when Qt is truly unavailable
- Narrow the Qt fallback detection in `rogue_app.py` so only genuine `PySide6` import failures trigger the Tk path
- Print the real Qt import/startup exception before fallback or re-raise so startup defects are visible instead of being mislabeled as `PySide6 unavailable`
- Add focused launcher tests covering:
- genuine `PySide6`-missing fallback
- non-PySide module import errors propagating normally
- Qt startup exceptions being surfaced instead of silently falling back
- Validate with targeted unit tests plus interpreter/import smoke checks for both the active Python and `.venv`

## Phase 23. PySide6 desktop migration

- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Preserve the current backend architecture and behavior:
- `brain/router.py`
- `ui_command_registry.py`
- `planner.py`
- `task_manager.py`
- `agent_loop.py`
- `tool_registry.py`
- existing tools and memory modules
- Add a new side-by-side Qt UI layer under `ui_qt/` instead of rewriting the backend or deleting the current Tkinter implementation
- Build a Qt-compatible desktop controller that reuses the existing router, startup checks, settings, model status lookup, activity tracking, and autonomous loop state
- Add a PySide6 application shell with:
- top header bar
- left sidebar
- central `QStackedWidget`
- dedicated `Chat`, `Agent`, `Help`, and `Settings` pages
- Keep chat command submission on the existing desktop command path:
- command registry lookup first
- router-backed execution for registered chat actions
- preserve confirmation-gated actions
- Ensure the chat transcript remains selectable/copyable and the input stays fixed and visible during resize
- Apply a dark command-center stylesheet using the current Rogue dark palette as the primary Qt theme
- Switch `rogue_app.py` to prefer the PySide6 launcher while preserving the Tkinter desktop as a legacy fallback for incremental migration safety
- Update dependencies and focused tests for:
- launcher selection
- backend/controller command execution
- help/settings model generation
- non-interactive Qt startup smoke coverage where feasible
- Validate with compile/import checks, targeted unit tests, and a non-interactive desktop startup smoke path

## Extension Goals

The current system already has a minimal working agent architecture. This extension adds deterministic, read-only inspection/reporting capabilities:

- Workspace summary reporting
- Safe project inspection
- Deterministic folder summaries
- Strict verification rules for the new report outputs
- Persistent task-state orchestration with resumable execution
- Schema-separated memory boundaries for session, task, project, and preference data
- Read-only task visibility through the CLI and desktop app
- Structured task detail reporting for active, resumable, completed, and recent agent tasks
- Natural-language folder inspection routing for safe aliases and safe local paths
- Preview-only folder organization routing for natural phrases such as `organize desktop` and `sort my downloads`
- Optional recursive preview-only folder organization with richer categorization and clearer reporting
- A minimal chat-first desktop control surface with quick commands, lightweight status, and structured preview rendering

## Proposed Architecture

Minimal integration architecture:

1. Keep `brain/router.py` as the top-level intent detector.
2. Add a new agent intent path for higher-level requests such as planning, status reporting, and tool-based execution.
3. Use `planner.py` to convert a user goal into ordered task objects.
4. Use `agent_loop.py` to execute those tasks through `tool_registry.py`.
5. Use `memory_manager.py` to record session context and persistent summaries.
6. Use `execution_logger.py` to write structured agent events to `logs/agent.log`.
7. Use `status_reporter.py` to keep `STATUS.md` synchronized with completed work, remaining work, blockers, and validation results.
8. Reuse existing tool implementations rather than duplicating filesystem, browser, project, or system logic.
9. Add read-only environment inspection helpers only where existing tools do not already expose the needed structured data.
10. Persist task state independently of logs and independently of session/project/preference memory.
11. Expose agent task-state inspection through `brain.py` and `rogue_app.py` by reading from `task_manager.py` rather than duplicating task logic.
12. Normalize folder-inspection and folder-organization phrases into deterministic, read-only agent plans rather than introducing ad hoc direct actions.
13. Keep organization previews non-destructive while allowing bounded recursive analysis when explicitly selected by deterministic phrase rules.

## Implementation Phases

### Phase 22. Desktop branding and restrained motion
- Keep the supported runtime path unchanged: `start_rogue.bat` -> `rogue_app.py`, with `brain.py` remaining secondary CLI support
- Scope UI changes to the live Tkinter desktop path only:
- `build_ui()` -> `build_top_bar()`
- the active chat workspace status line in `build_chat_view()`
- theme refresh hooks already used by the current shell
- Add a subtle Rogue branding block in the top-left header without changing command routing, agent execution, planner flow, or tool behavior
- Support a small optional brand asset for the header using Tkinter-native image handling, including multi-frame GIF playback when a compatible asset is present
- Provide a safe default fallback icon when no asset is supplied so the UI still gains a stronger identity without adding external dependencies
- Add restrained text animation only for selected moments such as desktop startup and key agent-running status transitions
- Keep animation limited to a single text surface and optional small header media so startup remains stable and the UI avoids flashy continuous motion
- Preserve theme compatibility for both the existing light shell and the dark cyber command-center palette by routing new visuals through the existing theme refresh path
- Validate with compile/import checks, focused unit coverage for the new helper behavior, and a Tkinter startup smoke test through `RogueApp`

### Phase 21. Anti-hallucination evidence hardening
- Keep `start_rogue.bat` -> `rogue_app.py` as the supported runtime path and preserve `brain.py` as secondary CLI support
- Keep the existing router -> planner -> task manager -> agent loop -> tool execution -> UI preview architecture intact
- Introduce a shared structured result contract for tools and command handlers with explicit evidence fields:
- `success`
- `action`
- `observed`
- `artifacts`
- `warnings`
- `errors`
- `inferences`
- `suggestions`
- Normalize legacy tool outputs through the registry boundary so unstructured strings cannot silently become optimistic success claims
- Require response formatting paths to distinguish:
- observed facts
- inferences
- suggestions
- Make missing evidence explicit with deterministic fallback language instead of guessing about files, reports, paths, command success, or task completion
- Update agent final-output and task-detail formatting so completion claims are based on verified execution state rather than generic prose
- Update desktop preview rendering to derive user-visible sections from structured payload data instead of invented summaries
- Add focused tests that prove Rogue does not fabricate:
- file existence
- file/report creation
- task completion
- command success
- saved artifact paths
- Validate the hardening pass with targeted unit tests and a supported-entrypoint compile/import run

### Phase 18. Theme and text-interaction stabilization for desktop Settings
- Keep `start_rogue.bat` -> `rogue_app.py` as the supported launcher path
- Preserve the current multi-view desktop structure and the existing `Chat`, `Agent`, `Help`, and `Settings` sections
- Replace the placeholder Settings theme row with a functional Appearance area that exposes `Light` / `Dark` mode and visible font-size status
- Persist the selected theme through the existing desktop settings file instead of adding a second config path
- Add a restrained dark palette and a matching light palette while keeping the current Tkinter widget structure readable and maintainable
- Apply theme changes consistently across the shell, cards, labels, buttons, text widgets, input widgets, agent controls, help content, and settings content
- Keep backend routing, planner, task, tool, memory, and autonomous-loop behavior unchanged
- Fix read-only chat/output interaction so text selection and `Ctrl+C` work reliably without making transcript widgets editable
- Add context menus for chat/output text and command input with copy/paste/select-all actions, plus `Clear Chat` where appropriate
- Update focused tests for settings persistence/defaults and desktop theme/text interaction helpers
- Validate startup stability through targeted tests plus a startup-safe import/compile pass

### Phase 17. Multi-view desktop shell refactor
- Keep `start_rogue.bat` -> `rogue_app.py` as the supported launcher path
- Replace the crowded single Home dashboard with a fixed-shell layout:
- top bar
- left navigation sidebar
- stacked main content views
- Make `Chat` the default landing view and primary user interaction surface
- Move autonomous loop controls and detailed agent state into a dedicated `Agent` view
- Move help/reference content into a dedicated `Help` view
- Add a simple but real `Settings` view with current values/placeholders for theme, font size, default mode, and model
- Keep the current router, planner, task manager, tool registry, preview rendering, and autonomous loop behavior unchanged
- Reuse existing chat transcript, preview rendering, and agent-state widgets where possible instead of rewriting backend-connected UI logic
- Preserve or improve scroll-safe behavior with per-view scrolling where needed
- Update focused desktop tests for the new shell navigation and startup-safe layout expectations
- Validate launch stability through the supported entrypoint path and document any remaining UI-only risks

### Phase 11. Desktop control-panel navigation and command registry
- Add a dedicated desktop command registry module so command definitions live in one place
- Add a top command bar with text input and `Execute` action near the dashboard header
- Add visible `Back`, `Help`, and `Run Task` controls in the desktop header
- Add safe navigation history helpers so secondary views can return to the main dashboard
- Bind `Escape` to the same back-navigation behavior and make the empty-history path safe
- Add a readable help view grouped by:
  - Navigation
  - System
  - Analysis
  - Actions
- Route supported command-bar commands through the registry instead of scattered conditionals
- Add confirmation-gated execution for risky desktop commands such as cleanup, move, and duplicate-related actions
- Reuse existing router-backed commands wherever possible instead of duplicating business logic
- Keep the current Tkinter layout and styling intact except for the header/command usability improvements

### Phase 12. Desktop interactivity and scrollability
- Keep the current desktop structure and command registry intact
- Add a persistent `Home` button to the header alongside the existing navigation controls
- Improve back/home history behavior so repeated secondary-view transitions stay predictable
- Add clipboard shortcuts and a right-click context menu to the command bar
- Make result/report content selectable where practical without replacing the app architecture
- Add a scrollable preview/result surface with a vertical scrollbar and mouse-wheel support
- Add light hover states and clearer status/feedback messaging to make the UI feel more responsive
- Add interactive result actions for file-based analysis rows:
  - open file
  - open containing folder
  - copy path
- Keep risky actions confirmation-gated and avoid introducing destructive automation

### Phase 13. Chat-style desktop design alignment
- Keep the current layout architecture intact while aligning the desktop to a chat-assistant visual language
- Standardize the header, command composer, response cards, and action buttons around a shared theme token set
- Make the command bar feel like a message composer instead of a utility form field
- Make preview/result panels read as agent responses instead of static report cards
- Tighten spacing, hierarchy, and button variants to reduce dashboard/admin-screen visual drift
- Preserve all existing command, routing, confirmation, and task functionality

### Phase 14. Minimal brain.agent adapter
- Add `brain/agent.py` with a minimal `RogueAgent` class
- Keep the existing router -> planner -> agent loop runtime path intact
- Reuse the current registry-backed tool execution model instead of introducing a parallel tool system
- Support simple goal planning plus sequential execution for registry-backed tasks
- Keep the result shape compatible with the structured tool payloads already used by the router and agent loop
- Add focused automated tests for the new adapter

### Phase 15. Minimal brain task queue
- Add `brain/task_queue.py` as a small execution queue for `RogueAgent`
- Keep it separate from `tasks/task_queue.py`, which remains the persistent engineering request queue
- Support enqueue, sequential execution, status tracking, and cancellation
- Route `RogueAgent.execute()` through the queue instead of invoking registry tools directly
- Keep execution deterministic and registry-backed with no new framework or dependency
- Add focused tests for queue behavior and agent integration

### Phase 16. Memory store recent history
- Extend `memory/memory_store.py` without breaking the existing saved-notes behavior
- Add recent action and recent command tracking with JSON persistence
- Keep notes and recent history in separate JSON files so existing note callers remain compatible
- Expose simple retrieval helpers for recent actions and recent commands
- Add a small convenience `log()` helper for action history
- Cover the new behavior with focused persistence tests

### Phase 17. Safe autonomous loop
- Add `brain/sensor.py` with a deterministic `RogueSensor` focused on safe Downloads inspection
- Add `brain/policy.py` with a minimal `RoguePolicy` that only auto-approves read-only tasks
- Add `brain/auto_loop.py` with a `RogueAutoLoop` that:
  - collects sensor state each cycle
  - derives a minimal goal for the existing `brain.agent.RogueAgent`
  - filters planned steps through the policy engine
  - executes only approved tasks
  - records cycle state and results into `memory/session/`
- Reuse `tool_registry.build_default_registry()` and `memory_manager.MemoryManager` instead of introducing a parallel autonomy stack
- Keep `start_rogue.bat`, `rogue_app.py`, and `brain.py` as the supported runtime path
- Add focused tests for sensor collection, policy filtering, and autonomous loop start/stop plus cycle execution

### Phase 18. Desktop Agent Control panel
- Add `brain/agent_state.py` with a thread-safe shared `AgentState` object for autonomous loop visibility
- Integrate `brain/auto_loop.py` with the shared state so each cycle records:
  - running status
  - selected mode
  - interval seconds
  - last cycle time
  - next cycle time
  - latest observation summary
  - latest generated plan
  - approved tasks
  - blocked tasks
  - last result
  - last error
- Keep loop execution and one-off cycles off the Tkinter main thread
- Refresh the desktop panel with `tkinter.after()` instead of direct cross-thread widget updates
- Add a dedicated card-style Agent Control panel to `rogue_app.py` with:
  - Start Agent
  - Stop Agent
  - Run One Cycle
  - Manual / Assist / Auto mode selector
- Keep the current Rogue desktop layout intact and avoid introducing a second UI path
- Add focused tests for shared state updates, mode-aware loop behavior, and UI snapshot formatting helpers where practical

### Phase 19. Desktop usability refinement
- Keep `start_rogue.bat` -> `rogue_app.py` as the only supported desktop runtime path
- Remove the duplicate bottom chat command input and standardize command execution on the top `Ask Rogue` composer
- Move `Clear Chat` into the top toolbar next to `Run Task`
- Increase the default desktop geometry to `1400x900` and the minimum size to `1200x750`
- Persist and restore window size and position through `config/ui_state.json`
- Prefer `Segoe UI` in the desktop font stack and normalize key sizes to:
  - body text `12`
  - section headers `14`
  - main title `16`
- Add right-click context menus to editable text inputs and read-only output text panels with:
  - Copy
  - Paste
  - Cut
  - Select All
  - Clear
- Support `Enter` to execute commands and `Shift+Enter` to insert a newline in the top command composer
- Add Up/Down command history navigation to the top composer without changing router behavior
- Improve spacing between major panels while preserving the current Rogue visual structure
- Add color-coded agent status indication for Running, Stopped, and Error states
- Improve agent plan display formatting for readability only; do not change planning logic
- Add focused Tk/UI tests for font preference, geometry persistence helpers, command composer behavior, and status formatting

### Phase 20. Home dashboard scroll-safe layout stabilization
- Keep `start_rogue.bat` -> `rogue_app.py` as the only supported desktop runtime path
- Keep the current Home / Command Center screen as the primary dashboard with no new navigation sections
- Preserve the existing Home blocks:
  - header
  - command bar
  - system status / conversation area
  - agent control
  - rogue response
- Keep the top header and top command bar fixed where practical
- Refactor the Home body below the fixed header into a vertically scrollable `Canvas` + `Scrollbar` container
- Update the Home canvas scrollregion dynamically on content and width changes
- Enable mouse-wheel scrolling for the Home canvas without changing backend behavior
- Compact the Agent Control panel by combining smaller status fields into denser rows while preserving all current information
- Give the Rogue Response / Output area more vertical space relative to the Agent Control panel
- Improve resize behavior for fullscreen and smaller windows:
  - keep a sensible default window size
  - keep a minimum window size
  - ensure major panels stretch cleanly without clipping
- Keep the current light-theme styling direction with only minimal spacing/layout adjustments
- Add focused UI tests for Home scroll helpers, compact Agent Control formatting helpers, and updated window-size constants where practical

### Phase 1. Planning refresh
- Update `PLANS.md` for the new read-only reporting scope
- Keep the existing architecture intact
- Define deterministic outputs and strict verification rules

### Phase 2. Read-only inspection helpers
- Add structured, read-only helpers for workspace summary, project inspection, and folder summary
- Reuse existing filesystem and project helpers where possible
- Avoid all write, move, or delete operations

### Phase 3. Task-state orchestration and memory boundaries
- Add `task_manager.py` for persistent resumable task records
- Refactor `memory_manager.py` into schema-separated session, project, and preference stores
- Keep logs diagnostic-only
### Phase 4. Planner and registry coverage
- Add planner intents for:
  - `workspace summary`
  - `inspect project <name>`
  - `summarize folder <alias-or-path>`
- Register only the additional inspection/reporting tools required by those plans

### Phase 5. Strict verification and retries
- Define task-specific verification for workspace summary outputs
- Define task-specific verification for project inspection outputs
- Define task-specific verification for folder summary outputs
- Keep retries bounded and deterministic

### Phase 6. Validation
- Add unit tests for planner routing, tool outputs, and verification behavior
- Add unit tests for task lifecycle and memory isolation
- Run the full test suite
- Execute representative end-to-end commands
- Update `STATUS.md` with results and remaining gaps

### Phase 7. Task visibility and UI observability
- Extend `task_manager.py` with deterministic read-only helpers for:
  - list all tasks
  - list active tasks
  - list resumable tasks
  - list recent tasks
  - show structured task details
- Extend `brain.py` to support:
  - `python brain.py agent list tasks`
  - `python brain.py agent list active tasks`
  - `python brain.py agent list resumable tasks`
  - `python brain.py agent recent tasks`
  - `python brain.py agent show task <id>`
- Extend `rogue_app.py` with a minimal agent-task sidebar view and safe task detail rendering
- Keep the existing Codex task queue UI intact and separate from agent task state

### Phase 8. Natural-language folder routing
- Extend safe folder alias coverage for:
  - `desktop`
  - `downloads`
  - `documents`
  - `pictures`
  - `music`
  - `videos`
  - `workspace`
  - `projects`
- Add deterministic phrase recognition for inspection requests such as:
  - `scan desktop`
  - `inspect downloads`
  - `check my desktop`
  - `what is on my desktop`
  - `list files in documents`
- Add deterministic phrase recognition for preview-only organization requests such as:
  - `organize my desktop`
  - `organize downloads`
  - `organize documents`
  - `clean up my desktop`
  - `sort my downloads`
  - `arrange my desktop`
  - `organize this folder`
- Route organization requests to preview-only workflows that explicitly state no files were modified
- Keep all organization behavior non-destructive in this phase

### Phase 9. Recursive preview and categorization quality
- Extend `preview_folder_organization` to support bounded recursive inspection
- Keep top-level preview as the default behavior
- Enable recursive preview only through deterministic phrase handling such as `clean up ...`, `arrange ...`, or explicit recursive wording
- Improve category coverage for:
  - images
  - documents
  - audio
  - video
  - archives
  - code
  - installers
  - shortcuts
  - folders
  - other
- Ensure preview output includes:
  - total files analyzed
  - top categories
  - sample filenames
  - top-level vs recursive scope
  - nested file counts when recursion is enabled
  - explicit confirmation that no files were modified

### Phase 10. Minimal desktop UI refresh
- Keep `rogue_app.py` as the supported desktop entrypoint
- Preserve the router-backed chat execution path instead of adding a new frontend architecture
- Reduce the desktop layout to:
  - a compact `Rogue` title bar
  - a left quick-command rail
  - a central chat transcript and input
  - a bottom structured preview panel
  - a small status line showing CPU, RAM, and active tasks
- Ensure quick commands trigger the exact same router commands that a user could type in chat
- Capture existing planner/agent/task outputs so the preview panel can render:
  - folder summaries
  - organization previews
  - workspace summaries
  - system-status summaries
- Standardize desktop typography around an Inter-first font stack with Windows-safe fallbacks and slightly larger readable sizes for chat, headers, quick commands, and preview content
- Render structured result output in light card-style containers with clearer section hierarchy, more vertical spacing, and minimal separators
- Replace the large always-visible task surface with a small active-task indicator that opens a simple task list on demand
- Keep the UI intentionally minimal and avoid adding dashboard-style navigation or analytics panels

## Risks

- `brain/router.py` is already broad and string-matching heavy, so invasive changes could break existing command handling
- The repo contains overlapping folders such as `legacy/`, `utilities/`, `memory_store/`, and ad hoc artifacts, which can confuse import paths and ownership
- Existing memory behavior is split between markdown notes and JSON note storage, so a unified memory interface must not break current features
- The desktop app is Tkinter-based; blocking agent execution on the UI thread would degrade responsiveness
- Some filesystem and application-launch tools perform real local actions, so tests must use mocks
- Project inspection must stay bounded and avoid scanning the entire drive or unstable hidden environments
- Folder summaries must remain deterministic even when the underlying directory contents are large
- The desktop app already has a Codex task panel, so agent-task additions must not blur the distinction between engineering tasks and agent workflow tasks
- CLI task commands should not accidentally overlap with existing free-form goal execution or the router's Codex task commands
- Natural-language folder phrases are ambiguous, so routing rules must prefer deterministic alias/path handling over fuzzy interpretation
- Existing direct router flows for downloads and home workspace already include confirmation-based organization behavior, so new phrase handling must avoid silently reintroducing file moves
- Recursive previews can become expensive on large folders, so traversal must remain bounded and deterministic
- Category previews must stay readable even when the analyzed folder contains thousands of files
- Tkinter layout changes can easily regress startup behavior, so the refresh must keep initialization simple and testable
- Structured preview rendering must tolerate plain-text router responses without crashing or hiding useful output
- Autonomous planning must not silently reintroduce destructive actions such as file moves, deletions, or process termination
- Background cycle execution must remain easy to stop and deterministic enough for unit tests

## Verification Strategy

- Run the existing unit tests before and after changes
- Add focused unit tests for each new reporting capability
- Use mocks for tool execution and filesystem side effects where appropriate
- Validate that `python rogue_app.py` still imports successfully
- Validate representative read-only agent workflows:
  - `python brain.py agent workspace summary`
  - `python brain.py agent inspect project RogueAI`
  - `python brain.py agent summarize folder downloads`
- Validate representative task visibility workflows:
  - `python brain.py agent list tasks`
  - `python brain.py agent list active tasks`
  - `python brain.py agent show task 1`
  - `python brain.py agent recent tasks`
- Validate representative natural-language folder workflows:
  - `python brain.py agent scan desktop`
  - `python brain.py agent inspect desktop`
  - `python brain.py agent summarize downloads`
  - `python brain.py agent organize desktop`
  - `python brain.py agent organize my downloads`
  - `python brain.py agent organize documents`
- Validate representative recursive preview workflows:
  - `python brain.py agent clean up my desktop`
  - `python brain.py agent arrange my desktop`
- Validate at least one safe autonomous cycle end to end using the existing `RogueAgent` plan structure
- Validate blocked steps are logged but never executed during autonomous cycles
- Validate the desktop UI still initializes through `python rogue_app.py`
- Validate the desktop UI renders minimal structured previews for:
  - `scan desktop`
  - `inspect downloads`
  - `workspace summary`
  - `agent report system status`
- Validate the desktop UI renders structured result sections inside card-style containers without adding new panels
- Validate the desktop UI task indicator reflects the active task count from `task_manager.py`
- Validate the desktop UI selects Inter when available and falls back cleanly on Windows when it is not installed
- Record each phase result and any blocker in `STATUS.md`

## Entry Point Standardization

- Supported launcher remains `start_rogue.bat`
- Supported app entrypoint remains `rogue_app.py`
- `brain.py` remains secondary CLI support
- New agent modules must integrate into this path rather than creating a competing entrypoint

## 2026-04-11 Chat Bubble Refinement Plan

### Audit

- Supported launcher remains `start_rogue.bat`
- Supported desktop entrypoint remains `rogue_app.py`
- Chat rendering is currently handled in `RogueApp.build_chat_view()`, `RogueApp.configure_chat_tags()`, and `RogueApp.add_message()`
- The transcript uses a single `ScrolledText` widget, so the safest change is a tag/layout refinement instead of a widget architecture rewrite
- Router execution, command history, message classification, and preview rendering already flow through the current chat surface and should remain unchanged

### Minimal Fix Scope

- Preserve the current `ScrolledText` transcript and command composer
- Reconfigure chat tags so user messages render as left-aligned bubbles and Rogue/assistant messages render as right-aligned bubbles
- Keep warning, tool, confirm, and diagnostics messages visually distinct without changing command behavior
- Limit readable bubble width with text margins and wrap behavior instead of introducing a new canvas/message component system
- Preserve scrollability, text selection, copy behavior, and responsive resizing

### Validation

- Run targeted syntax and unit-test checks for `rogue_app.py` and startup/UI behavior
- Validate that `add_message()` still appends transcript content normally
- Validate that chat bubble tag configuration encodes left/right alignment and non-full-width margins
- Run the supported desktop entrypoint in a non-interactive startup smoke check if feasible

## 2026-04-11 Chat Bubble Revert Plan

### Audit

- The bubble-specific change is isolated to `rogue_app.py` chat transcript tag configuration and a resize binding on `self.chat_box`
- Bubble-only regression coverage was added in `tests/test_startup_and_config.py` through `FakeTextWidget` and two chat-layout assertions
- The supported runtime path remains `start_rogue.bat` -> `rogue_app.py`, with routing and agent behavior outside the revert scope

### Minimal Fix Scope

- Remove the chat bubble resize binding and dynamic bubble margin helpers
- Restore the prior stable `ScrolledText` tag configuration with simple uniform margins and existing transcript insertion behavior
- Remove only the bubble-specific test scaffolding and assertions
- Preserve all other desktop UI, router, agent, settings, theme, and model-selection behavior

### Validation

- Run `py_compile` for `rogue_app.py` and `tests/test_startup_and_config.py`
- Run targeted startup/UI tests covering transcript behavior and desktop command registry integration
- Run the full test suite and a non-interactive desktop startup smoke check
- Run a lightweight non-interactive desktop command smoke check to confirm commands still execute normally

## 2026-04-12 PySide6 Transcript Animation Isolation Plan

### Audit

- Supported launcher remains `start_rogue.bat`
- Supported desktop entrypoint remains `rogue_app.py`
- The active PySide6 shell is wired through `ui_qt/main_window.py`, `ui_qt/backend.py`, and `ui_qt/chat_view.py`
- Transcript-local pending and typewriter behavior already exists in `ui_qt/chat_view.py`
- The top-right header banner in `ui_qt/main_window.py` is still fed directly from backend status strings, so it can surface raw command/progress text that should stay out of global status regions
- Minimal-risk fix is to preserve the current backend callbacks while constraining header rendering to stable state labels and ensuring only the latest transcript reply owns any active typing animation

### Minimal Fix Scope

- Keep the current PySide6 shell, backend controller, and transcript card architecture intact
- Preserve the chat-local pending placeholder flow: user message, temporary Rogue thinking bubble, then animated verified final reply inside the transcript
- Stop using the header banner for command text, chat-progress text, or raw task logs
- Keep any footer/help copy stable and non-animated
- Ensure older transcript bubbles do not continue animating once a newer Rogue reply becomes the active response
- Preserve text selection, copyability, and transcript scroll stability

### Validation

- Run targeted Qt unit tests for `ui_qt/chat_view.py`, `ui_qt/backend.py`, and the PySide6 main window shell
- Run `python -m py_compile` over the touched Qt modules and tests
- Run the supported launcher smoke coverage already present in `tests/test_rogue_launcher.py`
- Record validation results and any remaining risk in `STATUS.md`

## 2026-04-12 PySide6 Single-Response Chat Plan

### Audit

- Supported launcher remains `start_rogue.bat`
- Supported desktop entrypoint remains `rogue_app.py`
- The active PySide6 shell is isolated to `ui_qt/main_window.py`, `ui_qt/backend.py`, `ui_qt/chat_view.py`, and `ui_qt/agent_view.py`
- Chat currently renders whatever verified backend text is emitted, including raw structured result text from `result_contract.format_response_text()` and raw agent workflow `final_output`
- Structured router results are already stored in `last_structured_response_payload`
- Agent workflow runs are already stored in `last_agent_workflow_payload`
- The duplication concern is presentation-layer only: Chat needs one primary operator response, while Agent should remain the technical surface for workflow/state detail

### Minimal Fix Scope

- Preserve the current PySide6 shell, sidebar, views, command routing, and verified backend result flow
- Keep transcript ordering unchanged: user message first, then one Rogue response
- Add a Qt-side formatter that converts verified structured or agent payloads into one concise operator-style Chat response
- Stop Chat from showing raw technical workflow text when a verified payload is available
- Surface the raw structured/workflow detail text in Agent instead of Chat
- Preserve selectable/copyable text behavior and current view separation

### Validation

- Run targeted Qt unit tests for `ui_qt/backend.py`, `ui_qt/chat_view.py`, and `ui_qt/main_window.py`
- Add/adjust tests that verify one user input produces one main Rogue response in Chat
- Validate that Agent still exposes technical/state detail text
- Run `python -m py_compile` across the touched Qt modules and tests
- Run the supported launcher smoke coverage in `tests/test_rogue_launcher.py`

## 2026-04-13 Response Normalization And System Health Plan

### Audit

- Confirmed supported runtime path remains `start_rogue.bat` -> `rogue_app.py`, with `brain.py` as secondary CLI support
- Confirmed the active PySide6 chat response seam lives in `ui_qt/backend.py`, where verified structured payloads are already summarized for Chat while raw workflow detail stays in Agent
- Confirmed command routing is centralized in `brain/router.py` and agent tool exposure is centralized in `tool_registry.py`
- Confirmed existing verified system metadata tooling lives in `tools/system_info.py`, so `system health` should follow the same evidence-backed payload style instead of introducing a parallel app path
- Confirmed the requested scope is presentation and tooling only; routing engine internals, verification helpers, agent workflow flow, and Qt layout stay out of scope

### Minimal Fix Scope

- Add a new verified `tools/system_health.py` tool that collects real CPU, memory, and disk metrics from the local machine with safe fallbacks
- Register `system_health` in `tool_registry.py` and map `system health` plus the requested aliases in `brain/router.py`
- Standardize Chat operator responses in `ui_qt/backend.py` around `Title`, `Summary`, optional `Details`, optional `Warning`, and optional `Recommendation`
- Render only fields present in verified payloads and never inject placeholders or guessed values
- Preserve one chat response per user input and keep raw structured/workflow text available from Agent

### Validation

- Run `python -m py_compile` on the touched backend/router/tool/test files
- Run targeted unit tests for `tests/test_ui_qt_backend.py` and `tests/test_router.py`
- Run existing Qt launcher/startup coverage if the touched surface could affect startup stability
- Exercise one real local `system health` workflow through the supported code path and record any remaining risk in `STATUS.md`

## 2026-04-13 Storage Overview Plan

### Audit

- Confirmed the existing verified system command pattern already spans `tools/*`, `brain/router.py`, `tool_registry.py`, and `ui_qt/backend.py`
- Confirmed Chat normalization already uses a dedicated structured-payload seam in `ui_qt/backend.py`, so `storage overview` can be added without touching the Qt layout or routing engine
- Confirmed natural-folder routing can intercept phrases like `check disk`, so the new alias block needs to be placed ahead of generic folder-inspection matches
- Confirmed the current test coverage already exercises router alias mapping, structured Chat formatting, registry exposure, and Qt launcher stability

### Minimal Fix Scope

- Add a new verified `tools/storage_overview.py` tool that collects real disk usage, top directories, and large files from the local machine with conservative scanning
- Register `storage_overview` in `tool_registry.py` and map `storage overview`, `disk usage`, `check disk`, `disk analysis`, and `storage status` in `brain/router.py`
- Extend `ui_qt/backend.py` with a storage-overview Chat formatter that uses the standardized operator response format and omits unavailable fields
- Add targeted tests for the new tool, router aliases, and normalized Chat output while preserving one Chat response per user input

### Validation

- Run `python -m py_compile` on the touched tool/router/backend/test files
- Run targeted unit tests for `tests/test_tools_storage.py`, `tests/test_router.py`, `tests/test_ui_qt_backend.py`, and `tests/test_tool_registry.py`
- Run existing Qt launcher/startup coverage to confirm the PySide6 shell remains stable
- Execute one live `storage overview` command through the backend controller and record the observed metrics in `STATUS.md`

## 2026-04-14 Backend Success Inference Drift Plan

### Audit

- Confirmed the supported runtime path remains `start_rogue.bat` -> `rogue_app.py`, with `brain.py` as the secondary CLI entrypoint
- Confirmed the requested scope is limited to `ui_qt/backend.py` title/state classification for chat/operator responses
- Found two local success inference paths in `ui_qt/backend.py`: `infer_result_success(...)` and duplicate static helper `_infer_result_success(...)`
- Found one operator-response parser path that still infers `ok` from a `" Failed"` title suffix instead of consulting the local result-aware helper when raw structured payload data is available
- Confirmed the needed hardening is narrow: `planned_tasks == verified_tasks` must only imply success when `planned_tasks > 0`

### Minimal Fix Scope

- Keep the formatter and response layout intact
- Harden `infer_result_success(...)` so `0 planned / 0 verified` does not count as success
- Reuse `infer_result_success(...)` in the agent-run chat builder instead of the duplicate static helper
- Reuse `infer_result_success(...)` in operator-response parsing when structured raw payload data is available, while preserving the existing title-suffix fallback for plain text
- Add 2 focused tests covering the `0/0` non-success case and a real verified-result success case

### Validation

- Run `python -m unittest tests.test_ui_qt_backend`
- Run `python -m py_compile ui_qt/backend.py tests/test_ui_qt_backend.py`

## 2026-04-14 Command Envelope Minimal-Change Review Plan

### Audit

- Confirmed the `Command Envelope` seam enters Chat in `build_chat_response_text(...)`
- Confirmed `build_chat_response_text(...)` still duplicates the same payload-envelope rendering flow for agent and structured payloads
- Confirmed specialized Chat builders still use direct `payload.get("success", True)` decisions instead of the shared local helper, which can bypass explicit `error` handling
- Confirmed the generic structured-result branch still has a manual failure gate (`payload.get("success") is False or payload.get("errors")`) instead of deferring to the shared helper
- Confirmed the hardening requirement still belongs in `infer_result_success(...)`: `planned_tasks == verified_tasks` should only imply success when `planned_tasks > 0`

### Minimal Fix Scope

- Keep the `Command Envelope` seam and formatter intact
- Consolidate the duplicated payload-to-envelope render path behind one small helper in `ui_qt/backend.py`
- Route the remaining Chat `ok` decisions through `infer_result_success(...)`
- Keep plain-string wrapping single-path and non-destructive
- Update only `tests/test_ui_qt_backend.py` expectations and focused regression coverage needed for the preserved behavior

### Validation

- Run `python -m unittest tests.test_ui_qt_backend`
- Run `python -m py_compile ui_qt/backend.py tests/test_ui_qt_backend.py`
