from rest_framework import serializers

from apps.monitor.models import MonitorPlugin
from apps.monitor.services.custom_pull_plugin import CustomPullPluginService


class MonitorPluginSerializer(serializers.ModelSerializer):
    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)
    collector = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    collect_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    parent_monitor_object = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MonitorPlugin
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)
        template_type = attrs.get("template_type", getattr(instance, "template_type", "builtin"))
        template_id = attrs.get("template_id", getattr(instance, "template_id", ""))
        display_name = attrs.get("display_name", getattr(instance, "display_name", ""))
        monitor_objects = attrs.get("monitor_object")

        if template_type in {"api", "pull"}:
            if not template_id:
                raise serializers.ValidationError({"template_id": "模板ID不能为空"})
            if not display_name:
                raise serializers.ValidationError({"display_name": "模板名称不能为空"})

            if instance is not None:
                if "template_id" in attrs and attrs["template_id"] != instance.template_id:
                    raise serializers.ValidationError({"template_id": "模板ID不支持修改"})
                if monitor_objects is not None:
                    current_ids = list(instance.monitor_object.values_list("id", flat=True))
                    new_ids = [obj.id for obj in monitor_objects]
                    if current_ids != new_ids:
                        raise serializers.ValidationError({"monitor_object": "绑定对象不支持修改"})

            if monitor_objects is not None and len(monitor_objects) != 1:
                raise serializers.ValidationError({"monitor_object": "自定义模板必须且只能绑定一个监控对象"})

        return attrs

    def validate_template_type(self, value):
        allowed = {"builtin", "api", "pull", "snmp"}
        if value not in allowed:
            raise serializers.ValidationError("模板类型不合法")
        return value

    def get_parent_monitor_object(self, obj):
        """
        获取唯一的父监控对象ID（过滤掉子对象）
        """
        # 获取所有关联的监控对象中的父对象（parent 为 None 的对象）
        parent_objects = obj.monitor_object.filter(parent__isnull=True)

        # 如果存在父对象，返回第一个父对象的 ID
        if parent_objects.exists():
            return parent_objects.first().id

        # 如果没有父对象，返回 None
        return None

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data["is_pre"] = False
        template_type = validated_data.get("template_type")
        if template_type == "api":
            validated_data["collect_type"] = "push_api"
            validated_data["collector"] = "push_api"
        elif template_type == "pull":
            validated_data["collect_type"] = "bkpull"
            validated_data["collector"] = "Telegraf"

        plugin = super().create(validated_data)
        if template_type == "pull":
            CustomPullPluginService.initialize_templates(plugin)
        return plugin
