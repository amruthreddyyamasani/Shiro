"""Bounded, approval-gated Windows mouse and keyboard control.

This module is deliberately separate from perception. Vision proposes data;
this module validates the request, re-checks the foreground window, and is the
only code path that may call the Windows input API.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import platform
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, model_validator

from .tools import (
    DEFAULT_WINDOW_ALLOWLIST,
    PROTECTED_WINDOW_BLACKLIST,
    ToolDefinition,
    ToolError,
    ToolPolicyError,
    get_active_window_metadata,
)


ActionName = Literal[
    "move",
    "click",
    "double_click",
    "right_click",
    "scroll",
    "type_text",
    "press_key",
    "hotkey",
    "release_all",
]


class DesktopInputRequest(BaseModel):
    """One bounded input operation.

    Coordinates are absolute virtual-desktop pixels and must be paired with a
    fresh observation by higher-level execution code.
    """

    action: ActionName
    x: int | None = Field(default=None, ge=-16_000, le=16_000)
    y: int | None = Field(default=None, ge=-16_000, le=16_000)
    amount: int | None = Field(default=None, ge=-20, le=20)
    text: str | None = Field(default=None, max_length=4_000)
    key: str | None = Field(default=None, min_length=1, max_length=32)
    keys: list[str] | None = Field(default=None, min_length=2, max_length=4)
    target_hwnd: int | None = Field(default=None, gt=0)
    target_label: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_action_arguments(self) -> "DesktopInputRequest":
        point_actions = {"move", "click", "double_click", "right_click"}
        if self.action in point_actions and (self.x is None or self.y is None):
            raise ValueError("x and y are required for pointer actions")
        if self.action == "scroll" and (self.x is None or self.y is None):
            raise ValueError("x and y are required for scroll")
        if self.action == "scroll" and (self.amount is None or self.amount == 0):
            raise ValueError("scroll amount must be non-zero")
        if self.action == "type_text" and not self.text:
            raise ValueError("text is required for type_text")
        if self.action == "press_key" and not self.key:
            raise ValueError("key is required for press_key")
        if self.action == "hotkey" and not self.keys:
            raise ValueError("keys are required for hotkey")
        if self.action != "type_text" and self.text is not None:
            raise ValueError("text is only valid for type_text")
        if self.action != "press_key" and self.key is not None:
            raise ValueError("key is only valid for press_key")
        if self.action != "hotkey" and self.keys is not None:
            raise ValueError("keys are only valid for hotkey")
        if self.action != "scroll" and self.amount is not None:
            raise ValueError("amount is only valid for scroll")
        if self.action == "release_all" and any(
            value is not None
            for value in (
                self.x,
                self.y,
                self.amount,
                self.text,
                self.key,
                self.keys,
                self.target_label,
            )
        ):
            raise ValueError("release_all does not accept action arguments")
        return self


@dataclass(frozen=True)
class VirtualScreenBounds:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width - 1

    @property
    def bottom(self) -> int:
        return self.top + self.height - 1

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


class InputBackend:
    """Backend protocol implemented by the real Win32 and test backends."""

    def screen_bounds(self) -> VirtualScreenBounds:
        raise NotImplementedError

    def execute(self, request: DesktopInputRequest) -> dict[str, Any]:
        raise NotImplementedError

    def release_all(self) -> None:
        raise NotImplementedError


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("data", _INPUT_UNION),
    ]


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class EmergencyStop:
    """Thread-safe stop latch shared by the executor and the API control."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._release: Callable[[], None] | None = None
        self._lock = threading.RLock()

    def bind_release(self, release: Callable[[], None]) -> None:
        with self._lock:
            self._release = release

    def is_set(self) -> bool:
        return self._event.is_set()

    def stop(self) -> None:
        self._event.set()
        with self._lock:
            release = self._release
        if release is not None:
            release()

    def reset(self) -> None:
        self._event.clear()


