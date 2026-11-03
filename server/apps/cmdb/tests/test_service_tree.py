import logging
from uuid import uuid4

import pytest

from apps.cmdb.services.application_system import expand_systems_to_host_uuids
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.service_tree import (
    APPLICATION_RUN_HOST,
    SYSTEM_CONTAINS_APPLICATION,
    ServiceTreeService,
    _lookup_hosts_for_rows,
    applications_by_system,
    assign_host_plan,
    build_service_tree,
    can_create_application_model,
    create_layer_models,
    expand_systems_to_host_uuids_via_service_tree,
    layer_schema_from,
    match_host,
    parse_import_row,
    plan_import_rows,
    transfer_host_plan,
    unbind_host_plan,
)
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException


def _edges(*items):
    return list(items)


def _edge(asst, src_model, src, dst_model, dst):
    return {
        "model_asst_id": asst,
        "src_model_id": src_model,
        "src_inst_uuid": src,
        "dst_model_id": dst_model,
        "dst_inst_uuid": dst,
    }


def _loader(graph):
    def edge_loader(asst_id, uuids):
        wanted = set(uuids)
        return [edge for edge in graph if edge["model_asst_id"] == asst_id and (edge["src_inst_uuid"] in wanted or edge["dst_inst_uuid"] in wanted)]

    return edge_loader


def test_old_expander_still_only_walks_two_hops():
    graph = [
        _edge("system_contains_biz_group", "system", "s1", "biz_group", "g1"),
        _edge("biz_group_contains_application", "biz_group", "g1", "application", "a-grouped"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a-direct"),
        _edge(APPLICATION_RUN_HOST, "application", "a-grouped", "host", "h-hidden"),
        _edge(APPLICATION_RUN_HOST, "application", "a-direct", "host", "h-direct"),
    ]
    assert expand_systems_to_host_uuids(["s1"], edge_loader=_loader(graph)) == ["h-direct"]


def test_service_tree_expand_only_walks_direct_applications():
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a-direct"),
        _edge("system_contains_biz_group", "system", "s1", "biz_group", "g1"),
        _edge("biz_group_contains_application", "biz_group", "g1", "application", "a-grouped"),
        _edge(APPLICATION_RUN_HOST, "application", "a-direct", "host", "h-direct"),
        _edge(APPLICATION_RUN_HOST, "application", "a-grouped", "host", "h-hidden"),
        _edge(APPLICATION_RUN_HOST, "application", "a-direct", "host", "h-shared"),
    ]
    assert expand_systems_to_host_uuids_via_service_tree(["s1"], edge_loader=_loader(graph)) == [
        "h-direct",
        "h-shared",
    ]


def test_service_tree_expand_empty_or_unknown_returns_empty():
    assert expand_systems_to_host_uuids_via_service_tree([], edge_loader=lambda *_: []) == []
    assert expand_systems_to_host_uuids_via_service_tree(["missing"], edge_loader=lambda *_: []) == []


def test_applications_by_system_only_follows_direct_contains():
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a-direct"),
        _edge("system_contains_biz_group", "system", "s1", "biz_group", "g1"),
        _edge("biz_group_contains_application", "biz_group", "g1", "application", "a-grouped"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s2", "application", "a-other"),
    ]
    assert applications_by_system(["s1"], edge_loader=_loader(graph)) == {"s1": ["a-direct"]}


def test_applications_by_system_skips_self_referential_non_application_child(caplog):
    sentinel = "password=super-secret-token"
    loop = _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "system", "s1")
    loop["inst_name"] = sentinel
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a-ok"),
        loop,
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s2", "application", "a-other"),
    ]
    caplog.set_level(logging.WARNING, logger="cmdb")

    result = applications_by_system(["s1", "s2"], edge_loader=_loader(graph))

    assert result == {"s1": ["a-ok"], "s2": ["a-other"]}
    records = [record for record in caplog.records if record.name == "cmdb" and "event=service_tree_application_walk_skipped" in record.msg]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].msg == "event=service_tree_application_walk_skipped node_uuid=%s model_id=%s reason=%s"
    assert records[0].args == ("s1", "system", "cycle")
    assert records[0].getMessage() == "event=service_tree_application_walk_skipped node_uuid=s1 model_id=system reason=cycle"
    assert sentinel not in records[0].getMessage()
    assert records[0].exc_info is None
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_applications_by_system_bounds_skipped_node_identity(caplog):
    dirty = "s1\n" + ("z" * 200)
    sentinel = "password=super-secret-token"
    loop = _edge(SYSTEM_CONTAINS_APPLICATION, "system", dirty, "system", dirty)
    loop["inst_name"] = sentinel
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", dirty, "application", "a-ok"),
        loop,
    ]
    caplog.set_level(logging.WARNING, logger="cmdb")

    result = applications_by_system([dirty], edge_loader=_loader(graph))

    assert result == {dirty: ["a-ok"]}
    records = [record for record in caplog.records if record.name == "cmdb" and "event=service_tree_application_walk_skipped" in record.msg]
    assert len(records) == 1
    expected_uuid = ("s1\\n" + ("z" * 200))[:160]
    assert records[0].args == (expected_uuid, "system", "cycle")
    assert len(expected_uuid) == 160
    assert "\n" not in records[0].getMessage()
    assert "\r" not in records[0].getMessage()
    assert sentinel not in records[0].getMessage()
    assert records[0].getMessage() == f"event=service_tree_application_walk_skipped node_uuid={expected_uuid} model_id=system reason=cycle"


def test_applications_by_system_skips_cyclic_non_application_children(caplog):
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a-ok"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "system", "mid"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "mid", "system", "s1"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s-loop", "system", "other"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "other", "system", "s-loop"),
    ]
    caplog.set_level(logging.WARNING, logger="cmdb")

    result = applications_by_system(["s1", "s-loop"], edge_loader=_loader(graph))

    assert result == {"s1": ["a-ok"], "s-loop": []}
    messages = [record.getMessage() for record in caplog.records if record.name == "cmdb" and record.levelno == logging.WARNING]
    assert "event=service_tree_application_walk_skipped node_uuid=s1 model_id=system reason=cycle" in messages
    assert "event=service_tree_application_walk_skipped node_uuid=s-loop model_id=system reason=cycle" in messages
    assert not any(record.exc_info for record in caplog.records if record.name == "cmdb")


