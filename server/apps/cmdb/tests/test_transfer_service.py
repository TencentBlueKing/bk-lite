import pytest

from apps.cmdb.services.transfer_service import TransferError, TransferService
from apps.system_mgmt.models.user import User


def submit(transfer_owner, key="request-1", **overrides):
    args = dict(
        owner=transfer_owner,
        kind="export",
        model_id="host",
        team_id=1,
        include_children=False,
        params={"scope": "all", "attr_list": ["inst_name"], "association_list": [], "inst_uuids": []},
        authorization={"1": {"inst_names": [], "permission_instances_map": {}}},
        schema_hash="schema-1",
        idempotency_key=key,
    )
    args.update(overrides)
    return TransferService.submit(**args)


def test_submit_replays_same_request_and_rejects_changed_content(transfer_owner):
    task = submit(transfer_owner)
    assert task.status == "queued"
    assert submit(transfer_owner).pk == task.pk
    with pytest.raises(TransferError) as error:
        submit(transfer_owner, model_id="mysql")
    assert error.value.status_code == 409
    with pytest.raises(TransferError) as error:
        submit(transfer_owner, key="second")
    assert error.value.status_code == 429
    assert [item.pk for item in TransferService.list(transfer_owner)] == [task.pk]


def test_owner_scope_cancel_and_duplicate_delivery(transfer_owner):
    other = User.objects.create(username=transfer_owner.username, domain="tenant-b")
    task = submit(transfer_owner)
    with pytest.raises(TransferError) as error:
        TransferService.get(other, task.pk)
    assert error.value.status_code == 404
    token = TransferService.claim(task.pk)
    assert token
    assert TransferService.claim(task.pk) is None
    with pytest.raises(TransferError):
        TransferService.cancel(transfer_owner, task.pk)
    assert not TransferService.finish(task.pk, "old-token", "succeeded")
    assert TransferService.finish(task.pk, token, "succeeded", summary={"exported": 1})
    task = TransferService.get(transfer_owner, task.pk)
    assert task.status == "succeeded"
    assert task.summary == {"exported": 1}
    next_task = submit(transfer_owner, key="next")
    TransferService.cancel(transfer_owner, next_task.pk)
    assert TransferService.claim(next_task.pk) is None


def test_execution_capacity_and_import_model_exclusion(transfer_owner):
    b = User.objects.create(username="b", domain="tenant-a")
    c = User.objects.create(username="c", domain="tenant-a")
    first = submit(transfer_owner, kind="import")
    second = submit(b, kind="import")
    third = submit(c, model_id="mysql")
    one = TransferService.claim(first.pk)
    assert one
    assert TransferService.claim(second.pk) is None
    assert TransferService.claim(third.pk)
    TransferService.finish(first.pk, one, "succeeded")
    assert TransferService.claim(second.pk)


