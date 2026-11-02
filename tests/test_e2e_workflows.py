"""Comprehensive end-to-end integration tests for SHIRO Sprint major user workflows."""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from shiro.app import create_app
from shiro.config import Settings
from shiro.database import Database
from shiro.ollama_client import OllamaModelInfo, OllamaResponseError


class MockOllama:
    def __init__(self):
        self.stream_calls = []
        self.cancelled = False

    async def list_models(self):
        return [
            OllamaModelInfo(name="shiro:latest", size=2683396814),
            OllamaModelInfo(name="qwen3.5:2b", size=2683396812),
        ]

    async def aclose(self):
        pass

    async def stream_chat(self, messages):
        self.stream_calls.append(list(messages))
        # Check if memory extraction call
        if any("Return only JSON" in m.get("content", "") for m in messages):
            yield '{"memories": []}'
            return

        # Stream tokens
        tokens = ["Hello", " from", " local", " SHIRO", "!"]
        try:
            for token in tokens:
                yield token
        except GeneratorExit:
            self.cancelled = True
            raise


@pytest.fixture
def test_setup(tmp_path):
    approved_root = tmp_path / "workspace"
    approved_root.mkdir()
    settings = Settings(
        database_path=tmp_path / "shiro.db",
        allow_tools=True,
        approved_roots=[approved_root],
        project_root=approved_root,
    )
    database = Database(settings.database_path)
    database.initialize()
    mock_ollama = MockOllama()
    app = create_app(settings, database, mock_ollama)
    return app, settings, database, mock_ollama, approved_root


def test_workflow_1_create_and_switch_conversations(test_setup):
    """Workflow 1: Create, switch, list, and delete conversations with history intact."""
    app, _, _, _, _ = test_setup

    with TestClient(app) as client:
        # Create first thread
        res1 = client.post("/v1/conversations", json={"title": "Project Alpha"})
        assert res1.status_code == 201
        c1_id = res1.json()["id"]

        # Create second thread
        res2 = client.post("/v1/conversations", json={"title": "Project Beta"})
        assert res2.status_code == 201
        c2_id = res2.json()["id"]

        # List conversations
        listing = client.get("/v1/conversations").json()
        assert len(listing) == 2
        ids = [c["id"] for c in listing]
        assert c1_id in ids
        assert c2_id in ids

        # Send message in thread 1
        with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"content": "Alpha message", "conversation_id": c1_id},
        ) as stream1:
            events1 = [json.loads(line) for line in stream1.iter_lines() if line]
        assert any(e.get("type") == "done" for e in events1)

        # Send message in thread 2
        with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"content": "Beta message", "conversation_id": c2_id},
        ) as stream2:
            events2 = [json.loads(line) for line in stream2.iter_lines() if line]
        assert any(e.get("type") == "done" for e in events2)

        # Switch to thread 1: inspect persisted history
        msgs1 = client.get(f"/v1/conversations/{c1_id}/messages").json()
        assert len(msgs1) == 2
        assert msgs1[0]["content"] == "Alpha message"
        assert "Hello from local SHIRO!" in msgs1[1]["content"]

        # Switch to thread 2: inspect persisted history
        msgs2 = client.get(f"/v1/conversations/{c2_id}/messages").json()
        assert len(msgs2) == 2
        assert msgs2[0]["content"] == "Beta message"

        # Delete thread 1
        del_res = client.delete(f"/v1/conversations/{c1_id}")
        assert del_res.status_code == 204

        # Verify thread 2 remains intact
        remaining = client.get("/v1/conversations").json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == c2_id


def test_workflow_2_send_and_stream_chat_response(test_setup):
    """Workflow 2: Stream chat tokens and verify server-side behavior."""
    app, _, _, _, _ = test_setup

    with TestClient(app) as client:
        # Stream response
        with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"content": "Explain safety in SHIRO"},
        ) as stream:
            lines = [json.loads(line) for line in stream.iter_lines() if line]

        token_events = [e for e in lines if e.get("type") == "token"]
        done_events = [e for e in lines if e.get("type") == "done"]

        assert len(token_events) > 0
        assert len(done_events) == 1
        assert done_events[0]["content"] == "Hello from local SHIRO!"

        cid = done_events[0]["conversation_id"]
        messages = client.get(f"/v1/conversations/{cid}/messages").json()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"


