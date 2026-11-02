from __future__ import annotations

import asyncio

import httpx
import pytest

from shiro.config import Settings
from shiro.database import Database
from shiro.tools import ToolContext, ToolExecutor, build_default_registry


def make_executor(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    settings = Settings(
        database_path=tmp_path / "tools.db",
        approved_roots=[root],
        allow_tools=True,
    )
    database = Database(settings.database_path)
    database.initialize()
    return root, database, settings, ToolExecutor(build_default_registry())


def test_tools_reject_traversal_and_unsafe_calculation(tmp_path):
    root, database, settings, executor = make_executor(tmp_path)

    outside = asyncio.run(
        executor.execute(
            "list_files",
            {"directory": str(root / "..")},
            ToolContext(settings, database),
        )
    )
    unsafe_calculation = asyncio.run(
        executor.execute(
            "calculate",
            {"expression": "__import__('os').getcwd()"},
            ToolContext(settings, database),
        )
    )

    assert outside.status == "failed"
    assert unsafe_calculation.status == "failed"


def test_windows_system_info_is_read_only(tmp_path):
    _, database, settings, executor = make_executor(tmp_path)

    result = asyncio.run(
        executor.execute(
            "windows_system_info",
            {},
            ToolContext(settings, database),
        )
    )

    assert result.status == "succeeded"
    assert "python_version" in result.output
    assert "user" not in result.output


def test_symlink_escape_is_rejected_when_supported(tmp_path):
    root, database, settings, executor = make_executor(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable in this Windows test environment")

    result = asyncio.run(
        executor.execute(
            "list_files",
            {"directory": str(link)},
            ToolContext(settings, database),
        )
    )

    assert result.status == "failed"


def test_web_search_requires_one_time_approval_and_parses_untrusted_results(
    tmp_path, monkeypatch
):
    _, database, settings, executor = make_executor(tmp_path)

    class FakeClient:
        def __init__(self, **kwargs):
            del kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, endpoint, params):
            assert endpoint == "https://html.duckduckgo.com/html/"
            assert params == {"q": "SHIRO"}
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<a class="result__a" href="https://example.test/a">'
                    "Example result</a>"
                ),
            )

    monkeypatch.setattr("shiro.tools.httpx.Client", FakeClient)
    monkeypatch.setattr("shiro.tools._assert_public_host", lambda host: None)
    context = ToolContext(settings, database)

    pending = asyncio.run(
        executor.execute("web_search", {"query": "SHIRO"}, context)
    )
    approval = database.get_tool_approval(pending.approval_id)
    assert pending.status == "approval_required"
    assert approval is not None
    database.decide_tool_approval(approval.id, approved=True)

    executed = asyncio.run(
        executor.execute(
            "web_search",
            {"query": "SHIRO"},
            context,
            approval_id=approval.id,
        )
    )
    repeated = asyncio.run(
        executor.execute(
            "web_search",
            {"query": "SHIRO"},
            context,
            approval_id=approval.id,
        )
    )

    assert executed.status == "succeeded"
    assert executed.output["results"][0]["title"] == "Example result"
    assert repeated.status == "denied"


def test_approved_tool_expiration_is_enforced(tmp_path):
    _, database, settings, executor = make_executor(tmp_path)
    pending = asyncio.run(
        executor.execute("create_directory", {"path": str(tmp_path / "new")}, ToolContext(settings, database))
    )
    approval = database.get_tool_approval(pending.approval_id)
    assert approval is not None
    with database._connect() as connection:
        connection.execute(
            "UPDATE tool_approvals SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", approval.id),
        )
    database.decide_tool_approval(approval.id, approved=True)

    result = asyncio.run(
        executor.execute(
            "create_directory",
            {"path": str(tmp_path / "new")},
            ToolContext(settings, database),
            approval_id=approval.id,
        )
    )

    assert result.status == "denied"
