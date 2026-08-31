"""实例列表上报时间/状态取最后一条原始样本，而不是即时查询求值时刻。"""

from datetime import datetime, timezone

import pytest

from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService

pytestmark = pytest.mark.django_db

EVAL_TS = 1_782_888_110
SAMPLE_TS = 1_782_887_860


class _LastSampleVM:
    def __init__(self):
        self.queries = []

    def query(self, query, step="20m", time=None, lookback_delta=None):
        self.queries.append(query)
        assert step == "20m"
        assert "tlast_over_time" in query
        return {
            "data": {
                "result": [
                    {
                        "metric": {"instance_id": "host-1", "agent_id": "agent-1"},
                        "value": [EVAL_TS, str(SAMPLE_TS)],
                    }
                ]
            }
        }


def test_instance_list_time_and_status_follow_last_raw_sample(monkeypatch):
    MonitorObjectService.clear_instance_status_cache()
    monitor_object = MonitorObject.objects.create(
        name="HostLastSample",
        default_metric="any({instance_type='os'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-1',)",
        name="host-1",
        monitor_object=monitor_object,
    )
    fake_vm = _LastSampleVM()
    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: fake_vm)
    monkeypatch.setattr(
        "apps.monitor.utils.instance.datetime",
        type("FrozenDatetime", (), {"now": staticmethod(lambda tz: datetime.fromtimestamp(SAMPLE_TS + 30, tz=tz))}),
    )

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=20,
        name=None,
        qs=MonitorInstance.objects.filter(id=instance.id),
    )

    row = data["results"][0]
    assert row["time"] == SAMPLE_TS
    assert row["status"] == "normal"
    assert row["agent_id"] == "agent-1"
    assert "any({instance_type='os'})" not in fake_vm.queries[0]
    assert "max(tlast_over_time(({instance_type='os'})[20m])) by (instance_id)" in fake_vm.queries[0]


def test_instance_list_marks_stale_last_sample_unavailable(monkeypatch):
    MonitorObjectService.clear_instance_status_cache()
    monitor_object = MonitorObject.objects.create(
        name="HostStaleSample",
        default_metric="any({instance_type='os'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-1',)",
        name="host-1",
        monitor_object=monitor_object,
    )
    fake_vm = _LastSampleVM()
    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: fake_vm)
    monkeypatch.setattr(
        "apps.monitor.utils.instance.datetime",
        type("FrozenDatetime", (), {"now": staticmethod(lambda tz: datetime.fromtimestamp(SAMPLE_TS + 601, tz=tz))}),
    )

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=20,
        name=None,
        qs=MonitorInstance.objects.filter(id=instance.id),
    )

    row = data["results"][0]
    assert row["time"] == SAMPLE_TS
    assert row["status"] == "unavailable"



def test_plugin_status_map_uses_last_sample_iso_time(monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="HostPluginLastSample",
        default_metric="any({instance_type='os'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    fake_vm = _LastSampleVM()
    monkeypatch.setattr("apps.monitor.services.monitor_instance.VictoriaMetricsAPI", lambda: fake_vm)

    status_map = InstanceSearch(monitor_object, {}).get_plugin_normal_status_map(
        ["instance_id"],
        "any({plugin_id='host'}) by (instance_id)",
    )

    assert status_map == {
        "('host-1',)": datetime.fromtimestamp(SAMPLE_TS, tz=timezone.utc).isoformat(),
    }
    assert fake_vm.queries == [
        "max(tlast_over_time(({plugin_id='host'})[20m])) by (instance_id)",
    ]
