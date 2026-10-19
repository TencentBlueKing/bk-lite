import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT
from apps.module_link.constants import BATCH_LIMIT, ITEM_NEEDS_OBJECT, ITEM_NOT_FOUND, STATUS_CANCELLED
from apps.module_link.models import ModuleLinkModelMap, MonitorAccessDraft, MonitorLinkTask, MonitorLinkTaskItem
from apps.module_link.services.cmdb_monitor import CmdbMonitorTaskService, can_see_task, resolved_current_team, serialize_draft

pytestmark = pytest.mark.django_db

QUERY = "apps.module_link.services.cmdb_monitor.InstanceManage.query_entity_by_uuid"
PUSH = "apps.module_link.services.cmdb_monitor.MonitorLinkService.batch_push"
AUTH = "apps.module_link.services.cmdb_monitor._is_uuid_authorized"
SCOPE = "apps.module_link.services.cmdb_monitor.build_cmdb_push_actor_scope"
MONITOR = "apps.module_link.services.cmdb_monitor.Monitor"
BACKFILL = "apps.module_link.services.cmdb_monitor.CmdbToMonitorPushService._backfill_monitor_id"
CREATE_DONE = (
    "event=module_link_cmdb_monitor_task_completed task_id=%s total=%s ok=%s "
    "already_linked=%s not_found=%s conflict=%s failed=%s skipped_model=%s needs_object=%s"
)
RECYCLE_DONE = "event=module_link_recycle_completed deleted=%s"
ACTOR_SCOPE = {"allowed_org_ids": [1], "operator": "alice"}


def _request():
    return SimpleNamespace(
        user=SimpleNamespace(username="alice", is_superuser=True, group_list=[{"id": 1}]),
        COOKIES={"current_team": "1"},
    )


def _entity(inst_uuid, *, model_id="host", monitor_id="", **extra):
    row = {
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": extra.pop("inst_name", inst_uuid),
        "ip": extra.pop("ip", "10.0.0.1"),
        "organization": extra.pop("organization", [1]),
        "monitor_id": monitor_id,
    }
    row.update(extra)
    return row


def _patch_common(mocker, entities):
    mocker.patch(AUTH, return_value=True)
    mocker.patch(SCOPE, return_value=ACTOR_SCOPE)
    mocker.patch(QUERY, side_effect=lambda inst_uuid: entities.get(inst_uuid))
    mocker.patch(
        BACKFILL,
        side_effect=lambda entity, monitor_id, **kwargs: {**entity, "monitor_id": monitor_id},
    )


def test_over_limit_raises_without_creating(mocker):
    mocker.patch(AUTH, return_value=True)
    mocker.patch(SCOPE, return_value=ACTOR_SCOPE)
    push = mocker.patch(PUSH)
    with pytest.raises(ValueError):
        CmdbMonitorTaskService.create([f"u-{i}" for i in range(BATCH_LIMIT + 1)], request=_request())
    push.assert_not_called()
    assert MonitorLinkTask.objects.count() == 0


def test_buckets_and_drafts(mocker, caplog):
    entities = {
        "u-ok": _entity("u-ok"),
        "u-linked": _entity("u-linked", monitor_id="m-keep"),
        "u-miss": _entity("u-miss"),
        "u-conflict": _entity("u-conflict"),
        "u-skip": _entity("u-skip", model_id="k8s_cluster"),
        "u-custom": _entity("u-custom", model_id="weblogic"),
        "u-fail": _entity("u-fail"),
    }
    _patch_common(mocker, entities)
    mocker.patch(
        AUTH,
        side_effect=lambda request, inst_uuid: inst_uuid != "u-fail",
    )
    mocker.patch(
        PUSH,
        return_value={
            "results": [
                {"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-new"},
                {"inst_uuid": "u-miss", "status": "not_found", "monitor_id": None},
                {"inst_uuid": "u-conflict", "status": "conflict", "monitor_id": None},
            ]
        },
    )

    with caplog.at_level(logging.INFO, logger="module-link"):
        task = CmdbMonitorTaskService.create(
            ["u-ok", "u-linked", "u-miss", "u-conflict", "u-skip", "u-custom", "u-fail"],
            request=_request(),
        )

    by_uuid = {item.inst_uuid: item for item in task.items.all()}
    assert by_uuid["u-ok"].status == "ok"
    assert by_uuid["u-linked"].status == "already_linked"
    assert by_uuid["u-miss"].status == ITEM_NOT_FOUND
    assert by_uuid["u-conflict"].status == "conflict"
    assert by_uuid["u-skip"].status == "skipped_model"
    assert by_uuid["u-custom"].status == ITEM_NEEDS_OBJECT
    assert by_uuid["u-fail"].status == "failed"
    drafts = list(task.drafts.all())
    assert len(drafts) == 1
    assert drafts[0].object_name == "Host"
    assert drafts[0].rows[0]["cmdb_id"] == "u-miss"
    assert "password" not in drafts[0].rows[0]
    assert task.status == "waiting_access"
    assert CMDB_MODEL_TO_MONITOR_OBJECT["host"] == "Host"
    records = [row for row in caplog.records if row.msg == CREATE_DONE]
    assert len(records) == 1
    assert records[0].args[2:] == (1, 1, 1, 1, 1, 1, 1)


