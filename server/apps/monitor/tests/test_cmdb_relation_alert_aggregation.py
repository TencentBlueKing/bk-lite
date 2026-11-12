from types import SimpleNamespace

import pytest

from apps.monitor.nats import monitor as nm
from apps.monitor.services.cmdb_relation_alerts import build_relation_alert_view, compose_two_hop_peers, edges_from_peers, normalize_model_asst_ids


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
        "alert_count": 2,
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
        "alert_count": 4,
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
        "alert_count": 0,
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
    assert result["data"]["alert_count"] == 4


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


def test_two_hop_view_rolls_up_and_dedups_shared_hosts():
    entities = [
        {"inst_uuid": "sys-oa", "inst_name": "企业办公平台（OA）"},
        {"inst_uuid": "sys-trade", "inst_name": "BJ-TRADE-交易中台"},
        {"inst_uuid": "sys-empty", "inst_name": "空系统"},
    ]
    first_edges = [
        {
            "src_model_id": "system",
            "dst_model_id": "application",
            "src_inst_uuid": "sys-oa",
            "dst_inst_uuid": "app-doc",
        },
        {
            "src_model_id": "system",
            "dst_model_id": "application",
            "src_inst_uuid": "sys-oa",
            "dst_inst_uuid": "app-flow",
        },
        {
            "src_model_id": "system",
            "dst_model_id": "application",
            "src_inst_uuid": "sys-trade",
            "dst_inst_uuid": "app-core",
        },
    ]
    second_edges = [
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-doc",
            "dst_inst_uuid": "host-1",
        },
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-flow",
            "dst_inst_uuid": "host-1",
        },
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-flow",
            "dst_inst_uuid": "host-2",
        },
        {
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-core",
            "dst_inst_uuid": "host-3",
        },
    ]
    source_ids = ["sys-oa", "sys-trade", "sys-empty"]
    peers = compose_two_hop_peers(
        first_edges,
        second_edges,
        source_ids,
        "system",
        "application",
        "host",
    )
    assert peers["sys-oa"] == ["host-1", "host-2"]
    assert peers["sys-trade"] == ["host-3"]
    assert peers["sys-empty"] == []

    edges = edges_from_peers(peers, "system", "host")
    counts = {"host-1": 2, "host-2": 3, "host-3": 4}
    summary = build_relation_alert_view(
        entities=entities,
        edges=edges,
        alert_count_by_peer=counts,
        source_model_id="system",
        peer_model_id="host",
        view="summary",
    )
    assert summary == {
        "total_count": 3,
        "with_alert_count": 2,
        "without_alert_count": 1,
        "alert_count": 9,
        "with_alert_share": "66.7%",
        "without_alert_share": "33.3%",
    }
    top = build_relation_alert_view(
        entities=entities,
        edges=edges,
        alert_count_by_peer=counts,
        source_model_id="system",
        peer_model_id="host",
        view="top",
        limit=10,
    )
    assert [item["name"] for item in top] == ["企业办公平台（OA）", "BJ-TRADE-交易中台"]
    assert top[0]["alert_count"] == 5
    assert top[0]["host_count"] == 2
    assert top[0]["share"] == "55.6%"
    assert top[1]["alert_count"] == 4
    assert top[1]["host_count"] == 1


def _two_hop_association_options(language, model_id):
    catalog = {
        "system": [
            {
                "model_asst_id": "system_contains_application",
                "src_model_id": "system",
                "dst_model_id": "application",
            },
        ],
        "application": [
            {
                "model_asst_id": "system_contains_application",
                "src_model_id": "system",
                "dst_model_id": "application",
            },
            {
                "model_asst_id": "application_run_host",
                "src_model_id": "application",
                "dst_model_id": "host",
            },
        ],
    }
    return catalog.get(model_id, [])


