import importlib
import sys

import pytest
from core.collection.round_metadata import RoundMetadataMissingError, RoundMetadataValidationError
from core.infra import nats as nats_module


class FakeNatsRegistry:
    service_name = "default_stargazer"

    def register_handler(self, _subject, queue=None):
        return lambda handler: handler


_previous_nats_instance = nats_module._nats_instance
nats_module._nats_instance = FakeNatsRegistry()
sys.modules.pop("service.nats_server", None)
nats_server = importlib.import_module("service.nats_server")
nats_module._nats_instance = _previous_nats_instance


class Store:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error
        self.calls = []

    async def get_many(self, task_id, lookups):
        self.calls.append((task_id, lookups))
        if self.error:
            raise self.error
        return self.items


@pytest.mark.asyncio
async def test_round_metadata_handler_only_accepts_exact_bounded_lookups(monkeypatch):
    item = {
        "schema_version": 1,
        "kind": "inventory_snapshot",
        "collection_task_id": "321",
        "instance_id": "cmdb_321",
        "collection_target": "10.0.0.8",
        "collection_plugin_ref": "pc.config",
        "model_id": "pc",
        "publish_timestamp_ms": 1780000000123,
        "snapshot_id": "snapshot-1",
        "snapshot_status": "complete",
        "details": {"software_expected_count": 0, "software_error_count": 0},
    }
    store = Store([item])
    monkeypatch.setattr(nats_server, "_round_metadata_store", lambda: store)

    response = await nats_server.get_collection_round_metadata(
        {
            "schema_version": 1,
            "collection_task_id": "321",
            "instance_id": "cmdb_321",
            "lookups": [
                {
                    "collection_target": "10.0.0.8",
                    "publish_timestamp_ms": 1780000000123,
                }
            ],
        }
    )

    assert response == {"schema_version": 1, "items": [item]}
    assert store.calls == [
        (
            "321",
            [{"collection_target": "10.0.0.8", "publish_timestamp_ms": 1780000000123}],
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"schema_version": 2, "collection_task_id": "321", "instance_id": "cmdb_321", "lookups": [{}]},
        {"schema_version": 1, "collection_task_id": "321", "instance_id": "cmdb_other", "lookups": [{}]},
        {"schema_version": 1, "collection_task_id": "321", "instance_id": "cmdb_321", "lookups": []},
    ],
)
async def test_round_metadata_handler_rejects_invalid_identity_and_queries(payload):
    with pytest.raises(RoundMetadataValidationError, match="invalid_request"):
        await nats_server.get_collection_round_metadata(payload)


@pytest.mark.asyncio
async def test_round_metadata_handler_preserves_fixed_missing_error(monkeypatch):
    store = Store(error=RoundMetadataMissingError())
    monkeypatch.setattr(nats_server, "_round_metadata_store", lambda: store)

    with pytest.raises(RoundMetadataMissingError, match="metadata_missing"):
        await nats_server.get_collection_round_metadata(
            {
                "schema_version": 1,
                "collection_task_id": "321",
                "instance_id": "cmdb_321",
                "lookups": [{"collection_target": "10.0.0.8", "publish_timestamp_ms": 1780000000123}],
            }
        )
