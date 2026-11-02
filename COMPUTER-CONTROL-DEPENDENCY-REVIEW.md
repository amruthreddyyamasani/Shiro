# SHIRO — Desktop Control Dependency & Hardware Evaluation

**Review Date:** 2026-11-01
**Target Environment:** Windows 11 64-bit, Python 3.12, NVIDIA RTX 4050 6GB

---

## 1. Existing Installed Dependencies Review

A full inspection of the current `.venv` reveals the following relevant packages:

| Installed Package | Version | Current Role | Desktop Control Suitability |
| :--- | :---: | :--- | :--- |
| **`playwright`** | `1.64.1` | Installed in virtualenv | **Ready for browser automation.** Highly mature, deterministic CDP control, supports headless and headful Chromium. |
| **`pydantic`** | `2.14.2` | Data modeling & schemas | Used for strict tool parameter validation. |
| **`fastapi` / `starlette`** | `0.162.0` | API & streaming server | Ready for approval websocket/SSE events. |
| **`httpx`** | `0.28.1` | HTTP client | Local Ollama communication. |
| **`pytest`** | `8.4.2` | Test runner | Unit & integration test execution. |

---

## 2. Windows Desktop Automation Candidate Evaluation

### A. Windows UI Automation (UIA) Libraries

| Library | Mechanism | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- | :---: |
| **`pywinauto`** | Win32 + MS UIA COM | - Native Python bindings<br>- Supports UIA element tree and controls<br>- Can invoke buttons without cursor movement | - Slower on deeply nested trees<br>- Requires careful timeout tuning | **Recommended** (Primary UIA driver) |
| **Raw Win32 / `ctypes`** | Win32 API (`user32.dll`) | - Zero external dependencies<br>- Extremely fast `EnumWindows`, `GetClientRect`, `SendInput` | - Verbose boilerplate for full accessibility trees | **Recommended** (For window discovery & coordinates) |
| **`pywin32`** | Win32 COM wrappers | - Direct COM access | - Heavy install size, C extensions | *Secondary alternative* |

### B. Screen Capture Libraries

| Library | Technique | Performance | VRAM / RAM Usage | Recommendation |
| :--- | :--- | :--- | :--- | :---: |
| **`mss`** | GDI / Direct3D (ctypes) | **Ultra-fast (< 10 ms)** | Pure RAM (~15 MB), **0 VRAM** | **Recommended** (Primary screen capture) |
| **`Pillow` (`ImageGrab`)** | GDI Grab | Moderate (30–60 ms) | Pure RAM (~25 MB), 0 VRAM | *Alternative fallback* |
| **Windows Graphics Capture (WGC)** | WinRT DirectX API | Ultra-fast (hardware) | Hardware VRAM buffer | *Too complex for Phase 1* |

### C. Input Actuator Libraries

| Library | Technique | Failsafe Support | Security Features | Recommendation |
| :--- | :--- | :--- | :--- | :---: |
| **`pyautogui`** | Win32 `mouse_event` / `keybd_event` | **Native corner failsafe** | Simple API, built-in coordinate scaling | **Recommended** (Input actuation) |
| **`pynput`** | Win32 low-level hooks | Excellent event listening | Better for global panic keys (`Ctrl+Alt+Esc`) | **Recommended** (Emergency stop hook) |

---

## 3. Local Model & Vision Projector Capability Audit

An inspection of the local Ollama daemon at `http://127.0.0.1:11434` was conducted on `2026-11-01`:

```
Ollama Models Installed:
  - shiro:latest: size=2.50GB, family=qwen35, parameter_size=1.9B, quant=Q8_0
  - qwen3.5:2b:   size=2.50GB, family=qwen35, parameter_size=1.9B, quant=Q8_0
  - qwen3.5:4b:   size=3.10GB, family=qwen35, parameter_size=4.2B, quant=Q4_K_M
```

### Key Technical Verification:
Running an API `/api/show` query against `shiro:latest` revealed:
* **`capabilities`:** `['completion', 'vision', 'tools', 'thinking']`
* **`projector_info`:** `clip.has_vision_encoder: True`, `projector_type: 'qwen3vl_merger'`, `parameters: 331M`.

### Hardware Assessment:
* The installed `shiro:latest` model **already possesses a 331M multi-modal vision projector** (`qwen3vl_merger`).
* On the 6 GB RTX 4050, `shiro:latest` occupies **2.5 GB of VRAM**.
* Multi-modal inference (feeding a base64 encoded screenshot into `/api/chat` with an image prompt) operates within 3.0 GB total VRAM.
* **No external model downloads or cloud vision APIs are required.**

---

## 4. Minimum New Dependencies for Milestone A & B

To implement read-only desktop discovery and UI automation:

```
# Core UIA and Window Enumeration (Zero heavy C++ compiles)
pywinauto>=0.6.8,<0.7
mss>=9.0,<10.0
Pillow>=10.0,<11.0
```

*Note: For Milestone A (Window Discovery & Process Enumeration), only standard library `ctypes` and `win32` APIs can be used with zero new pip dependencies if desired.*

## 5. Milestone C implementation decision

The installed environment was rechecked before input implementation: `pyautogui`,
`pynput`, `pywin32`, `mss`, and Pillow were not present in SHIRO's virtualenv.
PyAutoGUI's documented corner failsafe is useful, but its multi-monitor behavior
is not a sufficient coordinate-boundary guarantee for SHIRO's virtual-desktop
capture. A global pynput listener was also not added because SHIRO must not
perform hidden background input capture.

For this milestone, SHIRO uses the maintained Windows `user32.SendInput` API
directly through a small, testable ctypes backend. This keeps the dependency
surface unchanged, supports virtual-desktop coordinates, exposes partial-send
failures, and lets the supervisor release tracked keys during emergency stop.
The higher-level controller remains backend-pluggable so a future reviewed
library adapter can be added without changing the policy or audit layer.
