# SHIRO — API Integration Map

This document provides a comprehensive and verified mapping of every HTTP endpoint in the SHIRO FastAPI backend (`shiro/app.py`), the underlying SQLite persistence layer (`shiro/database.py`), data models (`shiro/models.py`), streaming mechanics, identified backend gaps, and corresponding frontend usage.

---

## 1. System & Runtime Endpoints

### 1.1 Root Info
- **Feature**: Basic application identification and version.
- **HTTP Method**: `GET`
- **Path**: `/`
- **Request Schema**: None
- **Response Schema**:
  ```json
  {
    "name": "Shiro",
    "version": "0.1.0"
  }
  ```
- **Persistence**: None
- **Authentication**: None (Localhost only)
- **Streaming**: No
- **Errors**: Standard HTTP 500 on unexpected runtime failure.
- **Frontend Usage**: Connection verification, ping.

### 1.2 Health Check
- **Feature**: Real-time operational status of core backend services and safety configuration.
- **HTTP Method**: `GET`
- **Path**: `/healthz`
- **Request Schema**: None
- **Response Schema** (`HealthResponse`):
  ```json
  {
    "status": "ok",
    "model": "shiro:latest",
    "ollama_base_url": "http://127.0.0.1:11434",
    "thinking_disabled": true,
    "tools_enabled": true
  }
  ```
- **Persistence**: None
- **Authentication**: None (Localhost only)
- **Streaming**: No
- **Errors**: Standard HTTP 500 on failure.
- **Frontend Usage**: Dashboard status bar, network connectivity pill, pre-flight check.

---

## 2. Model Management Endpoints

### 2.1 Model Recommendation & Listing
- **Feature**: Lists all locally installed Ollama models and indicates the currently active/recommended model.
- **HTTP Method**: `GET`
- **Path**: `/v1/models/recommend`
- **Request Schema**: None
- **Response Schema** (`ModelRecommendationResponse`):
  ```json
  {
    "current_model": "shiro:latest",
    "models": [
      {
        "name": "shiro:latest",
        "size": 2683396814,
        "installed": true,
        "recommended": true
      },
      {
        "name": "qwen3.5:2b",
        "size": 2683396812,
        "installed": true,
        "recommended": false
      },
      {
        "name": "qwen3.5:4b",
        "size": 3324173934,
        "installed": true,
        "recommended": false
      }
    ]
  }
  ```
- **Persistence**: Queries local Ollama `/api/tags` via `OllamaClient.list_models()`.
- **Authentication**: None
- **Streaming**: No
- **Errors**:
  - `503 Service Unavailable`: If Ollama daemon is unreachable or responds with error.
- **Frontend Usage**: Dashboard model badge, model selector header in chat workspace.

---

## 3. Capabilities Endpoints

### 3.1 List Capabilities
- **Feature**: Discloses configured system boundaries, tool scopes, and safety flags.
- **HTTP Method**: `GET`
- **Path**: `/v1/capabilities`
- **Request Schema**: None
- **Response Schema** (`list[CapabilityResponse]`):
  ```json
  [
    {
      "name": "local_file_read",
      "status": "registered_allowlist",
      "description": "Read files only after configured-root and approval checks.",
      "execution_enabled": true
    },
    {
      "name": "local_file_write",
      "status": "registered_approval_required",
      "description": "Writes require a future explicit allowlist and approval.",
      "execution_enabled": true
    },
    {
      "name": "windows_app_control",
      "status": "disabled",
      "description": "No Windows application controller is installed.",
      "execution_enabled": false
    },
    {
      "name": "windows_system_info",
      "status": "registered_read_only",
      "description": "Read non-sensitive OS and runtime metadata only.",
      "execution_enabled": true
    },
    {
      "name": "web_request",
      "status": "fixed_search_approval_required",
      "description": "Only the fixed public search tool is available, with approval per query.",
      "execution_enabled": true
    },
    {
      "name": "self_improvement",
      "status": "review_only",
      "description": "Code changes require a reviewable proposal and test results.",
      "execution_enabled": false
    }
  ]
  ```
- **Persistence**: In-memory inspection of `runtime_settings`.
- **Authentication**: None
- **Streaming**: No
- **Errors**: None
- **Frontend Usage**: Capabilities & Tools view, Safety & Policy panel on Dashboard.

