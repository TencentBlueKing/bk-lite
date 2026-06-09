import pytest
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.models.monitor_object import MonitorObject


def _base_data(**over):
    data = {
        "plugin": "SeedPlugin",
        "plugin_desc": "",
        "status_query": "",
        "collector": "Telegraf",
        "collect_type": "host",
        "node_selector": {},
        "name": "SeedHost",
        "type": "OS",
        "description": "",
        "default_metric": "any({instance_type='SeedHost'}) by (instance_id)",
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["cpu_usage_total"],
        "metrics": [{
            "metric_group": "Base", "name": "cpu_usage_total", "display_name": "CPU使用率",
            "query": "x{__$labels__}", "unit": "percent", "data_type": "Number",
            "description": "", "dimensions": [], "instance_id_keys": ["instance_id"],
        }],
    }
    data.update(over)
    return data


@pytest.mark.django_db
def test_seed_uses_explicit_display_fields_block():
    block = [{"name": "处理器", "sort_order": 0, "metrics": [{"plugin": "SeedPlugin", "metric": "cpu_usage_total"}]}]
    MonitorPluginService.import_basic_monitor_object(_base_data(display_fields=block))
    obj = MonitorObject.objects.get(name="SeedHost")
    assert obj.display_fields == block
    assert obj.display_fields_customized is False


@pytest.mark.django_db
def test_seed_derives_from_supplementary_indicators_when_no_block():
    MonitorPluginService.import_basic_monitor_object(_base_data())
    obj = MonitorObject.objects.get(name="SeedHost")
    assert len(obj.display_fields) == 1
    col = obj.display_fields[0]
    assert col["name"] == "CPU使用率"
    assert col["metrics"] == [{"plugin": "SeedPlugin", "metric": "cpu_usage_total"}]


@pytest.mark.django_db
def test_seed_does_not_overwrite_user_customized():
    MonitorPluginService.import_basic_monitor_object(_base_data())
    obj = MonitorObject.objects.get(name="SeedHost")
    obj.display_fields = [{"name": "用户列", "sort_order": 0, "metrics": [{"plugin": "SeedPlugin", "metric": "cpu_usage_total"}]}]
    obj.display_fields_customized = True
    obj.save()
    MonitorPluginService.import_basic_monitor_object(_base_data())
    obj.refresh_from_db()
    assert obj.display_fields[0]["name"] == "用户列"
