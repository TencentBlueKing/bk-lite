import json
import logging
from types import SimpleNamespace

import pytest
import toml

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import SafeLogException

pytestmark = pytest.mark.django_db


def _request(data):
    return SimpleNamespace(
        data=data,
        user=SimpleNamespace(username="admin", domain="domain.com", group_list=[{"id": 1, "name": "Default"}]),
        COOKIES={},
    )


def _create_view(request):
    return SimpleNamespace(
        get_serializer=lambda *args, **kwargs: CollectModelSerializer(*args, context={"request": request}, **kwargs),
        perform_create=lambda serializer: serializer.save(),
    )


class _TaskView:
    def __init__(self, task_id):
        self.task_id = task_id

    def get_object(self):
        return CollectModels.objects.get(pk=self.task_id)


def _payload(**overrides):
    payload = {
        "name": "enable-switch-host",
        "task_type": "host",
        "driver_type": "job",
        "model_id": "host",
        "timeout": 60,
        "input_method": 0,
        "team": [1],
        "scan_cycle": {"value_type": "cycle", "value": "30"},
        "access_point": [{"id": "node-1", "cloud": 1}],
        "ip_range": "10.0.0.8",
        "credential": [{"username": "collect-user", "password": "secret-value", "port": 22}],
        "params": {},
    }
    payload.update(overrides)
    return payload


def _interval(node_mock, index):
    content = node_mock.return_value.batch_add_node_child_config.call_args_list[index].args[0][0]["content"]
    return toml.loads(content)["inputs"]["prometheus"][0]["interval"]


def test_create_disable_and_enable_keeps_cycle_and_reissues_node_config(mocker, django_capture_on_commit_callbacks):
    mocker.patch("apps.core.utils.serializers.get_permission_rules", return_value={"team": [1]})
    mocker.patch.object(CollectModelService, "has_permission")
    schedule = mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=None)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
    change_records = mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")

    request = _request(_payload())
    with django_capture_on_commit_callbacks(execute=True):
        task_id = CollectModelService.create(request, _create_view(request))

    created = CollectModels.objects.get(pk=task_id)
    assert created.enabled is True
    assert created.scan_cycle == "*/30 * * * *"
    assert created.cycle_value == "30"
    assert created.credential[0]["username"] == "collect-user"
    assert node.return_value.batch_add_node_child_config.call_count == 1
    assert node.return_value.delete_child_configs.call_count == 0
    assert _interval(node, 0) == "1800s"
    scheduled_by_create = schedule.call_count

    view = _TaskView(task_id)
    with django_capture_on_commit_callbacks(execute=True):
        disabled = CollectModelService.set_enabled(_request({"enabled": False}), view)

    created.refresh_from_db()
    assert disabled == {"id": task_id, "enabled": False}
    assert created.enabled is False
    assert created.scan_cycle == "*/30 * * * *"
    assert created.cycle_value == "30"
    assert created.ip_range == "10.0.0.8"
    assert created.credential[0]["username"] == "collect-user"
    assert node.return_value.batch_add_node_child_config.call_count == 1
    assert node.return_value.delete_child_configs.call_args.args[0] == [f"cmdb_{task_id}"]

    response = CollectModelService.exec_task(created, operator="admin")
    assert response.status_code == 400
    assert json.loads(response.content)["message"] == "任务已关闭"
    assert node.return_value.batch_add_node_child_config.call_count == 1

    with django_capture_on_commit_callbacks(execute=True):
        enabled = CollectModelService.set_enabled(_request({"enabled": True}), view)

    created.refresh_from_db()
    assert enabled == {"id": task_id, "enabled": True}
    assert created.enabled is True
    assert created.scan_cycle == "*/30 * * * *"
    assert created.cycle_value == "30"
    assert created.credential[0]["username"] == "collect-user"
    assert node.return_value.delete_child_configs.call_count == 2
    assert node.return_value.batch_add_node_child_config.call_count == 2
    assert _interval(node, 1) == "1800s"

    messages = [call.kwargs["message"] for call in change_records.call_args_list]
    assert "关闭采集任务. 任务名称: enable-switch-host" in messages
    assert "启用采集任务. 任务名称: enable-switch-host" in messages
    assert schedule.call_count == scheduled_by_create