def _model(model_id, name, is_pre):
    return {"model_id": model_id, "model_name": name, "is_pre": is_pre}


def _assoc(src, dst, asst="contains"):
    return {
        "src_model_id": src,
        "dst_model_id": dst,
        "asst_id": asst,
        "model_asst_id": f"{src}_{asst}_{dst}",
    }


_BUILTIN_MODELS = [
    _model("system", "应用系统", True),
    _model("application", "应用", True),
    _model("host", "主机", True),
]


def test_create_layer_button_absent_without_custom_model():
    associations = [
        _assoc("system", "application"),
        _assoc("application", "host", "run"),
    ]
    assert create_layer_models("system", associations, _BUILTIN_MODELS) == []


def test_create_layer_button_uses_custom_model_name_between_system_and_application():
    models = _BUILTIN_MODELS + [_model("env", "环境", False), _model("database", "数据库", False)]
    associations = [
        _assoc("system", "application"),
        _assoc("system", "env"),
        _assoc("env", "application"),
        _assoc("system", "database"),
        _assoc("application", "host", "run"),
    ]
    assert create_layer_models("system", associations, models) == [{"model_id": "env", "model_name": "环境"}]
    assert create_layer_models("env", associations, models) == []
    assert can_create_application_model("env", associations) is True
    assert can_create_application_model("database", associations) is False


def test_build_service_tree_exposes_custom_layer_button_on_system():
    tree = build_service_tree(
        system={"inst_uuid": "s1", "inst_name": "门户"},
        nodes={"a1": {"inst_uuid": "a1", "inst_name": "门户前端", "model_id": "application"}},
        edges=[_edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a1")],
        create_layers_by_model={"system": [{"model_id": "env", "model_name": "环境"}]},
        can_create_application_by_model={"system": True, "application": False},
        model_names={"system": "应用系统", "application": "应用", "env": "环境"},
    )
    assert tree["create_layers"] == [{"model_id": "env", "model_name": "环境"}]
    assert tree["can_create_application"] is True
    assert tree["children"][0]["create_layers"] == []
    assert tree["children"][0]["can_create_application"] is False


def test_assign_adds_edge_and_does_not_drop_existing():
    existing = [
        _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h1"),
        _edge(APPLICATION_RUN_HOST, "application", "a2", "host", "h1"),
    ]
    plan = assign_host_plan("a2", ["h1", "h2"], existing)
    assert plan["create"] == [("a2", "h2")]
    assert plan["delete"] == []


def test_transfer_only_cuts_current_application_edge():
    existing = [
        _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h1"),
        _edge(APPLICATION_RUN_HOST, "application", "a2", "host", "h1"),
        _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h2"),
    ]
    plan = transfer_host_plan(source_app="a1", target_app="a3", host_uuids=["h1"], existing=existing)
    assert plan["delete"] == [("a1", "h1")]
    assert plan["create"] == [("a3", "h1")]
    assert ("a2", "h1") not in plan["delete"]
    assert ("a1", "h2") not in plan["delete"]


def test_unbind_only_cuts_current_application_edge():
    existing = [
        _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h1"),
        _edge(APPLICATION_RUN_HOST, "application", "a2", "host", "h1"),
        _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h2"),
    ]
    plan = unbind_host_plan("a1", ["h1"], existing)
    assert plan["delete"] == [("a1", "h1")]
    assert ("a2", "h1") not in plan["delete"]
    assert ("a1", "h2") not in plan["delete"]


def test_layer_schema_reads_catalog_run_association():
    schema = layer_schema_from(
        [
            _assoc("system", "application"),
            {
                "src_model_id": "application",
                "dst_model_id": "host",
                "asst_id": "run",
                "model_asst_id": "application_host_run",
            },
        ],
        _BUILTIN_MODELS,
    )
    assert schema["run_model_asst_id"] == "application_host_run"
    assert schema["run_src_model"] == "application"


def test_transfer_hosts_uses_catalog_run_association(monkeypatch):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "sys-ops",
        "kind": "system",
        "depth": 0,
        "children": [{"inst_uuid": "a1", "inst_name": "ops-portal", "kind": "application", "depth": 1, "children": []}],
    }
    monkeypatch.setattr(ServiceTreeService, "get_org_tree", classmethod(lambda cls, system, is_visible=None, schema=None: tree))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuid",
        lambda uuid: {"inst_uuid": uuid, "model_id": "application", "inst_name": "notify-platform"},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._require_hosts",
        lambda uuids: [{"inst_uuid": uuid} for uuid in uuids],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._layer_schema",
        lambda: layer_schema_from(
            [
                _assoc("system", "application"),
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "asst_id": "run",
                    "model_asst_id": "application_host_run",
                },
            ],
            _BUILTIN_MODELS,
        ),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._host_edges_for_apps",
        lambda app_uuids, list_loader=None, seen=None, schema=None: [
            {
                "model_asst_id": "application_host_run",
                "asst_id": "run",
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "a1",
                "dst_inst_uuid": "h1",
            }
        ],
    )
    created = []
    deleted = []
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._create_association",
        lambda src, dst, asst, operator: created.append((src, dst, asst)),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._delete_association",
        lambda src, dst, asst, operator: deleted.append((src, dst, asst)),
    )
    ServiceTreeService.transfer_hosts(
        system={"inst_uuid": "s1"},
        source_app="a1",
        target_app="a2",
        host_uuids=["h1"],
        operator="alice",
        target_visible=True,
    )
    assert deleted == [("a1", "h1", "application_host_run")]
    assert created == [("a2", "h1", "application_host_run")]