def test_relation_alert_handler_two_hop_rolls_up_and_dedups(monkeypatch):
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
                "mon-2": SimpleNamespace(id="mon-2", cmdb_id="host-2"),
                "mon-3": SimpleNamespace(id="mon-3", cmdb_id="host-3"),
            },
            None,
        ),
    )
    policy_qs = object()
    monkeypatch.setattr(
        nm,
        "_count_new_monitor_alerts",
        lambda instance_ids, scope_ids, accessible_policy_qs: {"mon-1": 2, "mon-2": 3, "mon-3": 4},
    )
    monkeypatch.setattr(nm, "_get_nats_accessible_policy_queryset", lambda user_info: (policy_qs, None))
    monkeypatch.setattr(nm, "list_model_association_options", _two_hop_association_options)

    edge_calls = []

    def fake_edges(model_asst_id, uuids):
        edge_calls.append((model_asst_id, list(uuids)))
        if model_asst_id == "system_contains_application":
            return [
                {
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "src_inst_uuid": "sys-oa",
                    "dst_inst_uuid": "app-doc",
                },
                {
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "src_inst_uuid": "sys-oa",
                    "dst_inst_uuid": "app-flow",
                },
                {
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "src_inst_uuid": "sys-trade",
                    "dst_inst_uuid": "app-core",
                },
            ]
        if model_asst_id == "application_run_host":
            return [
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "src_inst_uuid": "app-doc",
                    "dst_inst_uuid": "host-1",
                },
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "src_inst_uuid": "app-flow",
                    "dst_inst_uuid": "host-1",
                },
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "src_inst_uuid": "app-flow",
                    "dst_inst_uuid": "host-2",
                },
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "src_inst_uuid": "app-core",
                    "dst_inst_uuid": "host-3",
                },
            ]
        raise AssertionError(model_asst_id)

    monkeypatch.setattr(nm, "query_association_edges", fake_edges)
    monkeypatch.setattr(
        nm.InstanceManage,
        "instance_list",
        lambda **kwargs: (
            [
                {"inst_uuid": "sys-oa", "inst_name": "企业办公平台（OA）"},
                {"inst_uuid": "sys-trade", "inst_name": "BJ-TRADE-交易中台"},
                {"inst_uuid": "sys-empty", "inst_name": "空系统"},
            ],
            3,
        ),
    )
    import apps.cmdb.nats.nats as cmdb_nats

    monkeypatch.setattr(cmdb_nats, "_build_nats_permission_map", lambda user_info, model_id="": {"1": {}})
    monkeypatch.setattr(cmdb_nats, "_resolve_nats_cmdb_language", lambda user_info=None: "zh-Hans")

    summary = nm.get_cmdb_relation_alert_aggregation(
        model_id="system",
        model_asst_id=["system_contains_application", "application_run_host"],
        peer_model_id="host",
        view="summary",
        user_info={"user": "u", "team": 1},
    )
    assert summary["result"] is True
    assert summary["data"] == {
        "total_count": 3,
        "with_alert_count": 2,
        "without_alert_count": 1,
        "alert_count": 9,
        "with_alert_share": "66.7%",
        "without_alert_share": "33.3%",
    }
    assert [item[0] for item in edge_calls] == ["system_contains_application", "application_run_host"]
    assert set(edge_calls[1][1]) == {"app-doc", "app-flow", "app-core"}

    top = nm.get_cmdb_relation_alert_aggregation(
        model_id="system",
        model_asst_id=["system_contains_application", "application_run_host"],
        peer_model_id="host",
        view="top",
        limit=10,
        user_info={"user": "u", "team": 1},
    )
    assert top["result"] is True
    assert [item["name"] for item in top["data"]] == ["企业办公平台（OA）", "BJ-TRADE-交易中台"]
    assert top["data"][0]["alert_count"] == 5
    assert top["data"][0]["host_count"] == 2
    assert top["data"][1]["alert_count"] == 4
    assert "BJ-TRADE-core" not in {item["name"] for item in top["data"]}
    assert "文档服务" not in {item["name"] for item in top["data"]}


def test_normalize_model_asst_ids_accepts_string_or_path():
    assert normalize_model_asst_ids("application_run_host") == ["application_run_host"]
    assert normalize_model_asst_ids(["system_contains_application", "application_run_host"]) == [
        "system_contains_application",
        "application_run_host",
    ]
    assert normalize_model_asst_ids("system_contains_application,application_run_host") == [
        "system_contains_application",
        "application_run_host",
    ]
    assert normalize_model_asst_ids("system_contains_application, application_run_host") == [
        "system_contains_application",
        "application_run_host",
    ]
    with pytest.raises(ValueError, match="模型关联不能为空"):
        normalize_model_asst_ids("")
    with pytest.raises(ValueError, match="模型关联不能为空"):
        normalize_model_asst_ids(["system_contains_application", " "])
    with pytest.raises(ValueError, match="模型关联路径格式不正确"):
        normalize_model_asst_ids({"id": "application_run_host"})


