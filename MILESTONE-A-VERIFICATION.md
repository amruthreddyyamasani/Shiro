# Milestone A — Verification Report

Milestone: Read-only Windows desktop discovery
Date: 2026-11-02
Verified by: Buffy (Codebuff)

## 1. Scope

- `windows_list_windows()`
- `windows_get_active_window()`
- Win32 ctypes integration
- Application allowlisting (positive allowlist; blocked processes filtered first)
- Minimal process/window metadata only
- Capability registration in the API
- Existing frontend ToolsView integration

Out of scope for this milestone:
- Screenshot capture
- Window focus/activation/resizing
- Keyboard or mouse control
- Window content reading
- Process command-line or environment collection

## 2. Verification checklist

### Tool implementation
- [x] `windows_list_windows` registered
- [x] `windows_get_active_window` registered
- [x] Input models are Pydantic: `WindowsListWindowsInput`, `EmptyInput`
- [x] Output shapes are dict-based and stable
- [x] No approval required for these read-only tools

### Win32 ctypes correctness
- [x] `EnumWindows` available via `ctypes.windll.user32`
- [x] Callback defined with `ctypes.WINFUNCTYPE(ctypes.c_int, HWND, LPARAM)`
- [x] `OpenDesktopW("Default", ...)` used to try the default desktop station
- [x] `EnumDesktopWindows` used for that desktop handle
- [x] Handles deduplicated by HWND
- [x] `OpenProcess(0x1000)` used for process name lookup
- [x] `QueryFullProcessImageNameW` used for image path
- [x] Process handle closed in `finally`
- [x] DPI awareness set best-effort via `shcore.SetProcessDpiAwareness(2)`
- [x] `GetDpiForWindow` used when available

### Safety properties
- [x] No `SendInput`
- [x] No focus change
- [x] No window activation, resize, or manipulation
- [x] No process command line collected
- [x] No environment variables collected
- [x] No window content collected
- [x] Blacklist filters sensitive/protected processes
- [x] Allowlist requires known processes to be in the allowlist
- [x] Inaccessible processes return empty name safely
- [x] Inaccessible HWND returns `None` safely

### API and frontend exposure
- [x] `GET /v1/capabilities` includes `windows_app_control` and `windows_system_info`
- [x] `windows_app_control` marked `registered_read_only`
- [x] `windows_system_info` marked `registered_read_only`
- [x] Frontend `ToolsView.tsx` renders tool and capability data

## 3. Test results

Command:
```
python -m pytest -q tests/test_windows_discovery.py -q
```
Result: **7 passed**

Selected assertions verified:
- Both tools are registered with the correct input models
- Live execution on Windows returns a successful result with `windows` list and audit record
- Non-Windows would return a safe policy error
- Allowlist and blacklist contents contain the expected entries
- Invalid/non-existent HWND returns `None`
- Blacklisted process windows are filtered out

Command:
```
python -m pytest -q tests/ -q
```
Result: **72 passed, 1 skipped, 1 warning**

Skipped test:
- `test_symlink_escape_is_rejected_when_supported` — symlink creation unavailable in this Windows environment (environmental skip)

## 4. Live execution evidence

Temporary database live run:
- Tool: `windows_list_windows`
- Arguments: `{"only_visible": true, "max_results": 5}`
- Status: `succeeded`
- Result contained enumerated windows with count and audit id

This confirms the implementation works in an interactive desktop session on this machine.

## 5. EnumWindows concern

The handoff notes describe repeated EnumWindows failures from earlier experiments. The current implementation does not use the patterns that typically fail. It uses a stable `WINFUNCTYPE` callback and standard `EnumWindows`/`EnumDesktopWindows` usage. A live enumeration succeeded here, so the earlier failures are not reproducible from the present source.

## 6. DPI awareness

DPI handling is best-effort:
- `SetProcessDpiAwareness(2)` is attempted when `shcore` exists
- `GetDpiForWindow` is used when available
- Failures are tolerated

This is appropriate for a read-only discovery tool.

## 7. Security classification

Read-only. No side effects. No focus manipulation. No input synthesis. No sensitive data collection beyond minimal allowed metadata. Execution is gated by the existing tool policy (`allow_tools` and approved roots are not required for read-only metadata, but tool execution must be enabled for the tool to run).

## 8. Conclusion

Milestone A is **implementated and verified** for the current environment.

The implementation is sound for a read-only Windows desktop discovery capability in an interactive session. The main caveat is environmental: in the absence of an interactive desktop session, results may be empty, which is expected and safe.
