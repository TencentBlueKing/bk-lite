import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from service.task_store import SENSITIVE_CREDENTIAL_KEYS, TaskStore, _sanitize_payload_for_storage


@pytest.fixture(autouse=True)
def payload_encryption_key(monkeypatch):
    monkeypatch.setenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", "unit-test-payload-encryption-key")


def test_claim_task_blocks_active_lease(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent("task-1", "queued", {"task_id": "task-1"}, {}, "2026-04-23T00:00:00+00:00")

    first_claim = store.claim_task(
        "task-1",
        "worker-a",
        "2026-04-23T00:00:10+00:00",
        "2026-04-23T00:00:00+00:00",
    )
    assert first_claim["claimed"] is True

    second_claim = store.claim_task(
        "task-1",
        "worker-b",
        "2026-04-23T00:00:11+00:00",
        "2026-04-23T00:00:01+00:00",
    )
    assert second_claim == {
        "claimed": False,
        "reason": "leased",
        "status": "running",
        "execution_status": "running",
        "callback_status": "none",
        "lease_owner": "worker-a",
        "lease_expires_at": "2026-04-23T00:00:10+00:00",
    }


def test_claim_task_can_take_over_stale_lease(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent("task-2", "queued", {"task_id": "task-2"}, {}, "2026-04-23T00:00:00+00:00")
    store.claim_task("task-2", "worker-a", "2026-04-23T00:00:02+00:00", "2026-04-23T00:00:00+00:00")

    takeover = store.claim_task(
        "task-2",
        "worker-b",
        "2026-04-23T00:00:20+00:00",
        "2026-04-23T00:00:05+00:00",
    )
    task = store.get_task("task-2")

    assert takeover["claimed"] is True
    assert takeover["execution_attempt"] == 2
    assert task["lease_owner"] == "worker-b"
    assert task["execution_attempt"] == 2


def test_claim_task_concurrently_allows_only_one_worker(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent("task-race", "queued", {"task_id": "task-race"}, {}, "2026-04-23T00:00:00+00:00")

    def claim(owner_id):
        return store.claim_task(
            "task-race",
            owner_id,
            "2026-04-23T00:00:10+00:00",
            "2026-04-23T00:00:01+00:00",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))

    assert sum(result["claimed"] for result in claims) == 1
    rejected = next(result for result in claims if not result["claimed"])
    assert rejected["reason"] == "leased"
    assert store.get_task("task-race")["execution_attempt"] == 1


def test_callback_status_preserves_execution_result(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent("task-3", "queued", {"task_id": "task-3"}, {"subject": "x"}, "2026-04-23T00:00:00+00:00")
    store.claim_task("task-3", "worker-a", "2026-04-23T00:00:10+00:00", "2026-04-23T00:00:00+00:00")
    store.update_execution_result(
        "task-3",
        "failed",
        {"task_id": "task-3", "success": False},
        "2026-04-23T00:00:02+00:00",
        owner_id="worker-a",
    )

    store.update_callback_status(
        "task-3",
        "failed",
        {"task_id": "task-3", "success": False, "callback_error": "boom"},
        "2026-04-23T00:00:03+00:00",
        preserve_status="failed",
    )

    task = store.get_task("task-3")
    assert task["status"] == "failed"
    assert task["execution_status"] == "failed"
    assert task["callback_status"] == "failed"


def test_callback_status_marks_success_task_as_callback_failed(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent("task-4", "queued", {"task_id": "task-4"}, {"subject": "x"}, "2026-04-23T00:00:00+00:00")
    store.claim_task("task-4", "worker-a", "2026-04-23T00:00:10+00:00", "2026-04-23T00:00:00+00:00")
    store.update_execution_result(
        "task-4",
        "success",
        {"task_id": "task-4", "success": True},
        "2026-04-23T00:00:02+00:00",
        owner_id="worker-a",
    )

    store.update_callback_status(
        "task-4",
        "failed",
        {"task_id": "task-4", "success": True, "callback_error": "boom"},
        "2026-04-23T00:00:03+00:00",
        preserve_status="success",
    )

    task = store.get_task("task-4")
    assert task["status"] == "callback_failed"
    assert task["execution_status"] == "success"
    assert task["callback_status"] == "failed"


# ============================================================================
# Credential Sanitization Tests (Issue #2880)
# ============================================================================


def test_sanitize_payload_removes_password_from_host_credentials():
    """Verify passwords are removed from host_credentials array."""
    payload = {
        "task_id": "test-1",
        "module": "shell",
        "host_credentials": [
            {"host": "10.0.0.1", "user": "root", "password": "secret123", "port": 22},
            {"host": "10.0.0.2", "user": "admin", "password": "hunter2", "port": 22},
        ],
    }

    sanitized = _sanitize_payload_for_storage(payload)

    assert "password" not in sanitized["host_credentials"][0]
    assert "password" not in sanitized["host_credentials"][1]
    assert sanitized["host_credentials"][0]["_redacted"] is True
    assert sanitized["host_credentials"][1]["_redacted"] is True
    # Non-sensitive fields preserved
    assert sanitized["host_credentials"][0]["host"] == "10.0.0.1"
    assert sanitized["host_credentials"][0]["user"] == "root"
    assert sanitized["host_credentials"][0]["port"] == 22


def test_sanitize_payload_removes_private_key_content():
    """Verify SSH private keys are removed from host_credentials."""
    payload = {
        "task_id": "test-2",
        "host_credentials": [
            {
                "host": "10.0.0.1",
                "user": "ubuntu",
                "private_key_content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
                "private_key_passphrase": "keypass123",
            },
        ],
    }

    sanitized = _sanitize_payload_for_storage(payload)

    assert "private_key_content" not in sanitized["host_credentials"][0]
    assert "private_key_passphrase" not in sanitized["host_credentials"][0]
    assert sanitized["host_credentials"][0]["_redacted"] is True
    assert sanitized["host_credentials"][0]["host"] == "10.0.0.1"


def test_sanitize_payload_removes_top_level_sensitive_fields():
    """Verify top-level sensitive fields are removed."""
    payload = {
        "task_id": "test-3",
        "module": "ping",
        "password": "should_be_removed",
        "private_key_content": "-----BEGIN...",
        "ansible_password": "also_removed",
    }

    sanitized = _sanitize_payload_for_storage(payload)

    assert "password" not in sanitized
    assert "private_key_content" not in sanitized
    assert "ansible_password" not in sanitized
    # Non-sensitive fields preserved
    assert sanitized["task_id"] == "test-3"
    assert sanitized["module"] == "ping"


def test_sanitize_payload_redacts_sensitive_extra_vars():
    payload = {
        "task_id": "extra-vars-test",
        "extra_vars": {
            "bklite_session_url": "https://server.example/session/secret",
            "api_token": "token-value",
            "target_path": "C:/Windows/Temp/bootstrap.exe",
        },
    }

    sanitized = _sanitize_payload_for_storage(payload)

    assert sanitized["extra_vars"]["bklite_session_url"] == "***"
    assert sanitized["extra_vars"]["api_token"] == "***"
    assert sanitized["extra_vars"]["target_path"] == "C:/Windows/Temp/bootstrap.exe"


def test_sanitize_payload_recursively_redacts_sensitive_extra_vars(tmp_path):
    secret = "nested-database-password"
    payload = {
        "task_id": "nested-extra-vars-test",
        "extra_vars": {
            "database": {"username": "reader", "password": secret},
            "targets": [
                {"host": "10.0.0.1", "api_token": "nested-api-token"},
                [{"host": "10.0.0.2", "client_secret": "nested-client-secret"}],
            ],
        },
    }

    store = TaskStore(str(tmp_path / "task.db"))
    store.create_if_absent(
        payload["task_id"],
        "queued",
        payload,
        {},
        "2026-04-23T00:00:00+00:00",
    )

    task = store.get_task(payload["task_id"])
    assert task["payload"]["extra_vars"] == {
        "database": {"username": "reader", "password": "***"},
        "targets": [
            {"host": "10.0.0.1", "api_token": "***"},
            [{"host": "10.0.0.2", "client_secret": "***"}],
        ],
    }
    assert secret.encode() not in (tmp_path / "task.db").read_bytes()


def test_sanitize_payload_handles_empty_payload():
    """Verify empty/None payloads are handled gracefully."""
    assert _sanitize_payload_for_storage({}) == {}
    assert _sanitize_payload_for_storage(None) is None


def test_sanitize_payload_handles_missing_host_credentials():
    """Verify payloads without host_credentials work correctly."""
    payload = {"task_id": "test-4", "module": "ping", "hosts": "all"}

    sanitized = _sanitize_payload_for_storage(payload)

    assert sanitized == payload


def test_create_if_absent_stores_sanitized_payload(tmp_path):
    """Verify create_if_absent sanitizes payload before storage."""
    store = TaskStore(str(tmp_path / "task.db"))

    payload_with_creds = {
        "task_id": "cred-test",
        "host_credentials": [
            {"host": "10.0.0.1", "user": "root", "password": "secret"},
        ],
    }

    store.create_if_absent(
        "cred-test",
        "queued",
        payload_with_creds,
        {},
        "2026-04-23T00:00:00+00:00",
    )

    task = store.get_task("cred-test")

    # Verify credentials are NOT in stored payload
    assert "password" not in task["payload"]["host_credentials"][0]
    assert task["payload"]["host_credentials"][0]["_redacted"] is True
    # Non-sensitive data preserved
    assert task["payload"]["host_credentials"][0]["host"] == "10.0.0.1"
    assert task["payload"]["host_credentials"][0]["user"] == "root"


def test_create_if_absent_redacts_callback_token_from_query_state(tmp_path):
    store = TaskStore(str(tmp_path / "callback.db"), "test-encryption-secret")
    callback_token = "callback-bearer-7f82d19a"
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {"caller": "ansible-executor", "execution_id": 1, "attempt_id": "a1", "token": callback_token},
    }

    store.create_if_absent(
        "callback-task",
        "queued",
        {"task_id": "callback-task", "callback": callback},
        callback,
        "2026-08-10T00:00:00Z",
    )

    task = store.get_task("callback-task")
    assert task["callback"]["context"]["token"] == "***"
    assert task["payload"]["callback"]["context"]["token"] == "***"
    assert task["callback"]["context"]["attempt_id"] == "a1"
    assert store.get_callback_config("callback-task")["context"]["token"] == callback_token
    assert callback_token.encode() not in (tmp_path / "callback.db").read_bytes()

    store.update_callback_status(
        "callback-task",
        "sent",
        {"task_id": "callback-task", "success": True},
        "2026-08-10T00:01:00Z",
        preserve_status="success",
    )

    assert store.get_callback_config("callback-task") is None


def test_create_without_callback_keeps_callback_secret_column_null(tmp_path):
    store = TaskStore(str(tmp_path / "no-callback.db"), "test-encryption-secret")
    store.create_if_absent(
        "no-callback-task",
        "queued",
        {"task_id": "no-callback-task"},
        {},
        "2026-08-10T00:00:00Z",
    )

    with store._connect() as connection:
        value = connection.execute(
            "SELECT callback_secret_json FROM task_state WHERE task_id = ?",
            ("no-callback-task",),
        ).fetchone()[0]

    assert value is None


def test_reading_legacy_execution_payload_scrubs_callback_token_copy(tmp_path):
    store = TaskStore(str(tmp_path / "legacy-callback.db"), "test-encryption-secret")
    callback_token = "legacy-callback-bearer-93ab"
    store.create_if_absent(
        "legacy-callback-task",
        "queued",
        {"task_id": "legacy-callback-task"},
        {},
        "2026-08-10T00:00:00Z",
    )
    legacy_payload = {
        "task_id": "legacy-callback-task",
        "password": "execution-password",
        "callback": {"context": {"token": callback_token}},
    }
    with store._connect() as connection:
        connection.execute(
            "UPDATE task_state SET execution_payload_json = ? WHERE task_id = ?",
            (store._encrypt_execution_payload(legacy_payload), "legacy-callback-task"),
        )

    loaded = store.get_execution_payload("legacy-callback-task")

    assert loaded["password"] == "execution-password"
    assert loaded["callback"]["context"]["token"] == "***"
    with store._connect() as connection:
        encrypted = connection.execute(
            "SELECT execution_payload_json FROM task_state WHERE task_id = ?",
            ("legacy-callback-task",),
        ).fetchone()[0]
    assert store._decrypt_execution_payload(encrypted)["callback"]["context"]["token"] == "***"
    assert callback_token.encode() not in (tmp_path / "legacy-callback.db").read_bytes()


def test_create_if_absent_preserves_execution_payload_for_worker_use(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    payload_with_creds = {
        "task_id": "execution-payload-test",
        "inventory_content": "[all]\n10.0.0.1 ansible_user=root ansible_password=secret\n",
        "host_credentials": [
            {"host": "10.0.0.1", "user": "root", "password": "secret"},
        ],
        "private_key_content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
    }

    store.create_if_absent(
        "execution-payload-test",
        "queued",
        payload_with_creds,
        {},
        "2026-04-23T00:00:00+00:00",
    )

    execution_payload = store.get_execution_payload("execution-payload-test")

    assert execution_payload == payload_with_creds
    assert b"ansible_password=secret" not in (tmp_path / "task.db").read_bytes()
    assert b"BEGIN RSA PRIVATE KEY" not in (tmp_path / "task.db").read_bytes()

    store.update_execution_result(
        "execution-payload-test",
        "success",
        {"success": True},
        "2026-04-23T00:01:00+00:00",
    )

    assert store.get_execution_payload("execution-payload-test") is None


def test_task_store_generates_stable_local_key_when_no_secret_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", raising=False)
    db_path = tmp_path / "task.db"
    payload = {"task_id": "anonymous-nats", "password": "credential"}

    first_store = TaskStore(str(db_path))
    first_store.create_if_absent(
        payload["task_id"],
        "queued",
        payload,
        {},
        "2026-04-23T00:00:00+00:00",
    )
    second_store = TaskStore(str(db_path))

    assert second_store.get_execution_payload(payload["task_id"]) == payload
    key_path = tmp_path / f"task.db{TaskStore.LOCAL_KEY_SUFFIX}"
    assert key_path.stat().st_mode & 0o777 == 0o600


def test_task_store_recovers_interrupted_empty_local_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", raising=False)
    db_path = tmp_path / "task.db"
    key_path = tmp_path / f"task.db{TaskStore.LOCAL_KEY_SUFFIX}"
    key_path.touch(mode=0o600)

    store = TaskStore(str(db_path))

    assert key_path.read_text(encoding="utf-8").strip()
    assert store._payload_cipher is not None


def test_task_store_concurrently_publishes_one_stable_local_key(tmp_path):
    db_path = tmp_path / "task.db"

    def load_secret():
        store = TaskStore.__new__(TaskStore)
        store.db_path = str(db_path)
        return store._load_or_create_local_encryption_secret()

    with ThreadPoolExecutor(max_workers=8) as executor:
        secrets = list(executor.map(lambda _: load_secret(), range(16)))

    assert len(set(secrets)) == 1


def test_update_execution_result_clears_terminal_execution_payload(tmp_path):
    payload_with_creds = {
        "task_id": "terminal-payload-test",
        "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": "secret"}],
    }

    for final_status in ("success", "failed"):
        store = TaskStore(str(tmp_path / f"{final_status}.db"))
        task_id = f"terminal-payload-{final_status}"
        store.create_if_absent(task_id, "queued", payload_with_creds, {}, "2026-04-23T00:00:00+00:00")
        store.claim_task(
            task_id,
            "worker-a",
            "2026-04-23T00:00:10+00:00",
            "2026-04-23T00:00:01+00:00",
        )

        updated = store.update_execution_result(
            task_id,
            final_status,
            {"task_id": task_id, "success": final_status == "success"},
            "2026-04-23T00:00:02+00:00",
            owner_id="worker-a",
        )

        assert updated is True
        assert store.get_execution_payload(task_id) is None


def test_init_erases_legacy_terminal_credentials_from_database_pages(tmp_path):
    db_path = tmp_path / "task.db"
    secret = "terminal-credential-physical-erase-9f7d2b4c-" + "x" * 128
    store = TaskStore(str(db_path))
    store.create_if_absent(
        "terminal-physical-erase",
        "queued",
        {
            "task_id": "terminal-physical-erase",
            "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": secret}],
        },
        {},
        "2026-04-23T00:00:00+00:00",
    )
    legacy_payload = json.dumps(
        {
            "task_id": "terminal-physical-erase",
            "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": secret}],
        },
        ensure_ascii=False,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA secure_delete = OFF")
        connection.execute("ALTER TABLE task_state DROP COLUMN execution_status")
        connection.execute(
            """
            UPDATE task_state
            SET status = 'success', execution_payload_json = ?
            WHERE task_id = 'terminal-physical-erase'
            """,
            (legacy_payload,),
        )
    assert secret.encode() in db_path.read_bytes()

    reloaded_store = TaskStore(str(db_path))

    assert reloaded_store.get_execution_payload("terminal-physical-erase") is None
    assert secret.encode() not in db_path.read_bytes()


