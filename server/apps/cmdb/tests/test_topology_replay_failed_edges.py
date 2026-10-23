"""写边失败不得把本轮拓扑登记为已同步。"""

from unittest import mock

import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services import topology_replay_service as replay
from apps.cmdb.services.topology_replay_service import LAST_SYNCED_TOPOLOGY_ROUND_KEY, PENDING_TOPOLOGY_REPLAY_KEY

pytestmark = pytest.mark.unit

_CONNECT_EDGE = {
    "source_inst_name": "10.0.0.1-switch-Gi0/1",
    "target_inst_name": "10.0.0.2-switch-Gi0/1",
    "model_id": "interface",
    "asst_id": "connect",
    "model_asst_id": "interface_connect_interface",
}


def _remember_relationships(self):
    """父类 format_metrics 只负责留下待写边，避免本测试进入 VM / 图库。"""
    self._topology_relationships = [dict(_CONNECT_EDGE)]


class WritebackQuery:
    """update / values_list 回写到同一任务对象，游标和 pending 才能被断言看见。"""

    def __init__(self, task):
        self.task = task

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.task

    def only(self, *args, **kwargs):
        return self

    def values_list(self, *fields, **kwargs):
        task = self.task

        class _Values:
            def first(_self):
                if fields == ("collect_digest",):
                    return task.collect_digest
                if len(fields) == 1:
                    return getattr(task, fields[0])
                return tuple(getattr(task, field) for field in fields)

        return _Values()

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self.task, key, value)
        return 1


class DrivingCannula:
    """驱动真实 TopologyReplayCollector.format_metrics，再把采集器留给重放读取。"""

    def __init__(self, inst_name, inst_id, task_id, collect_plugin, **kwargs):
        collector = collect_plugin.__new__(collect_plugin)
        collector.task_id = task_id
        collect_plugin.format_metrics(collector)
        self.collect_plugin_instance = collector

    def collect_controller(self):
        return {}


class SilentCannula:
    """不记录写边结果，对应旧测试里的假 MetricsCannula。"""

    def __init__(self, *args, **kwargs):
        return None

    def collect_controller(self):
        return None


class ExplodingCannula:
    def __init__(self, *args, **kwargs):
        raise AssertionError("过期或关闭拓扑时不应进入采集")


def _task(*, task_id=11, has_network_topo=True, version=1, pending=None, digest=None):
    params = {
        "has_network_topo": has_network_topo,
        "topology_channel_config_version": version,
    }
    if pending is not None:
        params[PENDING_TOPOLOGY_REPLAY_KEY] = pending
    task = mock.Mock()
    task.id = task_id
    task.model_id = "network"
    task.task_type = CollectPluginTypes.SNMP
    task.params = params
    task.collect_digest = {} if digest is None else digest
    task.format_data = {"__raw_data__": [{"__name__": "network_interfaces_info_gauge"}]}
    task.team = [1]
    task.data_cleanup_strategy = "no_cleanup"
    task.exec_status = "success"
    task.cycle_value_type = None
    task.cycle_value = None
    return task


def _marker(round_ts=500, version="1"):
    return {
        "round_ts": round_ts,
        "round_completed_at": round_ts + 60,
        "channel_config_version": version,
    }


def _bind(monkeypatch, task, cannula):
    monkeypatch.setattr(replay.CollectModels._default_manager, "filter", lambda *a, **k: WritebackQuery(task))
    monkeypatch.setattr(replay, "MetricsCannula", cannula)


def _script_edges(monkeypatch, task, results):
    calls = []
    queued = list(results)

    def apply(relationships, *, task_id=None):
        calls.append({"relationships": list(relationships or []), "task_id": task_id})
        if not queued:
            raise AssertionError("apply_topology_relationships_safe 被多调用了一次")
        return queued.pop(0)

    monkeypatch.setattr(replay, "apply_topology_relationships_safe", apply)
    monkeypatch.setattr(CollectNetworkMetrics, "format_metrics", _remember_relationships)
    _bind(monkeypatch, task, DrivingCannula)
    return calls


