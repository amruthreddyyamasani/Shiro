# Shiro V0.1

Shiro is an independent, local-first personal AI assistant foundation for Windows 11. V0.1 connects a small FastAPI service to a local Ollama server, persists conversations in SQLite, and streams model output back as newline-delimited JSON.

There is no Mercury dependency, cloud AI API, telemetry, cloud fallback, arbitrary command execution, or unrestricted file access in this version.

## Current scope

- Local Ollama connection at `http://127.0.0.1:11434`.
- Explicit `"think": false` on every supported `/api/chat` request.
- Streaming responses through `POST /v1/chat/stream`.
- Persistent conversations, messages and memories in `%LOCALAPPDATA%\\SHIRO\\data\\shiro.db`.
- Adaptive, configurable assistant personality using local system prompts.
- Read-only recommendations from models already installed in Ollama.
- Durable task plans with approval, pause/resume, bounded retry, cancellation, background execution, and restart recovery states.
- Registered local tools for approved file inspection, safe file creation, and mathematical calculation.
- Read-only Windows discovery plus bounded, visual-first desktop control through validated, audited input actions.
- A structured Ollama planner and bounded execution loop that verifies tool results.
- Approval-gated fixed-destination web search with bounded responses and no redirects.
- Reviewable self-improvement staging, diff, fixed local tests, apply, and rollback workflow.
- JSON configuration with environment-variable overrides.
- Localhost-only server validation.
- Model output remains data. Only registered tools can execute; there is no arbitrary command runner.
- Basic automated tests for settings, SQLite persistence, the Ollama stream adapter, and the API.

## Windows setup

