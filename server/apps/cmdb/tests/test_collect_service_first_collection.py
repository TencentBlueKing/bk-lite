import logging
import types

import pytest
from django.db import transaction

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_service import CollectModelService

pytestmark = pytest.mark.unit


def task(**overrides):
    values = {
        "id": 7,
        "is_k8s": False,
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "instances": [{"inst_name": "host-1"}],
        "ip_range": "",
        "access_point": [{"id": "node-1"}],
        "plugin_id": "host_info",
        "params": {},
        "timeout": 60,
        "decrypt_credentials": {"username": "root", "password": "secret"},
        "name": "task",
        "team": [1],
        "expire_days": 0,
        "data_cleanup_strategy": "no_cleanup",
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


def test_create_registers_one_on_commit_dispatch(mocker):
    callbacks = []
    mocker.patch(
        "apps.cmdb.services.collect_service.transaction.on_commit",
        side_effect=callbacks.append,
    )
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")

    assert CollectModelService.schedule_first_collection_if_needed(task()) is True

    send_task.assert_not_called()
    assert len(callbacks) == 1
    callbacks[0]()
    send_task.assert_called_once_with(
        CollectModelService.FIRST_COLLECTION_TASK,
        args=[7, mocker.ANY, "create"],
    )
    assert "secret" not in repr(send_task.call_args)


@pytest.mark.django_db(transaction=True)
def test_rollback_discards_first_collection_dispatch(mocker):
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            CollectModelService.schedule_first_collection_if_needed(task())
            raise RuntimeError("rollback")

    send_task.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_first_collection_dispatch_failure_does_not_block_delayed_sync(
    mocker,
    caplog,
):
    sensitive_error = RuntimeError(
        "password=top-secret broker=redis://user:pass@broker.internal/0"
    )
    send_task = mocker.patch(
        "apps.cmdb.services.collect_service.current_app.send_task",
        side_effect=[sensitive_error, None],
    )
    caplog.set_level(logging.ERROR, logger="cmdb")
    instance = task()

    with transaction.atomic():
        CollectModelService.schedule_first_collection_if_needed(instance)
        CollectModelService.schedule_delayed_sync_if_needed(
            instance,
            is_interval=True,
        )

    assert send_task.call_count == 2
    delayed_call = send_task.call_args_list[1]
    assert delayed_call.args == (CollectModelService.TASK,)
    assert delayed_call.kwargs == {
        "args": [7],
        "countdown": CollectModelService.DELAY_SYNC_COUNTDOWN_SECONDS,
    }
    first_collection_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if "[FirstCollection]" in record.getMessage()
    )
    assert "error_type=RuntimeError" in first_collection_logs
    assert "top-secret" not in first_collection_logs
    assert "redis://" not in first_collection_logs


def test_update_source_change_has_field_reason(mocker):
    callbacks = []
    mocker.patch(
        "apps.cmdb.services.collect_service.transaction.on_commit",
        side_effect=callbacks.append,
    )
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")
    old = task(params={"port": 22})
    new = task(params={"port": 2222})

    assert CollectModelService.schedule_first_collection_if_needed(
        new,
        old_instance=old,
        reason="update",
    ) is True

    callbacks[0]()
    assert send_task.call_args.kwargs["args"][2] == "update:params"


def test_governance_only_disabled_short_k8s_and_config_file_skip(mocker):
    on_commit = mocker.patch("apps.cmdb.services.collect_service.transaction.on_commit")

    assert CollectModelService.schedule_first_collection_if_needed(
        task(name="new"),
        old_instance=task(),
        reason="update",
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(cycle_value="5")
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(task_type=CollectPluginTypes.K8S)
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(task_type=CollectPluginTypes.CONFIG_FILE)
    ) is False
    mocker.patch("apps.cmdb.constants.constants.CMDB_FIRST_COLLECTION_ENABLED", False)
    assert CollectModelService.schedule_first_collection_if_needed(task()) is False
    on_commit.assert_not_called()


@pytest.mark.django_db
def test_create_schedules_first_and_delayed_sync(mocker, django_capture_on_commit_callbacks):
    instance = task()
    serializer = mocker.Mock(instance=instance)
    view = mocker.Mock()
    view.get_serializer.return_value = serializer
    request = mocker.Mock(data={}, user=mocker.Mock(username="admin"))
    mocker.patch.object(
        CollectModelService,
        "format_params",
        return_value=({}, True, "*/30 * * * *"),
    )
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch(
        "apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task"
    )
    first = mocker.patch.object(
        CollectModelService,
        "schedule_first_collection_if_needed",
        return_value=True,
    )
    delayed = mocker.patch.object(
        CollectModelService,
        "schedule_delayed_sync_if_needed",
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.create(request, view) == 7

    first.assert_called_once_with(instance=instance, reason="create")
    delayed.assert_called_once_with(instance=instance, is_interval=True)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("schedule_changed", "first_scheduled"),
    [
        (False, True),
        (True, False),
        (True, True),
    ],
)
def test_update_first_or_schedule_change_schedules_delayed_sync_once(
    mocker,
    django_capture_on_commit_callbacks,
    schedule_changed,
    first_scheduled,
):
    current = task(params={"port": 22})
    serializer = mocker.Mock(instance=current)
    view = mocker.Mock()
    view.get_object.return_value = current
    view.get_serializer.return_value = serializer
    request = mocker.Mock(data={"team": [1]}, user=mocker.Mock(username="admin"))
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(
        CollectModelService,
        "format_params",
        return_value=({"params": {"port": 2222}}, True, "*/30 * * * *"),
    )
    mocker.patch.object(CollectModelService, "format_update_credential")
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch(
        "apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task"
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectCredentialPoolService.diff_pool",
        return_value=([], [], []),
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids",
        return_value=0,
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    view.perform_update.side_effect = lambda _serializer: setattr(
        current,
        "params",
        {"port": 2222},
    )
    first = mocker.patch.object(
        CollectModelService,
        "schedule_first_collection_if_needed",
        return_value=first_scheduled,
    )
    delayed = mocker.patch.object(
        CollectModelService,
        "schedule_delayed_sync_if_needed",
    )
    mocker.patch.object(
        CollectModelService,
        "is_schedule_config_changed",
        return_value=schedule_changed,
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.update(request, view) == 7

    assert first.call_args.kwargs["old_instance"].params == {"port": 22}
    first.assert_called_once_with(
        instance=current,
        old_instance=first.call_args.kwargs["old_instance"],
        reason="update",
    )
    delayed.assert_called_once_with(instance=current, is_interval=True)
