"""列表和导出接入高级筛选，以及真实图上的写入后查询。"""

import os
import socket
import uuid

import pytest

from apps.cmdb.graph.advanced_filter import compile_advanced_filter, resolve_advanced_filter
from apps.cmdb.graph.format_type import ParameterCollector
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage


def test_instance_list_without_advanced_filter_keeps_the_original_query(fake_graph):
    fake = fake_graph(
        "apps.cmdb.services.instance",
        query_entity=([{"_id": 1, "inst_name": "mysql-a", "model_id": "mysql"}], 1),
    )
    rows, count = InstanceManage.instance_list("mysql", [], 1, 10, "", {})
    assert count == 1
    assert rows[0]["inst_name"] == "mysql-a"
    assert [call[0] for call in fake.calls] == ["query_entity"]


def test_instance_list_with_advanced_filter_returns_current_model_instances(monkeypatch):
    monkeypatch.setattr(
        ModelManage,
        "model_association_search",
        lambda model_id, **kwargs: [{"model_asst_id": "mysql_run_host", "src_model_id": "mysql", "dst_model_id": "host"}],
    )
    monkeypatch.setattr(ModelManage, "search_model_info", lambda model_id: {"model_id": model_id})
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr_v2",
        lambda model_id, **kwargs: [{"attr_id": "os_type" if model_id == "host" else "version", "attr_type": "str"}],
    )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query_compiled_entities(self, match, params, **kwargs):
            assert "h0.os_type = $str" in match or "h0.os_type = $" in match
            assert params["str1"] == "linux" or "linux" in params.values()
            return [{"inst_name": "mysql-a", "model_id": "mysql"}], 1

    monkeypatch.setattr("apps.cmdb.services.advanced_instance_query.GraphClient", lambda: FakeClient())
    rows, count = InstanceManage.instance_list(
        "mysql",
        [],
        1,
        10,
        "",
        {},
        advanced_filter={
            "logic": "AND",
            "conditions": [{"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"}],
        },
    )
    assert count == 1
    assert rows == [{"inst_name": "mysql-a", "model_id": "mysql"}]


def test_selected_export_ignores_advanced_filter(monkeypatch, fake_graph):
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr_v2",
        lambda *args, **kwargs: [{"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"}],
    )

    def forbidden(**kwargs):
        raise AssertionError("勾选导出不应执行高级筛选")

    monkeypatch.setattr("apps.cmdb.services.advanced_instance_query.run_advanced_instance_query", forbidden)
    fake_graph("apps.cmdb.services.instance", query_entity=([], 0))
    stream = InstanceManage.inst_export(
        "mysql",
        [1],
        {1: {"inst_names": [], "permission_instances_map": {}}},
        attr_list=["inst_name"],
        advanced_filter={"logic": "AND", "conditions": [{"path": [], "field": "version", "type": "str=", "value": "8.0"}]},
        file_backed=True,
    )
    stream.close()


def test_unselected_export_queries_with_the_advanced_filter(monkeypatch):
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr_v2",
        lambda *args, **kwargs: [{"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"}],
    )
    calls = {"n": 0}

    def run(**kwargs):
        calls["n"] += 1
        calls["filter"] = kwargs["advanced_filter"]
        calls["extra"] = kwargs["params"]
        if calls["n"] > 1:
            return [], None
        return [{"inst_name": "mysql-b", "inst_uuid": "11111111-1111-4111-8111-111111111111", "model_id": "mysql"}], None

    monkeypatch.setattr("apps.cmdb.services.advanced_instance_query.run_advanced_instance_query", run)
    advanced = {"logic": "AND", "conditions": [{"path": [], "field": "version", "type": "str*", "value": "8.0"}]}
    stream = InstanceManage.inst_export(
        "mysql",
        [],
        {1: {"inst_names": [], "permission_instances_map": {}}},
        attr_list=["inst_name"],
        extra_query=[{"field": "version", "type": "str*", "value": "8.0"}],
        advanced_filter=advanced,
        file_backed=True,
    )
    stream.close()
    assert calls["filter"] == advanced
    assert calls["extra"][0] == {"field": "model_id", "type": "str=", "value": "mysql"}
    assert {"field": "version", "type": "str*", "value": "8.0"} in calls["extra"]


