"""Network 双通道对账与拓扑重放判定测试。"""

from unittest import mock

import pytest

from apps.cmdb.collection.round_sync import SNAPSHOT_CONTRACT_LABEL, SNAPSHOT_CONTRACT_VERSION, CompletedRound
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import (
    COLLECTION_ROLE_DEVICE,
    COLLECTION_ROLE_TOPOLOGY,
    normalize_topology_contract,
    recommended_topology_interval_minutes,
)
from apps.cmdb.node_configs.network.network import NetworkNodeParams, NetworkTopoNodeParams
from apps.cmdb.services.topology_replay_service import LAST_SYNCED_TOPOLOGY_ROUND_KEY, get_last_synced_topology_round

pytestmark = pytest.mark.unit


def test_recommended_topology_interval_is_five_times_device():
    assert recommended_topology_interval_minutes(30) == 150
    assert recommended_topology_interval_minutes("10") == 50


def test_normalize_topology_contract_includes_interval_and_versions():
    contract = normalize_topology_contract(
        {
            "has_network_topo": True,
            "topology_interval_minutes": 120,
            "topology_interval_mode": "custom",
            "topology_timeout": 600,
        },
        device_cycle_minutes=30,
    )
    assert contract["topology_interval_minutes"] == 120
    assert contract["topology_interval_mode"] == "custom"
    assert contract["topology_timeout"] == 600
    assert contract["device_channel_config_version"] == 1
    assert contract["topology_channel_config_version"] == 1


def test_normalize_topology_contract_defaults_topology_timeout():
    contract = normalize_topology_contract({"has_network_topo": True})
    assert contract["topology_timeout"] == 600


def _network_instance(**overrides):
    base = {
        "id": 42,
        "model_id": "network",
        "driver_type": "snmp",
        "task_type": CollectPluginTypes.SNMP,
        "timeout": 300,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "instances": [{"ip_addr": "10.0.0.1"}],
        "ip_range": "",
        "access_point": [{"id": "node-1"}],
        "decrypt_credentials": {
            "version": "v2",
            "snmp_port": 161,
            "community": "public",
        },
        "params": {
            "has_network_topo": True,
            "topology_protocols": ["lldp", "cdp"],
            "topology_interval_minutes": 150,
            "topology_interval_mode": "recommended",
            "device_channel_config_version": 2,
            "topology_channel_config_version": 3,
        },
    }
    base.update(overrides)
    return mock.Mock(**base)


def test_device_and_topology_config_ids_differ_metric_scope_same():
    instance = _network_instance()
    device = NetworkNodeParams(instance)
    topo = NetworkTopoNodeParams(instance)

    assert device.config_id == "cmdb_42"
    assert topo.config_id == "cmdb_42_topology"
    assert device.metric_scope_id == topo.metric_scope_id == "cmdb_42"
    assert device.tags["instance_id"] == "cmdb_42"
    assert topo.tags["instance_id"] == "cmdb_42"
    assert device.collection_role == COLLECTION_ROLE_DEVICE
    assert topo.collection_role == COLLECTION_ROLE_TOPOLOGY
    assert device.channel_config_version == 2
    assert topo.channel_config_version == 3


def test_device_credentials_do_not_enable_inline_topo():
    instance = _network_instance()
    device = NetworkNodeParams(instance)
    credential = device.set_credential()
    assert credential["has_network_topo"] is False
    assert "topology_protocols" not in credential


def test_topology_credentials_carry_protocols_and_interval():
    instance = _network_instance()
    topo = NetworkTopoNodeParams(instance)
    credential = topo.set_credential()
    assert credential["has_network_topo"] is True
    assert credential["topology_protocols"] == "lldp,cdp"
    assert topo.resolved_interval == 150 * 60


