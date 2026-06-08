import pytest
from apps.monitor.models.monitor_object import MonitorObject


@pytest.mark.django_db
def test_monitor_object_has_display_fields_defaults():
    obj = MonitorObject.objects.create(name="UTHost", level="base")
    assert obj.display_fields == []
    assert obj.display_fields_customized is False


@pytest.mark.django_db
def test_display_fields_persists_structure():
    cols = [{"name": "CPU使用率", "sort_order": 0,
             "metrics": [{"plugin": "Host", "metric": "cpu_usage_total"}]}]
    obj = MonitorObject.objects.create(name="UTHost2", level="base", display_fields=cols)
    obj.refresh_from_db()
    assert obj.display_fields == cols


@pytest.mark.django_db
def test_display_fields_customized_persists():
    obj = MonitorObject.objects.create(name="UTHost3", level="base", display_fields_customized=True)
    obj.refresh_from_db()
    assert obj.display_fields_customized is True