def _falkordb_reachable():
    host = os.getenv("FALKORDB_HOST", "")
    if not host:
        return False
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _falkordb_reachable(), reason="FALKORDB_HOST 不可达，跳过真实图库集成测试")
def test_written_graph_answers_relation_filters():
    from apps.cmdb.graph.falkordb import FalkorDBClient

    client = FalkorDBClient()
    client.connect()
    label = "gtest_" + uuid.uuid4().hex[:12]
    try:

        def node(name, model_id, **extra):
            return client.create_entity(label, {"inst_name": name, "model_id": model_id, **extra}, {"is_only": {}, "is_required": {}}, [], "tester")

        def link(src, dst, asst):
            client.create_edge(asst, src["_id"], label, dst["_id"], label, {"model_asst_id": asst, "asst_id": "run"}, "model_asst_id")

        prod = node("prod-cluster", "cluster", env="生产")
        test = node("test-cluster", "cluster", env="测试")
        host_b = node("host-b", "host", os_type="Linux")
        host_b2 = node("host-b2", "host", os_type="Linux")
        host_x = node("host-x", "host", os_type="Linux")
        host_y = node("host-y", "host", os_type="Windows")
        link(host_b, prod, "host_belong_cluster")
        link(host_b2, prod, "host_belong_cluster")
        link(host_x, test, "host_belong_cluster")
        link(host_y, prod, "host_belong_cluster")
        mysql_b = node("mysql-b", "mysql", version="8.0.36")
        mysql_split = node("mysql-split", "mysql", version="8.0.36")
        node("mysql-bare", "mysql", version="8.0.40")
        mysql_old = node("mysql-old", "mysql", version="5.7.40")
        link(mysql_b, host_b, "mysql_run_host")
        link(mysql_b, host_b2, "mysql_run_host")
        link(mysql_split, host_x, "mysql_run_host")
        link(mysql_split, host_y, "mysql_run_host")
        link(mysql_old, host_b, "mysql_run_host")

        associations = {
            "mysql_run_host": {"src_model_id": "mysql", "dst_model_id": "host"},
            "host_belong_cluster": {"src_model_id": "host", "dst_model_id": "cluster"},
        }
        attrs = {"mysql": {"version": "str"}, "host": {"os_type": "str"}, "cluster": {"env": "str"}}
        visible = {"mysql", "host", "cluster"}

        def names(payload):
            logic, resolved = resolve_advanced_filter("mysql", payload, associations, visible, attrs)
            collector = ParameterCollector()
            match = compile_advanced_filter(
                "mysql",
                logic,
                resolved,
                label=label,
                collector=collector,
                permission_for=lambda model_id, alias: "",
                base_params=[{"field": "model_id", "type": "str=", "value": "mysql"}],
            )
            rows, count = client.query_compiled_entities(
                match,
                collector.get_params(),
                page={"skip": 0, "limit": 20},
                order="inst_name",
                include_count=True,
            )
            return sorted(row["inst_name"] for row in rows), count

        and_payload = {
            "logic": "AND",
            "conditions": [
                {"path": [], "field": "version", "type": "str*", "value": "8.0"},
                {"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "Linux"},
                {"path": ["mysql_run_host", "host_belong_cluster"], "field": "env", "type": "str=", "value": "生产"},
            ],
        }
        assert names(and_payload) == (["mysql-b"], 1)
        or_names, or_count = names({**and_payload, "logic": "OR"})
        assert or_names == ["mysql-b", "mysql-bare", "mysql-old", "mysql-split"]
        assert or_count == 4
        same_object, same_count = names(
            {
                "logic": "AND",
                "conditions": [
                    {"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "Linux"},
                    {"path": ["mysql_run_host"], "field": "os_type", "type": "str<>", "value": "Linux"},
                ],
            }
        )
        assert same_object == []
        assert same_count == 0
        no_host, _ = names({"logic": "AND", "conditions": [{"path": ["mysql_run_host"], "field": "os_type", "type": "str<>", "value": "Linux"}]})
        assert "mysql-bare" not in no_host
    finally:
        try:
            client._graph.query(f"MATCH (n:{label}) DETACH DELETE n")
        except Exception:
            pass
