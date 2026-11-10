import logging
from pathlib import Path

from apps.cmdb.constants.constants import INSTANCE, MODEL
from apps.cmdb.nats.nats import incident_impact_topology
from apps.cmdb.services.incident_impact_topology import SEED_LIMIT, assemble_incident_impact_topology, query_incident_impact_topology
from apps.core.logger import SafeLogException

HOST_A = "00000000-0000-4000-8000-000000000001"
HOST_B = "00000000-0000-4000-8000-000000000002"
APP = "00000000-0000-4000-8000-000000000003"
VM_A = "00000000-0000-4000-8000-000000000004"
VM_B = "00000000-0000-4000-8000-000000000005"
SHARED_HOST = "00000000-0000-4000-8000-000000000006"
CUSTOM_A = "00000000-0000-4000-8000-000000000007"
CUSTOM_B = "00000000-0000-4000-8000-000000000008"
CUSTOM_PARENT = "00000000-0000-4000-8000-000000000009"
SWITCH = "00000000-0000-4000-8000-000000000010"
NGINX = "00000000-0000-4000-8000-000000000011"
MISSING = "00000000-0000-4000-8000-000000000012"


def _node(inst_uuid, name, model_id, layer, visible=True):
    return {
        "inst_uuid": inst_uuid,
        "inst_name": name,
        "model_id": model_id,
        "model_name": model_id,
        "layer": layer,
        "visible": visible,
    }


def _edge(src, dst, asst_id, model_asst_id=None, asst_name=""):
    return {
        "src_inst_uuid": src,
        "dst_inst_uuid": dst,
        "asst_id": asst_id,
        "model_asst_id": model_asst_id or f"{src}_{asst_id}_{dst}",
        "asst_name": asst_name or ("运行于" if asst_id == "run" else "关联"),
    }


def _by_uuid(nodes):
    return {item["inst_uuid"]: item for item in nodes}


def _roles(result):
    return {item["inst_uuid"]: item["role"] for item in result["nodes"]}


def test_two_hosts_share_an_application_bridge():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        HOST_B: _node(HOST_B, "web-02", "host", "host"),
        APP: _node(APP, "支付中台", "application", "service"),
    }
    edges = [
        _edge(APP, HOST_A, "run", "application_run_host"),
        _edge(APP, HOST_B, "run", "application_run_host"),
    ]
    result = assemble_incident_impact_topology([HOST_A, HOST_B], instances, edges)
    assert _roles(result)[APP] == "bridge"
    assert {item["inst_uuid"] for item in result["nodes"] if item["role"] == "seed"} == {HOST_A, HOST_B}
    assert {item["parent_inst_uuid"] for item in result["links"]} == {APP}
    assert len(result["links"]) == 2


def test_two_vms_share_a_host_and_run_parent_is_dst():
    instances = {
        VM_A: _node(VM_A, "vm-a", "vm", "host"),
        VM_B: _node(VM_B, "vm-b", "vm", "host"),
        SHARED_HOST: _node(SHARED_HOST, "host-1", "host", "host"),
    }
    edges = [
        _edge(VM_A, SHARED_HOST, "run", "vm_run_host"),
        _edge(VM_B, SHARED_HOST, "run", "vm_run_host"),
    ]
    result = assemble_incident_impact_topology([VM_A, VM_B], instances, edges)
    assert _roles(result)[SHARED_HOST] == "bridge"
    assert {item["parent_inst_uuid"] for item in result["links"]} == {SHARED_HOST}


def test_unranked_run_parent_is_the_dst():
    instances = {
        CUSTOM_A: _node(CUSTOM_A, "a", "custom_a", "none"),
        CUSTOM_B: _node(CUSTOM_B, "b", "custom_b", "none"),
        CUSTOM_PARENT: _node(CUSTOM_PARENT, "dst", "custom_c", "none"),
    }
    edges = [
        _edge(CUSTOM_A, CUSTOM_PARENT, "run"),
        _edge(CUSTOM_B, CUSTOM_PARENT, "run"),
    ]
    result = assemble_incident_impact_topology([CUSTOM_A, CUSTOM_B], instances, edges)
    assert _roles(result)[CUSTOM_PARENT] == "bridge"
    assert {item["parent_inst_uuid"] for item in result["links"]} == {CUSTOM_PARENT}


