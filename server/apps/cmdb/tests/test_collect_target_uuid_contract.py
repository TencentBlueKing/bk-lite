from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_target_service import CollectTargetService

HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
SECOND_HOST_UUID = "4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc"


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


def test_collect_target_logs_one_info_summary_and_keeps_details_at_debug(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr("apps.cmdb.services.collect_target_service.logger", logger)

    targets = CollectTargetService.build_targets(
        _task(
            [
                {"inst_uuid": HOST_UUID, "model_id": "host", "ip_addr": "10.0.0.8"},
                {"inst_uuid": SECOND_HOST_UUID, "model_id": "host", "ip_addr": "10.0.0.9"},
            ]
        )
    )

    assert [target.host for target in targets] == ["10.0.0.8", "10.0.0.9"]
    assert logger.info.call_count == 1
    info_args = logger.info.call_args.args
    assert "目标构建完成" in info_args[0]
    assert info_args[1:] == (42, 2, 1)
    assert logger.debug.call_count == 2
    assert all("build object key" in call.args[0] for call in logger.debug.call_args_list)
