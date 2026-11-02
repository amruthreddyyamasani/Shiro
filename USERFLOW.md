# SHIRO — User Flows & Interaction Specifications

This document outlines the detailed user journeys across SHIRO's primary operating modes: conversation, task execution, tool authorization, memory management, and recovery.

---

## Flow 1: Launch & Session Initialization

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as SHIRO Frontend
    participant API as FastAPI Backend (127.0.0.1:8000)
    participant Ollama as Local Ollama (127.0.0.1:11434)
    participant DB as SQLite (shiro.db)

    User->>UI: Opens SHIRO in Browser
    UI->>API: GET /healthz
    API-->>UI: HealthResponse (status: ok, model: shiro:latest, tools: enabled)
    UI->>API: GET /v1/models/recommend
    API->>Ollama: GET /api/tags
    Ollama-->>API: Model list (shiro:latest, qwen3.5:2b, qwen3.5:4b)
    API-->>UI: ModelRecommendationResponse
    UI->>API: GET /v1/tasks/resumable
    API->>DB: Query planned/paused/running tasks
    DB-->>API: Returns list
    API-->>UI: Resumable tasks list
    UI->>User: Displays ready Dashboard with real operational metrics
```

### Edge Cases
- **Ollama daemon offline**: Header badge displays red "Ollama Disconnected" pill with instruction: `Run "ollama serve" on Windows`. Chat input is disabled with clear warning.
- **Backend unavailable**: Full-viewport polite reconnect banner with exponential backoff pinging `/healthz`.

---

## Flow 2: Chat & Stream Interaction

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Composer as Chat Composer
    participant Store as Chat Store
    participant API as FastAPI Backend
    participant Ollama as Ollama /api/chat
    participant DB as SQLite

    User->>Composer: Types prompt & presses Enter (or Shift+Enter for multiline)
    Composer->>Store: Optimistic append: {role: "user", content: text}
    Composer->>API: POST /v1/chat/stream {content: text, conversation_id: cid}
    API->>DB: INSERT INTO messages (role="user")
    API->>DB: SELECT memories matching keywords
    DB-->>API: Relevant memories
    API->>Ollama: POST /api/chat {stream: true, think: false, messages: [...]}
    loop Stream NDJSON
        Ollama-->>API: Token chunk
        API-->>Store: {"type": "token", "content": "..."}
        Store-->>Composer: Append chunk to active message bubble
    end
    Ollama-->>API: done: true
    API->>DB: INSERT INTO messages (role="assistant")
    API-->>Store: {"type": "done", "content": "full text"}
    API-)DB: Background: extract_and_store(user_message)
    Store-->>User: Message complete with timestamp and copy button
```

---

## Flow 3: Autonomous Task Planning & Execution

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Chat / Task Manager
    participant API as FastAPI Backend
    participant Agent as Agent Orchestrator
    participant Tools as Tool Registry & Executor
    participant DB as SQLite

    User->>UI: "List all files in workspace and summarize them"
    UI->>API: POST /v1/agent/plan {request: text}
    API->>Agent: create_plan(request)
    Agent->>API: Calls Ollama with tool schemas
    Agent->>DB: create_task_from_plan()
    DB-->>API: task record (status="planned" or "waiting_approval")
    API-->>UI: AgentPlanResponse (task_id, steps: [...])
    UI->>User: Renders interactive Task Plan Card with Step Checklist

    alt If task requires approval
        User->>UI: Clicks "Approve Plan"
        UI->>API: POST /v1/tasks/{task_id}/approve {approved: true}
        API->>DB: UPDATE task status='planned'
    end

    User->>UI: Clicks "Run Task" (or automatic execution)
    UI->>API: POST /v1/tasks/{task_id}/run
    API->>Agent: run_task(task_id)
    loop For each step
        Agent->>Tools: execute(step.tool, arguments)
        alt Step requires protected approval (e.g. create_text_file)
            Tools->>DB: create_tool_approval(...)
            Tools-->>Agent: status="approval_required", approval_id
            Agent->>DB: UPDATE task status="waiting_approval"
            Agent-->>UI: AgentRunResponse(status="waiting_approval", pending_step_id)
            UI->>User: Shows Approval Card with exact path and arguments
            User->>UI: Clicks "Authorize Once"
            UI->>API: POST /v1/tool-approvals/{approval_id}/decide {approved: true}
            UI->>API: POST /v1/tasks/{task_id}/run
            Tools->>DB: consume_tool_approval(approval_id)
            Tools->>Tools: Run handler
        end
        Tools->>DB: record_tool_audit(...)
        Tools-->>Agent: ToolResult
        Agent->>Agent: verify(result)
        Agent->>DB: update_task_step(status="succeeded")
    end
    Agent->>DB: UPDATE task status="succeeded"
    Agent-->>UI: AgentRunResponse(status="succeeded")
    UI->>User: Task completed indicator with verified output
```

---

## Flow 4: Restart & Crash Recovery

```mermaid
sequenceDiagram
    autonumber
    participant System as System Boot / Backend Restart
    participant DB as SQLite
    participant UI as Frontend App

    System->>DB: Database.initialize() executes
    DB->>DB: UPDATE tasks SET status='paused' WHERE status='running'
    DB->>DB: UPDATE agent_step_runs SET status='ambiguous' WHERE status='running'

    UI->>System: GET /v1/tasks/resumable
    System-->>UI: Returns paused & ambiguous tasks
    UI->>User: Displays "Recovered Tasks" banner
    Note over User,UI: Ambiguous tasks require manual user review.<br/>Never automatically re-execute interrupted operations.
```
