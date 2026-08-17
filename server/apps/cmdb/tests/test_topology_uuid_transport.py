from apps.cmdb.services.instance import InstanceManage


def test_topology_transport_recursively_replaces_graph_ids(monkeypatch):
    root_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    child_uuid = "8fe27a46-1fc0-41df-8db4-8d817e164291"
    monkeypatch.setattr(
        InstanceManage,
        "_query_instance_map_by_ids",
        lambda ids: {
            1: {"_id": 1, "inst_uuid": root_uuid},
            2: {"_id": 2, "inst_uuid": child_uuid},
        },
    )

    result = InstanceManage._transport_topology_result(
        {
            "src_result": {
                "_id": 1,
                "inst_name": "root",
                "children": [{"_id": 2, "inst_name": "child", "children": []}],
            },
            "dst_result": {"_id": 1, "inst_name": "root", "children": []},
        }
    )

    assert result["src_result"]["inst_uuid"] == root_uuid
    assert result["src_result"]["children"][0]["inst_uuid"] == child_uuid
    assert "_id" not in str(result)


def test_topology_transport_drops_nodes_without_uuid(monkeypatch):
    monkeypatch.setattr(InstanceManage, "_query_instance_map_by_ids", lambda ids: {})

    result = InstanceManage._transport_topology_result({"src_result": {"_id": 1, "inst_name": "legacy", "children": []}, "dst_result": {}})

    assert result["src_result"] == {}
