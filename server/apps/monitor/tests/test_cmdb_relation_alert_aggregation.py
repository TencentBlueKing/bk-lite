from types import SimpleNamespace

import pytest

from apps.monitor.nats import monitor as nm
from apps.monitor.services.cmdb_relation_alerts import build_relation_alert_view


def test_relation_alert_view_counts_hosts_without_edges_as_clear():
    entities = [
        {"inst_uuid": "app-1", "inst_name": "订单系统"},
        {"inst_uuid": "app-2", "inst_name": "门户"},
        {"inst_uuid": "app-3", "inst_name": "空应用"},
    ]
    edges = [
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-1",
            "dst_inst_uuid": "host-1",
        },
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-1",
            "dst_inst_uuid": "host-2",
        },
        {
            "src_model_id": "host",
            "dst_model_id": "application",
            "src_inst_uuid": "host-9",
            "dst_inst_uuid": "app-2",
        },
    ]

    summary = build_relation_alert_view(
        entities=entities,
        edges=edges,
        alert_count_by_peer={"host-1": 2, "host-9": 0},
        source_model_id="application",
        peer_model_id="host",
        view="summary",
    )
    assert summary == {
        "total_count": 3,
        "with_alert_count": 1,
        "without_alert_count": 2,
        "with_alert_share": "33.3%",
        "without_alert_share": "66.7%",
    }

    top = build_relation_alert_view(
        entities=entities,
        edges=edges,
        alert_count_by_peer={"host-1": 2, "host-2": 3},
        source_model_id="application",
        peer_model_id="host",
        view="top",
        limit=1,
    )
    assert top == [
        {
            "name": "订单系统",
            "value": 5,
            "inst_uuid": "app-1",
            "host_count": 2,
            "alert_count": 5,
            "share": "100.0%",
        },
    ]


def test_relation_alert_handler_uses_authorized_host_cmdb_ids(monkeypatch):
    class FakeManager:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=3)

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids, monitor_obj_id=None: (
            {
                "mon-1": SimpleNamespace(id="mon-1", cmdb_id="host-1"),
            },
            None,
        ),
    )
    policy_qs = object()
    captured = {}

    def fake_count(instance_ids, scope_ids, accessible_policy_qs):
        captured["instance_ids"] = list(instance_ids)
        captured["scope_ids"] = scope_ids
        captured["policy_qs"] = accessible_policy_qs
        return {"mon-1": 4, "mon-2": 9}

    monkeypatch.setattr(nm, "_count_new_monitor_alerts", fake_count)
    monkeypatch.setattr(nm, "_get_nats_accessible_policy_queryset", lambda user_info: (policy_qs, None))
    monkeypatch.setattr(
        nm,
        "list_model_association_options",
        lambda language, model_id: [
            {"model_asst_id": "application_run_host", "src_model_id": "application", "dst_model_id": "host"},
        ],
    )
    monkeypatch.setattr(
        nm,
        "query_association_edges",
        lambda model_asst_id, uuids: [
            {
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "app-1",
                "dst_inst_uuid": "host-1",
            },
            {
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "app-1",
                "dst_inst_uuid": "host-hidden",
            },
        ],
    )
    monkeypatch.setattr(
        nm.InstanceManage,
        "instance_list",
        lambda **kwargs: ([{"inst_uuid": "app-1", "inst_name": "订单"}, {"inst_uuid": "app-2", "inst_name": "空"}], 2),
    )

    import apps.cmdb.nats.nats as cmdb_nats

    monkeypatch.setattr(cmdb_nats, "_build_nats_permission_map", lambda user_info, model_id="": {"1": {}})
    monkeypatch.setattr(cmdb_nats, "_resolve_nats_cmdb_language", lambda user_info=None: "zh-Hans")

    result = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id="application_run_host",
        peer_model_id="host",
        view="summary",
        user_info={"user": "u", "team": 1},
    )

    assert result["result"] is True
    assert captured["instance_ids"] == ["mon-1"]
    assert captured["scope_ids"] == frozenset({1})
    assert captured["policy_qs"] is policy_qs
    assert result["data"] == {
        "total_count": 2,
        "with_alert_count": 1,
        "without_alert_count": 1,
        "with_alert_share": "50.0%",
        "without_alert_share": "50.0%",
    }


def test_relation_alert_handler_empty_permission_skips_queries(monkeypatch):
    def fail_instances(**kwargs):
        raise AssertionError("no permission must not list instances")

    monkeypatch.setattr(nm.InstanceManage, "instance_list", fail_instances)
    import apps.cmdb.nats.nats as cmdb_nats

    monkeypatch.setattr(cmdb_nats, "_build_nats_permission_map", lambda user_info, model_id="": None)

    result = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id="application_run_host",
        view="summary",
        user_info={"user": "u", "team": 1},
    )

    assert result["result"] is True
    assert result["data"] == {
        "total_count": 0,
        "with_alert_count": 0,
        "without_alert_count": 0,
        "with_alert_share": "0.0%",
        "without_alert_share": "0.0%",
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model_asst_id": "application_run_host"}, "模型不能为空"),
        ({"model_id": "application", "view": "distribution"}, "view"),
        ({"model_id": "application", "view": "other"}, "view"),
    ],
)
def test_relation_alert_handler_rejects_bad_input(kwargs, message):
    result = nm.get_cmdb_relation_alert_aggregation(**kwargs)
    assert result["result"] is False
    assert message in result["message"]


