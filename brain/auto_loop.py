"""Safe autonomous execution loop for RogueAI."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from brain.agent import RogueAgent
from brain.agent_state import AgentState
from brain.policy import RoguePolicy
from brain.sensor import RogueSensor
from memory_manager import MemoryManager
from planner import Planner
from tool_registry import build_default_registry


class RogueAutoLoop:
    """Run approved read-only agent cycles on a fixed interval."""

    def __init__(
        self,
        cycle_seconds: int = 60,
        agent: RogueAgent | None = None,
        policy: RoguePolicy | None = None,
        sensor: RogueSensor | None = None,
        memory_manager: MemoryManager | None = None,
        agent_state: AgentState | None = None,
        goal_builder=None,
        stop_event: threading.Event | None = None,
        thread_factory=None,
        clock=None,
    ):
        base_dir = Path(__file__).resolve().parent.parent
        default_memory_root = base_dir / "memory"
        memory_root = Path(getattr(memory_manager, "memory_root", default_memory_root))

        self.clock = clock or datetime.now
        self.cycle_seconds = max(1, int(cycle_seconds))
        if agent is None:
            registry = build_default_registry(
                projects_path=base_dir / "projects",
                memory_dir=memory_root,
                workspace_root=base_dir,
            )
            agent = RogueAgent(command_registry=registry, planner=Planner())
        self.agent = agent
        self.policy = policy or RoguePolicy()
        self.sensor = sensor or RogueSensor()
        self.memory_manager = memory_manager or MemoryManager(memory_root)
        self.agent_state = agent_state or AgentState(mode="auto", interval_seconds=self.cycle_seconds, clock=self.clock)
        self.goal_builder = goal_builder or self._default_goal_builder
        self.stop_event = stop_event or threading.Event()
        self.thread_factory = thread_factory or self._build_thread
        self._thread = None
        self._cycle_lock = threading.Lock()
        self.agent_state.set_interval_seconds(self.cycle_seconds)

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return False
        if self.agent_state.get_mode() == "manual":
            return False

        self.stop_event.clear()
        self.cycle_seconds = self.agent_state.get_interval_seconds()
        self.agent_state.mark_started()
        self._thread = self.thread_factory(target=self._run_forever)
        self._thread.start()
        return True

    def stop(self, wait: bool = True) -> bool:
        thread = self._thread
        if thread is None:
            return False

        self.stop_event.set()
        self.agent_state.mark_stopped()
        if wait and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=self.cycle_seconds + 1)

        if not thread.is_alive():
            self._thread = None
        return True

    def run_cycle(self) -> dict:
        if not self._cycle_lock.acquire(blocking=False):
            payload = {
                "success": False,
                "cycle_started_at": self._now().isoformat(timespec="seconds"),
                "goal": "",
                "sensor_state": {},
                "plan": [],
                "approved_plan": [],
                "blocked_plan": [],
                "execution": {
                    "success": False,
                    "plan": [],
                    "results": [],
                    "queue": [],
                    "final_output": "Cycle already running.",
                },
                "error": "Cycle already running.",
            }
            self.agent_state.apply_cycle_error(payload["error"], payload["cycle_started_at"], running=self.is_running())
            return payload

        cycle_started_at = self._now().isoformat(timespec="seconds")
        mode = self.agent_state.get_mode()
        self.cycle_seconds = self.agent_state.get_interval_seconds()
        self.agent_state.mark_cycle_started()
        try:
            sensor_state = self.sensor.collect_state()
            goal = str(self.goal_builder(sensor_state) or "").strip()
            plan = self.agent.plan(goal)
            filtered = self.policy.filter_tasks(plan)
            approved_plan = filtered["approved"]
            blocked_plan = filtered["blocked"]

            if mode == "manual":
                execution = {
                    "success": True,
                    "plan": [],
                    "results": [],
                    "queue": [],
                    "final_output": "Manual mode: observation and planning completed without executing tasks.",
                }
            elif mode == "assist":
                execution = {
                    "success": True,
                    "plan": [],
                    "results": [],
                    "queue": [],
                    "final_output": "Assist mode: approved tasks were prepared but not executed.",
                }
            elif approved_plan:
                execution = self.agent.execute(approved_plan)
            else:
                execution = {
                    "success": True,
                    "plan": [],
                    "results": [],
                    "queue": [],
                    "final_output": "No approved autonomous tasks to execute.",
                }

            payload = {
                "success": execution.get("success", False),
                "cycle_started_at": cycle_started_at,
                "mode": mode,
                "goal": goal,
                "sensor_state": sensor_state,
                "plan": plan,
                "approved_plan": approved_plan,
                "blocked_plan": blocked_plan,
                "execution": execution,
            }
            self._log_cycle(payload)
            self.agent_state.apply_cycle_payload(payload, running=self.is_running())
            return payload
        except Exception as exc:
            payload = {
                "success": False,
                "cycle_started_at": cycle_started_at,
                "mode": mode,
                "goal": "",
                "sensor_state": {},
                "plan": [],
                "approved_plan": [],
                "blocked_plan": [],
                "execution": {
                    "success": False,
                    "plan": [],
                    "results": [],
                    "queue": [],
                    "final_output": str(exc),
                },
                "error": str(exc),
            }
            self._log_cycle(payload)
            self.agent_state.apply_cycle_payload(payload, running=self.is_running())
            return payload
        finally:
            self._cycle_lock.release()

    def run_cycle_async(self) -> bool:
        if self._cycle_lock.locked():
            return False
        worker = self.thread_factory(target=self.run_cycle)
        worker.start()
        return True

    def _run_forever(self):
        try:
            while not self.stop_event.is_set():
                self.run_cycle()
                if self.agent_state.get_mode() == "manual":
                    self.stop_event.set()
                    break
                if self.stop_event.wait(self.cycle_seconds):
                    break
        finally:
            self.agent_state.mark_stopped()

    def _default_goal_builder(self, sensor_state: dict) -> str:
        downloads = sensor_state.get("downloads", {})
        if int(downloads.get("file_count", 0)) > 0:
            return "organize downloads"
        return "report system status"

    def _log_cycle(self, payload: dict):
        summary = {
            "timestamp": self._now().isoformat(timespec="seconds"),
            "goal": payload.get("goal", ""),
            "success": payload.get("success", False),
            "approved_task_count": len(payload.get("approved_plan", [])),
            "blocked_task_count": len(payload.get("blocked_plan", [])),
        }
        self.memory_manager.append_session(
            "auto_loop",
            json.dumps({"summary": summary, "payload": payload}, ensure_ascii=False),
            namespace="auto_loop",
        )

    def _build_thread(self, target):
        return threading.Thread(target=target, name="RogueAutoLoop", daemon=True)

    def _now(self) -> datetime:
        value = self.clock()
        if isinstance(value, datetime):
            return value
        raise TypeError("clock must return a datetime instance.")

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self.stop_event.is_set()