def test_relation_alert_handler_one_hop_string_matches_single_item_list(monkeypatch):
    _patch_relation_alert_sources(monkeypatch)
    monkeypatch.setattr(nm, "_get_nats_accessible_policy_queryset", lambda user_info: (object(), None))
    monkeypatch.setattr(nm, "_count_new_monitor_alerts", lambda instance_ids, scope_ids, accessible_policy_qs: {"mon-1": 4})
    monkeypatch.setattr(
        nm.InstanceManage,
        "instance_list",
        lambda **kwargs: ([{"inst_uuid": "app-1", "inst_name": "订单"}, {"inst_uuid": "app-2", "inst_name": "空"}], 2),
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
            }
        ],
    )
    user_info = {"user": "u", "team": 1}
    as_string = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id="application_run_host",
        peer_model_id="host",
        view="summary",
        user_info=user_info,
    )
    as_list = nm.get_cmdb_relation_alert_aggregation(
        model_id="application",
        model_asst_id=["application_run_host"],
        peer_model_id="host",
        view="summary",
        user_info=user_info,
    )
    assert as_string["result"] is True
    assert as_list["data"] == as_string["data"]
    assert as_string["data"]["alert_count"] == 4


@pytest.mark.parametrize(
    ("model_asst_id", "peer_model_id", "extra_option", "message"),
    [
        (
            ["system_contains_application", "does_not_exist"],
            "host",
            None,
            "关联路径第 2 跳不存在，或没有连接到上一跳模型",
        ),
        (
            ["system_contains_application", "biz_owns_rack"],
            "host",
            {"model_asst_id": "biz_owns_rack", "src_model_id": "biz", "dst_model_id": "rack"},
            "关联路径第 2 跳没有连接到上一跳模型",
        ),
        (
            ["system_contains_application", "application_run_host"],
            "application",
            None,
            "关联路径的最终对端不是指定模型",
        ),
        (
            "does_not_exist",
            "host",
            None,
            "模型关联不存在，或没有连接到该模型",
        ),
        (
            "application_run_host",
            "application",
            None,
            "模型关联的对端不是指定模型",
        ),
    ],
)
def test_relation_alert_handler_rejects_invalid_association_path(monkeypatch, model_asst_id, peer_model_id, extra_option, message):
    _patch_relation_alert_sources(monkeypatch)
    catalog = {
        "application": [
            {"model_asst_id": "application_run_host", "src_model_id": "application", "dst_model_id": "host"},
        ],
        "system": [
            {
                "model_asst_id": "system_contains_application",
                "src_model_id": "system",
                "dst_model_id": "application",
            },
        ],
    }
    if extra_option is not None:
        catalog.setdefault("application", []).append(extra_option)
    monkeypatch.setattr(nm, "list_model_association_options", lambda language, model_id: catalog.get(model_id, []))

    def fail_instances(**kwargs):
        raise AssertionError("invalid path must not list instances")

    monkeypatch.setattr(nm.InstanceManage, "instance_list", fail_instances)

    result = nm.get_cmdb_relation_alert_aggregation(
        model_id="system" if isinstance(model_asst_id, list) else "application",
        model_asst_id=model_asst_id,
        peer_model_id=peer_model_id,
        view="summary",
        user_info={"user": "u", "team": 1},
    )
    assert result["result"] is False
    assert message in result["message"]


def test_summary_alert_count_dedups_hosts_shared_by_systems():
    entities = [
        {"inst_uuid": "sys-a", "inst_name": "系统A"},
        {"inst_uuid": "sys-b", "inst_name": "系统B"},
    ]
    edges = [
        {
            "src_model_id": "system",
            "dst_model_id": "host",
            "src_inst_uuid": "sys-a",
            "dst_inst_uuid": "host-1",
        },
        {
            "src_model_id": "system",
            "dst_model_id": "host",
            "src_inst_uuid": "sys-b",
            "dst_inst_uuid": "host-1",
        },
    ]
    summary = build_relation_alert_view(
        entities=entities,
        edges=edges,
        alert_count_by_peer={"host-1": 3},
        source_model_id="system",
        peer_model_id="host",
        view="summary",
    )
    assert summary["with_alert_count"] == 2
    assert summary["alert_count"] == 3