def _patch_relation_alert_sources(monkeypatch):
    class FakeManager:
        def filter(self, **kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=3)

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids, monitor_obj_id=None: (
            {"mon-1": SimpleNamespace(id="mon-1", cmdb_id="host-1")},
            None,
        ),
    )
    monkeypatch.setattr(
        nm,
        "list_model_association_options",
        lambda language, model_id: [
            {"model_asst_id": "application_run_host", "src_model_id": "application", "dst_model_id": "host"},
        ],
    )
    monkeypatch.setattr(nm, "query_association_edges", lambda model_asst_id, uuids: [])
    import apps.cmdb.nats.nats as cmdb_nats

    monkeypatch.setattr(cmdb_nats, "_build_nats_permission_map", lambda user_info, model_id="": {"1": {}})
    monkeypatch.setattr(cmdb_nats, "_resolve_nats_cmdb_language", lambda user_info=None: "zh-Hans")


def test_relation_alert_handler_returns_policy_error_without_counting(monkeypatch):
    _patch_relation_alert_sources(monkeypatch)
    policy_error = {"result": False, "data": {}, "message": "获取对象权限失败"}
    monkeypatch.setattr(nm, "_get_nats_accessible_policy_queryset", lambda user_info: (None, policy_error))

    def fail_count(*args, **kwargs):
        raise AssertionError("policy error must not count alerts")

    def fail_instances(**kwargs):
        raise AssertionError("policy error must not list instances")

    monkeypatch.setattr(nm, "_count_new_monitor_alerts", fail_count)
    monkeypatch.setattr(nm.InstanceManage, "instance_list", fail_instances)

    result = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id="application_run_host",
        peer_model_id="host",
        view="summary",
        user_info={"user": "u", "team": 1},
    )
    assert result == policy_error


def test_relation_alert_handler_pages_instances_before_aggregate(monkeypatch):
    _patch_relation_alert_sources(monkeypatch)
    monkeypatch.setattr(nm, "_RELATION_ALERT_PAGE_SIZE", 1)
    monkeypatch.setattr(nm, "_get_nats_accessible_policy_queryset", lambda user_info: (object(), None))
    monkeypatch.setattr(nm, "_count_new_monitor_alerts", lambda instance_ids, scope_ids, accessible_policy_qs: {"mon-1": 4})
    pages = []

    def fake_list(**kwargs):
        assert kwargs["params"] == []
        kwargs["params"].append(kwargs["model_id"])
        pages.append(kwargs["page"])
        if kwargs["page"] == 1:
            return ([{"inst_uuid": "app-1", "inst_name": "甲"}], 2)
        if kwargs["page"] == 2:
            return ([{"inst_uuid": "app-2", "inst_name": "乙"}], 2)
        raise AssertionError(f"unexpected page {kwargs['page']}")

    monkeypatch.setattr(nm.InstanceManage, "instance_list", fake_list)
    monkeypatch.setattr(
        nm,
        "query_association_edges",
        lambda model_asst_id, uuids: [
            {
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "app-1",
                "dst_inst_uuid": "host-1",
            },
        ],
    )

    result = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id="application_run_host",
        peer_model_id="host",
        view="summary",
        user_info={"user": "u", "team": 1},
    )

    assert pages == [1, 2]
    assert result["result"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["with_alert_count"] == 1
    assert result["data"]["without_alert_count"] == 1


@pytest.mark.django_db
def test_count_new_monitor_alerts_skips_policy_or_org_invisible():
    from apps.monitor.models.monitor_object import MonitorObject
    from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy

    obj = MonitorObject.objects.create(name="RelationAlertVisibility", level="base")
    visible = MonitorPolicy.objects.create(
        monitor_object=obj,
        name="visible-policy",
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        enable=True,
        period={"type": "min", "value": 5},
    )
    hidden = MonitorPolicy.objects.create(
        monitor_object=obj,
        name="hidden-policy",
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        enable=True,
        period={"type": "min", "value": 5},
    )

    def add(policy_id, organizations, status="new", instance_id="mon-1"):
        MonitorAlert.objects.create(
            policy_id=policy_id,
            monitor_instance_id=instance_id,
            status=status,
            organizations=organizations,
        )

    add(visible.id, [1])
    add(hidden.id, [1])
    add(visible.id, [9])
    add(visible.id, [1], status="closed")
    add(0, [1])
    add(visible.id, [1], instance_id="mon-other")

    counts = nm._count_new_monitor_alerts(
        ["mon-1"],
        [1],
        MonitorPolicy.objects.filter(id=visible.id),
    )
    assert counts == {"mon-1": 2}