def test_unbind_hosts_only_cuts_selected_current_app_edge(monkeypatch):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "sys-ops",
        "kind": "system",
        "depth": 0,
        "children": [{"inst_uuid": "a1", "inst_name": "ops-portal", "kind": "application", "depth": 1, "children": []}],
    }
    monkeypatch.setattr(ServiceTreeService, "get_org_tree", classmethod(lambda cls, system, is_visible=None, schema=None: tree))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._require_hosts",
        lambda uuids: [{"inst_uuid": uuid} for uuid in uuids],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._layer_schema",
        lambda: layer_schema_from(
            [
                _assoc("system", "application"),
                {
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "asst_id": "run",
                    "model_asst_id": "application_host_run",
                },
            ],
            _BUILTIN_MODELS,
        ),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._host_edges_for_apps",
        lambda app_uuids, list_loader=None, seen=None, schema=None: [
            {
                "model_asst_id": "application_host_run",
                "asst_id": "run",
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "a1",
                "dst_inst_uuid": "h1",
            },
            {
                "model_asst_id": "application_host_run",
                "asst_id": "run",
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "a1",
                "dst_inst_uuid": "h2",
            },
            {
                "model_asst_id": "application_host_run",
                "asst_id": "run",
                "src_model_id": "application",
                "dst_model_id": "host",
                "src_inst_uuid": "a2",
                "dst_inst_uuid": "h1",
            },
        ],
    )
    created = []
    deleted = []
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._create_association",
        lambda src, dst, asst, operator: created.append((src, dst, asst)),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._delete_association",
        lambda src, dst, asst, operator: deleted.append((src, dst, asst)),
    )
    result = ServiceTreeService.unbind_hosts(
        system={"inst_uuid": "s1"},
        application_uuid="a1",
        host_uuids=["h1"],
        operator="alice",
    )
    assert result["unbound"] == ["h1"]
    assert deleted == [("a1", "h1", "application_host_run")]
    assert created == []


def test_host_mutations_do_not_rebuild_full_tree_with_hosts(monkeypatch):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "sys-ops",
        "kind": "system",
        "depth": 0,
        "children": [{"inst_uuid": "a1", "inst_name": "ops-portal", "kind": "application", "depth": 1, "children": []}],
    }
    monkeypatch.setattr(ServiceTreeService, "get_org_tree", classmethod(lambda cls, system, is_visible=None, schema=None: tree))

    def _boom(*args, **kwargs):
        raise AssertionError("host mutations must not rebuild the full service tree with hosts")

    monkeypatch.setattr(ServiceTreeService, "get_tree", classmethod(_boom))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuid",
        lambda uuid: {"inst_uuid": uuid, "model_id": "application", "inst_name": "notify-platform"},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._require_hosts",
        lambda uuids: [{"inst_uuid": uuid} for uuid in uuids],
    )
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree._host_edges_for_apps", lambda *args, **kwargs: [])
    monkeypatch.setattr("apps.cmdb.services.service_tree._create_association", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.services.service_tree._delete_association", lambda *args, **kwargs: None)

    ServiceTreeService.assign_hosts(
        system={"inst_uuid": "s1"},
        application_uuid="a1",
        host_uuids=["h1"],
        operator="alice",
    )
    ServiceTreeService.unbind_hosts(
        system={"inst_uuid": "s1"},
        application_uuid="a1",
        host_uuids=["h1"],
        operator="alice",
    )
    ServiceTreeService.transfer_hosts(
        system={"inst_uuid": "s1"},
        source_app="a1",
        target_app="a2",
        host_uuids=["h1"],
        operator="alice",
        target_visible=True,
    )


def test_assign_does_not_list_host_uuids_as_applications(monkeypatch):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "sys-ops",
        "kind": "system",
        "depth": 0,
        "children": [{"inst_uuid": "a1", "inst_name": "ops-portal", "kind": "application", "depth": 1, "children": []}],
    }
    monkeypatch.setattr(ServiceTreeService, "get_org_tree", classmethod(lambda cls, system, is_visible=None, schema=None: tree))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._require_hosts",
        lambda uuids: [{"inst_uuid": uuid} for uuid in uuids],
    )
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree.query_association_edges", lambda *args, **kwargs: [])
    listed = []

    def _list(model_id, inst_uuid):
        listed.append((model_id, inst_uuid))
        return []

    monkeypatch.setattr("apps.cmdb.services.service_tree._association_list_loader", _list)
    monkeypatch.setattr("apps.cmdb.services.service_tree._create_association", lambda *args, **kwargs: None)

    ServiceTreeService.assign_hosts(
        system={"inst_uuid": "s1"},
        application_uuid="a1",
        host_uuids=["h1", "h2"],
        operator="alice",
    )
    assert ("application", "h1") not in listed
    assert ("application", "h2") not in listed
    assert listed == [("application", "a1")]


def test_systems_for_applications_walks_direct_system_contains(monkeypatch):
    def _list(model_id, inst_uuid):
        if inst_uuid == "a1":
            return [
                {
                    "model_asst_id": "system_contains_application",
                    "asst_id": "contains",
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "inst_list": [{"inst_uuid": "s1", "model_id": "system", "inst_name": "sys-ops"}],
                }
            ]
        return []

    monkeypatch.setattr("apps.cmdb.services.service_tree._association_list_loader", _list)
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    assert ServiceTreeService.systems_for_applications(["a1"]) == {"a1": {"inst_uuid": "s1", "inst_name": "sys-ops"}}


def test_parse_import_row_requires_application_and_host():
    ok = parse_import_row(
        {
            "system": "门户",
            "application": "门户前端",
            "host": "web-1",
        },
        expected_system_name="门户",
    )
    assert ok["application"] == "门户前端"
    assert ok["host"] == "web-1"
    assert "group" not in ok

    try:
        parse_import_row(
            {"system": "门户", "application": "", "host": "web-1"},
            expected_system_name="门户",
        )
    except ValidationAppException as exc:
        assert "应用" in exc.message
    else:
        raise AssertionError("expected ValidationAppException")


def test_parse_import_row_empty_extra_columns_are_ignored():
    row = parse_import_row(
        {"应用系统": "门户", "业务分组": "生产", "二级分组": "web", "应用": "门户前端", "主机标识": "10.0.0.1"},
        expected_system_name="门户",
    )
    assert row["application"] == "门户前端"
    assert row["host"] == "10.0.0.1"
    assert "group" not in row


