import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.module_link.constants import BATCH_LIMIT, ITEM_NOT_FOUND, STATUS_CANCELLED
from apps.module_link.models import MonitorCmdbTask, MonitorCmdbTaskItem
from apps.module_link.services.monitor_cmdb import MonitorCmdbTaskService, serialize_task
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.module_push import MonitorToCmdbPushService
from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node

pytestmark = pytest.mark.django_db

AUTH = "apps.module_link.services.monitor_cmdb._is_monitor_id_authorized"
SCOPE = "apps.module_link.services.monitor_cmdb.build_monitor_push_actor_scope"
QUERY_UUID = "apps.module_link.services.monitor_cmdb.InstanceManage.query_entity_by_uuid"
QUERY_IDENT = "apps.module_link.services.monitor_cmdb.InstanceManage.query_entity_by_identity"
BIND = "apps.module_link.services.monitor_cmdb.MonitorLinkService.bind"
CREATE_CI = "apps.module_link.services.monitor_cmdb.InstanceManage.instance_create"
ENSURE_ATTR = "apps.module_link.services.monitor_cmdb.ensure_model_monitor_id_attr"
PUSH = "apps.monitor.services.module_push.MonitorToCmdbPushService.push_instance"
CREATE_DONE = (
    "event=module_link_monitor_cmdb_task_completed task_id=%s total=%s ok=%s " "already_linked=%s not_found=%s conflict=%s failed=%s skipped_model=%s"
)
ROW_FAILED = "event=module_link_monitor_cmdb_row_failed monitor_id=%s failed_stage=%s error_type=%s"
ACTOR_SCOPE = {"allowed_org_ids": [1], "operator": "alice"}


def _request(*, superuser=True, cmdb_edit=True):
    permission = {"monitor": {"integration_list-View"}}
    if cmdb_edit:
        permission["cmdb"] = {"asset_info-Edit"}
    return SimpleNamespace(
        user=SimpleNamespace(
            username="alice",
            is_superuser=superuser,
            group_list=[{"id": 1}],
            permission=permission,
        ),
        COOKIES={"current_team": "1"},
    )


@pytest.fixture
def host_object():
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


def _instance(host_object, *, pk, name="mon-1", ip="10.0.0.1", cloud=1, cmdb_id=None):
    inst = MonitorInstance.objects.create(
        id=pk,
        name=name,
        monitor_object=host_object,
        ip=ip,
        cloud_region_id=cloud,
        cmdb_id=cmdb_id,
        is_deleted=False,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)
    return inst


def _patch_common(mocker):
    mocker.patch(AUTH, return_value=True)
    mocker.patch(SCOPE, return_value=ACTOR_SCOPE)
    mocker.patch(ENSURE_ATTR, return_value=True)


def test_over_limit_raises_without_creating(mocker, host_object):
    _patch_common(mocker)
    push = mocker.patch(PUSH)
    with pytest.raises(ValueError):
        MonitorCmdbTaskService.create([f"m-{i}" for i in range(BATCH_LIMIT + 1)], "Host", request=_request())
    push.assert_not_called()
    assert MonitorCmdbTask.objects.count() == 0


def test_unmapped_object_raises_without_creating(mocker, host_object):
    _patch_common(mocker)
    with pytest.raises(ValueError):
        MonitorCmdbTaskService.create(["m-1"], "Weblogic", request=_request())
    assert MonitorCmdbTask.objects.count() == 0
    assert CMDB_MODEL_TO_MONITOR_OBJECT["host"] == "Host"


def test_already_linked_does_not_change_ci_fields(mocker, host_object):
    _instance(host_object, pk="m-linked", cmdb_id="u-keep")
    _patch_common(mocker)
    entity = {"inst_uuid": "u-keep", "inst_name": "keep-name", "ip_addr": "10.0.0.9", "monitor_id": "m-linked"}
    mocker.patch(QUERY_UUID, return_value=entity)
    ident = mocker.patch(QUERY_IDENT)
    bind = mocker.patch(BIND)
    create_ci = mocker.patch(CREATE_CI)
    push = mocker.patch.object(MonitorToCmdbPushService, "push_instance")

    task = MonitorCmdbTaskService.create(["m-linked"], "Host", request=_request())
    item = task.items.get()
    assert item.status == "already_linked"
    assert item.cmdb_id == "u-keep"
    assert task.status == "completed"
    ident.assert_not_called()
    bind.assert_not_called()
    create_ci.assert_not_called()
    push.assert_not_called()


