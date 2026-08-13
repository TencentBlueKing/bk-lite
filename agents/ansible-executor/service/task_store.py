import base64
import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from service.task_store_sanitization import (
    SENSITIVE_CREDENTIAL_KEYS as _SENSITIVE_CREDENTIAL_KEYS,
    _sanitize_callback_for_storage,
    _sanitize_execution_payload_for_storage,
    _sanitize_payload_for_storage,
)

TERMINAL_TASK_STATUSES = {"success", "failed", "callback_failed"}
SENSITIVE_CREDENTIAL_KEYS = _SENSITIVE_CREDENTIAL_KEYS


class TaskStore:
    EXECUTION_PAYLOAD_PREFIX = "fernet:v1:"
    LOCAL_KEY_SUFFIX = ".payload.key"

    def __init__(self, db_path: str, encryption_secret: str | None = None):
        self.db_path = db_path
        secret = encryption_secret or os.getenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", "")
        if not secret:
            secret = self._load_or_create_local_encryption_secret()
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._payload_cipher = Fernet(key)
        self._ensure_schema()

    def _load_or_create_local_encryption_secret(self) -> str:
        if self.db_path == ":memory:":
            return secrets.token_urlsafe(48)

        key_path = Path(f"{self.db_path}{self.LOCAL_KEY_SUFFIX}")
        lock_path = Path(f"{key_path}.lock")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                existing_secret = key_path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                existing_secret = ""
            if existing_secret:
                os.chmod(key_path, 0o600)
                return existing_secret
            if key_path.exists():
                try:
                    key_path.unlink()
                except FileNotFoundError:
                    pass

            secret = secrets.token_urlsafe(48)
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{key_path.name}.",
                dir=key_path.parent,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as key_file:
                    key_file.write(secret)
                    key_file.flush()
                    os.fsync(key_file.fileno())
                os.replace(temporary_path, key_path)
                os.chmod(key_path, 0o600)
                directory_descriptor = os.open(key_path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
                return secret
            finally:
                Path(temporary_path).unlink(missing_ok=True)

    def _encrypt_execution_payload(self, payload: dict[str, Any]) -> str:
        plaintext = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        return self.EXECUTION_PAYLOAD_PREFIX + self._payload_cipher.encrypt(plaintext).decode("ascii")

    def _decrypt_execution_payload(self, value: str) -> dict[str, Any]:
        if not value.startswith(self.EXECUTION_PAYLOAD_PREFIX):
            return json.loads(value)
        encrypted = value.removeprefix(self.EXECUTION_PAYLOAD_PREFIX).encode("ascii")
        try:
            plaintext = self._payload_cipher.decrypt(encrypted)
        except InvalidToken as exc:
            raise ValueError("task execution payload cannot be decrypted with the configured key") from exc
        return json.loads(plaintext.decode("utf-8"))

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA secure_delete = ON")
        return connection

    def _ensure_schema(self):
        db_parent = Path(self.db_path).parent
        db_parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_state (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    execution_payload_json TEXT,
                    callback_json TEXT,
                    callback_secret_json TEXT,
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
                "execution_payload_json": "ALTER TABLE task_state ADD COLUMN execution_payload_json TEXT",
                "callback_secret_json": "ALTER TABLE task_state ADD COLUMN callback_secret_json TEXT",
                "lease_owner": "ALTER TABLE task_state ADD COLUMN lease_owner TEXT",
                "lease_expires_at": "ALTER TABLE task_state ADD COLUMN lease_expires_at TEXT",
                "heartbeat_at": "ALTER TABLE task_state ADD COLUMN heartbeat_at TEXT",
                "execution_attempt": "ALTER TABLE task_state ADD COLUMN execution_attempt INTEGER NOT NULL DEFAULT 0",
            }
            for column, sql in migrations.items():
                if column not in columns:
                    conn.execute(sql)
            self._cleanup_terminal_execution_payloads(conn)
        os.chmod(self.db_path, 0o600)

    @staticmethod
    def _cleanup_terminal_execution_payloads(conn: sqlite3.Connection) -> None:
        """Run the security-critical legacy cleanup atomically during startup.

        A SQLite error aborts and rolls back initialization. Operators can fix the
        database lock/filesystem problem and restart; continuing would retain
        plaintext terminal credentials behind a healthy service.
        """
        terminal_statuses = tuple(sorted(TERMINAL_TASK_STATUSES))
        status_placeholders = ", ".join("?" for _ in terminal_statuses)
        conn.execute(
            f"""
            UPDATE task_state
            SET execution_payload_json = NULL
            WHERE execution_payload_json IS NOT NULL
              AND (
                  status IN ({status_placeholders})
                  OR execution_status IN ({status_placeholders})
              )
            """,
            (*terminal_statuses, *terminal_statuses),
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
                INSERT INTO task_state(
                    task_id,
                    status,
                    payload_json,
                    execution_payload_json,
                    callback_json,
                    callback_secret_json,
                    result_json,
                    execution_status,
                    callback_status,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    status,
                    json.dumps(_sanitize_payload_for_storage(payload), ensure_ascii=False),
                    self._encrypt_execution_payload(_sanitize_execution_payload_for_storage(payload or {})),
                    json.dumps(_sanitize_callback_for_storage(callback), ensure_ascii=False),
                    self._encrypt_execution_payload(callback) if callback else None,
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
            terminal_statuses = tuple(sorted(TERMINAL_TASK_STATUSES))
            status_placeholders = ", ".join("?" for _ in terminal_statuses)
            cursor = conn.execute(
                f"""
                UPDATE task_state
                SET status = 'running',
                    execution_status = 'running',
                    lease_owner = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    execution_attempt = COALESCE(execution_attempt, 0) + 1,
                    updated_at = ?
                WHERE task_id = ?
                  AND status NOT IN ({status_placeholders})
                  AND execution_status NOT IN ({status_placeholders})
                  AND (
                      execution_status != 'running'
                      OR lease_owner IS NULL
                      OR lease_expires_at IS NULL
                      OR lease_expires_at <= ?
                      OR lease_owner = ?
                  )
                """,
                (
                    owner_id,
                    lease_expires_at,
                    now_iso,
                    now_iso,
                    task_id,
                    *terminal_statuses,
                    *terminal_statuses,
                    now_iso,
                    owner_id,
                ),
            )
            row = conn.execute(
                """
                SELECT status, execution_status, callback_status, lease_owner, lease_expires_at, execution_attempt
                FROM task_state
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if not row:
                return {"claimed": False, "reason": "missing"}

            status, execution_status, callback_status, lease_owner, lease_expires_at_db, execution_attempt = row
            if cursor.rowcount > 0:
                return {
                    "claimed": True,
                    "status": status,
                    "execution_status": execution_status,
                    "callback_status": callback_status,
                    "execution_attempt": int(execution_attempt or 0),
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_expires_at_db,
                    "claimed_at": now_iso,
                }
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
            return {"claimed": False, "reason": "state_changed"}

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
                    execution_payload_json = NULL,
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
    ) -> bool:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT status, execution_status FROM task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not current:
                return False
            current_status, execution_status = current
            next_status = preserve_status or current_status
            if callback_status == "failed" and current_status == "success":
                next_status = "callback_failed"
            elif current_status == "callback_failed" and callback_status == "sent":
                next_status = execution_status or preserve_status or current_status
            cursor = conn.execute(
                """
                UPDATE task_state
                SET status = ?,
                    callback_status = ?,
                    result_json = ?,
                    callback_secret_json = CASE WHEN ? = 'sent' THEN NULL ELSE callback_secret_json END,
                    updated_at = ?
                WHERE task_id = ?
                  AND (? != 'failed' OR callback_status != 'sent')
                """,
                (
                    next_status,
                    callback_status,
                    json.dumps(result or {}, ensure_ascii=False),
                    callback_status,
                    now_iso,
                    task_id,
                    callback_status,
                ),
            )
            return cursor.rowcount > 0

    def get_callback_config(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT callback_secret_json FROM task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not row or not row[0]:
                return None
            return self._decrypt_execution_payload(row[0])

    def clear_callback_config(self, task_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE task_state SET callback_secret_json = NULL WHERE task_id = ?",
                (task_id,),
            )

    def clear_execution_payload(self, task_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE task_state SET execution_payload_json = NULL WHERE task_id = ?",
                (task_id,),
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

    def get_execution_payload(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT execution_payload_json
                FROM task_state
                WHERE task_id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return None
            payload = self._decrypt_execution_payload(row[0])
            sanitized_payload = _sanitize_execution_payload_for_storage(payload)
            if (
                sanitized_payload != payload
                or not row[0].startswith(self.EXECUTION_PAYLOAD_PREFIX)
            ):
                conn.execute(
                    "UPDATE task_state SET execution_payload_json = ? WHERE task_id = ?",
                    (self._encrypt_execution_payload(sanitized_payload), task_id),
                )
            return sanitized_payload
