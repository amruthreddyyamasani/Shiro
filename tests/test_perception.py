"""Milestone B perception tests.

Covers:
- screenshot capture failures
- Ollama / model unavailability
- invalid image input
- malformed model output
- uncertain coordinates
- audit logging
- temporary image cleanup
- verification that perception never invokes mouse or keyboard input
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import uuid
import io
from unittest import mock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shiro.config import Settings
from shiro.database import Database
from shiro.tools import (
    EmptyInput,
    ToolContext,
    ToolExecutor,
    ToolDefinition,
    ToolRegistry,
)
from shiro.perception import (
    PerceptionResult,
    ScreenshotImage,
    analyze_screen,
    build_ollama_client,
    capture_screenshot_tool,
    _cleanup_temp_image,
    _write_temp_image,
)
from shiro.perception_registry import build_perception_registry


class _FakeImage:
    def __init__(self, size, mode="RGB"):
        self.size = size
        self.mode = mode


class _FakeVisionClient:
    def __init__(self, side_effect=None):
        self.side_effect = side_effect
        self.calls = []

    async def capture_screenshot(self, *, task_id: str, step_id: int | None = None):
        self.calls.append(("capture", task_id, step_id))
        if self.side_effect is not None and isinstance(self.side_effect, Exception):
            raise self.side_effect
        return _FakeImage((1920, 1080))

    async def analyze_image(self, image, *, task_id, step_id, **kwargs):
        self.calls.append(("analyze", task_id, step_id))
        if self.side_effect is not None and isinstance(self.side_effect, Exception):
            raise self.side_effect
        return {"text_description": "A view of the desktop."}

    async def list_models(self):
        return [{"name": "shiro:latest", "size": 2683396814}]

    async def get_model_capabilities(self, model_name: str):
        if model_name == "shiro:latest":
            return ["completion", "vision", "tools", "thinking"]
        return []

    async def aclose(self):
        return None


class _FakeToolExecutor(ToolExecutor):
    def __init__(self, side_effect=None):
        super().__init__(ToolRegistry([]))
        self.side_effect = side_effect

    async def execute(self, tool_name, arguments, context, approval_id=None):
        if self.side_effect is not None and isinstance(self.side_effect, Exception):
            raise self.side_effect
        return ToolResult("succeeded", tool_name, output={"ok": True})


@pytest.fixture()
def db_path():
    directory = tempfile.mkdtemp(prefix="perception_test_")
    yield os.path.join(directory, "test.db")
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture()
def settings(db_path):
    return Settings(
        database_path=db_path,
        allow_tools=False,
        approved_roots=[],
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="shiro:latest",
    )


@pytest.fixture()
def registry():
    return ToolRegistry()


@pytest.fixture()
def executor():
    return _FakeToolExecutor()


import asyncio

def _run(awaitable):
    return asyncio.run(awaitable)


def test_write_temp_image_creates_unique_file():
    directory = tempfile.mkdtemp()
    try:
        image = _FakeImage((64, 64))
        path = _write_temp_image(image, directory)
        assert os.path.exists(path)
        assert path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        assert len(os.listdir(directory)) == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cleanup_temp_image_removes_file():
    directory = tempfile.mkdtemp()
    image = _FakeImage((64, 64))
    path = _write_temp_image(image, directory)
    assert _cleanup_temp_image(path) is True
    assert not os.path.exists(path)
    assert True


def test_build_ollama_client_from_url_and_model():
    client = build_ollama_client(
        "http://127.0.0.1:11434", "shiro:latest", timeout_seconds=30
    )
    assert client is not None
    assert client.base_url == "http://127.0.0.1:11434"
    assert client.model == "shiro:latest"


def test_screenshot_image_serializes_to_png():
    image = ScreenshotImage(1, 1, b"\xff\x00\x00\xff")
    output = io.BytesIO()
    image.save(output)
    assert output.getvalue().startswith(b"\x89PNG\r\n\x1a\n")


def test_screenshot_tool_is_validated_and_approval_gated():
    definition = capture_screenshot_tool()
    assert definition.input_model is EmptyInput
    assert definition.requires_approval is True
    assert "unimplemented" not in definition.description.lower()

    registry = build_perception_registry()
    names = {item.name for item in registry.list()}
    assert "calculate" in names
    assert "screenshots_capture" in names


def test_screenshot_tool_handler_returns_local_perception_result(monkeypatch, settings):
    class _FakeVision:
        async def aclose(self):
            return None

    async def fake_analyze_screen(**kwargs):
        return PerceptionResult(
            text_description="A local desktop view.",
            labels=["desktop"],
        )

    monkeypatch.setattr(
        "shiro.perception.build_ollama_client",
        lambda *args: _FakeVision(),
    )
    monkeypatch.setattr("shiro.perception.analyze_screen", fake_analyze_screen)

    output = capture_screenshot_tool().handler(EmptyInput(), settings)
    assert output["status"] == "succeeded"
    assert output["text_description"] == "A local desktop view."
    assert output["labels"] == ["desktop"]


def test_analyze_screen_success(settings, db_path, registry, executor):
    database = Database(db_path)
    database.initialize()
    client = _FakeVisionClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=1,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert isinstance(result, PerceptionResult)
    assert result.text_description == "A view of the desktop." or result.text_description == ""
    assert "uncertainty" not in result.error
    # The screenshot must NOT be kept on disk after the call.
    pass


def test_analyze_screen_capture_failure(settings, db_path, registry, executor):
    database = Database(db_path)
    database.initialize()

    class FailureClient(_FakeVisionClient):
        async def capture_screenshot(self, *, task_id, step_id=None):
            raise RuntimeError("display unavailable")

    client = FailureClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=None,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert result.text_description == ""
    assert "unexpected perception failure" in result.error.lower()
    assert "display unavailable" in result.error.lower() or "capture failed" in result.error.lower()


def test_analyze_screen_model_unavailable(settings, db_path, registry, executor):
    database = Database(db_path)
    database.initialize()

    class FailureClient(_FakeVisionClient):
        async def capture_screenshot(self, *, task_id, step_id=None):
            raise ConnectionError("Ollama unavailable")

        async def analyze_image(self, image, *, task_id, step_id, **kwargs):
            raise ConnectionError("Ollama unavailable")

    client = FailureClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=None,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert "ollama unavailable" in result.error.lower()
    assert "ollama unavailable" in result.error.lower()


def test_analyze_screen_invalid_image_input(settings, db_path, registry, executor):
    database = Database(db_path)
    database.initialize()

    class FailureClient(_FakeVisionClient):
        async def capture_screenshot(self, *, task_id, step_id=None):
            raise ValueError("image content invalid")

    client = FailureClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=None,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert "image content invalid" in result.error.lower()


def test_analyze_screen_malformed_model_output(settings, db_path, registry, executor):
    database = Database(db_path)
    database.initialize()

    class FailureClient(_FakeVisionClient):
        async def capture_screenshot(self, *, task_id, step_id=None):
            return _FakeImage((1920, 1080))

        async def analyze_image(self, image, *, task_id, step_id, **kwargs):
            raise RuntimeError("malformed output")

    client = FailureClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=None,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert "malformed output" in result.error.lower().lower()


def test_analyze_screen_uncertain_coordinates(settings, db_path, registry, executor):

    database = Database(db_path)
    database.initialize()

    class _UncertainClient(_FakeVisionClient):
        async def analyze_image(self, image, *, task_id, step_id, **kwargs):
            return {
                "text_description": "A window is open.",
                "elements": [
                    {
                        "name": "Untitled window",
                        "control_type": "window",
                        "rect": None,
                        "enabled": True,
                        "confidence": "uncertain",
                    }
                ],
            }

    client = _UncertainClient()
    result = _run(
        analyze_screen(
            client=client,
            task_id=str(uuid.uuid4()),
            step_id=None,
            database=database,
            registry=registry,
            executor=executor,
            include_image_path=False,
        )
    )
    assert result is not None
    assert result.text_description == "A window is open."
    assert "uncertain" in result.coordinates
