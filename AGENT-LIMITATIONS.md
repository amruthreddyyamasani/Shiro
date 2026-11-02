# SHIRO Agent Architecture & Operational Limitations

This document analyzes the architectural and runtime limitations identified during the empirical autonomous agent benchmark.

---

## 1. Classification of Identified Limitations

```
                                 ┌─────────────────────────┐
                                 │ Identified Limitations  │
                                 └────────────┬────────────┘
              ┌──────────────────────┬────────┴──────────────┬─────────────────────┐
              ▼                      ▼                       ▼                     ▼
      [Model Reasoning]     [Planner System]         [Tool Boundaries]     [Execution State]
      - Compact context      - Argument schema gap   - AST only math       - Task vs Tool token
      - Hallucinated args    - One-shot JSON fail    - No terminal shell   - In-memory lock
```

### A. Model Reasoning Limitations (Local 2B–4B Inference)
1. **Omission of Required Arguments:**
   When generating tool execution plans, small local models (`shiro:latest` / `qwen3.5:2b`) frequently omit required parameters (e.g., emitting `list_files: {}` without the mandatory `directory` argument, or `calculate: {}` without `expression`).
2. **Context Window Exhaustion on Large Files:**
   In-memory context retrieval during chat streaming can become sluggish when ingesting multiple source files simultaneously, taking 30–70s per turn on local hardware.
3. **Inconsistent Structural Compliance:**
   Zero-shot output occasionally injects conversational prose or preamble before or after JSON blocks, requiring regex stripping (`_parse_plan`).

### B. Planning Limitations
1. **Lack of Dynamic Re-planning:**
   The current planner generates a static multi-step array ahead of time. It cannot conditionally branch or alter Step 3 based on the outcome of Step 1 without starting a completely new planning cycle.
2. **Schema Invisibility in System Prompt:**
   The system prompt provides tool names and descriptions, but lacks full Pydantic JSON schemas for arguments. As a result, the LLM must guess whether a file path argument is named `path`, `filename`, or `file`.

### C. Tool Limitations
1. **AST Math Boundary:**
   The `calculate` tool is deliberately constrained to basic arithmetic (`+`, `-`, `*`, `/`, `**`). It cannot parse tabular data, compute percentiles, or execute arbitrary Python routines.
2. **No Interactive Execution:**
   Tools are atomic and request-response oriented. There is no streaming pipe or interactive command execution (e.g., long-running builds or interactive debuggers).

### D. Context and Memory Limitations
1. **Chat vs. Task Separation:**
   Tool run outputs generated during task runs are stored in the SQLite `agent_step_runs` table, but are not automatically appended to the active conversation history unless manually forwarded.
2. **Short-Term Memory Compression:**
   While long-term memory extraction operates asynchronously, short-term history is truncated at `max_history_messages` (default 24 messages).

### E. Backend Execution & Safety Boundaries
1. **Dual-Tier Approval Semantics:**
   SHIRO implements both *Task-level approvals* (`/v1/tasks/{id}/approve`) and *Tool-level approvals* (`/v1/tool-approvals/{id}/decide`). While this provides granular defense-in-depth, executing a task with `requires_approval=True` will require two separate approval gates if it also calls protected tools like `create_text_file`.
2. **Air-Gapped Localhost Binding:**
   All executions are restricted strictly to approved workspace roots. Absolute paths outside approved roots (such as `C:\Windows\System32\drivers\etc\hosts`) are rejected immediately by canonical path validation.

---

## 2. Priority Recommendations (Future Sprints)

| Priority | Category | Recommendation | Impact |
| :---: | :--- | :--- | :--- |
| **P1** | Planning | Include Pydantic argument schemas directly in `PLANNER_SYSTEM_PROMPT`. | Eliminates `Invalid arguments` planning validation errors. |
| **P2** | Agent Engine | Implement step-level iterative planning (plan next step from previous step output). | Enables true multi-step reactive workflows. |
| **P3** | Memory | Automatically post synthesized task summaries into active conversation thread. | Unifies chat context with background task results. |
| **P4** | Safety UI | Surface unified approval prompts when both plan and tool require confirmation. | Streamlines UX while retaining full security boundary. |
