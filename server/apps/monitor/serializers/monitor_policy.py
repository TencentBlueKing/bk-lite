import logging

from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorPolicy

logger = logging.getLogger(__name__)


class MonitorPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorPolicy
        fields = "__all__"

    def validate_group_by(self, value):
        """校验 group_by 首位必须是监控对象的实例主键，防止下游扫描链路误判实例归属。"""
        if not value:
            return value

        monitor_object = self._get_monitor_object()
        if monitor_object is None:
            return value

        instance_id_keys = getattr(monitor_object, "instance_id_keys", None)
        if not instance_id_keys:
            return value

        primary_key = instance_id_keys[0]
        if value[0] != primary_key:
            logger.warning(
                "group_by[0]=%s does not match instance_id_keys[0]=%s, auto-correcting",
                value[0],
                primary_key,
            )
            value = [primary_key] + [k for k in value if k != primary_key]

        return value

    def _get_monitor_object(self):
        """从请求数据或已有实例中获取关联的监控对象。"""
        request_data = self.initial_data if hasattr(self, "initial_data") else {}
        monitor_object_id = request_data.get("monitor_object")

        if monitor_object_id:
            from apps.monitor.models.monitor_object import MonitorObject

            try:
                return MonitorObject.objects.get(pk=monitor_object_id)
            except MonitorObject.DoesNotExist:
                return None

        if self.instance and hasattr(self.instance, "monitor_object"):
            return self.instance.monitor_object

        return None