def test_identity_match_binds_without_creating_or_upserting(mocker, host_object, caplog):
    _instance(host_object, pk="m-ok", name="host-ok", ip="10.0.0.2")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(
        QUERY_IDENT,
        side_effect=lambda model_id, identity: (
            {} if "monitor_id" in identity else {"inst_uuid": "u-hit", "inst_name": "keep-name", "ip_addr": "10.0.0.2", "monitor_id": ""}
        ),
    )
    bind = mocker.patch(BIND, return_value={"status": "ok", "monitor_id": "m-ok"})
    create_ci = mocker.patch(CREATE_CI)
    update = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_update")

    with caplog.at_level(logging.INFO, logger="module-link"):
        task = MonitorCmdbTaskService.create(["m-ok"], "Host", request=_request())

    item = task.items.get()
    assert item.status == "ok"
    assert item.cmdb_id == "u-hit"
    bind.assert_called_once()
    create_ci.assert_not_called()
    update.assert_not_called()
    records = [row for row in caplog.records if row.msg == CREATE_DONE]
    assert len(records) == 1
    assert records[0].args[2:] == (1, 0, 0, 0, 0, 0)


def test_not_found_does_not_create_ci(mocker, host_object):
    _instance(host_object, pk="m-miss", ip="10.0.0.3")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI)

    task = MonitorCmdbTaskService.create(["m-miss"], "Host", request=_request())
    item = task.items.get()
    assert item.status == ITEM_NOT_FOUND
    assert task.status == "waiting_create"
    create_ci.assert_not_called()


def test_identity_conflict_does_not_merge(mocker, host_object):
    _instance(host_object, pk="m-conflict", ip="10.0.0.4")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)

    def _ident(model_id, identity):
        if "monitor_id" in identity:
            return {}
        raise BaseAppException("identity 查询结果不唯一")

    mocker.patch(QUERY_IDENT, side_effect=_ident)
    bind = mocker.patch(BIND)

    task = MonitorCmdbTaskService.create(["m-conflict"], "Host", request=_request())
    assert task.items.get().status == "conflict"
    bind.assert_not_called()


def test_unauthorized_row_is_failed_not_403(mocker, host_object):
    _instance(host_object, pk="m-deny")
    _patch_common(mocker)
    mocker.patch(AUTH, return_value=False)
    task = MonitorCmdbTaskService.create(["m-deny"], "Host", request=_request())
    item = task.items.get()
    assert item.status == "failed"
    assert item.message == "没有这条实例的操作权限"
    assert serialize_task(task)["items"][0]["message"] == item.message


def test_create_missing_writes_only_selected_not_found(mocker, host_object):
    _instance(host_object, pk="m-miss", name="to-create", ip="10.0.0.8")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-new", "inst_name": "to-create", "monitor_id": "m-miss"})
    bind = mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-miss"], "Host", request=_request())
    item = task.items.get()
    assert item.message == "没有按 IP+云区域命中主机"
    create_ci.assert_not_called()

    task = MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    item.refresh_from_db()
    assert item.status == "ok"
    assert item.cmdb_id == "u-new"
    assert item.message == ""
    assert task.status == "completed"
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["inst_name"] == "to-create"
    assert payload["ip_addr"] == "10.0.0.8"
    assert payload["monitor_id"] == "m-miss"
    assert payload["cloud"] == 1
    bind.assert_called()


