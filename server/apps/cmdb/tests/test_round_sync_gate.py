"""轮次守门判定与 VM 查询轮次窗口测试。"""

from unittest import mock

import pytest

from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.collection.round_sync import (
    SNAPSHOT_CONTRACT_LABEL,
    SNAPSHOT_CONTRACT_VERSION,
    CompletedRound,
    cap_completed_round_lookback_seconds,
    completed_round_lookback_seconds,
    decide_gate_action,
    get_last_synced_round,
    query_instance_ids_with_vm_data,
    query_latest_completed_round,
    query_latest_completed_rounds,
    uses_vm_reconciliation,
)
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType

pytestmark = pytest.mark.unit


def test_uses_vm_reconciliation_excludes_non_round_gate_tasks():
    assert uses_vm_reconciliation(CollectPluginTypes.HOST) is True
    assert uses_vm_reconciliation(CollectPluginTypes.VM) is True
    assert uses_vm_reconciliation(CollectPluginTypes.CONFIG_FILE) is False
    assert uses_vm_reconciliation(CollectPluginTypes.K8S) is False


def test_completed_round_lookback_covers_cycle_and_24h_recovery():
    assert (
        completed_round_lookback_seconds(
            is_interval=True,
            cycle_value_type="cycle",
            cycle_value="480",
        )
        == 115_620
    )


def test_completed_round_lookback_is_capped_by_vm_retention():
    assert cap_completed_round_lookback_seconds(700_000, retention_seconds=604_800) == (604_800, True)
    assert cap_completed_round_lookback_seconds(115_620, retention_seconds=604_800) == (115_620, False)


@pytest.mark.parametrize(
    "is_interval,cycle_value_type,cycle_value",
    [
        (False, "cycle", "480"),
        (True, "timing", "08:00"),
        (True, "cycle", "invalid"),
        (True, "cycle", "0"),
    ],
)
def test_completed_round_lookback_uses_recovery_floor_for_non_minute_cycles(
    is_interval,
    cycle_value_type,
    cycle_value,
):
    assert (
        completed_round_lookback_seconds(
            is_interval=is_interval,
            cycle_value_type=cycle_value_type,
            cycle_value=cycle_value,
        )
        == 86_820
    )


def test_get_last_synced_round():
    assert get_last_synced_round(None) is None
    assert get_last_synced_round({}) is None
    assert get_last_synced_round({"last_synced_round": "1700000000"}) == 1700000000
    assert get_last_synced_round({"last_synced_round": "bad"}) is None


def test_completed_round_only_trusts_versioned_snapshot_contract():
    legacy = CompletedRound(started_at=100, completed_at=120)
    strict = CompletedRound(
        started_at=100,
        completed_at=120,
        labels={SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION},
    )

    assert legacy.snapshot_complete is False
    assert strict.snapshot_complete is True


def test_query_latest_completed_round_returns_start_and_completion_time():
    collection = mock.MagicMock()
    collection.query.return_value = {
        "data": {
            "result": [
                {
                    "metric": {
                        "__name__": "cmdb_round_complete_gauge",
                        "instance_id": "cmdb_11",
                        "collection_role": "device",
                    },
                    "value": [1_700_000_300, "1700000100"],
                }
            ]
        }
    }
    collection.query_sample_timestamps.return_value = {
        "data": {
            "result": [
                {
                    "metric": {
                        "__name__": "cmdb_round_complete_gauge",
                        "instance_id": "cmdb_11",
                        "collection_role": "device",
                    },
                    "value": [1_700_000_300, "1700000200.875"],
                }
            ]
        }
    }

    completed_round = query_latest_completed_round(
        "cmdb_11",
        collection=collection,
        collection_role="device",
        lookback_seconds=115_620,
    )

    assert completed_round == CompletedRound(
        started_at=1_700_000_100,
        completed_at=1_700_000_200.875,
    )
    marker_evaluation_time = collection.query.call_args.kwargs["evaluation_time"]
    assert marker_evaluation_time == collection.query_sample_timestamps.call_args.kwargs["evaluation_time"]