def test_already_linked_and_conflict_do_not_enter_draft(mocker):
    entities = {
        "u-linked": _entity("u-linked", monitor_id="m-keep"),
        "u-conflict": _entity("u-conflict"),
    }
    _patch_common(mocker, entities)
    mocker.patch(
        PUSH,
        return_value={"results": [{"inst_uuid": "u-conflict", "status": "conflict", "monitor_id": None}]},
    )
    task = CmdbMonitorTaskService.create(["u-linked", "u-conflict"], request=_request())
    assert task.drafts.count() == 0
    assert task.status == "completed"


def test_assign_object_unique_name_then_draft(mocker):
    entities = {"u-custom": _entity("u-custom", model_id="weblogic", inst_name="wl-1")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH)
    monitor = mocker.patch(MONITOR)
    monitor.return_value.list_cmdb_bind_candidates.return_value = []
    task = CmdbMonitorTaskService.create(["u-custom"], request=_request())
    item = task.items.get()
    assert item.status == ITEM_NEEDS_OBJECT

    monitor.return_value.list_cmdb_bind_candidates.return_value = [
        {"id": "m-1", "name": "wl-1", "cmdb_id": None},
    ]
    monitor.return_value.bind_cmdb_id.return_value = {"status": "ok", "monitor_id": "m-1"}
    task = CmdbMonitorTaskService.assign_object(
        task,
        item_ids=[str(item.id)],
        object_name="Tomcat",
        remember=True,
        request=_request(),
        current_team=1,
    )
    item.refresh_from_db()
    assert item.status == "ok"
    assert item.object_name == "Tomcat"
    assert ModuleLinkModelMap.objects.get(team=1, model_id="weblogic").object_name == "Tomcat"
    assert task.drafts.count() == 0


def test_assign_object_without_unique_name_creates_draft(mocker):
    entities = {"u-custom": _entity("u-custom", model_id="weblogic", inst_name="wl-1")}
    _patch_common(mocker, entities)
    monitor = mocker.patch(MONITOR)
    monitor.return_value.list_cmdb_bind_candidates.return_value = []
    task = CmdbMonitorTaskService.create(["u-custom"], request=_request())
    item = task.items.get()
    task = CmdbMonitorTaskService.assign_object(
        task,
        item_ids=[str(item.id)],
        object_name="Tomcat",
        remember=False,
        request=_request(),
        current_team=1,
    )
    item.refresh_from_db()
    assert item.status == ITEM_NOT_FOUND
    draft = task.drafts.get()
    assert draft.object_name == "Tomcat"
    assert draft.rows[0]["instance_name"] == "wl-1"
    assert ModuleLinkModelMap.objects.count() == 0