def test_unranked_connect_parent_is_the_src():
    instances = {
        CUSTOM_A: _node(CUSTOM_A, "a", "custom_a", "none"),
        CUSTOM_B: _node(CUSTOM_B, "b", "custom_b", "none"),
        CUSTOM_PARENT: _node(CUSTOM_PARENT, "src", "custom_c", "none"),
    }
    edges = [
        _edge(CUSTOM_PARENT, CUSTOM_A, "connect"),
        _edge(CUSTOM_PARENT, CUSTOM_B, "connect"),
    ]
    result = assemble_incident_impact_topology([CUSTOM_A, CUSTOM_B], instances, edges)
    assert _roles(result)[CUSTOM_PARENT] == "bridge"
    assert {item["parent_inst_uuid"] for item in result["links"]} == {CUSTOM_PARENT}


def test_different_layers_override_run_direction():
    instances = {
        APP: _node(APP, "支付中台", "application", "service"),
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
    }
    result = assemble_incident_impact_topology([APP, HOST_A], instances, [_edge(APP, HOST_A, "run", "application_run_host")])
    assert result["links"][0]["parent_inst_uuid"] == APP
    assert APP not in {item["inst_uuid"] for item in result["nodes"] if item["role"] == "bridge"}


def test_single_seed_does_not_pull_its_parent():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        APP: _node(APP, "支付中台", "application", "service"),
    }
    result = assemble_incident_impact_topology([HOST_A], instances, [_edge(APP, HOST_A, "run", "application_run_host")])
    assert [item["inst_uuid"] for item in result["nodes"]] == [HOST_A]
    assert result["links"] == []


def test_edge_between_two_seeds_is_kept_when_one_is_infrastructure():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        SWITCH: _node(SWITCH, "sw-1", "switch", "infrastructure"),
    }
    result = assemble_incident_impact_topology([HOST_A, SWITCH], instances, [_edge(HOST_A, SWITCH, "connect")])
    assert {item["inst_uuid"] for item in result["nodes"]} == {HOST_A, SWITCH}
    assert len(result["links"]) == 1


def test_belong_and_contains_do_not_enter_the_graph():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        HOST_B: _node(HOST_B, "web-02", "host", "host"),
        APP: _node(APP, "系统", "system", "system"),
    }
    edges = [
        _edge(HOST_A, APP, "belong", "host_belong_system"),
        _edge(HOST_B, APP, "belong", "host_belong_system"),
        _edge(APP, HOST_A, "contains", "system_contains_host"),
        _edge(APP, HOST_B, "contains", "system_contains_host"),
    ]
    result = assemble_incident_impact_topology([HOST_A, HOST_B], instances, edges)
    assert APP not in _roles(result)
    assert result["links"] == []


def test_non_seed_infrastructure_is_not_a_bridge():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        HOST_B: _node(HOST_B, "web-02", "host", "host"),
        SWITCH: _node(SWITCH, "sw-1", "switch", "infrastructure"),
    }
    edges = [
        _edge(HOST_A, SWITCH, "connect"),
        _edge(HOST_B, SWITCH, "connect"),
    ]
    result = assemble_incident_impact_topology([HOST_A, HOST_B], instances, edges)
    assert SWITCH not in _roles(result)
    assert result["links"] == []


def test_invisible_parent_is_not_pulled_and_its_name_is_absent():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        HOST_B: _node(HOST_B, "web-02", "host", "host"),
        APP: _node(APP, "SECRET-PARENT-NAME", "application", "service", visible=False),
    }
    edges = [
        _edge(APP, HOST_A, "run", "application_run_host"),
        _edge(APP, HOST_B, "run", "application_run_host"),
    ]
    result = assemble_incident_impact_topology([HOST_A, HOST_B], instances, edges)
    assert APP not in _roles(result)
    assert result["links"] == []
    assert "SECRET-PARENT-NAME" not in str(result)


def test_missing_seed_stays_found_false_without_edges():
    instances = {APP: _node(APP, "支付中台", "application", "service")}
    result = assemble_incident_impact_topology([MISSING], instances, [_edge(APP, MISSING, "run")])
    node = result["nodes"][0]
    assert node["found"] is False
    assert node["inst_name"] == ""
    assert node["role"] == "seed"
    assert result["links"] == []


