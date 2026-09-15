import types

import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException

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


def prepare_create(mocker, events, run):
    mocker.patch("apps.cmdb.services.collect_service.CollectionOffsetService.apply")
    instance = task()
    serializer = mocker.Mock(instance=instance)
    view = mocker.Mock()
    view.get_serializer.return_value = serializer
    request = mocker.Mock(data={}, user=mocker.Mock(username="admin"))
    mocker.patch.object(CollectModelService, "format_params", return_value=({}, True, "*/30 * * * *"))
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(
        CollectModelService,
        "push_butch_node_params",
        side_effect=lambda _instance: events.append("config_pushed"),
    )
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=run)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    return request, view


@pytest.mark.django_db
def test_create_marks_first_collection_ready_only_after_node_config_push(mocker, django_capture_on_commit_callbacks):
    events = []
    run = types.SimpleNamespace(id=91)
    request, view = prepare_create(mocker, events, run)
    mark_ready = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.mark_config_ready_and_dispatch",
        side_effect=lambda run_id: events.append(f"ready:{run_id}"),
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.create(request, view) == 7

    assert events == ["config_pushed", "ready:91"]
    mark_ready.assert_called_once_with(91)


@pytest.mark.django_db
def test_create_without_first_collection_only_pushes_config(mocker, django_capture_on_commit_callbacks):
    events = []
    request, view = prepare_create(mocker, events, None)
    mark_ready = mocker.patch("apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.mark_config_ready_and_dispatch")

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.create(request, view) == 7

    assert events == ["config_pushed"]
    mark_ready.assert_not_called()


@pytest.mark.django_db
def test_create_stays_successful_when_post_commit_config_push_fails(mocker, caplog, django_capture_on_commit_callbacks):
    events = []
    run = types.SimpleNamespace(id=93)
    request, view = prepare_create(mocker, events, run)
    error = RuntimeError("password=credential-sentinel payload=private-sentinel")
    mocker.patch.object(CollectModelService, "push_butch_node_params", side_effect=error)
    mark_ready = mocker.patch("apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.mark_config_ready_and_dispatch")

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.create(request, view) == 7

    mark_ready.assert_not_called()
    records = [record for record in caplog.records if "event=collect_task_external_sync_failed" in record.getMessage()]
    assert len(records) == 1
    assert records[0].msg == ("event=collect_task_external_sync_failed task_id=%s operation=create failed_stage=post_commit_sync error_type=%s")
    assert records[0].args == (7, "RuntimeError")
    assert records[0].exc_info[2] is error.__traceback__
    assert "credential-sentinel" not in caplog.text
    assert "private-sentinel" not in caplog.text


@pytest.mark.django_db
def test_create_without_recovery_run_surfaces_post_commit_config_failure(mocker, caplog, django_capture_on_commit_callbacks):
    events = []
    request, view = prepare_create(mocker, events, None)
    error = RuntimeError("password=credential-sentinel payload=private-sentinel")
    mocker.patch.object(CollectModelService, "push_butch_node_params", side_effect=error)

    with pytest.raises(BaseAppException, match="采集任务已保存，但外部资源同步失败"):
        with django_capture_on_commit_callbacks(execute=True):
            CollectModelService.create(request, view)

    assert "credential-sentinel" not in caplog.text
    assert "private-sentinel" not in caplog.text


def test_schedule_delegates_policy_and_persistence_to_orchestrator(mocker):
    run = types.SimpleNamespace(id=91)
    schedule = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.schedule",
        return_value=run,
    )
    current = task(params={"port": 2222})
    previous = task(params={"port": 22})

    assert (
        CollectModelService.schedule_first_collection_if_needed(
            current,
            old_instance=previous,
            reason="update",
        )
        is run
    )
    schedule.assert_called_once_with(current, old_task=previous, reason="update")


@pytest.mark.django_db
def test_update_replaces_node_config_before_first_collection_dispatch(mocker, django_capture_on_commit_callbacks):
    events = []
    instance = task()
    serializer = mocker.Mock(instance=instance)
    view = mocker.Mock()
    view.get_object.return_value = instance
    view.get_serializer.return_value = serializer
    request = mocker.Mock(data={"team": [1]}, user=mocker.Mock(username="admin"))
    run = types.SimpleNamespace(id=92)

    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(CollectModelService, "format_params", return_value=({"team": [1]}, True, "*/30 * * * *"))
    mocker.patch.object(CollectModelService, "format_update_credential")
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "_bump_network_channel_versions")
    mocker.patch.object(CollectModelService, "is_schedule_config_changed", return_value=False)
    mocker.patch.object(CollectModelService, "should_sync_node_params", return_value=True)
    mocker.patch.object(CollectModelService, "should_register_sync_beat", return_value=False)
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch.object(
        CollectModelService,
        "delete_butch_node_params",
        side_effect=lambda _instance: events.append("old_config_deleted"),
    )
    mocker.patch.object(
        CollectModelService,
        "push_butch_node_params",
        side_effect=lambda _instance: events.append("new_config_pushed"),
    )
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=run)
    mocker.patch("apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids", return_value=0)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.mark_config_ready_and_dispatch",
        side_effect=lambda run_id: events.append(f"ready:{run_id}"),
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.update(request, view) == instance.id

    assert events == ["old_config_deleted", "new_config_pushed", "ready:92"]


@pytest.mark.django_db
def test_disabling_k8s_schedule_still_removes_legacy_periodic_task(mocker, django_capture_on_commit_callbacks):
    instance = task(task_type=CollectPluginTypes.K8S, is_k8s=True, scan_cycle="*/30 * * * *")
    serializer = mocker.Mock(instance=instance)
    view = mocker.Mock()
    view.get_object.return_value = instance
    view.get_serializer.return_value = serializer
    view.perform_update.side_effect = lambda _serializer: setattr(instance, "is_interval", False)
    request = mocker.Mock(data={"team": [1]}, user=mocker.Mock(username="admin"))

    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(CollectModelService, "format_params", return_value=({"team": [1]}, False, ""))
    mocker.patch.object(CollectModelService, "format_update_credential")
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "_bump_network_channel_versions")
    mocker.patch.object(CollectModelService, "is_schedule_config_changed", return_value=True)
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=None)
    mocker.patch("apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids", return_value=0)
    delete_periodic = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.update(request, view) == instance.id

    delete_periodic.assert_called_once_with(f"{CollectModelService.NAME}_{instance.id}")