def test_expected_network_node_configs_returns_two_when_enabled(monkeypatch):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    instance = _network_instance()
    monkeypatch.setattr(
        NetworkNodeParams,
        "render_template",
        lambda self, context: "device-content",
    )
    monkeypatch.setattr(
        NetworkTopoNodeParams,
        "render_template",
        lambda self, context: "topo-content",
    )
    nodes = reconcile.expected_network_node_configs(instance)
    assert [n["id"] for n in nodes] == ["cmdb_42", "cmdb_42_topology"]
    assert nodes[0]["type"] == "network"
    assert nodes[1]["type"] == "network_topo"


def test_reconcile_delete_clears_both_configs(monkeypatch):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    delete_calls = []

    class FakeNodeMgmt:
        def delete_child_configs(self, payload):
            delete_calls.append(list(payload))

        def batch_add_node_child_config(self, nodes):
            raise AssertionError("delete path must not push")

    monkeypatch.setattr(reconcile, "NodeMgmt", FakeNodeMgmt)
    result = reconcile.reconcile_network_collection_configs(_network_instance(), delete=True)
    assert result["deleted"] == ["cmdb_42", "cmdb_42_topology"]
    assert delete_calls == [["cmdb_42", "cmdb_42_topology"]]


def test_reconcile_edit_deletes_existing_configs_before_recreate(monkeypatch):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    existing_ids = {"cmdb_42", "cmdb_42_topology"}

    class FakeNodeMgmt:
        def delete_child_configs(self, config_ids):
            existing_ids.difference_update(config_id for config_id in config_ids if isinstance(config_id, str))

        def batch_add_node_child_config(self, nodes):
            pushed_ids = {node["id"] for node in nodes}
            duplicate_ids = sorted(existing_ids & pushed_ids)
            if duplicate_ids:
                raise RuntimeError(f"duplicate child config ids: {duplicate_ids}")
            existing_ids.update(pushed_ids)

    monkeypatch.setattr(reconcile, "NodeMgmt", FakeNodeMgmt)
    monkeypatch.setattr(NetworkNodeParams, "render_template", lambda self, context: "device-content")
    monkeypatch.setattr(NetworkTopoNodeParams, "render_template", lambda self, context: "topo-content")

    instance = _network_instance()
    reconcile.reconcile_network_collection_configs(instance, delete=True)
    reconcile.reconcile_network_collection_configs(instance, delete=False)

    assert existing_ids == {"cmdb_42", "cmdb_42_topology"}


def test_reconcile_delete_propagates_node_mgmt_failure_without_leaking_error(monkeypatch, caplog):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    sensitive_sentinel = "SECRET_NETWORK_DELETE_PAYLOAD"
    original_error = RuntimeError(sensitive_sentinel)

    class FailingNodeMgmt:
        def delete_child_configs(self, config_ids):
            raise original_error

    monkeypatch.setattr(reconcile, "NodeMgmt", FailingNodeMgmt)

    with pytest.raises(RuntimeError) as exc_info:
        reconcile.reconcile_network_collection_configs(_network_instance(), delete=True)

    assert exc_info.value is original_error
    warning_records = [record for record in caplog.records if record.msg.startswith("[NetworkReconcile] 删除节点配置失败")]
    assert len(warning_records) == 1
    warning_record = warning_records[0]
    assert warning_record.msg == "[NetworkReconcile] 删除节点配置失败 task_id=%s config_ids=%s error_type=%s"
    assert warning_record.args == (42, ["cmdb_42", "cmdb_42_topology"], "RuntimeError")
    assert warning_record.getMessage() == (
        "[NetworkReconcile] 删除节点配置失败 task_id=42 " "config_ids=['cmdb_42', 'cmdb_42_topology'] error_type=RuntimeError"
    )
    assert sensitive_sentinel not in warning_record.getMessage()
    assert warning_record.exc_info is None


