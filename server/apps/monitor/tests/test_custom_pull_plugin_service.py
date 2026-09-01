"""CustomPullPluginService：自定义 PULL 插件必须绑定监控对象并写入 child/UI 模板。"""
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
from apps.monitor.services.custom_pull_plugin import DEFAULT_PULL_CHILD_TEMPLATE, CustomPullPluginService

pytestmark = pytest.mark.django_db


def test_initialize_templates_requires_bound_monitor_object():
    plugin = MonitorPlugin.objects.create(name="pull-unbound")
    with pytest.raises(BaseAppException, match="必须绑定一个监控对象"):
        CustomPullPluginService.initialize_templates(plugin)


def test_initialize_templates_writes_child_toml_and_ui_for_object():
    obj = MonitorObject.objects.create(name="HostPull", level="base")
    plugin = MonitorPlugin.objects.create(name="pull-bound")
    plugin.monitor_object.add(obj)

    CustomPullPluginService.initialize_templates(plugin)

    child = MonitorPluginConfigTemplate.objects.get(plugin=plugin, type="custom_pull", config_type="child")
    assert child.file_type == "toml"
    assert child.content == DEFAULT_PULL_CHILD_TEMPLATE
    assert "{{ server_url }}" in child.content

    ui = MonitorPluginUITemplate.objects.get(plugin=plugin)
    assert ui.content["object_name"] == "HostPull"
    assert ui.content["instance_type"] == "HostPull"
    assert ui.content["collect_type"] == "bkpull"
    assert ui.content["config_type"] == ["custom_pull"]


def test_initialize_templates_is_idempotent_and_refreshes_object_name():
    obj = MonitorObject.objects.create(name="OldName", level="base")
    plugin = MonitorPlugin.objects.create(name="pull-refresh")
    plugin.monitor_object.add(obj)
    CustomPullPluginService.initialize_templates(plugin)

    obj.name = "NewName"
    obj.save()
    CustomPullPluginService.initialize_templates(plugin)

    assert MonitorPluginConfigTemplate.objects.filter(plugin=plugin).count() == 1
    assert MonitorPluginUITemplate.objects.filter(plugin=plugin).count() == 1
    ui = MonitorPluginUITemplate.objects.get(plugin=plugin)
    assert ui.content["object_name"] == "NewName"
