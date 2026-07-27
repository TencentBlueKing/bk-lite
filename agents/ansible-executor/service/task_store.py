import base64
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

TERMINAL_TASK_STATUSES = {"success", "failed", "callback_failed"}

# Sensitive credential keys that must be removed from stored payloads
# to prevent credential leakage via task_query API
SENSITIVE_CREDENTIAL_KEYS = {
    "password",
    "private_key_content",
    "private_key_passphrase",
    "ansible_password",
    "ansible_ssh_passphrase",
    "ansible_become_password",
    "inventory_content",
}

SENSITIVE_EXTRA_VAR_MARKERS = (
    "password",
    "passphrase",
    "private_key",
    "secret",
    "session_url",
    "token",
)


def _sanitize_extra_vars(extra_vars: dict[str, Any]) -> dict[str, Any]:
    return {key: "***" if any(marker in str(key).lower() for marker in SENSITIVE_EXTRA_VAR_MARKERS) else value for key, value in extra_vars.items()}


def _sanitize_payload_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Remove sensitive credential fields from payload before storage.

    This prevents credential leakage via task_query API responses.
    The executor only needs credentials during execution, not for status queries.

    Args:
        payload: Original task payload that may contain sensitive credentials

    Returns:
        Sanitized payload with sensitive fields removed and _redacted marker added
    """
    if not payload:
        return payload

    sanitized = dict(payload)

    # Sanitize host_credentials array
    if "host_credentials" in sanitized and isinstance(sanitized["host_credentials"], list):
        sanitized_creds = []
        for cred in sanitized["host_credentials"]:
            if not isinstance(cred, dict):
                continue
            # Keep only non-sensitive fields
            sanitized_cred = {k: v for k, v in cred.items() if k not in SENSITIVE_CREDENTIAL_KEYS}
            # Add marker indicating credentials were redacted
            sanitized_cred["_redacted"] = True
            sanitized_creds.append(sanitized_cred)
        sanitized["host_credentials"] = sanitized_creds

    # Remove top-level sensitive fields
    for key in SENSITIVE_CREDENTIAL_KEYS:
        sanitized.pop(key, None)

    if isinstance(sanitized.get("extra_vars"), dict):
        sanitized["extra_vars"] = _sanitize_extra_vars(sanitized["extra_vars"])

    return sanitized


class TaskStore:
    EXECUTION_PAYLOAD_PREFIX = "fernet:v1:"

    def __init__(self, db_path: str, encryption_secret: str | None = None):
        self.db_path = db_path
        secret = encryption_secret or os.getenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", "")
        if not secret:
            raise ValueError("ANSIBLE_PAYLOAD_ENCRYPTION_KEY is required to protect task execution payloads")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._payload_cipher = Fernet(key)
        self._ensure_schema()

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
        return sqlite3.connect(self.db_path)

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
                "lease_owner": "ALTER TABLE task_state ADD COLUMN lease_owner TEXT",
                "lease_expires_at": "ALTER TABLE task_state ADD COLUMN lease_expires_at TEXT",
                "heartbeat_at": "ALTER TABLE task_state ADD COLUMN heartbeat_at TEXT",
                "execution_attempt": "ALTER TABLE task_state ADD COLUMN execution_attempt INTEGER NOT NULL DEFAULT 0",
            }
            for column, sql in migrations.items():
                if column not in columns:
                    conn.execute(sql)
        os.chmod(self.db_path, 0o600)

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
                    result_json,
                    execution_status,
                    callback_status,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    status,
                    json.dumps(_sanitize_payload_for_storage(payload), ensure_ascii=False),
                    self._encrypt_execution_payload(payload or {}),
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
            if not row[0].startswith(self.EXECUTION_PAYLOAD_PREFIX):
                conn.execute(
                    "UPDATE task_state SET execution_payload_json = ? WHERE task_id = ?",
                    (self._encrypt_execution_payload(payload), task_id),
                )
            return payload
