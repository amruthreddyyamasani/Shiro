"""Structured local planning and bounded execution for SHIRO tasks."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .database import Database
from .ollama_client import OllamaClient
from .memory import MemoryManager
from .service import PERSONALITY_PROMPTS
from .tools import ToolContext, ToolExecutor, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    verification: str = Field(default="The tool must return a successful result.", max_length=500)


class ParsedPlan(BaseModel):
    needs_action: bool = True
    title: str = Field(min_length=1, max_length=200)
    steps: list[PlanStep] = Field(min_length=1, max_length=20)


@dataclass(frozen=True)
class AgentStepSpec:
    task_id: str
    task_step_id: int
    tool_name: str
    arguments: dict[str, Any]
    verification: str
    approval_id: str | None


@dataclass(frozen=True)
class AgentRunResult:
    task_id: str
    status: str
    message: str
    completed_steps: int
    pending_step_id: int | None = None


class AgentStore:
    """Persist the tool-specific part of a plan and every execution attempt."""

    def __init__(self, database: Database):
        self.database = database

    def initialize(self) -> None:
        with self.database._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_step_specs (
                    task_step_id INTEGER PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    approval_id TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_step_id) REFERENCES task_steps(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_step_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    task_step_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('running', 'succeeded', 'failed',
                                   'waiting_approval', 'ambiguous')
                    ),
                    result_json TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_step_id) REFERENCES task_steps(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_agent_step_runs_step
                    ON agent_step_runs(task_step_id, id DESC);

                CREATE TABLE IF NOT EXISTS agent_cancellations (
                    task_id TEXT PRIMARY KEY,
                    requested_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                """
            )
            # A process can stop after a side effect but before saving its result.
            # Such a run is ambiguous and must be reviewed, never replayed blindly.
            connection.execute(
                """
                UPDATE agent_step_runs
                SET status = 'ambiguous', finished_at = ?
                WHERE status = 'running'
                """,
                (datetime.now(UTC).isoformat(),),
            )

    def create_task_from_plan(
        self,
        title: str,
        steps: list[PlanStep],
        requires_approval: bool,
        max_retries: int,
    ):
        task = self.database.create_task(
            title=title,
            steps=[step.description for step in steps],
            max_retries=max_retries,
            requires_approval=requires_approval,
        )
        task_steps = self.database.list_task_steps(task.id)
        with self.database._connect() as connection:
            connection.executemany(
                """
                INSERT INTO agent_step_specs (
                    task_step_id, task_id, tool_name, arguments_json, verification, approval_id
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                [
                    (
                        task_step.id,
                        task.id,
                        step.tool,
                        json.dumps(step.arguments, sort_keys=True),
                        step.verification,
                    )
                    for task_step, step in zip(task_steps, steps, strict=True)
                ],
            )
        return task

    def list_specs(self, task_id: str) -> list[AgentStepSpec]:
        with self.database._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, task_step_id, tool_name, arguments_json,
                       verification, approval_id
                FROM agent_step_specs WHERE task_id = ? ORDER BY task_step_id ASC
                """,
                (task_id,),
            ).fetchall()
        return [
            AgentStepSpec(
                task_id=str(row["task_id"]),
                task_step_id=int(row["task_step_id"]),
                tool_name=str(row["tool_name"]),
                arguments=json.loads(row["arguments_json"]),
                verification=str(row["verification"]),
                approval_id=row["approval_id"],
            )
            for row in rows
        ]

    def set_approval(self, task_step_id: int, approval_id: str) -> None:
        with self.database._connect() as connection:
            connection.execute(
                "UPDATE agent_step_specs SET approval_id = ? WHERE task_step_id = ?",
                (approval_id, task_step_id),
            )

    def latest_run(self, task_step_id: int):
        with self.database._connect() as connection:
            return connection.execute(
                """
                SELECT * FROM agent_step_runs
                WHERE task_step_id = ? ORDER BY id DESC LIMIT 1
                """,
                (task_step_id,),
            ).fetchone()

    def list_runs(self, task_id: str) -> list[dict[str, Any]]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_step_runs WHERE task_id = ? ORDER BY id ASC",
                (task_id,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "task_id": str(row["task_id"]),
                "task_step_id": int(row["task_step_id"]),
                "status": str(row["status"]),
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "error": row["error"],
                "started_at": datetime.fromisoformat(row["started_at"]),
                "finished_at": (
                    datetime.fromisoformat(row["finished_at"])
                    if row["finished_at"]
                    else None
                ),
            }
            for row in rows
        ]

    def list_all_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_step_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "task_id": str(row["task_id"]),
                "task_step_id": int(row["task_step_id"]),
                "status": str(row["status"]),
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "error": row["error"],
                "started_at": datetime.fromisoformat(row["started_at"]),
                "finished_at": (
                    datetime.fromisoformat(row["finished_at"])
                    if row["finished_at"]
                    else None
                ),
            }
            for row in rows
        ]

    def start_run(self, task_id: str, task_step_id: int) -> int:
        with self.database._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO agent_step_runs (
                    task_id, task_step_id, status, result_json, error,
                    started_at, finished_at
                ) VALUES (?, ?, 'running', NULL, NULL, ?, NULL)
                """,
                (task_id, task_step_id, datetime.now(UTC).isoformat()),
            )
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self.database._connect() as connection:
            connection.execute(
                """
                UPDATE agent_step_runs
                SET status = ?, result_json = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error,
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )

    def request_cancel(self, task_id: str) -> None:
        with self.database._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_cancellations (task_id, requested_at)
                VALUES (?, ?)
                ON CONFLICT(task_id) DO UPDATE SET requested_at = excluded.requested_at
                """,
                (task_id, datetime.now(UTC).isoformat()),
            )

    def is_cancel_requested(self, task_id: str) -> bool:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM agent_cancellations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return row is not None

    def clear_cancel(self, task_id: str) -> None:
        with self.database._connect() as connection:
            connection.execute(
                "DELETE FROM agent_cancellations WHERE task_id = ?",
                (task_id,),
            )


PLANNER_SYSTEM_PROMPT = """
You are SHIRO's task planner. Return only valid JSON, with no markdown:
{
  "needs_action": true,
  "title": "short task title",
  "steps": [
    {
      "description": "what this step does",
      "tool": "registered tool name",
      "arguments": {},
      "verification": "what result proves this step succeeded"
    }
  ]
}

