"""Persistence and stop/recovery tests for Milestone C.1."""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path

import pytest

from shiro.config import Settings
from shiro.database import Database
from shiro.input_control import (
    DesktopInputController,
    GlobalEmergencyStopService,
    InputBackend,
    VirtualScreenBounds,
)
from shiro.visual_control import VisualExecutionManager, VisualTaskRequest


class FakeBackend(InputBackend):
    def screen_bounds(self):
        return VirtualScreenBounds(0, 0, 100, 100)

    def execute(self, request):
        return {"status": "issued", "action": request.action}

    def release_all(self):
        pass


def test_visual_task_and_action_history_survive_restart_as_review_required(tmp_path: Path):
    path = tmp_path / "shiro.db"
    first = Database(path)
    first.initialize()
    first.create_visual_task(
        "run-1",
        "Harmless test",
        max_actions=3,
        max_duration_seconds=30,
        max_consecutive_failures=2,
    )
    first.update_visual_task(
        "run-1",
        status="running",
        current_action_json='{"action":"type_text","text":"test"}',
    )
    first.record_visual_action(
        "run-1",
        1,
        {"action": "click", "x": 10, "y": 10},
        "verified",
        verification={"success": True},
    )

    restarted = Database(path)
    restarted.initialize()
    recovered = restarted.get_visual_task("run-1")
    assert recovered is not None
    assert recovered["status"] == "paused"
    assert recovered["recovery_required"] is True
    assert "unknown" in str(recovered["error"])
    actions = restarted.list_visual_actions("run-1")
    assert len(actions) == 1
    assert actions[0]["status"] == "verified"


def test_emergency_stop_marks_active_visual_tasks_and_audits(tmp_path: Path):
    database = Database(tmp_path / "shiro.db")
    database.initialize()
    controller = DesktopInputController(
        backend=FakeBackend(),
        active_window_reader=lambda: {"active_window": {"process_name": "notepad.exe", "is_foreground": True}},
        min_interval_seconds=0,
    )
    manager = VisualExecutionManager(
        Settings(allow_tools=True),
        database,
        executor=None,
        input_controller=controller,
        ollama=None,
    )
    state = manager.create(VisualTaskRequest(task="stop test"))
    manager.emergency_stop("test")
    stopped = manager.get(state["run_id"])
    assert stopped["status"] == "stopped"
    assert stopped["error"] == "Emergency stop: test"
    assert database.list_tool_audits(limit=1)[0].tool_name == "emergency_stop"


@pytest.mark.skipif(platform.system() != "Windows", reason="Win32 global hook")
def test_global_emergency_stop_hook_starts_and_stops():
    service = GlobalEmergencyStopService(lambda _: None)
    assert service.start() is True
    assert service.start_error is None
    service.stop()
    assert service._thread is None or not service._thread.is_alive()


def test_unexpected_runner_cancellation_is_paused_for_review(tmp_path: Path):
    database = Database(tmp_path / "shutdown.db")
    database.initialize()
    controller = DesktopInputController(
        backend=FakeBackend(),
        active_window_reader=lambda: {"active_window": {"process_name": "notepad.exe", "is_foreground": True}},
        min_interval_seconds=0,
    )
    manager = VisualExecutionManager(
        Settings(allow_tools=True),
        database,
        executor=None,
        input_controller=controller,
        ollama=None,
    )
    state = manager.create(VisualTaskRequest(task="shutdown test"))

    async def interrupted(_run_id, _client):
        raise asyncio.CancelledError

    manager._observe = interrupted
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(manager._run(state["run_id"]))

    recovered = manager.get(state["run_id"])
    assert recovered["status"] == "paused"
    assert recovered["recovery_required"] is True
    assert "unknown" in str(recovered["error"])
