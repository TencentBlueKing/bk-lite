"""负责人交接：用原型中的人员与实例验证预览、替换、部分失败和审计。"""

import logging
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.change_record import INSTANCE_EDIT_CORRECTABLE_SCENARIOS, OWNER_HANDOVER
from apps.cmdb.models.owner_handover import OwnerHandoverTask
from apps.cmdb.services.owner_handover import OwnerHandoverRejected, OwnerHandoverService, UserDirectory, allows_instance, as_user_ids
from apps.cmdb.services.owner_handover_graph import GraphOwnerCatalog, InstanceHandoverWriter
from apps.cmdb.utils.change_record import _MIRROR_SCENARIOS
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.owner_handover import OwnerHandoverPreviewView, OwnerHandoverTaskCreateView
from apps.system_mgmt.models.user import EmploymentStatus
from apps.system_mgmt.models.user import User as DirectoryUser

ZHANG = 3
LI = 4
WANG = 5
ZHAO = 6
SENTINEL = "SENTINEL-OWNER-HANDOVER"


class MemoryDirectory:
    def __init__(self):
        self.people = {
            ZHANG: _person(ZHANG, "zhangsan", "张三", employment_status=EmploymentStatus.RESIGNED),
            LI: _person(LI, "lisi", "李四", employment_status=EmploymentStatus.EMPLOYED),
            WANG: _person(WANG, "wangwu", "王五", employment_status=EmploymentStatus.EMPLOYED),
            ZHAO: _person(ZHAO, "zhaoliu", "赵六", disabled=True, employment_status=EmploymentStatus.EMPLOYED),
        }

    def get(self, user_id):
        return self.people.get(int(user_id))


class MemoryCatalog:
    def __init__(self, instances):
        self.instances = instances

    def list_models(self):
        return [
            {
                "model_id": "host",
                "model_name": "主机",
                "fields": [
                    {"attr_id": "operator", "attr_name": "主要维护人"},
                    {"attr_id": "bak_operator", "attr_name": "备份维护人"},
                ],
            },
            {"model_id": "application", "model_name": "应用", "fields": [{"attr_id": "operator", "attr_name": "主要维护人"}]},
        ]

    def find_instances(self, model_id, user_id, field_ids):
        return [
            item
            for item in self.instances
            if item["model_id"] == model_id and any(user_id in as_user_ids(item.get(field_id)) for field_id in field_ids)
        ]

    def get_instance(self, model_id, inst_uuid):
        for item in self.instances:
            if item["model_id"] == model_id and item.get("inst_uuid") == inst_uuid:
                return item
        return None


class RecordingWriter:
    def __init__(self, fail_names=()):
        self.fail_names = set(fail_names)
        self.applied = []

    def apply(self, instance, changes, operator, source_label):
        if instance["inst_name"] in self.fail_names:
            raise RuntimeError("write failed")
        instance.update(changes)
        self.applied.append((instance["inst_name"], dict(changes), operator, source_label))


def _person(user_id, username, display_name, *, disabled=False, employment_status=EmploymentStatus.EMPLOYED):
    return {
        "id": user_id,
        "username": username,
        "display_name": display_name,
        "disabled": disabled,
        "employment_status": employment_status,
    }


def _instances():
    return [
        {
            "model_id": "host",
            "inst_uuid": "u-host-1",
            "inst_name": "web-prod-01",
            "organization": [1],
            "organization_display": "运维一组",
            "operator": [ZHANG],
            "bak_operator": [],
            "note": SENTINEL,
        },
        {
            "model_id": "host",
            "inst_uuid": "u-host-2",
            "inst_name": "web-prod-02",
            "organization": [1],
            "organization_display": "运维一组",
            "operator": [ZHANG, WANG],
            "bak_operator": [ZHANG],
        },
        {
            "model_id": "application",
            "inst_uuid": "u-app-1",
            "inst_name": "订单中心",
            "organization": [1],
            "organization_display": "业务平台",
            "operator": [ZHANG],
        },
        {
            "model_id": "host",
            "inst_uuid": "u-host-secret",
            "inst_name": "secret-host",
            "organization": [9],
            "organization_display": "其他组",
            "operator": [ZHANG],
        },
        {
            "model_id": "host",
            "inst_uuid": "u-host-dedupe",
            "inst_name": "db-01",
            "organization": [1],
            "organization_display": "运维一组",
            "operator": [ZHANG, LI],
            "bak_operator": [],
        },
    ]


def _actor():
    return SimpleNamespace(username="admin", domain="domain.com", is_superuser=False, group_list=[{"id": 1}], group_tree=[])


def _service(instances, writer, dispatch=None):
    return OwnerHandoverService(
        MemoryCatalog(instances),
        writer,
        MemoryDirectory(),
        lambda instance: 1 in (instance.get("organization") or []),
        _actor(),
        1,
        False,
        dispatch=dispatch or (lambda *_args: None),
    )


def _by_name(instances, name):
    return next(item for item in instances if item["inst_name"] == name)


def _preview(service, from_user_id, to_user_id, model_ids=None, **kwargs):
    kwargs.setdefault("attr_id", "operator")
    kwargs.setdefault("attr_name", "主要维护人")
    return service.preview(from_user_id, to_user_id, model_ids, **kwargs)