def test_reconcile_without_topology_deletes_only_topology_config(monkeypatch):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    delete_calls = []
    pushed_ids = []

    class FakeNodeMgmt:
        def delete_child_configs(self, config_ids):
            delete_calls.append(list(config_ids))

        def batch_add_node_child_config(self, nodes):
            pushed_ids.extend(node["id"] for node in nodes)

    monkeypatch.setattr(reconcile, "NodeMgmt", FakeNodeMgmt)
    monkeypatch.setattr(NetworkNodeParams, "render_template", lambda self, context: "device-content")

    instance = _network_instance(params={"has_network_topo": False})
    result = reconcile.reconcile_network_collection_configs(instance, delete=False)

    assert delete_calls == [["cmdb_42_topology"]]
    assert result["deleted"] == ["cmdb_42_topology"]
    assert pushed_ids == ["cmdb_42"]


def test_reconcile_without_topology_propagates_cleanup_failure_without_push(monkeypatch, caplog):
    from apps.cmdb.services import network_collection_reconcile as reconcile

    sensitive_sentinel = "SECRET_TOPOLOGY_DELETE_PAYLOAD"
    original_error = RuntimeError(sensitive_sentinel)

    class FailingNodeMgmt:
        def delete_child_configs(self, config_ids):
            assert config_ids == ["cmdb_42_topology"]
            raise original_error

        def batch_add_node_child_config(self, nodes):
            raise AssertionError("cleanup failure must stop config push")

    monkeypatch.setattr(reconcile, "NodeMgmt", FailingNodeMgmt)

    instance = _network_instance(params={"has_network_topo": False})
    with pytest.raises(RuntimeError) as exc_info:
        reconcile.reconcile_network_collection_configs(instance, delete=False)

    assert exc_info.value is original_error
    warning_records = [record for record in caplog.records if record.msg.startswith("[NetworkReconcile] 清理拓扑配置失败")]
    assert len(warning_records) == 1
    warning_record = warning_records[0]
    assert warning_record.msg == "[NetworkReconcile] 清理拓扑配置失败 task_id=%s config_id=%s error_type=%s"
    assert warning_record.args == (42, "cmdb_42_topology", "RuntimeError")
    assert warning_record.getMessage() == ("[NetworkReconcile] 清理拓扑配置失败 task_id=42 config_id=cmdb_42_topology error_type=RuntimeError")
    assert sensitive_sentinel not in warning_record.getMessage()
    assert warning_record.exc_info is None


def test_get_last_synced_topology_round():
    assert get_last_synced_topology_round(None) is None
    assert get_last_synced_topology_round({LAST_SYNCED_TOPOLOGY_ROUND_KEY: "9"}) == 9


def test_query_role_round_marker_ignores_legacy_attempt_labels():
    from apps.cmdb.services.topology_replay_service import query_role_round_marker

    class FakeCollection:
        def query(self, _sql, **_kwargs):
            return {
                "data": {
                    "result": [
                        {
                            "metric": {
                                "__name__": "cmdb_round_complete_gauge",
                                "instance_id": "cmdb_42",
                                "collection_role": COLLECTION_ROLE_TOPOLOGY,
                                "channel_config_version": "1",
                                "run_attempt_id": "legacy-attempt",
                                "collection_run_attempt_id": "legacy-attempt",
                            },
                            "value": [100, "100"],
                        },
                        {
                            "metric": {
                                "__name__": "cmdb_round_complete_gauge",
                                "instance_id": "cmdb_42",
                                "collection_role": COLLECTION_ROLE_TOPOLOGY,
                                "channel_config_version": "2",
                            },
                            "value": [200, "200"],
                        },
                    ]
                }
            }

        def query_sample_timestamps(self, _sql, **_kwargs):
            return {
                "data": {
                    "result": [
                        {
                            "metric": {
                                "__name__": "cmdb_round_complete_gauge",
                                "instance_id": "cmdb_42",
                                "collection_role": COLLECTION_ROLE_TOPOLOGY,
                                "channel_config_version": "1",
                                "run_attempt_id": "legacy-attempt",
                                "collection_run_attempt_id": "legacy-attempt",
                            },
                            "value": [200, "150.25"],
                        },
                        {
                            "metric": {
                                "__name__": "cmdb_round_complete_gauge",
                                "instance_id": "cmdb_42",
                                "collection_role": COLLECTION_ROLE_TOPOLOGY,
                                "channel_config_version": "2",
                            },
                            "value": [200, "250.5"],
                        },
                    ]
                }
            }

    marker = query_role_round_marker(
        "cmdb_42",
        collection_role=COLLECTION_ROLE_TOPOLOGY,
        collection=FakeCollection(),
    )

    assert marker == {
        "round_ts": 200,
        "round_completed_at": 250.5,
        "channel_config_version": "2",
    }


