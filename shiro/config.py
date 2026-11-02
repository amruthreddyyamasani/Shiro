"""Local configuration for Shiro.

Configuration is intentionally small and local. Values may be supplied in a
JSON file (normally ``config.json``) and overridden with ``SHIRO_*``
environment variables.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


def default_database_path() -> Path:
    """Return SHIRO's Windows app-data database location."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    base_path = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base_path / "SHIRO" / "data" / "shiro.db"


class Settings(BaseModel):
    """Validated runtime settings for the local Shiro server."""

    model_config = ConfigDict(extra="ignore")

    app_name: str = "Shiro"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "shiro:latest"
    personality_mode: Literal["adaptive", "friendly", "professional"] = "adaptive"
    database_path: Path = Field(default_factory=default_database_path)
    project_root: Path = Field(default_factory=Path.cwd)
    approved_roots: list[Path] = Field(default_factory=list)
    max_file_size_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)
    max_tool_calls_per_task: int = Field(default=20, ge=1, le=100)
    max_task_execution_seconds: float = Field(default=300.0, gt=0, le=3600)
    max_step_retries: int = Field(default=2, ge=0, le=5)
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=3600)
    max_history_messages: int = Field(default=24, ge=1, le=200)
    thinking_enabled: bool = False
    allow_tools: bool = False

    @field_validator("host")
    @classmethod
    def validate_localhost(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Shiro must bind to localhost only")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def validate_local_ollama_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Ollama must use a localhost URL")
        return value.rstrip("/")

    @field_validator("thinking_enabled")
    @classmethod
    def validate_thinking_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("thinking_enabled must remain false in V0.1")
        return value

    @field_validator("allow_tools")
    @classmethod
    def validate_tools_flag(cls, value: bool) -> bool:
        return value

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        """Load JSON configuration, then apply supported environment overrides."""

        selected_path = Path(
            config_path
            or os.environ.get("SHIRO_CONFIG_PATH", "config.json")
        )
        values: dict[str, Any] = {}
        if selected_path.is_file():
            with selected_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("Shiro config must be a JSON object")
            values.update(loaded)

        env_fields: dict[str, tuple[str, type[Any]]] = {
            "SHIRO_APP_NAME": ("app_name", str),
            "SHIRO_HOST": ("host", str),
            "SHIRO_PORT": ("port", int),
            "SHIRO_OLLAMA_BASE_URL": ("ollama_base_url", str),
            "SHIRO_OLLAMA_MODEL": ("ollama_model", str),
            "SHIRO_PERSONALITY_MODE": ("personality_mode", str),
            "SHIRO_DATABASE_PATH": ("database_path", str),
            "SHIRO_PROJECT_ROOT": ("project_root", str),
            "SHIRO_APPROVED_ROOTS": (
                "approved_roots",
                lambda value: [item for item in value.split(";") if item.strip()],
            ),
            "SHIRO_MAX_FILE_SIZE_BYTES": ("max_file_size_bytes", int),
            "SHIRO_MAX_TOOL_CALLS_PER_TASK": ("max_tool_calls_per_task", int),
            "SHIRO_MAX_TASK_EXECUTION_SECONDS": ("max_task_execution_seconds", float),
            "SHIRO_MAX_STEP_RETRIES": ("max_step_retries", int),
            "SHIRO_REQUEST_TIMEOUT_SECONDS": ("request_timeout_seconds", float),
            "SHIRO_MAX_HISTORY_MESSAGES": ("max_history_messages", int),
            "SHIRO_THINKING_ENABLED": ("thinking_enabled", lambda value: value.lower() == "true"),
            "SHIRO_ALLOW_TOOLS": ("allow_tools", lambda value: value.lower() == "true"),
        }
        for env_name, (field_name, converter) in env_fields.items():
            if env_name in os.environ:
                values[field_name] = converter(os.environ[env_name])
        return cls.model_validate(values)

    @property
    def resolved_database_path(self) -> Path:
        """Return an absolute SQLite path, expanding Windows environment variables."""

        configured_path = Path(os.path.expandvars(str(self.database_path)))
        if configured_path.is_absolute():
            return configured_path
        return Path.cwd() / configured_path