def test_update_without_enabled_keeps_disabled_task_from_pushing(mocker, django_capture_on_commit_callbacks):
    mocker.patch("apps.core.utils.serializers.get_permission_rules", return_value={"team": [1]})
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=None)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    task = CollectModels.objects.create(
        name="stay-disabled",
        task_type="host",
        driver_type="job",
        model_id="host",
        timeout=60,
        input_method=0,
        team=[1],
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        access_point=[{"id": "node-1", "cloud": 1}],
        ip_range="10.0.0.8",
        credential=[{"username": "collect-user", "password": "enc:kept", "port": 22}],
        params={},
        enabled=False,
    )
    request = _request(_payload(name="stay-disabled"))
    view = SimpleNamespace(
        get_object=lambda: CollectModels.objects.get(pk=task.id),
        get_serializer=lambda *args, **kwargs: CollectModelSerializer(*args, context={"request": request}, **kwargs),
        perform_update=lambda serializer: serializer.save(),
    )

    with django_capture_on_commit_callbacks(execute=True):
        CollectModelService.update(request, view)

    task.refresh_from_db()
    assert task.enabled is False
    assert task.scan_cycle == "*/30 * * * *"
    assert task.credential[0]["username"] == "collect-user"
    node.return_value.batch_add_node_child_config.assert_not_called()
    node.return_value.delete_child_configs.assert_called_once_with([f"cmdb_{task.id}"])


def test_set_enabled_rejects_non_boolean():
    task = CollectModels.objects.create(
        name="bad-flag",
        task_type="host",
        driver_type="job",
        model_id="host",
        team=[1],
        enabled=True,
    )
    with pytest.raises(ValidationAppException, match="启用开关必须是布尔值") as raised:
        CollectModelService.set_enabled(_request({"enabled": "false"}), _TaskView(task.id))
    assert raised.value.STATUS_CODE == 400
    task.refresh_from_db()
    assert task.enabled is True


def test_k8s_disable_removes_beat_and_enable_restores_saved_cycle(mocker):
    task = CollectModels.objects.create(
        name="k8s-switch",
        task_type=CollectPluginTypes.K8S,
        driver_type="job",
        model_id="k8s",
        team=[1],
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        enabled=True,
    )
    delete_beat = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    create_beat = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")

    task.enabled = False
    task.save(update_fields=["enabled", "updated_at"])
    CollectModelService.project_collect_task(task, replace=True)

    delete_beat.assert_called_once_with(f"sync_collect_task_{task.id}")
    create_beat.assert_not_called()

    task.enabled = True
    task.save(update_fields=["enabled", "updated_at"])
    CollectModelService.project_collect_task(task, replace=True)

    create_beat.assert_called_once_with(
        name=f"sync_collect_task_{task.id}",
        crontab="*/30 * * * *",
        args=[task.id],
        task=CollectModelService.TASK,
    )


ENABLED_CHANGED = "event=collect_task_enabled_changed task_id=%s enabled=%s"
EXTERNAL_SYNC_FAILED = "event=collect_task_external_sync_failed task_id=%s operation=set_enabled failed_stage=post_commit_sync error_type=%s"


