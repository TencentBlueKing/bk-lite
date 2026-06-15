from apps.monitor.models import PolicyTemplate, MonitorPlugin, MonitorObject


class PolicyService:
    @staticmethod
    def import_monitor_policy(data):
        """导入监控策略"""
        plugin_id = MonitorPlugin.objects.get(name=data["plugin"]).id
        monitor_object_id = MonitorObject.objects.get(name=data["object"]).id
        PolicyTemplate.objects.update_or_create(
            monitor_object_id=monitor_object_id,
            plugin_id=plugin_id,
            defaults={"templates": data["templates"]},
        )

    @staticmethod
    def get_policy_templates(monitor_object_name):
        """获取监控策略模板"""
        objs = PolicyTemplate.objects.select_related("monitor_object", "plugin").filter(monitor_object__name=monitor_object_name)
        templates = []
        for obj in objs:
            group_name = f"{obj.monitor_object.display_name or obj.monitor_object.name}（{obj.plugin.display_name or obj.plugin.name}）"
            for index, template in enumerate(obj.templates):
                item = {
                    **template,
                    "template_key": f"{obj.id}:{index}",
                    "monitor_object_id": obj.monitor_object_id,
                    "monitor_object_name": obj.monitor_object.name,
                    "monitor_object_display_name": obj.monitor_object.display_name or obj.monitor_object.name,
                    "plugin_id": obj.plugin_id,
                    "plugin_name": obj.plugin.name,
                    "plugin_display_name": obj.plugin.display_name or obj.plugin.name,
                    "plugin_collector": obj.plugin.collector,
                    "template_group": group_name,
                }
                templates.append(item)
        return templates

    @staticmethod
    def get_policy_templates_monitor_object():
        """获取监控策略模板"""
        return list(PolicyTemplate.objects.values_list("monitor_object_id", flat=True).distinct())
