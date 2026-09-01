from types import SimpleNamespace

import pytest

from apps.cmdb.collection.round_metadata import (
    RoundMetadataProtocolError,
    RoundMetadataReader,
    build_round_metadata_lookups,
    resolve_stargazer_namespace,
)


def metadata(target, timestamp_ms, *, model_id="pc"):
    return {
        "schema_version": 1,
        "kind": "inventory_snapshot",
        "collection_task_id": "321",
        "instance_id": "cmdb_321",
        "collection_target": target,
        "collection_plugin_ref": f"{model_id}.config",
        "model_id": model_id,
        "publish_timestamp_ms": timestamp_ms,
        "snapshot_id": f"snapshot-{timestamp_ms}",
        "snapshot_status": "complete",
        "details": {},
    }


def test_namespace_uses_access_point_region_and_defaults_safely():
    assert resolve_stargazer_namespace(SimpleNamespace(access_point=[{"cloud_name": "华东"}])) == "华东_stargazer"
    assert resolve_stargazer_namespace(SimpleNamespace(access_point=[])) == "default_stargazer"


def test_metric_roots_build_exact_deduplicated_millisecond_lookups():
    rows = [
        {"collection_target": "10.0.0.8", "_metric_time": 1780000000.123},
        {"collection_target": "10.0.0.8", "_metric_time": 1780000000.123},
        {"collection_target": "10.0.0.9", "_metric_time": 1780000001.456},
    ]

    assert build_round_metadata_lookups(rows) == [
        {"collection_target": "10.0.0.8", "publish_timestamp_ms": 1780000000123},
        {"collection_target": "10.0.0.9", "publish_timestamp_ms": 1780000001456},
    ]


def test_reader_batches_requests_and_validates_every_envelope():
    calls = []

    class Client:
        def __init__(self, instance_id=None):
            assert instance_id == "default_stargazer"

        def get_collection_round_metadata(self, payload, timeout=3):
            calls.append((payload, timeout))
            items = [metadata(item["collection_target"], item["publish_timestamp_ms"]) for item in payload["lookups"]]
            return {"success": True, "schema_version": 1, "items": items}

    task = SimpleNamespace(id=321, access_point=[])
    lookups = [{"collection_target": f"10.0.0.{index}", "publish_timestamp_ms": 1780000000000 + index} for index in range(1, 53)]

    result = RoundMetadataReader(task, rpc_factory=Client).get_many(lookups, model_id="pc")

    assert len(calls) == 2
    assert len(calls[0][0]["lookups"]) == 50
    assert len(calls[1][0]["lookups"]) == 2
    assert len(result) == 52


@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "error": "metadata_missing"},
        {"success": True, "schema_version": 2, "items": []},
        {"success": True, "schema_version": 1, "items": []},
        {"success": True, "schema_version": 1, "items": [metadata("wrong", 1780000000123)]},
    ],
)
def test_reader_fails_closed_on_missing_or_mismatched_metadata(response):
    class Client:
        def __init__(self, instance_id=None):
            pass

        def get_collection_round_metadata(self, payload, timeout=3):
            return response

    reader = RoundMetadataReader(SimpleNamespace(id=321, access_point=[]), rpc_factory=Client)

    with pytest.raises(RoundMetadataProtocolError):
        reader.get_many(
            [{"collection_target": "10.0.0.8", "publish_timestamp_ms": 1780000000123}],
            model_id="pc",
        )