def test_host_blank_cloud_uses_monitor_default_on_create(mocker, host_object):
    _instance(host_object, pk="m-nocloud", name="h-empty", ip="10.0.0.9", cloud=None)
    _patch_common(mocker)
    seen = []
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, side_effect=lambda model_id, identity: seen.append(identity) or {})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-def", "monitor_id": "m-nocloud"})
    bind = mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-nocloud"], "Host", request=_request())
    item = task.items.get()
    assert item.status == ITEM_NOT_FOUND
    assert item.cloud_region_id == CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
    assert any(row.get("ip_addr") == "10.0.0.9" and row.get("cloud") == CloudRegionConstants.DEFAULT_CLOUD_REGION_ID for row in seen)

    task = MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["cloud"] == CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
    bind.assert_called()


def test_create_missing_keeps_only_orgs_in_actor_scope(mocker, host_object):
    inst = _instance(host_object, pk="m-orgs", name="h-orgs", ip="10.0.0.33", cloud=None)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=2)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=4)
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-org", "monitor_id": "m-orgs"})
    mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-orgs"], "Host", request=_request())
    item = task.items.get()
    assert sorted(item.organization) == [1, 2, 4]

    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["organization"] == [1]
    assert payload["cloud"] == CloudRegionConstants.DEFAULT_CLOUD_REGION_ID


def test_host_blank_cloud_uses_node_cloud_for_identity(mocker, host_object):
    region = CloudRegion.objects.create(name="edge-region-7")
    Node.objects.create(
        id="node-7",
        name="node-7",
        ip="10.0.0.21",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
    )
    inst = _instance(host_object, pk="m-node-cloud", name="h-node", ip="10.0.0.21", cloud=None)
    inst.node_id = "node-7"
    inst.save(update_fields=["node_id"])
    _patch_common(mocker)
    seen = []
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, side_effect=lambda model_id, identity: seen.append(identity) or {})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-node", "monitor_id": "m-node-cloud"})
    mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-node-cloud"], "Host", request=_request())
    item = task.items.get()
    assert item.cloud_region_id == region.id
    assert any(row.get("ip_addr") == "10.0.0.21" and row.get("cloud") == region.id for row in seen)

    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["cloud"] == region.id


def test_host_blank_ip_uses_summary_facts(mocker, host_object):
    inst = _instance(host_object, pk="m-fact-ip", name="h-fact", ip=None)
    inst.summary_facts = {"asset.ip": "10.0.0.77"}
    inst.save(update_fields=["summary_facts"])
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-fact", "monitor_id": "m-fact-ip"})
    mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-fact-ip"], "Host", request=_request())
    item = task.items.get()
    assert item.ip == "10.0.0.77"

    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["ip_addr"] == "10.0.0.77"
    assert payload["cloud"] == CloudRegionConstants.DEFAULT_CLOUD_REGION_ID


def test_host_blank_ip_uses_node_ip(mocker, host_object):
    region = CloudRegion.objects.create(name="edge-region-ip")
    Node.objects.create(
        id="node-ip",
        name="node-ip",
        ip="10.0.0.88",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
    )
    inst = _instance(host_object, pk="m-node-ip", name="h-node-ip", ip=None, cloud=None)
    inst.node_id = "node-ip"
    inst.save(update_fields=["node_id"])
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-node-ip", "monitor_id": "m-node-ip"})
    mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-node-ip"], "Host", request=_request())
    item = task.items.get()
    assert item.ip == "10.0.0.88"

    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["ip_addr"] == "10.0.0.88"
    assert payload["cloud"] == region.id


def test_mysql_create_writes_name_org_ip_without_cloud(mocker):
    mysql = MonitorObject.objects.create(name="Mysql", display_name="Mysql", level="base")
    _instance(mysql, pk="m-mysql", name="db-1", ip="10.0.0.5")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI, return_value={"inst_uuid": "u-mysql", "monitor_id": "m-mysql"})
    mocker.patch(BIND, return_value={"status": "ok"})

    task = MonitorCmdbTaskService.create(["m-mysql"], "Mysql", request=_request())
    item = task.items.get()
    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    payload = create_ci.call_args.kwargs["instance_info"]
    assert payload["inst_name"] == "db-1"
    assert payload["organization"] == [1]
    assert payload["ip_addr"] == "10.0.0.5"
    assert payload["monitor_id"] == "m-mysql"
    assert "cloud" not in payload