def test_replay_stale_when_version_mismatch(monkeypatch):
    from apps.cmdb.services import topology_replay_service as replay

    task = mock.Mock(
        id=7,
        model_id="network",
        task_type=CollectPluginTypes.SNMP,
        params={
            "has_network_topo": True,
            "topology_channel_config_version": 5,
        },
        collect_digest={},
        format_data={"__raw_data__": [{"__name__": "network_interfaces_info_gauge"}]},
        team=[1],
        data_cleanup_strategy="no_cleanup",
    )
    monkeypatch.setattr(
        replay.CollectModels._default_manager,
        "filter",
        lambda **kwargs: mock.Mock(first=lambda: task),
    )
    status = replay.replay_topology_for_task(
        7,
        marker={"round_ts": 100, "channel_config_version": "4"},
    )
    assert status == "stale"


def test_replay_pending_when_interfaces_missing(monkeypatch):
    from apps.cmdb.services import topology_replay_service as replay

    updates = []
    task = mock.Mock(
        id=8,
        model_id="network",
        task_type=CollectPluginTypes.SNMP,
        params={"has_network_topo": True, "topology_channel_config_version": 1},
        collect_digest={},
        format_data={},
        team=[1],
        data_cleanup_strategy="no_cleanup",
    )

    class QS:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return task

        def only(self, *args):
            return self

        def update(self, **kwargs):
            updates.append(kwargs)
            return 1

        def values_list(self, *args, **kwargs):
            return self

    monkeypatch.setattr(replay.CollectModels._default_manager, "filter", lambda *a, **k: QS())
    status = replay.replay_topology_for_task(
        8,
        marker={"round_ts": 200, "channel_config_version": "1", "run_attempt_id": "b"},
    )
    assert status == "pending"
    pending_updates = [
        (u.get("params") or {})[PENDING_TOPOLOGY_REPLAY_KEY] for u in updates if PENDING_TOPOLOGY_REPLAY_KEY in (u.get("params") or {})
    ]
    assert pending_updates == [{"round_ts": 200, "channel_config_version": "1"}]


# import after defining usage
from apps.cmdb.services.topology_replay_service import PENDING_TOPOLOGY_REPLAY_KEY  # noqa: E402


def test_replay_idempotent_same_round(monkeypatch):
    from apps.cmdb.services import topology_replay_service as replay

    task = mock.Mock(
        id=9,
        model_id="network",
        task_type=CollectPluginTypes.SNMP,
        params={"has_network_topo": True, "topology_channel_config_version": 1},
        collect_digest={LAST_SYNCED_TOPOLOGY_ROUND_KEY: 300},
        format_data={"__raw_data__": [{"__name__": "network_interfaces_info_gauge"}]},
        team=[1],
        data_cleanup_strategy="no_cleanup",
    )
    monkeypatch.setattr(
        replay.CollectModels._default_manager,
        "filter",
        lambda *a, **k: mock.Mock(first=lambda: task),
    )
    status = replay.replay_topology_for_task(
        9,
        marker={"round_ts": 300, "channel_config_version": "1"},
    )
    assert status == "skipped"


