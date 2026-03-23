import json
import sqlite3
from pathlib import Path
from typing import Any


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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

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
                INSERT INTO task_state(task_id, status, payload_json, callback_json, result_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(callback or {}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    now_iso,
                    now_iso,
                ),
            )
            return True

    def update_status(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None,
        now_iso: str,
    ):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE task_state
                SET status = ?, result_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    status,
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
                SELECT task_id, status, payload_json, callback_json, result_json, created_at, updated_at
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
                "created_at": row[5],
                "updated_at": row[6],
            }