def test_create_missing_without_cmdb_edit_fails_row(mocker, host_object):
    _instance(host_object, pk="m-miss2", ip="10.0.0.11")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    create_ci = mocker.patch(CREATE_CI)

    task = MonitorCmdbTaskService.create(["m-miss2"], "Host", request=_request())
    item = task.items.get()
    task = MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request(superuser=False, cmdb_edit=False))
    item.refresh_from_db()
    assert item.status == "failed"
    assert item.message == "没有 CMDB 资产编辑权限"
    create_ci.assert_not_called()


def test_cancel_keeps_pointers(mocker, host_object):
    _instance(host_object, pk="m-ok2", ip="10.0.0.12")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(
        QUERY_IDENT,
        side_effect=lambda model_id, identity: ({} if "monitor_id" in identity else {"inst_uuid": "u-hit2", "monitor_id": ""}),
    )
    mocker.patch(BIND, return_value={"status": "ok"})
    task = MonitorCmdbTaskService.create(["m-ok2"], "Host", request=_request())
    MonitorCmdbTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == STATUS_CANCELLED
    assert task.items.get().cmdb_id == "u-hit2"


def test_recycle_deletes_expired_task_and_does_not_clear_cmdb_id(mocker, host_object):
    _instance(host_object, pk="m-ok3", cmdb_id="u-keep3")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value={"inst_uuid": "u-keep3", "monitor_id": "m-ok3"})
    update = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_update")
    task = MonitorCmdbTaskService.create(["m-ok3"], "Host", request=_request())
    task.retain_until = timezone.now() - timedelta(days=1)
    task.save(update_fields=["retain_until"])
    deleted = MonitorCmdbTaskService.recycle_expired()
    assert deleted == 1
    assert not MonitorCmdbTask.objects.filter(id=task.id).exists()
    assert not MonitorCmdbTaskItem.objects.filter(task_id=task.id).exists()
    update.assert_not_called()


def test_query_failure_log_stays_one_line(mocker, host_object, caplog):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    _instance(host_object, pk="m-1\r\nINJECTED", cmdb_id="u-x")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, side_effect=RuntimeError(secret))
    with caplog.at_level(logging.ERROR, logger="module-link"):
        task = MonitorCmdbTaskService.create(["m-1\r\nINJECTED"], "Host", request=_request())
    item = task.items.get()
    assert item.status == "failed"
    assert item.message == "查询配置项失败"
    assert secret not in item.message
    records = [row for row in caplog.records if row.msg == ROW_FAILED]
    assert len(records) == 1
    record = records[0]
    assert record.args[0] == "m-1  INJECTED"
    assert record.args[1] == "query_entity"
    assert record.args[2] == "RuntimeError"
    assert str(record.exc_info[1]) == "module link monitor cmdb row failed"
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert "\n" not in record.getMessage()


def test_create_missing_stores_business_exception_message(mocker, host_object):
    _instance(host_object, pk="m-org-fail", name="h-org-fail", ip="10.0.0.44")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    mocker.patch(CREATE_CI, side_effect=BaseAppException("organization [2, 4] 不在当前选择组织范围内"))

    task = MonitorCmdbTaskService.create(["m-org-fail"], "Host", request=_request())
    item = task.items.get()
    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    item.refresh_from_db()
    assert item.status == "failed"
    assert item.message == "organization [2, 4] 不在当前选择组织范围内"


def test_create_missing_runtime_error_uses_stage_sentence(mocker, host_object):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    _instance(host_object, pk="m-boom", name="h-boom", ip="10.0.0.45")
    _patch_common(mocker)
    mocker.patch(QUERY_UUID, return_value=None)
    mocker.patch(QUERY_IDENT, return_value={})
    mocker.patch(CREATE_CI, side_effect=RuntimeError(secret))

    task = MonitorCmdbTaskService.create(["m-boom"], "Host", request=_request())
    item = task.items.get()
    MonitorCmdbTaskService.create_missing(task, [str(item.id)], request=_request())
    item.refresh_from_db()
    assert item.status == "failed"
    assert item.message == "新建配置项失败"
    assert secret not in item.message
