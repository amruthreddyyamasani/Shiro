
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from shiro.app import create_app
from shiro.config import Settings
from shiro.database import Database


class FakeOllama:
    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []

    async def list_models(self):
        from shiro.ollama_client import OllamaModelInfo
        return [
            OllamaModelInfo(name="shiro:latest", size=1000),
            OllamaModelInfo(name="llama3:latest", size=2000),
        ]

    async def stream_chat(self, messages):
        self.calls.append(list(messages))

        # Return valid JSON for memory extraction requests.
        if any(
            "Return only JSON" in message.get("content", "")
            for message in messages
        ):
            yield '{"memories": []}'
            return

        yield "Hello"
        yield " locally"

    async def aclose(self):
        return None


class PlanningOllama(FakeOllama):
    def __init__(self, plan):
        super().__init__()
        self.plan = plan

    async def stream_chat(self, messages):
        if any("task planner" in message.get("content", "") for message in messages):
            self.calls.append(list(messages))
            yield json.dumps(self.plan)
            return
        async for token in super().stream_chat(messages):
            yield token


def make_test_app(tmp_path, fake_ollama=None):
    settings = Settings(database_path=tmp_path / "shiro.db")
    database = Database(settings.database_path)
    ollama = fake_ollama or FakeOllama()
    app = create_app(settings, database, ollama)  # type: ignore[arg-type]
    return app, settings, database, ollama


def test_stream_chat_persists_user_and_assistant_messages(tmp_path):
    fake_ollama = FakeOllama()
    app, settings, database, _ = make_test_app(tmp_path, fake_ollama)

    with TestClient(app) as client:
        conversation_response = client.post(
            "/v1/conversations",
            json={"title": "API test"},
        )
        conversation_id = conversation_response.json()["id"]

        response = client.post(
            "/v1/chat/stream",
            json={
                "conversation_id": conversation_id,
                "content": "Say hello",
            },
        )

    events = [json.loads(line) for line in response.text.splitlines()]

    assert response.status_code == 200
    assert [event["type"] for event in events] == ["token", "token", "done"]
    assert events[-1]["content"] == "Hello locally"
    assert fake_ollama.calls[0][-1] == {
        "role": "user",
        "content": "Say hello",
    }

    stored = database.list_messages(conversation_id)
    assert [(message.role, message.content) for message in stored] == [
        ("user", "Say hello"),
        ("assistant", "Hello locally"),
    ]


def test_stream_chat_includes_relevant_memory_context(tmp_path):
    fake_ollama = FakeOllama()
    app, _, database, _ = make_test_app(tmp_path, fake_ollama)
    database.add_memory("projects", "Building the SHIRO assistant.")

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/stream",
            json={"content": "Tell me about SHIRO"},
        )

    assert response.status_code == 200
    system_messages = [
        message["content"]
        for message in fake_ollama.calls[0]
        if message["role"] == "system"
    ]
    assert any("SHIRO assistant" in content for content in system_messages)
    assert any("friendly companion" in content for content in system_messages)