If Python 3.11 or newer is not installed, install it from [python.org](https://www.python.org/downloads/windows/) and enable the option to add Python to PATH. Close and reopen PowerShell afterward.

For the React/Vite frontend, install Node.js 18 or newer with npm.

Open PowerShell and run:

```powershell
$shiro = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SHIRO'
Set-Location $shiro

py -3.11 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

If `py -3.11` is not available but `python` is, use `python -m venv .venv` instead.

The committed `config.example.json` contains only portable localhost defaults. Copy it to the ignored `config.json` and set any machine-specific approved roots locally.

SHIRO stores runtime data outside the project folder at
`%LOCALAPPDATA%\\SHIRO\\data\\shiro.db`. If the older project-local
`data\\shiro.db` exists and the app-data database does not, SHIRO copies the
older file to the new location and leaves the original untouched.

Verify Ollama before starting Shiro:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Then start the server:

```powershell
python -m shiro.main
```

Shiro listens only on `http://127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Ollama

Install the Ollama Windows application separately, start its local service, and verify that it is reachable:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
ollama list
```

Set `ollama_model` in the local `config.json`, or use `SHIRO_OLLAMA_MODEL`, to the tag of a model already installed in your local Ollama instance. SHIRO sends inference only to the localhost Ollama endpoint; it does not add a cloud provider or download a model automatically.

## Frontend

In a second PowerShell window:

```powershell
Set-Location (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SHIRO\frontend')
npm install
npm run dev
```

The Vite development server prints its local URL. For the same checks used in this repository:

```powershell
npm exec tsc -- --noEmit --pretty
npm run build
```

## First request

From a second PowerShell window:

```powershell
$shiro = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SHIRO'
Set-Location $shiro
& .\.venv\Scripts\Activate.ps1

curl.exe -N -X POST http://127.0.0.1:8000/v1/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"content":"Hello Shiro"}'
```

The response is one JSON object per line. Token events arrive as they are produced, followed by a `done` event. The generated conversation ID is included in each event and the user/assistant messages are persisted locally.

## API surface

- `GET /healthz` — local configuration health information; it does not call a cloud service.
- `POST /v1/conversations` — create a conversation.
- `GET /v1/conversations/{conversation_id}/messages` — read local history.
- `POST /v1/chat/stream` — persist a user message, call Ollama, and stream model output.
- `GET /v1/models/recommend` — list installed local models and mark the configured model.
- `GET /v1/tools` — list registered tools and their approval classes.
- `POST /v1/tools/{tool_name}/execute` — execute one validated registered tool.
- `GET/POST /v1/tool-approvals` — inspect and decide one-time tool approvals.
- `POST /v1/agent/plan` — ask local Ollama for a validated structured task plan.
- `GET/POST /v1/tasks` — create and inspect approval-gated task plans.
- `POST /v1/tasks/{task_id}/approve` — approve or deny a task plan.
- `POST /v1/tasks/{task_id}/run` — execute a persisted plan through the registered-tool loop.
- `POST /v1/tasks/{task_id}/run/background` — queue local execution after the response.
- `POST /v1/tasks/{task_id}/cancel` — request safe cancellation between tool steps.
- `GET /v1/tasks/{task_id}/runs` — inspect persisted tool results and failures.
- `GET /v1/tasks/resumable` — inspect plans safe to resume.
- `GET /v1/capabilities` — show which local, web, and self-improvement capabilities are enabled.
- `POST /v1/computer-control/tasks` — start a bounded visual-first desktop task.
- `GET /v1/computer-control/tasks/{run_id}` — inspect persisted observation/action/verification state; interrupted runs return paused/review-required.
- `POST /v1/computer-control/tasks/{run_id}/pause|resume|cancel` — control a visual task.
- `POST /v1/computer-control/emergency-stop` — latch the input actuator stop, release tracked keys/buttons, and audit the stop. The Windows host also listens for `Ctrl+Alt+Escape` globally.
- `POST /v1/web/actions` — record a general web request for review; it does not execute arbitrary requests.
- `web_search` — the only online tool, fixed to DuckDuckGo HTML search and requiring a new approval for every query.
- `POST /v1/self-improvement/requests` — stage a proposed file change for review.
- `POST /v1/self-improvement/requests/{id}/test|apply|rollback` — test, apply after approval and passing tests, or restore backups.

Example request body:

```json
{
  "conversation_id": "optional-existing-id",
  "content": "What should I remember from this conversation?"
}
```

## Configuration

Copy `config.example.json` to `config.json` for local settings. `config.json` is ignored by Git because it is machine-local. Supported environment overrides include:

- `SHIRO_HOST`
- `SHIRO_PORT`
- `SHIRO_OLLAMA_BASE_URL`
- `SHIRO_OLLAMA_MODEL`
- `SHIRO_PERSONALITY_MODE`
- `SHIRO_DATABASE_PATH`
- `SHIRO_PROJECT_ROOT`
- `SHIRO_APPROVED_ROOTS` (semicolon-separated)
- `SHIRO_MAX_FILE_SIZE_BYTES`
- `SHIRO_MAX_TOOL_CALLS_PER_TASK`
- `SHIRO_MAX_TASK_EXECUTION_SECONDS`
- `SHIRO_MAX_STEP_RETRIES`
- `SHIRO_REQUEST_TIMEOUT_SECONDS`
- `SHIRO_MAX_HISTORY_MESSAGES`
- `SHIRO_ALLOW_TOOLS`

`SHIRO_HOST` and `SHIRO_OLLAMA_BASE_URL` are restricted to localhost addresses. Tool execution is disabled unless `SHIRO_ALLOW_TOOLS=true` and at least one approved root is configured. Thinking remains disabled and the client always sends `think: false`.

`SHIRO_DATABASE_PATH` may be used when a different local database location is
needed. Environment variables such as `%LOCALAPPDATA%` are expanded.

## Tests

With the virtual environment active:

```powershell
python -m pytest -q
python -m compileall shiro tests
```

The Ollama adapter test uses an in-memory HTTP transport, so the automated suite does not need a live model. The API tests use a fake local adapter. A controlled live screenshot-to-Ollama validation was performed manually on Windows; no automated test issues native input events.

## Local files and privacy

- `config.json` is the ignored machine-local configuration file; `config.example.json` is the shareable template.
- By default, SQLite runtime data is stored at `%LOCALAPPDATA%\SHIRO\data\shiro.db`. A legacy project-local `data\shiro.db`, if present, is also ignored.
- Screenshots, logs, benchmark workspaces/results, SQLite journals, Python/Node caches, and build output are ignored because they are generated or machine-local.
- The ECHO reference artwork and derived expression assets under `frontend/src/assets/echo/` are source assets and may be committed.

## Privacy and safety boundary

The server binds to localhost, and its default Ollama URL is localhost. No request is sent to a cloud AI service. Initial file tools are restricted to configured approved roots, block sensitive locations, resolve paths before access, enforce size limits, and never delete files. File writes require a single-use approval. Shell execution, registry changes, unrestricted process control, permanent deletion, arbitrary HTTP requests, and unrestricted Windows control remain disabled. Computer control is visual-first, allowlist-bound, action-budgeted, approval-aware, audited, and guarded by an explicit emergency-stop endpoint; screenshots are held only in memory for the current task preview.

A running task is marked paused when SHIRO restarts; an in-flight operation with an unknown outcome becomes ambiguous and is not replayed automatically. General web requests are not executed; the only online tool is the separately approval-gated fixed search tool. Self-improvement changes are staged outside the project, tested in a temporary copy, applied only after explicit approval and passing tests, and backed up for rollback.

## Troubleshooting

If Shiro reports that it cannot reach Ollama, confirm that the Ollama application is running and that this succeeds:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

If the model is listed as `shiro:latest`, keep that value in `config.json`. If your Ollama installation exposes a different tag, change only `ollama_model`; do not modify or uninstall existing models.
