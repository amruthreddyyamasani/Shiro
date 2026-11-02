"""Explicit approval records for web actions and self-improvement proposals."""

from __future__ import annotations

import json
import difflib
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class WebActionRecord:
    id: str
    method: str
    url: str
    reason: str
    request_body: str | None
    status: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True)
class ChangeRequestRecord:
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


@dataclass(frozen=True)
class ChangeStagingRecord:
    request_id: str
    staging_path: Path
    diff: str
    test_status: str
    test_output: str | None
    applied_files: list[str]
    applied_at: datetime | None


class WorkflowStore:
    """Persist approval-gated requests without executing them."""

    def __init__(self, database: Database):
        self.database = database

    def initialize(self) -> None:
        with self.database._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_actions (
                    id TEXT PRIMARY KEY,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    request_body TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'approved', 'denied')
                    ),
                    note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE TABLE IF NOT EXISTS change_requests (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    files_json TEXT NOT NULL,
                    test_command TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('proposed', 'approved', 'rejected')
                    ),
                    note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE TABLE IF NOT EXISTS change_staging (
                    request_id TEXT PRIMARY KEY,
                    staging_path TEXT NOT NULL,
                    diff_text TEXT NOT NULL,
                    test_status TEXT NOT NULL,
                    test_output TEXT,
                    applied_files_json TEXT NOT NULL,
                    applied_at TEXT,
                    FOREIGN KEY (request_id) REFERENCES change_requests(id)
                        ON DELETE CASCADE
                );
                """
            )

    def create_web_action(
        self,
        method: str,
        url: str,
        reason: str,
        request_body: str | None = None,
    ) -> WebActionRecord:
        action_id = str(uuid.uuid4())
        timestamp = _now()
        with self.database._connect() as connection:
            connection.execute(
                """
                INSERT INTO web_actions (
                    id, method, url, reason, request_body, status, note,
                    created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)
                """,
                (action_id, method, url, reason, request_body, timestamp),
            )
        action = self.get_web_action(action_id)
        if action is None:
            raise RuntimeError("Web action was not created")
        return action

    def get_web_action(self, action_id: str) -> WebActionRecord | None:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT * FROM web_actions WHERE id = ?", (action_id,)
            ).fetchone()
        return self._web_action_from_row(row) if row else None

    def list_web_actions(self, limit: int = 100) -> list[WebActionRecord]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM web_actions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._web_action_from_row(row) for row in rows]

    def decide_web_action(
        self, action_id: str, approved: bool, note: str | None = None
    ) -> WebActionRecord | None:
        action = self.get_web_action(action_id)
        if action is None:
            return None
        if action.status != "pending":
            raise ValueError("Only pending web actions can be decided")
        timestamp = _now()
        with self.database._connect() as connection:
            connection.execute(
                """
                UPDATE web_actions
                SET status = ?, note = ?, decided_at = ? WHERE id = ?
                """,
                ("approved" if approved else "denied", note, timestamp, action_id),
            )
        return self.get_web_action(action_id)

    def create_change_request(
        self,
        title: str,
        description: str,
        files: list[str],
        test_command: str,
        project_root: Path | None = None,
        proposed_files: dict[str, str] | None = None,
    ) -> ChangeRequestRecord:
        proposed_files = proposed_files or {}
        if set(proposed_files) - set(files):
            raise ValueError("Proposed file contents must be listed in files")
        for relative_path, content in proposed_files.items():
            self._validate_relative_path(relative_path)
            if len(content.encode("utf-8")) > 1_000_000:
                raise ValueError("Each proposed file is limited to 1 MB")
        request_id = str(uuid.uuid4())
        timestamp = _now()
        with self.database._connect() as connection:
            connection.execute(
                """
                INSERT INTO change_requests (
                    id, title, description, files_json, test_command, status,
                    note, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, 'proposed', NULL, ?, NULL)
                """,
                (
                    request_id,
                    title.strip(),
                    description.strip(),
                    json.dumps(files),
                    test_command.strip(),
                    timestamp,
                ),
            )
        request = self.get_change_request(request_id)
        if request is None:
            raise RuntimeError("Change request was not created")
        if proposed_files:
            self._prepare_staging(
                request_id,
                project_root or Path.cwd(),
                proposed_files,
            )
        return self.get_change_request(request_id)  # type: ignore[return-value]

    def get_change_request(self, request_id: str) -> ChangeRequestRecord | None:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT * FROM change_requests WHERE id = ?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        record = self._change_request_from_row(row)
        staging = self.get_change_staging(request_id)
        if staging is None:
            return record
        return replace(
            record,
            diff=staging.diff,
            test_status=staging.test_status,
            test_output=staging.test_output,
            applied_at=staging.applied_at,
        )

    def list_change_requests(self, limit: int = 100) -> list[ChangeRequestRecord]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM change_requests ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            self.get_change_request(str(row["id"]))  # type: ignore[misc]
            for row in rows
        ]

    def get_change_staging(self, request_id: str) -> ChangeStagingRecord | None:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT * FROM change_staging WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return ChangeStagingRecord(
            request_id=str(row["request_id"]),
            staging_path=Path(row["staging_path"]),
            diff=str(row["diff_text"]),
            test_status=str(row["test_status"]),
            test_output=row["test_output"],
            applied_files=list(json.loads(row["applied_files_json"])),
            applied_at=(
                datetime.fromisoformat(row["applied_at"])
                if row["applied_at"]
                else None
            ),
        )

    def run_change_tests(self, request_id: str, project_root: Path) -> ChangeStagingRecord:
        request = self.get_change_request(request_id)
        staging = self.get_change_staging(request_id)
        if request is None or staging is None:
            raise ValueError("Staged change request not found")
        if request.status != "approved":
            raise ValueError("Change request must be approved before tests run")

        with tempfile.TemporaryDirectory(prefix="shiro-review-") as temporary:
            review_root = Path(temporary) / "project"
            shutil.copytree(
                project_root,
                review_root,
                ignore=shutil.ignore_patterns(
                    ".venv", ".pytest_cache", "__pycache__", "data", "*.db"
                ),
            )
            for relative_path in staging.applied_files:
                source = staging.staging_path / relative_path
                target = review_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q"],
                    cwd=review_root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                status = "passed" if completed.returncode == 0 else "failed"
                output = (completed.stdout + "\n" + completed.stderr)[-20_000:]
            except subprocess.TimeoutExpired as exc:
                status = "timed_out"
                output = str(exc)[-20_000:]

        with self.database._connect() as connection:
            connection.execute(
                "UPDATE change_staging SET test_status = ?, test_output = ? WHERE request_id = ?",
                (status, output, request_id),
            )
        return self.get_change_staging(request_id)  # type: ignore[return-value]

    def apply_change_request(self, request_id: str, project_root: Path) -> ChangeStagingRecord:
        request = self.get_change_request(request_id)
        staging = self.get_change_staging(request_id)
        if request is None or staging is None:
            raise ValueError("Staged change request not found")
        if request.status != "approved":
            raise ValueError("Change request must be approved before applying")
        if staging.test_status != "passed":
            raise ValueError("Staged tests must pass before applying changes")

        backup_root = staging.staging_path / "backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        for relative_path in staging.applied_files:
            target = project_root / relative_path
            staged = staging.staging_path / relative_path
            if target.exists():
                backup = backup_root / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged, target)
        applied_at = _now()
        with self.database._connect() as connection:
            connection.execute(
                "UPDATE change_staging SET applied_at = ? WHERE request_id = ?",
                (applied_at, request_id),
            )
        return self.get_change_staging(request_id)  # type: ignore[return-value]

    def rollback_change_request(self, request_id: str, project_root: Path) -> ChangeStagingRecord:
        staging = self.get_change_staging(request_id)
        if staging is None or staging.applied_at is None:
            raise ValueError("No applied staged change is available to roll back")
        backup_root = staging.staging_path / "backup"
        for relative_path in staging.applied_files:
            target = project_root / relative_path
            backup = backup_root / relative_path
            if backup.exists():
                shutil.copy2(backup, target)
            elif target.exists():
                target.unlink()
        with self.database._connect() as connection:
            connection.execute(
                "UPDATE change_staging SET applied_at = NULL WHERE request_id = ?",
                (request_id,),
            )
        return self.get_change_staging(request_id)  # type: ignore[return-value]

    def decide_change_request(
        self, request_id: str, approved: bool, note: str | None = None
    ) -> ChangeRequestRecord | None:
        request = self.get_change_request(request_id)
        if request is None:
            return None
        if request.status != "proposed":
            raise ValueError("Only proposed change requests can be decided")
        timestamp = _now()
        with self.database._connect() as connection:
            connection.execute(
                """
                UPDATE change_requests
                SET status = ?, note = ?, decided_at = ? WHERE id = ?
                """,
                ("approved" if approved else "rejected", note, timestamp, request_id),
            )
        return self.get_change_request(request_id)

    @staticmethod
    def _web_action_from_row(row) -> WebActionRecord:
        return WebActionRecord(
            id=str(row["id"]),
            method=str(row["method"]),
            url=str(row["url"]),
            reason=str(row["reason"]),
            request_body=row["request_body"],
            status=str(row["status"]),
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=(
                datetime.fromisoformat(row["decided_at"])
                if row["decided_at"]
                else None
            ),
        )

    @staticmethod
    def _change_request_from_row(row) -> ChangeRequestRecord:
        return ChangeRequestRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            files=list(json.loads(row["files_json"])),
            test_command=str(row["test_command"]),
            status=str(row["status"]),
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=(
                datetime.fromisoformat(row["decided_at"])
                if row["decided_at"]
                else None
            ),
        )

    def _prepare_staging(
        self,
        request_id: str,
        project_root: Path,
        proposed_files: dict[str, str],
    ) -> None:
        project_root = project_root.resolve()
        staging_path = Path(self.database.path).parent / "change-staging" / request_id
        staging_path.mkdir(parents=True, exist_ok=True)
        diff_parts: list[str] = []
        for relative_path, content in proposed_files.items():
            self._validate_relative_path(relative_path)
            target = project_root / relative_path
            staged = staging_path / relative_path
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(content, encoding="utf-8", newline="")
            before = target.read_text(encoding="utf-8") if target.is_file() else ""
            diff_parts.extend(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=str(target),
                    tofile=str(target) + " (proposed)",
                )
            )
        with self.database._connect() as connection:
            connection.execute(
                """
                INSERT INTO change_staging (
                    request_id, staging_path, diff_text, test_status,
                    test_output, applied_files_json, applied_at
                ) VALUES (?, ?, ?, 'not_run', NULL, ?, NULL)
                """,
                (
                    request_id,
                    str(staging_path),
                    "".join(diff_parts),
                    json.dumps(sorted(proposed_files)),
                ),
            )

    @staticmethod
    def _validate_relative_path(relative_path: str) -> None:
        path = Path(relative_path)
        if (
            path.is_absolute()
            or bool(path.drive)
            or ".." in path.parts
            or not relative_path.strip()
        ):
            raise ValueError("Self-improvement files must be safe relative paths")