---

## 4. Tools & Tool Approval Endpoints

### 4.1 List Registered Tools
- **Feature**: Returns descriptions and approval rules for all registered tools.
- **HTTP Method**: `GET`
- **Path**: `/v1/tools`
- **Request Schema**: None
- **Response Schema** (`list[ToolDefinitionResponse]`):
  ```json
  [
    {"name": "list_files", "description": "List files in an approved workspace directory.", "requires_approval": false},
    {"name": "search_filenames", "description": "Search filenames matching a query within an approved workspace directory.", "requires_approval": false},
    {"name": "read_text_file", "description": "Read UTF-8 text from a file within an approved workspace directory.", "requires_approval": false},
    {"name": "create_directory", "description": "Create a directory in an approved workspace directory.", "requires_approval": true},
    {"name": "create_text_file", "description": "Create or overwrite a UTF-8 text file in an approved workspace directory.", "requires_approval": true},
    {"name": "calculate", "description": "Safely evaluate a basic arithmetic expression.", "requires_approval": false},
    {"name": "web_search", "description": "Search DuckDuckGo HTML for public documentation and web results.", "requires_approval": true},
    {"name": "windows_system_info", "description": "Read non-sensitive local operating-system and runtime metadata.", "requires_approval": false}
  ]
  ```
- **Persistence**: Read-only from `ToolRegistry`.
- **Authentication**: None
- **Streaming**: No
- **Errors**: None
- **Frontend Usage**: Tools catalog, tool badge in trace lines.

### 4.2 Execute Tool Directly
- **Feature**: Validates, requests approval for, or runs an authorized tool call.
- **HTTP Method**: `POST`
- **Path**: `/v1/tools/{tool_name}/execute`
- **Request Schema** (`ToolExecuteRequest`):
  ```json
  {
    "arguments": {"path": "<approved-root>\\test.txt"},
    "task_id": "optional-uuid",
    "step_id": 1,
    "approval_id": "optional-approval-uuid"
  }
  ```
- **Response Schema** (`ToolResultResponse`):
  ```json
  {
    "status": "succeeded | approval_required | failed",
    "tool_name": "create_text_file",
    "output": {"created": true, "bytes_written": 42},
    "error": null,
    "approval_id": "uuid-if-approval-required",
    "audit_id": 12
  }
  ```
- **Persistence**: Creates `tool_approvals` entry if approval required; creates `tool_audit` entry on completion.
- **Authentication**: None (Fails with 403 if `allow_tools` is false).
- **Streaming**: No
- **Errors**:
  - `403 Forbidden`: Tool execution disabled in settings.
  - `422 Unprocessable Entity`: Argument schema validation failure.
- **Frontend Usage**: Task execution runner, manual tool tester.

### 4.3 List Tool Approvals
- **Feature**: Lists pending or decided tool approval requests.
- **HTTP Method**: `GET`
- **Path**: `/v1/tool-approvals`
- **Query Parameters**: `status` (`pending`, `approved`, `denied`, optional)
- **Response Schema** (`list[ToolApprovalResponse]`):
  ```json
  [
    {
      "id": "uuid",
      "task_id": "uuid | null",
      "step_id": 1,
      "tool_name": "create_text_file",
      "arguments": {"path": "..."},
      "affected_resources": ["..."],
      "reason": "Creating test file",
      "status": "pending | approved | denied",
      "created_at": "2026-11-01T14:00:00Z",
      "expires_at": "2026-11-01T14:10:00Z",
      "decided_at": null,
      "consumed_at": null
    }
  ]
  ```
- **Persistence**: `tool_approvals` SQLite table.
- **Frontend Usage**: Approval Center, Chat inline confirmation cards.

### 4.4 Get Single Tool Approval
- **Feature**: Fetch details of a specific tool approval by ID.
- **HTTP Method**: `GET`
- **Path**: `/v1/tool-approvals/{approval_id}`
- **Response Schema**: `ToolApprovalResponse`
- **Errors**: `404 Not Found` if missing.
- **Frontend Usage**: Single approval verification view.