@pytest.mark.django_db
def test_preview_lists_prototype_assets_and_keeps_co_owners():
    instances = _instances()
    preview = _preview(_service(instances, RecordingWriter()), ZHANG, LI, ["host", "application", "network_device"])

    assert preview["total"] == 4
    assert preview["excluded_no_permission"] == 1
    assert preview["inapplicable_models"] == [{"model_id": "network_device", "model_name": "network_device"}]
    assert preview["by_model"] == [
        {"model_id": "host", "model_name": "主机", "count": 3},
        {"model_id": "application", "model_name": "应用", "count": 1},
    ]
    assert preview["from_user"]["label"] == "张三(zhangsan)"
    assert preview["to_user"]["label"] == "李四(lisi)"
    rows = {item["inst_name"]: item for item in preview["items"]}
    assert rows["web-prod-01"]["organization"] == "运维一组"
    assert rows["web-prod-01"]["changes"] == [{"attr_id": "operator", "attr_name": "主要维护人", "before": "张三(zhangsan)", "after": "李四(lisi)"}]
    host_two = {item["attr_id"]: item for item in rows["web-prod-02"]["changes"]}
    assert host_two["operator"]["before"] == "张三(zhangsan), 王五(wangwu)"
    assert host_two["operator"]["after"] == "李四(lisi), 王五(wangwu)"
    assert "bak_operator" not in host_two
    assert rows["db-01"]["changes"][0]["after"] == "李四(lisi)"
    assert rows["订单中心"]["organization"] == "业务平台"
    assert "secret-host" not in rows


@pytest.mark.django_db
def test_handover_changes_only_the_selected_user_field():
    instances = _instances()
    service = _service(instances, RecordingWriter())
    operator_preview = _preview(service, ZHANG, LI, ["host"])
    host_two = next(item for item in operator_preview["items"] if item["inst_name"] == "web-prod-02")
    assert [item["attr_id"] for item in host_two["changes"]] == ["operator"]

    payload, _created = service.submit(operator_preview["preview_token"], "only-operator")
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)
    assert result["status"] == "succeeded"
    assert _by_name(instances, "web-prod-02")["operator"] == [LI, WANG]
    assert _by_name(instances, "web-prod-02")["bak_operator"] == [ZHANG]

    backup = service.preview(ZHANG, LI, attr_id="bak_operator", attr_name="备份维护人")
    assert backup["total"] == 1
    assert backup["by_model"] == [{"model_id": "host", "model_name": "主机", "count": 1}]
    assert backup["items"][0]["changes"] == [{"attr_id": "bak_operator", "attr_name": "备份维护人", "before": "张三(zhangsan)", "after": "李四(lisi)"}]

    narrowed = service.preview(ZHANG, LI, ["application"], attr_id="bak_operator", attr_name="备份维护人")
    assert narrowed["total"] == 0
    assert narrowed["inapplicable_models"] == [{"model_id": "application", "model_name": "应用"}]

    with pytest.raises(OwnerHandoverRejected) as missing:
        service.preview(ZHANG, LI)
    assert missing.value.code == "field_required"


@pytest.mark.django_db
def test_resigning_source_is_allowed_and_inactive_target_is_rejected():
    service = _service(_instances(), RecordingWriter())
    preview = _preview(service, ZHANG, LI)
    assert preview["from_user"]["employment_status"] == EmploymentStatus.RESIGNED

    with pytest.raises(OwnerHandoverRejected) as same_user:
        _preview(service, LI, LI)
    assert same_user.value.code == "same_user"

    with pytest.raises(OwnerHandoverRejected) as inactive:
        _preview(service, ZHANG, ZHAO)
    assert inactive.value.code == "target_inactive"


@pytest.mark.django_db
def test_execute_keeps_successes_when_one_instance_fails(caplog):
    instances = _instances()
    writer = RecordingWriter(fail_names={"web-prod-02"})
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["host", "application"])
    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        payload, created = service.submit(preview["preview_token"], "handover-zhang-to-li")
        assert created is True
        task = OwnerHandoverTask.objects.get(pk=payload["id"])
        result = service.execute(task.id, task.execution_token)

    assert result["status"] == "partial_failed"
    assert result["success_count"] == 3
    assert result["failed_count"] == 1
    assert [name for name, *_rest in writer.applied] == ["db-01", "web-prod-01", "订单中心"]
    assert _by_name(instances, "web-prod-01")["operator"] == [LI]
    assert _by_name(instances, "web-prod-02")["operator"] == [ZHANG, WANG]
    assert _by_name(instances, "web-prod-02")["bak_operator"] == [ZHANG]
    assert _by_name(instances, "订单中心")["operator"] == [LI]
    assert _by_name(instances, "db-01")["operator"] == [LI]
    assert _by_name(instances, "secret-host")["operator"] == [ZHANG]
    failures = service.list_failures(task.id)
    assert failures["count"] == 1
    assert failures["items"][0]["inst_name"] == "web-prod-02"
    assert failures["items"][0]["reason_code"] == "write_failed"
    assert writer.applied[0][3] == "张三(zhangsan) → 李四(lisi)"
    write_logs = [record for record in caplog.records if record.levelno == logging.DEBUG]
    finish_logs = [record for record in caplog.records if record.levelno == logging.INFO and record.name == "cmdb"]
    assert write_logs[0].msg == ("owner handover instance failed, handover_id=%s, inst_uuid=%s, failed_stage=%s, error_type=%s")
    assert write_logs[0].args == (task.pk, "u-host-2", "write", "RuntimeError")
    assert finish_logs[-1].msg == ("owner handover finished, handover_id=%s, status=%s, success=%s, skipped=%s, failed=%s")
    assert finish_logs[-1].args[1:] == ("partial_failed", 3, 0, 1)
    assert SENTINEL not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.django_db
