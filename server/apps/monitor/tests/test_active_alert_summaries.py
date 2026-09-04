import logging
from types import SimpleNamespace

import pytest

from apps.monitor.services.active_alert_summaries import (
    ACTIVE_ALERT_SUMMARY_BATCH_SIZE,
    normalize_monitor_ids,
    summarize_active_alerts_by_monitor_ids,
)

MON_A = "mon-a"
MON_B = "mon-b"
MON_C = "mon-c"
_PERMISSION_FAIL_TEMPLATE = "active alert summary permission context failed monitor_id_count=%s " "failed_stage=permission_context error_type=%s"


def test_normalize_monitor_ids_dedupes_and_rejects_non_list():
    assert normalize_monitor_ids(["a", "a", "", None, "b"]) == ["a", "b"]
    with pytest.raises(ValueError):
        normalize_monitor_ids("a")


def test_summarize_empty_ids_returns_empty_items():
    result = summarize_active_alerts_by_monitor_ids(
        [],
        user_info={"user": "u"},
        accessible_policy_queryset_loader=lambda user_info: (SimpleNamespace(values_list=lambda *a, **k: []), None),
        accessible_instance_queryset_loader=lambda user_info: (
            SimpleNamespace(filter=lambda **k: SimpleNamespace(values_list=lambda *a, **kw: [])),
            None,
        ),
    )
    assert result == {"result": True, "data": {"items": []}, "message": ""}


