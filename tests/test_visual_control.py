"""Mocked observe-act-verify tests for the visual execution runner."""

from __future__ import annotations

import asyncio

import pytest

from shiro.config import Settings
from shiro.input_control import DesktopInputController, DesktopInputRequest, InputBackend, VirtualScreenBounds
from shiro.tools import ToolResult
from shiro.visual import VisualUnderstanding
from shiro.visual_control import (
    ProposedVisualAction,
    VisualExecutionManager,
    VisualPlanResponse,
    VisualTaskRequest,
    VisualVerificationExpectation,
)


class FakeBackend(InputBackend):
    def screen_bounds(self):
        return VirtualScreenBounds(0, 0, 100, 100)

    def execute(self, request):
        return {"action": request.action, "status": "issued"}

    def release_all(self):
        pass


class FakeOllama:
    async def aclose(self):
        pass


class FakeExecutor:
    def __init__(self, result: ToolResult | None = None):
        self.result = result or ToolResult("succeeded", "windows_input_action", output={"status": "issued"})
        self.calls: list[dict] = []

    async def execute(self, tool_name, arguments, context, approval_id=None):
        self.calls.append(arguments)
        return self.result


def visual(*, text: list[str] | None = None, confidence: float = 0.95) -> VisualUnderstanding:
    return VisualUnderstanding.model_validate(
        {
            "schema_version": "shiro.visual.v1",
            "screen_width": 100,
            "screen_height": 100,
            "active_window": {
                "title": "Untitled - Notepad",
                "process_name": "notepad.exe",
                "hwnd": 42,
                "pid": 7,
                "is_visible": True,
                "is_foreground": True,
                "bounding_rectangle": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            },
            "targets": [
                {
                    "id": "target_1",
                    "label": "Document editor",
                    "role": "text_field",
                    "bounds": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.2},
                    "confidence": confidence,
                    "interactable": True,
                }
            ],
            "visible_text": text or ["Document editor"],
            "uncertainties": [],
        }
    )


def manager(monkeypatch, observations, plans, executor=None):
    monkeypatch.setattr("shiro.visual_control.build_ollama_client", lambda *args: FakeOllama())
    selected_executor = executor or FakeExecutor()
    controller = DesktopInputController(
        backend=FakeBackend(),
        active_window_reader=lambda: {"active_window": {"process_name": "notepad.exe", "is_foreground": True}},
        min_interval_seconds=0,
    )
    selected = VisualExecutionManager(
        Settings(allow_tools=True),
        None,
        selected_executor,
        controller,
        FakeOllama(),
    )
    async def observe(run_id, client):
        return observations.pop(0)
    async def plan(task, observation_id, current_visual):
        return plans.pop(0)
    selected._observe = observe
    selected._plan = plan
    return selected, selected_executor


def action_plan(observation_id: str, *, done=False, target_id="target_1"):
    return VisualPlanResponse(
        observation_id=observation_id,
        done=done,
        reason="done" if done else "type into the document",
        action=None if done else ProposedVisualAction(action="type_text", text="SHIRO", target_id=target_id),
        verification=VisualVerificationExpectation(visible_text_contains=["SHIRO"] if not done else []),
    )


def test_runner_reobserves_and_verifies_after_action(monkeypatch):
    first = visual()
    second = visual(text=["Document editor", "SHIRO"])
    selected = None
    observations = [("obs-1", first), ("obs-2", second)]
    plans = [action_plan("obs-1"), action_plan("obs-2", done=True)]
    selected, executor = manager(monkeypatch, observations, plans)
    state = selected.create(VisualTaskRequest(task="Type SHIRO", max_actions=2))
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "succeeded"
    assert result["action_count"] == 1
    assert result["latest_verification"]["success"] is True
    assert executor.calls[0]["target_hwnd"] == 42


def test_low_confidence_target_needs_clarification():
    with pytest.raises(ValueError, match="confidence"):
        VisualExecutionManager._resolve_action(
            ProposedVisualAction(action="click", target_id="target_1"),
            "obs-1",
            visual(confidence=0.2),
        )


def test_stale_observation_id_never_acts(monkeypatch):
    observations = [("obs-current", visual())]
    plans = [action_plan("obs-old")]
    selected, executor = manager(monkeypatch, observations, plans)
    state = selected.create(VisualTaskRequest(task="click", max_actions=1))
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "needs_clarification"
    assert executor.calls == []


def test_action_limit_stops_repeated_unverified_work(monkeypatch):
    observations = [(f"obs-{n}", visual()) for n in range(3)]
    plans = [action_plan("obs-0"), action_plan("obs-1")]
    selected, executor = manager(monkeypatch, observations, plans)
    state = selected.create(VisualTaskRequest(task="Type SHIRO", max_actions=1))
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "failed"
    assert "action limit" in result["error"]
    assert len(executor.calls) == 1


def test_explicit_cancellation_prevents_input(monkeypatch):
    observations = [("obs-1", visual())]
    plans = [action_plan("obs-1")]
    selected, executor = manager(monkeypatch, observations, plans)
    state = selected.create(VisualTaskRequest(task="cancel", max_actions=1))
    selected.cancel(state["run_id"])
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "cancelled"
    assert executor.calls == []


def test_duration_limit_stops_before_planning(monkeypatch):
    observations = [("obs-1", visual())]
    plans = [action_plan("obs-1")]
    selected, executor = manager(monkeypatch, observations, plans)
    async def slow_observe(run_id, client):
        await asyncio.sleep(0.01)
        return observations.pop(0)

    selected._observe = slow_observe
    state = selected.create(
        VisualTaskRequest(task="timeout", max_actions=1, max_duration_seconds=0.001)
    )
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "failed"
    assert "duration limit" in result["error"]
    assert executor.calls == []


def test_unexpected_interface_change_fails_visual_verification(monkeypatch):
    first = visual()
    changed = visual(text=["Unexpected interface content"])
    observations = [("obs-1", first), ("obs-2", changed)]
    plans = [action_plan("obs-1")]
    selected, executor = manager(monkeypatch, observations, plans)
    state = selected.create(
        VisualTaskRequest(task="verify", max_actions=1, max_consecutive_failures=1)
    )
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "failed"
    assert result["latest_verification"]["success"] is False
    assert executor.calls


def test_approval_result_pauses_without_claiming_success(monkeypatch):
    observations = [("obs-1", visual())]
    plans = [action_plan("obs-1")]
    selected, _ = manager(
        monkeypatch,
        observations,
        plans,
        FakeExecutor(ToolResult("approval_required", "windows_input_action", approval_id="approval-1")),
    )
    state = selected.create(VisualTaskRequest(task="Type SHIRO"))
    asyncio.run(selected._run(state["run_id"]))
    result = selected.get(state["run_id"])
    assert result["status"] == "waiting_approval"
    assert result["approval_id"] == "approval-1"
    assert result["action_count"] == 0
