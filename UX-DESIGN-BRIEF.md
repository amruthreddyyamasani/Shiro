# SHIRO — UX Design Brief

## 1. Product Identity & Philosophy

**SHIRO** is not a generic cloud-based chatbot wrapper. It is a **local-first personal AI operating environment** designed for power users on Windows.

### Core Principles
1. **Local Authority**: All inference is executed locally through Ollama. The interface clearly communicates that no data ever leaves the local machine.
2. **Transparent Agency**: Autonomous operations must never feel like a "black box". Every tool call, file creation, calculation, and web search is presented with explicit rationale, target resources, and outcome verification.
3. **Sovereign Human In The Loop**: Dangerous side-effects (file writes, directory creations, external web requests) require explicit, one-time, expiring approvals. There is strictly no "Authorize all forever" escape hatch.
4. **Calm, High-Information Density**: The visual language is subdued, technical, and precise. No glowing orbs, no floating particles, no meaningless marketing gradients.

---

## 2. Target Personas & Use Cases

### Persona: The Local AI Engineer & Power User
- **Hardware**: Intel Core i7, 16 GB RAM, RTX 4050 (6 GB VRAM).
- **Needs**: Fast, local text generation; automatic contextual memory for ongoing projects; safe tool execution in whitelisted directories; inspection of model state without cloud latency.
- **Pain Points**: Cloud assistants that hallucinate file changes, silent permission creep, bloated web apps that hog CPU/GPU resources while local LLMs are running.

---

## 3. Personality States & Modalities

SHIRO operates across three distinct personality modes:
1. **Adaptive** (Default): Calibrates explanation depth based on question complexity. Terse for factual commands, structured for technical analysis.
2. **Friendly**: Warm, conversational tone suitable for brainstorming, casual discussion, and companionship.
3. **Professional**: Rigorous, highly structured, stating explicit assumptions, verification criteria, and execution boundaries.

---

## 4. Operational States & Interface Reflections

The application header and status pill dynamically reflect the real backend engine state:

| State | Visual Indicator | Meaning |
|-------|------------------|---------|
| **Idle** | Deep Navy / Emerald Dot | Ollama ready, model loaded, database connected. |
| **Streaming** | Restrained Cyan Pulse | Local LLM actively generating tokens via NDJSON stream. |
| **Planning** | Violet Pulse | Agent orchestrator synthesizing task steps via Ollama. |
| **Executing** | Electric Blue Spinner | Approved tool handler executing on local host. |
| **Waiting Approval**| Amber Ring / Alert Badge | Protected operation requires one-time user authorization. |
| **Paused** | Slate Neutral Dot | Task interrupted or awaiting resume command. |
| **Error / Ambiguous**| Rust / Crimson Glow | Model error, tool failure, or crash recovery review required. |
| **Offline** | Muted Grey Dot | Ollama daemon unreachable on `127.0.0.1:11434`. |

---

## 5. Information Architecture & Navigation

```
┌────────────────────────────────────────────────────────────────────────┐
│ App Shell                                                              │
│ ┌───────────────┬──────────────────────────────────┬─────────────────┐ │
│ │ Left Sidebar  │ Center Workspace                 │ Context Panel   │ │
│ │ • Brand       │ • Top Context Bar (Model, Status)│ (Collapsible)   │ │
│ │ • New Chat    │ • Main View:                     │ • Active Task   │ │
│ │ • Navigation  │   - Dashboard                    │ • Approvals     │ │
│ │   - Dashboard │   - Chat (Message Thread)        │ • System Stats  │ │
│ │   - Chat      │   - Task Manager                 │ • Live Trace    │ │
│ │   - Tasks     │   - Approvals                    │                 │ │
│ │   - Memory    │   - Memory Center                │                 │ │
│ │   - Tools     │   - Tool Registry                │                 │ │
│ │   - Settings  │ • Bottom Composer (Chat only)    │                 │ │
│ └───────────────┴──────────────────────────────────┴─────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Key Screen Flows

### Flow 1: Direct Conversational Query
1. User enters prompt in Chat Composer.
2. Immediate local echo; stream opens to `/v1/chat/stream`.
3. Model tokens stream smoothly into active message card.
4. Copy button, timestamp, and model tag appear upon stream termination (`done` event).
5. Background memory extraction updates relevant memories silently.

### Flow 2: Autonomous Task Execution & Approval
1. User requests a complex goal (e.g. "Create a project summary in workspace").
2. Agent engine synthesizes structured plan (`POST /v1/agent/plan`).
3. Plan card renders with numbered steps. Step 1 (`list_files`) executes automatically (read-only).
4. Step 2 (`create_text_file`) pauses and requests approval.
5. High-visibility Confirmation Card displays:
   - Tool name: `create_text_file`
   - File path: `<project-root>\summary.md`
   - Content preview & byte size
   - Expiration countdown
6. User clicks **"Authorize Once"**.
7. Tool executes, records audit row, verifies file creation, and completes task.

---

## 7. Anti-AI-Slop Review Guidelines

Every component and view in SHIRO must pass this quality bar:
- **No decorative skeletons**: If data is loading, use a precise single-line activity indicator.
- **No fake cards or mock metrics**: If backend has no data, show a clean, honest empty state.
- **No permanent floating orbs or background mesh animations**: Save GPU VRAM for the local LLM.
- **No truncated paths**: Technical paths must be fully inspectable with copy-to-clipboard actions.
