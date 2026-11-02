# SHIRO — Implementation Status

Generated: 2026-11-02
By: Buffy (Codebuff)

## Scope of this update

This status reflects the verified Milestone C implementation work:

- Planner edge-case tests
- Recovery-point guidance for version control
- Regression verification for Milestone A and the backend/frontend baseline
- Milestone B structured screenshot-perception validation
- Milestone C controlled input and visual observe-act-verify integration

Browser DOM automation and native always-on-top desktop hosting remain out of scope for this increment.

## Milestone C — current implementation status

### Stage A — perception validation: implemented and tested

- Real Win32 capture produced a 1536x960 RGBA desktop frame.
- The frame reached local Ollama at `127.0.0.1:11434` using `shiro:latest`.
- Ollama returned structured JSON after thinking was explicitly disabled for the bounded vision request.
- Results contain capture dimensions, active-window metadata, normalized target boxes, confidence values, visible text, and uncertainties.
- Observed pixel-space boxes are converted only when safely inside the matching captured frame.
- Temporary PNG cleanup was verified on success and model-failure paths.

### Stage B — controlled input: implemented and tested

- `shiro/input_control.py` is the only input actuator and uses the Windows `SendInput` API through a modular backend.
- Pointer coordinates are checked against the virtual desktop and the foreground process is checked against the existing allowlist/blacklist.
- Move, click, double-click, right-click, scroll, text, supported keys, hotkeys, and release-all are bounded and validated.
- Input failures, rate-limit violations, protected windows, and emergency-stop state fail closed.
- Consequential labels and keyboard operations use one-time approvals bound to exact arguments through the existing executor/audit path.
- The Windows host installs a global `Ctrl+Alt+Escape` low-level emergency hook that observes only that chord, stops active visual runs, and releases tracked keys/buttons.

### Stage C — visual loop: implemented and tested

- `shiro/visual_control.py` implements bounded observe → plan → validate → act → observe → verify execution.
- Pointer actions resolve their center from the current observation target; raw model coordinates are not accepted.
- Stale observation IDs, low-confidence targets, changed screens during approval, action/time/failure limits, cancellation, pause/resume, and verification failures are handled.
- Planning remains local Ollama inference; the vision model never invokes input APIs directly.
- Visual task lifecycle and action history persist in SQLite. Startup marks interrupted active runs paused and review-required; actions are never replayed automatically.

### Stage D — frontend integration: implemented

- The Computer Control workspace shows task state, latest local screenshot, current action, verification, recent actions, approvals, and pause/resume/cancel/emergency-stop controls.
- ECHO maps planning to THINKING, execution to WORKING, verified completion to HAPPY, clarification/approval/failure to CONFUSED, and backend loss to DISCONNECTED.

## Completed capabilities

### Planner reliability
- `AgentOrchestrator.create_plan()` supplies registered tools with authoritative `parameters_schema` from `definition.input_model.model_json_schema()`.
- Tool names are validated before acceptance.
- Tool arguments are validated with Pydantic before persistence or execution.
- Unknown tools and invalid/out-of-range/missing arguments raise `ValueError`.
- Malformed JSON and markdown-fenced JSON are handled.
- Empty plans are rejected.
- Overly long plans are rejected against `max_tool_calls_per_task`.
- Invalid plans are rejected before any persistence or execution.
- Bounded repair exists only for `list_files` (directory) and `calculate` (expression).
- Repair is not applied to other tools, and insufficient repair still fails validation.

### Milestone A — Read-only Windows desktop discovery
- `windows_list_windows` and `windows_get_active_window` are implemented, registered, capability-integrated, and tested.
- Win32 ctypes usage is the standard `WINFUNCTYPE` callback pattern.
- Process name lookup uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and `QueryFullProcessImageNameW`, with handle cleanup in `finally`.
- Allowlist plus protected-process blacklist filtering is in place.
- No focus/input manipulation and no sensitive data collection beyond minimal allowed metadata.

### Milestone B — Approval-gated screenshot perception (initial integration)
- A dependency-free Win32 GDI capture path reads one virtual-desktop frame without mouse, keyboard, focus, or window activation.
- Captured pixels are serialized to a temporary PNG and removed after local Ollama analysis.
- The `screenshots_capture` tool uses the existing validated tool registry and requires explicit approval before capture.
- The FastAPI capability and tool-listing endpoints expose the feature as local-only, approval-gated screen perception.
- The frontend Tools view receives the feature through its existing `/v1/tools` and `/v1/capabilities` integration; no frontend architecture change was required.

### Milestone C — Visual autonomous computer control
- `/v1/computer-control/tasks` starts a bounded local visual task.
- `/v1/computer-control/tasks/{run_id}` exposes persisted execution state and the latest in-memory screenshot preview; screenshots are not persisted to disk by the loop.
- `/v1/computer-control/emergency-stop` and its reset endpoint expose the explicit stop latch; Windows also accepts global `Ctrl+Alt+Escape`.
- Computer control is local-only and is not an unrestricted shell or browser-DOM tool.

