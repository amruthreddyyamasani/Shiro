# SHIRO — Desktop Control Staged Implementation Plan

**Strategy:** Incremental, Test-Driven, Safety-First Evolution
**Pre-condition:** Strictly maintain all existing backend APIs, frontend views, and security boundaries.

> **Active implementation note (2026-11-02):** Milestone C follows the
> visual-first architecture selected by the user. UIA and DOM inspection are
> not primary dependencies. Stage A structured perception, Stage B validated
> input, Stage C observe-act-verify, and Stage D frontend integration are
> implemented incrementally in the current SHIRO modules; this plan remains a
> roadmap for later hardening and native-host work.

---

## 1. Phased Roadmap Overview

```
 [MILESTONE A] ──► [MILESTONE B] ──► [MILESTONE C] ──► [MILESTONE D] ──► [MILESTONE E] ──► [MILESTONE F]
 Window Discovery   UI Element Tree   Controlled Mouse  Multi-Step Flow   Playwright Browser   Unified Workflows
 & Process Enum     & Screenshot      & Safe Typing      with Approvals   Automation          (Desktop+Web+Code)
 (READ-ONLY)        (READ-ONLY)       (ISOLATED APP)     (SUPERVISED)     (EXISTING LIB)      (END-TO-END)
```

---

## 2. Milestone Specifications

### Milestone A — Read-Only Desktop & Window Discovery (RECOMMENDED FIRST MILESTONE)
* **Goal:** Allow SHIRO to query active desktop windows, identify running applications, extract window titles, PIDs, and process names without modifying any desktop state.
* **Architecture:**
  * Win32 API via `ctypes` (`EnumWindows`, `IsWindowVisible`, `GetWindowTextW`, `GetWindowThreadProcessId`).
  * Process metadata lookup via Win32 `QueryFullProcessImageNameW`.
  * Filter out system windows, hidden windows, and blacklisted security processes (UAC, Task Manager, password vaults).
* **Dependencies:** Zero new external dependencies (pure Python standard library `ctypes`).
* **Tools Added to `shiro/tools.py`:**
  1. `windows_list_windows(only_visible=True, include_process_info=True)`
  2. `windows_get_active_window()`
* **Permission Level:** Read-only (`registered_read_only`), auto-permitted within safe whitelist.
* **Failure Handling:** Invalid HWND or closed window returns structured error without crashing.
* **Tests:** `tests/test_windows_discovery.py` — verify enumeration of known windows, blacklisting of system processes, and handling of closed HWNDs.
* **Acceptance Criteria:**
  * `GET /v1/capabilities` shows `windows_app_control: registered_read_only`.
  * Agent can accurately report which applications the user has open.
  * Zero mouse movement or keyboard input possible in this milestone.

---

### Milestone B — UI Element Identification & Window Screenshot Capture
* **Goal:** Inspect the accessibility tree of an approved application window and capture a cropped screenshot of that window.
* **Architecture:**
  * `pywinauto.Desktop(backend="uia")` or lightweight COM UIA wrappers to traverse UI controls (buttons, inputs, tabs).
  * `mss` screen capture cropped strictly to target window rectangle (`GetClientRect`).
* **Dependencies:** `pywinauto`, `mss`, `Pillow`.
* **Tools Added:**
  1. `windows_inspect_element_tree(hwnd, max_depth=3)`
  2. `windows_capture_window(hwnd, output_filename=None)`
* **Permission Level:** Read-only (`registered_read_only`), restricted to non-sensitive applications.
* **Failure Handling:** Minimized windows return clean warning; clipped coordinates outside screen are handled.
* **Tests:** `tests/test_element_tree.py`, `tests/test_screen_capture.py`.
* **Acceptance Criteria:**
  * Returns structured list of interactive elements (type, name, automation ID, bounding box).
  * Cropped image generated in temporary directory; no non-target monitors captured.

---

### Milestone C — Controlled Input in Designated Test Application
* **Goal:** Execute physical mouse clicks and keystrokes exclusively within a disposable test application (e.g., Windows Notepad or custom Tkinter sandbox).
* **Architecture:**
  * Action Supervisor: validates `GetForegroundWindow() == target_hwnd` before dispatching any `SendInput`.
  * Mouse movement with human-like cubic easing.
  * Hardware Emergency Stop: Mouse corner flick or `Ctrl+Alt+Escape`.
* **Dependencies:** `pyautogui`, `pynput`.
* **Tools Added:**
  1. `windows_focus_window(hwnd)`
  2. `windows_click_element(hwnd, element_name_or_coords)`
  3. `windows_type_text(hwnd, text, clear_first=False)`
* **Permission Level:** Approval-gated (`registered_approval_required`).
* **Failure Handling:** Focus loss immediately aborts action; emergency stop raises uncatchable exception.
* **Tests:** `tests/test_action_supervisor.py`, `tests/test_controlled_input.py`.
* **Acceptance Criteria:**
  * Can launch/focus Notepad, type "SHIRO Local Test", and verify text via UIA.
  * Attempting to click outside target window boundaries raises an immediate error.

---

### Milestone D — Approval-Gated Multi-Step Desktop Workflows
* **Goal:** Enable the agent planner to synthesize and execute multi-step desktop workflows under human supervision.
* **Architecture:**
  * Tie desktop tools into the existing `AgentStore` and `tool_approvals` table.
  * Dangerous actions (Save As, Close, Delete) generate pending approvals in the frontend.
* **Dependencies:** Existing SHIRO agent infrastructure.
* **Tests:** Multi-step workflow test in `tests/test_desktop_agent.py`.
* **Acceptance Criteria:**
  * Multi-step plan executes sequentially. Consequential step pauses with `status: waiting_approval`. Frontend approves and task finishes.

---

### Milestone E — Local Browser Automation (Playwright)
* **Goal:** Automate browser workflows on local or whitelisted web applications using existing `playwright` package.
* **Architecture:**
  * Isolated Chromium context launched on user-configured ports.
  * CDP-based element selector and navigation engine.
* **Dependencies:** `playwright` (already installed in `.venv`).
* **Tools Added:** `browser_navigate`, `browser_click`, `browser_type`, `browser_get_page_content`.
* **Acceptance Criteria:**
  * Navigates local web apps, fills forms, and inspects DOM without mouse interception.

---

### Milestone F — Unified Workflows (Desktop + Browser + Code)
* **Goal:** Seamlessly coordinate desktop applications, browser tasks, and file operations in a single autonomous workflow.
* **Acceptance Criteria:**
  * Agent reads CSV file, opens desktop app or browser, enters data, verifies completion, and logs immutable audit trail.

---

## 3. Explicit Recommendation for Phase 1

### **Proceed with Milestone A: Read-Only Desktop & Window Discovery**
1. **Zero Risk:** Purely read-only; impossible to cause unintended mouse clicks, keystrokes, or window focus theft.
2. **Zero New External Dependencies:** Can be implemented entirely via Python's standard library `ctypes` calling standard Windows 11 User32 and Kernel32 APIs.
3. **Immediate Architectural Value:** Gives SHIRO awareness of the user's active desktop context (which applications are running, which window has focus) to inform conversations and tasks.
4. **Verifiable In Isolation:** Can be fully unit-tested with existing `pytest` suite without requiring special mock hardware.
