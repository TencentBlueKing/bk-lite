from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.monitor.nats import monitor as nm


@pytest.fixture
def authorized_scope(mocker):
    mocker.patch(
        "apps.monitor.nats.monitor._get_nats_actor_scope",
        return_value=(None, None, None, [1], None, None),
    )
    mocker.patch(
        "apps.monitor.nats.monitor._get_authorized_monitor_instances",
        return_value=({"mon-1": SimpleNamespace(id="mon-1"), "mon-2": SimpleNamespace(id="mon-2")}, None),
    )


def test_query_latest_interface_metrics_empty_ids_returns_empty(authorized_scope):
    out = nm.query_latest_interface_metrics([], user_info={"user": "u"})
    assert out == {"result": True, "data": {"items": []}, "message": ""}


def test_query_latest_interface_metrics_omits_unauthorized_and_does_not_fail(authorized_scope, mocker):
    captured = {}

    def fake_query(vm_api, instance_ids):
        captured["ids"] = instance_ids
        return [{"instance_id": "mon-1", "ifDescr": "Gi0/1", "metrics": {"interface_ifOperStatus": 1}}]

    mocker.patch("apps.monitor.nats.monitor.query_interface_metric_items", side_effect=fake_query)
    mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI", return_value=Mock())
    out = nm.query_latest_interface_metrics(["mon-1", "ghost"], user_info={"user": "u"})
    assert out["result"] is True
    assert captured["ids"] == ["mon-1"]
    assert out["data"]["items"][0]["ifDescr"] == "Gi0/1"


def test_query_latest_interface_metrics_all_unauthorized_returns_empty(authorized_scope, mocker):
    fake_query = mocker.patch("apps.monitor.nats.monitor.query_interface_metric_items")
    out = nm.query_latest_interface_metrics(["ghost"], user_info={"user": "u"})
    assert out == {"result": True, "data": {"items": []}, "message": ""}
    fake_query.assert_not_called()


def test_query_latest_interface_metrics_rejects_over_limit(authorized_scope):
    out = nm.query_latest_interface_metrics([str(i) for i in range(201)], user_info={"user": "u"})
    assert out["result"] is False
    assert "不能超过" in out["message"]


def test_query_latest_interface_metrics_vm_failure_does_not_raise(authorized_scope, mocker):
    mocker.patch(
        "apps.monitor.nats.monitor.query_interface_metric_items",
        side_effect=RuntimeError("vm down"),
    )
    mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI", return_value=Mock())
    out = nm.query_latest_interface_metrics(["mon-1"], user_info={"user": "u"})
    assert out["result"] is False
    assert out["data"] == {"items": []}
