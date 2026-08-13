from apps.cmdb.management.commands.migrate_oa_cmdb_instance_uuid_refs import Command


def test_rewrite_renames_bk_inst_id_and_inst_id_aliases():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    stats = {"operation_analysis_orphan_removed": 0}
    payload = {
        "nodes": [
            {"id": "n1", "bk_obj_id": "bk_switch", "bk_inst_id": 10001},
            {"id": "n2", "data": {"instId": 10002}},
        ],
        "links": [
            {
                "id": "l1",
                "source_node_id": "n1",
                "target_node_id": "n2",
                "port_pairs": [
                    {
                        "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001},
                        "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002},
                    }
                ],
            }
        ],
    }

    rewritten, changed, orphan = Command()._rewrite_operation_analysis_value(
        payload,
        {
            10001: inst_uuid,
            10002: "c28e467a-501d-426f-a3c3-6e560c7b33cb",
            90001: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            90002: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        },
        stats,
    )

    assert changed is True
    assert orphan is False
    assert rewritten["nodes"][0]["bk_inst_uuid"] == inst_uuid
    assert "bk_inst_id" not in rewritten["nodes"][0]
    assert rewritten["nodes"][1]["data"]["instUuid"] == "c28e467a-501d-426f-a3c3-6e560c7b33cb"
    assert "instId" not in rewritten["nodes"][1]["data"]
    assert rewritten["links"][0]["port_pairs"][0]["source_interface"]["bk_inst_uuid"]


def test_rewrite_drops_orphan_identity_nodes():
    stats = {"operation_analysis_orphan_removed": 0}
    payload = {
        "nodes": [{"id": "n1", "bk_inst_id": 999}],
        "links": [{"id": "l1", "source_node_id": "n1", "target_node_id": "missing"}],
    }

    rewritten, changed, orphan = Command()._rewrite_operation_analysis_value(payload, {}, stats)

    assert changed is True
    assert orphan is False
    assert rewritten["nodes"] == []
    assert rewritten["links"] == []
    assert stats["operation_analysis_orphan_removed"] >= 1
