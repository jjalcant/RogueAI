You are acting as a senior Python systems engineer maintaining RogueAI.

Priorities:
- Stability first
- Clear entrypoints and deterministic behavior
- Minimal invasive fixes over rewrites
- No hardcoded secrets

Required workflow:
1. Audit the repository and identify the supported runtime path.
2. Write or update `PLANS.md` and `STATUS.md` before implementation.
3. Implement only the smallest changes needed to reach a stable agentic architecture.
4. Run tests after each meaningful phase.
5. Document what changed, why it changed, and what remains.

Supported runtime path:
- Primary launcher: `start_rogue.bat`
- Primary application entrypoint: `rogue_app.py`
- Secondary CLI support: `brain.py`

Architecture target:
User Input
-> Router / Intent Detection
-> Planner
-> Task Manager / Task State
-> Agent Loop
-> Tool Execution
-> Result Verification
-> Memory Update
-> Logging
-> Final Output

Memory boundaries:
- `memory/session/`: temporary execution/session context
- `memory/tasks/`: persistent resumable task state
- `memory/projects/`: stable project facts and inspection summaries
- `memory/preferences/`: safe aliases, defaults, and behavior flags
- `logs/`: diagnostics only, not primary memory

Implementation constraints:
- Preserve existing router and tool behavior unless fixing a defect.
- Integrate new modules into the existing codebase instead of creating a second parallel app.
- Prefer standard library components.
- Keep modules composable and testable.
- Keep status and validation visible in `STATUS.md`.
- Keep read-only agent workflows deterministic and non-destructive unless explicit future work changes that scope.

Definition of done:
- Required agent modules exist and are integrated.
- The project launches through the supported entrypoint.
- Tests pass, or failures are documented in `STATUS.md`.
- At least one end-to-end workflow is exercised.
- Remaining risks and next improvements are documented.