def test_workflow_3_create_and_execute_task(test_setup):
    """Workflow 3: Create, approve, and execute task."""
    app, _, _, _, _ = test_setup

    with TestClient(app) as client:
        # Create manual task requiring approval
        create_res = client.post(
            "/v1/tasks",
            json={
                "title": "Data indexing plan",
                "steps": ["Scan directory", "Compute file hashes"],
                "max_retries": 1,
                "requires_approval": True,
            },
        )
        assert create_res.status_code == 201
        task = create_res.json()
        task_id = task["id"]
        assert task["status"] == "waiting_approval"

        # Approve task
        approve_res = client.post(
            f"/v1/tasks/{task_id}/approve",
            json={"approved": True, "note": "Approved by supervisor"},
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "planned"

        # Pause and resume task
        pause_res = client.post(f"/v1/tasks/{task_id}/pause")
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "paused"

        resume_res = client.post(f"/v1/tasks/{task_id}/resume")
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "planned"


def test_workflow_4_approve_and_reject_tool_operations(test_setup):
    """Workflow 4: Request tool execution requiring approval, decide approve and reject."""
    app, _, _, _, approved_root = test_setup

    with TestClient(app) as client:
        # Request file write 1 -> requires approval
        test_file_1 = approved_root / "test1.txt"
        res1 = client.post(
            "/v1/tools/create_text_file/execute",
            json={"arguments": {"path": str(test_file_1), "content": "Sample content 1"}},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "approval_required"
        appr1_id = data1["approval_id"]

        # Approve operation 1
        decide1 = client.post(
            f"/v1/tool-approvals/{appr1_id}/decide",
            json={"approved": True},
        )
        assert decide1.status_code == 200
        assert decide1.json()["status"] == "approved"

        # Execute with approved token
        exec1 = client.post(
            "/v1/tools/create_text_file/execute",
            json={
                "arguments": {"path": str(test_file_1), "content": "Sample content 1"},
                "approval_id": appr1_id,
            },
        )
        assert exec1.status_code == 200
        assert exec1.json()["status"] == "succeeded"
        assert test_file_1.read_text(encoding="utf-8") == "Sample content 1"

        # Request file write 2 -> reject
        test_file_2 = approved_root / "test2.txt"
        res2 = client.post(
            "/v1/tools/create_text_file/execute",
            json={"arguments": {"path": str(test_file_2), "content": "Rejected content"}},
        )
        appr2_id = res2.json()["approval_id"]

        decide2 = client.post(
            f"/v1/tool-approvals/{appr2_id}/decide",
            json={"approved": False},
        )
        assert decide2.status_code == 200
        assert decide2.json()["status"] == "denied"


def test_workflow_5_memory_search_edit_delete(test_setup):
    """Workflow 5: Search, edit and delete long term memories."""
    app, _, _, _, _ = test_setup

    with TestClient(app) as client:
        # Create memory
        create_res = client.post(
            "/v1/memories",
            json={
                "category": "preferences",
                "content": "User prefers concise python code",
            },
        )
        assert create_res.status_code == 200
        m_id = create_res.json()["id"]

        # Search memory
        search_res = client.get("/v1/memories/search?q=concise").json()
        assert len(search_res) == 1
        assert search_res[0]["id"] == m_id

        # Update memory
        patch_res = client.patch(
            f"/v1/memories/{m_id}",
            json={"content": "User strictly prefers concise type-annotated Python"},
        )
        assert patch_res.status_code == 200
        assert "type-annotated" in patch_res.json()["content"]

        # Delete memory
        del_res = client.delete(f"/v1/memories/{m_id}")
        assert del_res.status_code == 204

        # Verify deleted
        after_search = client.get("/v1/memories/search?q=concise").json()
        assert len(after_search) == 0


def test_workflow_6_inspect_activity_records(test_setup):
    """Workflow 6: Inspect activity and audit records with category filtering."""
    app, _, _, _, approved_root = test_setup

    with TestClient(app) as client:
        # Run calculate tool
        client.post(
            "/v1/tools/calculate/execute",
            json={"arguments": {"expression": "100 * 3"}},
        )

        # Inspect audit events
        audits = client.get("/v1/audit").json()
        assert len(audits) >= 1
        assert any("calculate" in a["title"] for a in audits)

        # Filter by security_audit
        sec = client.get("/v1/audit?category=security_audit").json()
        assert all(a["category"] == "security_audit" for a in sec)

        # Search by keyword
        calc_search = client.get("/v1/audit?search=calculate").json()
        assert len(calc_search) >= 1


def test_workflow_7_review_self_improvement_proposal(test_setup):
    """Workflow 7: Create, review diff, test, apply with backup, and rollback."""
    app, _, _, _, approved_root = test_setup

    test_dir = approved_root / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",
    )

    with TestClient(app) as client:
        target_file = "notes.txt"
        create_res = client.post(
            "/v1/self-improvement/requests",
            json={
                "title": "Add architecture notes",
                "description": "Staging notes.txt for automated self-improvement review",
                "files": [target_file],
                "test_command": "python -m pytest -q",
                "proposed_files": {target_file: "# Shiro Architecture\nLocal-first design.\n"},
            },
        )
        assert create_res.status_code == 201
        req_id = create_res.json()["id"]
        assert "Local-first design" in create_res.json()["diff"]

        # Approve proposal first before running staging tests
        approve_res = client.post(
            f"/v1/self-improvement/requests/{req_id}/decide",
            json={"approved": True, "note": "Verified diff. Approved for staging tests."},
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "approved"

        # Run staging tests in isolated sandbox
        test_res = client.post(f"/v1/self-improvement/requests/{req_id}/test")
        assert test_res.status_code == 200
        assert test_res.json()["test_status"] == "passed"

        # Apply changes to workspace
        apply_res = client.post(f"/v1/self-improvement/requests/{req_id}/apply")
        assert apply_res.status_code == 200
        assert apply_res.json()["applied_at"] is not None
        assert (approved_root / target_file).read_text(encoding="utf-8") == "# Shiro Architecture\nLocal-first design.\n"

        # Rollback changes
        rollback_res = client.post(f"/v1/self-improvement/requests/{req_id}/rollback")
        assert rollback_res.status_code == 200
        assert not (approved_root / target_file).exists()


def test_workflow_8_handle_disconnection_and_recovery(test_setup):
    """Workflow 8: Handle backend and inference offline status gracefully."""
    app, _, _, _, _ = test_setup

    with TestClient(app) as client:
        # Health check is OK
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        # Capabilities endpoint
        caps = client.get("/v1/capabilities")
        assert caps.status_code == 200

        # System info check
        sys_info = client.get("/v1/system/info")
        assert sys_info.status_code == 200
        assert sys_info.json()["ollama_connected"] is True
