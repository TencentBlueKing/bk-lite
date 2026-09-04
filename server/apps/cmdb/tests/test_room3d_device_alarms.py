import logging

from apps.cmdb.services.room3d_device_alarms import _ENRICH_RESULT_SOFT_FAIL_TEMPLATE, _ENRICH_RPC_FAIL_TEMPLATE, enrich_room3d_devices_with_alarms

DEVICE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DEVICE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _rack_with_devices(*devices):
    return [{"rack_id": "r1", "devices": [dict(device) for device in devices]}]


def test_enrich_unbound_devices_without_monitor_call():
    racks = _rack_with_devices(
        {
            "device_id": DEVICE_A,
            "device_name": "SW-01",
            "monitor_id": "",
        }
    )

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={"user": "u"},
        monitor_client_factory=lambda: (_ for _ in ()).throw(AssertionError("should not call")),
    )

    device = racks[0]["devices"][0]
    assert "monitor_id" not in device
    assert device["monitor_bound"] is False
    assert device["alarm_unavailable"] is False
    assert device["active_alarm_count"] is None
    assert device["highest_severity"] is None


def test_enrich_applies_monitor_summaries_and_strips_monitor_id():
    racks = _rack_with_devices(
        {"device_id": DEVICE_A, "monitor_id": "mon-a"},
        {"device_id": DEVICE_B, "monitor_id": "mon-b"},
    )

    class FakeMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            assert monitor_ids == ["mon-a", "mon-b"]
            assert kwargs["user_info"]["user"] == "alice"
            return {
                "result": True,
                "data": {
                    "items": [
                        {
                            "monitor_id": "mon-a",
                            "active_alarm_count": 2,
                            "highest_severity": "critical",
                        },
                        {
                            "monitor_id": "mon-b",
                            "active_alarm_count": 0,
                            "highest_severity": None,
                        },
                    ]
                },
                "message": "",
            }

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={"user": "alice"},
        monitor_client_factory=FakeMonitor,
    )
    a, b = racks[0]["devices"]
    assert "monitor_id" not in a and "monitor_id" not in b
    assert a["monitor_bound"] is True
    assert a["active_alarm_count"] == 2
    assert a["highest_severity"] == "critical"
    assert a["alarm_unavailable"] is False
    assert b["active_alarm_count"] == 0
    assert b["highest_severity"] is None


def test_enrich_info_only_monitor_summary_is_bound_zero_alarms():
    """Monitor already excludes info; zero summary means no valid alarms / no glow."""
    racks = _rack_with_devices({"device_id": DEVICE_A, "monitor_id": "mon-info-only"})

    class InfoOnlyMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            assert monitor_ids == ["mon-info-only"]
            return {
                "result": True,
                "data": {
                    "items": [
                        {
                            "monitor_id": "mon-info-only",
                            "active_alarm_count": 0,
                            "highest_severity": None,
                        }
                    ]
                },
                "message": "",
            }

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={},
        monitor_client_factory=InfoOnlyMonitor,
    )
    device = racks[0]["devices"][0]
    assert "monitor_id" not in device
    assert device["monitor_bound"] is True
    assert device["alarm_unavailable"] is False
    assert device["active_alarm_count"] == 0
    assert device["highest_severity"] is None


def test_enrich_negative_count_marks_unavailable():
    racks = _rack_with_devices({"device_id": DEVICE_A, "monitor_id": "mon-a"})

    class NegativeCountMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            return {
                "result": True,
                "data": {
                    "items": [
                        {
                            "monitor_id": "mon-a",
                            "active_alarm_count": -1,
                            "highest_severity": "warning",
                        }
                    ]
                },
                "message": "",
            }

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={},
        monitor_client_factory=NegativeCountMonitor,
    )
    device = racks[0]["devices"][0]
    assert device["monitor_bound"] is True
    assert device["alarm_unavailable"] is True
    assert device["active_alarm_count"] is None
    assert device["highest_severity"] is None


