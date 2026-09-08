from apps.cmdb.services.instance import InstanceManage


def test_topology_transport_recursively_replaces_graph_ids(monkeypatch):
    root_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    child_uuid = "8fe27a46-1fc0-41df-8db4-8d817e164291"
    monkeypatch.setattr(
        InstanceManage,
        "_query_instance_map_by_ids",
        lambda ids: {
            1: {"_id": 1, "inst_uuid": root_uuid, "model_id": "switch"},
            2: {"_id": 2, "inst_uuid": child_uuid, "model_id": "interface"},
        },
    )
    monkeypatch.setattr(InstanceManage, "_query_stored_model_names", staticmethod(lambda model_ids: {}))

    result = InstanceManage._transport_topology_result(
        {
            "src_result": {
                "_id": 1,
                "inst_name": "root",
                "model_id": "switch",
                "children": [{"_id": 2, "inst_name": "child", "model_id": "interface", "asst_id": "belong", "children": []}],
            },
            "dst_result": {"_id": 1, "inst_name": "root", "model_id": "switch", "children": []},
        },
        language="zh-Hans",
    )

    assert result["src_result"]["inst_uuid"] == root_uuid
    assert result["src_result"]["model_name"] == "交换机"
    assert result["src_result"]["children"][0]["inst_uuid"] == child_uuid
    assert result["src_result"]["children"][0]["asst_id"] == "belong"
    assert result["src_result"]["children"][0]["asst_name"] == "属于"
    assert result["src_result"]["children"][0]["model_name"] == "网络设备接口"
    assert "_id" not in result["src_result"]
    assert "_id" not in result["src_result"]["children"][0]
    assert "_id" not in result["dst_result"]


def test_topology_transport_uses_english_model_names(monkeypatch):
    root_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    monkeypatch.setattr(
        InstanceManage,
        "_query_instance_map_by_ids",
        lambda ids: {1: {"_id": 1, "inst_uuid": root_uuid, "model_id": "switch"}},
    )
    monkeypatch.setattr(InstanceManage, "_query_stored_model_names", staticmethod(lambda model_ids: {}))

    result = InstanceManage._transport_topology_result(
        {"src_result": {"_id": 1, "inst_name": "root", "model_id": "switch", "children": []}, "dst_result": {}},
        language="en",
    )

    assert result["src_result"]["model_name"] == "Switch"


def test_topology_transport_drops_nodes_without_uuid(monkeypatch):
    monkeypatch.setattr(InstanceManage, "_query_instance_map_by_ids", lambda ids: {})

    result = InstanceManage._transport_topology_result({"src_result": {"_id": 1, "inst_name": "legacy", "children": []}, "dst_result": {}})

    assert result["src_result"] == {}