def test_same_enabled_value_reprojects_without_change_record(mocker, django_capture_on_commit_callbacks):
    mocker.patch.object(CollectModelService, "has_permission")
    change_records = mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    task = CollectModels.objects.create(
        name="already-on",
        task_type="host",
        driver_type="job",
        model_id="host",
        team=[1],
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        access_point=[{"id": "node-1"}],
        ip_range="10.0.0.8",
        credential=[{"username": "collect-user", "password": "secret-value"}],
        params={},
        enabled=True,
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = CollectModelService.set_enabled(_request({"enabled": True}), _TaskView(task.id))

    assert result == {"id": task.id, "enabled": True}
    change_records.assert_not_called()
    node.return_value.delete_child_configs.assert_called_once_with([f"cmdb_{task.id}"])
    node.return_value.batch_add_node_child_config.assert_called_once()


def test_set_enabled_keeps_saved_state_and_logs_without_secrets(mocker, django_capture_on_commit_callbacks, caplog):
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    raised = {}

    def withdraw(_config_ids):
        error = RuntimeError("secret-value")
        raised["error"] = error
        raise error

    node.return_value.delete_child_configs.side_effect = withdraw
    task = CollectModels.objects.create(
        name="close-then-fail",
        task_type="host",
        driver_type="job",
        model_id="host",
        team=[1],
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        access_point=[{"id": "node-1"}],
        ip_range="10.0.0.8",
        credential=[{"username": "collect-user", "password": "secret-value"}],
        params={},
        enabled=True,
    )

    caplog.set_level(logging.INFO, logger="cmdb")
    with pytest.raises(BaseAppException, match="采集任务已保存，但外部资源同步失败，请重新保存任务后重试"):
        with django_capture_on_commit_callbacks(execute=True):
            CollectModelService.set_enabled(_request({"enabled": False}), _TaskView(task.id))

    task.refresh_from_db()
    assert task.enabled is False
    assert task.credential[0]["username"] == "collect-user"
    assert str(task.credential[0]["password"]).startswith("enc:")
    info = next(record for record in caplog.records if record.msg == ENABLED_CHANGED)
    assert info.args == (task.id, False)
    assert info.getMessage() == f"event=collect_task_enabled_changed task_id={task.id} enabled=False"
    errors = [record for record in caplog.records if record.msg == EXTERNAL_SYNC_FAILED]
    assert len(errors) == 1
    assert errors[0].args == (task.id, "RuntimeError")
    error = raised["error"]
    assert error.args == ("secret-value",)
    assert errors[0].exc_info[0] is SafeLogException
    assert str(errors[0].exc_info[1]) == "RuntimeError"
    assert errors[0].exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(errors[0])
    assert "secret-value" not in errors[0].getMessage()
    assert "secret-value" not in formatted
    assert "secret-value" not in caplog.text
    assert sum(record.exc_info is not None for record in caplog.records if record.name == "cmdb") == 1
    assert not any(record.name.startswith("apps.core.exceptions") for record in caplog.records)


def test_set_enabled_permission_denial_keeps_the_task_and_skips_delivery(mocker):
    mocker.patch.object(CollectModelService, "has_permission", side_effect=BaseAppException("您没有操作该采集任务的权限！"))
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    task = CollectModels.objects.create(
        name="denied",
        task_type="host",
        driver_type="job",
        model_id="host",
        team=[1],
        access_point=[{"id": "node-1"}],
        ip_range="10.0.0.8",
        enabled=True,
    )

    with pytest.raises(BaseAppException, match="没有操作该采集任务的权限"):
        CollectModelService.set_enabled(_request({"enabled": False}), _TaskView(task.id))

    task.refresh_from_db()
    assert task.enabled is True
    node.return_value.delete_child_configs.assert_not_called()
    node.return_value.batch_add_node_child_config.assert_not_called()


def test_set_enabled_applies_the_locked_row_instead_of_the_earlier_object(mocker, django_capture_on_commit_callbacks):
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
    change_records = mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    node = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    task = CollectModels.objects.create(
        name="locked-row",
        task_type="host",
        driver_type="job",
        model_id="host",
        team=[1],
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        access_point=[{"id": "node-1"}],
        ip_range="10.0.0.8",
        enabled=True,
    )
    stale = CollectModels.objects.get(pk=task.id)
    CollectModels.objects.filter(pk=task.id).update(enabled=False)

    with django_capture_on_commit_callbacks(execute=True):
        result = CollectModelService.set_enabled(_request({"enabled": True}), SimpleNamespace(get_object=lambda: stale))

    task.refresh_from_db()
    assert result == {"id": task.id, "enabled": True}
    assert task.enabled is True
    assert change_records.call_args.kwargs["message"] == "启用采集任务. 任务名称: locked-row"
    node.return_value.batch_add_node_child_config.assert_called_once()


def test_closed_k8s_skips_a_new_run_and_continues_one_already_started(mocker):
    from apps.cmdb.tasks import celery_tasks as collect_tasks

    task = CollectModels.objects.create(
        name="k8s-inflight",
        task_type=CollectPluginTypes.K8S,
        driver_type="job",
        model_id="k8s",
        team=[1],
        is_interval=True,
        scan_cycle="*/30 * * * *",
        enabled=False,
        exec_status=CollectRunStatusType.RUNNING,
        task_id="exec-started",
        collect_digest={},
    )
    claim = mocker.patch("apps.cmdb.tasks.celery_tasks._claim_collect_task_execution", return_value=None)

    skipped = collect_tasks.sync_collect_task(task.id)
    assert skipped == {"status": "task_disabled", "task_id": task.id}
    claim.assert_not_called()

    continued = collect_tasks.sync_collect_task(task.id, execution_id="exec-started")
    assert continued != {"status": "task_disabled", "task_id": task.id}
    claim.assert_called_once()
