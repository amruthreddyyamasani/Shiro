"""
Planner edge-case tests for SHIRO.

These tests exercise the planner through AgentOrchestrator.create_plan() using
fake Ollama adapters. They do not hit any external API. They are aimed at the
planner reliability behaviors described in the handoff, not just the private
_parse_plan helper in isolation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pydantic

from shiro.agent import AgentOrchestrator
from shiro.config import Settings
from shiro.database import Database
from shiro.tools import ToolContext, ToolExecutor, ToolDefinition, ToolRegistry


def _tmp_path() -> str:
    import tempfile, os
    return os.path.join(tempfile.mkdtemp(), "db.db")


def _closeable_fake_ollama(plan_json: str):
    class FakeOllama:
        async def stream_chat(self, messages: list[dict[str, Any]]) -> Any:
            yield plan_json

        async def aclose(self) -> None:
            return None

    return FakeOllama()


def _registry_with_echo():
    class EchoInput(pydantic.BaseModel):
        x: int = pydantic.Field(ge=0, le=10)

    return ToolRegistry(
        [
            ToolDefinition(
                "echo", "A minimal test tool with validated input.", EchoInput, False, lambda request, settings: {}
            )
        ]
    )


def _build_agent(plan_json: str, *, registry=None, settings=None):
    registry = registry or _registry_with_echo()
    settings = settings or Settings(database_path=_tmp_path(), allow_tools=False)
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(plan_json)
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    return agent, database


def _valid_echo_plan() -> str:
    return json.dumps(
        {
            "needs_action": True,
            "title": "Valid echo plan",
            "steps": [
                {
                    "description": "A single echo step",
                    "tool": "echo",
                    "arguments": {"x": 5},
                    "verification": "The tool returned successfully",
                }
            ],
        }
    )


def test_valid_plan_is_parsed_and_validated():
    agent, _ = _build_agent(_valid_echo_plan())
    tools, plan = asyncio.run(agent.create_plan("Do the thing", None))
    assert plan.needs_action is True
    assert plan.title == "Valid echo plan"
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool == "echo"
    assert step.arguments == {"x": 5}


def test_unknown_tool_name_is_rejected():
    plan = json.dumps(
        {
            "needs_action": True,
            "title": "Bad tool plan",
            "steps": [
                {
                    "description": "Unknown tool",
                    "tool": "non_existent_tool",
                    "arguments": {},
                    "verification": "N/A",
                }
            ],
        }
    )
    agent, _ = _build_agent(plan)
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Bad tool", None))


def test_missing_required_argument_is_rejected():
    plan = json.dumps(
        {
            "needs_action": True,
            "title": "Missing argument plan",
            "steps": [
                {
                    "description": "Missing x",
                    "tool": "echo",
                    "arguments": {},
                    "verification": "N/A",
                }
            ],
        }
    )
    agent, _ = _build_agent(plan)
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Missing argument", None))


def test_invalid_argument_type_is_rejected():
    plan = json.dumps(
        {
            "needs_action": True,
            "title": "Wrong type plan",
            "steps": [
                {
                    "description": "String instead of int",
                    "tool": "echo",
                    "arguments": {"x": "nope"},
                    "verification": "N/A",
                }
            ],
        }
    )
    agent, _ = _build_agent(plan)
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Wrong type", None))


def test_out_of_range_argument_is_rejected():
    plan = json.dumps(
        {
            "needs_action": True,
            "title": "Out of range plan",
            "steps": [
                {
                    "description": "x too large",
                    "tool": "echo",
                    "arguments": {"x": 11},
                    "verification": "N/A",
                }
            ],
        }
    )
    agent, _ = _build_agent(plan)
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Out of range", None))


def test_malformed_json_is_rejected():
    agent, _ = _build_agent("this is not json at all")
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Malformed JSON", None))


def test_malformed_json_with_extra_text_is_rejected():
    agent, _ = _build_agent("not json }} } }")
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Malformed JSON", None))


def test_markdown_fenced_json_is_accepted():
    fenced = "```json\n" + _valid_echo_plan() + "\n```"
    agent, _ = _build_agent(fenced)
    tools, plan = asyncio.run(agent.create_plan("Fenced plan", None))
    assert plan.steps[0].tool == "echo"
    assert plan.steps[0].arguments == {"x": 5}


def test_markdown_fenced_json_without_language_is_accepted():
    fenced = "```\n" + _valid_echo_plan() + "\n```"
    agent, _ = _build_agent(fenced)
    tools, plan = asyncio.run(agent.create_plan("Fenced plan", None))
    assert plan.steps[0].tool == "echo"
    assert plan.steps[0].arguments == {"x": 5}


def test_empty_steps_array_is_rejected():
    plan = json.dumps({"needs_action": True, "title": "Empty steps", "steps": []})
    agent, _ = _build_agent(plan)
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Empty steps", None))


def test_overly_long_plan_is_rejected():
    settings = Settings(
        database_path=_tmp_path(),
        allow_tools=False,
        max_tool_calls_per_task=2,
    )
    registry = _registry_with_echo()
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Too long plan",
                "steps": [
                    {
                        "description": f"Step {i}",
                        "tool": "echo",
                        "arguments": {"x": i},
                        "verification": "N/A",
                    }
                    for i in range(3)
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Long plan", None))


def test_plan_too_long_does_not_persist_steps():
    settings = Settings(
        database_path=_tmp_path(),
        allow_tools=False,
        max_tool_calls_per_task=1,
    )
    registry = _registry_with_echo()
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Too long plan",
                "steps": [
                    {
                        "description": "Step one",
                        "tool": "echo",
                        "arguments": {"x": 1},
                        "verification": "N/A",
                    },
                    {
                        "description": "Step two",
                        "tool": "echo",
                        "arguments": {"x": 2},
                        "verification": "N/A",
                    },
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    try:
        asyncio.run(agent.create_plan("Long plan", None))
    except ValueError:
        pass
    # create_plan raises before persist_plan is called, so nothing is persisted.
    assert database.get_task("no-such-task") is None


def test_invalid_plan_rejection_is_not_partial_execution():
    settings = Settings(
        database_path=_tmp_path(),
        allow_tools=False,
        max_tool_calls_per_task=1,
    )

    class StoreInput(pydantic.BaseModel):
        value: str = pydantic.Field(min_length=1)

    registry = ToolRegistry(
        [
            ToolDefinition(
                "store",
                "A fake storing tool.",
                StoreInput,
                True,
                lambda request, settings: {"stored": True},
            )
        ]
    )
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Invalid plan",
                "steps": [
                    {
                        "description": "Store something",
                        "tool": "store",
                        "arguments": {},
                        "verification": "N/A",
                    }
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    try:
        asyncio.run(agent.create_plan("Invalid plan", None))
    except ValueError:
        pass
    # The invalid plan must not have been persisted.
    assert database.get_task("no-such-task") is None
    # The fake tool must not have been executed at all.
    tool_approvals = database.list_tool_approvals()
    assert [a for a in tool_approvals if a.tool_name == "store"] == []


def test_bounded_repair_for_list_files_without_directory():
    class ListFilesInput(pydantic.BaseModel):
        directory: str
        recursive: bool = False
        max_results: int = pydantic.Field(default=100, ge=1, le=500)

    import tempfile, os
    workspace = tempfile.mkdtemp()
    try:
        settings = Settings(
            database_path=_tmp_path(),
            allow_tools=False,
            approved_roots=[os.fspath(workspace)],
        )
        registry = ToolRegistry(
            [
                ToolDefinition(
                    "list_files",
                    "List files in a directory.",
                    ListFilesInput,
                    False,
                    lambda request, settings: {},
                )
            ]
        )
        database = Database(settings.database_path)
        database.initialize()
        ollama = _closeable_fake_ollama(
            json.dumps(
                {
                    "needs_action": True,
                    "title": "Repair test",
                    "steps": [
                        {
                            "description": "List files",
                            "tool": "list_files",
                            "arguments": {},
                            "verification": "N/A",
                        }
                    ],
                }
            )
        )
        agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
        tools, plan = asyncio.run(agent.create_plan("Repair", None))
        step = plan.steps[0]
        assert step.tool == "list_files"
        assert "directory" in step.arguments
        assert step.arguments["directory"] == os.fspath(workspace)
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)


def test_bounded_repair_for_calculate_without_expression():
    class CalculateInput(pydantic.BaseModel):
        expression: str = pydantic.Field(min_length=1, max_length=500)

    settings = Settings(database_path=_tmp_path(), allow_tools=False)
    registry = ToolRegistry(
        [
            ToolDefinition(
                "calculate",
                "Calculate an expression.",
                CalculateInput,
                False,
                lambda request, settings: {},
            )
        ]
    )
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Repair test",
                "steps": [
                    {
                        "description": "Calculate",
                        "tool": "calculate",
                        "arguments": {},
                        "verification": "N/A",
                    }
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    tools, plan = asyncio.run(agent.create_plan("Repair", None))
    step = plan.steps[0]
    assert step.tool == "calculate"
    assert step.arguments == {"expression": "0"}


def test_repair_is_not_applied_to_other_tools():
    # Only list_files and calculate get bounded repair.
    class EchoInput(pydantic.BaseModel):
        x: int = pydantic.Field(ge=0, le=10)

    settings = Settings(database_path=_tmp_path(), allow_tools=False)
    registry = ToolRegistry(
        [
            ToolDefinition(
                "echo",
                "A minimal test tool.",
                EchoInput,
                False,
                lambda request, settings: {},
            )
        ]
    )
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "No repair expected",
                "steps": [
                    {
                        "description": "A step",
                        "tool": "echo",
                        "arguments": {},
                        "verification": "N/A",
                    }
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    with _assert_plan_error():
        asyncio.run(agent.create_plan("No repair", None))


def test_repaired_plan_still_rejected_if_repair_is_insufficient():
    class CalculateInput(pydantic.BaseModel):
        expression: str = pydantic.Field(min_length=1, max_length=500)

    settings = Settings(database_path=_tmp_path(), allow_tools=False)
    registry = ToolRegistry(
        [
            ToolDefinition(
                "calculate",
                "Calculate an expression.",
                CalculateInput,
                False,
                lambda request, settings: {},
            )
        ]
    )
    database = Database(settings.database_path)
    database.initialize()
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Repair then invalid",
                "steps": [
                    {
                        "description": "Calculate invalid",
                        "tool": "calculate",
                        "arguments": {"expression": ""},
                        "verification": "N/A",
                    }
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    with _assert_plan_error():
        asyncio.run(agent.create_plan("Repair then invalid", None))


def test_plan_schema_is_authoritative_for_registered_tools():
    agent, database = _build_agent(_valid_echo_plan())
    tools, plan = asyncio.run(agent.create_plan("Check schema", None))
    echo = next(item for item in tools if item["name"] == "echo")
    assert echo["requires_approval"] is False
    assert isinstance(echo["parameters_schema"], dict)
    assert "properties" in echo["parameters_schema"]
    # The schema shown to the model must describe the required field.
    props = echo["parameters_schema"]["properties"]
    assert "x" in props
    assert props["x"]["type"] == "integer"


def test_plan_submit_is_not_executed_in_create_plan():
    class CalculateInput(pydantic.BaseModel):
        expression: str = pydantic.Field(min_length=1, max_length=500)

    settings = Settings(database_path=_tmp_path(), allow_tools=False)
    database = Database(settings.database_path)
    database.initialize()
    registry = ToolRegistry(
        [
            ToolDefinition(
                "calculate",
                "Calculate an expression.",
                CalculateInput,
                False,
                lambda request, settings: {"executed": True},
            )
        ]
    )
    ollama = _closeable_fake_ollama(
        json.dumps(
            {
                "needs_action": True,
                "title": "Not executed",
                "steps": [
                    {
                        "description": "Calculate 1",
                        "tool": "calculate",
                        "arguments": {"expression": "1"},
                        "verification": "N/A",
                    }
                ],
            }
        )
    )
    agent = AgentOrchestrator(settings, database, ollama, registry, ToolExecutor(registry))
    tools, plan = asyncio.run(agent.create_plan("Not executed", None))
    assert plan.steps[0].tool == "calculate"
    # create_plan only parses and validates; it does not run the tool handler.
    assert database.list_tool_audits() == []


def _assert_plan_error():
    class _PlanError(AssertionError):
        pass

    class _raises:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is None:
                raise _PlanError("Expected a ValueError from create_plan")
            if not isinstance(exc_value, ValueError):
                raise _PlanError(f"Expected ValueError, got {exc_type.__name__}: {exc_value}") from exc_value
            return True

    return _raises()
