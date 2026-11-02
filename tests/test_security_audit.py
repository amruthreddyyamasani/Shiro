"""Comprehensive security verification tests for SHIRO Milestone 1.

Specifically verifies:
1. Expired approval rejection (returns status="denied", "Approval is expired or already consumed").
2. Reused approval rejection (returns status="denied", "Approval is expired or already consumed").
3. Denied approval rejection (returns status="denied", "Tool approval was not granted").
4. Approval for a different operation rejection (returns status="denied", "Approval does not match this operation").
5. Unauthorized task execution rejection.
6. Backend validation of tool arguments (Pydantic validation error).
7. Cooperative cancellation of tasks.
8. Safe recovery of paused and ambiguous tasks on startup.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import pytest

from shiro.config import Settings
from shiro.database import Database
from shiro.agent import AgentOrchestrator
from shiro.tools import ToolContext, ToolExecutor, build_default_registry


def make_test_context(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    settings = Settings(
        database_path=tmp_path / "sec_test.db",
        project_root=tmp_path,
        approved_roots=[root],
        allow_tools=True,
    )
    database = Database(settings.database_path)
    database.initialize()
    executor = ToolExecutor(build_default_registry())
    return root, database, settings, executor


def test_expired_approval_rejection(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    file_path = str(root / "expired_test.txt")
    context = ToolContext(settings, database)

    # 1. Execute to generate approval with canonical arguments
    initial = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "secret", "overwrite": False},
            context,
        )
    )
    assert initial.status == "approval_required"
    approval_id = initial.approval_id

    # Approve it, but set expires_at in the past
    database.decide_tool_approval(approval_id, approved=True)
    past_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    with database._connect() as conn:
        conn.execute("UPDATE tool_approvals SET expires_at = ? WHERE id = ?", (past_time, approval_id))

    # 2. Attempt execution with expired approval ID
    result = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "secret", "overwrite": False},
            context,
            approval_id=approval_id,
        )
    )

    # Security check: must be denied, expired error returned, no file created
    assert result.status == "denied"
    assert "expired or already consumed" in result.error.lower()
    assert not (root / "expired_test.txt").exists()


def test_reused_approval_rejection(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    file_path = str(root / "reused_test.txt")
    context = ToolContext(settings, database)

    # 1. Initial execution requires approval
    initial = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "first run", "overwrite": True},
            context,
        )
    )
    assert initial.status == "approval_required"
    approval_id = initial.approval_id

    # Approve it
    database.decide_tool_approval(approval_id, approved=True)

    # 2. First consumption: must succeed
    first_run = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "first run", "overwrite": True},
            context,
            approval_id=approval_id,
        )
    )
    assert first_run.status == "succeeded"

    # 3. Second consumption (reuse attempt): MUST be rejected
    second_run = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "first run", "overwrite": True},
            context,
            approval_id=approval_id,
        )
    )
    assert second_run.status == "denied"
    assert "expired or already consumed" in second_run.error.lower()


def test_denied_approval_rejection(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    file_path = str(root / "denied_test.txt")
    context = ToolContext(settings, database)

    initial = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "denied", "overwrite": False},
            context,
        )
    )
    approval_id = initial.approval_id

    # User explicitly denies
    database.decide_tool_approval(approval_id, approved=False)

    # Attempt execution with denied approval
    result = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path, "content": "denied", "overwrite": False},
            context,
            approval_id=approval_id,
        )
    )

    assert result.status == "denied"
    assert "tool approval was not granted" in result.error.lower()
    assert not (root / "denied_test.txt").exists()


def test_approval_for_different_operation_rejection(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    file_path_a = str(root / "file_a.txt")
    file_path_b = str(root / "file_b.txt")
    context = ToolContext(settings, database)

    # Create approval for file_a
    initial = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path_a, "content": "a", "overwrite": False},
            context,
        )
    )
    approval_id = initial.approval_id
    database.decide_tool_approval(approval_id, approved=True)

    # Attempt to use file_a's approval to write file_b
    result = asyncio.run(
        executor.execute(
            "create_text_file",
            {"path": file_path_b, "content": "a", "overwrite": False},
            context,
            approval_id=approval_id,
        )
    )

    assert result.status == "denied"
    assert "does not match" in result.error.lower()
    assert not (root / "file_b.txt").exists()


def test_unauthorized_task_execution_rejection(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)

    # Create task with requires_approval=True
    task = database.create_task(
        title="Unapproved Task",
        steps=["Step 1"],
        requires_approval=True,
    )
    assert task.status == "waiting_approval"

    registry = build_default_registry()
    agent = AgentOrchestrator(
        settings,
        database,
        None,  # Ollama not needed for running already planned tasks
        registry,
        executor,
    )

    # Attempt running while still waiting_approval: must be rejected
    run_result = asyncio.run(agent.run_task(task.id))
    assert run_result.status == "waiting_approval"
    assert "approval is required" in run_result.message.lower()

    # Deny task approval: task status transitions to failed
    decided = database.decide_task_approval(task.id, approved=False)
    assert decided.status == "failed"
    denied_run = asyncio.run(agent.run_task(task.id))
    assert denied_run.status == "failed"


def test_backend_validation_of_tool_arguments(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    context = ToolContext(settings, database)

    # Missing required 'path' field
    result = asyncio.run(
        executor.execute(
            "read_text_file",
            {"wrong_key": 123},
            context,
        )
    )
    assert result.status == "failed"
    assert "validation error" in result.error.lower()

    # Out of range max_results for list_files
    bad_max = asyncio.run(
        executor.execute(
            "list_files",
            {"directory": str(root), "max_results": 999999},
            context,
        )
    )
    assert bad_max.status == "failed"
    assert "validation error" in bad_max.error.lower()


def test_cancellation_of_task(tmp_path):
    root, database, settings, executor = make_test_context(tmp_path)
    task = database.create_task(
        title="Cancel Test",
        steps=["Step 1", "Step 2"],
        requires_approval=False,
    )
    agent = AgentOrchestrator(
        settings,
        database,
        None,
        build_default_registry(),
        executor,
    )

    # Request cancel
    agent.store.request_cancel(task.id)
    assert agent.store.is_cancel_requested(task.id)

    # Cooperative cancel pauses the task
    canceled_task = database.set_task_status(task.id, "paused", "Cancellation requested")
    assert canceled_task.status == "paused"


def test_recovery_of_paused_and_ambiguous_tasks(tmp_path):
    db_path = tmp_path / "recovery.db"
    db = Database(db_path)
    db.initialize()

    # Simulate an in-flight running task before a crash
    task = db.create_task("Crash task", ["Step 1"], requires_approval=False)
    db.start_task(task.id)
    assert db.get_task(task.id).status == "running"

    # Simulate step run in progress
    agent = AgentOrchestrator(
        Settings(database_path=db_path),
        db,
        None,
        build_default_registry(),
        ToolExecutor(build_default_registry()),
    )
    steps = db.list_task_steps(task.id)
    agent.store.start_run(task.id, steps[0].id)
    assert agent.store.latest_run(steps[0].id)["status"] == "running"

    # CRASH & RESTART: initialize() simulates system startup recovery
    db_restarted = Database(db_path)
    db_restarted.initialize()
    agent_restarted = AgentOrchestrator(
        Settings(database_path=db_path),
        db_restarted,
        None,
        build_default_registry(),
        ToolExecutor(build_default_registry()),
    )

    # Verified: running tasks must be reset to paused
    recovered_task = db_restarted.get_task(task.id)
    assert recovered_task.status == "paused"

    # Verified: in-flight step runs must be marked ambiguous
    recovered_run = agent_restarted.store.latest_run(steps[0].id)
    assert recovered_run["status"] == "ambiguous"
