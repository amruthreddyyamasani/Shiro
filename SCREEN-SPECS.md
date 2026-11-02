# SHIRO — Screen Specifications & Layout Blueprint

This document details the layout, data dependencies, interactive behaviors, and states for every major screen in the SHIRO application.

---

## 1. Application Shell & Sidebar

### Layout Grid
- **Left Sidebar**: 260px fixed width (collapsible to 68px icon-only on compact displays).
  - Top: SHIRO Brand mark + version tag (`v0.1.0`) + local privacy badge (`Local-Only`).
  - Action: "New Conversation" button (`Cmd/Ctrl + N`).
  - Primary Nav Links:
    1. **Dashboard** (Icon: `LayoutDashboard`)
    2. **Chat** (Icon: `MessageSquare`)
    3. **Task Manager** (Icon: `CheckSquare`)
    4. **Approvals** (Icon: `ShieldAlert`, with dynamic pending count badge)
    5. **Memory Center** (Icon: `Brain`)
    6. **Tool Registry** (Icon: `Wrench`)
    7. **Settings** (Icon: `Settings`)
  - Bottom: Backend & Ollama connectivity indicator pill + current active model.
- **Center Workspace**: Flex-1 container displaying active route view.
- **Contextual Right Panel**: 340px collapsible drawer toggled via `Cmd/Ctrl + B` or header button.

---

## 2. Screen: Dashboard (Operational Overview)

### Purpose
Provides an instant status check of the local AI operating environment, active tasks, pending approvals, and quick actions.

### Data Sources
- `GET /healthz` -> Backend, Ollama, and Tool safety statuses.
- `GET /v1/models/recommend` -> Active model and installed models.
- `GET /v1/tasks` & `GET /v1/tasks/resumable` -> Task statistics.
- `GET /v1/tool-approvals?status=pending` -> Pending approval count.
- `GET /v1/capabilities` -> Allowed execution boundaries.

### Visual Components
1. **System Health Grid**: 4 operational metric cards:
   - *Engine Status*: "Online" / "Offline" with localhost endpoint.
   - *Active Model*: "shiro:latest" (1.9B Q8_0) with parameters.
   - *Active Tasks*: Total count of planned/running tasks.
   - *Pending Approvals*: Urgent count with click-through to Approvals view.
2. **Quick Action Bar**:
   - "Start New Chat" -> Navigates to `/chat`.
   - "Synthesize Task" -> Opens Task Planner modal.
   - "Review Approvals" -> Navigates to `/approvals`.
   - "Inspect Memories" -> Navigates to `/memory`.
3. **Execution Capabilities Table**:
   - Displays all 6 capabilities from `/v1/capabilities` with status tags (`registered_allowlist`, `registered_approval_required`, `registered_read_only`, `disabled`).
4. **Recent Tasks / Activity List**:
   - Shows latest 5 tasks with status badges and timestamps.

---

## 3. Screen: Chat (Conversational Workspace)

### Purpose
The primary interactive surface for chatting with local Ollama models, viewing streaming responses, and inspecting agent plans and step execution.

### Data Sources
- `GET /v1/conversations/{id}/messages` -> Historical messages.
- `POST /v1/chat/stream` -> NDJSON streaming response.
- `GET /v1/models/recommend` -> Model badge information.

### Visual Components
1. **Chat Header**:
   - Active Conversation Title.
   - Model Selector badge (`shiro:latest`).
   - Personality Mode Selector (`adaptive` / `friendly` / `professional`).
   - Clear / New Conversation button.
   - Context Panel toggle.
2. **Message Stream Container**:
   - Scrollable timeline.
   - **User Message**: Right-aligned, raised surface with primary text and timestamp.
   - **Assistant Message**: Left-aligned, markdown-rendered with syntax-highlighted code blocks, copy button, and token stream cursor.
   - **Agent Plan Card**: Inline step breakdown with icons indicating pending, running, or verified step results.
   - **Confirmation Box**: Inline interactive approval card when a step requires authorization.
3. **Bottom Composer**:
   - Auto-growing multiline textarea (up to 200px max height).
   - Enter to send, Shift+Enter for new line.
   - Stop generation button (active while streaming).
   - Character count and localhost privacy reminder (`100% Local Inference`).

---

## 4. Screen: Task Manager

### Purpose
Inspect, monitor, approve, pause, resume, and cancel agent tasks.

### Data Sources
- `GET /v1/tasks` -> All tasks.
- `GET /v1/tasks/{id}` -> Step breakdown.
- `GET /v1/tasks/{id}/runs` -> Execution run records.
- Action endpoints: `/approve`, `/pause`, `/resume`, `/cancel`, `/run`.

### Visual Components
- **Filter Tabs**: All / Planned / Waiting Approval / Running / Paused / Succeeded / Failed.
- **Task List View**: Cards displaying title, status mark, step progress count, creation timestamp.
- **Task Detail Drawer**:
  - Full step checklist with tool names and arguments.
  - Verification criteria.
  - Run attempts & retry count.
  - Action buttons based on status:
    - If `waiting_approval` -> "Approve" / "Deny".
    - If `planned` -> "Run Task".
    - If `running` -> "Pause".
    - If `paused` -> "Resume".
    - Always available -> "Cancel".