def test_match_host_requires_unique_existing_identity():
    hosts = [
        {"inst_uuid": "h1", "inst_name": "web-1", "ip_addr": "10.0.0.1"},
        {"inst_uuid": "h2", "inst_name": "web-2", "ip_addr": "10.0.0.2"},
        {"inst_uuid": "h3", "inst_name": "dup-ip", "ip_addr": "10.0.0.9"},
        {"inst_uuid": "h4", "inst_name": "dup-ip-2", "ip_addr": "10.0.0.9"},
    ]
    assert match_host("web-1", hosts)["inst_uuid"] == "h1"
    assert match_host("10.0.0.2", hosts)["inst_uuid"] == "h2"
    assert match_host("h1", hosts)["inst_uuid"] == "h1"
    try:
        match_host("missing", hosts)
    except ValidationAppException as exc:
        assert "主机" in exc.message
    else:
        raise AssertionError("expected ValidationAppException")
    try:
        match_host("10.0.0.9", hosts)
    except ValidationAppException as exc:
        assert "不唯一" in exc.message
    else:
        raise AssertionError("expected ValidationAppException")


def test_plan_import_creates_missing_apps_and_assigns_host():
    plan = plan_import_rows(
        system_name="门户",
        system_uuid="s1",
        rows=[
            {"system": "门户", "application": "门户前端", "host": "web-1"},
            {"system": "门户", "application": "直挂应用", "host": "web-2"},
        ],
        existing_tree={"apps": {}},
        hosts=[{"inst_uuid": "h1", "inst_name": "web-1", "ip_addr": "10.0.0.1"}, {"inst_uuid": "h2", "inst_name": "web-2"}],
    )
    assert plan["errors"] == []
    created = {(item["model_id"], item["inst_name"], item["parent_key"]) for item in plan["create_nodes"]}
    assert ("application", "门户前端", "s1") in created
    assert ("application", "直挂应用", "s1") in created
    assert {(item["app_key"], item["host_uuid"]) for item in plan["assign"]} == {
        ("a:/门户前端", "h1"),
        ("a:/直挂应用", "h2"),
    }


def test_plan_import_reuses_application_by_name_under_system():
    plan = plan_import_rows(
        system_name="门户",
        system_uuid="s1",
        rows=[{"system": "门户", "application": "门户前端", "host": "web-2"}],
        existing_tree={"apps": {"a:/门户前端": "a1"}},
        hosts=[{"inst_uuid": "h2", "inst_name": "web-2"}],
    )
    assert plan["create_nodes"] == []
    assert plan["assign"] == [{"app_key": "a1", "host_uuid": "h2"}]


def test_plan_import_fails_unknown_host_without_creating_that_row():
    plan = plan_import_rows(
        system_name="门户",
        system_uuid="s1",
        rows=[{"system": "门户", "application": "门户前端", "host": "ghost"}],
        existing_tree={"apps": {}},
        hosts=[{"inst_uuid": "h1", "inst_name": "web-1"}],
    )
    assert plan["assign"] == []
    assert len(plan["errors"]) == 1
    assert "主机" in plan["errors"][0]["message"]


class _VisitCountingHosts:
    """每次产出一台主机记一次，用来区分整批建索引和按行重扫。"""

    def __init__(self, hosts):
        self._hosts = list(hosts)
        self.visits = 0

    def __iter__(self):
        for host in self._hosts:
            self.visits += 1
            yield host


def _uuid4_hosts(size):
    return [
        {
            "inst_uuid": str(uuid4()),
            "inst_name": f"host-{index}",
            "ip_addr": f"10.{(index // 65536) % 256}.{(index // 256) % 256}.{index % 256}",
        }
        for index in range(size)
    ]


def test_match_host_prefers_uuid_over_name_and_keeps_ambiguous_lists():
    hosts = [
        {"inst_uuid": "uuid-1", "inst_name": "same-name", "ip_addr": "10.1.0.1"},
        {"inst_uuid": "same-name", "inst_name": "other", "ip_addr": "10.1.0.2"},
        {"inst_uuid": "uuid-3", "inst_name": "solo", "ip_addr": "10.1.0.3"},
    ]
    assert match_host("same-name", hosts)["inst_uuid"] == "same-name"
    assert match_host("solo", hosts)["inst_uuid"] == "uuid-3"
    assert match_host("10.1.0.3", hosts)["inst_uuid"] == "uuid-3"

    duplicate_names = [
        {"inst_uuid": "n1", "inst_name": "dup", "ip_addr": "10.2.0.1"},
        {"inst_uuid": "n2", "inst_name": "dup", "ip_addr": "10.2.0.2"},
    ]
    assert match_host("n1", duplicate_names)["inst_uuid"] == "n1"
    try:
        match_host("dup", duplicate_names)
    except ValidationAppException as exc:
        assert exc.message == "主机标识匹配不唯一"
    else:
        raise AssertionError("expected ValidationAppException")

    duplicate_ips = [
        {"inst_uuid": "i1", "inst_name": "ip-a", "ip_addr": "10.9.0.1"},
        {"inst_uuid": "i2", "inst_name": "ip-b", "ip_addr": "10.9.0.1"},
    ]
    try:
        match_host("10.9.0.1", duplicate_ips)
    except ValidationAppException as exc:
        assert exc.message == "主机标识匹配不唯一"
    else:
        raise AssertionError("expected ValidationAppException")

    try:
        match_host("missing-host", hosts)
    except ValidationAppException as exc:
        assert exc.message == "找不到对应的主机"
    else:
        raise AssertionError("expected ValidationAppException")


def test_plan_import_rows_scans_each_host_once():
    mismatches = []
    for size in (1000, 2000):
        raw_hosts = _uuid4_hosts(size)
        assert all(len(host["inst_uuid"]) == 36 for host in raw_hosts)
        counting = _VisitCountingHosts(raw_hosts)
        rows = [
            {"system": "门户", "application": "门户前端", "host": host["inst_uuid"]}
            for host in raw_hosts
        ]
        plan = plan_import_rows(
            system_name="门户",
            system_uuid="s1",
            rows=rows,
            existing_tree={"apps": {}},
            hosts=counting,
        )
        if counting.visits != size:
            mismatches.append((size, counting.visits))
        assert plan["errors"] == []
        assert [item["host_uuid"] for item in plan["assign"]] == [host["inst_uuid"] for host in raw_hosts]
    assert mismatches == []


