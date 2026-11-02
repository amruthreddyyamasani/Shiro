# SHIRO — Desktop-First Computer Control Architecture

**Author:** SHIRO Architecture Team
**Status:** PROPOSED / PLANNING PHASE ONLY
**Target Environment:** Windows 11 (AMD64), Python 3.12, Local Ollama
**Hardware Profile:** 16 GB System RAM, NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM)

> **Milestone C decision update (2026-11-02):** The active architecture for
> visual autonomous computer control is visual-first: OBSERVE → UNDERSTAND →
> PLAN → VALIDATE → ACT → OBSERVE AGAIN → VERIFY. Windows UI Automation and
> browser DOM inspection are optional future extensions, not the primary
> interaction path for this milestone. The older UIA-first sections below are
> retained as future-extension notes; the implemented path is documented in
> `shiro/visual.py`, `shiro/visual_control.py`, and `shiro/input_control.py`.

---

## 1. Executive Summary & Architectural Philosophy

SHIRO is an air-gapped, local-first Windows 11 autonomous workstation. The addition of desktop-first computer control transforms SHIRO from a file-and-code assistant into a bounded, transparent, local computer-use agent.

### Core Architecture Tenets
1. **Zero Unattended or Stealth Control:** Every desktop interaction must be visually signaled, bound to user-approved applications, and halted by an uninterceptable Emergency Stop.
2. **Local-First & Multi-Modal Inference:** All planning and image processing runs on the local NVIDIA RTX 4050 GPU (6 GB VRAM) using local Ollama models. No telemetry, cloud computer services, or remote screenshots.
3. **Accessibility-Tree-First, Vision-Assisted:** Physical mouse clicks at arbitrary pixel coordinates are fragile and error-prone. The primary control interface is **Windows UI Automation (UIA)** (deterministic control IDs, bounding boxes, element roles). Screen capture with vision assistance acts as secondary perception when UI automation trees are sparse or custom-rendered.
4. **Defense-in-Depth Supervisor:** Mouse, keyboard, and window activations are gated through a centralized Action Supervisor that enforces bounds on rates, execution times, target process IDs, and consequential actions.

---

## 2. Windows 11 Technical Stack & Component Decomposition

```
                                  ┌──────────────────────────────┐
                                  │      React 19 Frontend       │
                                  │  [Live Status / Panic Stop]  │
                                  └──────────────┬───────────────┘
                                                 │ HTTP / SSE (127.0.0.1)
                                  ┌──────────────▼───────────────┐
                                  │       FastAPI Backend        │
                                  │  - Central Action Supervisor │
                                  │  - App Allowlist & Policies  │
                                  └──────────────┬───────────────┘
                                                 │
                      ┌──────────────────────────┴──────────────────────────┐
                      ▼                                                     ▼
     ┌─────────────────────────────────┐                   ┌─────────────────────────────────┐
     │      Semantic Desktop Layer     │                   │     Visual Perception Layer     │
     │ - pywinauto / ctypes UIA        │                   │ - Windows Graphics Capture      │
     │ - Window Enumeration (Enum)     │                   │ - mss / Pillow (low VRAM)       │
     │ - Accessible Object Hierarchy   │                   │ - Local Vision Model / OCR      │
     └────────────────┬────────────────┘                   └────────────────┬────────────────┘
                      │                                                     │
                      └──────────────────────────┬──────────────────────────┘
                                                 ▼
                               ┌───────────────────────────────────┐
                               │     Hardware & Input Actuator     │
                               │ - Windows SendInput (pyautogui)   │
                               │ - App Target Focus Lock           │
                               │ - Emergency Global Hook (ESC/F12) │
                               └───────────────────────────────────┘
```

### Component Details:

### A. Semantic Accessibility Layer (Windows UI Automation)
* **Technology:** Microsoft UI Automation (UIA) COM interfaces via `pywinauto` (UIA backend) and `ctypes` bindings.
* **Responsibilities:**
  * Enumerate active desktop top-level windows (`EnumWindows`, `GetWindowTextW`, `GetWindowThreadProcessId`).
  * Inspect UI element trees: extract control types (Button, Edit, Document, ComboBox, TabItem), names, Automation IDs, and bounding rectangles (`BoundingRectangle`).
  * Perform deterministic control interactions (Invoke pattern, Value pattern, Selection pattern) without moving the physical cursor when supported.

### B. Visual Perception Layer (Screen Capture)
* **Technology:** High-performance desktop screen capture using `mss` (DirectX/GDI-backed) or `d3dshot` / Windows Graphics Capture API (WGC).
* **Responsibilities:**
  * Capture snapshots **only** upon explicit task step execution (never continuous polling or background surveillance).
  * Crop screenshots strictly to the bounding box of the user-approved target application window (`GetWindowRect`).
  * Mask sensitive system areas (Windows taskbar tray, notification centers, non-target monitor regions).
  * Support local vision inference via Ollama multi-modal endpoints (`qwen3.5:2b` / `qwen3.5:4b` vision projector) to resolve controls missing UIA labels.