def test_update_execution_result_keeps_payload_when_lease_owner_mismatches(tmp_path):
    store = TaskStore(str(tmp_path / "task.db"))
    payload_with_creds = {
        "task_id": "lease-lost-payload-test",
        "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": "secret"}],
    }
    store.create_if_absent(
        "lease-lost-payload-test",
        "queued",
        payload_with_creds,
        {},
        "2026-04-23T00:00:00+00:00",
    )
    store.claim_task(
        "lease-lost-payload-test",
        "worker-a",
        "2026-04-23T00:00:10+00:00",
        "2026-04-23T00:00:01+00:00",
    )

    updated = store.update_execution_result(
        "lease-lost-payload-test",
        "success",
        {"task_id": "lease-lost-payload-test", "success": True},
        "2026-04-23T00:00:02+00:00",
        owner_id="worker-b",
    )

    assert updated is False
    assert store.get_execution_payload("lease-lost-payload-test") == payload_with_creds


def test_init_clears_legacy_terminal_payloads_without_touching_active_tasks(tmp_path):
    db_path = tmp_path / "task.db"
    store = TaskStore(str(db_path))
    payload_with_creds = {
        "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": "secret"}],
    }
    stored_statuses = {
        "status-terminal": ("success", "queued"),
        "execution-terminal": ("running", "failed"),
        "callback-terminal": ("callback_failed", "success"),
        "queued": ("queued", "queued"),
        "running": ("running", "running"),
    }
    for task_id_suffix, (status, execution_status) in stored_statuses.items():
        task_id = f"legacy-{task_id_suffix}"
        callback = (
            {"subject": "job.callback", "context": {"token": "callback-secret"}}
            if task_id_suffix == "callback-terminal"
            else {}
        )
        store.create_if_absent(task_id, "queued", payload_with_creds, callback, "2026-04-23T00:00:00+00:00")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE task_state
                SET status = ?, execution_status = ?, execution_payload_json = ?
                WHERE task_id = ?
                """,
                (status, execution_status, json.dumps(payload_with_creds), task_id),
            )

    reloaded_store = TaskStore(str(db_path))
    for task_id_suffix in ("status-terminal", "execution-terminal", "callback-terminal"):
        assert reloaded_store.get_execution_payload(f"legacy-{task_id_suffix}") is None
    for task_id_suffix in ("queued", "running"):
        assert reloaded_store.get_execution_payload(f"legacy-{task_id_suffix}") == payload_with_creds
    callback = reloaded_store.get_callback_config("legacy-callback-terminal")
    assert callback["context"]["token"] == "callback-secret"
    assert b"fernet:v1:" in db_path.read_bytes()


def test_init_rolls_back_failed_terminal_cleanup_and_recovers_after_restart(tmp_path):
    db_path = tmp_path / "task.db"
    store = TaskStore(str(db_path))
    store.create_if_absent(
        "terminal",
        "queued",
        {"password": "legacy-secret"},
        {},
        "2026-04-23T00:00:00+00:00",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE task_state SET status = 'success', execution_payload_json = ? WHERE task_id = 'terminal'",
            (json.dumps({"password": "legacy-secret"}),),
        )
        connection.execute(
            """
            CREATE TRIGGER reject_terminal_cleanup
            BEFORE UPDATE OF execution_payload_json ON task_state
            BEGIN SELECT RAISE(ABORT, 'blocked cleanup'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="blocked cleanup"):
        TaskStore(str(db_path))
    with sqlite3.connect(db_path) as connection:
        assert "legacy-secret" in connection.execute(
            "SELECT execution_payload_json FROM task_state WHERE task_id = 'terminal'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER reject_terminal_cleanup")

    recovered_store = TaskStore(str(db_path))
    assert recovered_store.get_execution_payload("terminal") is None


def test_init_clears_terminal_fernet_payload_without_the_original_key(tmp_path):
    db_path = tmp_path / "task.db"
    old_store = TaskStore(str(db_path), "old-key")
    old_store.create_if_absent(
        "terminal",
        "queued",
        {"password": "encrypted-secret"},
        {},
        "2026-04-23T00:00:00+00:00",
    )
    with old_store._connect() as connection:
        ciphertext = connection.execute(
            "SELECT execution_payload_json FROM task_state WHERE task_id = 'terminal'"
        ).fetchone()[0]
        connection.execute("UPDATE task_state SET status = 'success' WHERE task_id = 'terminal'")

    new_store = TaskStore(str(db_path), "replacement-key")

    assert new_store.get_execution_payload("terminal") is None
    assert ciphertext.encode() not in db_path.read_bytes()


def test_sensitive_credential_keys_is_comprehensive():
    """Verify all known sensitive patterns are in the constant."""
    expected_keys = {
        "password",
        "private_key_content",
        "private_key_passphrase",
        "ansible_password",
        "ansible_ssh_passphrase",
        "ansible_become_password",
        "inventory_content",
    }
    assert SENSITIVE_CREDENTIAL_KEYS == expected_keys