def test_owner_changed_before_write_is_skipped_and_not_overwritten():
    instances = _instances()

    class StaleCatalog(MemoryCatalog):
        def get_instance(self, model_id, inst_uuid):
            item = super().get_instance(model_id, inst_uuid)
            if item and item["inst_name"] == "web-prod-01":
                return {**item, "operator": [WANG], "bak_operator": []}
            return item

    service = OwnerHandoverService(
        StaleCatalog(instances),
        RecordingWriter(),
        MemoryDirectory(),
        lambda instance: 1 in (instance.get("organization") or []),
        _actor(),
        1,
        False,
    )
    preview = _preview(service, ZHANG, LI, ["host"])
    payload, _created = service.submit(preview["preview_token"], "stale-key")
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)

    assert _by_name(instances, "web-prod-01")["operator"] == [ZHANG]
    assert result["skipped_count"] == 1
    assert result["success_count"] == 2
    assert result["status"] == "succeeded"
    statuses = {row["inst_uuid"]: row["transfer_status"] for row in service.list_outcome_statuses(task.id, ["u-host-1", "u-host-dedupe"])}
    assert statuses["u-host-1"] == "pending"
    assert statuses["u-host-dedupe"] == "succeeded"


@pytest.mark.django_db
def test_same_idempotency_key_returns_the_original_task(django_capture_on_commit_callbacks):
    instances = _instances()
    calls = []
    service = _service(instances, RecordingWriter(), dispatch=lambda task_id, token: calls.append((task_id, token)))
    preview = _preview(service, ZHANG, LI, ["application"])
    with django_capture_on_commit_callbacks(execute=True):
        first, created = service.submit(preview["preview_token"], "same-key")
    assert created is True
    assert len(calls) == 1
    again, created_again = service.submit(preview["preview_token"], "same-key")
    assert created_again is False
    assert again["id"] == first["id"]
    assert len(calls) == 1

    other = _service(instances, RecordingWriter())
    other_preview = _preview(other, ZHANG, WANG, ["application"])
    with pytest.raises(OwnerHandoverRejected) as conflict:
        other.submit(other_preview["preview_token"], "same-key")
    assert conflict.value.code == "idempotency_conflict"


@pytest.mark.django_db
def test_second_handover_for_the_same_person_is_rejected_while_the_first_is_queued():
    instances = _instances()
    service = _service(instances, RecordingWriter())
    preview = _preview(service, ZHANG, LI, ["application"])
    service.submit(preview["preview_token"], "first-key")
    second = _preview(service, ZHANG, WANG, ["host"])
    with pytest.raises(OwnerHandoverRejected) as busy:
        service.submit(second["preview_token"], "second-key")
    assert busy.value.code == "handover_busy"


@pytest.mark.django_db
def test_directory_keeps_resigned_sources_and_hides_them_from_targets():
    DirectoryUser.objects.create(
        username="zhangsan",
        display_name="张三",
        email="zhangsan@example.com",
        password="not-used",
        domain="domain.com",
        employment_status=EmploymentStatus.RESIGNED,
    )
    DirectoryUser.objects.create(
        username="lisi",
        display_name="李四",
        email="lisi@example.com",
        password="not-used",
        domain="domain.com",
        employment_status=EmploymentStatus.EMPLOYED,
    )
    DirectoryUser.objects.create(
        username="zhaoliu",
        display_name="赵六",
        email="zhaoliu@example.com",
        password="not-used",
        domain="domain.com",
        disabled=True,
        employment_status=EmploymentStatus.EMPLOYED,
    )
    directory = UserDirectory("domain.com")
    sources = {row["username"] for row in directory.search("from", "三")}
    targets = {row["username"] for row in directory.search("to", "")}
    assert sources == {"zhangsan"}
    assert targets == {"lisi"}


def test_graph_catalog_merges_user_fields_with_membership_query():
    calls = []

    class Graph:
        def query_entity(self, label, params, page=None, **kwargs):
            calls.append(params)
            field = params[1]["field"]
            if field == "operator":
                return [{"inst_uuid": "u-1", "inst_name": "web-prod-01", "operator": [ZHANG], "model_id": "host"}], 1
            return [{"inst_uuid": "u-1", "inst_name": "web-prod-01", "bak_operator": [ZHANG], "model_id": "host"}], 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    catalog = GraphOwnerCatalog(graph_factory=lambda: Graph(), model_search=lambda: [])
    rows = catalog.find_instances("host", ZHANG, ["operator", "bak_operator"])

    assert len(rows) == 1
    assert calls[0][1] == {"field": "operator", "type": "list_any[]", "value": [ZHANG]}
    assert calls[1][1]["type"] == "list_any[]"


def test_graph_catalog_keeps_only_user_type_fields():
    catalog = GraphOwnerCatalog(
        model_search=lambda: [
            {
                "model_id": "host",
                "model_name": "主机",
                "attrs": [
                    {"attr_id": "operator", "attr_name": "主要维护人", "attr_type": "user"},
                    {"attr_id": "owner", "attr_name": "负责人", "attr_type": "str"},
                    {"attr_id": "operator_display", "attr_name": "展示", "attr_type": "user", "is_display_field": True},
                ],
            },
            {"model_id": "network_device", "model_name": "网络设备", "attrs": [{"attr_id": "name", "attr_type": "str"}]},
        ]
    )
    assert catalog.list_models() == [{"model_id": "host", "model_name": "主机", "fields": [{"attr_id": "operator", "attr_name": "主要维护人"}]}]


