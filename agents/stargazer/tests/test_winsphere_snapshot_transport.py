from service.collection_service import CollectionService


def test_winsphere_snapshot_metadata_is_removed_from_metric_streams():
    service = CollectionService(
        {
            "plugin_name": "winsphere_info",
            "model_id": "winsphere",
            "host": "10.0.0.10",
        }
    )

    processed = service._process_result(
        {
            "success": True,
            "snapshot_id": "snapshot-1",
            "snapshot_status": "complete",
            "snapshot_manifest": {
                "schema_version": 1,
                "snapshot_id": "snapshot-1",
                "expected_models": ["winsphere", "winsphere_storage_pool", "winsphere_vm"],
                "models": {},
            },
            "result": {
                "winsphere": [{"resource_id": "endpoint"}],
                "winsphere_storage_pool": [
                    {
                        "resource_id": "storage-1",
                        "host_ids": ["host-1", "host-2"],
                    }
                ],
                "winsphere_vm": [],
            },
        }
    )

    metadata = service._extract_round_metadata(
        {
            "success": True,
            "snapshot_id": "snapshot-1",
            "snapshot_status": "complete",
            "snapshot_manifest": {
                "schema_version": 1,
                "snapshot_id": "snapshot-1",
                "expected_models": ["winsphere", "winsphere_storage_pool", "winsphere_vm"],
                "models": {},
            },
        }
    )

    for rows in processed.values():
        for row in rows:
            assert "snapshot_id" not in row
            assert "snapshot_status" not in row
            assert "snapshot_manifest" not in row
    assert "snapshot_manifest" not in processed["winsphere_storage_pool"][0]
    assert processed["winsphere_vm"] == [
        {
            "bk_obj_id": "winsphere_vm",
            "collect_status": "success",
        }
    ]
    assert metadata["details"]["snapshot_manifest"]["snapshot_id"] == "snapshot-1"
    assert processed["winsphere_storage_pool"][0]["host_ids"] == ('["host-1","host-2"]')


def test_winsphere_collection_exception_emits_queryable_failed_model_metric():
    service = CollectionService(
        {
            "plugin_name": "winsphere_info",
            "model_id": "winsphere",
            "host": "10.0.0.10",
        }
    )

    metrics = service._generate_error_response("HTTP 503")

    assert "winsphere_info{" in metrics
    assert 'collect_status="failed"' in metrics
    assert 'collect_error="HTTP 503"' in metrics