### 4.5 Decide Tool Approval
- **Feature**: Approve or deny a pending tool operation (one-time token).
- **HTTP Method**: `POST`
- **Path**: `/v1/tool-approvals/{approval_id}/decide`
- **Request Schema** (`ToolApprovalDecisionRequest`):
  ```json
  {
    "approved": true
  }
  ```
- **Response Schema**: `ToolApprovalResponse`
- **Persistence**: Updates `tool_approvals` row with `status` and `decided_at`.
- **Errors**:
  - `404 Not Found`: If approval does not exist.
  - `409 Conflict`: If approval is not currently `pending`.
- **Frontend Usage**: Approval Center buttons ("Authorize Once", "Deny").

---

## 5. Conversations & Messages Endpoints

### 5.1 Create Conversation
- **Feature**: Initializes a new persistent conversation thread.
- **HTTP Method**: `POST`
- **Path**: `/v1/conversations`
- **Request Schema** (`ConversationCreateRequest`):
  ```json
  {
    "title": "Optional conversation title"
  }
  ```
- **Response Schema** (`ConversationResponse`, status `201 Created`):
  ```json
  {
    "id": "c1f77d6f-71aa-4258-a5b6-7ebfb40a0df2",
    "title": "New conversation",
    "created_at": "2026-11-01T14:30:00Z",
    "updated_at": "2026-11-01T14:30:00Z"
  }
  ```
- **Persistence**: Inserts into `conversations` SQLite table.
- **Frontend Usage**: "New Chat" sidebar action.

### 5.2 Get Messages in Conversation
- **Feature**: Retrieves history of messages for a conversation (up to max history limit, default 24).
- **HTTP Method**: `GET`
- **Path**: `/v1/conversations/{conversation_id}/messages`
- **Request Schema**: None
- **Response Schema** (`list[MessageResponse]`):
  ```json
  [
    {
      "id": 1,
      "conversation_id": "c1f77d6f-71aa-4258-a5b6-7ebfb40a0df2",
      "role": "user",
      "content": "Hello SHIRO",
      "created_at": "2026-11-01T14:30:01Z"
    },
    {
      "id": 2,
      "conversation_id": "c1f77d6f-71aa-4258-a5b6-7ebfb40a0df2",
      "role": "assistant",
      "content": "Hello! How can I assist you today?",
      "created_at": "2026-11-01T14:30:05Z"
    }
  ]
  ```
- **Persistence**: Reads from `messages` SQLite table.
- **Errors**: `404 Not Found` if conversation does not exist.
- **Frontend Usage**: Loading conversation thread when clicked from sidebar.

---

## 6. Chat & Streaming Protocol

### 6.1 Chat Stream
- **Feature**: Streams local AI response token-by-token via Ollama, injects personality prompt and relevant memory, stores conversation history, and triggers asynchronous background memory extraction.
- **HTTP Method**: `POST`
- **Path**: `/v1/chat/stream`
- **Request Schema** (`MessageRequest`):
  ```json
  {
    "content": "What is the capital of France?",
    "conversation_id": "optional-uuid"
  }
  ```
- **Response Protocol**: `fastapi.responses.StreamingResponse` with `media_type="application/x-ndjson"`.
- **Stream Format**: Each line is a single valid JSON object ending with `\n`.
  - **Token Event** (emitted per token chunk from local Ollama):
    ```json
    {"type": "token", "conversation_id": "c1f77d6f-...", "content": "The"}
    ```
  - **Done Event** (emitted upon successful completion of model output):
    ```json
    {"type": "done", "conversation_id": "c1f77d6f-...", "content": "The capital of France is Paris."}
    ```
  - **Error Event** (emitted if Ollama fails or stream is severed):
    ```json
    {"type": "error", "conversation_id": "c1f77d6f-...", "error": {"code": "ollama_error", "message": "Connection refused"}}
    ```
- **Lifecycle & Persistence**:
  1. If `conversation_id` is null, a new conversation is created automatically.
  2. The user's message is immediately written to the `messages` table.
  3. System personality prompt (`PERSONALITY_PROMPTS[settings.personality_mode]`) is injected.
  4. Memory manager extracts top keyword-matched memories and prepends them as system context.
  5. Tokens are streamed to the client.
  6. Upon stream completion (`done`), the full assistant message is written to the `messages` table.
  7. In the background (after the stream closes), memory extraction runs on the user query.