def test_writer_updates_only_user_fields_without_relation_reconcile(monkeypatch):
    captured = {}

    def update(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"inst_name": "web-prod-01"}

    monkeypatch.setattr("apps.cmdb.services.owner_handover_graph.InstanceManage.instance_update_by_uuid", update)
    monkeypatch.setattr(CmdbRulesFormatUtil, "get_authorized_team_ids", staticmethod(lambda *args, **kwargs: [1]))
    writer = InstanceHandoverWriter(SimpleNamespace(roles=["admin"]), 1, False)
    writer.apply(
        {"inst_uuid": "u-host-1"},
        {"operator": [LI]},
        "admin",
        "张三(zhangsan) → 李四(lisi)",
    )

    assert captured["args"][2] == "u-host-1"
    assert captured["args"][3] == {"operator": [LI]}
    assert captured["kwargs"]["scenario"] == OWNER_HANDOVER
    assert captured["kwargs"]["schedule_post_actions"] is False
    assert captured["kwargs"]["audit_action"] == "负责人交接"
    assert captured["kwargs"]["audit_source"] == "张三(zhangsan) → 李四(lisi)"


@pytest.mark.django_db
def test_cancel_before_start_keeps_the_original_owner():
    instances = _instances()
    writer = RecordingWriter()
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["application"])
    payload, _created = service.submit(preview["preview_token"], "cancel-key")
    cancelled = service.cancel(payload["id"])
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)

    assert cancelled["status"] == "cancelled"
    assert result["status"] == "cancelled"
    assert writer.applied == []
    assert _by_name(instances, "订单中心")["operator"] == [ZHANG]


def test_owner_handover_task_is_registered_on_the_background_queue():
    from apps.core.celery_runtime.manifest import TASK_ROUTES

    assert TASK_ROUTES["apps.cmdb.tasks.owner_handover.execute_owner_handover"] == "background"


def test_handover_scenario_stays_in_cmdb_log_and_cannot_be_corrected():
    assert OWNER_HANDOVER == "owner_handover"
    assert OWNER_HANDOVER not in INSTANCE_EDIT_CORRECTABLE_SCENARIOS
    assert OWNER_HANDOVER not in _MIRROR_SCENARIOS


@pytest.mark.django_db
def test_model_filter_excludes_other_models_and_empty_scope_is_rejected():
    instances = _instances()
    service = _service(instances, RecordingWriter())
    preview = _preview(service, ZHANG, LI, ["host"])
    names = {item["inst_name"] for item in preview["items"]}
    assert names == {"db-01", "web-prod-01", "web-prod-02"}
    assert preview["total"] == 3

    empty = _service([], RecordingWriter())
    empty_preview = _preview(empty, ZHANG, LI, ["host"])
    with pytest.raises(OwnerHandoverRejected) as rejected:
        empty.submit(empty_preview["preview_token"], "empty-key")
    assert rejected.value.code == "no_instances"


@pytest.mark.django_db
def test_permission_lookup_failure_is_logged_once_and_does_not_name_other_orgs(caplog, monkeypatch):
    state = {"raise": False}

    def permissions(*_args, **_kwargs):
        if state["raise"]:
            raise RuntimeError("permission rpc down")
        return {}

    monkeypatch.setattr(CmdbRulesFormatUtil, "get_authorized_team_ids", staticmethod(lambda *_args, **_kwargs: [1]))
    monkeypatch.setattr(CmdbRulesFormatUtil, "format_user_context_permissions", staticmethod(permissions))
    monkeypatch.setattr(CmdbRulesFormatUtil, "has_object_permission", staticmethod(lambda *_args, **_kwargs: True))
    instances = _instances()
    writer = RecordingWriter()
    service = OwnerHandoverService(
        MemoryCatalog(instances),
        writer,
        MemoryDirectory(),
        lambda instance: allows_instance(_actor(), 1, False, instance),
        _actor(),
        1,
        False,
    )
    preview = _preview(service, ZHANG, LI, ["host", "application"])
    assert preview["excluded_no_permission"] == 1
    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        payload, _created = service.submit(preview["preview_token"], "permission-key")
        state["raise"] = True
        task = OwnerHandoverTask.objects.get(pk=payload["id"])
        result = service.execute(task.id, task.execution_token)

    assert result["status"] == "failed"
    assert result["success_count"] == 0
    assert writer.applied == []
    assert _by_name(instances, "web-prod-01")["operator"] == [ZHANG]
    assert _by_name(instances, "secret-host")["operator"] == [ZHANG]
    failures = service.list_failures(task.id)
    assert failures["count"] == 4
    assert "secret-host" not in {item["inst_name"] for item in failures["items"]}
    assert {item["reason_code"] for item in failures["items"]} == {"permission_check_failed"}
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == ("owner handover permission check failed, handover_id=%s, failed_stage=%s, error_type=%s")
    assert errors[0].args == (str(task.pk), "permission", "RuntimeError")
    assert errors[0].exc_info is not None
    assert SENTINEL not in caplog.text
    assert SENTINEL not in errors[0].getMessage()


@pytest.mark.django_db
def test_integer_owner_is_written_back_as_a_list():
    instances = [
        {
            "model_id": "host",
            "inst_uuid": "u-int",
            "inst_name": "int-host",
            "organization": [1],
            "organization_display": "运维一组",
            "operator": ZHANG,
        }
    ]
    writer = RecordingWriter()
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["host"])
    assert preview["items"][0]["changes"][0]["after"] == "李四(lisi)"
    payload, _created = service.submit(preview["preview_token"], "int-key")
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)
    assert result["status"] == "succeeded"
    assert instances[0]["operator"] == [LI]