def test_non_seed_child_is_not_pulled():
    instances = {
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
        NGINX: _node(NGINX, "nginx", "nginx", "appService"),
    }
    result = assemble_incident_impact_topology([HOST_A], instances, [_edge(NGINX, HOST_A, "run", "nginx_run_host")])
    assert [item["inst_uuid"] for item in result["nodes"]] == [HOST_A]
    assert result["links"] == []


def test_duplicate_edges_collapse():
    instances = {
        APP: _node(APP, "支付中台", "application", "service"),
        HOST_A: _node(HOST_A, "web-01", "host", "host"),
    }
    edge = _edge(APP, HOST_A, "run", "application_run_host")
    result = assemble_incident_impact_topology([APP, HOST_A], instances, [edge, dict(edge)])
    assert len(result["links"]) == 1


def test_over_limit_returns_seed_ids_without_opening_the_graph(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.incident_impact_topology.GraphClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("graph opened")),
    )
    seeds = [f"00000000-0000-4000-8000-{index:012d}" for index in range(SEED_LIMIT + 1)]
    result = query_incident_impact_topology(seeds, user_info={})
    assert result["truncated"] is True
    assert result["links"] == []
    assert len(result["nodes"]) == SEED_LIMIT + 1
    assert all(item["found"] is False and item["inst_name"] == "" for item in result["nodes"])


def test_duplicate_seeds_do_not_count_twice_toward_the_limit(monkeypatch):
    opened = {"value": False}

    class _Graph:
        def __enter__(self):
            opened["value"] = True
            return self

        def __exit__(self, *args):
            return False

        def query_entity(self, label, params):
            return [], 0

        def query_edge(self, label, params, return_entity=False):
            return []

    monkeypatch.setattr("apps.cmdb.services.incident_impact_topology.GraphClient", lambda *args, **kwargs: _Graph())
    result = query_incident_impact_topology([HOST_A] * (SEED_LIMIT + 5), user_info={}, can_view=lambda entity: True)
    assert opened["value"] is True
    assert result["truncated"] is False
    assert [item["inst_uuid"] for item in result["nodes"]] == [HOST_A]


class _Graph:
    def __init__(self, entities, edges, models=None, fail_models=False):
        self.entities = entities
        self.edges = edges
        self.models = models or []
        self.fail_models = fail_models
        self.queried = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, label, params):
        wanted = set(params[0]["value"])
        if label == MODEL:
            if self.fail_models:
                raise RuntimeError("SECRET-MODEL-CATALOG")
            return [item for item in self.models if item["model_id"] in wanted], 0
        if label == INSTANCE:
            self.queried.extend(params[0]["value"])
            return [item for item in self.entities if item["inst_uuid"] in wanted], 0
        return [], 0

    def query_edge(self, label, params, return_entity=False):
        asst_id = next(item["value"] for item in params if item["field"] == "asst_id")
        field = next(item for item in params if item["field"] in {"src_inst_uuid", "dst_inst_uuid"})
        wanted = set(field["value"])
        rows = []
        for edge in self.edges:
            if edge.get("asst_id") != asst_id or edge.get(field["field"]) not in wanted:
                continue
            rows.append(
                {
                    "edge": edge,
                    "src": {"inst_uuid": edge["src_inst_uuid"], "model_id": edge.get("src_model_id")},
                    "dst": {"inst_uuid": edge["dst_inst_uuid"], "model_id": edge.get("dst_model_id")},
                }
            )
        return rows


