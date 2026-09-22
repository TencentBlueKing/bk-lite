import logging

from apps.cmdb.services.application_system import expand_systems_to_host_uuids
from apps.cmdb.services.service_tree import (
    APPLICATION_RUN_HOST,
    SYSTEM_CONTAINS_APPLICATION,
    ServiceTreeService,
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
from apps.core.exceptions.base_app_exception import ValidationAppException


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