def test_query_latest_completed_rounds_batches_instances_in_one_pair_of_queries():
    collection = mock.MagicMock()
    collection.query.return_value = {
        "data": {
            "result": [
                {
                    "metric": {"__name__": "cmdb_round_complete_gauge", "instance_id": "cmdb_11"},
                    "value": [300, "100"],
                },
                {
                    "metric": {"__name__": "cmdb_round_complete_gauge", "instance_id": "cmdb_13"},
                    "value": [300, "200"],
                },
            ]
        }
    }
    collection.query_sample_timestamps.return_value = {
        "data": {
            "result": [
                {
                    "metric": {"__name__": "cmdb_round_complete_gauge", "instance_id": "cmdb_11"},
                    "value": [300, "160.25"],
                },
                {
                    "metric": {"__name__": "cmdb_round_complete_gauge", "instance_id": "cmdb_13"},
                    "value": [300, "260.5"],
                },
            ]
        }
    }

    rounds = query_latest_completed_rounds(
        ["cmdb_11", "cmdb_13"],
        collection=collection,
        collection_role="device",
        lookback_seconds=115_620,
        minimum_completed_at_by_instance={"cmdb_11": 150, "cmdb_13": 270},
    )

    assert rounds == {
        "cmdb_11": CompletedRound(started_at=100, completed_at=160.25),
    }
    assert collection.query.call_count == 1
    assert collection.query_sample_timestamps.call_count == 1
    assert "cmdb_11|cmdb_13" in collection.query.call_args.args[0]


def test_query_latest_completed_round_prefers_strict_contract_for_same_round():
    collection = mock.MagicMock()
    common = {
        "__name__": "cmdb_round_complete_gauge",
        "instance_id": "cmdb_11",
        "collection_role": "device",
    }
    strict = {**common, SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION}
    collection.query.return_value = {
        "data": {
            "result": [
                {"metric": common, "value": [300, "100"]},
                {"metric": strict, "value": [300, "100"]},
            ]
        }
    }
    collection.query_sample_timestamps.return_value = {
        "data": {
            "result": [
                {"metric": common, "value": [300, "160"]},
                {"metric": strict, "value": [300, "160"]},
            ]
        }
    }

    completed_round = query_latest_completed_round(
        "cmdb_11",
        collection=collection,
        collection_role="device",
        lookback_seconds=115_620,
    )

    assert completed_round.snapshot_complete is True


def test_query_instance_ids_with_vm_data_batches_compatibility_probe():
    collection = mock.MagicMock()
    collection.query.return_value = {
        "data": {
            "result": [
                {"metric": {"instance_id": "cmdb_11"}, "value": [300, "2"]},
                {"metric": {"instance_id": "cmdb_13"}, "value": [300, "1"]},
            ]
        }
    }

    instance_ids = query_instance_ids_with_vm_data(
        ["cmdb_11", "cmdb_12", "cmdb_13"],
        collection=collection,
    )

    assert instance_ids == {"cmdb_11", "cmdb_13"}
    assert collection.query.call_count == 1
    assert "cmdb_11|cmdb_12|cmdb_13" in collection.query.call_args.args[0]


@pytest.mark.parametrize(
    "exec_status,round_ts,last_synced,has_data,expected",
    [
        (CollectRunStatusType.RUNNING, 100, None, False, "skip_running"),
        (CollectRunStatusType.SUCCESS, None, 100, False, "skip_incomplete"),
        (CollectRunStatusType.SUCCESS, 100, 100, False, "skip_same_round"),
        (CollectRunStatusType.SUCCESS, 200, 100, False, "sync_round"),
        (CollectRunStatusType.SUCCESS, 200, None, False, "sync_round"),
        (CollectRunStatusType.SUCCESS, None, None, True, "sync_compat"),
        (CollectRunStatusType.SUCCESS, None, None, False, "skip_idle"),
    ],
)
def test_decide_gate_action(exec_status, round_ts, last_synced, has_data, expected):
    assert (
        decide_gate_action(
            exec_status=exec_status,
            round_ts=round_ts,
            last_synced_round=last_synced,
            has_vm_data=has_data,
        )
        == expected
    )


def _ok_response(result=None):
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "success",
        "data": {"result": result or []},
    }
    return resp


