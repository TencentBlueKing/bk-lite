import pytest

from apps.monitor.constants.license_catalog import MONITOR_LICENSE_OBJECT_NAMES
from apps.monitor.nats import monitor as nm


class _FakeQuerySet:
    def __init__(self, rows):
        self.rows = rows
        self.filter_kwargs = None

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        return self

    def values(self, *args):
        return self

    def annotate(self, **kwargs):
        return self.rows


@pytest.mark.unit
def test_license_monitor_instance_count_filters_active_catalog_objects(monkeypatch):
    fake_qs = _FakeQuerySet(
        [
            {"monitor_object__name": "Host", "instance_count": 2},
            {"monitor_object__name": "Mysql", "instance_count": 1},
        ]
    )
    monkeypatch.setattr(nm.MonitorInstance.objects, "filter", fake_qs.filter)

    out = nm.license_monitor_instance_count()

    assert out == {"result": True, "data": {"Host": 2, "Mysql": 1}, "message": ""}
    assert fake_qs.filter_kwargs["is_deleted"] is False
    assert fake_qs.filter_kwargs["is_active"] is True
    assert set(fake_qs.filter_kwargs["monitor_object__name__in"]) == set(MONITOR_LICENSE_OBJECT_NAMES)
    assert "Pod" not in fake_qs.filter_kwargs["monitor_object__name__in"]
    assert "TCP" not in fake_qs.filter_kwargs["monitor_object__name__in"]
