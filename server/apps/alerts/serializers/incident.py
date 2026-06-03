# -- coding: utf-8 --
from django.utils import timezone
from rest_framework import serializers

from apps.alerts.constants import PERMISSION_INCIDENT
from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models.models import Alert, Incident
from apps.alerts.utils.operator_scope import normalize_usernames, validate_incident_operators
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.core.utils.serializers import AuthSerializer
from apps.system_mgmt.models.user import User


class IncidentModelSerializer(AuthSerializer):
    """
    Serializer for Incident model.
    """

    permission_key = PERMISSION_INCIDENT

    # 持续时间
    duration = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    # 多对多字段处理 一个 alert 可归属多个 incident
    alert = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Alert.objects.all(),
        required=False,
        error_messages={
            "does_not_exist": "告警ID {pk_value} 不存在或无权限访问，请重新检查告警",
        },
    )
    sources = serializers.SerializerMethodField()
    alert_count = serializers.SerializerMethodField()
    operator_users = serializers.SerializerMethodField()
    collaborator_users = serializers.SerializerMethodField()
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)

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

    def __init__(self, instance=None, data=serializers.empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        allowed_alert_queryset = self.context.get("allowed_alert_queryset")
        if allowed_alert_queryset is not None:
            self.fields["alert"].queryset = allowed_alert_queryset

    def create(self, validated_data):
        """
        重写create方法来处理多对多关系
        """
        alerts = validated_data.pop("alert", [])
        incident = Incident.objects.create(**validated_data)
        if alerts:
            incident.alert.set(alerts)
        return incident

    def validate_operator(self, value):
        normalized_operators = normalize_usernames(value)
        if not normalized_operators:
            return normalized_operators

        alerts = self._get_operator_scope_alerts()
        normalized_operators, validation_message = validate_incident_operators(alerts, normalized_operators)
        if validation_message:
            raise serializers.ValidationError(validation_message)
        return normalized_operators

    def validate_team(self, value):
        value = normalize_team_ids(value)
        if not value:
            return value
        request = self.context.get("request")
        if request is None:
            return value
        user = getattr(request, "user", None)
        if user and getattr(user, "is_superuser", False):
            return value
        authorized_group_ids = get_authorized_group_ids(request)
        unauthorized_teams = set(value) - set(authorized_group_ids)
        if unauthorized_teams:
            raise serializers.ValidationError(f"You are not authorized to assign teams: {list(unauthorized_teams)}")
        return value

    def update(self, instance, validated_data):
        """
        重写update方法来处理多对多关系
        """
        alerts = validated_data.pop("alert", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if alerts is not None:
            instance.alert.set(alerts)
        return instance

    def _get_operator_scope_alerts(self):
        incoming_alerts = self.initial_data.get("alert") if hasattr(self, "initial_data") else None
        if incoming_alerts is not None:
            return self.context.get("allowed_alert_queryset", Alert.objects.none()).filter(id__in=incoming_alerts)
        if self.instance is not None:
            return self.instance.alert.all()
        return []

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
        prefetched_alerts = getattr(obj, "_prefetched_objects_cache", {}).get("alert")
        if prefetched_alerts is not None:
            return len(prefetched_alerts)

        # 如果使用了注解（推荐）
        if hasattr(obj, "alert_count"):
            return obj.alert_count

        # fallback: 直接计数
        return obj.alert.count() if obj.alert else 0

    def get_operator_users(self, obj):
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
            operator_user_map = self.context.get("operator_user_map")
            if operator_user_map is not None:
                return ", ".join(operator_user_map.get(u, u) for u in obj.operator)
            user_name_list = User.objects.filter(username__in=obj.operator).values_list("display_name", flat=True)
            return ", ".join(list(user_name_list))

        return ""

    def get_collaborator_users(self, obj):
        if not obj.collaborators:
            return []
        if not isinstance(obj.collaborators, list):
            return []
        operator_user_map = self.context.get("operator_user_map")
        if operator_user_map is not None:
            return [{"username": u, "display_name": operator_user_map.get(u, u)} for u in obj.collaborators]
        user_map = dict(User.objects.filter(username__in=obj.collaborators).values_list("username", "display_name"))
        return [{"username": u, "display_name": user_map.get(u, u)} for u in obj.collaborators]
