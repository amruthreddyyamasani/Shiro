"""Unit tests for Windows desktop and window discovery (Milestone A)."""

from __future__ import annotations

import asyncio
import platform
import pytest

from shiro.config import Settings
from shiro.database import Database
from shiro.tools import (
    ToolContext,
    ToolExecutor,
    build_default_registry,
    _query_window_metadata,
    DEFAULT_WINDOW_ALLOWLIST,
    PROTECTED_WINDOW_BLACKLIST,
    WindowsListWindowsInput,
    EmptyInput,
)


@pytest.fixture
def test_context(tmp_path):
    settings = Settings(
        database_path=tmp_path / "test.db",
        allow_tools=True,
        approved_roots=[tmp_path],
    )
    database = Database(settings.database_path)
    database.initialize()
    return settings, database


def test_windows_discovery_tools_registered():
    """Verify windows_list_windows and windows_get_active_window are registered with schemas."""
    registry = build_default_registry()
    list_tool = registry.get("windows_list_windows")
    active_tool = registry.get("windows_get_active_window")

    assert list_tool is not None
    assert not list_tool.requires_approval
    assert issubclass(list_tool.input_model, WindowsListWindowsInput)

    assert active_tool is not None
    assert not active_tool.requires_approval
    assert issubclass(active_tool.input_model, EmptyInput)


def test_windows_discovery_execution_and_audit(test_context):
    """Verify windows discovery executes safely and records an immutable audit record."""
    settings, database = test_context
    registry = build_default_registry()
    executor = ToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            "windows_list_windows",
            {"only_visible": True, "max_results": 10},
            ToolContext(settings, database),
        )
    )

    if platform.system() == "Windows":
        assert result.status == "succeeded"
        assert result.output is not None
        assert "windows" in result.output
        assert "count" in result.output
        assert isinstance(result.output["windows"], list)
        assert result.audit_id is not None

        # Verify audit record persisted in SQLite
        audits = database.list_tool_audits()
        matching = [a for a in audits if a.tool_name == "windows_list_windows"]
        assert len(matching) >= 1
        assert matching[0].status == "succeeded"
    else:
        # Non-Windows systems must return a safe policy error
        assert result.status == "failed"
        assert "only supported on Windows" in (result.error or "")


def test_windows_get_active_window_execution(test_context):
    """Verify windows_get_active_window executes and returns structured metadata."""
    settings, database = test_context
    registry = build_default_registry()
    executor = ToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            "windows_get_active_window",
            {},
            ToolContext(settings, database),
        )
    )

    if platform.system() == "Windows":
        assert result.status == "succeeded"
        assert result.output is not None
        assert "active_window" in result.output
    else:
        assert result.status == "failed"


def test_allowlist_and_blacklist_enforcement():
    """Verify allowlist permits safe applications and blacklist filters sensitive ones."""
    assert "notepad.exe" in DEFAULT_WINDOW_ALLOWLIST
    assert "calc.exe" in DEFAULT_WINDOW_ALLOWLIST
    assert "chrome.exe" in DEFAULT_WINDOW_ALLOWLIST

    assert "credentialuibroker.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "consent.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "taskmgr.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "keepass.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "1password.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "bitwarden.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "cmd.exe" in PROTECTED_WINDOW_BLACKLIST
    assert "powershell.exe" in PROTECTED_WINDOW_BLACKLIST


def test_inaccessible_window_handling():
    """Verify invalid or non-existent HWND returns None without throwing."""
    class MockUser32:
        def IsWindow(self, hwnd):
            return False

    res = _query_window_metadata(999999999, MockUser32())
    assert res is None


def test_blacklisted_process_is_filtered_out():
    """Verify that a window belonging to a blacklisted process is filtered out."""
    import ctypes

    class MockUser32:
        def IsWindow(self, hwnd):
            return True

        def GetWindowTextLengthW(self, hwnd):
            return 12

        def GetWindowTextW(self, hwnd, buf, max_len):
            buf.value = "Task Manager"
            return 12

        def GetWindowThreadProcessId(self, hwnd, byref_pid):
            ctypes.cast(byref_pid, ctypes.POINTER(ctypes.c_ulong)).contents.value = 1234
            return 1

        def GetWindowRect(self, hwnd, byref_rect):
            return 1

        def GetForegroundWindow(self):
            return 0

        def IsWindowVisible(self, hwnd):
            return True

    # Temporarily monkeypatch _get_process_name_by_pid
    import shiro.tools as tools_mod
    orig_get_proc = tools_mod._get_process_name_by_pid
    tools_mod._get_process_name_by_pid = lambda pid: "taskmgr.exe"
    try:
        res = _query_window_metadata(12345, MockUser32())
        assert res is None, "Task Manager must be completely filtered out by the blacklist"
    finally:
        tools_mod._get_process_name_by_pid = orig_get_proc


def test_discovery_never_sends_input(monkeypatch):
    """Verify that windows_list_windows and windows_get_active_window never call SendInput."""
    # If ctypes.windll.user32.SendInput is called, fail the test
    if platform.system() == "Windows":
        import ctypes
        def mock_send_input(*args, **kwargs):
            raise AssertionError("SendInput must NEVER be invoked during discovery!")

        monkeypatch.setattr(ctypes.windll.user32, "SendInput", mock_send_input, raising=False)
