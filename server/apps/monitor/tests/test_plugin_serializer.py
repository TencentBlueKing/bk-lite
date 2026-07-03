"""MonitorPluginSerializer 规格测试。"""

import pytest

from rest_framework import serializers

from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.plugin import MonitorPluginSerializer

pytestmark = pytest.mark.django_db


class TestValidateTemplateType:
    def test_invalid(self):
        with pytest.raises(serializers.ValidationError):
            MonitorPluginSerializer().validate_template_type("bogus")

    def test_valid(self):
        assert MonitorPluginSerializer().validate_template_type("api") == "api"


class TestValidate:
    def test_api_requires_template_id(self):
        s = MonitorPluginSerializer()
        with pytest.raises(serializers.ValidationError):
            s.validate({"template_type": "api", "template_id": "", "display_name": "n"})

    def test_api_requires_display_name(self):
        s = MonitorPluginSerializer()
        with pytest.raises(serializers.ValidationError):
            s.validate({"template_type": "api", "template_id": "t1", "display_name": ""})

    def test_custom_requires_single_object(self):
        obj1 = MonitorObject.objects.create(name="PSObj1", level="base")
        obj2 = MonitorObject.objects.create(name="PSObj2", level="base")
        s = MonitorPluginSerializer()
        with pytest.raises(serializers.ValidationError):
            s.validate({
                "template_type": "api", "template_id": "t1", "display_name": "n",
                "monitor_object": [obj1, obj2],
            })

    def test_builtin_passes_without_template_id(self):
        s = MonitorPluginSerializer()
        out = s.validate({"template_type": "builtin"})
        assert out["template_type"] == "builtin"

    def test_node_selector_normalized(self):
        s = MonitorPluginSerializer()
        out = s.validate({"template_type": "builtin", "node_selector": {"is_container": True}})
        assert out["node_selector"] == {"is_container": True}

    def test_invalid_node_selector_raises(self):
        s = MonitorPluginSerializer()
        with pytest.raises(serializers.ValidationError):
            s.validate({"template_type": "builtin", "node_selector": {"bogus_key": 1}})


class TestGetParentMonitorObject:
    def test_returns_parent_id(self):
        parent = MonitorObject.objects.create(name="PSParent", level="base")
        plugin = MonitorPlugin.objects.create(name="PSPlugin")
        plugin.monitor_object.add(parent)
        assert MonitorPluginSerializer().get_parent_monitor_object(plugin) == parent.id

    def test_returns_none_when_only_children(self):
        parent = MonitorObject.objects.create(name="PSParent2", level="base")
        child = MonitorObject.objects.create(name="PSChild2", level="derivative", parent=parent)
        plugin = MonitorPlugin.objects.create(name="PSPlugin2")
        plugin.monitor_object.add(child)
        assert MonitorPluginSerializer().get_parent_monitor_object(plugin) is None


class TestBuildDefaultStatusQuery:
    def test_uses_instance_id_keys(self):
        obj = MonitorObject.objects.create(name="PSObj3", level="base", instance_id_keys=["instance_id", "device"])
        plugin = MonitorPlugin.objects.create(name="PSPlugin3", template_id="tid-3")
        plugin.monitor_object.add(obj)
        q = MonitorPluginSerializer.build_default_status_query(plugin)
        assert "plugin_id='tid-3'" in q
        assert "by (instance_id, device)" in q

    def test_defaults_to_instance_id(self):
        plugin = MonitorPlugin.objects.create(name="PSPlugin4", template_id="tid-4")
        q = MonitorPluginSerializer.build_default_status_query(plugin)
        assert "by (instance_id)" in q


class TestCreate:
    def test_api_create_sets_collect_fields(self, mocker):
        obj = MonitorObject.objects.create(name="PSCreateObj", level="base")
        s = MonitorPluginSerializer(data={
            "name": "apiplugin", "template_type": "api", "template_id": "api-1",
            "display_name": "API插件", "monitor_object": [obj.id],
        })
        assert s.is_valid(), s.errors
        plugin = s.save()
        assert plugin.collect_type == "push_api"
        assert plugin.collector == "push_api"
        assert plugin.is_pre is False
        assert plugin.status_query  # 自动生成默认状态查询