def _assert_cursor_absent(task):
    digest = task.collect_digest or {}
    assert LAST_SYNCED_TOPOLOGY_ROUND_KEY not in digest


def _assert_pending(task, round_ts):
    pending = (task.params or {}).get(PENDING_TOPOLOGY_REPLAY_KEY)
    assert pending["round_ts"] == round_ts
    assert pending["channel_config_version"] == "1"


def test_failed_edges_keep_round_pending_and_gate_does_not_skip(monkeypatch):
    task = _task(pending={"round_ts": 500, "channel_config_version": "1"})
    calls = _script_edges(
        monkeypatch,
        task,
        [{"success": 0, "failed": 2}, {"success": 0, "failed": 2}],
    )
    marker = _marker()

    status = replay.replay_topology_for_task(task.id, marker=marker)

    assert status == "error"
    _assert_cursor_absent(task)
    _assert_pending(task, 500)
    assert task.exec_status == "success"
    assert calls[0]["relationships"][0]["asst_id"] == "connect"
    gate = replay.maybe_replay_topology_from_gate(task.id, task.params, task.collect_digest, marker=marker)
    assert gate != "skipped"
    assert gate == "error"
    _assert_cursor_absent(task)


def test_partial_edge_success_does_not_advance_cursor(monkeypatch):
    task = _task()
    _script_edges(monkeypatch, task, [{"success": 1, "failed": 1}])

    status = replay.replay_topology_for_task(task.id, marker=_marker())

    assert status == "error"
    _assert_cursor_absent(task)
    _assert_pending(task, 500)


def test_failed_edges_then_clean_replay_writes_cursor(monkeypatch):
    task = _task(pending={"round_ts": 500, "channel_config_version": "1"})
    _script_edges(
        monkeypatch,
        task,
        [{"success": 0, "failed": 1}, {"success": 2, "failed": 0}],
    )
    marker = _marker()

    assert replay.replay_topology_for_task(task.id, marker=marker) == "error"
    _assert_cursor_absent(task)
    _assert_pending(task, 500)

    assert replay.replay_topology_for_task(task.id, marker=marker) == "played"
    assert task.collect_digest[LAST_SYNCED_TOPOLOGY_ROUND_KEY] == 500
    assert PENDING_TOPOLOGY_REPLAY_KEY not in (task.params or {})


def test_clean_replay_plays_then_same_round_gate_skips(monkeypatch):
    task = _task()
    calls = _script_edges(monkeypatch, task, [{"success": 3, "failed": 0}])
    marker = _marker()

    assert replay.replay_topology_for_task(task.id, marker=marker) == "played"
    assert task.collect_digest[LAST_SYNCED_TOPOLOGY_ROUND_KEY] == 500
    assert PENDING_TOPOLOGY_REPLAY_KEY not in (task.params or {})
    assert task.exec_status == "success"

    gate = replay.maybe_replay_topology_from_gate(task.id, task.params, task.collect_digest, marker=marker)
    assert gate == "skipped"
    assert len(calls) == 1


def test_cannula_without_edge_result_still_plays(monkeypatch):
    task = _task()
    _bind(monkeypatch, task, SilentCannula)
    marker = _marker()

    assert replay.replay_topology_for_task(task.id, marker=marker) == "played"
    assert task.collect_digest[LAST_SYNCED_TOPOLOGY_ROUND_KEY] == 500

    gate = replay.maybe_replay_topology_from_gate(task.id, task.params, task.collect_digest, marker=marker)
    assert gate == "skipped"


def test_version_mismatch_stays_stale(monkeypatch):
    task = _task(version=5)
    _bind(monkeypatch, task, ExplodingCannula)

    status = replay.replay_topology_for_task(task.id, marker=_marker(version="4"))

    assert status == "stale"
    _assert_cursor_absent(task)


def test_topology_disabled_stays_stale(monkeypatch):
    task = _task(has_network_topo=False, pending={"round_ts": 500, "channel_config_version": "1"})
    _bind(monkeypatch, task, ExplodingCannula)

    status = replay.replay_topology_for_task(task.id, marker=_marker())

    assert status == "stale"
    _assert_cursor_absent(task)
