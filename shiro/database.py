
"""SQLite persistence for conversations, messages and long-term memories."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


MEMORY_CATEGORIES = {"preferences", "projects", "skills", "general"}
TASK_STATUSES = {
    "planned",
    "waiting_approval",
    "running",
    "paused",
    "succeeded",
    "failed",
}
TASK_STEP_STATUSES = {"pending", "running", "succeeded", "failed", "skipped"}
VISUAL_TASK_STATUSES = {
    "queued",
    "observing",
    "planning",
    "running",
    "paused",
    "waiting_approval",
    "needs_clarification",
    "succeeded",
    "failed",
    "cancelled",
    "stopped",
}
APPROVAL_STATUSES = {"pending", "approved", "denied"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def normalize_memory(content: str) -> str:
    """Normalize text for exact duplicate detection."""
    return " ".join(content.casefold().split())


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    id: int
    conversation_id: str
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    category: str
    content: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TaskRecord:
    id: str
    title: str
    status: str
    requires_approval: bool
    max_retries: int
    retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TaskStepRecord:
    id: int
    task_id: str
    position: int
    description: str
    status: str
    attempts: int


@dataclass(frozen=True)
class ApprovalRecord:
    id: int
    task_id: str
    status: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True)
class ToolApprovalRecord:
    id: str
    task_id: str | None
    step_id: int | None
    tool_name: str
    arguments_json: str
    affected_resources_json: str
    reason: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    decided_at: datetime | None
    consumed_at: datetime | None


@dataclass(frozen=True)
class ToolAuditRecord:
    id: int
    task_id: str | None
    step_id: int | None
    tool_name: str
    arguments_json: str
    status: str
    result_json: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime


class Database:
    """SQLite store with short-lived connections for local API use."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (
                        role IN ('system', 'user', 'assistant')
                    ),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
                    ON messages(conversation_id, id);

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL CHECK (
                        category IN ('preferences', 'projects', 'skills', 'general')
                    ),
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_category
                    ON memories(category);

                CREATE INDEX IF NOT EXISTS idx_memories_content
                    ON memories(content);

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('planned', 'waiting_approval', 'running',
                                   'paused', 'succeeded', 'failed')
                    ),
                    requires_approval INTEGER NOT NULL CHECK (
                        requires_approval IN (0, 1)
                    ),
                    max_retries INTEGER NOT NULL CHECK (max_retries >= 0),
                    retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')
                    ),
                    attempts INTEGER NOT NULL CHECK (attempts >= 0),
                    UNIQUE(task_id, position),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'approved', 'denied')
                    ),
                    note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status_updated
                    ON tasks(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_task_steps_task_position
                    ON task_steps(task_id, position);

                CREATE TABLE IF NOT EXISTS tool_approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    step_id INTEGER,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    affected_resources_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'approved', 'denied')
                    ),
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    decided_at TEXT,
                    consumed_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    step_id INTEGER,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS visual_tasks (
                    run_id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'queued', 'observing', 'planning', 'running', 'paused',
                        'waiting_approval', 'needs_clarification', 'succeeded',
                        'failed', 'cancelled', 'stopped'
                    )),
                    action_count INTEGER NOT NULL CHECK (action_count >= 0),
                    max_actions INTEGER NOT NULL CHECK (max_actions >= 1),
                    max_duration_seconds REAL NOT NULL CHECK (max_duration_seconds > 0),
                    consecutive_failures INTEGER NOT NULL CHECK (consecutive_failures >= 0),
                    max_consecutive_failures INTEGER NOT NULL CHECK (max_consecutive_failures >= 1),
                    current_action_json TEXT,
                    latest_observation_json TEXT,
                    latest_verification_json TEXT,
                    approval_id TEXT,
                    error TEXT,
                    recovery_required INTEGER NOT NULL DEFAULT 0 CHECK (recovery_required IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_visual_tasks_status_updated
                    ON visual_tasks(status, updated_at);

                CREATE TABLE IF NOT EXISTS visual_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    action_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    verification_json TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    UNIQUE(run_id, sequence),
                    FOREIGN KEY (run_id) REFERENCES visual_tasks(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_visual_actions_run_sequence
                    ON visual_actions(run_id, sequence);
                """
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = 'paused', updated_at = ?
                WHERE status = 'running'
                """,
                (iso_now(),),
            )
            connection.execute(
                """
                UPDATE visual_tasks
                SET status = 'paused',
                    recovery_required = 1,
                    error = COALESCE(error, 'Interrupted during restart; action outcome is unknown and requires review.'),
                    updated_at = ?
                WHERE status IN ('queued', 'observing', 'planning', 'running', 'waiting_approval')
                """,
                (iso_now(),),
            )

    # Conversations

    def create_conversation(self, title: str | None = None) -> ConversationRecord:
        conversation_id = str(uuid.uuid4())
        timestamp = iso_now()
        conversation_title = (
            title.strip() if title and title.strip() else "New conversation"
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, conversation_title, timestamp, timestamp),
            )
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation was not created")
        return conversation

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return self._conversation_from_row(row) if row else None

    def list_conversations(self, limit: int = 100) -> list[ConversationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
        return cursor.rowcount > 0

    def append_message(
        self, conversation_id: str, role: str, content: str
    ) -> MessageRecord:
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")

        timestamp = iso_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, timestamp),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
            message_id = int(cursor.lastrowid)

        return MessageRecord(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=datetime.fromisoformat(timestamp),
        )

    def list_messages(
        self, conversation_id: str, limit: int = 24
    ) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM (
                    SELECT id, conversation_id, role, content, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (conversation_id, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    # Long-term memories

    def add_memory(self, category: str, content: str) -> MemoryRecord:
        category = category.strip().lower()
        content = content.strip()

        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"Unsupported memory category: {category}")
        if not content:
            raise ValueError("Memory content cannot be empty")
        if len(content) > 2000:
            raise ValueError("Memory content cannot exceed 2000 characters")

        normalized = normalize_memory(content)
        timestamp = iso_now()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    category, content, normalized_content, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(normalized_content) DO NOTHING
                """,
                (category, content, normalized, timestamp, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, category, content, created_at, updated_at
                FROM memories WHERE normalized_content = ?
                """,
                (normalized,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Memory could not be saved")
        return self._memory_from_row(row)

    def list_memories(
        self, category: str | None = None, limit: int = 200
    ) -> list[MemoryRecord]:
        if category is not None and category not in MEMORY_CATEGORIES:
            raise ValueError(f"Unsupported memory category: {category}")

        with self._connect() as connection:
            if category:
                rows = connection.execute(
                    """
                    SELECT id, category, content, created_at, updated_at
                    FROM memories
                    WHERE category = ?
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (category, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, category, content, created_at, updated_at
                    FROM memories
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [self._memory_from_row(row) for row in rows]

    def search_memories(self, query: str, limit: int = 20) -> list[MemoryRecord]:
        terms = [term for term in query.strip().split() if term]
        if not terms:
            return []

        # Each term must occur in the memory content.
        conditions = " AND ".join("content LIKE ?" for _ in terms)
        parameters = [f"%{term}%" for term in terms]
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, category, content, created_at, updated_at
                FROM memories
                WHERE {conditions}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()

        return [self._memory_from_row(row) for row in rows]

    def update_memory(
        self,
        memory_id: int,
        content: str | None = None,
        category: str | None = None,
    ) -> MemoryRecord | None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()

            if existing is None:
                return None

            new_content = content.strip() if content is not None else existing["content"]
            new_category = (
                category.strip().lower()
                if category is not None
                else existing["category"]
            )

            if not new_content:
                raise ValueError("Memory content cannot be empty")
            if len(new_content) > 2000:
                raise ValueError("Memory content cannot exceed 2000 characters")
            if new_category not in MEMORY_CATEGORIES:
                raise ValueError(f"Unsupported memory category: {new_category}")

            connection.execute(
                """
                UPDATE memories
                SET content = ?, category = ?, normalized_content = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_content,
                    new_category,
                    normalize_memory(new_content),
                    iso_now(),
                    memory_id,
                ),
            )
            row = connection.execute(
                """
                SELECT id, category, content, created_at, updated_at
                FROM memories WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

        return self._memory_from_row(row) if row else None

    def delete_memory(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
        return cursor.rowcount > 0

    # Durable task plans and approvals

    def create_task(
        self,
        title: str,
        steps: list[str],
        max_retries: int = 2,
        requires_approval: bool = True,
    ) -> TaskRecord:
        title = title.strip()
        steps = [step.strip() for step in steps if step.strip()]
        if not title:
            raise ValueError("Task title cannot be empty")
        if not steps:
            raise ValueError("A task must contain at least one step")
        if len(steps) > 50:
            raise ValueError("A task cannot contain more than 50 steps")
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries must be between 0 and 5")

        task_id = str(uuid.uuid4())
        timestamp = iso_now()
        status = "waiting_approval" if requires_approval else "planned"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, title, status, requires_approval, max_retries,
                    retry_count, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    task_id,
                    title,
                    status,
                    int(requires_approval),
                    max_retries,
                    timestamp,
                    timestamp,
                ),
            )
            connection.executemany(
                """
                INSERT INTO task_steps (task_id, position, description, status, attempts)
                VALUES (?, ?, ?, 'pending', 0)
                """,
                [(task_id, position, step) for position, step in enumerate(steps)],
            )
            if requires_approval:
                connection.execute(
                    """
                    INSERT INTO task_approvals (
                        task_id, status, note, created_at, decided_at
                    ) VALUES (?, 'pending', NULL, ?, NULL)
                    """,
                    (task_id, timestamp),
                )
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("Task was not created")
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks(self, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_task_steps(self, task_id: str) -> list[TaskStepRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, position, description, status, attempts
                FROM task_steps WHERE task_id = ? ORDER BY position ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._task_step_from_row(row) for row in rows]

    def list_resumable_tasks(self, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM tasks
                WHERE status IN ('planned', 'paused', 'running')
                ORDER BY updated_at ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def decide_task_approval(
        self, task_id: str, approved: bool, note: str | None = None
    ) -> TaskRecord | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != "waiting_approval":
            raise ValueError("Only tasks waiting for approval can be decided")

        timestamp = iso_now()
        status = "approved" if approved else "denied"
        task_status = "planned" if approved else "failed"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_approvals
                SET status = ?, note = ?, decided_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                (status, note, timestamp, task_id),
            )
            connection.execute(
                """
                UPDATE tasks SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    task_status,
                    None if approved else (note or "Task approval denied"),
                    timestamp,
                    task_id,
                ),
            )
        return self.get_task(task_id)

    def get_task_approval_status(self, task_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status FROM task_approvals
                WHERE task_id = ? ORDER BY id DESC LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return str(row["status"]) if row else None

    def pause_task(self, task_id: str) -> TaskRecord | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status not in {"planned", "running"}:
            raise ValueError("Only planned or running tasks can be paused")
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = 'paused', updated_at = ? WHERE id = ?",
                (iso_now(), task_id),
            )
        return self.get_task(task_id)

    def resume_task(self, task_id: str) -> TaskRecord | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != "paused":
            raise ValueError("Only paused tasks can be resumed")
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = 'planned', updated_at = ? WHERE id = ?",
                (iso_now(), task_id),
            )
        return self.get_task(task_id)

    def start_task(self, task_id: str) -> TaskRecord | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != "planned":
            raise ValueError("Only planned tasks can start")
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (iso_now(), task_id),
            )
        return self.get_task(task_id)

    def record_task_failure(
        self, task_id: str, error: str
    ) -> TaskRecord | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != "running":
            raise ValueError("Only running tasks can record a failure")

        next_retry_count = task.retry_count + 1
        next_status = (
            "failed" if task.retry_count >= task.max_retries else "paused"
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, retry_count = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, next_retry_count, error[:2000], iso_now(), task_id),
            )
        return self.get_task(task_id)

    def set_task_status(
        self, task_id: str, status: str, last_error: str | None = None
    ) -> TaskRecord | None:
        if status not in TASK_STATUSES:
            raise ValueError(f"Unsupported task status: {status}")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, last_error, iso_now(), task_id),
            )
        return self.get_task(task_id)

    def update_task_step(
        self, step_id: int, status: str, attempts: int | None = None
    ) -> TaskStepRecord | None:
        if status not in TASK_STEP_STATUSES:
            raise ValueError(f"Unsupported task step status: {status}")
        with self._connect() as connection:
            if attempts is None:
                connection.execute(
                    "UPDATE task_steps SET status = ? WHERE id = ?",
                    (status, step_id),
                )
            else:
                connection.execute(
                    "UPDATE task_steps SET status = ?, attempts = ? WHERE id = ?",
                    (status, attempts, step_id),
                )
            row = connection.execute(
                "SELECT id, task_id, position, description, status, attempts "
                "FROM task_steps WHERE id = ?",
                (step_id,),
            ).fetchone()
        return self._task_step_from_row(row) if row else None

    # Visual computer-control task persistence

    def create_visual_task(
        self,
        run_id: str,
        task: str,
        *,
        max_actions: int,
        max_duration_seconds: float,
        max_consecutive_failures: int,
    ) -> dict[str, object]:
        timestamp = iso_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO visual_tasks (
                    run_id, task, status, action_count, max_actions,
                    max_duration_seconds, consecutive_failures,
                    max_consecutive_failures, created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, ?, ?, 0, ?, ?, ?)
                """,
                (
                    run_id,
                    task,
                    max_actions,
                    max_duration_seconds,
                    max_consecutive_failures,
                    timestamp,
                    timestamp,
                ),
            )
        result = self.get_visual_task(run_id)
        if result is None:
            raise RuntimeError("Visual task was not created")
        return result

    def get_visual_task(self, run_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM visual_tasks WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._visual_task_from_row(row) if row else None

    def list_visual_tasks(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM visual_tasks
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._visual_task_from_row(row) for row in rows]

    def update_visual_task(self, run_id: str, **fields: object) -> dict[str, object] | None:
        allowed = {
            "status",
            "action_count",
            "consecutive_failures",
            "current_action_json",
            "latest_observation_json",
            "latest_verification_json",
            "approval_id",
            "error",
            "recovery_required",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported visual task fields: {sorted(unknown)}")
        if "status" in fields and fields["status"] not in VISUAL_TASK_STATUSES:
            raise ValueError(f"Unsupported visual task status: {fields['status']}")
        if not fields:
            return self.get_visual_task(run_id)
        assignments = [f"{key} = ?" for key in fields]
        values = list(fields.values())
        assignments.append("updated_at = ?")
        values.append(iso_now())
        values.append(run_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE visual_tasks SET {', '.join(assignments)} WHERE run_id = ?",
                values,
            )
        return self.get_visual_task(run_id)

    def record_visual_action(
        self,
        run_id: str,
        sequence: int,
        action: dict[str, object],
        status: str,
        *,
        verification: dict[str, object] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO visual_actions (
                    run_id, sequence, action_json, status, verification_json,
                    error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    json.dumps(action, ensure_ascii=False, sort_keys=True),
                    status,
                    json.dumps(verification, ensure_ascii=False, sort_keys=True)
                    if verification is not None
                    else None,
                    error,
                    (started_at or utc_now()).isoformat(),
                    finished_at.isoformat() if finished_at else None,
                ),
            )
        return int(cursor.lastrowid)

    def list_visual_actions(self, run_id: str, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM visual_actions
                WHERE run_id = ? ORDER BY sequence ASC LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "run_id": str(row["run_id"]),
                "sequence": int(row["sequence"]),
                "action": json.loads(row["action_json"]),
                "status": str(row["status"]),
                "verification": json.loads(row["verification_json"])
                if row["verification_json"]
                else None,
                "error": row["error"],
                "started_at": datetime.fromisoformat(row["started_at"]),
                "finished_at": datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else None,
            }
            for row in rows
        ]

    @staticmethod
    def _visual_task_from_row(row: sqlite3.Row) -> dict[str, object]:
        def decode(name: str) -> object | None:
            return json.loads(row[name]) if row[name] else None

        return {
            "run_id": str(row["run_id"]),
            "task": str(row["task"]),
            "status": str(row["status"]),
            "action_count": int(row["action_count"]),
            "max_actions": int(row["max_actions"]),
            "max_duration_seconds": float(row["max_duration_seconds"]),
            "consecutive_failures": int(row["consecutive_failures"]),
            "max_consecutive_failures": int(row["max_consecutive_failures"]),
            "current_action": decode("current_action_json"),
            "latest_observation": decode("latest_observation_json"),
            "latest_verification": decode("latest_verification_json"),
            "approval_id": row["approval_id"],
            "error": row["error"],
            "recovery_required": bool(row["recovery_required"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }

    # Per-operation tool approvals and audit records

    def create_tool_approval(
        self,
        tool_name: str,
        arguments_json: str,
        affected_resources_json: str,
        reason: str,
        task_id: str | None = None,
        step_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> ToolApprovalRecord:
        approval_id = str(uuid.uuid4())
        timestamp = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_approvals (
                    id, task_id, step_id, tool_name, arguments_json,
                    affected_resources_json, reason, status, created_at,
                    expires_at, decided_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)
                """,
                (
                    approval_id,
                    task_id,
                    step_id,
                    tool_name,
                    arguments_json,
                    affected_resources_json,
                    reason,
                    timestamp.isoformat(),
                    expires_at.isoformat() if expires_at else None,
                ),
            )
        approval = self.get_tool_approval(approval_id)
        if approval is None:
            raise RuntimeError("Tool approval was not created")
        return approval

    def get_tool_approval(self, approval_id: str) -> ToolApprovalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tool_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        return self._tool_approval_from_row(row) if row else None

    def list_tool_approvals(
        self, status: str | None = None, limit: int = 100
    ) -> list[ToolApprovalRecord]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM tool_approvals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM tool_approvals
                    WHERE status = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._tool_approval_from_row(row) for row in rows]

    def decide_tool_approval(
        self, approval_id: str, approved: bool
    ) -> ToolApprovalRecord | None:
        approval = self.get_tool_approval(approval_id)
        if approval is None:
            return None
        if approval.status != "pending":
            raise ValueError("Only pending tool approvals can be decided")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tool_approvals SET status = ?, decided_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    "approved" if approved else "denied",
                    iso_now(),
                    approval_id,
                ),
            )
        return self.get_tool_approval(approval_id)

    def consume_tool_approval(self, approval_id: str) -> bool:
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tool_approvals
                SET consumed_at = ?
                WHERE id = ? AND status = 'approved' AND consumed_at IS NULL
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (now.isoformat(), approval_id, now.isoformat()),
            )
        return cursor.rowcount == 1

    def record_tool_audit(
        self,
        tool_name: str,
        arguments_json: str,
        status: str,
        result_json: str | None,
        error: str | None,
        started_at: datetime,
        finished_at: datetime,
        task_id: str | None = None,
        step_id: int | None = None,
    ) -> ToolAuditRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tool_audit (
                    task_id, step_id, tool_name, arguments_json, status,
                    result_json, error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_id,
                    tool_name,
                    arguments_json,
                    status,
                    result_json,
                    error,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                ),
            )
            audit_id = int(cursor.lastrowid)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tool_audit WHERE id = ?", (audit_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Tool audit record was not saved")
        return self._tool_audit_from_row(row)

    def list_tool_audits(self, limit: int = 100) -> list[ToolAuditRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM tool_audit
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._tool_audit_from_row(row) for row in rows]

    def list_task_approvals(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, status, note, created_at, decided_at
                FROM task_approvals
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "task_id": str(row["task_id"]),
                "status": str(row["status"]),
                "note": row["note"],
                "created_at": datetime.fromisoformat(row["created_at"]),
                "decided_at": (
                    datetime.fromisoformat(row["decided_at"])
                    if row["decided_at"]
                    else None
                ),
            }
            for row in rows
        ]

    # Database helpers

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _conversation_from_row(row: sqlite3.Row) -> ConversationRecord:
        return ConversationRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=int(row["id"]),
            conversation_id=str(row["conversation_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            category=str(row["category"]),
            content=str(row["content"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            status=str(row["status"]),
            requires_approval=bool(row["requires_approval"]),
            max_retries=int(row["max_retries"]),
            retry_count=int(row["retry_count"]),
            last_error=str(row["last_error"]) if row["last_error"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _task_step_from_row(row: sqlite3.Row) -> TaskStepRecord:
        return TaskStepRecord(
            id=int(row["id"]),
            task_id=str(row["task_id"]),
            position=int(row["position"]),
            description=str(row["description"]),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
        )

    @staticmethod
    def _tool_approval_from_row(row: sqlite3.Row) -> ToolApprovalRecord:
        return ToolApprovalRecord(
            id=str(row["id"]),
            task_id=str(row["task_id"]) if row["task_id"] else None,
            step_id=int(row["step_id"]) if row["step_id"] is not None else None,
            tool_name=str(row["tool_name"]),
            arguments_json=str(row["arguments_json"]),
            affected_resources_json=str(row["affected_resources_json"]),
            reason=str(row["reason"]),
            status=str(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=(
                datetime.fromisoformat(row["expires_at"])
                if row["expires_at"]
                else None
            ),
            decided_at=(
                datetime.fromisoformat(row["decided_at"])
                if row["decided_at"]
                else None
            ),
            consumed_at=(
                datetime.fromisoformat(row["consumed_at"])
                if row["consumed_at"]
                else None
            ),
        )

    @staticmethod
    def _tool_audit_from_row(row: sqlite3.Row) -> ToolAuditRecord:
        return ToolAuditRecord(
            id=int(row["id"]),
            task_id=str(row["task_id"]) if row["task_id"] else None,
            step_id=int(row["step_id"]) if row["step_id"] is not None else None,
            tool_name=str(row["tool_name"]),
            arguments_json=str(row["arguments_json"]),
            status=str(row["status"]),
            result_json=row["result_json"],
            error=row["error"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
        )