@pytest.mark.django_db
def test_cancel_after_the_first_write_stops_the_rest():
    instances = _instances()

    class StopAfterFirst(RecordingWriter):
        def apply(self, instance, changes, operator, source_label):
            super().apply(instance, changes, operator, source_label)
            OwnerHandoverTask.objects.filter(pk=self.task_id).update(cancel_requested=True)

    writer = StopAfterFirst()
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["host"])
    payload, _created = service.submit(preview["preview_token"], "stop-key")
    writer.task_id = payload["id"]
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)

    assert result["status"] == "cancelled"
    assert [name for name, *_rest in writer.applied] == ["db-01"]
    assert _by_name(instances, "db-01")["operator"] == [LI]
    assert _by_name(instances, "web-prod-01")["operator"] == [ZHANG]
    assert _by_name(instances, "web-prod-02")["operator"] == [ZHANG, WANG]


def test_creator_inside_the_team_can_handover_and_other_orgs_cannot(monkeypatch):
    monkeypatch.setattr(CmdbRulesFormatUtil, "get_authorized_team_ids", staticmethod(lambda *args, **kwargs: [1]))
    user = SimpleNamespace(username="alice", domain="domain.com", is_superuser=False, group_list=[{"id": 1}], group_tree=[], roles=[])
    own = {"organization": [1], "_creator": "alice", "model_id": "host", "inst_name": "web-prod-01"}
    other = {"organization": [9], "_creator": "bob", "model_id": "host", "inst_name": "secret-host"}
    assert allows_instance(user, 1, False, own) is True
    assert allows_instance(user, 1, False, other) is False


@pytest.mark.django_db
def test_preview_api_rejects_callers_without_execute_permission(authenticated_user):
    factory = APIRequestFactory()
    request = factory.post("/x/", {"from_user_id": ZHANG, "to_user_id": LI}, format="json")
    request.COOKIES["current_team"] = "1"
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"cmdb": set()}
    force_authenticate(request, user=authenticated_user)
    response = OwnerHandoverPreviewView.as_view()(request)
    assert response.status_code == 403
    create_request = factory.post("/x/", {"preview_token": "stale"}, format="json")
    create_request.COOKIES["current_team"] = "1"
    force_authenticate(create_request, user=authenticated_user)
    create_response = OwnerHandoverTaskCreateView.as_view()(create_request)
    assert create_response.status_code == 403


@pytest.mark.django_db
def test_cleanup_removes_old_handover_history_for_the_selected_user():
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.change_record import ORDINARY_ATTRIBUTE_CHANGE, OWNER_HANDOVER, UPDATE_INST, ChangeRecord

    service = _service([], RecordingWriter())
    old = now() - timedelta(days=40)
    recent = now() - timedelta(days=1)

    def make_task(**kwargs):
        task = OwnerHandoverTask.objects.create(
            operator_username="admin",
            operator_domain="domain.com",
            from_user_id=kwargs.get("from_user_id", ZHANG),
            to_user_id=kwargs.get("to_user_id", LI),
            team_id=kwargs.get("team_id", 1),
            status=kwargs.get("status", "succeeded"),
            execution_token=kwargs["token"],
            idempotency_key=kwargs["key"],
            request_hash="hash",
            model_ids=["host"],
            attr_id="operator",
            attr_name="主要维护人",
        )
        OwnerHandoverTask.objects.filter(pk=task.pk).update(created_at=kwargs["created_at"])
        return task

    old_task = make_task(token="old-token", key="old-key", created_at=old)
    recent_task = make_task(token="recent-token", key="recent-key", created_at=recent)
    running_task = make_task(token="running-token", key="running-key", created_at=old, status="running")
    other_user = make_task(token="other-token", key="other-key", created_at=old, from_user_id=WANG, to_user_id=ZHAO)
    other_team = make_task(token="team-token", key="team-key", created_at=old, team_id=9)

    def make_record(message, scenario, created):
        row = ChangeRecord.objects.create(
            model_id="host",
            label="instance",
            type=UPDATE_INST,
            scenario=scenario,
            message=message,
            operator="admin",
        )
        ChangeRecord.objects.filter(pk=row.pk).update(created_at=created)
        return row

    old_record = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", OWNER_HANDOVER, old)
    recent_record = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", OWNER_HANDOVER, recent)
    other_record = make_record("负责人交接. 来源:王五(wangwu) → 赵六(zhaoliu)", OWNER_HANDOVER, old)
    ordinary = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", ORDINARY_ATTRIBUTE_CHANGE, old)

    result = service.cleanup_history(ZHANG, 30)

    assert result == {"tasks": 1, "records": 1, "days": 30}
    remaining_tasks = set(OwnerHandoverTask.objects.values_list("id", flat=True))
    assert old_task.id not in remaining_tasks
    assert {recent_task.id, running_task.id, other_user.id, other_team.id} <= remaining_tasks
    remaining_records = set(ChangeRecord.objects.values_list("id", flat=True))
    assert old_record.id not in remaining_records
    assert {recent_record.id, other_record.id, ordinary.id} <= remaining_records

    with pytest.raises(OwnerHandoverRejected) as missing:
        service.cleanup_history(99, 30)
    assert missing.value.code == "user_not_found"