def test_history_limit_and_expiry_do_not_release_interrupted_import(transfer_owner):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.transfer_task import CmdbTransferTask

    ids = []
    for i in range(6):
        task = submit(transfer_owner, key=str(i))
        ids.append(task.pk)
        TransferService.cancel(transfer_owner, task.pk)
    assert [item.pk for item in TransferService.list(transfer_owner)] == list(reversed(ids[1:]))
    task = submit(transfer_owner, key="import", kind="import")
    token = TransferService.claim(task.pk)
    TransferService.interrupt(task.pk, token, "worker_lost")
    with pytest.raises(TransferError):
        TransferService.request_delete(transfer_owner, task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(expires_at=now() - timedelta(seconds=1))
    with pytest.raises(TransferError) as error:
        submit(transfer_owner, key="new-import", kind="import")
    assert error.value.status_code == 429


def test_deadline_rejects_old_worker_and_expired_queue_is_never_claimed(transfer_owner):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.transfer_task import CmdbTransferTask

    task = submit(transfer_owner)
    token = TransferService.claim(task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(deadline_at=now() - timedelta(seconds=1))
    with pytest.raises(TransferError) as error:
        TransferService.progress(task.pk, token, "writing_instances", 1)
    assert error.value.code == "execution_lost"
    assert not TransferService.finish(task.pk, token, "succeeded")
    TransferService.interrupt(task.pk, token, "expired")
    with pytest.raises(TransferError):
        TransferService.reconcile_interrupted(task.pk, verified_stopped=False, summary={})
    assert TransferService.reconcile_interrupted(task.pk, verified_stopped=True, summary={"created": 1})
    queued = submit(transfer_owner, key="new")
    CmdbTransferTask.objects.filter(pk=queued.pk).update(created_at=now() - timedelta(minutes=31))
    assert TransferService.claim(queued.pk) is None
    assert TransferService.get(transfer_owner, queued.pk).error_code == "queue_timeout"


def test_two_exports_block_third_worker_even_with_different_models(transfer_owner):
    b = User.objects.create(username="b", domain="a")
    c = User.objects.create(username="c", domain="a")
    one, two, three = submit(transfer_owner), submit(b), submit(c, model_id="mysql")
    assert TransferService.claim(one.pk)
    assert TransferService.claim(two.pk)
    assert TransferService.claim(three.pk) is None


def test_hidden_and_expired_idempotency_keys_cannot_recreate(transfer_owner):
    task = submit(transfer_owner)
    TransferService.cancel(transfer_owner, task.pk)
    TransferService.request_delete(transfer_owner, task.pk)
    with pytest.raises(TransferError) as error:
        submit(transfer_owner)
    assert error.value.code == "request_expired"


def test_retry_replaces_failed_record_before_history_eviction_and_preserves_files(transfer_owner):
    from apps.cmdb.models.transfer_task import CmdbTransferTask

    retained = []
    for index in range(4):
        task = submit(transfer_owner, key=f"history-{index}")
        TransferService.cancel(transfer_owner, task.pk)
        retained.append(task.pk)
    failed = submit(transfer_owner, key="failed")
    token = TransferService.claim(failed.pk)
    old_key = f"transfer/{transfer_owner.pk}/{failed.pk}/{token}/result.xlsx"
    TransferService.finish(failed.pk, token, "failed", artifacts={"result": {"key": old_key}})
    replacement = submit(transfer_owner, key="retry", retry_of=failed.pk)
    assert set(TransferService.list(transfer_owner).values_list("pk", flat=True)) == {*retained, replacement.pk}
    old = CmdbTransferTask.objects.get(pk=failed.pk)
    assert old.delete_pending and old.artifacts["result"]["key"] == old_key
    # 清理完成后响应丢失的重放仍可找到同一个替代任务。
    old.delete()
    assert TransferService.replayed_retry(transfer_owner, failed.pk, "retry").pk == replacement.pk


def test_rejected_retry_retains_failed_record_and_cannot_replace_another_owner(transfer_owner):
    failed = submit(transfer_owner)
    token = TransferService.claim(failed.pk)
    TransferService.finish(failed.pk, token, "failed")
    other = User.objects.create(username="other", domain=transfer_owner.domain)
    with pytest.raises(TransferError) as denied:
        submit(other, key="retry", retry_of=failed.pk)
    assert denied.value.status_code == 404
    assert not TransferService.list(other).exists()
    assert not TransferService.get(transfer_owner, failed.pk).delete_pending
    active = submit(transfer_owner, key="active")
    with pytest.raises(TransferError) as limited:
        submit(transfer_owner, key="retry", retry_of=failed.pk)
    assert limited.value.status_code == 429
    assert set(TransferService.list(transfer_owner).values_list("pk", flat=True)) == {failed.pk, active.pk}


def test_retry_idempotency_key_cannot_replace_a_different_failed_task(transfer_owner):
    failures = []
    for index in range(2):
        task = submit(transfer_owner, key=f"failed-{index}")
        token = TransferService.claim(task.pk)
        TransferService.finish(task.pk, token, "failed")
        failures.append(task.pk)
    replacement = submit(transfer_owner, key="retry", retry_of=failures[0])
    with pytest.raises(TransferError) as conflict:
        submit(transfer_owner, key="retry", retry_of=failures[1])
    assert conflict.value.code == "idempotency_conflict"
    assert set(TransferService.list(transfer_owner).values_list("pk", flat=True)) == {replacement.pk, failures[1]}
