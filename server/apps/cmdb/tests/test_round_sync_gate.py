"""轮次守门判定与 VM 查询轮次窗口测试。"""

from unittest import mock

import pytest

from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.collection.round_sync import decide_gate_action, get_last_synced_round, uses_vm_reconciliation
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType

pytestmark = pytest.mark.unit


def test_uses_vm_reconciliation_excludes_config_file():
    assert uses_vm_reconciliation(CollectPluginTypes.HOST) is True
    assert uses_vm_reconciliation(CollectPluginTypes.VM) is True
    assert uses_vm_reconciliation(CollectPluginTypes.CONFIG_FILE) is False


def test_get_last_synced_round():
    assert get_last_synced_round(None) is None
    assert get_last_synced_round({}) is None
    assert get_last_synced_round({"last_synced_round": "1700000000"}) == 1700000000
    assert get_last_synced_round({"last_synced_round": "bad"}) is None


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


def test_query_uses_round_window_and_filters_old_samples(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.time.time",
        lambda: 1_700_000_200,
    )
    round_ts = 1_700_000_100
    rows = [
        {"metric": {"__name__": "a"}, "value": [1_700_000_050, "1"]},
        {"metric": {"__name__": "b"}, "value": [1_700_000_150, "1"]},
    ]
    with mock.patch(
        "apps.cmdb.collection.query_vm.requests.post",
        return_value=_ok_response(rows),
    ) as post:
        payload = Collection().query("metric_a or metric_b", retries=1, min_timestamp=round_ts)

    query = post.call_args.kwargs["data"]["query"]
    assert query.startswith("last_over_time((metric_a or metric_b)[")
    assert query.endswith("s:])")
    # age = now - round_ts + buffer = 100 + 120 = 220
    assert "[220s:]" in query
    result = payload["data"]["result"]
    assert len(result) == 1
    assert result[0]["metric"]["__name__"] == "b"


def test_query_default_still_uses_1h_window():
    with mock.patch(
        "apps.cmdb.collection.query_vm.requests.post",
        return_value=_ok_response(),
    ) as post:
        Collection().query("metric_a or metric_b", retries=1)

    assert post.call_args.kwargs["data"]["query"] == ("last_over_time((metric_a or metric_b)[1h:])")


def test_sync_collect_tasks_gate_dispatches_new_round(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 11,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {"last_synced_round": 100},
        },
        {
            "id": 12,
            "exec_status": CollectRunStatusType.RUNNING,
            "collect_digest": {},
        },
        {
            "id": 13,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {"last_synced_round": 100},
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

    def fake_round_ts(instance_id, **_kwargs):
        if instance_id == "cmdb_11":
            return 200
        if instance_id == "cmdb_13":
            return 100
        return None

    monkeypatch.setattr(ct, "query_latest_round_ts", fake_round_ts)
    monkeypatch.setattr(ct, "has_instance_vm_data", lambda *_a, **_k: False)

    dispatched = []

    class _Delay:
        @staticmethod
        def delay(*args, **kwargs):
            dispatched.append((args, kwargs))

    monkeypatch.setattr(ct, "sync_collect_task", _Delay)

    result = ct.sync_collect_tasks_gate()

    assert result["dispatched"] == 1
    assert result["skipped"] == 2
    assert dispatched == [((11,), {"sync_round_ts": 200})]


def test_sync_collect_tasks_gate_compat_when_never_marked(monkeypatch):
    from apps.cmdb.tasks import celery_tasks as ct

    rows = [
        {
            "id": 21,
            "exec_status": CollectRunStatusType.SUCCESS,
            "collect_digest": {},
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
    monkeypatch.setattr(ct, "query_latest_round_ts", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "has_instance_vm_data", lambda *_a, **_k: True)

    dispatched = []

    class _Delay:
        @staticmethod
        def delay(*args, **kwargs):
            dispatched.append((args, kwargs))

    monkeypatch.setattr(ct, "sync_collect_task", _Delay)

    result = ct.sync_collect_tasks_gate()

    assert result["dispatched"] == 1
    assert dispatched == [((21,), {})]