@pytest.mark.django_db
def test_cleanup_without_a_user_removes_every_old_handover_in_range():
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.change_record import ORDINARY_ATTRIBUTE_CHANGE, OWNER_HANDOVER, UPDATE_INST, ChangeRecord

    service = _service([], RecordingWriter())
    old = now() - timedelta(days=40)
    recent = now() - timedelta(days=1)

    def make_task(**kwargs):
        task = OwnerHandoverTask.objects.create(
            operator_username="admin",
            operator_domain="domain.com",
            from_user_id=kwargs.get("from_user_id", ZHANG),
            to_user_id=kwargs.get("to_user_id", LI),
            team_id=kwargs.get("team_id", 1),
            status=kwargs.get("status", "succeeded"),
            execution_token=kwargs["token"],
            idempotency_key=kwargs["key"],
            request_hash="hash",
            model_ids=["host"],
            attr_id="operator",
            attr_name="主要维护人",
        )
        OwnerHandoverTask.objects.filter(pk=task.pk).update(created_at=kwargs["created_at"])
        return task

    zhang_task = make_task(token="zhang-token", key="zhang-key", created_at=old)
    wang_task = make_task(token="wang-token", key="wang-key", created_at=old, from_user_id=WANG, to_user_id=ZHAO)
    recent_task = make_task(token="recent-token", key="recent-key", created_at=recent)
    running_task = make_task(token="running-token", key="running-key", created_at=old, status="running")
    other_team = make_task(token="team-token", key="team-key", created_at=old, team_id=9)

    def make_record(message, scenario, created):
        row = ChangeRecord.objects.create(
            model_id="host",
            label="instance",
            type=UPDATE_INST,
            scenario=scenario,
            message=message,
            operator="admin",
        )
        ChangeRecord.objects.filter(pk=row.pk).update(created_at=created)
        return row

    zhang_record = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", OWNER_HANDOVER, old)
    wang_record = make_record("负责人交接. 来源:王五(wangwu) → 赵六(zhaoliu)", OWNER_HANDOVER, old)
    recent_record = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", OWNER_HANDOVER, recent)
    ordinary = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)", ORDINARY_ATTRIBUTE_CHANGE, old)

    result = service.cleanup_history(None, 30)

    assert result == {"tasks": 2, "records": 2, "days": 30}
    remaining_tasks = set(OwnerHandoverTask.objects.values_list("id", flat=True))
    assert zhang_task.id not in remaining_tasks
    assert wang_task.id not in remaining_tasks
    assert {recent_task.id, running_task.id, other_team.id} <= remaining_tasks
    remaining_records = set(ChangeRecord.objects.values_list("id", flat=True))
    assert zhang_record.id not in remaining_records
    assert wang_record.id not in remaining_records
    assert {recent_record.id, ordinary.id} <= remaining_records


@pytest.mark.django_db
def test_cleanup_can_target_several_users(caplog):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.models.change_record import OWNER_HANDOVER, UPDATE_INST, ChangeRecord

    service = _service([], RecordingWriter())
    old = now() - timedelta(days=40)

    def make_task(**kwargs):
        task = OwnerHandoverTask.objects.create(
            operator_username="admin",
            operator_domain="domain.com",
            from_user_id=kwargs["from_user_id"],
            to_user_id=kwargs["to_user_id"],
            team_id=1,
            status="succeeded",
            execution_token=kwargs["token"],
            idempotency_key=kwargs["key"],
            request_hash="hash",
            model_ids=["host"],
            attr_id="operator",
            attr_name="主要维护人",
            message=kwargs.get("message", ""),
        )
        OwnerHandoverTask.objects.filter(pk=task.pk).update(created_at=old)
        return task

    zhang_task = make_task(token="zhang-token", key="zhang-key", from_user_id=ZHANG, to_user_id=LI)
    wang_task = make_task(token="wang-token", key="wang-key", from_user_id=WANG, to_user_id=ZHAO, message=SENTINEL)
    other_task = make_task(token="other-token", key="other-key", from_user_id=LI, to_user_id=ZHAO)

    def make_record(message):
        return ChangeRecord.objects.create(
            model_id="host",
            label="instance",
            type=UPDATE_INST,
            scenario=OWNER_HANDOVER,
            message=message,
            operator="admin",
            created_at=old,
        )

    zhang_record = make_record("负责人交接. 来源:张三(zhangsan) → 李四(lisi)")
    wang_record = make_record("负责人交接. 来源:王五(wangwu) → 赵六(zhaoliu)")
    other_record = make_record(f"负责人交接. 来源:李四(lisi) → 赵六(zhaoliu) {SENTINEL}")
    ChangeRecord.objects.filter(pk__in=[zhang_record.pk, wang_record.pk, other_record.pk]).update(created_at=old)

    with caplog.at_level(logging.INFO, logger="cmdb"):
        result = service.cleanup_history([ZHANG, WANG], 30)

    assert result == {"tasks": 2, "records": 2, "days": 30}
    remaining_tasks = set(OwnerHandoverTask.objects.values_list("id", flat=True))
    assert zhang_task.id not in remaining_tasks
    assert wang_task.id not in remaining_tasks
    assert other_task.id in remaining_tasks
    remaining_records = set(ChangeRecord.objects.values_list("id", flat=True))
    assert zhang_record.id not in remaining_records
    assert wang_record.id not in remaining_records
    assert other_record.id in remaining_records
    cleaned = [record for record in caplog.records if record.msg.startswith("owner handover history cleaned")]
    assert cleaned[-1].msg == "owner handover history cleaned, user_id=%s, days=%s, tasks=%s, records=%s"
    assert cleaned[-1].args == ("3,5", 30, 2, 2)
    assert cleaned[-1].getMessage() == "owner handover history cleaned, user_id=3,5, days=30, tasks=2, records=2"
    assert cleaned[-1].exc_info is None
    assert SENTINEL not in caplog.text