def test_cancel_hides_draft(mocker):
    entities = {"u-miss": _entity("u-miss")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-miss", "status": "not_found", "monitor_id": None}]})
    task = CmdbMonitorTaskService.create(["u-miss"], request=_request())
    draft_id = task.drafts.get().id
    CmdbMonitorTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == STATUS_CANCELLED
    assert CmdbMonitorTaskService.get_draft(draft_id, request=_request()) is None


def test_refresh_promotes_linked_not_found(mocker):
    entities = {"u-miss": _entity("u-miss")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-miss", "status": "not_found", "monitor_id": None}]})
    task = CmdbMonitorTaskService.create(["u-miss"], request=_request())
    entities["u-miss"] = _entity("u-miss", monitor_id="m-later")
    task = CmdbMonitorTaskService.refresh(task)
    assert task.items.get().status == "ok"
    assert task.drafts.count() == 0
    assert task.status == "completed"


def test_recycle_deletes_expired_task_and_does_not_clear_monitor_id(mocker, caplog):
    entities = {"u-ok": _entity("u-ok")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-new"}]})
    update = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_update")
    task = CmdbMonitorTaskService.create(["u-ok"], request=_request())
    task.retain_until = timezone.now() - timedelta(days=1)
    task.save(update_fields=["retain_until"])
    with caplog.at_level(logging.INFO, logger="module-link"):
        deleted = CmdbMonitorTaskService.recycle_expired()
    assert deleted == 1
    assert not MonitorLinkTask.objects.filter(id=task.id).exists()
    assert not MonitorLinkTaskItem.objects.filter(task_id=task.id).exists()
    assert not MonitorAccessDraft.objects.filter(task_id=task.id).exists()
    update.assert_not_called()
    records = [row for row in caplog.records if row.msg == RECYCLE_DONE]
    assert len(records) == 1
    assert records[0].args == (1,)


def test_recycle_skips_unexpired(mocker):
    entities = {"u-ok": _entity("u-ok")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-new"}]})
    task = CmdbMonitorTaskService.create(["u-ok"], request=_request())
    assert CmdbMonitorTaskService.recycle_expired() == 0
    assert MonitorLinkTask.objects.filter(id=task.id).exists()


def test_draft_payload_has_no_password(mocker):
    entities = {"u-miss": _entity("u-miss", password="SECRET-PAYLOAD-DO-NOT-LOG")}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-miss", "status": "not_found", "monitor_id": None}]})
    task = CmdbMonitorTaskService.create(["u-miss"], request=_request())
    payload = serialize_draft(task.drafts.get())
    assert "password" not in str(payload)
    assert payload["rows"][0]["cmdb_id"] == "u-miss"
    assert payload["rows"][0]["ip"] == "10.0.0.1"
    assert payload["rows"][0]["instance_name"] == "u-miss"


def _visibility_request(*, username="bob", team=2, superuser=False, domain="domain.com"):
    return SimpleNamespace(
        user=SimpleNamespace(
            username=username,
            domain=domain,
            is_superuser=superuser,
            group_list=[{"id": team}],
        ),
        COOKIES={"current_team": str(team)},
    )


def _stored_task(team):
    return MonitorLinkTask.objects.create(
        operator="alice",
        team=team,
        status="waiting_access",
        summary={},
        retain_until=timezone.now() + timedelta(days=7),
    )


def test_resolved_current_team_rejects_foreign_cookie():
    request = _visibility_request(username="alice", team=1)
    request.COOKIES["current_team"] = "99"
    assert resolved_current_team(request) is None


def test_resolved_current_team_accepts_owned_cookie():
    request = _visibility_request(username="alice", team=1)
    assert resolved_current_team(request) == 1


def test_can_see_task_requires_overlapping_org():
    task = SimpleNamespace(operator="alice", team=[1])
    other = _visibility_request(username="alice", team=2)
    assert can_see_task(task, other, {"allowed_org_ids": [2], "operator": "alice"}) is False
    same = _visibility_request(username="carol", team=1)
    assert can_see_task(task, same, {"allowed_org_ids": [1], "operator": "carol"}) is True


def test_get_task_hides_same_operator_other_team(mocker):
    task = _stored_task([1])
    request = _visibility_request(username="alice", team=2)
    mocker.patch(SCOPE, return_value={"allowed_org_ids": [2], "operator": "alice"})
    assert CmdbMonitorTaskService.get_task(task.id, request=request) is None


def test_get_draft_hides_other_team(mocker):
    task = _stored_task([1])
    draft = MonitorAccessDraft.objects.create(
        task=task,
        object_name="Host",
        rows=[{"cmdb_id": "u-1", "ip": "10.0.0.1"}],
        expires_at=task.retain_until,
    )
    request = _visibility_request(username="bob", team=2)
    mocker.patch(SCOPE, return_value={"allowed_org_ids": [2], "operator": "bob"})
    assert CmdbMonitorTaskService.get_draft(draft.id, request=request) is None


def test_create_ignores_foreign_team_model_map(mocker):
    ModuleLinkModelMap.objects.create(team=99, model_id="weblogic", object_name="Tomcat")
    entities = {"u-custom": _entity("u-custom", model_id="weblogic")}
    _patch_common(mocker, entities)
    monitor = mocker.patch(MONITOR)
    request = _visibility_request(username="alice", team=1)
    request.COOKIES["current_team"] = "99"
    task = CmdbMonitorTaskService.create(["u-custom"], request=request)
    monitor.assert_not_called()
    item = task.items.get()
    assert item.status == ITEM_NEEDS_OBJECT
    assert item.object_name == ""


def test_assign_object_remember_ignores_foreign_team(mocker):
    entities = {"u-custom": _entity("u-custom", model_id="weblogic", inst_name="wl-1")}
    _patch_common(mocker, entities)
    monitor = mocker.patch(MONITOR)
    monitor.return_value.list_cmdb_bind_candidates.return_value = []
    task = CmdbMonitorTaskService.create(["u-custom"], request=_request())
    item = task.items.get()
    request = _visibility_request(username="alice", team=1)
    CmdbMonitorTaskService.assign_object(
        task,
        item_ids=[str(item.id)],
        object_name="Tomcat",
        remember=True,
        request=request,
        current_team=99,
    )
    assert ModuleLinkModelMap.objects.filter(team=99).count() == 0
    assert ModuleLinkModelMap.objects.filter(team=1).count() == 0


def test_draft_payload_includes_port(mocker):
    entities = {"u-mysql": _entity("u-mysql", model_id="mysql", inst_name="db-1", ip="10.0.0.9", port=3306)}
    _patch_common(mocker, entities)
    mocker.patch(PUSH, return_value={"results": [{"inst_uuid": "u-mysql", "status": "not_found", "monitor_id": None}]})
    task = CmdbMonitorTaskService.create(["u-mysql"], request=_request())
    payload = serialize_draft(task.drafts.get())
    assert payload["rows"][0]["ip"] == "10.0.0.9"
    assert payload["rows"][0]["port"] == "3306"
