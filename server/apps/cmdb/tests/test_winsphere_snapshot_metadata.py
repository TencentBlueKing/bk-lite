from copy import deepcopy

import pytest

from apps.cmdb.collection.round_metadata import RoundMetadataProtocolError
from apps.cmdb_enterprise.collect.winsphere import WinsphereSnapshotValidator

MODEL_ORDER = (
    "winsphere",
    "winsphere_host_pool",
    "winsphere_cluster",
    "winsphere_host",
    "winsphere_vm",
    "winsphere_storage_pool",
    "winsphere_vswitch",
    "winsphere_port_group",
)
EMPTY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
PLATFORM_HASH = "69d0799e32fc0cf86026618fcdbb59961871be3cda9eb8c9a9c1c151e77b550e"


def rows(target="10.0.0.10", ts=1780000000.123):
    result = {model_id: [{"collection_target": target, "_metric_time": ts}] for model_id in MODEL_ORDER}
    result["winsphere"][0]["resource_id"] = "platform-1"
    return result


def metadata(target="10.0.0.10", timestamp_ms=1780000000123, *, vswitch_authoritative=True):
    models = {
        model_id: {
            "count": 0,
            "identity_hash": EMPTY_HASH,
            "authoritative": True,
        }
        for model_id in MODEL_ORDER
    }
    models["winsphere"].update(count=1, identity_hash=PLATFORM_HASH)
    models["winsphere_vswitch"]["authoritative"] = vswitch_authoritative
    return {
        (target, timestamp_ms): {
            "snapshot_id": "snapshot-1",
            "snapshot_status": "complete",
            "details": {
                "snapshot_manifest": {
                    "schema_version": 1,
                    "snapshot_id": "snapshot-1",
                    "expected_models": list(MODEL_ORDER),
                    "models": models,
                }
            },
        }
    }


def test_winsphere_validator_returns_per_model_authority():
    authority = WinsphereSnapshotValidator(MODEL_ORDER).validate(rows(), metadata())

    assert authority == {model_id: True for model_id in MODEL_ORDER}


def test_winsphere_validator_aggregates_non_authoritative_model_across_targets():
    all_rows = rows()
    second = rows(target="10.0.0.11", ts=1780000001.456)
    for model_id in MODEL_ORDER:
        all_rows[model_id].extend(second[model_id])
    all_metadata = {
        **metadata(),
        **metadata(target="10.0.0.11", timestamp_ms=1780000001456, vswitch_authoritative=False),
    }

    authority = WinsphereSnapshotValidator(MODEL_ORDER).validate(all_rows, all_metadata)

    assert authority["winsphere"] is True
    assert authority["winsphere_vswitch"] is False


@pytest.mark.parametrize("mutation", ["missing_model", "wrong_count", "wrong_hash", "duplicate_identity"])
def test_winsphere_validator_fails_closed_on_manifest_or_identity_error(mutation):
    actual_rows = rows()
    actual_metadata = metadata()
    manifest = next(iter(actual_metadata.values()))["details"]["snapshot_manifest"]
    if mutation == "missing_model":
        manifest["models"].pop("winsphere_vm")
    elif mutation == "wrong_count":
        manifest["models"]["winsphere"]["count"] = 2
    elif mutation == "wrong_hash":
        manifest["models"]["winsphere"]["identity_hash"] = "0" * 64
    else:
        actual_rows["winsphere"].append(deepcopy(actual_rows["winsphere"][0]))

    with pytest.raises(RoundMetadataProtocolError):
        WinsphereSnapshotValidator(MODEL_ORDER).validate(actual_rows, actual_metadata)
