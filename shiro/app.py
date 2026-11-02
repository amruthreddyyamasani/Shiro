"""FastAPI application for Shiro V0.1."""

from __future__ import annotations

import json
import ipaddress
import os
import platform
import shutil
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from .config import Settings, default_database_path
from .database import Database
from .agent import AgentOrchestrator
from .models import (
    AgentPlanRequest,
    AgentPlanResponse,
    AgentRunResponse,
    AgentRunRecordResponse,
    AuditItemResponse,
    ConversationCreateRequest,
    ConversationResponse,
    CapabilityResponse,
    ChangeRequestCreateRequest,
    ChangeRequestDecisionRequest,
    ChangeRequestResponse,
    HealthResponse,
    MemoryCreateRequest,
    MemoryResponse,
    MemoryUpdateRequest,
    MessageRequest,
    MessageResponse,
    ModelRecommendationResponse,
    ModelResponse,
    ModelSelectRequest,
    PersonalityUpdateRequest,
    SettingsResponse,
    SystemInfoResponse,
    TaskApprovalRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskStepResponse,
    ToolApprovalDecisionRequest,
    ToolApprovalResponse,
    ToolDefinitionResponse,
    ToolExecuteRequest,
    ToolResultResponse,
    WebActionCreateRequest,
    WebActionResponse,
)
from .ollama_client import OllamaClient, OllamaError
from .perception_registry import build_perception_registry
from .service import ConversationNotFound, ShiroService
from .tools import ToolContext, ToolExecutor
from .workflow import WorkflowStore
from .input_control import DesktopInputController, GlobalEmergencyStopService
from .visual_control import VisualExecutionManager, VisualTaskRequest


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    ollama_client: OllamaClient | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.load()
    runtime_database = database or Database(
        _prepare_database_path(runtime_settings)
    )
    runtime_database.initialize()
    workflow = WorkflowStore(runtime_database)
    workflow.initialize()
    runtime_ollama = ollama_client or OllamaClient(
        base_url=runtime_settings.ollama_base_url,
        model=runtime_settings.ollama_model,
        timeout_seconds=runtime_settings.request_timeout_seconds,
    )
    service = ShiroService(runtime_settings, runtime_database, runtime_ollama)
    input_controller = DesktopInputController()
    tool_registry = build_perception_registry(input_controller)
    tool_executor = ToolExecutor(tool_registry)
    agent = AgentOrchestrator(
        runtime_settings,
        runtime_database,
        runtime_ollama,
        tool_registry,
        tool_executor,
    )
    visual_manager = VisualExecutionManager(
        runtime_settings,
        runtime_database,
        tool_executor,
        input_controller,
        runtime_ollama,
    )
    global_emergency_stop = GlobalEmergencyStopService(visual_manager.emergency_stop)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        global_emergency_stop.start()
        try:
            yield
        finally:
            global_emergency_stop.stop()
            await runtime_ollama.aclose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        description="Local-first personal AI assistant API.",
        lifespan=lifespan,
    )

    app.state.settings = runtime_settings
    app.state.database = runtime_database
    app.state.ollama = runtime_ollama
    app.state.service = service
    app.state.workflow = workflow
    app.state.tool_registry = tool_registry
    app.state.tool_executor = tool_executor
    app.state.agent = agent
    app.state.input_controller = input_controller
    app.state.visual_manager = visual_manager
    app.state.global_emergency_stop = global_emergency_stop

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {"name": runtime_settings.app_name, "version": "0.1.0"}

    @app.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            model=runtime_settings.ollama_model,
            ollama_base_url=runtime_settings.ollama_base_url,
            thinking_disabled=True,
            tools_enabled=runtime_settings.allow_tools,
        )

    @app.get(
        "/v1/models/recommend",
        response_model=ModelRecommendationResponse,
        tags=["models"],
    )
    async def recommend_models() -> ModelRecommendationResponse:
        try:
            installed_models = await runtime_ollama.list_models()
        except OllamaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        recommendations = [
            ModelResponse(
                name=model.name,
                size=model.size,
                recommended=model.name == runtime_settings.ollama_model,
            )
            for model in installed_models
        ]
        return ModelRecommendationResponse(
            current_model=runtime_settings.ollama_model,
            models=recommendations,
        )

    @app.post(
        "/v1/models/select",
        tags=["models"],
    )
    async def select_model(request: ModelSelectRequest) -> dict[str, str]:
        try:
            installed = await runtime_ollama.list_models()
        except OllamaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if not any(m.name == request.model for m in installed):
            raise HTTPException(
                status_code=400,
                detail=f"Model '{request.model}' is not installed in local Ollama.",
            )

        runtime_settings.ollama_model = request.model
        runtime_ollama.model = request.model
        return {"current_model": request.model}

    @app.get(
        "/v1/capabilities",
        response_model=list[CapabilityResponse],
        tags=["capabilities"],
    )
    async def capabilities() -> list[CapabilityResponse]:
        return [
            CapabilityResponse(
                name="local_file_read",
                status="registered_allowlist",
                description="Read files only after configured-root and approval checks.",
                execution_enabled=runtime_settings.allow_tools and bool(runtime_settings.approved_roots),
            ),
            CapabilityResponse(
                name="local_file_write",
                status="registered_approval_required",
                description="Writes require a future explicit allowlist and approval.",
                execution_enabled=runtime_settings.allow_tools and bool(runtime_settings.approved_roots),
            ),
            CapabilityResponse(
                name="windows_app_control",
                status="registered_read_only",
                description="Read-only Windows desktop and window discovery within application allowlist.",
                execution_enabled=runtime_settings.allow_tools,
            ),
            CapabilityResponse(
                name="computer_control",
                status="registered_approval_required",
                description=(
                    "Bounded mouse and keyboard actions for an approved foreground "
                    "application; every action is validated, approval-gated, and audited."
                ),
                execution_enabled=runtime_settings.allow_tools,
            ),
            CapabilityResponse(
                name="windows_system_info",
                status="registered_read_only",
                description="Read non-sensitive OS and runtime metadata only.",
                execution_enabled=runtime_settings.allow_tools,
            ),
            CapabilityResponse(
                name="screen_perception",
                status="registered_read_only_approval_required",
                description=(
                    "Capture one desktop screenshot and describe it with the "
                    "configured local Ollama vision model after approval."
                ),
                execution_enabled=runtime_settings.allow_tools,
            ),
            CapabilityResponse(
                name="web_request",
                status="fixed_search_approval_required",
                description="Only the fixed public search tool is available, with approval per query.",
                execution_enabled=runtime_settings.allow_tools,
            ),
            CapabilityResponse(
                name="self_improvement",
                status="review_only",
                description="Code changes require a reviewable proposal and test results.",
                execution_enabled=False,
            ),
        ]

    @app.get(
        "/v1/tools",
        response_model=list[ToolDefinitionResponse],
        tags=["tools"],
    )
    async def list_tools() -> list[ToolDefinitionResponse]:
        return [
            ToolDefinitionResponse(
                name=definition.name,
                description=definition.description,
                requires_approval=definition.requires_approval,
            )
            for definition in tool_registry.list()
        ]

    @app.post(
        "/v1/tools/{tool_name}/execute",
        response_model=ToolResultResponse,
        tags=["tools"],
    )
    async def execute_tool(
        tool_name: str,
        request: ToolExecuteRequest,
    ) -> ToolResultResponse:
        if not runtime_settings.allow_tools:
            raise HTTPException(status_code=403, detail="Tool execution is disabled")
        result = await tool_executor.execute(
            tool_name=tool_name,
            arguments=request.arguments,
            approval_id=request.approval_id,
            context=ToolContext(
                settings=runtime_settings,
                database=runtime_database,
                task_id=request.task_id,
                step_id=request.step_id,
            ),
        )
        return ToolResultResponse(
            status=result.status,
            tool_name=result.tool_name,
            output=result.output,
            error=result.error,
            approval_id=result.approval_id,
            audit_id=result.audit_id,
        )

    @app.get(
        "/v1/tool-approvals/{approval_id}",
        response_model=ToolApprovalResponse,
        tags=["tools"],
    )
    async def get_tool_approval(approval_id: str) -> ToolApprovalResponse:
        approval = runtime_database.get_tool_approval(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="Tool approval not found")
        return _tool_approval_response(approval)

    @app.get(
        "/v1/tool-approvals",
        response_model=list[ToolApprovalResponse],
        tags=["tools"],
    )
    async def list_tool_approvals(
        approval_status: str | None = Query(default=None, alias="status"),
    ) -> list[ToolApprovalResponse]:
        if approval_status is not None and approval_status not in {
            "pending",
            "approved",
            "denied",
        }:
            raise HTTPException(status_code=422, detail="Invalid approval status")
        return [
            _tool_approval_response(item)
            for item in runtime_database.list_tool_approvals(approval_status)
        ]

    @app.post(
        "/v1/tool-approvals/{approval_id}/decide",
        response_model=ToolApprovalResponse,
        tags=["tools"],
    )
    async def decide_tool_approval(
        approval_id: str,
        request: ToolApprovalDecisionRequest,
    ) -> ToolApprovalResponse:
        try:
            approval = runtime_database.decide_tool_approval(
                approval_id, request.approved
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if approval is None:
            raise HTTPException(status_code=404, detail="Tool approval not found")
        return _tool_approval_response(approval)

    @app.post("/v1/computer-control/emergency-stop", tags=["computer-control"])
    async def emergency_stop() -> dict[str, object]:
        visual_manager.emergency_stop("api")
        return {"status": "stopped", "accepting_actions": False}

    @app.post("/v1/computer-control/emergency-stop/reset", tags=["computer-control"])
    async def reset_emergency_stop() -> dict[str, object]:
        input_controller.reset()
        return {"status": "reset", "accepting_actions": True}

    @app.post("/v1/computer-control/tasks", tags=["computer-control"])
    async def create_visual_task(request: VisualTaskRequest) -> dict[str, Any]:
        if not runtime_settings.allow_tools:
            raise HTTPException(status_code=403, detail="Tool execution is disabled")
        state = visual_manager.create(request)
        visual_manager.start(str(state["run_id"]))
        return visual_manager.get(str(state["run_id"]))

    @app.get("/v1/computer-control/tasks/{run_id}", tags=["computer-control"])
    async def get_visual_task(run_id: str) -> dict[str, Any]:
        try:
            return visual_manager.get(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Visual task not found") from exc

    @app.post("/v1/computer-control/tasks/{run_id}/pause", tags=["computer-control"])
    async def pause_visual_task(run_id: str) -> dict[str, Any]:
        try:
            return visual_manager.pause(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Visual task not found") from exc

    @app.post("/v1/computer-control/tasks/{run_id}/resume", tags=["computer-control"])
    async def resume_visual_task(run_id: str) -> dict[str, Any]:
        try:
            state = visual_manager.resume(run_id)
            if state["status"] == "waiting_approval" and state.get("approval_id"):
                approval = runtime_database.get_tool_approval(str(state["approval_id"]))
                if approval is not None and approval.status == "pending":
                    return visual_manager.get(run_id)
                if approval is not None and approval.status == "denied":
                    return visual_manager.cancel(run_id)
            if state["status"] in {"paused", "waiting_approval"}:
                visual_manager.start(run_id)
            return visual_manager.get(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Visual task not found") from exc

    @app.post("/v1/computer-control/tasks/{run_id}/cancel", tags=["computer-control"])
    async def cancel_visual_task(run_id: str) -> dict[str, Any]:
        try:
            return visual_manager.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Visual task not found") from exc

    @app.post(
        "/v1/agent/plan",
        response_model=AgentPlanResponse,
        tags=["agent"],
    )
    async def plan_agent_task(request: AgentPlanRequest) -> AgentPlanResponse:
        try:
            _, plan = await agent.create_plan(request.request, request.conversation_id)
            task = agent.persist_plan(plan)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OllamaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return AgentPlanResponse(
            task_id=task.id,
            title=task.title,
            status=task.status,
            steps=[
                TaskStepResponse(
                    id=step.id,
                    task_id=step.task_id,
                    position=step.position,
                    description=step.description,
                    status=step.status,
                    attempts=step.attempts,
                )
                for step in runtime_database.list_task_steps(task.id)
            ],
        )

    @app.post(
        "/v1/web/actions",
        response_model=WebActionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["web"],
    )
    async def create_web_action(
        request: WebActionCreateRequest,
    ) -> WebActionResponse:
        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="URL must be HTTP or HTTPS")
        hostname = (parsed.hostname or "").casefold()
        if hostname in {"localhost", "localhost.localdomain"}:
            raise HTTPException(status_code=422, detail="Local destinations are blocked")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        ):
            raise HTTPException(status_code=422, detail="Private destinations are blocked")
        action = workflow.create_web_action(
            method=request.method,
            url=request.url,
            reason=request.reason,
            request_body=request.request_body,
        )
        return _web_action_response(action)

    @app.get(
        "/v1/web/actions",
        response_model=list[WebActionResponse],
        tags=["web"],
    )
    async def list_web_actions() -> list[WebActionResponse]:
        return [_web_action_response(item) for item in workflow.list_web_actions()]

    @app.post(
        "/v1/web/actions/{action_id}/approve",
        response_model=WebActionResponse,
        tags=["web"],
    )
    async def decide_web_action(
        action_id: str,
        request: TaskApprovalRequest,
    ) -> WebActionResponse:
        try:
            action = workflow.decide_web_action(
                action_id,
                approved=request.approved,
                note=request.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if action is None:
            raise HTTPException(status_code=404, detail="Web action not found")
        return _web_action_response(action)

    @app.post(
        "/v1/self-improvement/requests",
        response_model=ChangeRequestResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["self-improvement"],
    )
    async def create_change_request(
        request: ChangeRequestCreateRequest,
    ) -> ChangeRequestResponse:
        change_request = workflow.create_change_request(
            title=request.title,
            description=request.description,
            files=request.files,
            test_command=request.test_command,
            project_root=runtime_settings.project_root,
            proposed_files=request.proposed_files,
        )
        return _change_request_response(change_request)

    @app.get(
        "/v1/self-improvement/requests",
        response_model=list[ChangeRequestResponse],
        tags=["self-improvement"],
    )
    async def list_change_requests() -> list[ChangeRequestResponse]:
        return [
            _change_request_response(item)
            for item in workflow.list_change_requests()
        ]

    @app.post(
        "/v1/self-improvement/requests/{request_id}/decide",
        response_model=ChangeRequestResponse,
        tags=["self-improvement"],
    )
    async def decide_change_request(
        request_id: str,
        request: ChangeRequestDecisionRequest,
    ) -> ChangeRequestResponse:
        try:
            change_request = workflow.decide_change_request(
                request_id,
                approved=request.approved,
                note=request.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found")
        return _change_request_response(change_request)

    @app.post(
        "/v1/self-improvement/requests/{request_id}/test",
        response_model=ChangeRequestResponse,
        tags=["self-improvement"],
    )
    async def test_change_request(request_id: str) -> ChangeRequestResponse:
        try:
            workflow.run_change_tests(request_id, runtime_settings.project_root)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        change_request = workflow.get_change_request(request_id)
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found")
        return _change_request_response(change_request)

    @app.post(
        "/v1/self-improvement/requests/{request_id}/apply",
        response_model=ChangeRequestResponse,
        tags=["self-improvement"],
    )
    async def apply_change_request(request_id: str) -> ChangeRequestResponse:
        try:
            workflow.apply_change_request(request_id, runtime_settings.project_root)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        change_request = workflow.get_change_request(request_id)
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found")
        return _change_request_response(change_request)

    @app.post(
        "/v1/self-improvement/requests/{request_id}/rollback",
        response_model=ChangeRequestResponse,
        tags=["self-improvement"],
    )
    async def rollback_change_request(request_id: str) -> ChangeRequestResponse:
        try:
            workflow.rollback_change_request(request_id, runtime_settings.project_root)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        change_request = workflow.get_change_request(request_id)
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found")
        return _change_request_response(change_request)

    # Durable plans. Execution remains disabled until an allowlisted tool
    # layer is added; these endpoints only persist plans and approvals.

    @app.post(
        "/v1/tasks",
        response_model=TaskResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["tasks"],
    )
    async def create_task(request: TaskCreateRequest) -> TaskResponse:
        try:
            task = runtime_database.create_task(
                title=request.title,
                steps=request.steps,
                max_retries=request.max_retries,
                requires_approval=request.requires_approval,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _task_response(runtime_database, task)

    @app.get("/v1/tasks", response_model=list[TaskResponse], tags=["tasks"])
    async def list_tasks() -> list[TaskResponse]:
        return [
            _task_response(runtime_database, task)
            for task in runtime_database.list_tasks()
        ]

    @app.get(
        "/v1/tasks/resumable",
        response_model=list[TaskResponse],
        tags=["tasks"],
    )
    async def list_resumable_tasks() -> list[TaskResponse]:
        return [
            _task_response(runtime_database, task)
            for task in runtime_database.list_resumable_tasks()
        ]

    @app.get(
        "/v1/tasks/{task_id}",
        response_model=TaskResponse,
        tags=["tasks"],
    )
    async def get_task(task_id: str) -> TaskResponse:
        task = runtime_database.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(runtime_database, task)

    @app.get(
        "/v1/tasks/{task_id}/runs",
        response_model=list[AgentRunRecordResponse],
        tags=["tasks"],
    )
    async def list_task_runs(task_id: str) -> list[AgentRunRecordResponse]:
        if runtime_database.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return [
            AgentRunRecordResponse(**run)
            for run in agent.store.list_runs(task_id)
        ]

    @app.post(
        "/v1/tasks/{task_id}/approve",
        response_model=TaskResponse,
        tags=["tasks"],
    )
    async def decide_task(
        task_id: str,
        request: TaskApprovalRequest,
    ) -> TaskResponse:
        try:
            task = runtime_database.decide_task_approval(
                task_id,
                approved=request.approved,
                note=request.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(runtime_database, task)

    @app.post(
        "/v1/tasks/{task_id}/pause",
        response_model=TaskResponse,
        tags=["tasks"],
    )
    async def pause_task(task_id: str) -> TaskResponse:
        try:
            task = runtime_database.pause_task(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(runtime_database, task)

    @app.post(
        "/v1/tasks/{task_id}/resume",
        response_model=TaskResponse,
        tags=["tasks"],
    )
    async def resume_task(task_id: str) -> TaskResponse:
        try:
            task = runtime_database.resume_task(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        agent.store.clear_cancel(task_id)
        return _task_response(runtime_database, task)

    @app.post(
        "/v1/tasks/{task_id}/run",
        response_model=AgentRunResponse,
        tags=["tasks"],
    )
    async def run_task(task_id: str) -> AgentRunResponse:
        result = await agent.run_task(task_id)
        if result.status == "failed" and result.message == "Task not found":
            raise HTTPException(status_code=404, detail=result.message)
        return AgentRunResponse(
            task_id=result.task_id,
            status=result.status,
            message=result.message,
            completed_steps=result.completed_steps,
            pending_step_id=result.pending_step_id,
        )

    @app.post(
        "/v1/tasks/{task_id}/run/background",
        response_model=AgentRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["tasks"],
    )
    async def run_task_background(
        task_id: str,
        background_tasks: BackgroundTasks,
    ) -> AgentRunResponse:
        task = runtime_database.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        background_tasks.add_task(agent.run_task, task_id)
        return AgentRunResponse(
            task_id=task_id,
            status=task.status,
            message="Task queued for local background execution",
            completed_steps=0,
        )

    @app.post(
        "/v1/tasks/{task_id}/cancel",
        response_model=TaskResponse,
        tags=["tasks"],
    )
    async def cancel_task(task_id: str) -> TaskResponse:
        task = runtime_database.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        agent.store.request_cancel(task_id)
        if task.status in {"planned", "running", "waiting_approval"}:
            if task.status == "waiting_approval":
                task = runtime_database.set_task_status(
                    task_id,
                    "paused",
                    "Task cancellation requested",
                )
            else:
                task = runtime_database.pause_task(task_id)
                if task is not None:
                    task = runtime_database.set_task_status(
                        task_id,
                        "paused",
                        "Task cancellation requested",
                    )
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(runtime_database, task)

    # Conversations

    @app.post(
        "/v1/conversations",
        response_model=ConversationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["conversations"],
    )
    async def create_conversation(
        request: ConversationCreateRequest,
    ) -> ConversationResponse:
        return ConversationResponse.model_validate(
            service.create_conversation(request.title),
        )

    @app.get(
        "/v1/conversations",
        response_model=list[ConversationResponse],
        tags=["conversations"],
    )
    async def list_conversations() -> list[ConversationResponse]:
        return [
            ConversationResponse.model_validate(c)
            for c in service.list_conversations()
        ]

    @app.get(
        "/v1/conversations/{conversation_id}/messages",
        response_model=list[MessageResponse],
        tags=["conversations"],
    )
    async def get_messages(conversation_id: str) -> list[MessageResponse]:
        try:
            messages = service.list_messages(conversation_id)
        except ConversationNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            ) from exc

        return [MessageResponse.model_validate(message) for message in messages]

    @app.delete(
        "/v1/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["conversations"],
    )
    async def delete_conversation(conversation_id: str) -> None:
        deleted = service.delete_conversation(conversation_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    # Long-term memory

    @app.get(
        "/v1/memories",
        response_model=list[MemoryResponse],
        tags=["memory"],
    )
    async def list_memories(
        category: str | None = Query(default=None),
    ) -> list[MemoryResponse]:
        try:
            memories = runtime_database.list_memories(category=category)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return [MemoryResponse.model_validate(memory) for memory in memories]

    @app.post(
        "/v1/memories",
        response_model=MemoryResponse,
        tags=["memory"],
    )
    async def create_memory(
        request: MemoryCreateRequest,
    ) -> MemoryResponse:
        try:
            memory = runtime_database.add_memory(
                category=request.category,
                content=request.content,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return MemoryResponse.model_validate(memory)

    @app.get(
        "/v1/memories/search",
        response_model=list[MemoryResponse],
        tags=["memory"],
    )
    async def search_memories(
        q: str = Query(min_length=1, max_length=200),
    ) -> list[MemoryResponse]:
        memories = runtime_database.search_memories(q)
        return [MemoryResponse.model_validate(memory) for memory in memories]

    @app.patch(
        "/v1/memories/{memory_id}",
        response_model=MemoryResponse,
        tags=["memory"],
    )
    async def update_memory(
        memory_id: int,
        request: MemoryUpdateRequest,
    ) -> MemoryResponse:
        if not request.model_fields_set:
            raise HTTPException(
                status_code=422,
                detail="Provide at least one field to update.",
            )

        try:
            memory = runtime_database.update_memory(
                memory_id=memory_id,
                category=request.category,
                content=request.content,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")

        return MemoryResponse.model_validate(memory)

    @app.delete(
        "/v1/memories/{memory_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["memory"],
    )
    async def delete_memory(memory_id: int) -> None:
        deleted = runtime_database.delete_memory(memory_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")

    # Chat

    @app.post("/v1/chat/stream", tags=["chat"])
    async def stream_chat(request: MessageRequest) -> StreamingResponse:
        try:
            prepared = service.prepare_chat(
                request.conversation_id,
                request.content,
            )
        except ConversationNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            ) from exc

        async def lines() -> AsyncIterator[str]:
            async for event in service.stream_prepared_chat(prepared):
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson",
        )

    # Settings & Personality

    @app.get(
        "/v1/settings",
        response_model=SettingsResponse,
        tags=["settings"],
    )
    async def get_settings() -> SettingsResponse:
        return SettingsResponse(
            personality_mode=runtime_settings.personality_mode,
            ollama_model=runtime_settings.ollama_model,
            ollama_base_url=runtime_settings.ollama_base_url,
            database_path=str(runtime_settings.resolved_database_path),
            project_root=str(runtime_settings.project_root),
            approved_roots=[str(r) for r in runtime_settings.approved_roots],
            max_history_messages=runtime_settings.max_history_messages,
            allow_tools=runtime_settings.allow_tools,
            thinking_enabled=False,
            request_timeout_seconds=runtime_settings.request_timeout_seconds,
        )

    @app.post(
        "/v1/settings/personality",
        tags=["settings"],
    )
    async def update_personality(request: PersonalityUpdateRequest) -> dict[str, str]:
        runtime_settings.personality_mode = request.personality_mode
        return {"personality_mode": request.personality_mode}

    # System Information

    @app.get(
        "/v1/system/info",
        response_model=SystemInfoResponse,
        tags=["system"],
    )
    async def get_system_info() -> SystemInfoResponse:
        ollama_connected = False
        installed_names: list[str] = []
        try:
            models = await runtime_ollama.list_models()
            ollama_connected = True
            installed_names = [m.name for m in models]
        except Exception:
            ollama_connected = False

        db_path = runtime_settings.resolved_database_path
        db_size = db_path.stat().st_size if db_path.exists() else 0

        return SystemInfoResponse(
            os_name=platform.system(),
            os_version=platform.version(),
            os_release=platform.release(),
            architecture=platform.machine(),
            python_version=platform.python_version(),
            database_path=str(db_path),
            database_size_bytes=db_size,
            database_wal_enabled=True,
            ollama_base_url=runtime_settings.ollama_base_url,
            ollama_model=runtime_settings.ollama_model,
            ollama_connected=ollama_connected,
            ollama_installed_models=installed_names,
            app_version="0.1.0",
            host=runtime_settings.host,
            port=runtime_settings.port,
            tools_enabled=runtime_settings.allow_tools,
            personality_mode=runtime_settings.personality_mode,
            project_root=str(runtime_settings.project_root),
            approved_roots=[str(r) for r in runtime_settings.approved_roots],
        )

    # Activity & Audit Logs

    @app.get(
        "/v1/audit",
        response_model=list[AuditItemResponse],
        tags=["audit"],
    )
    async def list_audit_events(
        category: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        search: str | None = Query(default=None),
    ) -> list[AuditItemResponse]:
        items: list[AuditItemResponse] = []

        # 1. Tool audits & Approvals (Security Audit)
        if category in (None, "security_audit"):
            tool_audits = runtime_database.list_tool_audits(limit=limit)
            for audit in tool_audits:
                args = {}
                try:
                    args = json.loads(audit.arguments_json) if audit.arguments_json else {}
                except Exception:
                    pass
                res = None
                try:
                    res = json.loads(audit.result_json) if audit.result_json else None
                except Exception:
                    pass
                items.append(
                    AuditItemResponse(
                        id=f"tool_audit_{audit.id}",
                        event_type="tool_audit",
                        category="security_audit",
                        title=f"Tool Execution: {audit.tool_name}",
                        status=audit.status,
                        details={
                            "tool_name": audit.tool_name,
                            "arguments": args,
                            "result": res,
                            "error": audit.error,
                            "started_at": audit.started_at.isoformat(),
                            "finished_at": audit.finished_at.isoformat(),
                        },
                        task_id=audit.task_id,
                        step_id=audit.step_id,
                        timestamp=audit.started_at,
                    )
                )

            tool_approvals = runtime_database.list_tool_approvals(limit=limit)
            for app_rec in tool_approvals:
                t_args = {}
                t_res = []
                try:
                    t_args = json.loads(app_rec.arguments_json) if app_rec.arguments_json else {}
                except Exception:
                    pass
                try:
                    t_res = json.loads(app_rec.affected_resources_json) if app_rec.affected_resources_json else []
                except Exception:
                    pass
                items.append(
                    AuditItemResponse(
                        id=f"tool_approval_{app_rec.id}",
                        event_type="tool_approval",
                        category="security_audit",
                        title=f"Tool Approval: {app_rec.tool_name}",
                        status=app_rec.status,
                        details={
                            "tool_name": app_rec.tool_name,
                            "arguments": t_args,
                            "affected_resources": t_res,
                            "reason": app_rec.reason,
                            "decided_at": (
                                app_rec.decided_at.isoformat()
                                if app_rec.decided_at
                                else None
                            ),
                        },
                        task_id=app_rec.task_id,
                        step_id=app_rec.step_id,
                        timestamp=app_rec.created_at,
                    )
                )

            task_approvals = runtime_database.list_task_approvals(limit=limit)
            for tapp in task_approvals:
                items.append(
                    AuditItemResponse(
                        id=f"task_approval_{tapp['id']}",
                        event_type="task_approval",
                        category="security_audit",
                        title=f"Task Approval: Task {tapp['task_id'][:8]}",
                        status=tapp["status"],
                        details={
                            "note": tapp["note"],
                            "decided_at": (
                                tapp["decided_at"].isoformat()
                                if tapp["decided_at"]
                                else None
                            ),
                        },
                        task_id=tapp["task_id"],
                        timestamp=tapp["created_at"],
                    )
                )

        # 2. Task Step Runs (Task Execution Events)
        if category in (None, "task_event"):
            runs = agent.store.list_all_runs(limit=limit)
            for run in runs:
                items.append(
                    AuditItemResponse(
                        id=f"task_run_{run['id']}",
                        event_type="task_run",
                        category="task_event",
                        title=f"Step Run: Task {run['task_id'][:8]} Step #{run['task_step_id']}",
                        status=run["status"],
                        details={
                            "result": run["result"],
                            "error": run["error"],
                            "started_at": run["started_at"].isoformat(),
                            "finished_at": (
                                run["finished_at"].isoformat()
                                if run["finished_at"]
                                else None
                            ),
                        },
                        task_id=run["task_id"],
                        step_id=run["task_step_id"],
                        timestamp=run["started_at"],
                    )
                )

        items.sort(key=lambda x: x.timestamp, reverse=True)

        if search:
            q = search.lower().strip()
            items = [
                it
                for it in items
                if q in it.title.lower()
                or q in it.status.lower()
                or (it.task_id and q in it.task_id.lower())
                or q in json.dumps(it.details, default=str).lower()
            ]

        return items[:limit]

    return app


def _prepare_database_path(settings: Settings) -> Path:
    """Prepare app-data storage and preserve the original project database."""

    target = settings.resolved_database_path
    default_path = default_database_path().resolve()
    legacy_path = (Path.cwd() / "data" / "shiro.db").resolve()

    if (
        target.resolve() == default_path
        and target.resolve() != legacy_path
        and not target.exists()
        and legacy_path.is_file()
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, target)

    return target


def _task_response(database: Database, task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        status=task.status,
        requires_approval=task.requires_approval,
        max_retries=task.max_retries,
        retry_count=task.retry_count,
        last_error=task.last_error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        steps=[
            TaskStepResponse(
                id=step.id,
                task_id=step.task_id,
                position=step.position,
                description=step.description,
                status=step.status,
                attempts=step.attempts,
            )
            for step in database.list_task_steps(task.id)
        ],
    )


def _web_action_response(action) -> WebActionResponse:
    return WebActionResponse(
        id=action.id,
        method=action.method,
        url=action.url,
        reason=action.reason,
        request_body=action.request_body,
        status=action.status,
        note=action.note,
        created_at=action.created_at,
        decided_at=action.decided_at,
    )


def _change_request_response(change_request) -> ChangeRequestResponse:
    return ChangeRequestResponse(
        id=change_request.id,
        title=change_request.title,
        description=change_request.description,
        files=change_request.files,
        test_command=change_request.test_command,
        status=change_request.status,
        note=change_request.note,
        created_at=change_request.created_at,
        decided_at=change_request.decided_at,
        diff=change_request.diff,
        test_status=change_request.test_status,
        test_output=change_request.test_output,
        applied_at=change_request.applied_at,
    )


def _tool_approval_response(approval) -> ToolApprovalResponse:
    return ToolApprovalResponse(
        id=approval.id,
        task_id=approval.task_id,
        step_id=approval.step_id,
        tool_name=approval.tool_name,
        arguments=json.loads(approval.arguments_json),
        affected_resources=json.loads(approval.affected_resources_json),
        reason=approval.reason,
        status=approval.status,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        consumed_at=approval.consumed_at,
    )


app = create_app()