_HOST_UUID = "123e4567-e89b-42d3-a456-426614174000"
_OTHER_HOST_UUID = "123e4567-e89b-42d3-a456-426614174001"


def _import_row(host, application="门户前端", system="门户"):
    return {"应用系统": system, "应用": application, "主机标识": host}


class _RecordingGraph:
    def __init__(self, hosts):
        self.hosts = list(hosts)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query_entity(self, label, params, **kwargs):
        self.calls.append(list(params))
        indexed = {item.get("field"): item.get("value") for item in params}
        if indexed.get("model_id") != "host":
            return [], 0
        matched = list(self.hosts)
        if "inst_uuid" in indexed:
            wanted = set(indexed["inst_uuid"] or [])
            matched = [item for item in matched if item.get("inst_uuid") in wanted]
        elif "inst_name" in indexed:
            wanted = set(indexed["inst_name"] or [])
            matched = [item for item in matched if item.get("inst_name") in wanted]
        elif "ip_addr" in indexed:
            wanted = set(indexed["ip_addr"] or [])
            matched = [item for item in matched if item.get("ip_addr") in wanted]
        else:
            matched = []
        return matched, len(matched)


def _patch_host_graph(monkeypatch, hosts):
    graph = _RecordingGraph(hosts)

    def factory(**kwargs):
        return graph

    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", factory)
    monkeypatch.setattr("apps.cmdb.services.service_tree.GraphClient", factory)
    return graph


def _query_values(graph, field):
    values = []
    for params in graph.calls:
        for item in params:
            if item.get("field") == field:
                values.extend(item.get("value") or [])
    return values


def test_import_preload_accepts_name_ip_and_uuid_and_keeps_unknown_row(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="apps.core.exceptions.base_app_exception")
    host = {
        "inst_uuid": _HOST_UUID,
        "inst_name": "web-1",
        "ip_addr": "192.0.2.10",
        "model_id": "host",
    }
    graph = _patch_host_graph(monkeypatch, [host])
    rows = [
        _import_row("web-1"),
        _import_row("192.0.2.10"),
        _import_row(_HOST_UUID),
        _import_row("missing-host"),
    ]

    hosts = _lookup_hosts_for_rows(rows)

    assert match_host("web-1", hosts)["inst_uuid"] == _HOST_UUID
    assert match_host("192.0.2.10", hosts)["inst_uuid"] == _HOST_UUID
    assert match_host(_HOST_UUID, hosts)["inst_uuid"] == _HOST_UUID
    uuid_values = _query_values(graph, "inst_uuid")
    assert uuid_values == [_HOST_UUID]
    assert "web-1" not in uuid_values
    assert "192.0.2.10" not in uuid_values
    assert "missing-host" not in uuid_values
    assert "web-1" in _query_values(graph, "inst_name")
    assert "192.0.2.10" in _query_values(graph, "ip_addr")
    assert "inst_uuid 必须是 UUIDv4" not in caplog.text

    plan = plan_import_rows(
        system_name="门户",
        system_uuid="s1",
        rows=rows,
        existing_tree={"apps": {"a:/门户前端": "a1"}},
        hosts=hosts,
    )
    assert plan["create_nodes"] == []
    assert [item["host_uuid"] for item in plan["assign"]] == [_HOST_UUID, _HOST_UUID, _HOST_UUID]
    assert [(item["row"], item["message"]) for item in plan["errors"]] == [(4, "找不到对应的主机")]


def test_import_preload_reports_ambiguous_host_name_per_row(monkeypatch):
    _patch_host_graph(
        monkeypatch,
        [
            {
                "inst_uuid": _HOST_UUID,
                "inst_name": "web-1",
                "ip_addr": "192.0.2.10",
                "model_id": "host",
            },
            {
                "inst_uuid": _OTHER_HOST_UUID,
                "inst_name": "web-1",
                "ip_addr": "192.0.2.11",
                "model_id": "host",
            },
        ],
    )
    rows = [_import_row("web-1")]

    plan = plan_import_rows(
        system_name="门户",
        system_uuid="s1",
        rows=rows,
        existing_tree={"apps": {}},
        hosts=_lookup_hosts_for_rows(rows),
    )

    assert plan["assign"] == []
    assert plan["create_nodes"] == []
    assert [(item["row"], item["message"]) for item in plan["errors"]] == [(1, "主机标识匹配不唯一")]


def test_build_service_tree_shows_contains_application_even_if_asst_id_is_not_seeded_name():
    tree = build_service_tree(
        system={"inst_uuid": "s1", "inst_name": "sys-ops"},
        nodes={"a1": {"inst_uuid": "a1", "inst_name": "门户前端", "model_id": "application"}},
        edges=[
            {
                "model_asst_id": "system_application_contains",
                "asst_id": "contains",
                "src_model_id": "system",
                "src_inst_uuid": "s1",
                "dst_model_id": "application",
                "dst_inst_uuid": "a1",
            }
        ],
    )
    assert [child["inst_name"] for child in tree["children"]] == ["门户前端"]
    assert tree["children"][0]["kind"] == "application"


def test_get_tree_reads_contains_applications_from_association_list(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree.query_association_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.instance_association_instance_list_by_uuid",
        lambda model_id, inst_uuid, **kwargs: [
            {
                "model_asst_id": "system_application_contains",
                "asst_id": "contains",
                "src_model_id": "system",
                "dst_model_id": "application",
                "inst_list": [{"inst_uuid": "a1", "model_id": "application", "inst_name": "门户前端"}],
            }
        ]
        if model_id == "system"
        else [],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuids",
        lambda uuids: [{"inst_uuid": "a1", "inst_name": "门户前端", "model_id": "application"}] if "a1" in uuids else [],
    )
    tree = ServiceTreeService.get_tree({"inst_uuid": "s1", "inst_name": "sys-ops"})
    assert [child["inst_name"] for child in tree["children"]] == ["门户前端"]
    assert tree["children"][0]["host_count"] == 0


