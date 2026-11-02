from __future__ import annotations

from shiro.database import Database


def test_database_persists_conversations_and_messages(tmp_path):
    database = Database(tmp_path / "shiro.db")
    database.initialize()

    conversation = database.create_conversation("Test chat")
    database.append_message(conversation.id, "user", "Hello")
    database.append_message(conversation.id, "assistant", "Hi there")

    messages = database.list_messages(conversation.id)

    assert conversation.title == "Test chat"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["Hello", "Hi there"]


def test_database_persists_approved_task_plan_and_resumable_state(tmp_path):
    database = Database(tmp_path / "tasks.db")
    database.initialize()

    task = database.create_task(
        "Prepare a review plan",
        ["Inspect the project", "Write a summary"],
        max_retries=2,
    )

    assert task.status == "waiting_approval"
    assert [step.description for step in database.list_task_steps(task.id)] == [
        "Inspect the project",
        "Write a summary",
    ]

    approved = database.decide_task_approval(task.id, approved=True)
    assert approved is not None
    assert approved.status == "planned"
    assert [item.id for item in database.list_resumable_tasks()] == [task.id]

    paused = database.pause_task(task.id)
    assert paused is not None
    assert paused.status == "paused"
    resumed = database.resume_task(task.id)
    assert resumed is not None
    assert resumed.status == "planned"

    running = database.start_task(task.id)
    assert running is not None
    assert running.status == "running"

    failed_once = database.record_task_failure(task.id, "Temporary failure")
    assert failed_once is not None
    assert failed_once.status == "paused"
    assert failed_once.retry_count == 1

    resumed_again = database.resume_task(task.id)
    assert resumed_again is not None
    database.start_task(task.id)
    database.record_task_failure(task.id, "Second failure")
    database.resume_task(task.id)
    database.start_task(task.id)
    failed_final = database.record_task_failure(task.id, "Final failure")
    assert failed_final is not None
    assert failed_final.status == "failed"


def test_running_tasks_are_paused_when_database_restarts(tmp_path):
    path = tmp_path / "restart.db"
    database = Database(path)
    database.initialize()
    task = database.create_task("Restart-safe task", ["Wait"] , requires_approval=False)
    database.start_task(task.id)

    restarted = Database(path)
    restarted.initialize()

    recovered = restarted.get_task(task.id)
    assert recovered is not None
    assert recovered.status == "paused"