- **Errors**: `404 Not Found` if provided `conversation_id` is invalid.
- **Frontend Usage**: Main Chat composer, interactive streaming bubble.

---

## 7. Tasks & Agent Engine Endpoints

### 7.1 Plan Agent Task
- **Feature**: Uses local model to plan a structured list of steps with tool assignments.
- **HTTP Method**: `POST`
- **Path**: `/v1/agent/plan`
- **Request Schema** (`AgentPlanRequest`):
  ```json
  {
    "request": "Inspect files in workspace and calculate total count",
    "conversation_id": "optional-uuid"
  }
  ```
- **Response Schema** (`AgentPlanResponse`):
  ```json
  {
    "task_id": "uuid",
    "title": "Inspect workspace files",
    "status": "waiting_approval | planned",
    "steps": [
      {
        "id": 1,
        "task_id": "uuid",
        "position": 0,
        "description": "List files in directory",
        "status": "pending",
        "attempts": 0
      }
    ]
  }
  ```
- **Persistence**: Writes `tasks`, `task_steps`, `agent_step_specs`, and `task_approvals` (if required).
- **Errors**:
  - `422 Unprocessable Entity`: Model output failed JSON schema validation or tool argument check.
  - `503 Service Unavailable`: Ollama unreachable.
- **Frontend Usage**: Chat agent task creation, Task Manager.

### 7.2 Create Manual Task
- **Feature**: Creates an explicit task plan without LLM synthesis.
- **HTTP Method**: `POST`
- **Path**: `/v1/tasks`
- **Request Schema** (`TaskCreateRequest`):
  ```json
  {
    "title": "Sample Task",
    "steps": ["Step 1 description", "Step 2 description"],
    "max_retries": 2,
    "requires_approval": true
  }
  ```
- **Response Schema** (`TaskResponse`, status `201 Created`).
- **Frontend Usage**: Task creation modal.

### 7.3 List Tasks
- **Feature**: Returns all historical and active tasks.
- **HTTP Method**: `GET`
- **Path**: `/v1/tasks`
- **Response Schema**: `list[TaskResponse]`
- **Frontend Usage**: Task Manager list, Dashboard active tasks count.

### 7.4 List Resumable Tasks
- **Feature**: Returns tasks in `planned`, `paused`, or `running` state.
- **HTTP Method**: `GET`
- **Path**: `/v1/tasks/resumable`
- **Response Schema**: `list[TaskResponse]`
- **Frontend Usage**: Restart recovery banner, active task widget.

### 7.5 Get Task Detail
- **Feature**: Returns single task with its steps.
- **HTTP Method**: `GET`
- **Path**: `/v1/tasks/{task_id}`
- **Response Schema**: `TaskResponse`
- **Errors**: `404 Not Found`
- **Frontend Usage**: Task Inspector drawer / details view.

### 7.6 List Task Runs
- **Feature**: Returns execution attempts and verification results for each step.
- **HTTP Method**: `GET`
- **Path**: `/v1/tasks/{task_id}/runs`
- **Response Schema**: `list[AgentRunRecordResponse]`
- **Frontend Usage**: Trace timeline, step details.

### 7.7 Approve Task
- **Feature**: Authorizes a task currently in `waiting_approval` status.
- **HTTP Method**: `POST`
- **Path**: `/v1/tasks/{task_id}/approve`
- **Request Schema** (`TaskApprovalRequest`):
  ```json
  {
    "approved": true,
    "note": "Approved by user"
  }
  ```
- **Response Schema**: `TaskResponse`
- **Errors**: `409 Conflict` if not `waiting_approval`.
- **Frontend Usage**: Approval Center, Chat task card.

### 7.8 Pause / Resume / Cancel Task
- **Pause**: `POST /v1/tasks/{task_id}/pause` (Only planned/running tasks).
- **Resume**: `POST /v1/tasks/{task_id}/resume` (Only paused tasks).
- **Cancel**: `POST /v1/tasks/{task_id}/cancel` (Signals cooperative cancellation).
- **Responses**: `TaskResponse`
- **Frontend Usage**: Task control toolbar.