def test_build_service_tree_counts_run_hosts_even_if_asst_id_is_not_seeded_name():
    tree = build_service_tree(
        system={"inst_uuid": "s1", "inst_name": "sys-ops"},
        nodes={
            "a1": {"inst_uuid": "a1", "inst_name": "ops-portal", "model_id": "application"},
            "h1": {"inst_uuid": "h1", "inst_name": "web-1", "model_id": "host", "ip_addr": "10.0.0.1"},
        },
        edges=[
            {
                "model_asst_id": "application_host_run",
                "asst_id": "run",
                "src_model_id": "application",
                "src_inst_uuid": "a1",
                "dst_model_id": "host",
                "dst_inst_uuid": "h1",
            },
            {
                "model_asst_id": "system_application_contains",
                "asst_id": "contains",
                "src_model_id": "system",
                "src_inst_uuid": "s1",
                "dst_model_id": "application",
                "dst_inst_uuid": "a1",
            },
        ],
    )
    assert tree["children"][0]["host_count"] == 1
    assert tree["host_count"] == 1


def test_get_tree_reads_run_hosts_from_association_list(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree.query_association_edges", lambda *args, **kwargs: [])

    def _list(model_id, inst_uuid, **kwargs):
        if model_id == "system":
            return [
                {
                    "model_asst_id": "system_application_contains",
                    "asst_id": "contains",
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "inst_list": [{"inst_uuid": "a1", "model_id": "application", "inst_name": "ops-portal"}],
                }
            ]
        if model_id == "application":
            return [
                {
                    "model_asst_id": "application_host_run",
                    "asst_id": "run",
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "inst_list": [{"inst_uuid": "h1", "model_id": "host", "inst_name": "web-1", "ip_addr": "10.0.0.1"}],
                }
            ]
        return []

    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.instance_association_instance_list_by_uuid",
        _list,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            item
            for item in [
                {"inst_uuid": "a1", "inst_name": "ops-portal", "model_id": "application"},
                {"inst_uuid": "h1", "inst_name": "web-1", "model_id": "host", "ip_addr": "10.0.0.1"},
            ]
            if item["inst_uuid"] in set(uuids)
        ],
    )
    tree = ServiceTreeService.get_tree({"inst_uuid": "s1", "inst_name": "sys-ops"})
    assert tree["children"][0]["inst_name"] == "ops-portal"
    assert tree["children"][0]["host_count"] == 1
    assert [child["kind"] for child in tree["children"]] == ["application"]
    detail = ServiceTreeService.list_node_hosts({"inst_uuid": "s1", "inst_name": "sys-ops"}, "a1")
    assert [row["inst_name"] for row in detail["hosts"]] == ["web-1"]


def test_list_node_hosts_only_loads_selected_application_associations(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree.query_association_edges", lambda *args, **kwargs: [])
    listed_apps: list[str] = []

    def _list(model_id, inst_uuid, **kwargs):
        if model_id == "system":
            return [
                {
                    "model_asst_id": "system_application_contains",
                    "asst_id": "contains",
                    "src_model_id": "system",
                    "dst_model_id": "application",
                    "inst_list": [
                        {"inst_uuid": "a1", "model_id": "application", "inst_name": "ops-portal"},
                        {"inst_uuid": "a2", "model_id": "application", "inst_name": "notify-platform"},
                    ],
                }
            ]
        if model_id == "application":
            listed_apps.append(inst_uuid)
            host = {
                "a1": {"inst_uuid": "h1", "model_id": "host", "inst_name": "web-1"},
                "a2": {"inst_uuid": "h2", "model_id": "host", "inst_name": "web-2"},
            }[inst_uuid]
            return [
                {
                    "model_asst_id": "application_host_run",
                    "asst_id": "run",
                    "src_model_id": "application",
                    "dst_model_id": "host",
                    "inst_list": [host],
                }
            ]
        return []

    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.instance_association_instance_list_by_uuid",
        _list,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            item
            for item in [
                {"inst_uuid": "a1", "inst_name": "ops-portal", "model_id": "application"},
                {"inst_uuid": "a2", "inst_name": "notify-platform", "model_id": "application"},
                {"inst_uuid": "h1", "inst_name": "web-1", "model_id": "host"},
                {"inst_uuid": "h2", "inst_name": "web-2", "model_id": "host"},
            ]
            if item["inst_uuid"] in set(uuids)
        ],
    )
    detail = ServiceTreeService.list_node_hosts({"inst_uuid": "s1", "inst_name": "sys-ops"}, "a1")
    assert [row["inst_name"] for row in detail["hosts"]] == ["web-1"]
    assert listed_apps == ["a1"]


def test_build_service_tree_stops_at_application_and_counts_hosts():
    tree = build_service_tree(
        system={"inst_uuid": "s1", "inst_name": "门户"},
        nodes={
            "a1": {"inst_uuid": "a1", "inst_name": "门户前端", "model_id": "application"},
            "a2": {"inst_uuid": "a2", "inst_name": "直挂", "model_id": "application"},
        },
        edges=[
            _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a1"),
            _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a2"),
            _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h1"),
            _edge(APPLICATION_RUN_HOST, "application", "a1", "host", "h2"),
            _edge(APPLICATION_RUN_HOST, "application", "a2", "host", "h2"),
        ],
    )
    assert tree["kind"] == "system"
    assert tree["host_count"] == 2
    kinds = [child["kind"] for child in tree["children"]]
    assert kinds == ["application", "application"]
    assert "host" not in kinds
    by_name = {child["inst_name"]: child for child in tree["children"]}
    assert by_name["门户前端"]["host_count"] == 2
    assert by_name["直挂"]["host_count"] == 1


def test_build_service_tree_omits_invisible_nodes():
    tree = build_service_tree(
        system={"inst_uuid": "s1", "inst_name": "门户"},
        nodes={
            "a1": {"inst_uuid": "a1", "inst_name": "门户前端", "model_id": "application"},
            "a2": {"inst_uuid": "a2", "inst_name": "直挂", "model_id": "application"},
        },
        edges=[
            _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a1"),
            _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "a2"),
        ],
        visible_uuids={"a2"},
    )
    assert [child["inst_uuid"] for child in tree["children"]] == ["a2"]