class GlobalEmergencyStopService:
    """Process-global Ctrl+Alt+Escape stop hook.

    The hook observes only the configured emergency chord. It does not record
    ordinary keystrokes, and the callback delegates immediately to the shared
    emergency-stop handler.
    """

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_QUIT = 0x0012
    VK_CONTROL = {0xA2, 0xA3, 0x11}
    VK_ALT = {0xA4, 0xA5, 0x12}
    VK_ESCAPE = {0x1B}

    def __init__(self, on_trigger: Callable[[str], None]) -> None:
        self._on_trigger = on_trigger
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._thread_id: int | None = None
        self._hook: Any | None = None
        self._proc: Any | None = None
        self._start_error: str | None = None

    @property
    def start_error(self) -> str | None:
        return self._start_error

    def start(self) -> bool:
        if platform.system() != "Windows":
            self._start_error = "Global emergency stop is only supported on Windows"
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(
            target=self._run,
            name="shiro-global-emergency-stop",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._start_error is None and bool(self._thread_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread_id and platform.system() == "Windows":
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, self.WM_QUIT, 0, 0
                )
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            thread_id = int(kernel32.GetCurrentThreadId())
            self._thread_id = thread_id
            hook_proc_type = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_int,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            )
            pressed: set[int] = set()
            triggered = False

            def hook_proc(code: int, message: int, data_ptr: int) -> int:
                nonlocal triggered
                if code >= 0 and message in {
                    self.WM_KEYDOWN,
                    self.WM_SYSKEYDOWN,
                    self.WM_KEYUP,
                    self.WM_SYSKEYUP,
                }:
                    data = ctypes.cast(
                        data_ptr, ctypes.POINTER(_KBDLLHOOKSTRUCT)
                    ).contents
                    vk = int(data.vkCode)
                    is_down = message in {self.WM_KEYDOWN, self.WM_SYSKEYDOWN}
                    if is_down:
                        pressed.add(vk)
                    else:
                        pressed.discard(vk)
                    has_ctrl = bool(pressed.intersection(self.VK_CONTROL))
                    has_alt = bool(pressed.intersection(self.VK_ALT))
                    has_escape = bool(pressed.intersection(self.VK_ESCAPE))
                    if is_down and has_ctrl and has_alt and has_escape and not triggered:
                        triggered = True
                        try:
                            self._on_trigger("ctrl+alt+escape")
                        except Exception:
                            pass
                    if not (has_ctrl or has_alt or has_escape):
                        triggered = False
                    if triggered and (has_ctrl and has_alt and has_escape):
                        return 1
                return int(user32.CallNextHookEx(self._hook, code, message, data_ptr))

            self._proc = hook_proc_type(hook_proc)
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                hook_proc_type,
                ctypes.c_void_p,
                ctypes.wintypes.DWORD,
            ]
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
            user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
            user32.CallNextHookEx.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            ]
            user32.CallNextHookEx.restype = ctypes.c_long
            user32.GetMessageW.argtypes = [
                ctypes.POINTER(ctypes.wintypes.MSG),
                ctypes.c_void_p,
                ctypes.wintypes.UINT,
                ctypes.wintypes.UINT,
            ]
            user32.GetMessageW.restype = ctypes.c_int
            user32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
            # A low-level hook callback is owned by this Python thread. Passing
            # the executable module handle makes Windows look for the callback
            # in a native DLL and fails with ERROR_MOD_NOT_FOUND (126).
            # A null module handle is the supported form for this callback.
            module = None
            self._hook = user32.SetWindowsHookExW(
                self.WH_KEYBOARD_LL, self._proc, module, 0
            )
            if not self._hook:
                error = ctypes.get_last_error()
                self._start_error = ctypes.FormatError(error) if error else "SetWindowsHookExW failed"
                return
            self._ready.set()
            message = ctypes.wintypes.MSG()
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self._start_error = str(exc)
        finally:
            self._ready.set()
            if self._hook and platform.system() == "Windows":
                try:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
                except OSError:
                    pass
            self._hook = None
            self._thread_id = None


