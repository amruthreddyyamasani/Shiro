
"""Pydantic models used by the SHIRO HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MemoryCategory = Literal["preferences", "projects", "skills", "general"]


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=16_000)
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class MemoryCreateRequest(BaseModel):
    category: MemoryCategory
    content: str = Field(min_length=1, max_length=2000)


class MemoryUpdateRequest(BaseModel):
    category: MemoryCategory | None = None
    content: str | None = Field(default=None, min_length=1, max_length=2000)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: MemoryCategory
    content: str
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_base_url: str
    thinking_disabled: bool
    tools_enabled: bool


class ModelResponse(BaseModel):
    name: str
    size: int | None = None
    installed: bool = True
    recommended: bool = False


class ModelRecommendationResponse(BaseModel):
    current_model: str
    models: list[ModelResponse]


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    steps: list[str] = Field(min_length=1, max_length=50)
    max_retries: int = Field(default=2, ge=0, le=5)
    requires_approval: bool = True


class TaskStepResponse(BaseModel):
    id: int
    task_id: str
    position: int
    description: str
    status: str
    attempts: int


class TaskResponse(BaseModel):
    id: str
    title: str
    status: str
    requires_approval: bool
    max_retries: int
    retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[TaskStepResponse] = Field(default_factory=list)


class TaskApprovalRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=1000)


class AgentPlanRequest(BaseModel):
    request: str = Field(min_length=1, max_length=16_000)
    conversation_id: str | None = None


class AgentPlanResponse(BaseModel):
    task_id: str
    title: str
    status: str
    steps: list[TaskStepResponse]


class AgentRunResponse(BaseModel):
    task_id: str
    status: str
    message: str
    completed_steps: int
    pending_step_id: int | None = None


class AgentRunRecordResponse(BaseModel):
    id: int
    task_id: str
    task_step_id: int
    status: str
    result: dict[str, object] | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class CapabilityResponse(BaseModel):
    name: str
    status: str
    description: str
    execution_enabled: bool


class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    requires_approval: bool


class ToolExecuteRequest(BaseModel):
    arguments: dict[str, object] = Field(default_factory=dict)
    task_id: str | None = None
    step_id: int | None = None
    approval_id: str | None = None


class ToolResultResponse(BaseModel):
    status: str
    tool_name: str
    output: dict[str, object] | None = None
    error: str | None = None
    approval_id: str | None = None
    audit_id: int | None = None


class ToolApprovalDecisionRequest(BaseModel):
    approved: bool


class ToolApprovalResponse(BaseModel):
    id: str
    task_id: str | None
    step_id: int | None
    tool_name: str
    arguments: dict[str, object]
    affected_resources: list[str]
    reason: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    decided_at: datetime | None
    consumed_at: datetime | None


class WebActionCreateRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE"]
    url: str = Field(min_length=1, max_length=2048)
    reason: str = Field(min_length=1, max_length=1000)
    request_body: str | None = Field(default=None, max_length=20_000)


class WebActionResponse(BaseModel):
    id: str
    method: str
    url: str
    reason: str
    request_body: str | None
    status: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None


class ChangeRequestCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    files: list[str] = Field(min_length=1, max_length=100)
    test_command: str = Field(min_length=1, max_length=1000)
    proposed_files: dict[str, str] = Field(default_factory=dict)


class ChangeRequestDecisionRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=1000)


class ChangeRequestResponse(BaseModel):
    id: str
    title: str
    description: str
    files: list[str]
    test_command: str
    status: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None
    diff: str = ""
    test_status: str = "not_run"
    test_output: str | None = None
    applied_at: datetime | None = None


class ErrorResponse(BaseModel):
    error: str
    message: str


class AuditItemResponse(BaseModel):
    id: str
    event_type: str
    category: str
    title: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    step_id: int | None = None
    timestamp: datetime


class SystemInfoResponse(BaseModel):
    os_name: str
    os_version: str
    os_release: str
    architecture: str
    python_version: str
    database_path: str
    database_size_bytes: int
    database_wal_enabled: bool
    ollama_base_url: str
    ollama_model: str
    ollama_connected: bool
    ollama_installed_models: list[str]
    app_version: str
    host: str
    port: int
    tools_enabled: bool
    personality_mode: str
    project_root: str
    approved_roots: list[str]


class PersonalityUpdateRequest(BaseModel):
    personality_mode: Literal["adaptive", "friendly", "professional"]


class ModelSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class SettingsResponse(BaseModel):
    personality_mode: str
    ollama_model: str
    ollama_base_url: str
    database_path: str
    project_root: str
    approved_roots: list[str]
    max_history_messages: int
    allow_tools: bool
    thinking_enabled: bool
    request_timeout_seconds: float