def test_create_child_logs_lifecycle_template_and_keeps_return_contract(monkeypatch, caplog):
    sentinel = "password=super-secret-token"
    tree = {
        "inst_uuid": "s1",
        "inst_name": "门户",
        "kind": "system",
        "depth": 0,
        "children": [],
    }
    monkeypatch.setattr(ServiceTreeService, "get_tree", classmethod(lambda cls, system, is_visible=None: tree))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._create_instance",
        lambda *args, **kwargs: {"inst_uuid": "a-new", "inst_name": "门户前端"},
    )
    monkeypatch.setattr("apps.cmdb.services.service_tree._create_association", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="cmdb")

    result = ServiceTreeService.create_child(
        system={"inst_uuid": "s1", "organization": [1], "inst_name": sentinel},
        parent_uuid="s1",
        kind="application",
        inst_name="门户前端",
        operator="alice",
    )

    assert result == {"inst_uuid": "a-new", "inst_name": "门户前端", "kind": "application"}
    records = [record for record in caplog.records if record.name == "cmdb" and "event=service_tree_child_created" in record.msg]
    assert len(records) == 1
    assert records[0].msg == "event=service_tree_child_created system_uuid=%s parent_uuid=%s child_uuid=%s kind=%s"
    assert records[0].args == ("s1", "s1", "a-new", "application")
    assert records[0].getMessage() == "event=service_tree_child_created system_uuid=s1 parent_uuid=s1 child_uuid=a-new kind=application"
    assert sentinel not in records[0].getMessage()
    assert "alice" not in records[0].getMessage()
    assert "password" not in records[0].getMessage()


def test_create_child_custom_layer_uses_model_association(monkeypatch):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "门户",
        "kind": "system",
        "depth": 0,
        "children": [],
    }
    monkeypatch.setattr(ServiceTreeService, "get_tree", classmethod(lambda cls, system, is_visible=None: tree))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._create_instance",
        lambda model_id, *args, **kwargs: {"inst_uuid": "e-new", "inst_name": "生产", "model_id": model_id},
    )
    created = {}

    def capture_association(src_uuid, dst_uuid, model_asst_id, operator):
        created["asst"] = model_asst_id

    monkeypatch.setattr("apps.cmdb.services.service_tree._create_association", capture_association)
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree._layer_schema",
        lambda: layer_schema_from(
            [
                _assoc("system", "application"),
                _assoc("system", "env"),
                _assoc("env", "application"),
            ],
            _BUILTIN_MODELS + [_model("env", "环境", False)],
        ),
    )

    result = ServiceTreeService.create_child(
        system={"inst_uuid": "s1", "organization": [1], "inst_name": "门户"},
        parent_uuid="s1",
        kind="env",
        inst_name="生产",
        operator="alice",
    )
    assert result["kind"] == "env"
    assert created["asst"] == "system_contains_env"


def test_delete_node_logs_lifecycle_template(monkeypatch, caplog):
    tree = {
        "inst_uuid": "s1",
        "inst_name": "门户",
        "kind": "system",
        "depth": 0,
        "children": [{"inst_uuid": "a1", "inst_name": "门户前端", "kind": "application", "depth": 1, "children": []}],
    }
    monkeypatch.setattr(ServiceTreeService, "get_tree", classmethod(lambda cls, system, is_visible=None: tree))
    monkeypatch.setattr("apps.cmdb.services.service_tree.InstanceManage.instance_batch_delete_by_uuids", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="cmdb")

    result = ServiceTreeService.delete_node(
        system={"inst_uuid": "s1"},
        node_uuid="a1",
        operator="alice",
        user_groups=[],
        roles=[],
    )

    assert result is None
    records = [record for record in caplog.records if record.name == "cmdb" and "event=service_tree_node_deleted" in record.msg]
    assert len(records) == 1
    assert records[0].msg == "event=service_tree_node_deleted system_uuid=%s node_uuid=%s kind=%s"
    assert records[0].args == ("s1", "a1", "application")
    assert records[0].getMessage() == "event=service_tree_node_deleted system_uuid=s1 node_uuid=a1 kind=application"
    assert "alice" not in records[0].getMessage()


_PORTAL_SYSTEM = "11111111-1111-4111-8111-111111111111"
_PORTAL_FRONT = "22222222-2222-4222-8222-222222222222"
_PORTAL_BACK = "33333333-3333-4333-8333-333333333333"
_HOST_WEB = "44444444-4444-4444-8444-444444444444"
_HOST_DB = "55555555-5555-4555-8555-555555555555"


def _service_tree_edge(asst_id, model_asst, src_model, src, dst_model, dst):
    edge = _edge(model_asst, src_model, src, dst_model, dst)
    edge["asst_id"] = asst_id
    edge["_id"] = f"{model_asst}:{src}:{dst}"
    return edge


def _stub_service_tree_graph(monkeypatch, edges, entities):
    """只替换图查询。批量实例查询仍走 query_entity_by_uuids 的重复校验。"""
    queried: list[list[str]] = []

    def _matches(edge, params):
        for item in params or []:
            field = item.get("field")
            value = item.get("value")
            kind = str(item.get("type") or "")
            current = edge.get(field)
            if kind.endswith("[]"):
                if current not in set(value or []):
                    return False
            elif current != value:
                return False
        return True

    def _wrap(edge):
        src_uuid = edge["src_inst_uuid"]
        dst_uuid = edge["dst_inst_uuid"]
        src = dict(entities.get(src_uuid) or {"inst_uuid": src_uuid, "model_id": edge["src_model_id"]})
        dst = dict(entities.get(dst_uuid) or {"inst_uuid": dst_uuid, "model_id": edge["dst_model_id"]})
        return {"edge": dict(edge), "src": src, "dst": dst}

    class _Graph:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def query_edge(self, _label, params, **_kwargs):
            return [_wrap(edge) for edge in edges if _matches(edge, params)]

        def query_entity_by_inst_uuids(self, values):
            queried.append(list(values))
            return [dict(entities[value]) for value in values if value in entities]

    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.application_system.GraphClient", lambda **_kwargs: _Graph())
    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", lambda **_kwargs: _Graph())
    return queried


def _portal_entities(*hosts):
    entities = {
        _PORTAL_FRONT: {"inst_uuid": _PORTAL_FRONT, "inst_name": "门户前端", "model_id": "application"},
        _PORTAL_BACK: {"inst_uuid": _PORTAL_BACK, "inst_name": "门户后端", "model_id": "application"},
    }
    for host_uuid, name in hosts:
        entities[host_uuid] = {"inst_uuid": host_uuid, "inst_name": name, "model_id": "host", "ip_addr": "10.0.0.1"}
    return entities


