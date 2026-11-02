"""Safety tests for the bounded desktop input supervisor."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shiro.input_control import (
    DesktopInputController,
    DesktopInputRequest,
    InputBackend,
    VirtualScreenBounds,
)
from shiro.tools import ToolError, ToolPolicyError


class FakeBackend(InputBackend):
    def __init__(self, *, fail: bool = False):
        self.calls: list[DesktopInputRequest] = []
        self.releases = 0
        self.fail = fail

    def screen_bounds(self) -> VirtualScreenBounds:
        return VirtualScreenBounds(left=0, top=0, width=100, height=80)

    def execute(self, request: DesktopInputRequest) -> dict[str, object]:
        if self.fail:
            raise ToolError("fake input failure")
        self.calls.append(request)
        return {"action": request.action, "status": "issued"}

    def release_all(self) -> None:
        self.releases += 1


def active_window(process_name: str = "notepad.exe") -> dict[str, object]:
    return {
        "active_window": {
            "hwnd": 42,
            "pid": 100,
            "process_name": process_name,
            "title": "Untitled - Notepad",
            "is_foreground": True,
        }
    }


def controller(backend: FakeBackend | None = None) -> tuple[DesktopInputController, FakeBackend]:
    selected = backend or FakeBackend()
    return (
        DesktopInputController(
            backend=selected,
            active_window_reader=active_window,
            min_interval_seconds=0,
        ),
        selected,
    )


def test_pointer_action_is_validated_and_sent_to_allowlisted_foreground():
    selected, backend = controller()
    result = selected.execute(
        DesktopInputRequest(action="click", x=40, y=20, target_hwnd=42)
    )
    assert result["status"] == "issued"
    assert backend.calls[0].action == "click"


def test_out_of_bounds_pointer_is_rejected_before_backend():
    selected, backend = controller()
    with pytest.raises(ToolPolicyError, match="outside"):
        selected.execute(DesktopInputRequest(action="move", x=100, y=80))
    assert backend.calls == []


def test_disallowed_foreground_is_rejected():
    selected, backend = DesktopInputController(
        backend := FakeBackend(),
        active_window_reader=lambda: active_window("powershell.exe"),
        min_interval_seconds=0,
    ), backend
    with pytest.raises(ToolPolicyError, match="allowlist"):
        selected.execute(DesktopInputRequest(action="click", x=1, y=1))
    assert backend.calls == []


def test_invalid_action_arguments_and_keys_are_rejected():
    with pytest.raises(ValidationError):
        DesktopInputRequest(action="click", x=1)
    with pytest.raises(ValidationError):
        DesktopInputRequest(action="scroll", x=1, y=1, amount=0)
    with pytest.raises(ValidationError):
        DesktopInputRequest(action="type_text", text="ok", key="enter")


def test_backend_failure_is_not_reported_as_success():
    selected, _ = controller(FakeBackend(fail=True))
    with pytest.raises(ToolError, match="fake input failure"):
        selected.execute(DesktopInputRequest(action="press_key", key="enter"))


def test_emergency_stop_releases_and_blocks_future_actions():
    selected, backend = controller()
    selected.stop()
    assert backend.releases == 1
    with pytest.raises(ToolError, match="Emergency stop"):
        selected.execute(DesktopInputRequest(action="move", x=1, y=1))
    selected.reset()
    selected.execute(DesktopInputRequest(action="move", x=1, y=1))
    assert len(backend.calls) == 1


def test_rate_limit_prevents_accidental_repeated_input():
    backend = FakeBackend()
    selected = DesktopInputController(
        backend=backend,
        active_window_reader=active_window,
        min_interval_seconds=10,
    )
    selected.execute(DesktopInputRequest(action="move", x=1, y=1))
    with pytest.raises(ToolPolicyError, match="rate limit"):
        selected.execute(DesktopInputRequest(action="move", x=2, y=2))