@pytest.mark.django_db
def test_batch_handover_writes_distinct_owner_lists(caplog):
    instances = _instances()

    class BatchWriter:
        batch_size = 2

        def __init__(self):
            self.chunks = []

        def apply_many(self, rows, operator, source_label):
            self.chunks.append([(row["instance"]["inst_name"], dict(row["payload"]), operator, source_label) for row in rows])
            for row in rows:
                row["instance"].update(row["payload"])

    writer = BatchWriter()
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["host"])
    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        payload, _created = service.submit(preview["preview_token"], "batch-key")
        task = OwnerHandoverTask.objects.get(pk=payload["id"])
        result = service.execute(task.id, task.execution_token)

    assert result["status"] == "succeeded"
    assert result["success_count"] == 3
    assert [name for name, *_rest in writer.chunks[0]] == ["db-01", "web-prod-01"]
    assert [name for name, *_rest in writer.chunks[1]] == ["web-prod-02"]
    assert writer.chunks[0][0][1] == {"operator": [LI]}
    assert writer.chunks[1][0][1] == {"operator": [LI, WANG]}
    assert writer.chunks[0][0][3] == "张三(zhangsan) → 李四(lisi)"
    assert _by_name(instances, "web-prod-02")["operator"] == [LI, WANG]
    assert _by_name(instances, "web-prod-02")["bak_operator"] == [ZHANG]
    assert _by_name(instances, "secret-host")["operator"] == [ZHANG]
    assert SENTINEL not in caplog.text


@pytest.mark.django_db
def test_batch_failure_is_logged_once_per_instance_without_payload(caplog):
    instances = _instances()

    class Boom:
        batch_size = 2

        def apply_many(self, rows, operator, source_label):
            raise RuntimeError(SENTINEL)

    service = _service(instances, Boom())
    preview = _preview(service, ZHANG, LI, ["host"])
    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        payload, _created = service.submit(preview["preview_token"], "batch-fail")
        task = OwnerHandoverTask.objects.get(pk=payload["id"])
        result = service.execute(task.id, task.execution_token)

    assert result["status"] == "failed"
    assert result["success_count"] == 0
    assert result["failed_count"] == 3
    write_logs = [record for record in caplog.records if record.msg.startswith("owner handover instance failed")]
    assert len(write_logs) == 3
    assert write_logs[0].msg == "owner handover instance failed, handover_id=%s, inst_uuid=%s, failed_stage=%s, error_type=%s"
    assert write_logs[0].args[2:] == ("write", "RuntimeError")
    assert (
        write_logs[0].getMessage()
        == f"owner handover instance failed, handover_id={task.pk}, inst_uuid=u-host-dedupe, failed_stage=write, error_type=RuntimeError"
    )
    assert write_logs[0].exc_info is None
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert SENTINEL not in caplog.text
    assert _by_name(instances, "web-prod-01")["operator"] == [ZHANG]


@pytest.mark.django_db
def test_cancel_between_batches_keeps_the_written_chunk():
    instances = _instances()

    class StopAfterChunk:
        batch_size = 1

        def __init__(self):
            self.names = []

        def apply_many(self, rows, operator, source_label):
            for row in rows:
                row["instance"].update(row["payload"])
                self.names.append(row["instance"]["inst_name"])
            OwnerHandoverTask.objects.filter(pk=self.task_id).update(cancel_requested=True)

    writer = StopAfterChunk()
    service = _service(instances, writer)
    preview = _preview(service, ZHANG, LI, ["host"])
    payload, _created = service.submit(preview["preview_token"], "batch-stop")
    writer.task_id = payload["id"]
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    result = service.execute(task.id, task.execution_token)

    assert result["status"] == "cancelled"
    assert writer.names == ["db-01"]
    assert _by_name(instances, "db-01")["operator"] == [LI]
    assert _by_name(instances, "web-prod-01")["operator"] == [ZHANG]


@pytest.mark.django_db
def test_preview_transfer_status_updates_after_success_and_failure():
    instances = _instances()
    service = _service(instances, RecordingWriter(fail_names={"web-prod-02"}))
    preview = _preview(service, ZHANG, LI, ["host"])
    assert {item["transfer_status"] for item in preview["items"]} == {"pending"}
    payload, _created = service.submit(preview["preview_token"], "status-key")
    task = OwnerHandoverTask.objects.get(pk=payload["id"])
    service.execute(task.id, task.execution_token)
    rows = service.list_outcome_statuses(task.id, [item["inst_uuid"] for item in preview["items"]] + ["missing-uuid"])
    status = {row["inst_uuid"]: row["transfer_status"] for row in rows}
    by_name = {item["inst_name"]: item["inst_uuid"] for item in preview["items"]}
    assert status[by_name["db-01"]] == "succeeded"
    assert status[by_name["web-prod-01"]] == "succeeded"
    assert status[by_name["web-prod-02"]] == "failed"
    assert status["missing-uuid"] == "pending"


