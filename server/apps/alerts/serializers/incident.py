# -- coding: utf-8 --
from django.utils import timezone
from rest_framework import serializers

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models.models import Alert, Incident
from apps.system_mgmt.models.user import User


class IncidentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for Incident model.
    """
    # 持续时间
    duration = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    # 多对多字段处理 一个alert只能属于一个incident
    alert = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Alert.objects.all(),
        required=False,
        error_messages={
            'does_not_exist': '告警ID {pk_value} 已关联Incident或者不存在，请重新检查告警',
        }
    )
    sources = serializers.SerializerMethodField()
    alert_count = serializers.SerializerMethodField()
    operator_users = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            # "operator": {"write_only": True},
            "labels": {"write_only": True},
            "alert": {"write_only": True},  # 多对多关系字段
        }

    def create(self, validated_data):
        """
        重写create方法来处理多对多关系
        """
        alerts = validated_data.pop('alert', [])
        incident = Incident.objects.create(**validated_data)
        if alerts:
            incident.alert.set(alerts)
        return incident

    def update(self, instance, validated_data):
        """
        重写update方法来处理多对多关系
        """
        alerts = validated_data.pop('alert', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if alerts is not None:
            instance.alert.set(alerts)
        return instance

    @staticmethod
    def get_duration(obj):
        """
        当前时间- 创建时间
        """
        if obj.status not in IncidentStatus.ACTIVATE_STATUS:
            return "--"

        # 计算持续时间
        now = timezone.now()
        duration = now - obj.created_at
        total_seconds = int(duration.total_seconds())

        # 计算各个时间单位
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        # 构建格式化字符串
        result = ""
        if days > 0:
            result += f"{days}d "
        if hours > 0:
            result += f"{hours}h "
        if minutes > 0:
            result += f"{minutes}m "
        if seconds > 0 or result == "":
            result += f"{seconds}s"

        return result

    @staticmethod
    def get_sources(obj):
        """
        获取关联的告警源名称
        """
        sources = set()
        for alert in obj.alert.all():
            for event in alert.events.all():
                if event.source:
                    sources.add(event.source.name)
        return ", ".join(sorted(sources)) if sources else ""

    @staticmethod
    def get_alert_count(obj):
        """
        获取关联的告警数量
        """
        # 如果使用了注解（推荐）
        if hasattr(obj, 'alert_count'):
            return obj.alert_count

        # fallback: 直接计数
        return obj.alert.count() if obj.alert else 0

    @staticmethod
    def get_operator_users(obj):
        """
        获取操作员用户列表，从 JSONField 转换为字符串
        """
        if not obj.operator:
            return ""

        # 如果 operator 是字符串，直接返回
        if isinstance(obj.operator, str):
            return obj.operator

        # 如果 operator 是列表，转换为逗号分隔的字符串
        if isinstance(obj.operator, list):
            user_name_list = User.objects.filter(username__in=obj.operator).values_list("display_name", flat=True)
            return ", ".join(list(user_name_list))

        return ""
