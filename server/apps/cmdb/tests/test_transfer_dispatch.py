"""HTTP 接纳后的消息发布、背压、Broker 故障与真实任务路由。"""

import threading
from unittest.mock import Mock

import pytest
from kombu import Connection, Exchange, Queue

from apps.cmdb.services.transfer_dispatch import TransferDispatch
from apps.cmdb.tasks.transfer import execute_transfer, send_transfer


@pytest.fixture
def publisher_threads(monkeypatch):
    threads = []

    def startable_thread(**kwargs):
        thread = threading.Thread(**kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr("apps.cmdb.services.transfer_dispatch.Thread", startable_thread)
    yield threads
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_slow_publishers_are_bounded_and_do_not_accumulate_pending_threads(publisher_threads):
    started = [threading.Event(), threading.Event()]
    release = threading.Event()

    def send(task_id):
        started[int(task_id)].set()
        assert release.wait(2)

    try:
        TransferDispatch.submit("0", send)
        TransferDispatch.submit("1", send)
        assert all(event.wait(1) for event in started)
        overflow = Mock()
        TransferDispatch.submit("overflow", overflow)
        overflow.assert_not_called()
        assert len(publisher_threads) == 2
    finally:
        release.set()


def test_background_publish_failure_is_bounded_logged_and_releases_capacity(publisher_threads, caplog):
    error = OSError("PRIVATE-PUBLISH-SENTINEL")
    send = Mock(side_effect=error)
    for task_id in ("one", "two", "three"):
        TransferDispatch.submit(task_id, send)
        publisher_threads[-1].join(timeout=1)
        assert not publisher_threads[-1].is_alive()
    assert send.call_count == 3
    records = [record for record in caplog.records if "cmdb_transfer_dispatch_deferred" in record.msg]
    assert len(records) == 3
    for record, task_id in zip(records, ("one", "two", "three")):
        assert record.args == (task_id, "OSError")
        assert record.getMessage() == f"event=cmdb_transfer_dispatch_deferred task_id={task_id} failed_stage=dispatch error_type=OSError"
        assert record.exc_info is None
    assert "PRIVATE-PUBLISH-SENTINEL" not in caplog.text
    assert str(error) == "PRIVATE-PUBLISH-SENTINEL"


def test_transfer_publication_routes_to_existing_default_worker(monkeypatch):
    connection = Connection("memory://")
    factory = Mock(return_value=connection)
    monkeypatch.setattr(execute_transfer.app, "connection_for_write", factory)
    with Connection("memory://") as consumer:
        normal = Queue("celery", Exchange("celery"), routing_key="celery")(consumer)
        dedicated = Queue("cmdb_transfer", Exchange("cmdb_transfer"), routing_key="cmdb_transfer")(consumer)
        normal.declare()
        dedicated.declare()
        normal.purge()
        dedicated.purge()
        send_transfer("test-task-id")
        assert dedicated.get(no_ack=True) is None
        message = normal.get(no_ack=True)
        assert message is not None
        assert message.headers["task"] == "apps.cmdb.tasks.transfer.execute_transfer"
        assert message.payload[0] == ["test-task-id"]
    assert factory.call_args_list[0].kwargs["connect_timeout"] == 2


def test_unavailable_broker_does_not_retry_inside_one_publication(monkeypatch):
    from kombu.exceptions import OperationalError
    from kombu.transport.memory import Transport

    connect = Mock(side_effect=OSError("PRIVATE-CONNECT-SENTINEL"))
    monkeypatch.setattr(Transport, "establish_connection", connect)
    monkeypatch.setattr(Transport, "connection_errors", (OSError,))
    monkeypatch.setattr(execute_transfer.app, "connection_for_write", lambda **kwargs: Connection("memory://", **kwargs))
    with pytest.raises(OperationalError):
        send_transfer("unavailable")
    assert connect.call_count == 1


@pytest.mark.parametrize("kind", ["import", "export"])
def test_old_queued_task_is_republished_to_default_worker(transfer_owner, monkeypatch, kind):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.transfer_task import CmdbTransferTask
    from apps.cmdb.tasks.transfer import maintain_transfers
    from apps.cmdb.tests.test_transfer_service import submit

    task = submit(transfer_owner, kind=kind)
    # 已尝试投递到旧队列的记录，由正常维护补发到当前路由，不创建重复任务。
    CmdbTransferTask.objects.filter(pk=task.pk).update(dispatched_at=now() - timedelta(minutes=2))
    monkeypatch.setattr(execute_transfer.app, "connection_for_write", lambda **kwargs: Connection("memory://", **kwargs))
    execute = Mock()
    monkeypatch.setattr("apps.cmdb.tasks.transfer.TransferExecution.run", execute)
    with Connection("memory://") as consumer:
        queue = Queue("celery", Exchange("celery"), routing_key="celery")(consumer)
        queue.declare()
        queue.purge()
        maintain_transfers.run()
        message = queue.get(no_ack=True)
        assert message is not None
        assert message.payload[0] == [str(task.pk)]
        registered_task = execute_transfer.app.tasks[message.headers["task"]]
        registered_task.run(*message.payload[0])
    execute.assert_called_once_with(str(task.pk))
    assert CmdbTransferTask.objects.filter(owner=transfer_owner).count() == 1