### Tests
- New dedicated planner edge-case test module created: `tests/test_planner_edge_cases.py`.
- Existing Milestone A tests still pass.
- Existing tools tests still pass.
- Full backend suite still passes.

### Frontend
- TypeScript compiles cleanly.
- Production build succeeds.

## Verified capabilities

- `tests/test_planner_edge_cases.py` — **21 passed**
- `tests/test_windows_discovery.py` — **7 passed**
- `tests/test_tools.py` — **2 passed, 1 skipped**
- `tests/test_perception.py` — **12 passed**
- `tests/test_api.py` — **19 passed**
- `tests/test_input_control.py` — **7 passed**
- `tests/test_visual_control.py` — **8 passed**
- `tests/test_visual_persistence.py` — **4 passed**
- Full backend suite — **126 passed, 1 skipped, 1 warning**
- Python compilation — **success**
- Frontend `tsc --noEmit` — **success**
- Frontend production build — **success**

### Verified manually
- `create_plan()` was verified with fake Ollama adapters for valid plans, unknown tools, missing arguments, wrong types, out-of-range arguments, malformed JSON, fenced JSON, empty steps, too-long plans, bounded repair, repair insufficiency, and non-execution during planning.
- Real Stage A capture, local Ollama vision, structured parsing, active-window metadata, and temporary-file cleanup were verified on Windows.
- Real Windows C.1 validation used one disposable unsaved Notepad window: SHIRO captured the foreground, issued one `type_text` action, and verified the resulting text with a fresh screenshot and accessibility observation.
- Real Windows `Ctrl+Alt+Escape` stopped an active visual run and wrote an `emergency_stop` audit record; a backend restart recovered an active observation-only run as paused/review-required.

## Missing capabilities

- No dedicated end-to-end planner tests that go through the FastAPI `/v1/agent/plan` route with the real app factory. The current coverage exercises the planner through `AgentOrchestrator.create_plan()` with fakes, which is sufficient for the planner logic itself but does not prove the route layer.
- No Git repository exists in the workspace. This is a process gap, not a code defect.

## Remaining test gaps

- Planner route integration is not covered by its own tests.
- Planner recovery behavior across `run_task` edge cases is covered indirectly by the existing workflow/security tests, but is not the focus here.
- No coverage for the exact API error shape returned by `/v1/agent/plan` for each planner failure class.
- No destructive or consequential desktop actions were used as tests. The disposable Notepad document was not saved.
- The global hook observes only `Ctrl+Alt+Escape`; it is not a keylogger or general background input recorder.
- Native Windows transparent always-on-top companion hosting is not implemented; ECHO remains browser-integrated.

## Recovery point: version control

Before repository preparation, the project and its parent locations had no Git repository. This historical state was verified before initialization.

During the Git-readiness task, a local repository was initialized with an explicit ignore policy. No existing files were deleted, overwritten, reset, or added to remote history. Machine-local configuration, databases, screenshots, logs, benchmark output, caches, and desktop-session metadata remain outside version control.

## Exact commands and results

### Compile
Command:
```
python -m compileall shiro tests
```
Result: **success**

### New planner tests
Command:
```
python -m pytest -q tests/test_planner_edge_cases.py -q
```
Result: **21 passed**

### Focused regression set
Command:
```
python -m pytest -q tests/test_windows_discovery.py tests/test_tools.py tests/test_planner_edge_cases.py -q
```
Result: **30 passed, 1 skipped**

### Full backend suite
Command:
```
python -m pytest -q tests/ -q
```
Result: **119 passed, 1 skipped, 1 warning**

Warning: StarletteDeprecationWarning from the FastAPI test client; environmental, not application logic.

### Frontend TypeScript check
Command:
```
cd frontend && npx tsc --noEmit --pretty
```
Result: **success**

### Frontend production build
Command:
```
cd frontend && npm run build
```
Result: **success**

## Files changed in this session

- `shiro/visual.py`, `shiro/vision_client.py`, `shiro/perception.py` — structured visual schema, local Ollama contract, cleanup/preview metadata
- `shiro/input_control.py`, `shiro/visual_control.py` — validated input supervisor and bounded visual loop
- `shiro/tools.py`, `shiro/perception_registry.py`, `shiro/app.py` — registration, approvals, audit integration, and API routes
- `frontend/src/components/computer/ComputerControlView.tsx` — Computer Control workspace
- `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/app/App.tsx`, `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/components/echo/*` — API/UI/ECHO integration
- `tests/test_visual.py`, `tests/test_input_control.py`, `tests/test_visual_control.py`, `tests/test_perception.py` — coverage
- `IMPLEMENTATION-STATUS.md` — updated

## Out of scope

- Browser automation
- Native always-on-top desktop host

These were not implemented in this increment.
