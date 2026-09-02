import pytest
from core.collection.round_metadata import (
    MAX_ROUND_METADATA_BYTES,
    RedisRoundMetadataStore,
    RoundMetadataConflictError,
    RoundMetadataValidationError,
    build_round_metadata_envelope,
)


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def set(self, key, value, *, ex, nx):
        assert nx is True
        if key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]


def envelope(**overrides):
    values = {
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
        "details": {
            "software_expected_count": 1,
            "software_error_count": 0,
        },
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_round_metadata_store_is_idempotent_and_uses_bounded_ttl():
    redis = MemoryRedis()
    store = RedisRoundMetadataStore(redis)

    assert await store.save(envelope()) == "created"
    assert await store.save(envelope()) == "duplicate"
    assert list(redis.expirations.values()) == [24 * 60 * 60]
    assert await store.get_many(
        "321",
        [{"collection_target": "10.0.0.8", "publish_timestamp_ms": 1780000000123}],
    ) == [envelope()]


@pytest.mark.asyncio
async def test_round_metadata_store_rejects_conflicting_retry():
    store = RedisRoundMetadataStore(MemoryRedis())
    await store.save(envelope())

    with pytest.raises(RoundMetadataConflictError, match="metadata_conflict"):
        await store.save(envelope(snapshot_id="snapshot-2"))


@pytest.mark.asyncio
async def test_round_metadata_store_rejects_oversized_payload_before_redis_write():
    redis = MemoryRedis()
    store = RedisRoundMetadataStore(redis)

    with pytest.raises(RoundMetadataValidationError, match="metadata_too_large"):
        await store.save(
            envelope(
                collection_plugin_ref="winsphere.config",
                model_id="winsphere",
                details={
                    "snapshot_manifest": {
                        "value": "x" * MAX_ROUND_METADATA_BYTES,
                    }
                },
            )
        )

    assert redis.values == {}


def test_build_round_metadata_envelope_binds_transport_identity():
    result = build_round_metadata_envelope(
        task_id="321",
        target="10.0.0.8",
        plugin_ref="pc.config",
        model_id="pc",
        publish_timestamp_ms=1780000000123,
        metadata={
            "snapshot_id": "snapshot-1",
            "snapshot_status": "complete",
            "details": {"software_expected_count": 1, "software_error_count": 0},
        },
    )

    assert result == envelope()


@pytest.mark.parametrize(
    ("model_id", "details"),
    [
        ("pc", {}),
        ("pc", {"software_expected_count": -1, "software_error_count": 0}),
        ("winsphere", {}),
        ("winsphere", {"snapshot_manifest": "not-an-object"}),
    ],
)
def test_round_metadata_requires_bounded_model_specific_details(model_id, details):
    with pytest.raises(RoundMetadataValidationError, match="invalid_request"):
        build_round_metadata_envelope(
            task_id="321",
            target="10.0.0.8",
            plugin_ref=f"{model_id}.config",
            model_id=model_id,
            publish_timestamp_ms=1780000000123,
            metadata={
                "snapshot_id": "snapshot-1",
                "snapshot_status": "complete",
                "details": details,
            },
        )