class Win32InputBackend(InputBackend):
    """Small ctypes wrapper over the documented user32 SendInput API."""

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    WHEEL_DELTA = 120

    VK: dict[str, int] = {
        "backspace": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "pause": 0x13,
        "capslock": 0x14,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "pageup": 0x21,
        "pagedown": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "insert": 0x2D,
        "delete": 0x2E,
        "win": 0x5B,
        "lwin": 0x5B,
        "rwin": 0x5C,
        "f1": 0x70,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,
    }

    def __init__(self) -> None:
        self._user32: Any | None = None
        self._held: set[int] = set()
        self._held_mouse_buttons: set[str] = set()
        self._lock = threading.RLock()

    def _api(self) -> Any:
        if platform.system() != "Windows":
            raise ToolError("Windows input is only supported on Windows")
        if self._user32 is None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetSystemMetrics.argtypes = [ctypes.c_int]
            user32.GetSystemMetrics.restype = ctypes.c_int
            user32.SendInput.argtypes = [
                ctypes.wintypes.UINT,
                ctypes.POINTER(_INPUT),
                ctypes.c_int,
            ]
            user32.SendInput.restype = ctypes.wintypes.UINT
            self._user32 = user32
        return self._user32

    def screen_bounds(self) -> VirtualScreenBounds:
        user32 = self._api()
        return VirtualScreenBounds(
            left=user32.GetSystemMetrics(76),
            top=user32.GetSystemMetrics(77),
            width=user32.GetSystemMetrics(78),
            height=user32.GetSystemMetrics(79),
        )

    @staticmethod
    def _absolute(value: int, start: int, size: int) -> int:
        if size <= 1:
            return 0
        return round((value - start) * 65_535 / (size - 1))

    def _send(self, inputs: list[_INPUT]) -> None:
        if not inputs:
            return
        sent = self._api().SendInput(
            len(inputs),
            (_INPUT * len(inputs))(*inputs),
            ctypes.sizeof(_INPUT),
        )
        for event in inputs[:sent]:
            self._track_keyboard_event(event)
        if sent != len(inputs):
            self._release_held_without_tracking()
            error = ctypes.get_last_error()
            message = ctypes.FormatError(error) if error else "unknown SendInput error"
            raise ToolError(f"SendInput inserted {sent}/{len(inputs)} events: {message}")

    def _track_keyboard_event(self, event: _INPUT) -> None:
        if event.type == self.INPUT_MOUSE:
            flags = int(event.mi.dwFlags)
            if flags & self.MOUSEEVENTF_LEFTDOWN:
                self._held_mouse_buttons.add("left")
            if flags & self.MOUSEEVENTF_LEFTUP:
                self._held_mouse_buttons.discard("left")
            if flags & self.MOUSEEVENTF_RIGHTDOWN:
                self._held_mouse_buttons.add("right")
            if flags & self.MOUSEEVENTF_RIGHTUP:
                self._held_mouse_buttons.discard("right")
            return
        if event.type != self.INPUT_KEYBOARD or not event.ki.wVk:
            return
        if event.ki.dwFlags & self.KEYEVENTF_UNICODE:
            return
        if event.ki.dwFlags & self.KEYEVENTF_KEYUP:
            self._held.discard(int(event.ki.wVk))
        else:
            self._held.add(int(event.ki.wVk))

    def _release_held_without_tracking(self) -> None:
        if not self._held and not self._held_mouse_buttons:
            return
        releases: list[_INPUT] = [_INPUT(
            type=self.INPUT_KEYBOARD,
            ki=_KEYBDINPUT(
                wVk=code,
                wScan=0,
                dwFlags=self.KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            ),
        ) for code in sorted(self._held)]
        if "left" in self._held_mouse_buttons:
            releases.append(self._mouse(0, 0, self.MOUSEEVENTF_LEFTUP))
        if "right" in self._held_mouse_buttons:
            releases.append(self._mouse(0, 0, self.MOUSEEVENTF_RIGHTUP))
        try:
            self._api().SendInput(
                len(releases),
                (_INPUT * len(releases))(*releases),
                ctypes.sizeof(_INPUT),
            )
        finally:
            self._held.clear()
            self._held_mouse_buttons.clear()

    def _mouse(self, x: int, y: int, flags: int, data: int = 0) -> _INPUT:
        bounds = self.screen_bounds()
        return _INPUT(
            type=self.INPUT_MOUSE,
            mi=_MOUSEINPUT(
                dx=self._absolute(x, bounds.left, bounds.width),
                dy=self._absolute(y, bounds.top, bounds.height),
                mouseData=data & 0xFFFFFFFF,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )

    def _keyboard(self, vk: int, flags: int = 0, scan: int = 0) -> _INPUT:
        return _INPUT(
            type=self.INPUT_KEYBOARD,
            ki=_KEYBDINPUT(
                wVk=vk,
                wScan=scan,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )

    def _key_code(self, key: str) -> int:
        normalized = key.casefold().strip()
        if normalized in self.VK:
            return self.VK[normalized]
        if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
            return ord(normalized.upper())
        raise ToolError(f"Unsupported keyboard key: {key}")

    def _click_inputs(self, x: int, y: int, down: int, up: int) -> list[_INPUT]:
        absolute = self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE | self.MOUSEEVENTF_VIRTUALDESK
        return [self._mouse(x, y, absolute), self._mouse(x, y, down), self._mouse(x, y, up)]

    def execute(self, request: DesktopInputRequest) -> dict[str, Any]:
        with self._lock:
            if request.action == "move":
                self._send([self._mouse(request.x or 0, request.y or 0,
                                        self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE | self.MOUSEEVENTF_VIRTUALDESK)])
            elif request.action in {"click", "right_click", "double_click"}:
                if request.action == "right_click":
                    down, up = self.MOUSEEVENTF_RIGHTDOWN, self.MOUSEEVENTF_RIGHTUP
                else:
                    down, up = self.MOUSEEVENTF_LEFTDOWN, self.MOUSEEVENTF_LEFTUP
                inputs = self._click_inputs(request.x or 0, request.y or 0, down, up)
                if request.action == "double_click":
                    inputs.extend(self._click_inputs(request.x or 0, request.y or 0, down, up)[1:])
                self._send(inputs)
            elif request.action == "scroll":
                absolute = self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE | self.MOUSEEVENTF_VIRTUALDESK
                self._send([
                    self._mouse(request.x or 0, request.y or 0, absolute),
                    self._mouse(request.x or 0, request.y or 0, self.MOUSEEVENTF_WHEEL,
                                (request.amount or 0) * self.WHEEL_DELTA),
                ])
            elif request.action == "type_text":
                inputs: list[Win32InputBackend._INPUT] = []
                for character in request.text or "":
                    codepoint = ord(character)
                    if codepoint > 0xFFFF:
                        encoded = character.encode("utf-16-le")
                        units = [encoded[i] | (encoded[i + 1] << 8) for i in range(0, len(encoded), 2)]
                    else:
                        units = [codepoint]
                    for unit in units:
                        inputs.extend([
                            self._keyboard(0, self.KEYEVENTF_UNICODE, unit),
                            self._keyboard(0, self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP, unit),
                        ])
                self._send(inputs)
            elif request.action in {"press_key", "hotkey"}:
                names = [request.key] if request.action == "press_key" else request.keys or []
                codes = [self._key_code(name or "") for name in names]
                inputs = [self._keyboard(code) for code in codes]
                inputs.extend(self._keyboard(code, self.KEYEVENTF_KEYUP) for code in reversed(codes))
                self._send(inputs)
            elif request.action == "release_all":
                self.release_all()
            return {"action": request.action, "status": "issued"}

    def release_all(self) -> None:
        with self._lock:
            if not self._held and not self._held_mouse_buttons:
                return
            inputs = [self._keyboard(code, self.KEYEVENTF_KEYUP) for code in sorted(self._held)]
            if "left" in self._held_mouse_buttons:
                inputs.append(self._mouse(0, 0, self.MOUSEEVENTF_LEFTUP))
            if "right" in self._held_mouse_buttons:
                inputs.append(self._mouse(0, 0, self.MOUSEEVENTF_RIGHTUP))
            try:
                self._send(inputs)
            finally:
                self._held.clear()
                self._held_mouse_buttons.clear()


class DesktopInputController:
    """Safety supervisor around a pluggable input backend."""

    def __init__(
        self,
        backend: InputBackend | None = None,
        active_window_reader: Callable[[], dict[str, Any]] | None = None,
        *,
        max_duration_seconds: float = 5.0,
        min_interval_seconds: float = 0.25,
    ) -> None:
        self.backend = backend or Win32InputBackend()
        self.active_window_reader = active_window_reader or get_active_window_metadata
        self.max_duration_seconds = max_duration_seconds
        self.min_interval_seconds = min_interval_seconds
        self.emergency_stop = EmergencyStop()
        self.emergency_stop.bind_release(self.backend.release_all)
        self._last_action_at = 0.0
        self._lock = threading.Lock()

    def stop(self) -> None:
        self.emergency_stop.stop()

    def reset(self) -> None:
        self.emergency_stop.reset()

    def _check_foreground(self, request: DesktopInputRequest) -> dict[str, Any]:
        metadata = self.active_window_reader() or {}
        active = metadata.get("active_window")
        if not isinstance(active, dict):
            raise ToolPolicyError("No approved foreground window is available")
        process_name = str(active.get("process_name") or "").casefold()
        if process_name in PROTECTED_WINDOW_BLACKLIST or process_name not in DEFAULT_WINDOW_ALLOWLIST:
            raise ToolPolicyError("Foreground window is outside the approved application allowlist")
        if not active.get("is_foreground", False):
            raise ToolPolicyError("Target window is no longer foreground")
        if request.target_hwnd is not None and active.get("hwnd") != request.target_hwnd:
            raise ToolPolicyError("Foreground window does not match the approved target window")
        return active

    def execute(self, request: DesktopInputRequest) -> dict[str, Any]:
        started = time.monotonic()
        with self._lock:
            if self.emergency_stop.is_set():
                raise ToolError("Emergency stop is active")
            active = self._check_foreground(request)
            bounds = self.backend.screen_bounds()
            if request.action in {"move", "click", "double_click", "right_click", "scroll"}:
                if not bounds.contains(request.x or 0, request.y or 0):
                    raise ToolPolicyError("Pointer coordinates are outside the virtual desktop")
            if request.action != "release_all":
                now = time.monotonic()
                if now - self._last_action_at < self.min_interval_seconds:
                    raise ToolPolicyError("Input rate limit reached; wait before issuing another action")
                self._last_action_at = now
            if time.monotonic() - started > self.max_duration_seconds:
                raise TimeoutError("Input action exceeded its execution budget")
            output = self.backend.execute(request)
            if time.monotonic() - started > self.max_duration_seconds:
                self.stop()
                raise TimeoutError("Input action exceeded its execution budget")
            return {
                **output,
                "foreground_window": {
                    "hwnd": active.get("hwnd"),
                    "pid": active.get("pid"),
                    "process_name": active.get("process_name"),
                    "title": active.get("title"),
                },
                "screen_bounds": {
                    "left": bounds.left,
                    "top": bounds.top,
                    "width": bounds.width,
                    "height": bounds.height,
                },
            }


def desktop_input_tool(controller: DesktopInputController | None = None) -> ToolDefinition:
    """Create the approval-gated low-level desktop input tool."""
    selected = controller or DesktopInputController()

    def _handle(request: DesktopInputRequest, settings: Any) -> dict[str, Any]:
        del settings
        return selected.execute(request)

    def _needs_action_approval(request: DesktopInputRequest) -> bool:
        label = (request.target_label or "").casefold()
        consequential_words = (
            "delete",
            "remove",
            "submit",
            "send",
            "pay",
            "buy",
            "order",
            "confirm",
            "format",
            "uninstall",
            "publish",
            "post",
        )
        if any(word in label for word in consequential_words):
            return True
        # Keyboard sequences can submit, close, or launch a shell even when
        # the current target label is incomplete. Keep those action-specific.
        if request.action in {"press_key", "hotkey"}:
            return True
        if request.action == "type_text" and not any(
            marker in label for marker in ("text field", "editor", "document", "notepad")
        ):
            return True
        return False

    return ToolDefinition(
        name="windows_input_action",
        description=(
            "Issue one bounded mouse or keyboard action to the current approved "
            "foreground Windows application. Every call is approval-gated and audited."
        ),
        input_model=DesktopInputRequest,
        # Safe pointer navigation can run within an approved task. The checker
        # creates a one-time approval for consequential labels and keyboard
        # operations, using the existing ToolExecutor/audit path.
        requires_approval=False,
        handler=_handle,
        approval_checker=_needs_action_approval,
    )