Rules:
- Use only the registered tools listed by the system.
- Never invent tool names, arguments, permissions, or success claims.
- Keep plans short and limited to the user's request.
- Use read-only tools for inspection and calculate for arithmetic.
- File creation is allowed only when the user explicitly asks for it; it will still require approval.
- If no action is needed, set needs_action to false and use one harmless calculate step with 0.
""".strip()


class AgentOrchestrator:
    """Plan through Ollama, then execute only validated registered tools."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        ollama: OllamaClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
    ):
        self.settings = settings
        self.database = database
        self.ollama = ollama
        self.registry = registry
        self.executor = executor
        self.store = AgentStore(database)
        self.store.initialize()

    async def create_plan(
        self, request: str, conversation_id: str | None = None
    ) -> tuple[Any, ParsedPlan]:
        tools = [
            {
                "name": definition.name,
                "description": definition.description,
                "requires_approval": definition.requires_approval,
                "parameters_schema": definition.input_model.model_json_schema(),
            }
            for definition in self.registry.list()
        ]
        messages = [
            {
                "role": "system",
                "content": PERSONALITY_PROMPTS[self.settings.personality_mode],
            },
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "system",
                "content": "Registered tools:\n" + json.dumps(tools, sort_keys=True),
            },
        ]
        memory_context = MemoryManager(self.database, self.ollama).build_memory_context(request)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        if conversation_id:
            messages.extend(
                {
                    "role": item.role,
                    "content": item.content,
                }
                for item in self.database.list_messages(
                    conversation_id,
                    limit=self.settings.max_history_messages,
                )
            )
        messages.append({"role": "user", "content": request})
        parts: list[str] = []
        async for token in self.ollama.stream_chat(messages):
            parts.append(token)
            if sum(len(part) for part in parts) > 100_000:
                raise ValueError("Planner output exceeded the configured limit")
        plan = self._parse_plan("".join(parts))
        if len(plan.steps) > self.settings.max_tool_calls_per_task:
            raise ValueError("Plan exceeds the maximum tool-call limit")
        for step in plan.steps:
            definition = self.registry.get(step.tool)
            if definition is None:
                raise ValueError(f"Planner requested unknown tool: {step.tool}")
            # Bounded auto-repair for common default arguments if omitted by compact LLMs
            if step.tool == "list_files" and "directory" not in step.arguments:
                if self.settings.approved_roots:
                    step.arguments["directory"] = str(self.settings.approved_roots[0])
                else:
                    step.arguments["directory"] = "."
            elif step.tool == "calculate" and "expression" not in step.arguments:
                step.arguments["expression"] = "0"

            try:
                definition.input_model.model_validate(step.arguments)
            except ValidationError as exc:
                raise ValueError(f"Invalid arguments for {step.tool}: {exc}") from exc
        return tools, plan

    def persist_plan(self, plan: ParsedPlan):
        requires_approval = any(
            self.registry.get(step.tool).requires_approval  # type: ignore[union-attr]
            for step in plan.steps
        )
        return self.store.create_task_from_plan(
            title=plan.title,
            steps=plan.steps,
            requires_approval=requires_approval,
            max_retries=min(self.settings.max_step_retries, 5),
        )

    async def run_task(self, task_id: str) -> AgentRunResult:
        if not self.settings.allow_tools:
            return AgentRunResult(task_id, "failed", "Tool execution is disabled", 0)
        task = self.database.get_task(task_id)
        if task is None:
            return AgentRunResult(task_id, "failed", "Task not found", 0)
        if task.status == "waiting_approval":
            task_approval_status = self.database.get_task_approval_status(task_id)
            if task_approval_status == "pending":
                return AgentRunResult(task_id, task.status, "Task approval is required", 0)
            if task_approval_status == "approved":
                self.database.set_task_status(task_id, "planned")
                task = self.database.get_task(task_id)
            else:
                return AgentRunResult(task_id, task.status, "Task approval was denied", 0)
        if task.status != "planned":
            return AgentRunResult(task_id, task.status, "Task is not ready to run", 0)

        self.database.start_task(task_id)
        completed = 0
        tool_calls = 0
        task_started = time.monotonic()
        for spec in self.store.list_specs(task_id):
            if time.monotonic() - task_started > self.settings.max_task_execution_seconds:
                message = "Overall task execution timeout reached"
                self.database.set_task_status(task_id, "paused", message)
                return AgentRunResult(task_id, "paused", message, completed, spec.task_step_id)
            if self.store.is_cancel_requested(task_id):
                self.database.set_task_status(task_id, "paused", "Task cancellation requested")
                return AgentRunResult(task_id, "paused", "Task cancellation requested", completed)
            latest = self.store.latest_run(spec.task_step_id)
            if latest is not None and latest["status"] == "succeeded":
                completed += 1
                continue
            if latest is not None and latest["status"] == "ambiguous":
                self.database.set_task_status(
                    task_id,
                    "paused",
                    "An interrupted tool call may have completed; review required.",
                )
                return AgentRunResult(
                    task_id,
                    "paused",
                    "Ambiguous interrupted step requires review",
                    completed,
                    spec.task_step_id,
                )

            step = next(
                item for item in self.database.list_task_steps(task_id)
                if item.id == spec.task_step_id
            )
            max_attempts = self.settings.max_step_retries + 1
            for attempt in range(1, max_attempts + 1):
                if tool_calls >= self.settings.max_tool_calls_per_task:
                    message = "Maximum tool-call limit reached"
                    self.database.set_task_status(task_id, "failed", message)
                    return AgentRunResult(task_id, "failed", message, completed, spec.task_step_id)
                self.database.update_task_step(spec.task_step_id, "running", attempt)
                run_id = self.store.start_run(task_id, spec.task_step_id)
                tool_calls += 1
                result: ToolResult = await self.executor.execute(
                    spec.tool_name,
                    spec.arguments,
                    ToolContext(self.settings, self.database, task_id, spec.task_step_id),
                    approval_id=spec.approval_id,
                )
                if result.status == "approval_required":
                    if result.approval_id is None:
                        self.store.finish_run(run_id, "failed", error="Missing approval id")
                        return AgentRunResult(task_id, "failed", "Approval creation failed", completed)
                    self.store.set_approval(spec.task_step_id, result.approval_id)
                    self.store.finish_run(run_id, "waiting_approval")
                    self.database.set_task_status(task_id, "waiting_approval")
                    return AgentRunResult(
                        task_id,
                        "waiting_approval",
                        "Tool approval is required",
                        completed,
                        spec.task_step_id,
                    )
                if result.status != "succeeded" or not self._verified(spec, result):
                    error = result.error or "Tool result failed verification"
                    self.store.finish_run(run_id, "failed", error=error)
                    if attempt < max_attempts and result.status == "failed":
                        continue
                    self.database.update_task_step(spec.task_step_id, "failed", attempt)
                    self.database.record_task_failure(task_id, error)
                    return AgentRunResult(task_id, "failed", error, completed, spec.task_step_id)
                self.store.finish_run(run_id, "succeeded", result.output)
                self.database.update_task_step(spec.task_step_id, "succeeded", attempt)
                completed += 1
                break

        self.database.set_task_status(task_id, "succeeded")
        return AgentRunResult(task_id, "succeeded", "All planned steps completed", completed)

    @staticmethod
    def _parse_plan(raw: str) -> ParsedPlan:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        try:
            return ParsedPlan.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("Ollama returned an invalid structured plan") from exc

    @staticmethod
    def _verified(spec: AgentStepSpec, result: ToolResult) -> bool:
        if result.output is None:
            return False
        if spec.tool_name == "calculate":
            return isinstance(result.output.get("result"), (int, float))
        if spec.tool_name == "read_text_file":
            return isinstance(result.output.get("content"), str)
        if spec.tool_name == "list_files":
            return isinstance(result.output.get("files"), list)
        if spec.tool_name == "search_filenames":
            return isinstance(result.output.get("matches"), list)
        if spec.tool_name == "windows_list_windows":
            return isinstance(result.output.get("windows"), list)
        if spec.tool_name == "windows_get_active_window":
            return "active_window" in result.output
        if spec.tool_name == "windows_system_info":
            return isinstance(result.output.get("system"), str)
        return result.output.get("created") is True