def _portal_edges(*host_links):
    edges = [
        _service_tree_edge("contains", SYSTEM_CONTAINS_APPLICATION, "system", _PORTAL_SYSTEM, "application", _PORTAL_FRONT),
        _service_tree_edge("contains", SYSTEM_CONTAINS_APPLICATION, "system", _PORTAL_SYSTEM, "application", _PORTAL_BACK),
    ]
    for app_uuid, host_uuid in host_links:
        edges.append(_service_tree_edge("run", APPLICATION_RUN_HOST, "application", app_uuid, "host", host_uuid))
    return edges


def test_export_rows_distinct_hosts_keeps_one_row_per_application(monkeypatch):
    queried = _stub_service_tree_graph(
        monkeypatch,
        _portal_edges((_PORTAL_FRONT, _HOST_WEB), (_PORTAL_BACK, _HOST_DB)),
        _portal_entities((_HOST_WEB, "web-1"), (_HOST_DB, "db-1")),
    )

    rows = ServiceTreeService.export_rows({"inst_uuid": _PORTAL_SYSTEM, "inst_name": "门户"})

    assert rows == [
        {"应用系统": "门户", "应用": "门户前端", "主机标识": "web-1"},
        {"应用系统": "门户", "应用": "门户后端", "主机标识": "db-1"},
    ]
    assert [call for call in queried if _HOST_WEB in call or _HOST_DB in call] == [[_HOST_WEB, _HOST_DB]]


def test_export_rows_shared_host_keeps_one_row_per_application(monkeypatch):
    with pytest.raises(BaseAppException, match="inst_uuid 不允许重复"):
        InstanceManage.query_entity_by_uuids([_HOST_WEB, _HOST_WEB])

    queried = _stub_service_tree_graph(
        monkeypatch,
        _portal_edges((_PORTAL_FRONT, _HOST_WEB), (_PORTAL_BACK, _HOST_WEB)),
        _portal_entities((_HOST_WEB, "web-1")),
    )

    rows = ServiceTreeService.export_rows({"inst_uuid": _PORTAL_SYSTEM, "inst_name": "门户"})

    assert rows == [
        {"应用系统": "门户", "应用": "门户前端", "主机标识": "web-1"},
        {"应用系统": "门户", "应用": "门户后端", "主机标识": "web-1"},
    ]
    assert [call for call in queried if _HOST_WEB in call] == [[_HOST_WEB]]


def _service_tree_visibility_catalog():
    return {
        "aa": {"inst_uuid": "aa", "model_id": "application", "inst_name": "应用甲"},
        "ab": {"inst_uuid": "ab", "model_id": "application", "inst_name": "应用乙"},
        "hv": {"inst_uuid": "hv", "model_id": "host", "inst_name": "可见主机", "ip_addr": "10.1.1.1"},
        "hb": {"inst_uuid": "hb", "model_id": "host", "inst_name": "隐藏主机", "ip_addr": "10.9.9.9"},
        "hip": {"inst_uuid": "hip", "model_id": "host", "inst_name": "", "ip_addr": "10.2.2.2"},
        "huid": {"inst_uuid": "huid", "model_id": "host", "inst_name": "", "ip_addr": ""},
    }


def _install_service_tree_visibility_graph(monkeypatch):
    catalog = _service_tree_visibility_catalog()
    graph = [
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "aa"),
        _edge(SYSTEM_CONTAINS_APPLICATION, "system", "s1", "application", "ab"),
        _edge(APPLICATION_RUN_HOST, "application", "aa", "host", "hv"),
        _edge(APPLICATION_RUN_HOST, "application", "aa", "host", "hb"),
        _edge(APPLICATION_RUN_HOST, "application", "aa", "host", "hm"),
        _edge(APPLICATION_RUN_HOST, "application", "aa", "host", "hip"),
        _edge(APPLICATION_RUN_HOST, "application", "aa", "host", "huid"),
        _edge(APPLICATION_RUN_HOST, "application", "ab", "host", "hv"),
    ]
    monkeypatch.setattr("apps.cmdb.services.service_tree._layer_schema", lambda: layer_schema_from([], []))
    monkeypatch.setattr("apps.cmdb.services.service_tree.query_association_edges", _loader(graph))
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.instance_association_instance_list_by_uuid",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.service_tree.InstanceManage.query_entity_by_uuids",
        lambda uuids: [catalog[item] for item in uuids if item in catalog],
    )


def test_export_rows_omits_hidden_and_missing_hosts(monkeypatch):
    _install_service_tree_visibility_graph(monkeypatch)
    system = {"inst_uuid": "s1", "inst_name": "门户"}

    def is_visible(item):
        return item.get("inst_uuid") != "hb"

    detail = ServiceTreeService.list_node_hosts(system, "aa", is_visible=is_visible)
    listed = detail["hosts"]
    assert "hb" not in [row["inst_uuid"] for row in listed]
    assert "隐藏主机" not in [row["inst_name"] for row in listed]
    assert "10.9.9.9" not in [row["ip_addr"] for row in listed]
    assert "hv" in [row["inst_uuid"] for row in listed]

    rows = ServiceTreeService.export_rows(system, is_visible=is_visible)
    assert rows == [
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "可见主机"},
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "10.2.2.2"},
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "huid"},
        {"应用系统": "门户", "应用": "应用乙", "主机标识": "可见主机"},
    ]
    identifiers = [row["主机标识"] for row in rows]
    assert identifiers.count("可见主机") == 2
    for leaked in ("隐藏主机", "10.9.9.9", "hb", "hm"):
        assert leaked not in identifiers

    plain = ServiceTreeService.export_rows(system, is_visible=None)
    assert plain == [
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "可见主机"},
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "隐藏主机"},
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "10.2.2.2"},
        {"应用系统": "门户", "应用": "应用甲", "主机标识": "huid"},
        {"应用系统": "门户", "应用": "应用乙", "主机标识": "可见主机"},
    ]
    assert "hm" not in [row["主机标识"] for row in plain]
