from types import SimpleNamespace

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_target_service import CollectTargetService

HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def _task(instances):
    return SimpleNamespace(
        id=42,
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        is_job=False,
        instances=instances,
        ip_range="",
        params={},
        decrypt_credentials=[],
    )


def test_collect_target_uses_uuid_and_does_not_persist_graph_id_snapshot():
    targets = CollectTargetService.build_targets(
        _task(
            [
                {
                    "_id": 7,
                    "inst_uuid": HOST_UUID,
                    "model_id": "host",
                    "inst_name": "host-a",
                    "ip_addr": "10.0.0.8",
                }
            ]
        )
    )

    assert len(targets) == 1
    assert targets[0].instance_id == HOST_UUID
    assert targets[0].snapshot == {
        "inst_uuid": HOST_UUID,
        "model_id": "host",
        "inst_name": "host-a",
        "ip_addr": "10.0.0.8",
    }


def test_collect_target_skips_legacy_snapshot_without_uuid():
    targets = CollectTargetService.build_targets(_task([{"_id": 7, "model_id": "host", "ip_addr": "10.0.0.8"}]))

    assert targets == []