### 7.9 Execute Task
- **Synchronous**: `POST /v1/tasks/{task_id}/run` -> `AgentRunResponse`
- **Background**: `POST /v1/tasks/{task_id}/run/background` (Status `202 Accepted`) -> `AgentRunResponse`
- **Frontend Usage**: "Run Task" button in Task Manager.

---

## 8. Memory Management Endpoints

### 8.1 List Memories
- **HTTP Method**: `GET`
- **Path**: `/v1/memories`
- **Query Parameter**: `category` (`preferences`, `projects`, `skills`, `general`, optional)
- **Response Schema**: `list[MemoryResponse]`
- **Frontend Usage**: Memory Center list.

### 8.2 Create Memory
- **HTTP Method**: `POST`
- **Path**: `/v1/memories`
- **Request Schema** (`MemoryCreateRequest`):
  ```json
  {
    "category": "preferences",
    "content": "User prefers dark mode and concise code snippets"
  }
  ```
- **Response Schema**: `MemoryResponse`
- **Frontend Usage**: "Add Memory" modal.

### 8.3 Search Memories
- **HTTP Method**: `GET`
- **Path**: `/v1/memories/search`
- **Query Parameter**: `q` (string, 1-200 chars)
- **Response Schema**: `list[MemoryResponse]`
- **Frontend Usage**: Memory search bar.

### 8.4 Update Memory
- **HTTP Method**: `PATCH`
- **Path**: `/v1/memories/{memory_id}`
- **Request Schema** (`MemoryUpdateRequest`):
  ```json
  {
    "category": "skills",
    "content": "Updated content..."
  }
  ```
- **Response Schema**: `MemoryResponse`
- **Frontend Usage**: Memory edit drawer.

### 8.5 Delete Memory
- **HTTP Method**: `DELETE`
- **Path**: `/v1/memories/{memory_id}`
- **Response**: `204 No Content`
- **Frontend Usage**: Memory delete action.

---

## 9. Web Actions & Self-Improvement Endpoints

### 9.1 Web Actions
- `POST /v1/web/actions`: Propose a web request.
- `GET /v1/web/actions`: List web actions.
- `POST /v1/web/actions/{action_id}/approve`: Decide web action.

### 9.2 Self-Improvement
- `POST /v1/self-improvement/requests`: Create a proposal with staged files.
- `GET /v1/self-improvement/requests`: List proposals.
- `POST /v1/self-improvement/requests/{request_id}/decide`: Approve or reject.
- `POST /v1/self-improvement/requests/{request_id}/test`: Run isolated tests in temp copy.
- `POST /v1/self-improvement/requests/{request_id}/apply`: Apply with automatic backup.
- `POST /v1/self-improvement/requests/{request_id}/rollback`: Roll back to pre-applied state.

---

## 10. Resolved Backend Gaps

All previously identified backend gaps have been resolved with minimal, tested implementations:

| Gap ID | Description | Resolution Status | Verified Implementation |
|--------|-------------|-------------------|-------------------------|
| **GAP-01** | `GET /v1/conversations` | **RESOLVED** | `app.py` exposes `GET /v1/conversations` querying `Database.list_conversations()`. |
| **GAP-02** | `DELETE /v1/conversations/{id}` | **RESOLVED** | `app.py` exposes `DELETE /v1/conversations/{id}` with cascading deletion and 204 No Content. |
| **GAP-03** | `GET /v1/audit` | **RESOLVED** | Exposes `GET /v1/audit` with category filtering (`security_audit`, `task_event`), search queries, and timestamps. |
| **GAP-04** | `GET /v1/system/info` | **RESOLVED** | Exposes `GET /v1/system/info` returning factual Windows OS, Python, Ollama daemon, and SQLite metrics. |
| **GAP-05** | `POST /v1/models/select` | **RESOLVED** | Exposes `POST /v1/models/select` with validation against installed local Ollama models. |
| **GAP-06** | `POST /v1/settings/personality` | **RESOLVED** | Exposes `POST /v1/settings/personality` with validation (`adaptive`, `friendly`, `professional`). |
| **GAP-07** | `GET /v1/settings` | **RESOLVED** | Exposes `GET /v1/settings` disclosing active configuration and immutable safety constraints. |