def test_enrich_marks_unavailable_when_monitor_omits_or_fails():
    racks = _rack_with_devices({"device_id": DEVICE_A, "monitor_id": "mon-a"})

    class OmittingMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            return {"result": True, "data": {"items": []}, "message": ""}

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={},
        monitor_client_factory=OmittingMonitor,
    )
    assert racks[0]["devices"][0]["monitor_bound"] is True
    assert racks[0]["devices"][0]["alarm_unavailable"] is True
    assert "monitor_id" not in racks[0]["devices"][0]

    racks = _rack_with_devices({"device_id": DEVICE_A, "monitor_id": "mon-a"})

    class BoomMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, *args, **kwargs):
            raise RuntimeError("nats down")

    enrich_room3d_devices_with_alarms(
        racks,
        user_info={},
        monitor_client_factory=BoomMonitor,
    )
    assert racks[0]["devices"][0]["alarm_unavailable"] is True
    assert racks[0]["devices"][0]["monitor_bound"] is True


def test_default_monitor_client_uses_in_process_app_client(monkeypatch):
    """Avoid nested NATS when enrich runs inside get_room3d_layout handler."""
    captured = {}

    class FakeMonitor:
        def __init__(self, is_local_client=False):
            captured["is_local_client"] = is_local_client

    monkeypatch.setattr(
        "apps.rpc.monitor.Monitor",
        FakeMonitor,
    )
    from apps.cmdb.services.room3d_device_alarms import _default_monitor_client

    client = _default_monitor_client()
    assert isinstance(client, FakeMonitor)
    assert captured["is_local_client"] is True


def test_enrich_monitor_rpc_failure_owns_safe_traceback(caplog):
    racks = _rack_with_devices({"device_id": DEVICE_A, "monitor_id": "mon-a"})
    boom_message = "nats-down-without-payload"

    class BoomMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, *args, **kwargs):
            raise RuntimeError(boom_message)

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        enrich_room3d_devices_with_alarms(
            racks,
            user_info={},
            monitor_client_factory=BoomMonitor,
        )

    device = racks[0]["devices"][0]
    assert "monitor_id" not in device
    assert device["monitor_bound"] is True
    assert device["alarm_unavailable"] is True
    assert device["active_alarm_count"] is None
    assert device["highest_severity"] is None

    records = [record for record in caplog.records if record.msg == _ENRICH_RPC_FAIL_TEMPLATE]
    assert len(records) == 1
    record = records[0]
    assert record.args == (1, "RuntimeError")
    assert record.getMessage() == ("room3d device alarm enrich failed monitor_id_count=1 " "failed_stage=monitor_rpc error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert boom_message not in record.msg
    assert boom_message not in str(record.args)


def test_enrich_monitor_result_false_logs_warning(caplog):
    racks = _rack_with_devices(
        {"device_id": DEVICE_A, "monitor_id": "mon-a"},
        {"device_id": DEVICE_B, "monitor_id": "mon-b"},
    )

    class FalseResultMonitor:
        def query_active_alert_summaries_by_monitor_ids(self, *args, **kwargs):
            return {"result": False, "data": {"items": []}, "message": "permission denied"}

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        enrich_room3d_devices_with_alarms(
            racks,
            user_info={},
            monitor_client_factory=FalseResultMonitor,
        )

    for device in racks[0]["devices"]:
        assert "monitor_id" not in device
        assert device["monitor_bound"] is True
        assert device["alarm_unavailable"] is True
        assert device["active_alarm_count"] is None

    records = [record for record in caplog.records if record.msg == _ENRICH_RESULT_SOFT_FAIL_TEMPLATE]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == (2, "result_false")
    assert record.getMessage() == ("room3d device alarm enrich soft-failed monitor_id_count=2 " "failed_stage=monitor_result error_type=result_false")
    assert record.exc_info is None