def test_query_uses_completed_round_window_and_raw_sample_timestamps():
    round_started_at = 1_700_000_100
    round_completed_at = 1_700_000_200.875
    value_rows = [
        {"metric": {"__name__": "a", "instance_id": "cmdb_1"}, "value": [round_completed_at, "11"]},
        {"metric": {"__name__": "b", "instance_id": "cmdb_1"}, "value": [round_completed_at, "22"]},
        {"metric": {"__name__": "c", "instance_id": "cmdb_1"}, "value": [round_completed_at, "33"]},
    ]
    timestamp_rows = [
        {"metric": {"__cmdb_metric_name__": "a", "instance_id": "cmdb_1"}, "value": [round_completed_at, "1700000050"]},
        {"metric": {"__cmdb_metric_name__": "b", "instance_id": "cmdb_1"}, "value": [round_completed_at, "1700000150"]},
        {"metric": {"__cmdb_metric_name__": "c", "instance_id": "cmdb_1"}, "value": [round_completed_at, "1700000250"]},
    ]
    with mock.patch(
        "apps.cmdb.collection.query_vm.requests.post",
        side_effect=[_ok_response(value_rows), _ok_response(timestamp_rows)],
    ) as post:
        payload = Collection().query(
            "metric_a or metric_b",
            retries=1,
            min_timestamp=round_started_at,
            max_timestamp=round_completed_at,
        )

    value_request, timestamp_request = post.call_args_list
    assert value_request.kwargs["data"] == {
        "query": "last_over_time((metric_a or metric_b)[221s:])",
        "time": round_completed_at,
    }
    assert timestamp_request.kwargs["data"] == {
        "query": ('tlast_over_time((label_move((metric_a or metric_b), "__name__", ' '"__cmdb_metric_name__"))[221s:])'),
        "time": round_completed_at,
    }
    result = payload["data"]["result"]
    assert len(result) == 1
    assert result[0]["metric"]["__name__"] == "b"
    assert result[0]["value"][1] == "22"


def test_query_default_still_uses_1h_window():
    with mock.patch(
        "apps.cmdb.collection.query_vm.requests.post",
        return_value=_ok_response(),
    ) as post:
        Collection().query("metric_a or metric_b", retries=1)

    assert post.call_args.kwargs["data"]["query"] == ("last_over_time((metric_a or metric_b)[1h:])")