def test_summarize_excludes_info_and_picks_highest_severity(monkeypatch):
    policy_qs = SimpleNamespace(values_list=lambda *args, **kwargs: [1, 2])

    class _InstanceQS:
        def filter(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return [MON_A, MON_B]

    rows = [
        {"monitor_instance_id": MON_A, "level": "warning", "count": 1},
        {"monitor_instance_id": MON_A, "level": "critical", "count": 2},
        {"monitor_instance_id": MON_A, "level": "info", "count": 9},
        {"monitor_instance_id": MON_B, "level": "error", "count": 1},
    ]
    captured = {}

    class _AlertQS:
        def filter(self, **kwargs):
            captured["filter"] = kwargs
            return self

        def values(self, *args):
            return self

        def annotate(self, **kwargs):
            return rows

    monkeypatch.setattr(
        "apps.monitor.services.active_alert_summaries.MonitorAlert.objects",
        _AlertQS(),
    )

    result = summarize_active_alerts_by_monitor_ids(
        [MON_A, MON_B, MON_C],
        user_info={"user": "u"},
        accessible_policy_queryset_loader=lambda user_info: (policy_qs, None),
        accessible_instance_queryset_loader=lambda user_info: (_InstanceQS(), None),
    )

    assert captured["filter"]["status"] == "new"
    assert set(captured["filter"]["level__in"]) == {"critical", "error", "warning"}
    assert result["result"] is True
    by_id = {item["monitor_id"]: item for item in result["data"]["items"]}
    assert set(by_id) == {MON_A, MON_B}  # MON_C unauthorized → omitted
    assert by_id[MON_A]["active_alarm_count"] == 3
    assert by_id[MON_A]["highest_severity"] == "critical"
    assert by_id[MON_B]["active_alarm_count"] == 1
    assert by_id[MON_B]["highest_severity"] == "error"


def test_summarize_batches_above_100_keeps_all_authorized_results(monkeypatch):
    total = ACTIVE_ALERT_SUMMARY_BATCH_SIZE + 3
    ordered_ids = [f"mon-{index:03d}" for index in range(total)]
    policy_qs = SimpleNamespace(values_list=lambda *args, **kwargs: [1])

    class _InstanceQS:
        def filter(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return list(ordered_ids)

    batches: list[list[str]] = []

    class _AlertQS:
        def __init__(self):
            self._batch: list[str] = []

        def filter(self, **kwargs):
            batch = list(kwargs["monitor_instance_id__in"])
            batches.append(batch)
            self._batch = batch
            return self

        def values(self, *args):
            return self

        def annotate(self, **kwargs):
            # One warning on the first id of each batch so both batches contribute.
            return [
                {
                    "monitor_instance_id": self._batch[0],
                    "level": "warning",
                    "count": 1,
                }
            ]

    monkeypatch.setattr(
        "apps.monitor.services.active_alert_summaries.MonitorAlert.objects",
        _AlertQS(),
    )

    result = summarize_active_alerts_by_monitor_ids(
        ordered_ids,
        user_info={},
        accessible_policy_queryset_loader=lambda user_info: (policy_qs, None),
        accessible_instance_queryset_loader=lambda user_info: (_InstanceQS(), None),
    )

    assert len(batches) == 2
    assert len(batches[0]) == ACTIVE_ALERT_SUMMARY_BATCH_SIZE
    assert len(batches[1]) == 3
    assert batches[0] + batches[1] == ordered_ids

    items = result["data"]["items"]
    assert len(items) == total
    assert [item["monitor_id"] for item in items] == ordered_ids
    by_id = {item["monitor_id"]: item for item in items}
    assert by_id[ordered_ids[0]]["active_alarm_count"] == 1
    assert by_id[ordered_ids[0]]["highest_severity"] == "warning"
    assert by_id[ordered_ids[ACTIVE_ALERT_SUMMARY_BATCH_SIZE]]["active_alarm_count"] == 1
    assert by_id[ordered_ids[1]]["active_alarm_count"] == 0
    assert by_id[ordered_ids[1]]["highest_severity"] is None


def test_summarize_returns_zero_for_authorized_without_alerts(monkeypatch):
    policy_qs = SimpleNamespace(values_list=lambda *args, **kwargs: [1])

    class _InstanceQS:
        def filter(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return [MON_A]

    class _AlertQS:
        def filter(self, **kwargs):
            return self

        def values(self, *args):
            return self

        def annotate(self, **kwargs):
            return []

    monkeypatch.setattr(
        "apps.monitor.services.active_alert_summaries.MonitorAlert.objects",
        _AlertQS(),
    )

    result = summarize_active_alerts_by_monitor_ids(
        [MON_A],
        user_info={},
        accessible_policy_queryset_loader=lambda user_info: (policy_qs, None),
        accessible_instance_queryset_loader=lambda user_info: (_InstanceQS(), None),
    )
    assert result["data"]["items"] == [{"monitor_id": MON_A, "active_alarm_count": 0, "highest_severity": None}]


def test_summarize_propagates_permission_context_error():
    error = {"result": False, "data": {}, "message": "获取对象权限失败"}
    result = summarize_active_alerts_by_monitor_ids(
        [MON_A],
        user_info={},
        accessible_policy_queryset_loader=lambda user_info: (None, error),
        accessible_instance_queryset_loader=lambda user_info: (SimpleNamespace(), None),
    )
    assert result is error


def test_summarize_permission_loader_exception_owns_traceback(caplog):
    boom_message = "permission-loader-boom"

    def boom_loader(user_info):
        raise RuntimeError(boom_message)

    with caplog.at_level(logging.ERROR, logger="monitor"):
        result = summarize_active_alerts_by_monitor_ids(
            [MON_A],
            user_info={},
            accessible_policy_queryset_loader=boom_loader,
            accessible_instance_queryset_loader=lambda user_info: (SimpleNamespace(), None),
        )

    assert result == {
        "result": False,
        "data": {"items": []},
        "message": "告警权限上下文加载失败",
    }
    records = [record for record in caplog.records if record.msg == _PERMISSION_FAIL_TEMPLATE]
    assert len(records) == 1
    record = records[0]
    assert record.args == (1, "RuntimeError")
    assert record.getMessage() == (
        "active alert summary permission context failed monitor_id_count=1 " "failed_stage=permission_context error_type=RuntimeError"
    )
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert boom_message not in record.msg
    assert boom_message not in str(record.args)
