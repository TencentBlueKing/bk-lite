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
        objs = PolicyTemplate.objects.filter(monitor_object__name=monitor_object_name)
        templates = []
        for obj in objs:
            templates.extend(obj.templates)
        return templates

    @staticmethod
    def get_policy_templates_monitor_object():
        """获取监控策略模板"""
        return list(PolicyTemplate.objects.values_list("monitor_object_id", flat=True).distinct())
