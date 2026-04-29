from service.task_store import TaskStore


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