def test_health_reports_local_privacy_defaults(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["thinking_disabled"] is True
    assert response.json()["tools_enabled"] is False


def test_create_and_list_memories(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/memories",
            json={
                "category": "preferences",
                "content": "Prefers concise explanations.",
            },
        )

        list_response = client.get("/v1/memories")

    assert create_response.status_code == 200
    assert create_response.json()["category"] == "preferences"
    assert create_response.json()["content"] == "Prefers concise explanations."

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["content"] == "Prefers concise explanations."


def test_list_memories_by_category(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        client.post(
            "/v1/memories",
            json={"category": "skills", "content": "Learning Python."},
        )
        client.post(
            "/v1/memories",
            json={"category": "projects", "content": "Building SHIRO."},
        )

        response = client.get("/v1/memories?category=skills")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["category"] == "skills"


def test_search_memories(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        client.post(
            "/v1/memories",
            json={"category": "projects", "content": "Building SHIRO assistant."},
        )
        client.post(
            "/v1/memories",
            json={"category": "skills", "content": "Learning Python programming."},
        )

        response = client.get("/v1/memories/search?q=SHIRO")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert "SHIRO" in response.json()[0]["content"]


def test_update_memory(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/memories",
            json={"category": "skills", "content": "Learning Python."},
        )
        memory_id = create_response.json()["id"]

        update_response = client.patch(
            f"/v1/memories/{memory_id}",
            json={
                "category": "projects",
                "content": "Building a Python project.",
            },
        )

    assert update_response.status_code == 200
    assert update_response.json()["category"] == "projects"
    assert update_response.json()["content"] == "Building a Python project."


def test_delete_memory(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/memories",
            json={"category": "general", "content": "A temporary memory."},
        )
        memory_id = create_response.json()["id"]

        delete_response = client.delete(f"/v1/memories/{memory_id}")
        list_response = client.get("/v1/memories")

    assert delete_response.status_code == 204
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_missing_memory_returns_404(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        update_response = client.patch(
            "/v1/memories/999",
            json={"content": "Updated memory."},
        )
        delete_response = client.delete("/v1/memories/999")

    assert update_response.status_code == 404
    assert delete_response.status_code == 404


def test_invalid_memory_category_is_rejected(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/v1/memories",
            json={
                "category": "invalid-category",
                "content": "This should not be stored.",
            },
        )

    assert response.status_code == 422


def test_task_plan_requires_approval_and_can_resume(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/tasks",
            json={
                "title": "Review SHIRO",
                "steps": ["Inspect code", "Run tests"],
                "max_retries": 2,
            },
        )
        task_id = create_response.json()["id"]

        assert create_response.status_code == 201
        assert create_response.json()["status"] == "waiting_approval"

        approve_response = client.post(
            f"/v1/tasks/{task_id}/approve",
            json={"approved": True, "note": "Approved for planning only."},
        )
        pause_response = client.post(f"/v1/tasks/{task_id}/pause")
        resume_response = client.post(f"/v1/tasks/{task_id}/resume")
        resumable_response = client.get("/v1/tasks/resumable")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "planned"
    assert pause_response.json()["status"] == "paused"
    assert resume_response.json()["status"] == "planned"
    assert any(item["id"] == task_id for item in resumable_response.json())


def test_capabilities_web_approval_and_self_improvement_are_review_only(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        capabilities_response = client.get("/v1/capabilities")
        web_response = client.post(
            "/v1/web/actions",
            json={
                "method": "GET",
                "url": "https://example.test/status",
                "reason": "Check the requested status page.",
            },
        )
        web_id = web_response.json()["id"]
        web_approval_response = client.post(
            f"/v1/web/actions/{web_id}/approve",
            json={"approved": True, "note": "Approved for a future executor."},
        )
        change_response = client.post(
            "/v1/self-improvement/requests",
            json={
                "title": "Improve task recovery",
                "description": "Add coverage for restart recovery.",
                "files": ["shiro/database.py", "tests/test_database.py"],
                "test_command": "python -m pytest -q",
            },
        )
        change_id = change_response.json()["id"]
        change_decision_response = client.post(
            f"/v1/self-improvement/requests/{change_id}/decide",
            json={"approved": True, "note": "Review approved; still run tests."},
        )

    assert capabilities_response.status_code == 200
    assert all(item["execution_enabled"] is False for item in capabilities_response.json())
    assert web_response.status_code == 201
    assert web_response.json()["status"] == "pending"
    assert web_approval_response.json()["status"] == "approved"
    assert change_response.status_code == 201
    assert change_response.json()["status"] == "proposed"
    assert change_decision_response.json()["status"] == "approved"


def test_registered_tools_execute_safely_and_require_write_approval(tmp_path):
    settings = Settings(database_path=tmp_path / "shiro.db", allow_tools=True)
    database = Database(settings.database_path)
    database.initialize()
    approved_root = tmp_path / "workspace"
    approved_root.mkdir()
    settings = settings.model_copy(update={"approved_roots": [approved_root]})
    app = create_app(settings, database, FakeOllama())

    with TestClient(app) as client:
        tools_response = client.get("/v1/tools")
        capabilities_response = client.get("/v1/capabilities")
        screenshot_response = client.post(
            "/v1/tools/screenshots_capture/execute",
            json={"arguments": {}},
        )
        calculate_response = client.post(
            "/v1/tools/calculate/execute",
            json={"arguments": {"expression": "(2 + 3) * 4"}},
        )
        outside_response = client.post(
            "/v1/tools/list_files/execute",
            json={"arguments": {"directory": str(tmp_path)}},
        )
        write_response = client.post(
            "/v1/tools/create_text_file/execute",
            json={
                "arguments": {
                    "path": str(approved_root / "hello.txt"),
                    "content": "hello",
                }
            },
        )
        approval_id = write_response.json()["approval_id"]
        approval_response = client.post(
            f"/v1/tool-approvals/{approval_id}/decide",
            json={"approved": True},
        )
        executed_write_response = client.post(
            "/v1/tools/create_text_file/execute",
            json={
                "arguments": {
                    "path": str(approved_root / "hello.txt"),
                    "content": "hello",
                },
                "approval_id": approval_id,
            },
        )
        repeated_write_response = client.post(
            "/v1/tools/create_text_file/execute",
            json={
                "arguments": {
                    "path": str(approved_root / "hello.txt"),
                    "content": "hello",
                },
                "approval_id": approval_id,
            },
        )

    assert tools_response.status_code == 200
    assert {item["name"] for item in tools_response.json()} >= {
        "list_files",
        "read_text_file",
        "calculate",
        "screenshots_capture",
    }
    assert capabilities_response.status_code == 200
    screen_capability = next(
        item for item in capabilities_response.json() if item["name"] == "screen_perception"
    )
    assert screen_capability["execution_enabled"] is True
    assert screenshot_response.status_code == 200
    assert screenshot_response.json()["status"] == "approval_required"
    assert calculate_response.json()["status"] == "succeeded"
    assert calculate_response.json()["output"]["result"] == 20.0
    assert outside_response.json()["status"] == "failed"
    assert write_response.json()["status"] == "approval_required"
    assert approval_response.json()["status"] == "approved"
    assert executed_write_response.json()["status"] == "succeeded"
    assert repeated_write_response.json()["status"] == "denied"


def test_agent_plans_approves_executes_and_verifies_a_file_task(tmp_path):
    approved_root = tmp_path / "workspace"
    approved_root.mkdir()
    target = approved_root / "agent-created.txt"
    planner = PlanningOllama(
        {
            "needs_action": True,
            "title": "Create an agent file",
            "steps": [
                {
                    "description": "Create the requested text file.",
                    "tool": "create_text_file",
                    "arguments": {"path": str(target), "content": "created by SHIRO"},
                    "verification": "The file exists with the requested content.",
                }
            ],
        }
    )
    settings = Settings(
        database_path=tmp_path / "agent.db",
        allow_tools=True,
        approved_roots=[approved_root],
    )
    database = Database(settings.database_path)
    app = create_app(settings, database, planner)

    with TestClient(app) as client:
        plan_response = client.post(
            "/v1/agent/plan",
            json={"request": "Create the file requested by the user."},
        )
        task_id = plan_response.json()["task_id"]
        assert plan_response.json()["status"] == "waiting_approval"

        task_approval_response = client.post(
            f"/v1/tasks/{task_id}/approve",
            json={"approved": True},
        )
        first_run_response = client.post(f"/v1/tasks/{task_id}/run")
        pending_response = client.get("/v1/tool-approvals?status=pending")
        approval_id = pending_response.json()[0]["id"]
        tool_approval_response = client.post(
            f"/v1/tool-approvals/{approval_id}/decide",
            json={"approved": True},
        )
        final_run_response = client.post(f"/v1/tasks/{task_id}/run")

    assert task_approval_response.json()["status"] == "planned"
    assert first_run_response.json()["status"] == "waiting_approval"
    assert tool_approval_response.json()["status"] == "approved"
    assert final_run_response.json()["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "created by SHIRO"


def test_task_can_be_cancelled_before_execution(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/tasks",
            json={
                "title": "Cancel this task",
                "steps": ["Do not execute"],
                "requires_approval": False,
            },
        )
        task_id = create_response.json()["id"]
        cancel_response = client.post(f"/v1/tasks/{task_id}/cancel")
        resume_response = client.post(f"/v1/tasks/{task_id}/resume")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "paused"
    assert cancel_response.json()["last_error"] == "Task cancellation requested"
    assert resume_response.json()["status"] == "planned"


def test_self_improvement_stages_tests_applies_and_rolls_back(tmp_path):
    project_root = tmp_path / "project"
    test_root = project_root / "tests"
    test_root.mkdir(parents=True)
    (test_root / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",
    )
    settings = Settings(
        database_path=tmp_path / "review.db",
        project_root=project_root,
    )
    database = Database(settings.database_path)
    app = create_app(settings, database, FakeOllama())

    with TestClient(app) as client:
        create_response = client.post(
            "/v1/self-improvement/requests",
            json={
                "title": "Add a reviewed file",
                "description": "Stage a new file for review.",
                "files": ["notes.txt"],
                "test_command": "python -m pytest -q",
                "proposed_files": {"notes.txt": "reviewed change\n"},
            },
        )
        request_id = create_response.json()["id"]
        assert "reviewed change" in create_response.json()["diff"]
        client.post(
            f"/v1/self-improvement/requests/{request_id}/decide",
            json={"approved": True},
        )
        test_response = client.post(
            f"/v1/self-improvement/requests/{request_id}/test"
        )
        apply_response = client.post(
            f"/v1/self-improvement/requests/{request_id}/apply"
        )
        applied_content = (project_root / "notes.txt").read_text(encoding="utf-8")
        rollback_response = client.post(
            f"/v1/self-improvement/requests/{request_id}/rollback"
        )

    assert test_response.json()["test_status"] == "passed"
    assert apply_response.json()["applied_at"] is not None
    assert applied_content == "reviewed change\n"
    assert rollback_response.status_code == 200
    assert not (project_root / "notes.txt").exists()


def test_list_and_delete_conversations(tmp_path):
    app, _, database, _ = make_test_app(tmp_path, FakeOllama())

    with TestClient(app) as client:
        # Initially empty
        initial = client.get("/v1/conversations").json()
        assert initial == []

        # Create two conversations
        c1 = client.post("/v1/conversations", json={"title": "First"}).json()
        c2 = client.post("/v1/conversations", json={"title": "Second"}).json()

        # List conversations
        listing = client.get("/v1/conversations").json()
        assert len(listing) == 2
        titles = [c["title"] for c in listing]
        assert "First" in titles
        assert "Second" in titles

        # Delete conversation
        del_res = client.delete(f"/v1/conversations/{c1['id']}")
        assert del_res.status_code == 204

        # List again
        listing_after = client.get("/v1/conversations").json()
        assert len(listing_after) == 1
        assert listing_after[0]["id"] == c2["id"]

        # 404 on deleting non-existent conversation
        del_404 = client.delete("/v1/conversations/non-existent-id")
        assert del_404.status_code == 404


def test_settings_and_personality(tmp_path):
    app, _, _, _ = make_test_app(tmp_path, FakeOllama())

    with TestClient(app) as client:
        # Get settings
        settings_res = client.get("/v1/settings")
        assert settings_res.status_code == 200
        settings_data = settings_res.json()
        assert settings_data["personality_mode"] == "adaptive"
        assert settings_data["thinking_enabled"] is False

        # Update personality
        update_res = client.post(
            "/v1/settings/personality",
            json={"personality_mode": "professional"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["personality_mode"] == "professional"

        # Verify updated settings
        settings_after = client.get("/v1/settings").json()
        assert settings_after["personality_mode"] == "professional"


def test_model_selection(tmp_path):
    app, _, _, _ = make_test_app(tmp_path, FakeOllama())

    with TestClient(app) as client:
        # FakeOllama has models: "shiro:latest" and "llama3:latest"
        select_res = client.post(
            "/v1/models/select",
            json={"model": "llama3:latest"},
        )
        assert select_res.status_code == 200
        assert select_res.json()["current_model"] == "llama3:latest"

        # Selecting non-installed model returns 400
        bad_select = client.post(
            "/v1/models/select",
            json={"model": "non-existent-model:latest"},
        )
        assert bad_select.status_code == 400


def test_system_info(tmp_path):
    app, _, _, _ = make_test_app(tmp_path, FakeOllama())

    with TestClient(app) as client:
        res = client.get("/v1/system/info")
        assert res.status_code == 200
        data = res.json()
        assert "os_name" in data
        assert "python_version" in data
        assert data["app_version"] == "0.1.0"
        assert data["database_wal_enabled"] is True


def test_audit_logs(tmp_path):
    approved_root = tmp_path / "workspace"
    approved_root.mkdir()
    settings = Settings(
        database_path=tmp_path / "shiro.db",
        allow_tools=True,
        approved_roots=[approved_root],
    )
    database = Database(settings.database_path)
    database.initialize()
    app = create_app(settings, database, FakeOllama())

    with TestClient(app) as client:
        # Initially empty audit list
        initial_audits = client.get("/v1/audit").json()
        assert isinstance(initial_audits, list)

        # Trigger calculate (auto-permitted) to create a tool audit entry
        calc_res = client.post(
            "/v1/tools/calculate/execute",
            json={"arguments": {"expression": "2 + 2"}},
        )
        assert calc_res.status_code == 200

        # Trigger a protected file creation to create a tool approval entry
        client.post(
            "/v1/tools/create_text_file/execute",
            json={"arguments": {"path": str(approved_root / "hello.txt"), "content": "hi"}},
        )

        # Audit should now have records
        audits = client.get("/v1/audit").json()
        assert len(audits) >= 2
        security_audits = client.get("/v1/audit?category=security_audit").json()
        assert len(security_audits) >= 2

        # Search
        search_res = client.get("/v1/audit?search=calculate").json()
        assert len(search_res) >= 1