---

## 5. Screen: Approval Center

### Purpose
Centralized queue for all pending one-time tool authorizations and task approvals.

### Data Sources
- `GET /v1/tool-approvals?status=pending`
- `POST /v1/tool-approvals/{id}/decide`
- `GET /v1/tasks` (filtered for `waiting_approval`)

### Visual Components
- Clean card-based queue.
- Detailed parameter breakdown for each request:
  - Exact file path or URL.
  - Operation type (`create_text_file`, `web_search`, etc.).
  - Reason / intended side effect.
  - Expiration countdown timer.
- Action Buttons: "Authorize Once" (Cyan) vs "Deny" (Crimson).

---

## 6. Screen: Memory Center

### Purpose
Allows users to view, search, add, edit, and delete long-term memories extracted by SHIRO or created manually.

### Data Sources
- `GET /v1/memories` & `GET /v1/memories/search?q={query}`
- `POST /v1/memories`, `PATCH /v1/memories/{id}`, `DELETE /v1/memories/{id}`

### Visual Components
- Search bar with instant debounced filtering.
- Category filter pills: All, Preferences, Projects, Skills, General.
- Memory Grid with category badge, creation date, and content preview.
- "Add Memory" modal and inline "Edit" / "Delete" actions.

---

## 7. Screen: Tools & Capabilities

### Purpose
Expose all 8 registered tools, their parameters, approval rules, and safety boundaries.

### Data Sources
- `GET /v1/tools`
- `GET /v1/capabilities`

### Visual Components
- Tool cards displaying tool name, description, approval requirement badge (`Approval Required` vs `Auto-Permitted`), and parameter schema.

---

## 8. Screen: Activity & Audit Log

### Purpose
Provides an immutable chronological audit trail of all deterministic tool executions, human approval decisions, and agent step execution runs stored in SQLite.

### Data Sources
- `GET /v1/audit?category={all|security_audit|task_event}&search={query}&limit={100}`

### Visual Components
- Category filter pills: All Records, Security Audits (tool audits & approval decisions), Task Events (step execution runs).
- Real-time search bar filtering across tool names, status, error messages, and task UUIDs.
- Expandable event cards with JSON payload viewer (arguments, result outputs, errors, timestamps).
- Status marks for Succeeded, Approved, Failed, Denied, Pending, and Running.

---

## 9. Screen: Self-Improvement & Code Review

### Purpose
Enables supervised local self-improvement workflows: staging code proposals, inspecting file-level unified diffs, running isolated staging test harnesses, applying changes with atomic snapshots, and rolling back.

### Data Sources
- `GET /v1/self-improvement/requests`
- `POST /v1/self-improvement/requests` (Create proposal)
- `POST /v1/self-improvement/requests/{id}/decide` (Approve/Reject)
- `POST /v1/self-improvement/requests/{id}/test` (Isolated sandbox test)
- `POST /v1/self-improvement/requests/{id}/apply` (Apply to workspace with backup)
- `POST /v1/self-improvement/requests/{id}/rollback` (Revert to snapshot)

### Visual Components
- Split master-detail layout: Proposals list on left, detailed proposal inspector and diff viewer on right.
- Color-coded unified diff viewer (`+` green additions, `-` red deletions, `@@` cyan headers).
- Test harness execution status badge (`passed`, `failed`, `not_run`) with console output display.
- Strict state-machine action bar (Approve for Testing -> Run Staging Tests -> Apply Changes -> Roll Back).

---

## 10. Screen: System & Runtime Information

### Purpose
Direct introspection of Windows OS, local Ollama daemon, and SQLite persistence store with factual, non-fabricated metrics.

### Data Sources
- `GET /v1/system/info`
- `GET /v1/models/recommend`

### Visual Components
- Host OS Card: Operating system name, release, build, architecture, Python version, and Shiro version.
- Local Inference Card: Ollama connection status, base URL, active model, and list of installed models with disk sizes.
- Persistence Card: Database file path, file size in bytes/MB, WAL mode status, and PRAGMA foreign keys verification.
- Execution Boundaries Card: Localhost network binding (127.0.0.1:8000), approved workspace roots, and AST execution scope.

---

## 11. Screen: Application & Safety Settings

### Purpose
Allows configuration of assistant personality mode and active Ollama model while clearly distinguishing configurable items from immutable safety boundaries.

### Data Sources
- `GET /v1/settings`
- `POST /v1/settings/personality`
- `POST /v1/models/select`
- `GET /healthz`

### Visual Components
- Configurable Personality selector: Adaptive, Friendly, Professional with immediate backend confirmation.
- Configurable Model switcher: Dropdown populated with verified installed Ollama models.
- Immutable Security Boundaries card: Clear display of disabled cloud AI, localhost binding, and disabled thinking mode.
- Read-Only Persistence card: Storage path, WAL mode, and max history limits.