def test_replay_legacy_pending_without_completion_proof_never_deletes(monkeypatch):
    from apps.cmdb.services import topology_replay_service as replay

    task = mock.Mock(
        id=10,
        model_id="network",
        task_type=CollectPluginTypes.SNMP,
        params={"has_network_topo": True, "topology_channel_config_version": 1},
        collect_digest={},
        format_data={"__raw_data__": [{"__name__": "network_interfaces_info_gauge"}]},
        team=[1],
        data_cleanup_strategy="delete",
    )

    class QS:
        def first(self):
            return task

        def values_list(self, *_args, **_kwargs):
            return mock.Mock(first=lambda: {})

        def update(self, **_kwargs):
            return 1

    monkeypatch.setattr(replay.CollectModels._default_manager, "filter", lambda *a, **k: QS())
    observed = {}

    class FakeCannula:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def collect_controller(self):
            return None

    monkeypatch.setattr(replay, "MetricsCannula", FakeCannula)

    status = replay.replay_topology_for_task(
        10,
        marker={"round_ts": 200, "channel_config_version": "1"},
    )

    assert status == "played"
    assert observed["plugin_kwargs"]["snapshot_complete"] is False


def test_replay_missing_when_task_deleted(monkeypatch):
    from apps.cmdb.services import topology_replay_service as replay

    monkeypatch.setattr(
        replay.CollectModels._default_manager,
        "filter",
        lambda *a, **k: mock.Mock(first=lambda: None),
    )
    assert replay.replay_topology_for_task(404, marker={"round_ts": 1}) == "missing"


def test_gate_triggers_topology_replay_for_network(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 31,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {"last_synced_round": 100},
            "params": {"has_network_topo": True, "topology_interval_minutes": 2400},
            "model_id": "network",
            "task_type": CollectPluginTypes.SNMP,
            "is_interval": True,
            "cycle_value_type": "cycle",
            "cycle_value": "480",
        },
    ]

    class _QS:
        _pages = 0

        def __init__(self, data):
            self._data = data

        def filter(self, *args, **kwargs):
            return self

        def exclude(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def values(self, *args, **kwargs):
            return self

        def __getitem__(self, item):
            if isinstance(item, slice):
                _QS._pages += 1
                if _QS._pages > 1:
                    return []
                return list(self._data)
            raise TypeError(item)

    _QS._pages = 0
    monkeypatch.setattr(ct.CollectModels._default_manager, "filter", lambda *a, **k: _QS(rows))
    monkeypatch.setattr(ct, "_purge_legacy_vm_sync_beats", lambda: 0)
    observed_lookbacks = []

    def fake_completed_rounds(instance_ids, **kwargs):
        observed_lookbacks.append((kwargs.get("collection_role"), kwargs["lookback_seconds"]))
        if kwargs.get("collection_role") == "topology":
            return {
                "cmdb_31": CompletedRound(
                    started_at=200,
                    completed_at=260.5,
                    labels={
                        "channel_config_version": "1",
                        SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION,
                    },
                )
            }
        return {
            "cmdb_31": CompletedRound(
                started_at=100,
                completed_at=160.5,
                labels={SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION},
            )
        }

    monkeypatch.setattr(ct, "query_latest_completed_rounds", fake_completed_rounds)

    class _Delay:
        @staticmethod
        def delay(*args, **kwargs):
            return None

    monkeypatch.setattr(ct, "sync_collect_task", _Delay)
    called = []

    def fake_replay(task_id, params, digest, *, marker):
        called.append((task_id, params.get("has_network_topo"), digest.get("last_synced_round"), marker))
        return "played"

    monkeypatch.setattr(
        "apps.cmdb.services.topology_replay_service.maybe_replay_topology_from_gate",
        fake_replay,
    )
    result = ct.sync_collect_tasks_gate()
    assert called == [
        (
            31,
            True,
            100,
            {
                "round_ts": 200,
                "round_completed_at": 260.5,
                "channel_config_version": "1",
                SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION,
            },
        )
    ]
    assert observed_lookbacks == [("device", 115_620), ("topology", 230_820)]
    assert result["topo_replayed"] == 1
    assert result["skipped"] == 1