@pytest.mark.django_db
def test_history_filters_by_user_and_delete_keeps_running_tasks(caplog):
    service = _service([], RecordingWriter())

    def make_task(**kwargs):
        return OwnerHandoverTask.objects.create(
            operator_username="admin",
            operator_domain="domain.com",
            from_user_id=kwargs.get("from_user_id", ZHANG),
            to_user_id=kwargs.get("to_user_id", LI),
            from_label="张三(zhangsan)",
            to_label="李四(lisi)",
            team_id=kwargs.get("team_id", 1),
            status=kwargs.get("status", "succeeded"),
            execution_token=kwargs["token"],
            idempotency_key=kwargs["key"],
            request_hash="hash",
            model_ids=["host"],
            attr_id="operator",
            attr_name="主要维护人",
            message=kwargs.get("message", ""),
            success_count=1,
        )

    finished = make_task(token="done-token", key="done-key")
    running = make_task(token="run-token", key="run-key", status="running", message=SENTINEL)
    other_user = make_task(token="other-token", key="other-key", from_user_id=WANG, to_user_id=ZHAO)
    other_team = make_task(token="team-token", key="team-key", team_id=9)

    listed = service.list_tasks(ZHANG)
    assert {item["id"] for item in listed["items"]} == {str(finished.id), str(running.id)}
    assert listed["items"][0]["attr_name"] == "主要维护人"
    assert service.list_tasks()["count"] == 3

    with caplog.at_level(logging.INFO, logger="cmdb"):
        result = service.delete_tasks([finished.id, running.id, other_team.id])

    assert result == {"deleted": 1, "kept": 1}
    remaining = set(OwnerHandoverTask.objects.values_list("id", flat=True))
    assert finished.id not in remaining
    assert {running.id, other_user.id, other_team.id} <= remaining
    deleted_logs = [record for record in caplog.records if record.msg.startswith("owner handover tasks deleted")]
    assert deleted_logs[-1].msg == "owner handover tasks deleted, team_id=%s, tasks=%s, kept=%s"
    assert deleted_logs[-1].args == (1, 1, 1)
    assert deleted_logs[-1].getMessage() == "owner handover tasks deleted, team_id=1, tasks=1, kept=1"
    assert deleted_logs[-1].exc_info is None
    assert SENTINEL not in caplog.text

    with pytest.raises(OwnerHandoverRejected) as missing:
        service.delete_tasks([])
    assert missing.value.code == "bad_delete"


def test_graph_catalog_loads_instances_by_uuid():
    class Graph:
        def query_entity(self, label, params, page=None, **kwargs):
            assert params == [{"field": "inst_uuid", "type": "str[]", "value": ["u-1", "u-2"]}]
            assert page == {"skip": 0, "limit": 2}
            return [{"inst_uuid": "u-1", "_id": 11, "operator": [ZHANG]}, {"inst_uuid": "u-2", "_id": 12}], 2

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    found = GraphOwnerCatalog(graph_factory=lambda: Graph(), model_search=lambda: []).get_instances(["u-1", "u-2", "u-1"])
    assert found["u-2"]["_id"] == 12


@pytest.mark.django_db
def test_writer_apply_many_batches_graph_write_and_change_records(monkeypatch):
    from uuid import uuid4

    from apps.cmdb.display_field import DisplayFieldConverter
    from apps.cmdb.models.change_record import UPDATE_INST, ChangeRecord
    from apps.cmdb.services.instance import InstanceManage

    first_id = uuid4()
    second_id = uuid4()
    graph_calls = []

    class Graph:
        def batch_set_node_properties(self, label, rows):
            graph_calls.append((label, rows))
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def query_entity_by_uuids(inst_uuids, fields=None):
        assert inst_uuids == [str(second_id)]
        return [{"inst_uuid": str(second_id), "_id": 12, "model_id": "host", "inst_name": "web-prod-02", "operator": [ZHANG, WANG]}]

    monkeypatch.setattr("apps.cmdb.services.owner_handover_graph.GraphClient", lambda: Graph())
    monkeypatch.setattr(InstanceManage, "query_entity_by_uuids", staticmethod(query_entity_by_uuids))
    monkeypatch.setattr(DisplayFieldConverter, "convert_user", staticmethod(lambda user_list: ",".join(str(item) for item in user_list)))

    writer = InstanceHandoverWriter(SimpleNamespace(roles=["admin"]), 1, False)
    writer.apply_many(
        [
            {
                "model_name": "主机",
                "instance": {
                    "_id": 11,
                    "inst_uuid": str(first_id),
                    "inst_name": "web-prod-01",
                    "model_id": "host",
                    "operator": [ZHANG],
                    "note": SENTINEL,
                },
                "payload": {"operator": [LI]},
            },
            {
                "model_name": "主机",
                "instance": {
                    "inst_uuid": str(second_id),
                    "inst_name": "web-prod-02",
                    "model_id": "host",
                    "operator": [ZHANG, WANG],
                    "note": SENTINEL,
                },
                "payload": {"operator": [LI, WANG]},
            },
        ],
        "admin",
        "张三(zhangsan) → 李四(lisi)",
    )

    assert len(graph_calls) == 1
    written = {row["id"]: row["properties"] for row in graph_calls[0][1]}
    assert written[11]["operator"] == [LI]
    assert written[12]["operator"] == [LI, WANG]
    assert written[11]["operator_display"] == str(LI)
    assert written[12]["operator_display"] == f"{LI},{WANG}"
    assert '"source":"manual"' in written[11]["_collect_sources"]
    records = list(ChangeRecord.objects.filter(scenario=OWNER_HANDOVER, type=UPDATE_INST).order_by("inst_id"))
    assert [record.message for record in records] == [
        "负责人交接. 来源:张三(zhangsan) → 李四(lisi) 模型:主机 实例:web-prod-01",
        "负责人交接. 来源:张三(zhangsan) → 李四(lisi) 模型:主机 实例:web-prod-02",
    ]
    assert records[0].operator == "admin"
    assert records[0].before_data["operator"] == [ZHANG]
    assert records[1].after_data["operator"] == [LI, WANG]
    assert records[0].before_data["note"] == SENTINEL