def test_round_gate_marker_failure_log_owns_safe_traceback(caplog):
    from apps.cmdb.tasks import celery_tasks as ct

    sensitive_sentinel = "SECRET_VM_RESPONSE_BODY"
    original_error = RuntimeError(sensitive_sentinel)
    with caplog.at_level("ERROR", logger="cmdb"):
        try:
            raise original_error
        except RuntimeError as error:
            original_traceback = error.__traceback__
            ct._log_round_gate_marker_query_failure(
                error,
                failed_stage="device_marker_query",
                rows=2,
            )

    records = [record for record in caplog.records if record.msg.startswith("event=round_gate_marker_query_failed")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=round_gate_marker_query_failed failed_stage=%s rows=%s error_type=%s"
    assert record.args == ("device_marker_query", 2, "RuntimeError")
    assert record.getMessage() == ("event=round_gate_marker_query_failed failed_stage=device_marker_query rows=2 error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[2] is original_traceback
    assert record.exc_info[1] is not original_error
    assert original_error.args == (sensitive_sentinel,)
    assert sensitive_sentinel not in caplog.text


def test_compat_upsert_does_not_commit_an_unproven_round_cursor(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    monkeypatch.setattr(
        ct,
        "query_latest_round_ts",
        lambda *_a, **_k: pytest.fail("partial compatibility path must not discover or commit a marker"),
    )
    digest = {}

    ct._apply_last_synced_round(
        digest,
        instance_id=21,
        exec_status=CollectRunStatusType.SUCCESS,
        sync_round_ts=None,
        snapshot_complete=False,
        prev_synced_round=None,
    )

    assert digest == {}


def test_sync_collect_tasks_gate_dispatches_new_round(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 11,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {"last_synced_round": 100},
            "is_interval": True,
            "cycle_value_type": "cycle",
            "cycle_value": "480",
        },
        {
            "id": 12,
            "exec_status": CollectRunStatusType.RUNNING,
            "collect_digest": {},
            "is_interval": True,
            "cycle_value_type": "cycle",
            "cycle_value": "480",
        },
        {
            "id": 13,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {"last_synced_round": 100},
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
    monkeypatch.setattr(
        ct.CollectModels._default_manager,
        "filter",
        lambda *a, **k: _QS(rows),
    )
    monkeypatch.setattr(ct, "_purge_legacy_vm_sync_beats", lambda: 0)

    observed_batches = []

    def fake_completed_rounds(instance_ids, **kwargs):
        observed_batches.append((list(instance_ids), kwargs["lookback_seconds"], kwargs.get("collection_role")))
        return {
            "cmdb_11": CompletedRound(
                started_at=200,
                completed_at=260,
                labels={SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION},
            ),
            "cmdb_13": CompletedRound(
                started_at=100,
                completed_at=160,
                labels={SNAPSHOT_CONTRACT_LABEL: SNAPSHOT_CONTRACT_VERSION},
            ),
        }

    monkeypatch.setattr(ct, "query_latest_completed_rounds", fake_completed_rounds)
    dispatched = []

    class _Delay:
        @staticmethod
        def delay(*args, **kwargs):
            dispatched.append((args, kwargs))

    monkeypatch.setattr(ct, "sync_collect_task", _Delay)

    result = ct.sync_collect_tasks_gate()

    assert result["dispatched"] == 1
    assert result["skipped"] == 2
    # RUNNING 任务在访问 VM 前跳过；其余任务由一对批量查询覆盖。
    assert observed_batches == [(["cmdb_11", "cmdb_13"], 115_620, "device")]
    assert dispatched == [
        (
            (11,),
            {
                "sync_round_ts": 200,
                "sync_round_completed_at": 260,
                "sync_snapshot_complete": True,
            },
        )
    ]


def test_sync_collect_tasks_gate_treats_legacy_marker_as_upsert_only(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 14,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {},
            "params": {},
            "model_id": "host",
            "task_type": CollectPluginTypes.HOST,
            "is_interval": True,
            "cycle_value_type": "cycle",
            "cycle_value": "480",
        }
    ]

    class QS:
        pages = 0

        def filter(self, *args, **kwargs):
            return self

        def exclude(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def values(self, *args, **kwargs):
            return self

        def __getitem__(self, item):
            QS.pages += 1
            return rows if QS.pages == 1 else []

    QS.pages = 0
    monkeypatch.setattr(ct.CollectModels._default_manager, "filter", lambda *a, **k: QS())
    monkeypatch.setattr(ct, "_purge_legacy_vm_sync_beats", lambda: 0)
    monkeypatch.setattr(
        ct,
        "query_latest_completed_rounds",
        lambda *_a, **_k: {"cmdb_14": CompletedRound(started_at=200, completed_at=260)},
    )
    dispatched = []

    class Delay:
        @staticmethod
        def delay(*args, **kwargs):
            dispatched.append((args, kwargs))

    monkeypatch.setattr(ct, "sync_collect_task", Delay)

    ct.sync_collect_tasks_gate()

    assert dispatched == [
        (
            (14,),
            {
                "sync_round_ts": 200,
                "sync_round_completed_at": 260,
                "sync_snapshot_complete": False,
            },
        )
    ]


def test_sync_collect_tasks_gate_compat_when_never_marked(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 21,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {},
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
    monkeypatch.setattr(
        ct.CollectModels._default_manager,
        "filter",
        lambda *a, **k: _QS(rows),
    )
    monkeypatch.setattr(ct, "_purge_legacy_vm_sync_beats", lambda: 0)
    monkeypatch.setattr(ct, "query_latest_completed_rounds", lambda *_a, **_k: {})
    observed_compat_batches = []

    def fake_compat_probe(instance_ids):
        observed_compat_batches.append(list(instance_ids))
        return {"cmdb_21"}

    monkeypatch.setattr(ct, "query_instance_ids_with_vm_data", fake_compat_probe)

    dispatched = []

    class _Delay:
        @staticmethod
        def delay(*args, **kwargs):
            dispatched.append((args, kwargs))

    monkeypatch.setattr(ct, "sync_collect_task", _Delay)

    result = ct.sync_collect_tasks_gate()

    assert result["dispatched"] == 1
    assert observed_compat_batches == [["cmdb_21"]]
    assert dispatched == [((21,), {"sync_snapshot_complete": False})]
