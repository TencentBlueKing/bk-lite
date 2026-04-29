import json
import sqlite3
from pathlib import Path
from typing import Any


TERMINAL_TASK_STATUSES = {"success", "failed", "callback_failed"}


class TaskStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_state (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    callback_json TEXT,
                    result_json TEXT,
                    execution_status TEXT NOT NULL DEFAULT 'queued',
                    callback_status TEXT NOT NULL DEFAULT 'none',
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    heartbeat_at TEXT,
                    execution_attempt INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(task_state)")}
            migrations = {
                "execution_status": "ALTER TABLE task_state ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'queued'",
                "callback_status": "ALTER TABLE task_state ADD COLUMN callback_status TEXT NOT NULL DEFAULT 'none'",
                "lease_owner": "ALTER TABLE task_state ADD COLUMN lease_owner TEXT",
                "lease_expires_at": "ALTER TABLE task_state ADD COLUMN lease_expires_at TEXT",
                "heartbeat_at": "ALTER TABLE task_state ADD COLUMN heartbeat_at TEXT",
                "execution_attempt": "ALTER TABLE task_state ADD COLUMN execution_attempt INTEGER NOT NULL DEFAULT 0",
            }
            for column, sql in migrations.items():
                if column not in columns:
                    conn.execute(sql)

    def create_if_absent(
        self,
        task_id: str,
        status: str,
        payload: dict[str, Any],
        callback: dict[str, Any] | None,
        now_iso: str,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT task_id FROM task_state WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return False

            conn.execute(
                """
                INSERT INTO task_state(
                    task_id,
                    status,
                    payload_json,
                    callback_json,
                    result_json,
                    execution_status,
                    callback_status,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(callback or {}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    status,
                    "pending" if callback else "none",
                    now_iso,
                    now_iso,
                ),
            )
            return True

    def claim_task(self, task_id: str, owner_id: str, lease_expires_at: str, now_iso: str) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT status, execution_status, callback_status, lease_owner, lease_expires_at, execution_attempt
                FROM task_state
                WHERE task_id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"claimed": False, "reason": "missing"}

            status, execution_status, callback_status, lease_owner, lease_expires_at_db, execution_attempt = row
            if status in TERMINAL_TASK_STATUSES or execution_status in TERMINAL_TASK_STATUSES:
                return {
                    "claimed": False,
                    "reason": "terminal",
                    "status": status,
                    "execution_status": execution_status,
                    "callback_status": callback_status,
                }
            if execution_status == "running" and lease_owner and lease_expires_at_db and lease_expires_at_db > now_iso and lease_owner != owner_id:
                return {
                    "claimed": False,
                    "reason": "leased",
                    "status": status,
                    "execution_status": execution_status,
                    "callback_status": callback_status,
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_expires_at_db,
                }

            next_attempt = int(execution_attempt or 0) + 1
            conn.execute(
                """
                UPDATE task_state
                SET status = ?,
                    execution_status = ?,
                    lease_owner = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    execution_attempt = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    "running",
                    "running",
                    owner_id,
                    lease_expires_at,
                    now_iso,
                    next_attempt,
                    now_iso,
                    task_id,
                ),
            )
            return {
                "claimed": True,
                "status": "running",
                "execution_status": "running",
                "callback_status": callback_status,
                "execution_attempt": next_attempt,
                "lease_owner": owner_id,
                "lease_expires_at": lease_expires_at,
                "claimed_at": now_iso,
            }

    def renew_lease(self, task_id: str, owner_id: str, lease_expires_at: str, now_iso: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE task_state
                SET lease_expires_at = ?, heartbeat_at = ?, updated_at = ?
                WHERE task_id = ? AND lease_owner = ? AND execution_status = 'running'
                """,
                (lease_expires_at, now_iso, now_iso, task_id, owner_id),
            )
            return cursor.rowcount > 0

    def update_execution_result(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None,
        now_iso: str,
        owner_id: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            sql = """
                UPDATE task_state
                SET status = ?,
                    execution_status = ?,
                    result_json = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE task_id = ?
            """
            params: list[Any] = [
                status,
                status,
                json.dumps(result or {}, ensure_ascii=False),
                now_iso,
                now_iso,
                task_id,
            ]
            if owner_id is not None:
                sql += " AND lease_owner = ?"
                params.append(owner_id)
            cursor = conn.execute(
                sql,
                params,
            )
            return cursor.rowcount > 0

    def update_callback_status(
        self,
        task_id: str,
        callback_status: str,
        result: dict[str, Any] | None,
        now_iso: str,
        preserve_status: str | None = None,
    ):
        with self._connect() as conn:
            current = conn.execute(
                "SELECT status, execution_status FROM task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not current:
                return
            current_status, execution_status = current
            next_status = preserve_status or current_status
            if callback_status == "failed" and current_status == "success":
                next_status = "callback_failed"
            elif current_status == "callback_failed" and callback_status == "sent":
                next_status = execution_status or preserve_status or current_status
            conn.execute(
                """
                UPDATE task_state
                SET status = ?, callback_status = ?, result_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    next_status,
                    callback_status,
                    json.dumps(result or {}, ensure_ascii=False),
                    now_iso,
                    task_id,
                ),
            )

    def get_status(self, task_id: str) -> str | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT status FROM task_state WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return row[0]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT task_id, status, payload_json, callback_json, result_json,
                       execution_status, callback_status, lease_owner, lease_expires_at,
                       heartbeat_at, execution_attempt, created_at, updated_at
                FROM task_state
                WHERE task_id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return {
                "task_id": row[0],
                "status": row[1],
                "payload": json.loads(row[2] or "{}"),
                "callback": json.loads(row[3] or "{}"),
                "result": json.loads(row[4] or "{}"),
                "execution_status": row[5],
                "callback_status": row[6],
                "lease_owner": row[7],
                "lease_expires_at": row[8],
                "heartbeat_at": row[9],
                "execution_attempt": row[10],
                "created_at": row[11],
                "updated_at": row[12],
            }