def test_query_builds_a_bridge_from_run_edges_and_default_layers():
    entities = [
        {"inst_uuid": HOST_A, "inst_name": "web-01", "model_id": "host"},
        {"inst_uuid": HOST_B, "inst_name": "web-02", "model_id": "host"},
        {"inst_uuid": APP, "inst_name": "支付中台", "model_id": "application"},
    ]
    edges = [
        {**_edge(APP, HOST_A, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
        {**_edge(APP, HOST_B, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
        {**_edge(APP, HOST_A, "belong", "application_belong_host"), "src_model_id": "application", "dst_model_id": "host"},
    ]
    graph = _Graph(entities, edges)
    result = query_incident_impact_topology(
        [HOST_A, HOST_B],
        user_info={"locale": "zh-Hans"},
        graph_factory=lambda: graph,
        can_view=lambda entity: True,
    )
    assert _roles(result)[APP] == "bridge"
    assert {item["asst_id"] for item in result["links"]} == {"run"}
    assert {item["asst_name"] for item in result["links"]} == {"运行于"}
    assert _by_uuid(result["nodes"])[APP]["layer"] == "service"
    assert _by_uuid(result["nodes"])[HOST_A]["layer"] == "host"


def test_query_hides_an_invisible_parent_name():
    entities = [
        {"inst_uuid": HOST_A, "inst_name": "web-01", "model_id": "host"},
        {"inst_uuid": HOST_B, "inst_name": "web-02", "model_id": "host"},
        {"inst_uuid": APP, "inst_name": "SECRET-PARENT-NAME", "model_id": "application"},
    ]
    edges = [
        {**_edge(APP, HOST_A, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
        {**_edge(APP, HOST_B, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
    ]
    result = query_incident_impact_topology(
        [HOST_A, HOST_B],
        user_info={},
        graph_factory=lambda: _Graph(entities, edges),
        can_view=lambda entity: entity.get("inst_uuid") != APP,
    )
    assert APP not in _roles(result)
    assert "SECRET-PARENT-NAME" not in str(result)
    assert all(item["found"] for item in result["nodes"])


def test_query_keeps_invalid_uuid_without_asking_the_graph():
    graph = _Graph([{"inst_uuid": HOST_A, "inst_name": "web-01", "model_id": "host"}], [])
    result = query_incident_impact_topology(
        ["not-a-uuid", HOST_A.upper()],
        user_info={},
        graph_factory=lambda: graph,
        can_view=lambda entity: True,
    )
    assert graph.queried == [HOST_A]
    assert _by_uuid(result["nodes"])["not-a-uuid"]["found"] is False
    assert _by_uuid(result["nodes"])[HOST_A]["found"] is True


def test_model_catalog_failure_does_not_return_a_guessed_graph():
    entities = [
        {"inst_uuid": HOST_A, "inst_name": "web-01", "model_id": "host"},
        {"inst_uuid": HOST_B, "inst_name": "web-02", "model_id": "host"},
        {"inst_uuid": APP, "inst_name": "支付中台", "model_id": "application"},
    ]
    edges = [
        {**_edge(APP, HOST_A, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
        {**_edge(APP, HOST_B, "run", "application_run_host"), "src_model_id": "application", "dst_model_id": "host"},
    ]
    try:
        query_incident_impact_topology(
            [HOST_A, HOST_B],
            user_info={},
            graph_factory=lambda: _Graph(entities, edges, fail_models=True),
            can_view=lambda entity: True,
        )
    except RuntimeError as exc:
        assert str(exc) == "SECRET-MODEL-CATALOG"
    else:
        raise AssertionError("model catalog failure returned a graph")


def test_handler_failure_owns_one_safe_traceback(monkeypatch, caplog):
    sentinel = "SECRET-GRAPH-PAYLOAD"
    original = RuntimeError(sentinel)

    def boom(*args, **kwargs):
        raise original

    monkeypatch.setattr("apps.cmdb.services.incident_impact_topology.query_incident_impact_topology", boom)
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = incident_impact_topology(inst_uuids=[HOST_A], user_info={"user": "alice"})
    assert result == {"result": False, "message": "", "data": {"nodes": [], "links": [], "truncated": False}}
    records = [record for record in caplog.records if record.levelno >= logging.ERROR and "incident_impact_topology_failed" in record.msg]
    assert len(records) == 1
    record = records[0]
    assert record.args == ("RuntimeError", 1)
    assert record.getMessage() == "event=incident_impact_topology_failed failed_stage=query error_type=RuntimeError seed_count=1"
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is original.__traceback__
    assert record.exc_info[1] is not original
    assert sentinel not in record.getMessage()
    assert sentinel not in caplog.text
    assert HOST_A not in caplog.text
    assert original.args == (sentinel,)


def test_handler_rejects_a_non_list_without_querying(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.incident_impact_topology.query_incident_impact_topology",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("queried")),
    )
    result = incident_impact_topology(inst_uuids="not-a-list")
    assert result["result"] is False
    assert result["data"]["links"] == []


def test_service_module_does_not_import_alerts():
    source = (Path(__file__).resolve().parents[1] / "services" / "incident_impact_topology.py").read_text(encoding="utf-8")
    assert "apps.alerts" not in source
    assert "network_topology_among_uuids" not in source
    assert "topo_search_lite" not in source
