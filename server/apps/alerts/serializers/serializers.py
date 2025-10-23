# -- coding: utf-8 --
# @File: serializers.py
# @Time: 2025/5/14 16:22
# @Author: windyzhao
from django.utils import timezone
from rest_framework import serializers
from rest_framework.fields import empty

from apps.alerts.constants import AlertStatus, IncidentStatus, NotifyResultStatus
from apps.alerts.models import AlertSource, Alert, Event, Level, AlertAssignment, AlertShield, Incident, SystemSetting, \
    NotifyResult, OperatorLog
from apps.system_mgmt.models.user import User


class AlertSourceModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertSource model.
    """
    event_count = serializers.SerializerMethodField()
    last_event_time = serializers.SerializerMethodField()

    class Meta:
        model = AlertSource
        fields = "__all__"
        extra_kwargs = {
            # "secret": {"write_only": True},
            # "config": {"write_only": True},
            "last_active_time": {"write_only": True},
            "is_delete": {"write_only": True},
        }

    @staticmethod
    def get_event_count(obj):
        return obj.event_set.count()

    @staticmethod
    def get_last_event_time(obj):
        """
        获取最近一次事件时间
        """
        format_time = "%Y-%m-%d %H:%M:%S"
        last_event = obj.event_set.order_by('-received_at').first()
        if not last_event or not last_event.received_at:
            return ""
        # 如果需要格式化时间，可以在这里进行
        return last_event.received_at.strftime(format_time)


class EventModelSerializer(serializers.ModelSerializer):
    """
    Serializer for Event model.
    """

    # 格式化时间字段
    start_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    source_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = '__all__'
        extra_kwargs = {
            # "events": {"write_only": True},  # events 字段只读
            "start_time": {"read_only": True},
            "end_time": {"read_only": True},
            "labels": {"write_only": True},
            # "raw_data": {"write_only": True},
            "search_vector": {"write_only": True},
            # "labels": {"write_only": True},
        }

    @staticmethod
    def get_source_name(obj):
        """
        Get the names of the sources associated with the alert.
        通过 Alert -> Events -> AlertSource 获取告警源名称
        """
        # 如果使用了注解（推荐）
        return obj.source.name


class AlertModelSerializer(serializers.ModelSerializer):
    """
    Serializer for Alert model.
    """
    event_count = serializers.SerializerMethodField()
    source_names = serializers.SerializerMethodField()
    # 持续时间
    duration = serializers.SerializerMethodField()
    operator_user = serializers.SerializerMethodField()

    # 格式化时间字段
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    first_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    last_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    incident_name = serializers.SerializerMethodField()
    notify_status = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        try:
            self.alert_notify_result_map = self.set_alert_notify_result_map(instance)
        except Exception:
            self.alert_notify_result_map = {}

    class Meta:
        model = Alert
        exclude = ["events"]
        extra_kwargs = {
            # "events": {"write_only": True},  # events 字段只读
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "operator": {"write_only": True},
            "search_vector": {"write_only": True},
            "labels": {"write_only": True},
        }

    @staticmethod
    def set_alert_notify_result_map(instance):
        result = {}
        if isinstance(instance, list):
            # 如果是列表实例，预处理通知状态
            alerts = [i.alert_id for i in instance]
            notify_result = NotifyResult.objects.filter(notify_type="alert", notify_object__in=alerts).values_list(
                "notify_object", "notify_result")
            notify_result_map = {i[0]: i[1] for i in notify_result}
            for alert in instance:
                alert_result = notify_result_map.get(alert.alert_id)
                if alert_result:
                    result.setdefault(alert.alert_id, []).append(alert_result == "success")

        return result

    @staticmethod
    def get_duration(obj):
        """
        当前时间- 创建时间
        """
        if not obj.created_at or obj.status not in AlertStatus.ACTIVATE_STATUS:
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
    def get_source_names(obj):
        """
        Get the names of the sources associated with the alert.
        通过 Alert -> Events -> AlertSource 获取告警源名称
        """
        # 如果使用了注解（推荐）
        if hasattr(obj, 'source_names_annotated') and obj.source_names_annotated:
            return obj.source_names_annotated

        # fallback: 通过关联查询获取
        try:
            # Alert -> Events -> AlertSource
            source_names = set()  # 使用set去重
            for event in obj.events.all():
                if event.source:
                    source_names.add(event.source.name)
            return ", ".join(sorted(source_names))
        except Exception:
            return ""

    @staticmethod
    def get_event_count(obj):
        """
        Get the count of events associated with the alert.
        """
        # 如果使用了注解（推荐）
        if hasattr(obj, 'event_count_annotated'):
            return obj.event_count_annotated

        # fallback: 直接计数
        try:
            return obj.events.count()
        except Exception:
            return 0

    @staticmethod
    def get_operator_user(obj):
        if not obj.operator:
            return ""
        user_name_list = User.objects.filter(username__in=obj.operator).values_list("display_name", flat=True)
        return ", ".join(list(user_name_list))

    @staticmethod
    def get_incident_name(obj):
        """
        获取关联的事故标题
        """

        if hasattr(obj, 'incident_title_annotated'):
            return obj.incident_title_annotated

        return ""

    def get_notify_status(self, obj):
        """
        获取告警通知状态
        """
        alert_result = self.alert_notify_result_map.get(obj.alert_id)
        if not alert_result:
            return ""
        if all(alert_result):
            return NotifyResultStatus.SUCCESS
        if any(alert_result):
            return NotifyResultStatus.FAILED
        else:
            return NotifyResultStatus.PARTIAL_SUCCESS


class LevelModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = '__all__'


class AlertAssignmentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    class Meta:
        model = AlertAssignment
        fields = "__all__"
        extra_kwargs = {
            # 'alert_id': {'read_only': True},
            # 'status': {'required': True},
            # 'operator': {'required': True},
        }


class AlertShieldModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    class Meta:
        model = AlertShield
        fields = "__all__"
        extra_kwargs = {}


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


class SystemSettingModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = "__all__"
        extra_kwargs = {}


class OperatorLogModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = OperatorLog
        fields = "__all__"
