# SHIRO — Component Selection & Architecture Decision

## 1. Component & Library Evaluation Matrix

| Library / Source | Selected? | Technical Rationale | SHIRO Application |
|---|---|---|---|
| **React 19 + TypeScript** | **Yes** | Core modern industry standard for reactive, typed web application development. | Application core foundation. |
| **Vite 6** | **Yes** | Lightning-fast dev server and optimized production bundler with native ESM and zero bloat. | Build system & local development runner. |
| **Tailwind CSS 3.4** | **Yes** | Utility-first CSS framework enabling pixel-perfect tokenization and minimal CSS bundle output. | Full design token & utility styling layer. |
| **Lucide React** | **Yes** | Consistent, high-quality, lightweight SVG icon system matching shadcn conventions. | Universal icon family across sidebar, badges, cards, buttons. |
| **Custom Stream Client** | **Yes** | Direct NDJSON line-reader with abort controller matching `/v1/chat/stream`. | Native typed chat stream consumer (no bloated third-party AI SDK required). |
| **shadcn/ui (Native patterns)** | **Yes** | Accessible primitives (dialogs, tooltips, tabs, buttons, inputs) without vendor lock-in. | Foundational interactive components. |
| **React Bits (Selected free patterns)** | **Yes** | Selected micro-interactions: Thought Line, Call Chip, Status Mark, Stepper. | Agent trace visualizations and task progress indicators. |
| **assistant-ui** | *Rejected* | Designed primarily around Vercel AI SDK and OpenAI-compatible SSE; introduces unnecessary adapter complexity for SHIRO's native NDJSON FastAPI backend. | None. Native typed React chat state is cleaner and more reliable. |
| **Agent Elements** | *Rejected* | Hardcoded to `@ai-sdk/react` and `UIMessage` structures that don't match SHIRO's SQLite database models. | None. Adapted agentic patterns implemented directly. |
| **Three.js / Vanta / Lenis** | *Rejected* | Heavy GPU resource consumption that directly competes with local Ollama inference on 6 GB VRAM GPUs. | None. Zero decorative 3D or smooth-scroll overhead. |

---

## 2. Directory Architecture

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── app/
    │   ├── App.tsx             # Main application shell & router
    │   └── main.tsx            # React entry point
    ├── api/
    │   ├── client.ts           # Central typed API client & error handler
    │   ├── types.ts            # TypeScript interfaces matching backend models
    │   └── stream.ts           # NDJSON stream reader & parser
    ├── components/
    │   ├── ui/                 # Foundational primitives (Button, Input, Badge, Dialog, StatusMark, Card)
    │   ├── layout/             # Sidebar, Header, ContextPanel, AppShell
    │   ├── chat/               # ChatView, MessageList, MessageItem, Composer, ModelBadge
    │   ├── agent/              # TaskManagerView, ApprovalCenterView, TaskPlanCard, StepTrace
    │   ├── audit/              # ActivityLogView (Unified tool audit & task events timeline)
    │   ├── improvement/        # SelfImprovementView (Code review, diff viewer, test harness, backup & rollback)
    │   ├── system/             # SystemInfoView (Verified Windows, Ollama, and SQLite introspection)
    │   ├── dashboard/          # DashboardView (Metric cards, system status, capabilities, quick actions)
    │   ├── memory/             # MemoryCenterView (Category pills, search, modal creator, edit drawer)
    │   ├── tools/              # ToolsView (Registered tool catalog & execution boundaries)
    │   ├── settings/           # SettingsView (Configurable personality & model selection, immutable safety)
    │   └── common/             # ErrorBanner, EmptyState, CopyButton
    ├── hooks/
    │   ├── useChat.ts          # Conversation state & streaming management
    │   ├── useHealth.ts        # Backend & Ollama health polling
    │   └── useTasks.ts         # Task manager & approval polling
    └── styles/
        └── globals.css         # CSS variables & Tailwind directives
```

---

## 3. Chat Architecture Choice

### Native Typed React Chat Engine
Rather than importing heavy external chat packages that require proxying through a Vercel AI route, SHIRO uses a lightweight, robust custom hook (`useChat`):
- Connects directly to `/v1/chat/stream` using browser `fetch()` and `ReadableStreamDefaultReader`.
- Buffers NDJSON lines across TCP chunk boundaries.
- Emits real-time state updates for `token`, `done`, and `error` events.
- Supports instant local abort via `AbortController`.
- Persists message history directly in backend SQLite via conversation IDs.