### C. Input Actuator & Action Supervisor
* **Technology:** Win32 `SendInput` API (via `pyautogui` / `pynput` wrapped in a strict supervisor).
* **Responsibilities:**
  * Validate that the active foreground window belongs to the allowlisted PID before dispatching any mouse or keyboard event.
  * Clamp mouse coordinates strictly within the target window's client rectangle (`GetClientRect`).
  * Enforce human-like move pacing and action timeouts.
  * Provide an immediate panic halt via global keyboard hook (e.g., `Esc` held for 500ms or corner mouse fling).

### D. Browser Automation Layer
* **Technology:** Playwright (Chromium/Firefox) locally installed in `.venv`.
* **Responsibilities:**
  * Headless or headful browser control restricted to `localhost` or explicitly allowlisted web endpoints.
  * Deterministic DOM selectors, accessibility trees, and network tracing.

---

## 3. Hardware & Local Inference Budget (RTX 4050 6GB)

| Component | VRAM Footprint | System RAM Footprint | Execution Latency |
| :--- | :---: | :---: | :---: |
| **`shiro:latest` (Qwen 3.5 2B Q8_0)** | ~2.5 GB | ~1.2 GB | ~35 ms / token |
| **Vision Projector (`mmproj`)** | ~0.5 GB | ~0.5 GB | ~120 ms / frame |
| **Windows UI Automation Cache** | 0 GB | ~80 MB | < 25 ms / query |
| **Screenshot Buffer (1080p Crop)** | 0 GB | ~25 MB | < 10 ms / frame |
| **FastAPI + SQLite + Frontend** | 0 GB | ~250 MB | < 5 ms / request |
| **Total Runtime Headroom** | **~3.0 GB / 6.0 GB (50%)** | **~2.1 GB / 16.0 GB (13%)** | **Comfortable Headroom** |

> [!NOTE]
> The NVIDIA RTX 4050 (6 GB VRAM) cannot load a 7B or 14B vision model alongside desktop context. The existing `shiro:latest` / `qwen3.5:2b` architecture includes a lightweight 331M multi-modal vision projector (`qwen3vl_merger`), which fits comfortably within the 6 GB boundary while leaving 3.0 GB of VRAM free for operating system rendering and PyTorch/Playwright buffers.

---

## 4. Central Action Supervisor: State Machine

```
      ┌──────────────────────────┐
      │       Task Planned       │
      └────────────┬─────────────┘
                   │ User Dispatches Run
      ┌────────────▼─────────────┐
      │   Target App Validation  │◄──────── PID not allowlisted ──► [TASK REJECTED]
      └────────────┬─────────────┘
                   │ Target Validated
      ┌────────────▼─────────────┐
      │   Window Focus & Check   │◄──────── Consequential Action ──► [WAITING_APPROVAL]
      └────────────┬─────────────┘
                   │ Safe Action / Approved
      ┌────────────▼─────────────┐
      │ Visual Banner Activated  │ (Desktop control indicator active)
      └────────────┬─────────────┘
                   │
      ┌────────────▼─────────────┐
      │      SendInput Call      ├────────── Emergency Stop ───────► [HALT & LOCKOUT]
      └────────────┬─────────────┘
                   │ Step Complete
      ┌────────────▼─────────────┐
      │ Post-Action Verification │ (UIA state / visual delta)
      └──────────────────────────┘
```

### Safety Rules Enforced by Supervisor:
1. **Target Window Lock:** `GetForegroundWindow()` must equal the approved target process. If the user alt-tabs or another application pops up, input is instantly withheld.
2. **Coordinate Clamping:** All `(x, y)` coordinates must be relative to the client area and must not intersect desktop boundary areas (Start menu, system tray).
3. **Emergency Stop (Panic Button):**
   * Hardware: Flinging the mouse to any screen corner activates `pyautogui.FAILSAFE`.
   * Keyboard: Pressing `Ctrl+Alt+Escape` halts execution via global Win32 hook.
   * UI: A persistent "HALT SHIRO" floating button and frontend Panic Pill in the status bar.
4. **Bounded Action Limit:** Maximum 15 actions per desktop task before mandatory re-authorization.
5. **Rate Limiting:** Minimum 250ms delay between simulated mouse/keyboard events to prevent buffer flooding.

---

## 5. Integration with Existing SHIRO Infrastructure

| Existing SHIRO Subsystem | Desktop Control Integration Point |
| :--- | :--- |
| **`shiro/tools.py`** | Register new tools: `windows_list_windows`, `windows_focus_window`, `windows_inspect_element_tree`, `windows_capture_window`, `windows_send_input`. |
| **`shiro/database.py`** | Leverage existing `tool_approvals` table. Dangerous actions (close app, send keys, click submit) write pending approvals with bounding box and screenshot thumbnail. |
| **`shiro/agent.py`** | Sequential step loop already supports `approval_required` and pause/resume states via SQLite WAL. |
| **`shiro/app.py`** | Enable `windows_app_control` capability flag dynamically when desktop control module is active. |
| **Frontend UI** | Approvals view displays the target window name and coordinates. Context panel displays active desktop control status. |
